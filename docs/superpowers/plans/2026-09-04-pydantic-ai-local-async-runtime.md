# Pydantic AI Local Async Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove DBOS and run the singleton Pydantic AI agent in supervised process-local async tasks while PostgreSQL remains the canonical AG-UI request and replay journal.

**Architecture:** `AgentService` commits an authenticated request, then synchronously registers one task with `RunSupervisor`. `PydanticAgentRuntime` calls the deployment `Agent` directly with a fresh `CancellationToken` and projects AG-UI events into PostgreSQL; SSE only replays that journal. Process loss is not recovered: the next exclusive instance terminalizes orphaned runs as `indeterminate_execution` before readiness.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic AI 2.38.0 (`ag-ui`, `openrouter` extras), psycopg 3, PostgreSQL, pytest, pytest-asyncio, mypy, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-04-pydantic-ai-local-async-runtime-design.md`

## Global Constraints

- Exactly one Agent Server instance may be active against one Agent database; deployment uses recreate, never rolling overlap.
- The agent is not a worker: no queue, claim loop, lease, fencing token, heartbeat, execution poller, or cross-process retry.
- SSE disconnect only detaches the subscriber; it never cancels local execution.
- Ungraceful process loss never resumes execution; startup writes `RUN_ERROR(code="indeterminate_execution")` for every orphan.
- `run:terminal` is the only terminal producer key, and no new event may be stored after terminal closure.
- Request tools remain name-only selection over the server-owned `ToolRegistry`.
- `migrations/002_semora.sql` remains unchanged as rollback-only history.
- This workspace has no Git metadata. Do not initialize Git; record checkpoints in the SDD ledger and filesystem snapshots instead of claiming commits.

## File Map

- Create `src/agent_core/supervisor.py`: local task/token ownership and bounded shutdown.
- Replace `src/agent_core/runtime.py`: direct Pydantic execution adapter.
- Modify `src/agent_core/projection.py`: journal-oriented naming and explicit run start.
- Replace `src/agent_core/service.py`: local orchestration, abort, failure, shutdown, orphans.
- Create `migrations/004_local_async.sql`: remove workflow columns and close terminal journals.
- Modify `src/agent_core/store/postgres.py`: runtime-neutral request and interrupt persistence.
- Replace `src/agent_core/bootstrap.py`: exclusive local lifecycle without DBOS.
- Modify `src/agent_core/api/app.py`: local-capacity HTTP response.
- Modify dependency, unit, integration, E2E, and deployment documentation files named below.

---

### Task 1: Restore Process-Local Task Ownership

**Files:**

- Create: `agent-server/src/agent_core/supervisor.py`
- Create: `agent-server/tests/test_supervisor.py`

**Interfaces:**

- Consumes: `pydantic_ai.CancellationToken`.
- Produces: `ExecutionSettings(capacity=32, shutdown_timeout_seconds=35.0)` with `AGENT_RUN_` prefix.
- Produces: `RunSupervisor.start(run_id, execute) -> bool`, `contains(run_id) -> bool`,
  `abort(run_id) -> bool`, and `drain(*, timeout) -> None`.
- Produces: `RunCapacityExceeded`.

- [ ] **Step 1: Write failing task ownership and deduplication tests**

```python
@pytest.mark.asyncio
async def test_supervisor_owns_one_task_until_execution_finishes() -> None:
    supervisor = RunSupervisor(capacity=2)
    release = asyncio.Event()

    async def execute(token: CancellationToken) -> None:
        assert token.cancelled is False
        await release.wait()

    assert supervisor.start(RUN_ID, execute) is True
    assert supervisor.start(RUN_ID, execute) is False
    await asyncio.sleep(0)
    assert supervisor.contains(RUN_ID)
    release.set()
    await supervisor.drain(timeout=1)
    assert not supervisor.contains(RUN_ID)
```

- [ ] **Step 2: Write failing capacity, abort, and drain tests**

```python
@pytest.mark.asyncio
async def test_capacity_fails_fast_without_queueing() -> None:
    supervisor = RunSupervisor(capacity=1)
    release = asyncio.Event()

    async def execute(_: CancellationToken) -> None:
        await release.wait()

    supervisor.start("run-1", execute)
    with pytest.raises(RunCapacityExceeded):
        supervisor.start("run-2", execute)
    release.set()
    await supervisor.drain(timeout=1)


