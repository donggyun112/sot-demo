import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.auth.exceptions import DefaultCredentialsError
from httpx import ASGITransport, AsyncClient
from pydantic_ai import Agent, DeferredToolRequests, UserError
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel

from agent_core.agent import AgentRunDeps, AgentSettings, build_deployment_agent
from agent_core.api import create_app
from agent_core.bootstrap import (
    _compose_model_chain,
    _runtime_lifespan,
    create_environment_app,
)
from agent_core.tools import ToolRegistry


@pytest.fixture
def configured_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "AGENT_NAME": "test-agent",
        "AGENT_DESCRIPTION": "Test deployment",
        "AGENT_SYSTEM_PROMPT_FILE": str(Path(__file__).parents[1] / "README.md"),
        "AGENT_PROMPT_REVISION": "test-v1",
        "AGENT_MODELS": '["google-cloud:gemini-2.5-flash"]',
        "AGENT_AUTH_ISSUER": "https://issuer.test",
        "AGENT_AUTH_AUDIENCE": "agent",
        "AGENT_AUTH_JWKS_URI": "https://issuer.test/jwks",
        "AGENT_AUTH_ALLOWED_ALGORITHMS": '["RS256"]',
        "AGENT_AUTH_ALLOWED_CLIENT_IDS": '["test-client"]',
        "AGENT_DATABASE_URL": "postgresql://test:test@localhost/test",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


@pytest.mark.asyncio
@pytest.mark.usefixtures("configured_environment")
async def test_google_cloud_missing_adc_returns_redacted_unconfigured_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(name, raising=False)

    def missing_adc(*args: Any, **kwargs: Any) -> Any:
        raise DefaultCredentialsError(  # type: ignore[no-untyped-call]
            "private ADC path /secrets/provider.json"
        )

    monkeypatch.setattr("google.auth.default", missing_adc)
    application = create_environment_app()
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://agent.test",
    ) as client:
        response = await client.post("/ag-ui", json={})

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "service_unavailable", "message": "Agent is not configured"}
    }
    assert "private ADC" not in response.text


@pytest.mark.parametrize("failure", [asyncio.CancelledError(), SystemExit()])
@pytest.mark.usefixtures("configured_environment")
def test_model_composition_preserves_base_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    def fail(_refs: tuple[str, ...]) -> Model:
        raise failure

    monkeypatch.setattr("agent_core.bootstrap._compose_model_chain", fail)
    with pytest.raises(type(failure)) as caught:
        create_environment_app()
    assert caught.value is failure


@pytest.mark.asyncio
@pytest.mark.usefixtures("configured_environment")
async def test_environment_app_injects_composed_model_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = TestModel()
    composed: list[tuple[str, ...]] = []
    injected: list[Model] = []
    semora_wiring: list[tuple[object, object, float]] = []

    def compose(refs: tuple[str, ...]) -> Model:
        composed.append(refs)
        return sentinel

    def build(
        *,
        settings: AgentSettings,
        registry: ToolRegistry,
        model: Model,
    ) -> Agent[AgentRunDeps, str | DeferredToolRequests]:
        injected.append(model)
        return build_deployment_agent(settings=settings, registry=registry, model=model)

    def pool(*args: Any, **kwargs: Any) -> object:
        assert kwargs["open"] is False
        return object()

    def semora_engine(
        steps: object,
        *,
        transcript: object,
        lease_ttl: float,
    ) -> object:
        semora_wiring.append((steps, transcript, lease_ttl))
        return object()

    monkeypatch.setattr("agent_core.bootstrap._compose_model_chain", compose)
    monkeypatch.setattr("agent_core.bootstrap.build_deployment_agent", build)
    monkeypatch.setattr("agent_core.bootstrap.AsyncConnectionPool", pool)
    monkeypatch.setattr(
        "agent_core.bootstrap.PostgresSteps", lambda value: ("steps", value)
    )
    monkeypatch.setattr(
        "agent_core.bootstrap.PostgresTranscript",
        lambda value: ("transcript", value),
    )
    monkeypatch.setattr("agent_core.bootstrap.SemoraRuntimeEngine", semora_engine)
    monkeypatch.setattr("agent_core.bootstrap.HttpxJwksFetcher", lambda _uri: object())

    application = create_environment_app()
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://agent.test",
    ) as client:
        response = await client.post("/ag-ui", json={})

    assert response.status_code == 401
    assert composed == [("google-cloud:gemini-2.5-flash",)]
    assert len(injected) == 1
    assert injected[0] is sentinel
    assert len(semora_wiring) == 1
    steps, transcript, lease_ttl = semora_wiring[0]
    assert steps[0] == "steps"  # type: ignore[index]
    assert transcript[0] == "transcript"  # type: ignore[index]
    assert lease_ttl == 60.0


