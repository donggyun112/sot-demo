# Native Pydantic AI Multi-Model Boundary

Status: approved in chat on 2026-09-05.

## Problem

The local async runtime delegates execution to Pydantic AI, but `agent_core.agent` still constructs
`OpenRouterModel` with `OpenRouterProvider`. Agent construction, settings, bootstrap, tests, and
documentation are therefore coupled to one provider even though Pydantic AI 2.38.0 already supports
provider-qualified model names and native multi-model fallback.

Adding a custom provider resolver or registry would duplicate Pydantic AI's model inference and
fallback responsibilities. The correction is to expose Pydantic AI's native model abstraction at
the application boundary.

## Goals

- Remove all concrete provider imports and credentials from Agent Core.
- Configure an ordered model chain through deployment settings.
- Use Pydantic AI's native `FallbackModel` for cross-provider fallback.
- Let Pydantic AI resolve every `provider:model` reference.
- Keep credentials in provider-native environment variables.
- Validate malformed or unusable model configuration during application startup.
- Preserve the existing service, supervisor, PostgreSQL journal, AG-UI protocol, tool authority,
  cancellation, and crash semantics.
- Initially package OpenAI, Anthropic, Google, and OpenRouter provider support.

## Non-Goals

- A custom model resolver, provider registry, or provider factory layer.
- Selecting models from AG-UI request content.
- Dynamically changing the configured model chain for an already admitted run.
- Load balancing, cost-based routing, hedged requests, or provider SDK installation at runtime.
- Falling back on arbitrary application, tool, validation, or cancellation failures.
- Persisting credentials or accepting them from callers.

## Architecture

The dependency direction becomes:

```text
AGENT_MODELS=[primary, fallback-1, fallback-2]
provider-native credential variables
                    |
                    v
Pydantic AI FallbackModel(primary, *fallbacks)
  - infer provider-qualified model strings
  - invoke providers in order on ModelAPIError
                    |
                    v
build_deployment_agent(model=...)
                    |
                    v
PydanticAgentRuntime -> RunSupervisor -> AgentService
```

`agent_core.agent` may import the abstract Pydantic AI `Model` type. It must not import concrete
model or provider classes. Bootstrap composes the native `FallbackModel` once and injects that
ready `Model` into the deployment agent. No application-defined resolver sits between configuration
and Pydantic AI.

`AgentService`, `PydanticAgentRuntime`, `RunSupervisor`, projection, and persistence remain unaware
of both the model chain and the selected provider.

## Configuration

`AgentSettings` removes:

```text
openrouter_model
openrouter_api_key
```

and adds:

```python
models: tuple[str, ...]
```

The environment variable is a JSON array so ordering and model names containing punctuation remain
unambiguous:

```text
AGENT_MODELS=["openrouter:openai/gpt-5-mini","openai:gpt-5-mini","anthropic:claude-sonnet-4-0","google:gemini-2.5-flash"]
```

The first entry is the primary model. Remaining entries are attempted in order by `FallbackModel`.
The list must contain at least one non-empty, provider-qualified value and must not contain duplicate
references. Unqualified model names are rejected so provider selection never depends on implicit
defaults.

Pydantic AI 2.38.0 provider prefixes used by the initial package are:

- `openai`
- `anthropic`
- `google` for Google AI Studio
- `google-cloud` for Vertex AI
- `openrouter`

## Native Model Composition

Bootstrap constructs the model exactly once:

```python
model = FallbackModel(
    agent_settings.models[0],
    *agent_settings.models[1:],
)
```

`FallbackModel` uses Pydantic AI's default fallback condition: `ModelAPIError`. Authentication,
rate-limit, provider availability, and other model API errors may advance to the next configured
model according to Pydantic AI's exception hierarchy. Cancellation, tool failures, application
errors, invalid outputs, and arbitrary exceptions do not gain a custom fallback policy.

Even a one-entry configuration uses the same native composition path. This keeps bootstrap logic
and tests identical regardless of chain length.

The deployment-agent factory becomes:

```python
def build_deployment_agent(
    *,
    settings: AgentSettings,
    registry: ToolRegistry,
    model: Model,
) -> Agent[AgentRunDeps, str | DeferredToolRequests]: ...
```

