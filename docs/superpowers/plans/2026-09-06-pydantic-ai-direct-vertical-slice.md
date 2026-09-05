# Pydantic AI Direct Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a working SOT draft-to-main product slice with one FastAPI backend, one PostgreSQL database, a React/CopilotKit UI, and Pydantic AI's native AG-UI adapter.

**Architecture:** Replace the separate durable Agent Server with an in-process Pydantic AI `Agent` mounted inside the Platform FastAPI application. Keep completed SOT sessions and consensus records as ordinary domain data while accepting loss of partial model runs on disconnect.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic AI 2.38, psycopg 3, PostgreSQL 16, React, TypeScript, Vite, CopilotKit vNext, AG-UI, Vitest, Playwright, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-06-pydantic-ai-direct-vertical-slice-design.md`

## Global Constraints

- Use one FastAPI backend process and one PostgreSQL database.
- Use one asyncio task per AG-UI request; client disconnect cancellation is acceptable.
- Use Pydantic AI directly; the dependency graph must contain neither Semora nor LangGraph.
- Store completed SOT domain records only; do not create an agent run journal, lease, checkpoint, replay cursor, or recovery scanner.
- Configure models as ordered provider-neutral Pydantic AI references and construct a `FallbackModel` when more than one is configured.
- Keep all domain mutations behind the same authorization-aware service methods for HTTP handlers and agent tools.
- Use fixed `alice` and `bob` development identities selected by `X-SOT-User` for this local slice.

---

## File Structure

### Backend

- `backend/pyproject.toml`: Python dependencies and test/tool configuration.
- `backend/src/sot/__init__.py`: package exports.
- `backend/src/sot/settings.py`: database, model-chain, CORS, and frontend-build settings.
- `backend/src/sot/domain/models.py`: immutable domain records and request value objects.
- `backend/src/sot/domain/errors.py`: stable domain error codes.
- `backend/src/sot/domain/ports.py`: repository protocol.
- `backend/src/sot/domain/service.py`: authorization and state transitions.
- `backend/src/sot/store/memory.py`: deterministic unit-test repository.
- `backend/src/sot/store/postgres.py`: psycopg repository and transaction boundary.
- `backend/src/sot/agent.py`: Pydantic AI dependencies, model construction, instructions, and tools.
- `backend/src/sot/api.py`: REST endpoints, dev identity dependency, and AG-UI dispatch.
- `backend/src/sot/main.py`: lifespan, CORS, and static frontend mounting.
- `backend/migrations/001_platform.sql`: compact product-only schema and seed records.
- `backend/tests/test_domain.py`: domain state transition tests.
- `backend/tests/test_api.py`: REST contract tests with the memory repository.
- `backend/tests/test_agent.py`: Pydantic AI model/tool tests.
- `backend/tests/test_agui.py`: native AG-UI streaming contract.
- `backend/tests/integration/test_postgres.py`: repository integration path.

### Frontend

- `frontend/package.json`: Vite, React, CopilotKit, AG-UI, test, and build scripts.
- `frontend/src/main.tsx`: application bootstrap.
- `frontend/src/App.tsx`: top-level view state and resource loading.
- `frontend/src/api.ts`: typed REST client and development identity header.
- `frontend/src/types.ts`: API response types.
- `frontend/src/components/AppShell.tsx`: header and responsive navigation.
- `frontend/src/components/DocumentView.tsx`: main revision and provenance display.
- `frontend/src/components/SessionWorkspace.tsx`: branch conversation, CopilotKit chat, and curation rail.
- `frontend/src/components/TossView.tsx`: public bundle reader and fork action.
- `frontend/src/components/ProposalView.tsx`: comparison, approvals, and publication result.
- `frontend/src/styles.css`: responsive visual system derived from `msbd-real.html`.
- `frontend/src/**/*.test.tsx`: component and client tests.
- `frontend/e2e/vertical-slice.spec.ts`: draft-to-main browser acceptance.

### Repository

- `compose.yaml`: one PostgreSQL service plus backend and frontend services.
- `.env.example`: provider-neutral local configuration.
- `README.md`: working setup and current architecture.
- Remove `agent-server/` and `packages/service-auth/` after equivalent direct behavior is verified.

---

### Task 1: Create the Direct Pydantic AI Backend Shell

**Files:**

- Create: `backend/pyproject.toml`
- Create: `backend/src/sot/__init__.py`
- Create: `backend/src/sot/settings.py`
- Create: `backend/src/sot/agent.py`
- Create: `backend/src/sot/api.py`
- Create: `backend/src/sot/main.py`
- Test: `backend/tests/test_agent.py`
- Test: `backend/tests/test_agui.py`

- [ ] Write `test_build_model_uses_one_reference_directly` and `test_build_model_preserves_fallback_order` around this public factory:

```python
def build_model(references: tuple[str, ...]) -> Model | str:
    if not references:
        raise ValueError("at least one model is required")
    if len(references) == 1:
        return references[0]
    return FallbackModel(references[0], *references[1:])
