# Native Pydantic AI Multi-Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the OpenRouter-specific agent construction with an ordered, provider-neutral model chain implemented by Pydantic AI's native `FallbackModel`.

**Architecture:** `AgentSettings` parses ordered provider-qualified model references from `AGENT_MODELS`. Bootstrap constructs one native `FallbackModel(primary, *fallbacks)` and injects it into `build_deployment_agent`; Agent Core, runtime, supervisor, service, and PostgreSQL never construct or inspect concrete providers. Pydantic AI retains provider inference and its default `ModelAPIError` fallback boundary.

**Tech Stack:** Python 3.12+, Pydantic AI 2.38.0, Pydantic Settings 2.x, AG-UI 0.1.x, FastAPI, PostgreSQL, pytest, mypy, Ruff, uv.

**Spec:** `docs/superpowers/specs/2026-09-04-provider-neutral-model-boundary-design.md`

## Global Constraints

- Use `AGENT_MODELS` as a JSON array of ordered, provider-qualified model references.
- Require at least one non-empty reference; reject unqualified and duplicate references.
- Use `pydantic_ai.models.fallback.FallbackModel` directly; do not add a resolver, registry, routing service, or custom fallback policy.
- `FallbackModel` keeps its default `ModelAPIError` fallback condition.
- `agent_core.agent` receives a ready `Model` and imports no concrete provider/model class.
- Provider credentials remain in provider-native environment variables and never enter settings models, AG-UI, PostgreSQL, or public errors.
- Package exactly `pydantic-ai-slim[ag-ui,anthropic,google,openai,openrouter]==2.38.0`.
- Preserve the single-instance local async supervisor, terminal-closed PostgreSQL journal, API routes, request identity rules, abort behavior, and crash terminalization.
- The workspace has no Git metadata. Do not claim commits; record task checkpoints in `.superpowers/sdd/2026-09-05-native-pydantic-ai-multi-model/progress.md` during execution.

## File Structure

- `agent-server/src/agent_core/agent.py`: provider-neutral settings validation, run dependency assembly, and deployment-agent construction from an injected `Model`.
- `agent-server/src/agent_core/bootstrap.py`: native `FallbackModel` composition and application graph wiring.
- `agent-server/src/agent_core/service.py`: persistence of the ordered model-reference diagnostic only.
- `agent-server/tests/test_agent_assembly.py`: settings and injected-model contract.
- `agent-server/tests/test_service.py`: exact admission diagnostic contract.
- `agent-server/tests/test_model_fallback.py`: native Pydantic AI fallback behavior without network calls.
- `agent-server/tests/test_http.py`: bootstrap composition and unconfigured-app failure boundary.
- `agent-server/tests/test_pydantic_contract.py`: exact installed provider extras.
- `agent-server/tests/test_service_boundary.py`: no concrete provider imports in production source.
- `agent-server/tests/e2e/test_openrouter.py`: one-entry OpenRouter model-chain acceptance.
- `agent-server/README.md`: multi-model configuration, fallback boundary, and provider-native credentials.
- `agent-server/pyproject.toml`, `agent-server/uv.lock`: provider SDK distribution surface.

---

### Task 1: Make Agent Settings and Construction Provider-Neutral

**Files:**

- Modify: `agent-server/src/agent_core/agent.py`
- Modify: `agent-server/tests/test_agent_assembly.py`

**Interfaces:**

- Produces: `AgentSettings.models: tuple[str, ...]` populated by `AGENT_MODELS`.
- Produces: `build_deployment_agent(*, settings, registry, model: Model)`.
- Removes: `openrouter_model`, `openrouter_api_key`, `OpenRouterModel`, and `OpenRouterProvider` from Agent Core.
- Consumed by: Tasks 2–4.

- [ ] **Step 1: Replace the OpenRouter factory test with injected-model assertions**

Change the settings fixture to:

```python
def _settings(tmp_path: Path) -> AgentSettings:
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("Base prompt from deployment.", encoding="utf-8")
    return AgentSettings(
        name="discussion-agent",
        description="Helps two people find agreement.",
        system_prompt_file=prompt_file,
        prompt_revision="prompt-7",
        models=("openrouter:openai/gpt-5.2", "openai:gpt-5-mini"),
    )
```

Replace the construction test with:

```python
def test_builds_named_agent_with_injected_model(tmp_path: Path) -> None:
    model = TestModel()
    agent = build_deployment_agent(
        settings=_settings(tmp_path),
        registry=_registry(),
        model=model,
    )

    assert agent.name == "discussion-agent"
    assert agent.model is model
```

