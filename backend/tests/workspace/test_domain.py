from uuid import uuid4

import pytest

from sot.shared.errors import InvalidInput
from sot.shared.ids import WorkspaceId
from sot.workspace.domain import Permission, Workspace, WorkspaceRole, permissions_for


def test_fixed_workspace_role_catalog() -> None:
    assert permissions_for(WorkspaceRole.OWNER) == frozenset(Permission)
    assert permissions_for(WorkspaceRole.MEMBER) == {
        Permission.DOCUMENT_READ,
        Permission.SESSION_CREATE,
        Permission.SESSION_READ,
        Permission.SESSION_PARTICIPATE,
    }
    assert permissions_for(WorkspaceRole.VIEWER) == {
        Permission.DOCUMENT_READ,
        Permission.SESSION_READ,
    }


@pytest.mark.parametrize("name", ["", "  ", "x" * 201])
def test_workspace_rejects_invalid_name(name: str) -> None:
    with pytest.raises(InvalidInput):
        Workspace(WorkspaceId(uuid4()), name)