@pytest.mark.asyncio
async def test_abort_cancels_the_named_task_and_token() -> None:
    supervisor = RunSupervisor(capacity=2)
    observed: list[bool] = []

    async def execute(token: CancellationToken) -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            observed.append(token.cancelled)

    supervisor.start(RUN_ID, execute)
    await asyncio.sleep(0)
    assert supervisor.abort(RUN_ID) is True
    await supervisor.drain(timeout=1)
    assert observed == [True]
```

- [ ] **Step 3: Verify RED**

Run: `uv run --project agent-server pytest agent-server/tests/test_supervisor.py -q`

Expected: collection fails because `agent_core.supervisor` does not exist.

- [ ] **Step 4: Implement the local supervisor**

```python
type RunExecution = Callable[[CancellationToken], Awaitable[None]]


class RunCapacityExceeded(Exception):
    pass


class ExecutionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_RUN_", extra="ignore")
    capacity: int = Field(default=32, gt=0)
    shutdown_timeout_seconds: float = Field(default=35.0, gt=0)


@dataclass(slots=True)
class _OwnedRun:
    token: CancellationToken
    task: asyncio.Task[None]
```

`start` checks duplicate then capacity, creates a fresh token and named task, and removes the run in
`finally`. `abort` cancels both token and task. `drain` waits until timeout, cancels both the token
and task for every pending run, and gathers tasks with `return_exceptions=True`. No method accesses
PostgreSQL.

- [ ] **Step 5: Verify GREEN and static checks**

```bash
uv run --project agent-server pytest agent-server/tests/test_supervisor.py -q
uv run --project agent-server ruff check agent-server/src/agent_core/supervisor.py agent-server/tests/test_supervisor.py
uv run --project agent-server mypy agent-server/src/agent_core/supervisor.py agent-server/tests/test_supervisor.py
```

Expected: all commands exit 0. Record results and `snapshots/task-1-before` in
`.superpowers/sdd/2026-09-04-pydantic-ai-local-async-runtime/progress.md`.

---

### Task 2: Replace DBOS Runtime with Direct Pydantic Execution

**Files:**

- Replace: `agent-server/src/agent_core/runtime.py`
- Replace: `agent-server/tests/test_runtime.py`
- Modify: `agent-server/src/agent_core/agent.py`
- Modify: `agent-server/tests/test_agent_assembly.py`
- Modify: `agent-server/src/agent_core/projection.py`
- Modify: `agent-server/tests/test_projection.py`

**Interfaces:**

- Consumes: `MappedRun`, `AgentRunDeps`, `CancellationToken`, singleton `Agent`.
- Produces: `AGUIJournalProjector.started(run_id, thread_id) -> StoredEvent`,
  `project(run_id, thread_id, native_events, *, request_index=0) -> None`, and
  `fail(run_id, message, *, code) -> StoredEvent`.
- Produces: `PydanticAgentRuntime.execute(mapped, deps, cancellation_token) -> None`.
- Changes: `build_deployment_agent(*, settings, registry)` has no durability argument.

- [ ] **Step 1: Write failing direct invocation tests**

Use a recording agent and projector. Assert one call contains:

```python
assert call["run_id"] == RUN_ID
assert call["conversation_id"] == THREAD_ID
assert call["cancellation_token"] is token
assert call["deps"] == deps
assert callable(call["event_stream_handler"])
```

Have the recording agent invoke its supplied event handler with native text events. Assert the
projector receives the mapped run/thread IDs and `request_index=ctx.run_step`.

Add one real `pydantic_ai.models.test.TestModel(call_tools="all")` agent with a plain read-only tool.
Execute it through `PydanticAgentRuntime` and assert the journal contains exactly one
`RUN_STARTED`, one `RUN_FINISHED`, and one terminal event across the tool/model round.

- [ ] **Step 2: Write failing journal-start and agent-construction tests**

```python
@pytest.mark.asyncio
async def test_started_uses_stable_start_key() -> None:
    store = IdempotentRecordingStore()
    await AGUIJournalProjector(store).started(RUN_ID, THREAD_ID)
    assert store.producer_keys == ["run:started"]
    assert store.events[0].type == EventType.RUN_STARTED


