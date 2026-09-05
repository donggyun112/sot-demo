# Agent Loop Design

> Superseded by
> [`2026-09-03-pydantic-ai-runtime-migration-design.md`](./2026-09-03-pydantic-ai-runtime-migration-design.md).
> Retained only as historical context for the retired runtime.

> Status: approved on 2026-09-03.
>
> This specification is canonical for Agent Server execution. It supersedes the command routing,
> event guarantees, model recovery, prompt/provider and Semora integration details in
> `../plans/2026-08-30-agui-agent-boundary.md`. The boundary document remains canonical for HTTP,
> authentication, Agent-owned transport persistence and SSE/Redis mechanics.

## 1. Goal

Build one reusable Agent Server that accepts the official AG-UI `RunAgentInput`, runs one logical
agent through the released Semora runtime, and returns official AG-UI events. The execution must
outlive an SSE connection, while an explicit authenticated abort remains the only user action that
stops a live run.

This is a discussion and claim-generation service. It requires correct idempotency, reconnect and
explicit stop behavior, but it does not require payment-grade automatic recovery.

## 2. Fixed boundaries

```text
React
  -> Platform Server
  -> AG-UI HTTP/SSE
  -> Agent Server
  -> Semora
  -> OpenRouter
```

- Platform owns product concepts such as session, branch, toss, curation, consensus and main.
- Agent Server knows only AG-UI IDs/input, authenticated opaque ownership and its own transport
  records.
- Semora owns the model/tool loop, execution ledger, input lifecycle, lease/fencing, recovery,
  transcript, run metadata and model usage.
- OpenRouter is the only model provider in V1.
- The Agent Server never imports Platform code or reads Platform storage.
- The Platform never imports Agent/Semora code or reads Agent/Semora storage.

## 3. Released Semora contract

The runtime dependency is exactly:

```text
semora[postgres,openrouter]==0.2.0
```

Agent Server uses only public Semora 0.2.0 APIs:

- `Agent` as the executable declarative agent definition;
- `AgentRuntime.dispatch()` as the only execution entry point;
- `Prompt`, `Answer` and `Recover` as host commands;
- `ExecutionContext` for trusted run and subject identity;
- `PostgresSteps` and `PostgresTranscript` from `semora-store-pg`;
- `ControlPlane` hooks for bounded execution and tool-result observation;
- `Contended`, `Fenced`, `Indeterminate` and `InvalidTransition` as typed outcomes;
- the `aborted` predicate for cooperative stop.

Agent Server must not call `react_loop()`, choose directly among `run()`/`resume()`/`recover()`,
call `force_retry()`, access a private Semora member, or write a Semora table directly. An upgrade
from 0.2.0 requires the installed-package contract suite to pass before the dependency pin moves.

## 4. Agent declaration

There is no SOT `AgentRecipe`, `AgentSpec` or runtime registry. One deployment represents one
logical agent. Deployment configuration provides:

- `AGENT_NAME` and `AGENT_DESCRIPTION`;
- required `AGENT_SYSTEM_PROMPT_FILE`, read as UTF-8 during startup;
- required `AGENT_PROMPT_REVISION`;
- required `AGENT_OPENROUTER_MODEL`;
- `OPENROUTER_API_KEY` as a secret;
- an Agent-owned Python tool registry.

For each new execution, `AgentAssembly` creates a Semora `Agent` with the fixed name,
description and model, the request-selected subset of server tools, and that run's assembled
system prompt. Constructing a per-run `Agent` is configuration of the Semora declaration, not a
second agent contract.

## 5. Components

```text
AdmittedRunAgentInput
  -> CommandMapper
  -> ContextLoader
  -> PromptAssembly
  -> AgentAssembly
  -> SemoraRuntimePort
  -> DurableEventBridge
  -> Agent event journal
```

### 5.1 `CommandMapper`

Maps a validated AG-UI request to exactly one Semora `Prompt`, `Answer` or internal `Recover`.
It also produces LangChain/Semora history, the trusted `ExecutionContext`, and the public-to-
Semora interrupt resolution. It contains no Platform type or product rule.

### 5.2 `ContextLoader`

