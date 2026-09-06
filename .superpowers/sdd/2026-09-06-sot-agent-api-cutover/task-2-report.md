# Task 2 report

Status: DONE

Commit:

- `77e413173c5321993b0181c6d48ddb1ee18f1644` — `feat: persist completed agent turns server-side`

Base: `881974a5a16c0f26d9dff3794c45824062481198` (already on `main` when this task began).

## Scope

The coherent implementation commit contains six files, 932 insertions and five deletions:

- New `backend/src/sot/agent/api.py` with `ServerOnlyAGUIAdapter`, its sanitized native AG-UI event stream, completion lifecycle, and the canonical workspace/branch Agent router.
- Updated `backend/src/sot/agent/messages.py` with completed Pydantic-message mapping and strict `ToolCallPart.args` normalization while retaining `sot.tool-turn.v1`.
- Updated `backend/src/sot/agent/application.py` with the framework-neutral `CompletedRunWriter.write()` API; the Task 1 `execute()` API remains a compatibility alias.
- Narrow composition change in `backend/src/sot/bootstrap/app.py` registering `/api/v1/workspaces/{workspace_id}/branches/{branch_id}/agent` with the existing actor resolver and Task 1 singleton/preparer/writer.
- New `backend/tests/agent/test_agui.py` and `test_completion.py` with 25 trust-boundary and lifecycle cases.

No legacy Agent runtime or route was changed or removed. The legacy path remains `/api/v1/branches/{branch_id}/agent`, so it does not collide with the canonical workspace-scoped path. Task 3's server tool definitions were not pulled forward.

No frontend file or unrelated plan was staged. No push or merge was performed. After the commit, worktree status contains only the pre-existing frontend modifications/untracked streaming test and the unrelated untracked `docs/superpowers/plans/2026-09-06-sot-backend-v1-implementation.md`.

## Red evidence

All commands ran in `/Users/dongkseo/project/sot-demo/.worktrees/pydantic-direct-sot`.

The two required contract files were written before the production adapter/module. The initial focused command failed only because the secure API surface did not exist:

```text
uv run --project backend pytest backend/tests/agent/test_agui.py backend/tests/agent/test_completion.py -q

ERROR backend/tests/agent/test_agui.py
E ModuleNotFoundError: No module named 'sot.agent.api'
ERROR backend/tests/agent/test_completion.py
E ModuleNotFoundError: No module named 'sot.agent.api'
2 errors in 0.29s
[exit:2]
```

The bootstrap-registration test was then added before the composition edit:

```text
uv run --project backend pytest backend/tests/agent/test_agui.py::test_composition_registers_one_canonical_workspace_agent_route -q
E assert 0 == 1
1 failed in 0.40s
[exit:1]
```

The first implementation run exposed the intended malformed-args regression: the JSON string `"null"` was incorrectly normalized like Python `None` instead of rejected as a non-object. The failing case was already present before the mapper and was fixed by distinguishing actual `None` from parsed JSON:

```text
FAILED ...test_malformed_or_non_object_completed_tool_args_fail_safely[null]
E Failed: DID NOT RAISE <class 'ValueError'>
```

The consecutive-tail boundary was strengthened with a hostile ignored reasoning separator before changing the validator. It first proved the bypass:

```text
uv run --project backend pytest 'backend/tests/agent/test_agui.py::test_agent_rejects_untrusted_request_features[trailing-users-with-ignored-separator]' -q
E assert 200 == 422
1 failed in 0.40s
[exit:1]
```

The validator now finds the previous user/assistant conversation message while ignoring non-authoritative client reasoning, so two trailing prompts cannot be disguised by an ignored message.

During green-up, a separate test-fixture issue was traced rather than treated as product behavior: native streamed requests require `FunctionModel(stream_function=...)`; a non-stream `function` fails before model invocation. FastAPI's postponed evaluation also cannot resolve a closure-local `Depends(actor)` inside `Annotated`, so `agent.api` deliberately uses evaluated annotations (no future-annotations import), matching the existing product-router pattern.

