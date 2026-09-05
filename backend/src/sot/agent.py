from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.test import TestModel

from sot.domain.service import SOTService


@dataclass(frozen=True, slots=True)
class AgentDeps:
    user_id: str
    branch_id: UUID
    service: SOTService


def build_model(references: tuple[Model | str, ...]) -> Model | str:
    if not references:
        raise ValueError("at least one model is required")
    models = tuple(
        TestModel(call_tools=[]) if reference == "test" else reference
        for reference in references
    )
    if len(models) == 1:
        return models[0]
    return FallbackModel(models[0], *models[1:])


def build_agent(model: Model | str) -> Agent[AgentDeps, str]:
    agent = Agent(
        model,
        deps_type=AgentDeps,
        output_type=str,
        instructions=(
            "Help people examine a position, surface assumptions, and state "
            "concrete alternatives. Never claim that a draft changed the shared main "
            "document unless an authorized SOT tool confirms publication."
        ),
    )

    @agent.instructions
    def request_context(ctx: RunContext[AgentDeps]) -> str:
        return f"actor={ctx.deps.user_id} branch={ctx.deps.branch_id}"

    @agent.tool
    async def session_cite(
        ctx: RunContext[AgentDeps], turn_ids: list[UUID], summary: str
    ) -> dict[str, str]:
        """Preserve selected completed conversation turns as an immutable cite."""
        cite = await ctx.deps.service.create_cite(
            branch_id=ctx.deps.branch_id,
            actor_id=ctx.deps.user_id,
            turn_ids=tuple(turn_ids),
            summary=summary,
        )
        return {"citeId": str(cite.id)}

    @agent.tool
    async def sot_update(ctx: RunContext[AgentDeps], content: str) -> dict[str, str]:
        """Propose new shared SOT content without mutating the main revision."""
        proposal = await ctx.deps.service.create_proposal(
            branch_id=ctx.deps.branch_id,
            actor_id=ctx.deps.user_id,
            content=content,
        )
        return {"proposalId": str(proposal.id), "status": proposal.status.value}

    return agent


__all__ = ["AgentDeps", "build_agent", "build_model"]
