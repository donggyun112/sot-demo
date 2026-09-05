from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_ai import Agent
from pydantic_ai.ui.ag_ui import AGUIAdapter
from starlette.responses import Response

from sot.agent import AgentDeps

DEVELOPMENT_USERS = frozenset({"alice", "bob"})


def create_app(
    *,
    service: object,
    agent: Agent[AgentDeps, str],
    cors_origins: tuple[str, ...] = ("http://localhost:5173",),
) -> FastAPI:
    application = FastAPI(title="SOT")
    application.state.service = service
    application.state.agent = agent
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        return {"service": "sot", "status": "ready"}

    @application.post(
        "/api/v1/branches/{branch_id}/agent",
        response_model=None,
    )
    async def run_agent(
        branch_id: UUID,
        request: Request,
        x_sot_user: str = Header(default="alice"),
    ) -> Response:
        if x_sot_user not in DEVELOPMENT_USERS:
            return JSONResponse(
                {
                    "error": {
                        "code": "unknown_development_user",
                        "message": "Unknown user",
                    }
                },
                status_code=401,
            )
        deps = AgentDeps(
            user_id=x_sot_user,
            branch_id=branch_id,
            service=application.state.service,
        )
        return await AGUIAdapter.dispatch_request(
            request,
            agent=application.state.agent,
            deps=deps,
            manage_system_prompt="server",
        )

    return application


__all__ = ["DEVELOPMENT_USERS", "create_app"]
