import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tests.postgres import disposable_database


@pytest.mark.asyncio
@pytest.mark.integration
async def test_test_databases_are_unique_isolated_and_removed_even_after_failure() -> (
    None
):
    with pytest.raises(RuntimeError, match="test failure"):
        async with (
            disposable_database() as first_url,
            disposable_database() as second_url,
        ):
            first_name = conninfo_to_dict(first_url)["dbname"]
            second_name = conninfo_to_dict(second_url)["dbname"]
            assert isinstance(first_name, str) and isinstance(second_name, str)
            assert first_name != second_name
            assert first_name.startswith("sot_test_")
            assert second_name.startswith("sot_test_")
            async with await psycopg.AsyncConnection.connect(first_url) as first:
                await first.execute("CREATE TABLE marker (id integer)")
            async with await psycopg.AsyncConnection.connect(second_url) as second:
                row = await (
                    await second.execute("SELECT to_regclass('public.marker')")
                ).fetchone()
                assert row == (None,)
            raise RuntimeError("test failure")
    admin_url = make_conninfo(first_url, dbname="postgres")
    async with await psycopg.AsyncConnection.connect(admin_url) as connection:
        rows = await (
            await connection.execute(
                "SELECT datname FROM pg_database WHERE datname = ANY(%s)",
                ([first_name, second_name],),
            )
        ).fetchall()
        assert rows == []
