from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ag_ui.core import Tool
from pydantic_ai import Tool as PydanticTool
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.toolsets import FunctionToolset
from semora import Continue, ControlPlane, Ctx, Deny, ResumeInput, Suspend

type ToolResult = dict[str, Any]
type ToolExecutor = Callable[[Any], Awaitable[ToolResult]]
type ToolSelectionErrorCode = Literal["invalid_tool_descriptor"]


class ToolSelectionError(ValueError):
    def __init__(self, code: ToolSelectionErrorCode, tool_name: str) -> None:
        super().__init__(code)
        self.code = code
        self.tool_name = tool_name


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    name: str
    description: str
    parameters: dict[str, Any]
    instructions: str
    execute: ToolExecutor
    requires_approval: bool = False

    def descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class SelectedTools:
    def __init__(self, tools: Sequence[RegisteredTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @property
    def instructions(self) -> tuple[str, ...]:
        return tuple(tool.instructions for tool in self._tools.values())

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    async def execute(self, name: str, call_id: str, arguments: Any) -> ToolResult:
        del call_id
        tool = self._tools.get(name)
        if tool is None:
            return {"type": "error", "error": f"unknown tool: {name}"}
        return await tool.execute(arguments)

    def get(self, name: str) -> dict[str, Any] | None:
        tool = self._tools.get(name)
        return None if tool is None else tool.descriptor()

    def list(self) -> list[dict[str, Any]]:
        return [tool.descriptor() for tool in self._tools.values()]


class ToolRegistry:
    def __init__(self, tools: Iterable[RegisteredTool] = ()) -> None:
        registered: dict[str, RegisteredTool] = {}
        for tool in tools:
            if tool.name in registered:
                raise ValueError(f"duplicate registered tool: {tool.name}")
            registered[tool.name] = tool
        self._tools = registered

    def registered(self) -> tuple[RegisteredTool, ...]:
        return tuple(self._tools.values())

    def approval_required(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool is not None and tool.requires_approval

    def as_toolset(self) -> FunctionToolset[Any]:
        toolset: FunctionToolset[Any] = FunctionToolset(id="agent-server-tools-v1")
        for registered in self.registered():

            async def execute(
                _registered: RegisteredTool = registered,
                **arguments: Any,
            ) -> ToolResult:
                return await _registered.execute(arguments)

            tool = PydanticTool.from_schema(
                execute,
                name=registered.name,
                description=registered.description,
                json_schema=registered.parameters,
            )
            toolset.add_tool(tool)
        return toolset

    def select(self, requested: Sequence[Tool]) -> SelectedTools:
        selected: list[RegisteredTool] = []
        seen: set[str] = set()
        for descriptor in requested:
            if descriptor.name in seen or descriptor.name not in self._tools:
                raise ToolSelectionError("invalid_tool_descriptor", descriptor.name)
            seen.add(descriptor.name)
            selected.append(self._tools[descriptor.name])
        return SelectedTools(selected)


def build_tool_controls(registry: ToolRegistry) -> ControlPlane:
    async def pre_tool_use(_ctx: Ctx, call: ToolCallPart) -> Continue | Suspend:
        if not registry.approval_required(call.tool_name):
            return Continue()
        return Suspend(
            {
                "pending_id": call.tool_call_id,
                "tool_name": call.tool_name,
                "arguments": call.args_as_dict(),
            }
        )

    async def on_resume(
        _ctx: Ctx,
        call: ToolCallPart,
        resume: ResumeInput,
    ) -> Continue | Deny:
        edited_args = resume.answer.get("args")
        if edited_args is not None and edited_args != call.args_as_dict():
            return Deny(
                {
                    "type": "error",
                    "message": "Edited tool arguments are not supported.",
                }
            )
        return Continue()

    return ControlPlane(pre_tool_use=pre_tool_use, on_resume=on_resume)


__all__ = [
    "RegisteredTool",
    "SelectedTools",
    "ToolRegistry",
    "ToolResult",
    "ToolSelectionError",
    "build_tool_controls",
]
