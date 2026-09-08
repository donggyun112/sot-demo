from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field

import pytest
from ag_ui.core import BaseEvent, RunErrorEvent
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from sot.agent.api import ServerOnlyAGUIAdapter
from sot.agent.application import AgentRunPreparer, CompletedRunWriter, PreparedAgentRun
from sot.agent.messages import turns_to_model_messages
from sot.agent.models import build_agent
from sot.consensus.application import CreateProposal, ProposalSources
from sot.consensus.domain import Proposal, ProposalStatus
from sot.identity.contracts import Actor
from sot.session.application import (
    AppendCompletedTurns,
    ApplyCuration,
    BranchAccess,
    BundleAccess,
    RequiredApprovers,
    SessionAccess,
    VersionGuard,
)
from sot.session.contracts import NewTurn
from sot.consensus.contracts import DocumentEdit
from sot.session.domain import JoinTurns
from sot.shared.ids import BranchId, ProposalId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from tests.agent.test_agui import agui_payload, message
from tests.session.test_application import FixedClock, creator, setup
from tests.session.test_curation import CuratedMemory


@dataclass
class AgentProductStore(CuratedMemory):
    proposals: dict[ProposalId, Proposal] = field(default_factory=dict)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        snapshot = deepcopy(self.proposals)
        try:
            async with super().transaction() as tx:
                yield tx
        except BaseException:
            self.proposals = snapshot
            raise

    async def find(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
    ) -> Proposal | None:
        self.check(tx)
        proposal = self.proposals.get(proposal_id)
        return (
            deepcopy(proposal)
            if proposal is not None and proposal.workspace_id == workspace_id
            else None
        )

    async def get_for_update(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
    ) -> Proposal | None:
        return await self.find(tx, workspace_id, proposal_id)

    async def add(self, tx: TransactionContext, proposal: Proposal) -> None:
        self.check(tx)
        assert proposal.id not in self.proposals
        self.proposals[proposal.id] = deepcopy(proposal)

    async def save(self, tx: TransactionContext, proposal: Proposal) -> None:
        self.check(tx)
        assert proposal.id in self.proposals
        self.proposals[proposal.id] = deepcopy(proposal)


@dataclass(frozen=True)
class AgentProductHarness:
    store: AgentProductStore
    preparer: AgentRunPreparer
    writer: CompletedRunWriter
    actor: Actor
    workspace_id: WorkspaceId
    branch_id: BranchId


async def product_harness() -> AgentProductHarness:
    original, actor, workspace_id, document_id = setup()
    store = AgentProductStore()
    store.__dict__.update(original.__dict__)
    created = await creator(store).execute(actor, workspace_id, document_id)
    branch = store.branches[workspace_id, created.branch_id]
    for version in range(4):
        branch.append_completed(
            expected_version=version,
            messages=(
                NewTurn("user", f"question {version}"),
                NewTurn("assistant", f"answer {version}"),
            ),
            now=FixedClock().now(),
        )

    session_access = SessionAccess(store, store)
    branch_access = BranchAccess(store, session_access, store)
    cite_creator = ApplyCuration(
        store, store, branch_access, lambda: store, FixedClock()
    )
    bundles = BundleAccess(store, session_access, store)
    proposal_creator = CreateProposal(
        store,
        ProposalSources(
            session_access,
            store,
            bundles,
            RequiredApprovers(store),
            store,
        ),
        branch_access,
        VersionGuard(store, branch_access),
        lambda: store,
        FixedClock(),
    )
    return AgentProductHarness(
        store,
        AgentRunPreparer(
            store,
            branch_access,
            lambda: store,
            cite_creator,
            proposal_creator,
        ),
        CompletedRunWriter(
            AppendCompletedTurns(store, branch_access, lambda: store, FixedClock())
        ),
        actor,
        workspace_id,
        created.branch_id,
    )


def adapter(model: FunctionModel, prompt: str) -> ServerOnlyAGUIAdapter:
    run_input = ServerOnlyAGUIAdapter.build_run_input(
        json.dumps(
            agui_payload(messages=[message("user", prompt, suffix=prompt)])
        ).encode()
    )
    return ServerOnlyAGUIAdapter(
        build_agent(model), run_input, manage_system_prompt="server"
    )


async def run_events(
    prepared: PreparedAgentRun,
    current: ServerOnlyAGUIAdapter,
    writer: CompletedRunWriter,
) -> list[BaseEvent]:
    return [
        event
        async for event in current.run_server_stream(
            message_history=turns_to_model_messages(prepared.canonical_turns),
            deps=prepared.deps,
            completed_run_writer=writer,
        )
    ]


