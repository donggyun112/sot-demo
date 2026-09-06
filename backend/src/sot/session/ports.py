from typing import Protocol

from sot.session.domain import (
    Branch,
    Bundle,
    CurationRecord,
    Session,
    SessionMember,
    Turn,
)
from sot.shared.ids import BranchId, BundleId, SessionId, UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext


class CurationRepository(Protocol):
    async def list_curation(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
    ) -> tuple[CurationRecord, ...]:
        """Return operations in ascending ordinal order, after private authorization."""
        ...

    async def append_curation(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        record: CurationRecord,
    ) -> None: ...


class BundleRepository(Protocol):
    async def create_bundle(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        bundle: Bundle,
    ) -> None:
        """Insert immutable bundle and all items in caller transaction; never upsert."""
        ...

    async def session_for_bundle(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> SessionId | None:
        """Resolve ownership metadata only, without loading private bundle content."""
        ...

    async def load_bundle(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> Bundle | None: ...


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
