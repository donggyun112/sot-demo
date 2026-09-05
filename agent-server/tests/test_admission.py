import json
from collections.abc import Callable
from hashlib import sha256
from typing import Any
from uuid import uuid4

import pytest

from agent_core.admission import RunInputAdmissionError, admit_run_input

THREAD_ID = "019504e8-4b7c-7f3a-8c2d-123456789abc"
RUN_ID = "019504e8-4b7d-7a31-9c2d-123456789abc"
MESSAGE_ID = "019504e8-4b7e-7b32-ac2d-123456789abc"


def _valid_payload() -> dict[str, Any]:
    return {
        "threadId": THREAD_ID,
        "runId": RUN_ID,
        "messages": [{"id": MESSAGE_ID, "role": "user", "content": "hello"}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


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
        b'"messages":[{"content":"hello","id":"'
        + MESSAGE_ID.encode()
        + b'","role":"user"}],"runId":"'
        + RUN_ID.encode()
        + b'","threadId":"'
        + THREAD_ID.encode()
        + b'","tools":[]}'
    )

    admitted = admit_run_input(json.dumps(payload, indent=2).encode())

    assert admitted.input.run_id == RUN_ID
    assert admitted.canonical_payload == expected
    assert admitted.payload_hash == sha256(expected).digest()


def test_rejects_malformed_json() -> None:
    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(b"{")

    assert caught.value.code == "invalid_json"
    assert caught.value.path == ()


def test_rejects_input_outside_official_schema() -> None:
    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(b"{}")

    assert caught.value.code == "invalid_schema"
    assert caught.value.path == ("threadId",)


def test_rejects_unknown_schema_field_without_inspecting_free_form_json() -> None:
    payload = _valid_payload()
    payload["state"] = {"productExtension": {"anything": True}}
    payload["messages"][0]["unexpected"] = True

    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(json.dumps(payload).encode())

    assert caught.value.code == "unknown_field"
    assert caught.value.path == ("messages", 0, "unexpected")


def test_rejects_duplicate_json_members() -> None:
    raw = (
        b'{"threadId":"'
        + THREAD_ID.encode()
        + b'","threadId":"'
        + THREAD_ID.encode()
        + b'","runId":"'
        + RUN_ID.encode()
        + b'","messages":[],"tools":[],"context":[],"forwardedProps":{}}'
    )

    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(raw)

    assert caught.value.code == "invalid_json"
    assert caught.value.path == ()


def test_rejects_non_finite_json_number() -> None:
    payload = _valid_payload()
    payload["state"] = float("nan")

    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(json.dumps(payload).encode())

    assert caught.value.code == "invalid_json"
    assert caught.value.path == ()


def test_rejects_json_outside_jcs_numeric_domain() -> None:
    payload = _valid_payload()
    payload["state"] = 2**60

    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(json.dumps(payload).encode())

    assert caught.value.code == "non_canonical_json"
    assert caught.value.path == ()


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
                [
                    {
                        "interruptId": str(uuid4()),
                        "status": "resolved",
                        "payload": {},
                    }
                ],
            ),
            ("resume", 0, "interruptId"),
        ),
    ],
)
def test_rejects_identifier_outside_uuidv7_profile(
    mutate: Callable[[dict[str, Any]], None],
    expected_path: tuple[str | int, ...],
) -> None:
    payload = _valid_payload()
    mutate(payload)

    with pytest.raises(RunInputAdmissionError) as caught:
        admit_run_input(json.dumps(payload).encode())

    assert caught.value.code == "invalid_identifier"
    assert caught.value.path == expected_path


def test_preserves_opaque_tool_call_identifier() -> None:
    payload = _valid_payload()
    payload["messages"] = [
        {
            "id": MESSAGE_ID,
            "role": "assistant",
            "toolCalls": [
                {
                    "id": "provider-call:opaque/123",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ],
        }
    ]

    admitted = admit_run_input(json.dumps(payload).encode())

    message = admitted.input.messages[0]
    assert message.role == "assistant"
    assert message.tool_calls is not None
    assert message.tool_calls[0].id == "provider-call:opaque/123"
