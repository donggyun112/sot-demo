from dataclasses import FrozenInstanceError
from datetime import UTC

import pytest

from service_auth import (
    AuthenticationError,
    CredentialMissing,
    InvalidToken,
    JwksReadiness,
    JwksState,
    KeySourceUnavailable,
    Principal,
    SystemClock,
    VerificationProfile,
)


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
    [
        frozenset(),
        frozenset({"none"}),
        frozenset({"HS256"}),
        frozenset({"RS512"}),
        frozenset({"RS256", "HS256"}),
    ],
)
def test_profile_rejects_unapproved_algorithm_sets(algorithms: frozenset[str]) -> None:
    with pytest.raises(ValueError, match="allowed_algorithms"):
        valid_profile(allowed_algorithms=algorithms)


@pytest.mark.parametrize(
    "algorithms",
    [
        frozenset({"RS256"}),
        frozenset({"PS256"}),
        frozenset({"ES256"}),
        frozenset({"RS256", "PS256"}),
        frozenset({"RS256", "ES256"}),
        frozenset({"PS256", "ES256"}),
        frozenset({"RS256", "PS256", "ES256"}),
    ],
)
def test_profile_accepts_every_supported_non_empty_subset(
    algorithms: frozenset[str],
) -> None:
    assert valid_profile(allowed_algorithms=algorithms).allowed_algorithms == algorithms


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issuer", ""),
        ("audience", ""),
        ("jwks_uri", ""),
        ("jwks_uri", "http://issuer.example/jwks.json"),
    ],
)
def test_profile_rejects_missing_identity_or_non_https_key_source(
    field: str,
    value: str,
) -> None:
    with pytest.raises(ValueError, match="HTTPS jwks_uri"):
        valid_profile(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "maximum_token_lifetime",
        "clock_skew",
        "jwks_freshness",
        "jwks_maximum_age",
        "refresh_failure_backoff",
        "unknown_kid_refresh_cooldown",
    ],
)
@pytest.mark.parametrize("value", [0, -1])
def test_profile_rejects_non_positive_durations(field: str, value: int) -> None:
    with pytest.raises(ValueError, match="durations must be positive"):
        valid_profile(**{field: value})


@pytest.mark.parametrize(
    ("freshness", "maximum_age"),
    [(300, 300), (301, 300)],
)
def test_profile_requires_freshness_below_maximum_age(
    freshness: int,
    maximum_age: int,
) -> None:
    with pytest.raises(ValueError, match="jwks_freshness"):
        valid_profile(jwks_freshness=freshness, jwks_maximum_age=maximum_age)


def test_profile_is_immutable() -> None:
    profile = valid_profile()

    with pytest.raises(FrozenInstanceError):
        profile.audience = "changed"  # type: ignore[misc]


def test_principal_is_immutable() -> None:
    principal = Principal(
        "https://issuer.example",
        "opaque-user",
        "platform-web",
        frozenset({"agent:run"}),
    )

    with pytest.raises(FrozenInstanceError):
        principal.subject = "changed"  # type: ignore[misc]


def test_jwks_readiness_is_immutable_and_preserves_state() -> None:
    readiness = JwksReadiness(True, JwksState.FRESH, 12.5)

    assert readiness.state == "fresh"
    assert readiness.age_seconds == 12.5
    with pytest.raises(FrozenInstanceError):
        readiness.ready = False  # type: ignore[misc]


def test_system_clock_returns_utc_time_and_monotonic_values() -> None:
    clock = SystemClock()

    before = clock.monotonic()
    now = clock.utcnow()
    after = clock.monotonic()

    assert now.tzinfo is UTC
    assert before <= after


def test_authentication_errors_expose_only_bounded_messages() -> None:
    missing = CredentialMissing()
    invalid = InvalidToken("token_expired")
    unavailable = KeySourceUnavailable()

    assert isinstance(missing, AuthenticationError)
    assert isinstance(invalid, AuthenticationError)
    assert isinstance(unavailable, AuthenticationError)
    assert str(missing) == ""
    assert str(invalid) == "token_expired"
    assert invalid.reason == "token_expired"
    assert str(unavailable) == ""
