from sot.agent import build_agent, build_model
from sot.api import create_app
from sot.settings import Settings

settings = Settings()
app = create_app(
    service=object(),
    agent=build_agent(build_model(settings.models)),
    cors_origins=settings.cors_origins,
)

__all__ = ["app"]
