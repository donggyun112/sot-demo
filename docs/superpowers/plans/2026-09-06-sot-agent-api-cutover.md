# SOT Pydantic AI, API, and Product Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the product over to the approved workspace-scoped backend, server-canonical Pydantic AI history, server-side completed transcript persistence, and the existing React UI.

**Architecture:** One application-lifetime Pydantic AI Agent receives request-scoped actor, workspace, Branch lineage, canonical PostgreSQL history, and application capability ports. The AG-UI adapter accepts only the latest user input, commits completed messages in its `on_complete` callback before `RUN_FINISHED`, and turns persistence/version failures into `RUN_ERROR`; the frontend only renders the stream and refetches snapshots.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic AI 2.38.0 native AG-UI, psycopg 3, PostgreSQL 16, React 19, TypeScript 5.9, `@ag-ui/pydantic-ai` 0.0.3, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-06-sot-backend-v1-design.md`

## Global Constraints

- Complete `2026-09-06-sot-sharing-consensus.md` first.
- Preserve the existing UI layout and the current direct `@ag-ui/pydantic-ai` streaming behavior; do not reintroduce CopilotKit, Semora, LangGraph, DBOS, a worker, or another API server.
- Build one Pydantic AI Agent at application startup and keep all mutable actor/history/version state in request-scoped `AgentDeps`.
- The server loads completed Branch Turns as canonical history. Client history cannot replace it; only the current latest user input is accepted from AG-UI.
- Do not persist provider chunks, partial messages, AG-UI events, run records, leases, checkpoints, or replay cursors.
- Do not hold a PostgreSQL transaction or connection during model streaming.
- Every Agent tool checks and advances the run's current Branch version in the same transaction as its product mutation.
- The server commits completed user/assistant/tool Turns before emitting `RUN_FINISHED`. Persistence or version conflict emits `RUN_ERROR` and creates no completed transcript.
- Access tokens stay in frontend memory; refresh tokens remain HttpOnly cookies. All authenticated product URLs explicitly contain `workspace_id`.
- Preserve unrelated current frontend edits while applying this plan.

---

## File Structure

- `backend/src/sot/agent/api.py`: workspace-scoped native AG-UI endpoint and secure adapter.
- `backend/src/sot/agent/application.py`: authorize/context/read/run-completion orchestration.
- `backend/src/sot/agent/deps.py`: request-scoped `AgentDeps` and mutable Branch lineage holder.
- `backend/src/sot/agent/messages.py`: Turn ↔ Pydantic AI message mapping and latest-input extraction.
- `backend/src/sot/agent/models.py`: provider-neutral ordered model/fallback construction.
- `backend/src/sot/agent/prompts.py`: server-owned instructions and context rendering.
- `backend/src/sot/agent/tools.py`: capability-based `session_cite` and `sot_update` adapters.
- `backend/tests/agent/`: model, context, tool, completion, and AG-UI contract tests.
- `frontend/src/auth.ts`: in-memory access token, refresh, and Google login flow.
- `frontend/index.html`: Google Identity Services script and root document.
- `frontend/src/api.ts`: Bearer and workspace-scoped REST client.
- `frontend/src/types.ts`: canonical API projections.
- `frontend/src/components/AgentChat.tsx`: workspace-scoped stream and refetch-only completion.
- `frontend/e2e/vertical-slice.spec.ts`: authenticated workspace/toss/fork/consensus/main path.
- `backend/migrations/007_cutover.sql`: only compatibility views/data backfill required by cutover; no table deletion.

### Task 1: Build the Reusable Agent and Canonical Context Boundary

**Files:**

- Create: `backend/src/sot/agent/deps.py`
- Create: `backend/src/sot/agent/messages.py`
- Create: `backend/src/sot/agent/models.py`
- Create: `backend/src/sot/agent/prompts.py`
- Create: `backend/src/sot/agent/application.py`
- Create: `backend/tests/agent/test_models.py`
- Create: `backend/tests/agent/test_context.py`
- Modify: `backend/src/sot/bootstrap/app.py`

**Interfaces:**

- Consumes: `Actor`, `WorkspaceAuthorizer`, `BranchContextReader`, `CompletedTurnsAppender` from `session.contracts`, `UnitOfWorkFactory`.
- Produces: `AgentDeps`, `BranchLineage`, `AgentRunPreparer`, `CompletedRunWriter`, `build_model()`, and one reusable `Agent[AgentDeps, str]`.

- [ ] **Step 1: Move existing model-chain characterization tests to the new module**

```python
def test_build_model_uses_one_reference_directly() -> None:
    assert build_model(("openai:gpt-5.2",)) == "openai:gpt-5.2"


