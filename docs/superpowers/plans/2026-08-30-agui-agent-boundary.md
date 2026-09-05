# Agent Server / AG-UI Boundary Design

> Status: canonical, incrementally approved on 2026-08-31.
>
> This document supersedes the Agent ownership, worker, queue and streaming sections of
> `2026-08-30-agent-vertical-slice.md`. Only decisions explicitly approved in the design
> conversation are recorded here. Undecided items are listed at the end instead of being guessed.
>
> The approved Agent execution loop is specified in
> [`2026-09-03-agent-loop-design.md`](../specs/2026-09-03-agent-loop-design.md). That specification
> supersedes this document wherever command dispatch, Semora storage, event guarantees, prompt
> assembly or recovery policy differs.

## 1. Scope

SOT has a Platform Server and an Agent Server with a hard network boundary.

```text
React
  │ Platform API / Platform SSE
  ▼
Platform Server
  │ AG-UI HTTP/SSE
  ▼
Agent Server
  │ Python API
  ▼
Semora
```

The Platform owns session, branch, toss, curation, proposal, consensus, main and product
authorization. The Agent owns an AG-UI request, its Semora execution and its own request,
transcript and event records. Neither server imports the other server's package or reads the
other server's database.

Semora is installed only in Agent Server. Agent Server does not know any Platform domain type
or identifier.

## 2. One server is one agent

One deployed Agent Server represents one logical agent. It does not host a registry of agents and
does not select an `agentKey` at runtime.

Multiple replicas of the same Agent Server are replicas of the same logical agent and share the
same Agent PostgreSQL, Redis and Semora stores. Reusability means that the same server
implementation can be configured and deployed as another independent agent. The Platform chooses
which independent Agent Server endpoint to call.

The following do not exist:

- `/agents/{agentKey}/...`
- `agent_request.agent_key`
- a runtime multi-agent registry
- an agent recipe added to `RunAgentInput`

## 3. Public Agent interface

The invocation contract is the official AG-UI contract.

```http
POST /ag-ui
Content-Type: application/json
Accept: text/event-stream

RunAgentInput -> BaseEvent SSE
```

The only currently approved management extension is explicit abort:

```http
POST /runs/{runId}/abort
```

The invocation body remains an official `RunAgentInput`. No private cursor, recipe, Platform ID
or recovery command is added to it. Reattaching repeats the exact same POST and body.

## 4. Identity mapping

- AG-UI `threadId` maps to Semora `conversation_id`.
- A new normal AG-UI `runId` is the Agent invocation ID and the new Semora `run_id`.
- A resumed AG-UI invocation has a new AG-UI `runId`, while `interruptId` resolves the original
  Semora run that must receive the answer.
- `Recover` is an Agent Server decision and is never accepted as client input.

### 4.1 UUID profile

Every identifier created by SOT or Agent Server uses RFC 9562 UUIDv7 when the corresponding
protocol field permits it. This includes Platform session/branch bindings and AG-UI `threadId`,
`runId` and message IDs, plus Agent-generated event IDs and public interrupt IDs. UUIDv7 is
generated in application code; PostgreSQL 16 stores it in the native `uuid` type but is not the
generator.

The SOT AG-UI profile requires canonical hyphenated UUIDv7 values for `threadId`, `runId` and
message IDs. Agent Server rejects a new request that violates this profile with `422
invalid_identifier`. It does not rewrite an accepted caller ID, because rewriting would break
idempotency and resume references.

Semora/provider-owned identifiers that are not created at this boundary remain opaque text. In
particular, Semora pending/tool-call IDs and OpenRouter response/model IDs are preserved exactly.
Agent Server exposes a newly generated UUIDv7 `interruptId` and stores the opaque Semora pending
ID behind that public ID.

The initial request is stored with a payload hash.

- same `runId`, same payload: attach to the live execution or replay its records;
- same `runId`, different payload: idempotency conflict;
- new `runId`: a new invocation.

## 5. Command routing

`AgentRuntime.dispatch()` is the only Semora execution entry point. Agent Server does not choose
directly among `run()`, `resume()` and `recover()` and never calls the bare `react_loop()`.

For a new normal request, an empty `resume` plus a trailing user message becomes a Semora
`Prompt`. Prior messages are supplied as history, and the user message ID is preserved as the
Semora prompt ID. External `system` and `developer` messages are rejected by the Agent profile.

For `resume[]`, every `interruptId` is resolved to the original Semora run. A `resolved` or
`cancelled` entry becomes the corresponding Semora `Answer`. AG-UI interrupt cancellation means
declining an interrupt; it is not a request to abort the currently executing run.

For an existing request:

```text
local task exists                   -> subscribe
terminal Agent event exists         -> replay
no local task + Semora fresh        -> dispatch the stored original command
no local task + Semora interrupted  -> dispatch internal Recover
Semora waiting                      -> restore the persisted interrupt outcome
Semora completed                    -> repair terminal presentation from transcript
Semora Contended                    -> another replica owns it; subscribe
```

