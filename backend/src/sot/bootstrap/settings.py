from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOT_", extra="ignore", populate_by_name=True
    )

    database_url: str = "postgresql://sot:sot@localhost:54329/sot"
    models: tuple[str, ...] = ("test",)
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    environment: Literal["local", "test", "production"] = "local"
    development_auth: bool = False
    google_client_id: str = ""
    access_token_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("SOT_JWT_SECRET", "SOT_ACCESS_TOKEN_SECRET"),
    )
    access_token_lifetime_seconds: int = 900
    refresh_token_lifetime_seconds: int = 2592000

    @model_validator(mode="after")
    def validate_auth(self) -> Settings:
        if self.environment == "production" and self.development_auth:
            raise ValueError("development authentication is forbidden in production")
        if (
            self.access_token_lifetime_seconds <= 0
            or self.refresh_token_lifetime_seconds <= 0
        ):
            raise ValueError("token lifetimes must be positive")
        return self


__all__ = ["Settings"]
