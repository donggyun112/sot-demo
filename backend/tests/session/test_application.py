from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sot.document.contracts import DocumentSummary, DocumentView, RevisionView
from sot.document.domain import DocumentNotFound, RevisionId
from sot.identity.contracts import Actor
from sot.session.application import (
    AppendCompletedTurns,
    BranchAccess,
    CloseSession,
    CreateBranch,
    CreateSession,
    GetSession,
    InviteSessionMember,
    RequiredApprovers,
    SessionAccess,
    VersionGuard,
)
from sot.session.domain import (
    Branch,
    NewTurn,
    Session,
    SessionClosed,
    SessionForbidden,
    SessionMember,
    SessionMemberAlreadyExists,
    SessionNotFound,
    SessionRole,
    SessionStatus,
    Turn,
    VersionConflict,
)
from sot.shared.ids import BranchId, DocumentId, SessionId, UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.contracts import Permission, WorkspaceMembership, WorkspaceRole
from sot.workspace.domain import WorkspaceForbidden, WorkspaceNotFound, permissions_for

NOW = datetime(2026, 9, 6, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class Memory:
    sessions: dict[tuple[WorkspaceId, SessionId], Session] = field(default_factory=dict)
    members: dict[tuple[WorkspaceId, SessionId, UserId], SessionMember] = field(
        default_factory=dict
    )
    branches: dict[tuple[WorkspaceId, BranchId], Branch] = field(default_factory=dict)
    workspace_members: dict[tuple[WorkspaceId, UserId], WorkspaceMembership] = field(
        default_factory=dict
    )
    documents: dict[tuple[WorkspaceId, DocumentId], DocumentView] = field(
        default_factory=dict
    )
    active: object | None = None
    transactions: int = 0
    reads: list[str] = field(default_factory=list)
    fail_branch: bool = False
    conflict: bool = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        assert self.active is None, "nested transaction"
        self.active = object()
        self.transactions += 1
        snapshot = deepcopy((self.sessions, self.members, self.branches))
        try:
            yield self.active
        except BaseException:
            self.sessions, self.members, self.branches = snapshot
            raise
        finally:
            self.active = None

    def check(self, tx: TransactionContext) -> None:
        assert tx is self.active

    async def require_member(
        self, tx: TransactionContext, workspace_id: WorkspaceId, user_id: UserId
    ) -> WorkspaceMembership:
        self.check(tx)
        self.reads.append("workspace")
        member = self.workspace_members.get((workspace_id, user_id))
        if member is None:
            raise WorkspaceNotFound()
        return member

    async def require(
        self,
        tx: TransactionContext,
        actor: Actor,
        workspace_id: WorkspaceId,
        permission: Permission,
    ) -> WorkspaceMembership:
        member = await self.require_member(tx, workspace_id, actor.user_id)
        if permission not in permissions_for(member.role):
            raise WorkspaceForbidden()
        return member

    async def require_document(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> DocumentView:
        await self.require(tx, actor, workspace_id, Permission.DOCUMENT_READ)
        result = self.documents.get((workspace_id, document_id))
        if result is None:
            raise DocumentNotFound()
        return result

    async def create_session(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session: Session
    ) -> None:
        self.check(tx)
        assert workspace_id == session.workspace_id
        self.sessions[workspace_id, session.id] = deepcopy(session)

    async def load_session(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session_id: SessionId
    ) -> Session | None:
        self.check(tx)
        self.reads.append("session_content")
        return deepcopy(self.sessions.get((workspace_id, session_id)))

    async def save_session(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session: Session
    ) -> None:
        await self.create_session(tx, workspace_id, session)

    async def get_member(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        user_id: UserId,
    ) -> SessionMember | None:
        self.check(tx)
        self.reads.append("membership")
        return self.members.get((workspace_id, session_id, user_id))

    async def add_member(
        self, tx: TransactionContext, workspace_id: WorkspaceId, member: SessionMember
    ) -> None:
        self.check(tx)
        key = workspace_id, member.session_id, member.user_id
        if key in self.members:
            raise SessionMemberAlreadyExists()
        self.members[key] = member

    async def list_members(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session_id: SessionId
    ) -> tuple[SessionMember, ...]:
        self.check(tx)
        return tuple(
            m
            for (w, s, _), m in self.members.items()
            if (w, s) == (workspace_id, session_id)
        )

    async def create_branch(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch: Branch
    ) -> None:
        self.check(tx)
        if self.fail_branch:
            raise RuntimeError("branch write failed")
        self.branches[workspace_id, branch.id] = deepcopy(branch)

    async def session_for_branch(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> SessionId | None:
        self.check(tx)
        self.reads.append("branch_ownership")
        branch = self.branches.get((workspace_id, branch_id))
        return branch.session_id if branch else None

    async def load_branch(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> Branch | None:
        self.check(tx)
        self.reads.append("branch_content")
        return deepcopy(self.branches.get((workspace_id, branch_id)))

    async def advance_version(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        *,
        expected_version: int,
    ) -> int | None:
        self.check(tx)
        branch = self.branches.get((workspace_id, branch_id))
        if self.conflict or branch is None or branch.version != expected_version:
            return None
        branch.version += 1
        return branch.version

    async def append_turns(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        turns: tuple[Turn, ...],
    ) -> None:
        self.check(tx)
        self.branches[workspace_id, branch_id].turns += turns


def setup() -> tuple[Memory, Actor, WorkspaceId, DocumentId]:
    store, actor, workspace_id, document_id = (
        Memory(),
        Actor(UserId(uuid4())),
        WorkspaceId(uuid4()),
        DocumentId(uuid4()),
    )
    store.workspace_members[workspace_id, actor.user_id] = WorkspaceMembership(
        workspace_id, actor.user_id, WorkspaceRole.MEMBER
    )
    revision_id = RevisionId(uuid4())
    store.documents[workspace_id, document_id] = DocumentView(
        DocumentSummary(document_id, workspace_id, "Doc", revision_id, 1),
        RevisionView(
            revision_id,
            workspace_id,
            document_id,
            1,
            "main",
            None,
            actor.user_id,
            NOW,
            (),
        ),
    )
    return store, actor, workspace_id, document_id


def creator(store: Memory) -> CreateSession:
    return CreateSession(store, store, store, lambda: store, FixedClock())


def access(store: Memory) -> SessionAccess:
    return SessionAccess(store, store)


@pytest.mark.asyncio
async def test_creation_and_failed_initial_branch_are_atomic() -> None:
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    assert store.transactions == 1
    assert (
        store.members[workspace_id, result.session_id, actor.user_id].role
        is SessionRole.OWNER
    )
    assert (
        store.branches[workspace_id, result.branch_id].session_id == result.session_id
    )
    assert store.sessions[workspace_id, result.session_id].document_id == document_id
    store.fail_branch = True
    with pytest.raises(RuntimeError):
        await creator(store).execute(actor, workspace_id, document_id)
    assert len(store.sessions) == len(store.members) == len(store.branches) == 1


@pytest.mark.asyncio
async def test_creation_rejects_document_outside_workspace_and_viewer() -> None:
    store, actor, workspace_id, _ = setup()
    with pytest.raises(DocumentNotFound):
        await creator(store).execute(actor, workspace_id, DocumentId(uuid4()))
    store.workspace_members[workspace_id, actor.user_id] = WorkspaceMembership(
        workspace_id, actor.user_id, WorkspaceRole.VIEWER
    )
    with pytest.raises(WorkspaceForbidden):
        await creator(store).execute(actor, workspace_id, DocumentId(uuid4()))
    assert store.sessions == {}


@pytest.mark.asyncio
async def test_workspace_owner_without_invitation_cannot_read_private_content() -> None:
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    outsider = Actor(UserId(uuid4()))
    store.workspace_members[workspace_id, outsider.user_id] = WorkspaceMembership(
        workspace_id, outsider.user_id, WorkspaceRole.OWNER
    )
    store.reads.clear()
    with pytest.raises(SessionNotFound):
        await GetSession(access(store), lambda: store).execute(
            outsider, workspace_id, result.session_id
        )
    assert store.reads == ["workspace", "membership"]
    async with store.transaction() as tx:
        with pytest.raises(SessionNotFound):
            await BranchAccess(store, access(store), store).read(
                tx,
                actor=outsider,
                workspace_id=workspace_id,
                branch_id=result.branch_id,
            )
    assert "branch_content" not in store.reads


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_private_branch_existence_is_hidden_from_uninvited_member(
    existing: bool,
) -> None:
    store, actor, workspace_id, document_id = setup()
    created = await creator(store).execute(actor, workspace_id, document_id)
    outsider = Actor(UserId(uuid4()))
    store.workspace_members[workspace_id, outsider.user_id] = WorkspaceMembership(
        workspace_id, outsider.user_id, WorkspaceRole.OWNER
    )
    branch_id = created.branch_id if existing else BranchId(uuid4())
    store.reads.clear()

    async with store.transaction() as tx:
        with pytest.raises(SessionNotFound) as error:
            await BranchAccess(store, access(store), store).read(
                tx, actor=outsider, workspace_id=workspace_id, branch_id=branch_id
            )

    assert error.value.code == "session_not_found"
    assert store.reads == (
        ["workspace", "branch_ownership", "workspace", "membership"]
        if existing
        else ["workspace", "branch_ownership"]
    )


@pytest.mark.asyncio
async def test_invite_requires_workspace_member_and_owner_grant() -> None:
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    target = UserId(uuid4())
    invite = InviteSessionMember(store, access(store), store, lambda: store)
    with pytest.raises(WorkspaceNotFound):
        await invite.execute(
            actor,
            workspace_id,
            result.session_id,
            user_id=target,
            role=SessionRole.EDITOR,
        )
    store.workspace_members[workspace_id, target] = WorkspaceMembership(
        workspace_id, target, WorkspaceRole.MEMBER
    )
    await invite.execute(
        actor, workspace_id, result.session_id, user_id=target, role=SessionRole.EDITOR
    )
    assert (
        store.members[workspace_id, result.session_id, target].role
        is SessionRole.EDITOR
    )
    with pytest.raises(SessionForbidden):
        await invite.execute(
            Actor(target),
            workspace_id,
            result.session_id,
            user_id=actor.user_id,
            role=SessionRole.VIEWER,
        )
    with pytest.raises(SessionMemberAlreadyExists):
        await invite.execute(
            actor,
            workspace_id,
            result.session_id,
            user_id=target,
            role=SessionRole.VIEWER,
        )


@pytest.mark.asyncio
async def test_close_keeps_read_access_and_rejects_all_mutations() -> None:
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    await CloseSession(store, access(store), lambda: store).execute(
        actor, workspace_id, result.session_id
    )
    session = await GetSession(access(store), lambda: store).execute(
        actor, workspace_id, result.session_id
    )
    assert session.status is SessionStatus.CLOSED
    with pytest.raises(SessionClosed):
        await CreateBranch(store, access(store), lambda: store, FixedClock()).execute(
            actor, workspace_id, result.session_id
        )
    with pytest.raises(SessionClosed):
        await AppendCompletedTurns(
            store,
            BranchAccess(store, access(store), store),
            lambda: store,
            FixedClock(),
        ).execute(
            actor,
            workspace_id,
            result.branch_id,
            expected_version=0,
            messages=(NewTurn("user", "no"),),
        )
    async with store.transaction() as tx:
        with pytest.raises(SessionClosed):
            await VersionGuard(
                store, BranchAccess(store, access(store), store)
            ).advance(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                branch_id=result.branch_id,
                expected_version=0,
            )
    assert store.branches[workspace_id, result.branch_id].version == 0


@pytest.mark.asyncio
async def test_append_and_caller_owned_guard_use_conditional_versions() -> None:
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    branch_access = BranchAccess(store, access(store), store)
    append = AppendCompletedTurns(store, branch_access, lambda: store, FixedClock())
    added = await append.execute(
        actor,
        workspace_id,
        result.branch_id,
        expected_version=0,
        messages=(NewTurn("user", "Q"), NewTurn("assistant", "A")),
    )
    assert added.branch_version == 1
    assert [
        t.ordinal for t in store.branches[workspace_id, result.branch_id].turns
    ] == [1, 2]
    store.conflict = True
    with pytest.raises(VersionConflict):
        await append.execute(
            actor,
            workspace_id,
            result.branch_id,
            expected_version=1,
            messages=(NewTurn("tool", "lost"),),
        )
    assert len(store.branches[workspace_id, result.branch_id].turns) == 2
    store.conflict = False
    before = store.transactions
    async with store.transaction() as tx:
        version = await VersionGuard(store, branch_access).advance(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            branch_id=result.branch_id,
            expected_version=1,
        )
    assert version == 2
    assert store.transactions == before + 1


@pytest.mark.asyncio
async def test_membership_removal_and_workspace_downgrade_apply_immediately() -> None:
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    store.workspace_members[workspace_id, actor.user_id] = WorkspaceMembership(
        workspace_id, actor.user_id, WorkspaceRole.VIEWER
    )
    with pytest.raises(SessionForbidden):
        await CreateBranch(store, access(store), lambda: store, FixedClock()).execute(
            actor, workspace_id, result.session_id
        )
    del store.workspace_members[workspace_id, actor.user_id]
    store.reads.clear()
    with pytest.raises(WorkspaceNotFound):
        await GetSession(access(store), lambda: store).execute(
            actor, workspace_id, result.session_id
        )
    assert store.reads == ["workspace"]


@pytest.mark.asyncio
async def test_branch_reader_rejects_workspace_outsider_before_ownership_lookup() -> (
    None
):
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    store.workspace_members.clear()
    store.reads.clear()
    async with store.transaction() as tx:
        with pytest.raises(WorkspaceNotFound):
            await BranchAccess(store, access(store), store).read(
                tx, actor=actor, workspace_id=workspace_id, branch_id=result.branch_id
            )
    assert store.reads == ["workspace"]


@pytest.mark.asyncio
async def test_branch_creation_and_required_approvers_are_session_scoped() -> None:
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    branch = await CreateBranch(
        store, access(store), lambda: store, FixedClock()
    ).execute(actor, workspace_id, result.session_id)
    assert branch.id != result.branch_id
    assert branch.version == 0
    editor, viewer = UserId(uuid4()), UserId(uuid4())
    store.workspace_members[workspace_id, editor] = WorkspaceMembership(
        workspace_id, editor, WorkspaceRole.MEMBER
    )
    store.workspace_members[workspace_id, viewer] = WorkspaceMembership(
        workspace_id, viewer, WorkspaceRole.VIEWER
    )
    store.members[workspace_id, result.session_id, editor] = SessionMember(
        workspace_id, result.session_id, editor, SessionRole.EDITOR
    )
    store.members[workspace_id, result.session_id, viewer] = SessionMember(
        workspace_id, result.session_id, viewer, SessionRole.VIEWER
    )
    async with store.transaction() as tx:
        approvers = await RequiredApprovers(store).list_required_approvers(
            tx, workspace_id=workspace_id, session_id=result.session_id
        )
        context = await BranchAccess(store, access(store), store).read(
            tx, actor=actor, workspace_id=workspace_id, branch_id=branch.id
        )
    assert approvers == {actor.user_id, editor}
    assert context.document_id == document_id
    assert context.turns == ()
