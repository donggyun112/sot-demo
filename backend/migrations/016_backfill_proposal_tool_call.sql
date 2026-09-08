-- Tie updates already merged to the call that wrote them.
--
-- The tool call id was not recorded until now, so every existing passage
-- could be traced to its session and no further. The link is recoverable
-- rather than lost: the transcript still holds the sot_update call with the
-- edits it was made with, and the proposal holds the same edits.
--
-- This matches on identity, not resemblance:
--
--   * the call is a sot_update in a branch of the proposal's OWN session;
--   * its arguments are the proposal version's edits, in the same order;
--   * only versions with no call recorded are touched;
--   * a version matching more than one call is left alone, because then the
--     match is a guess and a wrong link is worse than no link.
WITH call AS (
    SELECT
        branch.session_id,
        turn.content::jsonb ->> 'tool_call_id' AS tool_call_id,
        turn.content::jsonb -> 'args' -> 'edits' AS edits
    FROM sot.sot_turn AS turn
    JOIN sot.sot_branch AS branch
        ON branch.workspace_id = turn.workspace_id
       AND branch.id = turn.branch_id
    WHERE turn.role = 'tool'
      AND turn.content ~ '^\s*\{'
      AND turn.content::jsonb ->> 'kind' = 'call'
      AND turn.content::jsonb ->> 'tool_name' = 'sot_update'
      AND turn.content::jsonb ->> 'tool_call_id' IS NOT NULL
),
candidate AS (
    SELECT
        version.workspace_id,
        version.proposal_id,
        version.proposal_version,
        min(call.tool_call_id) AS tool_call_id,
        count(*) AS matches
    FROM sot.sot_proposal_version AS version
    JOIN sot.sot_proposal AS proposal
        ON proposal.workspace_id = version.workspace_id
       AND proposal.id = version.proposal_id
    JOIN call
        ON call.session_id = proposal.source_session_id
       AND call.edits = (
            SELECT jsonb_agg(
                       jsonb_build_object('find', edit.find, 'replace', edit.replace)
                       ORDER BY edit.position
                   )
            FROM sot.sot_proposal_edit AS edit
            WHERE edit.workspace_id = version.workspace_id
              AND edit.proposal_id = version.proposal_id
              AND edit.proposal_version = version.proposal_version
       )
    WHERE version.tool_call_id IS NULL
    GROUP BY version.workspace_id, version.proposal_id, version.proposal_version
)
UPDATE sot.sot_proposal_version AS version
SET tool_call_id = candidate.tool_call_id
FROM candidate
WHERE candidate.matches = 1
  AND version.workspace_id = candidate.workspace_id
  AND version.proposal_id = candidate.proposal_id
  AND version.proposal_version = candidate.proposal_version;
