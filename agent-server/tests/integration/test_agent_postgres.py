import json
from pathlib import Path

import pytest
from ag_ui.core import RunErrorEvent, TextMessageContentEvent
from psycopg_pool import AsyncConnectionPool
from pydantic_ai import Agent, CancellationToken, DeferredToolRequests
from pydantic_ai.models.test import TestModel
from semora import AgentRuntime as SemoraRuntimeEngine
from semora_store_pg import PostgresSteps, PostgresTranscript
from uuid_utils import uuid7

from agent_core.admission import admit_run_input
from agent_core.agent import AgentRunDeps
from agent_core.auth.policy import AuthenticatedAgentCaller
from agent_core.command import RunInputMapper
from agent_core.projection import AGUIJournalProjector
from agent_core.runtime import SemoraAgentRuntime
from agent_core.store.postgres import (
    AgentRequestConflict,
    AgentRequestNotFound,
    PostgresAgentStore,
)
from agent_core.tools import ToolRegistry, build_tool_controls

MIGRATIONS = Path(__file__).parents[2] / "migrations"


def _caller(seed: bytes = b"a") -> AuthenticatedAgentCaller:
    return AuthenticatedAgentCaller(
        owner_issuer="https://issuer.example",
        owner_subject_hash=seed * 32,
        agent_subject="agtsub:v1:owner",
    )


def _payload(run_id: str, thread_id: str, text: str = "hello") -> bytes:
    return json.dumps(
        {
            "threadId": thread_id,
            "runId": run_id,
            "messages": [{"id": str(uuid7()), "role": "user", "content": text}],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        }
    ).encode()


async def _cleanup(pool: AsyncConnectionPool, run_id: str) -> None:
    async with pool.connection() as connection:
        await connection.execute(
            "DELETE FROM agent.agent_request WHERE run_id = %s",
            (run_id,),
        )


