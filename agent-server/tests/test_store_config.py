from pytest import MonkeyPatch

from agent_core.store.config import AgentDatabaseSettings


def test_agent_database_settings_uses_independent_agent_environment(
    monkeypatch: MonkeyPatch,
) -> None:
    """Break caught: Agent persistence reads another service's DB environment."""
    monkeypatch.setenv("AGENT_DATABASE_URL", "postgresql://isolated:secret@db/agent")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://wrong:wrong@db/other")

    settings = AgentDatabaseSettings()

    assert settings.database_url == "postgresql://isolated:secret@db/agent"
