from typing import Any

from psycopg import AsyncConnection

from sot.bootstrap.database import PostgresTransactionContext
from sot.consensus.domain import (
    Approval,
    ApprovalDecision,
    Proposal,
    DocumentEdit,
    ProposalCitation,
    ProposalNotFound,
    ProposalStatus,
    ProposalVersion,
)
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


class PostgresProposalRepository:
    async def list_proposal_ids(
        self, tx: TransactionContext, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> tuple[ProposalId, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT id FROM sot.sot_proposal WHERE workspace_id=%s AND document_id=%s "
                "ORDER BY created_at,id",
                (workspace_id, document_id),
            )
        ).fetchall()
        return tuple(ProposalId(row[0]) for row in rows)

    async def find(
        self, tx: TransactionContext, workspace_id: WorkspaceId, proposal_id: ProposalId
    ) -> Proposal | None:
        return await self._read(tx, workspace_id, proposal_id, lock=False)

    async def get_for_update(
        self, tx: TransactionContext, workspace_id: WorkspaceId, proposal_id: ProposalId
    ) -> Proposal | None:
        return await self._read(tx, workspace_id, proposal_id, lock=True)

    async def _read(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
        *,
        lock: bool,
    ) -> Proposal | None:
        conn = connection(tx)
        row = await (
            await conn.execute(
                "SELECT id,workspace_id,document_id,source_session_id,created_by,created_at,current_version,status FROM sot.sot_proposal WHERE workspace_id=%s AND id=%s"
                + (" FOR UPDATE" if lock else " FOR SHARE"),
                (workspace_id, proposal_id),
            )
        ).fetchone()
        if row is None:
            return None
        # Hold the aggregate stable while projecting its version-owned children.
        scope = (workspace_id, proposal_id, row[6])
        versions = await (
            await conn.execute(
                "SELECT proposal_version,base_revision_id,created_by,created_at FROM sot.sot_proposal_version WHERE workspace_id=%s AND proposal_id=%s AND proposal_version<=%s ORDER BY proposal_version",
                scope,
            )
        ).fetchall()
        edits = await (
            await conn.execute(
                "SELECT proposal_version,find,replace FROM sot.sot_proposal_edit WHERE workspace_id=%s AND proposal_id=%s AND proposal_version<=%s ORDER BY proposal_version,position",
                scope,
            )
        ).fetchall()
        bundles = await (
            await conn.execute(
                "SELECT proposal_version,bundle_id FROM sot.sot_proposal_bundle WHERE workspace_id=%s AND proposal_id=%s AND proposal_version<=%s ORDER BY proposal_version,position",
                scope,
            )
        ).fetchall()
        citations = await (
            await conn.execute(
                "SELECT proposal_version,bundle_id,bundle_item_position,claim_anchor FROM sot.sot_proposal_citation WHERE workspace_id=%s AND proposal_id=%s AND proposal_version<=%s ORDER BY proposal_version,position",
                scope,
            )
        ).fetchall()
        approvers = await (
            await conn.execute(
                "SELECT proposal_version,approver_user_id,additional FROM sot.sot_proposal_approver WHERE workspace_id=%s AND proposal_id=%s AND proposal_version<=%s ORDER BY proposal_version,approver_user_id",
                scope,
            )
        ).fetchall()
        approvals = await (
            await conn.execute(
                "SELECT proposal_version,approver_user_id,decision,decided_at FROM sot.sot_approval WHERE workspace_id=%s AND proposal_id=%s AND proposal_version<=%s ORDER BY proposal_version,decided_at,approver_user_id",
                scope,
            )
        ).fetchall()
        return Proposal(
            ProposalId(row[0]),
            WorkspaceId(row[1]),
            DocumentId(row[2]),
            SessionId(row[3]),
            UserId(row[4]),
            row[5],
            tuple(
                ProposalVersion(
                    proposal_id,
                    v[0],
                    v[1],
                    tuple(DocumentEdit(e[1], e[2]) for e in edits if e[0] == v[0]),
                    frozenset(UserId(a[1]) for a in approvers if a[0] == v[0]),
                    tuple(BundleId(b[1]) for b in bundles if b[0] == v[0]),
                    UserId(v[2]),
                    v[3],
                    tuple(
                        ProposalCitation(BundleId(c[1]), c[2], c[3])
                        for c in citations
                        if c[0] == v[0]
                    ),
                    frozenset(UserId(a[1]) for a in approvers if a[0] == v[0] and a[2]),
                )
                for v in versions
            ),
            tuple(
                Approval(proposal_id, a[0], UserId(a[1]), ApprovalDecision(a[2]), a[3])
                for a in approvals
            ),
            ProposalStatus(row[7]),
        )

    async def add(self, tx: TransactionContext, proposal: Proposal) -> None:
        await connection(tx).execute(
            "INSERT INTO sot.sot_proposal(id,workspace_id,document_id,source_session_id,created_by,created_at,current_version,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                proposal.id,
                proposal.workspace_id,
                proposal.document_id,
                proposal.source_session_id,
                proposal.created_by,
                proposal.created_at,
                proposal.version,
                proposal.status.value,
            ),
        )
        await self._append_snapshots(tx, proposal)

    async def save(self, tx: TransactionContext, proposal: Proposal) -> None:
        # The caller holds get_for_update's row lock in this same transaction.
        await self._append_snapshots(tx, proposal)
        row = await (
            await connection(tx).execute(
                "UPDATE sot.sot_proposal SET current_version=%s,status=%s WHERE workspace_id=%s AND id=%s RETURNING id",
                (
                    proposal.version,
                    proposal.status.value,
                    proposal.workspace_id,
                    proposal.id,
                ),
            )
        ).fetchone()
        if row is None:
            raise ProposalNotFound()

    async def _append_snapshots(
        self, tx: TransactionContext, proposal: Proposal
    ) -> None:
        conn = connection(tx)
        for version in proposal.versions:
            scope = (proposal.workspace_id, proposal.id, version.version)
            inserted = await (
                await conn.execute(
                    "INSERT INTO sot.sot_proposal_version(workspace_id,proposal_id,proposal_version,document_id,base_revision_id,created_by,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id,proposal_id,proposal_version) DO NOTHING RETURNING proposal_version",
                    (
                        *scope,
                        proposal.document_id,
                        version.base_revision_id,
                        version.created_by,
                        version.created_at,
                    ),
                )
            ).fetchone()
            if inserted is None:
                continue
            for position, edit in enumerate(version.edits):
                await conn.execute(
                    "INSERT INTO sot.sot_proposal_edit(workspace_id,proposal_id,proposal_version,position,find,replace) VALUES (%s,%s,%s,%s,%s,%s)",
                    (*scope, position, edit.find, edit.replace),
                )
            for position, bundle_id in enumerate(version.bundle_ids):
                await conn.execute(
                    "INSERT INTO sot.sot_proposal_bundle(workspace_id,proposal_id,proposal_version,position,bundle_id) VALUES (%s,%s,%s,%s,%s)",
                    (*scope, position, bundle_id),
                )
            for position, citation in enumerate(version.citations):
                await conn.execute(
                    "INSERT INTO sot.sot_proposal_citation(workspace_id,proposal_id,proposal_version,position,claim_anchor,bundle_id,bundle_item_position) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        *scope,
                        position,
                        citation.claim_anchor,
                        citation.bundle_id,
                        citation.bundle_item_position,
                    ),
                )
            for user_id in sorted(version.required_approver_ids, key=str):
                await conn.execute(
                    "INSERT INTO sot.sot_proposal_approver(workspace_id,proposal_id,proposal_version,approver_user_id,additional) VALUES (%s,%s,%s,%s,%s)",
                    (*scope, user_id, user_id in version.additional_approver_ids),
                )
        for approval in proposal.approvals:
            await conn.execute(
                "INSERT INTO sot.sot_approval(workspace_id,proposal_id,proposal_version,approver_user_id,decision,decided_at) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id,proposal_id,proposal_version,approver_user_id) DO NOTHING",
                (
                    proposal.workspace_id,
                    proposal.id,
                    approval.version,
                    approval.approver_user_id,
                    approval.decision.value,
                    approval.decided_at,
                ),
            )
