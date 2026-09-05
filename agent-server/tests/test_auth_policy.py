import base64
from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest
from service_auth import Principal

from agent_core.auth import AgentAuthorizationError, AgentAuthPolicy


def principal(scopes: frozenset[str] = frozenset({"agent:run"})) -> Principal:
    return Principal(
        "https://issuer.example",
        "opaque-user",
        "platform-web",
        scopes,
    )


def test_authorize_derives_only_trusted_agent_identity() -> None:
    policy = AgentAuthPolicy(frozenset({"platform-web"}))

    caller = policy.authorize(principal(), "agent:run")

    expected = sha256(b"https://issuer.example\x00opaque-user").digest()
    encoded = base64.urlsafe_b64encode(expected).rstrip(b"=").decode("ascii")
    assert caller.owner_issuer == "https://issuer.example"
    assert caller.owner_subject_hash == expected
    assert len(caller.owner_subject_hash) == 32
    assert caller.agent_subject == f"agtsub:v1:{encoded}"
    assert not hasattr(caller, "subject")


def test_authenticated_caller_is_immutable() -> None:
    policy = AgentAuthPolicy(frozenset({"platform-web"}))
    caller = policy.authorize(principal(), "agent:run")

    with pytest.raises(FrozenInstanceError):
        caller.owner_issuer = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("required_scope", ["agent:run", "agent:abort"])
def test_accepts_each_agent_scope_independently(required_scope: str) -> None:
    policy = AgentAuthPolicy(frozenset({"platform-web"}))
    authorized = principal(frozenset({required_scope}))

    caller = policy.authorize(authorized, required_scope)  # type: ignore[arg-type]

    assert caller.owner_issuer == "https://issuer.example"


def test_run_and_abort_scopes_are_independent() -> None:
    policy = AgentAuthPolicy(frozenset({"platform-web"}))

    with pytest.raises(AgentAuthorizationError, match="^scope_missing$") as caught:
        policy.authorize(principal(), "agent:abort")

    assert caught.value.reason == "scope_missing"
    assert caught.value.required_scope == "agent:abort"


def test_denied_client_fails_before_scope_policy() -> None:
    policy = AgentAuthPolicy(frozenset({"platform-service"}))

    with pytest.raises(AgentAuthorizationError, match="^client_forbidden$") as caught:
        policy.authorize(principal(frozenset()), "agent:run")

    assert caught.value.reason == "client_forbidden"
    assert caught.value.required_scope is None


def test_policy_rejects_empty_client_allow_list() -> None:
    with pytest.raises(ValueError, match="^allowed_client_ids must not be empty$"):
        AgentAuthPolicy(frozenset())
