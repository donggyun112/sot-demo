from __future__ import annotations

from sot.document.contracts import (
    DocumentReader,
    DocumentSummary,
    DocumentView,
    RevisionCitationInput,
    RevisionCitationView,
    RevisionResult,
    RevisionView,
)
from sot.document.domain import Document, DocumentNotFound, Revision
from sot.document.ports import (
    DocumentPublicationQuery,
    DocumentQuery,
    DocumentRepository,
)
from sot.identity.contracts import Actor
from sot.shared.clock import Clock
from sot.shared.ids import DocumentId, ProposalId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext, UnitOfWorkFactory
from sot.workspace.contracts import Permission, WorkspaceAuthorizer


def _summary(document: Document) -> DocumentSummary:
    if document.current_revision_id is None:
        raise DocumentNotFound()
    return DocumentSummary(
        id=document.id,
        workspace_id=document.workspace_id,
        title=document.title,
        current_revision_id=document.current_revision_id,
        version=document.version,
    )


def _revision_view(revision: Revision) -> RevisionView:
    return RevisionView(
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
    )


def _result(document: Document, revision: Revision) -> RevisionResult:
    return RevisionResult(_summary(document), _revision_view(revision))


class DocumentAccess(DocumentReader):
    def __init__(self, query: DocumentQuery, authorizer: WorkspaceAuthorizer) -> None:
        self._query = query
        self._authorizer = authorizer

    async def require_document(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> DocumentView:
        await self._authorizer.require(
            tx, actor, workspace_id, Permission.DOCUMENT_READ
        )
        result = await self._query.get(tx, workspace_id, document_id)
        if result is None or result.document.workspace_id != workspace_id:
            raise DocumentNotFound()
        return result


class DocumentPublicationAccess:
    """DocumentReader for publication; holds current main stable in caller tx."""

    def __init__(
        self, query: DocumentPublicationQuery, authorizer: WorkspaceAuthorizer
    ) -> None:
        self._query = query
        self._authorizer = authorizer

    async def require_document(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
    ) -> DocumentView:
        await self._authorizer.require(
            tx, actor, workspace_id, Permission.DOCUMENT_PUBLISH
        )
        result = await self._query.get_for_update(tx, workspace_id, document_id)
        if result is None or result.document.workspace_id != workspace_id:
            raise DocumentNotFound()
        return result


class CreateDocument:
    def __init__(
        self,
        repository: DocumentRepository,
        authorizer: WorkspaceAuthorizer,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        *,
        title: str,
        content: str,
    ) -> RevisionResult:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.DOCUMENT_CREATE
            )
            document = Document.create(workspace_id, actor.user_id, title)
            revision = document.initialize(content, actor.user_id, self._clock.now())
            await self._repository.create(tx, workspace_id, document, revision)
            return _result(document, revision)


class GetDocument:
    def __init__(
        self,
        reader: DocumentReader,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._reader = reader
        self._uow_factory = uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> DocumentView:
        async with self._uow_factory().transaction() as tx:
            return await self._reader.require_document(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                document_id=document_id,
            )


class GetRevision:
    def __init__(
        self,
        query: DocumentQuery,
        authorizer: WorkspaceAuthorizer,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._query = query
        self._authorizer = authorizer
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        number: int,
    ) -> RevisionView:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.DOCUMENT_READ
            )
            result = await self._query.get_revision(
                tx, workspace_id, document_id, number
            )
            if result is None or (
                result.workspace_id,
                result.document_id,
                result.number,
            ) != (workspace_id, document_id, number):
                raise DocumentNotFound()
            return result


class PublishDocumentRevision:
    """Publish inside the transaction owned by the caller."""

    def __init__(
        self,
        repository: DocumentRepository,
        authorizer: WorkspaceAuthorizer,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._clock = clock

    async def publish(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        document_id: DocumentId,
        expected_version: int,
        proposal_id: ProposalId,
        content: str,
        citations: tuple[RevisionCitationInput, ...],
    ) -> RevisionResult:
        await self._authorizer.require(
            tx, actor, workspace_id, Permission.DOCUMENT_PUBLISH
        )
        document = await self._repository.load(tx, workspace_id, document_id)
        if document is None or document.workspace_id != workspace_id:
            raise DocumentNotFound()
        revision = document.publish(
            content=content,
            proposal_id=proposal_id,
            citations=citations,
            actor_id=actor.user_id,
            expected_version=expected_version,
            now=self._clock.now(),
        )
        await self._repository.save_revision(
            tx,
            workspace_id,
            document,
            revision,
            expected_version=expected_version,
        )
        return _result(document, revision)


__all__ = [
    "CreateDocument",
    "DocumentAccess",
    "DocumentPublicationAccess",
    "GetDocument",
    "GetRevision",
    "PublishDocumentRevision",
]
