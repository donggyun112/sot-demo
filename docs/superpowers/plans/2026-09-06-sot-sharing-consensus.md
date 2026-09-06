# SOT Sharing and Consensus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add revocable public bundle capabilities, detached cross-workspace forks, versioned consensus, approvals, and explicit authorized publication to main.

**Architecture:** The sharing module owns only ShareLink capability lifecycle and sanitized fork orchestration; immutable Bundles remain session-owned. Consensus snapshots approvers per proposal version and calls document publication synchronously inside the top-level merge transaction, without an event bus or background worker.

**Tech Stack:** Python 3.12+, FastAPI, psycopg 3 async, PostgreSQL 16, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-06-sot-backend-v1-design.md`

## Global Constraints

- Complete `2026-09-06-sot-document-session.md` first.
- ShareLink is the only sharing state: `active -> revoked` or time-derived `expired`.
- A Bundle is an immutable session-owned snapshot; revoking a ShareLink never mutates or deletes its Bundle.
- Link creation requires the owning Session to be open; its owner can revoke an existing link after the Session closes, subject to current workspace permission.
- Public toss access reveals only BundleItem and allowed attribution fields, never private Turns, Session membership, or Workspace membership.
- A fork copies the public snapshot into a new private Session/Branch in an explicitly selected destination workspace.
- A fork grants no source permission, has no live source read, survives later revocation, and exposes only its stored attribution snapshot.
- Proposal approvers and approvals belong to one immutable Proposal version.
- Last approval produces `approved`, not a main revision. Only an explicit `MergeProposal` by `document.publish` permission can publish.
- Cross-module work is synchronous and shares the top-level `TransactionContext`; no event bus, outbox, worker, or cross-module SQL join.

---

## File Structure

- `backend/migrations/005_sharing.sql`: hashed ShareLinks and detached fork provenance.
- `backend/migrations/006_consensus.sql`: proposal versions, approver snapshots, approvals, and proposal bundles.
- `backend/src/sot/sharing/{api,application,contracts,domain,ports,postgres}.py`: capability links, public views, revoke, and fork.
- `backend/src/sot/consensus/{api,application,contracts,domain,ports,postgres}.py`: proposals, decisions, and merge orchestration.
- `backend/tests/sharing/`: token, public projection, revoke, and fork tests.
- `backend/tests/consensus/`: version, approver, decision, stale, and merge tests.
- `backend/tests/integration/test_sharing_consensus_postgres.py`: SQL constraints and concurrent publication.

### Task 1: Implement ShareLink Capability Lifecycle and Public Reads

**Files:**

- Create: `backend/src/sot/sharing/domain.py`
- Create: `backend/src/sot/sharing/contracts.py`
- Create: `backend/src/sot/sharing/ports.py`
- Create: `backend/src/sot/sharing/application.py`
- Create: `backend/tests/sharing/test_share_link.py`
- Create: `backend/tests/sharing/test_public_view.py`
- Create: `backend/tests/sharing/__init__.py`
- Modify: `backend/src/sot/session/contracts.py`
- Modify: `backend/src/sot/session/application.py`
- Modify: `backend/src/sot/identity/contracts.py`
- Modify: `backend/tests/session/test_bundle.py`
- Modify: `docs/superpowers/specs/2026-09-06-sot-backend-v1-design.md`

**Interfaces:**

- Consumes: `ShareableBundleReader` and `BundleRevocationAuthorizer` from `session.contracts`, `IdentityAttributionReader` from `identity.contracts`, `Clock`, `UnitOfWorkFactory`.
- Produces: `CreateShareLink`, `RevokeShareLink`, `ReadPublicBundle`, `PublicBundleSnapshot`, and token-hash repository contracts.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_share_link_status_is_active_revoked_or_expired() -> None:
    link = ShareLink.create(
        workspace_id=workspace_id, bundle_id=bundle_id,
        token_hash=token_hash, created_by=user_id,
        created_at=now, expires_at=now + timedelta(days=7),
    )
    assert link.status(now) is ShareLinkStatus.ACTIVE
    assert link.revoke(user_id, now).status(now) is ShareLinkStatus.REVOKED
    assert link.status(now + timedelta(days=8)) is ShareLinkStatus.EXPIRED


@pytest.mark.asyncio
async def test_public_read_returns_bundle_snapshot_only() -> None:
    result = await reader.execute(raw_token)
    assert result.items == public_bundle.items
    assert not hasattr(result, "session_id")
    assert not hasattr(result, "workspace_members")
    assert repository.last_lookup == sha256(raw_token.encode()).digest()
```

