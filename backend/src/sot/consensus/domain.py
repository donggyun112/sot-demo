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

# A proposal is read as a diff by every required approver before it can merge.
# Past a couple of screens that review stops happening, so the agent cannot
# grow one without bound. Every create/revise path builds a ProposalVersion,
# so this is the only place the cap has to be enforced.
PROPOSAL_CONTENT_LIMIT = 4000


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
class ProposalCitation:
    bundle_id: BundleId
    bundle_item_position: int
    claim_anchor: str

    def __post_init__(self) -> None:
        if self.bundle_item_position < 0 or not self.claim_anchor.strip():
            raise InvalidInput("proposal_citation_invalid", "Citation is invalid")


@dataclass(frozen=True, slots=True)
class DocumentEdit:
    """One anchored replacement against the base revision.

    `find` must occur exactly once in the document, so an edit names the place
    it changes instead of trusting a line number that the next merge moves. An
    empty `find` appends `replace` at the end, which is how the first section
    lands in a document that has nothing to anchor to yet.
    """

    find: str
    replace: str

    def __post_init__(self) -> None:
        if self.find == self.replace:
            raise InvalidInput("proposal_edit_invalid", "Edit changes nothing")
        if not self.find and not self.replace.strip():
            raise InvalidInput("proposal_edit_invalid", "Edit adds nothing")


@dataclass(frozen=True, slots=True)
class ProposalVersion:
    proposal_id: ProposalId
    version: int
    base_revision_id: UUID
    edits: tuple[DocumentEdit, ...]
    required_approver_ids: frozenset[UserId]
    bundle_ids: tuple[BundleId, ...]
    created_by: UserId
    created_at: datetime
    citations: tuple[ProposalCitation, ...]
    additional_approver_ids: frozenset[UserId] = frozenset()

    @property
    def added(self) -> str:
        """Everything this version puts into the document, for review limits."""
        return "\n".join(edit.replace for edit in self.edits)

    def apply(self, base: str) -> str:
        """The document as it would read if this version merged."""
        text = base
        for edit in self.edits:
            if not edit.find:
                text = f"{text.rstrip()}\n\n{edit.replace}" if text.strip() else edit.replace
                continue
            found = text.count(edit.find)
            if found == 0:
                raise InvalidInput(
                    "proposal_edit_not_found",
                    "The text this edit replaces is not in the document",
                )
            if found > 1:
                raise InvalidInput(
                    "proposal_edit_ambiguous",
                    "The text this edit replaces appears more than once; "
                    "include enough surrounding text to name one place",
                )
            text = text.replace(edit.find, edit.replace, 1)
        return text

    def __post_init__(self) -> None:
        if self.version < 1 or not self.edits or not self.required_approver_ids:
            raise InvalidInput(
                "proposal_version_invalid", "Proposal version is invalid"
            )
        if len(self.added) > PROPOSAL_CONTENT_LIMIT:
            raise InvalidInput(
                "proposal_content_too_long",
                f"Proposal content is {len(self.added)} characters; "
                f"keep it within {PROPOSAL_CONTENT_LIMIT} so approvers can review it",
            )
        if len(set(self.bundle_ids)) != len(self.bundle_ids):
            raise InvalidInput("proposal_bundles_invalid", "Duplicate proposal bundles")
        # A citation stands behind text this version ADDS. Anchoring it to
        # untouched document text would let a proposal claim evidence for
        # something it never wrote.
        if len(set(self.citations)) != len(self.citations) or any(
            citation.bundle_id not in self.bundle_ids
            or not any(citation.claim_anchor in edit.replace for edit in self.edits)
            for citation in self.citations
        ):
            raise InvalidInput(
                "proposal_citation_invalid", "Citation does not match proposal version"
            )
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
        edits: tuple[DocumentEdit, ...],
        required_approver_ids: frozenset[UserId],
        bundle_ids: tuple[BundleId, ...],
        citations: tuple[ProposalCitation, ...],
        now: datetime,
        additional_approver_ids: frozenset[UserId] = frozenset(),
    ) -> Proposal:
        cls._require_creator(created_by, required_approver_ids)
        proposal_id = ProposalId(uuid4())
        version = ProposalVersion(
            proposal_id,
            1,
            base_revision_id,
            edits,
            required_approver_ids,
            bundle_ids,
            created_by,
            now,
            citations,
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
        edits: tuple[DocumentEdit, ...],
        required_approver_ids: frozenset[UserId],
        bundle_ids: tuple[BundleId, ...],
        citations: tuple[ProposalCitation, ...],
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
            edits,
            required_approver_ids,
            bundle_ids,
            actor_id,
            now,
            citations,
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

    def require_approved(self, *, expected_version: int) -> None:
        self.require_version(expected_version)
        if self.status is not ProposalStatus.APPROVED:
            raise Conflict("proposal_not_approved", "Proposal version is not approved")

    def mark_stale(self, *, expected_version: int) -> Proposal:
        self.require_approved(expected_version=expected_version)
        return replace(self, status=ProposalStatus.STALE)

    def mark_merged(self, *, expected_version: int) -> Proposal:
        self.require_approved(expected_version=expected_version)
        return replace(self, status=ProposalStatus.MERGED)

    @staticmethod
    def _require_creator(creator: UserId, required: frozenset[UserId]) -> None:
        if creator not in required:
            raise InvalidInput(
                "proposal_creator_required", "Creator must remain required"
            )
