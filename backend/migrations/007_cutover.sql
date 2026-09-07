-- Canonical runtime cutover marker; intentionally no data or schema rewrite.
-- 001 uses unverified actor aliases and has no tenant/Google identity mapping.
-- Automatically importing those rows would invent ownership or disclose drafts.
-- Preserve all legacy tables/rows for an explicitly mapped future import. The
-- canonical schema from 002–006 is already complete, so no backfill is required.
-- Demo users/workspaces/documents belong only to tests/e2e_app.py.
SELECT 1;
