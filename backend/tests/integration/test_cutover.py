from __future__ import annotations

import httpx
import psycopg
import pytest

from sot.bootstrap.app import build_app
from sot.bootstrap.migrate import MIGRATIONS_PATH, run_migrations
from sot.bootstrap.settings import Settings

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_unmigrated_startup_fails_without_creating_schema(
    database_url: str,
) -> None:
    app = build_app(Settings(database_url=database_url, environment="test"))
    with pytest.raises(RuntimeError, match="sot-migrate"):
        async with app.router.lifespan_context(app):
            pass
    assert app.state.pool.closed
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        row = await (
            await connection.execute("SELECT to_regnamespace('sot')")
        ).fetchone()
        assert row == (None,)


async def test_canonical_startup_is_unseeded_even_with_development_auth(
    database_url: str,
) -> None:
    await run_migrations(database_url, MIGRATIONS_PATH)
    app = build_app(
        Settings(database_url=database_url, environment="test", development_auth=True)
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://test"
        ) as client:
            assert (await client.get("/api/v1/bootstrap")).status_code == 404
            assert (await client.get("/api/v1/workspaces")).status_code == 401
            assert (await client.get("/healthz")).status_code == 200
            assert (await client.get("/readyz")).status_code == 200
        async with await psycopg.AsyncConnection.connect(database_url) as connection:
            for table in ("sot_user", "sot_workspace", "sot_document", "documents"):
                row = await (
                    await connection.execute(
                        psycopg.sql.SQL("SELECT count(*) FROM sot.{}").format(
                            psycopg.sql.Identifier(table)
                        )
                    )
                ).fetchone()
                assert row == (0,)
    assert app.state.pool.closed
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://test"
    ) as client:
        assert (await client.get("/healthz")).status_code == 200
        assert (await client.get("/readyz")).status_code == 503


@pytest.mark.parametrize(
    "mutation",
    [
        "DELETE FROM sot.schema_migration WHERE version=7",
        "UPDATE sot.schema_migration SET filename='007_other.sql' WHERE version=7",
    ],
)
async def test_pending_or_mismatched_migration_blocks_web_startup(
    database_url: str,
    mutation: str,
) -> None:
    await run_migrations(database_url, MIGRATIONS_PATH)
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute(mutation)
        before = await (
            await connection.execute(
                "SELECT * FROM sot.schema_migration ORDER BY version"
            )
        ).fetchall()
    app = build_app(Settings(database_url=database_url, environment="test"))
    with pytest.raises(RuntimeError, match="sot-migrate"):
        async with app.router.lifespan_context(app):
            pass
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        assert (
            await (
                await connection.execute(
                    "SELECT * FROM sot.schema_migration ORDER BY version"
                )
            ).fetchall()
            == before
        )


async def test_browser_seed_is_repeatable_and_unknown_google_credentials_fail(
    database_url: str,
) -> None:
    from tests.e2e_app import (
        GOOGLE_CLIENT_ID,
        StaticGoogleTokenVerifier,
        seed_browser_fixtures,
    )

    await run_migrations(database_url, MIGRATIONS_PATH)
    await seed_browser_fixtures(database_url)
    await seed_browser_fixtures(database_url)
    app = build_app(
        Settings(
            database_url=database_url,
            environment="test",
            google_client_id=GOOGLE_CLIENT_ID,
        ),
        google_token_verifier=StaticGoogleTokenVerifier(),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://test"
        ) as client,
    ):
        for credential in ("alice", "google-test-mallory", "google-test-alice-extra"):
            response = await client.post(
                "/api/v1/auth/google", json={"credential": credential}
            )
            assert response.status_code == 401
        async with await psycopg.AsyncConnection.connect(database_url) as connection:
            for table, count in (
                ("sot_user", 2),
                ("sot_workspace", 2),
                ("sot_document", 2),
                ("sot_session", 0),
                ("sot_auth_session", 0),
            ):
                assert await (
                    await connection.execute(
                        psycopg.sql.SQL("SELECT count(*) FROM sot.{}").format(
                            psycopg.sql.Identifier(table)
                        )
                    )
                ).fetchone() == (count,)


async def test_cutover_preserves_legacy_rows_without_inventing_identity_or_tenant(
    database_url: str,
) -> None:
    await run_migrations(database_url, MIGRATIONS_PATH)
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute("""
            INSERT INTO sot.documents VALUES
            ('10000000-0000-4000-8000-000000000001', 'Legacy private document',
             '10000000-0000-4000-8000-000000000002', 'alice', now());
            INSERT INTO sot.revisions VALUES
            ('10000000-0000-4000-8000-000000000002',
             '10000000-0000-4000-8000-000000000001', 1, 'Legacy content', NULL, 'alice', now());
            DELETE FROM sot.schema_migration WHERE version=7;
        """)
    await run_migrations(database_url, MIGRATIONS_PATH)
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        assert await (
            await connection.execute("SELECT title FROM sot.documents")
        ).fetchall() == [("Legacy private document",)]
        assert await (
            await connection.execute("SELECT content FROM sot.revisions")
        ).fetchall() == [("Legacy content",)]
        assert await (
            await connection.execute("SELECT count(*) FROM sot.sot_user")
        ).fetchone() == (0,)
        assert await (
            await connection.execute("SELECT count(*) FROM sot.sot_workspace")
        ).fetchone() == (0,)
        assert await (
            await connection.execute("SELECT count(*) FROM sot.sot_document")
        ).fetchone() == (0,)
        assert await (
            await connection.execute("SELECT max(version) FROM sot.schema_migration")
        ).fetchone() == (16,)
