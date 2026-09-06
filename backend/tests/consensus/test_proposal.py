from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest

from sot.consensus.domain import ApprovalDecision, Proposal, ProposalStatus
from sot.shared.errors import Conflict, Forbidden, InvalidInput
from sot.shared.ids import BundleId, DocumentId, SessionId, UserId, WorkspaceId

NOW = datetime(2026, 9, 6, tzinfo=UTC)
ALICE = UserId(uuid4())
BOB = UserId(uuid4())
CAROL = UserId(uuid4())
BUNDLE = BundleId(uuid4())


def proposal() -> Proposal:
    return Proposal.create(
        workspace_id=WorkspaceId(uuid4()),
        document_id=DocumentId(uuid4()),
        source_session_id=SessionId(uuid4()),
        created_by=ALICE,
        base_revision_id=uuid4(),
        content="Initial proposal",
        required_approver_ids=frozenset({ALICE, BOB}),
        bundle_ids=(BUNDLE,),
        now=NOW,
    )


def test_only_all_required_approvals_approve_current_version() -> None:
    original = proposal()
    partial = original.decide(
        actor_id=ALICE, expected_version=1, decision=ApprovalDecision.APPROVE, now=NOW
    )
    approved = partial.decide(
        actor_id=BOB, expected_version=1, decision=ApprovalDecision.APPROVE, now=NOW
    )
    assert original.approvals == ()
    assert partial.status is ProposalStatus.OPEN
    assert approved.status is ProposalStatus.APPROVED
    assert approved.version == 1
    assert {
        (a.proposal_id, a.version, a.approver_user_id) for a in approved.approvals
    } == {
        (original.id, 1, ALICE),
        (original.id, 1, BOB),
    }


def test_revision_resets_approval_status_and_preserves_history() -> None:
    previous = proposal().decide(
        actor_id=ALICE, expected_version=1, decision=ApprovalDecision.REJECT, now=NOW
    )
    revised = previous.revise(
        actor_id=BOB,
        expected_version=1,
        base_revision_id=uuid4(),
        content="Revised",
        required_approver_ids=frozenset({ALICE, BOB, CAROL}),
        bundle_ids=(),
        now=NOW,
    )
    assert previous.status is ProposalStatus.REJECTED
    assert revised.status is ProposalStatus.OPEN
    assert revised.version == 2
    assert revised.approvals_for_current_version == ()
    assert revised.versions[0] == previous.current_version
    assert revised.approvals == previous.approvals
    assert revised.current_version.bundle_ids == ()
    assert revised.required_approvers == frozenset({ALICE, BOB, CAROL})


def test_approver_and_bundle_snapshots_and_source_binding_are_immutable() -> None:
    subject = proposal()
    with pytest.raises(FrozenInstanceError):
        subject.source_session_id = SessionId(uuid4())  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        subject.current_version.content = "tamper"  # type: ignore[misc]
    assert subject.required_approvers == frozenset({ALICE, BOB})
    assert subject.current_version.bundle_ids == (BUNDLE,)


@pytest.mark.parametrize("decision", list(ApprovalDecision))
def test_only_required_approvers_can_decide(decision: ApprovalDecision) -> None:
    with pytest.raises(Forbidden, match="approver"):
        proposal().decide(
            actor_id=CAROL, expected_version=1, decision=decision, now=NOW
        )


def test_duplicate_decision_and_old_version_are_conflicts() -> None:
    partial = proposal().decide(
        actor_id=ALICE, expected_version=1, decision=ApprovalDecision.APPROVE, now=NOW
    )
    with pytest.raises(Conflict, match="already"):
        partial.decide(
            actor_id=ALICE,
            expected_version=1,
            decision=ApprovalDecision.REJECT,
            now=NOW,
        )
    revised = partial.revise(
        actor_id=BOB,
        expected_version=1,
        base_revision_id=uuid4(),
        content="Revised",
        required_approver_ids=frozenset({ALICE, BOB}),
        bundle_ids=(),
        now=NOW,
    )
    with pytest.raises(Conflict, match="changed"):
        revised.decide(
            actor_id=BOB, expected_version=1, decision=ApprovalDecision.APPROVE, now=NOW
        )
    with pytest.raises(Conflict, match="changed"):
        revised.revise(
            actor_id=BOB,
            expected_version=1,
            base_revision_id=uuid4(),
            content="Old",
            required_approver_ids=frozenset({ALICE, BOB}),
            bundle_ids=(),
            now=NOW,
        )


def test_reject_closes_version_for_further_decisions() -> None:
    rejected = proposal().decide(
        actor_id=BOB, expected_version=1, decision=ApprovalDecision.REJECT, now=NOW
    )
    with pytest.raises(Conflict, match="open"):
        rejected.decide(
            actor_id=ALICE,
            expected_version=1,
            decision=ApprovalDecision.APPROVE,
            now=NOW,
        )


@pytest.mark.parametrize(
    "content,required",
    [(" ", frozenset({ALICE})), ("Text", frozenset()), ("Text", frozenset({BOB}))],
)
def test_invalid_content_or_omitted_creator_is_rejected(
    content: str,
    required: frozenset[UserId],
) -> None:
    with pytest.raises(InvalidInput):
        proposal().revise(
            actor_id=ALICE,
            expected_version=1,
            base_revision_id=uuid4(),
            content=content,
            required_approver_ids=required,
            bundle_ids=(),
            now=NOW,
        )


def test_version_preserves_explicit_approvers_separately_from_mandatory_set() -> None:
    original = proposal()
    revised = original.revise(
        actor_id=ALICE,
        expected_version=1,
        base_revision_id=uuid4(),
        content="Revised",
        required_approver_ids=frozenset({ALICE, BOB, CAROL}),
        additional_approver_ids=frozenset({CAROL}),
        bundle_ids=(),
        now=NOW,
    )
    assert revised.current_version.additional_approver_ids == frozenset({CAROL})
    assert original.current_version.additional_approver_ids == frozenset()
    with pytest.raises(InvalidInput):
        original.revise(
            actor_id=ALICE,
            expected_version=1,
            base_revision_id=uuid4(),
            content="Invalid",
            required_approver_ids=frozenset({ALICE, BOB}),
            additional_approver_ids=frozenset({CAROL}),
            bundle_ids=(),
            now=NOW,
        )


def test_invalid_decision_never_counts_as_approval() -> None:
    partial = proposal().decide(
        actor_id=ALICE,
        expected_version=1,
        decision=ApprovalDecision.APPROVE,
        now=NOW,
    )
    with pytest.raises(InvalidInput):
        partial.decide(
            actor_id=BOB,
            expected_version=1,
            decision=cast(ApprovalDecision, "not-a-decision"),
            now=NOW,
        )
