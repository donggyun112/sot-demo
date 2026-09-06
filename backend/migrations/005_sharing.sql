CREATE TABLE sot.sot_share_link (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    bundle_id uuid NOT NULL,
    token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
    created_by uuid NOT NULL REFERENCES sot.sot_user(id),
    created_at timestamptz NOT NULL,
    expires_at timestamptz,
    revoked_by uuid REFERENCES sot.sot_user(id),
    revoked_at timestamptz,
    -- Complete immutable public projection. Anonymous reads use this table alone.
    title text NOT NULL,
    author_display_name text NOT NULL,
    published_at timestamptz NOT NULL,
    items jsonb NOT NULL CHECK (jsonb_typeof(items) = 'array'),
    CHECK ((revoked_by IS NULL) = (revoked_at IS NULL)),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, bundle_id) REFERENCES sot.sot_bundle(workspace_id, id)
);
