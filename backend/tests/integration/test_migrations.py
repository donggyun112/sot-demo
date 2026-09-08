from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from sot.bootstrap import migrate
from sot.bootstrap.app import build_app
from sot.bootstrap.migrate import MigrationPlanError, run_migrations
from sot.bootstrap.settings import Settings

MIGRATIONS = Path(__file__).parents[2] / "migrations"


async def applied_versions(database_url: str) -> tuple[int, ...]:
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        cursor = await connection.execute(
            "SELECT version FROM sot.schema_migration ORDER BY version"
        )
        rows = await cursor.fetchall()
    return tuple(row[0] for row in rows)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_migrations_are_ordered_once_and_not_run_by_app_startup(
    database_url: str,
) -> None:
    await run_migrations(database_url, MIGRATIONS)
    await run_migrations(database_url, MIGRATIONS)
    expected = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
    assert await applied_versions(database_url) == expected

    app = build_app(Settings(database_url=database_url, models=("test",)))
    async with app.router.lifespan_context(app):
        assert await applied_versions(database_url) == expected


@pytest.mark.asyncio
@pytest.mark.integration
async def test_recorded_migration_filename_mismatch_is_rejected(
    database_url: str, tmp_path: Path
) -> None:
    (tmp_path / "001_first.sql").write_text("SELECT 1", encoding="utf-8")
    await run_migrations(database_url, tmp_path)
    (tmp_path / "001_first.sql").rename(tmp_path / "001_renamed.sql")
    with pytest.raises(MigrationPlanError, match="filename mismatch"):
        await run_migrations(database_url, tmp_path)
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        row = await (
            await connection.execute(
                "SELECT filename FROM sot.schema_migration WHERE version = 1"
            )
        ).fetchone()
        assert row == ("001_first.sql",)


@pytest.mark.asyncio
async def test_migration_plan_rejects_a_version_gap_before_connecting(
    tmp_path: Path,
) -> None:
    (tmp_path / "001_first.sql").write_text("SELECT 1", encoding="utf-8")
    (tmp_path / "003_third.sql").write_text("SELECT 3", encoding="utf-8")

    with pytest.raises(MigrationPlanError, match="gap"):
        await run_migrations("postgresql://unused", tmp_path)


@pytest.mark.asyncio
async def test_migration_plan_rejects_duplicate_versions_before_connecting(
    tmp_path: Path,
) -> None:
    (tmp_path / "001_first.sql").write_text("SELECT 1", encoding="utf-8")
    (tmp_path / "001_again.sql").write_text("SELECT 2", encoding="utf-8")

    with pytest.raises(MigrationPlanError, match="duplicate"):
        await run_migrations("postgresql://unused", tmp_path)


def test_migration_cli_exits_nonzero_when_the_plan_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def reject_plan(_database_url: str, _migrations_path: Path) -> None:
        raise MigrationPlanError("migration version gap: missing 2")

    monkeypatch.setattr(migrate, "run_migrations", reject_plan)

    with pytest.raises(SystemExit) as raised:
        migrate.main()

    assert raised.value.code == 1
    assert "migration version gap" in capsys.readouterr().err


