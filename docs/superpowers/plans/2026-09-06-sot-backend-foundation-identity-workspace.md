# SOT Backend Foundation, Identity, and Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vertical slice's global service and development-header identity boundary with an enforceable modular foundation, Google-backed SOT authentication, and workspace-scoped RBAC.

**Architecture:** Add the approved module skeleton beside the existing vertical slice, then route identity and workspace behavior through narrow application contracts and an explicit composition root. PostgreSQL transactions are represented by an opaque context, migrations run from a separate command, and FastAPI remains an inbound adapter only.

**Tech Stack:** Python 3.12+, FastAPI 0.116+, Pydantic 2, psycopg 3 async pool, PostgreSQL 16, google-auth 2.x, PyJWT 2.x, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-06-sot-backend-v1-design.md`

## Global Constraints

- Keep one FastAPI deployable and one PostgreSQL 16 database.
- Keep `identity`, `workspace`, `document`, `session`, `sharing`, `consensus`, and `agent` as the only product modules.
- Domain code is pure Python and must not import FastAPI, Pydantic, psycopg, or Pydantic AI.
- Application code depends on ports; only adapters know frameworks and persistence libraries.
- Use `psycopg` async with explicit SQL; do not add an ORM, DI framework, service locator, event bus, RLS, or context-variable transaction.
- A top-level command handler owns one transaction and passes an opaque `TransactionContext` to repositories and downstream application contracts.
- Role and permission catalogs are fixed in code; only scoped assignments are stored in PostgreSQL.
- Production authentication uses SOT access/refresh tokens after Google identity verification. `X-SOT-User` remains available only in an explicit local/test profile.
- Production composition must never mount legacy routes. Keep `sot.api.create_app()` as the separate characterization factory; any temporary mounting from `build_app()` requires both a local/test environment and explicit `development_auth=True`.
- Migrations use one global sequence and a separate deployment command; application startup must not run migrations.
- Integration tests create a uniquely named disposable database per test. Never reset a schema or run migrations against the local/default application database in tests.

---

## File Structure

- `backend/src/sot/bootstrap/app.py`: explicit `build_app()` composition root and FastAPI lifespan.
- `backend/src/sot/bootstrap/database.py`: PostgreSQL pool, transaction context, and UoW implementation.
- `backend/src/sot/bootstrap/migrate.py`: standalone ordered migration command.
- `backend/src/sot/bootstrap/settings.py`: runtime settings, including auth profile and secrets.
- `backend/src/sot/shared/{clock,errors,ids,unit_of_work}.py`: framework-neutral primitives.
- `backend/src/sot/identity/{api,application,contracts,domain,ports,postgres,tokens}.py`: SOT users, provider identities, auth sessions, and token flow.
- `backend/src/sot/identity/providers/{base,google}.py`: provider contract and Google adapter.
- `backend/src/sot/workspace/{api,application,contracts,domain,ports,postgres}.py`: workspace aggregates, memberships, and authorization.
- `backend/migrations/002_identity.sql`: identity and auth-session tables.
- `backend/migrations/003_workspace.sql`: workspace and membership tables.
- `backend/tests/architecture/test_dependencies.py`: layer and cross-module import enforcement.
- `backend/tests/identity/`: provider, facade, token, and HTTP contract tests.
- `backend/tests/workspace/`: RBAC, handler, and HTTP contract tests.
- `backend/tests/integration/test_migrations.py`: standalone migration and startup behavior.

### Task 1: Lock the Module and Layer Boundaries

**Files:**

- Create: `backend/src/sot/bootstrap/__init__.py`
- Create: `backend/src/sot/shared/__init__.py`
- Create: `backend/src/sot/identity/__init__.py`
- Create: `backend/src/sot/workspace/__init__.py`
- Create: `backend/src/sot/document/__init__.py`
- Create: `backend/src/sot/session/__init__.py`
- Create: `backend/src/sot/sharing/__init__.py`
- Create: `backend/src/sot/consensus/__init__.py`
- Create: `backend/src/sot/agent/__init__.py`
- Move: `backend/src/sot/agent.py` → `backend/src/sot/legacy_agent.py`
- Modify: `backend/src/sot/api.py`
- Modify: `backend/src/sot/main.py`
- Modify: `backend/tests/test_agent.py`
- Modify: `backend/tests/test_agui.py`
- Create: `backend/tests/architecture/test_dependencies.py`

**Interfaces:**

- Consumes: the module DAG in spec sections 4–6.
- Produces: import rules that every later task must pass.

- [ ] **Step 1: Run the current Agent characterization tests before resolving the module-name collision**

Run: `uv run --project backend pytest backend/tests/test_agent.py backend/tests/test_agui.py -q`

Expected: PASS.

- [ ] **Step 2: Write the failing architecture tests**

```python
from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

