import asyncio
import json
from base64 import b64decode
from binascii import Error as BinasciiError
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast

import httpx
from joserfc import jwk
from joserfc.errors import JoseError
from joserfc.jwk import ECKey, RSAKey

from service_auth.errors import InvalidToken, KeySourceUnavailable
from service_auth.models import Clock, JwksReadiness, JwksState, VerificationProfile

MAX_JWKS_BYTES = 256 * 1024
MAX_JWKS_KEYS = 64
MAX_KID_BYTES = 256


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


class JwksFetcher(Protocol):
    async def fetch(self) -> bytes: ...

    async def close(self) -> None: ...


type Sleeper = Callable[[float], Awaitable[None]]


class _DuplicateMember(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise _DuplicateMember
        result[name] = value
    return result


def _load_document(payload: bytes) -> dict[str, object]:
    if len(payload) > MAX_JWKS_BYTES:
        raise JwksDocumentError("jwks_too_large")
    try:
        document: object = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateMember) as error:
        raise JwksDocumentError("jwks_invalid") from error
    if not isinstance(document, dict):
        raise JwksDocumentError("jwks_invalid")
    return cast(dict[str, object], document)


def _bound_algorithm(
    candidate: dict[str, object],
    algorithms: frozenset[str],
) -> str | None:
    value = candidate.get("alg")
    if value is None:
        if len(algorithms) != 1:
            return None
        return next(iter(algorithms))
    if not isinstance(value, str) or not value:
        raise JwksDocumentError("jwks_key_invalid")
    if value not in algorithms:
        return None
    return value


def _is_signing_candidate(candidate: dict[str, object]) -> bool:
    use = candidate.get("use")
    if use is not None and not isinstance(use, str):
        raise JwksDocumentError("jwks_key_invalid")
    if use not in (None, "sig"):
        return False

    key_ops = candidate.get("key_ops")
    if key_ops is not None:
        if not isinstance(key_ops, list) or any(
            not isinstance(item, str) for item in key_ops
        ):
            raise JwksDocumentError("jwks_key_invalid")
        if "verify" not in key_ops:
            return False
    return True


def _key_type_supports_algorithm(key_type: object, algorithm: str) -> bool:
    if algorithm in {"RS256", "PS256"}:
        return key_type == "RSA"
    if algorithm == "ES256":
        return key_type == "EC"
    return False


