CREATE TABLE sot.sot_document (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES sot.sot_workspace(id),
    created_by uuid NOT NULL REFERENCES sot.sot_user(id),
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 200),
    version integer NOT NULL CHECK (version >= 0),
    current_revision_id uuid,
    UNIQUE (workspace_id, id)
);
CREATE TABLE sot.sot_document_revision (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    document_id uuid NOT NULL,
    number integer NOT NULL CHECK (number > 0),
    content text NOT NULL,
    proposal_id uuid,
    created_by uuid NOT NULL REFERENCES sot.sot_user(id),
    created_at timestamptz NOT NULL,
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, document_id, id),
    UNIQUE (workspace_id, document_id, number),
    FOREIGN KEY (workspace_id, document_id) REFERENCES sot.sot_document(workspace_id, id)
);
ALTER TABLE sot.sot_document ADD CONSTRAINT sot_document_current_revision_fk
    FOREIGN KEY (workspace_id, id, current_revision_id)
    REFERENCES sot.sot_document_revision(workspace_id, document_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE sot.sot_session (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES sot.sot_workspace(id),
    -- NULL belongs to detached public-bundle forks; normal creation requires a document.
    document_id uuid,
    created_by uuid NOT NULL REFERENCES sot.sot_user(id),
    created_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('open', 'closed')),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, document_id) REFERENCES sot.sot_document(workspace_id, id)
);
CREATE TABLE sot.sot_session_member (
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role text NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    PRIMARY KEY (workspace_id, session_id, user_id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES sot.sot_session(workspace_id, id),
    FOREIGN KEY (workspace_id, user_id) REFERENCES sot.sot_workspace_member(workspace_id, user_id)
);
CREATE TABLE sot.sot_branch (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    created_by uuid NOT NULL REFERENCES sot.sot_user(id),
    created_at timestamptz NOT NULL,
    version integer NOT NULL CHECK (version >= 0),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, session_id, id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES sot.sot_session(workspace_id, id)
);
CREATE TABLE sot.sot_turn (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    role text NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content text NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, branch_id, ordinal),
    FOREIGN KEY (workspace_id, branch_id) REFERENCES sot.sot_branch(workspace_id, id)
);
CREATE TABLE sot.sot_curation_op (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal > 0),
    kind text NOT NULL CHECK (kind IN ('drop', 'edit', 'join')),
    source_ids uuid[] NOT NULL CHECK (cardinality(source_ids) > 0),
    content text,
    created_by uuid NOT NULL REFERENCES sot.sot_user(id),
    created_at timestamptz NOT NULL,
    CHECK ((kind = 'drop' AND content IS NULL AND cardinality(source_ids) = 1)
        OR (kind = 'edit' AND content IS NOT NULL AND cardinality(source_ids) = 1)
        OR (kind = 'join' AND content IS NOT NULL)),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, branch_id, ordinal),
    FOREIGN KEY (workspace_id, branch_id) REFERENCES sot.sot_branch(workspace_id, id)
);
CREATE TABLE sot.sot_bundle (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    title text NOT NULL,
    published_by uuid NOT NULL REFERENCES sot.sot_user(id),
    published_at timestamptz NOT NULL,
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES sot.sot_session(workspace_id, id),
    FOREIGN KEY (workspace_id, session_id, branch_id)
        REFERENCES sot.sot_branch(workspace_id, session_id, id)
);
CREATE TABLE sot.sot_bundle_item (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    bundle_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    source_ids uuid[] NOT NULL CHECK (cardinality(source_ids) > 0),
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    content text NOT NULL,
    provenance text NOT NULL CHECK (provenance IN ('copied', 'edited')),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, bundle_id, position),
    FOREIGN KEY (workspace_id, bundle_id) REFERENCES sot.sot_bundle(workspace_id, id)
);
CREATE TABLE sot.sot_revision_citation (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    claim_anchor text NOT NULL CHECK (length(btrim(claim_anchor)) > 0),
    bundle_id uuid NOT NULL,
    bundle_item_position integer NOT NULL CHECK (bundle_item_position >= 0),
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, revision_id, position),
    FOREIGN KEY (workspace_id, revision_id) REFERENCES sot.sot_document_revision(workspace_id, id),
    FOREIGN KEY (workspace_id, bundle_id, bundle_item_position)
        REFERENCES sot.sot_bundle_item(workspace_id, bundle_id, position)
);
CREATE TABLE sot.sot_fork_origin (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    -- Opaque provenance only: deliberately no source Bundle/Document FK.
    source_bundle_id uuid NOT NULL,
    title text NOT NULL,
    author_display_name text NOT NULL,
    published_at timestamptz NOT NULL,
    UNIQUE (workspace_id, id),
    UNIQUE (workspace_id, session_id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES sot.sot_session(workspace_id, id)
);
