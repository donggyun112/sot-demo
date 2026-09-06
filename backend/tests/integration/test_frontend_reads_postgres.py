from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from sot.agent.messages import completed_messages_to_new_turns
from sot.bootstrap.app import SystemClock, build_app
from sot.bootstrap.database import PostgresTransactionContext
from sot.bootstrap.settings import Settings
from sot.document.application import CreateDocument
from sot.identity.tokens import SOTAccessTokenCodec
from sot.session.application import AppendCompletedTurns
from sot.session.domain import NewTurn
from sot.shared.ids import UserId
from sot.workspace.application import WorkspaceAccess
from sot.workspace.domain import WorkspaceMembership, WorkspaceRole
from sot.workspace.postgres import PostgresWorkspaceRepository
from tests.integration.test_document_session_postgres import Harness
from tests.integration.test_document_session_postgres import (
    state as state,  # noqa: PLC0414
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
SECRET = "frontend-read-test-signing-key-at-least-32-bytes"


def bearer(user_id: UserId) -> dict[str, str]:
    token = SOTAccessTokenCodec(SECRET, SystemClock(), timedelta(minutes=5)).encode(
        user_id
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def api(state: Harness, database_url: str) -> AsyncIterator[httpx.AsyncClient]:
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


def paths(s: Harness) -> tuple[str, ...]:
    base = f"/api/v1/workspaces/{s.workspace_id}"
    return (
        f"{base}/members/me",
        f"{base}/documents",
        f"{base}/documents/{s.document_id}/sessions",
        f"{base}/sessions/{s.session.id}/branches",
        f"{base}/branches/{s.branch.id}/turns",
        f"{base}/documents/{s.document_id}/proposals",
    )


async def test_all_reads_authenticate_before_resource_validation(
    state: Harness, api: httpx.AsyncClient
) -> None:
    for path in paths(state):
        for headers in ({}, {"X-SOT-User": str(state.owner.user_id)}):
            response = await api.get(
                path.replace(str(state.workspace_id), "not-a-workspace-id"),
                headers=headers,
            )
            assert response.status_code == 401, (path, response.text)
            assert response.json() == {
                "error": {
                    "code": "auth_token_invalid",
                    "message": "Authentication failed",
                }
            }


@pytest.mark.parametrize(
    ("role", "permissions"),
    [
        (
            "owner",
            [
                "document.create",
                "document.publish",
                "document.read",
                "session.create",
                "session.participate",
                "session.read",
                "workspace.manage",
            ],
        ),
        (
            "member",
            ["document.read", "session.create", "session.participate", "session.read"],
        ),
        ("viewer", ["document.read", "session.read"]),
    ],
)
async def test_current_member_reports_own_role_and_sorted_permissions(
    state: Harness, api: httpx.AsyncClient, role: str, permissions: list[str]
) -> None:
    s = state
    async with s.uow().transaction() as tx:
        await PostgresWorkspaceRepository().add_member(
            tx,
            WorkspaceMembership(s.workspace_id, s.other.user_id, WorkspaceRole(role)),
        )
    response = await api.get(paths(s)[0], headers=bearer(s.other.user_id))
    assert response.status_code == 200
    assert response.json() == {
        "workspace_id": str(s.workspace_id),
        "user_id": str(s.other.user_id),
        "role": role,
        "permissions": permissions,
    }


async def test_document_lists_and_resource_ids_stay_in_routed_workspace(
    state: Harness, api: httpx.AsyncClient
) -> None:
    s = state
    created = await CreateDocument(
        s.documents,
        WorkspaceAccess(PostgresWorkspaceRepository()),
        s.uow,
        SystemClock(),
    ).execute(
        s.other,
        s.other_workspace_id,
        title="Bob private document",
        content="other main",
    )
    alice = await api.get(paths(s)[1], headers=bearer(s.owner.user_id))
    bob = await api.get(
        f"/api/v1/workspaces/{s.other_workspace_id}/documents",
        headers=bearer(s.other.user_id),
    )
    assert alice.status_code == bob.status_code == 200
    assert [row["id"] for row in alice.json()] == [str(s.document_id)]
    assert [row["id"] for row in bob.json()] == [str(created.document.id)]
    assert alice.json()[0]["workspace_id"] == str(s.workspace_id)
    assert alice.json()[0]["title"] == "Policy"
    assert alice.json()[0]["version"] == 1
    for path in paths(s):
        denied = await api.get(path, headers=bearer(s.other.user_id))
        assert denied.status_code == 403, (path, denied.text)
        assert denied.json()["error"]["code"] == "workspace_forbidden"
    for path in paths(s)[2:]:
        cross = await api.get(
            path.replace(str(s.workspace_id), str(s.other_workspace_id)),
            headers=bearer(s.other.user_id),
        )
        absent = await api.get(
            path.replace(str(s.workspace_id), str(s.other_workspace_id))
            .replace(str(s.document_id), str(uuid4()))
            .replace(str(s.session.id), str(uuid4()))
            .replace(str(s.branch.id), str(uuid4())),
            headers=bearer(s.other.user_id),
        )
        assert cross.status_code == absent.status_code == 404
        assert cross.json() == absent.json()


async def test_session_lists_include_only_current_session_members(
    state: Harness, api: httpx.AsyncClient
) -> None:
    s = state
    async with s.uow().transaction() as tx:
        await PostgresWorkspaceRepository().add_member(
            tx,
            WorkspaceMembership(s.workspace_id, s.other.user_id, WorkspaceRole.MEMBER),
        )
    path = paths(s)[2]
    created = await api.post(path, headers=bearer(s.other.user_id), json={})
    assert created.status_code == 201
    alice = await api.get(path, headers=bearer(s.owner.user_id))
    bob = await api.get(path, headers=bearer(s.other.user_id))
    assert alice.status_code == bob.status_code == 200
    assert [row["id"] for row in alice.json()] == [str(s.session.id)]
    assert [row["id"] for row in bob.json()] == [created.json()["session_id"]]
    async with s.uow().transaction() as tx:
        assert isinstance(tx, PostgresTransactionContext)
        await tx.connection.execute(
            "DELETE FROM sot.sot_session_member WHERE workspace_id=%s AND user_id=%s",
            (s.workspace_id, s.other.user_id),
        )
    assert (await api.get(path, headers=bearer(s.other.user_id))).json() == []


async def test_branch_version_and_completed_turns_exclude_execution_internals(
    state: Harness, api: httpx.AsyncClient
) -> None:
    s = state
    turns_path, branches_path = paths(s)[4], paths(s)[3]
    empty = await api.get(turns_path, headers=bearer(s.owner.user_id))
    assert empty.status_code == 200
    assert empty.json() == []
    completed = completed_messages_to_new_turns(
        [
            ModelRequest(
                parts=[
                    SystemPromptPart("private system prompt"),
                    UserPromptPart("question"),
                ]
            ),
            ModelResponse(parts=[ToolCallPart("session_cite", {}, "private-call")]),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        "session_cite",
                        {"internal": "private tool payload"},
                        "private-call",
                    )
                ]
            ),
            ModelResponse(parts=[TextPart("completed answer")]),
        ]
    )
    saved = await AppendCompletedTurns(
        s.sessions, s.reader(), s.uow, SystemClock()
    ).execute(
        s.owner, s.workspace_id, s.branch.id, expected_version=0, messages=completed
    )
    response = await api.get(turns_path, headers=bearer(s.owner.user_id))
    assert response.status_code == 200
    assert [
        (row["ordinal"], row["role"], row["content"]) for row in response.json()
    ] == [(1, "user", "question"), (4, "assistant", "completed answer")]
    assert [row["id"] for row in response.json()] == [
        str(saved.turns[0].id),
        str(saved.turns[3].id),
    ]
    assert all(
        row["branch_id"] == str(s.branch.id)
        and row["workspace_id"] == str(s.workspace_id)
        for row in response.json()
    )
    assert "private" not in response.text and "sot.tool-turn" not in response.text
    branches = await api.get(branches_path, headers=bearer(s.owner.user_id))
    assert branches.status_code == 200
    assert [(row["id"], row["version"]) for row in branches.json()] == [
        (str(s.branch.id), 1)
    ]
    # An unfinished transaction is never a completed canonical transcript.
    with pytest.raises(RuntimeError, match="abort transaction"):
        async with s.uow().transaction() as tx:
            branch = await s.sessions.load_branch(tx, s.workspace_id, s.branch.id)
            assert branch is not None
            partial = branch.append_completed(
                expected_version=1,
                messages=(NewTurn("assistant", "rolled back partial"),),
                now=SystemClock().now(),
            )
            await s.sessions.append_turns(
                tx, s.workspace_id, s.branch.id, partial.turns
            )
            raise RuntimeError("abort transaction")
    assert (
        await api.get(turns_path, headers=bearer(s.owner.user_id))
    ).json() == response.json()


