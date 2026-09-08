from __future__ import annotations

from collections.abc import Mapping
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
    GetCurrentWorkspaceMember,
    GetWorkspace,
    ListActorWorkspaces,
    ListWorkspaceMembers,
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
            GetCurrentWorkspaceMember(access, lambda: store),
            ListWorkspaceMembers(store, access, store, lambda: store),
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
        assert rejected.json()["error"]["code"] == "workspace_forbidden"
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
        assert response.json() == {
            "error": {"code": "auth_token_invalid", "message": "Authentication failed"}
        }


@pytest.mark.asyncio
async def test_production_factory_exposes_only_canonical_authenticated_routes() -> None:
    app = build_app(
        Settings(
            environment="production",
            google_client_id="configured-client",
            access_token_secret=SecretStr("s" * 32),
            models=("test",),
        )
    )
    paths = app.openapi()["paths"]
    assert "/api/v1/bootstrap" not in paths
    assert not any(path.startswith("/api/v1/documents") for path in paths)
    assert {"/api/v1/me", "/api/v1/auth/google", "/api/v1/workspaces"} <= paths.keys()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        for path in ("/api/v1/bootstrap", "/api/v1/documents/example"):
            assert (await client.get(path)).status_code == 404
        response = await client.get("/api/v1/me", headers={"X-SOT-User": "alice"})
        assert response.status_code == 401
        assert response.json() == {
            "error": {"code": "auth_token_invalid", "message": "Authentication failed"}
        }


@pytest.mark.asyncio
async def test_composed_request_validation_has_safe_error_envelope() -> None:
    app = build_app(Settings(environment="test", models=("test",)))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        for body in ({}, {"credential": ""}, {"credential": "secret", "admin": True}):
            response = await client.post("/api/v1/auth/google", json=body)
            assert response.status_code == 422
            assert response.json() == {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed",
                }
            }


def test_canonical_response_schema_uses_explicit_closed_wire_models() -> None:
    app = build_app(Settings(environment="test", models=("test",)))
    schema = app.openapi()
    expected = {
        ("/api/v1/me", "get", "200"): "UserResponse",
        ("/api/v1/auth/google", "post", "200"): "AuthResponse",
        ("/api/v1/auth/refresh", "post", "200"): "AuthResponse",
        ("/api/v1/workspaces", "post", "201"): "WorkspaceResponse",
        ("/api/v1/workspaces/{workspace_id}", "get", "200"): "WorkspaceResponse",
        (
            "/api/v1/workspaces/{workspace_id}/members",
            "post",
            "201",
        ): "WorkspaceMemberResponse",
    }
    for (path, method, status), model in expected.items():
        wire = schema["paths"][path][method]["responses"][status]["content"][
            "application/json"
        ]["schema"]
        assert wire == {"$ref": f"#/components/schemas/{model}"}
        assert schema["components"]["schemas"][model]["additionalProperties"] is False
    listing = schema["paths"]["/api/v1/workspaces"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert listing["items"] == {"$ref": "#/components/schemas/WorkspaceResponse"}


def test_resource_read_openapi_contracts_are_closed_scoped_and_bearer_secured() -> None:
    schema = build_app(Settings(environment="test", models=("test",))).openapi()
    prefix = "/api/v1/workspaces/{workspace_id}"
    contracts = (
        (
            "/members/me",
            "get_current_workspace_member",
            "CurrentWorkspaceMemberResponse",
            False,
        ),
        ("/documents", "list_workspace_documents", "DocumentSummaryResponse", True),
        (
            "/documents/{document_id}/sessions",
            "list_document_sessions",
            "SessionResponse",
            True,
        ),
        (
            "/sessions/{session_id}/branches",
            "list_session_branches",
            "BranchResponse",
            True,
        ),
        ("/branches/{branch_id}/turns", "list_branch_turns", "TurnResponse", True),
        (
            "/documents/{document_id}/proposals",
            "list_document_proposals",
            "ProposalResponse",
            True,
        ),
    )
    for suffix, operation_id, model, collection in contracts:
        path = prefix + suffix
        assert path in schema["paths"], path
        operation = schema["paths"][path]["get"]
        assert operation["operationId"] == operation_id
        assert "requestBody" not in operation
        assert any(
            parameter["name"] == "workspace_id"
            and parameter["in"] == "path"
            and parameter["required"]
            for parameter in operation["parameters"]
        )
        assert operation["security"] == [{"HTTPBearer": []}]
        wire = operation["responses"]["200"]["content"]["application/json"]["schema"]
        if collection:
            assert wire["type"] == "array"
            wire = wire["items"]
        assert wire == {"$ref": f"#/components/schemas/{model}"}
        assert schema["components"]["schemas"][model]["additionalProperties"] is False
    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert schema["components"]["schemas"]["TurnResponse"]["properties"]["role"][
        "enum"
    ] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_composed_unexpected_failure_does_not_expose_internal_details() -> None:
    class FailingVerifier:
        async def verify(self, credential: str, audience: str) -> Mapping[str, object]:
            raise RuntimeError("provider secret and internal details")

    app = build_app(
        Settings(environment="test", google_client_id="configured"),
        google_token_verifier=FailingVerifier(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/google", json={"credential": "secret"}
        )
        assert response.status_code == 500
        assert response.json() == {
            "error": {"code": "internal_error", "message": "An internal error occurred"}
        }


@pytest.mark.asyncio
async def test_composed_auth_cors_allows_credentials_only_for_configured_origins() -> (
    None
):
    origin = "https://console.example.com"
    app = build_app(Settings(environment="test", cors_origins=(origin,)))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        preflight = await client.options(
            "/api/v1/auth/google",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers.get("access-control-allow-credentials") == "true"
        assert preflight.headers.get("access-control-allow-origin") == origin
        for request_origin in (origin, "https://untrusted.example.com"):
            response = await client.post(
                "/api/v1/auth/google",
                json={"credential": "not-a-real-token"},
                headers={"Origin": request_origin},
            )
            assert response.status_code == 401
            if request_origin == origin:
                assert (
                    response.headers.get("access-control-allow-credentials") == "true"
                )
                assert response.headers.get("access-control-allow-origin") == origin
            else:
                assert "access-control-allow-origin" not in response.headers
