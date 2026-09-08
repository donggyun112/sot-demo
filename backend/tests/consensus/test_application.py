from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sot.consensus.application import (
    CreateProposal,
    DecideProposal,
    ProposalSources,
    ReadProposal,
    ReviseProposal,
)
from sot.consensus.domain import (
    ApprovalDecision,
    DocumentEdit,
    Proposal,
    ProposalCitation,
    ProposalNotFound,
    ProposalStatus,
)
from sot.document.contracts import (
    DocumentSummary,
    DocumentView,
    RevisionId,
    RevisionView,
)
from sot.identity.contracts import Actor
from sot.session.application import SessionAccess
from sot.session.contracts import (
    BranchContext,
    BundleItem,
    BundleSnapshot,
    SessionPermission,
    SessionStatus,
    SessionView,
)
from sot.session.domain import Session, SessionMember, SessionRole
from sot.shared.errors import Conflict, Forbidden, InvalidInput, NotFound
from sot.shared.ids import (
    BranchId,
    BundleId,
    DocumentId,
    ProposalId,
    SessionId,
    UserId,
    WorkspaceId,
)
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.application import WorkspaceAccess
from sot.workspace.contracts import WorkspaceMembership, WorkspaceRole
from sot.workspace.domain import WorkspaceForbidden
from tests.session.test_application import Memory as SessionMemory
from tests.workspace.test_application import MemoryStore as WorkspaceMemory

NOW = datetime(2026, 9, 6, tzinfo=UTC)
ALICE, BOB, CAROL, DAN = (UserId(uuid4()) for _ in range(4))
WORKSPACE = WorkspaceId(uuid4())
DOCUMENT = DocumentId(uuid4())
SESSION = SessionId(uuid4())
BRANCH = BranchId(uuid4())
BUNDLE = BundleId(uuid4())
BASE_REVISION = RevisionId(uuid4())


class FakeEvidence:
    """Answers EvidenceFreezer for tests that do not exercise curation.

    A proposal freezes the conversation it was written from; these tests are
    about the proposal, so the frozen result is a stable stand-in they can
    assert against.
    """

    def __init__(self, items: tuple[BundleItem, ...] = ()) -> None:
        self.items = items
        self.bundle_id = BundleId(uuid4())
        self.calls: list[BranchId] = []

    async def freeze(
        self, tx, *, actor, workspace_id, branch_id, title
    ) -> FrozenEvidence:
        self.calls.append(branch_id)
        return FrozenEvidence(self.bundle_id, self.items)


@dataclass
class MemoryTransaction:
    proposals: dict[ProposalId, Proposal]
    branch_version: int
    locked: set[ProposalId] = field(default_factory=set)


class Store:
    def __init__(self) -> None:
        self.proposals: dict[ProposalId, Proposal] = {}
        self.branch_version = 0
        self.lock = asyncio.Lock()
        self.active: MemoryTransaction | None = None
        self.transactions = 0
        self.fail_save = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[MemoryTransaction]:
        async with self.lock:
            self.transactions += 1
            tx = MemoryTransaction(dict(self.proposals), self.branch_version)
            self.active = tx
            try:
                yield tx
                self.proposals = tx.proposals
                self.branch_version = tx.branch_version
            finally:
                self.active = None

    def tx(self, tx: TransactionContext) -> MemoryTransaction:
        assert tx is self.active
        assert isinstance(tx, MemoryTransaction)
        return tx

    async def get_for_update(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
    ) -> Proposal | None:
        context = self.tx(tx)
        proposal = context.proposals.get(proposal_id)
        if proposal is None or proposal.workspace_id != workspace_id:
            return None
        context.locked.add(proposal_id)
        await asyncio.sleep(0)
        return proposal

    async def find(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
    ) -> Proposal | None:
        proposal = self.tx(tx).proposals.get(proposal_id)
        return proposal if proposal and proposal.workspace_id == workspace_id else None

    async def add(self, tx: TransactionContext, proposal: Proposal) -> None:
        if self.fail_save:
            raise RuntimeError("storage unavailable")
        assert proposal.id not in self.tx(tx).proposals
        self.tx(tx).proposals[proposal.id] = proposal

    async def save(self, tx: TransactionContext, proposal: Proposal) -> None:
        assert proposal.id in self.tx(tx).locked
        if self.fail_save:
            raise RuntimeError("storage unavailable")
        self.tx(tx).proposals[proposal.id] = proposal


