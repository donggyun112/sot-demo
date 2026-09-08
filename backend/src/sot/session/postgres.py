from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from sot.bootstrap.database import PostgresTransactionContext
from sot.session.domain import (
    Branch,
    Bundle,
    BundleItem,
    CurationOperation,
    CurationRecord,
    DropTurn,
    EditTurn,
    JoinTurns,
    RestoreTurn,
    Session,
    SessionMember,
    SessionMemberAlreadyExists,
    SessionNotFound,
    SessionOrigin,
    SessionRole,
    SessionStatus,
    Turn,
)
from sot.shared.ids import (
    BranchId,
    BundleId,
    DocumentId,
    SessionId,
    UserId,
    WorkspaceId,
)
from sot.shared.unit_of_work import TransactionContext


def connection(tx: TransactionContext) -> AsyncConnection[Any]:
    if not isinstance(tx, PostgresTransactionContext):
        raise TypeError("PostgreSQL transaction required")
    return tx.connection


def require_scope(expected: WorkspaceId, actual: WorkspaceId) -> None:
    if expected != actual:
        raise ValueError("Session resource workspace mismatch")


class PostgresSessionRepository:
    async def list_session_ids(
        self, tx: TransactionContext, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> tuple[SessionId, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT id FROM sot.sot_session WHERE workspace_id=%s AND document_id=%s "
                "ORDER BY created_at,id",
                (workspace_id, document_id),
            )
        ).fetchall()
        return tuple(SessionId(row[0]) for row in rows)

    async def list_branches(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session_id: SessionId
    ) -> tuple[Branch, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT id,workspace_id,session_id,created_by,created_at,version "
                "FROM sot.sot_branch WHERE workspace_id=%s AND session_id=%s "
                "ORDER BY created_at,id",
                (workspace_id, session_id),
            )
        ).fetchall()
        return tuple(
            Branch(
                BranchId(r[0]),
                WorkspaceId(r[1]),
                SessionId(r[2]),
                UserId(r[3]),
                r[4],
                r[5],
            )
            for r in rows
        )

    async def create_session(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session: Session
    ) -> None:
        require_scope(workspace_id, session.workspace_id)
        await connection(tx).execute(
            "INSERT INTO sot.sot_session(id,workspace_id,document_id,created_by,created_at,status,"
            "forked_from_session_id,forked_from_branch_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                session.id,
                workspace_id,
                session.document_id,
                session.created_by,
                session.created_at,
                session.status.value,
                session.origin.session_id if session.origin else None,
                session.origin.branch_id if session.origin else None,
            ),
        )

    async def load_session(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session_id: SessionId
    ) -> Session | None:
        row = await (
            await connection(tx).execute(
                "SELECT id,workspace_id,document_id,created_by,created_at,status,"
                "forked_from_session_id,forked_from_branch_id "
                "FROM sot.sot_session WHERE workspace_id=%s AND id=%s",
                (workspace_id, session_id),
            )
        ).fetchone()
        return (
            Session(
                SessionId(row[0]),
                WorkspaceId(row[1]),
                DocumentId(row[2]) if row[2] else None,
                UserId(row[3]),
                row[4],
                SessionStatus(row[5]),
                SessionOrigin(SessionId(row[6]), BranchId(row[7])) if row[6] else None,
            )
            if row
            else None
        )

    async def save_session(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session: Session
    ) -> None:
        require_scope(workspace_id, session.workspace_id)
        cursor = await connection(tx).execute(
            "UPDATE sot.sot_session SET status=%s WHERE workspace_id=%s AND id=%s RETURNING id",
            (session.status.value, workspace_id, session.id),
        )
        if await cursor.fetchone() is None:
            raise SessionNotFound()

    async def get_member(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        user_id: UserId,
    ) -> SessionMember | None:
        row = await (
            await connection(tx).execute(
                "SELECT workspace_id,session_id,user_id,role FROM sot.sot_session_member WHERE workspace_id=%s AND session_id=%s AND user_id=%s",
                (workspace_id, session_id, user_id),
            )
        ).fetchone()
        return (
            SessionMember(
                WorkspaceId(row[0]),
                SessionId(row[1]),
                UserId(row[2]),
                SessionRole(row[3]),
            )
            if row
            else None
        )

    async def add_member(
        self, tx: TransactionContext, workspace_id: WorkspaceId, member: SessionMember
    ) -> None:
        require_scope(workspace_id, member.workspace_id)
        cursor = await connection(tx).execute(
            "INSERT INTO sot.sot_session_member(workspace_id,session_id,user_id,role) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (workspace_id,session_id,user_id) DO NOTHING RETURNING user_id",
            (workspace_id, member.session_id, member.user_id, member.role.value),
        )
        if await cursor.fetchone() is None:
            raise SessionMemberAlreadyExists()

    async def list_members(
        self, tx: TransactionContext, workspace_id: WorkspaceId, session_id: SessionId
    ) -> tuple[SessionMember, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT workspace_id,session_id,user_id,role FROM sot.sot_session_member WHERE workspace_id=%s AND session_id=%s ORDER BY user_id",
                (workspace_id, session_id),
            )
        ).fetchall()
        return tuple(
            SessionMember(
                WorkspaceId(r[0]), SessionId(r[1]), UserId(r[2]), SessionRole(r[3])
            )
            for r in rows
        )

    async def create_branch(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch: Branch
    ) -> None:
        require_scope(workspace_id, branch.workspace_id)
        await connection(tx).execute(
            "INSERT INTO sot.sot_branch(id,workspace_id,session_id,created_by,created_at,version) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                branch.id,
                workspace_id,
                branch.session_id,
                branch.created_by,
                branch.created_at,
                branch.version,
            ),
        )
        await self.append_turns(tx, workspace_id, branch.id, branch.turns)

    async def session_for_branch(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> SessionId | None:
        row = await (
            await connection(tx).execute(
                "SELECT session_id FROM sot.sot_branch WHERE workspace_id=%s AND id=%s",
                (workspace_id, branch_id),
            )
        ).fetchone()
        return SessionId(row[0]) if row else None

    async def load_branch(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> Branch | None:
        row = await (
            await connection(tx).execute(
                "SELECT id,workspace_id,session_id,created_by,created_at,version FROM sot.sot_branch WHERE workspace_id=%s AND id=%s",
                (workspace_id, branch_id),
            )
        ).fetchone()
        if row is None:
            return None
        turns = await (
            await connection(tx).execute(
                "SELECT id,workspace_id,branch_id,ordinal,role,content,created_at,created_by "
                "FROM sot.sot_turn WHERE workspace_id=%s AND branch_id=%s ORDER BY ordinal",
                (workspace_id, branch_id),
            )
        ).fetchall()
        return Branch(
            BranchId(row[0]),
            WorkspaceId(row[1]),
            SessionId(row[2]),
            UserId(row[3]),
            row[4],
            row[5],
            tuple(
                Turn(
                    t[0],
                    WorkspaceId(t[1]),
                    BranchId(t[2]),
                    t[3],
                    t[4],
                    t[5],
                    t[6],
                    UserId(t[7]),
                )
                for t in turns
            ),
        )

    async def advance_version(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        *,
        expected_version: int,
    ) -> int | None:
        row = await (
            await connection(tx).execute(
                "UPDATE sot.sot_branch SET version=version+1 WHERE workspace_id=%s AND id=%s AND version=%s RETURNING version",
                (workspace_id, branch_id, expected_version),
            )
        ).fetchone()
        return int(row[0]) if row else None

    async def append_turns(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        turns: tuple[Turn, ...],
    ) -> None:
        for turn in turns:
            require_scope(workspace_id, turn.workspace_id)
            if turn.branch_id != branch_id:
                raise ValueError("Turn branch mismatch")
            await connection(tx).execute(
                "INSERT INTO sot.sot_turn(id,workspace_id,branch_id,ordinal,role,content,created_at,created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    turn.id,
                    workspace_id,
                    branch_id,
                    turn.ordinal,
                    turn.role,
                    turn.content,
                    turn.created_at,
                    turn.created_by,
                ),
            )

    async def list_curation(
        self, tx: TransactionContext, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> tuple[CurationRecord, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT id,branch_id,ordinal,kind,source_ids,content,created_by,created_at FROM sot.sot_curation_op WHERE workspace_id=%s AND branch_id=%s ORDER BY ordinal",
                (workspace_id, branch_id),
            )
        ).fetchall()
        records = []
        for row in rows:
            operation: CurationOperation
            if row[3] == "drop":
                operation = DropTurn(row[4][0])
            elif row[3] == "restore":
                operation = RestoreTurn(row[4][0])
            elif row[3] == "edit":
                operation = EditTurn(row[4][0], row[5])
            else:
                operation = JoinTurns(tuple(row[4]), row[5])
            records.append(
                CurationRecord(
                    row[0], BranchId(row[1]), row[2], operation, UserId(row[6]), row[7]
                )
            )
        return tuple(records)

    async def append_curation(
        self, tx: TransactionContext, workspace_id: WorkspaceId, record: CurationRecord
    ) -> None:
        operation = record.operation
        ids: tuple[UUID, ...]
        content: str | None
        if isinstance(operation, DropTurn):
            kind, ids, content = "drop", (operation.turn_id,), None
        elif isinstance(operation, RestoreTurn):
            # No content: a restore reinstates the turn's own wording.
            kind, ids, content = "restore", (operation.turn_id,), None
        elif isinstance(operation, EditTurn):
            kind, ids, content = "edit", (operation.turn_id,), operation.content
        else:
            kind, ids, content = "join", operation.turn_ids, operation.content
        await connection(tx).execute(
            "INSERT INTO sot.sot_curation_op(id,workspace_id,branch_id,ordinal,kind,source_ids,content,created_by,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                record.id,
                workspace_id,
                record.branch_id,
                record.ordinal,
                kind,
                list(ids),
                content,
                record.created_by,
                record.created_at,
            ),
        )

    async def create_bundle(
        self, tx: TransactionContext, workspace_id: WorkspaceId, bundle: Bundle
    ) -> None:
        require_scope(workspace_id, bundle.workspace_id)
        await connection(tx).execute(
            "INSERT INTO sot.sot_bundle(id,workspace_id,session_id,branch_id,title,published_by,published_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                bundle.id,
                workspace_id,
                bundle.session_id,
                bundle.branch_id,
                bundle.title,
                bundle.published_by,
                bundle.published_at,
            ),
        )
        for position, item in enumerate(bundle.items):
            await connection(tx).execute(
                "INSERT INTO sot.sot_bundle_item(workspace_id,bundle_id,position,source_ids,role,content,provenance) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    workspace_id,
                    bundle.id,
                    position,
                    list(item.source_ids),
                    item.role,
                    item.content,
                    item.provenance,
                ),
            )

    async def session_for_bundle(
        self, tx: TransactionContext, workspace_id: WorkspaceId, bundle_id: BundleId
    ) -> SessionId | None:
        row = await (
            await connection(tx).execute(
                "SELECT session_id FROM sot.sot_bundle WHERE workspace_id=%s AND id=%s",
                (workspace_id, bundle_id),
            )
        ).fetchone()
        return SessionId(row[0]) if row else None

    async def load_bundle(
        self, tx: TransactionContext, workspace_id: WorkspaceId, bundle_id: BundleId
    ) -> Bundle | None:
        row = await (
            await connection(tx).execute(
                "SELECT id,workspace_id,session_id,branch_id,title,published_by,published_at FROM sot.sot_bundle WHERE workspace_id=%s AND id=%s",
                (workspace_id, bundle_id),
            )
        ).fetchone()
        if row is None:
            return None
        items = await (
            await connection(tx).execute(
                "SELECT source_ids,role,content,provenance FROM sot.sot_bundle_item WHERE workspace_id=%s AND bundle_id=%s ORDER BY position",
                (workspace_id, bundle_id),
            )
        ).fetchall()
        return Bundle(
            BundleId(row[0]),
            WorkspaceId(row[1]),
            SessionId(row[2]),
            BranchId(row[3]),
            row[4],
            tuple(BundleItem(tuple(i[0]), i[1], i[2], i[3]) for i in items),
            UserId(row[5]),
            row[6],
        )