def test_builds_agent_without_durable_capability(tmp_path: Path) -> None:
    agent = build_deployment_agent(settings=_settings(tmp_path), registry=_registry())
    assert agent.name == "discussion-agent"
```

- [ ] **Step 3: Verify RED**

Run:

```bash
uv run --project agent-server pytest agent-server/tests/test_runtime.py agent-server/tests/test_projection.py agent-server/tests/test_agent_assembly.py -q
```

Expected: missing `PydanticAgentRuntime`/`AGUIJournalProjector` and old `durability` signature failures.

- [ ] **Step 4: Implement direct runtime**

```python
class PydanticAgentRuntime:
    def __init__(self, *, agent: Agent[AgentRunDeps, str | DeferredToolRequests], projector: AGUIJournalProjector) -> None:
        self._agent = agent
        self._projector = projector

    async def execute(self, mapped: MappedRun, deps: AgentRunDeps, cancellation_token: CancellationToken) -> None:
        async def project_events(ctx: RunContext[AgentRunDeps], events: AsyncIterable[AgentStreamEvent]) -> None:
            await self._projector.project(
                mapped.identity.run_id,
                mapped.identity.conversation_id,
                events.__aiter__(),
                request_index=ctx.run_step,
            )

        await self._projector.started(mapped.identity.run_id, mapped.identity.conversation_id)
        await self._agent.run(
            mapped.user_prompt,
            deps=deps,
            message_history=mapped.message_history,
            deferred_tool_results=mapped.deferred_tool_results,
            conversation_id=mapped.identity.conversation_id,
            run_id=mapped.identity.run_id,
            cancellation_token=cancellation_token,
            event_stream_handler=project_events,
        )
```

Delete DBOS settings, client, status enum, queue, decorators, globals, workflow ID, and lifecycle.

- [ ] **Step 5: Rename projector and simplify agent factory**

Rename `DurableAGUIProjector` to `AGUIJournalProjector`. Its `started` method constructs
`RunStartedEvent(thread_id=thread_id, run_id=run_id)` and appends it with producer key
`run:started`. Keep deterministic request/event keys, interrupt mapping, `run:terminal`, and
bounded failure messages.

Remove `durability` from `build_deployment_agent` and remove `capabilities=[durability]` from the
`Agent` constructor. Keep model, output type, dynamic instructions, and filtered server toolset.

- [ ] **Step 6: Verify GREEN and static checks**

```bash
uv run --project agent-server pytest agent-server/tests/test_runtime.py agent-server/tests/test_projection.py agent-server/tests/test_agent_assembly.py -q
uv run --project agent-server ruff check agent-server/src/agent_core/runtime.py agent-server/src/agent_core/projection.py agent-server/src/agent_core/agent.py agent-server/tests/test_runtime.py agent-server/tests/test_projection.py agent-server/tests/test_agent_assembly.py
uv run --project agent-server mypy agent-server/src agent-server/tests/test_runtime.py agent-server/tests/test_projection.py agent-server/tests/test_agent_assembly.py
```

Expected: all commands exit 0. Record Task 2 and `snapshots/task-2-before` in the SDD ledger.

---

### Task 3: Rewire AgentService to Local Tasks

**Files:**

- Replace: `agent-server/src/agent_core/service.py`
- Replace: `agent-server/tests/test_service.py`
- Modify: `agent-server/tests/test_agui_api.py`

**Interfaces:**

- Consumes: `RunSupervisor`, `RunCapacityExceeded`, `PydanticAgentRuntime`, and store journal APIs.
- Produces: admission/start lock, local execution wrapper, `reconcile_orphans()`, and
  `shutdown(*, timeout)`.
- Removes: `WorkflowRuntime`, `WorkflowStatus`, `PersistedWorkflowRunSource`, status reconciliation,
  and persisted workflow reconstruction.

- [ ] **Step 1: Write failing admission and duplicate tests**

```python
assert await service.submit(_payload(), _caller()) == RUN_ID
assert order == ["admit", "start"]
```

For `RecordingStore(created=False)`, assert `order == ["admit"]`. Add two concurrent submissions
whose fake admission blocks: the admission/start lock must ensure exactly one supervisor start and
the duplicate must observe the registered run.

- [ ] **Step 2: Write failing failure, cancellation, capacity, and orphan tests**

Assert these exact outcomes:

```python
assert provider_failure.code == "agent_failed"
assert "private provider detail" not in provider_failure.message
assert explicit_abort.code == "aborted"
assert shutdown_cancellation.code == "server_shutdown"
assert capacity_failure.code == "capacity_exceeded"
assert orphan.code == "indeterminate_execution"
assert runtime.calls == []  # orphan reconciliation never executes a run
```

- [ ] **Step 3: Verify RED**

Run: `uv run --project agent-server pytest agent-server/tests/test_service.py agent-server/tests/test_agui_api.py -q`

Expected: constructor/lifecycle failures because service still consumes DBOS workflow operations.

- [ ] **Step 4: Implement admission/start and direct execution**

Create `self._admission_start_lock = asyncio.Lock()`. Keep mapping/context/assembly outside it.
Inside it, await `store.admit` with diagnostic config only:

```python
{"prompt_revision": self._prompt_revision, "model": self._model_id}
```

When `created` and non-terminal, synchronously call:

```python
self._supervisor.start(
    request.run_id,
    lambda token: self._execute(mapped, run_deps, token),
)
```

On `RunCapacityExceeded`, append terminal `capacity_exceeded` and re-raise. Existing identical rows
only replay; they never restart or reconcile execution.

- [ ] **Step 5: Implement the task wrapper**

```python
try:
    await self._runtime.execute(mapped, deps, token)
    if await self._store.terminal_sequence(run_id) is None:
        await self._store.append_event(
            run_id,
            RunFinishedEvent(thread_id=thread_id, run_id=run_id, outcome=RunFinishedSuccessOutcome()),
            producer_key="run:terminal",
            terminal=True,
        )
