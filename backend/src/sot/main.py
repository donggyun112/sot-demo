from sot.bootstrap.app import build_app
from sot.bootstrap.settings import Settings

app = build_app(Settings())

__all__ = ["app", "build_app"]
