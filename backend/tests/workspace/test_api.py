from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from pydantic import SecretStr

from sot.bootstrap.app import build_app, handle_sot_error
from sot.bootstrap.settings import Settings
from sot.identity.api import build_auth_router, resolve_actor
from sot.identity.contracts import Actor
from sot.shared.errors import SOTError
from sot.workspace.api import build_workspace_router
from sot.workspace.application import (
    AddWorkspaceMember,
    CreateWorkspace,
    GetWorkspace,
    ListActorWorkspaces,
    WorkspaceAccess,
)
from tests.identity.test_auth_facade import make_facade
from tests.workspace.test_application import MemoryStore


@pytest.mark.asyncio
async def test_workspace_routes_use_bearer_actor_and_routed_workspace() -> None:
    facade, _, _, _ = make_facade()
    store = MemoryStore()
    access = WorkspaceAccess(store)

    async def actor(request: Request) -> Actor:
        return await resolve_actor(request, facade)

    app = FastAPI()
    app.add_exception_handler(SOTError, handle_sot_error)
    app.include_router(build_auth_router(facade, Settings(environment="test")))
    app.include_router(
        build_workspace_router(
            CreateWorkspace(store, lambda: store),
            AddWorkspaceMember(store, access, store, lambda: store),
            ListActorWorkspaces(store, lambda: store),
            GetWorkspace(store, access, lambda: store),
            actor,
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        assert (await client.get("/api/v1/workspaces")).status_code == 401
        login = await client.post("/api/v1/auth/google", json={"credential": "owner"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        created = await client.post(
            "/api/v1/workspaces", json={"name": "Team"}, headers=headers
        )
        assert created.status_code == 201
        workspace_id = created.json()["id"]
        assert (await client.get("/api/v1/workspaces", headers=headers)).json() == [
            created.json()
        ]
        assert (
            await client.get(f"/api/v1/workspaces/{workspace_id}", headers=headers)
        ).json() == created.json()
        member_id = str(uuid4())
        body = {"user_id": member_id, "role": "viewer"}
        added = await client.post(
            f"/api/v1/workspaces/{workspace_id}/members", json=body, headers=headers
        )
        assert added.status_code == 201
        assert added.json() == {"workspace_id": workspace_id, **body}
        assert (
            await client.post(
                f"/api/v1/workspaces/{workspace_id}/members", json=body, headers=headers
            )
        ).status_code == 409
        other_workspace_id = str(uuid4())
        rejected = await client.post(
            f"/api/v1/workspaces/{other_workspace_id}/members",
            json=body,
            headers=headers,
        )
        assert rejected.status_code == 403
        assert rejected.json()["code"] == "workspace_forbidden"
        for extra in (
            {"workspace_id": workspace_id},
            {"actor": login.json()["user"]["id"]},
        ):
            assert (
                await client.post(
                    f"/api/v1/workspaces/{other_workspace_id}/members",
                    json={**body, **extra},
                    headers=headers,
                )
            ).status_code == 422
        assert (
            await client.post(
                "/api/v1/workspaces",
                json={"name": "Team", "owner_id": member_id},
                headers=headers,
            )
        ).status_code == 422
        assert (
            await client.post(
                "/api/v1/workspaces", json={"name": "  "}, headers=headers
            )
        ).status_code == 422
        assert (
            await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                json={**body, "role": "admin"},
                headers=headers,
            )
        ).status_code == 422


@pytest.mark.parametrize(
    "secret,client_id",
    [
        ("", ""),
        ("s" * 32, ""),
        ("", "configured-client"),
    ],
)
def test_production_composition_requires_google_and_signing_configuration(
    secret: str,
    client_id: str,
) -> None:
    with pytest.raises(ValueError):
        build_app(
            Settings(
                environment="production",
                access_token_secret=SecretStr(secret),
                google_client_id=client_id,
            )
        )


@pytest.mark.asyncio
async def test_local_composition_imports_without_google_and_fails_login_safely() -> (
    None
):
    app = build_app(
        Settings(
            environment="test", google_client_id="", access_token_secret=SecretStr("")
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/google", json={"credential": "not-a-real-token"}
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication failed"}
