from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints

from sot.identity.contracts import Actor
from sot.shared.ids import UserId, WorkspaceId
from sot.workspace.application import (
    AcceptInvitation,
    AddWorkspaceMember,
    CreateWorkspace,
    GetCurrentWorkspaceMember,
    GetWorkspace,
    InvitationView,
    InviteToWorkspace,
    ListActorWorkspaces,
    ListMyInvitations,
    ListWorkspaceInvitations,
    ListWorkspaceMembers,
    RevokeInvitation,
    WorkspaceMemberProfile,
)
from sot.workspace.domain import (
    Invitation,
    Permission,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
    permissions_for,
)


class CreateWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class AddWorkspaceMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    role: WorkspaceRole


class InviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)
    ]
    # Ownership is not transferable by invitation, so it is not offered here.
    role: Literal[WorkspaceRole.MEMBER, WorkspaceRole.VIEWER] = WorkspaceRole.MEMBER


class InvitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    invitee_email: str
    role: WorkspaceRole
    created_at: datetime
    expires_at: datetime
    # Present only where nothing delivers the invitation, so the inviter can
    # pass it on themselves. Never on a listing: a code is a credential, and
    # one that has already been sent should not be sitting on a screen.
    code: str | None = None

    @classmethod
    def from_invitation(
        cls, value: Invitation, *, code: str | None = None
    ) -> "InvitationResponse":
        return cls(
            id=value.id,
            workspace_id=value.workspace_id,
            invitee_email=value.invitee_email,
            role=value.role,
            created_at=value.created_at,
            expires_at=value.expires_at,
            code=code,
        )


class RedeemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=10, max_length=10)
    ]