## 6. Execution ownership

The Agent Server process owns the asynchronous Semora task. The HTTP/SSE generator is only a
subscriber and never owns or cancels execution.

There is no request queue consumer, Agent worker, claim loop, request lease, attempt counter or
Agent-owned execution state machine. Semora already owns durable execution semantics.

In a multi-replica deployment, every process uses a unique Semora owner value such as
`pod-id:process-uuid`. Shared `semora-store-pg` run leases and fencing tokens are the sole
execution ownership mechanism.

- lease acquisition succeeds: this replica executes or recovers;
- `Contended`: another live replica owns the run, so this replica subscribes;
- an expired lease may be acquired with a newer fencing token;
- stale writes from an old owner are rejected by Semora fencing.

Redis is never an execution lock.

## 7. Connection lifecycle

Transport detachment and execution cancellation are different operations.

```text
refresh / tab close / network loss / SSE disconnect
-> remove subscriber only
-> Semora execution continues

explicit Stop button
-> Platform sends an authenticated abort command
-> Agent Server records abort intent
-> Semora receives its existing aborted predicate
-> Semora records done(stop_reason="aborted")
```

The task is not force-cancelled with `asyncio.Task.cancel()`. Abort is idempotent. A previously
recorded abort prevents process-failure recovery from starting the run again.

AG-UI currently has no standard `RUN_CANCELLED`. The compatible terminal mapping is
`RUN_ERROR(code="aborted")`; the UI renders it as a neutral user stop. Semora's transcript and
run metadata retain the canonical stop reason.

## 8. Process failure and recovery

An SSE disconnect does not require recovery because the original process continues execution. A
process failure destroys its in-memory task. V1 recovery is demand-driven:

1. Platform re-POSTs the same `RunAgentInput` and `runId`.
2. Agent Server replays the persisted Agent events.
3. If no local task exists, Agent Server dispatches the stored original command for a fresh run
   or internal `Recover` for an interrupted run.
4. If the old lease has not expired, `Contended` is treated as subscription and the
   reconnect-triggered recovery coroutine may retry after lease expiry.

There is no periodic scanner that recovers runs with no reconnecting caller.

SOT is a discussion and claim-generation product, not a critical external-mutation service.
Accordingly:

- explicit user abort is never retried;
- V1 non-mutating/read-oriented tools may use Semora recovery;
- an `Indeterminate` execution terminates with `RUN_ERROR(code="indeterminate_execution")`;
- critical mutating tools are excluded until they have a stricter retry policy.

## 9. Recovery presentation

An internal recovery remains inside the same AG-UI `runId`. It does not emit another
`RUN_STARTED`.

Simple transport reattachment continues the existing `messageId` after the last event sequence.
Process recovery instead performs the following presentation repair:

1. preserve pre-crash partial events in the Agent audit journal;
2. emit `MESSAGES_SNAPSHOT` from the committed Semora conversation;
3. stream recovered output under a new `messageId` when Semora can recover safely;
4. emit exactly one terminal `RUN_FINISHED` or `RUN_ERROR` for the whole run.

No attempt-status table is required for this UI behavior; the ordered event journal is the audit
record.

## 10. Agent persistence

Agent Server owns request identity, public interrupt mapping and its AG-UI transport journal in
addition to Semora's own stores. PostgreSQL 16 is the canonical store. The initial migration uses
the following schema; application code supplies every UUIDv7 value.

