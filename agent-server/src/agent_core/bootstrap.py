from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from pydantic import ValidationError
from pydantic_ai import UserError
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from semora import AgentRuntime as SemoraRuntimeEngine
from semora_store_pg import PostgresSteps, PostgresTranscript
from service_auth import AccessTokenVerifier, SystemClock
from service_auth.jwks import AsyncJwksProvider, HttpxJwksFetcher

from agent_core.agent import AgentRunAssembly, AgentSettings, build_deployment_agent
from agent_core.api.app import create_app
from agent_core.auth.http import AgentAuthenticator
from agent_core.auth.policy import AgentAuthPolicy
from agent_core.auth.settings import AgentAuthSettings
from agent_core.context import ContextLoader
from agent_core.projection import AGUIJournalProjector
from agent_core.runtime import SemoraAgentRuntime
from agent_core.service import AgentService
from agent_core.store.config import AgentDatabaseSettings
from agent_core.store.postgres import PostgresAgentStore
from agent_core.supervisor import ExecutionSettings, RunSupervisor
from agent_core.tools import ToolRegistry, build_tool_controls


class _LifecyclePool(Protocol):
    async def open(self) -> None: ...

    async def wait(self) -> None: ...

    async def close(self) -> None: ...


class _LifecycleKeys(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...


class _LifecycleService(Protocol):
    async def shutdown(self, *, timeout: float) -> None: ...


@asynccontextmanager
async def _runtime_lifespan(
    *,
    pool: _LifecyclePool,
    keys: _LifecycleKeys,
    service: _LifecycleService,
    shutdown_timeout: float,
) -> AsyncIterator[None]:
    await pool.open()
    await pool.wait()
    await keys.start()
    try:
        yield
    finally:
        await service.shutdown(timeout=shutdown_timeout)
        await keys.close()
        await pool.close()


def _compose_model_chain(model_refs: tuple[str, ...]) -> Model:
    return FallbackModel(model_refs[0], *model_refs[1:])


def create_environment_app() -> FastAPI:
    try:
        agent_settings = AgentSettings()
        auth_settings = AgentAuthSettings()
        database_settings = AgentDatabaseSettings()
        execution_settings = ExecutionSettings()
    except (ValidationError, ValueError, UserError, ImportError):
        return create_app()

    try:
        model = _compose_model_chain(agent_settings.models)
    except Exception:  # noqa: BLE001 - provider initialization errors are configuration failures
        return create_app()

    pool = AsyncConnectionPool(
        database_settings.database_url,
        min_size=1,
        max_size=36,
        open=False,
    )
    store = PostgresAgentStore(pool)
    projector = AGUIJournalProjector(store)
    registry = ToolRegistry()
    deployment_agent = build_deployment_agent(
        settings=agent_settings,
        registry=registry,
        model=model,
    )
    runtime = SemoraAgentRuntime(
        agent=deployment_agent,
        engine=SemoraRuntimeEngine(
            PostgresSteps(pool),
            transcript=PostgresTranscript(pool),
            lease_ttl=execution_settings.lease_ttl_seconds,
        ),
        projector=projector,
        controls=build_tool_controls(registry),
        rules_version=agent_settings.prompt_revision,
    )
    service = AgentService(
        store=store,
        assembly=AgentRunAssembly(
            settings=agent_settings,
            registry=registry,
        ),
        runtime=runtime,
        supervisor=RunSupervisor(capacity=execution_settings.capacity),
        context_loader=ContextLoader(),
        prompt_revision=agent_settings.prompt_revision,
        model_refs=agent_settings.models,
    )

    clock = SystemClock()
    keys = AsyncJwksProvider(
        auth_settings.verification_profile(),
        HttpxJwksFetcher(auth_settings.jwks_uri),
        clock,
    )
    verifier = AccessTokenVerifier(auth_settings.verification_profile(), keys, clock)
    authenticator = AgentAuthenticator(
        verifier,
        AgentAuthPolicy(auth_settings.allowed_client_ids),
    )

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        async with _runtime_lifespan(
            pool=pool,
            keys=keys,
            service=service,
            shutdown_timeout=execution_settings.shutdown_timeout_seconds,
        ):
            yield

    return create_app(
        service=service,
        authenticate=authenticator,
        lifespan=lifespan,
    )


__all__ = ["create_environment_app"]
