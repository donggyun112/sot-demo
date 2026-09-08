from typing import Protocol
from uuid import UUID

from sot.shared.ids import UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.domain import (
    Invitation,
    Workspace,
    WorkspaceMembership,
)


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


class InvitationRepository(Protocol):
    async def add(self, tx: TransactionContext, invitation: Invitation) -> None: ...
    async def save(self, tx: TransactionContext, invitation: Invitation) -> None: ...
    async def find(
        self, tx: TransactionContext, invitation_id: UUID
    ) -> Invitation | None: ...
    async def find_pending(
        self, tx: TransactionContext, workspace_id: WorkspaceId, email: str
    ) -> Invitation | None: ...
    async def list_pending_for_workspace(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> tuple[Invitation, ...]: ...
    async def list_pending_for_invitee(
        self, tx: TransactionContext, user_id: UserId, email: str
    ) -> tuple[Invitation, ...]: ...


class InvitationDelivery(Protocol):
    """How an invitation reaches someone who is not in the product yet.

    An invitation names a person by an address, so something has to carry it
    there. Whether that happened decides what the inviter is shown: a code to
    pass along by hand, or nothing left to do.
    """

    @property
    def hands_back_code(self) -> bool:
        """True when the inviter has to deliver the code themselves."""
        ...

    async def deliver(self, invitation: Invitation, workspace_name: str) -> None: ...
