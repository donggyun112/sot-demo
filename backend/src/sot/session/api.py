from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from sot.identity.contracts import Actor
from sot.session.application import (
    ApplyCuration,
    AttachToBranch,
    CreateBranch,
    CreateSession,
    ForkSession,
    GetSession,
    ImportSession,
    InviteSessionMember,
    ListBranchTurns,
    ListDocumentSessions,
    ListSessionBranches,
    ListSessionMembers,
    PreviewBundle,
    ReadCitedConversation,
)
from sot.session.contracts import (
    BranchMutationResult,
    CreatedSessionResult,
    SessionView,
)
from sot.session.domain import (
    ATTACHMENT_LIMIT,
    EXPORT_LIMIT,
    Attachment,
    Branch,
    BundleItem,
    CurationOperation,
    DropTurn,
    EditTurn,
    JoinTurns,
    RestoreTurn,
    SessionRole,
    SessionStatus,
)
from sot.shared.ids import (
    BranchId,
    BundleId,
    DocumentId,
    SessionId,
    UserId,
    WorkspaceId,
)


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


class RestoreTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["restore"]
    turn_id: UUID

    def to_operation(self) -> RestoreTurn:
        return RestoreTurn(self.turn_id)


class CurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[int, Field(ge=0, strict=True)]
    operation: Annotated[
        DropTurnRequest | EditTurnRequest | JoinTurnsRequest | RestoreTurnRequest,
        Field(discriminator="kind"),
    ]

    def to_operation(self) -> CurationOperation:
        return self.operation.to_operation()


class AttachedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: Annotated[str, Field(min_length=1, max_length=200)]
    content: Annotated[str, Field(min_length=1, max_length=ATTACHMENT_LIMIT)]


class AttachmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[int, Field(ge=0, strict=True)]
    # Someone picks several files and then sends. They arrive together or not
    # at all: one version check, one order, nothing half-attached to undo.
    files: Annotated[tuple[AttachedFile, ...], Field(min_length=1, max_length=10)]


class ImportSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # One file: the conversation as it came out of wherever it happened. A
    # copied transcript is words; an export also carries what its agent did,
    # which is most of a real session and is why the bound is the larger one.
    filename: Annotated[str, Field(min_length=1, max_length=200)]
    content: Annotated[str, Field(min_length=1, max_length=EXPORT_LIMIT)]


class ForkSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # A fork copies one branch: the conversation the forker was reading.
    branch_id: UUID


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
    forked_from_session_id: UUID | None = None
    forked_from_branch_id: UUID | None = None
    # Set when this conversation was imported from a file. SOT did not run
    # it, and a reader has to be able to tell that from one it did.
    imported_from: str | None = None

    @classmethod
    def from_session(cls, value: SessionView) -> "SessionResponse":
        return cls(
            id=value.id,
            workspace_id=value.workspace_id,
            document_id=value.document_id,
            created_by=value.created_by,
            created_at=value.created_at,
            status=value.status,
            forked_from_session_id=value.forked_from_session_id,
            forked_from_branch_id=value.forked_from_branch_id,
            imported_from=value.imported_from,
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


class TurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    workspace_id: UUID
    branch_id: UUID
    ordinal: int
    # `attachment` is a file someone brought in. Its content is the file's
    # name, a blank line, then the file, so a reader can be shown the file
    # rather than the hundred lines inside it.
    role: Literal["user", "assistant", "tool", "attachment"]
    content: str
    created_at: datetime
    created_by: UUID
    # A tool turn carries its whole record. It stays inside the session:
    # curation keeps every tool turn out of bundles, so none of it reaches
    # shared evidence.
    tool_kind: Literal["call", "return", "retry"] | None = None
    tool_call_id: str | None = None
    tool_payload: JsonValue | None = None


class CitedConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle_id: UUID
    title: str
    # The conversation to open. A citation that cannot be read back is not
    # evidence, it is an ordinal.
    session_id: UUID
    items: tuple["BundleItemResponse", ...]


class BundleItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ids: tuple[UUID, ...]
    role: Literal["user", "assistant", "tool"]
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


class SendSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    # An editor can keep working in it; a viewer can only read what is there.
    role: Literal["editor", "viewer"] = "editor"


class SessionMemberResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    session_id: UUID
    user_id: UUID
    role: SessionRole


def build_session_router(
    create_session: CreateSession,
    import_session: ImportSession,
    fork_session: ForkSession,
    get_session: GetSession,
    create_branch: CreateBranch,
    apply_curation: ApplyCuration,
    preview_bundle: PreviewBundle,
    list_sessions: ListDocumentSessions,
    list_branches: ListSessionBranches,
    list_turns: ListBranchTurns,
    attach_to_branch: AttachToBranch,
    read_cited: ReadCitedConversation,
    invite_member: InviteSessionMember,
    list_members: ListSessionMembers,
    actor: Callable[[Request], Awaitable[Actor]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}")

    @router.get(
        "/documents/{document_id}/sessions", operation_id="list_document_sessions"
    )
    async def sessions_for_document(
        workspace_id: UUID,
        document_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> tuple[SessionResponse, ...]:
        return tuple(
            SessionResponse.from_session(item)
            for item in await list_sessions.execute(
                current, WorkspaceId(workspace_id), DocumentId(document_id)
            )
        )

    @router.get("/sessions/{session_id}/branches", operation_id="list_session_branches")
    async def branches_for_session(
        workspace_id: UUID,
        session_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> tuple[BranchResponse, ...]:
        return tuple(
            BranchResponse.from_branch(item)
            for item in await list_branches.execute(
                current, WorkspaceId(workspace_id), SessionId(session_id)
            )
        )

    @router.post("/branches/{branch_id}/attachments", status_code=201)
    async def attach(
        workspace_id: UUID,
        branch_id: UUID,
        body: AttachmentRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> BranchMutationResponse:
        result = await attach_to_branch.execute(
            current,
            WorkspaceId(workspace_id),
            BranchId(branch_id),
            expected_version=body.expected_version,
            attachments=tuple(
                Attachment(file.filename, file.content) for file in body.files
            ),
        )
        return BranchMutationResponse(
            resource_id=result.turns[-1].id, branch_version=result.branch_version
        )

    @router.get("/branches/{branch_id}/turns", operation_id="list_branch_turns")
    async def turns_for_branch(
        workspace_id: UUID,
        branch_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> tuple[TurnResponse, ...]:
        return tuple(
            TurnResponse(
                id=entry.turn.id,
                workspace_id=entry.turn.workspace_id,
                branch_id=entry.turn.branch_id,
                ordinal=entry.turn.ordinal,
                role=entry.turn.role,
                content=entry.turn.content,
                created_at=entry.turn.created_at,
                created_by=entry.turn.created_by,
                tool_kind=entry.tool.kind if entry.tool else None,
                tool_call_id=entry.tool.call_id if entry.tool else None,
                tool_payload=entry.tool.payload if entry.tool else None,
            )
            for entry in await list_turns.execute(
                current, WorkspaceId(workspace_id), BranchId(branch_id)
            )
        )

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

    @router.post("/documents/{document_id}/imported-sessions", status_code=201)
    async def import_transcript(
        workspace_id: UUID,
        document_id: UUID,
        body: ImportSessionRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> CreatedSessionResponse:
        return CreatedSessionResponse.from_result(
            await import_session.execute(
                current,
                WorkspaceId(workspace_id),
                DocumentId(document_id),
                filename=body.filename,
                content=body.content,
            )
        )

    @router.post("/sessions/{session_id}/forks", status_code=201)
    async def fork(
        workspace_id: UUID,
        session_id: UUID,
        body: ForkSessionRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> CreatedSessionResponse:
        return CreatedSessionResponse.from_result(
            await fork_session.execute(
                current,
                WorkspaceId(workspace_id),
                SessionId(session_id),
                branch_id=BranchId(body.branch_id),
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

    @router.get("/sessions/{session_id}/members", operation_id="list_session_members")
    async def members_of_session(
        workspace_id: UUID,
        session_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> tuple[SessionMemberResponse, ...]:
        return tuple(
            SessionMemberResponse(
                workspace_id=item.workspace_id,
                session_id=item.session_id,
                user_id=item.user_id,
                role=item.role,
            )
            for item in await list_members.execute(
                current, WorkspaceId(workspace_id), SessionId(session_id)
            )
        )

    @router.post("/sessions/{session_id}/members", status_code=201)
    async def send_session(
        workspace_id: UUID,
        session_id: UUID,
        body: SendSessionRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> SessionMemberResponse:
        # Sending a session IS adding the recipient to it: they continue the
        # same conversation rather than receiving a copy of it.
        member = await invite_member.execute(
            current,
            WorkspaceId(workspace_id),
            SessionId(session_id),
            user_id=UserId(body.user_id),
            role=SessionRole(body.role),
        )
        return SessionMemberResponse(
            workspace_id=member.workspace_id,
            session_id=member.session_id,
            user_id=member.user_id,
            role=member.role,
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

    @router.get("/bundles/{bundle_id}", operation_id="read_cited_conversation")
    async def cited(
        workspace_id: UUID,
        bundle_id: UUID,
        current: Annotated[Actor, Depends(actor)],
    ) -> CitedConversationResponse:
        result = await read_cited.execute(
            current, WorkspaceId(workspace_id), BundleId(bundle_id)
        )
        return CitedConversationResponse(
            bundle_id=result.bundle_id,
            title=result.title,
            session_id=result.session_id,
            items=tuple(BundleItemResponse.from_item(item) for item in result.items),
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

    return router
