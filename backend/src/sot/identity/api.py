from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from sot.bootstrap.settings import Settings
from sot.identity.application import AuthFacade, AuthResult
from sot.identity.contracts import Actor
from sot.identity.domain import AuthTokenInvalid, User
from sot.shared.ids import UserId

COOKIE = "sot_refresh"
AUTH_PATH = "/api/v1/auth"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: str = Field(min_length=1, repr=False)


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    email: str
    display_name: str

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(id=user.id, email=user.email, display_name=user.display_name)


class AuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse


async def resolve_actor(request: Request, facade: AuthFacade) -> Actor:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthTokenInvalid()
    return await facade.authenticate(token)


async def resolve_development_actor(
    request: Request, facade: AuthFacade, settings: Settings
) -> Actor:
    if settings.environment not in {"local", "test"} or not settings.development_auth:
        raise AuthTokenInvalid()
    try:
        actor = Actor(UserId(UUID(request.headers.get("x-sot-user", ""))))
        await facade.user(actor)
        return actor
    except ValueError:
        raise AuthTokenInvalid() from None


def build_auth_router(facade: AuthFacade, settings: Settings) -> APIRouter:
    router = APIRouter()

    async def actor(request: Request) -> Actor:
        if settings.development_auth and "authorization" not in request.headers:
            return await resolve_development_actor(request, facade, settings)
        return await resolve_actor(request, facade)

    def result_body(result: AuthResult, response: Response) -> AuthResponse:
        response.set_cookie(
            COOKIE,
            result.tokens.refresh_token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path=AUTH_PATH,
            max_age=settings.refresh_token_lifetime_seconds,
        )
        response.headers["Cache-Control"] = "no-store"
        return AuthResponse(
            access_token=result.tokens.access_token,
            user=UserResponse.from_user(result.user),
        )

    def clear_cookie(response: Response) -> None:
        response.delete_cookie(
            COOKIE,
            path=AUTH_PATH,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
        )

    @router.post(AUTH_PATH + "/google")
    async def google(body: LoginRequest, response: Response) -> AuthResponse:
        result = await facade.login(provider_name="google", credential=body.credential)
        return result_body(result, response)

    @router.post(AUTH_PATH + "/local")
    async def local(response: Response) -> AuthResponse:
        if settings.environment == "production" and settings.google_client_id:
            raise AuthTokenInvalid()
        result = await facade.login(provider_name="local", credential="Local")
        return result_body(result, response)

    @router.post(AUTH_PATH + "/refresh")
    async def refresh(request: Request, response: Response) -> AuthResponse:
        result = await facade.refresh(request.cookies.get(COOKIE, ""))
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
    async def me(current: Annotated[Actor, Depends(actor)]) -> UserResponse:
        return UserResponse.from_user(await facade.user(current))

    return router
