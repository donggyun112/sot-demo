from __future__ import annotations

from pathlib import Path

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
    assert await applied_versions(database_url) == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

    app = build_app(Settings(database_url=database_url, models=("test",)))
    async with app.router.lifespan_context(app):
        assert await applied_versions(database_url) == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)


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
