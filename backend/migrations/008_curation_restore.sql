-- A dropped turn can be put back. The op log is append-only, so undoing a
-- drop is itself an op: it names one turn and carries no content, because the
-- content it restores is the turn's own.
--
-- 004 left both checks unnamed, so their generated names are dropped by every
-- spelling Postgres could have chosen and the replacements are named.
ALTER TABLE sot.sot_curation_op
    DROP CONSTRAINT IF EXISTS sot_curation_op_kind_check,
    DROP CONSTRAINT IF EXISTS sot_curation_op_check,
    DROP CONSTRAINT IF EXISTS sot_curation_op_check1;

ALTER TABLE sot.sot_curation_op
    ADD CONSTRAINT sot_curation_op_kind
    CHECK (kind IN ('drop', 'edit', 'join', 'restore'));

ALTER TABLE sot.sot_curation_op
    ADD CONSTRAINT sot_curation_op_shape
    CHECK ((kind = 'drop' AND content IS NULL AND cardinality(source_ids) = 1)
        OR (kind = 'edit' AND content IS NOT NULL AND cardinality(source_ids) = 1)
        OR (kind = 'restore' AND content IS NULL AND cardinality(source_ids) = 1)
        OR (kind = 'join' AND content IS NOT NULL));
