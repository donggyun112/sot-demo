# SOT Document and Private Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement workspace-owned documents, immutable revisions, private sessions, branches, completed turns, curation, and immutable bundles behind module-specific ports.

**Architecture:** Build `document` and `session` as separate modules over the shared UoW. Workspace authorization is always checked before workspace-scoped repository access; private session actions additionally require an explicit session role, with the workspace role acting as the permission ceiling.

**Tech Stack:** Python 3.12+, FastAPI, psycopg 3 async, PostgreSQL 16, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-06-sot-backend-v1-design.md`

## Global Constraints

- Complete `2026-09-06-sot-backend-foundation-identity-workspace.md` first.
- Preserve one FastAPI process, one PostgreSQL database, explicit SQL, and one transaction per command handler.
- Every tenant-owned row and repository method requires `workspace_id`.
- Cross-module calls import only immutable DTOs and capability `Protocol`s from `contracts.py`.
- Query adapters read only tables owned by their module; do not add cross-module joins or denormalized projections.
- Domain objects are pure Python and own local state transitions; application handlers own actor authorization, orchestration, and transactions.
- `SessionMember` must reference a member of the same workspace. Workspace membership alone never reveals a private session.
- Turns are append-only and only completed user/assistant/tool messages are stored.
- Bundles are immutable snapshots and have no revoke state.

---

## File Structure

- `backend/migrations/004_document_session.sql`: canonical document/session tables alongside preserved vertical-slice tables.
- `backend/src/sot/document/{api,application,contracts,domain,ports,postgres}.py`: document aggregate, revision publication, queries, and routes.
- `backend/src/sot/session/{api,application,contracts,domain,ports,postgres}.py`: private sessions, roles, branches, turns, curation, bundles, and routes.
- `backend/tests/document/`: pure domain and application tests.
- `backend/tests/session/`: private-access, concurrency, curation, and bundle tests.
- `backend/tests/integration/test_document_session_postgres.py`: composite FK, isolation, and transaction tests.

### Task 1: Implement Workspace-Owned Documents and Revisions

**Files:**

- Create: `backend/src/sot/document/domain.py`
- Create: `backend/src/sot/document/contracts.py`
- Create: `backend/src/sot/document/ports.py`
- Create: `backend/src/sot/document/application.py`
- Create: `backend/tests/document/test_domain.py`
- Create: `backend/tests/document/test_application.py`

**Interfaces:**

- Consumes: `Actor`, `WorkspaceAuthorizer`, `Permission`, `UnitOfWorkFactory`.
- Produces: `DocumentReader`, `DocumentPublisher`, `CreateDocument`, `GetDocument`, and immutable revision DTOs.

- [ ] **Step 1: Write failing document invariant tests**

```python
def test_document_publication_requires_expected_version() -> None:
    document = Document.create(workspace_id, user_id, "Policy")
    document.initialize("revision one", user_id, clock.now())
    with pytest.raises(VersionConflict):
        document.publish(
            content="revision two", proposal_id=proposal_id,
            citations=(citation,), actor_id=user_id,
            expected_version=document.version - 1, now=clock.now(),
        )


def test_revision_is_immutable_and_numbered_from_one() -> None:
    document = Document.create(workspace_id, user_id, "Policy")
    first = document.initialize("one", user_id, clock.now())
    second = document.publish(
        content="two", proposal_id=proposal_id, citations=(), actor_id=user_id,
        expected_version=document.version, now=clock.now(),
    )
    assert (first.number, second.number) == (1, 2)
    assert document.current_revision_id == second.id
```

- [ ] **Step 2: Run focused tests and observe missing document types**

Run: `uv run --project backend pytest backend/tests/document/test_domain.py -q`

Expected: FAIL with missing `sot.document.domain` symbols.

- [ ] **Step 3: Define pure document types and contracts**

```python
@dataclass(frozen=True, slots=True)
class Revision:
    id: RevisionId
    workspace_id: WorkspaceId
    document_id: DocumentId
    number: int
    content: str
    proposal_id: ProposalId | None
    created_by: UserId
    created_at: datetime


class DocumentPublisher(Protocol):
    async def publish(
        self, tx: TransactionContext, *, actor: Actor,
        workspace_id: WorkspaceId, document_id: DocumentId,
        expected_version: int, proposal_id: ProposalId,
        content: str, citations: tuple[RevisionCitationInput, ...],
    ) -> RevisionResult: ...
