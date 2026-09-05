from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProposalStatus(StrEnum):
    OPEN = "open"
    PUBLISHED = "published"


@dataclass(frozen=True, slots=True)
class Document:
    id: UUID
    title: str
    current_revision_id: UUID
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Revision:
    id: UUID
    document_id: UUID
    number: int
    content: str
    proposal_id: UUID | None
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Session:
    id: UUID
    document_id: UUID
    owner_id: str
    title: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Branch:
    id: UUID
    session_id: UUID
    owner_id: str
    parent_branch_id: UUID | None
    source_toss_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NewTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class Turn:
    id: UUID
    branch_id: UUID
    ordinal: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Cite:
    id: UUID
    branch_id: UUID
    created_by: str
    turn_ids: tuple[UUID, ...]
    summary: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Toss:
    id: UUID
    cite_id: UUID
    token: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Proposal:
    id: UUID
    document_id: UUID
    branch_id: UUID
    created_by: str
    content: str
    status: ProposalStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SessionView:
    session: Session
    branch: Branch


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    proposal: Proposal
    approver_ids: tuple[str, ...]
    revision: Revision | None


__all__ = [
    "ApprovalResult",
    "Branch",
    "Cite",
    "Document",
    "NewTurn",
    "Proposal",
    "ProposalStatus",
    "Revision",
    "Session",
    "SessionView",
    "Toss",
    "Turn",
    "utc_now",
]
