from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict

from sot.document.application import GetDocument, GetRevision, ListDocuments
from sot.document.contracts import DocumentSummary, DocumentView, RevisionView
from sot.identity.contracts import Actor
from sot.shared.ids import DocumentId, WorkspaceId


class DocumentSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    title: str
    current_revision_id: UUID
    version: int

    @classmethod
    def from_summary(cls, value: DocumentSummary) -> "DocumentSummaryResponse":
        return cls(
            id=value.id,
            workspace_id=value.workspace_id,
            title=value.title,
            current_revision_id=value.current_revision_id,
            version=value.version,
        )


class RevisionCitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_anchor: str
    bundle_id: UUID
    bundle_item_position: int


class RevisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    document_id: UUID
    number: int
    content: str
    proposal_id: UUID | None
    created_by: UUID
    created_at: datetime
    citations: tuple[RevisionCitationResponse, ...]

    @classmethod
    def from_revision(cls, value: RevisionView) -> "RevisionResponse":
        return cls(
            id=value.id,
            workspace_id=value.workspace_id,
            document_id=value.document_id,
            number=value.number,
            content=value.content,
            proposal_id=value.proposal_id,
            created_by=value.created_by,
            created_at=value.created_at,
            citations=tuple(
                RevisionCitationResponse(
                    claim_anchor=item.claim_anchor,
                    bundle_id=item.bundle_id,
                    bundle_item_position=item.bundle_item_position,
                )
                for item in value.citations
            ),
        )


class DocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: DocumentSummaryResponse
    current_revision: RevisionResponse

    @classmethod
    def from_view(cls, value: DocumentView) -> "DocumentResponse":
        return cls(
            document=DocumentSummaryResponse.from_summary(value.document),
            current_revision=RevisionResponse.from_revision(value.current_revision),
        )


def build_document_router(
    get_document: GetDocument,
    get_revision: GetRevision,
    list_documents: ListDocuments,
    actor: Callable[[Request], Awaitable[Actor]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/documents")

    @router.get("", operation_id="list_workspace_documents")
    async def list_for_workspace(
        workspace_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> tuple[DocumentSummaryResponse, ...]:
        return tuple(
            DocumentSummaryResponse.from_summary(item)
            for item in await list_documents.execute(current, WorkspaceId(workspace_id))
        )

    @router.get("/{document_id}")
    async def get(
        workspace_id: UUID,
        document_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> DocumentResponse:
        return DocumentResponse.from_view(
            await get_document.execute(
                current, WorkspaceId(workspace_id), DocumentId(document_id)
            )
        )

    @router.get("/{document_id}/revisions/{number}")
    async def revision(
        workspace_id: UUID,
        document_id: UUID,
        number: Annotated[int, Path(ge=1)],
        current: Annotated[Actor, Depends(actor)],
    ) -> RevisionResponse:
        return RevisionResponse.from_revision(
            await get_revision.execute(
                current, WorkspaceId(workspace_id), DocumentId(document_id), number
            )
        )

    return router