```sql
CREATE SCHEMA IF NOT EXISTS agent;

CREATE TABLE agent.agent_request (
    run_id                 uuid PRIMARY KEY,
    thread_id              uuid NOT NULL,
    semora_run_id          uuid NOT NULL,
    request_kind           text NOT NULL
                           CHECK (request_kind IN ('prompt', 'resume')),
    owner_issuer           text NOT NULL,
    owner_subject_hash     bytea NOT NULL
                           CHECK (octet_length(owner_subject_hash) = 32),
    original_input         jsonb,
    payload_hash           bytea NOT NULL
                           CHECK (octet_length(payload_hash) = 32),
    execution_config       jsonb,
    next_event_sequence    bigint NOT NULL DEFAULT 1
                           CHECK (next_event_sequence > 0),
    abort_requested_at     timestamptz,
    deadline_exceeded_at   timestamptz,
    terminal_sequence      bigint,
    terminal_at            timestamptz,
    terminal_event         jsonb,
    replay_expires_at      timestamptz,
    tombstone_expires_at   timestamptz,
    redacted_at            timestamptz,
    created_at             timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (substring(run_id::text FROM 15 FOR 1) = '7'),
    CHECK (substring(thread_id::text FROM 15 FOR 1) = '7'),
    CHECK (substring(semora_run_id::text FROM 15 FOR 1) = '7'),
    CHECK (execution_config IS NULL OR jsonb_typeof(execution_config) = 'object'),
    CHECK (original_input IS NULL OR jsonb_typeof(original_input) = 'object'),
    CHECK ((terminal_sequence IS NULL) = (terminal_at IS NULL)),
    CHECK ((terminal_at IS NULL AND terminal_event IS NULL)
        OR (terminal_at IS NOT NULL AND terminal_event IS NOT NULL)),
    CHECK (terminal_sequence IS NULL OR terminal_sequence > 0),
    CHECK (
        (redacted_at IS NULL
            AND original_input IS NOT NULL
            AND execution_config IS NOT NULL)
        OR
        (redacted_at IS NOT NULL
            AND original_input IS NULL
            AND execution_config IS NULL)
    )
);

CREATE INDEX agent_request_owner_created_idx
    ON agent.agent_request (owner_subject_hash, created_at DESC);
CREATE INDEX agent_request_terminal_cleanup_idx
    ON agent.agent_request (replay_expires_at, run_id)
    WHERE terminal_at IS NOT NULL;

CREATE TABLE agent.agent_event (
    run_id          uuid NOT NULL
                    REFERENCES agent.agent_request(run_id) ON DELETE CASCADE,
    sequence        bigint NOT NULL CHECK (sequence > 0),
    event_id        uuid NOT NULL UNIQUE,
    producer_key    text,
    event_type      text NOT NULL,
    event           jsonb NOT NULL CHECK (jsonb_typeof(event) = 'object'),
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, sequence),
    CHECK (substring(event_id::text FROM 15 FOR 1) = '7')
);

CREATE UNIQUE INDEX agent_event_producer_key_uq
    ON agent.agent_event (run_id, producer_key)
    WHERE producer_key IS NOT NULL;
CREATE INDEX agent_event_created_idx
    ON agent.agent_event (created_at, run_id, sequence);

CREATE TABLE agent.agent_interrupt (
    interrupt_id          uuid PRIMARY KEY,
    origin_run_id         uuid NOT NULL
                          REFERENCES agent.agent_request(run_id) ON DELETE CASCADE,
    semora_run_id         uuid NOT NULL,
    semora_pending_id     text NOT NULL,
    semora_tool_call_id   text NOT NULL,
    resolution            text CHECK (resolution IN ('resolved', 'cancelled')),
    resolved_by_run_id    uuid
                          REFERENCES agent.agent_request(run_id) ON DELETE RESTRICT,
    created_at            timestamptz NOT NULL DEFAULT clock_timestamp(),
    resolved_at           timestamptz,
    UNIQUE (semora_run_id, semora_pending_id),
    CHECK (substring(interrupt_id::text FROM 15 FOR 1) = '7'),
    CHECK (substring(semora_run_id::text FROM 15 FOR 1) = '7'),
    CHECK (
        (resolution IS NULL AND resolved_by_run_id IS NULL AND resolved_at IS NULL)
        OR
        (resolution IS NOT NULL AND resolved_by_run_id IS NOT NULL AND resolved_at IS NOT NULL)
    )
);

CREATE OR REPLACE FUNCTION agent.append_event(
    p_run_id       uuid,
    p_event_id     uuid,
    p_producer_key text,
    p_event_type   text,
    p_event        jsonb,
    p_is_terminal  boolean DEFAULT false
) RETURNS SETOF agent.agent_event
LANGUAGE plpgsql
AS $$
DECLARE
    v_sequence          bigint;
    v_terminal_sequence bigint;
    v_now               timestamptz := clock_timestamp();
BEGIN
    SELECT next_event_sequence, terminal_sequence
      INTO v_sequence, v_terminal_sequence
      FROM agent.agent_request
     WHERE run_id = p_run_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown agent run %', p_run_id
            USING ERRCODE = '23503';
    END IF;

    IF p_producer_key IS NOT NULL THEN
        RETURN QUERY
        SELECT e.*
          FROM agent.agent_event AS e
         WHERE e.run_id = p_run_id
           AND e.producer_key = p_producer_key;
        IF FOUND THEN
            RETURN;
        END IF;
    END IF;

    IF p_is_terminal AND p_producer_key IS DISTINCT FROM 'run:terminal' THEN
        RAISE EXCEPTION 'terminal event requires run:terminal producer key'
            USING ERRCODE = '23514';
    END IF;
    IF p_is_terminal AND v_terminal_sequence IS NOT NULL THEN
        RAISE EXCEPTION 'run % already has a terminal event', p_run_id
            USING ERRCODE = '23505';
    END IF;

    UPDATE agent.agent_request
       SET next_event_sequence = v_sequence + 1
     WHERE run_id = p_run_id;

    INSERT INTO agent.agent_event
        (run_id, sequence, event_id, producer_key, event_type, event, created_at)
    VALUES
        (p_run_id, v_sequence, p_event_id, p_producer_key, p_event_type, p_event, v_now);

    IF p_is_terminal THEN
        UPDATE agent.agent_request
           SET terminal_sequence    = v_sequence,
               terminal_at          = v_now,
               terminal_event       = p_event,
               replay_expires_at    = v_now + interval '90 days',
               tombstone_expires_at = v_now + interval '365 days'
         WHERE run_id = p_run_id;
    END IF;

    RETURN QUERY
    SELECT e.*
      FROM agent.agent_event AS e
     WHERE e.run_id = p_run_id
       AND e.sequence = v_sequence;
END;
$$;
```

