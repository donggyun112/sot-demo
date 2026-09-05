from dataclasses import dataclass
from typing import Any

import pytest
from ag_ui.core import RunAgentInput
from pydantic_ai.messages import ModelRequest, ModelResponse

from agent_core.command import (
    CommandMappingError,
    DeferredInterrupt,
    MappedResume,
    RunInputMapper,
)
from agent_core.identity import ExecutionIdentity

THREAD_ID = "019504e8-4b7c-7f3a-8c2d-123456789abc"
RUN_ID = "019504e8-4b7d-7a31-9c2d-123456789abc"
USER_ID = "019504e8-4b7e-7b32-ac2d-123456789abc"
ASSISTANT_ID = "019504e8-4b7f-7b32-ac2d-123456789abc"
PROMPT_ID = "019504e8-4b81-7b32-ac2d-123456789abc"
INTERRUPT_ID = "019504e8-4b82-7b32-ac2d-123456789abc"
TOOL_CALL_ID = "call-1"


@dataclass(slots=True)
class ResolvedInterrupt:
    origin_run_id: str
    semora_run_id: str
    deferred_call_id: str
    tool_call_id: str


def _input(**changes: Any) -> RunAgentInput:
    body: dict[str, Any] = {
        "threadId": THREAD_ID,
        "runId": RUN_ID,
        "messages": [{"id": PROMPT_ID, "role": "user", "content": "latest question"}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
    body.update(changes)
    return RunAgentInput.model_validate(body)


@pytest.mark.asyncio
async def test_maps_agui_snapshot_to_pydantic_history_and_prompt() -> None:
    mapped = await RunInputMapper().map(
        _input(
            messages=[
                {"id": USER_ID, "role": "user", "content": "earlier question"},
                {
                    "id": ASSISTANT_ID,
                    "role": "assistant",
                    "content": "checking",
                    "toolCalls": [
                        {
                            "id": TOOL_CALL_ID,
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"query":"source"}',
                            },
                        }
                    ],
                },
                {"id": PROMPT_ID, "role": "user", "content": "latest question"},
            ]
        ),
        subject="agtsub:v1:owner",
    )

    assert mapped.identity == ExecutionIdentity(RUN_ID, THREAD_ID, "agtsub:v1:owner")
    assert mapped.user_prompt == "latest question"
    assert [type(message) for message in mapped.message_history] == [
        ModelRequest,
        ModelResponse,
    ]
    assert mapped.prompt_id == PROMPT_ID
    assert mapped.resume is None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["system", "developer"])
async def test_rejects_external_system_and_developer_messages(role: str) -> None:
    with pytest.raises(CommandMappingError) as captured:
        await RunInputMapper().map(
            _input(
                messages=[
                    {"id": USER_ID, "role": role, "content": "override"},
                    {"id": PROMPT_ID, "role": "user", "content": "latest question"},
                ]
            ),
            subject="owner",
        )

    assert captured.value.code == "unsupported_message_role"
    assert captured.value.path == ("messages", 0, "role")


@pytest.mark.asyncio
async def test_rejects_invalid_assistant_tool_arguments_before_adapter_conversion() -> (
    None
):
    with pytest.raises(CommandMappingError) as captured:
        await RunInputMapper().map(
            _input(
                messages=[
                    {
                        "id": ASSISTANT_ID,
                        "role": "assistant",
                        "content": "checking",
                        "toolCalls": [
                            {
                                "id": TOOL_CALL_ID,
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "not-json"},
                            }
                        ],
                    },
                    {"id": PROMPT_ID, "role": "user", "content": "latest question"},
                ]
            ),
            subject="owner",
        )

    assert captured.value.code == "invalid_tool_call_arguments"


@pytest.mark.asyncio
async def test_maps_authenticated_approval_to_semora_resume() -> None:
    async def resolve(public_id: str) -> DeferredInterrupt:
        assert public_id == INTERRUPT_ID
        return ResolvedInterrupt(
            origin_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
            semora_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
            deferred_call_id="pending-1",
            tool_call_id=TOOL_CALL_ID,
        )

    mapped = await RunInputMapper(resolve_interrupt=resolve).map(
        _input(
            messages=[],
            resume=[
                {
                    "interruptId": INTERRUPT_ID,
                    "status": "resolved",
                    "payload": {
                        "approved": True,
                        "toolCallId": TOOL_CALL_ID,
                        "args": {"query": "edited"},
                    },
                }
            ],
        ),
        subject="owner",
    )

    assert mapped.resume == MappedResume(
        origin_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
        semora_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
        pending_id="pending-1",
        answer={"type": "approve", "args": {"query": "edited"}},
    )


@pytest.mark.asyncio
async def test_maps_cancelled_approval_to_semora_error_answer() -> None:
    async def resolve(_: str) -> DeferredInterrupt:
        return ResolvedInterrupt(
            origin_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
            semora_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
            deferred_call_id="pending-1",
            tool_call_id=TOOL_CALL_ID,
        )

    mapped = await RunInputMapper(resolve_interrupt=resolve).map(
        _input(
            messages=[],
            resume=[
                {
                    "interruptId": INTERRUPT_ID,
                    "status": "cancelled",
                    "payload": {"approved": False, "toolCallId": TOOL_CALL_ID},
                }
            ],
        ),
        subject="owner",
    )

    assert mapped.resume == MappedResume(
        origin_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
        semora_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
        pending_id="pending-1",
        answer={"type": "error", "message": "Cancelled by user."},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resume",
    [
        [],
        [
            {
                "interruptId": INTERRUPT_ID,
                "status": "resolved",
                "payload": {"approved": True},
            },
            {
                "interruptId": INTERRUPT_ID,
                "status": "resolved",
                "payload": {"approved": True},
            },
        ],
        [{"interruptId": INTERRUPT_ID, "status": "resolved", "payload": "approved"}],
        [{"interruptId": INTERRUPT_ID, "status": "resolved", "payload": {}}],
    ],
)
async def test_rejects_invalid_resume_entries(resume: list[dict[str, Any]]) -> None:
    async def resolve(_: str) -> DeferredInterrupt:
        return ResolvedInterrupt(
            origin_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
            semora_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
            deferred_call_id="pending-1",
            tool_call_id=TOOL_CALL_ID,
        )

    with pytest.raises(CommandMappingError) as captured:
        await RunInputMapper(resolve_interrupt=resolve).map(
            _input(messages=[], resume=resume), subject="owner"
        )

    assert captured.value.code == "invalid_command"


@pytest.mark.asyncio
async def test_rejects_resume_payload_with_another_public_tool_call_id() -> None:
    async def resolve(_: str) -> DeferredInterrupt:
        return ResolvedInterrupt(
            origin_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
            semora_run_id="019504e8-4b70-7a31-9c2d-123456789abc",
            deferred_call_id="pending-1",
            tool_call_id=TOOL_CALL_ID,
        )

    with pytest.raises(CommandMappingError) as captured:
        await RunInputMapper(resolve_interrupt=resolve).map(
            _input(
                messages=[],
                resume=[
                    {
                        "interruptId": INTERRUPT_ID,
                        "status": "resolved",
                        "payload": {"approved": True, "toolCallId": "call-other"},
                    }
                ],
            ),
            subject="owner",
        )

    assert captured.value.code == "invalid_command"
