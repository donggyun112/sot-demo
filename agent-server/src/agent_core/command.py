from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from ag_ui.core import AssistantMessage as AguiAssistantMessage
from ag_ui.core import RunAgentInput
from ag_ui.core import ToolMessage as AguiToolMessage
from ag_ui.core import UserMessage as AguiUserMessage
from pydantic_ai.messages import ModelMessage
from pydantic_ai.ui.ag_ui import AGUIAdapter

from agent_core.identity import ExecutionIdentity

type CommandMappingErrorCode = Literal[
    "unsupported_message_role",
    "invalid_command",
    "invalid_tool_call_arguments",
]
type JsonPathPart = str | int


class DeferredInterrupt(Protocol):
    origin_run_id: str
    semora_run_id: str
    deferred_call_id: str
    tool_call_id: str


type InterruptResolver = Callable[[str], Awaitable[DeferredInterrupt]]


class CommandMappingError(ValueError):
    def __init__(
        self,
        code: CommandMappingErrorCode,
        path: tuple[JsonPathPart, ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.path = path


@dataclass(frozen=True, slots=True)
class MappedResume:
    origin_run_id: str
    semora_run_id: str
    pending_id: str
    answer: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MappedRun:
    identity: ExecutionIdentity
    user_prompt: str | None
    prompt_id: str | None
    message_history: list[ModelMessage]
    resume: MappedResume | None


class RunInputMapper:
    def __init__(self, resolve_interrupt: InterruptResolver | None = None) -> None:
        self._resolve_interrupt = resolve_interrupt

    async def map(self, request: RunAgentInput, *, subject: str) -> MappedRun:
        identity = ExecutionIdentity(
            run_id=request.run_id,
            conversation_id=request.thread_id,
            subject=subject,
        )
        self._validate_messages(request.messages)
        resume = request.resume
        if resume is not None:
            return await self._map_resume(identity, request.messages, resume)
        return self._map_prompt(identity, request.messages)

    async def _map_resume(
        self,
        identity: ExecutionIdentity,
        messages: Sequence[Any],
        resume: Sequence[Any],
    ) -> MappedRun:
        if len(resume) != 1 or self._resolve_interrupt is None:
            raise CommandMappingError("invalid_command", ("resume",))
        entry = resume[0]
        payload = entry.payload
        if not isinstance(payload, dict) or not isinstance(
            payload.get("approved"), bool
        ):
            raise CommandMappingError("invalid_command", ("resume", 0, "payload"))
        resolved = await self._resolve_interrupt(entry.interrupt_id)
        public_tool_call_id = payload.get("toolCallId")
        if public_tool_call_id != resolved.tool_call_id:
            raise CommandMappingError(
                "invalid_command", ("resume", 0, "payload", "toolCallId")
            )
        edited_args = payload.get("args")
        if edited_args is not None and not isinstance(edited_args, dict):
            raise CommandMappingError(
                "invalid_command", ("resume", 0, "payload", "args")
            )
        approved = payload["approved"] and entry.status != "cancelled"
        answer: dict[str, Any]
        if approved:
            answer = {"type": "approve"}
            if edited_args is not None:
                answer["args"] = edited_args
        else:
            answer = {"type": "error", "message": "Cancelled by user."}
        return MappedRun(
            identity=identity,
            user_prompt=None,
            prompt_id=None,
            message_history=[],
            resume=MappedResume(
                origin_run_id=resolved.origin_run_id,
                semora_run_id=resolved.semora_run_id,
                pending_id=resolved.deferred_call_id,
                answer=answer,
            ),
        )

    def _map_prompt(
        self,
        identity: ExecutionIdentity,
        messages: Sequence[Any],
    ) -> MappedRun:
        if not messages:
            raise CommandMappingError("invalid_command", ("messages",))
        trailing = messages[-1]
        if not isinstance(trailing, AguiUserMessage) or not isinstance(
            trailing.content, str
        ):
            raise CommandMappingError(
                "invalid_command", ("messages", len(messages) - 1)
            )
        return MappedRun(
            identity=identity,
            user_prompt=trailing.content,
            prompt_id=trailing.id,
            message_history=AGUIAdapter.load_messages(messages[:-1]),
            resume=None,
        )

    def _validate_messages(self, messages: Sequence[Any]) -> None:
        for index, message in enumerate(messages):
            if not isinstance(
                message, (AguiUserMessage, AguiAssistantMessage, AguiToolMessage)
            ):
                raise CommandMappingError(
                    "unsupported_message_role", ("messages", index, "role")
                )
            if isinstance(message, AguiAssistantMessage):
                for call in message.tool_calls or []:
                    try:
                        arguments = json.loads(call.function.arguments)
                    except json.JSONDecodeError as error:
                        raise CommandMappingError(
                            "invalid_tool_call_arguments",
                            ("messages", index, "toolCalls"),
                        ) from error
                    if not isinstance(arguments, dict):
                        raise CommandMappingError(
                            "invalid_tool_call_arguments",
                            ("messages", index, "toolCalls"),
                        )


__all__ = ["CommandMappingError", "MappedResume", "MappedRun", "RunInputMapper"]
