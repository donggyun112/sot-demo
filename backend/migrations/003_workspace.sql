CREATE TABLE sot.sot_workspace (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200)
);
CREATE TABLE sot.sot_workspace_member (
    workspace_id uuid NOT NULL REFERENCES sot.sot_workspace(id),
    user_id uuid NOT NULL REFERENCES sot.sot_user(id),
    role text NOT NULL CHECK (role IN ('owner', 'member', 'viewer')),
    PRIMARY KEY (workspace_id, user_id)
);
CREATE INDEX sot_workspace_member_user ON sot.sot_workspace_member(user_id, workspace_id);
