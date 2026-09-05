import json
from base64 import urlsafe_b64encode

import pytest
from conftest import FakeClock, FakeFetcher, jwks_for_key, sign_token
from joserfc import jwt
from joserfc.jwk import RSAKey

from service_auth import InvalidToken, VerificationProfile
from service_auth.jwks import AsyncJwksProvider
from service_auth.verifier import AccessTokenVerifier


def encoded(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def compact_header(header: object) -> str:
    return f"{encoded(json.dumps(header).encode())}.e30.c2ln"


def raw_compact_header(header: bytes) -> str:
    return f"{encoded(header)}.e30.c2ln"


def verifier_for(
    key: RSAKey,
    profile: VerificationProfile,
    clock: FakeClock,
) -> tuple[AccessTokenVerifier, FakeFetcher]:
    fetcher = FakeFetcher([jwks_for_key(key)])
    provider = AsyncJwksProvider(profile, fetcher, clock)
    return AccessTokenVerifier(profile, provider, clock), fetcher


@pytest.mark.asyncio
async def test_decodes_claims_only_after_valid_signature(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)
    token = sign_token(rsa_private_key, {"marker": "verified"})

    claims = await verifier._decode_verified_claims(token)

    assert claims == {"marker": "verified"}
    assert fetcher.calls == 1


@pytest.mark.asyncio
async def test_rejects_wrong_signature_with_bounded_reason(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
    wrong_rsa_private_key: RSAKey,
) -> None:
    verifier, _fetcher = verifier_for(rsa_private_key, profile, fake_clock)
    token = sign_token(wrong_rsa_private_key)

    with pytest.raises(InvalidToken, match="^signature_invalid$") as caught:
        await verifier._decode_verified_claims(token)

    assert caught.value.reason == "signature_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["", "one.two", "one.two.three.four"])
async def test_rejects_non_compact_tokens_before_key_lookup(
    token: str,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)

    with pytest.raises(InvalidToken, match="^token_malformed$"):
        await verifier._decode_verified_claims(token)

    assert fetcher.calls == 0


@pytest.mark.asyncio
async def test_rejects_token_over_16_kib_before_key_lookup(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)

    with pytest.raises(InvalidToken, match="^token_too_large$"):
        await verifier._decode_verified_claims("a" * (16 * 1024 + 1))

    assert fetcher.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        "%%%.e30.c2ln",
        raw_compact_header(b"not-json"),
        raw_compact_header(b'{"alg":"RS256","alg":"ES256"}'),
    ],
)
async def test_rejects_invalid_base64_json_or_duplicate_header_members(
    token: str,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)

    with pytest.raises(InvalidToken, match="^token_malformed$"):
        await verifier._decode_verified_claims(token)

    assert fetcher.calls == 0


@pytest.mark.asyncio
async def test_rejects_non_object_protected_header(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)

    with pytest.raises(InvalidToken, match="^header_invalid$"):
        await verifier._decode_verified_claims(compact_header([]))

    assert fetcher.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("header", "reason"),
    [
        ({"typ": "at+jwt", "alg": "RS256"}, "kid_missing"),
        ({"typ": "at+jwt", "alg": "RS256", "kid": ""}, "kid_missing"),
        ({"typ": "at+jwt", "alg": "RS256", "kid": 7}, "header_invalid"),
        (
            {"typ": "at+jwt", "alg": "RS256", "kid": "한" * 86},
            "header_invalid",
        ),
    ],
)
async def test_rejects_missing_invalid_or_oversized_kid(
    header: dict[str, object],
    reason: str,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)

    with pytest.raises(InvalidToken, match=f"^{reason}$"):
        await verifier._decode_verified_claims(compact_header(header))

    assert fetcher.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "typ",
    [None, "AT+JWT", "jwt", 7],
)
async def test_requires_exact_access_token_type(
    typ: object,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    header: dict[str, object] = {"alg": "RS256", "kid": "key-1"}
    if typ is not None:
        header["typ"] = typ
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)

    with pytest.raises(InvalidToken, match="^header_invalid$"):
        await verifier._decode_verified_claims(compact_header(header))

    assert fetcher.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("algorithm", [None, "", "none", "HS256", "RS512", 7])
async def test_rejects_missing_or_non_allow_list_algorithm(
    algorithm: object,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    header: dict[str, object] = {"typ": "at+jwt", "kid": "key-1"}
    if algorithm is not None:
        header["alg"] = algorithm
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)
    expected = "header_invalid" if algorithm == 7 else "algorithm_rejected"

    with pytest.raises(InvalidToken, match=f"^{expected}$"):
        await verifier._decode_verified_claims(compact_header(header))

    assert fetcher.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "forbidden",
    ["jku", "jwk", "x5u", "x5c", "x5t", "x5t#S256", "crit"],
)
async def test_rejects_forbidden_key_locator_or_critical_header_before_lookup(
    forbidden: str,
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    header = {
        "typ": "at+jwt",
        "alg": "RS256",
        "kid": "key-1",
        forbidden: "attacker-controlled",
    }
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)

    with pytest.raises(InvalidToken, match="^header_invalid$"):
        await verifier._decode_verified_claims(compact_header(header))

    assert fetcher.calls == 0


@pytest.mark.asyncio
async def test_token_carried_matching_jwk_is_rejected_before_provider_lookup(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    rsa_private_key: RSAKey,
) -> None:
    public_key = rsa_private_key.as_dict(private=False)
    token = jwt.encode(
        {"typ": "at+jwt", "alg": "RS256", "kid": "key-1", "jwk": public_key},
        {"marker": "verified"},
        rsa_private_key,
        algorithms=["RS256"],
        default_type=None,
    )
    verifier, fetcher = verifier_for(rsa_private_key, profile, fake_clock)

    with pytest.raises(InvalidToken, match="^header_invalid$"):
        await verifier._decode_verified_claims(token)

    assert fetcher.calls == 0