```

`Document` is the mutable-in-memory aggregate with `version`, `current_revision_id`, and domain methods that return new immutable revisions. `DocumentRepository` loads/saves the aggregate; `DocumentQuery` returns immutable `DocumentSummary`, `RevisionView`, and `DocumentView` projections.

- [ ] **Step 4: Write application tests with fake ports**

Verify `CreateDocument` requires `document.create`, creates revision 1 in one transaction, and `PublishDocumentRevision` requires `document.publish`. Verify a document ID from another workspace returns `DocumentNotFound` instead of leaking its existence.

- [ ] **Step 5: Implement minimal handlers**

Each handler opens `uow.transaction()`, calls `WorkspaceAuthorizer.require(...)`, then passes both `workspace_id` and aggregate ID to its repository. `PublishDocumentRevision` is exposed through `DocumentPublisher`; it never commits and can join the consensus handler's existing transaction.

- [ ] **Step 6: Run document tests and architecture checks**

```bash
uv run --project backend pytest backend/tests/document backend/tests/architecture -q
uv run --project backend ruff check backend/src/sot/document backend/tests/document
uv run --project backend mypy backend/src/sot/document backend/tests/document
```

Expected: all PASS.

- [ ] **Step 7: Commit document domain and application**

```bash
git add backend/src/sot/document backend/tests/document
git commit -m "feat: add workspace document revisions"
```

### Task 2: Implement Private Sessions, Roles, Branches, and Turns

**Files:**

- Create: `backend/src/sot/session/domain.py`
- Create: `backend/src/sot/session/contracts.py`
- Create: `backend/src/sot/session/ports.py`
- Create: `backend/src/sot/session/application.py`
- Create: `backend/tests/session/test_domain.py`
- Create: `backend/tests/session/test_application.py`

**Interfaces:**

- Consumes: `Actor`, `WorkspaceAuthorizer`, `WorkspaceMemberReader`, `DocumentReader`, `UnitOfWorkFactory`.
- Produces: `SessionAuthorizer`, immutable `SessionView`, `BranchContextReader`, `BranchVersionGuard`, `CompletedTurnsAppender` (implemented by `AppendCompletedTurns`), `SessionApproverReader`, `SessionForkWriter`, `BranchMutationResult`, and session command/query handlers.

- [ ] **Step 1: Write failing private-access and role-composition tests**

```python
@pytest.mark.parametrize(
    ("workspace_role", "session_role", "permission", "allowed"),
    [
        (WorkspaceRole.MEMBER, SessionRole.EDITOR, SessionPermission.EDIT, True),
        (WorkspaceRole.MEMBER, SessionRole.VIEWER, SessionPermission.EDIT, False),
        (WorkspaceRole.VIEWER, SessionRole.EDITOR, SessionPermission.EDIT, False),
        (WorkspaceRole.OWNER, None, SessionPermission.READ, False),
    ],
)
def test_effective_permission_is_scope_intersection(
    workspace_role, session_role, permission, allowed
) -> None:
    assert is_allowed(workspace_role, session_role, permission) is allowed


def test_completed_turns_are_append_only_and_versioned() -> None:
    branch = Branch.create(session_id, user_id, clock.now())
    result = branch.append_completed(
        expected_version=0,
        messages=(NewTurn("user", "question"), NewTurn("assistant", "answer")),
        now=clock.now(),
    )
    assert [turn.ordinal for turn in result.turns] == [1, 2]
    assert result.branch_version == 1
```

- [ ] **Step 2: Run focused tests and verify missing types**

Run: `uv run --project backend pytest backend/tests/session/test_domain.py -q`

Expected: FAIL with missing session domain symbols.

- [ ] **Step 3: Define session roles, permissions, and aggregate types**

```python
class SessionRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class SessionPermission(StrEnum):
    READ = "session.read"
    EDIT = "session.edit"
    MANAGE_MEMBERS = "session.manage_members"
    PUBLISH_BUNDLE = "session.publish_bundle"
    CREATE_TOSS = "session.create_toss"
    CREATE_PROPOSAL = "session.create_proposal"


class BranchVersionGuard(Protocol):
    async def advance(
        self, tx: TransactionContext, *, actor: Actor,
        workspace_id: WorkspaceId, branch_id: BranchId,
        expected_version: int,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class SessionView:
    id: SessionId
    workspace_id: WorkspaceId
    document_id: DocumentId | None
    created_by: UserId
    created_at: datetime
    status: SessionStatus


class SessionAuthorizer(Protocol):
    async def require(
        self, tx: TransactionContext, *, actor: Actor,
        workspace_id: WorkspaceId, session_id: SessionId,
        permission: SessionPermission,
    ) -> SessionView: ...


class CompletedTurnsAppender(Protocol):
    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, branch_id: BranchId,
        *, expected_version: int, messages: tuple[NewTurn, ...],
    ) -> CompletedTurnsResult: ...


