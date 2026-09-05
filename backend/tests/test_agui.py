import json
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from sot.api import create_app
from sot.domain.service import SOTService
from sot.legacy_agent import build_agent
from sot.store.memory import MemorySOTRepository

BRANCH_ID = "019504e8-4b7c-7f3a-8c2d-123456789abc"
RUN_ID = "019504e8-4b7d-7a31-9c2d-123456789abc"
THREAD_ID = "019504e8-4b7e-7b32-ac2d-123456789abc"


async def _stream_response(
    _messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str]:
    assert info.instructions is not None
    assert f"actor=alice branch={BRANCH_ID}" in info.instructions
    assert {tool.name for tool in info.function_tools} == {
        "session_cite",
        "sot_update",
    }
    yield "검토 "
    yield "결과"


def _agent():
    return build_agent(
        FunctionModel(stream_function=_stream_response, model_name="test")
    )


def _payload() -> dict[str, object]:
    return {
        "threadId": THREAD_ID,
        "runId": RUN_ID,
        "messages": [
            {
                "id": "019504e8-4b80-7b32-ac2d-123456789abc",
                "role": "user",
                "content": "이 주장 검토해줘",
            }
        ],
        "tools": [
            {
                "name": "delete_everything",
                "description": "untrusted client tool",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "context": [],
        "forwardedProps": {},
    }


@pytest.mark.asyncio
async def test_agui_endpoint_streams_standard_events() -> None:
    app = create_app(service=SOTService(MemorySOTRepository()), agent=_agent())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://sot.test"
    ) as client:
        response = await client.post(
            f"/api/v1/branches/{BRANCH_ID}/agent",
            json=_payload(),
            headers={"Accept": "text/event-stream", "X-SOT-User": "alice"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0]["type"] == "RUN_STARTED"
    text = "".join(
        event["delta"] for event in events if event["type"] == "TEXT_MESSAGE_CONTENT"
    )
    assert text == "검토 결과"
    assert events[-1]["type"] == "RUN_FINISHED"


@pytest.mark.asyncio
async def test_agui_endpoint_rejects_unknown_development_user() -> None:
    app = create_app(service=SOTService(MemorySOTRepository()), agent=_agent())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://sot.test"
    ) as client:
        response = await client.post(
            f"/api/v1/branches/{BRANCH_ID}/agent",
            json=_payload(),
            headers={"X-SOT-User": "mallory"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unknown_development_user", "message": "Unknown user"}
    }