```

- [ ] Run `uv run --project backend pytest backend/tests/test_agent.py -q` and confirm import failure proves the backend does not exist yet.

- [ ] Add `pydantic-ai-slim[ag-ui,anthropic,google,openai,openrouter]==2.38.0`, FastAPI, pydantic-settings, psycopg, uvicorn, and the existing dev tools to `backend/pyproject.toml`; do not add Semora packages.

- [ ] Implement `AgentSettings` with `SOT_MODELS` parsed as an ordered JSON tuple and implement `build_model()` exactly as tested.

- [ ] Define `AgentDeps(user_id: str, branch_id: UUID, service: SOTService)` and construct one server-owned `Agent[AgentDeps, str]` with concise SOT instructions.

- [ ] Write `test_agui_endpoint_streams_standard_events` using a Pydantic AI `FunctionModel` override and this endpoint shape:

```python
@router.post("/api/v1/branches/{branch_id}/agent")
async def run_agent(branch_id: UUID, request: Request, user: DevUser) -> Response:
    deps = AgentDeps(user_id=user.id, branch_id=branch_id, service=request.app.state.service)
    return await AGUIAdapter.dispatch_request(request, agent=request.app.state.agent, deps=deps)
```

- [ ] Run the focused AG-UI test and confirm it fails because the route is absent.

- [ ] Implement `create_app(service, agent)` with `/healthz` and the native `AGUIAdapter.dispatch_request()` route; configure backend-owned system instructions.

- [ ] Run `pytest`, Ruff, and mypy for the new backend and commit:

```bash
git add backend
git commit -m "feat: add direct Pydantic AI AG-UI backend"
```

### Task 2: Implement the SOT Domain State Machine in Memory

**Files:**

- Create: `backend/src/sot/domain/models.py`
- Create: `backend/src/sot/domain/errors.py`
- Create: `backend/src/sot/domain/ports.py`
- Create: `backend/src/sot/domain/service.py`
- Create: `backend/src/sot/store/memory.py`
- Test: `backend/tests/test_domain.py`

- [ ] Write failing tests for the complete path using fixed users `alice` and `bob`: create document/session/initial branch, append completed turns, cite selected turns, publish a toss, fork as Bob, create a proposal, approve as Alice and Bob, and assert revision 2 becomes current only after the second distinct approval.

- [ ] Define UUID-backed frozen records with explicit status enums:

```python
class ProposalStatus(StrEnum):
    OPEN = "open"
    PUBLISHED = "published"

@dataclass(frozen=True, slots=True)
class Turn:
    id: UUID
    branch_id: UUID
    ordinal: int
    role: Literal["user", "assistant"]
    content: str
