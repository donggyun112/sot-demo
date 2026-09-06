from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from sot.shared.errors import InvalidInput, NotFound
from sot.shared.ids import BundleId, UserId, WorkspaceId


class ShareLinkStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ShareLinkNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("share_link_not_found", "Share link not found")


@dataclass(frozen=True, slots=True)
class PublicBundleItem:
    source_ids: tuple[UUID, ...]
    role: Literal["user", "assistant"]
    content: str
    provenance: Literal["copied", "edited"]


@dataclass(frozen=True, slots=True)
class AttributionSnapshot:
    title: str
    author_display_name: str
    published_at: datetime


@dataclass(frozen=True, slots=True)
class PublicBundleSnapshot:
    bundle_id: BundleId
    title: str
    items: tuple[PublicBundleItem, ...]
    attribution: AttributionSnapshot


@dataclass(frozen=True, slots=True)
class ShareLink:
    id: UUID
    workspace_id: WorkspaceId
    bundle_id: BundleId
    token_hash: bytes = field(repr=False)
    created_by: UserId
    created_at: datetime
    expires_at: datetime | None
    snapshot: PublicBundleSnapshot
    revoked_by: UserId | None = None
    revoked_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
        token_hash: bytes,
        created_by: UserId,
        created_at: datetime,
        expires_at: datetime | None,
        snapshot: PublicBundleSnapshot,
    ) -> ShareLink:
        if expires_at is not None and expires_at <= created_at:
            raise InvalidInput(
                "share_link_expiry_invalid", "Expiry must be in the future"
            )
        if len(token_hash) != 32 or snapshot.bundle_id != bundle_id:
            raise InvalidInput(
                "share_link_invalid", "Invalid share link snapshot or hash"
            )
        return cls(
            uuid4(),
            workspace_id,
            bundle_id,
            token_hash,
            created_by,
            created_at,
            expires_at,
            snapshot,
        )

    def status(self, now: datetime) -> ShareLinkStatus:
        if self.revoked_at is not None:
            return ShareLinkStatus.REVOKED
        if self.expires_at is not None and self.expires_at <= now:
            return ShareLinkStatus.EXPIRED
        return ShareLinkStatus.ACTIVE

    def revoke(self, actor_id: UserId, now: datetime) -> ShareLink:
        if self.revoked_at is not None:
            return self
        return replace(self, revoked_by=actor_id, revoked_at=now)
