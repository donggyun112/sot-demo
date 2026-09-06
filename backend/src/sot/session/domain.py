from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from sot.shared.errors import Conflict, Forbidden, InvalidInput, NotFound
from sot.shared.ids import (
    BranchId,
    BundleId,
    DocumentId,
    SessionId,
    UserId,
    WorkspaceId,
)


class SessionRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class SessionPermission(StrEnum):
    READ = "session.read"
    EDIT = "session.edit"
    MANAGE_MEMBERS = "session.manage_members"
    PUBLISH_BUNDLE = "session.publish_bundle"
    CREATE_TOSS = "session.create_toss"
    REVOKE_TOSS = "session.revoke_toss"
    CREATE_PROPOSAL = "session.create_proposal"


def is_allowed(
    workspace_role: str, session_role: SessionRole | None, permission: SessionPermission
) -> bool:
    if workspace_role not in {"owner", "member", "viewer"} or session_role is None:
        return False
    if permission is SessionPermission.READ:
        return True
    if workspace_role == "viewer":
        return False
    if session_role is SessionRole.OWNER:
        return True
    return session_role is SessionRole.EDITOR and permission in {
        SessionPermission.EDIT,
        SessionPermission.CREATE_PROPOSAL,
    }


class SessionNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("session_not_found", "Session not found")


class BranchNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("branch_not_found", "Branch not found")


class SessionForbidden(Forbidden):
    def __init__(self) -> None:
        super().__init__("session_forbidden", "Session access denied")


class SessionClosed(Conflict):
    def __init__(self) -> None:
        super().__init__("session_closed", "Session is closed")


class SessionMemberAlreadyExists(Conflict):
    def __init__(self) -> None:
        super().__init__("session_member_exists", "Session member already exists")


class VersionConflict(Conflict):
    def __init__(self) -> None:
        super().__init__("version_conflict", "The resource changed after it was loaded")


class SessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class SessionMember:
    workspace_id: WorkspaceId
    session_id: SessionId
    user_id: UserId
    role: SessionRole


@dataclass(frozen=True, slots=True)
class ForkOrigin:
    """Copied public attribution; the source bundle ID is opaque, never a FK."""

    workspace_id: WorkspaceId
    session_id: SessionId
    source_bundle_id: BundleId
    title: str
    author_display_name: str
    published_at: datetime


@dataclass(slots=True)
class Session:
    id: SessionId
    workspace_id: WorkspaceId
    document_id: DocumentId | None
    created_by: UserId
    created_at: datetime
    status: SessionStatus = SessionStatus.OPEN

    @classmethod
    def create(
        cls,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        created_by: UserId,
        now: datetime,
    ) -> Session:
        if document_id is None:
            raise InvalidInput("session_document_required", "A document is required")
        return cls(SessionId(uuid4()), workspace_id, document_id, created_by, now)

    @classmethod
    def create_detached_fork(
        cls, workspace_id: WorkspaceId, created_by: UserId, now: datetime
    ) -> Session:
        """Create a public-bundle fork without any source/destination document link."""
        return cls(SessionId(uuid4()), workspace_id, None, created_by, now)

    def require_open(self) -> None:
        if self.status is not SessionStatus.OPEN:
            raise SessionClosed()

    def close(self) -> None:
        self.require_open()
        self.status = SessionStatus.CLOSED


