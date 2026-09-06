from __future__ import annotations

from typing import Protocol

from sot.consensus.domain import Proposal
from sot.shared.ids import ProposalId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext


class ProposalRepository(Protocol):
    async def find(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
    ) -> Proposal | None: ...

    async def get_for_update(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
    ) -> Proposal | None:
        """Lock the scoped aggregate until tx ends, before reading versions/decisions.

        Every existing-proposal command uses this lock and then checks the expected
        version. Concurrent decisions for one version must see earlier decisions.
        """
        ...

    async def add(self, tx: TransactionContext, proposal: Proposal) -> None:
        """Insert identity, immutable version, approver and ordered citation snapshots."""
        ...

    async def save(self, tx: TransactionContext, proposal: Proposal) -> None:
        """Save under get_for_update's lock in the same tx, without committing.

        Preserve source identity and existing version/approval records. Append only
        new versions and decisions; update aggregate current-version/status. The
        unique decision key is (proposal_id, version, approver_user_id).
        Persist citations by (proposal_id, version, position), preserving supplied
        order and all claim_anchor/bundle_id/bundle_item_position values. Existing
        version citations are immutable and never overwritten on status updates.
        """
        ...
