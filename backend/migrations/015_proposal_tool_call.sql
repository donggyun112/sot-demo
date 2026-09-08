-- Which sot_update call wrote this.
--
-- A passage could be traced to the session it came out of, but not to the
-- moment inside it. The conversation that produced a document is long; "it
-- came from this session" still leaves a reader scrolling for the point where
-- the decision was actually written.
--
-- The agent knows: the tool call is the write. Recording its id ties a merged
-- passage to the exact turn in the transcript.
--
-- NULL for a version no tool call made — one authored before this column, or
-- through any path that is not the agent's tool.
ALTER TABLE sot.sot_proposal_version
    ADD COLUMN tool_call_id text
        CHECK (tool_call_id IS NULL OR length(btrim(tool_call_id)) > 0);
