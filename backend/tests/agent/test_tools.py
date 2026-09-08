from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from sot.agent.deps import AgentDeps, BranchLineage, DocumentSnapshot
from sot.agent.models import build_agent
from sot.agent.tools import session_cite, sot_read, sot_update
from sot.consensus.contracts import DocumentEdit
from sot.document.contracts import DocumentSummary, DocumentView, RevisionView
from sot.document.domain import RevisionId
from sot.identity.contracts import Actor
from sot.session.contracts import BranchMutationResult, TurnId
from sot.session.domain import VersionConflict
from sot.shared.errors import InvalidInput
from sot.shared.ids import BranchId, DocumentId, UserId, WorkspaceId


@dataclass
class RecordingCiteCreator:
    result: BranchMutationResult
    calls: list[dict[str, object]] = field(default_factory=list)

    async def create_from_agent(
        self,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_branch_version: int,
        turn_ids: tuple[TurnId, ...],
        summary: str,
    ) -> BranchMutationResult:
        self.calls.append(
            {
                "actor": actor,
                "workspace_id": workspace_id,
                "branch_id": branch_id,
                "expected_branch_version": expected_branch_version,
                "turn_ids": turn_ids,
                "summary": summary,
            }
        )
        return self.result


@dataclass
class RecordingProposalCreator:
    result: BranchMutationResult
    failure: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    async def create_from_agent(
        self,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_branch_version: int,
        edits: tuple[DocumentEdit, ...],
    ) -> BranchMutationResult:
        self.calls.append(
            {
                "actor": actor,
                "workspace_id": workspace_id,
                "branch_id": branch_id,
                "expected_branch_version": expected_branch_version,
                "edits": edits,
            }
        )
        if self.failure is not None:
            raise self.failure
        return self.result


def agent_deps(
    *,
    expected_branch_version: int = 4,
    cite_creator: RecordingCiteCreator | None = None,
    proposal_creator: RecordingProposalCreator | None = None,
) -> AgentDeps:
    return AgentDeps(
        Actor(UserId(uuid4())),
        WorkspaceId(uuid4()),
        BranchId(uuid4()),
        BranchLineage(expected_branch_version),
        cite_creator
        or RecordingCiteCreator(
            BranchMutationResult(uuid4(), expected_branch_version + 1)
        ),
        proposal_creator
        or RecordingProposalCreator(
            BranchMutationResult(uuid4(), expected_branch_version + 1)
        ),
    )


def tool_context(deps: AgentDeps) -> RunContext[AgentDeps]:
    return cast(RunContext[AgentDeps], SimpleNamespace(deps=deps))


@pytest.mark.asyncio
async def test_session_cite_routes_server_context_and_advances_lineage() -> None:
    cite_id = uuid4()
    creator = RecordingCiteCreator(BranchMutationResult(cite_id, 5))
    deps = agent_deps(cite_creator=creator)
    turn_ids = (uuid4(), uuid4())

    result = await session_cite(tool_context(deps), turn_ids, "public rationale")

    assert result == {"citeId": str(cite_id), "branchVersion": 5}
    assert deps.lineage.expected_version == 5
    assert creator.calls == [
        {
            "actor": deps.actor,
            "workspace_id": deps.workspace_id,
            "branch_id": deps.branch_id,
            "expected_branch_version": 4,
            "turn_ids": turn_ids,
            "summary": "public rationale",
        }
    ]


@pytest.mark.asyncio
async def test_sot_update_returns_open_proposal_and_advances_lineage() -> None:
    proposal_id = uuid4()
    creator = RecordingProposalCreator(BranchMutationResult(proposal_id, 5))
    deps = agent_deps(proposal_creator=creator)

    result = await sot_update(
        tool_context(deps), [{"find": "", "replace": "candidate main"}]
    )

    assert result == {
        "proposalId": str(proposal_id),
        "status": "open",
        "branchVersion": 5,
    }
    assert deps.lineage.expected_version == 5
    assert creator.calls == [
        {
            "actor": deps.actor,
            "workspace_id": deps.workspace_id,
            "branch_id": deps.branch_id,
            "expected_branch_version": 4,
            "edits": (DocumentEdit("", "candidate main"),),
        }
    ]


@pytest.mark.asyncio
async def test_failed_tool_command_does_not_advance_lineage() -> None:
    creator = RecordingProposalCreator(
        BranchMutationResult(uuid4(), 5), failure=VersionConflict()
    )
    deps = agent_deps(proposal_creator=creator)

    with pytest.raises(VersionConflict):
        await sot_update(
            tool_context(deps), [{"find": "", "replace": "loser proposal"}]
        )

    assert deps.lineage.expected_version == 4


