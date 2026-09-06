import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sot.identity.contracts import Actor
from sot.shared.ids import BundleId, WorkspaceId
from sot.sharing.application import (
    CreateShareLink,
    ForkSharedBundle,
    ReadPublicBundle,
    RevokeShareLink,
)
from sot.sharing.contracts import PublicBundleSnapshot

_TOKEN_PATH = re.compile(r"(/tosses/)[^/\s?\"']+")


def _redact_path(value: str) -> str:
    return _TOKEN_PATH.sub(r"\1[redacted]", value)


class TossLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_path(str(record.msg))
        # Keep Uvicorn's five structured arguments for its AccessFormatter.
        if isinstance(record.args, tuple):
            record.args = tuple(
                _redact_path(str(arg)) if _TOKEN_PATH.search(str(arg)) else arg
                for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_path(str(value))
                if _TOKEN_PATH.search(str(value))
                else value
                for key, value in record.args.items()
            }
        return True


def install_toss_log_redaction() -> None:
    for name in ("uvicorn.access", "uvicorn.error", "httpx"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, TossLogFilter) for item in logger.filters):
            logger.addFilter(TossLogFilter())


class TossSecurityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        routed_scope = dict(scope)
        if _TOKEN_PATH.search(path):
            # The server keeps the original scope for access/error logging;
            # routing receives a private copy containing the capability.
            scope["path"] = _redact_path(path)
            scope["raw_path"] = scope["path"].encode()
        public = path.startswith("/api/v1/tosses/") and scope["method"] == "GET"
        # The outer server-error handler sends 500 responses outside this middleware.
        scope["sot_no_store"] = public

        async def secured_send(message: Message) -> None:
            if public and message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"cache-control"
                ] + [(b"cache-control", b"private, no-store")]
            await send(message)

        await self.app(routed_scope, receive, secured_send)


class CreateTossRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_at: AwareDatetime | None = None


class CreatedTossResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    token: str


class PublicBundleItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ids: tuple[UUID, ...]
    role: Literal["user", "assistant"]
    content: str
    provenance: Literal["copied", "edited"]


class AttributionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    author_display_name: str
    published_at: datetime


class PublicBundleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle_id: UUID
    title: str
    items: tuple[PublicBundleItemResponse, ...]
    attribution: AttributionResponse

    @classmethod
    def from_snapshot(cls, value: PublicBundleSnapshot) -> "PublicBundleResponse":
        return cls(
            bundle_id=value.bundle_id,
            title=value.title,
            items=tuple(
                PublicBundleItemResponse(
                    source_ids=item.source_ids,
                    role=item.role,
                    content=item.content,
                    provenance=item.provenance,
                )
                for item in value.items
            ),
            attribution=AttributionResponse(
                title=value.attribution.title,
                author_display_name=value.attribution.author_display_name,
                published_at=value.attribution.published_at,
            ),
        )


class ForkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    branch_id: UUID


class ForkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def build_sharing_router(
    create: CreateShareLink,
    revoke: RevokeShareLink,
    read: ReadPublicBundle,
    fork: ForkSharedBundle,
    actor: Callable[[Request], Awaitable[Actor]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post(
        "/workspaces/{workspace_id}/bundles/{bundle_id}/tosses", status_code=201
    )
    async def create_toss(
        workspace_id: UUID,
        bundle_id: UUID,
        body: CreateTossRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> CreatedTossResponse:
        result = await create.execute(
            current,
            WorkspaceId(workspace_id),
            BundleId(bundle_id),
            expires_at=body.expires_at,
        )
        return CreatedTossResponse(id=result.link_id, token=result.raw_token)

    @router.delete("/workspaces/{workspace_id}/tosses/{toss_id}", status_code=204)
    async def revoke_toss(
        workspace_id: UUID, toss_id: UUID, current: Annotated[Actor, Depends(actor)]
    ) -> Response:
        await revoke.execute(current, WorkspaceId(workspace_id), toss_id)
        return Response(status_code=204)

    @router.get("/tosses/{token}")
    async def public_toss(token: str) -> PublicBundleResponse:
        return PublicBundleResponse.from_snapshot(await read.execute(token))

    @router.post("/workspaces/{workspace_id}/tosses/{token}/fork", status_code=201)
    async def fork_toss(
        workspace_id: UUID,
        token: str,
        body: ForkRequest,
        current: Annotated[Actor, Depends(actor)],
    ) -> ForkResponse:
        result = await fork.execute(current, WorkspaceId(workspace_id), raw_token=token)
        return ForkResponse(session_id=result.session_id, branch_id=result.branch_id)

    return router
