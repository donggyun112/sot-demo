import uuid

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from service_auth import (
    AuthenticationError,
    CredentialMissing,
    InvalidToken,
    KeySourceUnavailable,
)
from starlette.responses import JSONResponse
from starlette.routing import Route

from agent_core.api import create_app
from agent_core.auth import AgentAuthorizationError
from agent_core.auth.http import (
    AgentResourceHidden,
    auth_error_response,
    extract_bearer,
)


@pytest.fixture
def test_app() -> FastAPI:
    application = FastAPI()

    @application.exception_handler(AuthenticationError)
    async def handle_authentication(
        _request: Request,
        error: AuthenticationError,
    ) -> JSONResponse:
        assert isinstance(
            error, (CredentialMissing, InvalidToken, KeySourceUnavailable)
        )
        return auth_error_response(error)

    @application.exception_handler(AgentAuthorizationError)
    async def handle_authorization(
        _request: Request,
        error: AgentAuthorizationError,
    ) -> JSONResponse:
        return auth_error_response(error)

    @application.exception_handler(AgentResourceHidden)
    async def handle_hidden(
        _request: Request,
        error: AgentResourceHidden,
    ) -> JSONResponse:
        return auth_error_response(error)

    @application.get("/raise/{kind}")
    async def raise_error(kind: str) -> None:
        errors: dict[str, Exception] = {
            "credential-missing": CredentialMissing(),
            "invalid-token": InvalidToken("signature_invalid"),
            "keys-unavailable": KeySourceUnavailable(),
            "client-forbidden": AgentAuthorizationError("client_forbidden"),
            "scope-run": AgentAuthorizationError("scope_missing", "agent:run"),
            "scope-abort": AgentAuthorizationError("scope_missing", "agent:abort"),
            "hidden-missing": AgentResourceHidden("missing"),
            "hidden-owner": AgentResourceHidden("owner_mismatch"),
        }
        raise errors[kind]

    return application


def test_extracts_case_insensitive_single_bearer() -> None:
    assert extract_bearer("bearer ey.example.token") == "ey.example.token"
    assert extract_bearer("  BEARER ey.example.token  ") == "ey.example.token"


@pytest.mark.parametrize(
    "value",
    [None, "", "Basic abc", "Bearer", "Bearer a b", "Bearer a,b"],
)
def test_rejects_missing_or_ambiguous_credentials(value: str | None) -> None:
    with pytest.raises(CredentialMissing):
        extract_bearer(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["credential-missing", "invalid-token"])
async def test_invalid_token_has_fixed_401_contract(
    kind: str, test_app: FastAPI
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/raise/{kind}")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    assert response.json() == {
        "error": {"code": "invalid_token", "message": "Authentication failed"}
    }


@pytest.mark.asyncio
async def test_disallowed_client_has_fixed_403_contract(test_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/raise/client-forbidden")

    assert response.status_code == 403
    assert "www-authenticate" not in response.headers
    assert response.json() == {
        "error": {"code": "forbidden", "message": "Caller is not allowed"}
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["agent:run", "agent:abort"])
async def test_missing_scope_has_fixed_403_challenge(
    scope: str, test_app: FastAPI
) -> None:
    kind = "scope-run" if scope == "agent:run" else "scope-abort"
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/raise/{kind}")

    assert response.status_code == 403
    assert response.headers["www-authenticate"] == (
        f'Bearer error="insufficient_scope", scope="{scope}"'
    )
    assert response.json() == {
        "error": {
            "code": "insufficient_scope",
            "message": "Required scope is missing",
        }
    }


@pytest.mark.asyncio
async def test_missing_and_owner_mismatch_are_identical_hidden_responses(
    test_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        missing = await client.get("/raise/hidden-missing")
        mismatch = await client.get("/raise/hidden-owner")

    assert missing.status_code == mismatch.status_code == 404
    assert (
        missing.json()
        == mismatch.json()
        == {"error": {"code": "run_not_found", "message": "Run not found"}}
    )
    assert missing.headers.get("www-authenticate") is None
    assert mismatch.headers.get("www-authenticate") is None


@pytest.mark.asyncio
async def test_unavailable_keys_have_fixed_503_retry_contract(
    test_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/raise/keys-unavailable")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert "www-authenticate" not in response.headers
    assert response.json() == {
        "error": {
            "code": "auth_keys_unavailable",
            "message": "Authentication keys are temporarily unavailable",
        }
    }


@pytest.mark.asyncio
async def test_unconfigured_app_exposes_contract_but_rejects_execution() -> None:
    application = create_app()
    paths = {route.path for route in application.routes if isinstance(route, Route)}
    assert paths == {
        "/docs",
        "/docs/oauth2-redirect",
        "/healthz",
        "/openapi.json",
        "/redoc",
        "/ag-ui",
        "/runs/{run_id}/abort",
    }

    run_id = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        ag_ui = await client.post("/ag-ui", json={})
        abort = await client.post(f"/runs/{run_id}/abort")

    assert ag_ui.status_code == 503
    assert abort.status_code == 503
