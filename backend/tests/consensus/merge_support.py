"""Controlled transactional adapters; these do not model PostgreSQL row locking."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace

from sot.consensus.application import (
    CreateProposal,
    DecideProposal,
    MergeProposal,
    ProposalSources,
)
from sot.consensus.domain import ApprovalDecision, DocumentEdit, ProposalCitation
from sot.document.application import DocumentAccess, PublishDocumentRevision
from sot.document.contracts import DocumentView, RevisionView
from sot.document.domain import Document, Revision, VersionConflict
from sot.identity.contracts import Actor
from sot.shared.ids import DocumentId, ProposalId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.contracts import Permission, WorkspaceMembership, WorkspaceRole
from sot.workspace.domain import WorkspaceForbidden
from tests.consensus.test_application import (
    ALICE,
    BOB,
    BUNDLE,
    CAROL,
    DOCUMENT,
    NOW,
    SESSION,
    WORKSPACE,
    Capabilities,
    FixedClock,
    MemoryTransaction,
    Store,
)
from tests.document.test_application import document_view


@dataclass(kw_only=True)
class MergeTransaction(MemoryTransaction):
    document: Document
    revisions: list[Revision]


class MergeStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.document = Document(DOCUMENT, WORKSPACE, ALICE, "Document")
        self.revisions = [self.document.initialize("Main", ALICE, NOW)]
        self.commits = 0
        self.failure: str | None = None
        self.barrier: asyncio.Barrier | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[MergeTransaction]:
        if self.barrier is not None:
            await self.barrier.wait()
        async with self.lock:
            self.transactions += 1
            tx = MergeTransaction(
                proposals=dict(self.proposals),
                branch_version=self.branch_version,
                document=replace(self.document),
                revisions=list(self.revisions),
            )
            self.active = tx
            try:
                yield tx
                if self.failure == "commit":
                    raise RuntimeError("commit failed")
                self.proposals = tx.proposals
                self.branch_version = tx.branch_version
                self.document = tx.document
                self.revisions = tx.revisions
                self.commits += 1
            finally:
                self.active = None

    def tx(self, tx: TransactionContext) -> MergeTransaction:
        assert tx is self.active
        assert isinstance(tx, MergeTransaction)
        return tx


class MergeDocuments:
    def __init__(self, store: MergeStore) -> None:
        self.store = store

    async def load(
        self, tx: TransactionContext, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> Document | None:
        document = self.store.tx(tx).document
        return (
            document
            if (document.workspace_id, document.id) == (workspace_id, document_id)
            else None
        )

    async def create(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
        revision: Revision,
    ) -> None:
        raise AssertionError("Merge must never create a Document")

    async def save_revision(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
        revision: Revision,
        *,
        expected_version: int,
    ) -> None:
        context = self.store.tx(tx)
        assert (workspace_id, document.id, revision.document_id) == (
            WORKSPACE,
            DOCUMENT,
            DOCUMENT,
        )
        if self.store.failure == "conflict" or (
            context.revisions[-1].number != expected_version
        ):
            raise VersionConflict()
        context.document = document
        context.revisions.append(revision)
        if self.store.failure == "revision":
            raise RuntimeError("revision storage failed")

    async def get(
        self, tx: TransactionContext, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> DocumentView | None:
        document = await self.load(tx, workspace_id, document_id)
        if document is None:
            return None
        return document_view(document, self.store.tx(tx).revisions[-1])

    async def get_revision(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        number: int,
    ) -> RevisionView | None:
        document = await self.load(tx, workspace_id, document_id)
        if document is None:
            return None
        for revision in self.store.tx(tx).revisions:
            if revision.number == number:
                return document_view(document, revision).current_revision
        return None


class PublicationAccess:
    def __init__(self, access: Capabilities) -> None:
        self.access = access

    async def require(
        self,
        tx: TransactionContext,
        actor: Actor,
        workspace_id: WorkspaceId,
        permission: Permission,
    ) -> WorkspaceMembership:
        await self.access.require_member(tx, workspace_id, actor.user_id)
        if permission is Permission.DOCUMENT_PUBLISH and actor.user_id != CAROL:
            raise WorkspaceForbidden()
        return WorkspaceMembership(
            workspace_id,
            actor.user_id,
            WorkspaceRole.OWNER if actor.user_id == CAROL else WorkspaceRole.MEMBER,
        )


class MergeHarness:
    def __init__(self) -> None:
        self.store = MergeStore()
        self.access = Capabilities(self.store)
        self.authorizer = PublicationAccess(self.access)
        documents = MergeDocuments(self.store)
        self.documents = DocumentAccess(documents, self.authorizer)
        self.publisher = PublishDocumentRevision(
            documents, self.authorizer, FixedClock()
        )
        sources = ProposalSources(
            self.access, self.documents, self.access, self.access, self.access
        )
        self.create = CreateProposal(
            self.store,
            sources,
            self.access,
            self.access,
            lambda: self.store,
            FixedClock(),
        )
        self.decide = DecideProposal(
            self.store, self.access, lambda: self.store, FixedClock()
        )
        self.merge = MergeProposal(
            self.store,
            self.authorizer,
            self.documents,
            self.publisher,
            lambda: self.store,
        )

    async def initial(self, *, approve: bool = True) -> ProposalId:
        proposal = await self.create.execute(
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
        if approve:
            for actor_id in (ALICE, BOB):
                await self.decide.execute(
                    Actor(actor_id),
                    WORKSPACE,
                    proposal.id,
                    expected_version=1,
                    decision=ApprovalDecision.APPROVE,
                )
        return proposal.id
