from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection

from sot.bootstrap.database import PostgresTransactionContext
from sot.identity.contracts import IdentityAttribution, UserNotFound
from sot.identity.domain import AuthSession, User, VerifiedIdentity
from sot.shared.ids import UserId
from sot.shared.unit_of_work import TransactionContext


def connection(tx: TransactionContext) -> AsyncConnection[Any]:
    if not isinstance(tx, PostgresTransactionContext):
        raise TypeError("PostgreSQL transaction required")
    return tx.connection


class PostgresIdentityRepository:
    async def require_attribution(
        self, tx: TransactionContext, user_id: UserId
    ) -> IdentityAttribution:
        row = await (
            await connection(tx).execute(
                "SELECT display_name FROM sot.sot_user WHERE id=%s", (user_id,)
            )
        ).fetchone()
        if row is None:
            raise UserNotFound()
        return IdentityAttribution(row[0])

    async def upsert_identity(
        self, tx: TransactionContext, identity: VerifiedIdentity
    ) -> User:
        conn = connection(tx)
        # Serialize absent identity creation too, without locking unrelated identities.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (json.dumps([identity.issuer, identity.subject]),),
        )
        row = await (
            await conn.execute(
                "SELECT user_id FROM sot.sot_user_identity WHERE issuer=%s AND subject=%s",
                (identity.issuer, identity.subject),
            )
        ).fetchone()
        user_id = UserId(row[0]) if row else UserId(uuid4())
        await conn.execute(
            "INSERT INTO sot.sot_user(id,email,display_name) VALUES (%s,%s,%s) "
            "ON CONFLICT(id) DO UPDATE SET email=excluded.email, display_name=excluded.display_name",
            (user_id, identity.email, identity.display_name),
        )
        if row is None:
            await conn.execute(
                "INSERT INTO sot.sot_user_identity(id,user_id,issuer,subject) VALUES (%s,%s,%s,%s)",
                (uuid4(), user_id, identity.issuer, identity.subject),
            )
        return User(user_id, identity.email, identity.display_name)

    async def get_user(self, tx: TransactionContext, user_id: UserId) -> User | None:
        row = await (
            await connection(tx).execute(
                "SELECT id,email,display_name FROM sot.sot_user WHERE id=%s", (user_id,)
            )
        ).fetchone()
        return User(UserId(row[0]), row[1], row[2]) if row else None

    async def add_session(self, tx: TransactionContext, session: AuthSession) -> None:
        await connection(tx).execute(
            "INSERT INTO sot.sot_auth_session(id,user_id,token_hash,family_id,expires_at,revoked_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                session.id,
                session.user_id,
                session.token_hash,
                session.family_id,
                session.expires_at,
                session.revoked_at,
            ),
        )

    async def find_session(
        self, tx: TransactionContext, token_hash: str
    ) -> AuthSession | None:
        conn = connection(tx)
        row = await (
            await conn.execute(
                "SELECT user_id FROM sot.sot_auth_session WHERE token_hash=%s",
                (token_hash,),
            )
        ).fetchone()
        if row is None:
            return None
        # All refresh/logout-all operations lock the same user before reading mutable session state.
        await conn.execute(
            "SELECT id FROM sot.sot_user WHERE id=%s FOR UPDATE", (row[0],)
        )
        row = await (
            await conn.execute(
                "SELECT id,user_id,token_hash,family_id,expires_at,revoked_at "
                "FROM sot.sot_auth_session WHERE token_hash=%s FOR UPDATE",
                (token_hash,),
            )
        ).fetchone()
        return (
            AuthSession(row[0], UserId(row[1]), row[2], row[3], row[4], row[5])
            if row
            else None
        )

    async def revoke_token(
        self, tx: TransactionContext, token_hash: str, now: datetime
    ) -> None:
        await connection(tx).execute(
            "UPDATE sot.sot_auth_session SET revoked_at=%s WHERE token_hash=%s AND revoked_at IS NULL",
            (now, token_hash),
        )

    async def revoke_family(
        self, tx: TransactionContext, family_id: UUID, now: datetime
    ) -> None:
        await connection(tx).execute(
            "UPDATE sot.sot_auth_session SET revoked_at=%s WHERE family_id=%s AND revoked_at IS NULL",
            (now, family_id),
        )

    async def revoke_all(
        self, tx: TransactionContext, user_id: UserId, now: datetime
    ) -> None:
        conn = connection(tx)
        await conn.execute(
            "SELECT id FROM sot.sot_user WHERE id=%s FOR UPDATE", (user_id,)
        )
        await conn.execute(
            "UPDATE sot.sot_auth_session SET revoked_at=%s WHERE user_id=%s AND revoked_at IS NULL",
            (now, user_id),
        )
