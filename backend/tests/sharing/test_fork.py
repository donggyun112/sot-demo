from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from datetime import timedelta
from hashlib import sha256
from typing import Literal, cast
from uuid import uuid4

import pytest

from sot.identity.contracts import Actor
from sot.session.application import CreateSessionFork
from sot.session.contracts import ForkAttribution, ForkedSessionResult, ForkSeedItem
from sot.shared.errors import InvalidInput
from sot.shared.ids import BundleId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.sharing.application import ForkSharedBundle, ReadPublicBundle
from sot.sharing.domain import (
    AttributionSnapshot,
    PublicBundleItem,
    PublicBundleSnapshot,
    ShareLink,
    ShareLinkNotFound,
)
from sot.workspace.contracts import WorkspaceMembership, WorkspaceRole
from sot.workspace.domain import WorkspaceForbidden, WorkspaceNotFound
from tests.session.test_application import NOW, FixedClock, setup
from tests.session.test_fork_origin import ForkMemory
from tests.sharing.test_share_link import SharingMemory


class RecordingWriter(CreateSessionFork):
    received: tuple[ForkSeedItem, ...] = ()
    attribution: ForkAttribution | None = None

    async def create_from_public_bundle(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        destination_workspace_id: WorkspaceId,
        source_bundle_id: BundleId,
        attribution: ForkAttribution,
        items: tuple[ForkSeedItem, ...],
    ) -> ForkedSessionResult:
        self.received, self.attribution = items, attribution
        return await super().create_from_public_bundle(
            tx,
            actor=actor,
            destination_workspace_id=destination_workspace_id,
            source_bundle_id=source_bundle_id,
            attribution=attribution,
            items=items,
        )


def fixture() -> tuple[
    ForkMemory,
    SharingMemory,
    Actor,
    WorkspaceId,
    ShareLink,
    RecordingWriter,
    ForkSharedBundle,
]:
    _, actor, destination, _ = setup()
    memory = ForkMemory()
    memory.workspace_members[destination, actor.user_id] = WorkspaceMembership(
        destination, actor.user_id, WorkspaceRole.MEMBER
    )
    bundle_id = BundleId(uuid4())
    link = ShareLink.create(
        workspace_id=WorkspaceId(uuid4()),
        bundle_id=bundle_id,
        token_hash=sha256(b"public-token").digest(),
        created_by=actor.user_id,
        created_at=NOW,
        expires_at=NOW + timedelta(days=1),
        snapshot=PublicBundleSnapshot(
            bundle_id,
            "Public title",
            (
                PublicBundleItem(
                    (uuid4(), uuid4()), "user", "Public question", "edited"
                ),
                PublicBundleItem((uuid4(),), "assistant", "Public answer", "copied"),
            ),
            AttributionSnapshot("Public title", "Publisher", NOW),
        ),
    )
    # No source workspace, session, profile, bundle, or private turn exists here.
    sharing = SharingMemory(memory, links={link.id: link})  # type: ignore[arg-type]
    writer = RecordingWriter(memory, memory, FixedClock())
    handler = ForkSharedBundle(
        ReadPublicBundle(sharing, lambda: sharing, sharing),
        memory,
        writer,
        lambda: sharing,
    )
    return memory, sharing, actor, destination, link, writer, handler


@pytest.mark.asyncio
async def test_fork_uses_one_transaction_and_only_sanitized_public_items() -> None:
    memory, _, actor, destination, link, writer, handler = fixture()
    result = await handler.execute(actor, destination, raw_token="public-token")
    assert memory.transactions == 1
    assert memory.reads == ["workspace"]
    assert memory.sessions[destination, result.session_id].document_id is None
    branch = memory.branches[destination, result.branch_id]
    assert [(t.role, t.content) for t in branch.turns] == [
        ("user", "Public question"),
        ("assistant", "Public answer"),
    ]
    assert [item.source_ids for item in writer.received] == [
        item.source_ids for item in link.snapshot.items
    ]
    assert all(type(item) is ForkSeedItem for item in writer.received)
    assert {f.name for f in fields(writer.received[0])} == {
        "source_ids",
        "role",
        "content",
    }
    assert type(writer.attribution) is ForkAttribution
    assert (
        memory.origins[destination, result.session_id].source_bundle_id
        == link.bundle_id
    )
    assert set(memory.workspace_members) == {(destination, actor.user_id)}


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing", "revoked", "expired"])
async def test_unusable_link_denies_fork_without_destination_writes(state: str) -> None:
    memory, sharing, actor, destination, link, _, handler = fixture()
    token = "public-token"
    if state == "missing":
        token = "invalid"
    elif state == "revoked":
        sharing.links[link.id] = link.revoke(actor.user_id, NOW)
    else:
        sharing.now_value = NOW + timedelta(days=1)
    with pytest.raises(ShareLinkNotFound):
        await handler.execute(actor, destination, raw_token=token)
    assert (memory.sessions, memory.members, memory.branches, memory.origins) == (
        {},
        {},
        {},
        {},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("membership", ["absent", "viewer"])
async def test_destination_permission_is_required_before_any_session_write(
    membership: str,
) -> None:
    memory, _, actor, destination, _, writer, handler = fixture()
    if membership == "absent":
        memory.workspace_members.clear()
    else:
        memory.workspace_members[destination, actor.user_id] = WorkspaceMembership(
            destination, actor.user_id, WorkspaceRole.VIEWER
        )
    memory.fail_branch = True  # Would expose a write attempted before permission.
    with pytest.raises((WorkspaceNotFound, WorkspaceForbidden)):
        await handler.execute(actor, destination, raw_token="public-token")
    assert writer.received == ()
    assert (memory.sessions, memory.members, memory.branches, memory.origins) == (
        {},
        {},
        {},
        {},
    )


@pytest.mark.asyncio
async def test_source_revocation_and_removal_do_not_change_completed_fork() -> None:
    memory, sharing, actor, destination, link, _, handler = fixture()
    result = await handler.execute(actor, destination, raw_token="public-token")
    before = deepcopy(
        (memory.sessions, memory.members, memory.branches, memory.origins)
    )
    sharing.links[link.id] = replace(link, revoked_at=NOW, revoked_by=actor.user_id)
    with pytest.raises(ShareLinkNotFound):
        await handler.execute(actor, destination, raw_token="public-token")
    sharing.links.clear()
    assert (memory.sessions, memory.members, memory.branches, memory.origins) == before
    assert (
        memory.origins[destination, result.session_id].author_display_name
        == "Publisher"
    )


@pytest.mark.asyncio
async def test_fork_command_rolls_back_writer_failure() -> None:
    memory, _, actor, destination, _, _, handler = fixture()
    memory.fail_origin = True
    with pytest.raises(RuntimeError, match="origin write failed"):
        await handler.execute(actor, destination, raw_token="public-token")
    assert (memory.sessions, memory.members, memory.branches, memory.origins) == (
        {},
        {},
        {},
        {},
    )


@pytest.mark.asyncio
async def test_malformed_public_tool_item_cannot_seed_private_tool_content() -> None:
    memory, sharing, actor, destination, link, _, handler = fixture()
    sharing.links[link.id] = replace(
        link,
        snapshot=replace(
            link.snapshot,
            items=(
                PublicBundleItem(
                    (uuid4(),),
                    cast(Literal["user", "assistant"], "tool"),
                    "Private tool payload",
                    "copied",
                ),
            ),
        ),
    )
    with pytest.raises(InvalidInput):
        await handler.execute(actor, destination, raw_token="public-token")
    assert (memory.sessions, memory.members, memory.branches, memory.origins) == (
        {},
        {},
        {},
        {},
    )
