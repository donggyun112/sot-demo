"""Disposable PostgreSQL databases for integration tests."""

import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo


def require_disposable_database_name(name: str) -> str:
    if not re.fullmatch(r"sot_test_[0-9a-f]{32}", name):
        raise ValueError("Refusing a non-disposable database target")
    return name


@asynccontextmanager
async def disposable_database() -> AsyncIterator[str]:
    # The setting supplies server credentials only. Neither an application URL nor
    # its database name can become the CREATE/DROP target.
    admin_url = make_conninfo(
        os.environ.get(
            "SOT_TEST_POSTGRES_ADMIN_URL",
            "postgresql://sot:sot@localhost:54329/postgres",
        ),
        dbname="postgres",
    )
    name = require_disposable_database_name("sot_test_" + uuid4().hex)
    async with await psycopg.AsyncConnection.connect(
        admin_url, autocommit=True
    ) as admin:
        # No IF NOT EXISTS: never adopt or later delete a pre-existing database.
        await admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                sql.Identifier(name)
            )
        )
        try:
            yield make_conninfo(admin_url, dbname=name)
        finally:
            target = require_disposable_database_name(name)
            await admin.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(target))
            )