def _request(method: str, path: str, json: object | None = None) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport, base_url="http://agent.test"
        ) as client:
            return await client.request(method, path, json=json)

    return asyncio.run(send())


def test_health_reports_agent_service_ready() -> None:
    response = _request("GET", "/healthz")

    assert response.status_code == 200
    assert response.json() == {"service": "agent-server", "status": "ready"}


def test_legacy_agent_route_is_not_exposed() -> None:
    response = _request("POST", "/agent", json={})

    assert response.status_code == 404


def test_composes_primary_and_fallbacks_in_declared_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []
    sentinel: Model = TestModel()

    def recording(primary: str, *fallbacks: str) -> Model:
        calls.append((primary, fallbacks))
        return sentinel

    monkeypatch.setattr("agent_core.bootstrap.FallbackModel", recording)
    result = _compose_model_chain(
        (
            "openrouter:openai/gpt-5.2",
            "openai:gpt-5-mini",
            "anthropic:claude-sonnet-4-0",
        )
    )

    assert result is sentinel
    assert calls == [
        (
            "openrouter:openai/gpt-5.2",
            ("openai:gpt-5-mini", "anthropic:claude-sonnet-4-0"),
        )
    ]


@pytest.mark.asyncio
async def test_model_configuration_failure_returns_unconfigured_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agent_core.bootstrap.AgentSettings",
        lambda: SimpleNamespace(models=("openai:gpt-5-mini",)),
    )
    monkeypatch.setattr("agent_core.bootstrap.AgentAuthSettings", lambda: object())
    monkeypatch.setattr("agent_core.bootstrap.AgentDatabaseSettings", lambda: object())
    monkeypatch.setattr("agent_core.bootstrap.ExecutionSettings", lambda: object())

    def fail(_model_refs: tuple[str, ...]) -> Model:
        raise UserError("missing credential")

    monkeypatch.setattr("agent_core.bootstrap._compose_model_chain", fail)
    application = create_environment_app()
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://agent.test",
    ) as client:
        response = await client.post("/ag-ui", json={})

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Agent is not configured",
        }
    }


@pytest.mark.asyncio
async def test_runtime_lifespan_orders_startup_and_shutdown() -> None:
    order: list[str] = []

    class Pool:
        async def open(self) -> None:
            order.append("pool.open")

        async def wait(self) -> None:
            order.append("pool.wait")

        async def close(self) -> None:
            order.append("pool.close")

    class Keys:
        async def start(self) -> None:
            order.append("keys.start")

        async def close(self) -> None:
            order.append("keys.close")

    class Service:
        async def shutdown(self, *, timeout: float) -> None:
            assert timeout == 17.0
            order.append("service.shutdown")

    async with _runtime_lifespan(
        pool=Pool(),
        keys=Keys(),
        service=Service(),
        shutdown_timeout=17.0,
    ):
        assert order == [
            "pool.open",
            "pool.wait",
            "keys.start",
        ]

    assert order == [
        "pool.open",
        "pool.wait",
        "keys.start",
        "service.shutdown",
        "keys.close",
        "pool.close",
    ]