- [ ] **Step 2: Run the tests and verify missing sharing types**

Run: `uv run --project backend pytest backend/tests/sharing/test_share_link.py backend/tests/sharing/test_public_view.py -q`

Expected: FAIL with missing sharing module symbols.

- [ ] **Step 3: Define the domain and safe public contract**

```python
class ShareLinkStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class PublicBundleSnapshot:
    bundle_id: BundleId
    title: str
    items: tuple[PublicBundleItem, ...]
    attribution: AttributionSnapshot
```

Do not place raw token, workspace ID, private Session ID, Turn objects, or membership data in `PublicBundleSnapshot`. `expired` is derived from `expires_at`; only revoke is a stored transition.

- [ ] **Step 4: Implement command/query handlers**

`CreateShareLink` authenticates the actor and calls `ShareableBundleReader.require_shareable_snapshot(tx, actor=actor, workspace_id=workspace_id, bundle_id=bundle_id)`. Session resolves the Bundle's actual owning Session and enforces owner-only `SessionPermission.PUBLISH_BUNDLE` and an open Session; sharing must not combine an ordinary `BundleReader` result with a separately supplied Session ID. The immutable internal `ShareableBundleSnapshot` wrapper carries the safe `BundleSnapshot` and its actual `published_by` identity. Publisher ID stays out of `BundleSnapshot` and every public DTO.

Approved attribution ruling: `author_display_name` means the display name of the user who actually published the Bundle, not the ShareLink creator. `IdentityAttributionReader.require_attribution(tx, published_by)` returns only frozen `IdentityAttribution(display_name)`. Sharing freezes that name at ShareLink creation into a complete sharing-owned `PublicBundleSnapshot`; later profile changes never change existing public snapshots or forks. Task 1 adds the narrow identity contract and a fake; Task 5 wires its production implementation without exposing a full User or cross-module SQL joins.

The handler generates `secrets.token_urlsafe(32)`, stores only SHA-256 bytes, and returns the raw token once. `RevokeShareLink` uses workspace-scoped lookup and passes the stored link's Bundle ID to the separate session-owned `BundleRevocationAuthorizer.require_revocation(tx, actor=actor, workspace_id=workspace_id, bundle_id=link.bundle_id)`. This capability checks current workspace permission and owner permission on the Bundle's actual owning Session using `SessionPermission.REVOKE_TOSS`, returns `None`, and permits both open and closed Sessions. It does not load a Bundle snapshot or reuse the open-session publication capability. Link creation continues to require the original open publish capability. `ReadPublicBundle` hashes its token, rejects revoked/expired links, and returns the stored public snapshot without actor/workspace authorization or source identity/session reads.

Test that owning Session A cannot authorize sharing Session B's Bundle when the actor is only a viewer/editor in B. No caller-provided Session ID may substitute for the Bundle's actual owner relationship.

Test create → close Session → revoke → public 404, including production PostgreSQL/API composition. Creation after close must remain rejected; non-owner and cross-workspace revocation must remain denied. Proposal revision must check workspace membership before its repository lookup, and absent/private proposal IDs must produce the same result for unauthorized actors.

- [ ] **Step 5: Run sharing tests and architecture checks**

```bash
uv run --project backend pytest backend/tests/sharing backend/tests/architecture -q
uv run --project backend ruff check backend/src/sot/sharing backend/tests/sharing
uv run --project backend mypy backend/src/sot/sharing backend/tests/sharing
```

Expected: all PASS.

- [ ] **Step 6: Commit ShareLink behavior**

```bash
git add backend/src/sot/sharing backend/tests/sharing
git commit -m "feat: add public bundle capabilities"
```

### Task 2: Implement Detached Cross-Workspace Forks

**Files:**

- Modify: `backend/src/sot/sharing/application.py`
- Modify: `backend/src/sot/sharing/contracts.py`
- Modify: `backend/src/sot/session/contracts.py`
- Modify: `backend/src/sot/session/application.py`
- Create: `backend/tests/sharing/test_fork.py`
- Create: `backend/tests/session/test_fork_origin.py`

**Interfaces:**

- Consumes: `WorkspaceAuthorizer`, `ReadPublicBundle`, `SessionForkWriter`.
- Produces: `ForkSharedBundle` and detached `ForkOrigin` persisted by the session module.

