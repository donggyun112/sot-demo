from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_core import ErrorDetails

from sot.agent.messages import (
    completed_messages_to_new_turns,
    encode_tool_call,
    encode_tool_retry,
    encode_tool_return,
    turns_to_model_messages,
)
from sot.session.contracts import NewTurn, Turn
from sot.shared.ids import BranchId, UserId, WorkspaceId

NOW = datetime(2026, 9, 6, tzinfo=UTC)
WORKSPACE = WorkspaceId(uuid4())
BRANCH = BranchId(uuid4())
SPEAKER = UserId(uuid4())


def stored(message: NewTurn, ordinal: int) -> Turn:
    return Turn(
        uuid4(),
        WORKSPACE,
        BRANCH,
        ordinal,
        message.role,
        message.content,
        NOW,
        SPEAKER,
    )


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


def test_tool_retry_round_trips_in_request_direction_with_timestamp() -> None:
    retry_content: list[ErrorDetails] = [
        {
            "type": "int_parsing",
            "loc": ("value",),
            "msg": "Input should be a valid integer",
            "input": "bad",
        }
    ]
    turns = (
        stored(
            encode_tool_call(
                tool_name="integer_tool",
                tool_call_id="call-bad",
                args={"value": "bad"},
            ),
            1,
        ),
        stored(
            encode_tool_retry(
                tool_name="integer_tool",
                tool_call_id="call-bad",
                content=retry_content,
                timestamp=NOW,
            ),
            2,
        ),
        stored(
            encode_tool_call(
                tool_name="integer_tool",
                tool_call_id="call-good",
                args={"value": 7},
            ),
            3,
        ),
        stored(
            encode_tool_return(
                tool_name="integer_tool",
                tool_call_id="call-good",
                result="value=7",
            ),
            4,
        ),
    )

    messages = turns_to_model_messages(turns)

    assert len(messages) == 4
    assert isinstance(messages[0], ModelResponse)
    assert messages[0].parts == [
        ToolCallPart("integer_tool", {"value": "bad"}, "call-bad")
    ]
    assert isinstance(messages[1], ModelRequest)
    assert messages[1].parts == [
        RetryPromptPart(
            retry_content,
            tool_name="integer_tool",
            tool_call_id="call-bad",
            timestamp=NOW,
        )
    ]
    assert isinstance(messages[2], ModelResponse)
    assert messages[2].parts == [
        ToolCallPart("integer_tool", {"value": 7}, "call-good")
    ]
    assert isinstance(messages[3], ModelRequest)
    assert messages[3].parts == [
        ToolReturnPart("integer_tool", "value=7", "call-good", timestamp=NOW)
    ]


def test_string_tool_retry_maps_from_completion_and_round_trips() -> None:
    completed = completed_messages_to_new_turns(
        (
            ModelRequest(
                parts=[
                    RetryPromptPart(
                        "Try the tool arguments again",
                        tool_name="integer_tool",
                        tool_call_id="call-bad",
                        timestamp=NOW,
                    )
                ]
            ),
        )
    )

    messages = turns_to_model_messages((stored(completed[0], 1),))

    assert isinstance(messages[0], ModelRequest)
    assert messages[0].parts == [
        RetryPromptPart(
            "Try the tool arguments again",
            tool_name="integer_tool",
            tool_call_id="call-bad",
            timestamp=NOW,
        )
    ]


def test_retry_rejects_non_json_validation_input() -> None:
    with pytest.raises(ValueError, match="^completed agent message is invalid$"):
        completed_messages_to_new_turns(
            (
                ModelRequest(
                    parts=[
                        RetryPromptPart(
                            [
                                {
                                    "type": "value_error",
                                    "loc": ("value",),
                                    "msg": "Invalid value",
                                    "input": object(),
                                }
                            ],
                            tool_name="integer_tool",
                            tool_call_id="call-bad",
                            timestamp=NOW,
                        )
                    ]
                ),
            )
        )


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
        '{"schema":"sot.tool-turn.v1","kind":"retry","tool_name":"x","tool_call_id":"id","content":"try again"}',
        '{"schema":"sot.tool-turn.v1","kind":"retry","tool_name":"x","tool_call_id":"id","content":{},"timestamp":1}',
        '{"schema":"sot.tool-turn.v1","kind":"retry","tool_name":"x","tool_call_id":"id","content":"","timestamp":"2026-09-06T00:00:00Z"}',
        '{"schema":"sot.tool-turn.v1","kind":"retry","tool_name":"x","tool_call_id":"id","content":[{"type":"bad","loc":["value"],"msg":"bad","input":1,"secret":"credential"}],"timestamp":1}',
        '{"schema":"sot.tool-turn.v1","kind":"retry","tool_name":"x","tool_call_id":"id","content":[{"type":"bad","loc":["value"],"msg":"bad","input":NaN}],"timestamp":"2026-09-06T00:00:00Z"}',
        '{"schema":"sot.tool-turn.v1","kind":"retry","tool_name":"x","tool_call_id":"id","content":"try again","timestamp":"not-a-timestamp"}',
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