Until retention redaction, `execution_config` contains diagnostic metadata only: Semora version,
prompt revision, selected OpenRouter model, selected tool names and execution limits. It does not
duplicate the rendered prompt, tool definitions, transcript, Semora execution state or model
usage. Application admission requires both `original_input` and `execution_config`; their
nullable DDL exists only for scheduled redaction. It is not an execution status. There are no `queued`,
`running`, `claimed`, `lease_owner`, `lease_until` or Agent execution `attempt` columns. Semora
execution store, transcript and Agent transport records remain separate schemas and interfaces
even when installed in the same PostgreSQL instance.

### 10.1 Payload hash and request idempotency

Implementation status (2026-08-31): `agent_core.admission` now implements the pure
`RunAgentInput` admission, strict unknown-field/I-JSON checks, UUIDv7 profile validation and JCS
SHA-256 calculation. HTTP authentication, request persistence and attach/replay behavior remain
outside that completed slice.

After strict AG-UI schema validation, Agent Server canonicalizes the entire parsed
`RunAgentInput` with RFC 8785 JCS and computes `SHA-256(canonical_bytes)`. JSON whitespace and
object-member order therefore do not affect the hash; array order, string bytes and every AG-UI
field do. Authorization headers and `Last-Event-ID` are transport metadata and are excluded.
Unknown input fields are rejected rather than silently discarded before hashing.

Request admission is one transaction:

1. derive and authenticate the owner subject;
2. `INSERT agent_request ... ON CONFLICT (run_id) DO NOTHING`;
3. when the row already exists, read it and compare owner first, then `payload_hash`;
4. different owner returns `404`; same owner and same hash attaches/replays; same owner and a
   different hash returns `409` with `code="run_id_conflict"`;
5. never include either hash in the error response.

A resume request locks all referenced `agent_interrupt` rows in UUID order. All interrupts must
be open, owned by the same subject, belong to one `thread_id` and resolve to one
`semora_run_id`. Repeating the same resume `runId` is idempotent; a different run trying to
resolve an already resolved interrupt receives `409 interrupt_already_resolved`.

### 10.2 Event sequence allocation transaction

Every code path that inserts an Agent event calls `agent.append_event(...)` inside its current
transaction, including recovery and terminal events. The function above takes the request-row
lock before both the producer-key lookup and sequence allocation. A terminal call passes
`p_producer_key = 'run:terminal'` and `p_is_terminal = true`; all other calls pass false.

All producers for one run therefore serialize on the request row. The sequence is allocated and
the event is inserted in the same transaction, so rollback does not leave a committed hole and
sequence order matches commit order. Stable `producer_key` values make source retries
idempotent: Semora RAW events use `semora:<event-id>`, the terminal event uses `run:terminal`, and
the model recovery gate uses the reserved keys specified below.

### 10.3 Retention and cleanup

- Redis hot replay expires after 24 hours; this does not affect correctness.
- A terminal run keeps full `agent_event`, `original_input` and `execution_config` for 90 days by
  default. `replay_expires_at = terminal_at + interval '90 days'`.
- At replay expiry, a daily Agent maintenance job deletes journal rows in batches of 1,000 and
  redacts `original_input`/`execution_config`, while retaining the payload hash, owner hash and
  terminal summary as an idempotency tombstone.
- The tombstone remains for 365 days by default. A repeated old `runId` during that period returns
  `410 replay_expired`; it is never mistaken for a new run.
- Incomplete, suspended and aborted-but-not-yet-terminal requests are never age-deleted
  automatically. They are alerted after 24 hours and require explicit lifecycle/privacy cleanup.
- Semora transcript/store retention is a separate policy. Agent maintenance never deletes Semora
  rows by guessing from Agent transport state.

The maintenance job is storage lifecycle work, not an Agent execution worker: it never starts,
claims, retries or completes a Semora run.

Each cleanup batch is one transaction. It locks only expired terminal requests and then deletes
their events and redacts their input:

```sql
WITH expired AS (
    SELECT run_id
      FROM agent.agent_request
     WHERE replay_expires_at <= clock_timestamp()
       AND redacted_at IS NULL
     ORDER BY replay_expires_at, run_id
     FOR UPDATE SKIP LOCKED
     LIMIT 1000
), deleted AS (
    DELETE FROM agent.agent_event AS e
     USING expired AS x
     WHERE e.run_id = x.run_id
    RETURNING e.run_id
)
UPDATE agent.agent_request AS r
   SET original_input = NULL,
       execution_config = NULL,
       redacted_at = clock_timestamp()
 WHERE r.run_id IN (SELECT run_id FROM expired);
```

