from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from sot.bootstrap.errors import register_error_handlers
from sot.bootstrap.settings import Settings
from sot.identity.api import build_auth_router
from tests.identity.test_auth_facade import make_facade


def make_app(settings: Settings | None = None) -> FastAPI:
    facade, _, _, _ = make_facade()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        build_auth_router(facade, settings or Settings(environment="test"))
    )
    return app


@pytest.mark.asyncio
async def test_login_cookie_me_rotation_and_logout_contract() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="https://test"
    ) as client:
        login = await client.post(
            "/api/v1/auth/google", json={"credential": "alice@example.com"}
        )
        assert login.status_code == 200
        assert "refresh_token" not in login.json()
        cookie = login.headers["set-cookie"]
        for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/api/v1/auth"):
            assert attribute in cookie
        access = login.json()["access_token"]
        me = await client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {access}"}
        )
        assert me.status_code == 200
        assert me.json()["email"] == "alice@example.com"
        assert (await client.post("/api/v1/auth/refresh")).status_code == 200
        assert (await client.post("/api/v1/auth/logout")).status_code == 204
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401


@pytest.mark.asyncio
async def test_bearer_required_and_logout_all_revokes_refresh() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="https://test"
    ) as client:
        assert (
            await client.get("/api/v1/me", headers={"X-SOT-User": "alice"})
        ).status_code == 401
        login = await client.post("/api/v1/auth/google", json={"credential": "alice"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        refresh = client.cookies.get("sot_refresh")
        assert (
            await client.post("/api/v1/auth/logout-all", headers=headers)
        ).status_code == 204
        assert (
            await client.post(
                "/api/v1/auth/refresh", headers={"Cookie": f"sot_refresh={refresh}"}
            )
        ).status_code == 401
        assert (
            await client.get("/api/v1/me", headers={"Authorization": "Bearer bad"})
        ).status_code == 401


def test_production_rejects_development_auth() -> None:
    with pytest.raises(ValidationError, match="development"):
        Settings(environment="production", development_auth=True)


def test_deployment_jwt_secret_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOT_JWT_SECRET", "deployment-test-value" * 3)
    assert (
        Settings().access_token_secret.get_secret_value() == "deployment-test-value" * 3
    )


@pytest.mark.asyncio
async def test_development_header_requires_explicit_opt_in_and_existing_user() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=make_app(Settings(environment="test", development_auth=True))
        ),
        base_url="https://test",
    ) as client:
        login = await client.post("/api/v1/auth/google", json={"credential": "alice"})
        user_id = login.json()["user"]["id"]
        assert (
            await client.get("/api/v1/me", headers={"X-SOT-User": user_id})
        ).status_code == 200
        for user in ("bad", "00000000-0000-0000-0000-000000000000"):
            assert (
                await client.get("/api/v1/me", headers={"X-SOT-User": user})
            ).status_code == 401


@pytest.mark.asyncio
async def test_production_never_resolves_development_header() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app(Settings(environment="production"))),
        base_url="https://test",
    ) as client:
        login = await client.post("/api/v1/auth/google", json={"credential": "alice"})
        user_id = login.json()["user"]["id"]
        assert (
            await client.get("/api/v1/me", headers={"X-SOT-User": user_id})
        ).status_code == 401