SRC = Path(__file__).parents[2] / "src" / "sot"
PRODUCT_MODULES = {
    "identity", "workspace", "document", "session", "sharing", "consensus", "agent"
}
FORBIDDEN_DOMAIN_ROOTS = {
    "fastapi", "starlette", "pydantic", "pydantic_settings",
    "psycopg", "psycopg_pool", "pydantic_ai",
}
FORBIDDEN_APPLICATION_ROOTS = FORBIDDEN_DOMAIN_ROOTS
# Identity contracts are the shared authenticated-Actor boundary. Every other
# edge is exactly the approved product DAG; reverse contract imports also fail.
ALLOWED_DEPENDENCIES = {
    "identity": set(),
    "workspace": {"identity"},
    "document": {"identity", "workspace"},
    "session": {"identity", "workspace", "document"},
    "sharing": {"identity", "workspace", "session"},
    "consensus": {"identity", "workspace", "document", "session", "sharing"},
    "agent": {"identity", "workspace", "document", "session", "consensus"},
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = ".".join(("sot", *path.relative_to(SRC).parts[:-1]))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, package)
            names.update(
                base if alias.name == "*" else f"{base}.{alias.name}"
                for alias in node.names
            )
    return names


def test_product_module_packages_exist() -> None:
    assert {path.name for path in SRC.iterdir() if path.is_dir()} >= PRODUCT_MODULES


def test_domain_has_no_framework_or_persistence_imports() -> None:
    for owner in PRODUCT_MODULES:
        for path in (SRC / owner).rglob("*.py"):
            if path.relative_to(SRC / owner).parts[0] not in {"domain.py", "domain"}:
                continue
            for name in imported_modules(path):
                parts = name.split(".")
                assert parts[0] not in FORBIDDEN_DOMAIN_ROOTS, (path, name)
                if parts[0] == "sot":
                    assert len(parts) >= 3 and (
                        parts[1] == "shared"
                        or (parts[1] == owner and parts[2] == "domain")
                    ), (path, name)


def test_application_has_no_fastapi_or_psycopg_imports() -> None:
    for owner in PRODUCT_MODULES:
        for path in (SRC / owner).rglob("*.py"):
            if path.relative_to(SRC / owner).parts[0] not in {"application.py", "application"}:
                continue
            for name in imported_modules(path):
                parts = name.split(".")
                assert parts[0] not in FORBIDDEN_APPLICATION_ROOTS, (path, name)
                if parts[0] == "sot":
                    assert len(parts) >= 3 and parts[1] in PRODUCT_MODULES | {"shared"}, (path, name)
                    if parts[1] == owner:
                        assert parts[2] in {"application", "contracts", "domain", "ports"} or (
                            parts[2:4] == ["providers", "base"]
                        ), (path, name)


def test_cross_module_imports_use_contracts_only() -> None:
    for owner in PRODUCT_MODULES:
        for path in (SRC / owner).rglob("*.py"):
            for imported in imported_modules(path):
                parts = imported.split(".")
                if parts[0] == "sot":
                    assert len(parts) >= 3, (path, imported)
                    target = parts[1]
                    assert target in PRODUCT_MODULES | {"shared", "bootstrap"}, (path, imported)
                    if target == "bootstrap":
                        assert parts[2] in {"settings", "database"}, (path, imported)
                    if target in PRODUCT_MODULES and target != owner:
                        assert target in ALLOWED_DEPENDENCIES[owner], (path, imported)
                        assert parts[2] == "contracts", (path, imported)
