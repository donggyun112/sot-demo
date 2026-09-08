-- Say who said it.
--
-- A turn recorded what was said and when, but not by whom, so every reader's
-- own name went on every line: open a session someone handed you and their
-- words are attributed to you. Forking makes that worse, because a fork is a
-- copy of what someone ELSE said.
--
-- Backfill is the branch's creator: before this column the only person who
-- could write to a branch was the one who made it, so that is not a guess.
ALTER TABLE sot.sot_turn ADD COLUMN created_by uuid;

UPDATE sot.sot_turn AS turn
SET created_by = branch.created_by
FROM sot.sot_branch AS branch
WHERE turn.workspace_id = branch.workspace_id
  AND turn.branch_id = branch.id;

ALTER TABLE sot.sot_turn
    ALTER COLUMN created_by SET NOT NULL,
    ADD CONSTRAINT sot_turn_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES sot.sot_user(id);
