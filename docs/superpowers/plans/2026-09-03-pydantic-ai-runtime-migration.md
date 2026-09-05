# Pydantic AI Runtime Migration Implementation Plan

> **Superseded:** Replaced on 2026-09-04 by
> `docs/superpowers/plans/2026-09-04-pydantic-ai-local-async-runtime.md`.
> This file is retained only as historical implementation context.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Semora with a Pydantic AI 2.38.0 agent running in DBOS while preserving strict AG-UI admission, detached durable execution, PostgreSQL replay, explicit abort, and server-owned tool authority.

**Architecture:** Construct one deployment-stable Pydantic AI agent before `DBOS.launch()`. Admit and persist requests through the existing Agent store, enqueue one deterministic DBOS workflow per public run, project Pydantic native events into idempotent PostgreSQL AG-UI events, and keep HTTP/SSE as a replay-only boundary.

**Tech Stack:** Python 3.12, Pydantic AI 2.38.0, DBOS, OpenRouter, AG-UI 0.1.x, FastAPI, psycopg 3, PostgreSQL, pytest, mypy, Ruff, uv.

**Spec:** `docs/superpowers/specs/2026-09-03-pydantic-ai-runtime-migration-design.md`

## Global Constraints

- Pin `pydantic-ai-slim[ag-ui,dbos,openrouter]==2.38.0`.
- Keep `ag-ui-protocol>=0.1.19,<0.2` as a direct dependency.
- Keep `POST /ag-ui`, `POST /runs/{run_id}/abort`, authentication, ownership hiding, request size, cursor, UUIDv7, and payload-idempotency behavior compatible.
- A disconnected SSE subscriber must not cancel or own execution.
- Only authenticated explicit abort may cancel a live workflow.
- Client tool descriptors select server-owned tools by name; their descriptions and schemas never become executable authority.
- Every runtime event must be committed to `agent_event` before a subscriber can observe it.
- DBOS workflow IDs, agent names, queue names, toolset IDs, workflow names, and step names are deployment-stable.
- Runtime-exposed errors must not contain secrets, raw subjects, provider bodies, or DBOS internals.
- The workspace currently has no `.git`; execute commit steps only after Git metadata is restored.

## File Structure

- `agent-server/src/agent_core/identity.py`: runtime-neutral trusted execution identity shared by context loading and run mapping.
- `agent-server/src/agent_core/command.py`: strict AG-UI-to-Pydantic run input mapping and deferred approval conversion.
- `agent-server/src/agent_core/agent.py`: deployment agent construction and serializable per-run dependency assembly.
- `agent-server/src/agent_core/tools.py`: server tool registry plus Pydantic function-tool adaptation and deterministic selection filtering.
- `agent-server/src/agent_core/projection.py`: stateful Pydantic-native-to-AG-UI transformation and stable producer-key generation.
- `agent-server/src/agent_core/runtime.py`: runtime-neutral launcher protocol, DBOS configuration, workflow registration, enqueue/status/cancel adapter.
- `agent-server/src/agent_core/service.py`: admission, assembly, durable launch, replay, and abort orchestration only.
- `agent-server/src/agent_core/store/postgres.py`: generic workflow/deferred identifiers and idempotent event persistence.
- `agent-server/migrations/003_pydantic_ai.sql`: live schema rename/backfill/constraint migration.
- `agent-server/tests/test_pydantic_contract.py`: installed Pydantic AI/DBOS API contract.
- `agent-server/tests/test_command_mapper.py`: Pydantic message and deferred result mapping.
- `agent-server/tests/test_agent_assembly.py`: singleton agent, instructions, and server-owned tool filtering.
- `agent-server/tests/test_projection.py`: native event projection and deterministic retry behavior.
- `agent-server/tests/test_runtime.py`: DBOS launcher/worker behavior through fakes.
- `agent-server/tests/integration/test_agent_postgres.py`: migration, workflow IDs, event idempotency, replay, interrupt, abort.
- `agent-server/tests/e2e/test_openrouter.py`: HTTP-to-DBOS-to-Pydantic-to-OpenRouter-to-SSE path.

---

### Task 1: Replace the Runtime Dependency Contract

**Files:**

- Modify: `agent-server/pyproject.toml`
- Modify: `agent-server/uv.lock`
- Delete: `agent-server/tests/test_semora_contract.py`
- Create: `agent-server/tests/test_pydantic_contract.py`

**Interfaces:**

- Consumes: package metadata only.
- Produces: installed `pydantic_ai.Agent`, `OpenRouterModel`, `AGUIEventStream`, `DeferredToolRequests`, `DeferredToolResults`, `DBOSDurability`, and `dbos.DBOS` APIs for later tasks.

