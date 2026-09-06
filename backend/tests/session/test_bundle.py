from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from uuid import uuid4

import pytest

from sot.identity.contracts import Actor
from sot.session import application, domain
from sot.shared.ids import BundleId, UserId, WorkspaceId
from sot.workspace.contracts import WorkspaceMembership, WorkspaceRole
from sot.workspace.domain import WorkspaceNotFound
from tests.session.test_application import NOW, FixedClock, access
from tests.session.test_curation import CuratedMemory, curation, prepared, source_branch


def test_published_bundle_is_immutable_and_survives_later_curation() -> None:
    branch = source_branch()
    projection = domain.CurationProjection.from_turns(branch.turns)
    projection.apply(domain.EditTurn(branch.turns[1].id, "public wording"))
    bundle = domain.Bundle.publish(
        branch, projection.items, branch.created_by, NOW, title="Public"
    )
    projection.apply(domain.EditTurn(branch.turns[1].id, "later edit"))
    assert bundle.items[1].content == "public wording"
    assert bundle.items[1].source_ids == (branch.turns[1].id,)
    with pytest.raises(FrozenInstanceError):
        bundle.items[1].content = "mutation"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        bundle.title = "mutation"  # type: ignore[misc]


def publisher(store: CuratedMemory) -> application.PublishBundle:
    return application.PublishBundle(
        store,
        store,
        store,
        application.BranchAccess(store, access(store), store),
        lambda: store,
        FixedClock(),
    )


@pytest.mark.asyncio
async def test_publish_materializes_projection_then_later_preview_changes_only() -> (
    None
):
    store, actor, branch = await prepared()
    await curation(store).execute(
        actor,
        branch.workspace_id,
        branch.id,
        expected_version=1,
        operation=domain.EditTurn(branch.turns[1].id, "public"),
    )
    before = store.transactions
    result = await publisher(store).execute(
        actor, branch.workspace_id, branch.id, expected_version=2, title="Public"
    )
    assert result.branch_version == 3
    assert store.transactions == before + 1
    await curation(store).execute(
        actor,
        branch.workspace_id,
        branch.id,
        expected_version=3,
        operation=domain.EditTurn(branch.turns[1].id, "later"),
    )
    preview = await application.PreviewBundle(
        store, application.BranchAccess(store, access(store), store), lambda: store
    ).execute(actor, branch.workspace_id, branch.id)
    assert [item.content for item in preview] == ["Q", "later"]
    reader = application.BundleAccess(store, access(store), store)
    before = store.transactions
    async with store.transaction() as tx:
        snapshot = await reader.require_snapshot(
            tx,
            actor=actor,
            workspace_id=branch.workspace_id,
            bundle_id=BundleId(result.resource_id),
        )
    assert store.transactions == before + 1
    assert [item.content for item in snapshot.items] == ["Q", "public"]
    assert set(asdict(snapshot)) == {"bundle_id", "title", "items", "published_at"}
    assert set(asdict(snapshot.items[0])) == {
        "source_ids",
        "role",
        "content",
        "provenance",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["stale", "race", "write", "editor", "closed", "ceiling"]
)
async def test_publish_failure_leaves_no_bundle_or_version_change(failure: str) -> None:
    store, actor, branch = await prepared()
    store.fail_write = failure == "write"
    store.conflict = failure == "race"
    if failure == "editor":
        store.members[branch.workspace_id, branch.session_id, actor.user_id] = (
            domain.SessionMember(
                branch.workspace_id,
                branch.session_id,
                actor.user_id,
                domain.SessionRole.EDITOR,
            )
        )
    if failure == "closed":
        store.sessions[branch.workspace_id, branch.session_id].close()
    if failure == "ceiling":
        store.workspace_members[branch.workspace_id, actor.user_id] = (
            WorkspaceMembership(
                branch.workspace_id, actor.user_id, WorkspaceRole.VIEWER
            )
        )
    error = {
        "stale": domain.VersionConflict,
        "race": domain.VersionConflict,
        "write": RuntimeError,
        "editor": domain.SessionForbidden,
        "closed": domain.SessionClosed,
        "ceiling": domain.SessionForbidden,
    }[failure]
    with pytest.raises(error):
        await publisher(store).execute(
            actor,
            branch.workspace_id,
            branch.id,
            expected_version=0 if failure == "stale" else 1,
            title="Public",
        )
    assert store.bundles == {}
    assert store.branches[branch.workspace_id, branch.id].version == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_bundle_reader_hides_existence_from_uninvited_member(
    existing: bool,
) -> None:
    store, actor, branch = await prepared()
    result = await publisher(store).execute(
        actor, branch.workspace_id, branch.id, expected_version=1, title="Public"
    )
    outsider = Actor(UserId(uuid4()))
    store.workspace_members[branch.workspace_id, outsider.user_id] = (
        WorkspaceMembership(branch.workspace_id, outsider.user_id, WorkspaceRole.OWNER)
    )
    store.reads.clear()
    async with store.transaction() as tx:
        with pytest.raises(domain.SessionNotFound):
            await application.BundleAccess(
                store, access(store), store
            ).require_snapshot(
                tx,
                actor=outsider,
                workspace_id=branch.workspace_id,
                bundle_id=BundleId(result.resource_id)
                if existing
                else BundleId(uuid4()),
            )
    assert "bundle_content" not in store.reads
    assert "session_content" not in store.reads


@pytest.mark.asyncio
async def test_bundle_and_preview_are_workspace_scoped() -> None:
    store, actor, branch = await prepared()
    result = await publisher(store).execute(
        actor, branch.workspace_id, branch.id, expected_version=1, title="Public"
    )
    other = WorkspaceId(uuid4())
    reader = application.BundleAccess(store, access(store), store)
    store.reads.clear()
    async with store.transaction() as tx:
        with pytest.raises(WorkspaceNotFound):
            await reader.require_snapshot(
                tx,
                actor=actor,
                workspace_id=other,
                bundle_id=BundleId(result.resource_id),
            )
    assert store.reads == ["workspace"]
    store.workspace_members[other, actor.user_id] = WorkspaceMembership(
        other, actor.user_id, WorkspaceRole.MEMBER
    )
    async with store.transaction() as tx:
        with pytest.raises(domain.SessionNotFound):
            await reader.require_snapshot(
                tx,
                actor=actor,
                workspace_id=other,
                bundle_id=BundleId(result.resource_id),
            )
    with pytest.raises(domain.SessionNotFound):
        await application.PreviewBundle(
            store, application.BranchAccess(store, access(store), store), lambda: store
        ).execute(actor, other, branch.id)
