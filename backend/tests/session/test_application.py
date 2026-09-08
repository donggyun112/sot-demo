from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError, dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sot.document.contracts import DocumentSummary, DocumentView, RevisionView
from sot.document.domain import DocumentNotFound, RevisionId
from sot.identity.contracts import Actor
from sot.session import contracts
from sot.session.application import (
    AppendCompletedTurns,
    AttachToBranch,
    BranchAccess,
    CloseSession,
    CreateBranch,
    CreateSession,
    ForkSession,
    GetSession,
    InviteSessionMember,
    RequiredApprovers,
    SessionAccess,
    VersionGuard,
)
from sot.session.domain import (
    Attachment,
    Branch,
    NewTurn,
    Session,
    SessionClosed,
    SessionForbidden,
    SessionMember,
    SessionMemberAlreadyExists,
    SessionNotFound,
    SessionOrigin,
    SessionPermission,
    SessionRole,
    SessionStatus,
    Turn,
    VersionConflict,
)
from sot.shared.errors import InvalidInput
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
async def test_authorized_session_is_an_immutable_view_without_transitions() -> None:
    store, actor, workspace_id, document_id = setup()
    created = await creator(store).execute(actor, workspace_id, document_id)
    authorizer: contracts.SessionAuthorizer = access(store)
    async with store.transaction() as tx:
        view = await authorizer.require(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session_id=created.session_id,
            permission=SessionPermission.READ,
        )

    with pytest.raises(FrozenInstanceError):
        view.status = SessionStatus.CLOSED  # type: ignore[misc]
    assert not hasattr(view, "close")
    assert not isinstance(view, Session)
    assert (
        view.id,
        view.workspace_id,
        view.document_id,
        view.created_by,
        view.created_at,
        view.status,
    ) == (
        created.session_id,
        workspace_id,
        document_id,
        actor.user_id,
        NOW,
        SessionStatus.OPEN,
    )
    await CloseSession(store, authorizer, lambda: store).execute(
        actor, workspace_id, created.session_id
    )
    closed = await GetSession(authorizer, lambda: store).execute(
        actor, workspace_id, created.session_id
    )
    assert closed.status is SessionStatus.CLOSED
    assert view.status is SessionStatus.OPEN


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
async def test_sending_a_session_to_yourself_is_refused() -> None:
    """You already hold what you are sending: this is a mistake, not an action."""
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    before = dict(store.members)
    with pytest.raises(InvalidInput) as caught:
        await InviteSessionMember(store, access(store), store, lambda: store).execute(
            actor,
            workspace_id,
            result.session_id,
            user_id=actor.user_id,
            role=SessionRole.EDITOR,
        )
    assert caught.value.code == "session_member_self"
    assert store.members == before


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
async def test_files_picked_together_attach_together_in_order() -> None:
    """Someone picks three files and then sends. They land as three turns in
    the order they were picked, under one version check: a partial attach
    would leave the sender undoing turns nobody asked for."""
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    branch_access = BranchAccess(store, access(store), store)
    attach = AttachToBranch(
        AppendCompletedTurns(store, branch_access, lambda: store, FixedClock())
    )

    added = await attach.execute(
        actor,
        workspace_id,
        result.branch_id,
        expected_version=0,
        attachments=(
            Attachment("a.md", "first"),
            Attachment("b.md", "second"),
        ),
    )

    assert [(turn.role, turn.content) for turn in added.turns] == [
        ("attachment", "a.md\n\nfirst"),
        ("attachment", "b.md\n\nsecond"),
    ]
    assert added.branch_version == 1