@pytest.mark.asyncio
async def test_an_update_the_model_wrote_wrong_comes_back_as_a_retry() -> None:
    """An anchor that misses, or an update too long to review, is the model's
    to fix. Killing the run instead would leave the person with nothing."""
    creator = RecordingProposalCreator(
        BranchMutationResult(uuid4(), 5),
        failure=InvalidInput(
            "proposal_content_too_many_lines", "Proposal content is 2000 lines"
        ),
    )
    deps = agent_deps(proposal_creator=creator)

    with pytest.raises(ModelRetry) as retried:
        await sot_update(tool_context(deps), [{"find": "", "replace": "a\nb"}])

    assert "2000 lines" in str(retried.value)
    assert deps.lineage.expected_version == 4


@pytest.mark.asyncio
async def test_agent_tools_expose_only_product_inputs() -> None:
    seen: list[AgentInfo] = []

    async def answer(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info)
        return ModelResponse(parts=[TextPart("done")])

    await build_agent(FunctionModel(answer)).run("inspect tools", deps=agent_deps())

    schemas = {
        tool.name: tool.parameters_json_schema for tool in seen[0].function_tools
    }
    assert set(schemas) == {"session_cite", "sot_read", "sot_update"}
    assert set(schemas["session_cite"]["properties"]) == {"turn_ids", "summary"}
    assert set(schemas["sot_update"]["properties"]) == {"edits"}
    # Reading takes nothing: which document is the run's business, not the
    # model's, and a document id from a prompt would be a way out of it.
    assert schemas["sot_read"]["properties"] == {}
    assert all(schema["additionalProperties"] is False for schema in schemas.values())
    assert not {
        "actor",
        "user_id",
        "workspace_id",
        "branch_id",
        "expected_version",
        "expected_branch_version",
    } & set().union(*(schema["properties"] for schema in schemas.values()))


@pytest.mark.asyncio
async def test_native_uuid_validation_retries_before_calling_command() -> None:
    turn_id = uuid4()
    creator = RecordingCiteCreator(BranchMutationResult(uuid4(), 5))
    deps = agent_deps(cite_creator=creator)
    retry_seen: RetryPromptPart | None = None

    async def call_tool(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        nonlocal retry_seen
        request_parts = [
            part
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
        ]
        returned = next(
            (
                part
                for part in request_parts
                if isinstance(part, ToolReturnPart)
                and part.tool_call_id == "cite-valid"
            ),
            None,
        )
        retry = next(
            (
                part
                for part in request_parts
                if isinstance(part, RetryPromptPart)
                and part.tool_call_id == "cite-invalid"
            ),
            None,
        )
        if returned is not None:
            return ModelResponse(parts=[TextPart("done")])
        if retry is not None:
            retry_seen = retry
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "session_cite",
                        {"turn_ids": [str(turn_id)], "summary": "valid"},
                        "cite-valid",
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "session_cite",
                    {"turn_ids": ["not-a-uuid"], "summary": "invalid"},
                    "cite-invalid",
                )
            ]
        )

    result = await build_agent(FunctionModel(call_tool)).run("cite", deps=deps)

    assert result.output == "done"
    assert retry_seen is not None
    assert creator.calls[0]["turn_ids"] == (turn_id,)
    assert len(creator.calls) == 1
    assert deps.lineage.expected_version == 5


@dataclass
class RecordingDocuments:
    view: DocumentView
    calls: list[tuple[Actor, WorkspaceId, DocumentId]] = field(default_factory=list)

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> DocumentView:
        self.calls.append((actor, workspace_id, document_id))
        return self.view


def document_view_at(revision: int, content: str) -> DocumentView:
    document_id = DocumentId(uuid4())
    workspace_id = WorkspaceId(uuid4())
    return DocumentView(
        DocumentSummary(document_id, workspace_id, "Policy", RevisionId(uuid4()), 1),
        RevisionView(
            RevisionId(uuid4()),
            workspace_id,
            document_id,
            revision,
            content,
            None,
            UserId(uuid4()),
            datetime(2026, 9, 8, tzinfo=UTC),
            (),
        ),
    )


@pytest.mark.asyncio
async def test_reading_returns_the_document_as_it_stands_now() -> None:
    """The snapshot the run started with goes stale the moment someone merges,
    and it is cut when the document is long. This is how the agent catches up."""
    view = document_view_at(4, "# Rate limits\n\nTen per second.")
    documents = RecordingDocuments(view)
    deps = agent_deps()
    deps = replace(
        deps,
        document=DocumentSnapshot.of(view.document.id, "Policy", 3, "stale"),
        document_reader=documents,
    )

    result = await sot_read(tool_context(deps))

    assert result == {
        "documentId": str(view.document.id),
        "title": "Policy",
        "revision": 4,
        "content": "# Rate limits\n\nTen per second.",
    }
    # Whose read it is, and in which workspace, comes from the run.
    assert documents.calls == [(deps.actor, deps.workspace_id, view.document.id)]


@pytest.mark.asyncio
async def test_reading_a_session_with_no_document_says_so_and_retries() -> None:
    deps = agent_deps()

    with pytest.raises(ModelRetry) as refused:
        await sot_read(tool_context(deps))

    assert "not attached to a document" in str(refused.value)
