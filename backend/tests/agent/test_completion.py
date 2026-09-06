from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

import pytest
from ag_ui.core import BaseEvent, RunErrorEvent
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.run import AgentRunResultEvent

from sot.agent.api import ServerOnlyAGUIAdapter, build_agent_router
from sot.agent.application import CompletedRunWriter
from sot.agent.messages import completed_messages_to_new_turns, turns_to_model_messages
from sot.agent.models import build_agent
from sot.bootstrap.errors import register_error_handlers
from sot.identity.contracts import Actor
from sot.session.application import AppendCompletedTurns, BranchAccess, SessionAccess
from sot.session.contracts import CompletedTurnsAppender, CompletedTurnsResult, NewTurn
from sot.shared.errors import SOTError
from tests.agent.test_agui import agui_payload, message
from tests.agent.test_context import Scenario, scenario
from tests.session.test_application import FixedClock


@dataclass
class RecordingAppender:
    delegate: CompletedTurnsAppender
    timeline: list[str]
    failure: Exception | None = None
    calls: int = 0

    async def execute(self, *args: Any, **kwargs: Any) -> CompletedTurnsResult:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        result = await self.delegate.execute(*args, **kwargs)
        self.timeline.append("commit")
        return result


class StorageUnavailable(SOTError):
    pass


def adapter_for(state: Scenario, model: FunctionModel) -> ServerOnlyAGUIAdapter:
    run_input = ServerOnlyAGUIAdapter.build_run_input(
        json.dumps(
            agui_payload(messages=[message("user", "next question", suffix="next")])
        ).encode()
    )
    return ServerOnlyAGUIAdapter(
        build_agent(model), run_input, manage_system_prompt="server"
    )


async def collect_events(
    adapter: ServerOnlyAGUIAdapter,
    state: Scenario,
    writer: CompletedRunWriter,
    timeline: list[str],
) -> list[BaseEvent]:
    prepared = await state.preparer.prepare(
        actor=state.actor,
        workspace_id=state.workspace_id,
        branch_id=state.branch_id,
    )
    events: list[BaseEvent] = []
    async for event in adapter.run_server_stream(
        message_history=turns_to_model_messages(prepared.canonical_turns),
        deps=prepared.deps,
        completed_run_writer=writer,
    ):
        timeline.append(event.type.value)
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_transcript_commits_before_run_finished() -> None:
    state = await scenario()
    timeline: list[str] = []
    appender = RecordingAppender(
        AppendCompletedTurns(
            state.store,
            BranchAccess(
                state.store, SessionAccess(state.store, state.store), state.store
            ),
            lambda: state.store,
            FixedClock(),
        ),
        timeline,
    )

    async def answer(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        assert state.store.active is None
        yield "next answer"

    events = await collect_events(
        adapter_for(state, FunctionModel(stream_function=answer)),
        state,
        CompletedRunWriter(appender),
        timeline,
    )

    event_types = [event.type.value for event in events]
    assert timeline.index("commit") < timeline.index("RUN_FINISHED")
    assert "RUN_ERROR" not in event_types
    turns = state.store.branches[state.workspace_id, state.branch_id].turns
    assert [turn.role for turn in turns[-2:]] == ["user", "assistant"]
    assert [turn.content for turn in turns[-2:]] == ["next question", "next answer"]
    assert state.store.active is None


@pytest.mark.asyncio
async def test_persistence_failure_emits_run_error_without_run_finished() -> None:
    state = await scenario()
    original = state.store.branches[state.workspace_id, state.branch_id].turns
    timeline: list[str] = []
    appender = RecordingAppender(
        AppendCompletedTurns(
            state.store,
            BranchAccess(
                state.store, SessionAccess(state.store, state.store), state.store
            ),
            lambda: state.store,
            FixedClock(),
        ),
        timeline,
        StorageUnavailable("turn_store_failed", "Turn was not stored"),
    )

    async def answer(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        yield "unsaved answer"

    events = await collect_events(
        adapter_for(state, FunctionModel(stream_function=answer)),
        state,
        CompletedRunWriter(appender),
        timeline,
    )

    event_types = [event.type.value for event in events]
    assert "RUN_ERROR" in event_types
    assert "RUN_FINISHED" not in event_types
    error = cast(
        RunErrorEvent,
        next(event for event in events if event.type.value == "RUN_ERROR"),
    )
    assert error.message == "Turn was not stored"
    assert error.code == "turn_store_failed"
    assert state.store.branches[state.workspace_id, state.branch_id].turns == original
    assert state.store.active is None


@pytest.mark.asyncio
async def test_version_conflict_emits_run_error_without_completed_run_turns() -> None:
    state = await scenario()
    stale = await state.preparer.prepare(
        actor=state.actor,
        workspace_id=state.workspace_id,
        branch_id=state.branch_id,
    )
    winner = await state.preparer.prepare(
        actor=state.actor,
        workspace_id=state.workspace_id,
        branch_id=state.branch_id,
    )
    await state.writer.write(
        winner.deps, messages=(NewTurn("assistant", "competing mutation"),)
    )
    committed = state.store.branches[state.workspace_id, state.branch_id].turns

    async def answer(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        yield "stale answer"

    adapter = adapter_for(state, FunctionModel(stream_function=answer))
    events = [
        event
        async for event in adapter.run_server_stream(
            message_history=turns_to_model_messages(stale.canonical_turns),
            deps=stale.deps,
            completed_run_writer=state.writer,
        )
    ]

    event_types = [event.type.value for event in events]
    assert "RUN_ERROR" in event_types
    assert "RUN_FINISHED" not in event_types
    error = cast(
        RunErrorEvent,
        next(event for event in events if event.type.value == "RUN_ERROR"),
    )
    assert error.code == "version_conflict"
    assert error.message == "The resource changed after it was loaded"
    assert state.store.branches[state.workspace_id, state.branch_id].turns == committed
    assert stale.lineage.expected_version == 1
    assert state.store.active is None


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"turn_ids": ["turn-1"]}, {"turn_ids": ["turn-1"]}),
        (None, {}),
        ('{"turn_ids":["turn-1"]}', {"turn_ids": ["turn-1"]}),
    ],
)
def test_completed_tool_call_args_are_normalized(
    args: str | dict[str, Any] | None, expected: dict[str, Any]
) -> None:
    turns = completed_messages_to_new_turns(
        (
            ModelResponse(parts=[ToolCallPart("session_cite", args, "tool-call-1")]),
            ModelRequest(
                parts=[
                    ToolReturnPart("session_cite", {"citeId": "cite-1"}, "tool-call-1")
                ]
            ),
        )
    )
    call = json.loads(turns[0].content)
    assert call == {
        "schema": "sot.tool-turn.v1",
        "kind": "call",
        "tool_name": "session_cite",
        "tool_call_id": "tool-call-1",
        "args": expected,
    }
    assert json.loads(turns[1].content) == {
        "schema": "sot.tool-turn.v1",
        "kind": "return",
        "tool_name": "session_cite",
        "tool_call_id": "tool-call-1",
        "result": {"citeId": "cite-1"},
    }


