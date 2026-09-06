"""Application integration with controlled transactions, not PostgreSQL concurrency.

Task 5 adds separate-connection PostgreSQL evidence for the same scenarios.
"""

import asyncio

import pytest

from sot.consensus.domain import ProposalStatus
from sot.identity.contracts import Actor
from sot.shared.errors import Conflict
from tests.consensus.merge_support import MergeHarness
from tests.consensus.test_application import CAROL, WORKSPACE


@pytest.mark.asyncio
async def test_controlled_concurrent_merge_publishes_one_revision_and_citation_set() -> (
    None
):
    env = MergeHarness()
    proposal_id = await env.initial()
    env.store.barrier = asyncio.Barrier(2)
    results = await asyncio.gather(
        *(
            env.merge.execute(Actor(CAROL), WORKSPACE, proposal_id, expected_version=1)
            for _ in range(2)
        ),
        return_exceptions=True,
    )
    conflicts = [result for result in results if isinstance(result, Conflict)]
    assert len(conflicts) == 1
    assert conflicts[0].code == "proposal_not_approved"
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert len(env.store.revisions) == 2
    assert len(env.store.revisions[-1].citations) == 2
    assert env.store.document.version == 2
    assert env.store.document.current_revision_id == env.store.revisions[-1].id
    assert env.store.proposals[proposal_id].status is ProposalStatus.MERGED


@pytest.mark.asyncio
async def test_controlled_competing_proposals_leave_second_base_stale() -> None:
    env = MergeHarness()
    proposal_ids = [await env.initial(), await env.initial()]
    env.store.barrier = asyncio.Barrier(2)
    results = await asyncio.gather(
        *(
            env.merge.execute(Actor(CAROL), WORKSPACE, proposal_id, expected_version=1)
            for proposal_id in proposal_ids
        )
    )
    assert {result.status for result in results} == {
        ProposalStatus.MERGED,
        ProposalStatus.STALE,
    }
    assert len(env.store.revisions) == 2
    assert len(env.store.revisions[-1].citations) == 2
    assert env.store.document.version == 2
