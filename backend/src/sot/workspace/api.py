from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from sot.identity.contracts import Actor
from sot.shared.ids import UserId, WorkspaceId
from sot.workspace.application import (
    AddWorkspaceMember,
    CreateWorkspace,
    GetCurrentWorkspaceMember,
    GetWorkspace,
    ListActorWorkspaces,
    ListWorkspaceMembers,
    WorkspaceMemberProfile,
)
from sot.workspace.domain import (
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
            for profile in await list_members.execute(current, WorkspaceId(workspace_id))
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

    return router
