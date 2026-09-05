from sot.agent import build_agent, build_model
from sot.api import create_app
from sot.domain.service import SOTService
from sot.settings import Settings
from sot.store.memory import MemorySOTRepository

settings = Settings()
app = create_app(
    service=SOTService(MemorySOTRepository()),
    agent=build_agent(build_model(settings.models)),
    cors_origins=settings.cors_origins,
)

__all__ = ["app"]
