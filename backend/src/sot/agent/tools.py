from typing import Literal, TypedDict

from pydantic_ai import RunContext

from sot.agent.deps import AgentDeps
from sot.session.contracts import TurnId


class SessionCiteResult(TypedDict):
    citeId: str
    branchVersion: int


class SOTUpdateResult(TypedDict):
    proposalId: str
    status: Literal["open"]
    branchVersion: int


async def session_cite(
    ctx: RunContext[AgentDeps], turn_ids: tuple[TurnId, ...], summary: str
) -> SessionCiteResult:
    """Preserve selected completed conversation turns as an immutable cite."""
    deps = ctx.deps
    result = await deps.cite_creator.create_from_agent(
        actor=deps.actor,
        workspace_id=deps.workspace_id,
        branch_id=deps.branch_id,
        expected_branch_version=deps.lineage.expected_version,
        turn_ids=turn_ids,
        summary=summary,
    )
    deps.lineage.advance_to(result.branch_version)
    return {"citeId": str(result.resource_id), "branchVersion": result.branch_version}


async def sot_update(ctx: RunContext[AgentDeps], content: str) -> SOTUpdateResult:
    """Create an open proposal for shared SOT content without publishing main."""
    deps = ctx.deps
    result = await deps.proposal_creator.create_from_agent(
        actor=deps.actor,
        workspace_id=deps.workspace_id,
        branch_id=deps.branch_id,
        expected_branch_version=deps.lineage.expected_version,
        content=content,
    )
    deps.lineage.advance_to(result.branch_version)
    return {
        "proposalId": str(result.resource_id),
        "status": "open",
        "branchVersion": result.branch_version,
    }


__all__ = ["session_cite", "sot_update"]
