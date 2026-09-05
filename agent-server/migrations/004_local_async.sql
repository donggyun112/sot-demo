BEGIN;

ALTER TABLE agent.agent_interrupt
    DROP CONSTRAINT IF EXISTS agent_interrupt_workflow_id_uuid7_check,
    DROP CONSTRAINT IF EXISTS agent_interrupt_workflow_deferred_uq,
    DROP CONSTRAINT IF EXISTS agent_interrupt_origin_deferred_uq;
ALTER TABLE agent.agent_interrupt DROP COLUMN IF EXISTS workflow_id;
ALTER TABLE agent.agent_interrupt
    ADD CONSTRAINT agent_interrupt_origin_deferred_uq
    UNIQUE (origin_run_id, deferred_call_id);

ALTER TABLE agent.agent_request
    DROP CONSTRAINT IF EXISTS agent_request_workflow_id_uuid7_check;
ALTER TABLE agent.agent_request DROP COLUMN IF EXISTS workflow_id;

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
    IF p_producer_key IS NULL THEN
        RAISE EXCEPTION 'producer key is required' USING ERRCODE = '23502';
    END IF;

    SELECT next_event_sequence, terminal_sequence
      INTO v_sequence, v_terminal_sequence
      FROM agent.agent_request
     WHERE run_id = p_run_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown agent run %', p_run_id USING ERRCODE = '23503';
    END IF;

    RETURN QUERY
    SELECT e.* FROM agent.agent_event AS e
     WHERE e.run_id = p_run_id AND e.producer_key = p_producer_key;
    IF FOUND THEN
        RETURN;
    END IF;

    IF v_terminal_sequence IS NOT NULL THEN
        RETURN QUERY
        SELECT e.* FROM agent.agent_event AS e
         WHERE e.run_id = p_run_id AND e.sequence = v_terminal_sequence;
        RETURN;
    END IF;

    IF p_is_terminal AND p_producer_key IS DISTINCT FROM 'run:terminal' THEN
        RAISE EXCEPTION 'terminal event requires run:terminal producer key'
            USING ERRCODE = '23514';
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

COMMIT;
