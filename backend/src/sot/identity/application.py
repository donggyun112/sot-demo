from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid4

from sot.identity.contracts import Actor
from sot.identity.domain import AuthSession, AuthTokenInvalid, User
from sot.identity.ports import AccessTokenCodec, IdentityRepository
from sot.identity.providers.base import AuthProvider
from sot.shared.clock import Clock
from sot.shared.ids import UserId
from sot.shared.unit_of_work import TransactionContext, UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: User
    tokens: TokenPair


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AuthFacade:
    def __init__(
        self,
        providers: Mapping[str, AuthProvider],
        repository: IdentityRepository,
        uow_factory: UnitOfWorkFactory,
        codec: AccessTokenCodec,
        clock: Clock,
        refresh_lifetime: timedelta,
    ) -> None:
        self._providers, self._repository, self._uow_factory = (
            providers,
            repository,
            uow_factory,
        )
        self._codec, self._clock, self._refresh_lifetime = (
            codec,
            clock,
            refresh_lifetime,
        )

    async def _issue(
        self, tx: TransactionContext, user: User, family_id: UUID
    ) -> AuthResult:
        raw = secrets.token_urlsafe(48)
        await self._repository.add_session(
            tx,
            AuthSession(
                uuid4(),
                user.id,
                token_hash(raw),
                family_id,
                self._clock.now() + self._refresh_lifetime,
            ),
        )
        return AuthResult(user, TokenPair(self._codec.encode(user.id), raw))

    async def login(self, *, provider_name: str, credential: str) -> AuthResult:
        provider = self._providers.get(provider_name)
        if provider is None:
            raise AuthTokenInvalid()
        identity = await provider.verify(credential)
        async with self._uow_factory().transaction() as tx:
            user = await self._repository.upsert_identity(tx, identity)
            return await self._issue(tx, user, uuid4())

    async def refresh(self, raw: str) -> AuthResult:
        result = None
        async with self._uow_factory().transaction() as tx:
            session = await self._repository.find_session(tx, token_hash(raw))
            now = self._clock.now()
            if session is not None:
                if session.revoked_at is not None or session.expires_at <= now:
                    await self._repository.revoke_family(tx, session.family_id, now)
                else:
                    user = await self._repository.get_user(tx, session.user_id)
                    if user is not None:
                        await self._repository.revoke_token(tx, session.token_hash, now)
                        result = await self._issue(tx, user, session.family_id)
        # Reuse revocation must commit before reporting authentication failure.
        if result is None:
            raise AuthTokenInvalid()
        return result

    async def logout(self, raw: str) -> None:
        async with self._uow_factory().transaction() as tx:
            session = await self._repository.find_session(tx, token_hash(raw))
            if session is not None:
                await self._repository.revoke_family(
                    tx, session.family_id, self._clock.now()
                )

    async def logout_all(self, actor: Actor) -> None:
        async with self._uow_factory().transaction() as tx:
            await self._repository.revoke_all(tx, actor.user_id, self._clock.now())

    async def require_actor(self, tx: TransactionContext, user_id: UserId) -> Actor:
        if await self._repository.get_user(tx, user_id) is None:
            raise AuthTokenInvalid()
        return Actor(user_id)

    async def authenticate(self, access_token: str) -> Actor:
        user_id = self._codec.decode(access_token)
        async with self._uow_factory().transaction() as tx:
            return await self.require_actor(tx, user_id)

    async def user(self, actor: Actor) -> User:
        async with self._uow_factory().transaction() as tx:
            user = await self._repository.get_user(tx, actor.user_id)
            if user is None:
                raise AuthTokenInvalid()
            return user
