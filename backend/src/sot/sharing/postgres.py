from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from sot.bootstrap.database import PostgresTransactionContext
from sot.shared.ids import BundleId, UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.sharing.domain import (
    AttributionSnapshot,
    PublicBundleItem,
    PublicBundleSnapshot,
    ShareLink,
    ShareLinkNotFound,
)


def connection(tx: TransactionContext) -> AsyncConnection[Any]:
    if not isinstance(tx, PostgresTransactionContext):
        raise TypeError("PostgreSQL transaction required")
    return tx.connection


def _link(row: tuple[Any, ...] | None) -> ShareLink | None:
    if row is None:
        return None
    snapshot = PublicBundleSnapshot(
        BundleId(row[2]),
        row[9],
        tuple(
            PublicBundleItem(
                tuple(UUID(value) for value in item["source_ids"]),
                item["role"],
                item["content"],
                item["provenance"],
            )
            for item in row[12]
        ),
        AttributionSnapshot(row[9], row[10], row[11]),
    )
    return ShareLink(
        row[0],
        WorkspaceId(row[1]),
        BundleId(row[2]),
        bytes(row[3]),
        UserId(row[4]),
        row[5],
        row[6],
        snapshot,
        UserId(row[7]) if row[7] else None,
        row[8],
    )


class PostgresShareLinkRepository:
    async def create_link(self, tx: TransactionContext, link: ShareLink) -> None:
        await connection(tx).execute(
            "INSERT INTO sot.sot_share_link(id,workspace_id,bundle_id,token_hash,created_by,created_at,expires_at,revoked_by,revoked_at,title,author_display_name,published_at,items) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                link.id,
                link.workspace_id,
                link.bundle_id,
                link.token_hash,
                link.created_by,
                link.created_at,
                link.expires_at,
                link.revoked_by,
                link.revoked_at,
                link.snapshot.title,
                link.snapshot.attribution.author_display_name,
                link.snapshot.attribution.published_at,
                Jsonb(
                    [
                        {
                            "source_ids": [str(value) for value in item.source_ids],
                            "role": item.role,
                            "content": item.content,
                            "provenance": item.provenance,
                        }
                        for item in link.snapshot.items
                    ]
                ),
            ),
        )

    async def find_link(
        self, tx: TransactionContext, workspace_id: WorkspaceId, link_id: UUID
    ) -> ShareLink | None:
        return _link(
            await (
                await connection(tx).execute(
                    "SELECT id,workspace_id,bundle_id,token_hash,created_by,created_at,expires_at,revoked_by,revoked_at,title,author_display_name,published_at,items FROM sot.sot_share_link WHERE workspace_id=%s AND id=%s",
                    (workspace_id, link_id),
                )
            ).fetchone()
        )

    async def save_link(self, tx: TransactionContext, link: ShareLink) -> None:
        cursor = await connection(tx).execute(
            "UPDATE sot.sot_share_link SET revoked_by=COALESCE(revoked_by,%s),revoked_at=COALESCE(revoked_at,%s) WHERE workspace_id=%s AND id=%s RETURNING id",
            (link.revoked_by, link.revoked_at, link.workspace_id, link.id),
        )
        if await cursor.fetchone() is None:
            raise ShareLinkNotFound()

    async def find_by_token_hash(
        self, tx: TransactionContext, token_hash: bytes
    ) -> ShareLink | None:
        return _link(
            await (
                await connection(tx).execute(
                    "SELECT id,workspace_id,bundle_id,token_hash,created_by,created_at,expires_at,revoked_by,revoked_at,title,author_display_name,published_at,items FROM sot.sot_share_link WHERE token_hash=%s",
                    (token_hash,),
                )
            ).fetchone()
        )
