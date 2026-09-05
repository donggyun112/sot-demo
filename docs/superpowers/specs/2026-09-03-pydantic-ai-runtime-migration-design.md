# Pydantic AI Runtime Migration Design

> Superseded by
> [`2026-09-04-pydantic-ai-local-async-runtime-design.md`](./2026-09-04-pydantic-ai-local-async-runtime-design.md)
> for execution ownership, recovery, cancellation, queueing, and deployment topology. Retained as
> historical context for the completed intermediate DBOS migration.

> Status: approved in principle on 2026-09-03.
>
> This specification replaces the Semora-specific execution, transcript, recovery, provider, and
> interrupt details in `2026-09-03-agent-loop-design.md`. The existing Agent Server boundary remains
> authoritative for HTTP authentication, request admission, ownership, PostgreSQL AG-UI event
> replay, disconnect behavior, and the explicit abort endpoint.

## 1. Goal

Replace Semora 0.2.0 with Pydantic AI 2.38.0 and DBOS while preserving the observable Agent Server
contract:

- `POST /ag-ui` accepts the existing strict SOT profile of AG-UI `RunAgentInput`;
- execution starts independently of the SSE subscriber and survives client disconnects;
- committed AG-UI events remain replayable from PostgreSQL by sequence;
- an authenticated explicit abort is the only user action that stops a live run;
- model and tool work survives process failure and resumes without repeating a completed durable
  step;
- client-supplied tool descriptors select server-owned tools but never define executable code,
  schemas, credentials, or authority;
- OpenRouter remains the only model provider in V1.

The runtime migration removes all Semora packages, types, active writes, naming, and compatibility
tests from the Agent Server. Semora tables remain read-only for one rollback window and are removed
by the later cleanup migration described below.

## 2. Fixed boundaries

```text
React
  -> Platform Server
  -> AG-UI HTTP/SSE
  -> Agent Server
       -> PostgreSQL agent_request / agent_event / agent_interrupt
       -> DBOS workflow system tables
       -> Pydantic AI Agent
       -> OpenRouter
```

- Platform continues to own session, branch, toss, curation, consensus, and main.
- Agent Server continues to own authentication, admission, request idempotency, event replay,
  public interrupt identities, and transport errors.
- Pydantic AI owns model messages, the model/tool loop, provider integration, usage, tool approval
  primitives, and native run events.
- DBOS owns durable workflow execution, step checkpoints, restart recovery, and single-workflow
  execution identity.
- PostgreSQL `agent_event` remains the only source served to AG-UI subscribers.
- Neither Pydantic AI nor DBOS may import Platform code or read Platform storage.

## 3. Dependency contract

The runtime dependency is pinned to:

```text
pydantic-ai-slim[ag-ui,dbos,openrouter]==2.38.0
```

The direct `ag-ui-protocol>=0.1.19,<0.2` dependency remains because request admission, stored event
models, and the public API use its types directly. FastAPI, psycopg, service-auth, and the existing
supporting dependencies remain.

The following dependencies are removed:

```text
semora
semora-llm
semora-store
semora-store-pg
langchain-core when no remaining import requires it
```

An upgrade of Pydantic AI or DBOS requires the installed-package contract test, migration tests,
and the full Agent Server suite to pass before the pin moves.

## 4. Component design

### 4.1 Deployment agent and run assembly

Bootstrap creates exactly one Pydantic AI `Agent` before DBOS launches. The deployment agent has:

- the deployment-stable agent name;
- an `OpenRouterModel` configured with the deployment model and API key;
- a dynamic instructions function that reads a serializable `AgentRunDeps` value;
- one stable server-owned toolset registered before DBOS launch;
- a deterministic tool-preparation capability that exposes only the tool names selected in
  `AgentRunDeps`;
- `DeferredToolRequests` in the allowed output type when any selected tool requires approval;
- a `DBOSDurability` capability and durable event handler registered before DBOS launch.