@pytest.mark.asyncio
async def test_append_and_caller_owned_guard_use_conditional_versions() -> None:
    store, actor, workspace_id, document_id = setup()
    result = await creator(store).execute(actor, workspace_id, document_id)
    branch_access = BranchAccess(store, access(store), store)
    append: contracts.CompletedTurnsAppender = AppendCompletedTurns(
        store, branch_access, lambda: store, FixedClock()
    )
    added = await append.execute(
        actor,
        workspace_id,
        result.branch_id,
        expected_version=0,
        messages=(
            NewTurn("user", "Q"),
            NewTurn("tool", "completed tool result"),
            NewTurn("assistant", "A"),
        ),
    )
    assert added.branch_version == 1
    assert [
        t.ordinal for t in store.branches[workspace_id, result.branch_id].turns
    ] == [1, 2, 3]
    assert [(turn.role, turn.content) for turn in added.turns] == [
        ("user", "Q"),
        ("tool", "completed tool result"),
        ("assistant", "A"),
    ]
    store.conflict = True
    with pytest.raises(VersionConflict):
        await append.execute(
            actor,
            workspace_id,
            result.branch_id,
            expected_version=1,
            messages=(NewTurn("tool", "lost"),),
        )
    assert store.branches[workspace_id, result.branch_id].turns == added.turns
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


def forker(store: Memory) -> ForkSession:
    return ForkSession(
        store,
        store,
        BranchAccess(store, access(store), store),
        lambda: store,
        FixedClock(),
    )


async def conversation(
    store: Memory, actor: Actor, workspace_id: WorkspaceId, document_id: DocumentId
) -> contracts.CreatedSessionResult:
    created = await creator(store).execute(actor, workspace_id, document_id)
    await AppendCompletedTurns(
        store, BranchAccess(store, access(store), store), lambda: store, FixedClock()
    ).execute(
        actor,
        workspace_id,
        created.branch_id,
        expected_version=0,
        messages=(NewTurn("user", "why five?"), NewTurn("assistant", "because ten")),
    )
    return created


@pytest.mark.asyncio
async def test_a_reader_forks_the_conversation_into_a_session_they_own() -> None:
    """A session sent read-only is a dead end until you can take it somewhere."""
    store, owner, workspace_id, document_id = setup()
    source = await conversation(store, owner, workspace_id, document_id)
    reader = Actor(UserId(uuid4()))
    store.workspace_members[workspace_id, reader.user_id] = WorkspaceMembership(
        workspace_id, reader.user_id, WorkspaceRole.MEMBER
    )
    async with store.transaction() as tx:
        await store.add_member(
            tx,
            workspace_id,
            SessionMember(
                workspace_id, source.session_id, reader.user_id, SessionRole.VIEWER
            ),
        )

    forked = await forker(store).execute(
        reader, workspace_id, source.session_id, branch_id=source.branch_id
    )

    assert forked.session_id != source.session_id
    session = store.sessions[workspace_id, forked.session_id]
    assert session.created_by == reader.user_id
    assert session.document_id == document_id
    assert session.origin == SessionOrigin(source.session_id, source.branch_id)
    # The forker owns their copy: reading someone else's is what they had.
    assert (
        store.members[workspace_id, forked.session_id, reader.user_id].role
        is SessionRole.OWNER
    )
    # The transcript comes across word for word, in order, with new identity.
    original = store.branches[workspace_id, source.branch_id]
    copy = store.branches[workspace_id, forked.branch_id]
    assert [(t.ordinal, t.role, t.content) for t in copy.turns] == [
        (t.ordinal, t.role, t.content) for t in original.turns
    ]
    assert {t.id for t in copy.turns}.isdisjoint({t.id for t in original.turns})
    assert all(turn.branch_id == forked.branch_id for turn in copy.turns)
    # Nothing the forker does lands in the session they read.
    assert original.session_id == source.session_id
    assert len(store.branches[workspace_id, source.branch_id].turns) == 2


@pytest.mark.asyncio
async def test_forking_a_session_you_cannot_read_finds_nothing() -> None:
    store, owner, workspace_id, document_id = setup()
    source = await conversation(store, owner, workspace_id, document_id)
    stranger = Actor(UserId(uuid4()))
    store.workspace_members[workspace_id, stranger.user_id] = WorkspaceMembership(
        workspace_id, stranger.user_id, WorkspaceRole.MEMBER
    )

    with pytest.raises(SessionNotFound):
        await forker(store).execute(
            stranger, workspace_id, source.session_id, branch_id=source.branch_id
        )

    assert len(store.sessions) == 1


