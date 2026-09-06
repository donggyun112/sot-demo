from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from sot.bootstrap.database import PostgresUnitOfWork
from sot.bootstrap.migrate import run_migrations
from sot.identity.application import AuthFacade
from sot.identity.contracts import Actor
from sot.identity.domain import AuthTokenInvalid, VerifiedIdentity
from sot.identity.postgres import PostgresIdentityRepository
from sot.identity.tokens import SOTAccessTokenCodec
from sot.shared.ids import UserId
from tests.identity.test_auth_facade import FakeClock, FakeProvider

DATABASE_URL = "postgresql://sot:sot@localhost:54329/sot"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_identity_transactions_rotation_concurrency_and_logout_all() -> None:
    await run_migrations(DATABASE_URL, Path(__file__).parents[2] / "migrations")
    async with AsyncConnectionPool[Any](DATABASE_URL, open=False) as pool:
        repo, clock = PostgresIdentityRepository(), FakeClock()
        uow = lambda: PostgresUnitOfWork(pool)
        facade = AuthFacade(
            {"google": FakeProvider()},
            repo,
            uow,
            SOTAccessTokenCodec("s" * 32, clock, timedelta(minutes=15)),
            clock,
            timedelta(days=30),
        )
        first, second = await asyncio.gather(
            *[
                facade.login(provider_name="google", credential=email)
                for email in ("old@example.com", "new@example.com")
            ]
        )
        assert first.user.id == second.user.id
        results = await asyncio.gather(
            *[facade.refresh(first.tokens.refresh_token) for _ in range(2)],
            return_exceptions=True,
        )
        assert sum(isinstance(result, AuthTokenInvalid) for result in results) == 1
        winner = next(
            result for result in results if not isinstance(result, BaseException)
        )
        with pytest.raises(AuthTokenInvalid):
            await facade.refresh(winner.tokens.refresh_token)
        second_rotated = await facade.refresh(second.tokens.refresh_token)
        await facade.logout_all(Actor(first.user.id))
        with pytest.raises(AuthTokenInvalid):
            await facade.refresh(second_rotated.tokens.refresh_token)
        async with uow().transaction() as tx:
            assert await repo.get_user(tx, first.user.id)
            assert await repo.get_user(tx, UserId(uuid4())) is None
        # User identity is issuer+subject, even when verified emails match.
        async with uow().transaction() as tx:
            other = await repo.upsert_identity(
                tx, VerifiedIdentity("other", str(uuid4()), "new@example.com", "Other")
            )
        assert other.id != first.user.id
        unique_subject = str(uuid4())
        with pytest.raises(RuntimeError):
            async with uow().transaction() as tx:
                await repo.upsert_identity(
                    tx, VerifiedIdentity("rollback", unique_subject, "x", "X")
                )
                raise RuntimeError("rollback")
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as connection:
            row = await (
                await connection.execute(
                    "SELECT count(*) FROM sot.sot_user_identity WHERE subject = %s",
                    (unique_subject,),
                )
            ).fetchone()
            assert row == (0,)
            raw = await (
                await connection.execute(
                    "SELECT token_hash FROM sot.sot_auth_session WHERE user_id = %s",
                    (first.user.id,),
                )
            ).fetchall()
            assert raw and all(len(value[0]) == 64 for value in raw)