- [ ] **Step 1: Write the failing installed-package contract test**

```python
# tests/test_pydantic_contract.py
from dbos import DBOS, DBOSConfig, Queue
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.durable_exec.dbos import DBOSDurability
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.ui.ag_ui import AGUIEventStream


def test_deployed_pydantic_ai_exposes_agent_server_contract() -> None:
    assert Agent is not None
    assert DeferredToolRequests is not None
    assert DeferredToolResults is not None
    assert DBOSDurability is not None
    assert OpenRouterModel is not None
    assert AGUIEventStream is not None
    assert DBOS is not None
    assert DBOSConfig is not None
    assert Queue is not None
```

- [ ] **Step 2: Run the contract test and verify it fails because Pydantic AI/DBOS is absent**

Run: `uv run --project agent-server pytest agent-server/tests/test_pydantic_contract.py -q`

Expected: collection fails with `ModuleNotFoundError` for `pydantic_ai` or `dbos`.

- [ ] **Step 3: Replace Semora dependencies and lock them**

Set the runtime dependency list to contain:

```toml
"pydantic-ai-slim[ag-ui,dbos,openrouter]==2.38.0",
```

Remove `semora[openrouter,postgres]==0.2.0`. Then run:

```bash
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv lock --project agent-server
UV_CACHE_DIR=/tmp/agent-server-uv-cache uv sync --project agent-server --all-groups
```

- [ ] **Step 4: Run the contract test and inspect the installed signatures used below**

Run: `uv run --project agent-server pytest agent-server/tests/test_pydantic_contract.py -q`

Expected: `1 passed`.

Run: `uv run --project agent-server python -c "from inspect import signature; from pydantic_ai import Agent; from pydantic_ai.durable_exec.dbos import DBOSDurability; print(signature(Agent)); print(signature(DBOSDurability))"`

Expected: signatures expose the constructor parameters referenced by this plan. Adjust only keyword spelling to the installed 2.38.0 public API; do not change the design boundaries.

- [ ] **Step 5: Remove the Semora contract test and commit**

```bash
git add agent-server/pyproject.toml agent-server/uv.lock agent-server/tests/test_pydantic_contract.py
git rm agent-server/tests/test_semora_contract.py
git commit -m "build(agent): replace semora with pydantic ai"
```

---

### Task 2: Introduce Runtime-Neutral Identity and Pydantic Run Mapping

**Files:**

- Create: `agent-server/src/agent_core/identity.py`
- Modify: `agent-server/src/agent_core/context.py`
- Replace: `agent-server/src/agent_core/command.py`
- Modify: `agent-server/tests/test_context_loader.py`
- Replace: `agent-server/tests/test_command_mapper.py`

**Interfaces:**

- Produces: `ExecutionIdentity(run_id: str, conversation_id: str, subject: str)`.
- Produces: `MappedRun(identity, user_prompt, message_history, deferred_tool_results)`.
- Produces: `RunInputMapper(resolve_interrupt).map(request, subject=...) -> MappedRun`.
- Consumes: `PostgresAgentStore.resolve_interrupt()` returning a `DeferredInterrupt` with `deferred_call_id` and `tool_call_id`.

- [ ] **Step 1: Write failing identity and prompt mapping tests**

```python
from pydantic_ai.messages import ModelRequest, ModelResponse

from agent_core.command import RunInputMapper
from agent_core.identity import ExecutionIdentity


async def test_maps_agui_snapshot_to_pydantic_history_and_prompt() -> None:
    mapped = await RunInputMapper().map(_input(), subject="agtsub:v1:owner")
    assert mapped.identity == ExecutionIdentity(
        run_id=RUN_ID,
        conversation_id=THREAD_ID,
        subject="agtsub:v1:owner",
    )
    assert mapped.user_prompt == "latest question"
    assert [type(message) for message in mapped.message_history] == [
        ModelRequest,
        ModelResponse,
    ]
    assert mapped.deferred_tool_results is None


async def test_rejects_external_system_and_developer_messages() -> None:
    with pytest.raises(CommandMappingError) as captured:
        await RunInputMapper().map(_input(messages=[SYSTEM_MESSAGE]), subject="owner")
    assert captured.value.code == "unsupported_message_role"
```

- [ ] **Step 2: Run the focused tests and verify missing runtime-neutral types fail**

Run: `uv run --project agent-server pytest agent-server/tests/test_command_mapper.py agent-server/tests/test_context_loader.py -q`

