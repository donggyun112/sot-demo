from __future__ import annotations

from functools import cached_property
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic_ai import Agent
from pydantic_ai.ui.ag_ui import AGUIAdapter
from starlette.responses import Response
from starlette.types import Lifespan

from sot.domain.errors import DomainError
from sot.domain.models import (
    ApprovalResult,
    Branch,
    Cite,
    Document,
    DocumentView,
    NewTurn,
    Proposal,
    Revision,
    RevisionProvenance,
    Session,
    SessionDetail,
    SessionView,
    Toss,
    TossView,
    Turn,
)
from sot.domain.service import DEVELOPMENT_USERS, SOTService
from sot.legacy_agent import AgentDeps

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ServerOnlyAGUIAdapter(AGUIAdapter[AgentDeps, str]):
    """Use native AG-UI transport without trusting client-declared tools."""

    @cached_property
    def toolset(self) -> None:
        return None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CreateSessionRequest(StrictModel):
    title: NonEmptyText


class TurnInput(StrictModel):
    role: Literal["user", "assistant"]
    content: NonEmptyText


class AppendTurnsRequest(StrictModel):
    turns: tuple[TurnInput, ...] = Field(min_length=1)


class CreateCiteRequest(StrictModel):
    turn_ids: tuple[UUID, ...] = Field(min_length=1)
    summary: NonEmptyText


class CreateProposalRequest(StrictModel):
    content: NonEmptyText


class BootstrapResponse(StrictModel):
    users: tuple[str, ...]
    current_user: str
    documents: tuple[Document, ...]


class DocumentResponse(StrictModel):
    document: Document
    current_revision: Revision
    revisions: tuple[Revision, ...]
    sessions: tuple[Session, ...]
    provenance: RevisionProvenance | None


class SessionResponse(StrictModel):
    session: Session
    branches: tuple[Branch, ...]
    turns: tuple[Turn, ...]
    cites: tuple[Cite, ...]
    proposals: tuple[Proposal, ...]


class SessionCreatedResponse(StrictModel):
    session: Session
    branch: Branch


class TurnsResponse(StrictModel):
    turns: tuple[Turn, ...]


class CiteResponse(StrictModel):
    cite: Cite


class TossResponse(StrictModel):
    toss: Toss


class TossViewResponse(StrictModel):
    toss: Toss
    cite: Cite
    turns: tuple[Turn, ...]


class BranchResponse(StrictModel):
    branch: Branch


class ProposalResponse(StrictModel):
    proposal: Proposal


class ApprovalResponse(StrictModel):
    proposal: Proposal
    approver_ids: tuple[str, ...]
    revision: Revision | None


async def development_user(x_sot_user: str = Header(default="alice")) -> str:
    if x_sot_user not in DEVELOPMENT_USERS:
        raise DomainError("unknown_development_user", "Unknown user")
    return x_sot_user


def _domain_status(error: DomainError) -> int:
    if error.code in {"actor_unknown", "unknown_development_user"}:
        return 401
    if error.code.endswith("_not_found"):
        return 404
    if error.code.endswith("_forbidden"):
        return 403
    return 409


