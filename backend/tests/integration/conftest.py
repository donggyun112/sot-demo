from collections.abc import AsyncIterator

import pytest_asyncio

from tests.postgres import disposable_database


@pytest_asyncio.fixture
async def database_url() -> AsyncIterator[str]:
    async with disposable_database() as url:
        yield url
