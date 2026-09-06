from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from sot.identity.application import AuthFacade
from sot.identity.contracts import Actor
from sot.identity.domain import AuthSession, AuthTokenInvalid, User, VerifiedIdentity
from sot.identity.tokens import SOTAccessTokenCodec
from sot.shared.ids import UserId
from sot.shared.unit_of_work import TransactionContext


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime.now(UTC).replace(microsecond=0)

    def now(self) -> datetime:
        return self.value


class FakeProvider:
    async def verify(self, credential: str) -> VerifiedIdentity:
        return VerifiedIdentity(
            "https://accounts.google.com", "google-123", credential, "Alice"
        )


class MemoryIdentityRepository:
    def __init__(self) -> None:
        self.users: dict[UserId, User] = {}
        self.identities: dict[tuple[str, str], UserId] = {}
        self.sessions: dict[str, AuthSession] = {}

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        before = (self.users.copy(), self.identities.copy(), self.sessions.copy())
        try:
            yield object()
        except BaseException:
            self.users, self.identities, self.sessions = before
            raise

    async def upsert_identity(
        self, tx: TransactionContext, identity: VerifiedIdentity
    ) -> User:
        key = (identity.issuer, identity.subject)
        user_id = self.identities.setdefault(key, UserId(uuid4()))
        user = User(user_id, identity.email, identity.display_name)
        self.users[user_id] = user
        return user

    async def get_user(self, tx: TransactionContext, user_id: UserId) -> User | None:
        return self.users.get(user_id)

    async def add_session(self, tx: TransactionContext, session: AuthSession) -> None:
        self.sessions[session.token_hash] = session

    async def find_session(
        self, tx: TransactionContext, token_hash: str
    ) -> AuthSession | None:
        return self.sessions.get(token_hash)

    async def revoke_token(
        self, tx: TransactionContext, token_hash: str, now: datetime
    ) -> None:
        self.sessions[token_hash] = replace(self.sessions[token_hash], revoked_at=now)

    async def revoke_family(
        self, tx: TransactionContext, family_id: object, now: datetime
    ) -> None:
        for key, session in self.sessions.items():
            if session.family_id == family_id:
                self.sessions[key] = replace(session, revoked_at=now)

    async def revoke_all(
        self, tx: TransactionContext, user_id: UserId, now: datetime
    ) -> None:
        for key, session in self.sessions.items():
            if session.user_id == user_id:
                self.sessions[key] = replace(session, revoked_at=now)


def make_facade() -> tuple[
    AuthFacade, MemoryIdentityRepository, FakeClock, SOTAccessTokenCodec
]:
    repo, clock = MemoryIdentityRepository(), FakeClock()
    codec = SOTAccessTokenCodec("s" * 32, clock, timedelta(minutes=15))
    facade = AuthFacade(
        {"google": FakeProvider()}, repo, lambda: repo, codec, clock, timedelta(days=30)
    )
    return facade, repo, clock, codec


@pytest.mark.asyncio
async def test_login_links_issuer_subject_and_issues_sot_tokens() -> None:
    facade, repo, _, codec = make_facade()
    first = await facade.login(provider_name="google", credential="alice@example.com")
    second = await facade.login(
        provider_name="google", credential="changed@example.com"
    )
    assert first.user.id == second.user.id
    assert second.user.email == "changed@example.com"
    assert await facade.authenticate(first.tokens.access_token) == Actor(first.user.id)
    claims = jwt.decode(
        first.tokens.access_token, "s" * 32, algorithms=["HS256"], issuer="sot"
    )
    assert set(claims) == {"sub", "iat", "exp", "iss", "jti"}
    assert codec.decode(first.tokens.access_token) == first.user.id
    assert all(
        session.token_hash != first.tokens.refresh_token
        for session in repo.sessions.values()
    )


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_only_the_reused_family_and_commits_revocation() -> (
    None
):
    facade, _, _, _ = make_facade()
    first = await facade.login(provider_name="google", credential="first")
    second = await facade.login(provider_name="google", credential="second")
    rotated = await facade.refresh(first.tokens.refresh_token)
    assert rotated.tokens.refresh_token != first.tokens.refresh_token
    with pytest.raises(AuthTokenInvalid):
        await facade.refresh(first.tokens.refresh_token)
    with pytest.raises(AuthTokenInvalid):
        await facade.refresh(rotated.tokens.refresh_token)
    assert await facade.refresh(second.tokens.refresh_token)


@pytest.mark.asyncio
async def test_logout_family_and_logout_all_devices() -> None:
    facade, _, _, _ = make_facade()
    first = await facade.login(provider_name="google", credential="first")
    second = await facade.login(provider_name="google", credential="second")
    await facade.logout(first.tokens.refresh_token)
    with pytest.raises(AuthTokenInvalid):
        await facade.refresh(first.tokens.refresh_token)
    rotated = await facade.refresh(second.tokens.refresh_token)
    await facade.logout_all(Actor(first.user.id))
    with pytest.raises(AuthTokenInvalid):
        await facade.refresh(rotated.tokens.refresh_token)


@pytest.mark.asyncio
async def test_expired_unknown_and_deleted_user_tokens_are_rejected() -> None:
    facade, repo, clock, _ = make_facade()
    result = await facade.login(provider_name="google", credential="first")
    clock.value += timedelta(days=31)
    for token in (result.tokens.refresh_token, "unknown"):
        with pytest.raises(AuthTokenInvalid):
            await facade.refresh(token)
    with pytest.raises(AuthTokenInvalid):
        await facade.authenticate(result.tokens.access_token)
    clock.value -= timedelta(days=31)
    repo.users.clear()
    with pytest.raises(AuthTokenInvalid):
        await facade.authenticate(result.tokens.access_token)


@pytest.mark.asyncio
async def test_unknown_provider_and_malformed_jwt_have_safe_errors() -> None:
    facade, _, _, codec = make_facade()
    with pytest.raises(AuthTokenInvalid, match="Authentication failed"):
        await facade.login(provider_name="email", credential="secret")
    for token in ("bad", jwt.encode({"sub": "bad"}, "s" * 32, algorithm="HS256")):
        with pytest.raises(AuthTokenInvalid, match="Authentication failed"):
            codec.decode(token)


@pytest.mark.parametrize(
    "replacement",
    [
        {"iss": "attacker"},
        {"sub": "invalid"},
        {"exp": 0},
        {"iat": 999999999999},
        {"iat": "1"},
        {"exp": True},
        {"jti": ""},
    ],
)
def test_signed_but_invalid_jwt_claims_rejected(replacement: dict[str, object]) -> None:
    _, _, clock, codec = make_facade()
    now = int(clock.now().timestamp())
    claims: dict[str, object] = {
        "sub": str(uuid4()),
        "iat": now,
        "exp": now + 60,
        "iss": "sot",
        "jti": str(uuid4()),
    }
    with pytest.raises(AuthTokenInvalid):
        codec.decode(jwt.encode({**claims, **replacement}, "s" * 32, algorithm="HS256"))


def test_wrong_signature_and_algorithm_rejected() -> None:
    _, _, _, codec = make_facade()
    token = codec.encode(UserId(uuid4()))
    claims = jwt.decode(token, options={"verify_signature": False})
    for secret, algorithm in (("x" * 32, "HS256"), ("s" * 64, "HS512")):
        with pytest.raises(AuthTokenInvalid):
            codec.decode(jwt.encode(claims, secret, algorithm=algorithm))