The deployment agent name and every durable toolset ID are stable identifiers. Changing either is
a workflow compatibility change and requires draining active workflows before deployment.

`AgentRunAssembly` replaces the old per-request `AgentAssembly`. It produces only serializable run
data: trusted identity, assembled instructions, selected tool names, conversation identity,
message history, prompt or deferred results, and execution budgets. It never constructs another
Pydantic AI `Agent` after DBOS launch.

The dynamic instructions function returns the already assembled server instructions from
`AgentRunDeps`. The tool-preparation function is pure: for the same selected-name tuple it exposes
the same subset of the startup-registered tool definitions. Tool implementations that perform I/O
are explicit DBOS steps and use stable step names.

Client-provided tool descriptions and JSON schemas are not passed to Pydantic AI. The request tool
list is only an ordered name selection against `ToolRegistry`.

### 4.2 `PydanticRuntimePort`

`PydanticRuntimePort` replaces `SemoraRuntimePort`. Its public operation starts or attaches to one
DBOS workflow whose workflow ID is derived deterministically from the admitted AG-UI `runId`.

The workflow receives only the workflow/public run ID. It performs database reads through explicit
DBOS steps and keeps workflow code deterministic. The workflow:

1. loads the admitted request and serialized `AgentRunDeps` in a DBOS step;
2. converts the approved AG-UI message snapshot to Pydantic AI model messages;
3. invokes `Agent.run()` inside a DBOS workflow;
4. routes model/provider I/O through `DBOSDurability` steps;
5. sends native Pydantic AI events to the durable AG-UI projector;
6. records exactly one terminal AG-UI event.

Starting the same workflow ID is idempotent. An already-running workflow is observed rather than
duplicated. A completed workflow is never run again.

### 4.3 `DurableAGUIProjector`

`DurableAGUIProjector` replaces `DurableEventBridge`. It transforms Pydantic AI native events into
official AG-UI `BaseEvent` values and commits them through `PostgresAgentStore.append_event()`.

Projection executes as DBOS-managed event-handler steps so model deltas can be persisted while the
workflow is running. Because a DBOS step may be retried before its result is checkpointed, every
projected event carries a deterministic producer key composed from:

```text
runId + Pydantic request index + native event index + AG-UI projection kind
```

`agent_event` enforces uniqueness on `(run_id, producer_key)`. Replaying an event-handler step
therefore returns the already committed sequence instead of appending a duplicate.

The projector owns only protocol presentation state: open thinking/text messages, tool call IDs,
and terminal emission. This state is reconstructed from committed `agent_event` rows before each
retry rather than trusted to process memory. Random identifiers are generated only by the first
successful database insert and are returned on conflicting retries.

Pydantic AI's `AGUIEventStream` is used where its standalone transformation produces the required
SOT event profile. A small SOT wrapper remains responsible for deterministic producer keys,
PostgreSQL persistence, public interrupt IDs, and the existing abort/error code mapping.

### 4.4 Workflow launcher and concurrency

`RunSupervisor` is removed. `AgentService.submit()` starts the registered DBOS workflow in
background mode and does not retain an application `asyncio.Task`.

DBOS is the durable authority for whether a workflow exists, is running, completed, failed, or was
cancelled. A DBOS queue enforces the existing per-deployment concurrency budget. On reconnect,
Agent Server queries DBOS by the deterministic workflow ID instead of constructing a Semora
`Recover` command or relying on process-local state.

### 4.5 `CommandMapper`

The Semora `Prompt`, `Answer`, `Recover`, `ExecutionContext`, and LangChain history mapping is
removed.

The replacement mapper produces serializable Pydantic run input:

- AG-UI history becomes validated Pydantic AI `ModelMessage` values;
- the trailing user message becomes the new user prompt;
- the AG-UI thread ID becomes Pydantic AI `conversation_id`;
- Pydantic AI receives its own internal run ID, while the public AG-UI run ID remains the DBOS
  workflow and transport identity;
- `resume[]` becomes `DeferredToolResults` after resolving public interrupt IDs;
- reconnect is attachment to the existing DBOS workflow, not another agent command.

