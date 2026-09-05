from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentDatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_")

    database_url: str = "postgresql://agent:agent@localhost:54330/agent"


__all__ = ["AgentDatabaseSettings"]