- [ ] **Step 1: Write failing cross-workspace fork tests**

```python
@pytest.mark.asyncio
async def test_fork_copies_only_public_items_into_destination_workspace() -> None:
    result = await fork_shared_bundle.execute(
        actor=bob, destination_workspace_id=bob_workspace,
        raw_token=alice_public_token,
    )
    assert result.session.workspace_id == bob_workspace
    assert result.session.status is SessionStatus.OPEN
    assert result.session.owner_id == bob.user_id
    assert result.seed_turns == turns_from(public_bundle.items)
    assert result.fork_origin.source_bundle_id == alice_bundle_id
    assert result.fork_origin.attribution == public_bundle.attribution


@pytest.mark.asyncio
async def test_revocation_after_fork_does_not_change_fork() -> None:
    result = await fork_once()
    await revoke_source_link()
    assert await destination_sessions.get(result.session.id) == result.session
```

- [ ] **Step 2: Run tests and verify `SessionForkWriter` is absent**

Run: `uv run --project backend pytest backend/tests/sharing/test_fork.py backend/tests/session/test_fork_origin.py -q`

Expected: FAIL on missing fork capability contracts.

- [ ] **Step 3: Define the narrow session capability**

```python
class SessionForkWriter(Protocol):
    async def create_from_public_bundle(
        self, tx: TransactionContext, *, actor: Actor,
        destination_workspace_id: WorkspaceId,
        source_bundle_id: BundleId,
        attribution: ForkAttribution,
        items: tuple[ForkSeedItem, ...],
    ) -> ForkedSessionResult: ...
```

`ForkAttribution` and `ForkSeedItem` come from `sot.session.contracts`. The sharing handler explicitly maps its public DTO into those session-owned inputs, so session never imports sharing. `ForkOrigin` stores destination `workspace_id`, new `session_id`, opaque `source_bundle_id`, and attribution fields copied at fork time. The source Bundle ID has deliberately no foreign key and is never dereferenced by a request path.

- [ ] **Step 4: Implement one top-level fork transaction**

`ForkSharedBundle` opens the transaction, authenticates public token snapshot, verifies `session.create` in the destination workspace, and calls `SessionForkWriter` with only sanitized DTOs. The session module creates Session + owner membership + initial Branch + seed Turns + ForkOrigin atomically. It does not add Bob to Alice's workspace or source session.

- [ ] **Step 5: Run fork and module-boundary tests**

```bash
uv run --project backend pytest backend/tests/sharing backend/tests/session/test_fork_origin.py backend/tests/architecture -q
uv run --project backend mypy backend/src/sot/sharing backend/src/sot/session
```

Expected: all PASS.

- [ ] **Step 6: Commit detached fork behavior**

```bash
git add backend/src/sot/sharing backend/src/sot/session backend/tests/sharing backend/tests/session/test_fork_origin.py
git commit -m "feat: add detached public bundle forks"
```

### Task 3: Implement Versioned Proposals and Approver Snapshots

**Files:**

- Create: `backend/src/sot/consensus/domain.py`
- Create: `backend/src/sot/consensus/contracts.py`
- Create: `backend/src/sot/consensus/ports.py`
- Create: `backend/src/sot/consensus/application.py`
- Modify: `backend/src/sot/session/contracts.py`
- Create: `backend/tests/consensus/test_proposal.py`
- Create: `backend/tests/consensus/test_application.py`

**Interfaces:**

- Consumes: `BundleReader`, `SessionApproverReader`, `SessionAuthorizer`, `BranchVersionGuard`, `DocumentReader`, `UnitOfWorkFactory`.
- Produces: `CreateProposal`, `ReviseProposal`, `DecideProposal`, `ProposalReader`, and immutable proposal-version results.

- [ ] **Step 1: Write failing version and approval tests**

```python
def test_new_version_invalidates_previous_approvals() -> None:
    proposal = proposal_with_required({alice_id, bob_id})
    proposal.approve(version=1, actor_id=alice_id, now=now)
    proposal.revise(
        actor_id=bob_id, expected_version=1, content="revised",
        required_approvers={alice_id, bob_id}, now=later,
    )
    assert proposal.version == 2
    assert proposal.approvals_for_current_version == ()


def test_membership_change_does_not_change_existing_snapshot() -> None:
    proposal = proposal_with_required({alice_id, bob_id})
    session_members.remove(bob_id)
    assert proposal.required_approvers == frozenset({alice_id, bob_id})
```

