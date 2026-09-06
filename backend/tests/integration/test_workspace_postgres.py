from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import jwt
import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr

from sot.bootstrap.app import build_app
from sot.bootstrap.database import PostgresUnitOfWork
from sot.bootstrap.migrate import run_migrations
from sot.bootstrap.settings import Settings
from sot.identity.contracts import Actor
from sot.identity.domain import VerifiedIdentity
from sot.identity.postgres import PostgresIdentityRepository
from sot.shared.ids import UserId, WorkspaceId
from sot.workspace.application import CreateWorkspace, WorkspaceAccess
from sot.workspace.domain import (
    Workspace,
    WorkspaceForbidden,
    WorkspaceMemberAlreadyExists,
    WorkspaceMembership,
    WorkspaceRole,
)
from sot.workspace.postgres import PostgresWorkspaceRepository

DATABASE_URL = "postgresql://sot:sot@localhost:54329/sot"


class StaticGoogleVerifier:
    async def verify(self, credential: str, audience: str) -> Mapping[str, object]:
        return {
            "iss": "https://accounts.google.com",
            "aud": audience,
            "sub": credential,
            "email": credential + "@example.com",
            "email_verified": True,
        }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workspace_postgres_scoping_constraints_and_atomic_rollback() -> None:
    await run_migrations(DATABASE_URL, Path(__file__).parents[2] / "migrations")
    async with AsyncConnectionPool[Any](DATABASE_URL, open=False) as pool:
        identity, repository = (
            PostgresIdentityRepository(),
            PostgresWorkspaceRepository(),
        )
        uow = lambda: PostgresUnitOfWork(pool)
        async with uow().transaction() as tx:
            owner = await identity.upsert_identity(
                tx, VerifiedIdentity("workspace-test", str(uuid4()), "owner", "Owner")
            )
            other = await identity.upsert_identity(
                tx, VerifiedIdentity("workspace-test", str(uuid4()), "other", "Other")
            )
        first = await CreateWorkspace(repository, uow).execute(
            Actor(owner.id), name="First"
        )
        second = await CreateWorkspace(repository, uow).execute(
            Actor(other.id), name="Second"
        )
        access = WorkspaceAccess(repository)
        async with uow().transaction() as tx:
            assert await repository.list_for_user(tx, owner.id) == (first,)
            assert await repository.get(tx, second.id) == second
            assert await repository.get(tx, WorkspaceId(uuid4())) is None
            assert await repository.get_member(tx, second.id, owner.id) is None
            assert (
                await access.require_member(tx, first.id, owner.id)
            ).role is WorkspaceRole.OWNER
            with pytest.raises(WorkspaceForbidden):
                await access.require_member(tx, second.id, owner.id)
        with pytest.raises(WorkspaceMemberAlreadyExists):
            async with uow().transaction() as tx:
                await repository.add_member(
                    tx, WorkspaceMembership(first.id, owner.id, WorkspaceRole.VIEWER)
                )
        async with uow().transaction() as tx:
            assert (
                await access.require_member(tx, first.id, owner.id)
            ).role is WorkspaceRole.OWNER
        rollback_id = WorkspaceId(uuid4())
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            async with uow().transaction() as tx:
                await repository.create(tx, Workspace(rollback_id, "Rollback"))
                await repository.add_member(
                    tx,
                    WorkspaceMembership(
                        rollback_id, UserId(uuid4()), WorkspaceRole.OWNER
                    ),
                )
        async with uow().transaction() as tx:
            assert await repository.get(tx, rollback_id) is None
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as connection:
            with pytest.raises(psycopg.errors.CheckViolation):
                await connection.execute(
                    "INSERT INTO sot.sot_workspace_member(workspace_id,user_id,role) VALUES (%s,%s,'admin')",
                    (first.id, other.id),
                )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_composed_google_auth_workspace_rbac_and_tenant_isolation() -> None:
    await run_migrations(DATABASE_URL, Path(__file__).parents[2] / "migrations")
    app = build_app(
        Settings(
            environment="test",
            database_url=DATABASE_URL,
            google_client_id="test-client",
            access_token_secret=SecretStr("s" * 32),
        ),
        google_token_verifier=StaticGoogleVerifier(),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client,
    ):
        owner = (
            await client.post("/api/v1/auth/google", json={"credential": str(uuid4())})
        ).json()
        outsider = (
            await client.post("/api/v1/auth/google", json={"credential": str(uuid4())})
        ).json()
        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
        other_headers = {"Authorization": f"Bearer {outsider['access_token']}"}
        created = await client.post(
            "/api/v1/workspaces", json={"name": "Workspace"}, headers=owner_headers
        )
        assert created.status_code == 201
        workspace_id = created.json()["id"]
        # Even a validly signed extra tenant/role claim cannot grant membership.
        claims = jwt.decode(
            outsider["access_token"], "s" * 32, algorithms=["HS256"], issuer="sot"
        )
        claimed = jwt.encode(
            {**claims, "workspace_id": workspace_id, "role": "owner"},
            "s" * 32,
            algorithm="HS256",
        )
        assert (
            await client.get(
                f"/api/v1/workspaces/{workspace_id}",
                headers={"Authorization": f"Bearer {claimed}"},
            )
        ).status_code == 403
        assert (
            await client.get("/api/v1/workspaces", headers=other_headers)
        ).json() == []
        assert (
            await client.get(
                f"/api/v1/workspaces/{workspace_id}", headers=other_headers
            )
        ).status_code == 403
        body = {"user_id": outsider["user"]["id"], "role": "viewer"}
        assert (
            await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                json=body,
                headers=other_headers,
            )
        ).status_code == 403
        assert (
            await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                json=body,
                headers=owner_headers,
            )
        ).status_code == 201
        assert (
            await client.get(
                f"/api/v1/workspaces/{workspace_id}", headers=other_headers
            )
        ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                json={"user_id": owner["user"]["id"], "role": "owner"},
                headers=other_headers,
            )
        ).status_code == 403
