from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal, get_args
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
    # The file a conversation was imported from. Present only for an import,
    # and it is the whole claim being made: SOT did not run this exchange,
    # somebody brought it. A reader has to be able to tell those apart.
    imported_from: str | None = None

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
    def imported(
        cls,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        created_by: UserId,
        now: datetime,
        *,
        filename: str,
    ) -> Session:
        """A conversation that happened somewhere else, brought in whole.

        The reasoning behind a decision is usually already had, in whatever
        tool it was had in, and retyping it to get it in front of the agent
        is how it gets lost. So it is imported — and marked, because SOT did
        not run it: the record says whose file it came from, not that this
        exchange was witnessed here.
        """
        name = filename.strip()
        if not name or "/" in name or "\\" in name:
            raise InvalidInput("attachment_name_invalid", "File name is invalid")
        session = cls.create(workspace_id, document_id, created_by, now)
        session.imported_from = name
        return session

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


# A conversation is read by people and re-read by the agent every run, so a
# file brought into one is bounded. Well past a long design document, and far
# short of anything that would make the session unreadable.
ATTACHMENT_LIMIT = 100_000


@dataclass(frozen=True, slots=True)
class Attachment:
    """A file someone brought into the conversation.

    It becomes a turn rather than a thing beside the conversation: what a
    person puts in front of the agent IS something they said, so it belongs
    in the transcript, in the agent's history, and in the evidence a passage
    written from it cites. Nothing else already does all four.
    """

    filename: str
    content: str

    def __post_init__(self) -> None:
        if not self.filename.strip() or "/" in self.filename or "\\" in self.filename:
            raise InvalidInput("attachment_name_invalid", "File name is invalid")
        if not self.content.strip():
            raise InvalidInput("attachment_empty", "File is empty")
        if len(self.content) > ATTACHMENT_LIMIT:
            raise InvalidInput(
                "attachment_too_long",
                f"File is {len(self.content)} characters; keep it within "
                f"{ATTACHMENT_LIMIT} so the conversation stays readable",
            )

    def as_turn(self) -> NewTurn:
        """Named, then quoted verbatim, under a role of its own.

        The model reads the name and the whole body — that is the point of
        bringing a file — while a reader of the transcript sees a file rather
        than the hundred lines inside it. Only the role can tell them apart:
        the same text typed by hand is a message, not an attachment.
        """
        return NewTurn("attachment", f"{self.filename.strip()}\n\n{self.content}")


TurnRole = Literal["user", "assistant", "tool", "attachment"]
TURN_ROLES = frozenset(get_args(TurnRole))


@dataclass(frozen=True, slots=True)
class NewTurn:
    role: TurnRole
    content: str

    def __post_init__(self) -> None:
        if self.role not in TURN_ROLES:
            raise InvalidInput("turn_role_invalid", "Turn role is invalid")


# A copied conversation is words, and words are small. An export carries
# what its agent did as well — every file it read, every command it ran — and
# a real session's record runs to megabytes. Both are bounded, at the size
# each actually is, and an import over the line is refused rather than
# quietly shortened.
TRANSCRIPT_LIMIT = 400_000
EXPORT_LIMIT = 20_000_000

# The line that says who speaks next, in the forms the tools actually emit:
# a heading, a bold label, or a bare label.
_USER_LABELS = frozenset(
    {"user", "you", "you said", "human", "me", "prompt", "질문", "사용자", "나", "유저"}
)
_ASSISTANT_LABELS = frozenset(
    {
        "assistant",
        "ai",
        "bot",
        "chatgpt",
        "chatgpt said",
        "claude",
        "gpt",
        "model",
        "response",
        "답변",
        "어시스턴트",
        "응답",
    }
)
_EMPHASIS = re.compile(r"\*\*|__|\*|`")


def _speaker(line: str) -> str | None:
    """Whose turn this line announces, or None if it announces nothing.

    The label is the whole line, however it was dressed: `## User`,
    `**Assistant:**`, `You said:`. Anything longer than a label is somebody
    talking, which is why the length is capped before the lookup.
    """
    label = line.strip().lstrip("#").strip()
    label = _EMPHASIS.sub("", label).strip().removesuffix(":").strip()
    if not label or len(label) > 32:
        return None
    folded = label.casefold()
    if folded in _USER_LABELS:
        return "user"
    if folded in _ASSISTANT_LABELS:
        return "assistant"
    return None


