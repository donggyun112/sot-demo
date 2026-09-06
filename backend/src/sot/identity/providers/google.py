from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import cast

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.id_token import verify_oauth2_token

from sot.identity.domain import AuthTokenInvalid, VerifiedIdentity
from sot.identity.providers.base import GoogleTokenVerifier


class ProductionGoogleTokenVerifier:
    async def verify(self, credential: str, audience: str) -> Mapping[str, object]:
        result = await asyncio.to_thread(
            verify_oauth2_token, credential, Request(), audience
        )
        return cast(Mapping[str, object], result)


class GoogleAuthAdapter:
    def __init__(self, audience: str, verifier: GoogleTokenVerifier) -> None:
        if not audience:
            raise ValueError("Google audience is required")
        self._audience, self._verifier = audience, verifier

    async def verify(self, credential: str) -> VerifiedIdentity:
        try:
            claims = await self._verifier.verify(credential, self._audience)
        except (ValueError, GoogleAuthError):
            raise AuthTokenInvalid() from None
        subject, email = claims.get("sub"), claims.get("email")
        if (
            claims.get("iss")
            not in ("accounts.google.com", "https://accounts.google.com")
            or claims.get("aud") != self._audience
            or claims.get("email_verified") is not True
            or not isinstance(subject, str)
            or not subject
            or not isinstance(email, str)
            or not email
        ):
            raise AuthTokenInvalid()
        name = claims.get("name")
        return VerifiedIdentity(
            "https://accounts.google.com",
            subject,
            email,
            name if isinstance(name, str) else email,
        )
