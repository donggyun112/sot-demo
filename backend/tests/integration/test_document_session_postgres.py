from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
import pytest_asyncio
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr

from sot.bootstrap.app import SystemClock, build_app
from sot.bootstrap.database import PostgresTransactionContext, PostgresUnitOfWork
from sot.bootstrap.migrate import run_migrations
from sot.bootstrap.settings import Settings
from sot.document.application import (
    CreateDocument,
    DocumentAccess,
    PublishDocumentRevision,
)
from sot.document.domain import VersionConflict as DocumentVersionConflict
from sot.document.postgres import PostgresDocumentRepository
from sot.identity.contracts import Actor
from sot.identity.domain import VerifiedIdentity
from sot.identity.postgres import PostgresIdentityRepository
from sot.session.application import (
    AppendCompletedTurns,
    ApplyCuration,
    BranchAccess,
    CreateSession,
    PublishBundle,
    SessionAccess,
)
from sot.session.domain import (
    Branch,
    Bundle,
    BundleItem,
    CurationOperation,
    CurationRecord,
    DropTurn,
    EditTurn,
    JoinTurns,
    NewTurn,
    Session,
    SessionMember,
    SessionMemberAlreadyExists,
    SessionRole,
    SessionStatus,
    VersionConflict,
)
from sot.session.postgres import PostgresSessionRepository
from sot.shared.ids import BundleId, DocumentId, ProposalId, WorkspaceId
from sot.workspace.application import CreateWorkspace, WorkspaceAccess
from sot.workspace.postgres import PostgresWorkspaceRepository
from tests.integration.test_workspace_postgres import StaticGoogleVerifier

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
MIGRATIONS = Path(__file__).parents[2] / "migrations"
NOW = datetime(2026, 9, 6, tzinfo=UTC)


async def test_canonical_schema_exists_and_keeps_legacy_tables(
    database_url: str,
) -> None:
    legacy_id, legacy_revision = uuid4(), uuid4()
    async with await psycopg.AsyncConnection.connect(database_url) as conn:
        await conn.execute((MIGRATIONS / "001_platform.sql").read_text())
        await conn.execute(
            "INSERT INTO sot.documents(id,title,current_revision_id,created_by,created_at) VALUES (%s,'Legacy',%s,'legacy',%s)",
            (legacy_id, legacy_revision, NOW),
        )
        await conn.execute(
            "INSERT INTO sot.revisions(id,document_id,number,content,created_by,created_at) VALUES (%s,%s,1,'preserve me','legacy',%s)",
            (legacy_revision, legacy_id, NOW),
        )
    await run_migrations(database_url, MIGRATIONS)
    async with await psycopg.AsyncConnection.connect(database_url) as conn:
        for table in (
            "sot_document",
            "sot_document_revision",
            "sot_revision_citation",
            "sot_session",
            "sot_session_member",
            "sot_branch",
            "sot_turn",
            "sot_curation_op",
            "sot_bundle",
            "sot_bundle_item",
        ):
            row = await (
                await conn.execute("SELECT to_regclass(%s)", ("sot." + table,))
            ).fetchone()
            assert row is not None and row[0] is not None, (
                f"missing canonical table {table}"
            )
        row = await (
            await conn.execute("SELECT to_regclass('sot.documents')")
        ).fetchone()
        assert row is not None and row[0] is not None
        row = await (
            await conn.execute(
                "SELECT title,current_revision_id FROM sot.documents WHERE id=%s",
                (legacy_id,),
            )
        ).fetchone()
        assert row == ("Legacy", legacy_revision)
        row = await (
            await conn.execute(
                "SELECT content FROM sot.revisions WHERE id=%s", (legacy_revision,)
            )
        ).fetchone()
        assert row == ("preserve me",)


@dataclass
class Harness:
    pool: AsyncConnectionPool[Any]
    documents: PostgresDocumentRepository
    sessions: PostgresSessionRepository
    owner: Actor
    other: Actor
    workspace_id: WorkspaceId
    other_workspace_id: WorkspaceId
    document_id: DocumentId
    session: Session
    branch: Branch

    def uow(self) -> PostgresUnitOfWork:
        return PostgresUnitOfWork(self.pool)

    def reader(self) -> BranchAccess:
        members = WorkspaceAccess(PostgresWorkspaceRepository())
        return BranchAccess(
            self.sessions, SessionAccess(self.sessions, members), members
        )