## Verification

Focused Task 2 contracts:

```text
uv run --project backend pytest backend/tests/agent/test_agui.py backend/tests/agent/test_completion.py -q
25 passed in 0.47s
```

Fresh final Agent suite after the last production edit:

```text
uv run --project backend pytest backend/tests/agent -q
53 passed in 1.21s
```

Architecture and fast-backend checks during implementation:

```text
uv run --project backend pytest backend/tests/architecture -q
37 passed in 0.07s

uv run --project backend pytest backend/tests -m 'not integration and not e2e' -q
364 passed, 45 deselected in 1.80s
```

Fresh PostgreSQL-inclusive final backend regression:

```text
uv run --project backend pytest backend/tests -m 'not e2e' -q
409 passed in 12.08s
```

Final lint, typing and formatting:

```text
uv run --project backend ruff check backend/src backend/tests
All checks passed!

uv run --project backend mypy backend/src backend/tests
Success: no issues found in 131 source files

uv run --project backend ruff format --check backend/src/sot/agent backend/tests/agent backend/src/sot/bootstrap/app.py
14 files already formatted
```

`git diff --check` and `git diff --cached --check` passed. Immediately before commit, the staged path list contained exactly the six files listed in Scope.

## Behavioral evidence

### Latest-input-only trust boundary

The successful forged-history contract supplies stale client user and assistant messages, forged client `state`, `context`, `forwardedProps.model`, and one final user input. The FunctionModel receives the PostgreSQL-shaped canonical history as the first two model messages and exactly one additional `ModelRequest(UserPromptPart("latest question"))`. No stale `forged` content enters the model messages. `AgentInfo.instructions` contains the canonical server instruction, and the current singleton Agent has no Task 3 function tools yet.

The adapter rejects all of the following with HTTP 422 and the exact closed envelope `invalid_agent_request` / `Agent request is invalid`:

- client system or developer instructions;
- a latest assistant message, no messages, or a blank latest user prompt;
- directly consecutive trailing user prompts;
- trailing user prompts disguised by an ignored reasoning message;
- URL/file content and uploaded-file activity references;
- any client-declared tool schema.

Each invalid case proves the model is not called and no preparation transaction is opened. The adapter's `toolset`, `state`, and `deferred_tool_results` are forced to `None`; server Agent definitions and request-scoped `AgentDeps` remain authoritative. The accepted prompt is stripped and represented as one frontend `ModelRequest`; stale client history is never passed through `AGUIAdapter.load_messages()`.

The route depends on the composition root's existing Bearer actor resolver. A contract without the required Bearer identity receives the stable `auth_token_invalid` response. Parsing the AG-UI body happens before `AgentRunPreparer.prepare()`, while authentication remains FastAPI dependency-owned.

### Completion ordering and atomic persistence

`ServerOnlyAGUIAdapter.run_server_stream()` installs an async-generator `on_complete` callback. It maps the accepted prompt plus completed result messages to application-owned `NewTurn` DTOs before invoking `CompletedRunWriter.write()`. Only after the session-owned `CompletedTurnsAppender` returns its committed result does lineage advance.

The success timeline records the real in-memory session appender commit before `RUN_FINISHED`. The appended completed transcript is exactly `user: next question`, `assistant: next answer`. The FunctionModel asserts that the preparation transaction is closed during streaming, and the writer's appender opens the separate short completion UoW.

A storage error raised from the appender yields `RUN_ERROR(code="turn_store_failed", message="Turn was not stored")`, yields no `RUN_FINISHED`, appends no Turn, and leaves no active transaction. A stale branch lineage similarly yields stable `version_conflict`, no `RUN_FINISHED`, no prompt/answer from the losing run, and does not advance the stale lineage.

