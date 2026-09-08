from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

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


class InvitationNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("invitation_not_found", "Invitation not found")


class InvitationAlreadyDecided(Conflict):
    def __init__(self) -> None:
        super().__init__("invitation_decided", "Invitation is no longer pending")


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REVOKED = "revoked"
    EXPIRED = "expired"


# Long enough that a teammate can act on it after a weekend, short enough that
# a forgotten invitation stops being a way in.
INVITATION_LIFETIME = timedelta(days=7)

# Read aloud or pasted from a chat message, so no 0/O or 1/I to mistype.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10


def new_code() -> str:
    """A code the invitee can redeem when no mail reaches them.

    It is the whole credential, so it is generated from a cryptographic source
    and is long enough that guessing one inside its lifetime is not a strategy.
    """
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_email(value: str) -> str:
    """One address, one spelling: invitations are matched on it."""
    email = value.strip().lower()
    if "@" not in email.strip("@") or len(email) > 320 or " " in email:
        raise InvalidInput("invitation_email_invalid", "Email address is invalid")
    return email


@dataclass(frozen=True, slots=True)
class Invitation:
    """An offer of membership that the invitee has to accept.

    An invitation names someone by the address their colleagues already know,
    so it works before they have an account. It is not membership: nothing is
    granted until they accept, and it stops being usable when it expires.
    """

    id: UUID
    workspace_id: WorkspaceId
    inviter_id: UserId
    invitee_email: str
    role: WorkspaceRole
    created_at: datetime
    expires_at: datetime
    code: str
    invitee_user_id: UserId | None = None
    status: InvitationStatus = InvitationStatus.PENDING
    decided_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.role is WorkspaceRole.OWNER:
            raise InvalidInput(
                "invitation_role_invalid", "Ownership is not transferable by invitation"
            )
        if self.invitee_email != normalize_email(self.invitee_email):
            raise InvalidInput("invitation_email_invalid", "Email address is invalid")
        if self.expires_at <= self.created_at:
            raise InvalidInput("invitation_expiry_invalid", "Expiry must be later")
        if (self.status is InvitationStatus.PENDING) != (self.decided_at is None):
            raise InvalidInput("invitation_status_invalid", "Invitation is invalid")
        if len(self.code) != CODE_LENGTH:
            raise InvalidInput("invitation_code_invalid", "Invitation code is invalid")

    @classmethod
    def create(
        cls,
        *,
        workspace_id: WorkspaceId,
        inviter_id: UserId,
        invitee_email: str,
        role: WorkspaceRole,
        now: datetime,
        invitee_user_id: UserId | None = None,
    ) -> Invitation:
        return cls(
            uuid4(),
            workspace_id,
            inviter_id,
            normalize_email(invitee_email),
            role,
            now,
            now + INVITATION_LIFETIME,
            new_code(),
            invitee_user_id,
        )

    def status_at(self, now: datetime) -> InvitationStatus:
        """Expiry is derived from the clock, never from a background job."""
        if self.status is InvitationStatus.PENDING and now >= self.expires_at:
            return InvitationStatus.EXPIRED
        return self.status

    def _settle(self, status: InvitationStatus, now: datetime) -> Invitation:
        if self.status_at(now) is not InvitationStatus.PENDING:
            raise InvitationAlreadyDecided()
        return replace(self, status=status, decided_at=now)

    def accept(self, actor_id: UserId, now: datetime) -> Invitation:
        # Only the person it was addressed to can turn it into membership.
        if self.invitee_user_id is None or self.invitee_user_id != actor_id:
            raise InvitationNotFound()
        return self._settle(InvitationStatus.ACCEPTED, now)

    def redeem(self, actor_id: UserId, code: str, now: datetime) -> Invitation:
        """Accept with the code instead of the address it was sent to.

        Someone may sign in under a different address than the one they were
        invited at, and where no mail is sent the code is the only thing that
        travels. Compared in constant time: it is a credential.
        """
        if not secrets.compare_digest(self.code, code.strip().upper()):
            raise InvitationNotFound()
        return replace(self, invitee_user_id=actor_id)._settle(
            InvitationStatus.ACCEPTED, now
        )

    def decline(self, actor_id: UserId, now: datetime) -> Invitation:
        if self.invitee_user_id is None or self.invitee_user_id != actor_id:
            raise InvitationNotFound()
        return self._settle(InvitationStatus.DECLINED, now)

    def revoke(self, now: datetime) -> Invitation:
        return self._settle(InvitationStatus.REVOKED, now)

    def expire(self, now: datetime) -> Invitation:
        """Settle a past-due row so a fresh invitation can take its place."""
        if self.status is not InvitationStatus.PENDING or now < self.expires_at:
            raise InvitationAlreadyDecided()
        return replace(self, status=InvitationStatus.EXPIRED, decided_at=now)

    def membership(self) -> WorkspaceMembership:
        if self.status is not InvitationStatus.ACCEPTED or self.invitee_user_id is None:
            raise InvitationAlreadyDecided()
        return WorkspaceMembership(self.workspace_id, self.invitee_user_id, self.role)
