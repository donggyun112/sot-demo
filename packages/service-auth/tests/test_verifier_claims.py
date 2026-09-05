import math

import pytest
from conftest import FakeClock, FakeFetcher, jwks_for_key, sign_token
from joserfc.jwk import RSAKey

from service_auth import (
    AccessTokenVerifier,
    InvalidToken,
    Principal,
    VerificationProfile,
)
from service_auth.jwks import AsyncJwksProvider


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


def verifier_for(
    key: RSAKey,
    profile: VerificationProfile,
    clock: FakeClock,
) -> AccessTokenVerifier:
    fetcher = FakeFetcher([jwks_for_key(key)])
    provider = AsyncJwksProvider(profile, fetcher, clock)
    return AccessTokenVerifier(profile, provider, clock)


async def verify_claims(
    claims: dict[str, object],
    key: RSAKey,
    profile: VerificationProfile,
    clock: FakeClock,
) -> Principal:
    verifier = verifier_for(key, profile, clock)
    return await verifier.verify(sign_token(key, claims))


@pytest.mark.asyncio
async def test_returns_only_normalized_principal(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    now = int(fake_clock.utcnow().timestamp())
    claims = valid_claims(now)
    claims["ignored-extra"] = "not returned"

    principal = await verify_claims(claims, rsa_private_key, profile, fake_clock)

    assert principal == Principal(
        issuer="https://issuer.example",
        subject="opaque-user",
        client_id="platform-web",
        scopes=frozenset({"agent:run", "agent:abort"}),
    )
    assert not hasattr(principal, "ignored-extra")


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer", [None, 7, "", "https://other.example"])
async def test_rejects_invalid_or_mismatched_issuer(
    issuer: object,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    if issuer is None:
        claims.pop("iss")
    else:
        claims["iss"] = issuer

    with pytest.raises(InvalidToken, match="^issuer_mismatch$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "audience",
    [
        None,
        7,
        "",
        "urn:agent:other",
        [],
        ["urn:agent:default", "urn:agent:other"],
        ["urn:agent:default", "urn:agent:default"],
    ],
)
async def test_rejects_invalid_or_multi_resource_audience(
    audience: object,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    if audience is None:
        claims.pop("aud")
    else:
        claims["aud"] = audience

    with pytest.raises(InvalidToken, match="^audience_mismatch$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
async def test_accepts_exact_one_element_audience_array(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    claims["aud"] = ["urn:agent:default"]

    principal = await verify_claims(claims, rsa_private_key, profile, fake_clock)

    assert principal.subject == "opaque-user"


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", [None, "", 7, ["opaque-user"]])
async def test_rejects_missing_empty_or_non_string_subject(
    subject: object,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    if subject is None:
        claims.pop("sub")
    else:
        claims["sub"] = subject

    with pytest.raises(InvalidToken, match="^subject_invalid$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["iat", "nbf", "exp"])
async def test_requires_every_numeric_date(
    name: str,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    claims.pop(name)

    with pytest.raises(InvalidToken, match="^time_claim_invalid$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["iat", "nbf", "exp"])
@pytest.mark.parametrize("value", [True, "1", math.nan, math.inf, -math.inf])
async def test_rejects_non_finite_or_non_numeric_dates(
    name: str,
    value: object,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    claims[name] = value

    with pytest.raises(InvalidToken, match="^time_claim_invalid$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [0, -1])
async def test_expiration_must_be_later_than_issued_at(
    offset: int,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    now = int(fake_clock.utcnow().timestamp())
    claims = valid_claims(now)
    claims["exp"] = now + offset

    with pytest.raises(InvalidToken, match="^time_claim_invalid$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
async def test_rejects_lifetime_over_300_seconds(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    now = int(fake_clock.utcnow().timestamp())
    claims = valid_claims(now)
    claims["exp"] = now + 301

    with pytest.raises(InvalidToken, match="^token_lifetime_exceeded$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
async def test_rejects_expiration_beyond_30_second_skew(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    now = int(fake_clock.utcnow().timestamp())
    claims = valid_claims(now)
    claims.update({"iat": now - 331, "nbf": now - 331, "exp": now - 31})

    with pytest.raises(InvalidToken, match="^token_expired$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["iat", "nbf"])
async def test_rejects_future_time_beyond_30_second_skew(
    name: str,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    now = int(fake_clock.utcnow().timestamp())
    claims = valid_claims(now)
    claims[name] = now + 31
    if name == "iat":
        claims["exp"] = now + 331

    with pytest.raises(InvalidToken, match="^token_not_yet_valid$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
async def test_accepts_exact_future_30_second_skew_boundary(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    now = int(fake_clock.utcnow().timestamp())
    claims = valid_claims(now)
    claims.update({"iat": now + 30, "nbf": now + 30, "exp": now + 330})

    principal = await verify_claims(claims, rsa_private_key, profile, fake_clock)

    assert principal.client_id == "platform-web"


@pytest.mark.asyncio
async def test_accepts_exact_expired_30_second_skew_boundary(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    now = int(fake_clock.utcnow().timestamp())
    claims = valid_claims(now)
    claims.update({"iat": now - 330, "nbf": now - 330, "exp": now - 30})

    principal = await verify_claims(claims, rsa_private_key, profile, fake_clock)

    assert principal.client_id == "platform-web"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        {},
        {"client_id": ""},
        {"client_id": 7},
        {"azp": ""},
        {"azp": 7},
        {"client_id": "platform-web", "azp": "platform-other"},
    ],
)
async def test_rejects_missing_invalid_or_conflicting_client_identity(
    identity: dict[str, object],
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    claims.pop("client_id")
    claims.update(identity)

    with pytest.raises(InvalidToken, match="^client_identity_invalid$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        {"azp": "platform-web"},
        {"client_id": "platform-web", "azp": "platform-web"},
    ],
)
async def test_accepts_azp_only_or_matching_client_identity(
    identity: dict[str, object],
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    claims.pop("client_id")
    claims.update(identity)

    principal = await verify_claims(claims, rsa_private_key, profile, fake_clock)

    assert principal.client_id == "platform-web"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [None, ""])
async def test_missing_or_empty_scope_normalizes_to_empty_set(
    scope: object,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    if scope is None:
        claims.pop("scope")
    else:
        claims["scope"] = scope

    principal = await verify_claims(claims, rsa_private_key, profile, fake_clock)

    assert principal.scopes == frozenset()


@pytest.mark.asyncio
async def test_repeated_spaces_and_duplicate_scopes_normalize(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    claims["scope"] = "  agent:run  agent:abort agent:run  "

    principal = await verify_claims(claims, rsa_private_key, profile, fake_clock)

    assert principal.scopes == frozenset({"agent:run", "agent:abort"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope",
    [7, ["agent:run"], 'agent:"run', "agent\\run", "agent:\trun", "에이전트"],
)
async def test_rejects_non_string_or_invalid_rfc6749_scope_tokens(
    scope: object,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    claims = valid_claims(int(fake_clock.utcnow().timestamp()))
    claims["scope"] = scope

    with pytest.raises(InvalidToken, match="^scope_invalid$"):
        await verify_claims(claims, rsa_private_key, profile, fake_clock)
