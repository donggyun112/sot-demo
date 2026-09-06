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
    GetWorkspace,
    ListActorWorkspaces,
)
from sot.workspace.domain import Workspace, WorkspaceMembership, WorkspaceRole


class CreateWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class AddWorkspaceMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    role: WorkspaceRole


def build_workspace_router(
    create: CreateWorkspace,
    add_member: AddWorkspaceMember,
    list_workspaces: ListActorWorkspaces,
    get_workspace: GetWorkspace,
    actor: Callable[[Request], Awaitable[Actor]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces")

    @router.get("")
    async def list_for_actor(
        current: Annotated[Actor, Depends(actor)],
    ) -> tuple[Workspace, ...]:
        return await list_workspaces.execute(current)

    @router.post("", status_code=201)
    async def create_workspace(
        body: CreateWorkspaceRequest, current: Annotated[Actor, Depends(actor)]
    ) -> Workspace:
        return await create.execute(current, name=body.name)

    @router.get("/{workspace_id}")
    async def get(
        workspace_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> Workspace:
        return await get_workspace.execute(current, WorkspaceId(workspace_id))

    @router.post("/{workspace_id}/members", status_code=201)
    async def add(
        workspace_id: UUID,
        body: AddWorkspaceMemberRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> WorkspaceMembership:
        return await add_member.execute(
            current,
            WorkspaceId(workspace_id),
            user_id=UserId(body.user_id),
            role=body.role,
        )

    return router
