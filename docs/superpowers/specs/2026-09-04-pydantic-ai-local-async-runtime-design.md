# Pydantic AI Local Async Runtime Design

> Status: approved on 2026-09-04.
>
> This specification supersedes the DBOS execution, recovery, cancellation, queue, and deployment
> design in `2026-09-03-pydantic-ai-runtime-migration-design.md`. It retains the existing AG-UI
> HTTP/SSE boundary, authentication rules, server-owned tool authority, Pydantic AI mapping, and
> PostgreSQL event journal.

## 1. Decision

Agent Server is one asynchronous application instance, not a worker and not a durable workflow
engine. It starts Pydantic AI runs as process-local `asyncio.Task` objects. PostgreSQL stores
admitted requests, abort intent, authenticated interrupt mappings, and replayable AG-UI events;
it is not a job queue and contains no claim, lease, fencing, attempt, or heartbeat state.

The service guarantees that an execution outlives an HTTP/SSE subscriber while its process is
alive. It does not guarantee that an in-flight execution resumes after process loss. A run left
non-terminal by an ungraceful process exit becomes `RUN_ERROR(code="indeterminate_execution")`
on the next startup, and the user may retry with a new `runId`.

## 2. Goals

- Keep one deployment-scoped Pydantic AI `Agent` and server-owned tool registry.
- Start execution only after authenticated request admission commits.
- Keep execution independent of SSE disconnects and reconnects.
- Persist every public event in the PostgreSQL AG-UI journal before subscribers observe it.
- Support explicit authenticated abort, bounded local concurrency, and graceful shutdown.
- End every admitted run with at most one terminal event.
- Remove DBOS dependencies, configuration, system-schema operations, and runtime concepts.

## 3. Non-goals

- Durable workflow resumption after process or host loss.
- Completed-step replay, exactly-once model calls, or exactly-once tool side effects.
- A PostgreSQL-backed worker, job queue, polling claim loop, lease, fencing token, or heartbeat.
- Multiple simultaneously active Agent Server replicas.
- Automatic retry of an indeterminate execution under the same `runId`.

If high availability or cross-process recovery becomes a requirement, it requires a new design;
it must not be introduced incrementally as hidden worker state in Agent tables.

## 4. Deployment invariant

Exactly one Agent Server instance may be active against an Agent database. Deployments use a
recreate strategy: the old instance finishes shutdown before the new instance performs startup
reconciliation and becomes ready. Rolling overlap, horizontal replicas, and two local processes
sharing one Agent database are unsupported.

Readiness becomes true only after the database pool is open, authentication keys are ready,
orphan reconciliation is complete, and the local supervisor can accept executions.

## 5. Ownership

| Concern | Owner |
| --- | --- |
| Model/tool loop and deferred tool results | Pydantic AI |
| Model provider integration | Pydantic AI OpenRouter model/provider |
| Selected executable tools and credentials | Agent Server `ToolRegistry` |
| Local task lifetime, capacity, abort signal, shutdown drain | `RunSupervisor` |
| Request admission, owner binding, abort intent | PostgreSQL Agent schema |
| Official AG-UI projection and replay ordering | `AGUIJournalProjector` + PostgreSQL journal |
| HTTP authentication, SSE cursors, error responses | Agent Server API |

Rename `DurableAGUIProjector` to `AGUIJournalProjector` so its name describes committed transport
events without implying durable execution.

## 6. Components

### 6.1 `RunSupervisor`

`RunSupervisor` keeps strong references to local tasks and Pydantic AI `CancellationToken`
instances. Its public behavior is:

```python
start(run_id, execute) -> bool
contains(run_id) -> bool
abort(run_id) -> bool
drain(timeout) -> None
```

`start` is synchronous: it deduplicates a local `runId`, enforces a default capacity of 32, creates
one named task, and removes it on completion. It never reads PostgreSQL and has no recovery loop.
`abort` cancels the Pydantic token and the owned task. `drain` first allows bounded completion,
then cancels remaining tasks and awaits their cleanup.

### 6.2 `PydanticAgentRuntime`

The runtime owns the deployment `Agent` and journal projector. It exposes one awaited `execute`
operation receiving the already mapped input, `AgentRunDeps`, and cancellation token. It calls the
singleton agent directly:

```python
await agent.run(
    mapped.user_prompt,
    deps=run_deps,
    message_history=mapped.message_history,
    deferred_tool_results=mapped.deferred_tool_results,
    conversation_id=mapped.identity.conversation_id,
    run_id=mapped.identity.run_id,
    cancellation_token=token,
    event_stream_handler=project_events,
)
```

No execution input is reloaded from PostgreSQL. There is no runtime status query, workflow ID,
queue, decorator registration, or application version compatibility key.

### 6.3 `AgentService`

`AgentService` remains the application orchestrator. It validates and maps the request, loads
context, assembles trusted run dependencies, admits the request, and starts the local task only
when admission created a new row. An existing identical `runId` only replays/subscribes; it never
starts a second execution.

A process-local admission/start lock covers the awaited database admission and synchronous
supervisor registration. This closes the same-process race where a simultaneous duplicate could
observe a committed non-terminal row before the creator registered its task. Mapping, context
loading, and prompt assembly remain outside the lock.

The task wrapper owns terminal error mapping. Expected provider, validation, policy, cancellation,
and timeout failures become bounded public `RUN_ERROR` events and do not escape as unobserved task
exceptions.

