CREATE TABLE IF NOT EXISTS ledger_step (
    run_id text NOT NULL,
    key text NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'done')),
    value jsonb,
    attempt integer NOT NULL DEFAULT 1,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    PRIMARY KEY (run_id, key)
);

CREATE TABLE IF NOT EXISTS ledger_run_lease (
    run_id text PRIMARY KEY,
    owner text NOT NULL,
    token bigint NOT NULL DEFAULT 1,
    expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_input (
    sequence bigserial PRIMARY KEY,
    run_id text NOT NULL,
    input_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'claimed', 'admitted', 'discarded')),
    value jsonb NOT NULL,
    submitted_at timestamptz NOT NULL DEFAULT now(),
    admitted_at timestamptz,
    UNIQUE (run_id, input_id)
);

CREATE INDEX IF NOT EXISTS ledger_input_pending
    ON ledger_input (run_id, sequence) WHERE status IN ('pending', 'claimed');
CREATE INDEX IF NOT EXISTS ledger_step_running
    ON ledger_step (started_at) WHERE status = 'running';

CREATE TABLE IF NOT EXISTS ledger_transcript (
    entry jsonb NOT NULL,
    seq bigserial PRIMARY KEY,
    ts timestamptz NOT NULL,
    conversation_id text GENERATED ALWAYS AS (entry ->> 'conversation_id') STORED,
    uuid text GENERATED ALWAYS AS (entry ->> 'uuid') STORED,
    parent_uuid text GENERATED ALWAYS AS (entry ->> 'parent_uuid') STORED,
    type text GENERATED ALWAYS AS (entry ->> 'type') STORED,
    schema_version text GENERATED ALWAYS AS (entry ->> 'schema_version') STORED,
    run_id text GENERATED ALWAYS AS (entry -> 'metadata' ->> 'run_id') STORED,
    UNIQUE (conversation_id, uuid)
);

CREATE INDEX IF NOT EXISTS ledger_transcript_replay
    ON ledger_transcript (conversation_id, seq);
CREATE INDEX IF NOT EXISTS ledger_transcript_run
    ON ledger_transcript (run_id) WHERE run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS ledger_run (
    run_id text PRIMARY KEY,
    conversation_id text,
    stop_reason text,
    tool_calls integer,
    interrupted_mid_turn boolean,
    started_at timestamptz,
    ended_at timestamptz
);

CREATE INDEX IF NOT EXISTS ledger_run_conversation
    ON ledger_run (conversation_id, started_at DESC);

CREATE TABLE IF NOT EXISTS ledger_run_model (
    run_id text NOT NULL,
    model text NOT NULL,
    prompt_tokens bigint,
    completion_tokens bigint,
    total_tokens bigint,
    cached_tokens bigint,
    cache_write_tokens bigint,
    cost_usd numeric(12, 6),
    PRIMARY KEY (run_id, model)
);

CREATE INDEX IF NOT EXISTS ledger_run_model_by_model ON ledger_run_model (model);