Normalizes caller-supplied AG-UI context/state together with records loaded from Agent-owned
context sources. Sources receive only the trusted opaque Semora `ExecutionContext`; they do not
receive or interpret Platform product concepts. The loader validates the merged value as canonical
JSON data and stamps every Agent-owned record with its server-registered source name.

It does not render prompts, select models or tools, execute the agent, or read Platform storage.

### 5.3 `PromptAssembly`

Produces the immutable system-prompt string used by the Semora `Agent`. It does not call a model,
select tools or persist events.

### 5.4 `AgentAssembly`

Constructs the Semora `Agent` from deployment identity, the OpenRouter model, selected server
tools and assembled prompt. It does not execute the agent.

### 5.5 `SemoraRuntimePort`

Exposes one operation equivalent to:

```python
await runtime.dispatch(execution_context, agent, command, controls=controls, **options)
```

No other component imports Semora execution methods.

### 5.6 `RunSupervisor`

Keeps strong references to local `asyncio.Task` and stop signals. It starts work immediately after
request admission commits, deduplicates tasks inside one process, and removes completed tasks.
It is not durable authority and contains no queue, polling claim loop, attempt counter or lease.

### 5.7 `DurableEventBridge`

Translates awaited Semora execution callbacks and host lifecycle transitions into official AG-UI
events. It appends an event to PostgreSQL before making it visible to Redis/SSE subscribers.

### 5.8 `RuntimeObservationSink`

Accepts Semora `EventEnvelope` values from `event_sink` for logs and metrics. Delivery is
best-effort. These observations are not required to reconstruct an AG-UI run and are not streamed
as `RAW` events by default.

## 6. Input profile and command mapping

The official AG-UI schema remains the wire contract. The SOT profile narrows it as follows:

- `threadId`, `runId` and message IDs must be canonical UUIDv7 values;
- external `system` and `developer` messages are rejected with
  `422 unsupported_message_role`;
- a normal request must end with one user message and have an empty `resume`;
- prior user/assistant/tool messages are the desired history;
- the trailing user text becomes `Prompt(text, prompt_id=<message id>)`;
- `resume[]` resolves public interrupt IDs and becomes Semora `Answer` commands;
- `Recover` is internal and can only be selected on same-run reconnect;
- `forwardedProps` cannot change the model, prompt identity, credentials or authority.

`RunAgentInput.messages` is a conversation snapshot. The mapper preserves AG-UI message IDs when
creating LangChain messages. Semora's public transcript replacement retains the common prefix,
rewinds divergence and appends the desired history. A changed message snapshot therefore requires
a new `runId`; it is never an idempotent replay of an existing run.

## 7. Prompt assembly

The model-visible order is:

```text
1. server base system prompt
2. server behavior and safety policy
3. server-owned instructions for the selected tools
4. request context/state encoded as an explicitly untrusted data block
5. mapped conversation history
6. trailing user Prompt
```

`context` and `state` may inform an answer but cannot grant a tool, change a credential, alter a
model or bypass a control. Tool enforcement remains outside the prompt.

Prompt Assembly renders once before a new run starts and passes a plain string as
`Agent.system_prompt`; V1 does not use a dynamic `SystemPromptSource`. Agent persistence records
only the prompt revision and model ID for diagnosis; it does not duplicate the rendered prompt.
Demand-driven recovery uses the currently deployed compatible Agent declaration. This service
accepts that a recovery after a deployment may use a newer model or prompt revision rather than
maintaining a historical runtime-config archive.

## 8. Tool selection

Actual tool implementations, schemas, credentials and execution belong to Agent Server/Semora.
`RunAgentInput.tools` is a selection request:

- each unique `tools[].name` must exist in the deployment's registry;
- unknown and duplicate names receive `422 invalid_tool_descriptor`;
- the server-owned description and input schema are passed to Semora;
- caller-provided descriptions and parameter schemas never replace server definitions;
- an empty list creates a model-only Semora `Agent`;
- V1 has no client-side tool execution and no request-supplied tool credentials, code or endpoint;
- V1 tools are non-mutating/read-oriented.

V1 does not install `semora-permissions`. The selected tool subset is the executable authority.
A future mutating tool catalog requires a separate policy design before it can be enabled.

## 9. Execution budgets