@pytest_asyncio.fixture
async def state(database_url: str) -> AsyncIterator[Harness]:
    await run_migrations(database_url, MIGRATIONS)
    async with AsyncConnectionPool[Any](database_url, open=False) as pool:
        identity, workspace = (
            PostgresIdentityRepository(),
            PostgresWorkspaceRepository(),
        )
        documents, sessions = PostgresDocumentRepository(), PostgresSessionRepository()
        uow = lambda: PostgresUnitOfWork(pool)
        async with uow().transaction() as tx:
            owner = Actor(
                (
                    await identity.upsert_identity(
                        tx, VerifiedIdentity("test", "owner", "owner@test", "Owner")
                    )
                ).id
            )
            other = Actor(
                (
                    await identity.upsert_identity(
                        tx, VerifiedIdentity("test", "other", "other@test", "Other")
                    )
                ).id
            )
        first = await CreateWorkspace(workspace, uow).execute(owner, name="First")
        second = await CreateWorkspace(workspace, uow).execute(other, name="Second")
        access = WorkspaceAccess(workspace)
        document = await CreateDocument(documents, access, uow, SystemClock()).execute(
            owner, first.id, title="Policy", content="initial"
        )
        created = await CreateSession(
            sessions, access, DocumentAccess(documents, access), uow, SystemClock()
        ).execute(owner, first.id, document.document.id)
        async with uow().transaction() as tx:
            session = await sessions.load_session(tx, first.id, created.session_id)
            branch = await sessions.load_branch(tx, first.id, created.branch_id)
        assert session is not None and branch is not None
        yield Harness(
            pool,
            documents,
            sessions,
            owner,
            other,
            first.id,
            second.id,
            document.document.id,
            session,
            branch,
        )


async def test_repository_queries_and_updates_are_tenant_scoped(state: Harness) -> None:
    s = state
    async with s.uow().transaction() as tx:
        assert await s.documents.get(tx, s.other_workspace_id, s.document_id) is None
        assert await s.documents.load(tx, s.other_workspace_id, s.document_id) is None
        assert (
            await s.documents.get_revision(tx, s.other_workspace_id, s.document_id, 1)
            is None
        )
        assert (
            await s.sessions.load_session(tx, s.other_workspace_id, s.session.id)
            is None
        )
        assert (
            await s.sessions.get_member(
                tx, s.other_workspace_id, s.session.id, s.owner.user_id
            )
            is None
        )
        assert (
            await s.sessions.list_members(tx, s.other_workspace_id, s.session.id) == ()
        )
        assert (
            await s.sessions.session_for_branch(tx, s.other_workspace_id, s.branch.id)
            is None
        )
        assert (
            await s.sessions.load_branch(tx, s.other_workspace_id, s.branch.id) is None
        )
        assert (
            await s.sessions.advance_version(
                tx, s.other_workspace_id, s.branch.id, expected_version=0
            )
            is None
        )
        assert (
            await s.sessions.list_curation(tx, s.other_workspace_id, s.branch.id) == ()
        )
        branch = await s.sessions.load_branch(tx, s.workspace_id, s.branch.id)
        assert branch is not None and branch.version == 0


async def test_session_membership_composite_fk_and_duplicates_preserve_roles(
    state: Harness,
) -> None:
    s = state
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        async with s.uow().transaction() as tx:
            await s.sessions.add_member(
                tx,
                s.workspace_id,
                SessionMember(
                    s.workspace_id, s.session.id, s.other.user_id, SessionRole.VIEWER
                ),
            )
    with pytest.raises(SessionMemberAlreadyExists):
        async with s.uow().transaction() as tx:
            await s.sessions.add_member(
                tx,
                s.workspace_id,
                SessionMember(
                    s.workspace_id, s.session.id, s.owner.user_id, SessionRole.VIEWER
                ),
            )
    async with s.uow().transaction() as tx:
        member = await s.sessions.get_member(
            tx, s.workspace_id, s.session.id, s.owner.user_id
        )
        assert member is not None and member.role is SessionRole.OWNER
        assert len(await s.sessions.list_members(tx, s.workspace_id, s.session.id)) == 1


