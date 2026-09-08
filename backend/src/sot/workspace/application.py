from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from sot.identity.contracts import (
    Actor,
    IdentityAttributionReader,
    IdentityDirectory,
    IdentityReader,
)
from sot.shared.clock import Clock
from sot.shared.errors import Conflict
from sot.shared.ids import UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext, UnitOfWorkFactory
from sot.workspace.contracts import WorkspaceAuthorizer, WorkspaceMemberReader
from sot.workspace.domain import (
    Invitation,
    InvitationNotFound,
    InvitationStatus,
    Permission,
    Workspace,
    WorkspaceForbidden,
    WorkspaceMembership,
    WorkspaceNotFound,
    WorkspaceRole,
    normalize_email,
    permissions_for,
)
from sot.workspace.ports import (
    InvitationDelivery,
    InvitationRepository,
    WorkspaceRepository,
)


class WorkspaceAccess:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    async def require_member(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership:
        member = await self._repository.get_member(tx, workspace_id, user_id)
        if member is None:
            raise WorkspaceForbidden()
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


class CreateWorkspace:
    def __init__(
        self, repository: WorkspaceRepository, uow_factory: UnitOfWorkFactory
    ) -> None:
        self._repository, self._uow_factory = repository, uow_factory

    async def execute(self, actor: Actor, *, name: str) -> Workspace:
        workspace = Workspace(WorkspaceId(uuid4()), name.strip())
        async with self._uow_factory().transaction() as tx:
            await self._repository.create(tx, workspace)
            await self._repository.add_member(
                tx,
                WorkspaceMembership(workspace.id, actor.user_id, WorkspaceRole.OWNER),
            )
        return workspace


class AddWorkspaceMember:
    def __init__(
        self,
        repository: WorkspaceRepository,
        authorizer: WorkspaceAuthorizer,
        identity: IdentityReader,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository, self._authorizer = repository, authorizer
        self._identity, self._uow_factory = identity, uow_factory

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        *,
        user_id: UserId,
        role: WorkspaceRole,
    ) -> WorkspaceMembership:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.WORKSPACE_MANAGE
            )
            await self._identity.require_actor(tx, user_id)
            member = WorkspaceMembership(workspace_id, user_id, role)
            await self._repository.add_member(tx, member)
        return member


class ListActorWorkspaces:
    def __init__(
        self, repository: WorkspaceRepository, uow_factory: UnitOfWorkFactory
    ) -> None:
        self._repository, self._uow_factory = repository, uow_factory

    async def execute(self, actor: Actor) -> tuple[Workspace, ...]:
        async with self._uow_factory().transaction() as tx:
            return await self._repository.list_for_user(tx, actor.user_id)


class GetCurrentWorkspaceMember:
    def __init__(
        self, members: WorkspaceMemberReader, uow_factory: UnitOfWorkFactory
    ) -> None:
        self._members, self._uow_factory = members, uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId
    ) -> WorkspaceMembership:
        async with self._uow_factory().transaction() as tx:
            return await self._members.require_member(tx, workspace_id, actor.user_id)


@dataclass(frozen=True, slots=True)
class WorkspaceMemberProfile:
    """Membership plus the display name, so the UI never has to show a raw id."""

    membership: WorkspaceMembership
    display_name: str


class ListWorkspaceMembers:
    def __init__(
        self,
        repository: WorkspaceRepository,
        members: WorkspaceMemberReader,
        attribution: IdentityAttributionReader,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository, self._members = repository, members
        self._attribution, self._uow_factory = attribution, uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId
    ) -> tuple[WorkspaceMemberProfile, ...]:
        async with self._uow_factory().transaction() as tx:
            # Membership alone is the gate: everyone in a workspace may see who
            # else is in it. Only the display name is exposed, never the profile.
            await self._members.require_member(tx, workspace_id, actor.user_id)
            memberships = await self._repository.list_members(tx, workspace_id)
            # ponytail: one attribution read per member, fine at workspace size;
            # batch the lookup if a workspace ever gets large enough to notice.
            profiles = []
            for membership in memberships:
                attribution = await self._attribution.require_attribution(
                    tx, membership.user_id
                )
                profiles.append(
                    WorkspaceMemberProfile(membership, attribution.display_name)
                )
            return tuple(profiles)


