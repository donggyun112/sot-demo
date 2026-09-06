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
