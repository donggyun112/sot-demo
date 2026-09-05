import json
from collections.abc import AsyncIterator

import pytest
from ag_ui.core import RunFinishedEvent, RunFinishedSuccessOutcome, RunStartedEvent
from httpx import ASGITransport, AsyncClient

from agent_core.api import create_app
from agent_core.auth.policy import AuthenticatedAgentCaller
from agent_core.store.postgres import StoredEvent
from agent_core.supervisor import RunCapacityExceeded

RUN_ID = "019504e8-4b7d-7a31-9c2d-123456789abc"
THREAD_ID = "019504e8-4b7c-7f3a-8c2d-123456789abc"


class FakeService:
    def __init__(self) -> None:
        self.aborted: list[str] = []

    async def submit(self, payload: bytes, caller: AuthenticatedAgentCaller) -> str:
        assert caller.agent_subject == "agtsub:v1:test"
        assert json.loads(payload)["runId"] == RUN_ID
        return RUN_ID

    async def stream(
        self,
        run_id: str,
        *,
        after_sequence: int,
    ) -> AsyncIterator[StoredEvent]:
        assert run_id == RUN_ID
        assert after_sequence == 0
        yield StoredEvent(
            1,
            "019504e8-4b7e-7b32-ac2d-123456789abc",
            RunStartedEvent(thread_id=THREAD_ID, run_id=RUN_ID).model_dump(
                mode="json", by_alias=True
            ),
        )
        yield StoredEvent(
            2,
            "019504e8-4b7f-7b32-ac2d-123456789abc",
            RunFinishedEvent(
                thread_id=THREAD_ID,
                run_id=RUN_ID,
                outcome=RunFinishedSuccessOutcome(),
            ).model_dump(mode="json", by_alias=True),
        )

    async def abort(self, run_id: str, caller: AuthenticatedAgentCaller) -> None:
        del caller
        self.aborted.append(run_id)


class CapacityService(FakeService):
    async def submit(self, payload: bytes, caller: AuthenticatedAgentCaller) -> str:
        del payload, caller
        raise RunCapacityExceeded


async def _authenticate(
    authorization: str | None,
    scope: str,
) -> AuthenticatedAgentCaller:
    assert authorization == "Bearer test"
    assert scope in {"agent:run", "agent:abort"}
    return AuthenticatedAgentCaller(
        owner_issuer="issuer",
        owner_subject_hash=b"x" * 32,
        agent_subject="agtsub:v1:test",
    )


def _payload() -> dict[str, object]:
    return {
        "threadId": THREAD_ID,
        "runId": RUN_ID,
        "messages": [
            {
                "id": "019504e8-4b80-7b32-ac2d-123456789abc",
                "role": "user",
                "content": "hello",
            }
        ],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


@pytest.mark.asyncio
async def test_agui_route_streams_durable_events_with_sse_sequence_ids() -> None:
    app = create_app(service=FakeService(), authenticate=_authenticate)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://agent.test",
    ) as client:
        response = await client.post(
            "/ag-ui",
            json=_payload(),
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 1\ndata:" in response.text
    assert '"type":"RUN_STARTED"' in response.text
    assert "id: 2\ndata:" in response.text
    assert '"type":"RUN_FINISHED"' in response.text


@pytest.mark.asyncio
async def test_abort_route_is_an_explicit_separate_intent() -> None:
    service = FakeService()
    app = create_app(service=service, authenticate=_authenticate)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://agent.test",
    ) as client:
        response = await client.post(
            f"/runs/{RUN_ID}/abort",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 202
    assert service.aborted == [RUN_ID]


@pytest.mark.asyncio
async def test_capacity_exceeded_returns_retryable_503() -> None:
    app = create_app(service=CapacityService(), authenticate=_authenticate)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://agent.test",
    ) as client:
        response = await client.post(
            "/ag-ui",
            json=_payload(),
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "2"
    assert response.json()["error"]["code"] == "capacity_exceeded"