class GetWorkspace:
    def __init__(
        self,
        repository: WorkspaceRepository,
        authorizer: WorkspaceAuthorizer,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository, self._authorizer = repository, authorizer
        self._uow_factory = uow_factory

    async def execute(self, actor: Actor, workspace_id: WorkspaceId) -> Workspace:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.DOCUMENT_READ
            )
            workspace = await self._repository.get(tx, workspace_id)
            if workspace is None:
                raise WorkspaceNotFound()
            return workspace


@dataclass(frozen=True, slots=True)
class IssuedInvitation:
    """A new invitation, plus whether the inviter has to deliver it by hand."""

    invitation: Invitation
    hand_over_code: bool


@dataclass(frozen=True, slots=True)
class InvitationView:
    """What either side of an invitation is allowed to read about it."""

    invitation: Invitation
    workspace_name: str
    inviter_display_name: str


class InviteToWorkspace:
    """Offer membership by email. Nothing is granted until it is accepted."""

    def __init__(
        self,
        invitations: InvitationRepository,
        workspaces: WorkspaceRepository,
        authorizer: WorkspaceAuthorizer,
        directory: IdentityDirectory,
        delivery: InvitationDelivery,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._invitations, self._workspaces = invitations, workspaces
        self._authorizer, self._directory = authorizer, directory
        self._delivery = delivery
        self._uow_factory, self._clock = uow_factory, clock

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        *,
        email: str,
        role: WorkspaceRole,
    ) -> IssuedInvitation:
        now = self._clock.now()
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.WORKSPACE_MANAGE
            )
            # Reject an invalid address before anything touches storage.
            invitee = await self._directory.find_by_email(tx, normalize_email(email))
            invitation = Invitation.create(
                workspace_id=workspace_id,
                inviter_id=actor.user_id,
                invitee_email=email,
                role=role,
                now=now,
                invitee_user_id=invitee,
            )
            if invitee is not None:
                existing = await self._workspaces.get_member(tx, workspace_id, invitee)
                if existing is not None:
                    raise Conflict(
                        "workspace_member_exists", "Already a member of this workspace"
                    )
            # One live invitation per address. A past-due row is settled first,
            # because the unique index cannot look at the clock itself.
            pending = await self._invitations.find_pending(
                tx, workspace_id, invitation.invitee_email
            )
            if pending is not None:
                if pending.status_at(now) is InvitationStatus.PENDING:
                    raise Conflict(
                        "invitation_pending", "This address already has an invitation"
                    )
                await self._invitations.save(tx, pending.expire(now))
            await self._invitations.add(tx, invitation)
            workspace = await self._workspaces.get(tx, workspace_id)
            # Inside the transaction: an invitation that could not be delivered
            # is not one that was sent.
            await self._delivery.deliver(
                invitation, workspace.name if workspace else ""
            )
            return IssuedInvitation(invitation, self._delivery.hands_back_code)


class ListWorkspaceInvitations:
    def __init__(
        self,
        invitations: InvitationRepository,
        authorizer: WorkspaceAuthorizer,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._invitations, self._authorizer = invitations, authorizer
        self._uow_factory, self._clock = uow_factory, clock

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId
    ) -> tuple[Invitation, ...]:
        now = self._clock.now()
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.WORKSPACE_MANAGE
            )
            return tuple(
                item
                for item in await self._invitations.list_pending_for_workspace(
                    tx, workspace_id
                )
                if item.status_at(now) is InvitationStatus.PENDING
            )


