"""Controlled application scenarios and disposable PostgreSQL concurrency evidence."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from sot.bootstrap.app import SystemClock
from sot.bootstrap.database import PostgresTransactionContext
from sot.consensus.application import MergeProposal
from sot.consensus.domain import Proposal, ProposalStatus
from sot.consensus.postgres import PostgresProposalRepository
from sot.document.application import DocumentPublicationAccess, PublishDocumentRevision
from sot.document.contracts import DocumentView
from sot.identity.contracts import Actor
from sot.shared.errors import Conflict
from sot.shared.ids import DocumentId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.application import WorkspaceAccess
from sot.workspace.postgres import PostgresWorkspaceRepository
from tests.consensus.merge_support import MergeHarness
from tests.consensus.test_application import CAROL, WORKSPACE
from tests.integration.test_consensus_postgres import SharingConsensus
from tests.integration.test_consensus_postgres import (
    consensus as consensus,  # noqa: PLC0414 -- shared fixture
)
from tests.integration.test_document_session_postgres import (
    state as state,  # noqa: PLC0414 -- shared fixture
)


class ConcurrentUow:
    def __init__(
        self, env: SharingConsensus, barrier: asyncio.Barrier, pids: set[int]
    ) -> None:
        self.env, self.barrier, self.pids = env, barrier, pids

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        async with self.env.state.uow().transaction() as tx:
            assert isinstance(tx, PostgresTransactionContext)
            self.pids.add(tx.connection.info.backend_pid)
            await self.barrier.wait()
            yield tx


class ConcurrentPublicationAccess(DocumentPublicationAccess):
    barrier: asyncio.Barrier | None = None

    async def require_document(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> DocumentView:
        if self.barrier is not None:
            await self.barrier.wait()
        return await super().require_document(
            tx, actor=actor, workspace_id=workspace_id, document_id=document_id
        )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("same_proposal", [True, False])
async def test_live_concurrent_merge_separate_connections(
    consensus: SharingConsensus, same_proposal: bool
) -> None:
    e, s = consensus, consensus.state
    first = await e.approved()
    second = first if same_proposal else await e.approved()
    barrier, pids = asyncio.Barrier(2), set[int]()
    members = WorkspaceAccess(PostgresWorkspaceRepository())
    documents = ConcurrentPublicationAccess(s.documents, members)
    if not same_proposal:
        documents.barrier = asyncio.Barrier(2)
    merge = MergeProposal(
        e.proposals,
        members,
        documents,
        PublishDocumentRevision(s.documents, members, SystemClock()),
        lambda: ConcurrentUow(e, barrier, pids),
    )
    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                merge.execute(s.other, s.workspace_id, pid, expected_version=1)
                for pid in (first, second)
            ),
            return_exceptions=True,
        ),
        timeout=10,
    )
    assert len(pids) == 2
    if same_proposal:
        conflicts = [r for r in results if isinstance(r, Conflict)]
        assert len(conflicts) == 1 and conflicts[0].code == "proposal_not_approved"
        assert sum(not isinstance(r, BaseException) for r in results) == 1
    else:
        assert not any(isinstance(r, BaseException) for r in results)
        assert {r.status for r in results if not isinstance(r, BaseException)} == {
            ProposalStatus.MERGED,
            ProposalStatus.STALE,
        }
    async with s.uow().transaction() as tx:
        assert isinstance(tx, PostgresTransactionContext)
        assert await (
            await tx.connection.execute(
                "SELECT count(*) FROM sot.sot_document_revision WHERE document_id=%s",
                (s.document_id,),
            )
        ).fetchone() == (2,)
        assert await (
            await tx.connection.execute(
                "SELECT count(*) FROM sot.sot_revision_citation WHERE workspace_id=%s",
                (s.workspace_id,),
            )
        ).fetchone() == (2,)
        document = await s.documents.get(tx, s.workspace_id, s.document_id)
        assert (
            document
            and document.document.version == 2
            and len(document.current_revision.citations) == 2
        )


class FailingProposalSave(PostgresProposalRepository):
    async def save(self, tx: TransactionContext, proposal: Proposal) -> None:
        await super().save(tx, proposal)
        if proposal.status is ProposalStatus.MERGED:
            raise RuntimeError("injected final proposal save failure")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_live_merge_rollback_has_no_orphan_revision_or_citations(
    consensus: SharingConsensus,
) -> None:
    e, s = consensus, consensus.state
    pid = await e.approved()
    members = WorkspaceAccess(PostgresWorkspaceRepository())
    merge = MergeProposal(
        FailingProposalSave(),
        members,
        DocumentPublicationAccess(s.documents, members),
        PublishDocumentRevision(s.documents, members, SystemClock()),
        s.uow,
    )
    with pytest.raises(RuntimeError, match="injected"):
        await merge.execute(s.other, s.workspace_id, pid, expected_version=1)
    async with s.uow().transaction() as tx:
        assert isinstance(tx, PostgresTransactionContext)
        assert await (
            await tx.connection.execute(
                "SELECT count(*) FROM sot.sot_document_revision WHERE document_id=%s",
                (s.document_id,),
            )
        ).fetchone() == (1,)
        assert await (
            await tx.connection.execute(
                "SELECT count(*) FROM sot.sot_revision_citation WHERE workspace_id=%s",
                (s.workspace_id,),
            )
        ).fetchone() == (0,)
        proposal = await e.proposals.find(tx, s.workspace_id, pid)
        document = await s.documents.get(tx, s.workspace_id, s.document_id)
        assert proposal and proposal.status is ProposalStatus.APPROVED
        assert document and document.document.version == 1
    assert (
        await e.merge.execute(s.other, s.workspace_id, pid, expected_version=1)
    ).status is ProposalStatus.MERGED


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
