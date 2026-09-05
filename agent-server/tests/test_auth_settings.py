import pytest
from pydantic import ValidationError

from agent_core.auth import AgentAuthSettings

AUTH_ENV = {
    "AGENT_AUTH_ISSUER": "https://issuer.example",
    "AGENT_AUTH_AUDIENCE": "urn:agent:default",
    "AGENT_AUTH_JWKS_URI": "https://issuer.example/jwks",
    "AGENT_AUTH_ALLOWED_ALGORITHMS": '["RS256"]',
    "AGENT_AUTH_ALLOWED_CLIENT_IDS": '["platform-web"]',
}


def set_auth_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    values = {**AUTH_ENV, **overrides}
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_settings_build_common_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    set_auth_env(monkeypatch)

    settings = AgentAuthSettings()
    profile = settings.verification_profile()

    assert profile.issuer == "https://issuer.example"
    assert profile.audience == "urn:agent:default"
    assert profile.jwks_uri == "https://issuer.example/jwks"
    assert profile.allowed_algorithms == frozenset({"RS256"})
    assert settings.allowed_client_ids == frozenset({"platform-web"})


@pytest.mark.parametrize("missing", list(AUTH_ENV))
def test_every_auth_environment_variable_is_required(
    missing: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in AUTH_ENV.items():
        if name != missing:
            monkeypatch.setenv(name, value)
    monkeypatch.delenv(missing, raising=False)

    with pytest.raises(ValidationError):
        AgentAuthSettings()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"AGENT_AUTH_JWKS_URI": "http://issuer.example/jwks"}, "HTTPS jwks_uri"),
        ({"AGENT_AUTH_ALLOWED_ALGORITHMS": '["HS256"]'}, "allowed_algorithms"),
    ],
)
def test_unsafe_common_profile_configuration_fails_closed(
    overrides: dict[str, str],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_auth_env(monkeypatch, **overrides)
    settings = AgentAuthSettings()

    with pytest.raises(ValueError, match=message):
        settings.verification_profile()


def test_settings_have_no_provider_credential_or_token_field() -> None:
    assert set(AgentAuthSettings.model_fields) == {
        "issuer",
        "audience",
        "jwks_uri",
        "allowed_algorithms",
        "allowed_client_ids",
    }
