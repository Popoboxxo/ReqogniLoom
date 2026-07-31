"""Issue #131 regression test: ``reqif`` must be an optional dependency.

The ReqIF services are pulled in transitively by ``rest_api/urls.py``, so a
module-level ``import reqif`` made a missing/broken install fatal for the whole
Django process (every REST route, every ``manage.py`` command including
``migrate``). These tests pin that the import chain stays clean.
"""

import ast
import importlib
import sys
from pathlib import Path

import pytest

_SERVICE_FILES = [
    "reqif_export_service.py",
    "reqif_import_service.py",
]


def _module_level_imports(path: Path) -> set[str]:
    """Return the top-level (module-scope) imported root package names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("filename", _SERVICE_FILES)
def test_reqif_is_not_imported_at_module_level(filename):
    path = Path(__file__).resolve().parent.parent / filename
    assert "reqif" not in _module_level_imports(path), (
        f"{filename} imports 'reqif' at module level — a missing optional "
        "dependency would break Django startup (issue #131)."
    )


def test_services_import_without_the_reqif_package(monkeypatch):
    """Importing the services with ``reqif`` unavailable must still succeed."""
    for name in list(sys.modules):
        if name == "reqif" or name.startswith("reqif."):
            monkeypatch.delitem(sys.modules, name, raising=False)
        if name.startswith("application.reqif_"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    real_import = importlib.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "reqif" or name.startswith("reqif."):
            raise ModuleNotFoundError("No module named 'reqif'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)

    export_module = importlib.import_module("application.reqif_export_service")
    importlib.import_module("application.reqif_import_service")

    # ...and the failure surfaces only when ReqIF is actually invoked.
    with pytest.raises(ImportError):
        export_module._load_reqif()