- [ ] **Step 2: Add settings validation tests**

Add this helper so environment-source tests do not accidentally supply a model value directly:

```python
def _settings_values(tmp_path: Path) -> dict[str, Any]:
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("Base prompt from deployment.", encoding="utf-8")
    return {
        "name": "discussion-agent",
        "description": "Helps two people find agreement.",
        "system_prompt_file": prompt_file,
        "prompt_revision": "prompt-7",
    }
```

Add parameterized tests that construct `AgentSettings` with invalid model tuples:

```python
@pytest.mark.parametrize(
    "models",
    [(), ("",), ("gpt-5-mini",), ("openai:",), (":gpt-5-mini",), ("openai:gpt-5-mini", "openai:gpt-5-mini")],
)
def test_agent_settings_reject_invalid_model_chains(
    tmp_path: Path,
    models: tuple[str, ...],
) -> None:
    values = _settings_values(tmp_path)
    with pytest.raises(ValidationError):
        AgentSettings(**values, models=models)
```

Add an environment parsing test using `monkeypatch` and `_env_file=None`:

```python
def test_agent_settings_parse_ordered_models_from_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _settings_values(tmp_path)
    monkeypatch.setenv(
        "AGENT_MODELS",
        '["openrouter:openai/gpt-5.2","anthropic:claude-sonnet-4-0"]',
    )
    settings = AgentSettings(**values, _env_file=None)
    assert settings.models == (
        "openrouter:openai/gpt-5.2",
        "anthropic:claude-sonnet-4-0",
    )
```

`_settings_values` must contain only name, description, system-prompt path, and prompt revision so the test proves `AGENT_MODELS` is the source of the model chain.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
cd agent-server
uv run --offline pytest tests/test_agent_assembly.py -q
```

Expected: failures because `AgentSettings` still requires OpenRouter fields and `build_deployment_agent` does not accept `model`.

- [ ] **Step 4: Implement `models` validation and model injection**

In `agent.py`, remove `SecretStr`, OpenRouter imports, and the provider-specific fields. Import `field_validator` and `Model`, then implement:

```python
class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        populate_by_name=True,
        extra="ignore",
    )

    name: str
    description: str
    system_prompt_file: Path
    prompt_revision: str
    models: tuple[str, ...]

    @field_validator("models")
    @classmethod
    def validate_models(cls, models: tuple[str, ...]) -> tuple[str, ...]:
        if not models:
            raise ValueError("at least one model is required")
        if len(models) != len(set(models)):
            raise ValueError("model references must be unique")
        for model_ref in models:
            provider, separator, model_name = model_ref.partition(":")
            if not separator or not provider.strip() or not model_name.strip():
                raise ValueError("models must use provider:model format")
        return models
```

Change the factory signature and construction:

```python
def build_deployment_agent(
    *,
    settings: AgentSettings,
    registry: ToolRegistry,
    model: Model,
) -> Agent[AgentRunDeps, str | DeferredToolRequests]:
    return Agent(
        model,
        name=settings.name,
        description=settings.description,
        deps_type=AgentRunDeps,
        output_type=[str, DeferredToolRequests],
        toolsets=[registry.as_toolset().filtered(_selected_tool)],
        instructions=_dynamic_instructions,
    )
