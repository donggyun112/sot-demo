-- Continue someone else's conversation without writing in their session.
--
-- A session you were only sent to READ is a dead end: you can follow the
-- reasoning and then have nowhere to take it. Forking copies the transcript
-- into a session of your own, at the point you read it, and remembers where
-- it came from so the two are still connected.
--
-- Both columns are NULL for a session that started from nothing, and they are
-- set together: an origin is a branch, not just a session.
ALTER TABLE sot.sot_session
    ADD COLUMN forked_from_session_id uuid,
    ADD COLUMN forked_from_branch_id uuid,
    ADD CONSTRAINT sot_session_fork_origin_complete CHECK (
        (forked_from_session_id IS NULL) = (forked_from_branch_id IS NULL)
    ),
    -- A fork never crosses a workspace: sharing does not, either.
    ADD CONSTRAINT sot_session_fork_origin_session
        FOREIGN KEY (workspace_id, forked_from_session_id)
        REFERENCES sot.sot_session(workspace_id, id),
    ADD CONSTRAINT sot_session_fork_origin_branch
        FOREIGN KEY (workspace_id, forked_from_branch_id)
        REFERENCES sot.sot_branch(workspace_id, id);

-- What came out of a conversation, for the session it came out of.
CREATE INDEX sot_session_fork_origin
    ON sot.sot_session (workspace_id, forked_from_session_id)
    WHERE forked_from_session_id IS NOT NULL;