TurnRole = Literal["user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class NewTurn:
    role: TurnRole
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant", "tool"}:
            raise InvalidInput("turn_role_invalid", "Turn role is invalid")


@dataclass(frozen=True, slots=True)
class Turn:
    id: UUID
    workspace_id: WorkspaceId
    branch_id: BranchId
    ordinal: int
    role: TurnRole
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CompletedTurnsResult:
    turns: tuple[Turn, ...]
    branch_version: int


@dataclass(slots=True)
class Branch:
    id: BranchId
    workspace_id: WorkspaceId
    session_id: SessionId
    created_by: UserId
    created_at: datetime
    version: int = 0
    turns: tuple[Turn, ...] = ()

    @classmethod
    def create(
        cls,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        created_by: UserId,
        now: datetime,
    ) -> Branch:
        return cls(BranchId(uuid4()), workspace_id, session_id, created_by, now)

    def append_completed(
        self, *, expected_version: int, messages: tuple[NewTurn, ...], now: datetime
    ) -> CompletedTurnsResult:
        if expected_version != self.version:
            raise VersionConflict()
        if not messages:
            raise InvalidInput("turns_empty", "Completed turns cannot be empty")
        turns = tuple(
            Turn(
                uuid4(),
                self.workspace_id,
                self.id,
                len(self.turns) + offset,
                message.role,
                message.content,
                now,
            )
            for offset, message in enumerate(messages, 1)
        )
        self.turns += turns
        self.version += 1
        return CompletedTurnsResult(turns, self.version)


@dataclass(frozen=True, slots=True)
class DropTurn:
    turn_id: UUID


@dataclass(frozen=True, slots=True)
class EditTurn:
    turn_id: UUID
    content: str


@dataclass(frozen=True, slots=True)
class JoinTurns:
    turn_ids: tuple[UUID, ...]
    content: str


CurationOperation = DropTurn | EditTurn | JoinTurns


@dataclass(frozen=True, slots=True)
class BundleItem:
    source_ids: tuple[UUID, ...]
    role: Literal["user", "assistant"]
    content: str
    provenance: Literal["copied", "edited"]


@dataclass(slots=True)
class CurationProjection:
    items: tuple[BundleItem, ...]

    @classmethod
    def from_turns(cls, turns: tuple[Turn, ...]) -> CurationProjection:
        # Tool payloads are private execution data, not public conversation items.
        return cls(
            tuple(
                BundleItem((turn.id,), turn.role, turn.content, "copied")
                for turn in turns
                if turn.role in {"user", "assistant"}
            )
        )

    def apply(self, operation: CurationOperation) -> None:
        ids = (
            operation.turn_ids
            if isinstance(operation, JoinTurns)
            else (operation.turn_id,)
        )
        if not ids or len(ids) != len(set(ids)):
            raise InvalidInput(
                "curation_selection_invalid", "Select distinct source turns"
            )
        positions = [
            i
            for i, item in enumerate(self.items)
            if set(ids).intersection(item.source_ids)
        ]
        available = {source for i in positions for source in self.items[i].source_ids}
        if not set(ids).issubset(available):
            raise InvalidInput(
                "curation_turn_not_found", "Selected turn is not in the projection"
            )
        if isinstance(operation, JoinTurns) and set(ids) != available:
            raise InvalidInput(
                "curation_selection_partial", "Select every source of a joined item"
            )
        if isinstance(operation, DropTurn):
            self.items = tuple(
                item for i, item in enumerate(self.items) if i not in positions
            )
            return
        source_ids = (
            ids
            if isinstance(operation, JoinTurns)
            else self.items[positions[0]].source_ids
        )
        replacement = BundleItem(
            source_ids, self.items[positions[0]].role, operation.content, "edited"
        )
        self.items = tuple(
            replacement if i == positions[0] else item
            for i, item in enumerate(self.items)
            if i == positions[0] or i not in positions
        )


@dataclass(frozen=True, slots=True)
class CurationRecord:
    id: UUID
    branch_id: BranchId
    ordinal: int
    operation: CurationOperation
    created_by: UserId
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Bundle:
    id: BundleId
    workspace_id: WorkspaceId
    session_id: SessionId
    branch_id: BranchId
    title: str
    items: tuple[BundleItem, ...]
    published_by: UserId
    published_at: datetime

    @classmethod
    def publish(
        cls,
        branch: Branch,
        items: tuple[BundleItem, ...],
        user_id: UserId,
        now: datetime,
        *,
        title: str,
    ) -> Bundle:
        return cls(
            BundleId(uuid4()),
            branch.workspace_id,
            branch.session_id,
            branch.id,
            title,
            tuple(items),
            user_id,
            now,
        )