```

- [ ] **Step 5: Verify Task 1**

Run:

```bash
cd agent-server
uv run --offline pytest tests/test_agent_assembly.py -q
uv run --offline ruff check src/agent_core/agent.py tests/test_agent_assembly.py
uv run --offline mypy --strict src/agent_core/agent.py tests/test_agent_assembly.py
```

Expected: all exit 0. Record Task 1 in the execution ledger; do not create a Git commit.

---

### Task 2: Persist the Ordered Model Diagnostic

**Files:**

- Modify: `agent-server/src/agent_core/service.py`
- Modify: `agent-server/tests/test_service.py`

**Interfaces:**

- Consumes: `tuple[str, ...]` from `AgentSettings.models`.
- Produces: `AgentService(..., model_refs: tuple[str, ...])`.
- Produces admission diagnostic `{"prompt_revision": str, "models": list[str]}`.
- Removes: singular `model_id` service state.

- [ ] **Step 1: Capture and assert the exact execution configuration**

Extend `RecordingStore` with:

```python
self.execution_configs: list[dict[str, Any]] = []
```

At the beginning of `admit`, append `execution_config`. Change `_service` to pass:

```python
model_refs=("openrouter:openai/gpt-5.2", "openai:gpt-5-mini"),
```

In `test_submit_commits_before_starting_local_run`, assert:

```python
assert store.execution_configs == [
    {
        "prompt_revision": "revision-1",
        "models": ["openrouter:openai/gpt-5.2", "openai:gpt-5-mini"],
    }
]
```

- [ ] **Step 2: Run the service test and verify RED**

Run:

```bash
cd agent-server
uv run --offline pytest tests/test_service.py::test_submit_commits_before_starting_local_run -q
```

Expected: constructor or assertion failure because the service still accepts and persists singular `model_id`.

- [ ] **Step 3: Replace singular model state in `AgentService`**

Change the constructor fields to:

```python
prompt_revision: str = "",
model_refs: tuple[str, ...] = (),
poll_interval: float = 0.25,
```

Store `self._model_refs = model_refs`. Change admission configuration to:

```python
execution_config={
    "prompt_revision": self._prompt_revision,
    "models": list(self._model_refs),
},
```

Do not persist credentials, resolved model objects, fallback exceptions, or provider client state.

- [ ] **Step 4: Verify Task 2**

Run:

```bash
cd agent-server
uv run --offline pytest tests/test_service.py -q
uv run --offline ruff check src/agent_core/service.py tests/test_service.py
uv run --offline mypy --strict src/agent_core/service.py tests/test_service.py
```

Expected: all exit 0. Record Task 2 in the execution ledger; do not create a Git commit.

---

### Task 3: Compose and Verify Native `FallbackModel`

**Files:**

- Modify: `agent-server/src/agent_core/bootstrap.py`
- Create: `agent-server/tests/test_model_fallback.py`
- Modify: `agent-server/tests/test_http.py`

**Interfaces:**

- Consumes: `AgentSettings.models` and injected-model agent factory from Task 1.
- Consumes: `AgentService.model_refs` from Task 2.
- Produces: `_compose_model_chain(model_refs: tuple[str, ...]) -> Model` as a private one-line bootstrap composition seam.
- Produces: one native `FallbackModel` per application graph.

- [ ] **Step 1: Write native fallback behavior tests**

Create `tests/test_model_fallback.py` with two `FunctionModel` instances and Pydantic AI's real `FallbackModel`:

```python
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import AgentInfo, FunctionModel


