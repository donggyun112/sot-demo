import json
from collections.abc import Mapping

import pytest
from joserfc.jwk import ECKey, OctKey, RSAKey

from service_auth import InvalidToken
from service_auth.jwks import JwksDocumentError, parse_jwks_document

MAX_JWKS_BYTES = 256 * 1024

RSA_PRIVATE = RSAKey.generate_key(
    2048,
    {"kid": "rsa-key", "alg": "RS256", "use": "sig"},
)
RSA_PUBLIC = RSA_PRIVATE.as_dict(private=False)
EC_PUBLIC = ECKey.generate_key(
    "P-256",
    {"kid": "ec-key", "alg": "ES256", "use": "sig"},
).as_dict(private=False)


def document(*keys: Mapping[str, object]) -> bytes:
    return json.dumps({"keys": list(keys)}).encode()


def rsa_public(**overrides: object) -> dict[str, object]:
    key: dict[str, object] = dict(RSA_PUBLIC)
    key.update(overrides)
    return key


def test_indexes_public_rsa_and_ec_verification_keys() -> None:
    index = parse_jwks_document(
        document(rsa_public(), dict(EC_PUBLIC)),
        frozenset({"RS256", "ES256"}),
    )

    assert index.get("rsa-key", "RS256").kid == "rsa-key"
    assert index.get("ec-key", "ES256").kid == "ec-key"


def test_binds_key_without_alg_only_for_one_allowed_algorithm() -> None:
    key = rsa_public()
    key.pop("alg")

    index = parse_jwks_document(document(key), frozenset({"PS256"}))

    assert index.get("rsa-key", "PS256").kid == "rsa-key"


def test_key_lookup_returns_bounded_unknown_kid_error() -> None:
    index = parse_jwks_document(document(rsa_public()), frozenset({"RS256"}))

    with pytest.raises(InvalidToken, match="^kid_unknown$") as caught:
        index.get("missing", "RS256")

    assert caught.value.reason == "kid_unknown"


@pytest.mark.parametrize("payload", [b"[]", b"null", b'"keys"'])
def test_rejects_non_object_root(payload: bytes) -> None:
    with pytest.raises(JwksDocumentError, match="^jwks_invalid$"):
        parse_jwks_document(payload, frozenset({"RS256"}))


@pytest.mark.parametrize("payload", [b"{}", b'{"keys":null}', b'{"keys":{}}'])
def test_rejects_missing_or_non_list_keys(payload: bytes) -> None:
    with pytest.raises(JwksDocumentError, match="^jwks_invalid$"):
        parse_jwks_document(payload, frozenset({"RS256"}))


def test_accepts_at_most_64_keys() -> None:
    keys = [rsa_public(kid=f"key-{number}") for number in range(64)]

    index = parse_jwks_document(document(*keys), frozenset({"RS256"}))

    assert len(index.keys) == 64


def test_rejects_more_than_64_keys_before_importing_them() -> None:
    keys = [rsa_public(kid=f"key-{number}") for number in range(65)]

    with pytest.raises(JwksDocumentError, match="^jwks_too_many_keys$"):
        parse_jwks_document(document(*keys), frozenset({"RS256"}))


@pytest.mark.parametrize(
    "payload",
    [
        b'{"keys":[],"keys":[]}',
        b'{"keys":[{"kty":"RSA","kid":"one","kid":"two"}]}',
    ],
)
def test_rejects_duplicate_json_members(payload: bytes) -> None:
    with pytest.raises(JwksDocumentError, match="^jwks_invalid$"):
        parse_jwks_document(payload, frozenset({"RS256"}))


@pytest.mark.parametrize("kid", ["", "a" * 257, "한" * 86])
def test_rejects_empty_or_over_256_utf8_byte_candidate_kid(kid: str) -> None:
    with pytest.raises(JwksDocumentError, match="^jwks_key_invalid$"):
        parse_jwks_document(document(rsa_public(kid=kid)), frozenset({"RS256"}))


def test_accepts_256_utf8_byte_candidate_kid() -> None:
    kid = "a" * 256

    index = parse_jwks_document(document(rsa_public(kid=kid)), frozenset({"RS256"}))

    assert index.get(kid, "RS256").kid == kid


def test_rejects_duplicate_candidate_kid() -> None:
    with pytest.raises(JwksDocumentError, match="^jwks_key_invalid$"):
        parse_jwks_document(
            document(rsa_public(), rsa_public(alg="PS256")),
            frozenset({"RS256", "PS256"}),
        )


def test_rejects_private_key_material() -> None:
    private_key = RSA_PRIVATE.as_dict(private=True)

    with pytest.raises(JwksDocumentError, match="^jwks_key_invalid$"):
        parse_jwks_document(document(private_key), frozenset({"RS256"}))


def test_rejects_symmetric_key_material() -> None:
    symmetric_key = OctKey.generate_key(
        256,
        {"kid": "symmetric", "alg": "HS256", "use": "sig"},
    ).as_dict(private=True)

    with pytest.raises(JwksDocumentError, match="^jwks_key_invalid$"):
        parse_jwks_document(document(symmetric_key), frozenset({"RS256"}))


@pytest.mark.parametrize(
    "key",
    [
        rsa_public(alg="ES256"),
        rsa_public(use="enc"),
        rsa_public(key_ops=["sign"]),
    ],
)
def test_rejects_document_without_compatible_signing_key(
    key: dict[str, object],
) -> None:
    with pytest.raises(JwksDocumentError, match="^jwks_no_usable_key$"):
        parse_jwks_document(document(key), frozenset({"RS256", "ES256"}))


def test_ignores_ineligible_key_when_another_signing_key_is_usable() -> None:
    index = parse_jwks_document(
        document(rsa_public(kid="encryption", use="enc"), rsa_public()),
        frozenset({"RS256"}),
    )

    assert len(index.keys) == 1
    assert index.get("rsa-key", "RS256").kid == "rsa-key"


def test_rejects_key_without_alg_when_profile_allows_multiple_algorithms() -> None:
    key = rsa_public()
    key.pop("alg")

    with pytest.raises(JwksDocumentError, match="^jwks_no_usable_key$"):
        parse_jwks_document(document(key), frozenset({"RS256", "PS256"}))


def test_rejects_malformed_candidate_key_material() -> None:
    malformed = {
        "kty": "RSA",
        "kid": "malformed",
        "alg": "RS256",
        "use": "sig",
        "n": "not-a-valid-modulus",
        "e": "AQAB",
    }

    with pytest.raises(JwksDocumentError, match="^jwks_key_invalid$"):
        parse_jwks_document(document(malformed), frozenset({"RS256"}))


def test_rejects_empty_key_set() -> None:
    with pytest.raises(JwksDocumentError, match="^jwks_no_usable_key$"):
        parse_jwks_document(document(), frozenset({"RS256"}))


def test_rejects_non_utf8_or_oversized_document() -> None:
    with pytest.raises(JwksDocumentError, match="^jwks_invalid$"):
        parse_jwks_document(b"\xff", frozenset({"RS256"}))
    with pytest.raises(JwksDocumentError, match="^jwks_too_large$"):
        parse_jwks_document(b" " * (MAX_JWKS_BYTES + 1), frozenset({"RS256"}))