A later batch deletes tombstone requests whose `tombstone_expires_at` has passed, also with
`FOR UPDATE SKIP LOCKED`, but only when `terminal_at IS NOT NULL`. Explicit privacy deletion may
shorten both windows.

## 11. Durable event delivery

PostgreSQL `agent_event` is canonical. Redis Stream is a bounded hot-replay and live-delivery
accelerator.

Producer order:

```text
translate Semora event
-> commit agent_event in PostgreSQL
-> XADD the committed event to Redis Stream
```

Subscriber order:

1. begin reading/buffering Redis live events;
2. replay DB events after the last delivered sequence;
3. merge DB replay and the Redis buffer in sequence order;
4. discard already delivered sequences;
5. fill any observed gap from DB;
6. periodically compare the DB high-water mark so a failed final Redis publication is found.

Redis loss never loses a canonical event. No event that exists only in Redis is acknowledged.
There is no Event Outbox or outbox publisher because subscribers reconcile directly with the
canonical DB journal.

Each SSE frame uses its standard `id:` field for the Agent event sequence without adding a field
to AG-UI `BaseEvent` JSON.

### 11.1 Redis keys and commands

Redis is namespaced by schema version and run. Curly braces form the Redis Cluster hash tag.

```text
agent:v1:run:{<run-uuid>}:events       Redis Stream
agent:v1:control:abort                 Redis Pub/Sub channel
```

After committing sequence `N`, the producer performs:

```text
XADD agent:v1:run:{<runId>}:events MAXLEN ~ 4096 N-0 event <BaseEvent JSON bytes>
EXPIRE agent:v1:run:{<runId>}:events 86400
```

Using the Agent sequence as Redis Stream ID makes merge order explicit. A failed XADD is logged
but does not fail or roll back the request. An event larger than 256 KiB is deliberately not
cached; it remains available from PostgreSQL. The approximate `MAXLEN` bound and refreshed
24-hour TTL keep a hot run bounded without pretending Redis is archival storage. No consumer
group, pending-entry list, `XCLAIM`, Redis lock or Redis queue is used.

Subscribers use `XREAD COUNT 256 BLOCK 1000` from the last delivered `<sequence>-0`. DB replay is
paged in groups of 500. While attached, each subscriber checks the PostgreSQL high-water mark
(`next_event_sequence - 1`) every two seconds, immediately on a Redis sequence gap and before
emitting an SSE heartbeat. SSE heartbeat interval is 15 seconds.

If Redis is unavailable, the subscriber switches to PostgreSQL polling at one-second intervals.
The process retries Redis with a circuit-breaker backoff from five to thirty seconds and rejoins
the same sequence merge when it returns. Redis failure does not make the pod unready. A
per-subscriber in-memory buffer is capped at 512 events or 4 MiB; a slower consumer is detached
and resumes through DB replay rather than applying backpressure to Semora.

The abort Pub/Sub channel contains only `runId` and `requestedAt`; it carries no subject or
credential. Pub/Sub is a low-latency hint. The durable abort fact is always PostgreSQL and the
fallback is the local-active-run DB check specified below.

## 12. Reconnect transport ownership

There are two independent connections:

```text
React <-> Platform Server       product projection stream
Platform <-> Agent Server      AG-UI event stream
```

React never calls Agent Server directly and never knows its event cursor or abort endpoint. A
browser refresh only breaks the React-to-Platform connection.

The component that directly calls Agent Server is Platform's `ResumableAguiClient`. Current AG-UI
reference `HttpAgent` does not preserve SSE `id`, send `Last-Event-ID`, reconnect a POST stream or
implement HTTP `connectAgent()`, so the Platform client supplies only this missing transport
behavior:

- preserve the last SSE ID;
- repeat the exact same `RunAgentInput` POST after transport failure;
- set `Last-Event-ID`;
- use bounded reconnect backoff;
- never turn disconnect into abort.

This extension changes neither `RunAgentInput` nor `BaseEvent`.

## 13. Messages and transcript

`RunAgentInput.messages` is the caller's current conversation snapshot. AG-UI message IDs are
preserved when mapping to LangChain/Semora messages.

For a normal request, the trailing new user message is the `Prompt`, while earlier messages are
history. Semora's transcript common-prefix replacement is used to retain the shared prefix,
rewind divergence and append the desired history. Therefore a changed history with a new `runId`
is an edit/branch, not an idempotent replay of the old invocation.

Resume tails and tool-result tails use their dedicated command paths and are not mistaken for a
new prompt.

## 14. Event mapping

Awaited planner/model and host-control events map to matching official AG-UI events:

- thinking -> AG-UI thinking-text lifecycle;
- text -> text-message start/content/end;
- tool call -> tool-call start/arguments/end;
- awaited post-tool observation -> tool-call result;
- suspension -> `RUN_FINISHED` interrupt outcome;
- normal completion -> `RUN_FINISHED` success;
- unrecoverable failure -> `RUN_ERROR`.

