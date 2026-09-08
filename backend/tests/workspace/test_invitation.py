from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from sot.identity.contracts import Actor
from sot.shared.errors import Conflict, InvalidInput
from sot.shared.ids import UserId
from sot.workspace.application import (
    AcceptInvitation,
    CreateWorkspace,
    InviteToWorkspace,
    ListMyInvitations,
    ListWorkspaceInvitations,
    RevokeInvitation,
    WorkspaceAccess,
)
from sot.workspace.delivery import LocalInvitationDelivery
from sot.workspace.domain import (
    CODE_ALPHABET,
    CODE_LENGTH,
    INVITATION_LIFETIME,
    InvitationAlreadyDecided,
    InvitationNotFound,
    InvitationStatus,
    WorkspaceForbidden,
    WorkspaceRole,
)
from tests.workspace.test_application import NOW, MemoryStore


async def workspace_with_owner() -> tuple[MemoryStore, Actor]:
    store = MemoryStore()
    owner = Actor(UserId(uuid4()))
    store.emails[owner.user_id] = "owner@example.com"
    workspace = await CreateWorkspace(store, lambda: store).execute(owner, name="Team")
    store.workspace_id = workspace.id  # type: ignore[attr-defined]
    return store, owner


def inviter(store: MemoryStore) -> InviteToWorkspace:
    return InviteToWorkspace(
        store,
        store,
        WorkspaceAccess(store),
        store,
        LocalInvitationDelivery(),
        lambda: store,
        store,
    )


@pytest.mark.asyncio
async def test_an_invitation_is_not_membership_until_it_is_accepted() -> None:
    store, owner = await workspace_with_owner()
    workspace_id = store.workspace_id  # type: ignore[attr-defined]
    invitee = Actor(UserId(uuid4()))
    store.emails[invitee.user_id] = "teammate@example.com"

    issued = await inviter(store).execute(
        owner, workspace_id, email="Teammate@Example.com ", role=WorkspaceRole.MEMBER
    )
    invitation = issued.invitation
    # The address is matched on, so it is stored in one spelling.
    assert invitation.invitee_email == "teammate@example.com"
    assert invitation.expires_at == NOW + INVITATION_LIFETIME
    assert (workspace_id, invitee.user_id) not in store.members

    mine = await ListMyInvitations(
        store, store, store, store, lambda: store, store
    ).execute(invitee)
    assert [(item.workspace_name, item.inviter_display_name) for item in mine] == [
        ("Team", "Unnamed")
    ]

    member = await AcceptInvitation(store, store, store, lambda: store, store).execute(
        invitee, invitation.id
    )
    assert member.role is WorkspaceRole.MEMBER
    assert store.members[workspace_id, invitee.user_id] == member
    assert store.invitations[invitation.id].status is InvitationStatus.ACCEPTED


@pytest.mark.asyncio
async def test_only_the_addressee_can_accept_and_only_once() -> None:
    store, owner = await workspace_with_owner()
    workspace_id = store.workspace_id  # type: ignore[attr-defined]
    invitee = Actor(UserId(uuid4()))
    stranger = Actor(UserId(uuid4()))
    store.emails[invitee.user_id] = "teammate@example.com"
    store.emails[stranger.user_id] = "stranger@example.com"
    issued = await inviter(store).execute(
        owner, workspace_id, email="teammate@example.com", role=WorkspaceRole.MEMBER
    )
    invitation = issued.invitation
    accept = AcceptInvitation(store, store, store, lambda: store, store)

    # An invitation is addressed, not a link: holding its id is not enough.
    with pytest.raises(InvitationNotFound):
        await accept.execute(stranger, invitation.id)
    assert (workspace_id, stranger.user_id) not in store.members

    await accept.execute(invitee, invitation.id)
    with pytest.raises(InvitationAlreadyDecided):
        await accept.execute(invitee, invitation.id)


@pytest.mark.asyncio
async def test_an_invitation_sent_before_they_had_an_account_binds_on_the_address() -> (
    None
):
    store, owner = await workspace_with_owner()
    workspace_id = store.workspace_id  # type: ignore[attr-defined]
    issued = await inviter(store).execute(
        owner, workspace_id, email="later@example.com", role=WorkspaceRole.VIEWER
    )
    invitation = issued.invitation
    assert invitation.invitee_user_id is None

    # They sign up afterwards; the address is what carries the invitation.
    newcomer = Actor(UserId(uuid4()))
    store.emails[newcomer.user_id] = "later@example.com"
    mine = await ListMyInvitations(
        store, store, store, store, lambda: store, store
    ).execute(newcomer)
    assert [item.invitation.id for item in mine] == [invitation.id]

    member = await AcceptInvitation(store, store, store, lambda: store, store).execute(
        newcomer, invitation.id
    )
    assert member.role is WorkspaceRole.VIEWER


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [WorkspaceRole.OWNER])
async def test_ownership_is_not_transferable_by_invitation(role: WorkspaceRole) -> None:
    store, owner = await workspace_with_owner()
    with pytest.raises(InvalidInput) as caught:
        await inviter(store).execute(
            owner,
            store.workspace_id,  # type: ignore[attr-defined]
            email="teammate@example.com",
            role=role,
        )
    assert caught.value.code == "invitation_role_invalid"


