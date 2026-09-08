from __future__ import annotations

from dataclasses import dataclass, replace
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
class SessionOrigin:
    """The conversation a session was forked from, at the branch it read."""

    session_id: SessionId
    branch_id: BranchId


@dataclass(slots=True)
class Session:
    id: SessionId
    workspace_id: WorkspaceId
    document_id: DocumentId | None
    created_by: UserId
    created_at: datetime
    status: SessionStatus = SessionStatus.OPEN
    origin: SessionOrigin | None = None

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
    def fork(
        cls,
        source: Session,
        branch_id: BranchId,
        created_by: UserId,
        now: datetime,
    ) -> Session:
        """Start a session of your own from a conversation you can read.

        Being sent a session read-only leaves you following an argument with
        nowhere to take it. A fork is where you take it: the same document,
        the transcript as it stands, and a record of where it came from.
        """
        source.require_open()
        if source.document_id is None:
            raise InvalidInput("session_document_required", "A document is required")
        return cls(
            SessionId(uuid4()),
            source.workspace_id,
            source.document_id,
            created_by,
            now,
            origin=SessionOrigin(source.id, branch_id),
        )

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

    @classmethod
    def copy_of(
        cls,
        source: Branch,
        session_id: SessionId,
        created_by: UserId,
        now: datetime,
    ) -> Branch:
        """The same conversation, in a branch the copier owns.

        Turns keep the words, the order and the moment they were said: a fork
        is a copy of a record, not a re-enactment of it. Only their identity
        is new, because they now belong to a different branch.
        """
        branch_id = BranchId(uuid4())
        return cls(
            branch_id,
            source.workspace_id,
            session_id,
            created_by,
            now,
            source.version,
            tuple(
                replace(turn, id=uuid4(), branch_id=branch_id) for turn in source.turns
            ),
        )

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


@dataclass(frozen=True, slots=True)
class RestoreTurn:
    """Undo a drop.

    The op log is append-only, so a dropped turn cannot come back by removing
    the drop. This op puts the turn's ORIGINAL content back — never content
    the caller supplies — at the position it held in the conversation.
    """

    turn_id: UUID


CurationOperation = DropTurn | EditTurn | JoinTurns | RestoreTurn


@dataclass(frozen=True, slots=True)
class BundleItem:
    source_ids: tuple[UUID, ...]
    role: Literal["user", "assistant"]
    content: str
    provenance: Literal["copied", "edited"]


@dataclass(slots=True)
class CurationProjection:
    items: tuple[BundleItem, ...]
    # The untouched conversation, kept so a drop can be undone with the turn's
    # own content and its own position rather than anything a caller sends.
    origin: tuple[BundleItem, ...] = ()

    @classmethod
    def from_turns(cls, turns: tuple[Turn, ...]) -> CurationProjection:
        # Tool payloads are private execution data, not public conversation items.
        items = tuple(
            BundleItem((turn.id,), turn.role, turn.content, "copied")
            for turn in turns
            if turn.role in {"user", "assistant"}
        )
        return cls(items, items)

    def _origin_rank(self, item: BundleItem) -> int:
        """Where an item belongs in the conversation, by its earliest source."""
        order = {
            source: i for i, one in enumerate(self.origin) for source in one.source_ids
        }
        return min(
            (order[source] for source in item.source_ids if source in order), default=0
        )

    def _restore(self, turn_id: UUID) -> None:
        if any(turn_id in item.source_ids for item in self.items):
            raise InvalidInput(
                "curation_turn_present", "This turn is already in the bundle"
            )
        original = next(
            (item for item in self.origin if turn_id in item.source_ids), None
        )
        if original is None:
            raise InvalidInput(
                "curation_turn_not_found", "Selected turn is not in the projection"
            )
        rank = self._origin_rank(original)
        at = next(
            (i for i, item in enumerate(self.items) if self._origin_rank(item) > rank),
            len(self.items),
        )
        self.items = self.items[:at] + (original,) + self.items[at:]

    def apply(self, operation: CurationOperation) -> None:
        if isinstance(operation, RestoreTurn):
            self._restore(operation.turn_id)
            return
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
