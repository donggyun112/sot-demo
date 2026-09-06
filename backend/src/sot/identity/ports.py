from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sot.identity.domain import AuthSession, User, VerifiedIdentity
from sot.shared.ids import UserId
from sot.shared.unit_of_work import TransactionContext


class IdentityRepository(Protocol):
    async def upsert_identity(
        self, tx: TransactionContext, identity: VerifiedIdentity
    ) -> User: ...
    async def get_user(
        self, tx: TransactionContext, user_id: UserId
    ) -> User | None: ...
    async def add_session(
        self, tx: TransactionContext, session: AuthSession
    ) -> None: ...
    async def find_session(
        self, tx: TransactionContext, token_hash: str
    ) -> AuthSession | None:
        """Lock this user's auth mutations until transaction completion."""
        ...

    async def revoke_token(
        self, tx: TransactionContext, token_hash: str, now: datetime
    ) -> None: ...
    async def revoke_family(
        self, tx: TransactionContext, family_id: UUID, now: datetime
    ) -> None: ...
    async def revoke_all(
        self, tx: TransactionContext, user_id: UserId, now: datetime
    ) -> None: ...


class AccessTokenCodec(Protocol):
    def encode(self, user_id: UserId) -> str: ...
    def decode(self, token: str) -> UserId: ...