@dataclass(frozen=True, slots=True)
class BranchMutationResult:
    resource_id: UUID
    branch_version: int


@dataclass(frozen=True, slots=True)
class ForkSeedItem:
    source_ids: tuple[UUID, ...]
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class ForkAttribution:
    title: str
    author_display_name: str
    published_at: datetime


class SessionForkWriter(Protocol):
    async def create_from_public_bundle(
        self, tx: TransactionContext, *, actor: Actor,
        destination_workspace_id: WorkspaceId,
        source_bundle_id: BundleId,
        attribution: ForkAttribution,
        items: tuple[ForkSeedItem, ...],
    ) -> ForkedSessionResult: ...


class SessionApproverReader(Protocol):
    async def list_required_approvers(
        self, tx: TransactionContext, *, workspace_id: WorkspaceId,
        session_id: SessionId,
    ) -> frozenset[UserId]: ...
```

`Session` has `status: open|closed`; `Branch` has `version`; `Turn.role` permits `user|assistant|tool`. Branch membership is inherited from the containing session; do not introduce branch-specific roles. Fork seed/attribution DTOs belong to the session contract so session never imports sharing types.

`Session.document_id` and `BranchContext.document_id` are `DocumentId | None`. NULL is only for detached public-fork sessions created explicitly through `Session.create_detached_fork(workspace_id, created_by, now)`. `SessionForkWriter` uses that path: it creates no destination Document automatically and retains no source Document field/link. Normal `Session.create(workspace_id, document_id, created_by, now)` requires a DocumentId and rejects None.

- [ ] **Step 4: Write handler tests before implementation**

Test `CreateSession`, `InviteSessionMember`, `CreateBranch`, `AppendCompletedTurns`, and `CloseSession`. Assert the creator is inserted as Session `owner`, invite requires an existing WorkspaceMember, workspace owner without a SessionMember row gets `SessionNotFound`, and a closed session rejects mutation while remaining readable to its members.

Verify that the public `SessionAuthorizer` returns an immutable view without aggregate state-transition methods; existing views remain unchanged after a later authorized close. Exercise completed user/tool/assistant append and stale-version rejection through the `CompletedTurnsAppender` contract.

- [ ] **Step 5: Implement session handlers and public contracts**

`CreateSession` verifies the document belongs to the URL workspace through `DocumentReader`, creates Session + owner membership + initial Branch in one transaction, and returns their IDs. `SessionAuthorizer` first requires active workspace membership, then session membership, then evaluates the permission intersection. Repository calls always use `(workspace_id, resource_id)`.

`SessionAuthorizer.require()` and `GetSession` return only frozen `SessionView`. Do not re-export the mutable `Session` aggregate from `contracts.py`; authorized state transitions load/save it through session-internal repository paths. `CloseSession` keeps its authorization, aggregate load, transition, and save inside its one transaction.

Declare `CompletedTurnsAppender` in `session/contracts.py`; `AppendCompletedTurns` structurally implements it. It owns a short transaction that atomically saves all completed user/assistant/tool Turns and advances the expected Branch version, returning immutable `CompletedTurnsResult`. Agent imports the Protocol, never the application handler.

The document-scoped `CreateSession` handler remains document-required. Test normal creation retaining its document, detached fork creation and public branch context preserving `document_id = None`, and rejection of source-document linkage in the detached construction contract.

`BranchVersionGuard.advance()` performs a conditional version update inside the caller's transaction and raises `VersionConflict` when no row matches. It manages neither a lock nor an agent-run record.

- [ ] **Step 6: Run session tests and architecture checks**

```bash
uv run --project backend pytest backend/tests/session backend/tests/architecture -q
uv run --project backend ruff check backend/src/sot/session backend/tests/session
uv run --project backend mypy backend/src/sot/session backend/tests/session
```

Expected: all PASS.

- [ ] **Step 7: Commit session behavior**

```bash
git add backend/src/sot/session backend/tests/session
git commit -m "feat: add private sessions and branches"
```

### Task 3: Implement Curation and Immutable Bundles

**Files:**

- Modify: `backend/src/sot/session/domain.py`
- Modify: `backend/src/sot/session/contracts.py`
- Modify: `backend/src/sot/session/ports.py`
- Modify: `backend/src/sot/session/application.py`
- Create: `backend/tests/session/test_curation.py`
- Create: `backend/tests/session/test_bundle.py`

**Interfaces:**

- Consumes: session/branch types from Task 2.
- Produces: `ApplyCuration`, `PreviewBundle`, `PublishBundle`, `CiteCreator`, `BundleReader`, `ShareableBundleReader`, and `BundleSnapshot`.

- [ ] **Step 1: Write failing curation provenance tests**

```python
def test_curation_changes_projection_without_editing_source_turn() -> None:
    projection = CurationProjection.from_turns(turns)
    projection.apply(DropTurn(turn_id=turns[0].id))
    projection.apply(EditTurn(turn_id=turns[1].id, content="public wording"))
    assert turns[1].content == "private wording"
    assert projection.items == (
        CuratedItem(source_turn_id=turns[1].id, content="public wording"),
    )