class MyInvitationResponse(BaseModel):
    """What an invitee sees: who is asking, and to join what."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    workspace_name: str
    inviter_display_name: str
    role: WorkspaceRole
    created_at: datetime
    expires_at: datetime

    @classmethod
    def from_view(cls, value: InvitationView) -> "MyInvitationResponse":
        return cls(
            id=value.invitation.id,
            workspace_id=value.invitation.workspace_id,
            workspace_name=value.workspace_name,
            inviter_display_name=value.inviter_display_name,
            role=value.invitation.role,
            created_at=value.invitation.created_at,
            expires_at=value.invitation.expires_at,
        )


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str

    @classmethod
    def from_workspace(cls, workspace: Workspace) -> "WorkspaceResponse":
        return cls(id=workspace.id, name=workspace.name)


class WorkspaceMemberResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole

    @classmethod
    def from_membership(cls, member: WorkspaceMembership) -> "WorkspaceMemberResponse":
        return cls(
            workspace_id=member.workspace_id, user_id=member.user_id, role=member.role
        )


class CurrentWorkspaceMemberResponse(WorkspaceMemberResponse):
    permissions: tuple[Permission, ...]


class WorkspaceMemberProfileResponse(WorkspaceMemberResponse):
    display_name: str

    @classmethod
    def from_profile(
        cls, profile: WorkspaceMemberProfile
    ) -> "WorkspaceMemberProfileResponse":
        return cls(
            workspace_id=profile.membership.workspace_id,
            user_id=profile.membership.user_id,
            role=profile.membership.role,
            display_name=profile.display_name,
        )


def build_workspace_router(
    create: CreateWorkspace,
    add_member: AddWorkspaceMember,
    invite: InviteToWorkspace,
    list_invitations: ListWorkspaceInvitations,
    revoke_invitation: RevokeInvitation,
    list_my_invitations: ListMyInvitations,
    decide_invitation: AcceptInvitation,
    list_workspaces: ListActorWorkspaces,
    get_workspace: GetWorkspace,
    get_member: GetCurrentWorkspaceMember,
    list_members: ListWorkspaceMembers,
    actor: Callable[[Request], Awaitable[Actor]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces")

    @router.get("/{workspace_id}/members", operation_id="list_workspace_members")
    async def members(
        workspace_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> tuple[WorkspaceMemberProfileResponse, ...]:
        return tuple(
            WorkspaceMemberProfileResponse.from_profile(profile)
            for profile in await list_members.execute(
                current, WorkspaceId(workspace_id)
            )
        )

    @router.get(
        "/{workspace_id}/members/me", operation_id="get_current_workspace_member"
    )
    async def current_member(
        workspace_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> CurrentWorkspaceMemberResponse:
        member = await get_member.execute(current, WorkspaceId(workspace_id))
        return CurrentWorkspaceMemberResponse(
            workspace_id=member.workspace_id,
            user_id=member.user_id,
            role=member.role,
            permissions=tuple(sorted(permissions_for(member.role))),
        )

    @router.get("")
    async def list_for_actor(
        current: Annotated[Actor, Depends(actor)],
    ) -> tuple[WorkspaceResponse, ...]:
        return tuple(
            WorkspaceResponse.from_workspace(workspace)
            for workspace in await list_workspaces.execute(current)
        )

    @router.post("", status_code=201)
    async def create_workspace(
        body: CreateWorkspaceRequest, current: Annotated[Actor, Depends(actor)]
    ) -> WorkspaceResponse:
        return WorkspaceResponse.from_workspace(
            await create.execute(current, name=body.name)
        )

    @router.get("/{workspace_id}")
    async def get(
        workspace_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> WorkspaceResponse:
        return WorkspaceResponse.from_workspace(
            await get_workspace.execute(current, WorkspaceId(workspace_id))
        )

    @router.post("/{workspace_id}/members", status_code=201)
    async def add(
        workspace_id: UUID,
        body: AddWorkspaceMemberRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> WorkspaceMemberResponse:
        return WorkspaceMemberResponse.from_membership(
            await add_member.execute(
                current,
                WorkspaceId(workspace_id),
                user_id=UserId(body.user_id),
                role=body.role,
            )
        )

    @router.get("/{workspace_id}/invitations", operation_id="list_invitations")
    async def invitations(
        workspace_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> tuple[InvitationResponse, ...]:
        return tuple(
            InvitationResponse.from_invitation(item)
            for item in await list_invitations.execute(
                current, WorkspaceId(workspace_id)
            )
        )

    @router.post("/{workspace_id}/invitations", status_code=201)
    async def send_invitation(
        workspace_id: UUID,
        body: InviteRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> InvitationResponse:
        issued = await invite.execute(
            current,
            WorkspaceId(workspace_id),
            email=body.email,
            role=WorkspaceRole(body.role),
        )
        return InvitationResponse.from_invitation(
            issued.invitation,
            code=issued.invitation.code if issued.hand_over_code else None,
        )

    @router.delete(
        "/{workspace_id}/invitations/{invitation_id}",
        status_code=204,
        operation_id="revoke_invitation",
    )
    async def revoke(
        workspace_id: UUID,
        invitation_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> Response:
        await revoke_invitation.execute(
            current, WorkspaceId(workspace_id), invitation_id
        )
        return Response(status_code=204)

    return router


def build_invitation_router(
    list_mine: ListMyInvitations,
    decide: AcceptInvitation,
    actor: Callable[[Request], Awaitable[Actor]],
) -> APIRouter:
    """An invitee's own view: not scoped to a workspace they are not in yet."""
    router = APIRouter(prefix="/api/v1/invitations")

    @router.get("", operation_id="list_my_invitations")
    async def mine(
        current: Annotated[Actor, Depends(actor)],
    ) -> tuple[MyInvitationResponse, ...]:
        return tuple(
            MyInvitationResponse.from_view(item)
            for item in await list_mine.execute(current)
        )

    @router.post("/{invitation_id}/accept", status_code=201)
    async def accept(
        invitation_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> WorkspaceMemberResponse:
        return WorkspaceMemberResponse.from_membership(
            await decide.execute(current, invitation_id)
        )

    @router.post("/redeem", status_code=201)
    async def redeem(
        body: RedeemRequest, current: Annotated[Actor, Depends(actor)]
    ) -> WorkspaceMemberResponse:
        return WorkspaceMemberResponse.from_membership(
            await decide.redeem(current, body.code)
        )

    @router.post("/{invitation_id}/decline", status_code=204)
    async def decline(
        invitation_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> Response:
        await decide.decline(current, invitation_id)
        return Response(status_code=204)

    return router
