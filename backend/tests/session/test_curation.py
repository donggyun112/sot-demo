from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from sot.identity.contracts import Actor
from sot.session import application, domain
from sot.session.domain import (
    Branch,
    NewTurn,
    SessionForbidden,
    SessionMember,
    SessionNotFound,
    SessionRole,
    VersionConflict,
)
from sot.shared.errors import InvalidInput
from sot.shared.ids import BranchId, BundleId, SessionId, UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.contracts import WorkspaceMembership, WorkspaceRole
from tests.session.test_application import (
    NOW,
    FixedClock,
    Memory,
    access,
    creator,
    setup,
)


def source_branch() -> Branch:
    branch = Branch.create(
        WorkspaceId(uuid4()), SessionId(uuid4()), UserId(uuid4()), NOW
    )
    branch.append_completed(
        expected_version=0,
        messages=(
            NewTurn("user", "question"),
            NewTurn("assistant", "private wording"),
            NewTurn("assistant", "third"),
            NewTurn("tool", "private tool payload"),
        ),
        now=NOW,
    )
    return branch


def test_curation_preserves_source_and_tracks_edited_provenance() -> None:
    branch = source_branch()
    projection = domain.CurationProjection.from_turns(branch.turns)
    projection.apply(domain.DropTurn(branch.turns[0].id))
    projection.apply(domain.EditTurn(branch.turns[1].id, "public wording"))
    assert branch.turns[1].content == "private wording"
    assert [(i.source_ids, i.content, i.provenance) for i in projection.items] == [
        ((branch.turns[1].id,), "public wording", "edited"),
        ((branch.turns[2].id,), "third", "copied"),
    ]


def test_join_uses_ordered_source_ids_and_replays_operations() -> None:
    branch = source_branch()
    ids = (branch.turns[0].id, branch.turns[1].id)
    projection = domain.CurationProjection.from_turns(branch.turns)
    projection.apply(domain.JoinTurns(ids, "summary"))
    projection.apply(domain.EditTurn(ids[0], "revised summary"))
    assert [(i.source_ids, i.content) for i in projection.items] == [
        (ids, "revised summary"),
        ((branch.turns[2].id,), "third"),
    ]
    assert projection.items[0].provenance == "edited"


@pytest.mark.parametrize("kind", ["unknown", "duplicate", "empty", "dropped", "tool"])
def test_invalid_selection_does_not_change_projection(kind: str) -> None:
    branch = source_branch()
    projection = domain.CurationProjection.from_turns(branch.turns)
    first = branch.turns[0].id
    if kind == "dropped":
        projection.apply(domain.DropTurn(first))
    before = projection.items
    ids = {
        "unknown": (uuid4(),),
        "duplicate": (first, first),
        "empty": (),
        "dropped": (first,),
        "tool": (branch.turns[3].id,),
    }[kind]
    with pytest.raises(InvalidInput):
        projection.apply(domain.JoinTurns(ids, "summary"))
    assert projection.items == before


