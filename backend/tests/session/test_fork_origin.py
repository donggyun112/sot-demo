from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError, dataclass, field
from uuid import uuid4

import pytest

from sot.session.application import CreateSessionFork
from sot.session.contracts import ForkAttribution, ForkSeedItem
from sot.session.domain import ForkOrigin, SessionRole, SessionStatus, Turn
from sot.shared.ids import BranchId, BundleId, SessionId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from tests.session.test_application import NOW, FixedClock, Memory, setup


@dataclass
class ForkMemory(Memory):
    origins: dict[tuple[WorkspaceId, SessionId], ForkOrigin] = field(
        default_factory=dict
    )
    fail_origin: bool = False
    fail_turns: bool = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        before = deepcopy(self.origins)
        try:
            async with super().transaction() as tx:
                yield tx
        except BaseException:
            self.origins = before
            raise

    async def create_origin(
        self, tx: TransactionContext, workspace_id: WorkspaceId, origin: ForkOrigin
    ) -> None:
        self.check(tx)
        assert origin.workspace_id == workspace_id
        self.origins[workspace_id, origin.session_id] = origin
        if self.fail_origin:
            raise RuntimeError("origin write failed")

    async def append_turns(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        turns: tuple[Turn, ...],
    ) -> None:
        await super().append_turns(tx, workspace_id, branch_id, turns)
        if self.fail_turns:
            raise RuntimeError("turn write failed")


@pytest.mark.asyncio
async def test_writer_joins_caller_transaction_and_creates_detached_private_session() -> (
    None
):
    _, actor, workspace_id, _ = setup()
    store = ForkMemory()
    source_id, source_bundle_id = uuid4(), BundleId(uuid4())
    async with store.transaction() as tx:
        result = await CreateSessionFork(
            store, store, FixedClock()
        ).create_from_public_bundle(
            tx,
            actor=actor,
            destination_workspace_id=workspace_id,
            source_bundle_id=source_bundle_id,
            attribution=ForkAttribution("Shared title", "Publisher", NOW),
            items=(ForkSeedItem((source_id,), "assistant", "Public answer"),),
        )
    session = store.sessions[workspace_id, result.session_id]
    assert session.document_id is None
    assert session.status is SessionStatus.OPEN
    assert session.created_by == actor.user_id
    assert (
        store.members[workspace_id, session.id, actor.user_id].role is SessionRole.OWNER
    )
    assert len(store.members) == 1
    assert store.documents == {}
    branch = store.branches[workspace_id, result.branch_id]
    assert branch.session_id == session.id
    assert [(t.role, t.content, t.ordinal) for t in branch.turns] == [
        ("assistant", "Public answer", 1)
    ]
    assert branch.turns[0].id != source_id
    assert branch.turns[0].workspace_id == workspace_id
    assert branch.turns[0].branch_id == branch.id
    origin = store.origins[workspace_id, session.id]
    assert origin.source_bundle_id == source_bundle_id
    assert (origin.title, origin.author_display_name, origin.published_at) == (
        "Shared title",
        "Publisher",
        NOW,
    )
    with pytest.raises(FrozenInstanceError):
        origin.author_display_name = "changed"  # type: ignore[misc]
    assert store.transactions == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["branch", "turns", "origin", "caller"])
async def test_any_failure_rolls_back_entire_fork(failure: str) -> None:
    _, actor, workspace_id, _ = setup()
    store = ForkMemory(
        fail_branch=failure == "branch",
        fail_turns=failure == "turns",
        fail_origin=failure == "origin",
    )
    with pytest.raises(RuntimeError):
        async with store.transaction() as tx:
            await CreateSessionFork(
                store, store, FixedClock()
            ).create_from_public_bundle(
                tx,
                actor=actor,
                destination_workspace_id=workspace_id,
                source_bundle_id=BundleId(uuid4()),
                attribution=ForkAttribution("Title", "Publisher", NOW),
                items=(ForkSeedItem((uuid4(),), "user", "Question"),),
            )
            raise RuntimeError("caller failed after fork")
    assert (store.sessions, store.members, store.branches, store.origins) == (
        {},
        {},
        {},
        {},
    )


@pytest.mark.asyncio
async def test_empty_public_bundle_creates_empty_branch() -> None:
    _, actor, workspace_id, _ = setup()
    store = ForkMemory()
    async with store.transaction() as tx:
        result = await CreateSessionFork(
            store, store, FixedClock()
        ).create_from_public_bundle(
            tx,
            actor=actor,
            destination_workspace_id=workspace_id,
            source_bundle_id=BundleId(uuid4()),
            attribution=ForkAttribution("Empty", "Publisher", NOW),
            items=(),
        )
    assert store.branches[workspace_id, result.branch_id].turns == ()
    assert store.origins[workspace_id, result.session_id].title == "Empty"
