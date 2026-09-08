from typing import Any

from psycopg import AsyncConnection

from sot.bootstrap.database import PostgresTransactionContext
from sot.shared.ids import UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.domain import (
    Workspace,
    WorkspaceMemberAlreadyExists,
    WorkspaceMembership,
    WorkspaceRole,
)


def connection(tx: TransactionContext) -> AsyncConnection[Any]:
    if not isinstance(tx, PostgresTransactionContext):
        raise TypeError("PostgreSQL transaction required")
    return tx.connection


class PostgresWorkspaceRepository:
    async def create(self, tx: TransactionContext, workspace: Workspace) -> None:
        await connection(tx).execute(
            "INSERT INTO sot.sot_workspace(id,name) VALUES (%s,%s)",
            (workspace.id, workspace.name),
        )

    async def get(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> Workspace | None:
        row = await (
            await connection(tx).execute(
                "SELECT id,name FROM sot.sot_workspace WHERE id=%s",
                (workspace_id,),
            )
        ).fetchone()
        return Workspace(WorkspaceId(row[0]), row[1]) if row else None

    async def add_member(
        self, tx: TransactionContext, member: WorkspaceMembership
    ) -> None:
        cursor = await connection(tx).execute(
            "INSERT INTO sot.sot_workspace_member(workspace_id,user_id,role) VALUES (%s,%s,%s) "
            "ON CONFLICT (workspace_id,user_id) DO NOTHING RETURNING user_id",
            (member.workspace_id, member.user_id, member.role.value),
        )
        if await cursor.fetchone() is None:
            raise WorkspaceMemberAlreadyExists()

    async def get_member(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        row = await (
            await connection(tx).execute(
                "SELECT workspace_id,user_id,role FROM sot.sot_workspace_member "
                "WHERE workspace_id=%s AND user_id=%s",
                (workspace_id, user_id),
            )
        ).fetchone()
        return (
            WorkspaceMembership(
                WorkspaceId(row[0]), UserId(row[1]), WorkspaceRole(row[2])
            )
            if row
            else None
        )

    async def list_members(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> tuple[WorkspaceMembership, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT workspace_id,user_id,role FROM sot.sot_workspace_member "
                "WHERE workspace_id=%s ORDER BY user_id",
                (workspace_id,),
            )
        ).fetchall()
        return tuple(
            WorkspaceMembership(
                WorkspaceId(row[0]), UserId(row[1]), WorkspaceRole(row[2])
            )
            for row in rows
        )

    async def list_for_user(
        self, tx: TransactionContext, user_id: UserId
    ) -> tuple[Workspace, ...]:
        rows = await (
            await connection(tx).execute(
                "SELECT w.id,w.name FROM sot.sot_workspace w "
                "JOIN sot.sot_workspace_member m ON m.workspace_id=w.id "
                "WHERE m.user_id=%s ORDER BY w.id",
                (user_id,),
            )
        ).fetchall()
        return tuple(Workspace(WorkspaceId(row[0]), row[1]) for row in rows)
