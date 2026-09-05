from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ag_ui.core import RunAgentInput
from pydantic import field_validator
from pydantic_ai import Agent, DeferredToolRequests, RunContext
from pydantic_ai.models import Model
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent_core.context import LoadedAgentContext
from agent_core.identity import ExecutionIdentity
from agent_core.prompt import PromptAssembly
from agent_core.tools import ToolRegistry


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        populate_by_name=True,
        extra="ignore",
    )

    name: str
    description: str
    system_prompt_file: Path
    prompt_revision: str
    models: tuple[str, ...]

    @field_validator("models")
    @classmethod
    def validate_models(cls, models: tuple[str, ...]) -> tuple[str, ...]:
        if not models:
            raise ValueError("at least one model is required")
        if len(models) != len(set(models)):
            raise ValueError("model references must be unique")
        for model_ref in models:
            provider, separator, model_name = model_ref.partition(":")
            if not separator or not provider.strip() or not model_name.strip():
                raise ValueError("models must use provider:model format")
        return models


@dataclass(frozen=True, slots=True)
class AgentRunDeps:
    identity: ExecutionIdentity
    instructions: str
    selected_tool_names: tuple[str, ...]


class AgentRunAssembly:
    def __init__(
        self,
        *,
        settings: AgentSettings,
        registry: ToolRegistry,
        prompt_assembly: PromptAssembly | None = None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._prompt_assembly = prompt_assembly or PromptAssembly()
        self._base_prompt = settings.system_prompt_file.read_text(encoding="utf-8")

    async def assemble(
        self,
        *,
        request: RunAgentInput,
        identity: ExecutionIdentity,
        loaded_context: LoadedAgentContext,
    ) -> AgentRunDeps:
        selected_tools = self._registry.select(request.tools)
        instructions = self._prompt_assembly.assemble(
            base_prompt=self._base_prompt,
            selected_tools=selected_tools,
            loaded_context=loaded_context,
        )
        return AgentRunDeps(
            identity=identity,
            instructions=instructions,
            selected_tool_names=selected_tools.names,
        )


def _dynamic_instructions(ctx: RunContext[AgentRunDeps]) -> str:
    return ctx.deps.instructions


def _selected_tool(ctx: RunContext[AgentRunDeps], tool: object) -> bool:
    name = getattr(tool, "name", None)
    return isinstance(name, str) and name in ctx.deps.selected_tool_names


def build_deployment_agent(
    *,
    settings: AgentSettings,
    registry: ToolRegistry,
    model: Model,
) -> Agent[AgentRunDeps, str | DeferredToolRequests]:
    return Agent(
        model,
        name=settings.name,
        description=settings.description,
        deps_type=AgentRunDeps,
        output_type=[str, DeferredToolRequests],
        toolsets=[registry.as_toolset().filtered(_selected_tool)],
        instructions=_dynamic_instructions,
    )


__all__ = [
    "AgentRunAssembly",
    "AgentRunDeps",
    "AgentSettings",
    "build_deployment_agent",
]