class RevokeInvitation:
    def __init__(
        self,
        invitations: InvitationRepository,
        authorizer: WorkspaceAuthorizer,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._invitations, self._authorizer = invitations, authorizer
        self._uow_factory, self._clock = uow_factory, clock

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, invitation_id: UUID
    ) -> None:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.WORKSPACE_MANAGE
            )
            invitation = await self._invitations.find(tx, invitation_id)
            # A workspace never learns about another workspace's invitations.
            if invitation is None or invitation.workspace_id != workspace_id:
                raise InvitationNotFound()
            await self._invitations.save(tx, invitation.revoke(self._clock.now()))


class ListMyInvitations:
    """What is waiting on me, across every workspace."""

    def __init__(
        self,
        invitations: InvitationRepository,
        workspaces: WorkspaceRepository,
        attribution: IdentityAttributionReader,
        directory: IdentityDirectory,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._invitations, self._workspaces = invitations, workspaces
        self._attribution, self._directory = attribution, directory
        self._uow_factory, self._clock = uow_factory, clock

    async def execute(self, actor: Actor) -> tuple[InvitationView, ...]:
        now = self._clock.now()
        async with self._uow_factory().transaction() as tx:
            email = await self._directory.require_email(tx, actor.user_id)
            views = []
            for item in await self._invitations.list_pending_for_invitee(
                tx, actor.user_id, email
            ):
                if item.status_at(now) is not InvitationStatus.PENDING:
                    continue
                workspace = await self._workspaces.get(tx, item.workspace_id)
                if workspace is None:
                    continue
                inviter = await self._attribution.require_attribution(
                    tx, item.inviter_id
                )
                views.append(
                    InvitationView(item, workspace.name, inviter.display_name)
                )
            return tuple(views)


class AcceptInvitation:
    """Accepting is what creates the membership, in one transaction."""

    def __init__(
        self,
        invitations: InvitationRepository,
        workspaces: WorkspaceRepository,
        directory: IdentityDirectory,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._invitations, self._workspaces = invitations, workspaces
        self._directory = directory
        self._uow_factory, self._clock = uow_factory, clock

    async def execute(
        self, actor: Actor, invitation_id: UUID
    ) -> WorkspaceMembership:
        now = self._clock.now()
        async with self._uow_factory().transaction() as tx:
            invitation = await self._bind(tx, invitation_id, actor)
            accepted = invitation.accept(actor.user_id, now)
            await self._invitations.save(tx, accepted)
            member = accepted.membership()
            await self._workspaces.add_member(tx, member)
            return member

    async def redeem(self, actor: Actor, code: str) -> WorkspaceMembership:
        """Join with the code, for an invitation that reached you by hand."""
        now = self._clock.now()
        async with self._uow_factory().transaction() as tx:
            invitation = await self._invitations.find_by_code(tx, code.strip().upper())
            if invitation is None:
                raise InvitationNotFound()
            accepted = invitation.redeem(actor.user_id, code, now)
            await self._invitations.save(tx, accepted)
            member = accepted.membership()
            await self._workspaces.add_member(tx, member)
            return member

    async def decline(self, actor: Actor, invitation_id: UUID) -> None:
        now = self._clock.now()
        async with self._uow_factory().transaction() as tx:
            invitation = await self._bind(tx, invitation_id, actor)
            await self._invitations.save(tx, invitation.decline(actor.user_id, now))

    async def _bind(
        self, tx: TransactionContext, invitation_id: UUID, actor: Actor
    ) -> Invitation:
        invitation = await self._invitations.find(tx, invitation_id)
        if invitation is None:
            raise InvitationNotFound()
        # An invitation sent before the invitee had an account binds to them
        # here, on the address it was addressed to.
        if invitation.invitee_user_id is None:
            email = await self._directory.require_email(tx, actor.user_id)
            if invitation.invitee_email != email:
                raise InvitationNotFound()
            return replace(invitation, invitee_user_id=actor.user_id)
        return invitation
