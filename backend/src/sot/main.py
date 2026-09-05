from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

from sot.api import create_app
from sot.domain.service import SOTService
from sot.legacy_agent import build_agent, build_model
from sot.settings import Settings
from sot.store.postgres import PostgresSOTRepository, apply_migrations

MIGRATIONS_PATH = Path(__file__).resolve().parents[2] / "migrations"


def build_app(settings: Settings) -> FastAPI:
    pool = AsyncConnectionPool(settings.database_url, open=False)
    service = SOTService(PostgresSOTRepository(pool))

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        await pool.open()
        try:
            await apply_migrations(pool, MIGRATIONS_PATH)
            if not await service.bootstrap(actor_id="alice"):
                await service.create_document(
                    actor_id="alice",
                    title="요청 제한 토큰",
                    content="초기 합의: 사용자별 작업 격리 정책을 검토한다.",
                )
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
