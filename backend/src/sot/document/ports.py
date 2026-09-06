from __future__ import annotations

from typing import Protocol

from sot.document.contracts import DocumentView, RevisionView
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


class DocumentPublicationQuery(Protocol):
    async def get_for_update(
        self, tx: TransactionContext, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> DocumentView | None:
        """Lock current main until the caller's transaction ends, then project it."""
        ...


__all__ = ["DocumentPublicationQuery", "DocumentQuery", "DocumentRepository"]
