# SOT Agent Vertical Slice Implementation Plan

> **ARCHIVED — DO NOT EXECUTE.** This plan is retained only as prototype history. Its embedded
> Semora gateway, `sot_agent_job`, queue worker, claim/lease/attempt state machine, direct writes
> to the Platform journal and custom Agent event contract are rejected architecture. The current
> approved design is
> [`Agent Server / AG-UI Boundary Design`](./2026-08-30-agui-agent-boundary.md).
>
> No task or code example below is an implementation instruction. A new vertical-slice plan must
> be written from the canonical design and approved before implementation begins.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 브라우저 연결과 독립적으로 Semora run을 실행하고, 끊긴 SSE가 DB journal cursor부터 delta를 복구하는 SOT Agent vertical slice를 만든다.

**Architecture:** FastAPI command는 PostgreSQL에 input과 `sot_agent_job`을 원자적으로 저장하고 즉시 `202`를 반환한다. 별도 worker가 같은 backend package 안의 `SemoraAgentGateway`로 Semora를 실행하며, Semora의 awaited `on_event`를 durable `sot_stream_event` journal에 번역한다. Branch snapshot은 canonical transcript와 journal을 cursor까지 합성하고 React가 이후 event를 SSE로 replay할 수 있게 한다.

**Tech Stack:** Python 3.12+, FastAPI, psycopg 3 async pool, PostgreSQL 16, semora 0.1 local package, Pydantic 2, pytest, pytest-asyncio, HTTPX

**Spec:** `docs/superpowers/specs/2026-08-30-sot-v1-design.md`

## Global Constraints

- Semora는 외부 HTTP service가 아니라 SOT backend가 import하는 Python package다.
- API process와 worker process는 같은 source와 PostgreSQL을 사용한다.
- `POST /messages` request와 SSE subscription의 수명을 결합하지 않는다.
- SSE disconnect와 client abort는 run을 취소하지 않는다.
- 같은 `Idempotency-Key`는 같은 `job_id`, `run_id`, `input_id`를 반환한다.
- Stream `seq`는 scope별 commit 순서와 같아야 하며 delivery는 at-least-once다.
- PostgreSQL `NOTIFY`는 wake-up 힌트이고 journal row가 source of truth다.
- `message.delta`는 batch 단위로 저장하고 completed message는 Semora transcript가 canonical source다.
- 현재 디렉터리는 Git repository가 아니므로 commit step 대신 각 task 종료 시 focused test와 전체 test를 실행한다.

---

## File Structure

```text
backend/
├── pyproject.toml                 # Python package, local Semora sources, test tools
├── src/sot/
│   ├── __init__.py
│   ├── config.py                  # environment settings only
│   ├── db.py                      # caller-owned psycopg AsyncConnectionPool
│   ├── agent/
│   │   ├── models.py              # job, run, signal, stream value types
│   │   ├── ports.py               # store, journal, gateway protocols
│   │   ├── submit.py              # durable message command
│   │   ├── semora_gateway.py      # embedded Semora adapter
│   │   └── worker.py              # claim-run-record lifecycle
│   ├── realtime/
│   │   ├── projection.py          # transcript + journal snapshot composition
│   │   └── sse.py                 # cursor replay/live generator
│   ├── store/
│   │   ├── schema.sql             # SOT + imported Semora schema
│   │   └── postgres.py            # job and journal adapters
│   ├── api/
│   │   ├── app.py                 # FastAPI factory/lifespan
│   │   └── branches.py            # message, snapshot, events, cancel routes
│   └── worker_main.py             # worker process entrypoint
└── tests/
    ├── fakes.py                   # deterministic ports, no production helpers
    ├── test_submit.py
    ├── test_journal.py
    ├── test_semora_gateway.py
    ├── test_worker.py
    ├── test_projection.py
    ├── test_api.py
    └── integration/
        ├── conftest.py
        ├── test_postgres_store.py
        └── test_reconnect.py
```