External `system` and `developer` messages remain rejected. Server instructions are authoritative
and are injected on every request. Client context/state remains untrusted prompt data and cannot
grant tools or alter credentials.

## 5. Persistence and schema changes

### 5.1 Retained Agent tables

`agent_request`, `agent_event`, and `agent_interrupt` remain. Their ownership and retention rules do
not change.

Semora-specific columns are renamed generically:

```text
agent_request.semora_run_id          -> workflow_id
agent_interrupt.semora_pending_id    -> deferred_call_id
agent_interrupt.semora_tool_call_id  -> tool_call_id
```

`agent_event.producer_key` becomes required for all runtime-produced events and receives a unique
constraint with `run_id`. Existing rows are backfilled with `legacy:<sequence>` before the column is
made non-null.

The migration copies existing values during the rename. Historical terminal runs remain replayable.
Non-terminal Semora-era runs are finalized as `RUN_ERROR(code="runtime_migrated")`; they are not
resumed through DBOS because their execution state is not representable safely.

### 5.2 DBOS tables

DBOS uses the configured Agent PostgreSQL instance as its system database with a separate DBOS
schema or table namespace. Application code never writes DBOS system tables directly.

DBOS schema initialization is an explicit deployment migration/startup step. Application replicas
must not race ad-hoc schema creation in production.

### 5.3 Removed Semora tables

The Semora ledger, lease, input, transcript, run, and usage tables stop receiving writes once the
new runtime deploys. They are retained for one rollback window and removed only in a later cleanup
migration after the Pydantic AI deployment is accepted.

## 6. Request and execution flow

1. Authenticate the caller and strictly admit `RunAgentInput` as today.
2. Select server-owned tools and assemble trusted instructions plus untrusted context.
3. Insert or verify `agent_request` using the canonical payload hash.
4. Derive a deterministic DBOS workflow ID from `runId`.
5. Enqueue the workflow asynchronously, or attach if it already exists.
6. Return an SSE response that only replays/subscribes to committed `agent_event` rows.
7. Project native Pydantic AI events into idempotently persisted AG-UI events.
8. Record exactly one terminal `RUN_FINISHED` or `RUN_ERROR`.
9. End subscribers after they observe the terminal sequence.

An SSE disconnect affects only step 6. It does not cancel the DBOS workflow.

## 7. Interrupt and resume flow

- A server-owned tool marked `requires_approval=True` yields Pydantic AI
  `DeferredToolRequests`.
- The projector creates or reuses a UUIDv7 public interrupt row keyed by the workflow and deferred
  call ID.
- It emits `RUN_FINISHED` with the existing AG-UI interrupt outcome.
- The next authenticated request resolves `resume[]` through `agent_interrupt` and builds
  `DeferredToolResults`.
- Approval continues the same logical conversation in a new Pydantic AI run executed under a new
  deterministic DBOS workflow ID derived from the new public AG-UI `runId`.
- The original `tool_call_id` is preserved so the resumed stream emits a result without fabricating
  a second tool-call start.

The public API follows AG-UI's multi-run resume model. Reusing a terminal interrupted `runId` with a
different payload remains an idempotency conflict.

## 8. Abort, timeout, and error mapping

`POST /runs/{runId}/abort` remains the only user-intent cancellation path.

1. Authorize ownership and commit `abort_requested_at`.
2. Cancel the matching DBOS workflow through its public handle/API.
3. If the workflow is already terminal, return success without changing the terminal event.
4. Otherwise append one `RUN_ERROR(code="aborted")` through the idempotent terminal producer key.

The whole-run deadline is enforced by the DBOS workflow timeout and checked at the Agent boundary.
Provider/model timeouts use Pydantic AI model settings. Tool timeouts wrap server tool execution.
Model-round and total-tool-call budgets are enforced through Pydantic AI hooks/capabilities.

Errors map as follows:

