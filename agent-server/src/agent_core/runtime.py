from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Any, Protocol

from pydantic_ai import Agent, CancellationToken, DeferredToolRequests, RunContext
from pydantic_ai.messages import AgentStreamEvent
from semora import AgentSuspended, Controls
from semora_store import Contended, ExecutionContext, Fenced, Indeterminate

from agent_core.agent import AgentRunDeps
from agent_core.command import MappedRun
from agent_core.projection import AGUIJournalProjector


class ExecutionContended(Exception):
    pass


class ExecutionSuperseded(Exception):
    pass


class ExecutionIndeterminate(Exception):
    pass


class SemoraEngine(Protocol):
    async def run(
        self,
        run_id: str | ExecutionContext,
        agent: Agent[Any, Any],
        prompt: str | None = None,
        **options: Any,
    ) -> Any: ...

    async def resume(
        self,
        run_id: str | ExecutionContext,
        pending_id: str,
        answer: dict[str, Any],
        agent: Agent[Any, Any],
        *,
        controls: Controls | None = None,
        rules_version: str = "",
        deps: Any = None,
    ) -> Any: ...


class SemoraAgentRuntime:
    def __init__(
        self,
        *,
        agent: Agent[AgentRunDeps, str | DeferredToolRequests],
        engine: SemoraEngine,
        projector: AGUIJournalProjector,
        controls: Controls,
        rules_version: str = "",
    ) -> None:
        self._agent = agent
        self._engine = engine
        self._projector = projector
        self._controls = controls
        self._rules_version = rules_version

    async def execute(
        self,
        mapped: MappedRun,
        deps: AgentRunDeps,
        cancellation_token: CancellationToken,
    ) -> None:
        identity = mapped.identity

        async def project_events(
            ctx: RunContext[AgentRunDeps],
            events: AsyncIterable[AgentStreamEvent],
        ) -> None:
            await self._projector.project(
                identity.run_id,
                identity.conversation_id,
                events.__aiter__(),
                request_index=ctx.run_step,
            )

        await self._projector.started(identity.run_id, identity.conversation_id)
        try:
            if mapped.resume is not None:
                outcome = await self._engine.resume(
                    mapped.resume.semora_run_id,
                    mapped.resume.pending_id,
                    mapped.resume.answer,
                    self._agent,
                    controls=self._controls,
                    rules_version=self._rules_version,
                    deps=deps,
                )
                if isinstance(outcome.output, str):
                    await self._projector.completed_text(
                        identity.run_id,
                        identity.conversation_id,
                        outcome.output,
                    )
                await self._projector.finished(
                    identity.run_id,
                    identity.conversation_id,
                )
                return

            await self._engine.run(
                identity.run_id,
                self._agent,
                mapped.user_prompt,
                controls=self._controls,
                rules_version=self._rules_version,
                prompt_id=mapped.prompt_id,
                conversation_id=identity.conversation_id,
                message_history=mapped.message_history,
                deps=deps,
                cancellation_token=cancellation_token,
                event_stream_handler=project_events,
            )
            await self._projector.finished(
                identity.run_id,
                identity.conversation_id,
            )
        except AgentSuspended as suspended:
            await self._projector.suspended(
                identity.run_id,
                identity.conversation_id,
                suspended.pending,
                semora_run_id=(
                    mapped.resume.semora_run_id
                    if mapped.resume is not None
                    else identity.run_id
                ),
            )
        except Contended as error:
            raise ExecutionContended from error
        except Fenced as error:
            raise ExecutionSuperseded from error
        except Indeterminate as error:
            raise ExecutionIndeterminate from error


__all__ = [
    "ExecutionContended",
    "ExecutionIndeterminate",
    "ExecutionSuperseded",
    "SemoraAgentRuntime",
    "SemoraEngine",
]
