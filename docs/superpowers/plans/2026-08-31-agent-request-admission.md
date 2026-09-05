# Agent Request Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the transport-independent Agent Server request-admission core that strictly parses official AG-UI `RunAgentInput`, enforces the approved UUIDv7 profile, and produces an RFC 8785 JCS SHA-256 payload hash.

**Architecture:** A single pure module accepts raw JSON bytes and returns an immutable admitted value. It uses the official AG-UI Pydantic model, rejects SDK-permitted unknown fields recursively, normalizes the parsed model to official camelCase JSON, canonicalizes it with JCS, and hashes those canonical bytes. HTTP/SSE, authentication, PostgreSQL, Redis and Semora remain outside this slice.

**Tech Stack:** Python 3.12+, `ag-ui-protocol`, Pydantic 2, Trail of Bits `rfc8785` 0.1.4, pytest

**Spec:** `docs/superpowers/plans/2026-08-30-agui-agent-boundary.md` sections 4.1 and 10.1

## Global Constraints

- The input type remains the official AG-UI `RunAgentInput`; no private recipe, cursor or recovery field is added.
- Validate canonical hyphenated UUIDv7 for `threadId`, `runId`, every `messages[].id`, and every `resume[].interruptId`.
- Semora, provider and tool-call identifiers remain opaque and are not inspected.
- Unknown schema fields are rejected, but keys inside schema-defined free-form JSON values such as `state`, `metadata` and `forwardedProps` remain valid.
- Hash the entire parsed, official camelCase `RunAgentInput` as `SHA-256(RFC8785_JCS_BYTES)`.
- JSON whitespace and object-member order do not affect the hash; array order and string content do.
- RFC 8785 I-JSON requirements apply, including rejection of duplicate object members and non-finite numbers.
- This directory has no Git metadata, so the plan records test checkpoints instead of commit steps.

---

### Task 1: Accepted input and canonical hash

**Files:**
- Create: `agent-server/src/agent_core/admission.py`
- Create: `agent-server/tests/test_admission.py`
- Modify: `agent-server/pyproject.toml`
- Modify: `agent-server/uv.lock`

**Interfaces:**
- Consumes: raw request body as `bytes`
- Produces: `admit_run_input(payload: bytes) -> AdmittedRunInput`
- Produces: immutable `AdmittedRunInput(input: RunAgentInput, canonical_payload: bytes, payload_hash: bytes)`
- Produces: `RunInputAdmissionError(code: AdmissionErrorCode, path: tuple[str | int, ...])`

- [x] **Step 1: Write the failing accepted-input test**

```python
from hashlib import sha256
import json

from agent_core.admission import admit_run_input

THREAD_ID = "019504e8-4b7c-7f3a-8c2d-123456789abc"
RUN_ID = "019504e8-4b7d-7a31-9c2d-123456789abc"
MESSAGE_ID = "019504e8-4b7e-7b32-ac2d-123456789abc"


def test_admits_official_input_and_hashes_jcs_payload() -> None:
    payload = {
        "tools": [],
        "messages": [{"role": "user", "content": "hello", "id": MESSAGE_ID}],
        "threadId": THREAD_ID,
        "forwardedProps": {"z": 1, "a": 2},
        "runId": RUN_ID,
        "context": [],
    }
    expected = (
        b'{"context":[],"forwardedProps":{"a":2,"z":1},'
        b'"messages":[{"content":"hello","id":"' + MESSAGE_ID.encode() +
        b'","role":"user"}],"runId":"' + RUN_ID.encode() +
        b'","threadId":"' + THREAD_ID.encode() + b'","tools":[]}'
    )

    admitted = admit_run_input(json.dumps(payload, indent=2).encode())

    assert admitted.input.run_id == RUN_ID
    assert admitted.canonical_payload == expected
    assert admitted.payload_hash == sha256(expected).digest()
```

- [x] **Step 2: Run the test and verify RED**