- [ ] **Step 2: Run tests and verify consensus types are absent**

Run: `uv run --project backend pytest backend/tests/consensus/test_proposal.py -q`

Expected: FAIL with missing consensus domain symbols.

- [ ] **Step 3: Define proposal state and version-owned records**

```python
class ProposalStatus(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"
    MERGED = "merged"


@dataclass(frozen=True, slots=True)
class ProposalVersion:
    proposal_id: ProposalId
    version: int
    base_revision_id: RevisionId
    content: str
    required_approver_ids: frozenset[UserId]
    bundle_ids: tuple[BundleId, ...]
    citations: tuple[ProposalCitation, ...]
```

Approval identity is `(proposal_id, proposal_version, approver_user_id)`. A reject moves only the current version to `rejected`; revising content or approvers creates the next version and restores `open` with no carried approvals.

- [ ] **Step 4: Define and use the session approver capability**

`SessionApproverReader.list_required_approvers(tx, workspace_id, session_id)` returns current Session owner/editor IDs. `CreateProposal` unions that set with creator and explicit additional approvers, validates every approver as an active WorkspaceMember, and stores the immutable snapshot.

Expose the Agent-facing mutation as a narrow contract that uses the session-owned result type:

```python
class ProposalCreator(Protocol):
    async def create_from_agent(
        self, *, actor: Actor, workspace_id: WorkspaceId,
        branch_id: BranchId, expected_branch_version: int,
        content: str,
    ) -> BranchMutationResult: ...
```

- [ ] **Step 5: Implement proposal command transactions**

`CreateProposal` requires Session `editor`, validates source bundle IDs through `BundleReader`, invokes `BranchVersionGuard.advance()` with the Agent-supplied expected version when called as a tool, and stores proposal/version/approvers in one transaction. It returns the session-owned `BranchMutationResult`, avoiding an import from the agent module. `ReviseProposal` checks expected Proposal version and writes a new version. `DecideProposal` allows only a current required approver, stores one decision, and derives `approved` only when all current required approvers approved.

- [ ] **Step 6: Verify consensus behavior**

```bash
uv run --project backend pytest backend/tests/consensus backend/tests/architecture -q
uv run --project backend ruff check backend/src/sot/consensus backend/tests/consensus
uv run --project backend mypy backend/src/sot/consensus backend/tests/consensus
```

Expected: all PASS.

- [ ] **Step 7: Commit proposal consensus**

```bash
git add backend/src/sot/consensus backend/src/sot/session/contracts.py backend/tests/consensus
git commit -m "feat: add versioned proposal consensus"
```

### Task 4: Implement Explicit Atomic Main Publication

**Files:**

- Modify: `backend/src/sot/consensus/application.py`
- Modify: `backend/src/sot/consensus/contracts.py`
- Modify: `backend/src/sot/consensus/domain.py`
- Modify: `backend/src/sot/consensus/ports.py`
- Modify: `backend/src/sot/document/contracts.py`
- Modify: `backend/src/sot/document/application.py`
- Modify: `backend/tests/consensus/test_proposal.py`
- Modify: `backend/tests/consensus/test_application.py`
- Create: `backend/tests/consensus/merge_support.py`
- Create: `backend/tests/consensus/test_merge.py`
- Create: `backend/tests/integration/test_concurrent_merge.py`
- Modify: `docs/superpowers/specs/2026-09-06-sot-backend-v1-design.md`
- Modify: `docs/superpowers/plans/2026-09-06-sot-sharing-consensus.md`

**Interfaces:**

- Merge consumes: `WorkspaceAuthorizer`, `DocumentReader`, `DocumentPublisher`; it never calls private `BundleReader`.
- Creation/revision consumes `BundleReader` to validate version-owned citations before approval.
- Produces: `ProposalCitation`, explicit citation inputs on create/revise, `MergeProposal`, and `MergeProposalResult` with a published revision and citations.

**Approved citation decision:** Add frozen consensus-owned `ProposalCitation(bundle_id, bundle_item_position, claim_anchor)` and an ordered immutable tuple on `ProposalVersion`. Each citation must reference its version's `bundle_ids`, an existing zero-based item in an authorized immutable Bundle snapshot, and a nonblank anchor occurring verbatim in that version's content. Reject duplicate `(claim_anchor, bundle_id, bundle_item_position)` identities. Create/revise require explicit `citations`; empty means none, and a revision never silently carries old citations. The current content-only Agent command explicitly supplies empty bundles/citations. Validate all Bundle inputs during source-session-authorized creation/revision; merge maps the frozen version inputs directly and grants no private read access.