Unexpected provider or mapping exceptions are converted by the server event stream to `RUN_ERROR(code="agent_run_failed", message="Agent run failed")`; raw exception text, malformed argument data, provider details, credentials, and internals are not emitted. Expected `SOTError` values keep their already-stable public code/message.

### Tool transcript mapping

Completed tool calls and returns reuse the Task 1 closed `sot.tool-turn.v1` envelope and retain `tool_name` and `tool_call_id`.

`ToolCallPart.args` coverage proves:

- a dictionary is accepted and strictly JSON-validated;
- actual Python `None` becomes `{}`;
- a JSON string is accepted only when it parses to an object;
- malformed JSON and JSON array/null/number strings fail with only `completed agent message is invalid`.

The complete mapping happens before the appender call. A synthetic completed result containing secret-bearing malformed args emits sanitized `RUN_ERROR`, does not invoke the appender, emits no `RUN_FINISHED`, and appends no transcript. Tool-return content is likewise validated as finite JSON before encoding. Server system parts and model thinking parts are intentionally not canonical Turns; tool-associated retry parts are canonical tool Turns, and unexpected completed part kinds fail closed.

### Cancellation and non-durable runs

The cancellation contract uses a real HTTP task and a streaming FunctionModel barrier. It cancels after the model begins but before completion. The task receives `asyncio.CancelledError`, the completion appender has zero calls, the existing branch Turns remain byte-for-byte unchanged, and exactly one transaction occurred: the already-closed preparation read. No completion, recovery, replay, event, checkpoint, chunk, or run-record storage was introduced. As specified, this task does not attempt to reverse independently committed tool transactions; Task 3 owns those tools.

### Singleton and boundaries

The canonical `Agent` remains application-lifetime state assembled once in `build_app()`. Request messages, actor, workspace, branch, lineage, adapter, and callback are local to each request; no request state is assigned to the singleton.

`sot.agent.application` remains free of Pydantic AI, `sot.agent.messages`, FastAPI, psycopg, and repository imports. Pydantic mapping is confined to the messages/API adapter side, and completion storage still crosses only `session.contracts.CompletedTurnsAppender`. All 37 architecture tests and the complete backend regression passed.

## Pydantic AI 2.38 / AG-UI 0.1.22 adaptation

The installed implementations and signatures were inspected locally (`pydantic-ai-slim 2.38.0`, `ag-ui-protocol 0.1.22`). Relevant native behavior:

- `AGUIAdapter.from_request()` builds a request-scoped adapter from `RunAgentInput`.
- `run_stream(..., message_history=..., deps=..., on_complete=...)` delegates to the native Pydantic event stream; no CopilotKit or custom wire protocol is involved.
- `UIEventStream.transform_stream()` invokes `on_complete` on `AgentRunResultEvent` before AG-UI `after_stream()` emits `RUN_FINISHED`.
- A callback exception follows `on_error`; the custom native AG-UI event stream marks the run errored and emits one sanitized `RunErrorEvent`, so `after_stream()` suppresses `RUN_FINISHED`.
- External task cancellation is an `asyncio.CancelledError` (`BaseException`) and bypasses the normal completion/error callback path, matching the no-persistence contract.

One important 2.38-specific detail required an explicit adaptation: `AGUIAdapter.run_stream_native()` appends the adapter's accepted frontend messages to `message_history` before calling the Agent. Consequently, `AgentRunResult.new_messages()` contains the model/tool messages but excludes the accepted user prompt. The completion callback therefore combines `self.messages`—which this secure adapter guarantees is exactly one validated user prompt—with `result.new_messages()` before mapping. This preserves the required persisted `user, assistant` transcript without trusting stale client history.

## Self-review and concerns

Self-reviewed the committed production diff, route order, closed errors, test behavior, and staged path list. Confirmed the canonical path exists exactly once in generated OpenAPI, while all legacy characterization tests remain green. Confirmed there is no DB/UoW scope around provider streaming and no request mutation on the singleton.