except asyncio.CancelledError:
    code = "aborted" if await self._store.is_aborted(run_id) else "server_shutdown"
    await self._append_error(run_id, code, "Run stopped")
except Exception:
    await self._append_error(run_id, "agent_failed", "Agent execution failed")
```

Consume expected task exceptions after journaling; never expose exception text.

- [ ] **Step 6: Implement abort, orphans, shutdown, and capacity HTTP expectation**

```python
async def abort(self, run_id: str, caller: AuthenticatedAgentCaller) -> None:
    await self._store.request_abort(run_id, caller)
    self._supervisor.abort(run_id)
    await self._append_error(run_id, "aborted", "Run stopped")

async def reconcile_orphans(self) -> None:
    for run_id in await self._store.nonterminal_run_ids():
        await self._append_error(run_id, "indeterminate_execution", "Agent execution ended when the server stopped.")

async def shutdown(self, *, timeout: float) -> None:
    await self._supervisor.drain(timeout=timeout)
```

Keep `stream` as PostgreSQL replay/polling only. Add API-service test expectation: capacity maps to
HTTP 503 and `Retry-After: 2`, never to a queued response.

- [ ] **Step 7: Verify GREEN and static checks**

```bash
uv run --project agent-server pytest agent-server/tests/test_service.py agent-server/tests/test_agui_api.py -q
uv run --project agent-server ruff check agent-server/src/agent_core/service.py agent-server/tests/test_service.py agent-server/tests/test_agui_api.py
uv run --project agent-server mypy agent-server/src agent-server/tests/test_service.py agent-server/tests/test_agui_api.py
```

Expected: all commands exit 0. Record Task 3 and `snapshots/task-3-before` in the SDD ledger.

---

### Task 4: Remove Workflow Persistence and Close Terminal Journals

**Files:**

- Create: `agent-server/migrations/004_local_async.sql`
- Modify: `agent-server/migrations/003_pydantic_ai.sql`
- Modify: `agent-server/src/agent_core/store/postgres.py`
- Modify: `agent-server/tests/integration/test_agent_postgres.py`
- Modify: `agent-server/tests/test_service.py`

**Interfaces:**

- Produces: `AgentRequest` without `workflow_id`.
- Removes: `load_request` and `resolve_interrupt_for_workflow`.
- Preserves authenticated interrupt resolution and all request/event replay methods.
- Produces terminal-closed `agent.append_event` behavior.

- [ ] **Step 1: Write failing schema and terminal-closure tests**

Assert `information_schema.columns` has no `agent.*.workflow_id`. Admit a run, append terminal
`RUN_ERROR`, then attempt a unique late `TEXT_MESSAGE_CONTENT`; assert `append_event` returns the
committed terminal row and replay still contains only the terminal event. Execute migrations 003
and 004 twice to prove raw-chain repeatability.

- [ ] **Step 2: Verify RED**

```bash
AGENT_TEST_DATABASE_URL="${AGENT_TEST_DATABASE_URL:-postgresql://agent:agent@localhost:54330/agent}" \
uv run --project agent-server pytest agent-server/tests/integration/test_agent_postgres.py -q
```

Expected: workflow-column and late-event assertions fail.

- [ ] **Step 3: Add migration 004**

Within one transaction:

```sql
ALTER TABLE agent.agent_interrupt
    DROP CONSTRAINT IF EXISTS agent_interrupt_workflow_id_uuid7_check,
    DROP CONSTRAINT IF EXISTS agent_interrupt_workflow_deferred_uq,
    DROP CONSTRAINT IF EXISTS agent_interrupt_origin_deferred_uq;
