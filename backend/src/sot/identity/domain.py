from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sot.shared.errors import SOTError
from sot.shared.ids import UserId


class AuthTokenInvalid(SOTError):
    def __init__(self) -> None:
        super().__init__("auth_token_invalid", "Authentication failed")


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    issuer: str
    subject: str
    email: str
    display_name: str


@dataclass(frozen=True, slots=True)
class User:
    id: UserId
    email: str
    display_name: str


@dataclass(frozen=True, slots=True)
class UserIdentity:
    id: UUID
    user_id: UserId
    issuer: str
    subject: str


@dataclass(frozen=True, slots=True)
class AuthSession:
    id: UUID
    user_id: UserId
    token_hash: str
    family_id: UUID
    expires_at: datetime
    revoked_at: datetime | None = None