Expected: import or assertion failures for `ExecutionIdentity`, `MappedRun`, and `RunInputMapper`.

- [ ] **Step 3: Add the runtime-neutral identity and remove `semora.ExecutionContext`**

```python
# src/agent_core/identity.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    run_id: str
    conversation_id: str
    subject: str
```

Change `AgentContextSource.load()` and `ContextLoader.load()` to accept `ExecutionIdentity`. Preserve all existing canonical JSON validation and source stamping behavior.

- [ ] **Step 4: Implement strict Pydantic message mapping**

Use `AGUIAdapter.load_messages()` only after explicit role validation. For a normal request, remove the final text user message before loading history and return its text as `user_prompt`. Preserve `invalid_tool_call_arguments` by parsing every assistant tool-call JSON argument before adapter conversion.

```python
@dataclass(frozen=True, slots=True)
class MappedRun:
    identity: ExecutionIdentity
    user_prompt: str | None
    message_history: list[ModelMessage]
    deferred_tool_results: DeferredToolResults | None
```

For one `resume[]` entry, resolve the authenticated interrupt and create:

```python
results = DeferredToolResults()
results.approvals[resolved.tool_call_id] = (
    ToolDenied("Cancelled by user.")
    if entry.status == "cancelled"
    else ToolApproved(override_args=edited_args)
)
```

Reject zero or multiple resume entries, non-object approval payloads, missing `approved`, and mismatched public/deferred tool IDs with `CommandMappingError("invalid_command", ...)`.

- [ ] **Step 5: Run mapper/context tests**

Run: `uv run --project agent-server pytest agent-server/tests/test_command_mapper.py agent-server/tests/test_context_loader.py -q`

Expected: all pass with no Semora or LangChain imports.

- [ ] **Step 6: Commit**

```bash
git add agent-server/src/agent_core/identity.py agent-server/src/agent_core/context.py agent-server/src/agent_core/command.py agent-server/tests/test_context_loader.py agent-server/tests/test_command_mapper.py
git commit -m "refactor(agent): map ag-ui input to pydantic runs"
```

---

### Task 3: Build One Deployment Agent and Server-Owned Toolset

**Files:**

- Modify: `agent-server/src/agent_core/tools.py`
- Replace: `agent-server/src/agent_core/agent.py`
- Modify: `agent-server/src/agent_core/prompt.py`
- Replace: `agent-server/tests/test_agent_assembly.py`

**Interfaces:**

- Produces: serializable `AgentRunDeps(identity, instructions, selected_tool_names)`.
- Produces: `AgentRunAssembly.assemble(request, identity, loaded_context) -> AgentRunDeps`.
- Produces: `build_deployment_agent(settings, registry, durability) -> Agent[AgentRunDeps, str | DeferredToolRequests]`.
- Consumes: `ToolRegistry.registered()` and `ToolRegistry.select()`.

- [ ] **Step 1: Write failing tests for singleton construction and tool authority**

```python
def test_builds_named_openrouter_agent_once(tmp_path: Path) -> None:
    durability = object()
    agent = build_deployment_agent(
        settings=_settings(tmp_path),
        registry=_registry(),
        durability=cast(Any, durability),
    )
    assert agent.name == "discussion-agent"
    assert agent.model.model_name == "openai/gpt-5.2"


async def test_run_deps_expose_only_server_selected_tools(tmp_path: Path) -> None:
    deps = await _assembly(tmp_path).assemble(
        request=_request_with_spoofed_lookup_schema(),
        identity=_identity(),
        loaded_context=_context(),
    )
    assert deps.selected_tool_names == ("lookup",)
    assert "server-owned lookup instructions" in deps.instructions
    assert "caller-owned description" not in deps.instructions
```

- [ ] **Step 2: Run the assembly tests and verify they fail on the Semora agent**

Run: `uv run --project agent-server pytest agent-server/tests/test_agent_assembly.py -q`

Expected: failures for missing `AgentRunDeps`, `AgentRunAssembly`, and `build_deployment_agent`.

- [ ] **Step 3: Adapt registered tools to Pydantic AI**

Add `requires_approval: bool = False` to `RegisteredTool`. Expose immutable registry order and build one Pydantic `FunctionToolset` with stable ID `agent-server-tools-v1`. Tool wrappers must call the existing server executor and ignore any caller schema.

```python
@dataclass(frozen=True, slots=True)
class AgentRunDeps:
    identity: ExecutionIdentity
    instructions: str
    selected_tool_names: tuple[str, ...]
```

