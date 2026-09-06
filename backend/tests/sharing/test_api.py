import io
import logging
from uuid import uuid4

import httpx
import pytest
from uvicorn.logging import AccessFormatter

from sot.bootstrap.app import build_app
from sot.bootstrap.settings import Settings


@pytest.mark.asyncio
async def test_sharing_routes_require_bearer() -> None:
    app = build_app(Settings(environment="test", models=("test",)))
    prefix = f"/api/v1/workspaces/{uuid4()}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        for method, path in (
            ("POST", f"/bundles/{uuid4()}/tosses"),
            ("DELETE", f"/tosses/{uuid4()}"),
            ("POST", "/tosses/secret-capability/fork"),
        ):
            response = await client.request(method, prefix + path, json={})
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "auth_token_invalid"


def test_sharing_public_schema_is_explicit_and_private_ids_are_absent() -> None:
    schema = build_app(Settings(environment="test", models=("test",))).openapi()
    response = schema["paths"]["/api/v1/tosses/{token}"]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicBundleResponse"
    }
    for name in (
        "PublicBundleResponse",
        "PublicBundleItemResponse",
        "AttributionResponse",
        "CreateTossRequest",
        "CreatedTossResponse",
        "ForkResponse",
    ):
        assert schema["components"]["schemas"][name]["additionalProperties"] is False
    fields = schema["components"]["schemas"]["PublicBundleResponse"]["properties"]
    assert set(fields) == {"bundle_id", "title", "items", "attribution"}


def test_access_logs_redact_public_and_fork_token_paths() -> None:
    build_app(Settings(environment="test", models=("test",)))
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(
        AccessFormatter(fmt="%(request_line)s %(status_code)s", use_colors=False)
    )
    logger = logging.getLogger("uvicorn.access")
    logger.addHandler(handler)
    try:
        logger.warning(
            '%s - "%s %s HTTP/%s" %s',
            "client",
            "GET",
            "/api/v1/tosses/secret-capability",
            "1.1",
            200,
        )
        logger.warning(
            '%s - "%s %s HTTP/%s" %s',
            "client",
            "POST",
            f"/api/v1/workspaces/{uuid4()}/tosses/second-secret/fork",
            "1.1",
            201,
        )
    finally:
        logger.removeHandler(handler)
    assert "secret-capability" not in output.getvalue()
    assert "second-secret" not in output.getvalue()
    assert "[redacted]" in output.getvalue()


@pytest.mark.asyncio
async def test_public_internal_errors_are_safe_and_not_cached() -> None:
    app = build_app(Settings(environment="test", models=("test",)))
    # The unopened pool models an unavailable dependency without a database.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://test",
    ) as client:
        response = await client.get("/api/v1/tosses/secret-capability")
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "An internal error occurred"}
    }
    assert response.headers["cache-control"] == "private, no-store"
