from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parents[2] / "src" / "sot"
PRODUCT_MODULES = {
    "identity", "workspace", "document", "session", "sharing", "consensus", "agent"
}
FORBIDDEN_DOMAIN_ROOTS = {"fastapi", "pydantic", "psycopg", "pydantic_ai"}
FORBIDDEN_APPLICATION_ROOTS = {"fastapi", "psycopg"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_product_module_packages_exist() -> None:
    assert {path.name for path in SRC.iterdir() if path.is_dir()} >= PRODUCT_MODULES


def test_domain_has_no_framework_or_persistence_imports() -> None:
    for path in SRC.glob("*/domain.py"):
        roots = {name.split(".", 1)[0] for name in imported_modules(path)}
        assert not roots & FORBIDDEN_DOMAIN_ROOTS, path


def test_application_has_no_fastapi_or_psycopg_imports() -> None:
    for path in SRC.glob("*/application.py"):
        roots = {name.split(".", 1)[0] for name in imported_modules(path)}
        assert not roots & FORBIDDEN_APPLICATION_ROOTS, path


def test_cross_module_imports_use_contracts_only() -> None:
    for owner in PRODUCT_MODULES:
        for path in (SRC / owner).glob("*.py"):
            for imported in imported_modules(path):
                parts = imported.split(".")
                if len(parts) >= 3 and parts[0] == "sot":
                    target = parts[1]
                    if target in PRODUCT_MODULES and target != owner:
                        assert parts[2] == "contracts", (path, imported)