def test_build_model_preserves_fallback_order() -> None:
    model = build_model(("openai:gpt-5.2", "anthropic:claude-sonnet-4-5"))
    assert isinstance(model, FallbackModel)
    assert [str(item) for item in model.models] == [
        "openai:gpt-5.2", "anthropic:claude-sonnet-4-5"
    ]


def test_build_model_rejects_empty_chain() -> None:
    with pytest.raises(ValueError, match="at least one model"):
        build_model(())
```

- [ ] **Step 2: Write a failing context test proving client history is not canonical**

```python
@pytest.mark.asyncio
async def test_prepare_loads_authorized_server_history_and_branch_version() -> None:
    prepared = await preparer.prepare(
        actor=alice, workspace_id=workspace_id, branch_id=branch_id
    )
    assert prepared.canonical_turns == stored_completed_turns
    assert prepared.lineage.expected_version == branch.version
    assert prepared.deps.actor == alice
```

- [ ] **Step 3: Run tests and verify new modules are missing**

Run: `uv run --project backend pytest backend/tests/agent/test_models.py backend/tests/agent/test_context.py -q`

Expected: FAIL on missing `sot.agent.models` and context types.

- [ ] **Step 4: Define request-scoped dependencies**

```python
@dataclass(slots=True)
class BranchLineage:
    expected_version: int

    def advance_to(self, version: int) -> None:
        if version <= self.expected_version:
            raise ValueError("branch version must increase")
        self.expected_version = version


@dataclass(frozen=True, slots=True)
class AgentDeps:
    actor: Actor
    workspace_id: WorkspaceId
    branch_id: BranchId
    lineage: BranchLineage
    cite_creator: CiteCreator
    proposal_creator: ProposalCreator
```

The mutable `BranchLineage` belongs to one request and is never stored on the Agent singleton.

`CompletedRunWriter` receives `session.contracts.CompletedTurnsAppender` by constructor injection. The composition root supplies the session-internal `AppendCompletedTurns` implementation; agent code never imports `session.application`. Call `execute(actor, workspace_id, branch_id, expected_version=..., messages=...)` with immutable `NewTurn` inputs from `session.contracts`, and use the returned `CompletedTurnsResult.branch_version`. This capability owns the short atomic completed-message transaction.

- [ ] **Step 5: Implement canonical Turn mapping and preparation**

`turns_to_model_messages()` groups stored user/tool request Turns into `ModelRequest` and assistant/tool response Turns into `ModelResponse` in ordinal order. It accepts domain DTOs and is the only file in this flow importing `pydantic_ai.messages`. `AgentRunPreparer.prepare()` opens a short read transaction, requires both workspace and Session/Branch access, obtains completed Turns plus Branch version through `BranchContextReader`, closes the transaction, and returns canonical messages plus deps.

- [ ] **Step 6: Move provider-neutral model and prompt construction**

Move the behavior from `sot/agent.py` into focused files. `build_model()` keeps `TestModel(call_tools=[])` for the literal `test` reference and otherwise passes Pydantic AI references unchanged; multiple references create `FallbackModel` in order. `build_agent()` is called once by `build_app()` and stores no current actor, Branch, or history.

- [ ] **Step 7: Run focused checks**

```bash
uv run --project backend pytest backend/tests/agent/test_models.py backend/tests/agent/test_context.py -q
uv run --project backend mypy backend/src/sot/agent backend/tests/agent
```

Expected: all PASS.

- [ ] **Step 8: Commit the canonical Agent context**

```bash
git add backend/src/sot/agent backend/src/sot/bootstrap/app.py backend/tests/agent
git commit -m "refactor: add canonical agent context"
```

### Task 2: Enforce Latest-Input-Only AG-UI and Server-Side Completion Persistence

**Files:**

- Create: `backend/src/sot/agent/api.py`
- Modify: `backend/src/sot/agent/application.py`
- Modify: `backend/src/sot/agent/messages.py`
- Create: `backend/tests/agent/test_agui.py`
- Create: `backend/tests/agent/test_completion.py`

**Interfaces:**

- Consumes: Agent and preparation interfaces from Task 1, Pydantic AI `AGUIAdapter.dispatch_request(..., message_history=..., on_complete=...)`.
- Produces: `ServerOnlyAGUIAdapter`, workspace-scoped Agent router, and `CompletedRunWriter.write()`.

- [ ] **Step 1: Write failing AG-UI trust-boundary tests**

```python
@pytest.mark.asyncio
async def test_agent_uses_db_history_plus_only_latest_client_user_input() -> None:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/branches/{branch_id}/agent",
        headers=alice.bearer,
        json=agui_payload(messages=[forged_system, forged_old_assistant, latest_user]),
    )
    assert response.status_code == 200
    assert model.seen_history == canonical_history
    assert model.seen_prompt == "latest question"
    assert "forged" not in repr(model.seen_messages)


