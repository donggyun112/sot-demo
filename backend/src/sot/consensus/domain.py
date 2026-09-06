from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sot.shared.errors import Conflict, Forbidden, InvalidInput, NotFound
from sot.shared.ids import (
    BundleId,
    DocumentId,
    ProposalId,
    SessionId,
    UserId,
    WorkspaceId,
)


class ProposalStatus(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"
    MERGED = "merged"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ProposalNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("proposal_not_found", "Proposal not found")


class ProposalVersionConflict(Conflict):
    def __init__(self) -> None:
        super().__init__(
            "proposal_version_conflict", "Proposal changed after it was loaded"
        )


@dataclass(frozen=True, slots=True)
class ProposalVersion:
    proposal_id: ProposalId
    version: int
    base_revision_id: UUID
    content: str
    required_approver_ids: frozenset[UserId]
    bundle_ids: tuple[BundleId, ...]
    created_by: UserId
    created_at: datetime
    additional_approver_ids: frozenset[UserId] = frozenset()

    def __post_init__(self) -> None:
        if (
            self.version < 1
            or not self.content.strip()
            or not self.required_approver_ids
        ):
            raise InvalidInput(
                "proposal_version_invalid", "Proposal version is invalid"
            )
        if len(set(self.bundle_ids)) != len(self.bundle_ids):
            raise InvalidInput("proposal_bundles_invalid", "Duplicate proposal bundles")
        if not self.additional_approver_ids <= self.required_approver_ids:
            raise InvalidInput(
                "proposal_approvers_invalid", "Additional approvers must be required"
            )


@dataclass(frozen=True, slots=True)
class Approval:
    proposal_id: ProposalId
    version: int
    approver_user_id: UserId
    decision: ApprovalDecision
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class Proposal:
    id: ProposalId
    workspace_id: WorkspaceId
    document_id: DocumentId
    source_session_id: SessionId
    created_by: UserId
    created_at: datetime
    versions: tuple[ProposalVersion, ...]
    approvals: tuple[Approval, ...] = ()
    status: ProposalStatus = ProposalStatus.OPEN

    @classmethod
    def create(
        cls,
        *,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        source_session_id: SessionId,
        created_by: UserId,
        base_revision_id: UUID,
        content: str,
        required_approver_ids: frozenset[UserId],
        bundle_ids: tuple[BundleId, ...],
        now: datetime,
        additional_approver_ids: frozenset[UserId] = frozenset(),
    ) -> Proposal:
        cls._require_creator(created_by, required_approver_ids)
        proposal_id = ProposalId(uuid4())
        version = ProposalVersion(
            proposal_id,
            1,
            base_revision_id,
            content,
            required_approver_ids,
            bundle_ids,
            created_by,
            now,
            additional_approver_ids,
        )
        return cls(
            proposal_id,
            workspace_id,
            document_id,
            source_session_id,
            created_by,
            now,
            (version,),
        )

    @property
    def current_version(self) -> ProposalVersion:
        return self.versions[-1]

    @property
    def version(self) -> int:
        return self.current_version.version

    @property
    def required_approvers(self) -> frozenset[UserId]:
        return self.current_version.required_approver_ids

    @property
    def approvals_for_current_version(self) -> tuple[Approval, ...]:
        return tuple(a for a in self.approvals if a.version == self.version)

    def require_version(self, expected_version: int) -> None:
        if self.version != expected_version:
            raise ProposalVersionConflict()

    def revise(
        self,
        *,
        actor_id: UserId,
        expected_version: int,
        base_revision_id: UUID,
        content: str,
        required_approver_ids: frozenset[UserId],
        bundle_ids: tuple[BundleId, ...],
        now: datetime,
        additional_approver_ids: frozenset[UserId] = frozenset(),
    ) -> Proposal:
        self.require_version(expected_version)
        if self.status is ProposalStatus.MERGED:
            raise Conflict("proposal_merged", "Merged proposal cannot be revised")
        self._require_creator(self.created_by, required_approver_ids)
        version = ProposalVersion(
            self.id,
            self.version + 1,
            base_revision_id,
            content,
            required_approver_ids,
            bundle_ids,
            actor_id,
            now,
            additional_approver_ids,
        )
        return replace(
            self, versions=(*self.versions, version), status=ProposalStatus.OPEN
        )

    def decide(
        self,
        *,
        actor_id: UserId,
        expected_version: int,
        decision: ApprovalDecision,
        now: datetime,
    ) -> Proposal:
        self.require_version(expected_version)
        if actor_id not in self.required_approvers:
            raise Forbidden("proposal_approver_required", "Required approver only")
        if any(
            a.approver_user_id == actor_id for a in self.approvals_for_current_version
        ):
            raise Conflict("proposal_already_decided", "Approver already decided")
        if self.status is not ProposalStatus.OPEN:
            raise Conflict("proposal_not_open", "Proposal version is not open")
        if not isinstance(decision, ApprovalDecision):
            raise InvalidInput(
                "proposal_decision_invalid", "Proposal decision is invalid"
            )
        approval = Approval(self.id, self.version, actor_id, decision, now)
        status = ProposalStatus.OPEN
        if decision is ApprovalDecision.REJECT:
            status = ProposalStatus.REJECTED
        elif len(self.approvals_for_current_version) + 1 == len(
            self.required_approvers
        ):
            status = ProposalStatus.APPROVED
        return replace(self, approvals=(*self.approvals, approval), status=status)

    @staticmethod
    def _require_creator(creator: UserId, required: frozenset[UserId]) -> None:
        if creator not in required:
            raise InvalidInput(
                "proposal_creator_required", "Creator must remain required"
            )
