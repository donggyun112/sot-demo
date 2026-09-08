from uuid import uuid4

import httpx
import pytest

from sot.bootstrap.app import build_app
from sot.bootstrap.settings import Settings


@pytest.mark.asyncio
async def test_consensus_routes_require_bearer() -> None:
    app = build_app(Settings(environment="test", models=("test",)))
    prefix = f"/api/v1/workspaces/{uuid4()}"
    proposal = f"/proposals/{uuid4()}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        for method, path in (
            ("POST", f"/documents/{uuid4()}/proposals"),
            ("GET", proposal),
            ("PUT", proposal),
            ("POST", proposal + "/decisions"),
            ("POST", proposal + "/merge"),
        ):
            response = await client.request(method, prefix + path, json={})
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "auth_token_invalid"


def test_proposal_citations_required_and_merge_projection_is_minimal() -> None:
    schema = build_app(Settings(environment="test", models=("test",))).openapi()
    models = schema["components"]["schemas"]
    for name in ("CreateProposalRequest", "ReviseProposalRequest"):
        # Evidence is not something a caller assembles: naming the branch
        # the update was written in is what records it.
        assert "branch_id" in models[name]["required"]
        assert "citations" not in models[name]["properties"]
        assert models[name]["additionalProperties"] is False
    assert set(models["MergeProposalResponse"]["properties"]) == {
        "proposal_id",
        "version",
        "status",
        "publication",
    }
