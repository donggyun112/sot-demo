from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from sot.consensus.application import (
    CreateProposal,
    DecideProposal,
    ListDocumentProposals,
    MergeProposal,
    ReadProposal,
    ReviseProposal,
)
from sot.consensus.contracts import MergeProposalResult, ProposalView
from sot.consensus.domain import (
    PROPOSAL_CONTENT_LIMIT,
    ApprovalDecision,
    DocumentEdit,
    ProposalStatus,
)
from sot.document.contracts import RevisionResult
from sot.identity.contracts import Actor
from sot.shared.ids import (
    BundleId,
    DocumentId,
    ProposalId,
    SessionId,
    UserId,
    WorkspaceId,
)


class DocumentEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # An empty `find` appends; anything else must name exactly one place in
    # the document, which the domain checks against the base revision.
    find: StrictStr = ""
    replace: Annotated[StrictStr, Field(max_length=PROPOSAL_CONTENT_LIMIT)]

    def to_edit(self) -> DocumentEdit:
        return DocumentEdit(self.find, self.replace)


class CreateProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_session_id: UUID
    # The branch the update was written in. Its conversation IS the grounds,
    # frozen when the proposal is made, so nothing is passed in here.
    branch_id: UUID
    edits: Annotated[list[DocumentEditRequest], Field(min_length=1)]
    additional_approver_ids: list[UUID] = Field(default_factory=list)


class ReviseProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[StrictInt, Field(ge=1)]
    branch_id: UUID
    edits: Annotated[list[DocumentEditRequest], Field(min_length=1)]
    additional_approver_ids: list[UUID] | None = None


class DecideProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[StrictInt, Field(ge=1)]
    decision: Literal["approve", "reject"]


class MergeProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[StrictInt, Field(ge=1)]


class CitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle_id: UUID
    bundle_item_position: int
    claim_anchor: str


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: UUID
    version: int
    approver_user_id: UUID
    decision: ApprovalDecision
    decided_at: datetime


class DocumentEditResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    find: str
    replace: str


class ProposalVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: UUID
    version: int
    base_revision_id: UUID
    edits: tuple[DocumentEditResponse, ...]
    required_approver_ids: tuple[UUID, ...]
    bundle_ids: tuple[UUID, ...]
    created_by: UUID
    created_at: datetime
    citations: tuple[CitationResponse, ...]
    additional_approver_ids: tuple[UUID, ...]


class ProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    document_id: UUID
    source_session_id: UUID
    created_by: UUID
    created_at: datetime
    version: int
    current_version: ProposalVersionResponse
    status: ProposalStatus
    approvals: tuple[ApprovalResponse, ...]

    @classmethod
    def from_view(cls, value: ProposalView) -> "ProposalResponse":
        v = value.current_version
        return cls(
            id=value.id,
            workspace_id=value.workspace_id,
            document_id=value.document_id,
            source_session_id=value.source_session_id,
            created_by=value.created_by,
            created_at=value.created_at,
            version=value.version,
            status=value.status,
            current_version=ProposalVersionResponse(
                proposal_id=v.proposal_id,
                version=v.version,
                base_revision_id=v.base_revision_id,
                edits=tuple(
                    DocumentEditResponse(find=e.find, replace=e.replace)
                    for e in v.edits
                ),
                required_approver_ids=tuple(sorted(v.required_approver_ids, key=str)),
                bundle_ids=v.bundle_ids,
                created_by=v.created_by,
                created_at=v.created_at,
                citations=tuple(
                    CitationResponse(
                        bundle_id=c.bundle_id,
                        bundle_item_position=c.bundle_item_position,
                        claim_anchor=c.claim_anchor,
                    )
                    for c in v.citations
                ),
                additional_approver_ids=tuple(
                    sorted(v.additional_approver_ids, key=str)
                ),
            ),
            approvals=tuple(
                ApprovalResponse(
                    proposal_id=a.proposal_id,
                    version=a.version,
                    approver_user_id=a.approver_user_id,
                    decision=a.decision,
                    decided_at=a.decided_at,
                )
                for a in value.approvals
            ),
        )


class PublishedDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    title: str
    current_revision_id: UUID
    version: int


class PublishedRevisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    document_id: UUID
    number: int
    content: str
    proposal_id: UUID | None
    created_by: UUID
    created_at: datetime
    citations: tuple[CitationResponse, ...]


class PublicationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: PublishedDocumentResponse
    revision: PublishedRevisionResponse

    @classmethod
    def from_result(cls, value: RevisionResult) -> "PublicationResponse":
        d, r = value.document, value.revision
        return cls(
            document=PublishedDocumentResponse(
                id=d.id,
                workspace_id=d.workspace_id,
                title=d.title,
                current_revision_id=d.current_revision_id,
                version=d.version,
            ),
            revision=PublishedRevisionResponse(
                id=r.id,
                workspace_id=r.workspace_id,
                document_id=r.document_id,
                number=r.number,
                content=r.content,
                proposal_id=r.proposal_id,
                created_by=r.created_by,
                created_at=r.created_at,
                citations=tuple(
                    CitationResponse(
                        bundle_id=c.bundle_id,
                        bundle_item_position=c.bundle_item_position,
                        claim_anchor=c.claim_anchor,
                    )
                    for c in r.citations
                ),
            ),
        )


class MergeProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: UUID
    version: int
    status: ProposalStatus
    publication: PublicationResponse | None

    @classmethod
    def from_result(cls, value: MergeProposalResult) -> "MergeProposalResponse":
        return cls(
            proposal_id=value.proposal_id,
            version=value.version,
            status=value.status,
            publication=PublicationResponse.from_result(value.publication)
            if value.publication
            else None,
        )


def build_consensus_router(
    create: CreateProposal,
    read: ReadProposal,
    revise: ReviseProposal,
    decide: DecideProposal,
    merge: MergeProposal,
    list_proposals: ListDocumentProposals,
    actor: Callable[[Request], Awaitable[Actor]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}")

    @router.get(
        "/documents/{document_id}/proposals", operation_id="list_document_proposals"
    )
    async def proposals_for_document(
        workspace_id: UUID,
        document_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> tuple[ProposalResponse, ...]:
        return tuple(
            ProposalResponse.from_view(item)
            for item in await list_proposals.execute(
                current, WorkspaceId(workspace_id), DocumentId(document_id)
            )
        )

    @router.post("/documents/{document_id}/proposals", status_code=201)
    async def create_proposal(
        workspace_id: UUID,
        document_id: UUID,
        body: CreateProposalRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> ProposalResponse:
        return ProposalResponse.from_view(
            await create.execute(
                current,
                WorkspaceId(workspace_id),
                SessionId(body.source_session_id),
                document_id=DocumentId(document_id),
                edits=tuple(edit.to_edit() for edit in body.edits),
                bundle_ids=tuple(BundleId(value) for value in body.bundle_ids),
                citations=tuple(value.to_citation() for value in body.citations),
                additional_approver_ids=frozenset(
                    UserId(value) for value in body.additional_approver_ids
                ),
            )
        )

    @router.get("/proposals/{proposal_id}")
    async def read_proposal(
        workspace_id: UUID, proposal_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> ProposalResponse:
        return ProposalResponse.from_view(
            await read.execute(
                current, WorkspaceId(workspace_id), ProposalId(proposal_id)
            )
        )

    @router.put("/proposals/{proposal_id}")
    async def revise_proposal(
        workspace_id: UUID,
        proposal_id: UUID,
        body: ReviseProposalRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> ProposalResponse:
        return ProposalResponse.from_view(
            await revise.execute(
                current,
                WorkspaceId(workspace_id),
                ProposalId(proposal_id),
                expected_version=body.expected_version,
                edits=tuple(edit.to_edit() for edit in body.edits),
                bundle_ids=tuple(BundleId(value) for value in body.bundle_ids),
                citations=tuple(value.to_citation() for value in body.citations),
                additional_approver_ids=frozenset(
                    UserId(value) for value in body.additional_approver_ids
                )
                if body.additional_approver_ids is not None
                else None,
            )
        )

    @router.post("/proposals/{proposal_id}/decisions")
    async def decide_proposal(
        workspace_id: UUID,
        proposal_id: UUID,
        body: DecideProposalRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> ProposalResponse:
        return ProposalResponse.from_view(
            await decide.execute(
                current,
                WorkspaceId(workspace_id),
                ProposalId(proposal_id),
                expected_version=body.expected_version,
                decision=ApprovalDecision(body.decision),
            )
        )

    @router.post("/proposals/{proposal_id}/merge")
    async def merge_proposal(
        workspace_id: UUID,
        proposal_id: UUID,
        body: MergeProposalRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> MergeProposalResponse:
        return MergeProposalResponse.from_result(
            await merge.execute(
                current,
                WorkspaceId(workspace_id),
                ProposalId(proposal_id),
                expected_version=body.expected_version,
            )
        )

    return router
