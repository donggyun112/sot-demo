from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from sot.bootstrap.database import PostgresTransactionContext
from sot.shared.ids import UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.domain import (
    Invitation,
    InvitationStatus,
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


COLUMNS = (
    "id,workspace_id,inviter_id,invitee_email,invitee_user_id,role,status,"
    "created_at,decided_at,expires_at,code"
)


def _invitation(row: tuple[Any, ...]) -> Invitation:
    return Invitation(
        row[0],
        WorkspaceId(row[1]),
        UserId(row[2]),
        row[3],
        WorkspaceRole(row[5]),
        row[7],
        row[9],
        row[10],
        UserId(row[4]) if row[4] else None,
        InvitationStatus(row[6]),
        row[8],
    )


class PostgresInvitationRepository:
    async def add(self, tx: TransactionContext, invitation: Invitation) -> None:
        await connection(tx).execute(
            f"INSERT INTO sot.sot_workspace_invitation({COLUMNS}) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                invitation.id,
                invitation.workspace_id,
                invitation.inviter_id,
                invitation.invitee_email,
                invitation.invitee_user_id,
                invitation.role,
                invitation.status,
                invitation.created_at,
                invitation.decided_at,
                invitation.expires_at,
                invitation.code,
            ),
        )

    async def save(self, tx: TransactionContext, invitation: Invitation) -> None:
        # Settling is one-way, so only a still-pending row may be written over.
        await connection(tx).execute(
            "UPDATE sot.sot_workspace_invitation "
            "SET status=%s, decided_at=%s, invitee_user_id=%s "
            "WHERE id=%s AND status='pending'",
            (
                invitation.status,
                invitation.decided_at,
                invitation.invitee_user_id,
                invitation.id,
            ),
        )

    async def find(
        self, tx: TransactionContext, invitation_id: UUID
    ) -> Invitation | None:
        row = await (
            await connection(tx).execute(
                f"SELECT {COLUMNS} FROM sot.sot_workspace_invitation WHERE id=%s",
                (invitation_id,),
            )
        ).fetchone()
        return _invitation(row) if row else None

    async def find_pending(
        self, tx: TransactionContext, workspace_id: WorkspaceId, email: str
    ) -> Invitation | None:
        row = await (
            await connection(tx).execute(
                f"SELECT {COLUMNS} FROM sot.sot_workspace_invitation "
                "WHERE workspace_id=%s AND invitee_email=%s AND status='pending'",
                (workspace_id, email),
            )
        ).fetchone()
        return _invitation(row) if row else None

    async def find_by_code(
        self, tx: TransactionContext, code: str
    ) -> Invitation | None:
        row = await (
            await connection(tx).execute(
                f"SELECT {COLUMNS} FROM sot.sot_workspace_invitation "
                "WHERE code=%s AND status='pending'",
                (code,),
            )
        ).fetchone()
        return _invitation(row) if row else None

    async def list_pending_for_workspace(
        self, tx: TransactionContext, workspace_id: WorkspaceId
    ) -> tuple[Invitation, ...]:
        rows = await (
            await connection(tx).execute(
                f"SELECT {COLUMNS} FROM sot.sot_workspace_invitation "
                "WHERE workspace_id=%s AND status='pending' ORDER BY created_at DESC",
                (workspace_id,),
            )
        ).fetchall()
        return tuple(_invitation(row) for row in rows)

    async def list_pending_for_invitee(
        self, tx: TransactionContext, user_id: UserId, email: str
    ) -> tuple[Invitation, ...]:
        # Either binding finds it: an invitation sent before they had an
        # account still reaches them once the address matches.
        rows = await (
            await connection(tx).execute(
                f"SELECT {COLUMNS} FROM sot.sot_workspace_invitation "
                "WHERE status='pending' AND (invitee_user_id=%s OR invitee_email=%s) "
                "ORDER BY created_at DESC",
                (user_id, email),
            )
        ).fetchall()
        return tuple(_invitation(row) for row in rows)
