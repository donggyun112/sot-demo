from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic_ai import RunContext
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

from sot.agent.deps import AgentDeps, BranchLineage
from sot.agent.models import build_agent
from sot.agent.tools import session_cite, sot_update
from sot.identity.contracts import Actor
from sot.session.contracts import BranchMutationResult, TurnId
from sot.session.domain import VersionConflict
from sot.shared.ids import BranchId, UserId, WorkspaceId


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
        content: str,
    ) -> BranchMutationResult:
        self.calls.append(
            {
                "actor": actor,
                "workspace_id": workspace_id,
                "branch_id": branch_id,
                "expected_branch_version": expected_branch_version,
                "content": content,
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

    result = await sot_update(tool_context(deps), "candidate main")

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
            "content": "candidate main",
        }
    ]


@pytest.mark.asyncio
async def test_failed_tool_command_does_not_advance_lineage() -> None:
    creator = RecordingProposalCreator(
        BranchMutationResult(uuid4(), 5), failure=VersionConflict()
    )
    deps = agent_deps(proposal_creator=creator)

    with pytest.raises(VersionConflict):
        await sot_update(tool_context(deps), "loser proposal")

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
    assert set(schemas) == {"session_cite", "sot_update"}
    assert set(schemas["session_cite"]["properties"]) == {"turn_ids", "summary"}
    assert set(schemas["sot_update"]["properties"]) == {"content"}
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
