-- A file someone brought into the conversation is its own kind of turn.
--
-- It was stored as a user turn holding the file's name and its whole body,
-- which is what the agent should read but not what a reader should see: the
-- transcript printed a hundred lines of YAML where a person had simply
-- handed over a file. The role is what lets the transcript show a file as a
-- file while the model still reads the text.
ALTER TABLE sot.sot_turn DROP CONSTRAINT sot_turn_role_check;

ALTER TABLE sot.sot_turn
    ADD CONSTRAINT sot_turn_role_check
    CHECK (role IN ('user', 'assistant', 'tool', 'attachment'));
