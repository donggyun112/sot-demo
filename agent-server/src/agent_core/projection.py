from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, cast

from ag_ui.core import (
    BaseEvent,
    Interrupt,
    RunErrorEvent,
    RunFinishedEvent,
    RunFinishedInterruptOutcome,
    RunFinishedSuccessOutcome,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from pydantic_ai.ui.ag_ui import AGUIEventStream

from agent_core.store.postgres import DeferredInterrupt, StoredEvent


class ProjectionStore(Protocol):
    async def append_event(
        self,
        run_id: str,
        event: BaseEvent,
        *,
        producer_key: str,
        terminal: bool = False,
    ) -> StoredEvent: ...

    async def replay(
        self,
        run_id: str,
        *,
        after_sequence: int,
    ) -> list[StoredEvent]: ...

    async def create_interrupt(
        self,
        *,
        run_id: str,
        semora_run_id: str,
        deferred_call_id: str,
        tool_call_id: str,
    ) -> DeferredInterrupt: ...


def producer_key(request_index: int, event_index: int, kind: str) -> str:
    return f"pydantic:{request_index}:{event_index}:{kind}"


class AGUIJournalProjector:
    def __init__(self, store: ProjectionStore) -> None:
        self._store = store

    async def started(self, run_id: str, thread_id: str) -> StoredEvent:
        return await self._store.append_event(
            run_id,
            RunStartedEvent(thread_id=thread_id, run_id=run_id),
            producer_key="run:started",
        )

    async def project(
        self,
        run_id: str,
        thread_id: str,
        native_events: AsyncIterator[Any],
        *,
        request_index: int = 0,
    ) -> None:
        committed = await self._store.replay(run_id, after_sequence=0)
        if any(
            item.event.get("type") in {"RUN_FINISHED", "RUN_ERROR"}
            for item in committed
        ):
            return

        message_id = next(
            (
                cast(str, item.event["messageId"])
                for item in committed
                if item.event.get("type") == "TEXT_MESSAGE_START"
                and isinstance(item.event.get("messageId"), str)
            ),
            None,
        )
        adapter = (
            AGUIEventStream(thread_id=thread_id, run_id=run_id, message_id=message_id)
            if message_id is not None
            else AGUIEventStream(thread_id=thread_id, run_id=run_id)
        )
        native_index = -1

        async def indexed_events() -> AsyncIterator[Any]:
            nonlocal native_index
            async for event in native_events:
                native_index += 1
                yield event

        async for transformed in adapter.transform_stream(indexed_events()):
            event = transformed
            if isinstance(event, RunErrorEvent):
                # Native stream errors may include private provider exception text.
                event = RunErrorEvent(
                    message="Agent execution failed", code="agent_failed"
                )
            if isinstance(event, RunFinishedEvent):
                # Semora publishes completion only after its durable attempt commits.
                continue
            if event.type.value == "RUN_STARTED":
                key = "run:started"
            elif event.type.value in {"RUN_FINISHED", "RUN_ERROR"}:
                key = "run:terminal"
            else:
                key = producer_key(request_index, native_index, event.type.value)
            await self._store.append_event(
                run_id,
                event,
                producer_key=key,
                terminal=key == "run:terminal",
            )

    async def fail(self, run_id: str, message: str, *, code: str) -> StoredEvent:
        public_message = message[:512] or "Agent execution failed"
        return await self._store.append_event(
            run_id,
            RunErrorEvent(message=public_message, code=code),
            producer_key="run:terminal",
            terminal=True,
        )

    async def completed_text(self, run_id: str, thread_id: str, text: str) -> None:
        del thread_id
        message_id = f"{run_id}:assistant"
        for key, event in (
            (
                "resume:text:start",
                TextMessageStartEvent(message_id=message_id, role="assistant"),
            ),
            (
                "resume:text:content",
                TextMessageContentEvent(message_id=message_id, delta=text),
            ),
            ("resume:text:end", TextMessageEndEvent(message_id=message_id)),
        ):
            await self._store.append_event(run_id, event, producer_key=key)

    async def finished(self, run_id: str, thread_id: str) -> StoredEvent:
        return await self._store.append_event(
            run_id,
            RunFinishedEvent(
                thread_id=thread_id,
                run_id=run_id,
                outcome=RunFinishedSuccessOutcome(),
            ),
            producer_key="run:terminal",
            terminal=True,
        )

    async def suspended(
        self,
        run_id: str,
        thread_id: str,
        pending: list[tuple[str, str]],
        *,
        semora_run_id: str,
    ) -> StoredEvent:
        interrupts: list[Interrupt] = []
        for pending_id, tool_call_id in pending:
            stored = await self._store.create_interrupt(
                run_id=run_id,
                semora_run_id=semora_run_id,
                deferred_call_id=pending_id,
                tool_call_id=tool_call_id,
            )
            interrupts.append(
                Interrupt(
                    id=stored.interrupt_id,
                    reason="tool_approval_required",
                    message="Approval required for tool execution.",
                    tool_call_id=tool_call_id,
                )
            )
        return await self._store.append_event(
            run_id,
            RunFinishedEvent(
                thread_id=thread_id,
                run_id=run_id,
                outcome=RunFinishedInterruptOutcome(interrupts=interrupts),
            ),
            producer_key="run:terminal",
            terminal=True,
        )


__all__ = ["AGUIJournalProjector", "ProjectionStore", "producer_key"]
