import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKSPACE = ROOT.parent


def test_distribution_is_installed_without_source_path_injection(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import agent_core; "
                "from importlib.metadata import version; "
                "assert version('agent-server') == '0.1.0'"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_container_entrypoint_uses_installed_uvicorn_and_imports_app() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    command_line = next(
        line for line in dockerfile.splitlines() if line.startswith("CMD ")
    )
    command = json.loads(command_line.removeprefix("CMD "))

    assert command[:4] == ["uv", "run", "uvicorn", "agent_core.main:app"]
    assert "PYTHONPATH" not in dockerfile
    assert importlib.util.find_spec("uvicorn") is not None

    from uvicorn import Config

    config = Config(command[3])
    config.load()
    assert config.loaded_app is not None


def test_container_uses_only_agent_and_shared_auth_from_root_context() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    copy_lines = [line for line in dockerfile.splitlines() if line.startswith("COPY ")]

    assert "COPY packages/service-auth /app/packages/service-auth" in copy_lines
    assert (
        "COPY agent-server/pyproject.toml agent-server/uv.lock /app/agent-server/"
        in copy_lines
    )
    assert "COPY agent-server/src /app/agent-server/src" in copy_lines
    assert "WORKDIR /app/agent-server" in dockerfile
    assert not any("platform" in line.lower() for line in copy_lines)
    assert not any(line in {"COPY . .", "COPY . /app"} for line in copy_lines)
    assert "PYTHONPATH" not in dockerfile


def test_root_docker_context_excludes_local_and_non_runtime_files() -> None:
    rules = (WORKSPACE / ".dockerignore").read_text().splitlines()

    assert "**/.venv" in rules
    assert "**/__pycache__" in rules
    assert "**/.pytest_cache" in rules
    assert "**/.ruff_cache" in rules
    assert "**/.mypy_cache" in rules
    assert "docs/" in rules
    assert "**/tests/" in rules
