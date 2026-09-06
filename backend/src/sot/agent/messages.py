"""Translate canonical Turns at the model boundary, including versioned tool data."""

import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from sot.session.contracts import NewTurn, Turn


class _ToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    schema_version: Literal["sot.tool-turn.v1"] = Field(alias="schema")
    tool_name: str = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)


class _ToolCall(_ToolEnvelope):
    kind: Literal["call"]
    args: dict[str, JsonValue]


class _ToolReturn(_ToolEnvelope):
    kind: Literal["return"]
    result: JsonValue


_TOOL_ENVELOPE: TypeAdapter[_ToolCall | _ToolReturn] = TypeAdapter(
    Annotated[_ToolCall | _ToolReturn, Field(discriminator="kind")]
)


def encode_tool_call(
    *, tool_name: str, tool_call_id: str, args: dict[str, JsonValue]
) -> NewTurn:
    envelope = _ToolCall(
        schema="sot.tool-turn.v1",
        kind="call",
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        args=args,
    )
    return NewTurn("tool", envelope.model_dump_json(by_alias=True))


def encode_tool_return(
    *, tool_name: str, tool_call_id: str, result: JsonValue
) -> NewTurn:
    envelope = _ToolReturn(
        schema="sot.tool-turn.v1",
        kind="return",
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        result=result,
    )
    return NewTurn("tool", envelope.model_dump_json(by_alias=True))


def turns_to_model_messages(turns: tuple[Turn, ...]) -> list[ModelMessage]:
    messages: list[ModelMessage] = []
    for turn in sorted(turns, key=lambda item: item.ordinal):
        part: UserPromptPart | TextPart | ToolCallPart | ToolReturnPart
        if turn.role == "user":
            part = UserPromptPart(turn.content, timestamp=turn.created_at)
        elif turn.role == "assistant":
            part = TextPart(turn.content)
        else:
            try:
                envelope = _TOOL_ENVELOPE.validate_python(json.loads(turn.content))
            except (ValidationError, json.JSONDecodeError):
                raise ValueError("stored tool turn is invalid") from None
            if isinstance(envelope, _ToolCall):
                part = ToolCallPart(
                    envelope.tool_name, envelope.args, envelope.tool_call_id
                )
            else:
                part = ToolReturnPart(
                    envelope.tool_name,
                    envelope.result,
                    envelope.tool_call_id,
                    timestamp=turn.created_at,
                )
        previous = messages[-1] if messages else None
        if isinstance(part, (UserPromptPart, ToolReturnPart)):
            if isinstance(previous, ModelRequest):
                previous.parts = [*previous.parts, part]
            else:
                messages.append(ModelRequest(parts=[part]))
        elif isinstance(previous, ModelResponse):
            previous.parts = [*previous.parts, part]
        else:
            messages.append(ModelResponse(parts=[part], timestamp=turn.created_at))
    return messages
