from __future__ import annotations

from typing import Protocol

from sot.document.contracts import DocumentView
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


__all__ = ["DocumentQuery", "DocumentRepository"]
