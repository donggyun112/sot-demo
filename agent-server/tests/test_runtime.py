from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from ag_ui.core import BaseEvent
from pydantic_ai import Agent, CancellationToken, RunContext
from pydantic_ai.messages import (
    AgentStreamEvent,
    FinalResultEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
)
from pydantic_ai.models.test import TestModel
from semora import AgentRuntime, ControlPlane, MemorySteps, MemoryTranscript

from agent_core.agent import AgentRunDeps, AgentSettings, build_deployment_agent
from agent_core.command import MappedResume, MappedRun
from agent_core.identity import ExecutionIdentity
from agent_core.projection import AGUIJournalProjector
from agent_core.runtime import SemoraAgentRuntime
from agent_core.store.postgres import DeferredInterrupt, StoredEvent
from agent_core.tools import RegisteredTool, ToolRegistry, build_tool_controls

RUN_ID = "019504e8-4b7d-7a31-9c2d-123456789abc"
THREAD_ID = "019504e8-4b7c-7f3a-8c2d-123456789abc"


def _mapped_run() -> MappedRun:
    return MappedRun(
        identity=ExecutionIdentity(RUN_ID, THREAD_ID, "agtsub:v1:test"),
        user_prompt="hello",
        prompt_id="prompt-1",
        message_history=[],
        resume=None,
    )


def _deps() -> AgentRunDeps:
    return AgentRunDeps(_mapped_run().identity, "trusted instructions", ())


class RecordingProjector:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def started(self, run_id: str, thread_id: str) -> StoredEvent:
        self.calls.append(("started", run_id, thread_id))
        return StoredEvent(1, "event-1", {"type": "RUN_STARTED"})

    async def project(
        self,
        run_id: str,
        thread_id: str,
        native_events: AsyncIterator[Any],
        *,
        request_index: int = 0,
    ) -> None:
        self.calls.append(("project", run_id, thread_id, request_index))
        async for _ in native_events:
            pass

    async def completed_text(self, run_id: str, thread_id: str, text: str) -> None:
        self.calls.append(("completed_text", run_id, thread_id, text))

    async def finished(self, run_id: str, thread_id: str) -> None:
        self.calls.append(("finished", run_id, thread_id))

    async def suspended(
        self,
        run_id: str,
        thread_id: str,
        pending: list[tuple[str, str]],
        *,
        semora_run_id: str,
    ) -> None:
        self.calls.append(("suspended", run_id, thread_id, pending, semora_run_id))


class RecordingEngine:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(
        self, run_id: str, agent: Any, user_prompt: str | None, **kwargs: Any
    ) -> Any:
        self.calls.append(
            {
                "operation": "run",
                "run_id": run_id,
                "agent": agent,
                "user_prompt": user_prompt,
                **kwargs,
            }
        )
        handler = kwargs["event_stream_handler"]

        async def events() -> AsyncIterator[AgentStreamEvent]:
            yield PartStartEvent(index=0, part=TextPart("hello"))
            yield PartEndEvent(index=0, part=TextPart("hello"))
            yield FinalResultEvent(tool_name=None, tool_call_id=None)

        await handler(
            cast(Any, SimpleNamespace(deps=kwargs["deps"], run_step=3)),
            events(),
        )
        return SimpleNamespace(output="hello")

    async def resume(
        self,
        run_id: str,
        pending_id: str,
        answer: dict[str, Any],
        agent: Any,
        **kwargs: Any,
    ) -> Any:
        self.calls.append(
            {
                "operation": "resume",
                "run_id": run_id,
                "pending_id": pending_id,
                "answer": answer,
                "agent": agent,
                **kwargs,
            }
        )
        return SimpleNamespace(output="approved result")


@pytest.mark.asyncio
async def test_runtime_calls_semora_once_with_mapped_input_and_token() -> None:
    agent = object()
    engine = RecordingEngine()
    projector = RecordingProjector()
    controls = ControlPlane()
    runtime = SemoraAgentRuntime(
        agent=cast(Any, agent),
        engine=cast(Any, engine),
        projector=cast(Any, projector),
        controls=controls,
    )
    token = CancellationToken()

    await runtime.execute(_mapped_run(), _deps(), token)

    assert len(engine.calls) == 1
    call = engine.calls[0]
    assert call["operation"] == "run"
    assert call["user_prompt"] == "hello"
    assert call["run_id"] == RUN_ID
    assert call["conversation_id"] == THREAD_ID
    assert call["prompt_id"] == "prompt-1"
    assert call["cancellation_token"] is token
    assert call["deps"] == _deps()
    assert call["controls"] is controls
    assert call["rules_version"] == ""
    assert projector.calls == [
        ("started", RUN_ID, THREAD_ID),
        ("project", RUN_ID, THREAD_ID, 3),
        ("finished", RUN_ID, THREAD_ID),
    ]


