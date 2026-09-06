from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sot.shared.ids import WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.sharing.domain import ShareLink


class ShareLinkRepository(Protocol):
    """Own immutable public snapshots; persist only the hashed capability token."""

    async def create_link(self, tx: TransactionContext, link: ShareLink) -> None: ...

    async def find_link(
        self, tx: TransactionContext, workspace_id: WorkspaceId, link_id: UUID
    ) -> ShareLink | None: ...

    async def save_link(self, tx: TransactionContext, link: ShareLink) -> None:
        """Persist revocation only, preserving the original snapshot and token hash."""
        ...

    async def find_by_token_hash(
        self, tx: TransactionContext, token_hash: bytes
    ) -> ShareLink | None:
        """Read sharing-owned state only; no source session/identity authorization."""
        ...