Run: `UV_CACHE_DIR=/tmp/sot-uv-cache uv run --offline pytest tests/test_admission.py::test_admits_official_input_and_hashes_jcs_payload -q`

Expected: collection fails because `agent_core.admission` does not exist.

- [x] **Step 3: Add the JCS dependency**

Add this runtime dependency to `pyproject.toml`:

```toml
"rfc8785>=0.1.4,<0.2",
```

Then run `UV_CACHE_DIR=/tmp/sot-uv-cache uv lock` and `UV_CACHE_DIR=/tmp/sot-uv-cache uv sync --offline` after the package is available in the lock/cache.

- [x] **Step 4: Implement the minimal accepted-input path**

Create `agent_core/admission.py` with:

```python
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Literal, TypeAlias

from ag_ui.core import RunAgentInput
from pydantic import ValidationError
import rfc8785

AdmissionErrorCode: TypeAlias = Literal[
    "invalid_json",
    "invalid_schema",
    "unknown_field",
    "invalid_identifier",
    "non_canonical_json",
]
JsonPathPart: TypeAlias = str | int


class RunInputAdmissionError(ValueError):
    def __init__(
        self,
        code: AdmissionErrorCode,
        path: tuple[JsonPathPart, ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.path = path


@dataclass(frozen=True, slots=True)
class AdmittedRunInput:
    input: RunAgentInput
    canonical_payload: bytes
    payload_hash: bytes


def admit_run_input(payload: bytes) -> AdmittedRunInput:
    try:
        parsed: Any = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RunInputAdmissionError("invalid_json") from error

    try:
        run_input = RunAgentInput.model_validate(parsed)
    except ValidationError as error:
        path = tuple(error.errors()[0]["loc"]) if error.errors() else ()
        raise RunInputAdmissionError("invalid_schema", path) from error

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
```

- [x] **Step 5: Run the focused test and verify GREEN**

Run: `UV_CACHE_DIR=/tmp/sot-uv-cache uv run --offline pytest tests/test_admission.py::test_admits_official_input_and_hashes_jcs_payload -q`

Expected: `1 passed`.

### Task 2: Strict JSON and schema rejection

**Files:**
- Modify: `agent-server/src/agent_core/admission.py`
- Modify: `agent-server/tests/test_admission.py`

**Interfaces:**
- Consumes: the Task 1 `admit_run_input` API
- Produces: `invalid_json` for duplicate members/non-finite constants, `invalid_schema` for official-model failures, and `unknown_field` with a camelCase path for extra schema fields

- [x] **Step 1: Add failing strictness tests**

```python
import pytest

from agent_core.admission import RunInputAdmissionError


def test_rejects_unknown_nested_schema_field(valid_payload: dict[str, object]) -> None:
    messages = valid_payload["messages"]
    assert isinstance(messages, list)
    assert isinstance(messages[0], dict)
    messages[0]["unexpected"] = True

    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(json.dumps(valid_payload).encode())

    assert caught.value.code == "unknown_field"
    assert caught.value.path == ("messages", 0, "unexpected")


def test_allows_arbitrary_keys_inside_free_form_json(valid_payload: dict[str, object]) -> None:
    valid_payload["state"] = {"productExtension": {"anything": True}}

    admitted = admit_run_input(json.dumps(valid_payload).encode())

    assert admitted.input.state == {"productExtension": {"anything": True}}


def test_rejects_duplicate_json_members() -> None:
    raw = (
        b'{"threadId":"' + THREAD_ID.encode() + b'","threadId":"' + THREAD_ID.encode()
        + b'","runId":"' + RUN_ID.encode()
        + b'","messages":[],"tools":[],"context":[],"forwardedProps":{}}'
    )

    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(raw)

    assert caught.value.code == "invalid_json"
```

- [x] **Step 2: Run the strictness tests and verify RED**

Run: `UV_CACHE_DIR=/tmp/sot-uv-cache uv run --offline pytest tests/test_admission.py -k 'unknown or arbitrary or duplicate' -q`

