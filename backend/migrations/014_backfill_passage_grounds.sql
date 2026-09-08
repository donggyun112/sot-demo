-- Ground every passage an update wrote, not just its first one.
--
-- Grounds used to be derived once per EDIT, anchored on the first line it
-- added. One edit routinely adds a whole skeleton of sections, so a merged
-- revision carried a single anchor and every section after the first read as
-- unsupported — no marking in the document, and no way back to the
-- conversation that decided it.
--
-- The derivation was corrected; these rows were written before it. This is
-- the same derivation applied to the same inputs, which is why it is a
-- repair and not an invention:
--
--   * only revisions that ALREADY carry grounds are touched, so no evidence
--     is claimed where none was recorded;
--   * the bundle and item are the ones that revision already cites;
--   * anchors are headings this revision introduced — present in its own text
--     and absent from the revision before it — which is exactly what its
--     update wrote;
--   * existing anchors are left alone, never repointed or removed.
WITH grounded AS (
    -- The bundle this revision already cites: its first recorded ground.
    SELECT DISTINCT ON (workspace_id, revision_id)
        workspace_id,
        revision_id,
        bundle_id,
        bundle_item_position,
        max(position) OVER (PARTITION BY workspace_id, revision_id)
            AS last_position
    FROM sot.sot_revision_citation
    ORDER BY workspace_id, revision_id, position
),
preceding AS (
    SELECT
        workspace_id,
        id AS revision_id,
        content,
        lag(content) OVER (
            PARTITION BY workspace_id, document_id ORDER BY number
        ) AS before
    FROM sot.sot_document_revision
),
introduced AS (
    SELECT
        p.workspace_id,
        p.revision_id,
        btrim(line) AS anchor,
        row_number() OVER (
            PARTITION BY p.workspace_id, p.revision_id ORDER BY ord
        ) AS offset_in_revision
    FROM preceding AS p
    CROSS JOIN LATERAL regexp_split_to_table(p.content, E'\n')
        WITH ORDINALITY AS split(line, ord)
    WHERE line ~ '^#{1,6}[ \t]+\S'
      AND position(btrim(line) IN coalesce(p.before, '')) = 0
)
INSERT INTO sot.sot_revision_citation
    (workspace_id, revision_id, position, claim_anchor,
     bundle_id, bundle_item_position)
SELECT
    i.workspace_id,
    i.revision_id,
    g.last_position + i.offset_in_revision,
    i.anchor,
    g.bundle_id,
    g.bundle_item_position
FROM introduced AS i
JOIN grounded AS g
    ON g.workspace_id = i.workspace_id AND g.revision_id = i.revision_id
WHERE NOT EXISTS (
    SELECT 1
    FROM sot.sot_revision_citation AS existing
    WHERE existing.workspace_id = i.workspace_id
      AND existing.revision_id = i.revision_id
      AND existing.claim_anchor = i.anchor
);
