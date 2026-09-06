from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sot.shared.ids import UserId
from sot.shared.unit_of_work import TransactionContext


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: UserId


class IdentityReader(Protocol):
    async def require_actor(self, tx: TransactionContext, user_id: UserId) -> Actor: ...
