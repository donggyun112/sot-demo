from base64 import urlsafe_b64encode
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from service_auth import Principal

type AgentScope = Literal["agent:run", "agent:abort"]
type AgentAuthorizationReason = Literal["client_forbidden", "scope_missing"]


class AgentAuthorizationError(Exception):
    def __init__(
        self,
        reason: AgentAuthorizationReason,
        required_scope: AgentScope | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.required_scope = required_scope


@dataclass(frozen=True, slots=True)
class AuthenticatedAgentCaller:
    owner_issuer: str
    owner_subject_hash: bytes
    agent_subject: str


class AgentAuthPolicy:
    def __init__(self, allowed_client_ids: frozenset[str]) -> None:
        if not allowed_client_ids:
            raise ValueError("allowed_client_ids must not be empty")
        self._allowed_client_ids = allowed_client_ids

    def authorize(
        self,
        principal: Principal,
        required_scope: AgentScope,
    ) -> AuthenticatedAgentCaller:
        if principal.client_id not in self._allowed_client_ids:
            raise AgentAuthorizationError("client_forbidden")
        if required_scope not in principal.scopes:
            raise AgentAuthorizationError("scope_missing", required_scope)

        owner_hash = sha256(
            principal.issuer.encode("utf-8")
            + b"\x00"
            + principal.subject.encode("utf-8")
        ).digest()
        encoded = urlsafe_b64encode(owner_hash).rstrip(b"=").decode("ascii")
        return AuthenticatedAgentCaller(
            owner_issuer=principal.issuer,
            owner_subject_hash=owner_hash,
            agent_subject=f"agtsub:v1:{encoded}",
        )