The host composes a small `ControlPlane` with fixed defaults captured in request diagnostic
metadata:

| Budget | Default |
| --- | ---: |
| model rounds | 16 |
| total tool calls | 32 |
| one tool call | 60 seconds |
| one model invocation | 5 minutes |
| whole active run | 15 minutes |

`before_model` enforces the model-round and wall-clock limits. Tool execution enforces total-call
and per-call limits. A round/tool budget stop becomes `Halt("policy")` internally and
`RUN_ERROR(code="execution_limit_exceeded")` externally. Wall-clock expiry records
`deadline_exceeded_at`, sets the cooperative stop signal and becomes
`RUN_ERROR(code="run_timeout")`.

## 10. Normal execution

1. Authenticate and admit `RunAgentInput`.
2. Insert `agent_request` and commit before execution starts.
3. Register a detached local task with `RunSupervisor`.
4. Append host `RUN_STARTED` to the Agent event journal.
5. Assemble the prompt, selected tools, Semora `Agent`, `ExecutionContext` and command.
6. Call `AgentRuntime.dispatch()` once.
7. Await every correctness-bearing event-journal append.
8. Append exactly one terminal `RUN_FINISHED` or `RUN_ERROR`.
9. Remove the local task; subscribers close after observing the terminal sequence.

The HTTP/SSE generator only replays and subscribes. Disconnecting it removes that subscriber and
never cancels the task.

## 11. Data ownership

### 11.1 Semora PostgreSQL

Agent Server installs and uses the schemas shipped by `semora-store-pg`:

- `ledger_step` for durable effects;
- `ledger_run_lease` for lease/fencing;
- `ledger_input` for durable inputs;
- `ledger_transcript` for append-only conversation entries;
- `ledger_run` for Semora run metadata;
- `ledger_run_model` for model usage.

These tables are accessed only through `PostgresSteps`, `PostgresTranscript` and Semora runtime
APIs. Agent Server does not create a transcript, checkpoint, tool-result, execution-state or usage
mirror.

### 11.2 Agent PostgreSQL

Agent-owned tables cover only the transport boundary:

- `agent_request`: payload idempotency, trusted owner, original input needed for reconnect,
  Semora run mapping, diagnostic model/prompt/tool names, abort/deadline and terminal summary;
- `agent_event`: ordered official AG-UI events used for SSE replay;
- `agent_interrupt`: public interrupt ID to opaque Semora pending ID mapping.

### 11.3 Redis

Redis Stream is a bounded hot/live cache of committed `agent_event` rows. PostgreSQL remains
canonical. A publish failure does not fail a run; subscribers reconcile by sequence from
PostgreSQL. Redis is never a queue, execution lock or ownership mechanism.

## 12. AG-UI event projection

| Source | AG-UI projection |
| --- | --- |
| host accepted execution | `RUN_STARTED` |
| Semora `thinking` | `THINKING_TEXT_MESSAGE_START/CONTENT/END` |
| Semora `text` | `TEXT_MESSAGE_START/CONTENT/END` |
| Semora `tool_call` | `TOOL_CALL_START/ARGS/END` |
| awaited post-tool observation | `TOOL_CALL_RESULT` |
| Semora suspension | `RUN_FINISHED` with interrupt outcome |
| Semora normal done | `RUN_FINISHED` with success outcome |
| failure, budget or timeout | `RUN_ERROR` |

Normal streaming does not emit repeated `MESSAGES_SNAPSHOT` events. A reconnect replays events
after its cursor. If the cursor has expired or a process recovery needs to repair presentation,
the adapter creates one `MESSAGES_SNAPSHOT` from `PostgresTranscript` and continues from there.

`agent_event` is a transport journal, not another transcript. Retention may remove old transport
deltas after a terminal run because Semora transcript remains the final-message source.

## 13. Idempotency and task ownership

- new `runId`: insert the request and attempt to start a task;
- existing `runId` with the same canonical payload hash: replay/subscribe;
- existing `runId` with a different payload hash: `409 idempotency_conflict`;
- existing run owned by a different authenticated subject: hidden `404`;
- simultaneous replicas may both attempt dispatch, but Semora lease/fencing is the only durable
  execution arbiter;
- Semora `Contended` means subscribe to the existing run, not emit `RUN_ERROR`.