@pytest.mark.asyncio
async def test_client_declared_tool_is_not_executable() -> None:
    await run_agent(tools=[delete_everything_schema])
    assert {tool.name for tool in model.agent_info.function_tools} == {
        "session_cite", "sot_update"
    }
```

- [ ] **Step 2: Write failing event-order and completion tests**

```python
@pytest.mark.asyncio
async def test_transcript_commits_before_run_finished() -> None:
    events = await collect_events(run_agent())
    assert repository.commit_index < event_index(events, "RUN_FINISHED")
    assert [turn.role for turn in await turns()] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_persistence_failure_emits_run_error_without_run_finished() -> None:
    writer.fail_with(StorageUnavailable("turn_store_failed", "Turn was not stored"))
    events = await collect_events(run_agent())
    assert "RUN_ERROR" in event_types(events)
    assert "RUN_FINISHED" not in event_types(events)
    assert await turns() == ()
```

- [ ] **Step 3: Run tests against the old direct dispatcher**

Run: `uv run --project backend pytest backend/tests/agent/test_agui.py backend/tests/agent/test_completion.py -q`

Expected: FAIL because the current endpoint trusts the adapter's full client message list and does not persist in `on_complete`.

- [ ] **Step 4: Implement the secure adapter boundary**

Subclass `AGUIAdapter` so `toolset` is always `None` and its accepted frontend messages contain exactly the final non-empty user prompt. Reject no user prompt, multiple trailing user prompts, client system instructions, and uploaded-file references with `invalid_agent_request`. Build the adapter from the request, pass PostgreSQL-derived `message_history`, `manage_system_prompt="server"`, and request deps into its stream.

- [ ] **Step 5: Persist through Pydantic AI's completion callback**

```python
async def on_complete(result: AgentRunResult[str]) -> AsyncIterator[BaseEvent]:
    await completed_run_writer.write(
        actor=deps.actor,
        workspace_id=deps.workspace_id,
        branch_id=deps.branch_id,
        expected_branch_version=deps.lineage.expected_version,
        new_messages=result.new_messages(),
    )
    if False:
        yield  # callback is an async iterator and emits no extra protocol event
