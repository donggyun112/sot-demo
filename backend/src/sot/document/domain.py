from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NewType
from uuid import UUID, uuid4

from sot.shared.errors import Conflict, InvalidInput, NotFound
from sot.shared.ids import BundleId, DocumentId, ProposalId, UserId, WorkspaceId

RevisionId = NewType("RevisionId", UUID)


class DocumentNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("document_not_found", "Document not found")


class VersionConflict(Conflict):
    def __init__(self) -> None:
        super().__init__("version_conflict", "The resource changed after it was loaded")


@dataclass(frozen=True, slots=True)
class RevisionCitationInput:
    claim_anchor: str
    bundle_id: BundleId
    bundle_item_position: int

    def __post_init__(self) -> None:
        if not self.claim_anchor.strip() or self.bundle_item_position < 0:
            raise InvalidInput("revision_citation_invalid", "Citation is invalid")


@dataclass(frozen=True, slots=True)
class RevisionCitation:
    revision_id: RevisionId
    claim_anchor: str
    bundle_id: BundleId
    bundle_item_position: int


@dataclass(frozen=True, slots=True)
class Revision:
    id: RevisionId
    workspace_id: WorkspaceId
    document_id: DocumentId
    number: int
    content: str
    proposal_id: ProposalId | None
    created_by: UserId
    created_at: datetime
    citations: tuple[RevisionCitation, ...] = ()


@dataclass(slots=True)
class Document:
    id: DocumentId
    workspace_id: WorkspaceId
    created_by: UserId
    title: str
    version: int = 0
    current_revision_id: RevisionId | None = None

    def __post_init__(self) -> None:
        self.title = self.title.strip()
        if not self.title or len(self.title) > 200:
            raise InvalidInput("document_title_invalid", "Document title is invalid")
        if self.version < 0:
            raise InvalidInput(
                "document_version_invalid", "Document version is invalid"
            )

    @classmethod
    def create(
        cls, workspace_id: WorkspaceId, created_by: UserId, title: str
    ) -> Document:
        return cls(DocumentId(uuid4()), workspace_id, created_by, title)

    def initialize(self, content: str, actor_id: UserId, now: datetime) -> Revision:
        if self.version != 0 or self.current_revision_id is not None:
            raise VersionConflict()
        return self._append_revision(content, None, (), actor_id, now)

    def publish(
        self,
        *,
        content: str,
        proposal_id: ProposalId,
        citations: tuple[RevisionCitationInput, ...],
        actor_id: UserId,
        expected_version: int,
        now: datetime,
    ) -> Revision:
        if expected_version != self.version or self.current_revision_id is None:
            raise VersionConflict()
        return self._append_revision(content, proposal_id, citations, actor_id, now)

    def _append_revision(
        self,
        content: str,
        proposal_id: ProposalId | None,
        citations: tuple[RevisionCitationInput, ...],
        actor_id: UserId,
        now: datetime,
    ) -> Revision:
        revision_id = RevisionId(uuid4())
        number = self.version + 1
        revision = Revision(
            id=revision_id,
            workspace_id=self.workspace_id,
            document_id=self.id,
            number=number,
            content=content,
            proposal_id=proposal_id,
            created_by=actor_id,
            created_at=now,
            citations=tuple(
                RevisionCitation(
                    revision_id,
                    item.claim_anchor,
                    item.bundle_id,
                    item.bundle_item_position,
                )
                for item in citations
            ),
        )
        self.version = number
        self.current_revision_id = revision_id
        return revision


__all__ = [
    "Document",
    "DocumentNotFound",
    "Revision",
    "RevisionCitation",
    "RevisionCitationInput",
    "RevisionId",
    "VersionConflict",
]