Semora `event_sink` delivery is explicitly best-effort. `EventEnvelope` values received there are
used for logs and metrics only and are not sent as `RAW` events by default. They are not part of
AG-UI correctness or replay. Complete conversation and tool-result truth remains in
`PostgresTranscript`; `agent_event` stores only the ordered AG-UI transport projection.

Normal streaming does not emit repeated `MESSAGES_SNAPSHOT` events. Cursor expiry or safe process
recovery emits one snapshot from the committed Semora transcript before continuing.

## 15. Tools

Actual tool implementations, registry, credentials, permissions, sandboxing and execution remain
inside Agent Server/Semora.

`RunAgentInput.tools` selects tools by unique name from this Agent Server's registry. The server's
description, input schema and implementation are canonical; caller-provided fields never replace
them. It is not executable-code injection and never carries credentials. Unknown or duplicate
tool names are rejected. An empty list creates a model-only Agent.

V1 tools are non-mutating/read-oriented. Client-side tool execution is not part of the current
design. The selected tool subset is the executable authority, so V1 does not add the optional
`semora-permissions` package. A user decision required by a server-owned tool uses the AG-UI
interrupt/resume lifecycle.

## 16. Internationalization and storage format

- store Unicode text without translating or normalizing individual chunks;
- persist official AG-UI camelCase JSON;
- use `timestamptz` and serialize timestamps as RFC 3339 UTC with `Z`;
- preserve original language/content;
- perform locale presentation and optional derived translation in the UI/Platform projection;
- do not turn locale handling into Agent execution semantics.

## 17. Explicit exclusions

- queue-based Agent execution worker;
- Agent-owned claim/lease/attempt state machine;
- Redis execution locks, queues or canonical state;
- Event Outbox for Agent streaming;
- direct React-to-Agent invocation;
- GET attach endpoint for Agent execution;
- private cursor/recovery fields in `RunAgentInput`;
- runtime multi-agent hosting or `agentKey` selection;
- Platform session/branch/toss/consensus concepts in Agent Server;
- automatic recovery of abandoned runs without a reconnect trigger;
- critical mutating V1 tools.

## 18. Prompt assembly and provider

Agent Server has a dedicated Prompt Assembly Layer between AG-UI input mapping and Semora model
execution. Prompt construction is not spread across the HTTP route, tool adapter or Semora event
translator.

```text
RunAgentInput
-> AG-UI input/command mapping
-> Prompt Assembly Layer
-> Semora Agent declaration
-> AgentRuntime.dispatch()
-> OpenRouter
```

OpenRouter is the only model provider for this Agent Server. Provider credentials remain an Agent
Server deployment secret and never arrive through `RunAgentInput`. One required model is selected
per deployment and cannot be overridden by `RunAgentInput`.

Prompt Assembly renders once for a new run in this order: server base prompt, server behavior and
safety policy, selected server-tool instructions, and `context`/`state` encoded as explicitly
untrusted data. Prior messages remain separate Semora history and the final user message remains
the unmodified `Prompt`. The Agent profile rejects external `system` and `developer` messages.

## 19. Authentication and execution owner

Agent Server is a resource server. Platform sends a short-lived RFC 9068-style JWT access token
in `Authorization: Bearer ...` over TLS. The token is issued for the Agent Server audience and
contains:

```text
typ = at+jwt
iss = trusted authorization issuer
aud = this logical Agent Server
sub = opaque stable end-user subject
azp/client_id = allow-listed Platform workload
scope = agent:run and/or agent:abort
iat, nbf, exp = bounded token lifetime (maximum five minutes)
```

JWT/JWS verification, claim validation and asynchronous JWKS caching live in the independently
installable `service-auth` package shared with Platform Server. The package returns a
domain-neutral principal and contains no Platform, Agent, FastAPI or Semora policy. Agent Server
still owns enforcement at its ingress: it validates the Agent audience independently, allow-lists
the Platform workload, checks `agent:run`/`agent:abort`, and never trusts a caller-supplied subject
header.

Each verifier has one configured trusted issuer, one logical audience and one explicit HTTPS
`jwks_uri`; it never follows `jku`, `jwk` or another token-provided URL. Agent Server validates an
explicit asymmetric algorithm allow-list, signature from the cached issuer JWKS, exact issuer and
audience, and time claims with at most 30 seconds of clock skew. It never accepts an OIDC ID token
as an access token. A key set is fresh for five minutes and usable for at most 15 minutes from its
last successful fetch during a transient issuer outage. An unknown `kid` causes one refresh and
then fails closed. Established SSE is not killed when its token later expires; every reconnect and
abort request is authenticated again.

The access token, raw `sub` and provider credentials are never persisted or logged. Ownership is
derived as:

```text
owner_subject_hash = SHA-256(UTF8(iss) || 0x00 || UTF8(sub))
semora_subject = "agtsub:v1:" || base64url(owner_subject_hash)
```