async def test_session_document_and_branch_parent_fks_cannot_cross_tenants(
    state: Harness,
) -> None:
    s = state
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        async with s.uow().transaction() as tx:
            await s.sessions.create_session(
                tx,
                s.other_workspace_id,
                Session.create(
                    s.other_workspace_id, s.document_id, s.other.user_id, NOW
                ),
            )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        async with s.uow().transaction() as tx:
            await s.sessions.create_branch(
                tx,
                s.other_workspace_id,
                Branch.create(s.other_workspace_id, s.session.id, s.other.user_id, NOW),
            )


async def test_document_conditional_publish_and_citation_failure_roll_back(
    state: Harness,
) -> None:
    from sot.document.contracts import RevisionCitationInput

    s = state
    async with s.uow().transaction() as tx:
        first = await s.documents.load(tx, s.workspace_id, s.document_id)
        stale = await s.documents.load(tx, s.workspace_id, s.document_id)
    assert first is not None and stale is not None
    revision = first.publish(
        content="winner",
        proposal_id=ProposalId(uuid4()),
        citations=(),
        actor_id=s.owner.user_id,
        expected_version=1,
        now=NOW,
    )
    async with s.uow().transaction() as tx:
        await s.documents.save_revision(
            tx, s.workspace_id, first, revision, expected_version=1
        )
    stale_revision = stale.publish(
        content="loser",
        proposal_id=ProposalId(uuid4()),
        citations=(),
        actor_id=s.owner.user_id,
        expected_version=1,
        now=NOW,
    )
    with pytest.raises(DocumentVersionConflict):
        async with s.uow().transaction() as tx:
            await s.documents.save_revision(
                tx, s.workspace_id, stale, stale_revision, expected_version=1
            )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        async with s.uow().transaction() as tx:
            await PublishDocumentRevision(
                s.documents,
                WorkspaceAccess(PostgresWorkspaceRepository()),
                SystemClock(),
            ).publish(
                tx,
                actor=s.owner,
                workspace_id=s.workspace_id,
                document_id=s.document_id,
                expected_version=2,
                proposal_id=ProposalId(uuid4()),
                content="must rollback",
                citations=(RevisionCitationInput("claim", BundleId(uuid4()), 0),),
            )
    async with s.uow().transaction() as tx:
        document = await s.documents.get(tx, s.workspace_id, s.document_id)
        assert document is not None
        assert document.document.version == 2
        assert document.current_revision.content == "winner"
        assert (
            await s.documents.get_revision(tx, s.workspace_id, s.document_id, 3) is None
        )