Add a pure preparation function that filters tool definitions using `ctx.deps.selected_tool_names`; an unknown name remains impossible because `ToolRegistry.select()` validates before admission.

- [ ] **Step 4: Construct the deployment agent before DBOS launch**

```python
model = OpenRouterModel(
    settings.openrouter_model,
    provider=OpenRouterProvider(api_key=settings.openrouter_api_key.get_secret_value()),
)
return Agent(
    model,
    name=settings.name,
    deps_type=AgentRunDeps,
    output_type=[str, DeferredToolRequests],
    toolsets=[registry.as_toolset()],
    capabilities=[prepare_tools_capability, durability],
    instructions=dynamic_instructions,
)
```

Keep prompt order unchanged: base prompt, server policy, selected tool instructions, untrusted context block.

- [ ] **Step 5: Run the assembly, prompt, and tool tests**

Run: `uv run --project agent-server pytest agent-server/tests/test_agent_assembly.py -q`

Expected: all pass; no `semora`, `semora_llm`, or `langchain_core` import remains in these modules.

- [ ] **Step 6: Commit**

```bash
git add agent-server/src/agent_core/agent.py agent-server/src/agent_core/tools.py agent-server/src/agent_core/prompt.py agent-server/tests/test_agent_assembly.py
git commit -m "feat(agent): build durable pydantic deployment agent"
```

---

### Task 4: Migrate Agent Persistence to Generic Workflow Identities

**Files:**

- Create: `agent-server/migrations/003_pydantic_ai.sql`
- Modify: `agent-server/src/agent_core/store/postgres.py`
- Modify: `agent-server/tests/integration/conftest.py`
- Modify: `agent-server/tests/integration/test_agent_postgres.py`

**Interfaces:**

- Produces: `AgentRequest(workflow_id, run_id, thread_id, original_input, terminal_sequence)`.
- Produces: `DeferredInterrupt(interrupt_id, deferred_call_id, tool_call_id)`.
- Produces: `append_event(run_id, event, producer_key: str, terminal=False) -> StoredEvent` with mandatory runtime producer keys.

- [ ] **Step 1: Write failing migration and generic-name integration assertions**

```python
async def test_runtime_columns_are_generic_and_producer_keys_are_idempotent(agent_pool) -> None:
    columns = await _columns(agent_pool, "agent", "agent_request")
    assert "workflow_id" in columns
    assert "semora_run_id" not in columns

    first = await store.append_event(run_id, event, producer_key="model:0:event:0:text")
    repeated = await store.append_event(run_id, event, producer_key="model:0:event:0:text")
    assert repeated == first
    assert len(await store.replay(run_id, after_sequence=0)) == 1
```

- [ ] **Step 2: Run the Postgres integration test and verify old columns fail**

Run: `AGENT_TEST_DATABASE_URL=$AGENT_TEST_DATABASE_URL uv run --project agent-server pytest agent-server/tests/integration/test_agent_postgres.py -q`

Expected: the new generic column assertion fails before migration 003 is applied.

- [ ] **Step 3: Write the live migration**

`003_pydantic_ai.sql` must execute these operations in order:

```sql
ALTER TABLE agent.agent_request RENAME COLUMN semora_run_id TO workflow_id;
ALTER TABLE agent.agent_interrupt RENAME COLUMN semora_run_id TO workflow_id;
ALTER TABLE agent.agent_interrupt RENAME COLUMN semora_pending_id TO deferred_call_id;
ALTER TABLE agent.agent_interrupt RENAME COLUMN semora_tool_call_id TO tool_call_id;

UPDATE agent.agent_event
   SET producer_key = 'legacy:' || sequence::text
 WHERE producer_key IS NULL;

ALTER TABLE agent.agent_event ALTER COLUMN producer_key SET NOT NULL;
```

Drop/recreate UUID profile constraints under generic names and preserve the unique interrupt key as `(workflow_id, deferred_call_id)`. Replace `agent.append_event` so every event requires a non-null producer key while retaining `run:terminal` as the only terminal key.

Finalize each non-terminal legacy request in the same transaction with one `RUN_ERROR` payload whose code is `runtime_migrated`, using `agent.append_event(..., 'run:terminal', ..., true)`.

- [ ] **Step 4: Rename Python store fields and queries**

Rename all Semora fields to the interfaces above. Add `get_request(run_id, caller)` for DBOS load steps. `resolve_interrupt()` returns the full `DeferredInterrupt`, not a bare string. Keep ownership checks in the SQL join.

- [ ] **Step 5: Apply migrations to the disposable integration database and run tests**

