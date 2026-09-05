from typing import Literal

from fastapi.responses import JSONResponse
from service_auth import (
    AccessTokenVerifier,
    CredentialMissing,
    InvalidToken,
    KeySourceUnavailable,
)

from agent_core.auth.policy import (
    AgentAuthorizationError,
    AgentAuthPolicy,
    AgentScope,
    AuthenticatedAgentCaller,
)

PUBLIC_ERRORS: dict[str, tuple[int, str]] = {
    "invalid_token": (401, "Authentication failed"),
    "forbidden": (403, "Caller is not allowed"),
    "insufficient_scope": (403, "Required scope is missing"),
    "run_not_found": (404, "Run not found"),
    "auth_keys_unavailable": (
        503,
        "Authentication keys are temporarily unavailable",
    ),
}

type HiddenResourceReason = Literal["missing", "owner_mismatch"]


class AgentResourceHidden(Exception):
    def __init__(self, reason: HiddenResourceReason) -> None:
        super().__init__(reason)
        self.reason = reason


type HttpAuthError = (
    CredentialMissing
    | InvalidToken
    | KeySourceUnavailable
    | AgentAuthorizationError
    | AgentResourceHidden
)


class AgentAuthenticator:
    def __init__(
        self,
        verifier: AccessTokenVerifier,
        policy: AgentAuthPolicy,
    ) -> None:
        self._verifier = verifier
        self._policy = policy

    async def __call__(
        self,
        authorization: str | None,
        scope: AgentScope,
    ) -> AuthenticatedAgentCaller:
        token = extract_bearer(authorization)
        principal = await self._verifier.verify(token)
        return self._policy.authorize(principal, scope)


def extract_bearer(authorization: str | None) -> str:
    if authorization is None:
        raise CredentialMissing
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or "," in parts[1]:
        raise CredentialMissing
    return parts[1]


def auth_error_response(error: HttpAuthError) -> JSONResponse:
    headers: dict[str, str] = {}
    if isinstance(error, (CredentialMissing, InvalidToken)):
        code = "invalid_token"
        headers["WWW-Authenticate"] = 'Bearer error="invalid_token"'
    elif isinstance(error, KeySourceUnavailable):
        code = "auth_keys_unavailable"
        headers["Retry-After"] = "5"
    elif isinstance(error, AgentResourceHidden):
        code = "run_not_found"
    elif error.reason == "client_forbidden":
        code = "forbidden"
    else:
        code = "insufficient_scope"
        assert error.required_scope is not None
        headers["WWW-Authenticate"] = (
            f'Bearer error="insufficient_scope", scope="{error.required_scope}"'
        )

    status, message = PUBLIC_ERRORS[code]
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
        headers=headers,
    )
