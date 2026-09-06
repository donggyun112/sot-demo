from uuid import uuid4

import httpx
import pytest

from sot.bootstrap.app import build_app
from sot.bootstrap.settings import Settings


@pytest.mark.asyncio
async def test_all_session_routes_require_bearer_authentication() -> None:
    app = build_app(Settings(environment="test", models=("test",)))
    prefix = f"/api/v1/workspaces/{uuid4()}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        for method, path, body in (
            ("POST", f"/documents/{uuid4()}/sessions", {}),
            ("GET", f"/sessions/{uuid4()}", None),
            ("POST", f"/sessions/{uuid4()}/branches", {}),
            ("POST", f"/branches/{uuid4()}/curation-ops", {}),
            ("GET", f"/branches/{uuid4()}/bundle-preview", None),
            ("POST", f"/branches/{uuid4()}/bundles", {}),
        ):
            result = await client.request(method, prefix + path, json=body)
            assert result.status_code == 401
            assert result.json()["error"]["code"] == "auth_token_invalid"


def test_session_request_and_response_models_are_closed() -> None:
    schema = build_app(Settings(environment="test", models=("test",))).openapi()
    prefix = "/api/v1/workspaces/{workspace_id}"
    for path, method, status, model in (
        ("/documents/{document_id}/sessions", "post", "201", "CreatedSessionResponse"),
        ("/sessions/{session_id}", "get", "200", "SessionResponse"),
        ("/sessions/{session_id}/branches", "post", "201", "BranchResponse"),
        ("/branches/{branch_id}/curation-ops", "post", "201", "BranchMutationResponse"),
        ("/branches/{branch_id}/bundles", "post", "201", "BranchMutationResponse"),
    ):
        response = schema["paths"][prefix + path][method]["responses"][status]
        assert response["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}"
        }
        assert schema["components"]["schemas"][model]["additionalProperties"] is False
    for model in (
        "EmptySessionRequest",
        "CurationRequest",
        "PublishBundleRequest",
        "DropTurnRequest",
        "EditTurnRequest",
        "JoinTurnsRequest",
    ):
        assert schema["components"]["schemas"][model]["additionalProperties"] is False
