from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from sot.agent.messages import (
    encode_tool_call,
    encode_tool_return,
    turns_to_model_messages,
)
from sot.session.contracts import NewTurn, Turn
from sot.shared.ids import BranchId, WorkspaceId

NOW = datetime(2026, 9, 6, tzinfo=UTC)
WORKSPACE = WorkspaceId(uuid4())
BRANCH = BranchId(uuid4())


def stored(message: NewTurn, ordinal: int) -> Turn:
    return Turn(uuid4(), WORKSPACE, BRANCH, ordinal, message.role, message.content, NOW)


def test_mapping_sorts_ordinals_and_groups_request_and_response_parts() -> None:
    turns = (
        stored(NewTurn("user", "question"), 1),
        stored(NewTurn("assistant", "checking"), 2),
        stored(
            encode_tool_call(
                tool_name="session_cite",
                tool_call_id="call-1",
                args={"summary": "결정", "turn_ids": ["turn-1"]},
            ),
            3,
        ),
        stored(
            encode_tool_return(
                tool_name="session_cite",
                tool_call_id="call-1",
                result={"citeId": "cite-1"},
            ),
            4,
        ),
        stored(NewTurn("assistant", "done"), 5),
    )
    messages = turns_to_model_messages(tuple(reversed(turns)))
    assert len(messages) == 4
    request, call, returned, answer = messages
    assert isinstance(request, ModelRequest)
    assert request.parts == [UserPromptPart("question", timestamp=NOW)]
    assert isinstance(call, ModelResponse)
    assert call.parts == [
        TextPart("checking"),
        ToolCallPart(
            "session_cite", {"summary": "결정", "turn_ids": ["turn-1"]}, "call-1"
        ),
    ]
    assert call.timestamp == NOW
    assert isinstance(returned, ModelRequest)
    assert returned.parts == [
        ToolReturnPart("session_cite", {"citeId": "cite-1"}, "call-1", timestamp=NOW)
    ]
    assert isinstance(answer, ModelResponse)
    assert answer.parts == [TextPart("done")]


def test_empty_history_maps_to_empty_messages() -> None:
    assert turns_to_model_messages(()) == []


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_tool_encoder_rejects_non_json_numbers(number: float) -> None:
    with pytest.raises(ValueError):
        encode_tool_call(tool_name="x", tool_call_id="id", args={"nested": [number]})
    with pytest.raises(ValueError):
        encode_tool_return(tool_name="x", tool_call_id="id", result={"nested": number})


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        "{}",
        '{"schema":"sot.tool-turn.v2","kind":"call","tool_name":"x","tool_call_id":"id","args":{}}',
        '{"schema":"sot.tool-turn.v1","kind":"unknown","tool_name":"x","tool_call_id":"id","args":{}}',
        '{"schema":"sot.tool-turn.v1","kind":"call","tool_name":"x","args":{}}',
        '{"schema":"sot.tool-turn.v1","kind":"call","tool_name":"x","tool_call_id":"id","args":{},"secret":"credential"}',
        '{"schema":"sot.tool-turn.v1","kind":"return","tool_name":"x","tool_call_id":"id","result":NaN}',
    ],
)
def test_malformed_or_unknown_tool_envelope_is_rejected_safely(content: str) -> None:
    with pytest.raises(ValueError, match="^stored tool turn is invalid$"):
        turns_to_model_messages((stored(NewTurn("tool", content), 1),))


def test_json_user_and_assistant_text_remains_text() -> None:
    envelope = encode_tool_call(tool_name="x", tool_call_id="id", args={})
    messages = turns_to_model_messages(
        (
            stored(replace(envelope, role="user"), 1),
            stored(replace(envelope, role="assistant"), 2),
        )
    )
    assert isinstance(messages[0], ModelRequest)
    assert isinstance(messages[0].parts[0], UserPromptPart)
    assert messages[0].parts[0].content == envelope.content
    assert isinstance(messages[1], ModelResponse)
    assert isinstance(messages[1].parts[0], TextPart)
    assert messages[1].parts[0].content == envelope.content
