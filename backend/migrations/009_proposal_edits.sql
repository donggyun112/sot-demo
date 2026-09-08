-- A proposal is a set of edits, not a replacement document.
--
-- The old shape stored the whole new body in `content`, so merging overwrote
-- the document and the review diff showed every untouched line as removed and
-- re-added. An edit names the text it replaces, so a proposal changes only
-- what the decision changes and reads as a real diff.
CREATE TABLE sot.sot_proposal_edit (
    workspace_id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    proposal_version integer NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    -- Empty `find` appends; anything else must name exactly one place in the
    -- document, which the domain enforces when the version is authored.
    find text NOT NULL,
    replace text NOT NULL,
    PRIMARY KEY (workspace_id, proposal_id, proposal_version, position),
    FOREIGN KEY (workspace_id, proposal_id, proposal_version)
        REFERENCES sot.sot_proposal_version(workspace_id, proposal_id, proposal_version)
);

-- Existing versions were whole-document bodies. Carry each across as one
-- append so no row is lost; they were authored before edits existed.
INSERT INTO sot.sot_proposal_edit
    (workspace_id, proposal_id, proposal_version, position, find, replace)
SELECT workspace_id, proposal_id, proposal_version, 0, '', content
FROM sot.sot_proposal_version;

ALTER TABLE sot.sot_proposal_version DROP COLUMN content;