def create_app(
    *,
    service: SOTService,
    agent: Agent[AgentDeps, str],
    cors_origins: tuple[str, ...] = ("http://localhost:5173",),
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    application = FastAPI(title="SOT", lifespan=lifespan)
    application.state.service = service
    application.state.agent = agent
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(DomainError)
    async def domain_error_handler(
        _request: Request, error: DomainError
    ) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}},
            status_code=_domain_status(error),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed",
                }
            },
            status_code=422,
        )

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        return {"service": "sot", "status": "ready"}

    @application.get("/api/v1/bootstrap", response_model=BootstrapResponse)
    async def bootstrap(
        actor_id: Annotated[str, Depends(development_user)],
    ) -> BootstrapResponse:
        documents = await service.bootstrap(actor_id=actor_id)
        return BootstrapResponse(
            users=tuple(sorted(DEVELOPMENT_USERS)),
            current_user=actor_id,
            documents=documents,
        )

    @application.get("/api/v1/documents/{document_id}", response_model=DocumentResponse)
    async def get_document(
        document_id: UUID,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> DocumentView:
        return await service.document_view(document_id=document_id, actor_id=actor_id)

    @application.post(
        "/api/v1/documents/{document_id}/sessions",
        response_model=SessionCreatedResponse,
        status_code=201,
    )
    async def create_session(
        document_id: UUID,
        payload: CreateSessionRequest,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> SessionView:
        return await service.create_session(
            document_id=document_id, owner_id=actor_id, title=payload.title
        )

    @application.get("/api/v1/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(
        session_id: UUID,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> SessionDetail:
        return await service.session_detail(session_id=session_id, actor_id=actor_id)

    @application.post(
        "/api/v1/branches/{branch_id}/turns",
        response_model=TurnsResponse,
        status_code=201,
    )
    async def append_turns(
        branch_id: UUID,
        payload: AppendTurnsRequest,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> TurnsResponse:
        turns = await service.append_turns(
            branch_id=branch_id,
            actor_id=actor_id,
            turns=tuple(
                NewTurn(role=turn.role, content=turn.content) for turn in payload.turns
            ),
        )
        return TurnsResponse(turns=turns)

    @application.post(
        "/api/v1/branches/{branch_id}/cites",
        response_model=CiteResponse,
        status_code=201,
    )
    async def create_cite(
        branch_id: UUID,
        payload: CreateCiteRequest,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> CiteResponse:
        cite = await service.create_cite(
            branch_id=branch_id,
            actor_id=actor_id,
            turn_ids=payload.turn_ids,
            summary=payload.summary,
        )
        return CiteResponse(cite=cite)

    @application.post(
        "/api/v1/cites/{cite_id}/tosses",
        response_model=TossResponse,
        status_code=201,
    )
    async def create_toss(
        cite_id: UUID,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> TossResponse:
        toss = await service.create_toss(cite_id=cite_id, actor_id=actor_id)
        return TossResponse(toss=toss)

    @application.get("/api/v1/tosses/{token}", response_model=TossViewResponse)
    async def get_toss(token: str) -> TossView:
        return await service.toss_view(token=token)

    @application.post(
        "/api/v1/tosses/{token}/fork",
        response_model=BranchResponse,
        status_code=201,
    )
    async def fork_toss(
        token: str,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> BranchResponse:
        branch = await service.fork_toss(token=token, actor_id=actor_id)
        return BranchResponse(branch=branch)

    @application.post(
        "/api/v1/branches/{branch_id}/proposals",
        response_model=ProposalResponse,
        status_code=201,
    )
    async def create_proposal(
        branch_id: UUID,
        payload: CreateProposalRequest,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> ProposalResponse:
        proposal = await service.create_proposal(
            branch_id=branch_id, actor_id=actor_id, content=payload.content
        )
        return ProposalResponse(proposal=proposal)

    @application.post(
        "/api/v1/proposals/{proposal_id}/approve",
        response_model=ApprovalResponse,
    )
    async def approve_proposal(
        proposal_id: UUID,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> ApprovalResult:
        return await service.approve_proposal(
            proposal_id=proposal_id, actor_id=actor_id
        )

    @application.post(
        "/api/v1/branches/{branch_id}/agent",
        response_model=None,
    )
    async def run_agent(
        branch_id: UUID,
        request: Request,
        actor_id: Annotated[str, Depends(development_user)],
    ) -> Response:
        deps = AgentDeps(
            user_id=actor_id,
            branch_id=branch_id,
            service=service,
        )
        return await ServerOnlyAGUIAdapter.dispatch_request(
            request,
            agent=application.state.agent,
            deps=deps,
            manage_system_prompt="server",
        )

    return application


__all__ = ["DEVELOPMENT_USERS", "create_app", "development_user"]
