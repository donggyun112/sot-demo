from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sot.identity.contracts import Actor
from sot.session.domain import (
    BundleItem,
    CompletedTurnsResult,
    NewTurn,
    SessionMember,
    SessionPermission,
    SessionRole,
    SessionStatus,
    Turn,
)
from sot.shared.ids import (
    BranchId,
    BundleId,
    DocumentId,
    SessionId,
    UserId,
    WorkspaceId,
)
from sot.shared.unit_of_work import TransactionContext

type TurnId = UUID


@dataclass(frozen=True, slots=True)
class CreatedSessionResult:
    session_id: SessionId
    branch_id: BranchId


@dataclass(frozen=True, slots=True)
class BranchMutationResult:
    resource_id: UUID
    branch_version: int


@dataclass(frozen=True, slots=True)
class BundleSnapshot:
    bundle_id: BundleId
    title: str
    items: tuple[BundleItem, ...]
    published_at: datetime


class BundleReader(Protocol):
    async def require_snapshot(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> BundleSnapshot: ...


@dataclass(frozen=True, slots=True)
class ShareableBundleSnapshot:
    """Internal capability result; published_by must never enter public DTOs."""

    snapshot: BundleSnapshot
    published_by: UserId


class ShareableBundleReader(Protocol):
    """Authorize publishing on the bundle's actual open owning session, then snapshot."""

    async def require_shareable_snapshot(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> ShareableBundleSnapshot: ...


class ToolRecordReader(Protocol):
    """Name the tool a turn records, for a transcript someone can audit.

    Only a CALL is nameable. A tool's return is execution data the caller
    never wrote and must not read back, so it has no name here and is left
    out of the transcript entirely.
    """

    def call_name(self, content: str) -> str | None: ...


class BundleOwningSessionReader(Protocol):
    """Which session a bundle was published from, for someone allowed to read it.

    Sharing never leaves the workspace, so a share link resolves to the session
    it curated rather than to a copy of it. Callers who may not read that
    session get the module's own not-found or forbidden.
    """

    async def require_owning_session(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> SessionId: ...


class BundleRevocationAuthorizer(Protocol):
    """Authorize the actual bundle owner to revoke a link, including closed sessions."""

    async def require_revocation(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> None:
        """Check workspace and owning-session owner permission; return no private state."""
        ...


class CiteCreator(Protocol):
    async def create_from_agent(
        self,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_branch_version: int,
        turn_ids: tuple[TurnId, ...],
        summary: str,
    ) -> BranchMutationResult: ...


@dataclass(frozen=True, slots=True)
class BranchContext:
    workspace_id: WorkspaceId
    session_id: SessionId
    document_id: DocumentId | None
    branch_id: BranchId
    version: int
    turns: tuple[Turn, ...]


@dataclass(frozen=True, slots=True)
class SessionView:
    id: SessionId
    workspace_id: WorkspaceId
    document_id: DocumentId | None
    created_by: UserId
    created_at: datetime
    status: SessionStatus


class SessionAuthorizer(Protocol):
    async def require(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        permission: SessionPermission,
    ) -> SessionView: ...


class CompletedTurnsAppender(Protocol):
    """Commit completed messages and the expected-version advance atomically."""

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        *,
        expected_version: int,
        messages: tuple[NewTurn, ...],
    ) -> CompletedTurnsResult: ...


class BranchContextReader(Protocol):
    async def read(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        permission: SessionPermission = SessionPermission.READ,
    ) -> BranchContext: ...


class BranchVersionGuard(Protocol):
    async def advance(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_version: int,
    ) -> int: ...


class SessionApproverReader(Protocol):
    """Internal capability; caller must authorize source session before reading."""

    async def list_required_approvers(
        self,
        tx: TransactionContext,
        *,
        workspace_id: WorkspaceId,
        session_id: SessionId,
    ) -> frozenset[UserId]: ...


__all__ = [
    "BranchContext",
    "BranchContextReader",
    "BranchMutationResult",
    "BranchVersionGuard",
    "BundleItem",
    "BundleOwningSessionReader",
    "BundleReader",
    "BundleRevocationAuthorizer",
    "BundleSnapshot",
    "CiteCreator",
    "CompletedTurnsAppender",
    "CompletedTurnsResult",
    "CreatedSessionResult",
    "NewTurn",
    "SessionApproverReader",
    "SessionAuthorizer",
    "SessionMember",
    "SessionPermission",
    "SessionRole",
    "SessionStatus",
    "SessionView",
    "ShareableBundleReader",
    "ShareableBundleSnapshot",
    "ToolRecordReader",
    "Turn",
    "TurnId",
]