@pytest.mark.asyncio
async def test_tools_advance_one_lineage_before_final_transcript_commit() -> None:
    harness = await product_harness()
    winner = await harness.preparer.prepare(
        actor=harness.actor,
        workspace_id=harness.workspace_id,
        branch_id=harness.branch_id,
    )
    branch = harness.store.branches[harness.workspace_id, harness.branch_id]
    selected = [str(branch.turns[0].id), str(branch.turns[1].id)]

    async def two_tools(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        returned = [
            part
            for current in messages
            if isinstance(current, ModelRequest)
            for part in current.parts
            if isinstance(part, ToolReturnPart)
        ]
        if returned:
            yield "winner complete"
            return
        yield {
            0: DeltaToolCall(
                "session_cite",
                json.dumps({"turn_ids": selected, "summary": "public rationale"}),
                tool_call_id="cite-1",
            ),
            1: DeltaToolCall(
                "sot_update",
                json.dumps({"edits": [{"find": "", "replace": "winner proposal"}]}),
                tool_call_id="proposal-1",
            ),
        }

    events = await run_events(
        winner,
        adapter(FunctionModel(stream_function=two_tools), "winner request"),
        harness.writer,
    )

    assert [event.type.value for event in events][-1] == "RUN_FINISHED"
    assert winner.lineage.expected_version == branch.version == 7
    assert len(harness.store.operations[harness.workspace_id, harness.branch_id]) == 1
    operation = harness.store.operations[harness.workspace_id, harness.branch_id][
        0
    ].operation
    assert isinstance(operation, JoinTurns)
    assert operation.content == "public rationale"
    proposal = next(iter(harness.store.proposals.values()))
    assert proposal.current_version.edits == (DocumentEdit("", "winner proposal"),)
    assert proposal.status is ProposalStatus.OPEN

    completed = branch.turns[-6:]
    assert [turn.role for turn in completed] == [
        "user",
        "tool",
        "tool",
        "tool",
        "tool",
        "assistant",
    ]
    returned_versions = [
        json.loads(turn.content)["result"]["branchVersion"]
        for turn in completed
        if turn.role == "tool" and json.loads(turn.content)["kind"] == "return"
    ]
    assert returned_versions == [5, 6]


@pytest.mark.asyncio
async def test_competing_run_emits_version_conflict_without_failed_side_effect() -> (
    None
):
    harness = await product_harness()
    winner = await harness.preparer.prepare(
        actor=harness.actor,
        workspace_id=harness.workspace_id,
        branch_id=harness.branch_id,
    )
    loser = await harness.preparer.prepare(
        actor=harness.actor,
        workspace_id=harness.workspace_id,
        branch_id=harness.branch_id,
    )
    branch = harness.store.branches[harness.workspace_id, harness.branch_id]
    selected = [str(branch.turns[0].id), str(branch.turns[1].id)]

    async def winning_cite(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        if any(
            isinstance(part, ToolReturnPart)
            for current in messages
            if isinstance(current, ModelRequest)
            for part in current.parts
        ):
            yield "winner complete"
            return
        yield {
            0: DeltaToolCall(
                "session_cite",
                json.dumps({"turn_ids": selected, "summary": "winner"}),
                tool_call_id="winner-cite",
            )
        }

    winner_events = await run_events(
        winner,
        adapter(FunctionModel(stream_function=winning_cite), "winner request"),
        harness.writer,
    )
    assert [event.type.value for event in winner_events][-1] == "RUN_FINISHED"
    committed_turns = branch.turns
    committed_operations = deepcopy(harness.store.operations)
    committed_proposals = deepcopy(harness.store.proposals)
    committed_version = branch.version

    async def losing_update(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield {
            0: DeltaToolCall(
                "sot_update",
                json.dumps({"edits": [{"find": "", "replace": "loser proposal"}]}),
                tool_call_id="loser-proposal",
            )
        }

    loser_events = await run_events(
        loser,
        adapter(FunctionModel(stream_function=losing_update), "loser request"),
        harness.writer,
    )

    event_types = [event.type.value for event in loser_events]
    assert "RUN_ERROR" in event_types
    assert "RUN_FINISHED" not in event_types
    error = next(event for event in loser_events if isinstance(event, RunErrorEvent))
    assert error.code == "version_conflict"
    assert loser.lineage.expected_version == 4
    assert branch.version == committed_version == 6
    assert branch.turns == committed_turns
    assert harness.store.operations == committed_operations
    assert harness.store.proposals == committed_proposals
    assert all(
        proposal.current_version.edits != (DocumentEdit("", "loser proposal"),)
        for proposal in harness.store.proposals.values()
    )
