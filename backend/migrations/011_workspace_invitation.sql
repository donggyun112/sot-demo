-- Invite by email, not by pasting someone's user id.
--
-- Adding a member used to need the raw id of a person who is not in the
-- workspace yet, so the only way in was for them to copy it out of their own
-- profile and send it over. An invitation names them the way people already
-- know each other, survives them not having an account yet, and needs their
-- consent before they are counted as a member.
CREATE TABLE sot.sot_workspace_invitation (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES sot.sot_workspace(id),
    inviter_id uuid NOT NULL REFERENCES sot.sot_user(id),
    invitee_email text NOT NULL CHECK (invitee_email = lower(btrim(invitee_email))),
    -- Resolved when the invitee already has an account; an invitation to
    -- someone who does not is still valid and binds on their first sign-in.
    invitee_user_id uuid REFERENCES sot.sot_user(id),
    -- What the invitee redeems where no mail can reach them. It is the whole
    -- credential, so it is unique and only useful while the row is pending.
    code text NOT NULL UNIQUE CHECK (code ~ '^[A-Z2-9]{10}$'),
    -- Ownership is not transferable by invitation.
    role text NOT NULL CHECK (role IN ('member', 'viewer')),
    status text NOT NULL CHECK (
        status IN ('pending', 'accepted', 'declined', 'revoked', 'expired')
    ),
    created_at timestamptz NOT NULL,
    decided_at timestamptz,
    expires_at timestamptz NOT NULL,
    CHECK (expires_at > created_at),
    CHECK ((status = 'pending') = (decided_at IS NULL)),
    UNIQUE (workspace_id, id)
);

-- One live invitation per workspace and address. The predicate cannot look at
-- now(), so a past-due row is settled to 'expired' before a new one is made.
CREATE UNIQUE INDEX sot_workspace_invitation_pending
    ON sot.sot_workspace_invitation (workspace_id, invitee_email)
    WHERE status = 'pending';

-- What an invitee is waiting on, by address or by account.
CREATE INDEX sot_workspace_invitation_invitee
    ON sot.sot_workspace_invitation (invitee_email)
    WHERE status = 'pending';
CREATE INDEX sot_workspace_invitation_invitee_user
    ON sot.sot_workspace_invitation (invitee_user_id)
    WHERE status = 'pending';