```

Add parameterized synthetic-source regressions against these same checker functions.
Reject reverse edges even through `contracts`, nested files, `from ..workspace import
contracts`, `from sot import workspace`, package/star imports, and private adapter
imports. Accept approved directed contract imports in absolute, relative, and
package-import forms. Include `domain/` and `application/` packages with nested
files and `__init__.py`; reject relative inward-layer violations and framework
imports there. Walk the full AST, including imports inside functions and
`TYPE_CHECKING`. Syntax errors must fail the check, never be silently skipped.

- [ ] **Step 3: Run the focused test and observe the missing module layout**

Run: `uv run --project backend pytest backend/tests/architecture/test_dependencies.py -q`

Expected: FAIL in `test_product_module_packages_exist` because the approved module packages do not exist yet.

- [ ] **Step 4: Move the old Agent module out of the canonical package name**

Move `sot/agent.py` to `sot/legacy_agent.py` and update only the current vertical-slice imports in `sot/api.py`, `sot/main.py`, `tests/test_agent.py`, and `tests/test_agui.py` from `sot.agent` to `sot.legacy_agent`. This preserves behavior while making `sot/agent/` unambiguous.

- [ ] **Step 5: Create only the package markers listed above**

Each `__init__.py` contains a one-line module docstring and exports nothing. Do not move `sot/api.py`, `sot/agent.py`, or `sot/domain/` in this task.

- [ ] **Step 6: Run architecture and characterization tests**

Run: `uv run --project backend pytest backend/tests/architecture/test_dependencies.py backend/tests/test_agent.py backend/tests/test_agui.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the boundary scaffold**

```bash
git add backend/src/sot backend/tests/architecture backend/tests/test_agent.py backend/tests/test_agui.py
git commit -m "refactor: define backend module boundaries"
```

### Task 2: Add Shared Errors, IDs, Unit of Work, and Standalone Migrations

**Files:**

- Create: `backend/src/sot/shared/errors.py`
- Create: `backend/src/sot/shared/ids.py`
- Create: `backend/src/sot/shared/clock.py`
- Create: `backend/src/sot/shared/unit_of_work.py`
- Create: `backend/src/sot/bootstrap/database.py`
- Create: `backend/src/sot/bootstrap/app.py`
- Create: `backend/src/sot/bootstrap/migrate.py`
- Create: `backend/src/sot/bootstrap/settings.py`
- Modify: `backend/src/sot/main.py`
- Modify: `backend/pyproject.toml`
- Create: `backend/tests/shared/test_unit_of_work.py`
- Create: `backend/tests/integration/test_migrations.py`
- Create: `backend/tests/postgres.py`
- Create: `backend/tests/integration/conftest.py`
- Create: `backend/tests/integration/test_database_isolation.py`
- Create: `backend/tests/shared/test_postgres_test_database.py`

**Interfaces:**

- Consumes: no product module.
- Produces: `SOTError`, UUID aliases, `Clock`, `TransactionContext`, `UnitOfWork`, `PostgresUnitOfWork`, `run_migrations()`, and `build_app(settings)` without startup migrations.

- [ ] **Step 1: Write unit tests for stable errors and transaction ownership**

```python
def test_sot_error_has_stable_code_and_safe_message() -> None:
    error = SOTError("version_conflict", "The resource changed")
    assert error.code == "version_conflict"
    assert error.message == "The resource changed"


@pytest.mark.asyncio
async def test_fake_uow_commits_once_on_success_and_rolls_back_once_on_error() -> None:
    success = FakeUnitOfWork()
    async with success.transaction():
        pass
    assert (success.commits, success.rollbacks) == (1, 0)

    failure = FakeUnitOfWork()
    with pytest.raises(RuntimeError):
        async with failure.transaction():
            raise RuntimeError("stop")
    assert (failure.commits, failure.rollbacks) == (0, 1)
```

- [ ] **Step 2: Run the shared tests and verify imports fail**

Run: `uv run --project backend pytest backend/tests/shared/test_unit_of_work.py -q`

Expected: FAIL with `ModuleNotFoundError: sot.shared.unit_of_work`.

- [ ] **Step 3: Define the framework-neutral shared contracts**

```python
class TransactionContext(Protocol):
    """Opaque transaction marker; application code may only pass it through."""


class UnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[TransactionContext]: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
```

