from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from functools import cached_property
from typing import Annotated, cast
from uuid import UUID

from ag_ui.core import (
    ActivityMessage,
    AssistantMessage,
    BaseEvent,
    DeveloperMessage,
    RunAgentInput,
    RunErrorEvent,
    SystemMessage,
    TextInputContent,
    UserMessage,
)
from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.ui.ag_ui import AGUIAdapter, AGUIEventStream
from starlette.responses import Response

from sot.agent.application import AgentRunPreparer, CompletedRunWriter
from sot.agent.deps import AgentDeps
from sot.agent.messages import (
    completed_messages_to_new_turns,
    turns_to_model_messages,
)
from sot.identity.contracts import Actor
from sot.shared.errors import InvalidInput, SOTError
from sot.shared.ids import BranchId, WorkspaceId


def _invalid_request() -> InvalidInput:
    return InvalidInput("invalid_agent_request", "Agent request is invalid")


class _ServerOnlyAGUIEventStream(AGUIEventStream[AgentDeps, str]):
    async def on_error(self, error: Exception) -> AsyncIterator[BaseEvent]:
        self._error = True
        if isinstance(error, SOTError):
            code, message = error.code, error.message
        else:
            code, message = "agent_run_failed", "Agent run failed"
        yield RunErrorEvent(message=message, code=code, timestamp=self._get_timestamp())


class ServerOnlyAGUIAdapter(AGUIAdapter[AgentDeps, str]):
    """Accept one text prompt while keeping instructions, history and tools server-owned."""

    @classmethod
    def build_run_input(cls, body: bytes) -> RunAgentInput:
        try:
            run_input = super().build_run_input(body)
            cls._latest_prompt(run_input)
        except (TypeError, ValidationError, ValueError):
            raise _invalid_request() from None
        return run_input

    @staticmethod
    def _latest_prompt(run_input: RunAgentInput) -> str:
        if run_input.tools:
            raise ValueError
        if any(
            isinstance(message, SystemMessage | DeveloperMessage | ActivityMessage)
            for message in run_input.messages
        ):
            raise ValueError
        if any(
            isinstance(message, UserMessage)
            and not (
                isinstance(message.content, str)
                or all(isinstance(part, TextInputContent) for part in message.content)
            )
            for message in run_input.messages
        ):
            raise ValueError
        if not run_input.messages or not isinstance(
            latest := run_input.messages[-1], UserMessage
        ):
            raise ValueError
        previous = next(
            (
                message
                for message in reversed(run_input.messages[:-1])
                if isinstance(message, UserMessage | AssistantMessage)
            ),
            None,
        )
        if isinstance(previous, UserMessage):
            raise TypeError
        if not isinstance(latest.content, str) or not (
            prompt := latest.content.strip()
        ):
            raise ValueError
        return prompt

    @cached_property
    def messages(self) -> list[ModelMessage]:
        return [
            ModelRequest(parts=[UserPromptPart(self._latest_prompt(self.run_input))])
        ]

    @cached_property
    def toolset(self) -> None:
        return None

    @cached_property
    def state(self) -> None:
        return None

    @cached_property
    def deferred_tool_results(self) -> None:
        return None

    def build_event_stream(self) -> _ServerOnlyAGUIEventStream:
        return _ServerOnlyAGUIEventStream(
            self.run_input, accept=self.accept, ag_ui_version=self.ag_ui_version
        )

    def run_server_stream(
        self,
        *,
        message_history: Sequence[ModelMessage],
        deps: AgentDeps,
        completed_run_writer: CompletedRunWriter,
    ) -> AsyncIterator[BaseEvent]:
        async def on_complete(result: AgentRunResult[str]) -> AsyncIterator[BaseEvent]:
            # Pydantic AI 2.38 appends adapter input to message_history, so it is
            # excluded from result.new_messages(); restore the one accepted prompt.
            messages = completed_messages_to_new_turns(
                [*self.messages, *result.new_messages()]
            )
            await completed_run_writer.write(deps, messages=messages)
            if False:
                yield cast(BaseEvent, None)

        return self.run_stream(
            message_history=message_history,
            deps=deps,
            on_complete=on_complete,
        )


def build_agent_router(
    agent: Agent[AgentDeps, str],
    preparer: AgentRunPreparer,
    completed_run_writer: CompletedRunWriter,
    actor: Callable[[Request], Awaitable[Actor]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}")

    @router.post("/branches/{branch_id}/agent", response_model=None)
    async def run_agent(
        workspace_id: UUID,
        branch_id: UUID,
        request: Request,
        current: Annotated[Actor, Depends(actor)],
    ) -> Response:
        adapter = cast(
            ServerOnlyAGUIAdapter,
            await ServerOnlyAGUIAdapter.from_request(
                request,
                agent=agent,
                manage_system_prompt="server",
                preserve_file_data=False,
                allow_uploaded_files=False,
            ),
        )
        prepared = await preparer.prepare(
            actor=current,
            workspace_id=WorkspaceId(workspace_id),
            branch_id=BranchId(branch_id),
        )
        stream = adapter.run_server_stream(
            message_history=turns_to_model_messages(prepared.canonical_turns),
            deps=prepared.deps,
            completed_run_writer=completed_run_writer,
        )
        return adapter.streaming_response(stream)

    return router


__all__ = ["ServerOnlyAGUIAdapter", "build_agent_router"]
