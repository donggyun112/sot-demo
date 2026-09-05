import pytest
from httpx import ASGITransport, AsyncClient

from sot.agent import build_agent
from sot.api import create_app
from sot.domain.service import SOTService
from sot.store.memory import MemorySOTRepository


async def _client() -> tuple[AsyncClient, SOTService]:
    service = SOTService(MemorySOTRepository())
    app = create_app(service=service, agent=build_agent("test"))
    return (
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://sot.test",
            headers={"X-SOT-User": "alice"},
        ),
        service,
    )


@pytest.mark.asyncio
async def test_rest_api_supports_the_complete_sot_path() -> None:
    client, service = await _client()
    document = await service.create_document(
        actor_id="alice",
        title="요청 제한 토큰",
        content="초기 합의",
    )

    async with client:
        bootstrap = await client.get("/api/v1/bootstrap")
        assert bootstrap.status_code == 200
        assert bootstrap.json()["documents"][0]["id"] == str(document.id)
        assert bootstrap.json()["users"] == ["alice", "bob"]

        document_response = await client.get(f"/api/v1/documents/{document.id}")
        assert document_response.status_code == 200
        assert document_response.json()["current_revision"]["number"] == 1

        session_response = await client.post(
            f"/api/v1/documents/{document.id}/sessions",
            json={"title": "레이트리밋 검토"},
        )
        assert session_response.status_code == 201
        session_id = session_response.json()["session"]["id"]
        alice_branch_id = session_response.json()["branch"]["id"]

        turns_response = await client.post(
            f"/api/v1/branches/{alice_branch_id}/turns",
            json={
                "turns": [
                    {"role": "assistant", "content": "격리 수준은 A와 B가 있습니다."},
                    {"role": "user", "content": "B"},
                ]
            },
        )
        assert turns_response.status_code == 201
        turn_ids = [turn["id"] for turn in turns_response.json()["turns"]]

        cite_response = await client.post(
            f"/api/v1/branches/{alice_branch_id}/cites",
            json={"turn_ids": turn_ids, "summary": "프로세스 격리를 선택함"},
        )
        assert cite_response.status_code == 201
        cite_id = cite_response.json()["cite"]["id"]

        toss_response = await client.post(f"/api/v1/cites/{cite_id}/tosses")
        assert toss_response.status_code == 201
        token = toss_response.json()["toss"]["token"]

        public_toss = await client.get(
            f"/api/v1/tosses/{token}", headers={"X-SOT-User": ""}
        )
        assert public_toss.status_code == 200
        assert public_toss.json()["cite"]["summary"] == "프로세스 격리를 선택함"
        assert len(public_toss.json()["turns"]) == 2

        fork_response = await client.post(
            f"/api/v1/tosses/{token}/fork",
            headers={"X-SOT-User": "bob"},
        )
        assert fork_response.status_code == 201
        bob_branch_id = fork_response.json()["branch"]["id"]

        proposal_response = await client.post(
            f"/api/v1/branches/{bob_branch_id}/proposals",
            json={"content": "각 사용자 작업은 별도 프로세스로 격리한다."},
            headers={"X-SOT-User": "bob"},
        )
        assert proposal_response.status_code == 201
        proposal_id = proposal_response.json()["proposal"]["id"]

        first = await client.post(
            f"/api/v1/proposals/{proposal_id}/approve",
            headers={"X-SOT-User": "bob"},
        )
        assert first.status_code == 200
        assert first.json()["revision"] is None
        assert first.json()["approver_ids"] == ["bob"]

        second = await client.post(f"/api/v1/proposals/{proposal_id}/approve")
        assert second.status_code == 200
        assert second.json()["proposal"]["status"] == "published"
        assert second.json()["revision"]["number"] == 2

        published_document = await client.get(f"/api/v1/documents/{document.id}")
        assert published_document.json()["provenance"]["cite"]["id"] == cite_id
        assert published_document.json()["provenance"]["toss"]["token"] == token

        session = await client.get(f"/api/v1/sessions/{session_id}")
        assert session.status_code == 200
        assert {branch["id"] for branch in session.json()["branches"]} == {
            alice_branch_id,
            bob_branch_id,
        }


@pytest.mark.asyncio
async def test_rest_api_maps_domain_errors_to_stable_problem_codes() -> None:
    client, service = await _client()
    document = await service.create_document(
        actor_id="alice", title="문서", content="초기"
    )
    session = await service.create_session(
        document_id=document.id, owner_id="alice", title="검토"
    )

    async with client:
        forbidden = await client.post(
            f"/api/v1/branches/{session.branch.id}/turns",
            json={"turns": [{"role": "user", "content": "침범"}]},
            headers={"X-SOT-User": "bob"},
        )
        missing = await client.get(
            "/api/v1/documents/019504e8-4b7c-7f3a-8c2d-123456789abc"
        )
        unknown = await client.get(
            "/api/v1/bootstrap", headers={"X-SOT-User": "mallory"}
        )

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "branch_forbidden"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "document_not_found"
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "unknown_development_user"


@pytest.mark.asyncio
async def test_rest_api_rejects_unknown_request_fields() -> None:
    client, service = await _client()
    document = await service.create_document(
        actor_id="alice", title="문서", content="초기"
    )

    async with client:
        response = await client.post(
            f"/api/v1/documents/{document.id}/sessions",
            json={"title": "검토", "unexpected": True},
        )

    assert response.status_code == 422
