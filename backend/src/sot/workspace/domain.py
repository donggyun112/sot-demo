from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sot.shared.errors import Conflict, Forbidden, InvalidInput, NotFound
from sot.shared.ids import UserId, WorkspaceId


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(StrEnum):
    WORKSPACE_MANAGE = "workspace.manage"
    DOCUMENT_CREATE = "document.create"
    DOCUMENT_READ = "document.read"
    DOCUMENT_PUBLISH = "document.publish"
    SESSION_CREATE = "session.create"
    SESSION_READ = "session.read"
    SESSION_PARTICIPATE = "session.participate"


def permissions_for(role: WorkspaceRole) -> frozenset[Permission]:
    if role is WorkspaceRole.OWNER:
        return frozenset(Permission)
    read = frozenset({Permission.DOCUMENT_READ, Permission.SESSION_READ})
    if role is WorkspaceRole.MEMBER:
        return read | {Permission.SESSION_CREATE, Permission.SESSION_PARTICIPATE}
    return read


class WorkspaceForbidden(Forbidden):
    def __init__(self) -> None:
        super().__init__("workspace_forbidden", "Workspace access denied")


class WorkspaceNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("workspace_not_found", "Workspace not found")


class WorkspaceMemberAlreadyExists(Conflict):
    def __init__(self) -> None:
        super().__init__("workspace_member_exists", "Workspace member already exists")


@dataclass(frozen=True, slots=True)
class Workspace:
    id: WorkspaceId
    name: str

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > 200:
            raise InvalidInput("workspace_name_invalid", "Workspace name is invalid")


@dataclass(frozen=True, slots=True)
class WorkspaceMembership:
    workspace_id: WorkspaceId
    user_id: UserId
    role: WorkspaceRole
