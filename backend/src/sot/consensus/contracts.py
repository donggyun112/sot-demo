from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sot.consensus.domain import (
    PROPOSAL_CONTENT_LIMIT,
    PROPOSAL_LINE_LIMIT,
    Approval,
    ApprovalDecision,
    DocumentEdit,
    ProposalCitation,
    ProposalStatus,
    ProposalVersion,
)
from sot.document.contracts import RevisionResult
from sot.identity.contracts import Actor
from sot.session.contracts import BranchMutationResult
from sot.shared.ids import (
    BranchId,
    DocumentId,
    ProposalId,
    SessionId,
    UserId,
    WorkspaceId,
)
from sot.shared.unit_of_work import TransactionContext


@dataclass(frozen=True, slots=True)
class ProposalView:
    """Current proposal only; never includes private session or bundle contents."""

    id: ProposalId
    workspace_id: WorkspaceId
    document_id: DocumentId
    source_session_id: SessionId
    created_by: UserId
    created_at: datetime
    current_version: ProposalVersion
    status: ProposalStatus
    approvals: tuple[Approval, ...]

    @property
    def version(self) -> int:
        return self.current_version.version


@dataclass(frozen=True, slots=True)
class MergeProposalResult:
    """Publication projection for publishers without private source-session access."""

    proposal_id: ProposalId
    version: int
    status: ProposalStatus
    publication: RevisionResult | None


class ProposalReader(Protocol):
    async def require_proposal(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
    ) -> ProposalView: ...


class ProposalCreator(Protocol):
    async def create_from_agent(
        self,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_branch_version: int,
        edits: tuple[DocumentEdit, ...],
    ) -> BranchMutationResult: ...


__all__ = [
    "PROPOSAL_CONTENT_LIMIT",
    "PROPOSAL_LINE_LIMIT",
    "Approval",
    "ApprovalDecision",
    "DocumentEdit",
    "MergeProposalResult",
    "ProposalCitation",
    "ProposalCreator",
    "ProposalReader",
    "ProposalStatus",
    "ProposalVersion",
    "ProposalView",
]