class Capabilities:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.members = {ALICE, BOB, CAROL, DAN}
        self.editors = {ALICE, BOB}
        self.viewers = {DAN}
        self.document_id: DocumentId | None = DOCUMENT
        self.revision_id = BASE_REVISION
        self.bundle_ids = {BUNDLE}
        self.bundle_items = (
            BundleItem((uuid4(),), "user", "Question", "copied"),
            BundleItem((uuid4(),), "assistant", "Evidence", "edited"),
        )
        self.session_reads = 0
        self.session_views = 0
        self.bundle_reads = 0
        self.document_reads = 0

    async def require_member(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership:
        self.store.tx(tx)
        if workspace_id != WORKSPACE or user_id not in self.members:
            raise NotFound("workspace_not_found", "Workspace not found")
        return WorkspaceMembership(WORKSPACE, user_id, WorkspaceRole.MEMBER)

    async def require(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        permission: SessionPermission,
    ) -> SessionView:
        await self.require_member(tx, workspace_id, actor.user_id)
        self.session_reads += 1
        if session_id != SESSION or actor.user_id not in self.editors | self.viewers:
            raise NotFound("session_not_found", "Session not found")
        if (
            permission is not SessionPermission.READ
            and actor.user_id not in self.editors
        ):
            raise Forbidden("session_forbidden", "Session access denied")
        self.session_views += 1
        return SessionView(
            SESSION, WORKSPACE, self.document_id, ALICE, NOW, SessionStatus.OPEN
        )

    async def list_required_approvers(
        self,
        tx: TransactionContext,
        *,
        workspace_id: WorkspaceId,
        session_id: SessionId,
    ) -> frozenset[UserId]:
        self.store.tx(tx)
        assert workspace_id == WORKSPACE and session_id == SESSION
        return frozenset(self.editors)

    async def require_document(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> DocumentView:
        await self.require_member(tx, workspace_id, actor.user_id)
        if document_id != DOCUMENT:
            raise NotFound("document_not_found", "Document not found")
        self.document_reads += 1
        return DocumentView(
            DocumentSummary(DOCUMENT, WORKSPACE, "Document", self.revision_id, 1),
            RevisionView(
                self.revision_id, WORKSPACE, DOCUMENT, 1, "Main", None, ALICE, NOW, ()
            ),
        )

    async def require_snapshot(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> BundleSnapshot:
        await self.require(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session_id=SESSION,
            permission=SessionPermission.READ,
        )
        self.bundle_reads += 1
        if bundle_id not in self.bundle_ids:
            raise NotFound("bundle_not_found", "Bundle not found")
        return BundleSnapshot(bundle_id, "Bundle", self.bundle_items, NOW)

    async def read(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        permission: SessionPermission = SessionPermission.READ,
    ) -> BranchContext:
        if branch_id != BRANCH:
            raise NotFound("branch_not_found", "Branch not found")
        await self.require(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session_id=SESSION,
            permission=permission,
        )
        return BranchContext(
            WORKSPACE,
            SESSION,
            self.document_id,
            BRANCH,
            self.store.tx(tx).branch_version,
            (),
        )

    async def advance(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_version: int,
    ) -> int:
        await self.read(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            branch_id=branch_id,
            permission=SessionPermission.CREATE_PROPOSAL,
        )
        context = self.store.tx(tx)
        if context.branch_version != expected_version:
            raise Conflict("version_conflict", "Branch changed")
        context.branch_version += 1
        return context.branch_version


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class Harness:
    store: Store
    access: Capabilities
    create: CreateProposal
    revise: ReviseProposal
    decide: DecideProposal
    read: ReadProposal

    async def initial(self, *, extras: frozenset[UserId] = frozenset()) -> ProposalId:
        result = await self.create.execute(
            Actor(ALICE),
            WORKSPACE,
            SESSION,
            document_id=DOCUMENT,
            edits=(DocumentEdit("", "Proposed main"),),
            bundle_ids=(BUNDLE,),
            citations=(ProposalCitation(BUNDLE, 0, "main"),),
            additional_approver_ids=extras,
        )
        return result.id


@pytest.fixture
def env() -> Harness:
    store = Store()
    access = Capabilities(store)
    sources = ProposalSources(access, access, access, access, access, FakeEvidence())
    return Harness(
        store,
        access,
        CreateProposal(store, sources, access, access, lambda: store, FixedClock()),
        ReviseProposal(store, sources, lambda: store, FixedClock()),
        DecideProposal(store, access, lambda: store, FixedClock()),
        ReadProposal(store, access, access, lambda: store),
    )


@pytest.mark.asyncio
async def test_creation_freezes_required_union_bundles_and_authorized_source(
    env: Harness,
) -> None:
    proposal_id = await env.initial(extras=frozenset({CAROL}))
    saved = env.store.proposals[proposal_id]
    assert saved.required_approvers == frozenset({ALICE, BOB, CAROL})
    assert saved.current_version.additional_approver_ids == frozenset({CAROL})
    assert saved.current_version.bundle_ids == (BUNDLE,)
    assert saved.current_version.base_revision_id == BASE_REVISION
    assert (saved.workspace_id, saved.source_session_id, saved.document_id) == (
        WORKSPACE,
        SESSION,
        DOCUMENT,
    )
    assert env.store.transactions == 1
    env.access.editors.remove(BOB)
    assert env.store.proposals[proposal_id].required_approvers == frozenset(
        {ALICE, BOB, CAROL}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor,workspace,session,document",
    [
        (DAN, WORKSPACE, SESSION, DOCUMENT),
        (CAROL, WORKSPACE, SESSION, DOCUMENT),
        (ALICE, WorkspaceId(uuid4()), SESSION, DOCUMENT),
        (ALICE, WORKSPACE, SessionId(uuid4()), DOCUMENT),
        (ALICE, WORKSPACE, SESSION, DocumentId(uuid4())),
    ],
)
async def test_create_rejects_uneditable_or_wrong_scope_source(
    env: Harness,
    actor: UserId,
    workspace: WorkspaceId,
    session: SessionId,
    document: DocumentId,
) -> None:
    with pytest.raises((NotFound, Forbidden, InvalidInput)):
        await env.create.execute(
            Actor(actor),
            workspace,
            session,
            document_id=document,
            edits=(DocumentEdit("", "Bad"),),
            bundle_ids=(),
            citations=(),
        )
    assert env.store.proposals == {}


@pytest.mark.asyncio
async def test_invalid_bundle_or_inactive_approver_rolls_back(env: Harness) -> None:
    env.access.members.remove(BOB)
    with pytest.raises(NotFound):
        await env.initial()
    env.access.members.add(BOB)
    env.access.bundle_ids.clear()
    with pytest.raises(NotFound):
        await env.initial()
    assert env.store.proposals == {}


@pytest.mark.asyncio
async def test_revision_resnapshots_mandatory_preserves_explicit_and_resets_approvals(
    env: Harness,
) -> None:
    proposal_id = await env.initial(extras=frozenset({CAROL}))
    await env.decide.execute(
        Actor(ALICE),
        WORKSPACE,
        proposal_id,
        expected_version=1,
        decision=ApprovalDecision.APPROVE,
    )
    env.access.editors.remove(BOB)
    env.access.editors.add(DAN)
    env.access.revision_id = RevisionId(uuid4())
    result = await env.revise.execute(
        Actor(DAN),
        WORKSPACE,
        proposal_id,
        expected_version=1,
        edits=(DocumentEdit("", "Revised main"),),
        bundle_ids=(),
        citations=(),
    )
    assert result.version == 2
    assert result.status is ProposalStatus.OPEN
    assert result.current_version.required_approver_ids == frozenset(
        {ALICE, CAROL, DAN}
    )
    assert result.current_version.base_revision_id == env.access.revision_id
    assert result.approvals == ()
    saved = env.store.proposals[proposal_id]
    assert saved.versions[0].required_approver_ids == frozenset({ALICE, BOB, CAROL})
    assert len(saved.approvals) == 1


@pytest.mark.asyncio
async def test_only_creator_changes_explicit_extras_and_cannot_remove_mandatory(
    env: Harness,
) -> None:
    proposal_id = await env.initial(extras=frozenset({CAROL}))
    with pytest.raises(Forbidden):
        await env.revise.execute(
            Actor(BOB),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            edits=(DocumentEdit("", "Changed"),),
            bundle_ids=(),
            citations=(),
            additional_approver_ids=frozenset(),
        )
    result = await env.revise.execute(
        Actor(ALICE),
        WORKSPACE,
        proposal_id,
        expected_version=1,
        edits=(DocumentEdit("", "Changed"),),
        bundle_ids=(),
        citations=(),
        additional_approver_ids=frozenset(),
    )
    assert result.current_version.required_approver_ids == frozenset({ALICE, BOB})


@pytest.mark.asyncio
async def test_additional_approver_reads_current_proposal_and_decides_without_private_access(
    env: Harness,
) -> None:
    proposal_id = await env.initial(extras=frozenset({CAROL}))
    session_reads, bundle_reads = env.access.session_reads, env.access.bundle_reads
    view = await env.read.execute(Actor(CAROL), WORKSPACE, proposal_id)
    result = await env.decide.execute(
        Actor(CAROL),
        WORKSPACE,
        proposal_id,
        expected_version=1,
        decision=ApprovalDecision.APPROVE,
    )
    assert view.current_version.edits == (DocumentEdit("", "Proposed main"),)
    assert not hasattr(view, "versions")
    assert result.approvals[0].approver_user_id == CAROL
    assert env.access.session_reads == session_reads
    assert env.access.bundle_reads == bundle_reads
    async with env.store.transaction() as tx:
        with pytest.raises(NotFound):
            await env.access.require(
                tx,
                actor=Actor(CAROL),
                workspace_id=WORKSPACE,
                session_id=SESSION,
                permission=SessionPermission.READ,
            )


@pytest.mark.asyncio
async def test_nonrequired_reader_needs_source_session_and_cannot_decide(
    env: Harness,
) -> None:
    proposal_id = await env.initial()
    assert (
        await env.read.execute(Actor(DAN), WORKSPACE, proposal_id)
    ).id == proposal_id
    with pytest.raises(NotFound):
        await env.read.execute(Actor(CAROL), WORKSPACE, proposal_id)
    with pytest.raises(NotFound):
        await env.decide.execute(
            Actor(CAROL),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            decision=ApprovalDecision.APPROVE,
        )


@pytest.mark.asyncio
async def test_removed_workspace_member_cannot_read_or_decide_snapshot(
    env: Harness,
) -> None:
    proposal_id = await env.initial(extras=frozenset({CAROL}))
    env.access.members.remove(CAROL)
    with pytest.raises(NotFound):
        await env.read.execute(Actor(CAROL), WORKSPACE, proposal_id)
    with pytest.raises(NotFound):
        await env.decide.execute(
            Actor(CAROL),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            decision=ApprovalDecision.APPROVE,
        )
    assert CAROL in env.store.proposals[proposal_id].required_approvers


@pytest.mark.asyncio
async def test_concurrent_decisions_keep_both_approvals_and_approve_without_publication(
    env: Harness,
) -> None:
    proposal_id = await env.initial()
    await asyncio.gather(
        *(
            env.decide.execute(
                Actor(actor),
                WORKSPACE,
                proposal_id,
                expected_version=1,
                decision=ApprovalDecision.APPROVE,
            )
            for actor in (ALICE, BOB)
        )
    )
    saved = env.store.proposals[proposal_id]
    assert saved.status is ProposalStatus.APPROVED
    assert {a.approver_user_id for a in saved.approvals} == {ALICE, BOB}
    assert env.access.revision_id == BASE_REVISION


@pytest.mark.asyncio
async def test_concurrent_revisions_only_one_expected_version_wins(
    env: Harness,
) -> None:
    proposal_id = await env.initial()
    results = await asyncio.gather(
        *(
            env.revise.execute(
                Actor(actor),
                WORKSPACE,
                proposal_id,
                expected_version=1,
                edits=(DocumentEdit("", "Revision"),),
                bundle_ids=(),
                citations=(),
            )
            for actor in (ALICE, BOB)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(r, Conflict) for r in results) == 1
    assert env.store.proposals[proposal_id].version == 2


@pytest.mark.asyncio
async def test_agent_derives_source_and_advances_branch_atomically(
    env: Harness,
) -> None:
    result = await env.create.create_from_agent(
        actor=Actor(ALICE),
        workspace_id=WORKSPACE,
        branch_id=BRANCH,
        expected_branch_version=0,
        edits=(DocumentEdit("", "Agent proposal"),),
    )
    saved = env.store.proposals[ProposalId(result.resource_id)]
    assert result.branch_version == env.store.branch_version == 1
    assert (saved.source_session_id, saved.document_id) == (SESSION, DOCUMENT)
    assert env.store.transactions == 1
    with pytest.raises(Conflict):
        await env.create.create_from_agent(
            actor=Actor(ALICE),
            workspace_id=WORKSPACE,
            branch_id=BRANCH,
            expected_branch_version=0,
            edits=(DocumentEdit("", "Stale"),),
        )
    assert len(env.store.proposals) == 1


@pytest.mark.asyncio
async def test_agent_storage_failure_rolls_back_branch_advance(env: Harness) -> None:
    env.store.fail_save = True
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await env.create.create_from_agent(
            actor=Actor(ALICE),
            workspace_id=WORKSPACE,
            branch_id=BRANCH,
            expected_branch_version=0,
            edits=(DocumentEdit("", "Failed"),),
        )
    assert env.store.branch_version == 0
    assert env.store.proposals == {}


@pytest.mark.asyncio
async def test_detached_agent_branch_cannot_create_proposal(env: Harness) -> None:
    env.access.document_id = None
    with pytest.raises(InvalidInput, match="document"):
        await env.create.create_from_agent(
            actor=Actor(ALICE),
            workspace_id=WORKSPACE,
            branch_id=BRANCH,
            expected_branch_version=0,
            edits=(DocumentEdit("", "Detached"),),
        )
    assert env.store.proposals == {}
    assert env.store.branch_version == 0


@pytest.mark.asyncio
async def test_wrong_workspace_hides_proposal_from_all_commands(env: Harness) -> None:
    proposal_id = await env.initial()
    other = WorkspaceId(uuid4())
    with pytest.raises(NotFound):
        await env.read.execute(Actor(ALICE), other, proposal_id)
    with pytest.raises(NotFound):
        await env.revise.execute(
            Actor(ALICE),
            other,
            proposal_id,
            expected_version=1,
            edits=(DocumentEdit("", "Bad"),),
            bundle_ids=(),
            citations=(),
        )
    with pytest.raises(NotFound):
        await env.decide.execute(
            Actor(ALICE),
            other,
            proposal_id,
            expected_version=1,
            decision=ApprovalDecision.APPROVE,
        )
    assert env.store.proposals[proposal_id].version == 1


@pytest.mark.asyncio
async def test_reader_capability_joins_callers_transaction(env: Harness) -> None:
    proposal_id = await env.initial()
    async with env.store.transaction() as tx:
        view = await env.read.require_proposal(
            tx,
            actor=Actor(ALICE),
            workspace_id=WORKSPACE,
            proposal_id=proposal_id,
        )
        assert view.current_version.edits == (DocumentEdit("", "Proposed main"),)
        assert env.store.transactions == 2


@pytest.mark.asyncio
async def test_racing_revision_invalidates_old_version_decision(env: Harness) -> None:
    proposal_id = await env.initial()
    revised, decision = await asyncio.gather(
        env.revise.execute(
            Actor(ALICE),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            edits=(DocumentEdit("", "Next"),),
            bundle_ids=(),
            citations=(),
        ),
        env.decide.execute(
            Actor(BOB),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            decision=ApprovalDecision.APPROVE,
        ),
        return_exceptions=True,
    )
    assert not isinstance(revised, Exception)
    assert isinstance(decision, Conflict)
    assert env.store.proposals[proposal_id].version == 2
    assert env.store.proposals[proposal_id].approvals == ()


@pytest.mark.asyncio
async def test_racing_duplicate_decisions_store_only_one(env: Harness) -> None:
    proposal_id = await env.initial()
    results = await asyncio.gather(
        *(
            env.decide.execute(
                Actor(ALICE),
                WORKSPACE,
                proposal_id,
                expected_version=1,
                decision=ApprovalDecision.APPROVE,
            )
            for _ in range(2)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, Conflict) for result in results) == 1
    assert len(env.store.proposals[proposal_id].approvals) == 1


@pytest.mark.asyncio
async def test_failed_decision_and_revision_leave_saved_version_unchanged(
    env: Harness,
) -> None:
    proposal_id = await env.initial()
    original = env.store.proposals[proposal_id]
    env.store.fail_save = True
    with pytest.raises(RuntimeError):
        await env.decide.execute(
            Actor(ALICE),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            decision=ApprovalDecision.APPROVE,
        )
    with pytest.raises(RuntimeError):
        await env.revise.execute(
            Actor(ALICE),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            edits=(DocumentEdit("", "Failed"),),
            bundle_ids=(),
            citations=(),
        )
    assert env.store.proposals[proposal_id] == original


@pytest.mark.asyncio
async def test_prior_explicit_approver_loses_access_after_removal_in_revision(
    env: Harness,
) -> None:
    proposal_id = await env.initial(extras=frozenset({CAROL}))
    await env.revise.execute(
        Actor(ALICE),
        WORKSPACE,
        proposal_id,
        expected_version=1,
        edits=(DocumentEdit("", "Next"),),
        bundle_ids=(),
        citations=(),
        additional_approver_ids=frozenset(),
    )
    with pytest.raises(NotFound):
        await env.read.execute(Actor(CAROL), WORKSPACE, proposal_id)
    with pytest.raises(NotFound):
        await env.decide.execute(
            Actor(CAROL),
            WORKSPACE,
            proposal_id,
            expected_version=2,
            decision=ApprovalDecision.APPROVE,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "reader_capability", "revise", "decide"])
async def test_hidden_and_absent_proposals_have_identical_safe_errors(
    env: Harness,
    operation: str,
) -> None:
    proposal_id = await env.initial()
    original = dict(env.store.proposals)
    content_reads = (
        env.access.session_views,
        env.access.bundle_reads,
        env.access.document_reads,
    )
    errors: list[tuple[type[NotFound], str, str]] = []
    for target in (ProposalId(uuid4()), proposal_id):
        with pytest.raises(NotFound) as caught:
            if operation == "read":
                await env.read.execute(Actor(CAROL), WORKSPACE, target)
            elif operation == "reader_capability":
                async with env.store.transaction() as tx:
                    await env.read.require_proposal(
                        tx,
                        actor=Actor(CAROL),
                        workspace_id=WORKSPACE,
                        proposal_id=target,
                    )
            elif operation == "revise":
                await env.revise.execute(
                    Actor(CAROL),
                    WORKSPACE,
                    target,
                    expected_version=999,
                    edits=(DocumentEdit("", "Must not be saved"),),
                    bundle_ids=(BUNDLE,),
                    citations=(),
                )
            else:
                await env.decide.execute(
                    Actor(CAROL),
                    WORKSPACE,
                    target,
                    expected_version=999,
                    decision=ApprovalDecision.APPROVE,
                )
        errors.append((type(caught.value), caught.value.code, caught.value.message))
    assert (
        errors == [(ProposalNotFound, "proposal_not_found", "Proposal not found")] * 2
    )
    assert env.store.proposals == original
    assert (
        env.access.session_views,
        env.access.bundle_reads,
        env.access.document_reads,
    ) == content_reads


@pytest.mark.asyncio
async def test_known_source_viewer_permission_error_remains_forbidden(
    env: Harness,
) -> None:
    proposal_id = await env.initial()
    with pytest.raises(Forbidden) as caught:
        await env.revise.execute(
            Actor(DAN),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            edits=(DocumentEdit("", "Cannot edit"),),
            bundle_ids=(),
            citations=(),
        )
    assert (caught.value.code, caught.value.message) == (
        "session_forbidden",
        "Session access denied",
    )
    assert env.store.proposals[proposal_id].version == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "revise", "decide"])
async def test_workspace_forbidden_is_not_normalized_to_proposal_not_found(
    env: Harness,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    proposal_id = await env.initial()

    async def deny_workspace(
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership:
        raise Forbidden("workspace_forbidden", "Workspace access denied")

    monkeypatch.setattr(env.access, "require_member", deny_workspace)
    with pytest.raises(Forbidden) as caught:
        if operation == "read":
            await env.read.execute(Actor(ALICE), WORKSPACE, proposal_id)
        elif operation == "revise":
            await env.revise.execute(
                Actor(ALICE),
                WORKSPACE,
                proposal_id,
                expected_version=1,
                edits=(DocumentEdit("", "Denied"),),
                bundle_ids=(),
                citations=(),
            )
        else:
            await env.decide.execute(
                Actor(ALICE),
                WORKSPACE,
                proposal_id,
                expected_version=1,
                decision=ApprovalDecision.APPROVE,
            )
    assert type(caught.value) is Forbidden
    assert (caught.value.code, caught.value.message) == (
        "workspace_forbidden",
        "Workspace access denied",
    )
    assert env.store.proposals[proposal_id].version == 1
    assert env.store.proposals[proposal_id].approvals == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("save_fails", [False, True])
async def test_revision_reuses_authorized_source_and_recomputes_approvers(
    env: Harness,
    monkeypatch: pytest.MonkeyPatch,
    save_fails: bool,
) -> None:
    proposal_id = await env.initial()
    original = env.store.proposals[proposal_id]
    env.access.editors.add(DAN)
    env.store.fail_save = save_fails
    require = env.access.require
    calls = 0

    async def authorize_once(
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        permission: SessionPermission,
    ) -> SessionView:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise NotFound("session_not_found", "Session not found")
        return await require(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session_id=session_id,
            permission=permission,
        )

    monkeypatch.setattr(env.access, "require", authorize_once)
    if save_fails:
        with pytest.raises(RuntimeError, match="storage unavailable"):
            await env.revise.execute(
                Actor(ALICE),
                WORKSPACE,
                proposal_id,
                expected_version=1,
                edits=(DocumentEdit("", "Must roll back"),),
                bundle_ids=(),
                citations=(),
            )
        assert env.store.proposals[proposal_id] == original
    else:
        revised = await env.revise.execute(
            Actor(ALICE),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            edits=(DocumentEdit("", "Authorized revision"),),
            bundle_ids=(),
            citations=(),
        )
        assert revised.version == 2
        assert revised.current_version.required_approver_ids == frozenset(
            {ALICE, BOB, DAN}
        )
    assert calls == 1


@pytest.mark.asyncio
async def test_create_freezes_explicit_citations_in_supplied_order(
    env: Harness,
) -> None:
    result = await env.create.execute(
        Actor(ALICE),
        WORKSPACE,
        SESSION,
        document_id=DOCUMENT,
        edits=(DocumentEdit("", "Proposed main"),),
        bundle_ids=(BUNDLE,),
        citations=(
            ProposalCitation(BUNDLE, 1, "main"),
            ProposalCitation(BUNDLE, 0, "Proposed"),
        ),
    )
    saved = env.store.proposals[result.id].current_version
    assert tuple(
        (c.bundle_id, c.bundle_item_position, c.claim_anchor) for c in saved.citations
    ) == ((BUNDLE, 1, "main"), (BUNDLE, 0, "Proposed"))
    assert env.access.bundle_reads == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "revise"])
@pytest.mark.parametrize("invalid", ["out_of_range", "unlisted", "anchor", "duplicate"])
async def test_invalid_citation_leaves_saved_versions_unchanged(
    env: Harness, operation: str, invalid: str
) -> None:
    proposal_id = await env.initial()
    original = dict(env.store.proposals)
    citation = ProposalCitation(BUNDLE, 0, "main")
    if invalid == "out_of_range":
        citation = ProposalCitation(BUNDLE, 2, "main")
    elif invalid == "unlisted":
        citation = ProposalCitation(BundleId(uuid4()), 0, "main")
    elif invalid == "anchor":
        citation = ProposalCitation(BUNDLE, 0, "missing")
    citations = (citation, citation) if invalid == "duplicate" else (citation,)
    with pytest.raises(InvalidInput) as caught:
        if operation == "create":
            await env.create.execute(
                Actor(ALICE),
                WORKSPACE,
                SESSION,
                document_id=DOCUMENT,
                edits=(DocumentEdit("", "Proposed main"),),
                bundle_ids=(BUNDLE,),
                citations=citations,
            )
        else:
            await env.revise.execute(
                Actor(ALICE),
                WORKSPACE,
                proposal_id,
                expected_version=1,
                edits=(DocumentEdit("", "Proposed main"),),
                bundle_ids=(BUNDLE,),
                citations=citations,
            )
    assert caught.value.code == "proposal_citation_invalid"
    assert env.store.proposals == original


@pytest.mark.asyncio
async def test_revision_explicitly_replaces_citations_without_carrying_old_set(
    env: Harness,
) -> None:
    proposal_id = await env.initial()
    original = env.store.proposals[proposal_id].current_version
    revised = await env.revise.execute(
        Actor(ALICE),
        WORKSPACE,
        proposal_id,
        expected_version=1,
        edits=(DocumentEdit("", "Another main"),),
        bundle_ids=(BUNDLE,),
        citations=(ProposalCitation(BUNDLE, 1, "Another"),),
    )
    assert revised.current_version.citations == (
        ProposalCitation(BUNDLE, 1, "Another"),
    )
    cleared = await env.revise.execute(
        Actor(ALICE),
        WORKSPACE,
        proposal_id,
        expected_version=2,
        edits=(DocumentEdit("", "Another main"),),
        bundle_ids=(BUNDLE,),
        citations=(),
    )
    assert cleared.current_version.citations == ()
    assert env.store.proposals[proposal_id].versions[0] == original
    assert original.citations == (ProposalCitation(BUNDLE, 0, "main"),)


@pytest.mark.asyncio
async def test_revision_revalidates_access_to_previously_cited_bundle(
    env: Harness,
) -> None:
    proposal_id = await env.initial()
    original = env.store.proposals[proposal_id]
    env.access.bundle_ids.clear()
    with pytest.raises(NotFound):
        await env.revise.execute(
            Actor(ALICE),
            WORKSPACE,
            proposal_id,
            expected_version=1,
            edits=(DocumentEdit("", "Proposed main"),),
            bundle_ids=(BUNDLE,),
            citations=(ProposalCitation(BUNDLE, 0, "main"),),
        )
    assert env.store.proposals[proposal_id] == original


@pytest.mark.asyncio
@pytest.mark.parametrize("workspace_member", [False, True])
async def test_revision_normalizes_absent_and_private_proposals_with_real_authorizers(
    env: Harness, workspace_member: bool
) -> None:
    proposal_id = await env.initial()

    class Workspaces(WorkspaceMemory):
        def check(self, tx: TransactionContext) -> None:
            env.store.tx(tx)

    class Sessions(SessionMemory):
        def check(self, tx: TransactionContext) -> None:
            env.store.tx(tx)

    workspaces, sessions = Workspaces(), Sessions()
    sessions.sessions[WORKSPACE, SESSION] = Session(
        SESSION, WORKSPACE, DOCUMENT, ALICE, NOW
    )
    sessions.members[WORKSPACE, SESSION, ALICE] = SessionMember(
        WORKSPACE, SESSION, ALICE, SessionRole.OWNER
    )
    if workspace_member:
        workspaces.members[WORKSPACE, CAROL] = WorkspaceMembership(
            WORKSPACE, CAROL, WorkspaceRole.OWNER
        )
    members = WorkspaceAccess(workspaces)
    sources = ProposalSources(
        SessionAccess(sessions, members), env.access, env.access, env.access, members
    )
    revise = ReviseProposal(env.store, sources, lambda: env.store, FixedClock())
    outcomes = []
    for candidate in (ProposalId(uuid4()), proposal_id):
        with pytest.raises((Forbidden, NotFound)) as caught:
            await revise.execute(
                Actor(CAROL),
                WORKSPACE,
                candidate,
                expected_version=1,
                edits=(DocumentEdit("", "private revision"),),
                bundle_ids=(),
                citations=(),
            )
        outcomes.append((type(caught.value), caught.value.code))
    expected = (
        (ProposalNotFound, "proposal_not_found")
        if workspace_member
        else (WorkspaceForbidden, "workspace_forbidden")
    )
    assert outcomes == [expected, expected]
    assert env.store.proposals[proposal_id].version == 1
