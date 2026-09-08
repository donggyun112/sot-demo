from dataclasses import replace
from uuid import uuid4

import pytest

from sot.consensus.domain import (
    ApprovalDecision,
    DocumentEdit,
    ProposalNotFound,
    ProposalStatus,
)
from sot.document.domain import DocumentNotFound
from sot.identity.contracts import Actor
from sot.session.contracts import SessionPermission
from sot.shared.errors import Conflict, NotFound
from sot.shared.ids import DocumentId, ProposalId, WorkspaceId
from sot.workspace.domain import WorkspaceForbidden
from tests.consensus.merge_support import MergeHarness
from tests.consensus.test_application import (
    ALICE,
    BOB,
    BUNDLE,
    CAROL,
    SESSION,
    WORKSPACE,
)


@pytest.mark.asyncio
async def test_last_approval_does_not_publish_main() -> None:
    env = MergeHarness()
    proposal_id = await env.initial(approve=False)
    base = env.store.document.current_revision_id
    for actor in (ALICE, BOB):
        result = await env.decide.execute(
            Actor(actor),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            decision=ApprovalDecision.APPROVE,
        )
    assert result.status is ProposalStatus.APPROVED
    assert env.store.document.current_revision_id == base
    assert len(env.store.revisions) == 1


@pytest.mark.asyncio
async def test_publisher_without_private_membership_merges_only_approved_evidence() -> (
    None
):
    env = MergeHarness()
    proposal_id = await env.initial()
    async with env.store.transaction() as tx:
        with pytest.raises(NotFound):
            await env.access.require(
                tx,
                actor=Actor(CAROL),
                workspace_id=WORKSPACE,
                session_id=SESSION,
                permission=SessionPermission.READ,
            )
    private_reads = env.access.session_reads, env.access.bundle_reads
    transactions, commits = env.store.transactions, env.store.commits
    # Publication must survive private access loss after the version was approved.
    env.access.bundle_ids.clear()
    result = await env.merge.execute(
        Actor(CAROL), WORKSPACE, proposal_id, expected_version=1
    )
    assert result.proposal_id == proposal_id
    assert result.version == 1
    assert result.status is ProposalStatus.MERGED
    assert result.publication is not None
    revision = result.publication.revision
    # The proposal APPENDS: merging leaves the document it was written
    # against in place instead of overwriting it.
    assert revision.content == "Main\n\nProposed main"
    assert revision.created_by == CAROL
    assert revision.proposal_id == proposal_id
    assert tuple(
        (c.bundle_id, c.bundle_item_position, c.claim_anchor)
        for c in revision.citations
    ) == ((BUNDLE, 1, "main"), (BUNDLE, 0, "Proposed"))
    assert env.store.document.current_revision_id == revision.id
    assert env.store.document.version == 2
    assert len(env.store.revisions) == 2
    assert env.store.proposals[proposal_id].status is ProposalStatus.MERGED
    assert env.store.transactions == transactions + 1
    assert env.store.commits == commits + 1
    assert (env.access.session_reads, env.access.bundle_reads) == private_reads
    assert not hasattr(result, "source_session_id")
    assert not hasattr(result, "proposal")


@pytest.mark.asyncio
async def test_nonpublisher_cannot_distinguish_existing_from_missing_proposal() -> None:
    env = MergeHarness()
    proposal_id = await env.initial()
    errors = []
    for target in (proposal_id, ProposalId(uuid4())):
        with pytest.raises(WorkspaceForbidden) as caught:
            await env.merge.execute(
                Actor(ALICE), WORKSPACE, target, expected_version=999
            )
        errors.append((caught.value.code, caught.value.message))
    assert errors[0] == errors[1]
    assert len(env.store.revisions) == 1
    assert env.store.proposals[proposal_id].status is ProposalStatus.APPROVED


@pytest.mark.asyncio
async def test_merge_scopes_proposal_and_document_identity() -> None:
    env = MergeHarness()
    proposal_id = await env.initial()
    with pytest.raises(NotFound):
        await env.merge.execute(
            Actor(CAROL), WorkspaceId(uuid4()), proposal_id, expected_version=1
        )
    with pytest.raises(ProposalNotFound):
        await env.merge.execute(
            Actor(CAROL), WORKSPACE, ProposalId(uuid4()), expected_version=1
        )
    env.store.proposals[proposal_id] = replace(
        env.store.proposals[proposal_id], document_id=DocumentId(uuid4())
    )
    with pytest.raises(DocumentNotFound):
        await env.merge.execute(
            Actor(CAROL), WORKSPACE, proposal_id, expected_version=1
        )
    assert len(env.store.revisions) == 1
    assert env.store.proposals[proposal_id].status is ProposalStatus.APPROVED


@pytest.mark.asyncio
async def test_base_change_marks_stale_and_commits_without_publication() -> None:
    env = MergeHarness()
    proposal_id = await env.initial()
    competing = env.store.document.publish(
        content="Another main",
        proposal_id=ProposalId(uuid4()),
        citations=(),
        actor_id=CAROL,
        expected_version=1,
        now=env.store.revisions[0].created_at,
    )
    env.store.revisions.append(competing)
    commits = env.store.commits
    result = await env.merge.execute(
        Actor(CAROL), WORKSPACE, proposal_id, expected_version=1
    )
    assert result.status is ProposalStatus.STALE
    assert result.publication is None
    assert env.store.proposals[proposal_id].status is ProposalStatus.STALE
    assert env.store.document.current_revision_id == competing.id
    assert len(env.store.revisions) == 2
    assert env.store.commits == commits + 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        ProposalStatus.OPEN,
        ProposalStatus.REJECTED,
        ProposalStatus.STALE,
        ProposalStatus.MERGED,
    ],
)
async def test_only_current_approved_version_can_merge(status: ProposalStatus) -> None:
    env = MergeHarness()
    proposal_id = await env.initial()
    with pytest.raises(Conflict) as caught:
        await env.merge.execute(
            Actor(CAROL), WORKSPACE, proposal_id, expected_version=2
        )
    assert caught.value.code == "proposal_version_conflict"
    env.store.proposals[proposal_id] = replace(
        env.store.proposals[proposal_id], status=status
    )
    with pytest.raises(Conflict) as caught:
        await env.merge.execute(
            Actor(CAROL), WORKSPACE, proposal_id, expected_version=1
        )
    assert caught.value.code == "proposal_not_approved"
    assert len(env.store.revisions) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["revision", "proposal", "commit", "conflict"])
async def test_failure_rolls_back_revision_citations_pointer_and_proposal(
    failure: str,
) -> None:
    env = MergeHarness()
    proposal_id = await env.initial()
    document, revisions = replace(env.store.document), list(env.store.revisions)
    proposal, commits = env.store.proposals[proposal_id], env.store.commits
    env.store.failure = failure
    env.store.fail_save = failure == "proposal"
    with pytest.raises((RuntimeError, Conflict)):
        await env.merge.execute(
            Actor(CAROL), WORKSPACE, proposal_id, expected_version=1
        )
    assert env.store.document == document
    assert env.store.revisions == revisions
    assert env.store.proposals[proposal_id] == proposal
    assert env.store.commits == commits
