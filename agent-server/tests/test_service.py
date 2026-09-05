import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from ag_ui.core import BaseEvent, RunAgentInput, RunErrorEvent, RunStartedEvent
from pydantic_ai import CancellationToken
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from semora import AgentRuntime as SemoraRuntimeEngine
from semora import MemorySteps, MemoryTranscript
from uuid_utils import uuid7

from agent_core.admission import AdmittedRunInput
from agent_core.agent import AgentRunDeps, AgentSettings, build_deployment_agent
from agent_core.auth.policy import AuthenticatedAgentCaller
from agent_core.command import MappedRun
from agent_core.context import LoadedAgentContext
from agent_core.identity import ExecutionIdentity
from agent_core.projection import AGUIJournalProjector
from agent_core.runtime import (
    ExecutionContended,
    ExecutionIndeterminate,
    SemoraAgentRuntime,
)
from agent_core.service import AgentRuntime, AgentService
from agent_core.store.postgres import (
    AdmissionResult,
    AgentRequest,
    DeferredInterrupt,
    StoredEvent,
)
from agent_core.supervisor import RunCapacityExceeded, RunSupervisor
from agent_core.tools import ToolRegistry, build_tool_controls

RUN_ID = str(uuid7())
THREAD_ID = str(uuid7())


def _payload(*, run_id: str = RUN_ID, thread_id: str = THREAD_ID) -> bytes:
    return json.dumps(
        {
            "threadId": thread_id,
            "runId": run_id,
            "messages": [{"id": str(uuid7()), "role": "user", "content": "hello"}],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        }
    ).encode()


def _caller() -> AuthenticatedAgentCaller:
    return AuthenticatedAgentCaller("issuer", b"x" * 32, "agtsub:v1:test")