async def test_additional_approver_sees_proposal_but_no_private_session_resources(
    state: Harness, api: httpx.AsyncClient
) -> None:
    s = state
    async with s.uow().transaction() as tx:
        await PostgresWorkspaceRepository().add_member(
            tx,
            WorkspaceMembership(s.workspace_id, s.other.user_id, WorkspaceRole.MEMBER),
        )
    await AppendCompletedTurns(s.sessions, s.reader(), s.uow, SystemClock()).execute(
        s.owner,
        s.workspace_id,
        s.branch.id,
        expected_version=0,
        messages=(
            NewTurn("user", "private source turn"),
            NewTurn("assistant", "private answer"),
        ),
    )
    body = {
        "source_session_id": str(s.session.id),
        "content": "reviewable proposal",
        "citations": [],
        "additional_approver_ids": [str(s.other.user_id)],
    }
    visible = await api.post(paths(s)[5], headers=bearer(s.owner.user_id), json=body)
    hidden = await api.post(
        paths(s)[5],
        headers=bearer(s.owner.user_id),
        json={**body, "content": "hidden proposal", "additional_approver_ids": []},
    )
    assert visible.status_code == hidden.status_code == 201
    listed = await api.get(paths(s)[5], headers=bearer(s.other.user_id))
    assert listed.status_code == 200
    assert listed.json() == [visible.json()]
    assert (
        "private source turn" not in listed.text and "private answer" not in listed.text
    )
    assert "hidden proposal" not in listed.text
    assert (await api.get(paths(s)[2], headers=bearer(s.other.user_id))).json() == []
    for path in paths(s)[3:5]:
        denied = await api.get(path, headers=bearer(s.other.user_id))
        absent = await api.get(
            path.replace(str(s.session.id), str(uuid4())).replace(
                str(s.branch.id), str(uuid4())
            ),
            headers=bearer(s.other.user_id),
        )
        assert denied.status_code == absent.status_code == 404
        assert denied.json() == absent.json()
    # Decision visibility does not grant private session membership.
    decision = await api.post(
        f"/api/v1/workspaces/{s.workspace_id}/proposals/{visible.json()['id']}/decisions",
        headers=bearer(s.other.user_id),
        json={"expected_version": 1, "decision": "approve"},
    )
    assert decision.status_code == 200
    assert (
        await api.get(paths(s)[4], headers=bearer(s.other.user_id))
    ).status_code == 404


async def test_removed_workspace_member_loses_all_read_access(
    state: Harness, api: httpx.AsyncClient
) -> None:
    s = state
    async with s.uow().transaction() as tx:
        assert isinstance(tx, PostgresTransactionContext)
        await tx.connection.execute(
            "DELETE FROM sot.sot_session_member WHERE workspace_id=%s AND user_id=%s",
            (s.workspace_id, s.owner.user_id),
        )
        await tx.connection.execute(
            "DELETE FROM sot.sot_workspace_member WHERE workspace_id=%s AND user_id=%s",
            (s.workspace_id, s.owner.user_id),
        )
    for path in paths(s):
        response = await api.get(path, headers=bearer(s.owner.user_id))
        assert response.status_code == 403, (path, response.text)
        assert response.json()["error"]["code"] == "workspace_forbidden"