```

- [ ] Define a `SOTRepository` protocol whose methods read and write complete domain records; include `transaction()` as an async context manager so publication is atomic in both memory and PostgreSQL implementations.

- [ ] Implement `SOTService` methods with these stable signatures:

```python
async def create_session(self, *, document_id: UUID, owner_id: str, title: str) -> SessionView: ...
async def append_turns(self, *, branch_id: UUID, actor_id: str, turns: tuple[NewTurn, ...]) -> tuple[Turn, ...]: ...
async def create_cite(self, *, branch_id: UUID, actor_id: str, turn_ids: tuple[UUID, ...], summary: str) -> Cite: ...
async def create_toss(self, *, cite_id: UUID, actor_id: str) -> Toss: ...
async def fork_toss(self, *, token: str, actor_id: str) -> Branch: ...
async def create_proposal(self, *, branch_id: UUID, actor_id: str, content: str) -> Proposal: ...
async def approve_proposal(self, *, proposal_id: UUID, actor_id: str) -> ApprovalResult: ...
```

- [ ] Enforce owner/member access, immutable cite turn selection, unique toss tokens, one approval per user, two distinct approvals, and one publication per proposal with named `DomainError` codes.

- [ ] Implement `MemorySOTRepository` without mocks and make every focused test pass.

- [ ] Run backend pytest/Ruff/mypy and commit:

```bash
git add backend/src/sot/domain backend/src/sot/store/memory.py backend/tests/test_domain.py
git commit -m "feat: add SOT domain state transitions"
```

### Task 3: Add the Platform REST API

**Files:**

- Modify: `backend/src/sot/api.py`
- Test: `backend/tests/test_api.py`

- [ ] Write failing HTTP tests for `X-SOT-User`, error response codes, and these routes:

```text
GET  /api/v1/bootstrap
GET  /api/v1/documents/{document_id}
POST /api/v1/documents/{document_id}/sessions
GET  /api/v1/sessions/{session_id}
POST /api/v1/branches/{branch_id}/turns
POST /api/v1/branches/{branch_id}/cites
POST /api/v1/cites/{cite_id}/tosses
GET  /api/v1/tosses/{token}
POST /api/v1/tosses/{token}/fork
POST /api/v1/branches/{branch_id}/proposals
POST /api/v1/proposals/{proposal_id}/approve
```

- [ ] Implement Pydantic request/response schemas with `extra="forbid"`; return errors as `{"error":{"code":...,"message":...}}` and map not-found to 404, forbidden to 403, invalid transitions to 409, and input validation to 422.

- [ ] Resolve `alice` by default and accept only `alice` or `bob` from `X-SOT-User`; include both identities in `/bootstrap` so the demo UI can switch actors.

- [ ] Make public toss reads the only route that does not require a development identity.

- [ ] Run the API tests plus the backend suite and commit:

```bash
git add backend/src/sot/api.py backend/tests/test_api.py
git commit -m "feat: expose SOT platform API"
```

### Task 4: Persist Product State in PostgreSQL

**Files:**

- Create: `backend/migrations/001_platform.sql`
- Create: `backend/src/sot/store/postgres.py`
- Create: `backend/tests/integration/test_postgres.py`
- Modify: `backend/src/sot/main.py`
- Modify: `backend/src/sot/settings.py`

- [ ] Write a PostgreSQL integration test that applies the migration, runs the same draft-to-main service scenario as Task 2, reconnects with a new repository instance, and reads the published revision.

- [ ] Create normalized tables for documents, revisions, sessions, branches, turns, cites, cite turns, tosses, proposals, and approvals. Add database constraints for unique turn ordinals, toss tokens, proposal approvals, and revision numbers.

- [ ] Implement `PostgresSOTRepository` with `psycopg_pool.AsyncConnectionPool`; make `transaction()` pin one connection and use one database transaction for second approval plus revision publication.

- [ ] Add a FastAPI lifespan that opens the pool, applies checked-in migrations, seeds the demo document and revision idempotently, and closes the pool.

- [ ] Run the integration test against `postgresql://sot:sot@localhost:54329/sot`, then run all backend checks and commit:

```bash
git add backend/migrations backend/src/sot/store backend/src/sot/main.py backend/src/sot/settings.py backend/tests/integration
git commit -m "feat: persist SOT product state in PostgreSQL"
```

### Task 5: Connect Server-Owned Agent Tools

**Files:**

- Modify: `backend/src/sot/agent.py`
- Test: `backend/tests/test_agent.py`
- Test: `backend/tests/test_agui.py`

- [ ] Write failing `FunctionModel` tests proving the agent can call only `session_cite` and `sot_update`, and that both tools apply the authenticated actor and route branch from `AgentDeps`.

- [ ] Implement tools as thin calls to `SOTService`:

```python
@agent.tool
async def session_cite(ctx: RunContext[AgentDeps], turn_ids: list[UUID], summary: str) -> dict[str, str]:
    cite = await ctx.deps.service.create_cite(
        branch_id=ctx.deps.branch_id,
        actor_id=ctx.deps.user_id,
        turn_ids=tuple(turn_ids),
        summary=summary,
    )
    return {"citeId": str(cite.id)}
```

