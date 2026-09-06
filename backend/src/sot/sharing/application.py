from __future__ import annotations

import secrets
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from sot.identity.contracts import Actor, IdentityAttributionReader
from sot.session.contracts import ShareableBundleReader
from sot.shared.clock import Clock
from sot.shared.ids import BundleId, WorkspaceId
from sot.shared.unit_of_work import UnitOfWorkFactory
from sot.sharing.contracts import CreatedShareLink
from sot.sharing.domain import (
    AttributionSnapshot,
    PublicBundleItem,
    PublicBundleSnapshot,
    ShareLink,
    ShareLinkNotFound,
    ShareLinkStatus,
)
from sot.sharing.ports import ShareLinkRepository


class CreateShareLink:
    def __init__(
        self,
        repository: ShareLinkRepository,
        bundles: ShareableBundleReader,
        identities: IdentityAttributionReader,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._bundles = bundles
        self._identities = identities
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
        *,
        expires_at: datetime | None = None,
    ) -> CreatedShareLink:
        async with self._uow_factory().transaction() as tx:
            shareable = await self._bundles.require_shareable_snapshot(
                tx, actor=actor, workspace_id=workspace_id, bundle_id=bundle_id
            )
            author = await self._identities.require_attribution(
                tx, shareable.published_by
            )
            bundle = shareable.snapshot
            snapshot = PublicBundleSnapshot(
                bundle.bundle_id,
                bundle.title,
                tuple(
                    PublicBundleItem(
                        item.source_ids, item.role, item.content, item.provenance
                    )
                    for item in bundle.items
                ),
                AttributionSnapshot(
                    bundle.title, author.display_name, bundle.published_at
                ),
            )
            raw_token = secrets.token_urlsafe(32)
            link = ShareLink.create(
                workspace_id=workspace_id,
                bundle_id=bundle_id,
                token_hash=sha256(raw_token.encode()).digest(),
                created_by=actor.user_id,
                created_at=self._clock.now(),
                expires_at=expires_at,
                snapshot=snapshot,
            )
            await self._repository.create_link(tx, link)
            return CreatedShareLink(link.id, raw_token)


class RevokeShareLink:
    def __init__(
        self,
        repository: ShareLinkRepository,
        bundles: ShareableBundleReader,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._bundles = bundles
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, link_id: UUID
    ) -> None:
        async with self._uow_factory().transaction() as tx:
            link = await self._repository.find_link(tx, workspace_id, link_id)
            if link is None:
                raise ShareLinkNotFound()
            await self._bundles.require_shareable_snapshot(
                tx, actor=actor, workspace_id=workspace_id, bundle_id=link.bundle_id
            )
            await self._repository.save_link(
                tx, link.revoke(actor.user_id, self._clock.now())
            )


class ReadPublicBundle:
    def __init__(
        self,
        repository: ShareLinkRepository,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, raw_token: str) -> PublicBundleSnapshot:
        async with self._uow_factory().transaction() as tx:
            link = await self._repository.find_by_token_hash(
                tx, sha256(raw_token.encode()).digest()
            )
            if (
                link is None
                or link.status(self._clock.now()) is not ShareLinkStatus.ACTIVE
            ):
                raise ShareLinkNotFound()
            return link.snapshot
