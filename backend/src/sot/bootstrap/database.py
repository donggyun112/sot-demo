from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from sot.shared.unit_of_work import TransactionContext


@dataclass(frozen=True, slots=True)
class PostgresTransactionContext:
    connection: AsyncConnection[Any]


class PostgresUnitOfWork:
    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        async with (
            self._pool.connection() as connection,
            connection.transaction(),
        ):
            yield PostgresTransactionContext(connection)


__all__ = ["PostgresTransactionContext", "PostgresUnitOfWork"]
