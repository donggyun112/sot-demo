from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sot.sharing.domain import (
    AttributionSnapshot,
    PublicBundleItem,
    PublicBundleSnapshot,
)


@dataclass(frozen=True, slots=True)
class CreatedShareLink:
    link_id: UUID
    raw_token: str = field(repr=False)


__all__ = [
    "AttributionSnapshot",
    "CreatedShareLink",
    "PublicBundleItem",
    "PublicBundleSnapshot",
]
