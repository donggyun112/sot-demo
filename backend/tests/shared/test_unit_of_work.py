from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, cast

import pytest
from psycopg_pool import AsyncConnectionPool

from sot.bootstrap.database import (
    PostgresTransactionContext,
    PostgresUnitOfWork,
)
from sot.shared.errors import SOTError
from sot.shared.unit_of_work import TransactionContext


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        context = cast(TransactionContext, object())
        try:
            yield context
        except BaseException:
            self.rollbacks += 1
            raise
        else:
            self.commits += 1


class _FakeTransaction:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> None:
        self._connection.transactions += 1

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is None:
            self._connection.commits += 1
        else:
            self._connection.rollbacks += 1


class _FakeConnection:
    def __init__(self) -> None:
        self.transactions = 0
        self.commits = 0
        self.rollbacks = 0

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)


class _FakeConnectionLease:
    def __init__(self, pool: _FakePool) -> None:
        self._pool = pool

    async def __aenter__(self) -> _FakeConnection:
        self._pool.checkouts += 1
        return self._pool.connection_instance

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._pool.returns += 1


class _FakePool:
    def __init__(self) -> None:
        self.connection_instance = _FakeConnection()
        self.checkouts = 0
        self.returns = 0

    def connection(self) -> _FakeConnectionLease:
        return _FakeConnectionLease(self)


def test_sot_error_has_stable_code_and_safe_message() -> None:
    error = SOTError("version_conflict", "The resource changed")

    assert error.code == "version_conflict"
    assert error.message == "The resource changed"


@pytest.mark.asyncio
async def test_fake_uow_commits_once_on_success_and_rolls_back_once_on_error() -> None:
    success = FakeUnitOfWork()
    async with success.transaction():
        pass
    assert (success.commits, success.rollbacks) == (1, 0)

    failure = FakeUnitOfWork()
    with pytest.raises(RuntimeError):
        async with failure.transaction():
            raise RuntimeError("stop")
    assert (failure.commits, failure.rollbacks) == (0, 1)


@pytest.mark.asyncio
async def test_postgres_uow_owns_one_connection_and_transaction() -> None:
    pool = _FakePool()
    unit_of_work = PostgresUnitOfWork(cast(AsyncConnectionPool[Any], pool))

    async with unit_of_work.transaction() as context:
        assert isinstance(context, PostgresTransactionContext)
        assert context.connection is pool.connection_instance

    assert (pool.checkouts, pool.returns) == (1, 1)
    assert pool.connection_instance.transactions == 1
    assert (pool.connection_instance.commits, pool.connection_instance.rollbacks) == (
        1,
        0,
    )


@pytest.mark.asyncio
async def test_postgres_uow_leaves_rollback_to_psycopg_transaction() -> None:
    pool = _FakePool()
    unit_of_work = PostgresUnitOfWork(cast(AsyncConnectionPool[Any], pool))

    with pytest.raises(RuntimeError, match="stop"):
        async with unit_of_work.transaction():
            raise RuntimeError("stop")

    assert (pool.checkouts, pool.returns) == (1, 1)
    assert pool.connection_instance.transactions == 1
    assert (pool.connection_instance.commits, pool.connection_instance.rollbacks) == (
        0,
        1,
    )
