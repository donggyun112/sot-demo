-- Handing a session over is adding a member to it, not minting a link.
--
-- A share link was a capability token that let ANOTHER workspace fork the
-- curated turns into a detached copy: no document, no way back to the
-- conversation, and nothing the two sides could keep working on together.
-- There is no cross-workspace sharing in this product, and what people
-- actually want is to continue the same session, so both the link and the
-- fork provenance it wrote are gone. `sot_session_member` already carries who
-- holds a session, and holding it is what grants access.
DROP TABLE IF EXISTS sot.sot_share_link;
DROP TABLE IF EXISTS sot.sot_fork_origin;