```

Pass this callback to `adapter.run_stream(...)`/`dispatch_request(...)`. Pydantic AI invokes it before the adapter's `after_stream()` emits `RUN_FINISHED`; an exception follows the adapter error path and emits `RUN_ERROR`. `CompletedRunWriter` maps only completed new user/assistant/tool messages, opens one short transaction, appends them atomically with expected Branch version, and returns the new version.

- [ ] **Step 6: Verify cancellation behavior**

Add a streaming model barrier, cancel the HTTP task before completion, and assert there is no completed Turn, run record, checkpoint, or recovery attempt. Already committed tool transactions are not reversed.

- [ ] **Step 7: Run Agent contract checks**

```bash
uv run --project backend pytest backend/tests/agent -q
uv run --project backend ruff check backend/src/sot/agent backend/tests/agent
uv run --project backend mypy backend/src/sot/agent backend/tests/agent
```

Expected: all PASS.

- [ ] **Step 8: Commit the server-owned AG-UI lifecycle**

```bash
git add backend/src/sot/agent backend/tests/agent
git commit -m "feat: persist completed agent turns server-side"
```

### Task 3: Make Agent Tools Participate in Branch Lineage

**Files:**

- Create: `backend/src/sot/agent/tools.py`
- Modify: `backend/src/sot/agent/deps.py`
- Modify: `backend/src/sot/agent/prompts.py`
- Modify: `backend/src/sot/consensus/contracts.py`
- Modify: `backend/src/sot/session/contracts.py`
- Create: `backend/tests/agent/test_tools.py`
- Create: `backend/tests/agent/test_concurrency.py`

**Interfaces:**

- Consumes: `CiteCreator`, `ProposalCreator`, session-owned `BranchMutationResult`, `BranchVersionGuard`, request `BranchLineage`.
- Produces: server-owned `session_cite` and `sot_update` tools that return their new Branch version.

- [ ] **Step 1: Write failing tool-lineage tests**

```python
@pytest.mark.asyncio
async def test_tool_advances_request_lineage_after_atomic_mutation() -> None:
    deps = agent_deps(expected_branch_version=4)
    result = await invoke_session_cite(deps, turn_ids, "public rationale")
    assert result["branchVersion"] == 5
    assert deps.lineage.expected_version == 5
    assert await cite_exists(result["citeId"])


@pytest.mark.asyncio
async def test_competing_run_stops_before_tool_side_effect() -> None:
    winner = agent_deps(expected_branch_version=4)
    loser = agent_deps(expected_branch_version=4)
    await invoke_session_cite(winner, turn_ids, "winner")
    with pytest.raises(VersionConflict):
        await invoke_sot_update(loser, "loser proposal")
    assert await proposals_with_content("loser proposal") == ()
```

- [ ] **Step 2: Run tests and verify old tools have no version contract**

Run: `uv run --project backend pytest backend/tests/agent/test_tools.py backend/tests/agent/test_concurrency.py -q`

Expected: FAIL because current `AgentDeps` routes through `SOTService` and has no lineage.

- [ ] **Step 3: Define exact tool command results**

```python
class CiteCreator(Protocol):
    async def create_from_agent(
        self, *, actor: Actor, workspace_id: WorkspaceId,
        branch_id: BranchId, expected_branch_version: int,
        turn_ids: tuple[TurnId, ...], summary: str,
    ) -> BranchMutationResult: ...
```

The canonical `BranchMutationResult` and `CiteCreator` are imported from `sot.session.contracts`; they are repeated here only to pin the consumed signature. `ProposalCreator.create_from_agent()` comes from `sot.consensus.contracts`, has the same routing/version fields plus proposal content, and returns the same `BranchMutationResult`.

- [ ] **Step 4: Implement thin tool adapters**

Each tool reads `ctx.deps.lineage.expected_version`, calls one application command, and calls `lineage.advance_to(result.branch_version)` only after commit succeeds. It uses actor/workspace/branch from deps and never accepts them from model arguments. `sot_update` creates an open Proposal; it cannot publish main.

- [ ] **Step 5: Test final append after one or more tools**

Run one Agent that starts at version 4, commits two tools returning 5 and 6, then commits its transcript at expected version 6 and receives 7. Run a competing Agent starting at 4 and assert its first mutation emits `RUN_ERROR` with `version_conflict` and no product side effect.

- [ ] **Step 6: Run Agent and cross-module checks**

```bash
uv run --project backend pytest backend/tests/agent backend/tests/session backend/tests/consensus backend/tests/architecture -q
uv run --project backend mypy backend/src backend/tests
```

Expected: all PASS.

- [ ] **Step 7: Commit lineage-aware tools**

```bash
git add backend/src/sot/agent backend/src/sot/session/contracts.py backend/src/sot/consensus/contracts.py backend/tests/agent
git commit -m "feat: guard agent tools with branch versions"
```

### Task 4: Connect the Existing React UI to Authentication and Workspace APIs

**Files:**

- Create: `frontend/src/auth.ts`
- Create: `frontend/src/auth.test.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/api.test.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/index.html`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/components/AgentChat.tsx`
- Modify: `frontend/src/components/AgentChat.streaming.test.tsx`
- Modify: `frontend/src/components/SessionWorkspace.tsx`
- Modify: `frontend/src/components/TossView.tsx`
- Modify: `frontend/src/components/ProposalView.tsx`

**Interfaces:**