Run: `psql "$AGENT_TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f agent-server/migrations/001_agent.sql -f agent-server/migrations/003_pydantic_ai.sql`

Run: `AGENT_TEST_DATABASE_URL=$AGENT_TEST_DATABASE_URL uv run --project agent-server pytest agent-server/tests/integration/test_agent_postgres.py -q`

Expected: all store tests pass, duplicate producer keys return the original row, and legacy runtime names are absent from active Agent tables.

- [ ] **Step 6: Commit**

```bash
git add agent-server/migrations/003_pydantic_ai.sql agent-server/src/agent_core/store/postgres.py agent-server/tests/integration/conftest.py agent-server/tests/integration/test_agent_postgres.py
git commit -m "refactor(store): migrate semora identifiers to workflows"
```

---

### Task 5: Project Pydantic Native Events into Durable AG-UI Events

**Files:**

- Create: `agent-server/src/agent_core/projection.py`
- Create: `agent-server/tests/test_projection.py`
- Delete: projection portions of `agent-server/src/agent_core/runtime.py`
- Replace: projection portions of `agent-server/tests/test_runtime.py`

**Interfaces:**

- Produces: `producer_key(request_index, event_index, kind) -> str`.
- Produces: `DurableAGUIProjector(store).project(run_id, thread_id, native_events) -> None`.
- Consumes: `PostgresAgentStore.append_event()` and `PostgresAgentStore.replay()`.

- [ ] **Step 1: Write failing projection tests with Pydantic model events**

```python
async def test_projects_text_and_tools_to_ordered_agui_events() -> None:
    store = RecordingStore()
    projector = DurableAGUIProjector(store)
    await projector.project(RUN_ID, THREAD_ID, _native_text_and_tool_events())
    assert [event.type for event in store.events] == [
        EventType.RUN_STARTED,
        EventType.TEXT_MESSAGE_START,
        EventType.TEXT_MESSAGE_CONTENT,
        EventType.TEXT_MESSAGE_END,
        EventType.TOOL_CALL_START,
        EventType.TOOL_CALL_ARGS,
        EventType.TOOL_CALL_END,
        EventType.TOOL_CALL_RESULT,
        EventType.RUN_FINISHED,
    ]
    assert len(store.producer_keys) == len(set(store.producer_keys))


async def test_retry_reuses_committed_projection_without_duplicates() -> None:
    store = IdempotentRecordingStore()
    projector = DurableAGUIProjector(store)
    await projector.project(RUN_ID, THREAD_ID, _native_text_events())
    await projector.project(RUN_ID, THREAD_ID, _native_text_events())
    assert len(store.events) == EXPECTED_EVENT_COUNT
```

- [ ] **Step 2: Run tests and verify the projector is missing**

Run: `uv run --project agent-server pytest agent-server/tests/test_projection.py -q`

Expected: import failure for `agent_core.projection`.

- [ ] **Step 3: Implement producer keys and standalone AG-UI transformation**

Create one `AGUIEventStream(thread_id=thread_id, run_id=run_id)` per logical run. Feed it an async iterator of `NativeEvent` values through `transform_stream()`. Before appending each transformed event, assign a key:

```python
def producer_key(request_index: int, event_index: int, kind: str) -> str:
    return f"pydantic:{request_index}:{event_index}:{kind}"
```

Use `run:started` and `run:terminal` for host terminal boundaries. On a retry, replay committed rows first to reconstruct whether thinking/text/tool streams and the run itself are already open or closed. Do not mint a second public event for a committed producer key.

- [ ] **Step 4: Add SOT interrupt and error wrapping**

When final output is `DeferredToolRequests`, create authenticated interrupt mappings through the store and emit `RUN_FINISHED` with interrupt outcome. Map cancellation, usage-limit, model/provider, invalid-transition, indeterminate DBOS, and unexpected exceptions to the fixed codes in the spec. Truncate public messages to 512 characters and never serialize exception reprs containing request bodies.

- [ ] **Step 5: Run projection and existing protocol tests**

