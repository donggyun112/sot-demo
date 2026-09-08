from __future__ import annotations

import logging
from typing import Protocol

from sot.workspace.domain import Invitation

logger = logging.getLogger(__name__)


class LocalInvitationDelivery:
    """No mail here. The code is issued and handed back to the inviter.

    A local or test install has no way to reach an address, so pretending to
    send mail would leave invitations that never arrive. The code is the
    delivery: the inviter passes it on however they already talk.
    """

    hands_back_code = True

    async def deliver(self, invitation: Invitation, workspace_name: str) -> None:
        logger.info(
            "invitation issued for %s to %s (no mail in this environment)",
            workspace_name,
            invitation.invitee_email,
        )


class EmailInvitationDelivery:
    """Send the invitation to the address it was written to."""

    hands_back_code = False

    def __init__(self, mailer: Mailer, base_url: str) -> None:
        self._mailer, self._base_url = mailer, base_url

    async def deliver(self, invitation: Invitation, workspace_name: str) -> None:
        await self._mailer.send(
            to=invitation.invitee_email,
            subject=f"Join {workspace_name} on SOT",
            body=(
                f"You have been invited to {workspace_name}.\n\n"
                f"Open {self._base_url}/invitations and enter this code:\n\n"
                f"    {invitation.code}\n\n"
                f"It stops working on {invitation.expires_at:%Y-%m-%d}."
            ),
        )


class Mailer(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...