## Task 1: Backend Package and Durable Submit Contract

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/sot/__init__.py`
- Create: `backend/src/sot/agent/models.py`
- Create: `backend/src/sot/agent/ports.py`
- Create: `backend/src/sot/agent/submit.py`
- Create: `backend/tests/fakes.py`
- Test: `backend/tests/test_submit.py`

**Interfaces:**
- Produces: `SubmitMessage.execute(branch_id: UUID, prompt: str, idempotency_key: str) -> SubmitResult`
- Produces: `AgentStore.enqueue_message(...) -> SubmitResult`
- Produces: immutable `AgentJob`, `SubmitResult`, `RunStatus`, `StreamScope`, `StreamEvent`

- [ ] **Step 1: Write the failing submit test**

```python
async def test_submit_returns_one_durable_run_for_retried_command() -> None:
    store = MemoryAgentStore()
    command = SubmitMessage(store)

    first = await command.execute(BRANCH_ID, "compare both assumptions", "idem-1")
    retry = await command.execute(BRANCH_ID, "compare both assumptions", "idem-1")

    assert retry == first
    assert store.jobs == [AgentJob.from_submit(first, BRANCH_ID, "compare both assumptions")]
```

- [ ] **Step 2: Run the test and verify RED**

Run: `UV_CACHE_DIR=/tmp/sot-uv-cache uv run --project backend pytest backend/tests/test_submit.py -q`

Expected: import failure for missing `sot.agent.submit`.

- [ ] **Step 3: Add the package and minimal contracts**

```python
class AgentStore(Protocol):
    async def enqueue_message(
        self, branch_id: UUID, prompt: str, idempotency_key: str
    ) -> SubmitResult: ...

class SubmitMessage:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    async def execute(self, branch_id: UUID, prompt: str, idempotency_key: str) -> SubmitResult:
        if not prompt.strip():
            raise ValueError("prompt must not be blank")
        if not idempotency_key:
            raise ValueError("idempotency key is required")
        return await self._store.enqueue_message(branch_id, prompt, idempotency_key)
```

- [ ] **Step 4: Add blank-prompt and different-key tests, then make them pass**

Run: `UV_CACHE_DIR=/tmp/sot-uv-cache uv run --project backend pytest backend/tests/test_submit.py -q`

Expected: all submit tests pass.

## Task 2: Ordered, Idempotent Stream Journal Contract

**Files:**
- Modify: `backend/src/sot/agent/models.py`
- Modify: `backend/src/sot/agent/ports.py`
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/test_journal.py`

**Interfaces:**
- Produces: `StreamJournal.append(scope, producer_event_id, event_type, data, run_id, message_id) -> StreamEvent`
- Produces: `StreamJournal.read_after(scope, cursor, limit) -> list[StreamEvent]`
- Produces: `StreamJournal.bounds(scope) -> StreamBounds`

- [ ] **Step 1: Write failing order and producer-idempotency tests**

```python
async def test_journal_replays_committed_events_once_in_sequence() -> None:
    journal = MemoryStreamJournal()
    scope = StreamScope("branch", BRANCH_ID)
    one = await journal.append(scope, "delta-1", "message.delta", {"text": "a"})
    duplicate = await journal.append(scope, "delta-1", "message.delta", {"text": "a"})
    two = await journal.append(scope, "delta-2", "message.delta", {"text": "b"})

    assert duplicate == one
    assert [event.seq for event in await journal.read_after(scope, 0, 100)] == [1, 2]
    assert two.seq == 2
```

- [ ] **Step 2: Verify RED, implement the protocol and memory fake, then verify GREEN**

Run: `UV_CACHE_DIR=/tmp/sot-uv-cache uv run --project backend pytest backend/tests/test_journal.py -q`

- [ ] **Step 3: Add retention-floor behavior**

```python
with pytest.raises(CursorExpired):
    await journal.read_after(scope, cursor=3, limit=100)
```

The fake returns `CursorExpired(floor_seq=5)` only when `cursor < floor_seq - 1`.

## Task 3: PostgreSQL Job Queue and Stream Journal