- Consumes: `/auth/*`, `/me`, `/workspaces`, workspace-scoped REST routes, and workspace-scoped AG-UI route.
- Produces: in-memory token session, Google login UI, tenant-aware `SOTApi`, and refetch-only Agent completion.

- [ ] **Step 1: Preserve and run the current frontend baseline**

```bash
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

Expected: all PASS before changing files. Do not discard or recreate existing UI/streaming edits.

- [ ] **Step 2: Write failing auth storage tests**

```typescript
it("keeps access tokens in memory and refreshes through the cookie", async () => {
  const auth = new AuthSession(fetchMock);
  await auth.loginWithGoogle("google-id-token");
  expect(auth.accessToken).toBe("access-1");
  expect(localStorage.length).toBe(0);
  await auth.refresh();
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringEndingWith("/api/v1/auth/refresh"),
    expect.objectContaining({ credentials: "include" }),
  );
});
```

- [ ] **Step 3: Write failing workspace-routing API tests**

```typescript
it("routes tenant resources by URL and sends bearer identity", async () => {
  const api = new SOTApi(baseUrl, () => "access-token");
  await api.getSession(workspaceId, sessionId);
  expect(fetchMock).toHaveBeenCalledWith(
    `${baseUrl}/api/v1/workspaces/${workspaceId}/sessions/${sessionId}`,
    expect.objectContaining({ headers: expect.objectContaining({
      Authorization: "Bearer access-token",
    }) }),
  );
});
```

- [ ] **Step 4: Implement auth and typed API boundaries**

`AuthSession` stores the access token in a private field only, always uses `credentials: "include"` for auth routes, performs one refresh-and-retry after a 401, and clears memory on refresh failure. The production login component passes the Google Identity Services credential to `/api/v1/auth/google`. Local/test configuration may render fixed test-Google credentials, but production never shows an actor switcher or sends `X-SOT-User`.

Load `https://accounts.google.com/gsi/client` asynchronously from `frontend/index.html`, initialize it with `VITE_GOOGLE_CLIENT_ID`, and pass only the returned credential string to `AuthSession.loginWithGoogle()`.

`SOTApi` requires `workspaceId` for every tenant method, omits it only for `/me`, `/workspaces`, auth, and public toss read, and decodes the stable error envelope.

- [ ] **Step 5: Update UI state without redesigning it**

Add explicit selected Workspace state above document/session state. Preserve existing components and visual layout. Change toss fork to require a destination Workspace selection. Change Proposal approval UI so full approval shows `approved`; show a separate Merge action only to users with `document.publish` permission.

- [ ] **Step 6: Remove frontend transcript append from Agent completion**

Construct `PydanticAIAgent` with `/api/v1/workspaces/${workspaceId}/branches/${branchId}/agent` and Bearer headers. On `RUN_FINISHED`, call only the session snapshot refetch. On `RUN_ERROR`/abort, retain the input and partial output already shown; never call `appendTurns`, never treat partial text as canonical, and preserve the existing AbortError handling test.

- [ ] **Step 7: Run frontend verification**