ALTER TABLE agent.agent_interrupt DROP COLUMN IF EXISTS workflow_id;
ALTER TABLE agent.agent_interrupt
    ADD CONSTRAINT agent_interrupt_origin_deferred_uq UNIQUE (origin_run_id, deferred_call_id);

ALTER TABLE agent.agent_request
    DROP CONSTRAINT IF EXISTS agent_request_workflow_id_uuid7_check;
ALTER TABLE agent.agent_request DROP COLUMN IF EXISTS workflow_id;
```

Replace `agent.append_event` with the migration-003 signature. After existing producer-key lookup,
return the committed terminal row and stop when `v_terminal_sequence IS NOT NULL`; otherwise retain
terminal-key validation, sequence allocation, insertion, and terminal metadata updates.

- [ ] **Step 4: Keep migration 003 repeatable after migration 004**

Guard every migration-003 constraint statement referencing `workflow_id` with an
`information_schema.columns` existence check. Running `003 -> 004 -> 003 -> 004` must succeed.

- [ ] **Step 5: Make store models and SQL runtime-neutral**

```python
@dataclass(frozen=True, slots=True)
class AgentRequest:
    run_id: str
    thread_id: str
    original_input: dict[str, Any]
    terminal_sequence: int | None
    execution_config: dict[str, Any]
```

Remove workflow columns from admit/get construction. Interrupt insert becomes `(interrupt_id,
origin_run_id, deferred_call_id, tool_call_id)` with conflict target `(origin_run_id,
deferred_call_id)`. Delete internal workflow reconstruction queries. Remove `workflow_id=` from all
test constructors and assert execution config stores only prompt revision/model.

- [ ] **Step 6: Verify GREEN and static checks**

```bash
AGENT_TEST_DATABASE_URL="${AGENT_TEST_DATABASE_URL:-postgresql://agent:agent@localhost:54330/agent}" \
uv run --project agent-server pytest agent-server/tests/integration/test_agent_postgres.py agent-server/tests/test_service.py -q
uv run --project agent-server ruff check agent-server/src/agent_core/store/postgres.py agent-server/tests/integration/test_agent_postgres.py agent-server/tests/test_service.py
uv run --project agent-server mypy agent-server/src agent-server/tests/integration/test_agent_postgres.py agent-server/tests/test_service.py
```

Expected: all commands exit 0. Record Task 4 and `snapshots/task-4-before` in the SDD ledger.

---

### Task 5: Wire Exclusive Bootstrap and Capacity Handling

**Files:**

- Replace: `agent-server/src/agent_core/bootstrap.py`
- Modify: `agent-server/src/agent_core/api/app.py`
- Modify: `agent-server/tests/test_auth_http.py`
- Modify: `agent-server/tests/test_http.py`
- Modify: `agent-server/tests/test_service_boundary.py`

**Interfaces:**

- Consumes: `ExecutionSettings`, `RunSupervisor`, `PydanticAgentRuntime`,
  `AGUIJournalProjector`, service orphan/shutdown lifecycle.
- Produces startup order `pool -> keys -> reconcile_orphans -> ready` and shutdown order
  `service.shutdown -> keys.close -> pool.close`.
- Produces HTTP 503 capacity response with `Retry-After: 2`.

- [ ] **Step 1: Write failing lifecycle and capacity tests**

Using recording components, assert:

```python
assert startup_order == ["pool.open", "pool.wait", "keys.start", "reconcile_orphans"]
assert shutdown_order == ["service.shutdown", "keys.close", "pool.close"]
```

Assert shutdown receives `ExecutionSettings.shutdown_timeout_seconds`. Add an HTTP test where
service raises `RunCapacityExceeded`; expect status 503, header `retry-after == "2"`, and body code
`capacity_exceeded`.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run --project agent-server pytest agent-server/tests/test_auth_http.py agent-server/tests/test_http.py agent-server/tests/test_service_boundary.py -q
```

