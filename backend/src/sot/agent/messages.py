"""Translate canonical Turns at the model boundary, including versioned tool data."""

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, Literal, Never

from pydantic import (
    AwareDatetime,
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
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_core import ErrorDetails

from sot.agent.deps import CompletedTurnReference
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


class _RetryError(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    error_type: str = Field(alias="type", min_length=1)
    location: tuple[str | int, ...] = Field(alias="loc")
    message: str = Field(alias="msg", min_length=1)
    input: JsonValue


_RetryContent = (
    Annotated[str, Field(min_length=1)]
    | Annotated[list[_RetryError], Field(min_length=1)]
)


class _ToolRetry(_ToolEnvelope):
    kind: Literal["retry"]
    content: _RetryContent
    timestamp: AwareDatetime


_TOOL_ENVELOPE: TypeAdapter[_ToolCall | _ToolReturn | _ToolRetry] = TypeAdapter(
    Annotated[_ToolCall | _ToolReturn | _ToolRetry, Field(discriminator="kind")]
)
_TOOL_ARGS: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(
    dict[str, JsonValue], config=ConfigDict(strict=True, allow_inf_nan=False)
)
_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(
    JsonValue, config=ConfigDict(strict=True, allow_inf_nan=False)
)
_RETRY_CONTENT: TypeAdapter[_RetryContent] = TypeAdapter(
    _RetryContent, config=ConfigDict(strict=True, allow_inf_nan=False)
)


def _reject_non_json_constant(_value: str) -> Never:
    raise ValueError


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


def encode_tool_retry(
    *,
    tool_name: str,
    tool_call_id: str,
    content: list[ErrorDetails] | str,
    timestamp: datetime,
) -> NewTurn:
    envelope = _ToolRetry(
        schema="sot.tool-turn.v1",
        kind="retry",
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        content=_RETRY_CONTENT.validate_python(content),
        timestamp=timestamp,
    )
    return NewTurn("tool", envelope.model_dump_json(by_alias=True))


def completed_turn_references(
    turns: tuple[Turn, ...],
) -> tuple[CompletedTurnReference, ...]:
    """Map authorized history without promoting any conversation text to instructions."""
    references: list[CompletedTurnReference] = []
    for turn in sorted(turns, key=lambda turn: turn.ordinal):
        if turn.role in {"user", "assistant"}:
            references.append(
                CompletedTurnReference(
                    turn.id, turn.ordinal, len(references) + 1, turn.role
                )
            )
    return tuple(references)


def turns_to_model_messages(turns: tuple[Turn, ...]) -> list[ModelMessage]:
    messages: list[ModelMessage] = []
    for turn in sorted(turns, key=lambda item: item.ordinal):
        part: (
            UserPromptPart | TextPart | ToolCallPart | ToolReturnPart | RetryPromptPart
        )
        if turn.role == "user":
            part = UserPromptPart(turn.content, timestamp=turn.created_at)
        elif turn.role == "assistant":
            part = TextPart(turn.content)
        else:
            try:
                json.loads(turn.content, parse_constant=_reject_non_json_constant)
                envelope = _TOOL_ENVELOPE.validate_json(turn.content)
            except ValueError:
                raise ValueError("stored tool turn is invalid") from None
            if isinstance(envelope, _ToolCall):
                part = ToolCallPart(
                    envelope.tool_name, envelope.args, envelope.tool_call_id
                )
            elif isinstance(envelope, _ToolReturn):
                part = ToolReturnPart(
                    envelope.tool_name,
                    envelope.result,
                    envelope.tool_call_id,
                    timestamp=turn.created_at,
                )
            else:
                content: list[ErrorDetails] | str
                if isinstance(envelope.content, str):
                    content = envelope.content
                else:
                    content = [
                        ErrorDetails(
                            type=error.error_type,
                            loc=error.location,
                            msg=error.message,
                            input=error.input,
                        )
                        for error in envelope.content
                    ]
                part = RetryPromptPart(
                    content,
                    tool_name=envelope.tool_name,
                    tool_call_id=envelope.tool_call_id,
                    timestamp=envelope.timestamp,
                )
        previous = messages[-1] if messages else None
        if isinstance(part, (UserPromptPart, ToolReturnPart, RetryPromptPart)):
            if isinstance(previous, ModelRequest):
                previous.parts = [*previous.parts, part]
            else:
                messages.append(ModelRequest(parts=[part]))
        elif isinstance(previous, ModelResponse):
            previous.parts = [*previous.parts, part]
        else:
            messages.append(ModelResponse(parts=[part], timestamp=turn.created_at))
    return messages


def _normalized_tool_args(args: str | dict[str, Any] | None) -> dict[str, JsonValue]:
    try:
        value: object = {} if args is None else args
        if isinstance(args, str):
            value = json.loads(args)
        if not isinstance(value, dict):
            raise TypeError
        return _TOOL_ARGS.validate_python(value)
    except (json.JSONDecodeError, TypeError, ValidationError, ValueError):
        raise ValueError("completed agent message is invalid") from None


def completed_messages_to_new_turns(
    messages: Sequence[ModelMessage],
) -> tuple[NewTurn, ...]:
    """Map only completed transcript parts into the closed Turn representation."""
    turns: list[NewTurn] = []
    try:
        for message in messages:
            if isinstance(message, ModelRequest):
                for request_part in message.parts:
                    if isinstance(request_part, SystemPromptPart):
                        continue
                    if isinstance(request_part, RetryPromptPart):
                        if request_part.tool_name is None:
                            raise TypeError
                        turns.append(
                            encode_tool_retry(
                                tool_name=request_part.tool_name,
                                tool_call_id=request_part.tool_call_id,
                                content=request_part.content,
                                timestamp=request_part.timestamp,
                            )
                        )
                    elif isinstance(request_part, UserPromptPart):
                        if not isinstance(request_part.content, str):
                            raise TypeError
                        turns.append(NewTurn("user", request_part.content))
                    elif isinstance(request_part, ToolReturnPart):
                        turns.append(
                            encode_tool_return(
                                tool_name=request_part.tool_name,
                                tool_call_id=request_part.tool_call_id,
                                result=_JSON_VALUE.validate_python(
                                    request_part.content
                                ),
                            )
                        )
                    else:
                        raise TypeError
            elif isinstance(message, ModelResponse):
                for response_part in message.parts:
                    if isinstance(response_part, ThinkingPart):
                        continue
                    if isinstance(response_part, TextPart):
                        turns.append(NewTurn("assistant", response_part.content))
                    elif isinstance(response_part, ToolCallPart):
                        turns.append(
                            encode_tool_call(
                                tool_name=response_part.tool_name,
                                tool_call_id=response_part.tool_call_id,
                                args=_normalized_tool_args(response_part.args),
                            )
                        )
                    else:
                        raise TypeError
            else:
                raise TypeError
    except (TypeError, ValidationError, ValueError):
        raise ValueError("completed agent message is invalid") from None
    return tuple(turns)


class ToolRecords:
    """Reads the tool envelope this module writes, for the session transcript."""

    def call_name(self, content: str) -> str | None:
        try:
            payload = json.loads(content)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("kind") != "call":
            return None
        name = payload.get("tool_name")
        return name if isinstance(name, str) and name else None