Run: `uv run --project agent-server pytest agent-server/tests/test_projection.py agent-server/tests/test_http.py agent-server/tests/test_agui_api.py -q`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add agent-server/src/agent_core/projection.py agent-server/src/agent_core/runtime.py agent-server/tests/test_projection.py agent-server/tests/test_runtime.py
git commit -m "feat(agent): persist pydantic events as ag-ui"
```

---

### Task 6: Register and Control the DBOS Workflow

**Files:**

- Replace: `agent-server/src/agent_core/runtime.py`
- Replace: `agent-server/tests/test_runtime.py`
- Delete: `agent-server/src/agent_core/supervisor.py`
- Delete: `agent-server/tests/test_supervisor.py`

**Interfaces:**

- Produces: `WorkflowRuntime.start(run_id: str) -> None`.
- Produces: `WorkflowRuntime.cancel(run_id: str) -> None`.
- Produces: `WorkflowRuntime.status(run_id: str) -> WorkflowStatus`.
- Produces: `configure_dbos(settings, agent, store) -> DBOSWorkflowRuntime` before `DBOS.launch()`.

- [ ] **Step 1: Write failing launcher tests against a fake DBOS client**

```python
async def test_start_uses_one_deterministic_workflow_id() -> None:
    client = RecordingWorkflowClient()
    runtime = DBOSWorkflowRuntime(client=client, enqueue=client.enqueue)
    await runtime.start(RUN_ID)
    await runtime.start(RUN_ID)
    assert client.workflow_ids == [f"agent-run:{RUN_ID}", f"agent-run:{RUN_ID}"]
    assert client.executions == 1


async def test_abort_cancels_only_the_matching_workflow() -> None:
    client = RecordingWorkflowClient()
    runtime = DBOSWorkflowRuntime(client=client, enqueue=client.enqueue)
    await runtime.cancel(RUN_ID)
    assert client.cancelled == [f"agent-run:{RUN_ID}"]
```

- [ ] **Step 2: Run the runtime tests and verify the DBOS runtime is missing**

Run: `uv run --project agent-server pytest agent-server/tests/test_runtime.py -q`

Expected: failures for missing `DBOSWorkflowRuntime` and workflow status types.

- [ ] **Step 3: Implement stable DBOS configuration and workflow registration**

Add settings with exact defaults:

```python
class WorkflowSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_DBOS_")
    application_name: str = "sot-agent-server"
    application_version: str = "pydantic-ai-v1"
    system_database_url: str
    schema_name: str = "dbos"
    run_migrations: bool = False
    queue_concurrency: int = 32
```

Instantiate `DBOS` once. Register the stable queue name `agent-runs-v1`, the module-level workflow `agent_core.runtime.run_agent_workflow`, its request-load step, and the Pydantic durability event handler before `DBOS.launch()`.

The workflow input is only `run_id`. Load the stored request/run deps in a DBOS step, then call:

```python
await deployment_agent.run(
    mapped.user_prompt,
    deps=run_deps,
    message_history=mapped.message_history,
    deferred_tool_results=mapped.deferred_tool_results,
    conversation_id=mapped.identity.conversation_id,
)
```

Use the public DBOS enqueue/background API with workflow ID `agent-run:{run_id}`. Treat an existing workflow as attachment, not an error. Use the public workflow handle/client for status and cancellation.

- [ ] **Step 4: Make event side effects retry-safe**

Pass the durable event handler to `DBOSDurability(event_stream_handler=...)`. The handler must delegate only to `DurableAGUIProjector`; every database append uses the deterministic producer key from Task 5. Do not pass `CancellationToken` to a durable DBOS run; external abort cancels the workflow handle.

- [ ] **Step 5: Run runtime tests**

Run: `uv run --project agent-server pytest agent-server/tests/test_runtime.py agent-server/tests/test_projection.py -q`

Expected: all pass; repeated starts execute once and cancellation targets one workflow.

- [ ] **Step 6: Remove the process-local supervisor and commit**

```bash
git rm agent-server/src/agent_core/supervisor.py agent-server/tests/test_supervisor.py
git add agent-server/src/agent_core/runtime.py agent-server/tests/test_runtime.py
git commit -m "feat(agent): execute runs as dbos workflows"
```

---

### Task 7: Wire Service, Bootstrap, Abort, and Replay

**Files:**

- Replace: `agent-server/src/agent_core/service.py`
- Modify: `agent-server/src/agent_core/bootstrap.py`
- Modify: `agent-server/src/agent_core/api/app.py`
- Modify: `agent-server/tests/test_agui_api.py`
- Modify: `agent-server/tests/test_http.py`
- Modify: `agent-server/tests/test_service_boundary.py`
- Modify: `agent-server/tests/integration/test_agent_postgres.py`

**Interfaces:**

- Consumes: `AgentRunAssembly`, `RunInputMapper`, `WorkflowRuntime`, `PostgresAgentStore`.
- Preserves: `AgentService.submit`, `stream`, and `abort` public signatures used by the HTTP adapter.

- [ ] **Step 1: Write failing service tests for detached workflow launch and abort**

```python
async def test_submit_commits_before_starting_workflow() -> None:
    order: list[str] = []
    service = _service(store=RecordingStore(order), runtime=RecordingRuntime(order))
    assert await service.submit(_payload(), _caller()) == RUN_ID
    assert order == ["admit", "start"]