Define `UserId`, `WorkspaceId`, `DocumentId`, `SessionId`, `BranchId`, `BundleId`, and `ProposalId` as `NewType(..., UUID)`. Define `SOTError(code, message)` plus `NotFound`, `Forbidden`, `Conflict`, and `InvalidInput` subclasses with no HTTP dependency.

- [ ] **Step 4: Implement the PostgreSQL transaction adapter**

`PostgresTransactionContext` contains one `psycopg.AsyncConnection[Any]`. `PostgresUnitOfWork.transaction()` obtains one pool connection, opens one `connection.transaction()`, yields the opaque context, and relies on psycopg for commit/rollback. It exposes no repositories as properties.

- [ ] **Step 5: Write the migration integration test**

Create a function-scoped `database_url` fixture using a guarded async context
manager in `tests/postgres.py`. It connects to the maintenance `postgres` database
using `SOT_TEST_POSTGRES_ADMIN_URL` (default local server credentials), generates
its own `sot_test_<32 lowercase hex UUID>` name, and executes quoted `CREATE
DATABASE ... TEMPLATE template0`. Only after successful creation may cleanup drop
that exact generated name. Validate the full name before both operations, quote
it with `psycopg.sql.Identifier`, and never accept the application URL or a caller
supplied name as a destructive target. Do not use `IF NOT EXISTS` to adopt an
existing database. Close every application pool/connection before cleanup.

Guard tests reject `sot`, `postgres`, templates, malformed names, and SQL-shaped
inputs. Real PostgreSQL tests prove two simultaneous fixtures are isolated and
both databases disappear after an exception. If the role cannot create disposable
databases, report the privilege error; never fall back to resetting a shared DB.
All identity/workspace and legacy integration tests must consume this fixture.

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_migrations_are_ordered_once_and_not_run_by_app_startup(
    database_url: str,
) -> None:
    await run_migrations(database_url, MIGRATIONS)
    await run_migrations(database_url, MIGRATIONS)
    assert await applied_versions(database_url) == (1,)

    app = build_app(Settings(database_url=database_url, models=("test",)))
    async with app.router.lifespan_context(app):
        assert await applied_versions(database_url) == (1,)