async def test_completed_turns_curation_and_immutable_bundle_round_trip(
    state: Harness,
) -> None:
    s = state
    appended = await AppendCompletedTurns(
        s.sessions, s.reader(), s.uow, SystemClock()
    ).execute(
        s.owner,
        s.workspace_id,
        s.branch.id,
        expected_version=0,
        messages=(
            NewTurn("user", "question"),
            NewTurn("assistant", "private"),
            NewTurn("assistant", "third"),
            NewTurn("tool", "secret"),
        ),
    )
    curate = ApplyCuration(s.sessions, s.sessions, s.reader(), s.uow, SystemClock())
    operations: tuple[CurationOperation, ...] = (
        EditTurn(appended.turns[1].id, "public"),
        JoinTurns((appended.turns[0].id, appended.turns[1].id), "summary"),
        DropTurn(appended.turns[2].id),
    )
    for version, operation in enumerate(operations, 1):
        await curate.execute(
            s.owner,
            s.workspace_id,
            s.branch.id,
            expected_version=version,
            operation=operation,
        )
    with pytest.raises(VersionConflict):
        await curate.execute(
            s.owner,
            s.workspace_id,
            s.branch.id,
            expected_version=1,
            operation=DropTurn(appended.turns[0].id),
        )
    published = await PublishBundle(
        s.sessions, s.sessions, s.sessions, s.reader(), s.uow, SystemClock()
    ).execute(
        s.owner, s.workspace_id, s.branch.id, expected_version=4, title="Snapshot"
    )
    async with s.uow().transaction() as tx:
        bundle = await s.sessions.load_bundle(
            tx, s.workspace_id, BundleId(published.resource_id)
        )
        assert bundle is not None
        assert [(i.content, i.provenance) for i in bundle.items] == [
            ("summary", "edited")
        ]
        assert bundle.items[0].source_ids == (
            appended.turns[0].id,
            appended.turns[1].id,
        )
        assert await s.sessions.load_bundle(tx, s.other_workspace_id, bundle.id) is None
        assert (
            await s.sessions.session_for_bundle(tx, s.other_workspace_id, bundle.id)
            is None
        )
        assert (
            await s.sessions.session_for_bundle(tx, s.workspace_id, bundle.id)
            == s.session.id
        )
        branch = await s.sessions.load_branch(tx, s.workspace_id, s.branch.id)
        assert branch is not None and branch.turns == appended.turns
    with pytest.raises(psycopg.errors.UniqueViolation):
        async with s.uow().transaction() as tx:
            await s.sessions.create_bundle(
                tx, s.workspace_id, replace(bundle, title="overwrite")
            )
    await curate.execute(
        s.owner,
        s.workspace_id,
        s.branch.id,
        expected_version=5,
        operation=EditTurn(appended.turns[0].id, "later"),
    )
    async with s.uow().transaction() as tx:
        unchanged = await s.sessions.load_bundle(tx, s.workspace_id, bundle.id)
        assert unchanged is not None and unchanged.items[0].content == "summary"