@pytest.mark.asyncio
async def test_runtime_routes_resume_to_origin_run_and_projects_completed_text() -> (
    None
):
    engine = RecordingEngine()
    projector = RecordingProjector()
    controls = ControlPlane()
    mapped = MappedRun(
        identity=_mapped_run().identity,
        user_prompt=None,
        prompt_id=None,
        message_history=[],
        resume=MappedResume(
            origin_run_id="origin-run",
            semora_run_id="origin-run",
            pending_id="pending-1",
            answer={"type": "approve"},
        ),
    )
    runtime = SemoraAgentRuntime(
        agent=cast(Any, object()),
        engine=cast(Any, engine),
        projector=cast(Any, projector),
        controls=controls,
    )

    await runtime.execute(mapped, _deps(), CancellationToken())

    call = engine.calls[0]
    assert call["operation"] == "resume"
    assert call["run_id"] == "origin-run"
    assert call["pending_id"] == "pending-1"
    assert call["answer"] == {"type": "approve"}
    assert projector.calls == [
        ("started", RUN_ID, THREAD_ID),
        ("completed_text", RUN_ID, THREAD_ID, "approved result"),
        ("finished", RUN_ID, THREAD_ID),
    ]


class IdempotentStore:
    def __init__(self) -> None:
        self.events: list[BaseEvent] = []
        self._stored: dict[str, StoredEvent] = {}

    async def append_event(
        self,
        run_id: str,
        event: BaseEvent,
        *,
        producer_key: str,
        terminal: bool = False,
    ) -> StoredEvent:
        del run_id, terminal
        if existing := self._stored.get(producer_key):
            return existing
        self.events.append(event)
        stored = StoredEvent(
            len(self.events),
            f"event-{len(self.events)}",
            event.model_dump(mode="json", by_alias=True),
        )
        self._stored[producer_key] = stored
        return stored

    async def replay(self, run_id: str, *, after_sequence: int) -> list[StoredEvent]:
        del run_id
        return [
            event for event in self._stored.values() if event.sequence > after_sequence
        ]

    async def create_interrupt(
        self,
        *,
        run_id: str,
        semora_run_id: str,
        deferred_call_id: str,
        tool_call_id: str,
    ) -> DeferredInterrupt:
        return DeferredInterrupt(
            "interrupt-1",
            run_id,
            semora_run_id,
            deferred_call_id,
            tool_call_id,
        )


@pytest.mark.asyncio
async def test_real_tool_round_projects_one_start_and_one_terminal() -> None:
    store = IdempotentStore()
    projector = AGUIJournalProjector(store)
    agent = Agent(TestModel(call_tools="all"), deps_type=AgentRunDeps)

    @agent.tool
    async def lookup(ctx: RunContext[AgentRunDeps], query: str = "source") -> str:
        del ctx, query
        return "found"

    runtime = SemoraAgentRuntime(
        agent=cast(Any, agent),
        engine=AgentRuntime(MemorySteps(), transcript=MemoryTranscript()),
        projector=projector,
        controls=ControlPlane(),
    )

    await runtime.execute(_mapped_run(), _deps(), CancellationToken())

    types = [event.type.value for event in store.events]
    assert types.count("RUN_STARTED") == 1
    assert types.count("RUN_FINISHED") == 1
    assert sum(kind in {"RUN_FINISHED", "RUN_ERROR"} for kind in types) == 1


@pytest.mark.asyncio
async def test_semora_durably_suspends_and_resumes_approval_required_tool(
    tmp_path: Path,
) -> None:
    executed: list[dict[str, Any]] = []

    async def lookup(arguments: Any) -> dict[str, Any]:
        executed.append(arguments)
        return {"type": "text", "text": "found"}

    registry = ToolRegistry(
        [
            RegisteredTool(
                name="lookup",
                description="Look up a record.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
                instructions="Use lookup.",
                execute=lookup,
                requires_approval=True,
            )
        ]
    )
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("Use selected tools.", encoding="utf-8")
    agent = build_deployment_agent(
        settings=AgentSettings(
            name="test-agent",
            description="test",
            system_prompt_file=prompt_file,
            prompt_revision="rules-1",
            models=("openai:test",),
        ),
        registry=registry,
        model=TestModel(call_tools="all"),
    )
    projector = RecordingProjector()
    runtime = SemoraAgentRuntime(
        agent=agent,
        engine=AgentRuntime(MemorySteps(), transcript=MemoryTranscript()),
        projector=cast(Any, projector),
        controls=build_tool_controls(registry),
    )

    deps = AgentRunDeps(_mapped_run().identity, "trusted", ("lookup",))
    await runtime.execute(_mapped_run(), deps, CancellationToken())

    suspended = next(call for call in projector.calls if call[0] == "suspended")
    pending_id, tool_call_id = suspended[3][0]
    assert pending_id == tool_call_id
    assert executed == []

    resumed = MappedRun(
        identity=ExecutionIdentity("resume-run", THREAD_ID, "agtsub:v1:test"),
        user_prompt=None,
        prompt_id=None,
        message_history=[],
        resume=MappedResume(
            origin_run_id=RUN_ID,
            semora_run_id=RUN_ID,
            pending_id=pending_id,
            answer={"type": "approve"},
        ),
    )
    await runtime.execute(resumed, deps, CancellationToken())

    assert executed == [{}]
    assert any(call[0] == "completed_text" for call in projector.calls)