It passes the injected model to `Agent` and preserves the existing name, description, dependency
type, output type, filtered server-owned toolset, and dynamic instructions. It does not inspect or
override the model chain.

The runtime continues calling `agent.run(...)` without a model override. The deployment agent's
native `FallbackModel` remains the sole model for every run owned by that process.

## Credentials and Dependencies

Pydantic AI provider implementations read their native deployment credentials:

- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- Google AI Studio: `GOOGLE_API_KEY`, with `GEMINI_API_KEY` accepted by Pydantic AI as a legacy alias
- Google Vertex: standard Google application credentials
- OpenRouter: `OPENROUTER_API_KEY`

No credential becomes an `AgentSettings` field, AG-UI field, persisted request value, or loggable
model diagnostic.

The exact Pydantic AI dependency becomes:

```text
pydantic-ai-slim[ag-ui,anthropic,google,openai,openrouter]==2.38.0
```

Provider packages are fixed at image build time. Adding another built-in Pydantic AI provider means
adding its package extra and documenting its native model prefix and credentials; Agent Core does
not change.

## Bootstrap and Failure Handling

Bootstrap performs composition in this order:

1. Parse agent, auth, database, and execution settings.
2. Validate that `AGENT_MODELS` is non-empty, qualified, and duplicate-free.
3. Construct Pydantic AI `FallbackModel` from the ordered strings.
4. Inject it into `build_deployment_agent`.
5. Construct projector, runtime, supervisor, and service as before.

Settings validation, missing provider packages, unknown provider names, and missing credential
configuration are handled at this startup boundary. They produce the existing unconfigured
application rather than a partially constructed service. Error responses and logs must not contain
credential values.

A provider failure after admission keeps the current behavior. If the native fallback chain is
exhausted, the run receives a terminal `RUN_ERROR` with code `agent_failed`; raw provider errors are
not exposed through AG-UI.

## Persistence

Admission stores this diagnostic execution configuration:

```json
{
  "prompt_revision": "<revision>",
  "models": ["<primary>", "<fallback-1>"]
}
```

The ordered references contain no credentials. Existing rows using the singular `model` diagnostic
remain readable because execution configuration is not used to reconstruct or resume local tasks.
No database migration is required.

Duplicate submission of an existing run only replays its journal. It never restarts the run with a
newly configured model chain.

## Deployment Migration

This is an intentional environment configuration break:

```text
AGENT_OPENROUTER_MODEL=<name>
->
AGENT_MODELS=["openrouter:<name>"]
```

There is no compatibility alias for `AGENT_OPENROUTER_MODEL`; retaining it would preserve the
provider-specific setting and create precedence ambiguity. `OPENROUTER_API_KEY` remains valid when
an OpenRouter model appears in the chain.

Rollout retains the existing single-instance recreate policy.

## Testing and Acceptance

- Settings tests cover JSON parsing, ordering, empty lists, unqualified values, and duplicates.
- Agent assembly tests inject a Pydantic `TestModel` and prove Agent Core performs no provider
  construction.
- Native composition tests monkeypatch or inspect `FallbackModel` construction and verify the exact
  primary/fallback order without making network requests.
- A fake primary that raises `ModelAPIError` and a successful fake fallback prove Pydantic AI owns
  fallback execution and the AG-UI journal still receives one start and one terminal event.
- A non-model exception proves the application does not broaden Pydantic AI's fallback condition.
- Bootstrap tests prove the composed model object reaches `build_deployment_agent` unchanged.
- Service tests assert the ordered `models` diagnostic and absence of credentials.
- Dependency tests assert the exact provider-extra set.
- Source-boundary tests forbid concrete provider/model imports from Agent Core.
- The OpenRouter live E2E remains one provider acceptance case, configured as a one-entry model
  chain. Other providers do not require live credentials in the default test suite.
- Full pytest, Ruff, mypy, lock consistency, and provider-specific residue checks must pass.

## Documentation

README will document `AGENT_MODELS`, ordered fallback behavior, the exact default `ModelAPIError`
fallback boundary, and provider-native credentials. OpenRouter becomes one example in a native
Pydantic AI model chain rather than the application's model architecture.
