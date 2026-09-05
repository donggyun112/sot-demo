# Pydantic AI Direct SOT Vertical Slice Design

**Date:** 2026-09-06
**Status:** Approved direction; implementation pending
**Supersedes:** The two-server, Semora-backed agent execution architecture in `2026-08-30-sot-v1-design.md`

## 1. Decision

The first working SOT product slice will use one FastAPI application, one PostgreSQL
database, a React frontend, and Pydantic AI's native AG-UI integration.

Semora and LangGraph will not participate in the request path. The application will not
maintain an agent execution journal, checkpoint partial model runs, replay SSE events, or
continue an agent run after its client disconnects.

This decision changes the implementation architecture, not the SOT product model. SOT
still owns sessions, branches, curated evidence, tosses, proposals, approvals, and main
document revisions.

## 2. Why this is the smallest correct architecture

The agent performs one ordinary asynchronous model/tool run per browser request. Pydantic
AI already owns the model loop, tool loop, provider integrations, model fallback, AG-UI
input conversion, and AG-UI event streaming. A graph runtime would add value only if the
agent itself acquired a fixed multi-node workflow with explicit branches, joins, or
long-lived resumable execution.

SOT's branch and consensus concepts are product-domain state transitions. They are not
agent execution graph nodes and must remain independent of the model runtime.

## 3. Goals

1. Replace the static concept demo with a working React interface.
2. Implement one vertical path: create a draft session, talk to an agent, curate evidence,
   create a toss, fork it, approve a proposal, and observe a new main revision.
3. Use Pydantic AI directly for the agent and AG-UI streaming.
4. Persist completed SOT product state in PostgreSQL.
5. Keep model configuration provider-neutral and support ordered fallback models.
6. Keep domain mutations server-authoritative and testable without an LLM.

## 4. Non-goals

- Surviving an application crash in the middle of a model run
- Resuming a partial stream using `Last-Event-ID`
- Agent run leases, recovery scanners, queues, or worker processes
- Durable agent checkpoints or an agent event journal
- A separate Agent Server deployment or agent database
- Semora or LangGraph integration
- Horizontal execution of the same logical agent across replicas
- Production billing, organization administration, or enterprise identity integration

## 5. System architecture

```text
Browser
  ├── React SOT views ── REST/JSON ───────────────┐
  └── CopilotKit chat ── AG-UI/SSE ──────────────┤
                                                   ▼
                                  FastAPI Platform Application
                                  ├── SOT domain services
                                  ├── Pydantic AI Agent
                                  ├── AGUIAdapter
                                  └── PostgreSQL repositories
                                                   │
                         ┌─────────────────────────┴──────────────────┐
                         ▼                                            ▼
                    PostgreSQL                                  Model providers
                 product data only                         ordered fallback chain
```

The FastAPI process is the only backend service. The Pydantic AI agent is an in-process
component, not a worker and not a separately deployed service.

## 6. Backend boundaries

### 6.1 Domain API

REST endpoints under `/api/v1` own SOT resources and state transitions. The initial slice
needs APIs for:

- documents and current main revisions
- draft sessions and branches
- completed conversation turns
- evidence curation and immutable cites
- toss creation and token-based reading
- fork creation
- proposal creation, approval, and main revision publication

Domain services enforce transition rules. Repository code persists state but does not
contain product policy. Agent tools call the same domain services as HTTP handlers rather
than writing tables directly.

### 6.2 Agent endpoint

The application exposes an AG-UI endpoint under `/api/v1/agent`. It uses Pydantic AI's
`AGUIAdapter` and an in-process `Agent` directly.

The server owns instructions, tools, tool schemas, and tool implementations. The client
may select from explicitly allowed frontend tools but cannot introduce server authority.

An ordered tuple of Pydantic AI model references configures a `FallbackModel`. Provider
credentials remain environment variables understood by their provider integrations; SOT
does not define an OpenRouter-only model abstraction.

### 6.3 Request lifetime

