BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'agent' AND table_name = 'agent_request'
           AND column_name = 'semora_run_id'
    ) THEN
        ALTER TABLE agent.agent_request RENAME COLUMN semora_run_id TO workflow_id;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'agent' AND table_name = 'agent_interrupt'
           AND column_name = 'semora_run_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'agent' AND table_name = 'agent_interrupt'
           AND column_name = 'semora_pending_id'
    ) THEN
        ALTER TABLE agent.agent_interrupt RENAME COLUMN semora_run_id TO workflow_id;
        ALTER TABLE agent.agent_interrupt RENAME COLUMN semora_pending_id TO deferred_call_id;
        ALTER TABLE agent.agent_interrupt RENAME COLUMN semora_tool_call_id TO tool_call_id;
    END IF;
END;
$$;

UPDATE agent.agent_event
   SET producer_key = 'legacy:' || sequence::text
 WHERE producer_key IS NULL;

ALTER TABLE agent.agent_event ALTER COLUMN producer_key SET NOT NULL;

ALTER TABLE agent.agent_request
    DROP CONSTRAINT IF EXISTS agent_request_semora_run_id_check,
    DROP CONSTRAINT IF EXISTS agent_request_workflow_id_uuid7_check;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'agent' AND table_name = 'agent_request'
           AND column_name = 'workflow_id'
    ) THEN
        ALTER TABLE agent.agent_request
            ADD CONSTRAINT agent_request_workflow_id_uuid7_check
            CHECK (substring(workflow_id::text FROM 15 FOR 1) = '7');
    END IF;
END;
$$;

ALTER TABLE agent.agent_interrupt
    DROP CONSTRAINT IF EXISTS agent_interrupt_semora_run_id_check,
    DROP CONSTRAINT IF EXISTS agent_interrupt_semora_run_id_semora_pending_id_key,
    DROP CONSTRAINT IF EXISTS agent_interrupt_workflow_id_uuid7_check,
    DROP CONSTRAINT IF EXISTS agent_interrupt_workflow_deferred_uq;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'agent' AND table_name = 'agent_interrupt'
           AND column_name = 'workflow_id'
    ) THEN
        ALTER TABLE agent.agent_interrupt
            ADD CONSTRAINT agent_interrupt_workflow_id_uuid7_check
                CHECK (substring(workflow_id::text FROM 15 FOR 1) = '7'),
            ADD CONSTRAINT agent_interrupt_workflow_deferred_uq
                UNIQUE (workflow_id, deferred_call_id);
    END IF;
END;
$$;

DROP INDEX IF EXISTS agent.agent_event_producer_key_uq;
CREATE UNIQUE INDEX agent_event_producer_key_uq
    ON agent.agent_event (run_id, producer_key);

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

DO $$
DECLARE
    request_row record;
BEGIN
    FOR request_row IN
        SELECT run_id FROM agent.agent_request WHERE terminal_sequence IS NULL
    LOOP
        PERFORM * FROM agent.append_event(
            request_row.run_id,
            request_row.run_id,
            'run:terminal',
            'RUN_ERROR',
            jsonb_build_object(
                'type', 'RUN_ERROR',
                'message', 'Runtime migrated while the run was incomplete.',
                'code', 'runtime_migrated'
            ),
            true
        );
    END LOOP;
END;
$$;

COMMIT;
