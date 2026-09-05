# Agent Loop Implementation Plan

> Superseded by
> [`2026-09-03-pydantic-ai-runtime-migration.md`](./2026-09-03-pydantic-ai-runtime-migration.md).
> Retained only as historical implementation context.

**Goal:** Build the Agent Server's executable AG-UI-to-Semora loop without introducing a worker, queue, or Platform dependency.

**Architecture:** FastAPI accepts the official AG-UI input, validates and records the request, then starts a detached in-process execution supervised by the Agent Server. A declarative Semora `Agent` is assembled from server-owned configuration and tools, and every execution enters Semora only through `AgentRuntime.dispatch()`. Semora remains the execution/transcript authority; Agent-owned PostgreSQL tables retain AG-UI request identity, replay events, and interrupt mappings. Redis is an optional live hint/cache and never canonical.

**Tech Stack:** Python 3.12+, FastAPI, ag-ui-protocol, Semora 0.2.0 (`postgres`, `openrouter` extras), psycopg 3, PostgreSQL, pytest, mypy, ruff.

**Canonical design:** `docs/superpowers/specs/2026-09-03-agent-loop-design.md`

## Implementation order

### 1. Semora public contract and dependency

- Add a contract test that imports only the approved Semora 0.2.0 public APIs.
- Pin `semora[postgres,openrouter]==0.2.0` and update the lock/environment.
- Verify the focused contract test.

### 2. Declarative agent assembly

- Add typed Agent settings for name, description, system prompt file, prompt revision, OpenRouter model, and execution limits.
- Add a server-owned tool registry with duplicate/unknown selection rejection.
- Add prompt assembly with fixed ordering and explicit untrusted context delimiters.
- Build the Semora `Agent` from settings, the OpenRouter model, and selected server-owned tools.
- Cover settings, prompt ordering, tool selection, and construction with unit tests.

### 3. AG-UI command mapping

- Reject client-supplied `system` and `developer` messages.
- Map prior messages to Semora history and the trailing user message to `Prompt` while preserving its ID.
- Map AG-UI resume payloads to Semora `Answer`; reserve `Recover` for internal recovery.
- Cover valid and invalid message shapes with unit tests.

### 4. Semora execution adapter

- Define a narrow runtime protocol around `dispatch()` for testability.
- Construct `ExecutionContext` from opaque authenticated subject data.
- Execute only via `AgentRuntime.dispatch()` and translate Semora stream events into official AG-UI events.
- Keep `event_sink` diagnostic-only and make event persistence an awaited boundary.
- Cover ordering, terminal states, suspension, and errors with scripted runtime tests.

### 5. Agent-owned persistence

- Add minimal migrations and repositories for `agent_request`, `agent_event`, and `agent_interrupt`.
- Implement idempotent request admission, monotonic per-run event sequencing, replay by cursor, abort intent, and terminal state.
- Reuse Semora's `PostgresSteps` and `PostgresTranscript`; do not duplicate their execution ledger.
- Cover repositories with PostgreSQL integration tests.

### 6. Detached supervision, SSE, and abort

- Add an in-process task supervisor keyed by run ID; no polling worker or queue.
- Return promptly after durable admission, stream committed events over SSE, and resume replay from the database cursor after reconnect.
- Treat disconnect as unsubscribe only. Add an explicit stop endpoint that records abort intent and signals a local execution when present.
- Cover refresh/reconnect, subscribe-to-running-run, explicit stop, and replica-safe database fallback.

### 7. Application wiring and verification

- Wire settings, database pools, Semora stores/runtime, repositories, and routes in FastAPI lifespan.
- Add readiness separate from liveness.
- Run focused tests after each slice, then the full unit/integration suite, ruff, and mypy.
- Update Agent Server README only where behavior is actually implemented.

## Guardrails

- Agent Server code must not import Platform packages or Platform domain vocabulary.
- Do not add a worker, job queue, claim/lease table, outbox, or scanner.
- Do not call `react_loop`, `force_retry`, Semora private APIs, or Semora tables directly.
- Do not let request payloads define executable tools or system/developer prompts.
- Do not equate SSE disconnect with abort.
- Do not claim a stage complete until its tests and static checks pass.