Expected: unknown-field and duplicate-member tests fail because the SDK/json parser currently accepts them.

- [x] **Step 3: Implement recursive extra detection and duplicate rejection**

Add a JSON `object_pairs_hook` that raises on repeated names and a recursive walker that checks `BaseModel.model_extra`. The walker descends through model fields and lists/tuples, uses each Pydantic field's serialization alias for paths, and does not interpret ordinary dictionaries as schemas.

```python
from pydantic import BaseModel


class _DuplicateMember(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateMember(key)
        result[key] = value
    return result


def _reject_unknown_fields(value: Any, path: tuple[JsonPathPart, ...] = ()) -> None:
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
```

Pass `_unique_object` to `json.loads`, reject `NaN`/`Infinity` through `parse_constant`, catch `_DuplicateMember`, and call `_reject_unknown_fields(run_input)` before canonicalization.

- [x] **Step 4: Run the strictness tests and verify GREEN**

Run: `UV_CACHE_DIR=/tmp/sot-uv-cache uv run --offline pytest tests/test_admission.py -k 'unknown or arbitrary or duplicate' -q`

Expected: all selected tests pass.

### Task 3: UUIDv7 profile

**Files:**
- Modify: `agent-server/src/agent_core/admission.py`
- Modify: `agent-server/tests/test_admission.py`
- Modify: `agent-server/README.md`

**Interfaces:**
- Consumes: parsed official `RunAgentInput`
- Produces: `invalid_identifier` with exact camelCase path for non-canonical/non-v7 profile IDs

- [x] **Step 1: Add failing table-driven identifier tests**

```python
@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (lambda body: body.__setitem__("threadId", "not-a-uuid"), ("threadId",)),
        (lambda body: body.__setitem__("runId", str(uuid4())), ("runId",)),
        (
            lambda body: body["messages"][0].__setitem__("id", MESSAGE_ID.upper()),
            ("messages", 0, "id"),
        ),
        (
            lambda body: body.__setitem__(
                "resume",
                [{"interruptId": str(uuid4()), "status": "resolved", "payload": {}}],
            ),
            ("resume", 0, "interruptId"),
        ),
    ],
)
def test_rejects_identifier_outside_uuidv7_profile(
    valid_payload: dict[str, object],
    mutate: Callable[[dict[str, object]], None],
    expected_path: tuple[str | int, ...],
) -> None:
    mutate(valid_payload)

    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(json.dumps(valid_payload).encode())

    assert caught.value.code == "invalid_identifier"
    assert caught.value.path == expected_path
```

Add a separate accepted test with an opaque assistant `toolCalls[].id` to ensure tool/provider identifiers are not subjected to UUID validation.

- [x] **Step 2: Run the UUID tests and verify RED**

Run: `UV_CACHE_DIR=/tmp/sot-uv-cache uv run --offline pytest tests/test_admission.py -k 'identifier or opaque' -q`

Expected: invalid IDs are accepted because profile validation is not implemented.

- [x] **Step 3: Implement UUIDv7 profile validation**

```python
from uuid import UUID


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
```

Call `_validate_identifier_profile(run_input)` after schema/unknown-field validation and before canonicalization.

- [x] **Step 4: Run focused and full verification**

Run:

```bash
UV_CACHE_DIR=/tmp/sot-uv-cache uv run --offline pytest tests/test_admission.py -q
UV_CACHE_DIR=/tmp/sot-uv-cache uv run --offline pytest -q
UV_CACHE_DIR=/tmp/sot-uv-cache uv run --offline ruff check .
UV_CACHE_DIR=/tmp/sot-uv-cache uv run --offline mypy src tests
```

Expected: all admission tests and the full suite pass; Ruff and mypy report no issues.

- [x] **Step 5: Update the Agent Server status**

Update `agent-server/README.md` to state that the pure admission core is implemented and explicitly repeat that `/ag-ui`, persistence, authentication and Semora execution are still not wired.
