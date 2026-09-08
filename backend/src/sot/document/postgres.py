from typing import Any

from psycopg import AsyncConnection

from sot.bootstrap.database import PostgresTransactionContext
from sot.document.contracts import (
    DocumentSummary,
    DocumentView,
    PassageGround,
    RevisionCitationView,
    RevisionSummary,
    RevisionView,
)
from sot.document.domain import Document, Revision, RevisionId, VersionConflict
from sot.shared.ids import (
    BundleId,
    DocumentId,
    ProposalId,
    SessionId,
    UserId,
    WorkspaceId,
)
from sot.shared.unit_of_work import TransactionContext


def connection(tx: TransactionContext) -> AsyncConnection[Any]:
    if not isinstance(tx, PostgresTransactionContext):
        raise TypeError("PostgreSQL transaction required")
    return tx.connection


class PostgresDocumentRepository:
    async def list_documents(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> tuple[DocumentSummary, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT id,workspace_id,title,current_revision_id,version "
                "FROM sot.sot_document WHERE workspace_id=%s "
                "AND current_revision_id IS NOT NULL ORDER BY title,id",
                (workspace_id,),
            )
        ).fetchall()
        return tuple(
            DocumentSummary(DocumentId(r[0]), WorkspaceId(r[1]), r[2], r[3], r[4])
            for r in rows
        )

    async def get_for_update(
        self, tx: TransactionContext, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> DocumentView | None:
        row = await (
            await connection(tx).execute(
                "SELECT id FROM sot.sot_document WHERE workspace_id=%s AND id=%s FOR UPDATE",
                (workspace_id, document_id),
            )
        ).fetchone()
        return await self.get(tx, workspace_id, document_id) if row else None

    async def create(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
        revision: Revision,
    ) -> None:
        self._validate(workspace_id, document, revision)
        await connection(tx).execute(
            "INSERT INTO sot.sot_document(id,workspace_id,created_by,title,version,current_revision_id) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                document.id,
                workspace_id,
                document.created_by,
                document.title,
                document.version,
                document.current_revision_id,
            ),
        )
        await self._insert_revision(tx, workspace_id, revision)

    async def load(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> Document | None:
        row = await (
            await connection(tx).execute(
                "SELECT id,workspace_id,created_by,title,version,current_revision_id "
                "FROM sot.sot_document WHERE workspace_id=%s AND id=%s",
                (workspace_id, document_id),
            )
        ).fetchone()
        return (
            Document(
                DocumentId(row[0]),
                WorkspaceId(row[1]),
                UserId(row[2]),
                row[3],
                row[4],
                RevisionId(row[5]) if row[5] else None,
            )
            if row
            else None
        )

    async def save_revision(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
        revision: Revision,
        *,
        expected_version: int,
    ) -> None:
        self._validate(workspace_id, document, revision)
        if document.version != expected_version + 1:
            raise VersionConflict()
        cursor = await connection(tx).execute(
            "UPDATE sot.sot_document SET version=%s,current_revision_id=%s "
            "WHERE workspace_id=%s AND id=%s AND version=%s RETURNING id",
            (
                document.version,
                revision.id,
                workspace_id,
                document.id,
                expected_version,
            ),
        )
        if await cursor.fetchone() is None:
            raise VersionConflict()
        await self._insert_revision(tx, workspace_id, revision)

    async def save_title(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
    ) -> None:
        # No version condition: a title is a label, and the last person to
        # name it wins. The revision history is what carries concurrency.
        await connection(tx).execute(
            "UPDATE sot.sot_document SET title=%s WHERE workspace_id=%s AND id=%s",
            (document.title, workspace_id, document.id),
        )

    async def list_revisions(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> tuple[RevisionSummary, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT id,number,proposal_id,created_by,created_at "
                "FROM sot.sot_document_revision "
                "WHERE workspace_id=%s AND document_id=%s ORDER BY number DESC",
                (workspace_id, document_id),
            )
        ).fetchall()
        return tuple(
            RevisionSummary(
                RevisionId(r[0]),
                r[1],
                ProposalId(r[2]) if r[2] else None,
                UserId(r[3]),
                r[4],
            )
            for r in rows
        )

    async def list_grounds(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> tuple[PassageGround, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT DISTINCT ON (c.claim_anchor) "
                "c.claim_anchor,c.bundle_id,c.bundle_item_position,r.number,"
                "p.source_session_id,v.tool_call_id "
                "FROM sot.sot_revision_citation c "
                "JOIN sot.sot_document_revision r "
                "  ON r.workspace_id=c.workspace_id AND r.id=c.revision_id "
                "LEFT JOIN sot.sot_proposal p "
                "  ON p.workspace_id=r.workspace_id AND p.id=r.proposal_id "
                "LEFT JOIN sot.sot_proposal_version v "
                "  ON v.workspace_id=p.workspace_id AND v.proposal_id=p.id "
                " AND v.proposal_version=p.current_version "
                "WHERE r.workspace_id=%s AND r.document_id=%s "
                "ORDER BY c.claim_anchor, r.number DESC",
                (workspace_id, document_id),
            )
        ).fetchall()
        return tuple(
            PassageGround(
                r[0],
                BundleId(r[1]),
                r[2],
                r[3],
                SessionId(r[4]) if r[4] else None,
                r[5],
            )
            for r in rows
        )

    @staticmethod
    def _validate(
        workspace_id: WorkspaceId, document: Document, revision: Revision
    ) -> None:
        if not (
            workspace_id == document.workspace_id == revision.workspace_id
            and document.id == revision.document_id
            and document.current_revision_id == revision.id
            and document.version == revision.number
        ):
            raise ValueError("Document revision scope mismatch")

    async def _insert_revision(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        revision: Revision,
    ) -> None:
        await connection(tx).execute(
            "INSERT INTO sot.sot_document_revision(id,workspace_id,document_id,number,content,proposal_id,created_by,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                revision.id,
                workspace_id,
                revision.document_id,
                revision.number,
                revision.content,
                revision.proposal_id,
                revision.created_by,
                revision.created_at,
            ),
        )
        for position, citation in enumerate(revision.citations):
            if citation.revision_id != revision.id:
                raise ValueError("Citation revision mismatch")
            await connection(tx).execute(
                "INSERT INTO sot.sot_revision_citation(workspace_id,revision_id,position,claim_anchor,bundle_id,bundle_item_position) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    workspace_id,
                    revision.id,
                    position,
                    citation.claim_anchor,
                    citation.bundle_id,
                    citation.bundle_item_position,
                ),
            )

    async def get(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> DocumentView | None:
        document = await self.load(tx, workspace_id, document_id)
        if document is None or document.current_revision_id is None:
            return None
        revision = await self.get_revision(
            tx, workspace_id, document_id, document.version
        )
        if revision is None or revision.id != document.current_revision_id:
            return None
        return DocumentView(
            DocumentSummary(
                document.id,
                workspace_id,
                document.title,
                document.current_revision_id,
                document.version,
            ),
            revision,
        )

    async def get_revision(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        number: int,
    ) -> RevisionView | None:
        row = await (
            await connection(tx).execute(
                "SELECT id,workspace_id,document_id,number,content,proposal_id,created_by,created_at "
                "FROM sot.sot_document_revision WHERE workspace_id=%s AND document_id=%s AND number=%s",
                (workspace_id, document_id, number),
            )
        ).fetchone()
        if row is None:
            return None
        citations = await (
            await connection(tx).execute(
                "SELECT claim_anchor,bundle_id,bundle_item_position FROM sot.sot_revision_citation "
                "WHERE workspace_id=%s AND revision_id=%s ORDER BY position",
                (workspace_id, row[0]),
            )
        ).fetchall()
        return RevisionView(
            RevisionId(row[0]),
            WorkspaceId(row[1]),
            DocumentId(row[2]),
            row[3],
            row[4],
            ProposalId(row[5]) if row[5] else None,
            UserId(row[6]),
            row[7],
            tuple(RevisionCitationView(c[0], BundleId(c[1]), c[2]) for c in citations),
        )
