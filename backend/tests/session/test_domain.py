from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sot.session.domain import (
    Branch,
    NewTurn,
    Session,
    SessionClosed,
    SessionPermission,
    SessionRole,
    SessionStatus,
    VersionConflict,
    is_allowed,
)
from sot.shared.errors import InvalidInput
from sot.shared.ids import DocumentId, SessionId, UserId, WorkspaceId

NOW = datetime(2026, 9, 6, tzinfo=UTC)


@pytest.mark.parametrize(
    "workspace_role,session_role,permission,allowed",
    [
        ("member", SessionRole.EDITOR, SessionPermission.EDIT, True),
        ("member", SessionRole.VIEWER, SessionPermission.EDIT, False),
        ("viewer", SessionRole.EDITOR, SessionPermission.EDIT, False),
        ("owner", None, SessionPermission.READ, False),
        ("member", SessionRole.OWNER, SessionPermission.MANAGE_MEMBERS, True),
        ("member", SessionRole.EDITOR, SessionPermission.PUBLISH_BUNDLE, False),
        ("member", SessionRole.EDITOR, SessionPermission.CREATE_TOSS, False),
        ("member", SessionRole.EDITOR, SessionPermission.CREATE_PROPOSAL, True),
        ("viewer", SessionRole.OWNER, SessionPermission.MANAGE_MEMBERS, False),
        ("viewer", SessionRole.OWNER, SessionPermission.READ, True),
        ("unknown", SessionRole.OWNER, SessionPermission.READ, False),
    ],
)
def test_effective_permission_is_scope_intersection(
    workspace_role: str,
    session_role: SessionRole | None,
    permission: SessionPermission,
    allowed: bool,
) -> None:
    assert is_allowed(workspace_role, session_role, permission) is allowed


def test_completed_turns_are_append_only_and_versioned() -> None:
    branch = Branch.create(
        WorkspaceId(uuid4()), SessionId(uuid4()), UserId(uuid4()), NOW
    )
    first = branch.append_completed(
        expected_version=0,
        messages=(
            NewTurn("user", "question"),
            NewTurn("assistant", "answer"),
        ),
        now=NOW,
    )
    second = branch.append_completed(
        expected_version=1, messages=(NewTurn("tool", '{"result":1}'),), now=NOW
    )
    assert [turn.ordinal for turn in first.turns] == [1, 2]
    assert first.branch_version == 1
    assert [turn.ordinal for turn in second.turns] == [3]
    assert second.branch_version == 2
    assert [turn.content for turn in branch.turns] == [
        "question",
        "answer",
        '{"result":1}',
    ]
    with pytest.raises(VersionConflict):
        branch.append_completed(
            expected_version=1, messages=(NewTurn("user", "stale"),), now=NOW
        )
    assert len(branch.turns) == 3


def test_invalid_or_empty_completion_does_not_advance_branch() -> None:
    branch = Branch.create(
        WorkspaceId(uuid4()), SessionId(uuid4()), UserId(uuid4()), NOW
    )
    with pytest.raises(InvalidInput):
        branch.append_completed(expected_version=0, messages=(), now=NOW)
    with pytest.raises(InvalidInput):
        NewTurn("system", "unsafe")  # type: ignore[arg-type]
    assert branch.version == 0
    assert branch.turns == ()


def test_closing_session_is_terminal() -> None:
    session = Session.create(
        WorkspaceId(uuid4()), DocumentId(uuid4()), UserId(uuid4()), NOW
    )
    session.require_open()
    session.close()
    assert session.status is SessionStatus.CLOSED
    with pytest.raises(SessionClosed):
        session.require_open()
    with pytest.raises(SessionClosed):
        session.close()
