from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from sot.shared.errors import Conflict, Forbidden, InvalidInput, NotFound
from sot.shared.ids import BranchId, DocumentId, SessionId, UserId, WorkspaceId


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


@dataclass(slots=True)
class Session:
    id: SessionId
    workspace_id: WorkspaceId
    document_id: DocumentId
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
        return cls(SessionId(uuid4()), workspace_id, document_id, created_by, now)

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