def test_published_bundle_is_an_immutable_snapshot() -> None:
    bundle = Bundle.publish(branch, projection.items, user_id, clock.now())
    projection.apply(EditTurn(turn_id=turns[1].id, content="later edit"))
    assert bundle.items[0].content == "public wording"
```

- [ ] **Step 2: Run focused tests and verify commands are absent**

Run: `uv run --project backend pytest backend/tests/session/test_curation.py backend/tests/session/test_bundle.py -q`

Expected: FAIL on missing curation and bundle types.

- [ ] **Step 3: Define curation operations and bundle contracts**

Use typed operations `DropTurn`, `EditTurn`, and `JoinTurns` with source Turn IDs. Each `BundleItem` records ordered source Turn IDs, public content, and whether it was copied or edited. `BundleSnapshot` contains only fields safe for cross-workspace sharing; it contains no raw private Turn object.

`JoinTurns` preserves the explicit input source-ID order, including reversed selections. Insert the result at the earliest selected projection position with that item's role, preserving unselected item order. Rejoining only some sources of an existing joined item must raise `curation_selection_partial` without changing the projection or source Turns. Cover both cases with regression tests.

```python
class BundleReader(Protocol):
    async def require_snapshot(
        self, tx: TransactionContext, *, actor: Actor,
        workspace_id: WorkspaceId, bundle_id: BundleId,
    ) -> BundleSnapshot: ...


class ShareableBundleReader(Protocol):
    async def require_shareable_snapshot(
        self, tx: TransactionContext, *, actor: Actor,
        workspace_id: WorkspaceId, bundle_id: BundleId,
    ) -> BundleSnapshot: ...


class CiteCreator(Protocol):
    async def create_from_agent(
        self, *, actor: Actor, workspace_id: WorkspaceId,
        branch_id: BranchId, expected_branch_version: int,
        turn_ids: tuple[TurnId, ...], summary: str,
    ) -> BranchMutationResult: ...
```

- [ ] **Step 4: Implement handlers and invariants**

`ApplyCuration` requires Session `editor`, checks `expected_branch_version`, persists ordered operations, and advances Branch version. `CiteCreator.create_from_agent()` records the selected Turn IDs and summary as a typed curation selection through that same command path and returns `BranchMutationResult`. `PublishBundle` requires Session `owner`, materializes the current projection as immutable bundle/items, and advances Branch version in the same transaction. A later curation creates a different preview and never updates an existing bundle.

Implement `ShareableBundleReader` in session: require workspace membership before resolving the Bundle's actual owning Session, enforce that exact Session's owner-only `SessionPermission.PUBLISH_BUNDLE`, then return the same safe immutable `BundleSnapshot` in the caller's transaction. The public capability takes no Session ID and adds no private owner/Session/Workspace metadata to the snapshot. Keep ordinary `BundleReader` read semantics separate. Regression: an actor who owns Session A but can only read/edit Session B may read B's Bundle but cannot obtain a shareable snapshot of it.

- [ ] **Step 5: Verify curation and bundle behavior**

```bash
uv run --project backend pytest backend/tests/session -q
uv run --project backend ruff check backend/src/sot/session backend/tests/session
uv run --project backend mypy backend/src/sot/session backend/tests/session
```

Expected: all PASS.

- [ ] **Step 6: Commit curation and bundles**

```bash
git add backend/src/sot/session backend/tests/session
git commit -m "feat: add curation and immutable bundles"
```

### Task 4: Persist and Expose Document and Session Modules

**Files:**

- Create: `backend/migrations/004_document_session.sql`
- Create: `backend/src/sot/document/postgres.py`
- Create: `backend/src/sot/session/postgres.py`
- Create: `backend/src/sot/document/api.py`
- Create: `backend/src/sot/session/api.py`
- Modify: `backend/src/sot/bootstrap/app.py`
- Create: `backend/tests/document/test_api.py`
- Create: `backend/tests/session/test_api.py`
- Create: `backend/tests/integration/test_document_session_postgres.py`

**Interfaces:**

- Consumes: handlers and ports from Tasks 1–3 plus identity/workspace request dependencies.
- Produces: canonical workspace-scoped document/session REST routes and PostgreSQL adapters.

- [ ] **Step 1: Write tenant-isolation integration tests**

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_child_id_cannot_escape_workspace_scope(app, tokens) -> None:
    document = await create_document(app, tokens.alice, workspace_a)
    response = await app.get(
        f"/api/v1/workspaces/{workspace_b}/documents/{document.id}",
        headers=tokens.bob.bearer,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
async def test_session_member_requires_same_workspace_member(repositories, tx) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        await repositories.sessions.add_member(
            tx, workspace_id, session_id, outside_user_id, SessionRole.VIEWER
        )
```

