BEGIN;

ALTER TABLE agent.agent_interrupt
    ADD COLUMN IF NOT EXISTS runtime_run_id uuid;
UPDATE agent.agent_interrupt
   SET runtime_run_id = origin_run_id
 WHERE runtime_run_id IS NULL;
ALTER TABLE agent.agent_interrupt
    ALTER COLUMN runtime_run_id SET NOT NULL;
ALTER TABLE agent.agent_interrupt
    DROP COLUMN IF EXISTS semora_run_id;
ALTER TABLE agent.agent_interrupt
    DROP CONSTRAINT IF EXISTS agent_interrupt_origin_deferred_uq;
ALTER TABLE agent.agent_interrupt
    DROP CONSTRAINT IF EXISTS agent_interrupt_runtime_pending_uq;
ALTER TABLE agent.agent_interrupt
    ADD CONSTRAINT agent_interrupt_runtime_pending_uq
    UNIQUE (runtime_run_id, deferred_call_id);
CREATE INDEX IF NOT EXISTS agent_interrupt_runtime_run_idx
    ON agent.agent_interrupt (runtime_run_id);

CREATE TABLE IF NOT EXISTS ledger_step (
    run_id      text        NOT NULL,
    key         text        NOT NULL,
    status      text        NOT NULL CHECK (status IN ('running', 'done')),
    value       jsonb,
    attempt     integer     NOT NULL DEFAULT 1,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    PRIMARY KEY (run_id, key)
);

CREATE TABLE IF NOT EXISTS ledger_run_lease (
    run_id     text        PRIMARY KEY,
    owner      text        NOT NULL,
    token      bigint      NOT NULL DEFAULT 1,
    expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_input (
    sequence     bigserial   PRIMARY KEY,
    run_id       text        NOT NULL,
    input_id     text        NOT NULL,
    status       text        NOT NULL,
    value        jsonb       NOT NULL,
    submitted_at timestamptz NOT NULL DEFAULT now(),
    admitted_at  timestamptz,
    UNIQUE (run_id, input_id)
);

ALTER TABLE ledger_input DROP CONSTRAINT IF EXISTS ledger_input_status_check;
ALTER TABLE ledger_input ADD CONSTRAINT ledger_input_status_check
    CHECK (status IN ('pending', 'claimed', 'admitted', 'discarded'));

DROP INDEX IF EXISTS ledger_input_pending;
CREATE INDEX IF NOT EXISTS ledger_input_pending
    ON ledger_input (run_id, sequence) WHERE status IN ('pending', 'claimed');
CREATE INDEX IF NOT EXISTS ledger_step_running
    ON ledger_step (started_at) WHERE status = 'running';

CREATE TABLE IF NOT EXISTS ledger_transcript (
    entry           jsonb       NOT NULL,
    seq             bigserial   PRIMARY KEY,
    ts              timestamptz NOT NULL,
    conversation_id text        GENERATED ALWAYS AS (entry ->> 'conversation_id') STORED,
    uuid            text        GENERATED ALWAYS AS (entry ->> 'uuid') STORED,
    parent_uuid     text        GENERATED ALWAYS AS (entry ->> 'parent_uuid') STORED,
    type            text        GENERATED ALWAYS AS (entry ->> 'type') STORED,
    schema_version  text        GENERATED ALWAYS AS (entry ->> 'schema_version') STORED,
    run_id          text        GENERATED ALWAYS AS (entry -> 'metadata' ->> 'run_id') STORED,
    UNIQUE (conversation_id, uuid)
);

CREATE INDEX IF NOT EXISTS ledger_transcript_replay
    ON ledger_transcript (conversation_id, seq);
CREATE INDEX IF NOT EXISTS ledger_transcript_run
    ON ledger_transcript (run_id) WHERE run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS ledger_run (
    run_id               text PRIMARY KEY,
    conversation_id      text,
    stop_reason          text,
    tool_calls           integer,
    interrupted_mid_turn boolean,
    started_at           timestamptz,
    ended_at             timestamptz
);

CREATE INDEX IF NOT EXISTS ledger_run_conversation
    ON ledger_run (conversation_id, started_at DESC);

CREATE TABLE IF NOT EXISTS ledger_run_model (
    run_id             text   NOT NULL,
    model              text   NOT NULL,
    prompt_tokens      bigint,
    completion_tokens  bigint,
    total_tokens       bigint,
    cached_tokens      bigint,
    cache_write_tokens bigint,
    cost_usd           numeric(12, 6),
    PRIMARY KEY (run_id, model)
);

CREATE INDEX IF NOT EXISTS ledger_run_model_by_model
    ON ledger_run_model (model);

COMMIT;