The request row stores the trusted `owner_issuer` and 32-byte hash. `ExecutionContext.subject`
receives `semora_subject`; Semora rejects a caller-supplied subject that differs from that trusted
context. Every attach, resume and abort recomputes the hash from a newly validated token and must
match the stored owner. A mismatch returns `404` to avoid disclosing run existence. Invalid token
is `401` with `WWW-Authenticate: Bearer`; valid identity without scope is `403`.

Authorization is not part of the payload hash, so a reconnect with a refreshed token remains the
same invocation. V1 does not persist `jti` or reject token reuse because the same safe POST is
intentionally repeatable. Network policy restricts the service to Platform ingress; mTLS may be
added at the service mesh, but the application authorization contract remains the verified JWT.

The detailed package, cache, error and test contract is defined in
[`2026-09-02-shared-service-auth-design.md`](../specs/2026-09-02-shared-service-auth-design.md).

## 20. Abort and recovery wiring

### 20.1 Cross-replica abort

`POST /runs/{runId}/abort` is an authenticated, idempotent intent command. It performs:

1. lock `agent_request`, verify owner and set `abort_requested_at = COALESCE(...,
   clock_timestamp())` in PostgreSQL;
2. commit before signalling;
3. set the local process's `asyncio.Event` if that process owns the task;
4. `PUBLISH agent:v1:control:abort` as a best-effort hint to other replicas;
5. return `202` with `code="abort_requested"`; an already terminal run returns its existing
   terminal summary with `200`.

Every process keeps a strong in-memory registry `runId -> (Task, asyncio.Event)` only for tasks it
currently owns. The Semora call receives the synchronous predicate
`aborted=lambda: abort_event.is_set()`. Redis Pub/Sub sets the corresponding event on the owning
replica. Independently, each replica batches the IDs of its local active tasks and checks
`abort_requested_at` in PostgreSQL once per second. Thus a lost Pub/Sub message or complete Redis
outage increases abort latency but cannot lose the intent.

No code uses `Task.cancel()` for user abort. Semora observes the predicate between model chunks
and tool boundaries, records `done(stop_reason="aborted")`, and Agent maps it to the agreed AG-UI
terminal. While a provider is silent, latency is bounded by the 60-second inter-chunk timeout. If
the execution process died before recording the Semora terminal, a later same-run reconnect runs
Semora recovery with `aborted()` already true solely to close the run; it never clears or retries
the interrupted model step.

### 20.2 Provider failure and `Indeterminate`

Semora `ModelFailurePolicy` permits at most one retry for a rate-limit, server or network failure
before any output is visible. After visible output, an automatic retry is forbidden because it
would duplicate presentation. Context overflow is not compacted automatically in V1.

An `Indeterminate` execution is not force-retried. Agent emits
`RUN_ERROR(code="indeterminate_execution")`, and the user may start a new `runId`. `Contended`
means another replica owns the lease and is handled as subscription; `Fenced` ends only the stale
local task. There are no recovery phase events or Agent-owned recovery budget.

### 20.3 Process shutdown

SIGTERM is infrastructure interruption, not user abort:

1. set the process to draining and make readiness fail immediately;
2. reject only brand-new runs with `503 draining`; existing replay/attach and abort paths remain
   available while the server is alive;
3. keep existing Semora tasks and SSE subscribers for a 35-second application drain window;
4. close remaining subscribers, then cancel remaining infrastructure tasks without setting
   `abort_requested_at` or emitting a user-aborted terminal;
5. allow Semora async context cleanup to release leases; an abrupt kill falls back to lease TTL
   and fencing.

Semora intentionally leaves a cancelled in-flight effect indeterminate, so the next same-run
reconnect follows the recovery policy above. Kubernetes
`terminationGracePeriodSeconds` is 45 seconds, leaving ten seconds after application drain for
socket and lease cleanup.

### 20.4 Semora integration seam

No recovery feature above requires a Semora private method, internal table write or compatibility
shim. Agent Server uses these existing public seams:

- released `semora[postgres,openrouter]==0.2.0` packages;
- the Semora `Agent` declarative execution definition;
- `AgentRuntime.dispatch()` as the only execution entry point;
- `Prompt`, `Answer` and `Recover` commands;
- `ExecutionContext.subject` for the trusted opaque owner;
- `PostgresSteps` and `PostgresTranscript` for all Semora-owned persistence;
- `ControlPlane` for execution budgets and awaited tool-result observation;
- `Contended`, `Fenced`, `Indeterminate` and `InvalidTransition` for typed decisions;
- the existing `aborted` predicate and Semora terminal event for user stop.

Agent Server constructs a pure UUIDv7 string and supplies it as Semora `run_id`; it does not use
Semora's optional prefixed ID convenience function. Cross-replica delivery of an abort flag,
AG-UI translation, Agent event persistence and authentication are host responsibilities around
Semora rather than gaps or runtime workarounds. Agent Server does not call `react_loop()`,
`force_retry()`, private Semora members or Semora SQL. Contract tests pin these public seams before
implementation.

