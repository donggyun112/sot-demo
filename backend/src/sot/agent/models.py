from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.test import TestModel

from sot.agent.deps import AgentDeps
from sot.agent.prompts import INSTRUCTIONS, request_context


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
    """Build the application-lifetime definition; every run supplies fresh deps."""
    agent = Agent(
        model, deps_type=AgentDeps, output_type=str, instructions=INSTRUCTIONS
    )
    agent.instructions(request_context)
    return agent
