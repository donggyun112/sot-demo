import json
import math
import re
from base64 import b64decode
from collections.abc import Mapping
from typing import cast

from joserfc import jwt
from joserfc.errors import BadSignatureError, JoseError

from service_auth.errors import AuthReason, InvalidToken
from service_auth.jwks import AsyncJwksProvider
from service_auth.models import Clock, Principal, SystemClock, VerificationProfile

MAX_TOKEN_BYTES = 16 * 1024
MAX_KID_BYTES = 256
BASE64URL_SEGMENT = re.compile(rb"^[A-Za-z0-9_-]+$")
FORBIDDEN_HEADERS = frozenset({"jku", "jwk", "x5u", "x5c", "x5t", "x5t#S256", "crit"})
SCOPE_TOKEN = re.compile(r"^[\x21\x23-\x5B\x5D-\x7E]+$")


class _DuplicateMember(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise _DuplicateMember
        result[name] = value
    return result


def _parse_protected_header(token: str) -> dict[str, object]:
    if not token:
        raise InvalidToken("token_malformed")
    if len(token.encode("utf-8")) > MAX_TOKEN_BYTES:
        raise InvalidToken("token_too_large")
    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidToken("token_malformed")
    try:
        encoded = parts[0].encode("ascii")
        if BASE64URL_SEGMENT.fullmatch(encoded) is None:
            raise ValueError
        raw = b64decode(
            encoded + b"=" * (-len(encoded) % 4),
            altchars=b"-_",
            validate=True,
        )
        value: object = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise InvalidToken("token_malformed") from error
    if not isinstance(value, dict):
        raise InvalidToken("header_invalid")
    return cast(dict[str, object], value)


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
    if name == "kid" and len(value.encode("utf-8")) > MAX_KID_BYTES:
        raise InvalidToken("header_invalid")
    return value


def _numeric_date(claims: Mapping[str, object], name: str) -> float:
    value = claims.get(name)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
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
            decoded = jwt.decode(
                token,
                key,
                algorithms=self._profile.allowed_algorithms,
            )
        except BadSignatureError as error:
            raise InvalidToken("signature_invalid") from error
        except JoseError as error:
            raise InvalidToken("token_malformed") from error
        if decoded.header != header:
            raise InvalidToken("header_invalid")
        if not isinstance(decoded.claims, dict):
            raise InvalidToken("token_malformed")
        return cast(Mapping[str, object], decoded.claims)

    def _validate_times(self, claims: Mapping[str, object], now: float) -> None:
        issued_at = _numeric_date(claims, "iat")
        not_before = _numeric_date(claims, "nbf")
        expires_at = _numeric_date(claims, "exp")
        if expires_at <= issued_at:
            raise InvalidToken("time_claim_invalid")
        if expires_at - issued_at > self._profile.maximum_token_lifetime:
            raise InvalidToken("token_lifetime_exceeded")
        if (
            issued_at > now + self._profile.clock_skew
            or not_before > now + self._profile.clock_skew
        ):
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
