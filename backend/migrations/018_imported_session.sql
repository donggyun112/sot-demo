-- A conversation that happened somewhere else, brought in whole.
--
-- The reasoning behind a decision is usually already had, in whatever tool it
-- was had in. Retyping it to get it in front of the agent is how it gets
-- lost, so it can be imported instead — and it has to be marked, because SOT
-- did not run it. Everything else in a session is an exchange this system
-- witnessed; an import is a claim about one it did not, and a reader who
-- cannot tell those apart cannot trust either.
--
-- NULL for every session that started here, which is all of them so far.
ALTER TABLE sot.sot_session
    ADD COLUMN imported_from text,
    ADD CONSTRAINT sot_session_imported_from_named CHECK (
        imported_from IS NULL OR length(btrim(imported_from)) BETWEEN 1 AND 200
    );
