from uuid import uuid4

import httpx
import pytest

from sot.bootstrap.app import build_app
from sot.bootstrap.settings import Settings


@pytest.mark.asyncio
async def test_document_routes_require_bearer_authentication() -> None:
    app = build_app(Settings(environment="test", models=("test",)))
    prefix = f"/api/v1/workspaces/{uuid4()}/documents/{uuid4()}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        for path in (prefix, prefix + "/revisions/1"):
            result = await client.get(path, headers={"X-SOT-User": "alice"})
            assert result.status_code == 401
            assert result.json() == {
                "error": {
                    "code": "auth_token_invalid",
                    "message": "Authentication failed",
                }
            }
        created = await client.post(
            f"/api/v1/workspaces/{uuid4()}/documents",
            headers={"X-SOT-User": "alice"},
            json={"title": "Policy", "content": ""},
        )
        assert created.status_code == 401


def test_document_response_contracts_are_closed_explicit_models() -> None:
    schema = build_app(Settings(environment="test", models=("test",))).openapi()
    prefix = "/api/v1/workspaces/{workspace_id}/documents/{document_id}"
    post = schema["paths"]["/api/v1/workspaces/{workspace_id}/documents"]["post"]
    assert post["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DocumentResponse"
    }
    for path, model in (
        (prefix, "DocumentResponse"),
        (prefix + "/revisions/{number}", "RevisionResponse"),
    ):
        response = schema["paths"][path]["get"]["responses"]["200"]
        assert response["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}"
        }
        assert schema["components"]["schemas"][model]["additionalProperties"] is False