@pytest.mark.asyncio
async def test_one_live_invitation_per_address_and_none_for_a_member() -> None:
    store, owner = await workspace_with_owner()
    workspace_id = store.workspace_id  # type: ignore[attr-defined]
    invitee = Actor(UserId(uuid4()))
    store.emails[invitee.user_id] = "teammate@example.com"
    await inviter(store).execute(
        owner, workspace_id, email="teammate@example.com", role=WorkspaceRole.MEMBER
    )

    with pytest.raises(Conflict) as caught:
        await inviter(store).execute(
            owner, workspace_id, email="teammate@example.com", role=WorkspaceRole.VIEWER
        )
    assert caught.value.code == "invitation_pending"

    # A past-due one is settled first, so the address can be invited again.
    store.now_value = NOW + INVITATION_LIFETIME + timedelta(minutes=1)
    replacement_issued = await inviter(store).execute(
        owner, workspace_id, email="teammate@example.com", role=WorkspaceRole.VIEWER
    )
    replacement = replacement_issued.invitation
    assert replacement.role is WorkspaceRole.VIEWER
    assert [item.status for item in store.invitations.values()].count(
        InvitationStatus.EXPIRED
    ) == 1

    await AcceptInvitation(store, store, store, lambda: store, store).execute(
        invitee, replacement.id
    )
    with pytest.raises(Conflict) as already:
        await inviter(store).execute(
            owner, workspace_id, email="teammate@example.com", role=WorkspaceRole.MEMBER
        )
    assert already.value.code == "workspace_member_exists"


@pytest.mark.asyncio
async def test_an_expired_invitation_is_not_a_way_in() -> None:
    store, owner = await workspace_with_owner()
    workspace_id = store.workspace_id  # type: ignore[attr-defined]
    invitee = Actor(UserId(uuid4()))
    store.emails[invitee.user_id] = "teammate@example.com"
    issued = await inviter(store).execute(
        owner, workspace_id, email="teammate@example.com", role=WorkspaceRole.MEMBER
    )
    invitation = issued.invitation

    store.now_value = NOW + INVITATION_LIFETIME
    assert (
        await ListMyInvitations(
            store, store, store, store, lambda: store, store
        ).execute(invitee)
        == ()
    )
    with pytest.raises(InvitationAlreadyDecided):
        await AcceptInvitation(store, store, store, lambda: store, store).execute(
            invitee, invitation.id
        )
    assert (workspace_id, invitee.user_id) not in store.members


@pytest.mark.asyncio
async def test_only_a_manager_sees_or_revokes_a_workspace_invitation() -> None:
    store, owner = await workspace_with_owner()
    workspace_id = store.workspace_id  # type: ignore[attr-defined]
    invitee = Actor(UserId(uuid4()))
    store.emails[invitee.user_id] = "teammate@example.com"
    issued = await inviter(store).execute(
        owner, workspace_id, email="teammate@example.com", role=WorkspaceRole.MEMBER
    )
    invitation = issued.invitation
    listing = ListWorkspaceInvitations(
        store, WorkspaceAccess(store), lambda: store, store
    )
    revoke = RevokeInvitation(store, WorkspaceAccess(store), lambda: store, store)

    assert [item.id for item in await listing.execute(owner, workspace_id)] == [
        invitation.id
    ]
    with pytest.raises(WorkspaceForbidden):
        await listing.execute(invitee, workspace_id)
    with pytest.raises(WorkspaceForbidden):
        await revoke.execute(invitee, workspace_id, invitation.id)

    # A workspace never learns about another workspace's invitations.
    other = await CreateWorkspace(store, lambda: store).execute(owner, name="Other")
    with pytest.raises(InvitationNotFound):
        await revoke.execute(owner, other.id, invitation.id)

    await revoke.execute(owner, workspace_id, invitation.id)
    assert await listing.execute(owner, workspace_id) == ()
    with pytest.raises(InvitationAlreadyDecided):
        await AcceptInvitation(store, store, store, lambda: store, store).execute(
            invitee, invitation.id
        )


@pytest.mark.asyncio
async def test_the_code_is_the_delivery_where_no_mail_is_sent() -> None:
    store, owner = await workspace_with_owner()
    workspace_id = store.workspace_id  # type: ignore[attr-defined]
    issued = await inviter(store).execute(
        owner, workspace_id, email="teammate@example.com", role=WorkspaceRole.MEMBER
    )
    # Nothing carried it, so the inviter is handed the code to pass on.
    assert issued.hand_over_code is True
    assert len(issued.invitation.code) == CODE_LENGTH
    assert set(issued.invitation.code) <= set(CODE_ALPHABET)

    # Redeeming works under whatever address they actually signed in with.
    newcomer = Actor(UserId(uuid4()))
    store.emails[newcomer.user_id] = "someone.else@example.com"
    accept = AcceptInvitation(store, store, store, lambda: store, store)
    member = await accept.redeem(newcomer, issued.invitation.code.lower())
    assert member.user_id == newcomer.user_id
    assert member.role is WorkspaceRole.MEMBER
    assert store.invitations[issued.invitation.id].status is InvitationStatus.ACCEPTED


@pytest.mark.asyncio
async def test_a_wrong_or_spent_code_is_not_a_way_in() -> None:
    store, owner = await workspace_with_owner()
    workspace_id = store.workspace_id  # type: ignore[attr-defined]
    issued = await inviter(store).execute(
        owner, workspace_id, email="teammate@example.com", role=WorkspaceRole.MEMBER
    )
    newcomer = Actor(UserId(uuid4()))
    store.emails[newcomer.user_id] = "newcomer@example.com"
    accept = AcceptInvitation(store, store, store, lambda: store, store)

    with pytest.raises(InvitationNotFound):
        await accept.redeem(newcomer, "AAAAAAAAAA")
    assert (workspace_id, newcomer.user_id) not in store.members

    await accept.redeem(newcomer, issued.invitation.code)
    other = Actor(UserId(uuid4()))
    store.emails[other.user_id] = "other@example.com"
    # A spent code is no longer pending, so it finds nothing.
    with pytest.raises(InvitationNotFound):
        await accept.redeem(other, issued.invitation.code)