async def test_failed_turn_insert_rolls_back_conditional_branch_advance(
    state: Harness,
) -> None:
    s = state
    completed = s.branch.append_completed(
        expected_version=0, messages=(NewTurn("user", "Q"),), now=NOW
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        async with s.uow().transaction() as tx:
            assert (
                await s.sessions.advance_version(
                    tx, s.workspace_id, s.branch.id, expected_version=0
                )
                == 1
            )
            await s.sessions.append_turns(
                tx, s.workspace_id, s.branch.id, (*completed.turns, *completed.turns)
            )
    async with s.uow().transaction() as tx:
        branch = await s.sessions.load_branch(tx, s.workspace_id, s.branch.id)
        assert branch is not None and branch.version == 0 and branch.turns == ()


async def test_concurrent_branch_advances_have_one_winner_and_session_close_persists(
    state: Harness,
) -> None:
    async def advance() -> int | None:
        async with state.uow().transaction() as tx:
            return await state.sessions.advance_version(
                tx, state.workspace_id, state.branch.id, expected_version=0
            )

    versions = await asyncio.gather(advance(), advance())
    assert versions.count(1) == 1 and versions.count(None) == 1
    state.session.close()
    async with state.uow().transaction() as tx:
        await state.sessions.save_session(tx, state.workspace_id, state.session)
    async with state.uow().transaction() as tx:
        session = await state.sessions.load_session(
            tx, state.workspace_id, state.session.id
        )
        assert session is not None and session.status is SessionStatus.CLOSED


async def test_failed_curation_and_bundle_writes_roll_back_branch_and_children(
    state: Harness,
) -> None:
    s = state
    record = CurationRecord(
        uuid4(), s.branch.id, 1, DropTurn(uuid4()), s.owner.user_id, NOW
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        async with s.uow().transaction() as tx:
            assert (
                await s.sessions.advance_version(
                    tx, s.workspace_id, s.branch.id, expected_version=0
                )
                == 1
            )
            await s.sessions.append_curation(tx, s.workspace_id, record)
            await s.sessions.append_curation(
                tx, s.workspace_id, replace(record, id=uuid4())
            )
    invalid_bundle = Bundle.publish(
        s.branch,
        (BundleItem((), "user", "bad", "copied"),),
        s.owner.user_id,
        NOW,
        title="Rollback",
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with s.uow().transaction() as tx:
            assert (
                await s.sessions.advance_version(
                    tx, s.workspace_id, s.branch.id, expected_version=0
                )
                == 1
            )
            await s.sessions.create_bundle(tx, s.workspace_id, invalid_bundle)
    async with s.uow().transaction() as tx:
        branch = await s.sessions.load_branch(tx, s.workspace_id, s.branch.id)
        assert branch is not None and branch.version == 0
        assert await s.sessions.list_curation(tx, s.workspace_id, s.branch.id) == ()
        assert (
            await s.sessions.load_bundle(tx, s.workspace_id, invalid_bundle.id) is None
        )


async def test_revision_citations_round_trip_and_reject_cross_tenant_bundle(
    state: Harness,
) -> None:
    from sot.document.contracts import RevisionCitationInput

    s = state
    bundle = Bundle.publish(
        s.branch,
        (BundleItem((uuid4(),), "assistant", "Evidence", "copied"),),
        s.owner.user_id,
        NOW,
        title="Source",
    )
    publisher = PublishDocumentRevision(
        s.documents, WorkspaceAccess(PostgresWorkspaceRepository()), SystemClock()
    )
    async with s.uow().transaction() as tx:
        await s.sessions.create_bundle(tx, s.workspace_id, bundle)
        await publisher.publish(
            tx,
            actor=s.owner,
            workspace_id=s.workspace_id,
            document_id=s.document_id,
            expected_version=1,
            proposal_id=ProposalId(uuid4()),
            content="cited",
            citations=(
                RevisionCitationInput("claim A", bundle.id, 0),
                RevisionCitationInput("claim B", bundle.id, 0),
            ),
        )
    async with s.uow().transaction() as tx:
        revision = await s.documents.get_revision(tx, s.workspace_id, s.document_id, 2)
        assert revision is not None
        assert [
            (c.claim_anchor, c.bundle_id, c.bundle_item_position)
            for c in revision.citations
        ] == [("claim A", bundle.id, 0), ("claim B", bundle.id, 0)]
    other = await CreateDocument(
        s.documents,
        WorkspaceAccess(PostgresWorkspaceRepository()),
        s.uow,
        SystemClock(),
    ).execute(s.other, s.other_workspace_id, title="Other", content="initial")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        async with s.uow().transaction() as tx:
            await publisher.publish(
                tx,
                actor=s.other,
                workspace_id=s.other_workspace_id,
                document_id=other.document.id,
                expected_version=1,
                proposal_id=ProposalId(uuid4()),
                content="cross tenant",
                citations=(RevisionCitationInput("claim", bundle.id, 0),),
            )
    async with s.uow().transaction() as tx:
        document = await s.documents.get(tx, s.other_workspace_id, other.document.id)
        assert document is not None and document.document.version == 1


async def test_composed_document_session_routes_contracts_rbac_and_versions(
    database_url: str,
) -> None:
    await run_migrations(database_url, MIGRATIONS)
    app = build_app(
        Settings(
            environment="production",
            database_url=database_url,
            google_client_id="test",
            access_token_secret=SecretStr("s" * 32),
        ),
        google_token_verifier=StaticGoogleVerifier(),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client,
    ):
        first = (
            await client.post("/api/v1/auth/google", json={"credential": "first"})
        ).json()
        second = (
            await client.post("/api/v1/auth/google", json={"credential": "second"})
        ).json()
        headers = {"Authorization": "Bearer " + first["access_token"]}
        other_headers = {"Authorization": "Bearer " + second["access_token"]}
        w = (
            await client.post("/api/v1/workspaces", json={"name": "A"}, headers=headers)
        ).json()["id"]
        other_w = (
            await client.post("/api/v1/workspaces", json={"name": "B"}, headers=headers)
        ).json()["id"]
        from sot.shared.ids import UserId

        actor = Actor(UserId(UUID(first["user"]["id"])))
        uow = lambda: PostgresUnitOfWork(app.state.pool)
        document = await CreateDocument(
            PostgresDocumentRepository(),
            WorkspaceAccess(PostgresWorkspaceRepository()),
            uow,
            SystemClock(),
        ).execute(actor, WorkspaceId(UUID(w)), title="Policy", content="initial")
        root = f"/api/v1/workspaces/{w}"
        doc_url = root + f"/documents/{document.document.id}"
        response = await client.get(doc_url, headers=headers)
        assert response.status_code == 200
        assert set(response.json()) == {"document", "current_revision"}
        revision = await client.get(doc_url + "/revisions/1", headers=headers)
        assert revision.status_code == 200 and revision.json()["content"] == "initial"
        assert (
            await client.get(doc_url + "/revisions/2", headers=headers)
        ).status_code == 404
        assert (
            await client.get(doc_url.replace(w, other_w), headers=headers)
        ).status_code == 404
        assert (await client.get(doc_url, headers=other_headers)).status_code == 403
        created = await client.post(doc_url + "/sessions", json={}, headers=headers)
        assert created.status_code == 201
        assert set(created.json()) == {"session_id", "branch_id"}
        session_id, branch_id = (
            created.json()["session_id"],
            created.json()["branch_id"],
        )
        session_url, branch_url = (
            root + "/sessions/" + session_id,
            root + "/branches/" + branch_id,
        )
        read_session = await client.get(session_url, headers=headers)
        assert read_session.status_code == 200 and read_session.json()[
            "document_id"
        ] == str(document.document.id)
        # Even a workspace owner cannot discover an uninvited private session.
        await client.post(
            root + "/members",
            json={"user_id": second["user"]["id"], "role": "owner"},
            headers=headers,
        )
        assert (await client.get(session_url, headers=other_headers)).status_code == 404
        assert (
            await client.get(branch_url + "/bundle-preview", headers=other_headers)
        ).status_code == 404
        assert (
            await client.get(session_url.replace(w, other_w), headers=headers)
        ).status_code == 404
        assert (
            await client.post(session_url + "/branches", json={}, headers=headers)
        ).status_code == 201
        sessions = PostgresSessionRepository()
        members = WorkspaceAccess(PostgresWorkspaceRepository())
        from sot.shared.ids import BranchId, SessionId

        async with uow().transaction() as tx:
            await sessions.add_member(
                tx,
                WorkspaceId(UUID(w)),
                SessionMember(
                    WorkspaceId(UUID(w)),
                    SessionId(UUID(session_id)),
                    UserId(UUID(second["user"]["id"])),
                    SessionRole.VIEWER,
                ),
            )
        assert (
            await client.post(session_url + "/branches", json={}, headers=other_headers)
        ).status_code == 403
        appended = await AppendCompletedTurns(
            sessions,
            BranchAccess(sessions, SessionAccess(sessions, members), members),
            uow,
            SystemClock(),
        ).execute(
            actor,
            WorkspaceId(UUID(w)),
            BranchId(UUID(branch_id)),
            expected_version=0,
            messages=(NewTurn("user", "Q"), NewTurn("assistant", "A")),
        )
        edit_body = {
            "kind": "edit",
            "turn_id": str(appended.turns[1].id),
            "content": "edited",
        }
        body = {"expected_version": 1, "operation": edit_body}
        curated = await client.post(
            branch_url + "/curation-ops", json=body, headers=headers
        )
        assert curated.status_code == 201 and curated.json()["branch_version"] == 2
        conflict = await client.post(
            branch_url + "/curation-ops", json=body, headers=headers
        )
        assert (
            conflict.status_code == 409
            and conflict.json()["error"]["code"] == "version_conflict"
        )
        preview = await client.get(branch_url + "/bundle-preview", headers=headers)
        assert preview.status_code == 200 and [
            i["content"] for i in preview.json()
        ] == ["Q", "edited"]
        published = await client.post(
            branch_url + "/bundles",
            json={"expected_version": 2, "title": "Public"},
            headers=headers,
        )
        assert published.status_code == 201 and published.json()["branch_version"] == 3
        for path, invalid in (
            (doc_url + "/sessions", {"document_id": None}),
            (session_url + "/branches", {"workspace_id": other_w}),
            (branch_url + "/curation-ops", {**body, "unexpected": True}),
            (
                branch_url + "/curation-ops",
                {**body, "operation": {**edit_body, "unexpected": True}},
            ),
            (branch_url + "/curation-ops", {**body, "expected_version": -1}),
            (
                branch_url + "/bundles",
                {"expected_version": 3, "title": "x", "actor": "other"},
            ),
        ):
            invalid_response = await client.post(path, json=invalid, headers=headers)
            assert invalid_response.status_code == 422
            assert invalid_response.json() == {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed",
                }
            }