async def test_stream_disconnect_does_not_cancel_workflow() -> None:
    runtime = RecordingRuntime([])
    service = _service(runtime=runtime)
    stream = service.stream(RUN_ID, after_sequence=0)
    await anext(stream)
    await stream.aclose()
    assert runtime.cancelled == []


async def test_abort_persists_intent_before_cancelling_workflow() -> None:
    order: list[str] = []
    service = _service(store=RecordingStore(order), runtime=RecordingRuntime(order))
    await service.abort(RUN_ID, _caller())
    assert order == ["request_abort", "cancel"]
```

- [ ] **Step 2: Run service/API tests and verify the old supervisor path fails expectations**

Run: `uv run --project agent-server pytest agent-server/tests/test_agui_api.py agent-server/tests/test_http.py -q`

Expected: failures because `AgentService` still starts local tasks and signals local stop events.

- [ ] **Step 3: Simplify `AgentService` to durable orchestration**

`submit()` must admit, map, load context, build serializable run deps, persist execution config, then call `runtime.start(run_id)` only when no terminal Agent event exists. `stream()` remains DB polling/replay only. `abort()` calls `store.request_abort()` before `runtime.cancel()` and is idempotent for terminal workflows.

Remove Semora exception mapping and `_execute()`/`_poll_abort()` from the service; workflow/projector layers now own execution errors.

- [ ] **Step 4: Rebuild bootstrap lifecycle**

Bootstrap order must be:

```text
load settings -> construct Postgres/auth -> configure DBOS -> construct durability/projector
-> construct one Pydantic Agent -> register workflow/queue -> open pools/JWKS
-> DBOS.launch() -> serve -> DBOS.destroy() -> close JWKS/pools
```

Set DBOS `run_migrations=False`. Document and use the out-of-band command:

```bash
uv run --project agent-server dbos migrate \
  -s "$AGENT_DBOS_SYSTEM_DATABASE_URL" \
  --schema dbos
```

- [ ] **Step 5: Remove supervisor-specific HTTP errors and assert no Semora source imports**

Delete the `RunCapacityExceeded` handler from `api/app.py`; DBOS queue admission failures map to the same `capacity_exceeded` response through a runtime-neutral exception. Extend `test_service_boundary.py`:

```python
def test_agent_source_has_no_semora_imports() -> None:
    assert not any(target.startswith("semora") for target in all_import_targets())
