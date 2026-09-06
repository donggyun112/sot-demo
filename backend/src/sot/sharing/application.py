from __future__ import annotations

import secrets
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from sot.identity.contracts import Actor, IdentityAttributionReader
from sot.session.contracts import (
    BundleRevocationAuthorizer,
    ForkAttribution,
    ForkedSessionResult,
    ForkSeedItem,
    SessionForkWriter,
    ShareableBundleReader,
)
from sot.shared.clock import Clock
from sot.shared.ids import BundleId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext, UnitOfWorkFactory
from sot.sharing.contracts import CreatedShareLink, PublicBundleReader
from sot.sharing.domain import (
    AttributionSnapshot,
    PublicBundleItem,
    PublicBundleSnapshot,
    ShareLink,
    ShareLinkNotFound,
    ShareLinkStatus,
)
from sot.sharing.ports import ShareLinkRepository
from sot.workspace.contracts import Permission, WorkspaceAuthorizer


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
        bundles: BundleRevocationAuthorizer,
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
            await self._bundles.require_revocation(
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
            return await self.require_snapshot(tx, raw_token)

    async def require_snapshot(
        self, tx: TransactionContext, raw_token: str
    ) -> PublicBundleSnapshot:
        link = await self._repository.find_by_token_hash(
            tx, sha256(raw_token.encode()).digest()
        )
        if link is None or link.status(self._clock.now()) is not ShareLinkStatus.ACTIVE:
            raise ShareLinkNotFound()
        return link.snapshot


class ForkSharedBundle:
    def __init__(
        self,
        public_bundles: PublicBundleReader,
        workspaces: WorkspaceAuthorizer,
        sessions: SessionForkWriter,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._public_bundles = public_bundles
        self._workspaces = workspaces
        self._sessions = sessions
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: Actor,
        destination_workspace_id: WorkspaceId,
        *,
        raw_token: str,
    ) -> ForkedSessionResult:
        async with self._uow_factory().transaction() as tx:
            snapshot = await self._public_bundles.require_snapshot(tx, raw_token)
            await self._workspaces.require(
                tx, actor, destination_workspace_id, Permission.SESSION_CREATE
            )
            return await self._sessions.create_from_public_bundle(
                tx,
                actor=actor,
                destination_workspace_id=destination_workspace_id,
                source_bundle_id=snapshot.bundle_id,
                attribution=ForkAttribution(
                    snapshot.attribution.title,
                    snapshot.attribution.author_display_name,
                    snapshot.attribution.published_at,
                ),
                items=tuple(
                    ForkSeedItem(item.source_ids, item.role, item.content)
                    for item in snapshot.items
                ),
            )