Each AG-UI request owns one asyncio task. If the browser disconnects, cancellation of that
run is acceptable. Partial assistant output and partial run events are not persisted.

After a successful `RUN_FINISHED`, the client commits the completed user and assistant
turns through the session API. Reloading a session reconstructs AG-UI message history from
completed product conversation turns. A failed or disconnected run can be retried as a
new run and may repeat model work.

This is deliberately at-most-one completed transcript commit, not exactly-once model
execution. Domain mutations still use database transactions and unique constraints where
duplicate publication would be harmful.

## 7. Product data and PostgreSQL

PostgreSQL stores product truth:

- users and document membership required by the demo
- documents and immutable main revisions
- sessions, branches, and completed conversation turns
- curated cite manifests and their selected source turns
- toss records and public read tokens
- proposals, approval records, and publication links

It does not store provider event streams, model checkpoints, agent leases, execution
attempts, or resumable SSE cursors.

Migrations from the current Agent Server are removed rather than adapted. A new compact
platform schema is created around domain invariants.

## 8. Frontend

The production UI is a React application. CopilotKit supplies the AG-UI client connection
and streaming agent interaction; SOT-specific views remain ordinary React components.

The initial navigation mirrors the validated static demo:

1. document list
2. main document with cited claims
3. session and branch list
4. session workspace with agent conversation and curation rail
5. toss reader and fork action
6. proposal comparison, approval state, and resulting main revision

`index.html` and `msbd-real.html` remain design references during the migration. The React
application does not embed or incrementally patch their scripts.

## 9. Error handling

- Validation and domain conflicts return stable problem codes from REST endpoints.
- Model or provider failures surface through standard AG-UI error events.
- A disconnected stream leaves no resumable execution record; the UI offers a retry.
- A failed transcript commit leaves the completed text visible locally and offers a save
  retry without rerunning the model.
- Domain publication uses a transaction so approvals and the resulting main revision
  cannot be partially applied.

## 10. Security boundary

- Browser identity is resolved once by the FastAPI application and passed to domain
  services and agent dependencies.
- Public toss tokens grant read access only to their immutable published bundle.
- Agent instructions and executable tools are server-owned.
- Provider credentials never reach the browser or product database.
- Agent tool calls cannot bypass the same authorization checks used by REST handlers.

Authentication for the first local vertical slice may use a fixed development identity.
Replacing it with real login must not change domain service signatures or authorization
rules.

## 11. Testing

### Backend

- Unit tests cover domain state transitions without PostgreSQL or an LLM.
- Repository integration tests run against PostgreSQL.
- Pydantic AI agent tests use `TestModel` or `FunctionModel`.
- AG-UI contract tests assert request validation and streamed event ordering.
- A provider smoke test remains opt-in.

### Frontend

- Component tests cover loading, empty, streaming, failure, and approval states.
- Contract tests use generated or shared API schemas rather than handwritten response
  guesses.
- One browser acceptance test covers the complete draft-to-main vertical path.

## 12. Migration

1. Preserve the static demos as references.
2. Replace the current `agent-server` internals with the direct Pydantic AI endpoint.
3. Remove Semora dependencies, agent store code, execution migrations, replay, leases,
   supervisor, and recovery tests.
4. Add the platform domain schema, repositories, services, and REST API.
5. Add the React/CopilotKit application and connect it to REST and AG-UI.
6. Update Compose to run one PostgreSQL database, one FastAPI application, and the web
   application.
7. Update the root documentation only after the working vertical slice passes acceptance.

## 13. Acceptance criteria

- One command starts the database, backend, and frontend locally.
- A user can complete the draft-to-main path without editing fixtures or HTML.
- Agent streaming uses Pydantic AI's native AG-UI integration.
- The dependency graph contains neither Semora nor LangGraph.
- Killing an in-flight browser request does not create recovery work or a stuck run.
- PostgreSQL contains SOT domain records but no agent execution journal.
- Backend, frontend, contract, and browser acceptance tests pass.