```

- [ ] **Step 6: Run unit and integration service tests**

Run: `uv run --project agent-server pytest agent-server/tests/test_agui_api.py agent-server/tests/test_http.py agent-server/tests/test_service_boundary.py -q`

Run: `AGENT_TEST_DATABASE_URL=$AGENT_TEST_DATABASE_URL AGENT_DBOS_SYSTEM_DATABASE_URL=$AGENT_DBOS_SYSTEM_DATABASE_URL uv run --project agent-server pytest agent-server/tests/integration/test_agent_postgres.py -q`

Expected: all pass; submit is detached, replay is DB-backed, and abort cancels only the workflow.

- [ ] **Step 7: Commit**

```bash
git add agent-server/src/agent_core/service.py agent-server/src/agent_core/bootstrap.py agent-server/src/agent_core/api/app.py agent-server/tests/test_agui_api.py agent-server/tests/test_http.py agent-server/tests/test_service_boundary.py agent-server/tests/integration/test_agent_postgres.py
git commit -m "refactor(agent): wire service to pydantic dbos runtime"
```

---

### Task 8: Validate Restart Recovery and Finish Semora Cleanup

**Files:**

- Replace: `agent-server/tests/e2e/test_openrouter.py`
- Modify: `agent-server/README.md`
- Modify: `agent-server/Dockerfile`
- Modify: `docs/superpowers/specs/2026-09-03-agent-loop-design.md`
- Modify: `docs/superpowers/plans/2026-09-03-agent-loop-implementation.md`
- Retain unchanged: `agent-server/migrations/002_semora.sql` as rollback-only legacy migration.

**Interfaces:**

- Consumes: the complete Pydantic AI + DBOS runtime.
- Produces: deployment documentation and acceptance evidence.

- [ ] **Step 1: Rewrite the E2E test around Pydantic AI and DBOS**

The test must start a disposable DBOS schema, launch the app, submit one UUIDv7 AG-UI run, disconnect after `RUN_STARTED`, reconnect with `Last-Event-ID`, and assert exactly one terminal result. Use the real OpenRouter path only when `OPENROUTER_API_KEY` is configured; otherwise mark the test `e2e` and skip with an explicit reason.

```python
assert events[0]["type"] == "RUN_STARTED"
assert events[-1]["type"] == "RUN_FINISHED"
assert sum(event["type"] == "RUN_STARTED" for event in events) == 1
assert sum(event["type"] in {"RUN_FINISHED", "RUN_ERROR"} for event in events) == 1
```

- [ ] **Step 2: Add a restart recovery integration test and verify it fails first**

Start a workflow whose first durable tool step blocks on a test-controlled database flag. Destroy the first DBOS runtime after the step starts, create a second runtime with the same application name/version/system database, release the flag, and assert the second runtime finishes the same workflow ID without repeating the completed model/tool step.

Run: `AGENT_TEST_DATABASE_URL=$AGENT_TEST_DATABASE_URL AGENT_DBOS_SYSTEM_DATABASE_URL=$AGENT_DBOS_SYSTEM_DATABASE_URL uv run --project agent-server pytest agent-server/tests/integration/test_agent_postgres.py -k restart -q`

Expected before lifecycle/recovery completion: FAIL because the second runtime does not yet resume or reconcile the event journal.

- [ ] **Step 3: Complete recovery reconciliation**

On startup and authenticated reconnect, query workflow status. If DBOS is terminal but `agent_event` has no terminal row, append the corresponding terminal event with `run:terminal`. If DBOS is pending/running, attach only. If DBOS state is absent for an admitted non-terminal request, append `RUN_ERROR(code="indeterminate_execution")`; never silently start a second workflow under another ID.

- [ ] **Step 4: Update deployment and migration documentation**

Document:

- fresh databases apply `001_agent.sql` then `003_pydantic_ai.sql`; `002_semora.sql` is legacy rollback material only;
- production runs `dbos migrate` before application rollout;
- application DB roles use `run_migrations=False`;
- required `AGENT_DBOS_SYSTEM_DATABASE_URL`, stable application name/version, and DBOS schema;
- Semora tables remain read-only for one rollback window;
- rollback cannot resume Pydantic/DBOS workflows through Semora.

Remove README statements that Semora owns execution/transcript and replace them with the approved Pydantic AI/DBOS ownership model. Ensure the Docker build installs the new frozen lockfile and has no Semora-specific setup.

- [ ] **Step 5: Run the complete verification suite**

```bash
uv run --project agent-server pytest agent-server/tests -q
uv run --project agent-server ruff check agent-server/src agent-server/tests
uv run --project agent-server mypy agent-server/src agent-server/tests
```

Expected: all tests pass, Ruff exits 0, and mypy exits 0.

Run the source/dependency residue checks:

```bash
rg -n "semora|semora_|Semora" agent-server/src agent-server/tests agent-server/pyproject.toml agent-server/README.md
uv tree --project agent-server | rg "semora"
```

Expected: both searches return no matches. References are allowed only in `002_semora.sql`, historical design/plan documents, and the new migration design/plan explaining the replacement.

- [ ] **Step 6: Run the OpenRouter E2E test when credentials are available**

Run: `uv run --project agent-server pytest agent-server/tests/e2e/test_openrouter.py -q -m e2e`

Expected: one real run streams from OpenRouter through DBOS and PostgreSQL to AG-UI and finishes exactly once.

- [ ] **Step 7: Commit**

```bash
git add agent-server/tests/e2e/test_openrouter.py agent-server/README.md agent-server/Dockerfile docs/superpowers/specs/2026-09-03-agent-loop-design.md docs/superpowers/plans/2026-09-03-agent-loop-implementation.md
git commit -m "docs(agent): complete pydantic ai runtime migration"
```

---

## Plan Self-Review Result

- Spec coverage: dependency pin, singleton agent, server-owned tools, Pydantic message mapping, DBOS durability, PostgreSQL projection, interrupt/resume, explicit abort, restart recovery, deployment migration, and Semora cleanup each map to a task.
- Placeholder scan: no deferred implementation placeholders are present; each behavior names its test, implementation interface, command, and expected result.
- Type consistency: `ExecutionIdentity`, `MappedRun`, `AgentRunDeps`, `AgentRunAssembly`, `DurableAGUIProjector`, `WorkflowRuntime`, and generic store interrupt types are introduced before consumers use them.
- Scope: all tasks belong to the single Agent Server runtime migration and converge on one end-to-end acceptance path.