```

- [ ] **Step 6: Run the migration test and verify it fails against startup migration behavior**

Run: `uv run --project backend pytest backend/tests/integration/test_migrations.py -q -m integration`

Expected: FAIL because `build_app()` currently invokes `apply_migrations()` in its lifespan and there is no migration ledger.

- [ ] **Step 7: Implement the ordered standalone migration runner**

Create `sot.schema_migration(version integer primary key, filename text unique, applied_at timestamptz)` and parse migration filenames by their numeric prefix. In one transaction per file, acquire `pg_advisory_xact_lock(hashtext('sot-schema-migration'))`, skip a recorded version only when its stored filename matches, execute the SQL, and insert its ledger row. `python -m sot.bootstrap.migrate` reads `SOT_DATABASE_URL` and exits nonzero on a gap, duplicate version, or recorded filename mismatch. Test filename drift on a disposable database and prove its existing ledger row remains unchanged.

- [ ] **Step 8: Move settings and make startup migration-free**

`bootstrap/settings.py` retains `database_url`, `models`, and `cors_origins`, and adds `environment: Literal["local", "test", "production"]`. Change `sot/main.py` to re-export `app` from `sot.bootstrap.app`; its lifespan opens/closes the pool only. Add a `sot-migrate = "sot.bootstrap.migrate:main"` project script.

- [ ] **Step 9: Run shared, integration, lint, and type checks**

```bash
uv run --project backend pytest backend/tests/shared backend/tests/integration/test_migrations.py -q
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy backend/src backend/tests
```

Expected: all PASS.

- [ ] **Step 10: Commit the foundation**

```bash
git add backend/src/sot/shared backend/src/sot/bootstrap backend/src/sot/main.py backend/pyproject.toml backend/tests/shared backend/tests/postgres.py backend/tests/integration/__init__.py backend/tests/integration/conftest.py backend/tests/integration/test_database_isolation.py backend/tests/integration/test_migrations.py
git commit -m "feat: add explicit transactions and migrations"
```

### Task 3: Implement the Unified Authentication Facade

**Files:**

- Create: `backend/migrations/002_identity.sql`
- Create: `backend/src/sot/identity/domain.py`
- Create: `backend/src/sot/identity/contracts.py`
- Create: `backend/src/sot/identity/ports.py`
- Create: `backend/src/sot/identity/application.py`
- Create: `backend/src/sot/identity/tokens.py`
- Create: `backend/src/sot/identity/postgres.py`
- Create: `backend/src/sot/identity/providers/base.py`
- Create: `backend/src/sot/identity/providers/google.py`
- Create: `backend/src/sot/identity/api.py`
- Modify: `backend/src/sot/bootstrap/settings.py`
- Modify: `backend/pyproject.toml`
- Create: `backend/tests/identity/test_auth_facade.py`
- Create: `backend/tests/identity/test_google_provider.py`
- Create: `backend/tests/identity/test_api.py`
- Create: `backend/tests/integration/test_identity_postgres.py`

**Interfaces:**

- Consumes: `Clock`, `TransactionContext`, `UnitOfWorkFactory`, `SOTError`.
- Produces: `Actor`, `AuthFacade`, `AuthProvider`, `IdentityReader`, `resolve_actor()`, and `/api/v1/auth/*` routes.

- [ ] **Step 1: Write AuthFacade tests with a fake provider and repositories**

```python
@pytest.mark.asyncio
async def test_login_links_issuer_subject_and_issues_sot_tokens() -> None:
    provider = FakeProvider(VerifiedIdentity(
        issuer="https://accounts.google.com", subject="google-123",
        email="alice@example.com", display_name="Alice",
    ))
    facade = auth_facade(provider=provider)
    result = await facade.login(provider_name="google", credential="id-token")
    assert result.user.email == "alice@example.com"
    assert result.tokens.access_token
    assert result.tokens.refresh_token
    assert await facade.authenticate(result.tokens.access_token) == Actor(result.user.id)


@pytest.mark.asyncio
async def test_refresh_rotates_only_one_token_family() -> None:
    first = await facade.login(provider_name="google", credential="first-device")
    second = await facade.login(provider_name="google", credential="second-device")
    rotated = await facade.refresh(first.tokens.refresh_token)
    with pytest.raises(AuthTokenInvalid):
        await facade.refresh(first.tokens.refresh_token)
    assert await facade.refresh(second.tokens.refresh_token)
    assert rotated.tokens.refresh_token != first.tokens.refresh_token
```

- [ ] **Step 2: Run the facade test and verify missing identity types**

Run: `uv run --project backend pytest backend/tests/identity/test_auth_facade.py -q`

Expected: FAIL with missing `sot.identity` modules.

- [ ] **Step 3: Define identity domain and public contracts**

```python
@dataclass(frozen=True, slots=True)
class Actor:
    user_id: UserId


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    issuer: str
    subject: str
    email: str
    display_name: str


class AuthProvider(Protocol):
    async def verify(self, credential: str) -> VerifiedIdentity: ...


class GoogleTokenVerifier(Protocol):
    async def verify(self, credential: str, audience: str) -> Mapping[str, object]: ...


class IdentityReader(Protocol):
    async def require_actor(self, tx: TransactionContext, user_id: UserId) -> Actor: ...
```

Domain records are `User`, `UserIdentity`, and `AuthSession`. Enforce provider identity uniqueness on `(issuer, subject)`, never on mutable Google email.

- [ ] **Step 4: Implement token and facade behavior**

Add `google-auth>=2,<3` and `PyJWT[crypto]>=2.10,<3`. `SOTAccessTokenCodec` issues HS256 JWTs containing `sub`, `iat`, `exp`, `iss="sot"`, and a random `jti`; it contains no workspace claim. Refresh tokens use `secrets.token_urlsafe(48)`, store only SHA-256 hashes, rotate in one transaction, and retain one `family_id` per browser/device.

`AuthFacade.login()` verifies through the selected provider, upserts `(issuer, subject)`, creates one auth session, and returns raw tokens. `refresh()` revokes the presented hash before inserting the replacement. `logout()` revokes the current family; `logout_all()` revokes every active session for the actor.

- [ ] **Step 5: Test and implement Google verification**

Inject `GoogleTokenVerifier` into `GoogleAuthAdapter`. The production verifier wraps `google.oauth2.id_token.verify_oauth2_token`; unit tests use a deterministic fake. Assert the adapter rejects a mismatched `aud`, an unverified email, missing `sub`, and an issuer outside `accounts.google.com`/`https://accounts.google.com`. Normalize only a verified result into `VerifiedIdentity`.

- [ ] **Step 6: Create the identity migration and PostgreSQL adapter**

`002_identity.sql` creates `sot.sot_user`, `sot.sot_user_identity`, and `sot.sot_auth_session`. Use UUID primary keys; unique `(issuer, subject)`; unique refresh `token_hash`; `family_id`; `expires_at`; `revoked_at`; and indexes on `(user_id, revoked_at)` and `(family_id, revoked_at)`. The adapter receives `TransactionContext` on every method and never commits.

- [ ] **Step 7: Write HTTP contract tests before the routes**

```python
@pytest.mark.asyncio
async def test_google_login_sets_refresh_cookie_and_returns_access_token() -> None:
    response = await client.post("/api/v1/auth/google", json={"credential": "google-id"})
    assert response.status_code == 200
    assert response.json()["access_token"]
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=Lax" in cookie


@pytest.mark.asyncio
async def test_access_token_identifies_user_without_workspace_claim() -> None:
    token = (await login(client)).access_token
    claims = codec.decode_claims_for_test(token)
    assert "workspace_id" not in claims
    assert (await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})).status_code == 200
```

- [ ] **Step 8: Implement auth routes and request actor resolution**

Add `POST /api/v1/auth/google`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/logout-all`, and `GET /api/v1/me`. Access tokens are returned in JSON; refresh tokens are set only as `HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`. `resolve_actor()` reads only Bearer auth in production. A separate `resolve_development_actor()` accepts `X-SOT-User` only when `environment in {"local", "test"}` and startup rejects development auth in production.

- [ ] **Step 9: Run identity checks**

```bash
uv run --project backend pytest backend/tests/identity backend/tests/integration/test_identity_postgres.py -q
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy backend/src backend/tests
```

Expected: all PASS with no network access.

- [ ] **Step 10: Commit identity**

```bash
git add backend/migrations/002_identity.sql backend/pyproject.toml backend/src/sot/identity backend/src/sot/bootstrap/settings.py backend/tests/identity backend/tests/integration/test_identity_postgres.py
git commit -m "feat: add unified Google and SOT authentication"
```

### Task 4: Implement Workspace Membership and RBAC

**Files:**

- Create: `backend/migrations/003_workspace.sql`
- Create: `backend/src/sot/workspace/domain.py`
- Create: `backend/src/sot/workspace/contracts.py`
- Create: `backend/src/sot/workspace/ports.py`
- Create: `backend/src/sot/workspace/application.py`
- Create: `backend/src/sot/workspace/postgres.py`
- Create: `backend/src/sot/workspace/api.py`
- Create: `backend/tests/workspace/test_domain.py`
- Create: `backend/tests/workspace/test_application.py`
- Create: `backend/tests/workspace/test_api.py`
- Create: `backend/tests/integration/test_workspace_postgres.py`

**Interfaces:**

- Consumes: `Actor`, `TransactionContext`, `UnitOfWorkFactory`, shared IDs/errors.
- Produces: `WorkspaceAuthorizer`, `WorkspaceMemberReader`, workspace command/query handlers, and workspace HTTP routes.

- [ ] **Step 1: Write failing role-catalog and permission tests**

```python
def test_fixed_workspace_role_catalog() -> None:
    assert permissions_for(WorkspaceRole.OWNER) >= {
        Permission.WORKSPACE_MANAGE, Permission.DOCUMENT_PUBLISH,
        Permission.SESSION_CREATE, Permission.SESSION_PARTICIPATE,
    }
    assert Permission.SESSION_CREATE in permissions_for(WorkspaceRole.MEMBER)
    assert permissions_for(WorkspaceRole.VIEWER) == {Permission.DOCUMENT_READ, Permission.SESSION_READ}


@pytest.mark.asyncio
async def test_authorizer_requires_membership_in_the_routed_workspace() -> None:
    with pytest.raises(WorkspaceForbidden):
        await authorizer.require(tx, actor, other_workspace_id, Permission.SESSION_CREATE)
```

- [ ] **Step 2: Run the tests and verify the module is absent**

Run: `uv run --project backend pytest backend/tests/workspace/test_domain.py backend/tests/workspace/test_application.py -q`

Expected: FAIL with missing workspace domain and handlers.

- [ ] **Step 3: Define the domain and public capability contracts**

```python
class WorkspaceRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(StrEnum):
    WORKSPACE_MANAGE = "workspace.manage"
    DOCUMENT_CREATE = "document.create"
    DOCUMENT_READ = "document.read"
    DOCUMENT_PUBLISH = "document.publish"
    SESSION_CREATE = "session.create"
    SESSION_READ = "session.read"
    SESSION_PARTICIPATE = "session.participate"


class WorkspaceAuthorizer(Protocol):
    async def require(
        self, tx: TransactionContext, actor: Actor,
        workspace_id: WorkspaceId, permission: Permission,
    ) -> WorkspaceMembership: ...
```

`owner` includes `DOCUMENT_CREATE`; `member` and `viewer` do not. `WorkspaceMemberReader.require_member()` is the capability used by the session module to enforce `SessionMember ⊆ WorkspaceMember`.

- [ ] **Step 4: Implement handlers with one transaction each**

Implement `CreateWorkspace`, `AddWorkspaceMember`, `ListActorWorkspaces`, and `GetWorkspace`. Creating a workspace inserts its creator as `owner` in the same transaction. `AddWorkspaceMember` requires `workspace.manage`. Repository and downstream contracts receive `tx` and never commit.

- [ ] **Step 5: Create migration and adapter**

`003_workspace.sql` creates `sot.sot_workspace` and `sot.sot_workspace_member`, including primary key `(workspace_id, user_id)`, role check `owner|member|viewer`, FK to `sot_user`, and an index for listing by user. The PostgreSQL adapter includes `workspace_id` in every lookup and update predicate.

- [ ] **Step 6: Add workspace-scoped HTTP tests and routes**

Test `GET /api/v1/workspaces`, `POST /api/v1/workspaces`, and `POST /api/v1/workspaces/{workspace_id}/members`. Assert an access token for one user cannot operate on an unjoined workspace and that the URL path, not a token claim, supplies tenant context. Route DTOs use `extra="forbid"` and map to application commands explicitly.

- [ ] **Step 7: Wire identity and workspace in `build_app()`**

Modify `bootstrap/app.py` so it constructs the pool, UoW factory, identity/workspace adapters, handlers, `AuthFacade`, routers, and exception mapper through constructor injection. FastAPI `Depends` resolves only request actor and request-scoped route inputs. Production uses a canonical FastAPI app with no legacy routes. Test the actual production factory's route surface and bearer boundary.

Centralize authentication, authorization, not-found, conflict, request validation,
and unexpected-failure mapping into the approved `{error: {code, message}}`
envelope. Route functions propagate typed errors; they do not create local
`HTTPException(detail=...)` auth responses. Use explicit closed Pydantic response
DTOs and field-by-field mapping for login, refresh, me, workspace, and membership
responses. Never return or recursively serialize domain/application dataclasses.
Contract tests against the composed app lock both response schemas and safe error
envelopes. Unknown add-member target users are a target-not-found error (404),
while an unknown authenticated token subject remains an authentication error (401).

- [ ] **Step 8: Run the milestone verification**

```bash
uv run --project backend pytest backend/tests/architecture backend/tests/shared backend/tests/identity backend/tests/workspace backend/tests/integration/test_migrations.py backend/tests/integration/test_identity_postgres.py backend/tests/integration/test_workspace_postgres.py -q
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy backend/src backend/tests
```

Expected: all PASS; existing vertical-slice tests remain runnable through their legacy composition path.

- [ ] **Step 9: Commit workspace RBAC**

```bash
git add backend/migrations/003_workspace.sql backend/src/sot/workspace backend/src/sot/bootstrap/app.py backend/tests/workspace backend/tests/integration/test_workspace_postgres.py
git commit -m "feat: add workspace-scoped RBAC"
```
