CREATE TABLE sot.sot_proposal (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    document_id uuid NOT NULL,
    source_session_id uuid NOT NULL,
    created_by uuid NOT NULL REFERENCES sot.sot_user(id),
    created_at timestamptz NOT NULL,
    current_version integer NOT NULL CHECK (current_version > 0),
    status text NOT NULL CHECK (status IN ('open', 'approved', 'rejected', 'stale', 'merged')),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, id, document_id),
    FOREIGN KEY (workspace_id, document_id) REFERENCES sot.sot_document(workspace_id, id),
    FOREIGN KEY (workspace_id, source_session_id) REFERENCES sot.sot_session(workspace_id, id)
);
CREATE TABLE sot.sot_proposal_version (
    workspace_id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    proposal_version integer NOT NULL CHECK (proposal_version > 0),
    document_id uuid NOT NULL,
    base_revision_id uuid NOT NULL,
    content text NOT NULL CHECK (length(btrim(content)) > 0),
    created_by uuid NOT NULL REFERENCES sot.sot_user(id),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (workspace_id, proposal_id, proposal_version),
    FOREIGN KEY (workspace_id, proposal_id, document_id)
        REFERENCES sot.sot_proposal(workspace_id, id, document_id),
    FOREIGN KEY (workspace_id, document_id, base_revision_id)
        REFERENCES sot.sot_document_revision(workspace_id, document_id, id)
);
ALTER TABLE sot.sot_proposal ADD CONSTRAINT sot_proposal_current_version_fk
    FOREIGN KEY (workspace_id, id, current_version)
    REFERENCES sot.sot_proposal_version(workspace_id, proposal_id, proposal_version)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE sot.sot_proposal_bundle (
    workspace_id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    proposal_version integer NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    bundle_id uuid NOT NULL,
    PRIMARY KEY (workspace_id, proposal_id, proposal_version, bundle_id),
    UNIQUE (workspace_id, proposal_id, proposal_version, position),
    FOREIGN KEY (workspace_id, proposal_id, proposal_version)
        REFERENCES sot.sot_proposal_version(workspace_id, proposal_id, proposal_version),
    FOREIGN KEY (workspace_id, bundle_id) REFERENCES sot.sot_bundle(workspace_id, id)
);
CREATE TABLE sot.sot_proposal_citation (
    workspace_id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    proposal_version integer NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    claim_anchor text NOT NULL CHECK (length(btrim(claim_anchor)) > 0),
    bundle_id uuid NOT NULL,
    bundle_item_position integer NOT NULL CHECK (bundle_item_position >= 0),
    PRIMARY KEY (workspace_id, proposal_id, proposal_version, position),
    UNIQUE (workspace_id, proposal_id, proposal_version, claim_anchor, bundle_id, bundle_item_position),
    FOREIGN KEY (workspace_id, proposal_id, proposal_version)
        REFERENCES sot.sot_proposal_version(workspace_id, proposal_id, proposal_version),
    FOREIGN KEY (workspace_id, proposal_id, proposal_version, bundle_id)
        REFERENCES sot.sot_proposal_bundle(workspace_id, proposal_id, proposal_version, bundle_id),
    FOREIGN KEY (workspace_id, bundle_id, bundle_item_position)
        REFERENCES sot.sot_bundle_item(workspace_id, bundle_id, position)
);
CREATE TABLE sot.sot_proposal_approver (
    workspace_id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    proposal_version integer NOT NULL,
    approver_user_id uuid NOT NULL REFERENCES sot.sot_user(id),
    additional boolean NOT NULL,
    PRIMARY KEY (workspace_id, proposal_id, proposal_version, approver_user_id),
    FOREIGN KEY (workspace_id, proposal_id, proposal_version)
        REFERENCES sot.sot_proposal_version(workspace_id, proposal_id, proposal_version)
);
CREATE TABLE sot.sot_approval (
    workspace_id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    proposal_version integer NOT NULL,
    approver_user_id uuid NOT NULL,
    decision text NOT NULL CHECK (decision IN ('approve', 'reject')),
    decided_at timestamptz NOT NULL,
    PRIMARY KEY (workspace_id, proposal_id, proposal_version, approver_user_id),
    FOREIGN KEY (workspace_id, proposal_id, proposal_version, approver_user_id)
        REFERENCES sot.sot_proposal_approver(workspace_id, proposal_id, proposal_version, approver_user_id)
);
CREATE INDEX sot_proposal_open_document_idx ON sot.sot_proposal(workspace_id, document_id)
    WHERE status IN ('open', 'approved');
CREATE INDEX sot_proposal_open_session_idx ON sot.sot_proposal(workspace_id, source_session_id)
    WHERE status IN ('open', 'approved');
