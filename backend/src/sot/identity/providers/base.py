from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from sot.identity.domain import VerifiedIdentity


class AuthProvider(Protocol):
    async def verify(self, credential: str) -> VerifiedIdentity: ...


class GoogleTokenVerifier(Protocol):
    async def verify(self, credential: str, audience: str) -> Mapping[str, object]: ...
