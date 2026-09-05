from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from sot.domain.errors import DomainError
from sot.domain.models import (
    Branch,
    Cite,
    Document,
    Proposal,
    ProposalStatus,
    Revision,
    Session,
    Toss,
    Turn,
)

Row = dict[str, Any]


def _document(row: Row) -> Document:
    return Document(**row)


def _revision(row: Row) -> Revision:
    return Revision(**row)


def _session(row: Row) -> Session:
    return Session(**row)


def _branch(row: Row) -> Branch:
    return Branch(**row)


def _turn(row: Row) -> Turn:
    return Turn(**row)


def _cite(row: Row) -> Cite:
    return Cite(
        id=row["id"],
        branch_id=row["branch_id"],
        created_by=row["created_by"],
        turn_ids=tuple(row["turn_ids"]),
        summary=row["summary"],
        created_at=row["created_at"],
    )


def _toss(row: Row) -> Toss:
    return Toss(**row)


def _proposal(row: Row) -> Proposal:
    return Proposal(
        id=row["id"],
        document_id=row["document_id"],
        branch_id=row["branch_id"],
        created_by=row["created_by"],
        content=row["content"],
        status=ProposalStatus(row["status"]),
        created_at=row["created_at"],
    )


class PostgresSOTRepository:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool
        self._active_connection: ContextVar[AsyncConnection[Any] | None] = ContextVar(
            f"sot_connection_{id(self)}", default=None
        )

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[AsyncConnection[Any]]:
        active = self._active_connection.get()
        if active is not None:
            yield active
            return
        async with self._pool.connection() as connection:
            yield connection

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        active = self._active_connection.get()
        if active is not None:
            async with active.transaction():
                yield
            return
        async with self._pool.connection() as connection:
            token = self._active_connection.set(connection)
            try:
                async with connection.transaction():
                    yield
            finally:
                self._active_connection.reset(token)

    async def _fetchone(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = (),
    ) -> Row | None:
        async with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(query, params)
            row = await cursor.fetchone()
            return cast(Row | None, row)

    async def _fetchall(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = (),
    ) -> tuple[Row, ...]:
        async with (
            self._connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(query, params)
            return tuple(cast(list[Row], await cursor.fetchall()))

    async def save_document(self, document: Document) -> None:
        async with self._connection() as connection:
            await connection.execute(
                """
                INSERT INTO sot.documents
                    (id, title, current_revision_id, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET title = EXCLUDED.title,
                    current_revision_id = EXCLUDED.current_revision_id
                """,
                (
                    document.id,
                    document.title,
                    document.current_revision_id,
                    document.created_by,
                    document.created_at,
                ),
            )

    async def get_document(self, document_id: UUID) -> Document | None:
        row = await self._fetchone(
            "SELECT * FROM sot.documents WHERE id = %s", (document_id,)
        )
        return _document(row) if row else None

    async def list_documents(self) -> tuple[Document, ...]:
        rows = await self._fetchall(
            "SELECT * FROM sot.documents ORDER BY created_at, id"
        )
        return tuple(_document(row) for row in rows)

    async def save_revision(self, revision: Revision) -> None:
        try:
            async with self._connection() as connection:
                await connection.execute(
                    """
                    INSERT INTO sot.revisions
                        (id, document_id, number, content, proposal_id,
                         created_by, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        revision.id,
                        revision.document_id,
                        revision.number,
                        revision.content,
                        revision.proposal_id,
                        revision.created_by,
                        revision.created_at,
                    ),
                )
        except UniqueViolation as error:
            raise DomainError(
                "revision_number_conflict", "Revision number already exists"
            ) from error

    async def get_revision(self, revision_id: UUID) -> Revision | None:
        row = await self._fetchone(
            "SELECT * FROM sot.revisions WHERE id = %s", (revision_id,)
        )
        return _revision(row) if row else None

    async def list_revisions(self, document_id: UUID) -> tuple[Revision, ...]:
        rows = await self._fetchall(
            "SELECT * FROM sot.revisions WHERE document_id = %s ORDER BY number",
            (document_id,),
        )
        return tuple(_revision(row) for row in rows)

    async def save_session(self, session: Session) -> None:
        async with self._connection() as connection:
            await connection.execute(
                """
                INSERT INTO sot.sessions
                    (id, document_id, owner_id, title, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    session.id,
                    session.document_id,
                    session.owner_id,
                    session.title,
                    session.created_at,
                ),
            )

    async def get_session(self, session_id: UUID) -> Session | None:
        row = await self._fetchone(
            "SELECT * FROM sot.sessions WHERE id = %s", (session_id,)
        )
        return _session(row) if row else None

    async def list_sessions(self, document_id: UUID) -> tuple[Session, ...]:
        rows = await self._fetchall(
            "SELECT * FROM sot.sessions WHERE document_id = %s ORDER BY created_at, id",
            (document_id,),
        )
        return tuple(_session(row) for row in rows)

    async def save_branch(self, branch: Branch) -> None:
        async with self._connection() as connection:
            await connection.execute(
                """
                INSERT INTO sot.branches
                    (id, session_id, owner_id, parent_branch_id,
                     source_toss_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    branch.id,
                    branch.session_id,
                    branch.owner_id,
                    branch.parent_branch_id,
                    branch.source_toss_id,
                    branch.created_at,
                ),
            )

    async def get_branch(self, branch_id: UUID) -> Branch | None:
        row = await self._fetchone(
            "SELECT * FROM sot.branches WHERE id = %s", (branch_id,)
        )
        return _branch(row) if row else None

    async def list_branches(self, session_id: UUID) -> tuple[Branch, ...]:
        rows = await self._fetchall(
            "SELECT * FROM sot.branches WHERE session_id = %s ORDER BY created_at, id",
            (session_id,),
        )
        return tuple(_branch(row) for row in rows)

    async def append_turns(self, turns: tuple[Turn, ...]) -> None:
        try:
            async with (
                self._connection() as connection,
                connection.cursor() as cursor,
            ):
                await cursor.executemany(
                    """
                    INSERT INTO sot.turns
                        (id, branch_id, ordinal, role, content, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        (
                            turn.id,
                            turn.branch_id,
                            turn.ordinal,
                            turn.role,
                            turn.content,
                            turn.created_at,
                        )
                        for turn in turns
                    ),
                )
        except UniqueViolation as error:
            raise DomainError(
                "turn_ordinal_conflict", "Turn ordinal already exists"
            ) from error

    async def list_turns(self, branch_id: UUID) -> tuple[Turn, ...]:
        rows = await self._fetchall(
            "SELECT * FROM sot.turns WHERE branch_id = %s ORDER BY ordinal",
            (branch_id,),
        )
        return tuple(_turn(row) for row in rows)

    async def get_turns(self, turn_ids: tuple[UUID, ...]) -> tuple[Turn, ...]:
        if not turn_ids:
            return ()
        rows = await self._fetchall(
            "SELECT * FROM sot.turns WHERE id = ANY(%s)", (list(turn_ids),)
        )
        by_id = {row["id"]: _turn(row) for row in rows}
        return tuple(by_id[turn_id] for turn_id in turn_ids if turn_id in by_id)

    async def save_cite(self, cite: Cite) -> None:
        async with self.transaction(), self._connection() as connection:
            await connection.execute(
                """
                INSERT INTO sot.cites
                    (id, branch_id, created_by, summary, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    cite.id,
                    cite.branch_id,
                    cite.created_by,
                    cite.summary,
                    cite.created_at,
                ),
            )
            async with connection.cursor() as cursor:
                await cursor.executemany(
                    """
                    INSERT INTO sot.cite_turns (cite_id, turn_id, ordinal)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        (cite.id, turn_id, ordinal)
                        for ordinal, turn_id in enumerate(cite.turn_ids, start=1)
                    ),
                )

    async def get_cite(self, cite_id: UUID) -> Cite | None:
        row = await self._fetchone(
            """
            SELECT c.*, array_agg(ct.turn_id ORDER BY ct.ordinal) AS turn_ids
            FROM sot.cites c
            JOIN sot.cite_turns ct ON ct.cite_id = c.id
            WHERE c.id = %s
            GROUP BY c.id
            """,
            (cite_id,),
        )
        return _cite(row) if row else None

    async def list_cites(self, branch_id: UUID) -> tuple[Cite, ...]:
        rows = await self._fetchall(
            """
            SELECT c.*, array_agg(ct.turn_id ORDER BY ct.ordinal) AS turn_ids
            FROM sot.cites c
            JOIN sot.cite_turns ct ON ct.cite_id = c.id
            WHERE c.branch_id = %s
            GROUP BY c.id
            ORDER BY c.created_at, c.id
            """,
            (branch_id,),
        )
        return tuple(_cite(row) for row in rows)

    async def save_toss(self, toss: Toss) -> None:
        try:
            async with self._connection() as connection:
                await connection.execute(
                    """
                    INSERT INTO sot.tosses
                        (id, cite_id, token, created_by, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        toss.id,
                        toss.cite_id,
                        toss.token,
                        toss.created_by,
                        toss.created_at,
                    ),
                )
        except UniqueViolation as error:
            raise DomainError(
                "toss_token_conflict", "Toss token already exists"
            ) from error

    async def get_toss_by_token(self, token: str) -> Toss | None:
        row = await self._fetchone(
            "SELECT * FROM sot.tosses WHERE token = %s", (token,)
        )
        return _toss(row) if row else None

    async def get_toss(self, toss_id: UUID) -> Toss | None:
        row = await self._fetchone("SELECT * FROM sot.tosses WHERE id = %s", (toss_id,))
        return _toss(row) if row else None

    async def save_proposal(self, proposal: Proposal) -> None:
        async with self._connection() as connection:
            await connection.execute(
                """
                INSERT INTO sot.proposals
                    (id, document_id, branch_id, created_by,
                     content, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status
                """,
                (
                    proposal.id,
                    proposal.document_id,
                    proposal.branch_id,
                    proposal.created_by,
                    proposal.content,
                    proposal.status.value,
                    proposal.created_at,
                ),
            )

    async def get_proposal(self, proposal_id: UUID) -> Proposal | None:
        row = await self._fetchone(
            "SELECT * FROM sot.proposals WHERE id = %s", (proposal_id,)
        )
        return _proposal(row) if row else None

    async def list_proposals(self, branch_id: UUID) -> tuple[Proposal, ...]:
        rows = await self._fetchall(
            "SELECT * FROM sot.proposals WHERE branch_id = %s ORDER BY created_at, id",
            (branch_id,),
        )
        return tuple(_proposal(row) for row in rows)

    async def add_approval(self, proposal_id: UUID, actor_id: str) -> None:
        row = await self._fetchone(
            "SELECT status FROM sot.proposals WHERE id = %s FOR UPDATE",
            (proposal_id,),
        )
        if row is None:
            raise DomainError("proposal_not_found", "Proposal does not exist")
        if row["status"] != ProposalStatus.OPEN.value:
            raise DomainError("proposal_closed", "Proposal is already published")
        try:
            async with self._connection() as connection:
                await connection.execute(
                    "INSERT INTO sot.approvals (proposal_id, actor_id) VALUES (%s, %s)",
                    (proposal_id, actor_id),
                )
        except UniqueViolation as error:
            raise DomainError(
                "approval_duplicate", "Actor already approved proposal"
            ) from error

    async def list_approvals(self, proposal_id: UUID) -> tuple[str, ...]:
        rows = await self._fetchall(
            """
            SELECT actor_id FROM sot.approvals
            WHERE proposal_id = %s ORDER BY created_at, actor_id
            """,
            (proposal_id,),
        )
        return tuple(cast(str, row["actor_id"]) for row in rows)


async def apply_migrations(pool: AsyncConnectionPool, migrations_path: Path) -> None:
    migrations = sorted(migrations_path.glob("*.sql"))
    if not migrations:
        raise RuntimeError(f"no migrations found in {migrations_path}")
    async with pool.connection() as connection, connection.transaction():
        for migration in migrations:
            await connection.execute(migration.read_text(encoding="utf-8"))


__all__ = ["PostgresSOTRepository", "apply_migrations"]