No blocking concerns. Two deliberate follow-on boundaries remain:

- Task 3 will register the server-owned `session_cite` and `sot_update` functions. This task rejects client tool declarations and preserves whatever tool definitions exist on the singleton, which is currently an empty Task 1 set.
- The event-stream subclass uses Pydantic AI 2.38's documented `AGUIEventStream` extension hooks but necessarily sets its internal error flag, matching the installed native `on_error()` implementation. A future Pydantic AI upgrade should rerun these ordering/error contract tests.

## Review fix round 1

Status: DONE. The fix and this report are committed together as one coherent change; its SHA is recorded in the task handoff because a Git commit cannot contain its own object ID.

### Scope and rationale

The review fix changes five implementation/test files plus this report:

- `backend/src/sot/agent/api.py` now checks every native AG-UI `UserMessage`, not only the final prompt. String and text-only stale content remain ignorable; any image, audio, video, document, or deprecated binary input part is rejected before preparation or model invocation. Native file/upload `ActivityMessage` values remain rejected globally.
- `backend/src/sot/agent/messages.py` extends the existing `sot.tool-turn.v1` discriminated union with the closed `retry` kind. It stores only `content`, `tool_name`, `tool_call_id`, and an aware timestamp, then reconstructs a native `RetryPromptPart` in `ModelRequest` direction.
- `backend/tests/agent/test_agui.py`, `test_completion.py`, and `test_messages.py` add real HTTP/native-adapter regressions, an actual Pydantic integer-tool validation retry, persistence/reload pairing, string/list retry content, and malformed/non-JSON safe-failure cases.

The original bypass existed because `_latest_prompt()` validated multimodal content only on the last `UserMessage`; stale typed user content was ignored without first enforcing the request-wide trust policy. The original dangling tool call existed because completed `RetryPromptPart` values were skipped while their preceding failed `ToolCallPart` values were persisted. The fix preserves transcript order as failed call → retry response → corrected call → return, with each direction grouped into the corresponding Pydantic `ModelResponse` or `ModelRequest`.

Tool retry validation is atomic with completion mapping. Malformed envelopes, extra fields, empty/invalid content, non-finite JSON, invalid timestamps, and non-JSON error inputs fail with the stable internal mapping error. The completion callback consequently emits sanitized `RUN_ERROR`, emits no `RUN_FINISHED`, and appends no completed-run Turns. Tool-role retry details remain excluded from public product DTOs. A native retry without a tool name cannot satisfy the closed tool-turn schema and fails the completion mapping atomically instead of being silently dropped.

### Reuse audit and retained custom boundaries

The audit followed the project rule in order: existing code, standard library/platform, installed dependency, then maintained library.

- Existing code: the Task 1 `sot.tool-turn.v1` envelope, strict Turn mapper, completion callback, and session-owned atomic appender were extended rather than replaced.
- Standard library/platform: the standard JSON parser rejects non-standard non-finite constants before decoding a stored envelope. This preserves the existing finite-JSON guarantee because Pydantic's JSON-mode `JsonValue` parser accepts `NaN`.
- Installed dependency: `RunAgentInput`, `UserMessage`, `TextInputContent`, and the native typed image/audio/video/document/binary content union are used after `AGUIAdapter.build_run_input()`; no hand-written request-content discriminator was added.
- Maintained library: Pydantic AI 2.38's `RetryPromptPart` and `pydantic_core.ErrorDetails` define the completion/reload shape, while Pydantic's closed models, discriminated `TypeAdapter`, `JsonValue`, `AwareDatetime`, and JSON serializer enforce and emit the SOT envelope. Native `AGUIAdapter.run_stream()` and `AGUIEventStream` completion/error ordering remain unchanged.

Only two custom boundaries remain, because no library can decide them for SOT: the latest-input/request-wide trust policy, and the mapping between native Pydantic model parts and canonical database `Turn` values. Authentication, authorization, and transactions remain in their existing SOT application/session boundaries. No custom AG-UI protocol, CopilotKit layer, arbitrary-object serializer, or request state on the singleton Agent was introduced.