Expected: lifecycle and capacity tests fail while bootstrap still launches DBOS.

- [ ] **Step 3: Construct the local graph once**

```python
execution_settings = ExecutionSettings()
pool = AsyncConnectionPool(
    database_settings.database_url,
    min_size=1,
    max_size=36,
    open=False,
)
store = PostgresAgentStore(pool)
projector = AGUIJournalProjector(store)
registry = ToolRegistry()
agent = build_deployment_agent(settings=agent_settings, registry=registry)
runtime = PydanticAgentRuntime(agent=agent, projector=projector)
supervisor = RunSupervisor(capacity=execution_settings.capacity)
service = AgentService(
    store=store,
    assembly=AgentRunAssembly(settings=agent_settings, registry=registry),
    runtime=runtime,
    supervisor=supervisor,
    context_loader=ContextLoader(),
    prompt_revision=agent_settings.prompt_revision,
    model_id=agent_settings.openrouter_model,
)
```

Delete DBOS durability, settings, configuration, launch, destroy, and persisted-run source imports.

- [ ] **Step 4: Implement lifespan and capacity response**

```python
await pool.open()
await pool.wait()
await keys.start()
await service.reconcile_orphans()
try:
    yield
finally:
    await service.shutdown(timeout=execution_settings.shutdown_timeout_seconds)
    await keys.close()
    await pool.close()
```

Handle `RunCapacityExceeded` as JSON `capacity_exceeded`, HTTP 503, `Retry-After: 2`. Do not add
leader election, advisory locks, schedulers, or background database scans.

- [ ] **Step 5: Strengthen source boundaries**

In `test_service_boundary.py`, build the retired package name as `"db" "os"` so the residue test
does not contain the literal. Assert no source import has that root. Remove the branding exception
for `sot-agent-server`, which no longer exists.

- [ ] **Step 6: Verify GREEN and static checks**

```bash
uv run --project agent-server pytest agent-server/tests/test_auth_http.py agent-server/tests/test_http.py agent-server/tests/test_service_boundary.py agent-server/tests/test_service.py -q
uv run --project agent-server ruff check agent-server/src agent-server/tests/test_auth_http.py agent-server/tests/test_http.py agent-server/tests/test_service_boundary.py
uv run --project agent-server mypy agent-server/src agent-server/tests/test_auth_http.py agent-server/tests/test_http.py agent-server/tests/test_service_boundary.py
```

Expected: all commands exit 0. Record Task 5 and `snapshots/task-5-before` in the SDD ledger.

---

### Task 6: Remove DBOS Distribution Surface and Complete Acceptance

**Files:**

- Modify: `agent-server/pyproject.toml`
- Modify: `agent-server/uv.lock`
- Modify: `agent-server/tests/test_pydantic_contract.py`
- Replace: `agent-server/tests/e2e/test_openrouter.py`
- Modify: `agent-server/README.md`
- Modify: `docs/superpowers/plans/2026-09-03-pydantic-ai-runtime-migration.md`
- Create: `agent-server/.superpowers/sdd/2026-09-04-pydantic-ai-local-async-runtime/progress.md`

**Interfaces:**

- Produces exact dependency `pydantic-ai-slim[ag-ui,openrouter]==2.38.0`.
- Produces live E2E requiring only `RUN_OPENROUTER_E2E=1`, `OPENROUTER_API_KEY`, and Agent PostgreSQL.
- Produces exclusive single-instance/recreate deployment documentation.