def _validate_rsa_modulus(candidate: dict[str, object]) -> None:
    value = candidate.get("n")
    if not isinstance(value, str) or not value or "=" in value:
        raise JwksDocumentError("jwks_key_invalid")
    try:
        encoded = value.encode("ascii")
        raw = b64decode(
            encoded + b"=" * (-len(encoded) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (BinasciiError, UnicodeEncodeError, ValueError) as error:
        raise JwksDocumentError("jwks_key_invalid") from error
    if int.from_bytes(raw, "big").bit_length() < 2048:
        raise JwksDocumentError("jwks_key_invalid")


def _import_verification_key(
    candidate: dict[str, object],
    algorithm: str,
) -> VerificationKey:
    if candidate.get("kty") == "RSA":
        _validate_rsa_modulus(candidate)
    try:
        imported = jwk.import_key(
            cast(dict[str, str | list[str]], candidate),
        )
        if not isinstance(imported, (RSAKey, ECKey)) or imported.is_private:
            raise JwksDocumentError("jwks_key_invalid")
        imported.check_use("sig")
        imported.check_key_op("verify")
        imported.check_alg(algorithm)
    except JwksDocumentError:
        raise
    except (JoseError, TypeError, ValueError) as error:
        raise JwksDocumentError("jwks_key_invalid") from error
    return imported


def parse_jwks_document(payload: bytes, algorithms: frozenset[str]) -> KeyIndex:
    document = _load_document(payload)
    candidates = document.get("keys")
    if not isinstance(candidates, list):
        raise JwksDocumentError("jwks_invalid")
    if len(candidates) > MAX_JWKS_KEYS:
        raise JwksDocumentError("jwks_too_many_keys")

    keys: dict[tuple[str, str], VerificationKey] = {}
    seen_kids: set[str] = set()
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, dict):
            raise JwksDocumentError("jwks_key_invalid")
        candidate = cast(dict[str, object], raw_candidate)

        if candidate.get("kty") == "oct":
            raise JwksDocumentError("jwks_key_invalid")
        algorithm = _bound_algorithm(candidate, algorithms)
        if algorithm is None or not _is_signing_candidate(candidate):
            continue
        if not _key_type_supports_algorithm(candidate.get("kty"), algorithm):
            continue

        kid = candidate.get("kid")
        if (
            not isinstance(kid, str)
            or not kid
            or len(kid.encode("utf-8")) > MAX_KID_BYTES
            or kid in seen_kids
        ):
            raise JwksDocumentError("jwks_key_invalid")

        key = _import_verification_key(candidate, algorithm)
        seen_kids.add(kid)
        keys[(kid, algorithm)] = key

    if not keys:
        raise JwksDocumentError("jwks_no_usable_key")
    return KeyIndex(MappingProxyType(keys))


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
        self._last_unknown_refresh: float | None = None
        self._refresh_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._refresh_task: asyncio.Task[None] | None = None
        self._maintenance_task: asyncio.Task[None] | None = None
        self._started = False
        self._closing = False
        self._closed = False
        self._fetcher_closed = False

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
        age = (
            None
            if self._last_success is None
            else self._clock.monotonic() - self._last_success
        )
        return JwksReadiness(
            state in {JwksState.FRESH, JwksState.STALE_USABLE},
            state,
            age,
        )

    def _cached_key(self, kid: str, algorithm: str) -> VerificationKey | None:
        if self._index is None:
            return None
        try:
            return self._index.get(kid, algorithm)
        except InvalidToken:
            return None

    def _remaining_failure_backoff(self) -> float:
        if self._last_failure is None:
            return 0
        elapsed = self._clock.monotonic() - self._last_failure
        return max(0, self._profile.refresh_failure_backoff - elapsed)

    async def _fetch_and_install(self) -> None:
        try:
            payload = await self._fetcher.fetch()
            replacement = parse_jwks_document(payload, self._profile.allowed_algorithms)
        except (JwksDocumentError, JwksFetchError) as error:
            self._last_failure = self._clock.monotonic()
            raise KeySourceUnavailable from error

        self._index = replacement
        self._last_success = self._clock.monotonic()
        self._last_failure = None

    async def _refresh_singleflight(self) -> None:
        async with self._refresh_lock:
            task = self._refresh_task
            if task is None or task.done():
                if self._remaining_failure_backoff() > 0 or self._closing:
                    raise KeySourceUnavailable
                task = asyncio.create_task(self._fetch_and_install())
                self._refresh_task = task
        await asyncio.shield(task)

    def _unknown_refresh_allowed(self) -> bool:
        if self._last_unknown_refresh is None:
            return True
        elapsed = self._clock.monotonic() - self._last_unknown_refresh
        return elapsed >= self._profile.unknown_kid_refresh_cooldown

    async def get_key(self, kid: str, algorithm: str) -> VerificationKey:
        state = self._state()
        cached = self._cached_key(kid, algorithm)
        if state is JwksState.FRESH and cached is not None:
            return cached

        if cached is None and state in {JwksState.FRESH, JwksState.STALE_USABLE}:
            if not self._unknown_refresh_allowed():
                raise InvalidToken("kid_unknown")
            self._last_unknown_refresh = self._clock.monotonic()

        try:
            await self._refresh_singleflight()
        except KeySourceUnavailable:
            if state is JwksState.STALE_USABLE and cached is not None:
                return cached
            if state in {JwksState.FRESH, JwksState.STALE_USABLE}:
                raise InvalidToken("kid_unknown") from None
            raise

        assert self._index is not None
        try:
            return self._index.get(kid, algorithm)
        except InvalidToken:
            self._last_unknown_refresh = self._clock.monotonic()
            raise

    def _maintenance_delay(self) -> float:
        backoff = self._remaining_failure_backoff()
        if self._last_success is None:
            return backoff
        age = self._clock.monotonic() - self._last_success
        until_stale = max(0, self._profile.jwks_freshness - age)
        return max(backoff, until_stale)

    async def _maintain(self) -> None:
        while not self._closing:
            await self._sleeper(self._maintenance_delay())
            if self._closing:
                return
            try:
                await self._refresh_singleflight()
            except KeySourceUnavailable:
                pass

    async def start(self) -> None:
        if self._started or self._closed:
            return
        self._started = True
        try:
            await self._refresh_singleflight()
        except KeySourceUnavailable:
            pass
        if not self._closing:
            self._maintenance_task = asyncio.create_task(self._maintain())

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closing = True

            maintenance = self._maintenance_task
            if maintenance is not None and not maintenance.done():
                maintenance.cancel()
                with suppress(asyncio.CancelledError):
                    await maintenance

            refresh = self._refresh_task
            if refresh is not None and not refresh.done():
                refresh.cancel()
                with suppress(asyncio.CancelledError):
                    await refresh

            if not self._fetcher_closed:
                await self._fetcher.close()
                self._fetcher_closed = True
            self._closed = True


class HttpxJwksFetcher:
    def __init__(self, uri: str, client: httpx.AsyncClient | None = None) -> None:
        try:
            url = httpx.URL(uri)
        except httpx.InvalidURL as error:
            raise ValueError("HTTPS jwks_uri is required") from error
        if url.scheme != "https" or not url.host:
            raise ValueError("HTTPS jwks_uri is required")

        self._uri = url
        self._timeout = httpx.Timeout(3.0, connect=2.0)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=self._timeout,
        )

    async def fetch(self) -> bytes:
        body = bytearray()
        try:
            async with self._client.stream(
                "GET",
                self._uri,
                follow_redirects=False,
                timeout=self._timeout,
            ) as response:
                if response.status_code != 200:
                    raise JwksFetchError("jwks_http_error")
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_JWKS_BYTES:
                        raise JwksFetchError("jwks_too_large")
        except (httpx.HTTPError, JwksFetchError) as error:
            raise JwksFetchError("jwks_fetch_failed") from error
        return bytes(body)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
