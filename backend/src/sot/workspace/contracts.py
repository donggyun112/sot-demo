from typing import Protocol

from sot.identity.contracts import Actor
from sot.shared.ids import UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.domain import Permission, WorkspaceMembership, WorkspaceRole


class WorkspaceAuthorizer(Protocol):
    async def require(
        self,
        tx: TransactionContext,
        actor: Actor,
        workspace_id: WorkspaceId,
        permission: Permission,
    ) -> WorkspaceMembership: ...


class WorkspaceMemberReader(Protocol):
    async def require_member(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership: ...


__all__ = [
    "Permission",
    "WorkspaceAuthorizer",
    "WorkspaceMemberReader",
    "WorkspaceMembership",
    "WorkspaceRole",
]
