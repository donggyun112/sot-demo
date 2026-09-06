from __future__ import annotations

from collections.abc import Mapping

import pytest

from sot.identity.domain import AuthTokenInvalid
from sot.identity.providers.google import GoogleAuthAdapter


class StaticVerifier:
    def __init__(self, claims: Mapping[str, object]) -> None:
        self.claims = claims

    async def verify(self, credential: str, audience: str) -> Mapping[str, object]:
        assert credential == "credential"
        assert audience == "client-id"
        return self.claims


CLAIMS: dict[str, object] = {
    "iss": "https://accounts.google.com",
    "sub": "123",
    "aud": "client-id",
    "email": "alice@example.com",
    "email_verified": True,
    "name": "Alice",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("iss", "https://evil.example"),
        ("aud", "wrong"),
        ("sub", ""),
        ("sub", None),
        ("email_verified", False),
        ("email_verified", "true"),
        ("email", ""),
    ],
)
async def test_rejects_invalid_google_claims(field: str, value: object) -> None:
    adapter = GoogleAuthAdapter("client-id", StaticVerifier({**CLAIMS, field: value}))
    with pytest.raises(AuthTokenInvalid, match="Authentication failed"):
        await adapter.verify("credential")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "issuer", ["accounts.google.com", "https://accounts.google.com"]
)
async def test_normalizes_both_verified_google_issuers(issuer: str) -> None:
    adapter = GoogleAuthAdapter("client-id", StaticVerifier({**CLAIMS, "iss": issuer}))
    identity = await adapter.verify("credential")
    assert identity.issuer == "https://accounts.google.com"
    assert identity.subject == "123"
    assert identity.email == "alice@example.com"


@pytest.mark.asyncio
async def test_verification_failure_does_not_expose_credential() -> None:
    class RejectingVerifier:
        async def verify(self, credential: str, audience: str) -> Mapping[str, object]:
            raise ValueError("secret credential")

    with pytest.raises(AuthTokenInvalid, match="^Authentication failed$"):
        await GoogleAuthAdapter("client-id", RejectingVerifier()).verify("credential")
