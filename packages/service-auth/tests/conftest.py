import asyncio
import json
from collections import deque
from datetime import UTC, datetime, timedelta

import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from service_auth import VerificationProfile


class FakeClock:
    def __init__(self) -> None:
        self.wall = datetime(2026, 9, 2, tzinfo=UTC)
        self.tick = 1000.0

    def utcnow(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.tick

    def advance(self, seconds: float) -> None:
        self.wall += timedelta(seconds=seconds)
        self.tick += seconds


class FakeFetcher:
    def __init__(self, outcomes: list[bytes | Exception]) -> None:
        self.outcomes = deque(outcomes)
        self.calls = 0
        self.call_events: asyncio.Queue[int] = asyncio.Queue()
        self.closed = False
        self.close_calls = 0

    async def fetch(self) -> bytes:
        self.calls += 1
        self.call_events.put_nowait(self.calls)
        outcome = self.outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def close(self) -> None:
        self.closed = True
        self.close_calls += 1


class BlockingFetcher(FakeFetcher):
    def __init__(self, payload: bytes) -> None:
        super().__init__([payload])
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch(self) -> bytes:
        self.calls += 1
        self.call_events.put_nowait(self.calls)
        self.entered.set()
        await self.release.wait()
        outcome = self.outcomes.popleft()
        assert isinstance(outcome, bytes)
        return outcome


class ControlledSleeper:
    def __init__(self) -> None:
        self.delays: asyncio.Queue[float] = asyncio.Queue()
        self.waiters: asyncio.Queue[asyncio.Event] = asyncio.Queue()

    async def __call__(self, delay: float) -> None:
        gate = asyncio.Event()
        await self.delays.put(delay)
        await self.waiters.put(gate)
        await gate.wait()

    async def release_next(self) -> None:
        gate = await self.waiters.get()
        gate.set()


def public_rsa_document(kid: str) -> bytes:
    key = RSAKey.generate_key(
        2048,
        {"kid": kid, "alg": "RS256", "use": "sig"},
    )
    return json.dumps({"keys": [key.as_dict(private=False)]}).encode()


def jwks_for_key(key: RSAKey) -> bytes:
    return json.dumps({"keys": [key.as_dict(private=False)]}).encode()


def sign_token(
    key: RSAKey,
    claims: dict[str, object] | None = None,
    **header: object,
) -> str:
    protected = {"typ": "at+jwt", "alg": "RS256", "kid": "key-1", **header}
    return jwt.encode(
        protected,
        claims or {"marker": "verified"},
        key,
        algorithms=["RS256"],
        default_type=None,
    )


@pytest.fixture
def profile() -> VerificationProfile:
    return VerificationProfile(
        issuer="https://issuer.example",
        audience="urn:agent:default",
        jwks_uri="https://issuer.example/jwks.json",
        allowed_algorithms=frozenset({"RS256"}),
    )


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(scope="session")
def jwks_one() -> bytes:
    return public_rsa_document("key-1")


@pytest.fixture(scope="session")
def jwks_two() -> bytes:
    return public_rsa_document("key-2")


@pytest.fixture(scope="session")
def rsa_private_key() -> RSAKey:
    return RSAKey.generate_key(
        2048,
        {"kid": "key-1", "alg": "RS256", "use": "sig"},
    )


@pytest.fixture(scope="session")
def wrong_rsa_private_key() -> RSAKey:
    return RSAKey.generate_key(
        2048,
        {"kid": "key-1", "alg": "RS256", "use": "sig"},
    )
