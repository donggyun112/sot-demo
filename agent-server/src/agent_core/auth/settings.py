from pydantic_settings import BaseSettings, SettingsConfigDict
from service_auth import VerificationProfile


class AgentAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_AUTH_")

    issuer: str
    audience: str
    jwks_uri: str
    allowed_algorithms: frozenset[str]
    allowed_client_ids: frozenset[str]

    def verification_profile(self) -> VerificationProfile:
        return VerificationProfile(
            issuer=self.issuer,
            audience=self.audience,
            jwks_uri=self.jwks_uri,
            allowed_algorithms=self.allowed_algorithms,
        )