- [ ] **Step 1: Write failing dependency contract**

Replace DBOS imports with:

```python
from pydantic_ai import Agent, CancellationToken, DeferredToolRequests, DeferredToolResults
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.ui.ag_ui import AGUIEventStream
```

Assert parsed project dependencies contain exactly
`pydantic-ai-slim[ag-ui,openrouter]==2.38.0`. Run the contract test and expect this assertion to fail
while the `dbos` extra remains.

- [ ] **Step 2: Remove the extra and refresh the lock**

Change `pyproject.toml`, then run:

```bash
uv lock --project agent-server
uv sync --project agent-server --frozen
```

Expected: DBOS leaves the resolved tree.

- [ ] **Step 3: Rewrite live E2E without DBOS**

Construct `AGUIJournalProjector`, `PydanticAgentRuntime`, `RunSupervisor`, and `AgentService`
directly. Apply migrations 001, 003, and 004. Submit, consume `RUN_STARTED`, close the subscriber,
reconnect after its sequence, and assert exactly one start and one terminal `RUN_FINISHED`. Always
call `service.shutdown(timeout=5)` before closing the pool. Gate only on `RUN_OPENROUTER_E2E=1` and
`OPENROUTER_API_KEY`.

Add a no-provider acceptance case that inserts a non-terminal request, creates a fresh service,
calls `reconcile_orphans`, and asserts `indeterminate_execution` without calling runtime execution.

- [ ] **Step 4: Rewrite README and superseded-plan banner**

Document Pydantic ownership, local supervisor ownership, PostgreSQL journal ownership, disconnect,
abort, crash terminalization, new-run retry, single active instance, recreate rollout, and migration
chain 001/003/004. Remove DBOS database, migration command, application version, queue, worker,
claim, lease, and automatic recovery instructions. Mark the old DBOS plan superseded by this plan.

- [ ] **Step 5: Run complete verification**

```bash
TERM=dumb uv run --project agent-server pytest agent-server/tests -q
uv run --project agent-server ruff check agent-server/src agent-server/tests
uv run --project agent-server mypy agent-server/src agent-server/tests
```

Expected: all non-live tests pass; only the credential-gated OpenRouter test may skip.

- [ ] **Step 6: Run residue and lock checks**

From `agent-server`:

```bash
test -z "$(rg -n -i 'dbos' src tests README.md pyproject.toml)"
test -z "$(uv tree --offline | rg -i 'dbos')"
uv lock --check --offline
```

Expected: all exit 0. DBOS may remain only in superseded historical docs and SDD history.

- [ ] **Step 7: Run live acceptance when configured**

```bash
RUN_OPENROUTER_E2E=1 OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
uv run --project agent-server pytest agent-server/tests/e2e/test_openrouter.py -q -m e2e
```

Expected: one run survives subscriber disconnect and finishes exactly once. If the key is absent,
record the explicit skip as the only unverified external boundary.

- [ ] **Step 8: Final review and checkpoint**

Use CodeCanvas against `agent-server/src` to inspect `AgentService.submit`, `abort`,
`reconcile_orphans`, `RunSupervisor.start`, and `PydanticAgentRuntime.execute`. Confirm the only HTTP
entry points remain `/healthz`, `/ag-ui`, and `/runs/{run_id}/abort`. Record exact test counts,
static checks, residue checks, E2E status, and all rulings in the SDD ledger. Preserve snapshots and
do not claim a Git commit or merge.

---

## Plan Self-Review Result

- Spec coverage: Tasks 1–6 cover task ownership, direct Pydantic execution, projection, admission
  race closure, abort, shutdown, crash terminalization, terminal closure, schema cleanup,
  dependency removal, exclusive deployment, and acceptance evidence.
- Placeholder scan: no deferred placeholders remain; each behavior names concrete APIs, assertions,
  commands, and expected results.
- Type consistency: `ExecutionSettings`, `RunSupervisor`, `AGUIJournalProjector`,
  `PydanticAgentRuntime`, and revised `AgentService` are introduced before bootstrap/E2E consumers.
- Scope: one runtime ownership change only; no worker, queue, lease, multi-replica, or durable-recovery
  subsystem is introduced.
