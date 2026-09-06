from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from sot.identity.contracts import Actor, IdentityAttribution, UserNotFound
from sot.session.application import BundleAccess
from sot.session.domain import SessionForbidden, SessionMember, SessionRole
from sot.shared.errors import InvalidInput
from sot.shared.ids import BundleId, UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.sharing.application import CreateShareLink, RevokeShareLink
from sot.sharing.domain import (
    AttributionSnapshot,
    PublicBundleSnapshot,
    ShareLink,
    ShareLinkNotFound,
    ShareLinkStatus,
)
from sot.workspace.contracts import WorkspaceMembership, WorkspaceRole
from tests.session.test_application import NOW, access, creator
from tests.session.test_bundle import publisher
from tests.session.test_curation import CuratedMemory, prepared


@dataclass
class SharingMemory:
    source: CuratedMemory
    links: dict[UUID, ShareLink] = field(default_factory=dict)
    names: dict[UserId, str] = field(default_factory=dict)
    now_value: datetime = NOW
    fail_save: bool = False
    last_lookup: bytes | None = None

    def now(self) -> datetime:
        return self.now_value

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        before = deepcopy(self.links)
        try:
            async with self.source.transaction() as tx:
                yield tx
        except BaseException:
            self.links = before
            raise

    async def create_link(self, tx: TransactionContext, link: ShareLink) -> None:
        self.source.check(tx)
        assert isinstance(link.token_hash, bytes) and len(link.token_hash) == 32
        self.links[link.id] = link
        if self.fail_save:
            raise RuntimeError("write failed")

    async def find_link(
        self, tx: TransactionContext, workspace_id: WorkspaceId, link_id: UUID
    ) -> ShareLink | None:
        self.source.check(tx)
        link = self.links.get(link_id)
        return link if link and link.workspace_id == workspace_id else None

    async def save_link(self, tx: TransactionContext, link: ShareLink) -> None:
        await self.create_link(tx, link)

    async def find_by_token_hash(
        self, tx: TransactionContext, token_hash: bytes
    ) -> ShareLink | None:
        self.source.check(tx)
        self.last_lookup = token_hash
        return next(
            (v for v in self.links.values() if v.token_hash == token_hash), None
        )

    async def require_attribution(
        self, tx: TransactionContext, user_id: UserId
    ) -> IdentityAttribution:
        self.source.check(tx)
        if user_id not in self.names:
            raise UserNotFound()
        return IdentityAttribution(self.names[user_id])


def create_handler(store: SharingMemory) -> CreateShareLink:
    return CreateShareLink(
        store,
        BundleAccess(store.source, access(store.source), store.source),
        store,
        lambda: store,
        store,
    )


def revoke_handler(store: SharingMemory) -> RevokeShareLink:
    return RevokeShareLink(
        store,
        BundleAccess(store.source, access(store.source), store.source),
        lambda: store,
        store,
    )


async def shared_fixture() -> tuple[SharingMemory, Actor, WorkspaceId, BundleId]:
    source, actor, branch = await prepared()
    result = await publisher(source).execute(
        actor, branch.workspace_id, branch.id, expected_version=1, title="Public"
    )
    store = SharingMemory(source, names={actor.user_id: "Publisher"})
    return store, actor, branch.workspace_id, BundleId(result.resource_id)


def test_lifecycle_is_immutable_and_expiry_is_derived() -> None:
    bundle_id, user_id = BundleId(uuid4()), UserId(uuid4())
    link = ShareLink.create(
        workspace_id=WorkspaceId(uuid4()),
        bundle_id=bundle_id,
        token_hash=sha256(b"token").digest(),
        created_by=user_id,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
        snapshot=PublicBundleSnapshot(
            bundle_id, "Public", (), AttributionSnapshot("Public", "Publisher", NOW)
        ),
    )
    assert link.status(NOW) is ShareLinkStatus.ACTIVE
    assert link.status(NOW + timedelta(days=7)) is ShareLinkStatus.EXPIRED
    revoked = link.revoke(user_id, NOW)
    assert revoked.status(NOW) is ShareLinkStatus.REVOKED
    assert revoked.status(NOW + timedelta(days=8)) is ShareLinkStatus.REVOKED
    assert link.revoked_at is None
    assert revoked.revoke(UserId(uuid4()), NOW + timedelta(days=1)) == revoked


