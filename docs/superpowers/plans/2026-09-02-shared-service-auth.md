# Shared Service Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independently reusable JWT verification package and an Agent-owned authorization adapter without adding production AG-UI routes or execution behavior.

**Architecture:** `packages/service-auth` owns asynchronous JWKS retrieval, cache state, JOSE verification, claim normalization and HTTP-neutral authentication errors. `agent-server` consumes the package, applies its own client/scope policy, derives opaque ownership, and maps typed failures to its future HTTP contract; neither package knows Platform domain state.

**Tech Stack:** Python 3.12+, joserfc 1.7.5+, httpx 0.28+, FastAPI 0.116+, pydantic-settings 2.10+, pytest 8+, pytest-asyncio 1+, Ruff, mypy strict, uv

**Spec:** `docs/superpowers/specs/2026-09-02-shared-service-auth-design.md`

## Global Constraints

- Stop after every task, report changed files and exact test output, and wait for explicit user approval before starting the next task.
- Execution note (2026-09-02): after approving Tasks 1-3 individually, the user explicitly
  authorized continuous execution of the already-written plan through an operationally verified
  state. That authorization satisfies the intermediate review gates for Tasks 4-9; scope limits
  below remain unchanged.
- Do not add `/ag-ui`, `/runs/{runId}/abort`, `/readyz`, persistence, SSE, Redis, Semora/OpenRouter execution, token issuance, Platform login or an Agent loop.
- `service-auth` must not import FastAPI, Platform, Agent, Semora, Redis or database packages.
- Agent Server must not import Platform code or trust a caller-provided subject header.
- Python requirement remains `>=3.12`; all new Python passes Ruff and strict mypy.
- Use [`joserfc>=1.7.5,<2`](https://pypi.org/project/joserfc/1.7.5/) and `httpx>=0.28,<1`; 1.7.5 is the current verified PyPI release as of 2026-09-02.
- V1 supported algorithms are exactly `RS256`, `PS256`, and `ES256`; deployment configuration must select a non-empty subset.
- JWT lifetime is at most 300 seconds, clock skew is 30 seconds, JWKS freshness is 300 seconds, maximum usable age is 900 seconds, and refresh backoff/cooldown is 5 seconds.
- Production JWKS access is HTTPS-only, follows no redirects, uses 2-second connect and 3-second read timeouts, accepts at most 256 KiB and 64 keys, and never follows token-provided URLs.
- Never persist or log a raw bearer token, raw subject, full owner hash or raw attacker-provided `kid`.
- The workspace is currently not a Git repository. Do not initialize one. Commit steps are executed only if the plan is later run inside an existing Git checkout; otherwise report the task checkpoint without committing.

## File Map

```text
packages/service-auth/
├── pyproject.toml                         package/dependency/tool configuration
├── uv.lock                                independently resolved dependency graph
├── README.md                              public purpose and test command
├── src/service_auth/__init__.py           intentionally small public API
├── src/service_auth/errors.py             bounded HTTP-neutral error taxonomy
├── src/service_auth/models.py             immutable config/result/clock contracts
├── src/service_auth/jwks.py               JWKS parser, HTTPS fetcher and cache
├── src/service_auth/verifier.py           header, signature and claim verification
├── tests/conftest.py                      fake clock/fetcher and signing fixtures
├── tests/test_models.py                   profile and immutable-value tests
├── tests/test_jwks_document.py             JWKS validation tests
├── tests/test_jwks_http.py                 bounded HTTPS client tests
├── tests/test_jwks_cache.py                freshness/failure/concurrency tests
├── tests/test_verifier_signature.py        JOSE/header/key-selection tests
├── tests/test_verifier_claims.py           RFC 9068-style claim tests
└── tests/test_distribution.py              install/import/boundary tests

agent-server/
├── pyproject.toml                          local service-auth dependency
├── uv.lock                                 resolved dependency graph
├── Dockerfile                              monorepo-root build context
├── README.md                               build/test commands and auth boundary
├── src/agent_core/auth/__init__.py         Agent-auth public exports
├── src/agent_core/auth/policy.py           client/scope/owner policy
├── src/agent_core/auth/settings.py         AGENT_AUTH_* deployment settings
├── src/agent_core/auth/http.py             bearer extraction and error responses
├── tests/test_auth_policy.py               Agent authorization tests
├── tests/test_auth_settings.py             environment/profile mapping tests
├── tests/test_auth_http.py                 exact HTTP contract tests
├── tests/test_service_boundary.py          approved common-package exception
└── tests/test_distribution.py              container/package regression tests
```

---

### Task 1: Create the independent package and immutable contracts

**Files:**
- Create: `packages/service-auth/pyproject.toml`
- Create: `packages/service-auth/src/service_auth/__init__.py`
- Create: `packages/service-auth/src/service_auth/errors.py`
- Create: `packages/service-auth/src/service_auth/models.py`
- Create: `packages/service-auth/tests/test_models.py`

**Interfaces:**
- Consumes: no project code
- Produces: `AuthReason`, `AuthenticationError`, `CredentialMissing`, `InvalidToken`, `KeySourceUnavailable`, `Clock`, `SystemClock`, `VerificationProfile`, `Principal`, `JwksState`, and `JwksReadiness`

- [x] **Step 1: Write the package metadata and failing model tests**

Create `pyproject.toml` with the exact runtime and development boundaries:

```toml
[project]
name = "service-auth"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.28,<1",
    "joserfc>=1.7.5,<2",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/service_auth"]

[dependency-groups]
dev = [
    "mypy>=1.11",
    "pytest>=8",
    "pytest-asyncio>=1,<2",
    "ruff>=0.6",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
```

Create tests proving immutability, defaults, algorithm restrictions and configuration invariants:

```python
from dataclasses import FrozenInstanceError

import pytest

from service_auth.models import Principal, VerificationProfile


def valid_profile(**overrides: object) -> VerificationProfile:
    values: dict[str, object] = {
        "issuer": "https://issuer.example",
        "audience": "urn:agent:default",
        "jwks_uri": "https://issuer.example/jwks.json",
        "allowed_algorithms": frozenset({"RS256"}),
    }
    values.update(overrides)
    return VerificationProfile(**values)  # type: ignore[arg-type]


def test_profile_has_closed_security_defaults() -> None:
    profile = valid_profile()
    assert profile.maximum_token_lifetime == 300
    assert profile.clock_skew == 30
    assert profile.jwks_freshness == 300
    assert profile.jwks_maximum_age == 900
    assert profile.refresh_failure_backoff == 5
    assert profile.unknown_kid_refresh_cooldown == 5


@pytest.mark.parametrize(
    "algorithms",
    [frozenset(), frozenset({"none"}), frozenset({"HS256"}), frozenset({"RS512"})],
)
def test_profile_rejects_unapproved_algorithm_sets(algorithms: frozenset[str]) -> None:
    with pytest.raises(ValueError, match="allowed_algorithms"):
        valid_profile(allowed_algorithms=algorithms)


def test_principal_is_immutable() -> None:
    principal = Principal("https://issuer.example", "opaque-user", "platform-web", frozenset())
    with pytest.raises(FrozenInstanceError):
        principal.subject = "changed"  # type: ignore[misc]
```

Also cover empty issuer/audience/URI, non-HTTPS production URI, non-positive durations,
`jwks_freshness >= jwks_maximum_age`, and accepted subsets of `RS256`/`PS256`/`ES256`.

- [x] **Step 2: Run the focused tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv lock --project packages/service-auth
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_models.py -q
```

Expected: collection fails because `service_auth.models` does not exist.

- [x] **Step 3: Implement the contracts and bounded errors**

Implement frozen, slotted dataclasses and an injectable clock:

```python
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from typing import Protocol

SUPPORTED_ALGORITHMS = frozenset({"RS256", "PS256", "ES256"})


class Clock(Protocol):
    def utcnow(self) -> datetime: ...
    def monotonic(self) -> float: ...


class SystemClock:
    def utcnow(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return monotonic()


@dataclass(frozen=True, slots=True)
class VerificationProfile:
    issuer: str
    audience: str
    jwks_uri: str
    allowed_algorithms: frozenset[str]
    maximum_token_lifetime: int = 300
    clock_skew: int = 30
    jwks_freshness: int = 300
    jwks_maximum_age: int = 900
    refresh_failure_backoff: int = 5
    unknown_kid_refresh_cooldown: int = 5

    def __post_init__(self) -> None:
        if not self.issuer or not self.audience or not self.jwks_uri.startswith("https://"):
            raise ValueError("issuer, audience, and HTTPS jwks_uri are required")
        if not self.allowed_algorithms or not self.allowed_algorithms <= SUPPORTED_ALGORITHMS:
            raise ValueError("allowed_algorithms must be a supported non-empty subset")
        durations = (
            self.maximum_token_lifetime,
            self.clock_skew,
            self.jwks_freshness,
            self.jwks_maximum_age,
            self.refresh_failure_backoff,
            self.unknown_kid_refresh_cooldown,
        )
        if any(value <= 0 for value in durations):
            raise ValueError("verification durations must be positive")
        if self.jwks_freshness >= self.jwks_maximum_age:
            raise ValueError("jwks_freshness must be less than jwks_maximum_age")


@dataclass(frozen=True, slots=True)
class Principal:
    issuer: str
    subject: str
    client_id: str
    scopes: frozenset[str]


class JwksState(StrEnum):
    EMPTY = "empty"
    FRESH = "fresh"
    STALE_USABLE = "stale_usable"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class JwksReadiness:
    ready: bool
    state: JwksState
    age_seconds: float | None
```

Define one base exception and exact internal reason values in `errors.py`; exception messages must
contain only the bounded code:

```python
from typing import Literal

type AuthReason = Literal[
    "token_malformed", "token_too_large", "header_invalid", "algorithm_rejected",
    "kid_missing", "kid_unknown", "signature_invalid", "issuer_mismatch",
    "audience_mismatch", "subject_invalid", "time_claim_invalid",
    "token_not_yet_valid", "token_expired", "token_lifetime_exceeded",
    "client_identity_invalid", "scope_invalid",
]


class AuthenticationError(Exception):
    pass


class CredentialMissing(AuthenticationError):
    pass


class InvalidToken(AuthenticationError):
    def __init__(self, reason: AuthReason) -> None:
        super().__init__(reason)
        self.reason = reason


class KeySourceUnavailable(AuthenticationError):
    pass
```

Export only supported consumer contracts from `__init__.py`; do not export fetch/parser internals.

- [x] **Step 4: Run package tests, lint and types**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_models.py -q
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth ruff check packages/service-auth/src packages/service-auth/tests
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth mypy packages/service-auth/src
```

Expected: all commands exit 0.

- [x] **Step 5: Review checkpoint and conditional commit**

Report the public contracts and test output. Wait for approval. In an existing Git checkout only:

```bash
git add packages/service-auth
git commit -m "feat(auth): define shared authentication contracts"
```

---

### Task 2: Validate and fetch bounded JWKS documents

**Files:**
- Create: `packages/service-auth/src/service_auth/jwks.py`
- Create: `packages/service-auth/tests/test_jwks_document.py`
- Create: `packages/service-auth/tests/test_jwks_http.py`

**Interfaces:**
- Consumes: `VerificationProfile`
- Produces: `VerificationKey = RSAKey | ECKey`, `KeyIndex`, `JwksFetcher`, `HttpxJwksFetcher`, and package-private `parse_jwks_document(payload, algorithms)`

- [x] **Step 1: Write failing JWKS document tests**

Use generated joserfc keys so fixtures contain no static private material:

```python
import json

import pytest
from joserfc.jwk import RSAKey

from service_auth.jwks import JwksDocumentError, parse_jwks_document


def public_rsa(kid: str = "key-1") -> dict[str, object]:
    key = RSAKey.generate_key(2048, {"kid": kid, "alg": "RS256", "use": "sig"})
    return key.as_dict(private=False)


def test_indexes_one_public_verification_key() -> None:
    index = parse_jwks_document(
        json.dumps({"keys": [public_rsa()]}).encode(), frozenset({"RS256"})
    )
    assert index.get("key-1", "RS256").kid == "key-1"


def test_rejects_duplicate_candidate_kid() -> None:
    key = public_rsa()
    with pytest.raises(JwksDocumentError):
        parse_jwks_document(json.dumps({"keys": [key, key]}).encode(), frozenset({"RS256"}))
```

Add named cases for non-object roots, missing/non-list `keys`, more than 64 keys, duplicate JSON
members, empty/over-256-byte `kid`, private keys, `oct` keys, incompatible `alg`, `use="enc"`,
`key_ops` without `verify`, malformed key material, and a document with no usable signing key.

- [x] **Step 2: Write failing bounded HTTP fetch tests**

Use `httpx.MockTransport` and inject the client:

```python
import httpx
import pytest

from service_auth.jwks import HttpxJwksFetcher, JwksFetchError


@pytest.mark.asyncio
async def test_fetcher_returns_bounded_body_without_following_redirects() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"location": "https://evil.example/jwks"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = HttpxJwksFetcher("https://issuer.example/jwks", client=client)
    with pytest.raises(JwksFetchError):
        await fetcher.fetch()
    assert calls == 1
    await client.aclose()
```

Add exact cases for 200 success, 404/500, timeout, a streamed body of 262145 bytes, and ownership:
`close()` closes an internally created client but not an injected client.

- [x] **Step 3: Run focused tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_jwks_document.py packages/service-auth/tests/test_jwks_http.py -q
```

Expected: collection fails because `service_auth.jwks` does not exist.

- [x] **Step 4: Implement document parsing and the HTTPS fetcher**

Use a `(kid, algorithm)` index and bind a key without `alg` only when the verifier profile has one
allowed algorithm:

```python
class JwksDocumentError(ValueError):
    pass


class JwksFetchError(RuntimeError):
    pass


type VerificationKey = RSAKey | ECKey


@dataclass(frozen=True, slots=True)
class KeyIndex:
    keys: Mapping[tuple[str, str], VerificationKey]

    def get(self, kid: str, algorithm: str) -> VerificationKey:
        try:
            return self.keys[(kid, algorithm)]
        except KeyError as error:
            raise InvalidToken("kid_unknown") from error
```

`parse_jwks_document` must reject duplicate JSON members, enforce all size/count/key constraints,
call `jwk.import_key`, reject private or symmetric material, call `check_use("sig")`,
`check_key_op("verify")`, and `check_alg(bound_algorithm)`, and replace no state on error.

Implement the fetch protocol and bounded streaming body:

```python
class JwksFetcher(Protocol):
    async def fetch(self) -> bytes: ...
    async def close(self) -> None: ...


class HttpxJwksFetcher:
    def __init__(self, uri: str, client: httpx.AsyncClient | None = None) -> None:
        self._uri = uri
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(3.0, connect=2.0),
        )

    async def fetch(self) -> bytes:
        body = bytearray()
        try:
            async with self._client.stream("GET", self._uri) as response:
                if response.status_code != 200:
                    raise JwksFetchError("jwks_http_error")
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 256 * 1024:
                        raise JwksFetchError("jwks_too_large")
        except (httpx.HTTPError, JwksFetchError) as error:
            raise JwksFetchError("jwks_fetch_failed") from error
        return bytes(body)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
```

Keep `JwksDocumentError` and `JwksFetchError` package-private by omitting them from
`service_auth.__init__`.

- [x] **Step 5: Run focused and static checks**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_jwks_document.py packages/service-auth/tests/test_jwks_http.py -q
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth ruff check packages/service-auth/src packages/service-auth/tests
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth mypy packages/service-auth/src
```

Expected: all commands exit 0.

- [x] **Step 6: Review checkpoint and conditional commit**

Report accepted/rejected JWK classes and transport limits. Wait for approval. In Git only:

```bash
git add packages/service-auth
git commit -m "feat(auth): validate and fetch issuer key sets"
```

---

### Task 3: Implement JWKS freshness and outage behavior

**Files:**
- Modify: `packages/service-auth/src/service_auth/jwks.py`
- Create: `packages/service-auth/tests/conftest.py`
- Create: `packages/service-auth/tests/test_jwks_cache.py`

**Interfaces:**
- Consumes: `Clock`, `VerificationProfile`, `KeyIndex`, `JwksFetcher`
- Produces: `Sleeper`, `AsyncJwksProvider.get_key(kid: str, algorithm: str) -> VerificationKey`, and `AsyncJwksProvider.readiness() -> JwksReadiness`

- [x] **Step 1: Add deterministic clock and fetcher fixtures**

```python
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta


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
        self.closed = False

    async def fetch(self) -> bytes:
        self.calls += 1
        outcome = self.outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def close(self) -> None:
        self.closed = True


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
```

- [x] **Step 2: Write failing cache-state tests**

```python
@pytest.mark.asyncio
async def test_known_key_survives_transient_refresh_failure_until_maximum_age(
    profile: VerificationProfile, fake_clock: FakeClock, jwks_one: bytes
) -> None:
    fetcher = FakeFetcher([jwks_one, JwksFetchError("offline")])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    first = await provider.get_key("key-1", "RS256")
    fake_clock.advance(301)
    stale = await provider.get_key("key-1", "RS256")
    assert stale is first
    assert provider.readiness().state is JwksState.STALE_USABLE


@pytest.mark.asyncio
async def test_expired_cache_fails_when_refresh_fails(
    profile: VerificationProfile, fake_clock: FakeClock, jwks_one: bytes
) -> None:
    fetcher = FakeFetcher([jwks_one, JwksFetchError("offline")])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    await provider.get_key("key-1", "RS256")
    fake_clock.advance(901)
    with pytest.raises(KeySourceUnavailable):
        await provider.get_key("key-1", "RS256")
```

Add exact tests for EMPTY readiness, FRESH no-fetch hits, refresh/key rotation at 301 seconds,
exactly 300 seconds remaining FRESH, exactly 900 seconds remaining STALE_USABLE, 901 seconds being
EXPIRED, failed refresh not replacing a valid set, and an unknown key after a successful forced
refresh producing `InvalidToken("kid_unknown")`.

- [x] **Step 3: Run the cache tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_jwks_cache.py -q
```

Expected: import or attribute failure for `AsyncJwksProvider`.

- [x] **Step 4: Implement atomic cache installation and state calculation**

Use only monotonic time for key age:

```python
type Sleeper = Callable[[float], Awaitable[None]]


class AsyncJwksProvider:
    def __init__(
        self,
        profile: VerificationProfile,
        fetcher: JwksFetcher,
        clock: Clock,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        self._profile = profile
        self._fetcher = fetcher
        self._clock = clock
        self._sleeper = sleeper
        self._index: KeyIndex | None = None
        self._last_success: float | None = None
        self._last_failure: float | None = None

    def _state(self) -> JwksState:
        if self._last_success is None:
            return JwksState.EMPTY
        age = self._clock.monotonic() - self._last_success
        if age <= self._profile.jwks_freshness:
            return JwksState.FRESH
        if age <= self._profile.jwks_maximum_age:
            return JwksState.STALE_USABLE
        return JwksState.EXPIRED

    def readiness(self) -> JwksReadiness:
        state = self._state()
        age = None if self._last_success is None else self._clock.monotonic() - self._last_success
        return JwksReadiness(state in {JwksState.FRESH, JwksState.STALE_USABLE}, state, age)
```

Implement `_refresh()` so it parses into a local `KeyIndex` first and swaps `_index` plus
`_last_success` only after complete success. `get_key()` uses FRESH directly, refreshes
STALE_USABLE/EMPTY/EXPIRED, falls back only to a known key in STALE_USABLE, and translates an
unusable fetch failure to `KeySourceUnavailable` without exception text.

- [x] **Step 5: Run focused tests and static checks**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_jwks_cache.py -q
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth ruff check packages/service-auth/src packages/service-auth/tests
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth mypy packages/service-auth/src
```

Expected: all commands exit 0.

- [x] **Step 6: Review checkpoint and conditional commit**

Report the state-transition table and boundary test results. Wait for approval. In Git only:

```bash
git add packages/service-auth
git commit -m "feat(auth): cache issuer keys across bounded outages"
```

---

### Task 4: Add single-flight refresh, cooldown and lifecycle

**Files:**
- Modify: `packages/service-auth/src/service_auth/jwks.py`
- Modify: `packages/service-auth/tests/test_jwks_cache.py`

**Interfaces:**
- Consumes: Task 3 `AsyncJwksProvider`
- Produces: idempotent `start()`/`close()`, one shared refresh task, five-second failure backoff, and five-second global unknown-key refresh cooldown

- [x] **Step 1: Write failing concurrency and lifecycle tests**

Use `asyncio.Event` to prove calls overlap instead of relying on sleeps:

```python
class BlockingFetcher(FakeFetcher):
    def __init__(self, payload: bytes) -> None:
        super().__init__([payload])
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch(self) -> bytes:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        outcome = self.outcomes.popleft()
        assert isinstance(outcome, bytes)
        return outcome


@pytest.mark.asyncio
async def test_concurrent_empty_cache_lookups_share_one_fetch(
    profile: VerificationProfile, fake_clock: FakeClock, blocking_fetcher: BlockingFetcher
) -> None:
    provider = AsyncJwksProvider(profile, blocking_fetcher, fake_clock)
    lookups = [asyncio.create_task(provider.get_key("key-1", "RS256")) for _ in range(20)]
    await blocking_fetcher.entered.wait()
    blocking_fetcher.release.set()
    await asyncio.gather(*lookups)
    assert blocking_fetcher.calls == 1


@pytest.mark.asyncio
async def test_random_unknown_kids_share_global_cooldown(
    provider_with_one_key: AsyncJwksProvider, fake_clock: FakeClock, fetcher: FakeFetcher
) -> None:
    for kid in ("random-1", "random-2", "random-3"):
        with pytest.raises(InvalidToken, match="kid_unknown"):
            await provider_with_one_key.get_key(kid, "RS256")
    assert fetcher.calls == 2  # initial fetch plus one forced refresh
```

Add exact cases for one refresh after cooldown expiry, failure backoff, `start()` called twice,
initial start failure leaving not-ready state, periodic refresh at the freshness deadline,
`close()` called twice, close during refresh, and closing only the fetcher-owned resources.

- [x] **Step 2: Run focused tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_jwks_cache.py -q
```

Expected: new concurrency/lifecycle assertions fail.

- [x] **Step 3: Implement shared refresh and lifecycle ownership**

Use a lock only to publish/capture the shared task; await it outside the lock:

```python
async def _refresh_singleflight(self) -> None:
    async with self._refresh_lock:
        task = self._refresh_task
        if task is None or task.done():
            task = asyncio.create_task(self._fetch_and_install())
            self._refresh_task = task
    await asyncio.shield(task)
```

Before creating a refresh, check `_last_failure` against `refresh_failure_backoff`. For unknown
keys, check and update `_last_unknown_refresh` globally, not per `kid`. After a successful forced
refresh that still lacks the key, retain the cooldown timestamp. `start()` performs one immediate
attempt, records network failure without raising, and starts exactly one maintenance task.
`close()` sets a closing flag, cancels and awaits the maintenance task, cancels and awaits any
provider-owned in-flight refresh, closes the fetcher once, and is safe to call again. Maintenance
uses the injected `Sleeper`; tests release it with events and never advance real time.

- [x] **Step 4: Run the complete JWKS suite and static checks**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_jwks_document.py packages/service-auth/tests/test_jwks_http.py packages/service-auth/tests/test_jwks_cache.py -q
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth ruff check packages/service-auth/src packages/service-auth/tests
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth mypy packages/service-auth/src
```

Expected: all commands exit 0 and the concurrency test reports one fetch.

- [x] **Step 5: Review checkpoint and conditional commit**

Report task ownership/cancellation behavior and fetch counts. Wait for approval. In Git only:

```bash
git add packages/service-auth
git commit -m "feat(auth): serialize key refresh and lifecycle"
```

---

### Task 5: Verify protected headers and signatures

**Files:**
- Create: `packages/service-auth/src/service_auth/verifier.py`
- Create: `packages/service-auth/tests/test_verifier_signature.py`
- Modify: `packages/service-auth/tests/conftest.py`

**Interfaces:**
- Consumes: `VerificationProfile`, `AsyncJwksProvider.get_key()`, `InvalidToken`
- Produces: package-private `_decode_verified_claims(token: str) -> Mapping[str, object]` and public `AccessTokenVerifier`

- [x] **Step 1: Add signed-token fixtures and failing signature tests**

```python
from joserfc import jwt
from joserfc.jwk import RSAKey


@pytest.fixture
def rsa_private_key() -> RSAKey:
    return RSAKey.generate_key(2048, {"kid": "key-1", "alg": "RS256", "use": "sig"})


def sign_token(key: RSAKey, claims: dict[str, object], **header: object) -> str:
    protected = {"typ": "at+jwt", "alg": "RS256", "kid": "key-1", **header}
    return jwt.encode(protected, claims, key, algorithms=["RS256"])
```

Test a valid signature, wrong key, more/fewer than three compact segments, over-16-KiB token,
invalid base64/JSON/non-object header, missing/empty/over-256-byte `kid`, missing/wrong-case `typ`,
`none`/`HS256`/non-allow-listed `alg`, and the presence of each forbidden header: `jku`, `jwk`,
`x5u`, `x5c`, `x5t`, `x5t#S256`, `crit`.

The key test must prove that a token-carried `jwk` matching the signing key is rejected before
provider lookup.

- [x] **Step 2: Run focused tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_verifier_signature.py -q
```

Expected: collection fails because `service_auth.verifier` does not exist.

- [x] **Step 3: Implement strict preflight and joserfc verification**

Parse the protected header with strict JSON and bounded base64url decoding. Treat every parsed
value as untrusted until `jwt.decode` succeeds:

```python
from base64 import b64decode

FORBIDDEN_HEADERS = frozenset({"jku", "jwk", "x5u", "x5c", "x5t", "x5t#S256", "crit"})


class _DuplicateMember(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise _DuplicateMember(name)
        result[name] = value
    return result


def _parse_protected_header(token: str) -> dict[str, object]:
    if not token or len(token.encode("utf-8")) > 16 * 1024:
        raise InvalidToken("token_too_large" if token else "token_malformed")
    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidToken("token_malformed")
    try:
        encoded = parts[0].encode("ascii")
        raw = b64decode(encoded + b"=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise InvalidToken("token_malformed") from error
    if not isinstance(value, dict):
        raise InvalidToken("header_invalid")
    return value


def _required_header_text(
    header: Mapping[str, object],
    name: str,
    missing_reason: AuthReason,
) -> str:
    value = header.get(name)
    if value is None or value == "":
        raise InvalidToken(missing_reason)
    if not isinstance(value, str):
        raise InvalidToken("header_invalid")
    if name == "kid" and len(value.encode("utf-8")) > 256:
        raise InvalidToken("header_invalid")
    return value


class AccessTokenVerifier:
    def __init__(
        self,
        profile: VerificationProfile,
        keys: AsyncJwksProvider,
        clock: Clock | None = None,
    ) -> None:
        self._profile = profile
        self._keys = keys
        self._clock = clock or SystemClock()

    async def _decode_verified_claims(self, token: str) -> Mapping[str, object]:
        header = _parse_protected_header(token)
        algorithm = _required_header_text(header, "alg", "algorithm_rejected")
        kid = _required_header_text(header, "kid", "kid_missing")
        if header.get("typ") != "at+jwt" or FORBIDDEN_HEADERS.intersection(header):
            raise InvalidToken("header_invalid")
        if algorithm not in self._profile.allowed_algorithms:
            raise InvalidToken("algorithm_rejected")
        key = await self._keys.get_key(kid, algorithm)
        try:
            decoded = jwt.decode(token, key, algorithms=self._profile.allowed_algorithms)
        except BadSignatureError as error:
            raise InvalidToken("signature_invalid") from error
        except JoseError as error:
            raise InvalidToken("token_malformed") from error
        if decoded.header != header:
            raise InvalidToken("header_invalid")
        if not isinstance(decoded.claims, dict):
            raise InvalidToken("token_malformed")
        return decoded.claims
```

`_unique_object` raises on duplicate protected-header member names. `_required_header_text`
requires a string, rejects empty values, and applies the 256-byte UTF-8 bound to `kid`. The
verified-header equality check makes parser disagreement fail closed.

Use exception chaining internally, but never expose caught text through the public exception or
HTTP layer. Keep raw header values out of logs.

- [x] **Step 4: Run signature tests and static checks**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_verifier_signature.py -q
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth ruff check packages/service-auth/src packages/service-auth/tests
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth mypy packages/service-auth/src
```

Expected: all commands exit 0.

- [x] **Step 5: Review checkpoint and conditional commit**

Report the exact accepted header profile and rejected key-locator tests. Wait for approval. In Git:

```bash
git add packages/service-auth
git commit -m "feat(auth): verify access token signatures"
```

---

### Task 6: Normalize and validate access-token claims

**Files:**
- Modify: `packages/service-auth/src/service_auth/verifier.py`
- Create: `packages/service-auth/tests/test_verifier_claims.py`
- Modify: `packages/service-auth/src/service_auth/__init__.py`

**Interfaces:**
- Consumes: verified claim mapping, injected `Clock`, `VerificationProfile`
- Produces: `await AccessTokenVerifier.verify(token: str) -> Principal`

- [x] **Step 1: Write failing claim-table tests**

Build every token with a valid signature so each assertion isolates claim behavior:

```python
def valid_claims(now: int) -> dict[str, object]:
    return {
        "iss": "https://issuer.example",
        "aud": "urn:agent:default",
        "sub": "opaque-user",
        "client_id": "platform-web",
        "scope": "agent:run agent:abort",
        "iat": now,
        "nbf": now,
        "exp": now + 300,
    }


@pytest.mark.asyncio
async def test_returns_only_normalized_principal(verifier: AccessTokenVerifier, token: str) -> None:
    principal = await verifier.verify(token)
    assert principal == Principal(
        issuer="https://issuer.example",
        subject="opaque-user",
        client_id="platform-web",
        scopes=frozenset({"agent:run", "agent:abort"}),
    )
```

Parameterize exact failures for issuer type/value; audience type/value/multi-audience; empty or
non-string subject; each missing time claim; bool, string, NaN and infinity NumericDates;
`exp <= iat`; 301-second lifetime; expiration and future `iat`/`nbf`; exact ±30-second boundaries;
missing/bad/mismatched `client_id`/`azp`; non-string scope; invalid RFC 6749 scope-token bytes.

Add successes for `aud=[expected]`, `azp` without `client_id`, matching `azp` and `client_id`, absent
scope producing an empty set, repeated spaces/duplicate scopes normalizing to one value, and extra
claims not appearing on `Principal`.

- [x] **Step 2: Run focused tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_verifier_claims.py -q
```

Expected: public `verify()` or claim assertions fail.

- [x] **Step 3: Implement custom claim validation**

Do not rely on permissive library defaults. Validate booleans separately because `bool` subclasses
`int`, require finite numbers, and use the injected clock:

```python
SCOPE_TOKEN = re.compile(r"^[\x21\x23-\x5B\x5D-\x7E]+$")


def _numeric_date(claims: Mapping[str, object], name: str) -> float:
    value = claims.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InvalidToken("time_claim_invalid")
    return float(value)


def _exact_issuer(claims: Mapping[str, object], expected: str) -> str:
    value = claims.get("iss")
    if not isinstance(value, str) or value != expected:
        raise InvalidToken("issuer_mismatch")
    return value


def _exact_audience(claims: Mapping[str, object], expected: str) -> None:
    value = claims.get("aud")
    if value == expected:
        return
    if isinstance(value, list) and value == [expected]:
        return
    raise InvalidToken("audience_mismatch")


def _non_empty_text(value: object, reason: AuthReason) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidToken(reason)
    return value


def _normalize_client_identity(claims: Mapping[str, object]) -> str:
    client_id = claims.get("client_id")
    azp = claims.get("azp")
    if client_id is not None and (not isinstance(client_id, str) or not client_id):
        raise InvalidToken("client_identity_invalid")
    if azp is not None and (not isinstance(azp, str) or not azp):
        raise InvalidToken("client_identity_invalid")
    if client_id is None and azp is None:
        raise InvalidToken("client_identity_invalid")
    if client_id is not None and azp is not None and client_id != azp:
        raise InvalidToken("client_identity_invalid")
    value = client_id if isinstance(client_id, str) else azp
    assert isinstance(value, str)
    return value


def _normalize_scope(value: object) -> frozenset[str]:
    if value is None or value == "":
        return frozenset()
    if not isinstance(value, str):
        raise InvalidToken("scope_invalid")
    members = [member for member in value.split(" ") if member]
    if any(SCOPE_TOKEN.fullmatch(member) is None for member in members):
        raise InvalidToken("scope_invalid")
    return frozenset(members)


def _validate_times(self, claims: Mapping[str, object], now: float) -> None:
    issued_at = _numeric_date(claims, "iat")
    not_before = _numeric_date(claims, "nbf")
    expires_at = _numeric_date(claims, "exp")
    if expires_at <= issued_at:
        raise InvalidToken("time_claim_invalid")
    if expires_at - issued_at > self._profile.maximum_token_lifetime:
        raise InvalidToken("token_lifetime_exceeded")
    if issued_at > now + self._profile.clock_skew or not_before > now + self._profile.clock_skew:
        raise InvalidToken("token_not_yet_valid")
    if expires_at < now - self._profile.clock_skew:
        raise InvalidToken("token_expired")


async def verify(self, token: str) -> Principal:
    claims = await self._decode_verified_claims(token)
    issuer = _exact_issuer(claims, self._profile.issuer)
    _exact_audience(claims, self._profile.audience)
    subject = _non_empty_text(claims.get("sub"), "subject_invalid")
    client_id = _normalize_client_identity(claims)
    scopes = _normalize_scope(claims.get("scope"))
    self._validate_times(claims, self._clock.utcnow().timestamp())
    return Principal(issuer, subject, client_id, scopes)
```

Add the two definitions above as methods of the Task 5 `AccessTokenVerifier` class (one class-level
indent is omitted in the excerpt for readability); the remaining helpers stay module-private pure
functions.

Implement leeway inclusively: values exactly 30 seconds over/behind the wall clock pass; values
beyond 30 seconds fail. Missing scope becomes `frozenset()`. Split on ASCII space, remove empty and
duplicate members, then validate every remaining member against `SCOPE_TOKEN`.

- [x] **Step 4: Run the complete package suite and static checks**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests -q
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth ruff check packages/service-auth/src packages/service-auth/tests
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth mypy packages/service-auth/src
```

Expected: all commands exit 0.

- [x] **Step 5: Review checkpoint and conditional commit**

Report the claim matrix and boundary values. Wait for approval. In Git only:

```bash
git add packages/service-auth
git commit -m "feat(auth): validate access token claims"
```

---

### Task 7: Add Agent-owned policy, identity derivation and settings

**Files:**
- Create: `agent-server/src/agent_core/auth/__init__.py`
- Create: `agent-server/src/agent_core/auth/policy.py`
- Create: `agent-server/src/agent_core/auth/settings.py`
- Create: `agent-server/tests/test_auth_policy.py`
- Create: `agent-server/tests/test_auth_settings.py`
- Modify: `agent-server/pyproject.toml:1-38`
- Modify: `agent-server/uv.lock`
- Modify: `agent-server/tests/test_service_boundary.py:24-38`

**Interfaces:**
- Consumes: `Principal`, `VerificationProfile`
- Produces: `AgentScope`, `AgentAuthorizationReason`, `AgentAuthorizationError`, `AuthenticatedAgentCaller`, `AgentAuthPolicy.authorize()`, `AgentAuthSettings.verification_profile()`

- [x] **Step 1: Add the local package dependency and update the boundary expectation**

Add:

```toml
dependencies = [
    "ag-ui-protocol>=0.1.19,<0.2",
    "fastapi>=0.116,<1",
    "psycopg[binary]>=3.2,<4",
    "psycopg-pool>=3.2,<4",
    "pydantic-settings>=2.10,<3",
    "rfc8785>=0.1.4,<0.2",
    "service-auth",
    "uvicorn>=0.35,<1",
]

[tool.uv.sources]
service-auth = { path = "../packages/service-auth" }
```

Change `test_agent_distribution_has_no_cross_service_dependency` so it still forbids Platform,
backend and Agent application packages but accepts exactly this source mapping:

```python
assert sources == {"service-auth": {"path": "../packages/service-auth"}}
assert "service-auth" in {
    re.split(r"[<>=@\[ ]", dependency.lower(), maxsplit=1)[0]
    for dependency in project["project"]["dependencies"]
}
```

Run `uv lock --project agent-server` only after `packages/service-auth` tests are green.

- [x] **Step 2: Write failing Agent policy tests**

```python
from hashlib import sha256

import pytest
from service_auth import Principal

from agent_core.auth import AgentAuthPolicy, AgentAuthorizationError


def principal(scopes: frozenset[str] = frozenset({"agent:run"})) -> Principal:
    return Principal("https://issuer.example", "opaque-user", "platform-web", scopes)


def test_authorize_derives_only_trusted_agent_identity() -> None:
    policy = AgentAuthPolicy(frozenset({"platform-web"}))
    caller = policy.authorize(principal(), "agent:run")
    expected = sha256(b"https://issuer.example\x00opaque-user").digest()
    assert caller.owner_issuer == "https://issuer.example"
    assert caller.owner_subject_hash == expected
    assert caller.semora_subject == "agtsub:v1:" + base64.urlsafe_b64encode(expected).rstrip(b"=").decode()
    assert not hasattr(caller, "subject")


def test_run_and_abort_scopes_are_independent() -> None:
    policy = AgentAuthPolicy(frozenset({"platform-web"}))
    with pytest.raises(AgentAuthorizationError, match="scope_missing"):
        policy.authorize(principal(), "agent:abort")
```

Add tests for a denied client, empty allow-list configuration, exact 32-byte hash, frozen caller,
and both accepted Agent scopes.

- [x] **Step 3: Write failing Agent settings tests**

Use JSON arrays for set-valued pydantic-settings environment variables:

```python
def test_settings_build_common_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_AUTH_ISSUER", "https://issuer.example")
    monkeypatch.setenv("AGENT_AUTH_AUDIENCE", "urn:agent:default")
    monkeypatch.setenv("AGENT_AUTH_JWKS_URI", "https://issuer.example/jwks")
    monkeypatch.setenv("AGENT_AUTH_ALLOWED_ALGORITHMS", '["RS256"]')
    monkeypatch.setenv("AGENT_AUTH_ALLOWED_CLIENT_IDS", '["platform-web"]')
    settings = AgentAuthSettings()
    assert settings.verification_profile().allowed_algorithms == frozenset({"RS256"})
    assert settings.allowed_client_ids == frozenset({"platform-web"})
```

Also assert every variable is required, unsafe URI/algorithm values fail through
`VerificationProfile`, and no provider credential/token field exists.

- [x] **Step 4: Run focused tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv lock --project agent-server
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server pytest agent-server/tests/test_auth_policy.py agent-server/tests/test_auth_settings.py agent-server/tests/test_service_boundary.py -q
```

Expected: auth module collection fails before implementation; after dependency-only edits the
boundary test passes and auth imports still fail.

- [x] **Step 5: Implement Agent policy and settings**

```python
type AgentScope = Literal["agent:run", "agent:abort"]
type AgentAuthorizationReason = Literal["client_forbidden", "scope_missing"]


class AgentAuthorizationError(Exception):
    def __init__(
        self,
        reason: AgentAuthorizationReason,
        required_scope: AgentScope | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.required_scope = required_scope


@dataclass(frozen=True, slots=True)
class AuthenticatedAgentCaller:
    owner_issuer: str
    owner_subject_hash: bytes
    semora_subject: str


class AgentAuthPolicy:
    def __init__(self, allowed_client_ids: frozenset[str]) -> None:
        if not allowed_client_ids:
            raise ValueError("allowed_client_ids must not be empty")
        self._allowed_client_ids = allowed_client_ids

    def authorize(self, principal: Principal, required_scope: AgentScope) -> AuthenticatedAgentCaller:
        if principal.client_id not in self._allowed_client_ids:
            raise AgentAuthorizationError("client_forbidden")
        if required_scope not in principal.scopes:
            raise AgentAuthorizationError("scope_missing", required_scope)
        owner_hash = sha256(principal.issuer.encode() + b"\x00" + principal.subject.encode()).digest()
        encoded = urlsafe_b64encode(owner_hash).rstrip(b"=").decode("ascii")
        return AuthenticatedAgentCaller(principal.issuer, owner_hash, f"agtsub:v1:{encoded}")
```

Implement settings without constructing a verifier or opening network connections:

```python
class AgentAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_AUTH_")

    issuer: str
    audience: str
    jwks_uri: str
    allowed_algorithms: frozenset[str]
    allowed_client_ids: frozenset[str]

    def verification_profile(self) -> VerificationProfile:
        return VerificationProfile(
            issuer=self.issuer,
            audience=self.audience,
            jwks_uri=self.jwks_uri,
            allowed_algorithms=self.allowed_algorithms,
        )
```

- [x] **Step 6: Run Agent policy/settings and regression tests**

Run:

```bash
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server pytest agent-server/tests/test_auth_policy.py agent-server/tests/test_auth_settings.py agent-server/tests/test_service_boundary.py -q
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server pytest agent-server/tests -q
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server ruff check agent-server/src agent-server/tests
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server mypy agent-server/src
```

Expected: all commands exit 0; existing `/healthz` and admission behavior remain unchanged.

- [x] **Step 7: Review checkpoint and conditional commit**

Report dependency direction, owner test vector and environment names. Wait for approval. In Git:

```bash
git add agent-server packages/service-auth
git commit -m "feat(agent): authorize verified service principals"
```

---

### Task 8: Define the Agent HTTP authentication contract without wiring routes

**Files:**
- Create: `agent-server/src/agent_core/auth/http.py`
- Create: `agent-server/tests/test_auth_http.py`
- Modify: `agent-server/src/agent_core/auth/__init__.py`
- Verify unchanged: `agent-server/src/agent_core/api/app.py`

**Interfaces:**
- Consumes: common authentication errors and Agent authorization errors
- Produces: `extract_bearer(authorization: str | None) -> str`, `AgentResourceHidden`, and `auth_error_response(error) -> JSONResponse`

- [x] **Step 1: Write failing bearer and response tests through a test-only app**

```python
def test_extracts_case_insensitive_single_bearer() -> None:
    assert extract_bearer("bearer ey.example.token") == "ey.example.token"


@pytest.mark.parametrize("value", [None, "", "Basic abc", "Bearer", "Bearer a b", "Bearer a,b"])
def test_rejects_missing_or_ambiguous_credentials(value: str | None) -> None:
    with pytest.raises(CredentialMissing):
        extract_bearer(value)


@pytest.mark.asyncio
async def test_invalid_token_has_fixed_401_contract(test_app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/raise/invalid-token")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    assert response.json() == {"error": {"code": "invalid_token", "message": "Authentication failed"}}
```

The test-only app registers handlers for `AuthenticationError`, `AgentAuthorizationError`, and
`AgentResourceHidden`. Add exact assertions for disallowed client 403, missing required scope 403 with
the required scope challenge, hidden missing/owner-mismatch 404 equality, and unavailable keys 503
with `Retry-After: 5` and no `WWW-Authenticate`.

Add a regression assertion that `create_app()` still exposes only `/healthz` plus FastAPI's schema
routes and still returns 404 for `/ag-ui` and `/runs/<uuid>/abort`.

- [x] **Step 2: Run focused tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server pytest agent-server/tests/test_auth_http.py agent-server/tests/test_http.py -q
```

Expected: collection fails because `agent_core.auth.http` does not exist.

- [x] **Step 3: Implement exact safe response mapping**

Use fixed tables, not exception strings:

```python
PUBLIC_ERRORS = {
    "invalid_token": (401, "Authentication failed"),
    "forbidden": (403, "Caller is not allowed"),
    "insufficient_scope": (403, "Required scope is missing"),
    "run_not_found": (404, "Run not found"),
    "auth_keys_unavailable": (503, "Authentication keys are temporarily unavailable"),
}


def extract_bearer(authorization: str | None) -> str:
    if authorization is None:
        raise CredentialMissing()
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or "," in parts[1]:
        raise CredentialMissing()
    return parts[1]
```

Define the hidden-resource type locally in Agent code:

```python
type HiddenResourceReason = Literal["missing", "owner_mismatch"]


class AgentResourceHidden(Exception):
    def __init__(self, reason: HiddenResourceReason) -> None:
        super().__init__(reason)
        self.reason = reason
```

Map by exception type and bounded reason only:

```python
type HttpAuthError = (
    CredentialMissing
    | InvalidToken
    | KeySourceUnavailable
    | AgentAuthorizationError
    | AgentResourceHidden
)


def auth_error_response(error: HttpAuthError) -> JSONResponse:
    headers: dict[str, str] = {}
    if isinstance(error, (CredentialMissing, InvalidToken)):
        code = "invalid_token"
        headers["WWW-Authenticate"] = 'Bearer error="invalid_token"'
    elif isinstance(error, KeySourceUnavailable):
        code = "auth_keys_unavailable"
        headers["Retry-After"] = "5"
    elif isinstance(error, AgentResourceHidden):
        code = "run_not_found"
    elif error.reason == "client_forbidden":
        code = "forbidden"
    else:
        code = "insufficient_scope"
        assert error.required_scope is not None
        headers["WWW-Authenticate"] = (
            f'Bearer error="insufficient_scope", scope="{error.required_scope}"'
        )
    status, message = PUBLIC_ERRORS[code]
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
        headers=headers,
    )
```

Every `InvalidToken` reason maps to the same 401. Scope comes only from the typed
`AgentAuthorizationError.required_scope`; never interpolate token, subject, `kid`, or caught
exception text. Both `AgentResourceHidden("missing")` and
`AgentResourceHidden("owner_mismatch")` produce identical bodies, status and headers.

- [x] **Step 4: Run HTTP, boundary and full Agent tests**

Run:

```bash
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server pytest agent-server/tests/test_auth_http.py agent-server/tests/test_http.py agent-server/tests/test_service_boundary.py -q
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server pytest agent-server/tests -q
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server ruff check agent-server/src agent-server/tests
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server mypy agent-server/src
```

Expected: all commands exit 0 and production route assertions remain unchanged.

- [x] **Step 5: Review checkpoint and conditional commit**

Show the five public response fixtures and route list. Wait for approval. In Git only:

```bash
git add agent-server
git commit -m "feat(agent): define authentication HTTP responses"
```

---

### Task 9: Prove independent packaging and monorepo container installation

**Files:**
- Create: `packages/service-auth/README.md`
- Create: `packages/service-auth/tests/test_distribution.py`
- Modify: `agent-server/Dockerfile:1-10`
- Modify: `agent-server/tests/test_distribution.py:1-48`
- Modify: `agent-server/README.md:1-59`
- Modify: `packages/service-auth/uv.lock`
- Verify: `agent-server/uv.lock`

**Interfaces:**
- Consumes: completed package and Agent adapters
- Produces: independently installable `service-auth`, Agent image built from the monorepo root, and reproducible verification commands

- [x] **Step 1: Write failing distribution and forbidden-import tests**

In the common package, parse every source file with `ast` and assert forbidden roots are absent:

```python
FORBIDDEN_ROOTS = {
    "fastapi", "agent_core", "platform_server", "semora", "redis", "psycopg",
}


def test_shared_package_has_no_service_or_framework_imports() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for target in import_targets(path):
            if target.split(".", 1)[0] in FORBIDDEN_ROOTS:
                violations.append(f"{path.relative_to(SRC)} -> {target}")
    assert violations == []
```

Add a subprocess test executed outside the source directory that imports `service_auth` and
asserts `importlib.metadata.version("service-auth") == "0.1.0"` without `PYTHONPATH`.

Update Agent's Dockerfile test to require root-context copies for both projects and retain the
installed uvicorn entrypoint. The test must reject a Dockerfile that uses `PYTHONPATH` or copies
Platform code.

- [x] **Step 2: Run distribution tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests/test_distribution.py -q
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server pytest agent-server/tests/test_distribution.py -q
```

Expected: common README/distribution or Docker root-context assertions fail before packaging edits.

- [x] **Step 3: Make the Docker build context explicit**

Replace the Dockerfile's copy layout while keeping the runtime command:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY packages/service-auth /app/packages/service-auth
COPY agent-server/pyproject.toml agent-server/uv.lock /app/agent-server/
COPY agent-server/src /app/agent-server/src

WORKDIR /app/agent-server
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "agent_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The supported build command becomes:

```bash
docker build -f agent-server/Dockerfile .
```

Do not copy a future Platform directory or root application source into the image.

- [x] **Step 4: Document package and verification commands**

`packages/service-auth/README.md` states that it verifies credentials but issues no tokens and
contains no service authorization policy. Add its isolated test command. Update Agent README with
the shared-library dependency, Agent-owned scope/client/owner boundary, root-context Docker build,
and the explicit statement that production auth routes are not wired in this slice.

Generate/verify both locks:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv lock --project packages/service-auth
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv lock --project agent-server
```

- [x] **Step 5: Run full verification**

Run:

```bash
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth pytest packages/service-auth/tests -q
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth ruff check packages/service-auth/src packages/service-auth/tests
UV_CACHE_DIR=/tmp/service-auth-uv-cache uv run --project packages/service-auth mypy packages/service-auth/src
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server pytest agent-server/tests -q
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server ruff check agent-server/src agent-server/tests
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv run --project agent-server mypy agent-server/src
docker build -f agent-server/Dockerfile .
```

Expected: all commands exit 0. If Docker is unavailable, report that single environmental gap and
do not claim container verification; all Python/package checks must still pass.

- [x] **Step 6: Confirm scope did not expand**

Run:

```bash
rg -n '(@application\.(post|put|patch|delete)|/ag-ui|/runs/.*/abort|from semora|import semora|openrouter)' agent-server/src packages/service-auth/src
```

Expected: no new production route, Semora or OpenRouter match. Existing `/healthz` is the only
application endpoint introduced by project code.

- [x] **Step 7: Final review checkpoint and conditional commit**

Present the full command matrix, route-surface proof, dependency boundary and any environmental
gap. Wait for final user acceptance. In Git only:

```bash
git add packages/service-auth agent-server docs/superpowers
git commit -m "feat(auth): add reusable service credential verification"
```

## Completion Evidence

Do not call the slice complete without all of the following evidence:

- common package pytest, Ruff and mypy outputs;
- Agent pytest, Ruff and mypy outputs;
- exact `service-auth` and Agent dependency graphs from both `pyproject.toml` files;
- route-surface test showing no production authentication/AG-UI route was added;
- cache tests proving 300/900-second boundaries, single-flight and unknown-key cooldown;
- fixed owner derivation test vector;
- Docker build result or an explicit statement that Docker was the only unverified environment;
- user approval at every task checkpoint.
