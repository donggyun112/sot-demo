from __future__ import annotations

from typing import Protocol

from sot.document.contracts import (
    DocumentSummary,
    DocumentView,
    PassageGround,
    RevisionSummary,
    RevisionView,
)
from sot.document.domain import Document, Revision
from sot.shared.ids import DocumentId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext


class DocumentRepository(Protocol):
    async def create(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
        revision: Revision,
    ) -> None: ...

    async def load(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> Document | None: ...

    async def save_revision(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
        revision: Revision,
        *,
        expected_version: int,
    ) -> None:
        """Conditionally advance from expected_version or raise VersionConflict."""
        ...

    async def save_title(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
    ) -> None:
        """Store the document's title. Leaves the revision history alone."""
        ...


class DocumentQuery(Protocol):
    async def get(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> DocumentView | None: ...

    async def get_revision(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        number: int,
    ) -> RevisionView | None: ...

    async def list_revisions(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> tuple[RevisionSummary, ...]:
        """Newest first. Empty for a document the workspace does not have."""
        ...

    async def list_grounds(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> tuple[PassageGround, ...]:
        """The newest citation for each claim across every revision."""
        ...


class DocumentPublicationQuery(Protocol):
    async def get_for_update(
        self, tx: TransactionContext, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> DocumentView | None:
        """Lock current main until the caller's transaction ends, then project it."""
        ...


class DocumentListQuery(Protocol):
    async def list_documents(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> tuple[DocumentSummary, ...]: ...


__all__ = [
    "DocumentListQuery",
    "DocumentPublicationQuery",
    "DocumentQuery",
    "DocumentRepository",
]
