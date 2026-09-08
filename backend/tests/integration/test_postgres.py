"""Canonical publication survives a pool and application reconnect."""

import httpx
import pytest
from pydantic import SecretStr

from sot.bootstrap.app import build_app
from sot.bootstrap.settings import Settings
from tests.integration.test_consensus_postgres import (
    SECRET,
    SharingConsensus,
    bearer,
)
from tests.integration.test_consensus_postgres import (
    consensus as consensus,  # noqa: PLC0414
)
from tests.integration.test_document_session_postgres import (
    state as state,  # noqa: PLC0414
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_published_revision_survives_repository_reconnect(
    consensus: SharingConsensus,
    database_url: str,
) -> None:
    s = consensus.state
    proposal_id = await consensus.approved()
    published = await consensus.merge.execute(
        s.owner,
        s.workspace_id,
        proposal_id,
        expected_version=1,
    )
    assert published.publication is not None
    app = build_app(
        Settings(
            database_url=database_url,
            environment="production",
            models=("test",),
            google_client_id="configured-client",
            access_token_secret=SecretStr(SECRET),
        )
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://test"
        ) as client,
    ):
        sent = await client.post(
            f"/api/v1/workspaces/{s.workspace_id}/sessions/{s.session.id}/members",
            headers=bearer(s.owner.user_id),
            json={"user_id": str(s.other.user_id), "role": "editor"},
        )
        assert sent.status_code == 201
    await s.pool.close()
    reconnected = build_app(
        Settings(
            database_url=database_url,
            environment="production",
            models=("test",),
            google_client_id="configured-client",
            access_token_secret=SecretStr(SECRET),
        )
    )
    async with (
        reconnected.router.lifespan_context(reconnected),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(reconnected), base_url="https://test"
        ) as client,
    ):
        response = await client.get(
            f"/api/v1/workspaces/{s.workspace_id}/documents/{s.document_id}",
            headers=bearer(s.owner.user_id),
        )
        assert response.status_code == 200
        revision = response.json()["current_revision"]
        assert revision["number"] == 2
        # The proposal appended, so the base revision survives the merge.
        assert revision["content"] == "initial\n\nFirst claim. Second claim."
        assert revision["proposal_id"] == str(proposal_id)
        # The grounds are the conversation the update was written from, so the
        # citation points at the frozen session rather than anything a caller
        # picked out.
        assert [
            (c["claim_anchor"], c["bundle_item_position"])
            for c in revision["citations"]
        ] == [("First claim. Second claim.", 1)]
        # The session was handed to a teammate before the restart, and they
        # still hold it afterwards.
        members = await client.get(
            f"/api/v1/workspaces/{s.workspace_id}/sessions/{s.session.id}/members",
            headers=bearer(s.other.user_id),
        )
        assert members.status_code == 200
        assert {(item["user_id"], item["role"]) for item in members.json()} >= {
            (str(s.other.user_id), "editor")
        }
