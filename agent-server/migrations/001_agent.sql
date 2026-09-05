CREATE SCHEMA IF NOT EXISTS agent;

CREATE TABLE IF NOT EXISTS agent.agent_request (
    run_id                 uuid PRIMARY KEY,
    thread_id              uuid NOT NULL,
    semora_run_id          uuid NOT NULL,
    request_kind           text NOT NULL CHECK (request_kind IN ('prompt', 'resume')),
    owner_issuer           text NOT NULL,
    owner_subject_hash     bytea NOT NULL CHECK (octet_length(owner_subject_hash) = 32),
    original_input         jsonb,
    payload_hash           bytea NOT NULL CHECK (octet_length(payload_hash) = 32),
    execution_config       jsonb,
    next_event_sequence    bigint NOT NULL DEFAULT 1 CHECK (next_event_sequence > 0),
    abort_requested_at     timestamptz,
    deadline_exceeded_at   timestamptz,
    terminal_sequence      bigint,
    terminal_at            timestamptz,
    terminal_event         jsonb,
    replay_expires_at      timestamptz,
    tombstone_expires_at   timestamptz,
    redacted_at            timestamptz,
    created_at             timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (substring(run_id::text FROM 15 FOR 1) = '7'),
    CHECK (substring(thread_id::text FROM 15 FOR 1) = '7'),
    CHECK (substring(semora_run_id::text FROM 15 FOR 1) = '7'),
    CHECK (execution_config IS NULL OR jsonb_typeof(execution_config) = 'object'),
    CHECK (original_input IS NULL OR jsonb_typeof(original_input) = 'object'),
    CHECK ((terminal_sequence IS NULL) = (terminal_at IS NULL)),
    CHECK ((terminal_at IS NULL AND terminal_event IS NULL)
        OR (terminal_at IS NOT NULL AND terminal_event IS NOT NULL)),
    CHECK (terminal_sequence IS NULL OR terminal_sequence > 0)
);

CREATE INDEX IF NOT EXISTS agent_request_owner_created_idx
    ON agent.agent_request (owner_subject_hash, created_at DESC);

CREATE TABLE IF NOT EXISTS agent.agent_event (
    run_id          uuid NOT NULL REFERENCES agent.agent_request(run_id) ON DELETE CASCADE,
    sequence        bigint NOT NULL CHECK (sequence > 0),
    event_id        uuid NOT NULL UNIQUE,
    producer_key    text,
    event_type      text NOT NULL,
    event           jsonb NOT NULL CHECK (jsonb_typeof(event) = 'object'),
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, sequence),
    CHECK (substring(event_id::text FROM 15 FOR 1) = '7')
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_event_producer_key_uq
    ON agent.agent_event (run_id, producer_key)
    WHERE producer_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS agent.agent_interrupt (
    interrupt_id          uuid PRIMARY KEY,
    origin_run_id         uuid NOT NULL
                          REFERENCES agent.agent_request(run_id) ON DELETE CASCADE,
    semora_run_id         uuid NOT NULL,
    semora_pending_id     text NOT NULL,
    semora_tool_call_id   text NOT NULL,
    resolution            text CHECK (resolution IN ('resolved', 'cancelled')),
    resolved_by_run_id    uuid REFERENCES agent.agent_request(run_id) ON DELETE RESTRICT,
    created_at            timestamptz NOT NULL DEFAULT clock_timestamp(),
    resolved_at           timestamptz,
    UNIQUE (semora_run_id, semora_pending_id),
    CHECK (substring(interrupt_id::text FROM 15 FOR 1) = '7'),
    CHECK (substring(semora_run_id::text FROM 15 FOR 1) = '7')
);

CREATE OR REPLACE FUNCTION agent.append_event(
    p_run_id       uuid,
    p_event_id     uuid,
    p_producer_key text,
    p_event_type   text,
    p_event        jsonb,
    p_is_terminal  boolean DEFAULT false
) RETURNS SETOF agent.agent_event
LANGUAGE plpgsql
AS $$
DECLARE
    v_sequence          bigint;
    v_terminal_sequence bigint;
    v_now               timestamptz := clock_timestamp();
BEGIN
    SELECT next_event_sequence, terminal_sequence
      INTO v_sequence, v_terminal_sequence
      FROM agent.agent_request
     WHERE run_id = p_run_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown agent run %', p_run_id USING ERRCODE = '23503';
    END IF;

    IF p_producer_key IS NOT NULL THEN
        RETURN QUERY
        SELECT e.* FROM agent.agent_event AS e
         WHERE e.run_id = p_run_id AND e.producer_key = p_producer_key;
        IF FOUND THEN
            RETURN;
        END IF;
    END IF;

    IF p_is_terminal AND p_producer_key IS DISTINCT FROM 'run:terminal' THEN
        RAISE EXCEPTION 'terminal event requires run:terminal producer key'
            USING ERRCODE = '23514';
    END IF;
    IF p_is_terminal AND v_terminal_sequence IS NOT NULL THEN
        RAISE EXCEPTION 'run % already has a terminal event', p_run_id
            USING ERRCODE = '23505';
    END IF;

    UPDATE agent.agent_request
       SET next_event_sequence = v_sequence + 1
     WHERE run_id = p_run_id;

    INSERT INTO agent.agent_event
        (run_id, sequence, event_id, producer_key, event_type, event, created_at)
    VALUES
        (p_run_id, v_sequence, p_event_id, p_producer_key, p_event_type, p_event, v_now);

    IF p_is_terminal THEN
        UPDATE agent.agent_request
           SET terminal_sequence = v_sequence,
               terminal_at = v_now,
               terminal_event = p_event,
               replay_expires_at = v_now + interval '90 days',
               tombstone_expires_at = v_now + interval '365 days'
         WHERE run_id = p_run_id;
    END IF;

    RETURN QUERY
    SELECT e.* FROM agent.agent_event AS e
     WHERE e.run_id = p_run_id AND e.sequence = v_sequence;
END;
$$;