@pytest.mark.asyncio
@pytest.mark.integration
async def test_backfill_grounds_every_passage_an_update_wrote(
    database_url: str,
) -> None:
    """The repair in 014, on data shaped the way the old derivation left it.

    Running the migrations proves only that the statement parses. This proves
    it does the thing: a revision that carried one anchor for a skeleton of
    sections ends up carrying one per section, on the bundle it already cited.
    """
    await run_migrations(database_url, MIGRATIONS)
    async with await psycopg.AsyncConnection.connect(database_url) as conn:
        ids = {
            name: uuid4()
            for name in (
                "user",
                "workspace",
                "document",
                "session",
                "branch",
                "bundle",
                "first",
                "second",
            )
        }
        await conn.execute(
            "INSERT INTO sot.sot_user(id,email,display_name) VALUES (%s,'a@test','A')",
            (ids["user"],),
        )
        await conn.execute(
            "INSERT INTO sot.sot_workspace(id,name) VALUES (%s,'W')",
            (ids["workspace"],),
        )
        await conn.execute(
            "INSERT INTO sot.sot_document(id,workspace_id,created_by,title,version) "
            "VALUES (%s,%s,%s,'D',2)",
            (ids["document"], ids["workspace"], ids["user"]),
        )
        await conn.execute(
            "INSERT INTO sot.sot_session(id,workspace_id,document_id,created_by,created_at,status) "
            "VALUES (%s,%s,%s,%s,now(),'open')",
            (ids["session"], ids["workspace"], ids["document"], ids["user"]),
        )
        await conn.execute(
            "INSERT INTO sot.sot_branch(id,workspace_id,session_id,created_by,created_at,version) "
            "VALUES (%s,%s,%s,%s,now(),1)",
            (ids["branch"], ids["workspace"], ids["session"], ids["user"]),
        )
        await conn.execute(
            "INSERT INTO sot.sot_bundle"
            "(id,workspace_id,session_id,branch_id,title,published_by,published_at) "
            "VALUES (%s,%s,%s,%s,'B',%s,now())",
            (
                ids["bundle"],
                ids["workspace"],
                ids["session"],
                ids["branch"],
                ids["user"],
            ),
        )
        await conn.execute(
            "INSERT INTO sot.sot_bundle_item"
            "(workspace_id,bundle_id,position,source_ids,role,content,provenance) "
            "VALUES (%s,%s,0,%s,'user','왜?','copied')",
            (ids["workspace"], ids["bundle"], [uuid4()]),
        )
        # Revision one: the document before the update.
        await conn.execute(
            "INSERT INTO sot.sot_document_revision"
            "(id,workspace_id,document_id,number,content,created_by,created_at) "
            "VALUES (%s,%s,%s,1,'머리말',%s,now())",
            (ids["first"], ids["workspace"], ids["document"], ids["user"]),
        )
        # Revision two: one update wrote three sections, and the old
        # derivation anchored only the first of them.
        await conn.execute(
            "INSERT INTO sot.sot_document_revision"
            "(id,workspace_id,document_id,number,content,created_by,created_at) "
            "VALUES (%s,%s,%s,2,%s,%s,now())",
            (
                ids["second"],
                ids["workspace"],
                ids["document"],
                (
                    "머리말\n\n## 문제 정의\n샌다.\n\n## 전달 방식\n헤더로.\n\n"
                    "## 미결정 사항\n(추가)"
                ),
                ids["user"],
            ),
        )
        await conn.execute(
            "INSERT INTO sot.sot_revision_citation"
            "(workspace_id,revision_id,position,claim_anchor,bundle_id,bundle_item_position) "
            "VALUES (%s,%s,0,'## 문제 정의',%s,0)",
            (ids["workspace"], ids["second"], ids["bundle"]),
        )

        await conn.execute(
            (MIGRATIONS / "014_backfill_passage_grounds.sql").read_text()
        )

        anchors = await (
            await conn.execute(
                "SELECT claim_anchor FROM sot.sot_revision_citation "
                "WHERE revision_id=%s ORDER BY position",
                (ids["second"],),
            )
        ).fetchall()
        assert [row[0] for row in anchors] == [
            "## 문제 정의",
            "## 전달 방식",
            "## 미결정 사항",
        ]
        # The heading revision one already had is not this update's to claim,
        # and revision one carried no grounds, so it gains none.
        assert await (
            await conn.execute(
                "SELECT count(*) FROM sot.sot_revision_citation WHERE revision_id=%s",
                (ids["first"],),
            )
        ).fetchone() == (0,)
        # Applying the repair twice adds nothing: anchors are matched, not
        # appended blindly.
        await conn.execute(
            (MIGRATIONS / "014_backfill_passage_grounds.sql").read_text()
        )
        assert await (
            await conn.execute(
                "SELECT count(*) FROM sot.sot_revision_citation WHERE revision_id=%s",
                (ids["second"],),
            )
        ).fetchone() == (3,)