@dataclass
class CuratedMemory(Memory):
    operations: dict[
        tuple[WorkspaceId, BranchId], tuple[domain.CurationRecord, ...]
    ] = field(default_factory=dict)
    bundles: dict[tuple[WorkspaceId, BundleId], domain.Bundle] = field(
        default_factory=dict
    )
    fail_write: bool = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        snapshot = deepcopy((self.operations, self.bundles))
        try:
            async with super().transaction() as tx:
                yield tx
        except BaseException:
            self.operations, self.bundles = snapshot
            raise

    async def list_curation(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> tuple[domain.CurationRecord, ...]:
        self.check(tx)
        self.reads.append("curation_content")
        return self.operations.get((workspace_id, branch_id), ())

    async def append_curation(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        record: domain.CurationRecord,
    ) -> None:
        self.check(tx)
        self.operations[workspace_id, record.branch_id] = (
            *self.operations.get((workspace_id, record.branch_id), ()),
            record,
        )
        if self.fail_write:
            raise RuntimeError("curation write failed")

    async def create_bundle(
        self, tx: TransactionContext, workspace_id: WorkspaceId, bundle: domain.Bundle
    ) -> None:
        self.check(tx)
        self.bundles[workspace_id, bundle.id] = bundle
        if self.fail_write:
            raise RuntimeError("bundle write failed")

    async def session_for_bundle(
        self, tx: TransactionContext, workspace_id: WorkspaceId, bundle_id: BundleId
    ) -> SessionId | None:
        self.check(tx)
        self.reads.append("bundle_ownership")
        bundle = self.bundles.get((workspace_id, bundle_id))
        return bundle.session_id if bundle else None

    async def load_bundle(
        self, tx: TransactionContext, workspace_id: WorkspaceId, bundle_id: BundleId
    ) -> domain.Bundle | None:
        self.check(tx)
        self.reads.append("bundle_content")
        return self.bundles.get((workspace_id, bundle_id))


async def prepared() -> tuple[CuratedMemory, Actor, Branch]:
    original, actor, workspace_id, document_id = setup()
    store = CuratedMemory()
    store.__dict__.update(original.__dict__)
    created = await creator(store).execute(actor, workspace_id, document_id)
    branch = store.branches[workspace_id, created.branch_id]
    branch.append_completed(
        expected_version=0,
        messages=(NewTurn("user", "Q"), NewTurn("assistant", "private")),
        now=NOW,
    )
    return store, actor, deepcopy(branch)


def curation(store: CuratedMemory) -> application.ApplyCuration:
    return application.ApplyCuration(
        store,
        store,
        application.BranchAccess(store, access(store), store),
        lambda: store,
        FixedClock(),
    )


@pytest.mark.asyncio
async def test_curation_and_agent_cite_share_ordered_atomic_versioned_command() -> None:
    store, actor, branch = await prepared()
    command = curation(store)
    before = store.transactions
    first = await command.execute(
        actor,
        branch.workspace_id,
        branch.id,
        expected_version=1,
        operation=domain.EditTurn(branch.turns[1].id, "public"),
    )
    second = await command.create_from_agent(
        actor=actor,
        workspace_id=branch.workspace_id,
        branch_id=branch.id,
        expected_branch_version=2,
        turn_ids=(branch.turns[0].id, branch.turns[1].id),
        summary="citation",
    )
    records = store.operations[branch.workspace_id, branch.id]
    assert (first.branch_version, second.branch_version) == (2, 3)
    assert [r.ordinal for r in records] == [1, 2]
    assert isinstance(records[1].operation, domain.JoinTurns)
    assert records[1].id == second.resource_id
    assert store.transactions == before + 2
    assert store.branches[branch.workspace_id, branch.id].turns == branch.turns


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["stale", "race", "write", "invalid"])
async def test_curation_failure_rolls_back_operation_and_version(failure: str) -> None:
    store, actor, branch = await prepared()
    store.fail_write = failure == "write"
    store.conflict = failure == "race"
    expected_error = {
        "stale": VersionConflict,
        "race": VersionConflict,
        "write": RuntimeError,
        "invalid": InvalidInput,
    }[failure]
    with pytest.raises(expected_error):
        await curation(store).execute(
            actor,
            branch.workspace_id,
            branch.id,
            expected_version=0 if failure == "stale" else 1,
            operation=domain.EditTurn(
                uuid4() if failure == "invalid" else branch.turns[0].id, "edit"
            ),
        )
    assert store.operations == {}
    assert store.branches[branch.workspace_id, branch.id].version == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [SessionRole.EDITOR, SessionRole.VIEWER, None])
async def test_curation_enforces_private_editor_permission_before_content(
    role: SessionRole | None,
) -> None:
    store, _actor, branch = await prepared()
    outsider = Actor(UserId(uuid4()))
    store.workspace_members[branch.workspace_id, outsider.user_id] = (
        WorkspaceMembership(branch.workspace_id, outsider.user_id, WorkspaceRole.OWNER)
    )
    if role is not None:
        store.members[branch.workspace_id, branch.session_id, outsider.user_id] = (
            SessionMember(
                branch.workspace_id, branch.session_id, outsider.user_id, role
            )
        )
    store.reads.clear()
    if role is SessionRole.EDITOR:
        await curation(store).execute(
            outsider,
            branch.workspace_id,
            branch.id,
            expected_version=1,
            operation=domain.DropTurn(branch.turns[0].id),
        )
        assert store.branches[branch.workspace_id, branch.id].version == 2
    else:
        with pytest.raises(SessionNotFound if role is None else SessionForbidden):
            await curation(store).execute(
                outsider,
                branch.workspace_id,
                branch.id,
                expected_version=1,
                operation=domain.DropTurn(branch.turns[0].id),
            )
        assert "curation_content" not in store.reads
        assert "branch_content" not in store.reads
