from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sot.shared.errors import NotFound
from sot.shared.ids import UserId
from sot.shared.unit_of_work import TransactionContext


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: UserId


class UserNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("user_not_found", "User not found")


class IdentityReader(Protocol):
    """Read a target identity; raise UserNotFound for a nonexistent user."""

    async def require_actor(self, tx: TransactionContext, user_id: UserId) -> Actor: ...


@dataclass(frozen=True, slots=True)
class IdentityAttribution:
    display_name: str


class IdentityAttributionReader(Protocol):
    """Resolve a publisher's display name without exposing their private profile."""

    async def require_attribution(
        self, tx: TransactionContext, user_id: UserId
    ) -> IdentityAttribution: ...


class IdentityDirectory(Protocol):
    """Find an account by the address colleagues already know it by.

    Returns None rather than raising: an invitation to someone without an
    account yet is valid, and binds when they first sign in.
    """

    async def find_by_email(
        self, tx: TransactionContext, email: str
    ) -> UserId | None: ...

    async def require_email(self, tx: TransactionContext, user_id: UserId) -> str:
        """The address this account is reachable at, for matching invitations."""
        ...