**Files:**
- Create: `compose.yaml`
- Create: `backend/src/sot/config.py`
- Create: `backend/src/sot/db.py`
- Create: `backend/src/sot/store/schema.sql`
- Create: `backend/src/sot/store/postgres.py`
- Create: `backend/tests/integration/conftest.py`
- Test: `backend/tests/integration/test_postgres_store.py`

**Interfaces:**
- Produces: `PostgresAgentStore(pool)` implementing `AgentStore`
- Produces: `claim_next(worker_id, lease_seconds) -> AgentJob | None`
- Produces: fenced `finish_job`, `fail_job`, `request_cancel`, `cancel_requested`
- Produces: `PostgresStreamJournal(pool)` implementing `StreamJournal`

- [ ] **Step 1: Start PostgreSQL and write the failing atomic enqueue test**

```python
async def test_enqueue_is_atomic_and_idempotent(pg_store: PostgresAgentStore) -> None:
    first = await pg_store.enqueue_message(BRANCH_ID, "hello", "same-key")
    second = await pg_store.enqueue_message(BRANCH_ID, "hello", "same-key")
    assert second == first
    assert await pg_store.job_count() == 1
```

Run: `docker compose up -d db`

Run: `TEST_DATABASE_URL=postgresql://sot:sot@localhost:54329/sot UV_CACHE_DIR=/tmp/sot-uv-cache uv run --project backend pytest backend/tests/integration/test_postgres_store.py -q`

- [ ] **Step 2: Add the minimal schema**

```sql
create table sot_agent_job (
  id uuid primary key,
  branch_id uuid not null,
  run_id text not null unique,
  input_id text not null unique,
  prompt text not null,
  idempotency_key text not null unique,
  status text not null check (status in ('queued','running','completed','failed','cancel_requested','cancelled')),
  attempt bigint not null default 0,
  lease_owner text,
  lease_until timestamptz,
  cancel_requested_at timestamptz,
  created_at timestamptz not null default now()
);

create table sot_stream (
  scope_type text not null,
  scope_id uuid not null,
  next_seq bigint not null default 1,
  floor_seq bigint not null default 1,
  primary key (scope_type, scope_id)
);

create table sot_stream_event (
  scope_type text not null,
  scope_id uuid not null,
  seq bigint not null,
  id uuid not null unique,
  run_id text,
  message_id text,
  producer_event_id text not null,
  event_type text not null,
  payload jsonb not null,
  occurred_at timestamptz not null default now(),
  expires_at timestamptz,
  primary key (scope_type, scope_id, seq),
  unique (scope_type, scope_id, producer_event_id)
);
```

- [ ] **Step 3: Implement enqueue and `FOR UPDATE SKIP LOCKED` claim**

Allocate IDs in Python, insert one job in one transaction, and on unique idempotency conflict return the existing row. Claim only queued jobs or expired running leases and increment `attempt`. Terminal updates require the same `lease_owner` and `attempt`, fencing a stale worker after lease recovery.

- [ ] **Step 4: Implement stream append with scope-row serialization**

```sql
select next_seq from sot_stream
where scope_type = %s and scope_id = %s
for update;

update sot_stream set next_seq = next_seq + 1
where scope_type = %s and scope_id = %s;
```

Insert the event in the same transaction. A duplicate `(scope_type, scope_id, producer_event_id)` returns the original row without allocating another visible event.

- [ ] **Step 5: Test two concurrent appenders and expired leases**

Assert committed events replay as contiguous `[1, 2]`; assert two workers cannot own the same live lease.

## Task 4: Embedded Semora Gateway

**Files:**
- Create: `backend/src/sot/agent/semora_gateway.py`
- Test: `backend/tests/test_semora_gateway.py`

**Interfaces:**
- Consumes: local `semora.AgentRuntime`, `semora_store.ExecutionContext`
- Produces: `SemoraAgentGateway.run(job, emit, cancelled) -> AgentOutcome`
- Produces: normalized signals `message.delta`, `message.completed`, `run.suspended`, `run.failed`

- [ ] **Step 1: Write the failing adapter test with an injected runtime**

