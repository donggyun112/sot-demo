from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any
from uuid import uuid4

import httpx
import psycopg
import pytest
import pytest_asyncio
from pydantic import SecretStr

from sot.bootstrap.app import SystemClock, build_app
from sot.bootstrap.database import PostgresTransactionContext
from sot.bootstrap.settings import Settings
from sot.consensus.application import (
    CreateProposal,
    DecideProposal,
    MergeProposal,
    ProposalSources,
    ReviseProposal,
)
from sot.consensus.domain import (
    ApprovalDecision,
    DocumentEdit,
    ProposalStatus,
)
from sot.consensus.postgres import PostgresProposalRepository
from sot.document.application import (
    DocumentAccess,
    DocumentPublicationAccess,
    PublishDocumentRevision,
)
from sot.identity.tokens import SOTAccessTokenCodec
from sot.session.application import (
    AppendCompletedTurns,
    BundleAccess,
    FreezeEvidence,
    RequiredApprovers,
    SessionAccess,
    VersionGuard,
)
from sot.session.domain import Bundle, BundleItem, NewTurn
from sot.shared.ids import BundleId, ProposalId, UserId
from sot.workspace.application import WorkspaceAccess
from sot.workspace.domain import WorkspaceMembership, WorkspaceRole
from sot.workspace.postgres import PostgresWorkspaceRepository
from tests.integration.test_document_session_postgres import NOW, Harness
from tests.integration.test_document_session_postgres import (
    state as state,  # noqa: PLC0414 -- shared fixture
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
SECRET = "integration-only-sharing-consensus-secret-1234567890"


@dataclass
class SharingConsensus:
    state: Harness
    bundle: Bundle
    proposals: PostgresProposalRepository
    create: CreateProposal
    revise: ReviseProposal
    decide: DecideProposal
    merge: MergeProposal

    async def approved(self) -> ProposalId:
        s = self.state
        proposal = await self.create.execute(
            s.owner,
            s.workspace_id,
            s.session.id,
            document_id=s.document_id,
            edits=(DocumentEdit("", "First claim. Second claim."),),
            branch_id=s.branch.id,
        )
        await self.decide.execute(
            s.owner,
            s.workspace_id,
            proposal.id,
            expected_version=1,
            decision=ApprovalDecision.APPROVE,
        )
        return proposal.id


@pytest_asyncio.fixture
async def consensus(state: Harness) -> SharingConsensus:
    s = state
    members = WorkspaceAccess(PostgresWorkspaceRepository())
    sessions = SessionAccess(s.sessions, members)
    bundles = BundleAccess(s.sessions, sessions, members)
    documents = DocumentAccess(s.documents, members)
    sources = ProposalSources(
        sessions,
        documents,
        bundles,
        RequiredApprovers(s.sessions),
        members,
        # The real thing: a proposal freezes the conversation it came out of.
        FreezeEvidence(s.sessions, s.sessions, s.reader(), SystemClock()),
    )
    proposals = PostgresProposalRepository()
    bundle = Bundle.publish(
        s.branch,
        (
            BundleItem((uuid4(),), "user", "public question", "copied"),
            BundleItem((uuid4(),), "assistant", "public answer", "edited"),
        ),
        s.owner.user_id,
        NOW,
        title="Frozen title",
    )
    # A session with a conversation in it: an update proposed from this branch
    # records those turns as the grounds it was written from.
    await AppendCompletedTurns(s.sessions, s.reader(), s.uow, SystemClock()).execute(
        s.owner,
        s.workspace_id,
        s.branch.id,
        expected_version=0,
        messages=(
            NewTurn("user", "what should the limit be?"),
            NewTurn("assistant", "five to ten per second is usual"),
        ),
    )
    async with s.uow().transaction() as tx:
        await s.sessions.create_bundle(tx, s.workspace_id, bundle)
        await PostgresWorkspaceRepository().add_member(
            tx,
            WorkspaceMembership(s.workspace_id, s.other.user_id, WorkspaceRole.OWNER),
        )
    return SharingConsensus(
        s,
        bundle,
        proposals,
        CreateProposal(
            proposals,
            sources,
            s.reader(),
            VersionGuard(s.sessions, s.reader()),
            s.uow,
            SystemClock(),
        ),
        ReviseProposal(proposals, sources, s.uow, SystemClock()),
        DecideProposal(proposals, members, s.uow, SystemClock()),
        MergeProposal(
            proposals,
            members,
            DocumentPublicationAccess(s.documents, members),
            PublishDocumentRevision(s.documents, members, SystemClock()),
            s.uow,
        ),
    )


@pytest_asyncio.fixture
async def api(
    consensus: SharingConsensus, database_url: str
) -> AsyncIterator[httpx.AsyncClient]:
    app = build_app(
        Settings(
            environment="production",
            google_client_id="configured-client",
            database_url=database_url,
            models=("test",),
            access_token_secret=SecretStr(SECRET),
        )
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client,
    ):
        yield client


def bearer(user_id: UserId) -> dict[str, str]:
    return {
        "Authorization": "Bearer "
        + SOTAccessTokenCodec(SECRET, SystemClock(), timedelta(minutes=5)).encode(
            user_id
        )
    }


async def test_version_citations_roundtrip_and_decision_uniqueness(
    consensus: SharingConsensus,
) -> None:
    e, s = consensus, consensus.state
    pid = await e.approved()
    async with s.uow().transaction() as tx:
        before = await e.proposals.find(tx, s.workspace_id, pid)
        assert before is not None and before.status is ProposalStatus.APPROVED
        assert await e.proposals.find(tx, s.other_workspace_id, pid) is None
    await e.revise.execute(
        s.owner,
        s.workspace_id,
        pid,
        expected_version=1,
        edits=(DocumentEdit("", "Third claim"),),
        branch_id=s.branch.id,
    )
    await e.decide.execute(
        s.owner,
        s.workspace_id,
        pid,
        expected_version=2,
        decision=ApprovalDecision.APPROVE,
    )
    async with s.uow().transaction() as tx:
        after = await e.proposals.find(tx, s.workspace_id, pid)
        assert after and after.versions[0] == before.versions[0]
        assert [c.claim_anchor for c in after.versions[0].citations] == [
            "First claim. Second claim."
        ]
        assert [c.claim_anchor for c in after.versions[1].citations] == ["Third claim"]
        assert [a.version for a in after.approvals] == [1, 2]
    with pytest.raises(psycopg.errors.UniqueViolation):
        async with s.uow().transaction() as tx:
            assert isinstance(tx, PostgresTransactionContext)
            await tx.connection.execute(
                "INSERT INTO sot.sot_approval SELECT * FROM sot.sot_approval WHERE workspace_id=%s AND proposal_id=%s AND proposal_version=2",
                (s.workspace_id, pid),
            )


@pytest.mark.parametrize(
    "mutation",
    [
        "item",
        "membership",
        "duplicate",
        "workspace",
        "negative_position",
        "negative_item",
        "blank_anchor",
    ],
)
async def test_citation_constraints(consensus: SharingConsensus, mutation: str) -> None:
    e, s = consensus, consensus.state
    pid = await e.approved()
    unselected = replace(e.bundle, id=BundleId(uuid4()))
    async with s.uow().transaction() as tx:
        await s.sessions.create_bundle(tx, s.workspace_id, unselected)
        saved = await e.proposals.find(tx, s.workspace_id, pid)
    assert saved is not None
    cited = saved.versions[0].citations[0]
    expected: type[psycopg.IntegrityError] = (
        psycopg.errors.UniqueViolation
        if mutation == "duplicate"
        else psycopg.errors.ForeignKeyViolation
    )
    if mutation in {"negative_position", "negative_item", "blank_anchor"}:
        expected = psycopg.errors.CheckViolation
    with pytest.raises(expected):
        async with s.uow().transaction() as tx:
            assert isinstance(tx, PostgresTransactionContext)
            await tx.connection.execute(
                "INSERT INTO sot.sot_proposal_citation(workspace_id,proposal_id,proposal_version,position,claim_anchor,bundle_id,bundle_item_position) VALUES (%s,%s,1,%s,%s,%s,%s)",
                (
                    s.other_workspace_id if mutation == "workspace" else s.workspace_id,
                    pid,
                    -1 if mutation == "negative_position" else 2,
                    " "
                    if mutation == "blank_anchor"
                    else cited.claim_anchor
                    if mutation == "duplicate"
                    else "Second",
                    unselected.id if mutation == "membership" else cited.bundle_id,
                    -1
                    if mutation == "negative_item"
                    else 90
                    if mutation == "item"
                    else cited.bundle_item_position
                    if mutation == "duplicate"
                    else 0,
                ),
            )


async def test_http_proposal_refuses_supplied_evidence_and_merges_minimally(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    prefix = f"/api/v1/workspaces/{s.workspace_id}"
    body = {
        "source_session_id": str(s.session.id),
        "edits": [{"find": "", "replace": "First claim"}],
        "branch_id": str(s.branch.id),
    }
    # Grounds come from the conversation, so a caller cannot hand them in.
    assert (
        await api.post(
            prefix + f"/documents/{s.document_id}/proposals",
            headers=bearer(s.owner.user_id),
            json={**body, "bundle_ids": [str(e.bundle.id)]},
        )
    ).status_code == 422
    created = await api.post(
        prefix + f"/documents/{s.document_id}/proposals",
        headers=bearer(s.owner.user_id),
        json=body,
    )
    assert created.status_code == 201, created.text
    path = prefix + "/proposals/" + created.json()["id"]
    assert (
        await api.put(
            path,
            headers=bearer(s.owner.user_id),
            json={
                "expected_version": 1,
                "edits": [{"find": "", "replace": "Revision"}],
                "branch_id": str(s.branch.id),
                "citations": [],
            },
        )
    ).status_code == 422
    assert (
        await api.post(
            path + "/decisions",
            headers=bearer(s.owner.user_id),
            json={"expected_version": 1, "decision": "approve"},
        )
    ).status_code == 200
    async with s.uow().transaction() as tx:
        assert isinstance(tx, PostgresTransactionContext)
        await tx.connection.execute(
            "UPDATE sot.sot_workspace_member SET role='member' WHERE workspace_id=%s AND user_id=%s",
            (s.workspace_id, s.owner.user_id),
        )
    forbidden = await api.post(
        path + "/merge", headers=bearer(s.owner.user_id), json={"expected_version": 1}
    )
    assert (
        forbidden.status_code == 403
        and forbidden.json()["error"]["code"] == "workspace_forbidden"
    )
    assert (await api.get(path, headers=bearer(s.other.user_id))).status_code == 404
    merged = await api.post(
        path + "/merge", headers=bearer(s.other.user_id), json={"expected_version": 1}
    )
    assert merged.status_code == 200 and merged.json()["status"] == "merged"
    assert set(merged.json()) == {"proposal_id", "version", "status", "publication"}
    assert (
        "source_session_id" not in merged.text
        and "required_approver_ids" not in merged.text
    )
    assert (
        await api.post(
            path + "/merge",
            headers=bearer(s.other.user_id),
            json={"expected_version": 1},
        )
    ).status_code == 409


async def test_http_revise_rederives_the_grounds_from_the_session(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    pid = await e.approved()
    path = f"/api/v1/workspaces/{s.workspace_id}/proposals/{pid}"
    body: dict[str, Any] = {
        "expected_version": 1,
        "edits": [{"find": "", "replace": "Next claim"}],
        "branch_id": str(s.branch.id),
    }
    response = await api.put(path, headers=bearer(s.owner.user_id), json=body)
    assert response.status_code == 200 and response.json()["version"] == 2
    assert [
        (c["claim_anchor"], c["bundle_item_position"])
        for c in response.json()["current_version"]["citations"]
    ] == [("Next claim", 1)]
    assert response.json()["approvals"] == []
    assert (
        await api.get(path, headers=bearer(s.owner.user_id))
    ).json() == response.json()
    conflict = await api.put(path, headers=bearer(s.owner.user_id), json=body)
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "proposal_version_conflict"
    )
    async with s.uow().transaction() as tx:
        proposal = await e.proposals.find(tx, s.workspace_id, pid)
        assert proposal and [len(v.citations) for v in proposal.versions] == [1, 1]


async def test_authenticated_routes_reject_invalid_workspace_and_strict_inputs(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    prefix = "/api/v1/workspaces/not-a-uuid"
    for method, suffix, body in (
        (
            "POST",
            f"/documents/{s.document_id}/proposals",
            {
                "source_session_id": str(s.session.id),
                "edits": [{"find": "", "replace": "claim"}],
                "branch_id": str(s.branch.id),
            },
        ),
        ("GET", f"/proposals/{uuid4()}", None),
        (
            "PUT",
            f"/proposals/{uuid4()}",
            {
                "expected_version": 1,
                "edits": [{"find": "", "replace": "claim"}],
                "branch_id": str(s.branch.id),
            },
        ),
        (
            "POST",
            f"/proposals/{uuid4()}/decisions",
            {"expected_version": 1, "decision": "approve"},
        ),
        ("POST", f"/proposals/{uuid4()}/merge", {"expected_version": 1}),
    ):
        response = await api.request(
            method, prefix + suffix, headers=bearer(s.owner.user_id), json=body
        )
        assert (
            response.status_code == 422
            and response.json()["error"]["code"] == "invalid_request"
        )
    pid = await e.approved()
    path = f"/api/v1/workspaces/{s.workspace_id}/proposals/{pid}/merge"
    for payload in (
        {"expected_version": "1"},
        {"expected_version": True},
        {"expected_version": 1, "workspace_id": str(s.workspace_id)},
    ):
        assert (
            await api.post(path, headers=bearer(s.other.user_id), json=payload)
        ).status_code == 422
    wrong = await api.post(
        f"/api/v1/workspaces/{s.other_workspace_id}/proposals/{pid}/merge",
        headers=bearer(s.other.user_id),
        json={"expected_version": 1},
    )
    assert (
        wrong.status_code == 404
        and wrong.json()["error"]["code"] == "proposal_not_found"
    )


async def test_proposal_read_holds_status_and_approvals_consistent(
    consensus: SharingConsensus,
) -> None:
    e, s = consensus, consensus.state
    proposal = await e.create.execute(
        s.owner,
        s.workspace_id,
        s.session.id,
        document_id=s.document_id,
        edits=(DocumentEdit("", "claim"),),
        branch_id=s.branch.id,
    )
    task = None
    try:
        async with s.uow().transaction() as tx:
            loaded = await e.proposals.find(tx, s.workspace_id, proposal.id)
            assert (
                loaded
                and loaded.status is ProposalStatus.OPEN
                and loaded.approvals == ()
            )
            task = asyncio.create_task(
                e.decide.execute(
                    s.owner,
                    s.workspace_id,
                    proposal.id,
                    expected_version=1,
                    decision=ApprovalDecision.APPROVE,
                )
            )
            done, _ = await asyncio.wait({task}, timeout=0.1)
            assert not done, (
                "A decision must not change a multi-query aggregate snapshot mid-read"
            )
    finally:
        if task is not None:
            result = await task
            assert result.status is ProposalStatus.APPROVED


async def test_additional_approvers_remain_version_owned_snapshots(
    consensus: SharingConsensus,
) -> None:
    e, s = consensus, consensus.state
    pid = await e.approved()
    await e.revise.execute(
        s.owner,
        s.workspace_id,
        pid,
        expected_version=1,
        edits=(DocumentEdit("", "new"),),
        branch_id=s.branch.id,
        additional_approver_ids=frozenset({s.other.user_id}),
    )
    await e.decide.execute(
        s.owner,
        s.workspace_id,
        pid,
        expected_version=2,
        decision=ApprovalDecision.APPROVE,
    )
    other = await e.decide.execute(
        s.other,
        s.workspace_id,
        pid,
        expected_version=2,
        decision=ApprovalDecision.REJECT,
    )
    assert other.status is ProposalStatus.REJECTED
    async with s.uow().transaction() as tx:
        loaded = await e.proposals.find(tx, s.workspace_id, pid)
        assert loaded and loaded.status is ProposalStatus.REJECTED
        assert loaded.versions[0].required_approver_ids == frozenset({s.owner.user_id})
        assert loaded.versions[0].additional_approver_ids == frozenset()
        assert loaded.versions[1].required_approver_ids == frozenset(
            {s.owner.user_id, s.other.user_id}
        )
        assert loaded.versions[1].additional_approver_ids == frozenset(
            {s.other.user_id}
        )
        assert len(loaded.approvals) == 3


@pytest.mark.parametrize("workspace_member", [False, True])
async def test_production_revision_absent_private_responses_match(
    consensus: SharingConsensus, api: httpx.AsyncClient, workspace_member: bool
) -> None:
    e, s = consensus, consensus.state
    pid = await e.approved()
    if not workspace_member:
        async with s.uow().transaction() as tx:
            assert isinstance(tx, PostgresTransactionContext)
            await tx.connection.execute(
                "DELETE FROM sot.sot_workspace_member WHERE workspace_id=%s AND user_id=%s",
                (s.workspace_id, s.other.user_id),
            )
    responses = []
    for candidate in (uuid4(), pid):
        response = await api.put(
            f"/api/v1/workspaces/{s.workspace_id}/proposals/{candidate}",
            headers=bearer(s.other.user_id),
            json={
                "expected_version": 1,
                "edits": [{"find": "", "replace": "private change"}],
                "branch_id": str(s.branch.id),
            },
        )
        responses.append((response.status_code, response.json()["error"]["code"]))
    expected = (
        (404, "proposal_not_found")
        if workspace_member
        else (403, "workspace_forbidden")
    )
    assert responses == [expected, expected]
