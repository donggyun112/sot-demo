from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from sot.shared.unit_of_work import TransactionContext
from sot.sharing.domain import (
    AttributionSnapshot,
    PublicBundleItem,
    PublicBundleSnapshot,
)


@dataclass(frozen=True, slots=True)
class CreatedShareLink:
    link_id: UUID
    raw_token: str = field(repr=False)


class PublicBundleReader(Protocol):
    """Authenticate a public snapshot capability in the caller's transaction."""

    async def require_snapshot(
        self, tx: TransactionContext, raw_token: str
    ) -> PublicBundleSnapshot: ...


__all__ = [
    "AttributionSnapshot",
    "CreatedShareLink",
    "PublicBundleItem",
    "PublicBundleReader",
    "PublicBundleSnapshot",
]