```bash
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

Expected: all PASS.

- [ ] **Step 8: Commit the UI connection**

```bash
git add frontend/src
git commit -m "feat: connect UI to workspace authentication"
```

### Task 5: Cut Over Bootstrap, E2E, Containers, and Documentation

**Files:**

- Create: `backend/migrations/007_cutover.sql`
- Modify: `backend/src/sot/bootstrap/app.py`
- Modify: `backend/src/sot/main.py`
- Modify: `backend/tests/integration/test_postgres.py`
- Create: `backend/tests/e2e_app.py`
- Modify: `frontend/e2e/vertical-slice.spec.ts`
- Modify: `frontend/playwright.config.ts`
- Modify: `compose.yaml`
- Modify: `backend/Dockerfile`
- Modify: `frontend/Dockerfile`
- Modify: `.env.example`
- Modify: `README.md`
- Remove: `backend/src/sot/api.py`
- Remove: `backend/src/sot/legacy_agent.py`
- Remove: `backend/src/sot/domain/`
- Remove: `backend/src/sot/store/`
- Replace: `backend/tests/test_domain.py`
- Replace: `backend/tests/test_api.py`
- Replace: `backend/tests/test_agent.py`
- Replace: `backend/tests/test_agui.py`

**Interfaces:**

- Consumes: all canonical module routers, adapters, handlers, AuthFacade, and Agent from prior tasks.
- Produces: one production composition path, one authenticated E2E path, and no runtime dependency on `SOTService`.

- [ ] **Step 1: Write the authenticated E2E flow first**

Create `backend/tests/e2e_app.py` with the real composition root and a `StaticGoogleTokenVerifier` that maps only `google-test-alice` and `google-test-bob` to valid Google claim dictionaries. Configure Playwright's test web server to run this app with `SOT_ENVIRONMENT=test`; production composition continues to inject the real verifier. Exercise the real `/auth/google` and SOT token flow. The browser test must:

```text
login Alice -> select workspace -> create private session
-> stream Agent response -> verify server-persisted completed Turns
-> curate -> publish Bundle -> create toss
-> public read without auth
-> login Bob -> choose Bob workspace -> detached fork
-> create Proposal -> Bob approves -> Alice approves
-> verify status approved and main unchanged
-> Alice with document.publish merges
-> verify new main revision and provenance
```

Assert the fork contains only public BundleItems, Alice's private Turns are unavailable to Bob, and a second concurrent Agent run on one Branch ends in `version_conflict` without tool side effects.

- [ ] **Step 2: Run E2E and observe legacy-contract failures**

Run: `pnpm --dir frontend e2e`

Expected: FAIL until bootstrap, containers, seed data, and UI all use canonical auth/workspace routes.

- [ ] **Step 3: Add only required compatibility migration/backfill**

`007_cutover.sql` inserts deterministic local-demo identities, one workspace, memberships, document, and revision only when canonical rows are absent. Use Alice `00000000-0000-4000-8000-0000000000a1`, Bob `00000000-0000-4000-8000-0000000000b0`, workspace `00000000-0000-4000-8000-000000000100`, and document `00000000-0000-4000-8000-000000000200`. Use `INSERT ... ON CONFLICT DO NOTHING`, record the source as `legacy-001`, and do not drop or rewrite 001 tables.

- [ ] **Step 4: Make canonical `build_app()` the only runtime composition**

Construct pool/UoW, module PostgreSQL adapters, capability contracts, handlers, AuthFacade, one Agent, exception mapper, and routers explicitly. Lifespan opens/closes the pool and performs readiness checks only. Remove bootstrap seeding and migration execution from startup. `sot/main.py` contains only `app = build_app(Settings())` plus exports.

- [ ] **Step 5: Remove legacy Python runtime after focused parity passes**

Delete the old global `SOTService`, repository, monolithic routes, and `legacy_agent.py` only after all canonical module tests pass. Move still-valid characterization assertions into their owning module/API tests; do not delete coverage for the draft-to-main workflow, provider fallback, error envelope, PostgreSQL reconnect, or AG-UI event ordering.

- [ ] **Step 6: Update deployment configuration**

Compose keeps exactly `db`, `backend`, and `frontend`. Backend startup runs after an explicit one-shot migration command/service has succeeded; web replicas never race migrations. Configure `SOT_ENVIRONMENT`, `SOT_DATABASE_URL`, `SOT_MODELS`, `SOT_JWT_SECRET`, `SOT_GOOGLE_CLIENT_ID`, and provider keys with placeholder values in `.env.example`. Keep PostgreSQL 16 and the existing frontend proxy.

- [ ] **Step 7: Update README architecture and response examples**

Document the seven-module monolith, Google→SOT token flow, explicit workspace URLs, public toss exception, server-side Agent transcript commit, explicit Proposal merge, and migration command. Remove `SOTService`, automatic publication-on-last-approval, CopilotKit, frontend `appendTurns`, and development actor-switch claims.

- [ ] **Step 8: Run complete verification**

```bash
uv run --project backend pytest backend/tests -q
uv run --project backend ruff check backend
uv run --project backend mypy backend/src backend/tests
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend build
docker compose build
pnpm --dir frontend e2e
```

Expected: all PASS. The opt-in live provider smoke test may remain skipped when no provider key is configured.

- [ ] **Step 9: Commit the canonical cutover**

```bash
git add backend frontend compose.yaml .env.example README.md
git commit -m "feat: cut over to canonical SOT backend"
```
