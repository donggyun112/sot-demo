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


@dataclass(frozen=True, slots=True)
class CitedConversation:
    """The frozen conversation a document passage was written out of.

    A citation on its own is an ordinal — it says a passage stands on the
    second item of some bundle, which tells a reader nothing. This is what
    the reader actually needs: what was said, and which session to open to
    keep reading it.
    """

    bundle_id: BundleId
    title: str
    session_id: SessionId
    items: tuple[BundleItem, ...]


class BundleReader(Protocol):
    async def require_snapshot(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> BundleSnapshot: ...


class CitedConversationReader(BundleReader, Protocol):
    """Reads the frozen turns AND names the session they came from."""

    async def require_owning_session(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> SessionId: ...


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


@dataclass(frozen=True, slots=True)
class FrozenEvidence:
    """The conversation an update was written from, frozen at that moment."""

    bundle_id: BundleId
    items: tuple[BundleItem, ...]


class EvidenceFreezer(Protocol):
    """Freeze a branch's curated conversation as the grounds for an update.

    The grounds for an edit are the conversation that produced it, so they are
    captured when the edit is proposed rather than asked for as a separate
    chore. Runs inside the caller's transaction: an update that cannot record
    what it was written from is not an update that happened.
    """

    async def freeze(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        title: str,
    ) -> FrozenEvidence: ...


@dataclass(frozen=True, slots=True)
class ToolRecord:
    """What a tool turn recorded: the call, or its return.

    The whole of it. A transcript that shows an update happened but not what
    it was made with is not a record anyone can audit — and the arguments and
    the result were already streamed to whoever watched the run, so hiding
    them afterwards only made the same session read differently on reload.

    It stays inside the session: curation keeps every tool turn out of
    bundles, so none of this reaches shared evidence.
    """

    kind: str
    name: str
    call_id: str
    payload: object | None = None


class ToolRecordReader(Protocol):
    """Read the tool envelope a turn carries, for a transcript to show."""

    def record(self, content: str) -> ToolRecord | None: ...


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
class TranscriptTurn:
    """A turn as a reader sees it: a tool turn keeps its whole record."""

    turn: Turn
    tool: ToolRecord | None = None


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
    # Set when this session was forked out of a conversation someone else's
    # session was holding, so a reader can follow it back.
    forked_from_session_id: SessionId | None = None
    forked_from_branch_id: BranchId | None = None


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
    "EvidenceFreezer",
    "FrozenEvidence",
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