class RecordingStore:
    def __init__(
        self,
        order: list[str],
        *,
        created: bool = True,
    ) -> None:
        self.order = order
        self.created = created
        self.appended: list[BaseEvent] = []
        self._events: dict[str, list[StoredEvent]] = {}
        self._terminal: dict[str, int] = {}
        self._producer_events: dict[tuple[str, str], StoredEvent] = {}
        self._aborted: set[str] = set()
        self.admission_entered: asyncio.Event | None = None
        self.admission_release: asyncio.Event | None = None
        self.admission_calls = 0
        self._admitted: set[str] = set()
        self.execution_configs: list[dict[str, Any]] = []
        self.resolved_interrupt: DeferredInterrupt | None = None
        self.origin_request: AgentRequest | None = None

    async def admit(
        self,
        admitted: AdmittedRunInput,
        caller: AuthenticatedAgentCaller,
        *,
        execution_config: dict[str, Any],
    ) -> AdmissionResult:
        del caller
        self.execution_configs.append(execution_config)
        self.admission_calls += 1
        self.order.append("admit")
        if self.admission_entered is not None:
            self.admission_entered.set()
        if self.admission_release is not None:
            await self.admission_release.wait()
        created = self.created and admitted.input.run_id not in self._admitted
        self._admitted.add(admitted.input.run_id)
        return AdmissionResult(
            AgentRequest(
                run_id=admitted.input.run_id,
                thread_id=admitted.input.thread_id,
                original_input=json.loads(admitted.canonical_payload),
                terminal_sequence=self._terminal.get(admitted.input.run_id),
                execution_config=execution_config,
            ),
            created,
        )

    async def resolve_interrupt(
        self,
        interrupt_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> Any:
        del interrupt_id, caller
        if self.resolved_interrupt is None:
            raise AssertionError("no interrupt configured")
        return self.resolved_interrupt

    async def get_request(
        self,
        run_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> AgentRequest:
        del caller
        if self.origin_request is None or self.origin_request.run_id != run_id:
            raise AssertionError("no origin request configured")
        return self.origin_request

    async def replay(self, run_id: str, *, after_sequence: int) -> list[StoredEvent]:
        return [
            event
            for event in self._events.get(run_id, [])
            if event.sequence > after_sequence
        ]

    async def terminal_sequence(self, run_id: str) -> int | None:
        return self._terminal.get(run_id)

    async def request_abort(
        self,
        run_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> None:
        del caller
        self.order.append("request_abort")
        self._aborted.add(run_id)

    async def is_aborted(self, run_id: str) -> bool:
        return run_id in self._aborted

    async def append_event(
        self,
        run_id: str,
        event: BaseEvent,
        *,
        producer_key: str,
        terminal: bool = False,
    ) -> StoredEvent:
        if stored := self._producer_events.get((run_id, producer_key)):
            return stored
        existing = self._events.get(run_id, [])
        if producer_key == "run:terminal" and run_id in self._terminal:
            return existing[self._terminal[run_id] - 1]
        self.appended.append(event)
        stored = StoredEvent(
            len(existing) + 1,
            str(uuid7()),
            event.model_dump(mode="json", by_alias=True),
        )
        self._events.setdefault(run_id, []).append(stored)
        self._producer_events[run_id, producer_key] = stored
        if terminal:
            self._terminal[run_id] = stored.sequence
        return stored

    async def create_interrupt(
        self,
        *,
        run_id: str,
        semora_run_id: str,
        deferred_call_id: str,
        tool_call_id: str,
    ) -> DeferredInterrupt:
        del run_id, semora_run_id, deferred_call_id, tool_call_id
        raise AssertionError("text-only runs must not request tool approval")


class RecordingRuntime:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[tuple[MappedRun, AgentRunDeps, CancellationToken]] = []
        self.failure = failure
        self.release: asyncio.Event | None = None

    async def execute(
        self,
        mapped: MappedRun,
        deps: AgentRunDeps,
        token: CancellationToken,
    ) -> None:
        self.calls.append((mapped, deps, token))
        if self.failure is not None:
            raise self.failure
        if self.release is not None:
            await self.release.wait()


class RecordingSupervisor(RunSupervisor):
    def __init__(self, order: list[str], *, capacity: int = 32) -> None:
        super().__init__(capacity=capacity)
        self.order = order

    def start(self, run_id: str, execute: Any) -> bool:
        self.order.append("start")
        return super().start(run_id, execute)

    def abort(self, run_id: str) -> bool:
        self.order.append("abort")
        return super().abort(run_id)


class Assembly:
    async def assemble(
        self,
        *,
        request: RunAgentInput,
        identity: ExecutionIdentity,
        loaded_context: LoadedAgentContext,
    ) -> AgentRunDeps:
        del request, loaded_context
        return AgentRunDeps(identity, "trusted instructions", ())


class Context:
    async def load(self, **kwargs: Any) -> LoadedAgentContext:
        del kwargs
        return LoadedAgentContext((), None, ())


def _service(
    *,
    store: RecordingStore,
    runtime: AgentRuntime,
    supervisor: RunSupervisor | None = None,
) -> AgentService:
    return AgentService(
        store=store,
        assembly=Assembly(),
        runtime=runtime,
        supervisor=supervisor or RecordingSupervisor(store.order),
        context_loader=Context(),
        prompt_revision="revision-1",
        model_refs=("openrouter:openai/gpt-5.2", "openai:gpt-5-mini"),
        poll_interval=0,
    )


async def _wait_for_terminal(store: RecordingStore, run_id: str = RUN_ID) -> None:
    for _ in range(100):
        if await store.terminal_sequence(run_id) is not None:
            return
        await asyncio.sleep(0)
    raise AssertionError("background run did not terminate")


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", [False, True], ids=["success", "exhausted"])
async def test_native_fallback_through_runtime_and_journal(exhausted: bool) -> None:
    calls: list[str] = []

    async def primary(
        _messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> AsyncIterator[str]:
        calls.append("primary")
        raise ModelAPIError("primary", "private primary provider secret")
        yield "unreachable"

    async def fallback(
        _messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> AsyncIterator[str]:
        calls.append("fallback")
        if exhausted:
            raise ModelAPIError("fallback", "private fallback provider secret")
        yield "fallback "
        yield "answer"

    chain = FallbackModel(
        FunctionModel(stream_function=primary, model_name="primary"),
        FunctionModel(stream_function=fallback, model_name="fallback"),
    )
    settings = AgentSettings(
        name="integration",
        description="test",
        system_prompt_file="unused.md",
        prompt_revision="test",
        models=("openai:primary", "openai:fallback"),
    )
    agent = build_deployment_agent(
        settings=settings, registry=ToolRegistry(), model=chain
    )
    store = RecordingStore([])
    supervisor = RunSupervisor()
    service = _service(
        store=store,
        runtime=SemoraAgentRuntime(
            agent=agent,
            engine=SemoraRuntimeEngine(MemorySteps(), transcript=MemoryTranscript()),
            projector=AGUIJournalProjector(store),
            controls=build_tool_controls(ToolRegistry()),
        ),
        supervisor=supervisor,
    )

    assert await service.submit(_payload(), _caller()) == RUN_ID
    await service.shutdown(timeout=5)
    journal = await store.replay(RUN_ID, after_sequence=0)
    events = [item.event for item in journal]
    types = [event["type"] for event in events]
    terminals = [
        event for event in events if event["type"] in {"RUN_FINISHED", "RUN_ERROR"}
    ]

    assert supervisor.active == 0
    if exhausted:
        assert calls
        assert calls[::2] == ["primary"] * (len(calls) // 2)
        assert calls[1::2] == ["fallback"] * (len(calls) // 2)
    else:
        assert calls == ["primary", "fallback"]
    assert types.count("RUN_STARTED") == 1
    assert len(terminals) == 1
    assert await store.terminal_sequence(RUN_ID) == journal[-1].sequence
    if exhausted:
        assert terminals[0]["type"] == "RUN_ERROR"
        assert terminals[0]["code"] == "agent_failed"
        assert terminals[0]["message"] == "Agent execution failed"
        assert "private primary" not in json.dumps(events)
        assert "private fallback" not in json.dumps(events)
    else:
        assert terminals[0]["type"] == "RUN_FINISHED"
        assert (
            "".join(
                event["delta"]
                for event in events
                if event["type"] == "TEXT_MESSAGE_CONTENT"
            )
            == "fallback answer"
        )


@pytest.mark.asyncio
async def test_submit_commits_before_starting_local_run() -> None:
    order: list[str] = []
    store = RecordingStore(order)
    service = _service(store=store, runtime=RecordingRuntime())

    assert await service.submit(_payload(), _caller()) == RUN_ID
    await _wait_for_terminal(store)
    assert order == ["admit", "start"]
    assert store.appended[-1].type.value == "RUN_FINISHED"
    assert store.execution_configs == [
        {
            "prompt_revision": "revision-1",
            "models": ["openrouter:openai/gpt-5.2", "openai:gpt-5-mini"],
        }
    ]


@pytest.mark.asyncio
async def test_existing_nonterminal_admission_restarts_request_driven_execution() -> (
    None
):
    order: list[str] = []
    store = RecordingStore(order, created=False)
    service = _service(
        store=store,
        runtime=RecordingRuntime(),
    )

    assert await service.submit(_payload(), _caller()) == RUN_ID
    await _wait_for_terminal(store)
    assert order == ["admit", "start"]


@pytest.mark.asyncio
async def test_resume_rebuilds_trusted_deps_from_authenticated_origin_request() -> None:
    origin_run_id = str(uuid7())
    resume_run_id = str(uuid7())
    origin_payload = _payload(run_id=origin_run_id)
    store = RecordingStore([])
    store.resolved_interrupt = DeferredInterrupt(
        str(uuid7()),
        origin_run_id,
        origin_run_id,
        "pending-1",
        "call-1",
    )
    store.origin_request = AgentRequest(
        run_id=origin_run_id,
        thread_id=THREAD_ID,
        original_input=json.loads(origin_payload),
        terminal_sequence=1,
        execution_config={},
    )
    runtime = RecordingRuntime()
    service = _service(store=store, runtime=runtime)
    resume_payload = json.dumps(
        {
            "threadId": THREAD_ID,
            "runId": resume_run_id,
            "messages": [],
            "tools": [],
            "context": [],
            "forwardedProps": {},
            "resume": [
                {
                    "interruptId": store.resolved_interrupt.interrupt_id,
                    "status": "resolved",
                    "payload": {
                        "approved": True,
                        "toolCallId": "call-1",
                    },
                }
            ],
        }
    ).encode()

    await service.submit(resume_payload, _caller())
    await _wait_for_terminal(store, resume_run_id)

    mapped, deps, _token = runtime.calls[0]
    assert mapped.identity.run_id == resume_run_id
    assert mapped.resume is not None
    assert mapped.resume.origin_run_id == origin_run_id
    assert mapped.resume.semora_run_id == origin_run_id
    assert deps.identity.run_id == origin_run_id


@pytest.mark.asyncio
async def test_concurrent_duplicate_admission_starts_exactly_once() -> None:
    order: list[str] = []
    store = RecordingStore(order)
    store.admission_entered = asyncio.Event()
    store.admission_release = asyncio.Event()
    supervisor = RecordingSupervisor(order)
    service = _service(
        store=store,
        runtime=RecordingRuntime(),
        supervisor=supervisor,
    )
    payload = _payload()

    first = asyncio.create_task(service.submit(payload, _caller()))
    await store.admission_entered.wait()
    second = asyncio.create_task(service.submit(payload, _caller()))
    await asyncio.sleep(0)
    assert store.admission_calls == 1
    store.admission_release.set()

    results = await asyncio.gather(first, second)
    assert list(results) == [RUN_ID, RUN_ID]
    assert order.count("start") == 1


@pytest.mark.asyncio
async def test_provider_failure_is_redacted() -> None:
    store = RecordingStore([])
    service = _service(
        store=store,
        runtime=RecordingRuntime(failure=RuntimeError("private provider detail")),
    )

    await service.submit(_payload(), _caller())
    await _wait_for_terminal(store)

    failure = store.appended[-1]
    assert isinstance(failure, RunErrorEvent)
    assert failure.code == "agent_failed"
    assert "private provider detail" not in failure.message


@pytest.mark.asyncio
async def test_indeterminate_semora_effect_has_dedicated_public_error() -> None:
    store = RecordingStore([])
    service = _service(
        store=store,
        runtime=RecordingRuntime(failure=ExecutionIndeterminate()),
    )

    await service.submit(_payload(), _caller())
    await _wait_for_terminal(store)

    failure = store.appended[-1]
    assert isinstance(failure, RunErrorEvent)
    assert failure.code == "indeterminate_execution"


@pytest.mark.asyncio
async def test_contended_semora_attempt_does_not_write_terminal_event() -> None:
    store = RecordingStore([])
    service = _service(
        store=store,
        runtime=RecordingRuntime(failure=ExecutionContended()),
    )

    await service.submit(_payload(), _caller())
    await service.shutdown(timeout=1)

    assert await store.terminal_sequence(RUN_ID) is None


@pytest.mark.asyncio
async def test_abort_persists_intent_before_cancelling_run() -> None:
    order: list[str] = []
    store = RecordingStore(order)
    runtime = RecordingRuntime()
    runtime.release = asyncio.Event()
    service = _service(store=store, runtime=runtime)
    await service.submit(_payload(), _caller())
    await asyncio.sleep(0)

    await service.abort(RUN_ID, _caller())
    await _wait_for_terminal(store)

    assert order[-2:] == ["request_abort", "abort"]
    failure = store.appended[-1]
    assert isinstance(failure, RunErrorEvent)
    assert failure.code == "aborted"


@pytest.mark.asyncio
async def test_shutdown_cancellation_is_distinct_from_abort() -> None:
    store = RecordingStore([])
    runtime = RecordingRuntime()
    runtime.release = asyncio.Event()
    service = _service(store=store, runtime=runtime)
    await service.submit(_payload(), _caller())
    await asyncio.sleep(0)

    await service.shutdown(timeout=0)
    await _wait_for_terminal(store)

    failure = store.appended[-1]
    assert isinstance(failure, RunErrorEvent)
    assert failure.code == "server_shutdown"


@pytest.mark.asyncio
async def test_capacity_failure_is_terminal_and_never_queues() -> None:
    first_run = str(uuid7())
    second_run = str(uuid7())
    store = RecordingStore([])
    runtime = RecordingRuntime()
    runtime.release = asyncio.Event()
    service = _service(
        store=store,
        runtime=runtime,
        supervisor=RunSupervisor(capacity=1),
    )
    await service.submit(_payload(run_id=first_run), _caller())

    with pytest.raises(RunCapacityExceeded):
        await service.submit(_payload(run_id=second_run), _caller())

    failure = store.appended[-1]
    assert isinstance(failure, RunErrorEvent)
    assert failure.code == "capacity_exceeded"
    await service.shutdown(timeout=0)


@pytest.mark.asyncio
async def test_stream_disconnect_does_not_cancel_run() -> None:
    store = RecordingStore([])
    await store.append_event(
        RUN_ID,
        RunStartedEvent(thread_id=THREAD_ID, run_id=RUN_ID),
        producer_key="run:started",
    )
    supervisor = RecordingSupervisor([])
    service = _service(
        store=store,
        runtime=RecordingRuntime(),
        supervisor=supervisor,
    )
    stream = service.stream(RUN_ID, after_sequence=0)

    await anext(stream)
    await stream.aclose()

    assert supervisor.order == []
