from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool

from sot.api import create_app
from sot.bootstrap.database import PostgresUnitOfWork
from sot.bootstrap.errors import handle_sot_error, register_error_handlers
from sot.bootstrap.settings import Settings
from sot.document.api import build_document_router
from sot.document.application import DocumentAccess, GetDocument, GetRevision
from sot.document.postgres import PostgresDocumentRepository
from sot.domain.service import SOTService
from sot.identity.api import build_auth_router, resolve_actor, resolve_development_actor
from sot.identity.application import AuthFacade
from sot.identity.contracts import Actor
from sot.identity.postgres import PostgresIdentityRepository
from sot.identity.providers.base import AuthProvider, GoogleTokenVerifier
from sot.identity.providers.google import (
    GoogleAuthAdapter,
    ProductionGoogleTokenVerifier,
)
from sot.identity.tokens import SOTAccessTokenCodec
from sot.legacy_agent import build_agent, build_model
from sot.session.api import build_session_router
from sot.session.application import (
    ApplyCuration,
    BranchAccess,
    CreateBranch,
    CreateSession,
    GetSession,
    PreviewBundle,
    PublishBundle,
    SessionAccess,
)
from sot.session.postgres import PostgresSessionRepository
from sot.store.postgres import PostgresSOTRepository
from sot.workspace.api import build_workspace_router
from sot.workspace.application import (
    AddWorkspaceMember,
    CreateWorkspace,
    GetWorkspace,
    ListActorWorkspaces,
    WorkspaceAccess,
)
from sot.workspace.postgres import PostgresWorkspaceRepository


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


# Local/test imports remain usable without persistent auth configuration.
_LOCAL_TOKEN_SECRET = secrets.token_urlsafe(48)


def build_app(
    settings: Settings, *, google_token_verifier: GoogleTokenVerifier | None = None
) -> FastAPI:
    secret = settings.access_token_secret.get_secret_value()
    if settings.environment == "production" and (
        not secret or not settings.google_client_id
    ):
        raise ValueError("Production authentication configuration is required")
    clock = SystemClock()
    codec = SOTAccessTokenCodec(
        secret or _LOCAL_TOKEN_SECRET,
        clock,
        timedelta(seconds=settings.access_token_lifetime_seconds),
    )
    pool = AsyncConnectionPool(settings.database_url, open=False)
    uow_factory = lambda: PostgresUnitOfWork(pool)
    identity = PostgresIdentityRepository()
    providers: dict[str, AuthProvider] = {}
    if settings.google_client_id:
        providers["google"] = GoogleAuthAdapter(
            settings.google_client_id,
            google_token_verifier or ProductionGoogleTokenVerifier(),
        )
    facade = AuthFacade(
        providers,
        identity,
        uow_factory,
        codec,
        clock,
        timedelta(seconds=settings.refresh_token_lifetime_seconds),
    )
    workspace = PostgresWorkspaceRepository()
    access = WorkspaceAccess(workspace)

    async def actor(request: Request) -> Actor:
        if settings.development_auth and "authorization" not in request.headers:
            return await resolve_development_actor(request, facade, settings)
        return await resolve_actor(request, facade)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        await pool.open()
        try:
            application.state.pool = pool
            yield
        finally:
            await pool.close()

    if settings.environment in {"local", "test"} and settings.development_auth:
        application = create_app(
            service=SOTService(PostgresSOTRepository(pool)),
            agent=build_agent(build_model(settings.models)),
            cors_origins=settings.cors_origins,
            lifespan=lifespan,
        )
    else:
        application = FastAPI(title="SOT", lifespan=lifespan)
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @application.get("/healthz")
        async def health() -> dict[str, str]:
            return {"service": "sot", "status": "ready"}

    register_error_handlers(application)
    application.include_router(build_auth_router(facade, settings))
    application.include_router(
        build_workspace_router(
            CreateWorkspace(workspace, uow_factory),
            AddWorkspaceMember(workspace, access, facade, uow_factory),
            ListActorWorkspaces(workspace, uow_factory),
            GetWorkspace(workspace, access, uow_factory),
            actor,
        )
    )
    application.state.pool = pool
    documents = PostgresDocumentRepository()
    document_access = DocumentAccess(documents, access)
    sessions = PostgresSessionRepository()
    session_access = SessionAccess(sessions, access)
    branch_access = BranchAccess(sessions, session_access, access)
    application.include_router(
        build_document_router(
            GetDocument(document_access, uow_factory),
            GetRevision(documents, access, uow_factory),
            actor,
        )
    )
    application.include_router(
        build_session_router(
            CreateSession(sessions, access, document_access, uow_factory, clock),
            GetSession(session_access, uow_factory),
            CreateBranch(sessions, session_access, uow_factory, clock),
            ApplyCuration(sessions, sessions, branch_access, uow_factory, clock),
            PreviewBundle(sessions, branch_access, uow_factory),
            PublishBundle(
                sessions, sessions, sessions, branch_access, uow_factory, clock
            ),
            actor,
        )
    )
    return application


app = build_app(Settings())

__all__ = ["app", "build_app", "handle_sot_error"]
