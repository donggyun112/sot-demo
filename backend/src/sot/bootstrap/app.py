from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

from sot.api import create_app
from sot.bootstrap.settings import Settings
from sot.domain.service import SOTService
from sot.legacy_agent import build_agent, build_model
from sot.store.postgres import PostgresSOTRepository


def build_app(settings: Settings) -> FastAPI:
    pool = AsyncConnectionPool(settings.database_url, open=False)
    service = SOTService(PostgresSOTRepository(pool))

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        await pool.open()
        try:
            application.state.pool = pool
            yield
        finally:
            await pool.close()

    application = create_app(
        service=service,
        agent=build_agent(build_model(settings.models)),
        cors_origins=settings.cors_origins,
        lifespan=lifespan,
    )
    application.state.pool = pool
    return application


app = build_app(Settings())

__all__ = ["app", "build_app"]
