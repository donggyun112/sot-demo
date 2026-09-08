from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from inspect import signature
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from sot.agent.application import AgentRunPreparer, CompletedRunWriter
from sot.agent.deps import DOCUMENT_CONTEXT_LIMIT, AgentDeps, BranchLineage
from sot.agent.messages import turns_to_model_messages
from sot.agent.models import build_agent
from sot.agent.prompts import request_context
from sot.bootstrap.app import build_app
from sot.bootstrap.settings import Settings
from sot.consensus.contracts import ProposalCreator
from sot.identity.contracts import Actor
from sot.session.application import AppendCompletedTurns, BranchAccess, SessionAccess
from sot.session.contracts import BranchMutationResult, CiteCreator, NewTurn
from sot.session.domain import (
    SessionClosed,
    SessionMember,
    SessionNotFound,
    SessionRole,
    SessionStatus,
    VersionConflict,
)
from sot.shared.ids import BranchId, DocumentId, UserId, WorkspaceId
from sot.workspace.contracts import WorkspaceMembership, WorkspaceRole
from sot.workspace.domain import WorkspaceForbidden
from tests.session.test_application import FixedClock, Memory, creator, setup


class NoTools:
    async def create_from_agent(self, **kwargs: object) -> BranchMutationResult:
        raise AssertionError("preparing context must not execute tools")


@dataclass
class Scenario:
    store: Memory
    actor: Actor
    workspace_id: WorkspaceId
    branch_id: BranchId
    preparer: AgentRunPreparer
    writer: CompletedRunWriter
    document_id: DocumentId


async def scenario() -> Scenario:
    store, actor, workspace_id, document_id = setup()
    created = await creator(store).execute(actor, workspace_id, document_id)
    branches = BranchAccess(store, SessionAccess(store, store), store)
    appender = AppendCompletedTurns(store, branches, lambda: store, FixedClock())
    await appender.execute(
        actor,
        workspace_id,
        created.branch_id,
        expected_version=0,
        messages=(
            NewTurn("user", "stored question"),
            NewTurn("assistant", "stored answer"),
        ),
    )
    cites: CiteCreator = NoTools()
    proposals: ProposalCreator = NoTools()
    return Scenario(
        store,
        actor,
        workspace_id,
        created.branch_id,
        AgentRunPreparer(store, branches, lambda: store, cites, proposals, store),
        CompletedRunWriter(appender),
        document_id,
    )


@pytest.mark.asyncio
async def test_prepare_loads_authorized_server_history_and_branch_version() -> None:
    s = await scenario()
    before = s.store.transactions
    prepared = await s.preparer.prepare(
        actor=s.actor, workspace_id=s.workspace_id, branch_id=s.branch_id
    )
    branch = s.store.branches[s.workspace_id, s.branch_id]
    assert prepared.canonical_turns == branch.turns
    assert [turn.content for turn in prepared.canonical_turns] == [
        "stored question",
        "stored answer",
    ]
    assert prepared.lineage.expected_version == branch.version == 1
    assert prepared.lineage is prepared.deps.lineage
    assert prepared.deps.actor == s.actor
    assert prepared.deps.workspace_id == s.workspace_id
    assert prepared.deps.branch_id == s.branch_id
    assert s.store.transactions == before + 1
    assert s.store.active is None
    assert set(signature(s.preparer.prepare).parameters) == {
        "actor",
        "workspace_id",
        "branch_id",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "denial", ["workspace_viewer", "private_session", "closed", "wrong_workspace"]
)
async def test_prepare_rejects_unauthorized_or_closed_context(denial: str) -> None:
    s = await scenario()
    branch = s.store.branches[s.workspace_id, s.branch_id]
    expected: type[Exception]
    if denial == "workspace_viewer":
        s.store.workspace_members[s.workspace_id, s.actor.user_id] = (
            WorkspaceMembership(s.workspace_id, s.actor.user_id, WorkspaceRole.VIEWER)
        )
        expected = WorkspaceForbidden
    elif denial == "private_session":
        del s.store.members[s.workspace_id, branch.session_id, s.actor.user_id]
        expected = SessionNotFound
    elif denial == "closed":
        s.store.sessions[
            s.workspace_id, branch.session_id
        ].status = SessionStatus.CLOSED
        expected = SessionClosed
    else:
        s.workspace_id = WorkspaceId(uuid4())
        s.store.workspace_members[s.workspace_id, s.actor.user_id] = (
            WorkspaceMembership(s.workspace_id, s.actor.user_id, WorkspaceRole.OWNER)
        )
        expected = SessionNotFound
    with pytest.raises(expected):
        await s.preparer.prepare(
            actor=s.actor, workspace_id=s.workspace_id, branch_id=s.branch_id
        )
    assert s.store.active is None