## 21. Operational limits

These are safe V1 defaults and configuration bounds, not product/business quotas:

| Limit | Default behavior |
| --- | --- |
| Request body | 2 MiB; reject before JSON parsing with `413` |
| Messages / tools | at most 256 messages and 64 tool descriptors per invocation |
| Serialized Agent event | 2 MiB in PostgreSQL; events above 256 KiB bypass Redis |
| Active Semora tasks | 32 per replica; new run receives `503 capacity_exceeded` + `Retry-After: 2` |
| Active tasks per subject | 4 per replica; Platform owns any global/user business quota |
| New-run protective rate | token bucket 10/minute per subject, burst 4; reattach and abort do not consume it |
| Whole run wall clock | 15 minutes, excluding time suspended for a human answer |
| Model rounds | 16 per run |
| Tool calls | 32 total per run |
| OpenRouter connect | 10 seconds |
| OpenRouter first byte | 60 seconds |
| OpenRouter inter-chunk idle | 60 seconds |
| One model invocation | 5 minutes maximum |
| One read-only tool call | 60 seconds default, 5 minutes hard maximum |
| SSE heartbeat | 15 seconds |

The protective subject limiter is in-process and deliberately approximate across replicas; it is
not billing or authorization state and does not justify making Redis canonical. Platform applies
global product quotas before calling an Agent. Capacity checks apply only when starting a new
Semora task: exact-run replay, subscription and abort remain possible under saturation. There is
no in-Agent waiting queue.

The 15-minute wall-clock deadline is a durable system stop, not a user abort. On expiry the task
first sets `deadline_exceeded_at` in PostgreSQL and then sets its local stop event; it does not use
`Task.cancel()`. Semora's existing predicate records its generic aborted stop, while Agent emits
`RUN_ERROR(code="run_timeout")` instead of the neutral user-stop presentation. A reconnect checks
both durable stop timestamps before recovery. If user abort and deadline race, the earlier
persisted timestamp determines the external terminal reason.

Prompt Assembly validates the selected model's context window before starting OpenRouter and
reserves the configured maximum output tokens; an oversized assembled prompt fails with
`context_limit_exceeded` rather than relying on provider truncation. OpenRouter 429/5xx may use at
most one bounded retry before any output is visible, honoring `Retry-After` up to ten seconds.
After a visible chunk, automatic provider retry is forbidden and Semora durability decides
recovery.

### 21.1 Health and readiness

- `/livez` checks only that the process/event loop is alive; it does not query dependencies.
- `/readyz` requires: not draining, Agent PostgreSQL reachable, schema revision compatible,
  prompt configuration valid, OpenRouter credential loaded, and a usable cached JWKS set.
- Redis failure reports degraded health/metrics but readiness remains true because PostgreSQL
  replay is the defined fallback.
- Readiness never calls OpenRouter and does not flap merely because the local concurrency limit is
  full; new runs receive the explicit capacity response.
- Migrations run as a separate deployment/init job, never concurrently in every web process.

Required metrics include active tasks/subscribers, run start/terminal/abort totals, Semora
`Contended` and reconnect-triggered recovery, DB replay count/lag, Redis publish
failure/gap/fallback duration, SSE slow-consumer detach, OpenRouter latency/error/rate-limit and
shutdown drain remainder. Logs contain run/thread/event UUIDs and opaque subject hash prefix, but
never prompts, message bodies, tokens or tool credentials.

## 22. Still undecided

The following still requires product/design feedback before implementation:

- concrete V1 server-owned tool catalog;
- the Platform-side product projection and browser-stream schema.

## 23. Standards and implementation evidence

- UUIDv7 layout and generation: [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html)
- invariant JSON hashing input: [RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785.html)
- JWT access-token claims and resource-server validation:
  [RFC 9068](https://www.rfc-editor.org/rfc/rfc9068.html)
- PostgreSQL 16 native UUID, JSONB and constraint behavior:
  [UUID type](https://www.postgresql.org/docs/16/datatype-uuid.html),
  [JSON types](https://www.postgresql.org/docs/16/datatype-json.html),
  [constraints](https://www.postgresql.org/docs/16/ddl-constraints.html)
- Redis Stream append/bounds and blocking reads:
  [XADD](https://redis.io/docs/latest/commands/xadd/),
  [XREAD](https://redis.io/docs/latest/commands/xread/)
- readiness and termination behavior:
  [Kubernetes probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/),
  [Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/),
  [container lifecycle hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
- Semora public/runtime evidence:
  `packages/semora/src/semora/runtime.py:698`,
  `packages/semora/src/semora/orchestration.py:127`,
  `packages/semora/src/semora/orchestrator.py:557`,
  `packages/semora/src/semora/orchestrator.py:1126`, and
  `packages/semora-store/src/semora_store/ledger.py:49` in the Semora repository.
