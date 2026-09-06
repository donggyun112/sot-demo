from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from sot.identity.contracts import Actor
from sot.session.application import (
    ApplyCuration,
    CreateBranch,
    CreateSession,
    GetSession,
    PreviewBundle,
    PublishBundle,
)
from sot.session.contracts import BranchMutationResult, CreatedSessionResult
from sot.session.domain import (
    Branch,
    BundleItem,
    CurationOperation,
    DropTurn,
    EditTurn,
    JoinTurns,
    Session,
    SessionStatus,
)
from sot.shared.ids import BranchId, DocumentId, SessionId, WorkspaceId


class EmptySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DropTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["drop"]
    turn_id: UUID

    def to_operation(self) -> DropTurn:
        return DropTurn(self.turn_id)


class EditTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["edit"]
    turn_id: UUID
    content: str

    def to_operation(self) -> EditTurn:
        return EditTurn(self.turn_id, self.content)


class JoinTurnsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["join"]
    turn_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    content: str

    def to_operation(self) -> JoinTurns:
        return JoinTurns(self.turn_ids, self.content)


class CurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[int, Field(ge=0, strict=True)]
    operation: Annotated[
        DropTurnRequest | EditTurnRequest | JoinTurnsRequest,
        Field(discriminator="kind"),
    ]

    def to_operation(self) -> CurationOperation:
        return self.operation.to_operation()


class PublishBundleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[int, Field(ge=0, strict=True)]
    title: str


class CreatedSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    branch_id: UUID

    @classmethod
    def from_result(cls, value: CreatedSessionResult) -> "CreatedSessionResponse":
        return cls(session_id=value.session_id, branch_id=value.branch_id)


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    document_id: UUID | None
    created_by: UUID
    created_at: datetime
    status: SessionStatus

    @classmethod
    def from_session(cls, value: Session) -> "SessionResponse":
        return cls(
            id=value.id,
            workspace_id=value.workspace_id,
            document_id=value.document_id,
            created_by=value.created_by,
            created_at=value.created_at,
            status=value.status,
        )


class BranchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    session_id: UUID
    created_by: UUID
    created_at: datetime
    version: int

    @classmethod
    def from_branch(cls, value: Branch) -> "BranchResponse":
        return cls(
            id=value.id,
            workspace_id=value.workspace_id,
            session_id=value.session_id,
            created_by=value.created_by,
            created_at=value.created_at,
            version=value.version,
        )


class BranchMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: UUID
    branch_version: int

    @classmethod
    def from_result(cls, value: BranchMutationResult) -> "BranchMutationResponse":
        return cls(resource_id=value.resource_id, branch_version=value.branch_version)


class BundleItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ids: tuple[UUID, ...]
    role: Literal["user", "assistant"]
    content: str
    provenance: Literal["copied", "edited"]

    @classmethod
    def from_item(cls, value: BundleItem) -> "BundleItemResponse":
        return cls(
            source_ids=value.source_ids,
            role=value.role,
            content=value.content,
            provenance=value.provenance,
        )


def build_session_router(
    create_session: CreateSession,
    get_session: GetSession,
    create_branch: CreateBranch,
    apply_curation: ApplyCuration,
    preview_bundle: PreviewBundle,
    publish_bundle: PublishBundle,
    actor: Callable[[Request], Awaitable[Actor]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}")

    @router.post("/documents/{document_id}/sessions", status_code=201)
    async def create(
        workspace_id: UUID,
        document_id: UUID,
        body: EmptySessionRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> CreatedSessionResponse:
        return CreatedSessionResponse.from_result(
            await create_session.execute(
                current, WorkspaceId(workspace_id), DocumentId(document_id)
            )
        )

    @router.get("/sessions/{session_id}")
    async def get(
        workspace_id: UUID,
        session_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> SessionResponse:
        return SessionResponse.from_session(
            await get_session.execute(
                current, WorkspaceId(workspace_id), SessionId(session_id)
            )
        )

    @router.post("/sessions/{session_id}/branches", status_code=201)
    async def branch(
        workspace_id: UUID,
        session_id: UUID,
        body: EmptySessionRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> BranchResponse:
        return BranchResponse.from_branch(
            await create_branch.execute(
                current, WorkspaceId(workspace_id), SessionId(session_id)
            )
        )

    @router.post("/branches/{branch_id}/curation-ops", status_code=201)
    async def curate(
        workspace_id: UUID,
        branch_id: UUID,
        body: CurationRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> BranchMutationResponse:
        return BranchMutationResponse.from_result(
            await apply_curation.execute(
                current,
                WorkspaceId(workspace_id),
                BranchId(branch_id),
                expected_version=body.expected_version,
                operation=body.to_operation(),
            )
        )

    @router.get("/branches/{branch_id}/bundle-preview")
    async def preview(
        workspace_id: UUID,
        branch_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> tuple[BundleItemResponse, ...]:
        return tuple(
            BundleItemResponse.from_item(item)
            for item in await preview_bundle.execute(
                current, WorkspaceId(workspace_id), BranchId(branch_id)
            )
        )

    @router.post("/branches/{branch_id}/bundles", status_code=201)
    async def publish(
        workspace_id: UUID,
        branch_id: UUID,
        body: PublishBundleRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> BranchMutationResponse:
        return BranchMutationResponse.from_result(
            await publish_bundle.execute(
                current,
                WorkspaceId(workspace_id),
                BranchId(branch_id),
                expected_version=body.expected_version,
                title=body.title,
            )
        )

    return router
