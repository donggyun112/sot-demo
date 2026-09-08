from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from sot.identity.contracts import Actor, IdentityAttribution
from sot.shared.errors import Conflict
from sot.shared.ids import UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.application import (
    AddWorkspaceMember,
    CreateWorkspace,
    GetWorkspace,
    ListActorWorkspaces,
    ListWorkspaceMembers,
    WorkspaceAccess,
)
from sot.workspace.domain import (
    Invitation,
    InvitationStatus,
    Permission,
    Workspace,
    WorkspaceForbidden,
    WorkspaceMemberAlreadyExists,
    WorkspaceMembership,
    WorkspaceRole,
)

NOW = datetime(2026, 9, 6, tzinfo=UTC)


@dataclass
class MemoryStore:
    workspaces: dict[WorkspaceId, Workspace] = field(default_factory=dict)
    members: dict[tuple[WorkspaceId, UserId], WorkspaceMembership] = field(
        default_factory=dict
    )
    active: object | None = None
    transactions: int = 0
    fail_member: bool = False
    display_names: dict[UserId, str] = field(default_factory=dict)
    emails: dict[UserId, str] = field(default_factory=dict)
    invitations: dict[UUID, Invitation] = field(default_factory=dict)
    now_value: datetime = NOW

    def check(self, tx: TransactionContext) -> None:
        assert self.active is tx

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        assert self.active is None, "nested transaction"
        before = (
            self.workspaces.copy(),
            self.members.copy(),
            self.invitations.copy(),
        )
        self.active = object()
        self.transactions += 1
        try:
            yield self.active
        except BaseException:
            self.workspaces, self.members, self.invitations = before
            raise
        finally:
            self.active = None

    async def create(self, tx: TransactionContext, workspace: Workspace) -> None:
        self.check(tx)
        self.workspaces[workspace.id] = workspace

    async def add_member(
        self, tx: TransactionContext, member: WorkspaceMembership
    ) -> None:
        self.check(tx)
        if self.fail_member:
            raise RuntimeError("membership insert failed")
        key = member.workspace_id, member.user_id
        if key in self.members:
            raise WorkspaceMemberAlreadyExists()
        self.members[key] = member

    async def get(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> Workspace | None:
        self.check(tx)
        return self.workspaces.get(workspace_id)

    async def get_member(
        self, tx: TransactionContext, workspace_id: WorkspaceId, user_id: UserId
    ) -> WorkspaceMembership | None:
        self.check(tx)
        return self.members.get((workspace_id, user_id))

    async def list_for_user(
        self, tx: TransactionContext, user_id: UserId
    ) -> tuple[Workspace, ...]:
        self.check(tx)
        return tuple(
            w for w in self.workspaces.values() if (w.id, user_id) in self.members
        )

    async def list_members(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> tuple[WorkspaceMembership, ...]:
        self.check(tx)
        return tuple(
            member
            for (member_workspace, _), member in self.members.items()
            if member_workspace == workspace_id
        )

    async def require_actor(self, tx: TransactionContext, user_id: UserId) -> Actor:
        self.check(tx)
        return Actor(user_id)

    def now(self) -> datetime:
        return self.now_value

    async def find_by_email(
        self, tx: TransactionContext, email: str
    ) -> UserId | None:
        self.check(tx)
        return next((u for u, e in self.emails.items() if e == email), None)

    async def require_email(self, tx: TransactionContext, user_id: UserId) -> str:
        self.check(tx)
        return self.emails[user_id]

    async def add(self, tx: TransactionContext, invitation: Invitation) -> None:
        self.check(tx)
        live = self.invitations.values()
        if any(
            item.workspace_id == invitation.workspace_id
            and item.invitee_email == invitation.invitee_email
            and item.status is InvitationStatus.PENDING
            for item in live
        ):
            raise Conflict("invitation_pending", "Already invited")
        self.invitations[invitation.id] = invitation

    async def save(self, tx: TransactionContext, invitation: Invitation) -> None:
        self.check(tx)
        held = self.invitations.get(invitation.id)
        # The real update only writes over a still-pending row.
        if held is None or held.status is InvitationStatus.PENDING:
            self.invitations[invitation.id] = invitation

    async def find(
        self, tx: TransactionContext, invitation_id: UUID
    ) -> Invitation | None:
        self.check(tx)
        return self.invitations.get(invitation_id)

    async def find_pending(
        self, tx: TransactionContext, workspace_id: WorkspaceId, email: str
    ) -> Invitation | None:
        self.check(tx)
        return next(
            (
                item
                for item in self.invitations.values()
                if item.workspace_id == workspace_id
                and item.invitee_email == email
                and item.status is InvitationStatus.PENDING
            ),
            None,
        )

    async def find_by_code(
        self, tx: TransactionContext, code: str
    ) -> Invitation | None:
        self.check(tx)
        return next(
            (
                item
                for item in self.invitations.values()
                if item.code == code and item.status is InvitationStatus.PENDING
            ),
            None,
        )

    async def list_pending_for_workspace(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> tuple[Invitation, ...]:
        self.check(tx)
        return tuple(
            item
            for item in self.invitations.values()
            if item.workspace_id == workspace_id
            and item.status is InvitationStatus.PENDING
        )

    async def list_pending_for_invitee(
        self, tx: TransactionContext, user_id: UserId, email: str
    ) -> tuple[Invitation, ...]:
        self.check(tx)
        return tuple(
            item
            for item in self.invitations.values()
            if item.status is InvitationStatus.PENDING
            and (item.invitee_user_id == user_id or item.invitee_email == email)
        )

    async def require_attribution(
        self, tx: TransactionContext, user_id: UserId
    ) -> IdentityAttribution:
        self.check(tx)
        return IdentityAttribution(self.display_names.get(user_id, "Unnamed"))


@pytest.mark.asyncio
async def test_members_are_listed_with_names_to_members_only() -> None:
    store = MemoryStore()
    owner, viewer, outsider = (Actor(UserId(uuid4())) for _ in range(3))
    store.display_names = {owner.user_id: "Alice", viewer.user_id: "Bob"}
    workspace = await CreateWorkspace(store, lambda: store).execute(owner, name="Team")
    access = WorkspaceAccess(store)
    await AddWorkspaceMember(store, access, store, lambda: store).execute(
        owner, workspace.id, user_id=viewer.user_id, role=WorkspaceRole.VIEWER
    )
    listing = ListWorkspaceMembers(store, access, store, lambda: store)
    # A viewer sees the roster too: names are what replace raw ids in the UI.
    assert {
        (profile.display_name, profile.membership.role)
        for profile in await listing.execute(viewer, workspace.id)
    } == {("Alice", WorkspaceRole.OWNER), ("Bob", WorkspaceRole.VIEWER)}
    with pytest.raises(WorkspaceForbidden):
        await listing.execute(outsider, workspace.id)


@pytest.mark.asyncio
async def test_create_workspace_atomically_inserts_owner_and_lists_only_memberships() -> (
    None
):
    store = MemoryStore()
    owner, outsider = Actor(UserId(uuid4())), Actor(UserId(uuid4()))
    workspace = await CreateWorkspace(store, lambda: store).execute(
        owner, name="Research"
    )
    assert store.transactions == 1
    assert store.members[workspace.id, owner.user_id].role is WorkspaceRole.OWNER
    assert await ListActorWorkspaces(store, lambda: store).execute(owner) == (
        workspace,
    )
    assert await ListActorWorkspaces(store, lambda: store).execute(outsider) == ()
    access = WorkspaceAccess(store)
    assert (
        await GetWorkspace(store, access, lambda: store).execute(owner, workspace.id)
        == workspace
    )
    with pytest.raises(WorkspaceForbidden):
        await GetWorkspace(store, access, lambda: store).execute(outsider, workspace.id)


@pytest.mark.asyncio
async def test_membership_failure_rolls_back_workspace_creation() -> None:
    store = MemoryStore(fail_member=True)
    with pytest.raises(RuntimeError, match="membership insert"):
        await CreateWorkspace(store, lambda: store).execute(
            Actor(UserId(uuid4())), name="Research"
        )
    assert not store.workspaces


@pytest.mark.asyncio
async def test_authorizer_requires_membership_in_routed_workspace() -> None:
    store = MemoryStore()
    actor = Actor(UserId(uuid4()))
    workspace = await CreateWorkspace(store, lambda: store).execute(
        actor, name="Research"
    )
    access = WorkspaceAccess(store)
    async with store.transaction() as tx:
        assert (
            await access.require(tx, actor, workspace.id, Permission.SESSION_CREATE)
        ).role is WorkspaceRole.OWNER
        with pytest.raises(WorkspaceForbidden):
            await access.require(
                tx, actor, WorkspaceId(uuid4()), Permission.SESSION_CREATE
            )
        with pytest.raises(WorkspaceForbidden):
            await access.require_member(tx, workspace.id, UserId(uuid4()))


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [WorkspaceRole.MEMBER, WorkspaceRole.VIEWER])
async def test_only_owner_can_add_members_and_duplicates_cannot_change_roles(
    role: WorkspaceRole,
) -> None:
    store = MemoryStore()
    owner, member, target = (Actor(UserId(uuid4())) for _ in range(3))
    workspace = await CreateWorkspace(store, lambda: store).execute(
        owner, name="Research"
    )
    access = WorkspaceAccess(store)
    add = AddWorkspaceMember(store, access, store, lambda: store)
    result = await add.execute(owner, workspace.id, user_id=member.user_id, role=role)
    assert result.role is role
    assert store.transactions == 2
    with pytest.raises(WorkspaceForbidden):
        await add.execute(
            member, workspace.id, user_id=target.user_id, role=WorkspaceRole.OWNER
        )
    with pytest.raises(WorkspaceMemberAlreadyExists):
        await add.execute(
            owner, workspace.id, user_id=member.user_id, role=WorkspaceRole.OWNER
        )
    assert store.members[workspace.id, member.user_id].role is role
    async with store.transaction() as tx:
        with pytest.raises(WorkspaceForbidden):
            await access.require(tx, member, workspace.id, Permission.DOCUMENT_CREATE)
