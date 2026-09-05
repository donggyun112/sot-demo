import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"
FORBIDDEN_ROOTS = {
    "agent_core",
    "fastapi",
    "platform_server",
    "psycopg",
    "redis",
    "semora",
}


def import_targets(path: Path) -> list[str]:
    targets: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            targets.append(node.module)
    return targets


def test_shared_package_has_no_service_or_framework_imports() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for target in import_targets(path):
            if target.split(".", 1)[0] in FORBIDDEN_ROOTS:
                violations.append(f"{path.relative_to(SRC)} -> {target}")

    assert violations == []


def test_distribution_imports_outside_source_tree_with_type_marker(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from importlib.metadata import version; "
                "from importlib.resources import files; "
                "from service_auth import AccessTokenVerifier; "
                "assert AccessTokenVerifier; "
                "assert version('service-auth') == '0.1.0'; "
                "assert files('service_auth').joinpath('py.typed').is_file()"
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