@dataclass(frozen=True, slots=True)
class ExportedTool:
    """What an agent called somewhere else, and what came back.

    A conversation with an agent in it is mostly what the agent did, and an
    import that keeps only the words keeps the story without the evidence:
    the reader can no longer see which file was read or what a command
    returned. So a call and its result come across whole. Writing them as
    turns needs the envelope the transcript reads back, which belongs to the
    agent module, so this carries the pieces and the caller borrows the pen.
    """

    name: str
    call_id: str
    args: dict[str, object]
    result: object = None
    # A call that was interrupted has no result. Keeping the call anyway is
    # the point: it says the agent tried.
    answered: bool = False


ExportedEntry = NewTurn | ExportedTool


def read_session_export(content: str) -> tuple[ExportedEntry, ...]:
    """A conversation exported as structured turns, tool records included.

    The shape is the one an export can actually be mapped onto without
    guessing: an ordered list of turns, each either something said or one
    tool call with its result. Anything a caller sends that is not one of
    those is refused rather than half-read.
    """
    try:
        document = json.loads(content)
    except ValueError:
        raise InvalidInput("transcript_invalid", "The file is not a conversation")
    if not isinstance(document, dict) or not isinstance(
        document.get("turns"), list
    ):
        raise InvalidInput("transcript_invalid", "The file is not a conversation")
    entries: list[ExportedEntry] = []
    for turn in document["turns"]:
        if not isinstance(turn, dict):
            raise InvalidInput("transcript_invalid", "A turn is not a turn")
        role = turn.get("role")
        if role == "tool":
            name, call_id = turn.get("name"), turn.get("call_id")
            args = turn.get("args")
            if not isinstance(name, str) or not name.strip():
                raise InvalidInput("transcript_invalid", "A tool record has no name")
            if not isinstance(call_id, str) or not call_id.strip():
                raise InvalidInput("transcript_invalid", "A tool record has no call")
            entries.append(
                ExportedTool(
                    name,
                    call_id,
                    args if isinstance(args, dict) else {},
                    turn.get("result"),
                    "result" in turn,
                )
            )
            continue
        if role not in {"user", "assistant"}:
            raise InvalidInput("transcript_invalid", "A turn has no speaker")
        said = turn.get("content")
        if not isinstance(said, str) or not said.strip():
            continue
        entries.append(NewTurn(role, said))
    return tuple(entries)


def looks_like_export(content: str) -> bool:
    """Whether this file is structured turns rather than a copied transcript."""
    return content.lstrip().startswith("{")


def read_transcript(content: str) -> tuple[NewTurn, ...]:
    """The conversation in a file someone copied out of another tool.

    Nothing about such a file is structured, so this recognises the handful of
    ways those tools mark who is speaking and refuses to guess past that: a
    file with no marker it knows is one thing the importer said, whole. Better
    a conversation with one long turn than one invented out of paragraph
    breaks.

    Text before the first speaker line belongs to whoever spoke first — an
    export that opens with a title and then "You said:" must not lose the
    title, and one that opens mid-sentence is that person talking.
    """
    turns: list[NewTurn] = []
    role: str | None = None
    said: list[str] = []

    def close() -> None:
        text = "\n".join(said).strip()
        said.clear()
        if text:
            turns.append(NewTurn(role or "user", text))

    for line in content.splitlines():
        next_role = _speaker(line)
        if next_role is None:
            said.append(line)
            continue
        if role is None:
            # Whatever stood above the first speaker is that speaker's: an
            # export opens with the conversation's own title, and a title is
            # not a turn somebody took.
            role = next_role
            continue
        close()
        role = next_role
    close()
    return tuple(turns)


@dataclass(frozen=True, slots=True)
class Turn:
    id: UUID
    workspace_id: WorkspaceId
    branch_id: BranchId
    ordinal: int
    role: TurnRole
    content: str
    created_at: datetime
    # Who was at the keyboard. An assistant or tool turn belongs to the person
    # whose run produced it, which is who a reader would hold to it.
    created_by: UserId


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
        self,
        *,
        author: UserId,
        expected_version: int,
        messages: tuple[NewTurn, ...],
        now: datetime,
    ) -> CompletedTurnsResult:
        """Append what was just said. The author is who said it, not who owns
        the branch: a session can be held by several people."""
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
                author,
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
        # Tool payloads are private execution data, not public conversation
        # items. A file someone brought is theirs, so it carries as one.
        items = tuple(
            BundleItem(
                (turn.id,),
                "user" if turn.role == "attachment" else turn.role,
                turn.content,
                "copied",
            )
            for turn in turns
            if turn.role in {"user", "assistant", "attachment"}
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