### 6.4 PostgreSQL journal

`agent_request` and `agent_event` remain canonical for transport replay. Producer keys stay
deterministic and `run:terminal` remains the only terminal producer key.

The append function becomes terminal-closed: after a terminal sequence exists, a repeated producer
key returns its existing event and any new producer key returns the committed terminal event
without appending. This prevents late Pydantic events racing with abort or shutdown from appearing
after the terminal event.

## 7. Execution lifecycle

1. Authenticate the caller and validate canonical AG-UI input.
2. Map messages/resume data, load request context, and assemble trusted run dependencies.
3. Insert `agent_request` and commit.
4. If the row is new, synchronously register one local task with `RunSupervisor`.
5. Append `RUN_STARTED` using producer key `run:started` before the model call.
6. Invoke `PydanticAgentRuntime.execute` once.
7. Project and await each Pydantic AI event append.
8. Persist exactly one `RUN_FINISHED` or `RUN_ERROR`.
9. Remove the task from the supervisor.

If local capacity is exhausted after admission, the service writes
`RUN_ERROR(code="capacity_exceeded")` and returns HTTP 503 with `Retry-After: 2`. It does not leave
an admitted non-terminal request behind.

The SSE generator only polls/replays PostgreSQL. Closing the generator never touches the task or
cancellation token.

## 8. Abort, shutdown, and crashes

### Explicit abort

The abort endpoint authenticates ownership, persists `abort_requested_at`, asks the supervisor to
cancel the local token/task, and appends `RUN_ERROR(code="aborted")` idempotently. A request for an
already terminal run is successful and changes nothing. A valid owned run with no local task is
also terminalized as aborted.

The task wrapper catches `asyncio.CancelledError`. It reads the already-persisted abort intent:
an explicit abort maps to `aborted`; shutdown cancellation without abort intent maps to
`server_shutdown`. It writes the terminal event idempotently and consumes the cancellation so the
supervisor never leaves an unobserved task exception.

### Graceful shutdown

The application stops accepting traffic and drains local tasks for a bounded interval while the
database pool remains open. Tasks still active after the interval are cancelled and terminalized
as `RUN_ERROR(code="server_shutdown")`. Only then are authentication and database resources
closed.

### Ungraceful process loss

On startup, before readiness, every non-terminal request from the previous process is terminalized
as `RUN_ERROR(code="indeterminate_execution")`. No model or tool call is resumed, reconstructed,
or automatically retried. This operation is safe only because the deployment invariant forbids an
overlapping live instance.

## 9. Persistence changes

Add a forward-only migration after `003_pydantic_ai.sql` that:

- removes `workflow_id` from active Agent request and interrupt records;
- keys interrupt idempotency by `(origin_run_id, deferred_call_id)`;
- makes the event append function terminal-closed;
- retains prior runtime tables only as rollback material for the documented rollback window.

`execution_config` retains diagnostic `prompt_revision` and `model` values only. Persisted subject,
rendered instructions, and selected tool names are removed because this runtime never reconstructs
an execution after process loss.

The DBOS system schema is not accessed by the application. Operators may remove it after the
rollback window; the application migration does not drop an externally owned schema.

## 10. Dependency and configuration cleanup

- Change the runtime dependency to `pydantic-ai-slim[ag-ui,openrouter]` at the existing pin.
- Remove DBOS imports, configuration, queue/workflow names, lifecycle calls, and environment
  variables.
- Remove `AGENT_DBOS_SYSTEM_DATABASE_URL` and DBOS migration instructions from deployment docs.
- Add or retain only local execution capacity and shutdown timeout settings.
- Keep `migrations/002_semora.sql` unchanged as rollback-only history.

## 11. Security and tool behavior

Authentication, opaque owner hashing, server-owned tool definitions, request tool-name filtering,
and untrusted context rendering do not change. V1 tools remain non-mutating/read-oriented. Because
model and tool calls may have happened before a process crash, callers must not infer that an
`indeterminate_execution` had no external effects.

## 12. Verification

Focused tests must prove:

- the local task survives SSE disconnect and completes into the PostgreSQL journal;
- identical same-process submissions start at most one local task;
- capacity exhaustion writes a terminal error;
- explicit abort records intent before cancelling and produces one terminal event;
- provider failure and task cancellation cannot leave a live SSE stream waiting forever;
- late events cannot append after a terminal event;
- graceful shutdown drains or terminalizes every owned task;
- startup reconciliation terminalizes pre-existing non-terminal rows without executing them;
- deferred approval/resume still maps and runs through Pydantic AI;
- source, lockfile, configuration, README, and tests contain no active DBOS references.

The live OpenRouter acceptance test requires only the provider key and Agent PostgreSQL database.
It disconnects after `RUN_STARTED`, reconnects by event cursor, and observes exactly one terminal
event. A separate crash test inserts a non-terminal request, constructs a fresh application, and
asserts startup reconciliation emits `indeterminate_execution` without invoking the model.

## 13. Acceptance invariants

- One admitted run creates no more than one process-local task.
- One run has monotonically ordered events and at most one terminal event.
- No event is appended after a terminal event.
- Subscriber lifetime never controls execution lifetime.
- Only explicit abort, execution completion/failure, graceful shutdown, or next-start orphan
  reconciliation terminalizes a run.
- No application code polls PostgreSQL for executable work.
- No application code claims, leases, fences, resumes, or retries execution after process loss.