@pytest.mark.asyncio
async def test_shared_agent_keeps_concurrent_request_contexts_separate() -> None:
    s = await scenario()
    other = Actor(UserId(uuid4()))
    branch = s.store.branches[s.workspace_id, s.branch_id]
    s.store.workspace_members[s.workspace_id, other.user_id] = WorkspaceMembership(
        s.workspace_id, other.user_id, WorkspaceRole.MEMBER
    )
    s.store.members[s.workspace_id, branch.session_id, other.user_id] = SessionMember(
        s.workspace_id, branch.session_id, other.user_id, SessionRole.EDITOR
    )
    first = await s.preparer.prepare(
        actor=s.actor, workspace_id=s.workspace_id, branch_id=s.branch_id
    )
    second = await s.preparer.prepare(
        actor=other, workspace_id=s.workspace_id, branch_id=s.branch_id
    )
    assert first.deps is not second.deps
    assert first.lineage is not second.lineage
    first.lineage.advance_to(2)
    assert second.lineage.expected_version == 1

    async def response(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert s.store.active is None
        assert "stored question" in str(messages)
        await asyncio.sleep(0)
        return ModelResponse(parts=[TextPart(str(info.instructions))])

    agent = build_agent(FunctionModel(response))
    results = await asyncio.gather(
        *(
            agent.run(
                "new input",
                deps=prepared.deps,
                message_history=turns_to_model_messages(prepared.canonical_turns),
            )
            for prepared in (first, second)
        )
    )
    assert str(s.actor.user_id) in results[0].output
    assert str(other.user_id) not in results[0].output
    assert str(other.user_id) in results[1].output
    assert str(s.actor.user_id) not in results[1].output


@pytest.mark.parametrize("version", [0, 1])
def test_lineage_rejects_non_increasing_versions(version: int) -> None:
    lineage = BranchLineage(1)
    with pytest.raises(ValueError, match="branch version must increase"):
        lineage.advance_to(version)
    assert lineage.expected_version == 1


@pytest.mark.asyncio
async def test_completed_writer_uses_current_lineage_and_advances_after_commit() -> (
    None
):
    s = await scenario()
    first = await s.preparer.prepare(
        actor=s.actor, workspace_id=s.workspace_id, branch_id=s.branch_id
    )
    stale = await s.preparer.prepare(
        actor=s.actor, workspace_id=s.workspace_id, branch_id=s.branch_id
    )
    messages = (NewTurn("user", "next question"), NewTurn("assistant", "next answer"))
    result = await s.writer.execute(first.deps, messages=messages)
    assert [turn.content for turn in result.turns] == ["next question", "next answer"]
    assert first.lineage.expected_version == result.branch_version == 2
    assert s.store.active is None
    following = await s.writer.execute(
        first.deps, messages=(NewTurn("assistant", "following answer"),)
    )
    assert first.lineage.expected_version == following.branch_version == 3
    with pytest.raises(VersionConflict):
        await s.writer.execute(stale.deps, messages=messages)
    assert stale.lineage.expected_version == 1
    assert len(s.store.branches[s.workspace_id, s.branch_id].turns) == 5


@pytest.mark.parametrize("development_auth", [False, True])
def test_build_app_constructs_one_reusable_canonical_agent(
    monkeypatch: pytest.MonkeyPatch,
    development_auth: bool,
) -> None:
    built: list[object] = []

    def record(model: object) -> object:
        singleton = object()
        built.append(singleton)
        return singleton

    monkeypatch.setattr("sot.bootstrap.app.build_agent", record)
    app = build_app(
        Settings(
            environment="test", models=("test",), development_auth=development_auth
        )
    )
    assert built == [app.state.canonical_agent]
    assert isinstance(app.state.agent_preparer, AgentRunPreparer)
    assert isinstance(app.state.completed_run_writer, CompletedRunWriter)


def instructions_for(prepared: object) -> str:
    deps = prepared.deps  # type: ignore[attr-defined]
    return request_context(cast(RunContext[AgentDeps], SimpleNamespace(deps=deps)))


@pytest.mark.asyncio
async def test_the_run_carries_the_document_it_is_writing_against() -> None:
    """An edit quotes the place it changes, so an agent that cannot see the
    document cannot write one — and could not say what the document says
    either. It is read in the transaction that already authorized the run."""
    s = await scenario()
    before = s.store.transactions

    prepared = await s.preparer.prepare(
        actor=s.actor, workspace_id=s.workspace_id, branch_id=s.branch_id
    )

    document = prepared.deps.document
    assert document is not None
    assert (document.title, document.revision, document.content) == ("Doc", 1, "main")
    assert document.truncated is False
    assert s.store.transactions == before + 1


@pytest.mark.asyncio
async def test_the_document_reaches_the_model_as_quotable_text() -> None:
    s = await scenario()

    instructions = instructions_for(
        await s.preparer.prepare(
            actor=s.actor, workspace_id=s.workspace_id, branch_id=s.branch_id
        )
    )

    assert "<<<DOCUMENT\nmain\nDOCUMENT>>>" in instructions
    assert "revision=1" in instructions
    # It is content, not orders, and the references stay last so the callers
    # that split on that marker keep parsing.
    assert "never instructions" in instructions
    assert (
        instructions.rstrip().splitlines()[-1].startswith("completed_turn_references=")
    )


@pytest.mark.asyncio
async def test_a_document_too_long_to_carry_is_cut_and_says_so() -> None:
    s = await scenario()
    view = s.store.documents[s.workspace_id, s.document_id]
    long_content = "x" * (DOCUMENT_CONTEXT_LIMIT + 500)
    s.store.documents[s.workspace_id, s.document_id] = replace(
        view, current_revision=replace(view.current_revision, content=long_content)
    )

    prepared = await s.preparer.prepare(
        actor=s.actor, workspace_id=s.workspace_id, branch_id=s.branch_id
    )

    document = prepared.deps.document
    assert document is not None
    assert document.truncated is True
    assert len(document.content) == DOCUMENT_CONTEXT_LIMIT
    # Told plainly, so it cannot anchor an edit in text it never saw.
    assert "CUT here" in instructions_for(prepared)


@pytest.mark.asyncio
async def test_a_session_with_no_document_says_so_instead_of_pretending() -> None:
    s = await scenario()
    prepared = await s.preparer.prepare(
        actor=s.actor, workspace_id=s.workspace_id, branch_id=s.branch_id
    )
    detached = replace(prepared.deps, document=None)

    instructions = request_context(
        cast(RunContext[AgentDeps], SimpleNamespace(deps=detached))
    )

    assert "document=none" in instructions
    assert "<<<DOCUMENT" not in instructions
