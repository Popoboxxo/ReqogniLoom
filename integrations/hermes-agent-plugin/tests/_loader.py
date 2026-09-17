"""Shared helper: load the plugin package by file path.

The plugin root (``integrations/hermes-agent-plugin/``) isn't installed
as a real package (it's loaded directly off disk by the Hermes host, same
as ``plugins/disk-cleanup`` in hermes-agent), and ``__init__.py`` uses a
relative import (``from .reqogniloom_client import ...``) to match that
reference plugin's convention. To make the relative import resolve under
plain ``python -m unittest``, load ``__init__.py`` with
``submodule_search_locations`` set so it behaves as a real package.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_PKG_NAME = "reqogniloom_plugin_under_test"


def load_plugin() -> ModuleType:
    if _PKG_NAME in sys.modules:
        return sys.modules[_PKG_NAME]
    spec = importlib.util.spec_from_file_location(
        _PKG_NAME,
        PLUGIN_ROOT / "__init__.py",
        submodule_search_locations=[str(PLUGIN_ROOT)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PKG_NAME] = module
    spec.loader.exec_module(module)
    return module
