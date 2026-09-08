from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

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
    ProposalCitation,
    ProposalStatus,
)
from sot.consensus.postgres import PostgresProposalRepository
from sot.document.application import (
    DocumentAccess,
    DocumentPublicationAccess,
    PublishDocumentRevision,
)
from sot.identity.postgres import PostgresIdentityRepository
from sot.identity.tokens import SOTAccessTokenCodec
from sot.session.application import (
    BundleAccess,
    CloseSession,
    RequiredApprovers,
    SessionAccess,
    VersionGuard,
)
from sot.session.domain import Bundle, BundleItem, SessionMember, SessionRole
from sot.shared.ids import BundleId, ProposalId, UserId
from sot.sharing.application import CreateShareLink
from sot.sharing.postgres import PostgresShareLinkRepository
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
    shares: PostgresShareLinkRepository
    proposals: PostgresProposalRepository
    create: CreateProposal
    revise: ReviseProposal
    decide: DecideProposal
    merge: MergeProposal
    toss: CreateShareLink

    async def approved(self) -> ProposalId:
        s = self.state
        proposal = await self.create.execute(
            s.owner,
            s.workspace_id,
            s.session.id,
            document_id=s.document_id,
            edits=(DocumentEdit("", "First claim. Second claim."),),
            bundle_ids=(self.bundle.id,),
            citations=(
                ProposalCitation(self.bundle.id, 1, "Second claim"),
                ProposalCitation(self.bundle.id, 0, "First claim"),
            ),
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
        sessions, documents, bundles, RequiredApprovers(s.sessions), members
    )
    shares, proposals = PostgresShareLinkRepository(), PostgresProposalRepository()
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
    async with s.uow().transaction() as tx:
        await s.sessions.create_bundle(tx, s.workspace_id, bundle)
        await PostgresWorkspaceRepository().add_member(
            tx,
            WorkspaceMembership(s.workspace_id, s.other.user_id, WorkspaceRole.OWNER),
        )
    return SharingConsensus(
        s,
        bundle,
        shares,
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
        CreateShareLink(
            shares, bundles, PostgresIdentityRepository(), s.uow, SystemClock()
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


async def test_raw_token_absent_and_public_snapshot_survives_identity_session_changes(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    created = await api.post(
        f"/api/v1/workspaces/{s.workspace_id}/bundles/{e.bundle.id}/tosses",
        headers=bearer(s.owner.user_id),
        json={},
    )
    assert created.status_code == 201
    token, link_id = created.json()["token"], UUID(created.json()["id"])
    async with s.uow().transaction() as tx:
        assert isinstance(tx, PostgresTransactionContext)
        row = await (
            await tx.connection.execute(
                "SELECT token_hash, row_to_json(sot_share_link)::text FROM sot.sot_share_link WHERE id=%s",
                (link_id,),
            )
        ).fetchone()
        assert row and row[0] == sha256(token.encode()).digest() and token not in row[1]
        await tx.connection.execute(
            "UPDATE sot.sot_user SET display_name='Changed' WHERE id=%s",
            (s.owner.user_id,),
        )
        await tx.connection.execute(
            "DELETE FROM sot.sot_session_member WHERE workspace_id=%s AND session_id=%s",
            (s.workspace_id, s.session.id),
        )
    response = await api.get(f"/api/v1/tosses/{token}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["attribution"]["author_display_name"] == "Owner"
    assert [i["content"] for i in response.json()["items"]] == [
        "public question",
        "public answer",
    ]
    assert (
        str(s.workspace_id) not in response.text
        and str(s.owner.user_id) not in response.text
    )


async def test_fork_detached_snapshot_and_revocation_expiry(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    created = await e.toss.execute(s.owner, s.workspace_id, e.bundle.id)
    token = created.raw_token
    path = f"/api/v1/workspaces/{s.other_workspace_id}/tosses/{token}/fork"
    assert (
        await api.post(path, headers=bearer(s.owner.user_id), json={})
    ).status_code == 403
    response = await api.post(path, headers=bearer(s.other.user_id), json={})
    assert response.status_code == 201
    async with s.uow().transaction() as tx:
        assert isinstance(tx, PostgresTransactionContext)
        row = await (
            await tx.connection.execute(
                "SELECT s.document_id,o.title,o.author_display_name FROM sot.sot_session s JOIN sot.sot_fork_origin o ON (o.workspace_id,o.session_id)=(s.workspace_id,s.id) WHERE s.id=%s",
                (UUID(response.json()["session_id"]),),
            )
        ).fetchone()
        assert row == (None, "Frozen title", "Owner")
        docs = await (
            await tx.connection.execute(
                "SELECT count(*) FROM sot.sot_document WHERE workspace_id=%s",
                (s.other_workspace_id,),
            )
        ).fetchone()
        assert docs == (0,)
    revoked = await api.delete(
        f"/api/v1/workspaces/{s.workspace_id}/tosses/{created.link_id}",
        headers=bearer(s.owner.user_id),
    )
    assert revoked.status_code == 204
    public = await api.get(f"/api/v1/tosses/{token}")
    assert (
        public.status_code == 404
        and public.headers["cache-control"] == "private, no-store"
    )
    expired = await e.toss.execute(s.owner, s.workspace_id, e.bundle.id)
    async with s.uow().transaction() as tx:
        assert isinstance(tx, PostgresTransactionContext)
        await tx.connection.execute(
            "UPDATE sot.sot_share_link SET expires_at=created_at WHERE id=%s",
            (expired.link_id,),
        )
    assert (await api.get(f"/api/v1/tosses/{expired.raw_token}")).status_code == 404


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
        bundle_ids=(e.bundle.id,),
        citations=(ProposalCitation(e.bundle.id, 0, "Third claim"),),
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
            "Second claim",
            "First claim",
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
                    else "First claim"
                    if mutation == "duplicate"
                    else "Second",
                    unselected.id if mutation == "membership" else e.bundle.id,
                    -1
                    if mutation == "negative_item"
                    else 90
                    if mutation == "item"
                    else 0,
                ),
            )


async def test_http_proposal_required_citations_permissions_and_minimal_merge(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    prefix = f"/api/v1/workspaces/{s.workspace_id}"
    body = {
        "source_session_id": str(s.session.id),
        "edits": [{"find": "", "replace": "First claim"}],
        "bundle_ids": [str(e.bundle.id)],
    }
    assert (
        await api.post(
            prefix + f"/documents/{s.document_id}/proposals",
            headers=bearer(s.owner.user_id),
            json=body,
        )
    ).status_code == 422
    body["citations"] = []
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
            json={"expected_version": 1, "edits": [{"find": "", "replace": "Revision"}], "bundle_ids": []},
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


async def test_actual_bundle_publisher_is_frozen_and_revoke_never_rewrites_snapshot(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    bundle = replace(e.bundle, id=BundleId(uuid4()), published_by=s.other.user_id)
    async with s.uow().transaction() as tx:
        await s.sessions.add_member(
            tx,
            s.workspace_id,
            SessionMember(
                s.workspace_id, s.session.id, s.other.user_id, SessionRole.EDITOR
            ),
        )
        await s.sessions.create_bundle(tx, s.workspace_id, bundle)
    link = await e.toss.execute(s.owner, s.workspace_id, bundle.id)
    response = await api.get(f"/api/v1/tosses/{link.raw_token}")
    assert response.json()["attribution"] == {
        "title": "Frozen title",
        "author_display_name": "Other",
        "published_at": "2026-09-06T00:00:00Z",
    }
    async with s.uow().transaction() as tx:
        original = await e.shares.find_link(tx, s.workspace_id, link.link_id)
        assert original is not None
        await e.shares.save_link(
            tx,
            replace(
                original.revoke(s.owner.user_id, SystemClock().now()),
                snapshot=replace(original.snapshot, title="must not replace"),
            ),
        )
        loaded = await e.shares.find_link(tx, s.workspace_id, link.link_id)
        assert (
            loaded
            and loaded.snapshot == original.snapshot
            and loaded.token_hash == original.token_hash
        )


async def test_http_revise_citations_are_explicit_ordered_and_new_empty_version_clears_them(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    pid = await e.approved()
    path = f"/api/v1/workspaces/{s.workspace_id}/proposals/{pid}"
    citations = [
        {
            "bundle_id": str(e.bundle.id),
            "bundle_item_position": 1,
            "claim_anchor": "Next",
        },
        {
            "bundle_id": str(e.bundle.id),
            "bundle_item_position": 0,
            "claim_anchor": "claim",
        },
    ]
    body: dict[str, Any] = {
        "expected_version": 1,
        "edits": [{"find": "", "replace": "Next claim"}],
        "bundle_ids": [str(e.bundle.id)],
        "citations": citations,
    }
    response = await api.put(path, headers=bearer(s.owner.user_id), json=body)
    assert response.status_code == 200 and response.json()["version"] == 2
    assert response.json()["current_version"]["citations"] == citations
    assert response.json()["approvals"] == []
    assert (
        await api.get(path, headers=bearer(s.owner.user_id))
    ).json() == response.json()
    conflict = await api.put(path, headers=bearer(s.owner.user_id), json=body)
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "proposal_version_conflict"
    )
    body.update(expected_version=2, citations=[])
    empty = await api.put(path, headers=bearer(s.owner.user_id), json=body)
    assert (
        empty.status_code == 200 and empty.json()["current_version"]["citations"] == []
    )
    async with s.uow().transaction() as tx:
        proposal = await e.proposals.find(tx, s.workspace_id, pid)
        assert proposal and [len(v.citations) for v in proposal.versions] == [2, 2, 0]


async def test_authenticated_routes_reject_invalid_workspace_and_strict_inputs(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    prefix = "/api/v1/workspaces/not-a-uuid"
    for method, suffix, body in (
        ("POST", f"/bundles/{e.bundle.id}/tosses", {}),
        ("DELETE", f"/tosses/{uuid4()}", None),
        ("POST", "/tosses/token/fork", {}),
        (
            "POST",
            f"/documents/{s.document_id}/proposals",
            {
                "source_session_id": str(s.session.id),
                "edits": [{"find": "", "replace": "claim"}],
                "citations": [],
            },
        ),
        ("GET", f"/proposals/{uuid4()}", None),
        (
            "PUT",
            f"/proposals/{uuid4()}",
            {
                "expected_version": 1,
                "edits": [{"find": "", "replace": "claim"}],
                "bundle_ids": [],
                "citations": [],
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


async def test_real_request_logs_hide_capability_tokens(
    consensus: SharingConsensus,
    api: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    e, s = consensus, consensus.state
    link = await e.toss.execute(s.owner, s.workspace_id, e.bundle.id)
    with caplog.at_level(logging.INFO, logger="httpx"):
        assert (await api.get(f"/api/v1/tosses/{link.raw_token}")).status_code == 200
        assert (
            await api.post(
                f"/api/v1/workspaces/{s.other_workspace_id}/tosses/{link.raw_token}/fork",
                headers=bearer(s.other.user_id),
                json={},
            )
        ).status_code == 201
    assert link.raw_token not in caplog.text
    assert "/tosses/[redacted]" in caplog.text


async def test_anonymous_http_reads_with_identity_and_source_tables_unavailable(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    link = await e.toss.execute(s.owner, s.workspace_id, e.bundle.id)
    # Only this disposable fixture's schema changes. PostgreSQL retains FK targets
    # when renamed, while any anonymous identity/session SQL would now fail.
    async with s.uow().transaction() as tx:
        assert isinstance(tx, PostgresTransactionContext)
        await tx.connection.execute(
            "ALTER TABLE sot.sot_user RENAME TO unavailable_user"
        )
        await tx.connection.execute(
            "ALTER TABLE sot.sot_session RENAME TO unavailable_session"
        )
        await tx.connection.execute(
            "ALTER TABLE sot.sot_bundle RENAME TO unavailable_bundle"
        )
        await tx.connection.execute(
            "ALTER TABLE sot.sot_bundle_item RENAME TO unavailable_bundle_item"
        )
    response = await api.get(
        f"/api/v1/tosses/{link.raw_token}",
        headers={"Authorization": "Bearer invalid-ignored-for-public-read"},
    )
    assert response.status_code == 200
    assert response.json()["attribution"]["author_display_name"] == "Owner"
    assert [item["content"] for item in response.json()["items"]] == [
        "public question",
        "public answer",
    ]


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
        citations=(),
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
        bundle_ids=(),
        citations=(),
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


async def test_production_owner_revokes_closed_session_toss_with_unchanged_permissions(
    consensus: SharingConsensus, api: httpx.AsyncClient
) -> None:
    e, s = consensus, consensus.state
    prefix = f"/api/v1/workspaces/{s.workspace_id}"
    created = await api.post(
        prefix + f"/bundles/{e.bundle.id}/tosses",
        headers=bearer(s.owner.user_id),
        json={},
    )
    assert created.status_code == 201
    link_id, token = UUID(created.json()["id"]), created.json()["token"]
    members = WorkspaceAccess(PostgresWorkspaceRepository())
    await CloseSession(s.sessions, SessionAccess(s.sessions, members), s.uow).execute(
        s.owner, s.workspace_id, s.session.id
    )
    create_after_close = await api.post(
        prefix + f"/bundles/{e.bundle.id}/tosses",
        headers=bearer(s.owner.user_id),
        json={},
    )
    assert (
        create_after_close.status_code == 409
        and create_after_close.json()["error"]["code"] == "session_closed"
    )
    path = prefix + f"/tosses/{link_id}"
    assert (await api.delete(path, headers=bearer(s.other.user_id))).status_code == 404
    assert (
        await api.delete(
            f"/api/v1/workspaces/{s.other_workspace_id}/tosses/{link_id}",
            headers=bearer(s.other.user_id),
        )
    ).status_code == 404
    async with s.uow().transaction() as tx:
        await s.sessions.add_member(
            tx,
            s.workspace_id,
            SessionMember(
                s.workspace_id, s.session.id, s.other.user_id, SessionRole.EDITOR
            ),
        )
    denied = await api.delete(path, headers=bearer(s.other.user_id))
    assert (
        denied.status_code == 403
        and denied.json()["error"]["code"] == "session_forbidden"
    )
    public = await api.get(f"/api/v1/tosses/{token}")
    assert public.status_code == 200
    revoked = await api.delete(path, headers=bearer(s.owner.user_id))
    assert revoked.status_code == 204
    hidden = await api.get(f"/api/v1/tosses/{token}")
    assert (
        hidden.status_code == 404
        and hidden.headers["cache-control"] == "private, no-store"
    )
    assert (await api.delete(path, headers=bearer(s.owner.user_id))).status_code == 204
    async with s.uow().transaction() as tx:
        link = await e.shares.find_link(tx, s.workspace_id, link_id)
        assert link and link.revoked_by == s.owner.user_id
        assert await s.sessions.load_bundle(tx, s.workspace_id, e.bundle.id) == e.bundle


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
                "bundle_ids": [],
                "citations": [],
            },
        )
        responses.append((response.status_code, response.json()["error"]["code"]))
    expected = (
        (404, "proposal_not_found")
        if workspace_member
        else (403, "workspace_forbidden")
    )
    assert responses == [expected, expected]
