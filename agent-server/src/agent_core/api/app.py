from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Literal, Protocol, TypedDict, cast

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from service_auth import AuthenticationError

from agent_core.admission import RunInputAdmissionError
from agent_core.auth.http import AgentResourceHidden, HttpAuthError, auth_error_response
from agent_core.auth.policy import AgentAuthorizationError, AuthenticatedAgentCaller
from agent_core.command import CommandMappingError
from agent_core.store.postgres import (
    AgentRequestConflict,
    AgentRequestNotFound,
    StoredEvent,
)
from agent_core.supervisor import RunCapacityExceeded
from agent_core.tools import ToolSelectionError

MAX_REQUEST_BYTES = 2 * 1024 * 1024
type AgentScope = Literal["agent:run", "agent:abort"]
type Authenticate = Callable[
    [str | None, AgentScope], Awaitable[AuthenticatedAgentCaller]
]


class AgentHttpService(Protocol):
    async def submit(self, payload: bytes, caller: AuthenticatedAgentCaller) -> str: ...

    def stream(
        self,
        run_id: str,
        *,
        after_sequence: int,
    ) -> AsyncIterator[StoredEvent]: ...

    async def abort(
        self,
        run_id: str,
        caller: AuthenticatedAgentCaller,
    ) -> None: ...


class HealthResponse(TypedDict):
    service: Literal["agent-server"]
    status: Literal["ready"]


def _unavailable() -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": "service_unavailable",
                "message": "Agent is not configured",
            }
        },
        status_code=503,
        headers={"Retry-After": "5"},
    )


def _sse(event: StoredEvent) -> str:
    data = json.dumps(event.event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.sequence}\ndata: {data}\n\n"


def create_app(
    *,
    service: AgentHttpService | None = None,
    authenticate: Authenticate | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[Any]] | None = None,
) -> FastAPI:
    application = FastAPI(title="Agent Server", lifespan=lifespan)

    @application.exception_handler(AuthenticationError)
    async def authentication_error(
        _request: Request,
        error: AuthenticationError,
    ) -> JSONResponse:
        return auth_error_response(cast(HttpAuthError, error))

    @application.exception_handler(AgentAuthorizationError)
    async def authorization_error(
        _request: Request,
        error: AgentAuthorizationError,
    ) -> JSONResponse:
        return auth_error_response(error)

    @application.exception_handler(AgentRequestNotFound)
    async def request_not_found(
        _request: Request,
        _error: AgentRequestNotFound,
    ) -> JSONResponse:
        return auth_error_response(AgentResourceHidden("missing"))

    @application.exception_handler(AgentRequestConflict)
    async def request_conflict(
        _request: Request,
        _error: AgentRequestConflict,
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "idempotency_conflict",
                    "message": "Run payload conflicts",
                }
            },
            status_code=409,
        )

    @application.exception_handler(RunInputAdmissionError)
    async def admission_error(
        _request: Request,
        error: RunInputAdmissionError,
    ) -> JSONResponse:
        status = 400 if error.code == "invalid_json" else 422
        return JSONResponse(
            {"error": {"code": error.code, "path": list(error.path)}},
            status_code=status,
        )

    @application.exception_handler(RunCapacityExceeded)
    async def capacity_exceeded(
        _request: Request,
        _error: RunCapacityExceeded,
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "capacity_exceeded",
                    "message": "Agent execution capacity is full",
                }
            },
            status_code=503,
            headers={"Retry-After": "2"},
        )

    @application.exception_handler(CommandMappingError)
    async def command_error(
        _request: Request,
        error: CommandMappingError,
    ) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code, "path": list(error.path)}},
            status_code=422,
        )

    @application.exception_handler(ToolSelectionError)
    async def tool_error(
        _request: Request,
        error: ToolSelectionError,
    ) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code, "tool": error.tool_name}},
            status_code=422,
        )

    @application.get("/healthz")
    async def health() -> HealthResponse:
        return {"service": "agent-server", "status": "ready"}

    @application.post("/ag-ui", response_model=None)
    async def run_agent(
        request: Request,
        authorization: str | None = Header(default=None),
        last_event_id: str | None = Header(default=None),
    ) -> StreamingResponse | JSONResponse:
        if service is None or authenticate is None:
            return _unavailable()
        payload = await request.body()
        if len(payload) > MAX_REQUEST_BYTES:
            return JSONResponse(
                {
                    "error": {
                        "code": "request_too_large",
                        "message": "Request is too large",
                    }
                },
                status_code=413,
            )
        caller = await authenticate(authorization, "agent:run")
        run_id = await service.submit(payload, caller)
        try:
            after_sequence = int(last_event_id or "0")
            if after_sequence < 0:
                raise ValueError
        except ValueError:
            return JSONResponse(
                {
                    "error": {
                        "code": "invalid_cursor",
                        "message": "Invalid event cursor",
                    }
                },
                status_code=400,
            )

        async def events() -> AsyncIterator[str]:
            async for event in service.stream(run_id, after_sequence=after_sequence):
                yield _sse(event)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.post("/runs/{run_id}/abort", status_code=202)
    async def abort_run(
        run_id: str,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        if service is None or authenticate is None:
            return _unavailable()
        caller = await authenticate(authorization, "agent:abort")
        await service.abort(run_id, caller)
        return JSONResponse(
            {"runId": run_id, "status": "abort_requested"},
            status_code=202,
        )

    return application


app = create_app()
