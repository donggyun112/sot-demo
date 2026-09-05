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
        if (
            not self.issuer
            or not self.audience
            or not self.jwks_uri.startswith("https://")
        ):
            raise ValueError("issuer, audience, and HTTPS jwks_uri are required")
        if (
            not self.allowed_algorithms
            or not self.allowed_algorithms <= SUPPORTED_ALGORITHMS
        ):
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
