import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"


def _import_targets(path: Path) -> list[str]:
    targets: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            targets.append(node.module)
    return targets


def test_agent_source_has_no_platform_imports() -> None:
    violations: list[str] = []
    forbidden_roots = {"sot", "backend", "platform_server"}

    for path in sorted(SRC.rglob("*.py")):
        for target in _import_targets(path):
            if target.split(".", 1)[0] in forbidden_roots:
                violations.append(f"{path.relative_to(SRC)} -> {target}")

    assert violations == []


def test_agent_source_has_no_retired_runtime_imports() -> None:
    retired_roots = {("dbos")}
    assert not any(
        target.split(".", 1)[0] in retired_roots
        for path in sorted(SRC.rglob("*.py"))
        for target in _import_targets(path)
    )


def test_agent_core_has_no_concrete_provider_imports() -> None:
    violations: list[str] = []
    concrete_roots = (
        "pydantic_ai.providers.",
        "pydantic_ai.models.openai",
        "pydantic_ai.models.anthropic",
        "pydantic_ai.models.google",
        "pydantic_ai.models.openrouter",
    )
    for path in sorted(SRC.rglob("*.py")):
        for target in _import_targets(path):
            if target.startswith(concrete_roots):
                violations.append(f"{path.relative_to(SRC)} -> {target}")
    assert violations == []


def test_agent_distribution_has_no_cross_service_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = (
        project["project"]["dependencies"] + project["dependency-groups"]["dev"]
    )
    sources = project.get("tool", {}).get("uv", {}).get("sources", {})

    for dependency in dependencies:
        name = re.split(r"[<>=@\[ ]", dependency.lower(), maxsplit=1)[0]
        assert name not in {"agent-core", "backend", "sot-backend"}
    assert sources == {"service-auth": {"path": "../packages/service-auth"}}
    assert "service-auth" in {
        re.split(r"[<>=@\[ ]", dependency.lower(), maxsplit=1)[0]
        for dependency in project["project"]["dependencies"]
    }


def test_agent_runtime_and_distribution_use_no_product_branding() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["name"] == "agent-server"

    violations: list[str] = []
    forbidden = re.compile(r"\b(?:sot|platform)\b", re.IGNORECASE)
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and forbidden.search(node.value)
            ):
                violations.append(f"{path.relative_to(SRC)}: {node.value!r}")

    assert violations == []
