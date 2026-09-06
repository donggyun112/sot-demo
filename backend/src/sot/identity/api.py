from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from sot.bootstrap.settings import Settings
from sot.identity.application import AuthFacade, AuthResult
from sot.identity.contracts import Actor
from sot.identity.domain import AuthTokenInvalid
from sot.shared.ids import UserId

COOKIE = "sot_refresh"
AUTH_PATH = "/api/v1/auth"


class LoginRequest(BaseModel):
    credential: str = Field(min_length=1, repr=False)


async def resolve_actor(request: Request, facade: AuthFacade) -> Actor:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Authentication failed")
    try:
        return await facade.authenticate(token)
    except AuthTokenInvalid:
        raise HTTPException(401, "Authentication failed") from None


async def resolve_development_actor(
    request: Request, facade: AuthFacade, settings: Settings
) -> Actor:
    if settings.environment not in {"local", "test"} or not settings.development_auth:
        raise HTTPException(401, "Authentication failed")
    try:
        actor = Actor(UserId(UUID(request.headers.get("x-sot-user", ""))))
        await facade.user(actor)
        return actor
    except (ValueError, AuthTokenInvalid):
        raise HTTPException(401, "Authentication failed") from None


def build_auth_router(facade: AuthFacade, settings: Settings) -> APIRouter:
    router = APIRouter()

    async def actor(request: Request) -> Actor:
        if settings.development_auth and "authorization" not in request.headers:
            return await resolve_development_actor(request, facade, settings)
        return await resolve_actor(request, facade)

    def result_body(result: AuthResult, response: Response) -> dict[str, object]:
        response.set_cookie(
            COOKIE,
            result.tokens.refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            path=AUTH_PATH,
            max_age=settings.refresh_token_lifetime_seconds,
        )
        response.headers["Cache-Control"] = "no-store"
        return {
            "access_token": result.tokens.access_token,
            "token_type": "bearer",
            "user": asdict(result.user),
        }

    def clear_cookie(response: Response) -> None:
        response.delete_cookie(
            COOKIE, path=AUTH_PATH, httponly=True, secure=True, samesite="lax"
        )

    @router.post(AUTH_PATH + "/google")
    async def google(body: LoginRequest, response: Response) -> dict[str, object]:
        try:
            result = await facade.login(
                provider_name="google", credential=body.credential
            )
        except AuthTokenInvalid:
            raise HTTPException(401, "Authentication failed") from None
        return result_body(result, response)

    @router.post(AUTH_PATH + "/refresh")
    async def refresh(request: Request, response: Response) -> dict[str, object]:
        try:
            result = await facade.refresh(request.cookies.get(COOKIE, ""))
        except AuthTokenInvalid:
            raise HTTPException(401, "Authentication failed") from None
        return result_body(result, response)

    @router.post(AUTH_PATH + "/logout", status_code=204)
    async def logout(request: Request, response: Response) -> None:
        await facade.logout(request.cookies.get(COOKIE, ""))
        clear_cookie(response)

    @router.post(AUTH_PATH + "/logout-all", status_code=204)
    async def logout_all(
        response: Response, current: Annotated[Actor, Depends(actor)]
    ) -> None:
        await facade.logout_all(current)
        clear_cookie(response)

    @router.get("/api/v1/me")
    async def me(current: Annotated[Actor, Depends(actor)]) -> dict[str, object]:
        return asdict(await facade.user(current))

    return router
