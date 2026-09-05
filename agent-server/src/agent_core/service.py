from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any, Protocol, cast

from ag_ui.core import (
    BaseEvent,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunFinishedSuccessOutcome,
)
from pydantic_ai import CancellationToken

from agent_core.admission import AdmittedRunInput, admit_run_input
from agent_core.agent import AgentRunDeps
from agent_core.auth.policy import AuthenticatedAgentCaller
from agent_core.command import DeferredInterrupt, MappedRun, RunInputMapper
from agent_core.context import LoadedAgentContext
from agent_core.identity import ExecutionIdentity
from agent_core.runtime import (
    ExecutionContended,
    ExecutionIndeterminate,
    ExecutionSuperseded,
)
from agent_core.store.postgres import AdmissionResult, AgentRequest, StoredEvent
from agent_core.supervisor import RunCapacityExceeded, RunSupervisor


class AgentStore(Protocol):
    async def admit(
        self,
        admitted: AdmittedRunInput,
        caller: AuthenticatedAgentCaller,
        *,
        execution_config: dict[str, Any],
    ) -> AdmissionResult: ...

    async def resolve_interrupt(
        self,
        interrupt_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> Any: ...

    async def get_request(
        self,
        run_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> AgentRequest: ...

    async def replay(
        self,
        run_id: str,
        *,
        after_sequence: int,
    ) -> list[StoredEvent]: ...

    async def terminal_sequence(self, run_id: str) -> int | None: ...

    async def request_abort(
        self,
        run_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> None: ...

    async def is_aborted(self, run_id: str) -> bool: ...

    async def append_event(
        self,
        run_id: str,
        event: BaseEvent,
        *,
        producer_key: str,
        terminal: bool = False,
    ) -> StoredEvent: ...


class RunAssembler(Protocol):
    async def assemble(
        self,
        *,
        request: RunAgentInput,
        identity: ExecutionIdentity,
        loaded_context: LoadedAgentContext,
    ) -> AgentRunDeps: ...


class RequestContextLoader(Protocol):
    async def load(
        self,
        *,
        execution: ExecutionIdentity,
        request_context: Any,
        request_state: Any,
    ) -> LoadedAgentContext: ...


class AgentRuntime(Protocol):
    async def execute(
        self,
        mapped: MappedRun,
        deps: AgentRunDeps,
        cancellation_token: CancellationToken,
    ) -> None: ...


class AgentService:
    def __init__(
        self,
        *,
        store: AgentStore,
        assembly: RunAssembler,
        runtime: AgentRuntime,
        supervisor: RunSupervisor,
        context_loader: RequestContextLoader,
        prompt_revision: str = "",
        model_refs: tuple[str, ...] = (),
        poll_interval: float = 0.25,
    ) -> None:
        self._store = store
        self._assembly = assembly
        self._runtime = runtime
        self._supervisor = supervisor
        self._context_loader = context_loader
        self._prompt_revision = prompt_revision
        self._model_refs = model_refs
        self._poll_interval = poll_interval
        self._admission_start_lock = asyncio.Lock()

    async def submit(self, payload: bytes, caller: AuthenticatedAgentCaller) -> str:
        admitted = admit_run_input(payload)
        request = admitted.input

        async def resolve(interrupt_id: str) -> DeferredInterrupt:
            return cast(
                DeferredInterrupt,
                await self._store.resolve_interrupt(interrupt_id, caller),
            )

        mapped = await RunInputMapper(resolve_interrupt=resolve).map(
            request,
            subject=caller.agent_subject,
        )
        assembly_request = request
        assembly_identity = mapped.identity
        if mapped.resume is not None:
            origin = await self._store.get_request(
                mapped.resume.semora_run_id,
                caller,
            )
            assembly_request = RunAgentInput.model_validate(origin.original_input)
            assembly_identity = ExecutionIdentity(
                origin.run_id,
                origin.thread_id,
                caller.agent_subject,
            )
        loaded_context = await self._context_loader.load(
            execution=assembly_identity,
            request_context=assembly_request.context,
            request_state=assembly_request.state,
        )
        run_deps = await self._assembly.assemble(
            request=assembly_request,
            identity=assembly_identity,
            loaded_context=loaded_context,
        )

        async with self._admission_start_lock:
            admission = await self._store.admit(
                admitted,
                caller,
                execution_config={
                    "prompt_revision": self._prompt_revision,
                    "models": list(self._model_refs),
                },
            )
            if admission.request.terminal_sequence is None:
                try:
                    self._supervisor.start(
                        request.run_id,
                        lambda token: self._execute(mapped, run_deps, token),
                    )
                except RunCapacityExceeded:
                    await self._append_error(
                        request.run_id,
                        "capacity_exceeded",
                        "Agent execution capacity is full",
                    )
                    raise
        return request.run_id

    async def _execute(
        self,
        mapped: MappedRun,
        deps: AgentRunDeps,
        token: CancellationToken,
    ) -> None:
        run_id = mapped.identity.run_id
        try:
            await self._runtime.execute(mapped, deps, token)
            if await self._store.terminal_sequence(run_id) is None:
                await self._store.append_event(
                    run_id,
                    RunFinishedEvent(
                        thread_id=mapped.identity.conversation_id,
                        run_id=run_id,
                        outcome=RunFinishedSuccessOutcome(),
                    ),
                    producer_key="run:terminal",
                    terminal=True,
                )
        except asyncio.CancelledError:
            code = (
                "aborted" if await self._store.is_aborted(run_id) else "server_shutdown"
            )
            await self._append_error(run_id, code, "Run stopped")
        except (ExecutionContended, ExecutionSuperseded):
            return
        except ExecutionIndeterminate:
            await self._append_error(
                run_id,
                "indeterminate_execution",
                "Agent execution could not be resumed safely.",
            )
        except Exception:  # noqa: BLE001 - redact all provider/runtime failures at boundary
            await self._append_error(
                run_id,
                "agent_failed",
                "Agent execution failed",
            )

    async def _append_error(self, run_id: str, code: str, message: str) -> StoredEvent:
        return await self._store.append_event(
            run_id,
            RunErrorEvent(message=message, code=code),
            producer_key="run:terminal",
            terminal=True,
        )

    async def stream(
        self,
        run_id: str,
        *,
        after_sequence: int,
    ) -> AsyncGenerator[StoredEvent, None]:
        cursor = after_sequence
        while True:
            replay = await self._store.replay(run_id, after_sequence=cursor)
            for event in replay:
                cursor = event.sequence
                yield event
            terminal = await self._store.terminal_sequence(run_id)
            if terminal is not None and cursor >= terminal:
                return
            await asyncio.sleep(self._poll_interval)

    async def abort(
        self,
        run_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> None:
        await self._store.request_abort(run_id, caller)
        self._supervisor.abort(run_id)
        await self._append_error(run_id, "aborted", "Run stopped")

    async def shutdown(self, *, timeout: float) -> None:
        await self._supervisor.drain(timeout=timeout)


__all__ = [
    "AgentRuntime",
    "AgentService",
    "AgentStore",
    "RequestContextLoader",
    "RunAssembler",
]
