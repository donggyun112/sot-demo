from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest_asyncio
from psycopg_pool import AsyncConnectionPool

DATABASE_URL = "postgresql://agent:agent@localhost:54330/agent"
MIGRATIONS = Path(__file__).parents[2] / "migrations"


@pytest_asyncio.fixture(scope="session")
async def agent_pool() -> AsyncIterator[AsyncConnectionPool]:
    async with await psycopg.AsyncConnection.connect(
        DATABASE_URL,
        autocommit=True,
    ) as connection:
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            await connection.execute(migration.read_text(encoding="utf-8"))

    pool = AsyncConnectionPool(DATABASE_URL, min_size=1, max_size=4, open=False)
    await pool.open()
    await pool.wait()
    try:
        yield pool
    finally:
        await pool.close()
