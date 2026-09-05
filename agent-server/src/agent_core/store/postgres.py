from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from ag_ui.core import BaseEvent
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from uuid_utils import uuid7

from agent_core.admission import AdmittedRunInput
from agent_core.auth.policy import AuthenticatedAgentCaller


class AgentRequestConflict(Exception):
    pass


class AgentRequestNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AgentRequest:
    run_id: str
    thread_id: str
    original_input: dict[str, Any]
    terminal_sequence: int | None
    execution_config: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    request: AgentRequest
    created: bool


@dataclass(frozen=True, slots=True)
class StoredEvent:
    sequence: int
    event_id: str
    event: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DeferredInterrupt:
    interrupt_id: str
    origin_run_id: str
    semora_run_id: str
    deferred_call_id: str
    tool_call_id: str


class PostgresAgentStore:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def admit(
        self,
        admitted: AdmittedRunInput,
        caller: AuthenticatedAgentCaller,
        *,
        execution_config: dict[str, Any],
    ) -> AdmissionResult:
        request = admitted.input
        original_input = json.loads(admitted.canonical_payload)
        request_kind = "resume" if request.resume else "prompt"
        async with (
            self._pool.connection() as connection,
            connection.transaction(),
        ):
            inserted = await connection.execute(
                """
                    INSERT INTO agent.agent_request (
                        run_id, thread_id, request_kind,
                        owner_issuer, owner_subject_hash, original_input,
                        payload_hash, execution_config
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO NOTHING
                    RETURNING run_id
                    """,
                (
                    request.run_id,
                    request.thread_id,
                    request_kind,
                    caller.owner_issuer,
                    caller.owner_subject_hash,
                    Jsonb(original_input),
                    admitted.payload_hash,
                    Jsonb(execution_config),
                ),
            )
            created = await inserted.fetchone() is not None
            cursor = await connection.execute(
                """
                    SELECT run_id, thread_id, owner_issuer, owner_subject_hash,
                           original_input, payload_hash, terminal_sequence,
                           execution_config
                      FROM agent.agent_request
                     WHERE run_id = %s
                    """,
                (request.run_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise AgentRequestNotFound
            if (
                row[2] != caller.owner_issuer
                or bytes(row[3]) != caller.owner_subject_hash
            ):
                raise AgentRequestNotFound
            if bytes(row[5]) != admitted.payload_hash:
                raise AgentRequestConflict
            return AdmissionResult(
                request=AgentRequest(
                    run_id=str(row[0]),
                    thread_id=str(row[1]),
                    original_input=row[4],
                    terminal_sequence=row[6],
                    execution_config=row[7],
                ),
                created=created,
            )

    async def append_event(
        self,
        run_id: str,
        event: BaseEvent,
        *,
        producer_key: str,
        terminal: bool = False,
    ) -> StoredEvent:
        payload = event.model_dump(mode="json", by_alias=True)
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM agent.append_event(%s, %s, %s, %s, %s, %s)",
                (
                    run_id,
                    str(uuid7()),
                    producer_key,
                    event.type.value,
                    Jsonb(payload),
                    terminal,
                ),
            )
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("append_event returned no row")
        return StoredEvent(sequence=row[1], event_id=str(row[2]), event=row[5])

    async def replay(self, run_id: str, *, after_sequence: int) -> list[StoredEvent]:
        async with (
            self._pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(
                """
                    SELECT sequence, event_id, event
                      FROM agent.agent_event
                     WHERE run_id = %s AND sequence > %s
                     ORDER BY sequence
                    """,
                (run_id, after_sequence),
            )
            rows = await cursor.fetchall()
        return [
            StoredEvent(
                sequence=row["sequence"],
                event_id=str(row["event_id"]),
                event=row["event"],
            )
            for row in rows
        ]

    async def get_request(
        self,
        run_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> AgentRequest:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT run_id, thread_id, original_input, terminal_sequence,
                       execution_config
                  FROM agent.agent_request
                 WHERE run_id = %s
                   AND owner_issuer = %s
                   AND owner_subject_hash = %s
                """,
                (run_id, caller.owner_issuer, caller.owner_subject_hash),
            )
            row = await cursor.fetchone()
        if row is None:
            raise AgentRequestNotFound
        return AgentRequest(
            run_id=str(row[0]),
            thread_id=str(row[1]),
            original_input=row[2],
            terminal_sequence=row[3],
            execution_config=row[4],
        )

    async def terminal_sequence(self, run_id: str) -> int | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT terminal_sequence FROM agent.agent_request WHERE run_id = %s",
                (run_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise AgentRequestNotFound
        return cast(int | None, row[0])

    async def create_interrupt(
        self,
        *,
        run_id: str,
        semora_run_id: str,
        deferred_call_id: str,
        tool_call_id: str,
    ) -> DeferredInterrupt:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO agent.agent_interrupt (
                    interrupt_id, origin_run_id, runtime_run_id,
                    deferred_call_id, tool_call_id
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (runtime_run_id, deferred_call_id) DO UPDATE
                    SET deferred_call_id = EXCLUDED.deferred_call_id
                RETURNING interrupt_id, origin_run_id, runtime_run_id,
                          deferred_call_id, tool_call_id
                """,
                (
                    str(uuid7()),
                    run_id,
                    semora_run_id,
                    deferred_call_id,
                    tool_call_id,
                ),
            )
            row = await cursor.fetchone()
        assert row is not None
        return DeferredInterrupt(str(row[0]), str(row[1]), str(row[2]), row[3], row[4])

    async def resolve_interrupt(
        self,
        interrupt_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> DeferredInterrupt:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT i.interrupt_id, i.origin_run_id, i.runtime_run_id,
                       i.deferred_call_id, i.tool_call_id
                  FROM agent.agent_interrupt AS i
                  JOIN agent.agent_request AS r ON r.run_id = i.origin_run_id
                 WHERE i.interrupt_id = %s
                   AND r.owner_issuer = %s
                   AND r.owner_subject_hash = %s
                """,
                (interrupt_id, caller.owner_issuer, caller.owner_subject_hash),
            )
            row = await cursor.fetchone()
        if row is None:
            raise AgentRequestNotFound
        return DeferredInterrupt(str(row[0]), str(row[1]), str(row[2]), row[3], row[4])

    async def request_abort(
        self,
        run_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                UPDATE agent.agent_request
                   SET abort_requested_at = COALESCE(abort_requested_at, clock_timestamp())
                 WHERE run_id = %s
                   AND owner_issuer = %s
                   AND owner_subject_hash = %s
                RETURNING run_id
                """,
                (run_id, caller.owner_issuer, caller.owner_subject_hash),
            )
            if await cursor.fetchone() is None:
                raise AgentRequestNotFound

    async def is_aborted(self, run_id: str) -> bool:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT abort_requested_at IS NOT NULL
                  FROM agent.agent_request WHERE run_id = %s
                """,
                (run_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise AgentRequestNotFound
        return bool(row[0])


__all__ = [
    "AdmissionResult",
    "AgentRequest",
    "AgentRequestConflict",
    "AgentRequestNotFound",
    "DeferredInterrupt",
    "PostgresAgentStore",
    "StoredEvent",
]