- [ ] **Step 2: Run the integration test and verify the schema is absent**

Run: `uv run --project backend pytest backend/tests/integration/test_document_session_postgres.py -q -m integration`

Expected: FAIL because migration 004 and module adapters do not exist.

- [ ] **Step 3: Create canonical tables without deleting vertical-slice data**

`004_document_session.sql` creates `sot.sot_document`, `sot.sot_document_revision`, `sot.sot_revision_citation`, `sot.sot_session`, `sot.sot_session_member`, `sot.sot_branch`, `sot.sot_turn`, `sot.sot_curation_op`, `sot.sot_bundle`, `sot.sot_bundle_item`, and session-owned `sot.sot_fork_origin`. Every table has `workspace_id`; every parent exposes `UNIQUE(workspace_id, id)`; child FKs use both columns. Add `UNIQUE(workspace_id, branch_id, ordinal)`, document/branch `version >= 0`, role/status checks, and the composite FK from SessionMember to WorkspaceMember. `sot_fork_origin.source_bundle_id` is an opaque UUID with no source Bundle FK. Keep the 001 tables untouched until the final cutover plan.

In migration 004, `sot_session.document_id` is nullable for detached public-fork sessions only. Preserve the composite `(workspace_id, document_id)` Document FK when non-null; normal document-scoped creation must still validate a required Document. Fork creation uses NULL and must neither auto-create a destination Document nor persist a source Document ID/FK.

- [ ] **Step 4: Implement explicit SQL adapters**

Each adapter unwraps only `PostgresTransactionContext`, maps rows in its own module, includes workspace predicates in every query, and never calls commit. Document queries do not join session tables; session queries do not join document tables.

- [ ] **Step 5: Write API contract tests before routes**

Cover these common-prefix-relative routes with Bearer tokens and `extra="forbid"` DTOs:

```text
GET  /workspaces/{workspace_id}/documents/{document_id}
GET  /workspaces/{workspace_id}/documents/{document_id}/revisions/{number}
POST /workspaces/{workspace_id}/documents/{document_id}/sessions
GET  /workspaces/{workspace_id}/sessions/{session_id}
POST /workspaces/{workspace_id}/sessions/{session_id}/branches
POST /workspaces/{workspace_id}/branches/{branch_id}/curation-ops
GET  /workspaces/{workspace_id}/branches/{branch_id}/bundle-preview
POST /workspaces/{workspace_id}/branches/{branch_id}/bundles
```

Assert missing auth is 401, denied access is 403, cross-workspace child IDs are 404, version conflict is 409, and malformed DTOs are 422 with the stable error envelope.

- [ ] **Step 6: Implement thin module routers and composition wiring**

Routes map Pydantic DTOs to application commands and results back to response DTOs. They contain no domain transition or SQL. Register document/session routers in `build_app()` and inject handlers by constructor-built route factories.

- [ ] **Step 7: Run milestone verification**

```bash
uv run --project backend pytest backend/tests/document backend/tests/session backend/tests/integration/test_document_session_postgres.py backend/tests/architecture -q
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy backend/src backend/tests
```

Expected: all PASS and the original vertical-slice schema remains present.

- [ ] **Step 8: Commit persistence and API**

```bash
git add backend/migrations/004_document_session.sql backend/src/sot/document backend/src/sot/session backend/src/sot/bootstrap/app.py backend/tests/document backend/tests/session backend/tests/integration/test_document_session_postgres.py
git commit -m "feat: expose tenant-scoped documents and sessions"
```