- [ ] Implement `sot_update` as proposal creation, not direct main mutation; return the proposal ID and open status.

- [ ] Test that arbitrary client tool schemas do not become executable server tools and that backend instructions remain authoritative.

- [ ] Run all backend checks and commit:

```bash
git add backend/src/sot/agent.py backend/tests/test_agent.py backend/tests/test_agui.py
git commit -m "feat: connect agent to authorized SOT tools"
```

### Task 6: Build the React and CopilotKit Product UI

**Files:**

- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/DocumentView.tsx`
- Create: `frontend/src/components/SessionWorkspace.tsx`
- Create: `frontend/src/components/TossView.tsx`
- Create: `frontend/src/components/ProposalView.tsx`
- Create: `frontend/src/styles.css`
- Test: `frontend/src/**/*.test.tsx`

- [ ] Scaffold Vite React TypeScript with scripts `dev`, `build`, `test`, `typecheck`, and dependencies `@copilotkitnext/react`, `@ag-ui/pydantic-ai`, React 19, and Zod. Use the direct `PydanticAIAgent` connection; do not add a Node agent runtime.

- [ ] Write API client tests proving every mutation sends `X-SOT-User`, public toss reads omit it, and non-2xx problem codes become typed `ApiError` instances.

- [ ] Implement the shell with actor switching, document/session navigation, narrow-screen navigation, visible loading states, retryable errors, keyboard focus, and `aria-live` status announcements.

- [ ] Write component tests for empty document state, loaded main revision, session creation, streaming chat, cite selection, toss creation, fork creation, proposal approval, and publication.

- [ ] Connect the session workspace to the native endpoint:

```tsx
const agent = new PydanticAIAgent({
  url: `${apiBase}/api/v1/branches/${branch.id}/agent`,
  headers: { "X-SOT-User": actor.id },
});
```

- [ ] On successful agent completion, persist the completed user/assistant pair through `/branches/{branch_id}/turns`; on disconnect or error, retain unsaved text in the UI and show retry/save actions.

- [ ] Recreate the static demo's information hierarchy with responsive CSS while keeping SOT controls as ordinary React components around `CopilotChat`.

- [ ] Run frontend tests, TypeScript, and production build and commit:

```bash
git add frontend
git commit -m "feat: add working SOT React interface"
```

### Task 7: Replace the Legacy Runtime and Verify the Vertical Slice

**Files:**

- Modify: `compose.yaml`
- Create: `.env.example`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `frontend/e2e/vertical-slice.spec.ts`
- Modify: `.gitignore`
- Modify: `README.md`
- Remove: `agent-server/`
- Remove: `packages/service-auth/`

- [ ] Write the Playwright acceptance test that switches between Alice and Bob and performs: create session, send an agent message, save completed turns, create cite/toss, open toss as Bob, fork, propose text, approve as Bob, switch to Alice, approve, and verify main revision 2 with cite provenance.

- [ ] Update Compose to start `db`, `backend`, and `frontend`; wait for PostgreSQL health before backend and proxy `/api` from the frontend container to backend.

- [ ] Add `.env.example` with `SOT_DATABASE_URL`, `SOT_MODELS`, and provider credential names using placeholder values only.

- [ ] Delete the old Agent Server, service-auth package, Semora migrations, agent database volume, and their tests after the new focused suites pass.

- [ ] Update `README.md` to describe the one-process backend and commands:

```bash
cp .env.example .env
docker compose up --build
```

- [ ] Run fresh verification:

```bash
uv run --project backend pytest backend/tests -q
uv run --project backend ruff format --check backend/src backend/tests
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy backend/src backend/tests
uv lock --project backend --check
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
docker compose build
pnpm --dir frontend exec playwright test
```

- [ ] Confirm `rg -n 'semora|langgraph|agent-db|Last-Event-ID|run_lease' backend frontend compose.yaml README.md` has no runtime references.

- [ ] Commit the completed migration:

```bash
git add -A
git commit -m "feat: ship direct Pydantic AI SOT vertical slice"
```
