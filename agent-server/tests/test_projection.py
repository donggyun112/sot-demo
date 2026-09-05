from collections.abc import AsyncIterator
from typing import Any

import pytest
from ag_ui.core import BaseEvent, EventType, RunFinishedEvent
from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import (
    DeferredToolRequestsEvent,
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturnPart,
)

from agent_core.projection import AGUIJournalProjector, producer_key
from agent_core.store.postgres import DeferredInterrupt, StoredEvent

RUN_ID = "019504e8-4b7d-7a31-9c2d-123456789abc"
THREAD_ID = "019504e8-4b7c-7f3a-8c2d-123456789abc"


class IdempotentRecordingStore:
    def __init__(self) -> None:
        self.events: list[BaseEvent] = []
        self.producer_keys: list[str] = []
        self._stored: dict[str, StoredEvent] = {}
        self.interrupts: list[DeferredInterrupt] = []

    async def append_event(
        self,
        run_id: str,
        event: BaseEvent,
        *,
        producer_key: str,
        terminal: bool = False,
    ) -> StoredEvent:
        del run_id, terminal
        self.producer_keys.append(producer_key)
        if existing := self._stored.get(producer_key):
            return existing
        self.events.append(event)
        stored = StoredEvent(
            sequence=len(self.events),
            event_id=f"event-{len(self.events)}",
            event=event.model_dump(mode="json", by_alias=True),
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
        interrupt = DeferredInterrupt(
            interrupt_id="interrupt-1",
            origin_run_id=run_id,
            semora_run_id=semora_run_id,
            deferred_call_id=deferred_call_id,
            tool_call_id=tool_call_id,
        )
        self.interrupts.append(interrupt)
        return interrupt


async def _native_text_and_tool_events() -> AsyncIterator[Any]:
    events = [
        PartStartEvent(index=0, part=TextPart("")),
        PartDeltaEvent(index=0, delta=TextPartDelta("hello")),
        PartEndEvent(index=0, part=TextPart("hello")),
        PartStartEvent(index=1, part=ToolCallPart("lookup", {}, "call-1")),
        PartDeltaEvent(
            index=1,
            delta=ToolCallPartDelta(
                args_delta='{"query":"source"}',
                tool_call_id="call-1",
            ),
        ),
        PartEndEvent(
            index=1,
            part=ToolCallPart("lookup", {"query": "source"}, "call-1"),
        ),
        FunctionToolCallEvent(ToolCallPart("lookup", {"query": "source"}, "call-1")),
        FunctionToolResultEvent(
            ToolReturnPart("lookup", {"type": "text", "text": "found"}, "call-1")
        ),
        FinalResultEvent(tool_name=None, tool_call_id=None),
    ]
    for event in events:
        yield event


@pytest.mark.asyncio
async def test_projects_text_and_tools_to_ordered_agui_events() -> None:
    store = IdempotentRecordingStore()
    await AGUIJournalProjector(store).project(
        RUN_ID,
        THREAD_ID,
        _native_text_and_tool_events(),
    )

    assert [event.type for event in store.events] == [
        EventType.RUN_STARTED,
        EventType.TEXT_MESSAGE_START,
        EventType.TEXT_MESSAGE_CONTENT,
        EventType.TEXT_MESSAGE_END,
        EventType.TOOL_CALL_START,
        EventType.TOOL_CALL_ARGS,
        EventType.TOOL_CALL_END,
        EventType.TOOL_CALL_RESULT,
    ]

    await AGUIJournalProjector(store).finished(RUN_ID, THREAD_ID)
    assert store.events[-1].type == EventType.RUN_FINISHED
    assert len(store.producer_keys) == len(set(store.producer_keys))


@pytest.mark.asyncio
async def test_retry_reuses_committed_projection_without_duplicates() -> None:
    store = IdempotentRecordingStore()
    projector = AGUIJournalProjector(store)

    await projector.project(RUN_ID, THREAD_ID, _native_text_and_tool_events())
    expected_count = len(store.events)
    await projector.project(RUN_ID, THREAD_ID, _native_text_and_tool_events())

    assert len(store.events) == expected_count
    assert len(set(store.producer_keys)) == expected_count


def test_producer_key_is_stable_and_scoped_to_projection_kind() -> None:
    assert producer_key(2, 7, "TEXT_MESSAGE_CONTENT") == (
        "pydantic:2:7:TEXT_MESSAGE_CONTENT"
    )


@pytest.mark.asyncio
async def test_deferred_tool_request_becomes_authenticated_interrupt() -> None:
    async def events() -> AsyncIterator[Any]:
        yield DeferredToolRequestsEvent(
            DeferredToolRequests(
                approvals=[ToolCallPart("lookup", {"query": "source"}, "call-1")],
                metadata={"call-1": {"pending_id": "pending-1"}},
            )
        )

    store = IdempotentRecordingStore()
    projector = AGUIJournalProjector(store)
    await projector.project(RUN_ID, THREAD_ID, events())

    assert store.interrupts == []
    assert all(event.type != EventType.RUN_FINISHED for event in store.events)

    await projector.suspended(
        RUN_ID,
        THREAD_ID,
        [("pending-1", "call-1")],
        semora_run_id=RUN_ID,
    )

    assert store.interrupts == [
        DeferredInterrupt("interrupt-1", RUN_ID, RUN_ID, "pending-1", "call-1")
    ]
    assert store.events[-1].type == EventType.RUN_FINISHED
    assert isinstance(store.events[-1], RunFinishedEvent)
    assert store.events[-1].outcome is not None
    assert store.events[-1].outcome.type == "interrupt"


@pytest.mark.asyncio
async def test_public_failure_is_bounded_and_idempotently_terminal() -> None:
    store = IdempotentRecordingStore()
    event = await AGUIJournalProjector(store).fail(
        RUN_ID,
        "x" * 600,
        code="provider_error",
    )

    assert event.event["code"] == "provider_error"
    assert event.event["message"] == "x" * 512
    assert store.producer_keys == ["run:terminal"]
