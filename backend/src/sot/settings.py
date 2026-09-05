from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SOT_", extra="ignore")

    database_url: str = "postgresql://sot:sot@localhost:54329/sot"
    models: tuple[str, ...] = ("test",)
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)


__all__ = ["Settings"]
