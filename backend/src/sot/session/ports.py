from typing import Protocol

from sot.session.domain import Branch, Session, SessionMember, Turn
from sot.shared.ids import BranchId, SessionId, UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext


class SessionRepository(Protocol):
    async def create_session(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session: Session
    ) -> None: ...

    async def load_session(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session_id: SessionId
    ) -> Session | None: ...

    async def save_session(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session: Session
    ) -> None: ...

    async def get_member(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        user_id: UserId,
    ) -> SessionMember | None: ...

    async def add_member(
        self, tx: TransactionContext, workspace_id: WorkspaceId, member: SessionMember
    ) -> None: ...

    async def list_members(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session_id: SessionId
    ) -> tuple[SessionMember, ...]: ...

    async def create_branch(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch: Branch
    ) -> None: ...

    async def session_for_branch(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> SessionId | None:
        """Resolve only ownership metadata; never return private branch contents."""
        ...

    async def load_branch(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> Branch | None: ...

    async def advance_version(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        *,
        expected_version: int,
    ) -> int | None:
        """Conditional update; return new version or None on mismatch in caller tx."""
        ...

    async def append_turns(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        turns: tuple[Turn, ...],
    ) -> None: ...
