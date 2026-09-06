from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "src" / "sot"
PRODUCT_MODULES = {
    "identity",
    "workspace",
    "document",
    "session",
    "sharing",
    "consensus",
    "agent",
}
FORBIDDEN_DOMAIN_ROOTS = {
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic_settings",
    "psycopg",
    "psycopg_pool",
    "pydantic_ai",
}
FORBIDDEN_APPLICATION_ROOTS = FORBIDDEN_DOMAIN_ROOTS
ALLOWED_DEPENDENCIES = {
    "identity": set(),
    "workspace": {"identity"},
    "document": {"identity", "workspace"},
    "session": {"identity", "workspace", "document"},
    "sharing": {"identity", "workspace", "session"},
    "consensus": {"identity", "workspace", "document", "session", "sharing"},
    "agent": {"identity", "workspace", "document", "session", "consensus"},
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = ".".join(("sot", *path.relative_to(SRC).parts[:-1]))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, package)
            names.update(
                base if alias.name == "*" else f"{base}.{alias.name}"
                for alias in node.names
            )
    return names


def test_product_module_packages_exist() -> None:
    assert {path.name for path in SRC.iterdir() if path.is_dir()} >= PRODUCT_MODULES


def test_domain_has_no_framework_or_persistence_imports() -> None:
    for owner in PRODUCT_MODULES:
        for path in (SRC / owner).rglob("*.py"):
            if path.relative_to(SRC / owner).parts[0] not in {"domain.py", "domain"}:
                continue
            for name in imported_modules(path):
                parts = name.split(".")
                assert parts[0] not in FORBIDDEN_DOMAIN_ROOTS, (path, name)
                if parts[0] == "sot":
                    assert len(parts) >= 3 and (
                        parts[1] == "shared"
                        or (parts[1] == owner and parts[2] == "domain")
                    ), (path, name)


def test_application_has_no_fastapi_or_psycopg_imports() -> None:
    for owner in PRODUCT_MODULES:
        for path in (SRC / owner).rglob("*.py"):
            if path.relative_to(SRC / owner).parts[0] not in {
                "application.py",
                "application",
            }:
                continue
            for name in imported_modules(path):
                parts = name.split(".")
                assert parts[0] not in FORBIDDEN_APPLICATION_ROOTS, (path, name)
                if parts[0] == "sot":
                    assert len(parts) >= 3 and parts[1] in PRODUCT_MODULES | {
                        "shared"
                    }, (path, name)
                    if parts[1] == owner:
                        assert parts[2] in {
                            "application",
                            "contracts",
                            "domain",
                            "ports",
                        } or (parts[2:4] == ["providers", "base"]), (path, name)


def test_cross_module_imports_use_contracts_only() -> None:
    for owner in PRODUCT_MODULES:
        for path in (SRC / owner).rglob("*.py"):
            for imported in imported_modules(path):
                parts = imported.split(".")
                if parts[0] == "sot":
                    assert len(parts) >= 3, (path, imported)
                    target = parts[1]
                    assert target in PRODUCT_MODULES | {"shared", "bootstrap"}, (
                        path,
                        imported,
                    )
                    if target == "bootstrap":
                        assert parts[2] in {"settings", "database"}, (path, imported)
                    if target in PRODUCT_MODULES and target != owner:
                        assert target in ALLOWED_DEPENDENCIES[owner], (path, imported)
                        assert parts[2] == "contracts", (path, imported)


@pytest.mark.parametrize(
    "path,source",
    [
        (
            "workspace/application.py",
            "from sot.document.contracts import DocumentReader",
        ),
        (
            "identity/providers/google.py",
            "from sot.workspace.contracts import WorkspaceAuthorizer",
        ),
        ("sharing/api.py", "from sot.consensus import contracts"),
        (
            "identity/application.py",
            "from ..workspace.contracts import WorkspaceAuthorizer",
        ),
        ("identity/providers/google.py", "from ...workspace import contracts"),
        ("document/api.py", "from sot import workspace"),
        ("document/api.py", "import sot.workspace"),
        ("document/api.py", "from sot.workspace import postgres"),
        ("document/api.py", "from sot.workspace import *"),
        ("document/api.py", "import sot"),
        ("document/api.py", "from sot.api import create_app"),
        ("document/api.py", "from sot.bootstrap.app import build_app"),
        ("document/api.py", "if True:\n    import sot.workspace.postgres"),
    ],
)
def test_module_checker_rejects_reverse_private_and_package_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, source: str
) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr(__name__ + ".SRC", tmp_path)
    with pytest.raises(AssertionError):
        test_cross_module_imports_use_contracts_only()


@pytest.mark.parametrize(
    "path,source",
    [
        ("document/api.py", "from sot.workspace import contracts"),
        (
            "session/application/read.py",
            "from ...document.contracts import DocumentReader",
        ),
        ("consensus/api.py", "from ..sharing.contracts import BundleReader"),
        ("agent/tools.py", "from sot.identity.contracts import Actor"),
        ("document/api.py", "import sot.workspace.contracts as workspace"),
        ("document/api/__init__.py", "from ...workspace import contracts"),
    ],
)
def test_module_checker_accepts_only_directed_contract_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, source: str
) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr(__name__ + ".SRC", tmp_path)
    test_cross_module_imports_use_contracts_only()


@pytest.mark.parametrize(
    "path,source",
    [
        ("session/domain/entities.py", "import pydantic"),
        ("session/domain.py", "from . import postgres"),
        ("session/domain/__init__.py", "from ..application import CreateSession"),
        ("session/domain/entities.py", "from psycopg_pool import AsyncConnectionPool"),
        (
            "session/domain/entities.py",
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import pydantic",
        ),
    ],
)
def test_domain_checker_covers_nested_files_and_relative_layer_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, source: str
) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr(__name__ + ".SRC", tmp_path)
    with pytest.raises(AssertionError):
        test_domain_has_no_framework_or_persistence_imports()


@pytest.mark.parametrize(
    "path,source",
    [
        ("session/application/create.py", "import fastapi"),
        ("session/application.py", "from .postgres import Repository"),
        ("session/application/__init__.py", "from ..api import Request"),
    ],
)
def test_application_checker_covers_nested_files_and_relative_layer_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, source: str
) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr(__name__ + ".SRC", tmp_path)
    with pytest.raises(AssertionError):
        test_application_has_no_fastapi_or_psycopg_imports()


def test_architecture_checker_does_not_silently_skip_invalid_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "session" / "api.py"
    target.parent.mkdir()
    target.write_text("from broken syntax", encoding="utf-8")
    monkeypatch.setattr(__name__ + ".SRC", tmp_path)
    with pytest.raises(SyntaxError):
        test_cross_module_imports_use_contracts_only()
