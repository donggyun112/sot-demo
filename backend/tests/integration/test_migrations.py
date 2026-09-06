from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from sot.bootstrap import migrate
from sot.bootstrap.app import build_app
from sot.bootstrap.migrate import MigrationPlanError, run_migrations
from sot.bootstrap.settings import Settings

DATABASE_URL = "postgresql://sot:sot@localhost:54329/sot"
MIGRATIONS = Path(__file__).parents[2] / "migrations"


async def reset_sot_schema(database_url: str) -> None:
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute("DROP SCHEMA IF EXISTS sot CASCADE")


async def applied_versions(database_url: str) -> tuple[int, ...]:
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        cursor = await connection.execute(
            "SELECT version FROM sot.schema_migration ORDER BY version"
        )
        rows = await cursor.fetchall()
    return tuple(row[0] for row in rows)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_migrations_are_ordered_once_and_not_run_by_app_startup() -> None:
    await reset_sot_schema(DATABASE_URL)
    await run_migrations(DATABASE_URL, MIGRATIONS)
    await run_migrations(DATABASE_URL, MIGRATIONS)
    assert await applied_versions(DATABASE_URL) == (1, 2)

    app = build_app(Settings(database_url=DATABASE_URL, models=("test",)))
    async with app.router.lifespan_context(app):
        assert await applied_versions(DATABASE_URL) == (1, 2)


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