```python
async def test_gateway_translates_semora_text_and_done_events() -> None:
    runtime = ScriptedRuntime([
        {"type": "text", "text": "hel"},
        {"type": "text", "text": "lo"},
        {"type": "done", "content": "hello", "stop_reason": "completed"},
    ])
    seen: list[AgentSignal] = []
    async def collect(signal: AgentSignal) -> None:
        seen.append(signal)
    outcome = await SemoraAgentGateway(runtime, MODEL, NO_TOOLS).run(JOB, collect, never)
    assert [s.type for s in seen] == ["message.delta", "message.delta"]
    assert outcome.content == "hello"
```

- [ ] **Step 2: Verify RED and implement the adapter**

Use trusted coordinates:

```python
context = ExecutionContext(
    job.run_id,
    session_id=str(job.branch_id),
    namespace=job.conversation_id,
    subject=str(job.actor_id),
)
await runtime.run(
    context,
    model,
    tools,
    job.prompt,
    prompt_id=job.input_id,
    conversation_id=job.conversation_id,
    on_event=translate,
    aborted=cancelled,
)
```

Do not use Semora `event_sink` for text streaming; its observation contract is best-effort. Use the awaited engine `on_event`, whose failure aborts the attempt and lets the worker retry or fail visibly.

- [ ] **Step 3: Add an actual Semora scripted-model smoke test**

Use a test `BaseChatModel` that yields `AIMessageChunk(content="hel")` and `AIMessageChunk(content="lo")`. Assert the real `AgentRuntime` produces the same normalized delta sequence and completed outcome.

## Task 5: Worker Lifecycle and Delta Batching

**Files:**
- Create: `backend/src/sot/agent/worker.py`
- Create: `backend/src/sot/worker_main.py`
- Test: `backend/tests/test_worker.py`

**Interfaces:**
- Consumes: `AgentStore`, `StreamJournal`, `AgentGateway`
- Produces: `AgentWorker.run_once(worker_id: str) -> bool`
- Produces: stable producer IDs `<run_id>:<kind>:<ordinal>`

- [ ] **Step 1: Write the failing run-to-completion test**

```python
async def test_worker_persists_deltas_before_completing_job() -> None:
    gateway = ScriptedGateway([delta("hel"), delta("lo")], outcome="hello")
    worker = AgentWorker(store, journal, gateway, batch_chars=3, batch_ms=50)
    assert await worker.run_once("worker-1") is True
    assert [e.type for e in journal.events] == [
        "run.started", "message.delta", "message.delta", "message.completed", "run.completed"
    ]
    assert store.job.status is RunStatus.COMPLETED
```

- [ ] **Step 2: Implement claim, awaited journal sink, completion and failure**

The worker marks `running`, emits `run.started`, awaits every journal append, runs Semora, and writes `message.completed` plus `run.completed` before the fenced terminal job update. Before each append it renews the same owner/attempt lease; a background monitor renews during quiet model periods and caches the durable cancel flag for Semora's synchronous `aborted` predicate. Failure, explicit cancellation, and suspension each receive an honest durable terminal event/state.

- [ ] **Step 3: Add explicit cancellation and worker-crash recovery tests**

Assert SSE disconnection has no worker API and cannot cancel. Assert only `request_cancel(run_id)` makes `cancelled()` true. Assert an expired lease can be reclaimed under the same `run_id` and duplicate producer IDs do not duplicate events.

## Task 6: Consistent Branch Snapshot

**Files:**
- Create: `backend/src/sot/realtime/projection.py`
- Test: `backend/tests/test_projection.py`

**Interfaces:**
- Produces: `BranchProjectionService.snapshot(branch_id) -> BranchSnapshot`
- Snapshot contains: `messages`, `in_progress_messages`, `active_runs`, `stream_cursor`

- [ ] **Step 1: Write the failing no-gap projection test**

```python
async def test_snapshot_cursor_covers_exactly_the_folded_deltas() -> None:
    transcript = [completed_message("m1", "before")]
    events = [delta_event(1, "m2", "hel"), delta_event(2, "m2", "lo")]
    snapshot = await service.snapshot(BRANCH_ID)
    assert snapshot.in_progress_messages["m2"] == "hello"
    assert snapshot.stream_cursor == 2
```

