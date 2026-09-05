from pathlib import Path

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from psycopg_pool import AsyncConnectionPool

from sot.domain.models import NewTurn
from sot.domain.service import SOTService
from sot.main import build_app
from sot.settings import Settings
from sot.store.postgres import PostgresSOTRepository, apply_migrations

DATABASE_URL = "postgresql://sot:sot@localhost:54329/sot"
MIGRATIONS = Path(__file__).parents[2] / "migrations"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_published_revision_survives_repository_reconnect() -> None:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as connection:
        await connection.execute("DROP SCHEMA IF EXISTS sot CASCADE")

    first_pool = AsyncConnectionPool(DATABASE_URL, open=False)
    await first_pool.open()
    await apply_migrations(first_pool, MIGRATIONS)
    service = SOTService(PostgresSOTRepository(first_pool))

    document = await service.create_document(
        actor_id="alice", title="요청 제한 토큰", content="초기 합의"
    )
    session = await service.create_session(
        document_id=document.id, owner_id="alice", title="레이트리밋 검토"
    )
    turns = await service.append_turns(
        branch_id=session.branch.id,
        actor_id="alice",
        turns=(
            NewTurn(role="assistant", content="격리 수준은 A와 B가 있습니다."),
            NewTurn(role="user", content="B"),
        ),
    )
    cite = await service.create_cite(
        branch_id=session.branch.id,
        actor_id="alice",
        turn_ids=tuple(turn.id for turn in turns),
        summary="프로세스 격리를 선택함",
    )
    toss = await service.create_toss(cite_id=cite.id, actor_id="alice")
    bob_branch = await service.fork_toss(token=toss.token, actor_id="bob")
    proposal = await service.create_proposal(
        branch_id=bob_branch.id,
        actor_id="bob",
        content="각 사용자 작업은 별도 프로세스로 격리한다.",
    )
    await service.approve_proposal(proposal_id=proposal.id, actor_id="bob")
    published = await service.approve_proposal(
        proposal_id=proposal.id, actor_id="alice"
    )
    assert published.revision is not None
    await first_pool.close()

    second_pool = AsyncConnectionPool(DATABASE_URL, open=False)
    await second_pool.open()
    reconnected = SOTService(PostgresSOTRepository(second_pool))
    revision = await reconnected.current_revision(document.id)

    assert revision.number == 2
    assert revision.content == "각 사용자 작업은 별도 프로세스로 격리한다."
    assert (await reconnected.toss_view(token=toss.token)).cite.id == cite.id
    await second_pool.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_application_lifespan_migrates_seeds_and_closes_pool() -> None:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as connection:
        await connection.execute("DROP SCHEMA IF EXISTS sot CASCADE")

    app = build_app(Settings(database_url=DATABASE_URL, models=("test",)))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://sot.test"
        ) as client:
            response = await client.get("/api/v1/bootstrap")

        assert response.status_code == 200
        assert response.json()["documents"][0]["title"] == "요청 제한 토큰"
        assert not app.state.pool.closed

    assert app.state.pool.closed