- [ ] **Step 1: Write failing explicit-publication tests**

```python
@pytest.mark.asyncio
async def test_last_approval_does_not_publish_main() -> None:
    await decide(alice, Decision.APPROVE)
    result = await decide(bob, Decision.APPROVE)
    assert result.status is ProposalStatus.APPROVED
    assert await documents.current_revision(document_id) == base_revision


@pytest.mark.asyncio
async def test_merge_requires_publish_permission_and_current_base() -> None:
    with pytest.raises(WorkspaceForbidden):
        await merge.execute(actor=member, command=merge_command)
    await advance_document_main_elsewhere()
    stale = await merge.execute(actor=owner, command=merge_command)
    assert stale.status is ProposalStatus.STALE
```

- [ ] **Step 2: Run tests and verify merge is not implemented**

Run: `uv run --project backend pytest backend/tests/consensus/test_merge.py -q`

Expected: FAIL because the modular consensus application lacks `MergeProposal`.

- [ ] **Step 3: Implement `MergeProposal` as the transaction owner**

Within one UoW transaction: require `document.publish`; lock/load the workspace-scoped Proposal; require expected version and status `approved`; load its Document revision through `DocumentReader`; mark stale and return without publishing when the base differs; map only that version's frozen citations to `RevisionCitationInput`; call `DocumentPublisher.publish(tx, ...)` with the loaded Document version; mark Proposal `merged`; save both modules; commit once. Return `MergeProposalResult(proposal_id, version, status, publication)` without source-session/creator/approver metadata. A workspace publisher without source-session membership must succeed; a non-publisher must be denied before proposal lookup.

- [ ] **Step 4: Test concurrent merge**

At Task 4, run two calls with controlled transaction adapters and an asyncio barrier. Assert exactly one new revision, one citation set and one main-pointer advance; the second receives stable `proposal_not_approved` conflict. Also cover competing proposals sharing a base and rollback after revision save, proposal save, conditional publication conflict, and commit failure. These tests prove application transaction composition, not PostgreSQL locking. Task 5 must add separate-connection live PostgreSQL concurrency. Do not use a global idempotency table.

- [ ] **Step 5: Run focused and integration tests**

```bash
uv run --project backend pytest backend/tests/consensus backend/tests/integration/test_concurrent_merge.py -q
uv run --project backend mypy backend/src/sot/consensus backend/src/sot/document
```

Expected: all PASS.

- [ ] **Step 6: Commit explicit publication**

```bash
git add backend/src/sot/consensus backend/src/sot/document backend/tests/consensus backend/tests/integration/test_concurrent_merge.py
git commit -m "feat: separate consensus from main publication"
```

### Task 5: Persist and Expose Sharing and Consensus

**Files:**

- Create: `backend/migrations/005_sharing.sql`
- Create: `backend/migrations/006_consensus.sql`
- Create: `backend/src/sot/sharing/postgres.py`
- Create: `backend/src/sot/sharing/api.py`
- Create: `backend/src/sot/consensus/postgres.py`
- Create: `backend/src/sot/consensus/api.py`
- Modify: `backend/src/sot/session/postgres.py`
- Modify: `backend/src/sot/bootstrap/app.py`
- Create: `backend/tests/sharing/test_api.py`
- Create: `backend/tests/consensus/test_api.py`
- Create: `backend/tests/integration/test_sharing_consensus_postgres.py`
- Modify: `backend/tests/integration/test_concurrent_merge.py`

**Interfaces:**

- Consumes: all handlers from Tasks 1–4 and request actor resolution.
- Produces: canonical toss, fork, proposal, decision, and merge REST APIs.

- [ ] **Step 1: Write persistence and HTTP contract tests**

Assert raw toss tokens are absent from PostgreSQL, revoked/expired public reads are 404, fork requires Bearer auth and destination membership, proposal approval uniqueness is version-scoped, and explicit merge requires workspace publish permission.

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_raw_toss_token_is_not_stored(pool, api) -> None:
    created = await api.create_toss(workspace_id, bundle_id, owner_token)
    async with pool.connection() as connection:
        row = await connection.execute(
            "SELECT token_hash FROM sot.sot_share_link WHERE id = %s",
            (created.id,),
        )
        stored = await row.fetchone()
    assert stored is not None
    assert created.token.encode() not in stored[0]


