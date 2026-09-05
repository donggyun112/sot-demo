from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel


@dataclass(frozen=True, slots=True)
class AgentDeps:
    user_id: str
    branch_id: UUID
    service: object


def build_model(references: tuple[Model | str, ...]) -> Model | str:
    if not references:
        raise ValueError("at least one model is required")
    if len(references) == 1:
        return references[0]
    return FallbackModel(references[0], *references[1:])


def build_agent(model: Model | str) -> Agent[AgentDeps, str]:
    return Agent(
        model,
        deps_type=AgentDeps,
        output_type=str,
        instructions=(
            "Help people examine a position, surface assumptions, and state "
            "concrete alternatives. Never claim that a draft changed the shared main "
            "document unless an authorized SOT tool confirms publication."
        ),
    )


__all__ = ["AgentDeps", "build_agent", "build_model"]
