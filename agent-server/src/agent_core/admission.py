import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

import rfc8785
from ag_ui.core import RunAgentInput
from pydantic import BaseModel, ValidationError

type AdmissionErrorCode = Literal[
    "invalid_json",
    "invalid_schema",
    "unknown_field",
    "invalid_identifier",
    "non_canonical_json",
]
type JsonPathPart = str | int


class RunInputAdmissionError(ValueError):
    def __init__(
        self,
        code: AdmissionErrorCode,
        path: tuple[JsonPathPart, ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.path = path


class _DuplicateMember(ValueError):
    pass


class _NonFiniteNumber(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateMember(key)
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise _NonFiniteNumber(value)


@dataclass(frozen=True, slots=True)
class AdmittedRunInput:
    input: RunAgentInput
    canonical_payload: bytes
    payload_hash: bytes


def _reject_unknown_fields(
    value: Any,
    path: tuple[JsonPathPart, ...] = (),
) -> None:
    if isinstance(value, BaseModel):
        if value.model_extra:
            key = min(value.model_extra)
            raise RunInputAdmissionError("unknown_field", (*path, key))
        for name, field in type(value).model_fields.items():
            alias = field.serialization_alias or field.alias or name
            _reject_unknown_fields(getattr(value, name), (*path, alias))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_unknown_fields(item, (*path, index))


def _require_uuid7(value: str, path: tuple[JsonPathPart, ...]) -> None:
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise RunInputAdmissionError("invalid_identifier", path) from error
    if parsed.version != 7 or str(parsed) != value:
        raise RunInputAdmissionError("invalid_identifier", path)


def _validate_identifier_profile(run_input: RunAgentInput) -> None:
    _require_uuid7(run_input.thread_id, ("threadId",))
    _require_uuid7(run_input.run_id, ("runId",))
    for index, message in enumerate(run_input.messages):
        _require_uuid7(message.id, ("messages", index, "id"))
    for index, resume in enumerate(run_input.resume or ()):
        _require_uuid7(resume.interrupt_id, ("resume", index, "interruptId"))


def admit_run_input(payload: bytes) -> AdmittedRunInput:
    try:
        parsed: Any = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_finite,
        )
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        _DuplicateMember,
        _NonFiniteNumber,
    ) as error:
        raise RunInputAdmissionError("invalid_json") from error

    try:
        run_input = RunAgentInput.model_validate(parsed)
    except ValidationError as error:
        path = tuple(error.errors()[0]["loc"]) if error.errors() else ()
        raise RunInputAdmissionError("invalid_schema", path) from error

    _reject_unknown_fields(run_input)
    _validate_identifier_profile(run_input)
    normalized = run_input.model_dump(mode="json", by_alias=True)
    try:
        canonical_payload = rfc8785.dumps(normalized)
    except rfc8785.CanonicalizationError as error:
        raise RunInputAdmissionError("non_canonical_json") from error

    return AdmittedRunInput(
        input=run_input,
        canonical_payload=canonical_payload,
        payload_hash=sha256(canonical_payload).digest(),
    )