async def _columns(
    pool: AsyncConnectionPool,
    schema: str,
    table: str,
) -> set[str]:
    async with pool.connection() as connection:
        cursor = await connection.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = %s AND table_name = %s
            """,
            (schema, table),
        )
        return {row[0] for row in await cursor.fetchall()}


@pytest.mark.asyncio
async def test_runtime_columns_are_generic_and_producer_keys_are_idempotent(
    agent_pool: AsyncConnectionPool,
) -> None:
    request_columns = await _columns(agent_pool, "agent", "agent_request")
    interrupt_columns = await _columns(agent_pool, "agent", "agent_interrupt")
    assert "workflow_id" not in request_columns
    assert "workflow_id" not in interrupt_columns


@pytest.mark.asyncio
async def test_request_admission_is_owner_scoped_and_payload_idempotent(
    agent_pool: AsyncConnectionPool,
) -> None:
    run_id, thread_id = str(uuid7()), str(uuid7())
    store = PostgresAgentStore(agent_pool)
    admitted = admit_run_input(_payload(run_id, thread_id))
    try:
        first = await store.admit(
            admitted,
            _caller(),
            execution_config={"prompt_revision": "p1", "model": "m1"},
        )
        repeated = await store.admit(
            admitted,
            _caller(),
            execution_config={"prompt_revision": "p1", "model": "m1"},
        )

        assert first.created is True
        assert repeated.created is False
        assert repeated.request.run_id == run_id
        assert repeated.request.execution_config == {
            "prompt_revision": "p1",
            "model": "m1",
        }
        assert await store.get_request(run_id, _caller()) == repeated.request

        with pytest.raises(AgentRequestConflict):
            await store.admit(
                admit_run_input(_payload(run_id, thread_id, "changed")),
                _caller(),
                execution_config={"prompt_revision": "p1", "model": "m1"},
            )
        with pytest.raises(AgentRequestNotFound):
            await store.admit(
                admitted,
                _caller(b"b"),
                execution_config={"prompt_revision": "p1", "model": "m1"},
            )
    finally:
        await _cleanup(agent_pool, run_id)


@pytest.mark.asyncio
async def test_event_append_is_idempotent_and_terminal_closed(
    agent_pool: AsyncConnectionPool,
) -> None:
    run_id, thread_id = str(uuid7()), str(uuid7())
    store = PostgresAgentStore(agent_pool)
    await store.admit(
        admit_run_input(_payload(run_id, thread_id)),
        _caller(),
        execution_config={"prompt_revision": "p1", "model": "m1"},
    )
    try:
        terminal = await store.append_event(
            run_id,
            RunErrorEvent(message="stopped", code="aborted"),
            producer_key="run:terminal",
            terminal=True,
        )
        duplicate = await store.append_event(
            run_id,
            RunErrorEvent(message="different", code="agent_failed"),
            producer_key="run:terminal",
            terminal=True,
        )
        late = await store.append_event(
            run_id,
            TextMessageContentEvent(message_id="message-1", delta="late"),
            producer_key="pydantic:99:1:TEXT_MESSAGE_CONTENT",
        )

        assert duplicate.sequence == 1
        assert terminal.sequence == 1
        assert late == terminal
        replay = await store.replay(run_id, after_sequence=0)
        assert [item.sequence for item in replay] == [1]
        assert replay[0].event["type"] == "RUN_ERROR"
        assert await store.terminal_sequence(run_id) == 1
    finally:
        await _cleanup(agent_pool, run_id)


@pytest.mark.asyncio
async def test_abort_and_interrupt_mapping_are_canonical_in_postgres(
    agent_pool: AsyncConnectionPool,
) -> None:
    run_id, thread_id = str(uuid7()), str(uuid7())
    resume_run_id = str(uuid7())
    store = PostgresAgentStore(agent_pool)
    await store.admit(
        admit_run_input(_payload(run_id, thread_id)),
        _caller(),
        execution_config={"prompt_revision": "p1", "model": "m1"},
    )
    await store.admit(
        admit_run_input(_payload(resume_run_id, thread_id)),
        _caller(),
        execution_config={"prompt_revision": "p1", "model": "m1"},
    )
    try:
        interrupt = await store.create_interrupt(
            run_id=run_id,
            semora_run_id=run_id,
            deferred_call_id="pending-1",
            tool_call_id="call-1",
        )

        assert interrupt.deferred_call_id == "pending-1"
        assert interrupt.tool_call_id == "call-1"
        assert (
            await store.resolve_interrupt(interrupt.interrupt_id, _caller())
            == interrupt
        )
        repeated = await store.create_interrupt(
            run_id=resume_run_id,
            semora_run_id=run_id,
            deferred_call_id="pending-1",
            tool_call_id="call-1",
        )
        assert repeated == interrupt
        assert await store.is_aborted(run_id) is False
        await store.request_abort(run_id, _caller())
        assert await store.is_aborted(run_id) is True
    finally:
        await _cleanup(agent_pool, resume_run_id)
        await _cleanup(agent_pool, run_id)


@pytest.mark.asyncio
async def test_semora_0_3_ledger_and_transcript_schema_is_installed(
    agent_pool: AsyncConnectionPool,
) -> None:
    async with agent_pool.connection() as connection:
        cursor = await connection.execute(
            """
            SELECT to_regclass(name)
              FROM unnest(%s::text[]) AS name
             ORDER BY name
            """,
            (
                [
                    "ledger_input",
                    "ledger_run",
                    "ledger_run_lease",
                    "ledger_run_model",
                    "ledger_step",
                    "ledger_transcript",
                ],
            ),
        )
        rows = await cursor.fetchall()

    assert all(row[0] is not None for row in rows)


@pytest.mark.asyncio
async def test_semora_runtime_commits_postgres_ledger_transcript_and_public_events(
    agent_pool: AsyncConnectionPool,
) -> None:
    run_id, thread_id = str(uuid7()), str(uuid7())
    payload = _payload(run_id, thread_id)
    store = PostgresAgentStore(agent_pool)
    admitted = admit_run_input(payload)
    await store.admit(admitted, _caller(), execution_config={})
    mapped = await RunInputMapper().map(admitted.input, subject=_caller().agent_subject)
    deps = AgentRunDeps(mapped.identity, "trusted instructions", ())
    registry = ToolRegistry()
    runtime = SemoraAgentRuntime(
        agent=Agent(
            TestModel(),
            deps_type=AgentRunDeps,
            output_type=[str, DeferredToolRequests],
        ),
        engine=SemoraRuntimeEngine(
            PostgresSteps(agent_pool),
            transcript=PostgresTranscript(agent_pool),
        ),
        projector=AGUIJournalProjector(store),
        controls=build_tool_controls(registry),
    )

    try:
        await runtime.execute(mapped, deps, CancellationToken())

        assert await store.terminal_sequence(run_id) is not None
        async with agent_pool.connection() as connection:
            ledger = await connection.execute(
                "SELECT count(*) FROM ledger_step WHERE run_id = %s",
                (run_id,),
            )
            transcript = await connection.execute(
                "SELECT count(*) FROM ledger_transcript WHERE conversation_id = %s",
                (thread_id,),
            )
            assert (await ledger.fetchone())[0] > 0  # type: ignore[index]
            assert (await transcript.fetchone())[0] > 0  # type: ignore[index]
    finally:
        async with agent_pool.connection() as connection:
            for table in (
                "ledger_input",
                "ledger_run_model",
                "ledger_run",
                "ledger_run_lease",
                "ledger_step",
            ):
                await connection.execute(
                    f"DELETE FROM {table} WHERE run_id = %s",
                    (run_id,),
                )
            await connection.execute(
                "DELETE FROM ledger_transcript WHERE conversation_id = %s",
                (thread_id,),
            )
        await _cleanup(agent_pool, run_id)


@pytest.mark.asyncio
async def test_runtime_migrations_are_raw_chain_repeatable(
    agent_pool: AsyncConnectionPool,
) -> None:
    migration_003 = (MIGRATIONS / "003_pydantic_ai.sql").read_text(encoding="utf-8")
    migration_004 = (MIGRATIONS / "004_local_async.sql").read_text(encoding="utf-8")
    migration_005 = (MIGRATIONS / "005_semora_0_3.sql").read_text(encoding="utf-8")

    async with agent_pool.connection() as connection:
        for _ in range(2):
            await connection.execute(migration_003)
            await connection.execute(migration_004)
            await connection.execute(migration_005)