@pytest.mark.asyncio
async def test_merge_endpoint_requires_document_publish(client, approved_proposal) -> None:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/proposals/{approved_proposal.id}/merge",
        headers=member_token.bearer,
        json={"expected_version": approved_proposal.version},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "workspace_forbidden"
```

- [ ] **Step 2: Run tests and verify migrations/adapters are absent**

Run: `uv run --project backend pytest backend/tests/sharing/test_api.py backend/tests/consensus/test_api.py backend/tests/integration/test_sharing_consensus_postgres.py -q`

Expected: FAIL on missing migrations and adapters.

- [ ] **Step 3: Create sharing migration**

`005_sharing.sql` creates `sot.sot_share_link` with destination-independent token hash, source `workspace_id`, Bundle composite FK, `expires_at`, `revoked_at`, and unique hash. Add no source-workspace join path. The session-owned `sot_fork_origin` table already exists from migration 004; this task only adds its session adapter mapping.

- [ ] **Step 4: Create consensus migration**

`006_consensus.sql` creates `sot.sot_proposal`, `sot.sot_proposal_version`, `sot.sot_proposal_bundle`, `sot.sot_proposal_citation`, `sot.sot_proposal_approver`, and `sot.sot_approval`. Include workspace-scoped composite FKs, proposal version uniqueness, approval primary key `(workspace_id, proposal_id, proposal_version, approver_user_id)`, status checks, and indexes for open proposals by document/session.

Persist `sot_proposal_citation(workspace_id, proposal_id, proposal_version, position, claim_anchor, bundle_id, bundle_item_position)` with primary key `(workspace_id, proposal_id, proposal_version, position)` and unique citation identity `(workspace_id, proposal_id, proposal_version, claim_anchor, bundle_id, bundle_item_position)`. Add composite FKs to the proposal version, its version-owned `sot_proposal_bundle` membership, and session's existing `sot_bundle_item(workspace_id, bundle_id, position)`. Positions must be nonnegative and anchors nonblank; application/domain validate the exact content substring. Read/write citation order through consensus-owned SQL only, preserve older versions, and never rewrite citations on status/approval changes.

- [ ] **Step 5: Implement adapters and canonical routes**

Adapters accept `TransactionContext`, use explicit SQL, map rows locally, and never cross-read module tables. Register:

```text
POST   /api/v1/workspaces/{workspace_id}/bundles/{bundle_id}/tosses
DELETE /api/v1/workspaces/{workspace_id}/tosses/{toss_id}
GET    /api/v1/tosses/{token}
POST   /api/v1/workspaces/{workspace_id}/tosses/{token}/fork
POST   /api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals
GET    /api/v1/workspaces/{workspace_id}/proposals/{proposal_id}
PUT    /api/v1/workspaces/{workspace_id}/proposals/{proposal_id}
POST   /api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/decisions
POST   /api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/merge
```

Public GET adds `Cache-Control: private, no-store`. Logging middleware redacts the toss token path. All other routes resolve actor and validate path workspace before invoking handlers.

Proposal create/revise HTTP bodies require a `citations` list of `{bundle_id, bundle_item_position, claim_anchor}`; `[]` deliberately creates a version without citations. Reject missing citation input rather than guessing or carrying prior values. Expose merge's minimal `MergeProposalResult`, not the private `ProposalView`. Add persistence round trips across multiple versions, citation FK/uniqueness tests, a nonmember publisher HTTP test, and live concurrent merges over separate PostgreSQL connections (including rollback with no orphan revision/citations).

- [ ] **Step 6: Run milestone verification**

```bash
uv run --project backend pytest backend/tests/sharing backend/tests/consensus backend/tests/integration/test_sharing_consensus_postgres.py backend/tests/integration/test_concurrent_merge.py backend/tests/architecture -q
uv run --project backend ruff check backend/src backend/tests
uv run --project backend mypy backend/src backend/tests
```

Expected: all PASS.

- [ ] **Step 7: Commit persistence and routes**

```bash
git add backend/migrations/005_sharing.sql backend/migrations/006_consensus.sql backend/src/sot/sharing backend/src/sot/consensus backend/src/sot/session/postgres.py backend/src/sot/bootstrap/app.py backend/tests/sharing backend/tests/consensus backend/tests/integration
git commit -m "feat: expose sharing and consensus workflows"
```