@pytest.mark.asyncio
async def test_a_workspace_viewer_may_not_fork_because_they_may_not_start_one() -> None:
    store, owner, workspace_id, document_id = setup()
    source = await conversation(store, owner, workspace_id, document_id)
    viewer = Actor(UserId(uuid4()))
    store.workspace_members[workspace_id, viewer.user_id] = WorkspaceMembership(
        workspace_id, viewer.user_id, WorkspaceRole.VIEWER
    )
    async with store.transaction() as tx:
        await store.add_member(
            tx,
            workspace_id,
            SessionMember(
                workspace_id, source.session_id, viewer.user_id, SessionRole.VIEWER
            ),
        )

    with pytest.raises(WorkspaceForbidden):
        await forker(store).execute(
            viewer, workspace_id, source.session_id, branch_id=source.branch_id
        )


@pytest.mark.asyncio
async def test_forking_names_the_session_the_branch_actually_belongs_to() -> None:
    store, actor, workspace_id, document_id = setup()
    source = await conversation(store, actor, workspace_id, document_id)
    other = await conversation(store, actor, workspace_id, document_id)

    with pytest.raises(SessionNotFound):
        await forker(store).execute(
            actor, workspace_id, other.session_id, branch_id=source.branch_id
        )


@pytest.mark.asyncio
async def test_a_turn_records_who_said_it_not_who_owns_the_branch() -> None:
    """Two people in one session: the transcript has to tell them apart, or
    every reader's own name goes on everyone else's words."""
    store, owner, workspace_id, document_id = setup()
    created = await creator(store).execute(owner, workspace_id, document_id)
    guest = Actor(UserId(uuid4()))
    store.workspace_members[workspace_id, guest.user_id] = WorkspaceMembership(
        workspace_id, guest.user_id, WorkspaceRole.MEMBER
    )
    async with store.transaction() as tx:
        await store.add_member(
            tx,
            workspace_id,
            SessionMember(
                workspace_id, created.session_id, guest.user_id, SessionRole.EDITOR
            ),
        )
    append = AppendCompletedTurns(
        store, BranchAccess(store, access(store), store), lambda: store, FixedClock()
    )
    await append.execute(
        owner,
        workspace_id,
        created.branch_id,
        expected_version=0,
        messages=(NewTurn("user", "mine"),),
    )
    await append.execute(
        guest,
        workspace_id,
        created.branch_id,
        expected_version=1,
        messages=(NewTurn("user", "theirs"), NewTurn("assistant", "answered")),
    )

    turns = store.branches[workspace_id, created.branch_id].turns
    assert [(turn.content, turn.created_by) for turn in turns] == [
        ("mine", owner.user_id),
        ("theirs", guest.user_id),
        # The agent answered inside the guest's run, so it is theirs to own.
        ("answered", guest.user_id),
    ]


@pytest.mark.asyncio
async def test_a_fork_keeps_the_words_with_the_person_who_said_them() -> None:
    store, owner, workspace_id, document_id = setup()
    source = await conversation(store, owner, workspace_id, document_id)
    reader = Actor(UserId(uuid4()))
    store.workspace_members[workspace_id, reader.user_id] = WorkspaceMembership(
        workspace_id, reader.user_id, WorkspaceRole.MEMBER
    )
    async with store.transaction() as tx:
        await store.add_member(
            tx,
            workspace_id,
            SessionMember(
                workspace_id, source.session_id, reader.user_id, SessionRole.VIEWER
            ),
        )

    forked = await forker(store).execute(
        reader, workspace_id, source.session_id, branch_id=source.branch_id
    )

    # Copying a conversation does not make the copier its author.
    copy = store.branches[workspace_id, forked.branch_id]
    assert {turn.created_by for turn in copy.turns} == {owner.user_id}
