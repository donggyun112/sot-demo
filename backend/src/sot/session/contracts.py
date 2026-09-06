from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
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
from sot.shared.errors import InvalidInput
from sot.shared.ids import (
    BranchId,
    BundleId,
    DocumentId,
    SessionId,
    UserId,
    WorkspaceId,
)
from sot.shared.unit_of_work import TransactionContext


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
    """Authorize publishing on the bundle's actual owning session, then snapshot."""

    async def require_shareable_snapshot(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> ShareableBundleSnapshot: ...


class CiteCreator(Protocol):
    async def create_from_agent(
        self,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_branch_version: int,
        turn_ids: tuple[UUID, ...],
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


@dataclass(frozen=True, slots=True)
class ForkSeedItem:
    source_ids: tuple[UUID, ...]
    role: Literal["user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant"}:
            raise InvalidInput("fork_seed_role_invalid", "Fork seed role is invalid")


@dataclass(frozen=True, slots=True)
class ForkAttribution:
    title: str
    author_display_name: str
    published_at: datetime


@dataclass(frozen=True, slots=True)
class ForkedSessionResult:
    session_id: SessionId
    branch_id: BranchId


class SessionForkWriter(Protocol):
    """Create a detached Session via Session.create_detached_fork and seed its branch.

    document_id stays None. Never create a destination document automatically or
    retain a source document link; source_bundle_id is opaque provenance only.
    """

    async def create_from_public_bundle(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        destination_workspace_id: WorkspaceId,
        source_bundle_id: BundleId,
        attribution: ForkAttribution,
        items: tuple[ForkSeedItem, ...],
    ) -> ForkedSessionResult: ...


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
    "BundleReader",
    "BundleSnapshot",
    "CiteCreator",
    "CompletedTurnsAppender",
    "CompletedTurnsResult",
    "CreatedSessionResult",
    "ForkAttribution",
    "ForkSeedItem",
    "ForkedSessionResult",
    "NewTurn",
    "SessionApproverReader",
    "SessionAuthorizer",
    "SessionForkWriter",
    "SessionMember",
    "SessionPermission",
    "SessionRole",
    "SessionStatus",
    "SessionView",
    "ShareableBundleReader",
    "ShareableBundleSnapshot",
    "Turn",
]