### Red evidence

The real HTTP regression covered every supported native user content form. The stale text form stayed green, while stale image URL, audio data, video URL, document data, and binary URL cases all proved the bypass before the production change:

```text
uv run pytest tests/agent/test_agui.py -q
5 failed, 14 passed in 0.65s
```

The retry contract was then added before its encoder existed:

```text
uv run pytest tests/agent/test_messages.py -q
E ImportError: cannot import name 'encode_tool_retry' from 'sot.agent.messages'
1 error in 0.25s
```

The native completion regression uses `AGUIAdapter` with an actual Pydantic tool declared as `value: int`. A streamed `{"value":"bad"}` call produces Pydantic's real `RetryPromptPart`, followed by corrected `{"value":7}` arguments, a real tool return, and the final answer.

### Final green evidence

Fresh focused contracts after the final production edit and formatting:

```text
uv run pytest tests/agent/test_agui.py tests/agent/test_completion.py tests/agent/test_messages.py -q
54 passed in 0.50s
```

The native retry test asserts the persisted six-Turn sequence `user, tool(call-bad), tool(retry-bad), tool(call-good), tool(return-good), assistant`; reload produces request/response parts with exactly matching counters for `call-bad` and `call-good`, preserves the native retry timestamp/content, and is accepted as history by a subsequent native adapter/model stream. The stale-file HTTP tests assert HTTP 422 with the stable `invalid_agent_request` envelope, no model invocation, and no preparation transaction.

Agent and architecture regression:

```text
uv run pytest tests/agent tests/architecture -q
106 passed in 1.22s
```

PostgreSQL-inclusive backend regression excluding only live-provider e2e tests:

```text
uv run pytest -m 'not e2e' -q
425 passed in 12.62s
```

Lint, formatting, and strict typing for the changed boundary:

```text
uv run ruff check .
All checks passed!

uv run ruff format --check src/sot/agent/api.py src/sot/agent/messages.py tests/agent/test_agui.py tests/agent/test_completion.py tests/agent/test_messages.py
5 files already formatted

uv run mypy src/sot/agent tests/agent/test_agui.py tests/agent/test_completion.py tests/agent/test_messages.py
Success: no issues found in 10 source files
```

The original report's repository-wide mypy command was also reproduced exactly from the worktree root and remains green:

```text
uv run --project backend mypy backend/src backend/tests
Success: no issues found in 131 source files
```

Running `uv run mypy src` from `backend/` discovers `backend/pyproject.toml` and its strict configuration; it reports only two pre-existing redundant casts at `src/sot/store/postgres.py:120` and `:132`. `git diff --exit-code 77e413173c5321993b0181c6d48ddb1ee18f1644 -- backend/src/sot/store/postgres.py` passes, proving this fix did not touch that file. The difference from the original report is command working directory/config discovery, not a Task 2 regression, so those unrelated casts were not changed.

`git diff --check` passed. The staged path audit for the fix contains only the five fix files above and this report; the concurrently updated cutover plan, unrelated backend-v1 plan, and dirty frontend files remain unstaged.

### Fix self-review and concerns

The native content union and `RetryPromptPart` signatures were inspected against installed AG-UI 0.1.22/Pydantic AI 2.38.0. Review confirmed all supplied messages are scanned before any UoW, safe stale text still cannot reach the model, both tool calls have one response after reload, retry timestamp precision is preserved, and retry validation cannot invoke arbitrary serialization. Completion persistence still occurs before `RUN_FINISHED`, cancellation behavior and transaction separation are unchanged, and application-layer import boundaries remain intact.

No blocking concerns. The deliberate compatibility boundary remains pinned to Pydantic AI 2.38.0; its native content-part and retry-part contracts are covered by the new tests and must be rerun on dependency upgrades.
