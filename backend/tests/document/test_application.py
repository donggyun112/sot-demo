from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sot.document.application import (
    CreateDocument,
    DocumentAccess,
    GetDocument,
    GetRevision,
    ListPassageGrounds,
    ListRevisions,
    PublishDocumentRevision,
    RenameDocument,
)
from sot.document.contracts import (
    DocumentSummary,
    DocumentView,
    PassageGround,
    RevisionCitationView,
    RevisionResult,
    RevisionSummary,
    RevisionView,
)
from sot.document.domain import (
    Document,
    DocumentNotFound,
    Revision,
    RevisionCitationInput,
)
from sot.identity.contracts import Actor
from sot.shared.ids import BundleId, DocumentId, ProposalId, UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext
from sot.workspace.domain import (
    Permission,
    WorkspaceForbidden,
    WorkspaceMembership,
    WorkspaceRole,
)

NOW = datetime(2026, 9, 6, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class MemoryDocuments:
    documents: dict[tuple[WorkspaceId, DocumentId], Document] = field(
        default_factory=dict
    )
    revisions: dict[tuple[WorkspaceId, DocumentId], list[Revision]] = field(
        default_factory=dict
    )
    active: object | None = None
    transactions: int = 0
    authorized: bool = False
    denied: bool = False
    permissions: list[Permission] = field(default_factory=list)
    lookups: list[tuple[WorkspaceId, DocumentId]] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    save_expected_versions: list[int] = field(default_factory=list)

    def check(self, tx: TransactionContext) -> None:
        assert self.active is tx

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransactionContext]:
        assert self.active is None, "nested transaction"
        self.active = object()
        self.transactions += 1
        try:
            yield self.active
        finally:
            self.active = None

    async def require(
        self,
        tx: TransactionContext,
        actor: Actor,
        workspace_id: WorkspaceId,
        permission: Permission,
    ) -> WorkspaceMembership:
        self.check(tx)
        self.events.append("authorize")
        if self.denied:
            raise WorkspaceForbidden()
        self.authorized = True
        self.permissions.append(permission)
        return WorkspaceMembership(workspace_id, actor.user_id, WorkspaceRole.OWNER)

    async def create(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
        revision: Revision,
    ) -> None:
        self.check(tx)
        assert self.authorized
        assert workspace_id == document.workspace_id == revision.workspace_id
        key = workspace_id, document.id
        self.documents[key] = document
        self.revisions[key] = [revision]

    async def load(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> Document | None:
        self.check(tx)
        assert self.authorized
        self.events.append("query")
        self.lookups.append((workspace_id, document_id))
        return self.documents.get((workspace_id, document_id))

    async def save_revision(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
        revision: Revision,
        *,
        expected_version: int,
    ) -> None:
        self.check(tx)
        assert self.authorized
        assert document.version == expected_version + 1
        self.save_expected_versions.append(expected_version)
        key = workspace_id, document.id
        assert key in self.documents
        self.documents[key] = document
        self.revisions[key].append(revision)

    async def save_title(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document: Document,
    ) -> None:
        self.check(tx)
        assert self.authorized
        self.events.append("save_title")
        key = workspace_id, document.id
        assert key in self.documents
        self.documents[key] = document

    async def list_revisions(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> tuple[RevisionSummary, ...]:
        self.check(tx)
        assert self.authorized
        self.events.append("query_revisions")
        self.lookups.append((workspace_id, document_id))
        return tuple(
            RevisionSummary(
                revision.id,
                revision.number,
                revision.proposal_id,
                revision.created_by,
                revision.created_at,
            )
            for revision in reversed(
                self.revisions.get((workspace_id, document_id), [])
            )
        )

    async def list_grounds(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> tuple[PassageGround, ...]:
        self.check(tx)
        assert self.authorized
        self.events.append("query_grounds")
        newest: dict[str, PassageGround] = {}
        for revision in self.revisions.get((workspace_id, document_id), []):
            for citation in revision.citations:
                newest[citation.claim_anchor] = PassageGround(
                    citation.claim_anchor,
                    citation.bundle_id,
                    citation.bundle_item_position,
                    revision.number,
                )
        return tuple(newest[key] for key in sorted(newest))

    async def get(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> DocumentView | None:
        self.check(tx)
        assert self.authorized
        self.events.append("query")
        self.lookups.append((workspace_id, document_id))
        document = self.documents.get((workspace_id, document_id))
        if document is None:
            return None
        revision = self.revisions[workspace_id, document_id][-1]
        return document_view(document, revision)

    async def get_revision(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        number: int,
    ) -> RevisionView | None:
        self.check(tx)
        assert self.authorized
        self.events.append("query_revision")
        self.lookups.append((workspace_id, document_id))
        for revision in self.revisions.get((workspace_id, document_id), []):
            if revision.number == number:
                return document_view(
                    self.documents[workspace_id, document_id], revision
                ).current_revision
        return None


def document_view(document: Document, revision: Revision) -> DocumentView:
    return DocumentView(
        document=DocumentSummary(
            id=document.id,
            workspace_id=document.workspace_id,
            title=document.title,
            current_revision_id=revision.id,
            version=document.version,
        ),
        current_revision=RevisionView(
            id=revision.id,
            workspace_id=revision.workspace_id,
            document_id=revision.document_id,
            number=revision.number,
            content=revision.content,
            proposal_id=revision.proposal_id,
            created_by=revision.created_by,
            created_at=revision.created_at,
            citations=tuple(
                RevisionCitationView(
                    item.claim_anchor, item.bundle_id, item.bundle_item_position
                )
                for item in revision.citations
            ),
        ),
    )


@pytest.mark.asyncio
async def test_create_document_authorizes_then_creates_revision_one_atomically() -> (
    None
):
    store = MemoryDocuments()
    actor, workspace_id = Actor(UserId(uuid4())), WorkspaceId(uuid4())

    result = await CreateDocument(store, store, lambda: store, FixedClock()).execute(
        actor, workspace_id, title=" Policy ", content="first"
    )

    assert isinstance(result, RevisionResult)
    assert result.document.title == "Policy"
    assert result.revision.number == 1
    assert result.revision.content == "first"
    assert result.document.current_revision_id == result.revision.id
    assert store.transactions == 1
    assert store.permissions == [Permission.DOCUMENT_CREATE]


@pytest.mark.asyncio
async def test_get_document_scopes_lookup_and_hides_another_workspace() -> None:
    store = MemoryDocuments()
    actor = Actor(UserId(uuid4()))
    source_workspace, routed_workspace = WorkspaceId(uuid4()), WorkspaceId(uuid4())
    created = await CreateDocument(store, store, lambda: store, FixedClock()).execute(
        actor, source_workspace, title="Policy", content="first"
    )
    store.authorized = False

    with pytest.raises(DocumentNotFound):
        await GetDocument(DocumentAccess(store, store), lambda: store).execute(
            actor, routed_workspace, created.document.id
        )

    assert store.lookups[-1] == (routed_workspace, created.document.id)
    assert store.permissions[-1] is Permission.DOCUMENT_READ
    assert store.events[-2:] == ["authorize", "query"]


@pytest.mark.asyncio
async def test_document_reader_denial_never_queries_the_document() -> None:
    store = MemoryDocuments(denied=True)
    actor, workspace_id = Actor(UserId(uuid4())), WorkspaceId(uuid4())
    reader = DocumentAccess(store, store)

    async with store.transaction() as tx:
        with pytest.raises(WorkspaceForbidden):
            await reader.require_document(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                document_id=DocumentId(uuid4()),
            )

    assert store.events == ["authorize"]
    assert store.lookups == []


@pytest.mark.asyncio
async def test_publish_joins_callers_transaction_and_requires_publish_permission() -> (
    None
):
    store = MemoryDocuments()
    actor, workspace_id = Actor(UserId(uuid4())), WorkspaceId(uuid4())
    created = await CreateDocument(store, store, lambda: store, FixedClock()).execute(
        actor, workspace_id, title="Policy", content="first"
    )
    store.authorized = False
    publisher = PublishDocumentRevision(store, store, FixedClock())

    async with store.transaction() as tx:
        result = await publisher.publish(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            document_id=created.document.id,
            expected_version=1,
            proposal_id=ProposalId(uuid4()),
            content="second",
            citations=(),
        )

    assert result.revision.number == 2
    assert result.document.version == 2
    assert store.transactions == 2
    assert store.permissions[-1] is Permission.DOCUMENT_PUBLISH
    assert store.save_expected_versions == [1]


@pytest.mark.asyncio
async def test_revision_read_authorizes_before_scoped_historical_lookup() -> None:
    store = MemoryDocuments()
    actor, workspace_id = Actor(UserId(uuid4())), WorkspaceId(uuid4())
    created = await CreateDocument(store, store, lambda: store, FixedClock()).execute(
        actor, workspace_id, title="Policy", content="first"
    )
    getter = GetRevision(store, store, lambda: store)
    result = await getter.execute(actor, workspace_id, created.document.id, 1)
    assert result.content == "first"
    assert store.events[-2:] == ["authorize", "query_revision"]
    assert store.permissions[-1] is Permission.DOCUMENT_READ
    for routed_workspace, number in ((WorkspaceId(uuid4()), 1), (workspace_id, 99)):
        with pytest.raises(DocumentNotFound):
            await getter.execute(actor, routed_workspace, created.document.id, number)
    store.events.clear()
    store.denied = True
    with pytest.raises(WorkspaceForbidden):
        await getter.execute(actor, workspace_id, created.document.id, 1)
    assert store.events == ["authorize"]


@pytest.mark.asyncio
async def test_a_document_can_be_renamed_without_touching_its_history() -> None:
    """A name is picked before anyone knows what the document will say."""
    store = MemoryDocuments()
    actor, workspace_id = Actor(UserId(uuid4())), WorkspaceId(uuid4())
    created = await CreateDocument(store, store, lambda: store, FixedClock()).execute(
        actor, workspace_id, title="Untitled", content="first"
    )
    rename = RenameDocument(store, store, lambda: store)

    renamed = await rename.execute(
        actor, workspace_id, created.document.id, title="  Rate limits  "
    )

    assert renamed.title == "Rate limits"
    assert renamed.version == created.document.version
    assert renamed.current_revision_id == created.revision.id
    assert store.permissions[-1] is Permission.DOCUMENT_CREATE
    assert len(store.revisions[workspace_id, created.document.id]) == 1


@pytest.mark.asyncio
async def test_renaming_another_workspaces_document_finds_nothing() -> None:
    store = MemoryDocuments()
    actor = Actor(UserId(uuid4()))
    source, routed = WorkspaceId(uuid4()), WorkspaceId(uuid4())
    created = await CreateDocument(store, store, lambda: store, FixedClock()).execute(
        actor, source, title="Policy", content="first"
    )

    with pytest.raises(DocumentNotFound):
        await RenameDocument(store, store, lambda: store).execute(
            actor, routed, created.document.id, title="Theirs"
        )

    assert store.documents[source, created.document.id].title == "Policy"


@pytest.mark.asyncio
async def test_history_authorizes_before_reading_and_runs_newest_first() -> None:
    store = MemoryDocuments()
    actor, workspace_id = Actor(UserId(uuid4())), WorkspaceId(uuid4())
    created = await CreateDocument(store, store, lambda: store, FixedClock()).execute(
        actor, workspace_id, title="Policy", content="first"
    )
    document = store.documents[workspace_id, created.document.id]
    async with store.transaction() as tx:
        await PublishDocumentRevision(store, store, FixedClock()).publish(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            document_id=document.id,
            expected_version=1,
            proposal_id=ProposalId(uuid4()),
            content="second",
            citations=(),
        )

    history = await ListRevisions(store, store, lambda: store).execute(
        actor, workspace_id, document.id
    )

    assert [item.number for item in history] == [2, 1]
    assert history[0].proposal_id is not None and history[1].proposal_id is None
    assert store.permissions[-1] is Permission.DOCUMENT_READ
    assert store.events[-2:] == ["authorize", "query_revisions"]


@pytest.mark.asyncio
async def test_history_denial_never_reads_the_revisions() -> None:
    store = MemoryDocuments(denied=True)
    actor, workspace_id = Actor(UserId(uuid4())), WorkspaceId(uuid4())

    with pytest.raises(WorkspaceForbidden):
        await ListRevisions(store, store, lambda: store).execute(
            actor, workspace_id, DocumentId(uuid4())
        )

    assert store.events == ["authorize"]


@pytest.mark.asyncio
async def test_grounds_follow_the_document_forward_not_just_its_last_update() -> None:
    """A revision only cites what THAT update wrote.

    A document is the sum of many updates, so a passage written two revisions
    ago and untouched since is still grounded by the conversation that wrote
    it. Reading only the current revision's citations left every earlier
    passage looking like nobody had decided it.
    """
    store = MemoryDocuments()
    actor, workspace_id = Actor(UserId(uuid4())), WorkspaceId(uuid4())
    created = await CreateDocument(store, store, lambda: store, FixedClock()).execute(
        actor, workspace_id, title="Policy", content="머리말"
    )
    document = store.documents[workspace_id, created.document.id]
    publish = PublishDocumentRevision(store, store, FixedClock())
    bundle, later = BundleId(uuid4()), BundleId(uuid4())
    async with store.transaction() as tx:
        await publish.publish(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            document_id=document.id,
            expected_version=1,
            proposal_id=ProposalId(uuid4()),
            content="머리말\n\n## 전달 방식\n헤더로.",
            citations=(RevisionCitationInput("## 전달 방식", bundle, 0),),
        )
    async with store.transaction() as tx:
        await publish.publish(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            document_id=document.id,
            expected_version=2,
            proposal_id=ProposalId(uuid4()),
            content="머리말\n\n## 전달 방식\n헤더로.\n\n## 감사\n남긴다.",
            citations=(RevisionCitationInput("## 감사", later, 0),),
        )

    grounds = await ListPassageGrounds(store, store, lambda: store).execute(
        actor, workspace_id, document.id
    )

    # Both passages are grounded, each by the update that wrote it.
    assert {(one.claim_anchor, one.revision_number) for one in grounds} == {
        ("## 전달 방식", 2),
        ("## 감사", 3),
    }
    assert {one.bundle_id for one in grounds} == {bundle, later}


@pytest.mark.asyncio
async def test_a_rewritten_passage_is_grounded_by_the_update_that_rewrote_it() -> None:
    store = MemoryDocuments()
    actor, workspace_id = Actor(UserId(uuid4())), WorkspaceId(uuid4())
    created = await CreateDocument(store, store, lambda: store, FixedClock()).execute(
        actor, workspace_id, title="Policy", content="머리말"
    )
    document = store.documents[workspace_id, created.document.id]
    publish = PublishDocumentRevision(store, store, FixedClock())
    first, second = BundleId(uuid4()), BundleId(uuid4())
    for version, bundle in ((1, first), (2, second)):
        async with store.transaction() as tx:
            await publish.publish(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                document_id=document.id,
                expected_version=version,
                proposal_id=ProposalId(uuid4()),
                content="머리말\n\n## 전달 방식\n다시 씀.",
                citations=(RevisionCitationInput("## 전달 방식", bundle, 0),),
            )

    grounds = await ListPassageGrounds(store, store, lambda: store).execute(
        actor, workspace_id, document.id
    )

    # The newer conversation supersedes the older one for that passage.
    assert len(grounds) == 1
    assert grounds[0].bundle_id == second
    assert grounds[0].revision_number == 3