No Agent table contains queued/running/claimed state, an execution attempt, lease owner or lease
expiry.

## 14. Demand-driven recovery

There is no periodic recovery scanner.

On an authenticated same-run reconnect with no local task and no Agent terminal event:

| Semora state/outcome | Host action |
| --- | --- |
| `fresh` | dispatch the stored original `Prompt`/`Answer` |
| `interrupted` | dispatch internal `Recover` |
| waiting/suspended | restore the persisted public interrupt outcome |
| completed | create final snapshot/terminal projection from transcript/run metadata |
| `Contended` | subscribe because another replica is active |
| `Fenced` | stop the stale local task and subscribe |
| `Indeterminate` | terminate with `RUN_ERROR(code="indeterminate_execution")` |

The host never calls `force_retry()`. A user may retry an indeterminate discussion turn with a
new `runId`.

## 15. Provider failures

Semora `ModelFailurePolicy` allows at most one retry for rate-limit, server or network failure
before any output is visible. A provider failure after visible output is not retried because it
would duplicate text. Context overflow is not automatically compacted in V1 and becomes
`RUN_ERROR(code="context_limit_exceeded")`. Authentication and invalid-request provider errors
fail immediately.

## 16. Explicit abort

`POST /runs/{runId}/abort` is authenticated and idempotent:

1. verify owner and `agent:abort` scope;
2. set `agent_request.abort_requested_at` in PostgreSQL and commit;
3. set a matching local stop event when present;
4. publish a best-effort Redis abort hint for another replica;
5. active replicas also reconcile their run IDs against PostgreSQL once per second;
6. expose the local event through Semora's synchronous `aborted` predicate.

User abort is not implemented with `Task.cancel()`. It becomes `RUN_ERROR(code="aborted")`, which
the Platform/UI presents as a neutral user stop. SSE disconnect, browser refresh, process shutdown
and deadline expiry are not user aborts.

## 17. Process lifecycle

Startup constructs one PostgreSQL pool, `PostgresSteps`, `PostgresTranscript`, OpenRouter model,
tool registry, configured `AgentRuntime` and `RunSupervisor`. Migrations run outside application
replicas.

On SIGTERM the server becomes unready, rejects only new runs, and drains current tasks/subscribers
for 35 seconds. Remaining infrastructure tasks may then be cancelled without setting user abort.
An interrupted Semora run is handled by demand-driven recovery on the next reconnect.

Readiness requires valid deployment configuration, PostgreSQL, compatible schemas, an OpenRouter
credential and usable authentication keys. Redis failure is degraded but ready because DB replay
is the fallback. Readiness never calls OpenRouter.

## 18. Required acceptance tests

The test suite must exercise the installed Semora 0.2.0 package, not import the sibling Semora
repository.

- construct the declared `Agent` and dispatch a scripted model-only prompt;
- dispatch a tool call and project `TOOL_CALL_*` plus `TOOL_CALL_RESULT`;
- suspend and resume through public interrupt mapping;
- reject external system/developer messages and unknown tools;
- preserve common-prefix transcript history for a new run;
- repeat the same `runId` without starting a second execution;
- reject a same-ID/different-payload request;
- disconnect SSE while the detached task completes;
- reconnect from an event cursor and merge replay/live sequences without duplicates;
- fall back to PostgreSQL when Redis is unavailable;
- route `Contended` to subscription;
- recover a process-interrupted run only after reconnect;
- terminate `Indeterminate` without `force_retry`;
- deliver cross-replica explicit abort through Redis hint and DB fallback;
- retry one pre-output transient provider failure and never retry partial output;
- emit one terminal event under completion/error/abort races;
- drain shutdown without recording user abort.

## 19. Explicit exclusions

- a queue-backed Agent worker;
- Agent-owned execution claim/lease/attempt state;
- a second agent loop or graph engine;
- a custom serialized agent recipe/manifest;
- a runtime multi-agent registry;
- duplicated Semora transcript/checkpoint/usage storage;
- automatic `force_retry` or abandoned-run scanner;
- lossless Semora `event_sink` delivery;
- request-selected model/provider or external tool implementation;
- mutating V1 tools;
- Platform product concepts inside Agent Server.
