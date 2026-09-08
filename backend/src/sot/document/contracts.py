from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sot.document.domain import RevisionCitationInput, RevisionId
from sot.identity.contracts import Actor
from sot.shared.ids import BundleId, DocumentId, ProposalId, UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    id: DocumentId
    workspace_id: WorkspaceId
    title: str
    current_revision_id: RevisionId
    version: int


@dataclass(frozen=True, slots=True)
class RevisionCitationView:
    claim_anchor: str
    bundle_id: BundleId
    bundle_item_position: int


@dataclass(frozen=True, slots=True)
class RevisionView:
    id: RevisionId
    workspace_id: WorkspaceId
    document_id: DocumentId
    number: int
    content: str
    proposal_id: ProposalId | None
    created_by: UserId
    created_at: datetime
    citations: tuple[RevisionCitationView, ...]


@dataclass(frozen=True, slots=True)
class RevisionSummary:
    """One entry in a document's history. Bodies stay out of the list."""

    id: RevisionId
    number: int
    proposal_id: ProposalId | None
    created_by: UserId
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentView:
    document: DocumentSummary
    current_revision: RevisionView


@dataclass(frozen=True, slots=True)
class RevisionResult:
    document: DocumentSummary
    revision: RevisionView


class DocumentReader(Protocol):
    async def require_document(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> DocumentView: ...


class DocumentPublisher(Protocol):
    async def publish(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        expected_version: int,
        proposal_id: ProposalId,
        content: str,
        citations: tuple[RevisionCitationInput, ...],
    ) -> RevisionResult: ...


__all__ = [
    "DocumentPublisher",
    "DocumentReader",
    "DocumentSummary",
    "DocumentView",
    "RevisionCitationInput",
    "RevisionCitationView",
    "RevisionResult",
    "RevisionSummary",
    "RevisionView",
]
