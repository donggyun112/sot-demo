# Agent Server

This service hosts one logical Pydantic AI agent through Semora 0.3. It accepts official
AG-UI `RunAgentInput`, lets Pydantic AI own the model/tool loop, and projects events into
a PostgreSQL replay journal.

```text
Platform Server -- AG-UI HTTP/SSE --> Agent Server -- Semora -- Pydantic AI --> providers
                                             |          |
                                             |          +--> PostgreSQL ledger/transcript
                                             +--> PostgreSQL AG-UI journal
```

The public surface is:

```text
GET  /healthz
POST /ag-ui                 official RunAgentInput -> BaseEvent SSE
POST /runs/{runId}/abort    explicit user-intent abort extension
```

## Execution and failure model

One process-local `RunSupervisor` owns each active `asyncio.Task` and its Pydantic AI
cancellation token. Semora runs inside that task; it is not a worker or task queue.
PostgreSQL owns admitted requests, abort intent, deferred interrupts, the terminal-closed
AG-UI journal, Semora effect intents/results, leases, and the native message transcript.

An SSE disconnect, browser refresh, or network loss detaches only that subscriber;
execution continues and a client can reconnect using the last event sequence. Only
an authenticated explicit abort cancels a live run.

A process crash leaves a non-terminal request available for request-driven recovery.
Reposting the same canonical request with the same `runId` reacquires the Semora run;
the stable user-message ID prevents redelivery. There is no startup scanner or polling
worker. A step that started but cannot safely be repeated ends as
`indeterminate_execution`. Provider failures are exposed only as the generic
`agent_failed` terminal event.

This design requires exactly one active Agent Server instance for an Agent database.
Deploy with a recreate strategy: stop and drain the old instance before starting the
new one. Do not overlap replicas or use rolling deployment for this service.

Request tools are only an ordered name selection. Descriptions, schemas, credentials,
and executors come from the server-owned `ToolRegistry`; callers cannot add authority
by supplying a tool schema. Request context and state are rendered as explicitly
untrusted prompt data. The trusted `(iss, sub)` identity is stored only as an opaque
SHA-256 owner and converted to the agent subject.

## Configuration

The local execution settings are:

- `AGENT_RUN_CAPACITY` (default `32`): maximum active runs; excess requests receive
  HTTP 503 with `Retry-After: 2` and a terminal `capacity_exceeded` event.
- `AGENT_RUN_SHUTDOWN_TIMEOUT_SECONDS` (default `35`): graceful drain period before
  remaining tasks are cancelled as `server_shutdown`.
- `AGENT_RUN_LEASE_TTL_SECONDS` (default `60`): Semora lease/fencing interval for one
  durable run attempt. This is integrity state, not queue ownership.

Configure the model chain as a JSON array of Pydantic AI model references:

```text
AGENT_MODELS=["openrouter:openai/gpt-5-mini","openai:gpt-5-mini"]
```

Models are tried in order: the first entry is primary and later entries are
fallbacks. Fallback occurs only under Pydantic AI's default `ModelAPIError` policy;
other failures are not retried on another provider. Callers cannot choose or
override the model chain.

Supported model prefixes map to credentials as follows:

- `openai:` uses `OPENAI_API_KEY`.
- `anthropic:` uses `ANTHROPIC_API_KEY`.
- `google:` uses a Google AI Studio API key from `GOOGLE_API_KEY` (or the legacy
  `GEMINI_API_KEY`).
- `google-cloud:` uses Google application credentials, such as Application Default
  Credentials configured through `GOOGLE_APPLICATION_CREDENTIALS`.
- `openrouter:` uses `OPENROUTER_API_KEY`.

Set credentials for every provider prefix used by the configured chain.

Provider initialization errors raised while Pydantic AI constructs the chain leave
the app unconfigured; requests receive the generic HTTP 503 response. Some providers
defer credential discovery until the first request, so successful startup does not
verify every credential. Those deferred failures remain runtime failures and are
journaled as a terminal `RUN_ERROR` with public code `agent_failed` and a redacted
message. The native fallback policy remains unchanged.

The existing `AGENT_*`, authentication, and PostgreSQL settings remain required by
the application graph.

## Database rollout

Fresh and upgraded Agent databases apply these migrations in order:

1. `001_agent.sql`
2. `003_pydantic_ai.sql`
3. `004_local_async.sql`
4. `005_semora_0_3.sql`

Migration `002` is legacy rollback material and is not part of a fresh deployment.
Migration `004` removes the retired workflow columns and closes the event journal after
its terminal event. Migration `005` installs Semora 0.3's PostgreSQL step ledger,
leases, queued inputs, transcript, and run/model accounting tables. The
`003 -> 004 -> 005` chain is repeatable.

## Verification

```bash
uv run --project agent-server pytest agent-server/tests -q
uv run --project agent-server ruff check agent-server/src agent-server/tests
uv run --project agent-server mypy agent-server/src agent-server/tests
```

The live OpenRouter acceptance test is opt-in:

```bash
RUN_OPENROUTER_E2E=1 \
OPENROUTER_API_KEY=[REDACTED:API key param] \
uv run --project agent-server pytest agent-server/tests/e2e/test_openrouter.py -q -m e2e
```

Build from the repository root so the local `service-auth` dependency is available:

```bash
docker build -f agent-server/Dockerfile .
```
