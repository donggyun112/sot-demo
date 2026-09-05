# Agent Server Legacy Cleanup Implementation Plan

> **For agentic workers:** Execute this plan inline and task-by-task. Do not delegate it. Every
> production change follows a failing cleanup contract test.

**Goal:** Remove the obsolete queue/worker/request-lease Agent prototype and leave a tested,
bootable Agent Server skeleton for the approved AG-UI/Semora implementation.

**Architecture:** Retain only the FastAPI process boundary, service entrypoint, independent Agent
database settings, packaging and service-isolation checks. Delete the unused lifecycle state
machine, PostgreSQL queue store, old schema and their tests instead of adapting them to the new
design. Do not add any replacement execution behavior in this slice.

**Tech Stack:** Python 3.12+, FastAPI, pytest, Ruff, mypy

**Spec:** `docs/superpowers/plans/2026-08-30-agui-agent-boundary.md`

## Global Constraints

- One deployed Agent Server represents one logical agent.
- Platform and Agent packages, databases and migrations remain isolated.
- No queue consumer, request claim/lease/attempt state machine or execution worker remains.
- Semora remains the future execution owner; this cleanup does not integrate it yet.
- Do not create `/ag-ui`, new persistence DDL, Redis, auth, prompt or OpenRouter code here.
- Keep the application importable and the existing health endpoint operational.
- This workspace is not a Git repository, so the plan has verification checkpoints instead of
  commit steps.

---

### Task 1: Define the clean skeleton contract

**Files:**

- Modify: `agent-server/tests/test_http.py`
- Modify: `agent-server/tests/test_service_boundary.py`

**Interfaces:**

- Consumes: current `agent_core.api.create_app`, `agent_core` and `agent_core.store` exports
- Produces: a failing HTTP test that defines the removed public route and corrected isolation tests

- [x] **Step 1: Replace the old `/agent` expectations**

  Keep the health test and add a test that `POST /agent` returns `404`. Remove tests for its old
  validation-only `501` behavior.

- [x] **Step 2: Correct the dependency-boundary test**

  Keep the prohibition on Platform/backend/SOT dependencies. Remove the obsolete prohibition on
  Semora/LangChain, because the approved Agent Server will own Semora in the next slice.

- [x] **Step 3: Verify RED**

  Run:

  ```bash
  UV_CACHE_DIR=/tmp/sot-agent-cleanup-uv-cache uv run --offline pytest -q \
    tests/test_http.py tests/test_service_boundary.py
  ```

  Expected: one failure because the existing `/agent` route validates the empty body as `422`
  instead of being absent with `404`.

### Task 2: Remove the obsolete execution model

**Files:**

- Delete: `agent-server/src/agent_core/contract.py`
- Delete: `agent-server/src/agent_core/store/postgres.py`
- Delete: `agent-server/src/agent_core/store/schema.sql`
- Delete: `agent-server/tests/test_contract.py`
- Delete: `agent-server/tests/integration/conftest.py`
- Delete: `agent-server/tests/integration/test_agent_postgres.py`
- Delete: `agent-server/tests/integration/__init__.py`
- Modify: `agent-server/src/agent_core/__init__.py`
- Modify: `agent-server/src/agent_core/store/__init__.py`
- Modify: `agent-server/src/agent_core/api/app.py`

**Interfaces:**

- Consumes: failing Task 1 tests
- Produces: bootable `agent_core.main:app`, `GET /healthz`, and independent DB settings only

- [x] **Step 1: Delete legacy-only source and tests**

  Remove the lifecycle enum/dataclasses/protocols, queue store/schema and tests that specify the
  rejected worker architecture.

- [x] **Step 2: Minimize package exports**

  Make `agent_core.__all__` empty and make `agent_core.store` export only
  `AgentDatabaseSettings`. Do not add placeholder replacement abstractions.

- [x] **Step 3: Remove the old route**

  Keep `create_app()` and `/healthz`; remove `POST /agent`, its `RunAgentInput` import and its
  route-specific validation handler.

- [x] **Step 4: Verify GREEN**

  Run the Task 1 command again. Expected: all selected tests pass.

### Task 3: Align documentation and verify the baseline

**Files:**

- Modify: `agent-server/README.md`
- Verify: `agent-server/pyproject.toml`
- Verify: `agent-server/uv.lock`

**Interfaces:**

- Consumes: the clean skeleton from Task 2
- Produces: an explicit handoff point for the first new AG-UI implementation slice

- [x] **Step 1: Update the Agent README status**

  Replace the warning about existing `/agent` and request-lease prototype with a statement that
  the legacy prototype has been removed and execution is intentionally not implemented yet.

- [x] **Step 2: Preserve target dependencies without adding new ones**

  Do not change the lockfile in this cleanup. Existing AG-UI/PostgreSQL dependencies are part of
  the approved next slices; Semora/OpenRouter/auth/Redis dependencies are added only with their
  implementing tests.

- [x] **Step 3: Run complete verification**

  ```bash
  UV_CACHE_DIR=/tmp/sot-agent-cleanup-uv-cache uv run --offline pytest -q
  UV_CACHE_DIR=/tmp/sot-agent-cleanup-uv-cache uv run --offline ruff check .
  UV_CACHE_DIR=/tmp/sot-agent-cleanup-uv-cache uv run --offline mypy src tests
  ```

  Expected: all commands pass with no skipped legacy integration suite and no mypy errors.

- [x] **Step 4: Re-run entrypoint and dead-code analysis**

  Confirm the only HTTP entrypoint is `/healthz`, the package imports without source-path
  injection, and no `queued`, `claim_next`, `lease_owner`, `attempt`, `worker_id`, `/agent` or
  `PostgresAgentStore` production symbol remains. This is a cleanup inspection, not a permanent
  source-shape test.
