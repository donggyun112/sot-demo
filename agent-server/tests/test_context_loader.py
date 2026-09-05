from typing import Any

import pytest
from ag_ui.core import Context

from agent_core.context import AgentContextRecord, ContextLoader, LoadedAgentContext
from agent_core.identity import ExecutionIdentity


class ProfileContextSource:
    name = "profile"

    async def load(self, execution: ExecutionIdentity) -> list[AgentContextRecord]:
        assert execution == ExecutionIdentity(
            "run-1", "conversation-1", "agtsub:v1:owner"
        )
        return [AgentContextRecord(key="language", value="ko")]


@pytest.mark.asyncio
async def test_loader_combines_request_data_with_agent_owned_records() -> None:
    loaded = await ContextLoader([ProfileContextSource()]).load(
        execution=ExecutionIdentity("run-1", "conversation-1", "agtsub:v1:owner"),
        request_context=[Context(description="topic", value="agreement")],
        request_state={"draft": True},
    )

    assert loaded == LoadedAgentContext(
        request_context=(Context(description="topic", value="agreement"),),
        request_state={"draft": True},
        agent_records=(
            AgentContextRecord(key="language", value="ko", source="profile"),
        ),
    )
    assert loaded.as_untrusted_payload() == {
        "request_context": [{"description": "topic", "value": "agreement"}],
        "request_state": {"draft": True},
        "agent_records": [{"source": "profile", "key": "language", "value": "ko"}],
    }


@pytest.mark.asyncio
async def test_loader_rejects_source_spoofing_another_source_name() -> None:
    class InvalidSource:
        name = "profile"

        async def load(self, _: ExecutionIdentity) -> list[AgentContextRecord]:
            return [AgentContextRecord(key="language", value="ko", source="caller")]

    with pytest.raises(ValueError, match="must not set source"):
        await ContextLoader([InvalidSource()]).load(
            execution=ExecutionIdentity("run-1", "conversation-1", "owner"),
            request_context=[],
            request_state=None,
        )


def test_loaded_context_is_json_serializable_data() -> None:
    loaded = LoadedAgentContext(
        request_context=(),
        request_state=None,
        agent_records=(AgentContextRecord(key="count", value=3, source="stats"),),
    )
    payload: dict[str, Any] = loaded.as_untrusted_payload()
    assert payload["agent_records"] == [{"source": "stats", "key": "count", "value": 3}]
