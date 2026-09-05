CREATE SCHEMA IF NOT EXISTS sot;

CREATE TABLE IF NOT EXISTS sot.documents (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    current_revision_id UUID NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sot.sessions (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES sot.documents(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sot.branches (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sot.sessions(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    parent_branch_id UUID REFERENCES sot.branches(id),
    source_toss_id UUID,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sot.turns (
    id UUID PRIMARY KEY,
    branch_id UUID NOT NULL REFERENCES sot.branches(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (branch_id, ordinal)
);

CREATE TABLE IF NOT EXISTS sot.cites (
    id UUID PRIMARY KEY,
    branch_id UUID NOT NULL REFERENCES sot.branches(id) ON DELETE CASCADE,
    created_by TEXT NOT NULL,
    summary TEXT NOT NULL CHECK (length(btrim(summary)) > 0),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sot.cite_turns (
    cite_id UUID NOT NULL REFERENCES sot.cites(id) ON DELETE CASCADE,
    turn_id UUID NOT NULL REFERENCES sot.turns(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (cite_id, ordinal),
    UNIQUE (cite_id, turn_id)
);

CREATE TABLE IF NOT EXISTS sot.tosses (
    id UUID PRIMARY KEY,
    cite_id UUID NOT NULL REFERENCES sot.cites(id),
    token TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sot.proposals (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES sot.documents(id) ON DELETE CASCADE,
    branch_id UUID NOT NULL REFERENCES sot.branches(id) ON DELETE CASCADE,
    created_by TEXT NOT NULL,
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    status TEXT NOT NULL CHECK (status IN ('open', 'published')),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sot.approvals (
    proposal_id UUID NOT NULL REFERENCES sot.proposals(id) ON DELETE CASCADE,
    actor_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (proposal_id, actor_id)
);

CREATE TABLE IF NOT EXISTS sot.revisions (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES sot.documents(id) ON DELETE CASCADE,
    number INTEGER NOT NULL CHECK (number > 0),
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    proposal_id UUID REFERENCES sot.proposals(id),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (document_id, number)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'documents_current_revision_fk'
    ) THEN
        ALTER TABLE sot.documents
            ADD CONSTRAINT documents_current_revision_fk
            FOREIGN KEY (current_revision_id) REFERENCES sot.revisions(id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'branches_source_toss_fk'
    ) THEN
        ALTER TABLE sot.branches
            ADD CONSTRAINT branches_source_toss_fk
            FOREIGN KEY (source_toss_id) REFERENCES sot.tosses(id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS sessions_document_idx ON sot.sessions(document_id);
CREATE INDEX IF NOT EXISTS branches_session_idx ON sot.branches(session_id);
CREATE INDEX IF NOT EXISTS turns_branch_idx ON sot.turns(branch_id, ordinal);
CREATE INDEX IF NOT EXISTS cites_branch_idx ON sot.cites(branch_id);
CREATE INDEX IF NOT EXISTS proposals_branch_idx ON sot.proposals(branch_id);