@pytest.mark.asyncio
async def test_native_fallback_uses_next_model_after_model_api_error() -> None:
    calls: list[str] = []

    def primary(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        calls.append("primary")
        raise ModelAPIError("primary", "unavailable")

    def fallback(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        calls.append("fallback")
        return ModelResponse(parts=[TextPart("ok")], model_name="fallback")

    model = FallbackModel(
        FunctionModel(primary, model_name="primary"),
        FunctionModel(fallback, model_name="fallback"),
    )
    result = await Agent(model).run("hello")

    assert result.output == "ok"
    assert calls == ["primary", "fallback"]
```

Add this second test to prove the application did not broaden Pydantic AI's default fallback boundary:

```python
@pytest.mark.asyncio
async def test_native_fallback_does_not_catch_arbitrary_errors() -> None:
    fallback_calls = 0

    def primary(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise RuntimeError("tool-side failure")

    def fallback(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        nonlocal fallback_calls
        fallback_calls += 1
        return ModelResponse(parts=[TextPart("unexpected")], model_name="fallback")

    model = FallbackModel(
        FunctionModel(primary, model_name="primary"),
        FunctionModel(fallback, model_name="fallback"),
    )

    with pytest.raises(RuntimeError, match="tool-side failure"):
        await Agent(model).run("hello")
    assert fallback_calls == 0
```

- [ ] **Step 2: Write bootstrap composition tests**

In `test_http.py`, add:

```python
from types import SimpleNamespace

from pydantic_ai import UserError
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel

from agent_core.bootstrap import (
    _compose_model_chain,
    _runtime_lifespan,
    create_environment_app,
)
```

Monkeypatch `agent_core.bootstrap.FallbackModel` with a recording callable and assert:

```python
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
        ("openrouter:openai/gpt-5.2", "openai:gpt-5-mini", "anthropic:claude-sonnet-4-0")
    )

    assert result is sentinel
    assert calls == [
        (
            "openrouter:openai/gpt-5.2",
            ("openai:gpt-5-mini", "anthropic:claude-sonnet-4-0"),
        )
    ]
```

Add an unconfigured-app test. Extend the existing `httpx` import to `from httpx import ASGITransport, AsyncClient`, then use:

```python
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
```

The test must not assert or expose the exception text.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```bash
cd agent-server
uv run --offline pytest tests/test_model_fallback.py tests/test_http.py -q
```

Expected: native behavior tests pass, while bootstrap tests fail because `_compose_model_chain` and injected model wiring do not exist.

- [ ] **Step 4: Implement native bootstrap composition**

Import `UserError`, `Model`, and `FallbackModel`, then add:

```python
def _compose_model_chain(model_refs: tuple[str, ...]) -> Model:
    return FallbackModel(model_refs[0], *model_refs[1:])
```

Move model composition into the configuration `try` block:

```python
try:
    agent_settings = AgentSettings()
    auth_settings = AgentAuthSettings()
    database_settings = AgentDatabaseSettings()
    execution_settings = ExecutionSettings()
    model = _compose_model_chain(agent_settings.models)
except (ValidationError, ValueError, UserError, ImportError):
    return create_app()
```

Pass `model=model` into `build_deployment_agent` and pass
`model_refs=agent_settings.models` into `AgentService`. Remove every reference to
`agent_settings.openrouter_model`.

Do not pass `model=` to `PydanticAgentRuntime.execute`; the deployment agent already owns the native model chain.

- [ ] **Step 5: Verify Task 3 and whole-source type consistency**

Run:

```bash
cd agent-server
uv run --offline pytest tests/test_model_fallback.py tests/test_http.py tests/test_agent_assembly.py tests/test_service.py -q
uv run --offline ruff check src tests/test_model_fallback.py tests/test_http.py tests/test_agent_assembly.py tests/test_service.py
uv run --offline mypy src tests/test_model_fallback.py tests/test_http.py tests/test_agent_assembly.py tests/test_service.py
```

Expected: all exit 0. Record Task 3 in the execution ledger; do not create a Git commit.

---

### Task 4: Ship Provider Extras and Update Acceptance Surfaces

**Files:**

- Modify: `agent-server/pyproject.toml`
- Modify: `agent-server/uv.lock`
- Modify: `agent-server/tests/test_pydantic_contract.py`
- Modify: `agent-server/tests/test_service_boundary.py`
- Modify: `agent-server/tests/e2e/test_openrouter.py`
- Modify: `agent-server/README.md`

**Interfaces:**

- Produces exact dependency `pydantic-ai-slim[ag-ui,anthropic,google,openai,openrouter]==2.38.0`.
- Produces an OpenRouter live acceptance configured through one-entry `AgentSettings.models`.
- Produces documented provider-native credentials and native fallback semantics.

- [ ] **Step 1: Write the failing dependency and source-boundary contracts**

Change `test_pydantic_contract.py` to import `FallbackModel` and assert the only Pydantic AI dependency is:

```python
assert pydantic_dependencies == [
    "pydantic-ai-slim[ag-ui,anthropic,google,openai,openrouter]==2.38.0"
]
```

In `test_service_boundary.py`, add a production-source check:

```python
def test_agent_core_has_no_concrete_provider_imports() -> None:
    violations: list[str] = []
    concrete_roots = (
        "pydantic_ai.providers.",
        "pydantic_ai.models.openai",
        "pydantic_ai.models.anthropic",
        "pydantic_ai.models.google",
        "pydantic_ai.models.openrouter",
    )
    for path in sorted(SRC.rglob("*.py")):
        for target in _import_targets(path):
            if target.startswith(concrete_roots):
                violations.append(f"{path.relative_to(SRC)} -> {target}")
    assert violations == []
```

The generic `pydantic_ai.models.fallback` import remains allowed.

- [ ] **Step 2: Run the contracts and verify RED**

Run:

```bash
cd agent-server
uv run --offline pytest tests/test_pydantic_contract.py tests/test_service_boundary.py -q
```

Expected: dependency mismatch and concrete OpenRouter import failures.

- [ ] **Step 3: Update provider extras and lock**

Change `pyproject.toml` to:

```toml
"pydantic-ai-slim[ag-ui,anthropic,google,openai,openrouter]==2.38.0",
```

Then run:

```bash
cd agent-server
uv lock
uv sync --frozen
```

Expected: Anthropic and Google provider dependencies enter the resolved tree without changing Pydantic AI 2.38.0.

- [ ] **Step 4: Update the OpenRouter live E2E**

Remove `SecretStr` construction. Build settings with:

```python
models=(
    f"openrouter:{os.environ.get('OPENROUTER_MODEL', 'openai/gpt-5-mini')}",
),
```

Construct the native model chain and inject it:

```python
model = FallbackModel(settings.models[0], *settings.models[1:])
agent = build_deployment_agent(
    settings=settings,
    registry=registry,
    model=model,
)
```

Pass `model_refs=settings.models` to `AgentService`. Keep the existing disconnect/reconnect assertions, cleanup, and bounded shutdown unchanged.

- [ ] **Step 5: Rewrite README model configuration**

Replace the OpenRouter-only configuration text with:

```text
AGENT_MODELS=["openrouter:openai/gpt-5-mini","openai:gpt-5-mini"]
```

Document that order is primary then fallbacks, fallback occurs only under Pydantic AI's default `ModelAPIError` policy, and callers cannot choose a model. List `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`/legacy `GEMINI_API_KEY`, Google application credentials, and `OPENROUTER_API_KEY`. Retain the single-instance recreate and local-crash semantics.

- [ ] **Step 6: Verify Task 4**

Run:

```bash
cd agent-server
uv run --offline pytest tests/test_pydantic_contract.py tests/test_service_boundary.py tests/e2e/test_openrouter.py -q
uv run --offline ruff check src tests
uv run --offline mypy src tests
uv lock --check --offline
```

Expected: non-live tests pass and only the credential-gated OpenRouter case may skip. Record Task 4 in the execution ledger; do not create a Git commit.

---

### Task 5: Complete Verification and Review

**Files:**

- Create during execution: `agent-server/.superpowers/sdd/2026-09-05-native-pydantic-ai-multi-model/progress.md`
- Review: all files changed by Tasks 1–4

**Interfaces:**

- Consumes all prior tasks.
- Produces final evidence for native fallback, provider-neutral boundaries, complete tests, and optional live acceptance.

- [ ] **Step 1: Run the full non-live verification**

```bash
cd agent-server
TERM=dumb uv run --offline pytest tests -q
uv run --offline ruff check src tests
uv run --offline mypy src tests
uv lock --check --offline
```

Expected: all commands exit 0; only the explicitly credential-gated live provider test may skip.

- [ ] **Step 2: Run residue checks**

```bash
cd agent-server
test -z "$(rg -n 'openrouter_model|openrouter_api_key|AGENT_OPENROUTER_MODEL' src tests README.md pyproject.toml)"
test -z "$(rg -n 'PydanticModelResolver|ModelResolver|ProviderRegistry' src tests README.md pyproject.toml)"
```

Expected: both commands exit 0. Provider-specific names remain only where they are valid examples, dependency extras, credential names, or the OpenRouter live E2E.

- [ ] **Step 3: Review call flow with CodeCanvas**

Against `agent-server/src/agent_core`, inspect:

- `bootstrap._compose_model_chain`
- `agent.build_deployment_agent`
- `runtime.PydanticAgentRuntime.execute`
- `service.AgentService.submit`

Confirm the graph is `AGENT_MODELS -> FallbackModel -> Agent -> runtime`, and no model-selection edge reaches the HTTP request or PostgreSQL reconstruction paths. Confirm entry points remain `GET /healthz`, `POST /ag-ui`, and `POST /runs/{run_id}/abort`.

- [ ] **Step 4: Run live OpenRouter acceptance when credentials exist**

```bash
cd agent-server
RUN_OPENROUTER_E2E=1 \
uv run --env-file /Users/dongkseo/project/nexora-console/.env \
pytest tests/e2e/test_openrouter.py -q -m e2e
```

Expected: two tests pass: the real OpenRouter disconnect/reconnect run and PostgreSQL orphan terminalization. If that environment file or credential is absent, record the explicit skip without weakening non-live acceptance.

- [ ] **Step 5: Record final evidence**

Write exact test counts, static-check results, lock result, residue results, live acceptance status, and the no-Git ruling into the execution ledger. Do not claim a commit, branch, PR, or merge.

---

## Plan Self-Review Result

- Spec coverage: Tasks 1–5 cover ordered settings, native Pydantic model inference, default fallback behavior, model injection, startup failures, persistence diagnostics, provider extras, live acceptance, documentation, and source boundaries.
- Scope: one model-construction boundary correction; no request routing, custom resolver, provider registry, custom fallback condition, database migration, or orchestration change.
- Type consistency: `AgentSettings.models`, `build_deployment_agent(..., model: Model)`, `_compose_model_chain(...) -> Model`, and `AgentService.model_refs` are introduced before their final bootstrap/E2E consumers.
- Placeholder scan: every behavior has exact fields, signatures, assertions, commands, and expected results; no deferred implementation placeholders remain.
