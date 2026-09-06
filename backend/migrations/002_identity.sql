CREATE TABLE sot.sot_user (
    id uuid PRIMARY KEY,
    email text NOT NULL,
    display_name text NOT NULL
);
CREATE TABLE sot.sot_user_identity (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES sot.sot_user(id),
    issuer text NOT NULL,
    subject text NOT NULL,
    UNIQUE (issuer, subject)
);
CREATE TABLE sot.sot_auth_session (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES sot.sot_user(id),
    token_hash text NOT NULL UNIQUE,
    family_id uuid NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE INDEX sot_auth_user_active ON sot.sot_auth_session(user_id, revoked_at);
CREATE INDEX sot_auth_family_active ON sot.sot_auth_session(family_id, revoked_at);