- [ ] **Step 2: Implement one consistent-read projection**

Inside one database transaction read `next_seq - 1` as `N`, read canonical Semora transcript, read journal rows through `N`, fold only deltas for messages not present as completed transcript messages, and return `stream_cursor=N`.

- [ ] **Step 3: Test completion handoff**

When transcript contains final `m2`, snapshot must use the transcript content, ignore old `m2` deltas, and still return the cursor through the completion event.

## Task 7: FastAPI Commands, Snapshot, Cancel and SSE Replay

**Files:**
- Create: `backend/src/sot/realtime/sse.py`
- Create: `backend/src/sot/api/branches.py`
- Create: `backend/src/sot/api/app.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `create_app(container: Container) -> FastAPI`
- Produces: `POST /api/v1/branches/{branch_id}/messages`
- Produces: `GET /api/v1/branches/{branch_id}`
- Produces: `GET /api/v1/branches/{branch_id}/events`
- Produces: `POST /api/v1/runs/{run_id}/cancel`

- [ ] **Step 1: Write the failing `202` and retry contract tests**

Assert the body is `{job_id, run_id, input_id}` and the second request with the same `Idempotency-Key` returns the same body.

- [ ] **Step 2: Implement the command and snapshot routes**

Reject missing idempotency headers with `400 application/problem+json`. The route ends after durable enqueue; it never awaits `AgentGateway.run`.

- [ ] **Step 3: Write and implement SSE replay tests**

```python
events = stream_events(journal, scope, after=7, wakeup=fake_wakeup)
assert [event.seq async for event in take(events, 2)] == [8, 9]
```

The generator reads all rows after cursor before waiting. On wake-up or heartbeat it reads the DB again. `CursorExpired` yields one synthetic `stream.reset` frame and closes.

- [ ] **Step 4: Test disconnect semantics**

Cancel the SSE response task and assert the agent job remains `running`. Call the explicit cancel endpoint and assert it changes to `cancel_requested`.

## Task 8: Reconnect End-to-End Acceptance

**Files:**
- Test: `backend/tests/integration/test_reconnect.py`
- Create: `backend/README.md`

**Interfaces:**
- Verifies the whole agent slice against PostgreSQL and a real Semora runtime with a delayed scripted model.

- [ ] **Step 1: Write a failing reconnect scenario**

1. Submit a prompt and receive `run_id`.
2. Start worker and consume the first delta.
3. Disconnect the SSE client.
4. Allow the worker to write more deltas.
5. Fetch branch snapshot and note cursor `N`.
6. Reconnect with `after=N`.
7. Assert combined snapshot plus replay equals the final transcript exactly once.

- [ ] **Step 2: Make the scenario pass without timing sleeps**

Use barriers/events in the scripted model and wake-up fake. Do not use arbitrary `sleep()` for correctness.

- [ ] **Step 3: Run the complete verification suite**

```bash
UV_CACHE_DIR=/tmp/sot-uv-cache uv run --project backend ruff check backend/src backend/tests
UV_CACHE_DIR=/tmp/sot-uv-cache uv run --project backend mypy backend/src
TEST_DATABASE_URL=postgresql://sot:sot@localhost:54329/sot \
  UV_CACHE_DIR=/tmp/sot-uv-cache uv run --project backend pytest backend/tests -q
```

Expected: all checks and tests pass with no warnings.

## Plan Self-Review

- Spec coverage: browser-independent run, durable enqueue, embedded Semora, ordered journal, snapshot cursor, SSE replay, explicit cancel, recovery and tests are assigned to Tasks 1–8.
- Scope boundary: React rendering, curation, toss, consensus and main UI are deliberately outside this Agent vertical slice.
- Type consistency: `SubmitResult`, `AgentJob`, `StreamScope`, `StreamEvent`, `AgentSignal`, `AgentOutcome` are introduced before their consumers.
- Runtime correctness: Semora engine `on_event`, not best-effort lifecycle `event_sink`, carries text delta into the journal.
- Persistence correctness: scope-row sequence allocation prevents a lower uncommitted seq from appearing after a higher committed cursor.