@pytest.mark.asyncio
async def test_create_uses_actual_publisher_and_stores_only_hash() -> None:
    store, publisher_actor, workspace_id, bundle_id = await shared_fixture()
    sharer = Actor(UserId(uuid4()))
    bundle = store.source.bundles[workspace_id, bundle_id]
    store.source.workspace_members[workspace_id, sharer.user_id] = WorkspaceMembership(
        workspace_id, sharer.user_id, WorkspaceRole.MEMBER
    )
    store.source.members[workspace_id, bundle.session_id, sharer.user_id] = (
        SessionMember(
            workspace_id, bundle.session_id, sharer.user_id, SessionRole.OWNER
        )
    )
    store.names[sharer.user_id] = "Link creator"
    before = store.source.transactions
    result = await create_handler(store).execute(sharer, workspace_id, bundle_id)
    assert store.source.transactions == before + 1
    link = store.links[result.link_id]
    assert link.created_by == sharer.user_id != publisher_actor.user_id
    assert link.snapshot.attribution.author_display_name == "Publisher"
    assert len(result.raw_token) == 43
    assert link.token_hash == sha256(result.raw_token.encode()).digest()
    assert result.raw_token not in repr(link)
    assert result.raw_token not in repr(result)
    second = await create_handler(store).execute(sharer, workspace_id, bundle_id)
    assert second.raw_token != result.raw_token


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [SessionRole.VIEWER, SessionRole.EDITOR])
async def test_owning_other_session_cannot_create_or_revoke_link(
    role: SessionRole,
) -> None:
    store, owner, workspace_id, bundle_id = await shared_fixture()
    result = await create_handler(store).execute(owner, workspace_id, bundle_id)
    attacker = Actor(UserId(uuid4()))
    bundle = store.source.bundles[workspace_id, bundle_id]
    store.source.workspace_members[workspace_id, attacker.user_id] = (
        WorkspaceMembership(workspace_id, attacker.user_id, WorkspaceRole.MEMBER)
    )
    document_id = store.source.sessions[workspace_id, bundle.session_id].document_id
    assert document_id is not None
    await creator(store.source).execute(attacker, workspace_id, document_id)
    store.source.members[workspace_id, bundle.session_id, attacker.user_id] = (
        SessionMember(workspace_id, bundle.session_id, attacker.user_id, role)
    )
    with pytest.raises(SessionForbidden):
        await create_handler(store).execute(attacker, workspace_id, bundle_id)
    with pytest.raises(SessionForbidden):
        await revoke_handler(store).execute(attacker, workspace_id, result.link_id)
    assert len(store.links) == 1
    assert store.links[result.link_id].status(NOW) is ShareLinkStatus.ACTIVE


@pytest.mark.asyncio
async def test_revoke_is_workspace_scoped_and_preserves_bundle() -> None:
    store, actor, workspace_id, bundle_id = await shared_fixture()
    result = await create_handler(store).execute(actor, workspace_id, bundle_id)
    bundles = deepcopy(store.source.bundles)
    with pytest.raises(ShareLinkNotFound):
        await revoke_handler(store).execute(actor, WorkspaceId(uuid4()), result.link_id)
    before = store.source.transactions
    await revoke_handler(store).execute(actor, workspace_id, result.link_id)
    assert store.source.transactions == before + 1
    assert store.links[result.link_id].revoked_by == actor.user_id
    assert store.source.bundles == bundles


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["write", "identity", "expiry"])
async def test_create_failure_leaves_no_link(failure: str) -> None:
    store, actor, workspace_id, bundle_id = await shared_fixture()
    store.fail_save = failure == "write"
    if failure == "identity":
        store.names.clear()
    error = {"write": RuntimeError, "identity": UserNotFound, "expiry": InvalidInput}[
        failure
    ]
    with pytest.raises(error):
        await create_handler(store).execute(
            actor,
            workspace_id,
            bundle_id,
            expires_at=NOW if failure == "expiry" else None,
        )
    assert store.links == {}


@pytest.mark.asyncio
async def test_failed_revoke_rolls_back_link_state() -> None:
    store, actor, workspace_id, bundle_id = await shared_fixture()
    result = await create_handler(store).execute(actor, workspace_id, bundle_id)
    store.fail_save = True
    with pytest.raises(RuntimeError):
        await revoke_handler(store).execute(actor, workspace_id, result.link_id)
    assert store.links[result.link_id].status(NOW) is ShareLinkStatus.ACTIVE
