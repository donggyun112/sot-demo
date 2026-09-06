from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import AsyncConnection

from sot.bootstrap.settings import Settings

MIGRATIONS_PATH = Path(__file__).resolve().parents[3] / "migrations"
_MIGRATION_FILENAME = re.compile(r"^(?P<version>\d+)(?:[_-].*)?\.sql$")
_MIGRATION_LOCK = "sot-schema-migration"


class MigrationPlanError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _Migration:
    version: int
    path: Path

    @property
    def filename(self) -> str:
        return self.path.name


def _migration_plan(migrations_path: Path) -> tuple[_Migration, ...]:
    files = sorted(migrations_path.glob("*.sql"))
    if not files:
        raise MigrationPlanError(f"no migrations found in {migrations_path}")

    migrations: list[_Migration] = []
    for path in files:
        match = _MIGRATION_FILENAME.fullmatch(path.name)
        if match is None:
            raise MigrationPlanError(
                f"migration filename must start with a numeric version: {path.name}"
            )
        migrations.append(_Migration(int(match.group("version")), path))

    versions = [migration.version for migration in migrations]
    duplicates = sorted(
        version for version in set(versions) if versions.count(version) > 1
    )
    if duplicates:
        rendered = ", ".join(str(version) for version in duplicates)
        raise MigrationPlanError(f"duplicate migration version: {rendered}")

    migrations.sort(key=lambda migration: migration.version)
    expected = list(range(1, migrations[-1].version + 1))
    ordered_versions = [migration.version for migration in migrations]
    if ordered_versions != expected:
        missing = sorted(set(expected) - set(ordered_versions))
        rendered = ", ".join(str(version) for version in missing)
        raise MigrationPlanError(f"migration version gap: missing {rendered}")

    return tuple(migrations)


async def _create_ledger(connection: AsyncConnection[object]) -> None:
    async with connection.transaction():
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))", (_MIGRATION_LOCK,)
        )
        await connection.execute("CREATE SCHEMA IF NOT EXISTS sot")
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sot.schema_migration (
                version INTEGER PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


async def _apply_migration(
    connection: AsyncConnection[object], migration: _Migration
) -> None:
    async with connection.transaction():
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))", (_MIGRATION_LOCK,)
        )
        cursor = await connection.execute(
            "SELECT 1 FROM sot.schema_migration WHERE version = %s",
            (migration.version,),
        )
        if await cursor.fetchone() is not None:
            return

        await connection.execute(migration.path.read_text(encoding="utf-8"))
        await connection.execute(
            """
            INSERT INTO sot.schema_migration (version, filename)
            VALUES (%s, %s)
            """,
            (migration.version, migration.filename),
        )


async def run_migrations(database_url: str, migrations_path: Path) -> None:
    migrations = _migration_plan(migrations_path)
    connection = await psycopg.AsyncConnection.connect(database_url)
    try:
        await _create_ledger(connection)
        for migration in migrations:
            await _apply_migration(connection, migration)
    finally:
        await connection.close()


def main() -> None:
    settings = Settings()
    try:
        asyncio.run(run_migrations(settings.database_url, MIGRATIONS_PATH))
    except Exception as error:
        print(f"migration failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()


__all__ = ["MIGRATIONS_PATH", "MigrationPlanError", "main", "run_migrations"]
