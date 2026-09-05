import tomllib
from pathlib import Path

from pydantic_ai import (
    Agent,
    CancellationToken,
    DeferredToolRequests,
    DeferredToolResults,
)
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.ui.ag_ui import AGUIEventStream


def test_deployed_pydantic_ai_exposes_agent_server_contract() -> None:
    assert Agent is not None
    assert DeferredToolRequests is not None
    assert DeferredToolResults is not None
    assert CancellationToken is not None
    assert FallbackModel is not None
    assert AGUIEventStream is not None

    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    pydantic_dependencies = [
        dependency
        for dependency in project["project"]["dependencies"]
        if dependency.startswith("pydantic-ai-slim")
    ]
    assert pydantic_dependencies == [
        "pydantic-ai-slim[ag-ui,anthropic,google,openai,openrouter]==2.38.0"
    ]


def test_semora_runtime_packages_are_exact_pypi_dependencies() -> None:
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = project["project"]["dependencies"]

    assert "semora==0.3.0" in dependencies
    assert "semora-store==0.3.0" in dependencies
    assert "semora-store-pg==0.3.0" in dependencies
    sources = project.get("tool", {}).get("uv", {}).get("sources", {})
    assert not any(name.startswith("semora") for name in sources)