| Source | AG-UI result |
| --- | --- |
| explicit abort | `RUN_ERROR(code="aborted")` |
| whole-run deadline | `RUN_ERROR(code="run_timeout")` |
| round/tool budget | `RUN_ERROR(code="execution_limit_exceeded")` |
| OpenRouter or model failure | `RUN_ERROR(code="provider_error")` |
| invalid deferred transition | `RUN_ERROR(code="invalid_transition")` |
| DBOS indeterminate/corrupt workflow state | `RUN_ERROR(code="indeterminate_execution")` |
| unexpected task-boundary failure | `RUN_ERROR(code="agent_failed")` |

Error messages exposed to clients remain bounded and must not contain credentials, raw subjects,
provider request bodies, or DBOS internals.

## 9. Deployment and recovery

DBOS launches after all agents, toolsets, workflows, and event handlers are registered. Readiness is
false until PostgreSQL and DBOS initialization succeed.

Every replica registers the same stable workflow definitions. The deterministic workflow ID makes
simultaneous submissions converge on one durable execution. On process restart, DBOS resumes
incomplete workflows from its last completed step. Agent Server reconciles terminal DBOS state with
`agent_event` before serving a non-terminal reconnect.

Deployment order:

1. deploy the additive/rename Agent migration and initialize DBOS tables;
2. mark non-terminal Semora-era requests with `runtime_migrated` terminal events;
3. deploy the Pydantic AI runtime;
4. verify new execution, replay, abort, interrupt, and restart recovery;
5. retain Semora tables and the previous image for one rollback window;
6. remove Semora tables in a later, separately approved cleanup.

## 10. Testing

Tests are replaced or added at four levels.

### Unit

- AG-UI messages map to Pydantic AI messages without accepting external system/developer authority.
- caller tool descriptors select only server-owned tools.
- prompt/context ordering and escaping remain unchanged.
- native Pydantic events project to the expected ordered AG-UI events.
- repeated projection of the same producer key creates no duplicate event.
- Pydantic errors and cancellations map to fixed public codes.

### Contract

- installed Pydantic AI exposes `Agent`, `OpenRouterModel`, `AGUIEventStream`, deferred tool types,
  and `DBOSDurability` used by the service;
- Pydantic AI is pinned at 2.38.0;
- no production or test module imports Semora after the migration.

### Integration

- a request commits before the workflow starts;
- two replicas/submissions converge on one workflow and one event sequence;
- disconnecting SSE leaves execution running;
- reconnect replays from the requested sequence and continues live delivery;
- abort cancels the DBOS workflow and emits one terminal event;
- an interrupted tool resumes with the original tool call identity;
- process restart resumes an incomplete model/tool workflow;
- replay of a DBOS event-handler step does not duplicate AG-UI events.

### End-to-end

- OpenRouter model-only execution streams through PostgreSQL to AG-UI;
- one server-owned tool call executes and reports its result;
- authentication, ownership hiding, request limits, and UUIDv7 validation remain unchanged.

## 11. Acceptance criteria

The migration is accepted only when:

- all Semora dependencies, imports, migrations-at-runtime, and contract tests are removed;
- the full test suite, Ruff, and strict mypy pass;
- the existing `/ag-ui` and abort HTTP contracts remain compatible;
- SSE disconnect/reconnect, explicit abort, tool approval, and restart recovery pass integration
  tests;
- every runtime AG-UI event is idempotently persisted before subscribers can observe it;
- two concurrent replicas cannot execute the same public run twice;
- no client-provided prompt, context, state, or tool descriptor acquires server authority;
- no credentials or raw authenticated subject are persisted or returned.

## 12. Deliberate non-goals

- changing Platform product concepts or APIs;
- replacing PostgreSQL event replay with direct Pydantic AI HTTP streaming;
- introducing client-side executable tools;
- adopting Pydantic Graph for product workflows;
- adding multi-agent orchestration;
- migrating historical completed transcripts into Pydantic AI message storage;
- dropping Semora tables in the same deployment as the runtime migration.
