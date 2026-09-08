from typing import Protocol

from sot.shared.ids import UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.domain import Workspace, WorkspaceMembership


class WorkspaceRepository(Protocol):
    async def create(self, tx: TransactionContext, workspace: Workspace) -> None: ...
    async def get(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> Workspace | None: ...
    async def add_member(
        self, tx: TransactionContext, member: WorkspaceMembership
    ) -> None: ...
    async def get_member(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None: ...
    async def list_for_user(
        self, tx: TransactionContext, user_id: UserId
    ) -> tuple[Workspace, ...]: ...
    async def list_members(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> tuple[WorkspaceMembership, ...]: ...