@pytest.mark.parametrize("args", ["not-json", "[]", "null", "1"])
def test_malformed_or_non_object_completed_tool_args_fail_safely(args: str) -> None:
    with pytest.raises(ValueError, match="^completed agent message is invalid$"):
        completed_messages_to_new_turns(
            (ModelResponse(parts=[ToolCallPart("session_cite", args, "call-1")]),)
        )


@pytest.mark.asyncio
async def test_malformed_completed_args_emit_run_error_and_append_nothing() -> None:
    state = await scenario()
    original = state.store.branches[state.workspace_id, state.branch_id].turns
    appender = RecordingAppender(
        AppendCompletedTurns(
            state.store,
            BranchAccess(
                state.store, SessionAccess(state.store, state.store), state.store
            ),
            lambda: state.store,
            FixedClock(),
        ),
        [],
    )

    async def unused_stream(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        yield "unused"

    adapter = adapter_for(state, FunctionModel(stream_function=unused_stream))
    prepared = await state.preparer.prepare(
        actor=state.actor,
        workspace_id=state.workspace_id,
        branch_id=state.branch_id,
    )
    result = AgentRunResult("unused")
    result._state.message_history = [
        ModelRequest(parts=[UserPromptPart("next question")]),
        ModelResponse(
            parts=[ToolCallPart("session_cite", "not-json secret", "call-1")]
        ),
    ]

    async def native_events() -> AsyncIterator[AgentRunResultEvent[str]]:
        yield AgentRunResultEvent(result)

    async def on_complete(completed: AgentRunResult[str]) -> AsyncIterator[BaseEvent]:
        messages = completed_messages_to_new_turns(tuple(completed.new_messages()))
        await CompletedRunWriter(appender).write(prepared.deps, messages=messages)
        if False:
            yield cast(BaseEvent, None)

    events = [
        event
        async for event in adapter.transform_stream(
            native_events(), on_complete=on_complete
        )
    ]
    event_types = [event.type.value for event in events]
    assert "RUN_ERROR" in event_types
    assert "RUN_FINISHED" not in event_types
    error = cast(
        RunErrorEvent,
        next(event for event in events if event.type.value == "RUN_ERROR"),
    )
    assert error.message == "Agent run failed"
    assert "secret" not in repr(error)
    assert appender.calls == 0
    assert state.store.branches[state.workspace_id, state.branch_id].turns == original


@pytest.mark.asyncio
async def test_http_cancellation_before_completion_persists_no_artifacts() -> None:
    state = await scenario()
    started = asyncio.Event()
    release = asyncio.Event()
    original = state.store.branches[state.workspace_id, state.branch_id].turns
    transactions_before = state.store.transactions
    appender = RecordingAppender(
        AppendCompletedTurns(
            state.store,
            BranchAccess(
                state.store, SessionAccess(state.store, state.store), state.store
            ),
            lambda: state.store,
            FixedClock(),
        ),
        [],
    )

    async def stream(_messages: list[ModelMessage], _info: AgentInfo):
        assert state.store.active is None
        started.set()
        yield "partial"
        await release.wait()
        yield "never completed"

    app = FastAPI()
    register_error_handlers(app)

    async def actor(_request: Request) -> Actor:
        return state.actor

    app.include_router(
        build_agent_router(
            build_agent(FunctionModel(stream_function=stream)),
            state.preparer,
            CompletedRunWriter(appender),
            actor,
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://sot.test"
    ) as client:
        request_task = asyncio.create_task(
            client.post(
                f"/api/v1/workspaces/{state.workspace_id}/branches/{state.branch_id}/agent",
                json=agui_payload(
                    messages=[message("user", "cancel me", suffix="cancel")]
                ),
            )
        )
        started_task = asyncio.create_task(started.wait())
        done, _ = await asyncio.wait(
            {request_task, started_task},
            timeout=2,
            return_when=asyncio.FIRST_COMPLETED,
        )
        assert started_task in done, (
            request_task.result().text
            if request_task in done
            else "model did not start"
        )
        request_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request_task

    assert appender.calls == 0
    assert state.store.branches[state.workspace_id, state.branch_id].turns == original
    assert state.store.transactions == transactions_before + 1
    assert state.store.active is None
