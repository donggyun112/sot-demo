from __future__ import annotations

import json

import pytest

from sot.agent.messages import ToolRecords, turns_to_model_messages
from sot.session.domain import ExportedTool, NewTurn, read_session_export
from sot.shared.errors import InvalidInput

EXPORT = json.dumps(
    {
        "turns": [
            {"role": "user", "content": "설계문서 지금 어때?"},
            {
                "role": "tool",
                "name": "sot_read",
                "call_id": "toolu_01",
                "args": {},
                "result": {"title": "정책", "revision": 3},
            },
            {"role": "assistant", "content": "리비전 3까지 있습니다."},
            {
                "role": "tool",
                "name": "sot_update",
                "call_id": "toolu_02",
                "args": {"edits": [{"find": "초안", "replace": "확정"}]},
            },
        ]
    }
)


def test_an_export_keeps_what_the_agent_did() -> None:
    """A conversation with an agent in it is mostly what the agent did. An
    import that keeps only the words keeps the story without the evidence."""
    entries = read_session_export(EXPORT)

    assert entries[0] == NewTurn("user", "설계문서 지금 어때?")
    assert entries[1] == ExportedTool(
        "sot_read", "toolu_01", {}, {"title": "정책", "revision": 3}, True
    )
    assert entries[2] == NewTurn("assistant", "리비전 3까지 있습니다.")
    # A call that was interrupted has no result. Keeping the call anyway is
    # the point: it says the agent tried.
    assert entries[3] == ExportedTool(
        "sot_update", "toolu_02", {"edits": [{"find": "초안", "replace": "확정"}]}, None, False
    )


def test_an_imported_record_is_the_same_envelope_as_our_own() -> None:
    """A reader should not have to know which agent wrote a record, so the
    import writes through the same pen the transcript reads back with."""
    records = ToolRecords()
    entry = read_session_export(EXPORT)[1]
    assert isinstance(entry, ExportedTool)

    call = records.call(
        tool_name=entry.name, tool_call_id=entry.call_id, args=entry.args
    )
    returned = records.result(
        tool_name=entry.name, tool_call_id=entry.call_id, result=entry.result
    )

    assert call.role == "tool"
    read_back = records.record(call.content)
    assert read_back is not None
    assert (read_back.kind, read_back.name, read_back.call_id) == (
        "call",
        "sot_read",
        "toolu_01",
    )
    read_return = records.record(returned.content)
    assert read_return is not None
    assert read_return.kind == "return"
    assert read_return.payload == {"title": "정책", "revision": 3}


@pytest.mark.parametrize(
    "body",
    [
        "not json at all",
        json.dumps({"messages": []}),
        json.dumps({"turns": [{"role": "system", "content": "x"}]}),
        json.dumps({"turns": [{"role": "tool", "call_id": "c", "args": {}}]}),
        json.dumps({"turns": [{"role": "tool", "name": "t", "args": {}}]}),
    ],
    ids=["garbage", "no-turns", "no-speaker", "tool-without-name", "tool-without-call"],
)
def test_a_file_that_is_not_a_conversation_is_refused(body: str) -> None:
    # Half-reading someone's record is worse than not reading it.
    with pytest.raises(InvalidInput):
        read_session_export(body)


def test_the_model_is_never_asked_to_resume_another_agents_call() -> None:
    """Imported tool records stay in the transcript and out of the history:
    they are calls to tools this agent does not have, and an interrupted one
    has no result to pair with."""
    records = ToolRecords()
    entry = read_session_export(EXPORT)[3]
    assert isinstance(entry, ExportedTool)
    orphan = records.call(
        tool_name=entry.name, tool_call_id=entry.call_id, args=entry.args
    )

    # Replaying it is what AgentRunPreparer refuses to do for an import; this
    # is what would otherwise reach the model — an unanswered call.
    from datetime import UTC, datetime
    from uuid import uuid4

    from sot.session.domain import Turn
    from sot.shared.ids import BranchId, UserId, WorkspaceId

    turn = Turn(
        uuid4(),
        WorkspaceId(uuid4()),
        BranchId(uuid4()),
        1,
        orphan.role,
        orphan.content,
        datetime.now(UTC),
        UserId(uuid4()),
    )
    replayed = turns_to_model_messages((turn,))
    assert len(replayed) == 1
    assert replayed[0].parts[0].tool_name == "sot_update"
