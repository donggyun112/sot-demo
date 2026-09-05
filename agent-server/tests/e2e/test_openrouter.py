import json
import os
from pathlib import Path

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool
from pydantic_ai.models.fallback import FallbackModel
from semora import AgentRuntime as SemoraRuntimeEngine
from semora_store_pg import PostgresSteps, PostgresTranscript
from uuid_utils import uuid7

from agent_core.agent import AgentRunAssembly, AgentSettings, build_deployment_agent
from agent_core.auth.policy import AuthenticatedAgentCaller
from agent_core.context import ContextLoader
from agent_core.projection import AGUIJournalProjector
from agent_core.runtime import SemoraAgentRuntime
from agent_core.service import AgentService
from agent_core.store.postgres import PostgresAgentStore
from agent_core.supervisor import RunSupervisor
from agent_core.tools import ToolRegistry, build_tool_controls

DATABASE_URL = os.environ.get(
    "AGENT_TEST_DATABASE_URL",
    "postgresql://agent:agent@localhost:54330/agent",
)
API_KEY = os.environ.get("OPENROUTER_API_KEY")
MIGRATIONS = Path(__file__).parents[2] / "migrations"

pytestmark = pytest.mark.e2e


def _caller() -> AuthenticatedAgentCaller:
    return AuthenticatedAgentCaller(
        owner_issuer="https://e2e.local",
        owner_subject_hash=b"e" * 32,
        agent_subject="agtsub:v1:e2e",
    )


def _payload(run_id: str, thread_id: str) -> bytes:
    return json.dumps(
        {
            "threadId": thread_id,
            "runId": run_id,
            "messages": [
                {
                    "id": str(uuid7()),
                    "role": "user",
                    "content": "Reply with exactly E2E_OK and nothing else.",
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        }
    ).encode()


async def _apply_migrations() -> None:
    async with await psycopg.AsyncConnection.connect(
        DATABASE_URL,
        autocommit=True,
    ) as connection:
        for name in (
            "001_agent.sql",
            "003_pydantic_ai.sql",
            "004_local_async.sql",
            "005_semora_0_3.sql",
        ):
            await connection.execute((MIGRATIONS / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_OPENROUTER_E2E") != "1" or not API_KEY,
    reason="set RUN_OPENROUTER_E2E=1 and OPENROUTER_API_KEY for the live test",
)
async def test_openrouter_run_survives_subscriber_disconnect(tmp_path: Path) -> None:
    assert API_KEY is not None
    await _apply_migrations()
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text(
        "Reply to the user directly and concisely.",
        encoding="utf-8",
    )
    settings = AgentSettings(
        name="discussion-agent",
        description="Answers one request.",
        system_prompt_file=prompt_file,
        prompt_revision="e2e-pydantic-v1",
        models=(
            f"openrouter:{os.environ.get('OPENROUTER_MODEL', 'openai/gpt-5-mini')}",
        ),
    )
    pool = AsyncConnectionPool(DATABASE_URL, min_size=1, max_size=4, open=False)
    await pool.open()
    await pool.wait()
    store = PostgresAgentStore(pool)
    projector = AGUIJournalProjector(store)
    registry = ToolRegistry()
    model = FallbackModel(settings.models[0], *settings.models[1:])
    runtime = SemoraAgentRuntime(
        agent=build_deployment_agent(
            settings=settings,
            registry=registry,
            model=model,
        ),
        engine=SemoraRuntimeEngine(
            PostgresSteps(pool),
            transcript=PostgresTranscript(pool),
        ),
        projector=projector,
        controls=build_tool_controls(registry),
    )
    service = AgentService(
        store=store,
        assembly=AgentRunAssembly(settings=settings, registry=registry),
        runtime=runtime,
        supervisor=RunSupervisor(),
        context_loader=ContextLoader(),
        prompt_revision=settings.prompt_revision,
        model_refs=settings.models,
        poll_interval=0.02,
    )
    run_id, thread_id = str(uuid7()), str(uuid7())

    try:
        await service.submit(_payload(run_id, thread_id), _caller())
        first_stream = service.stream(run_id, after_sequence=0)
        first = await anext(first_stream)
        await first_stream.aclose()
        reconnected = [
            event
            async for event in service.stream(
                run_id,
                after_sequence=first.sequence,
            )
        ]
        events = [first.event, *(event.event for event in reconnected)]

        assert events[0]["type"] == "RUN_STARTED"
        assert events[-1]["type"] == "RUN_FINISHED"
        assert sum(event["type"] == "RUN_STARTED" for event in events) == 1
        assert (
            sum(event["type"] in {"RUN_FINISHED", "RUN_ERROR"} for event in events) == 1
        )
    finally:
        await service.shutdown(timeout=5)
        async with pool.connection() as connection:
            await connection.execute(
                "DELETE FROM agent.agent_request WHERE run_id = %s",
                (run_id,),
            )
            await connection.execute(
                "DELETE FROM ledger_step WHERE run_id = %s",
                (run_id,),
            )
            await connection.execute(
                "DELETE FROM ledger_run_lease WHERE run_id = %s",
                (run_id,),
            )
            await connection.execute(
                "DELETE FROM ledger_input WHERE run_id = %s",
                (run_id,),
            )
            await connection.execute(
                "DELETE FROM ledger_transcript WHERE conversation_id = %s",
                (thread_id,),
            )
            await connection.execute(
                "DELETE FROM ledger_run WHERE run_id = %s",
                (run_id,),
            )
            await connection.execute(
                "DELETE FROM ledger_run_model WHERE run_id = %s",
                (run_id,),
            )
        await pool.close()
