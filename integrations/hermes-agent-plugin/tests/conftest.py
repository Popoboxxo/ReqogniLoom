"""Pytest fixtures shared by the plugin's tests.

The plugin keeps *state* in ``$HERMES_HOME/reqogniloom/`` — ``state.json`` for
the interview/listen mode, ``servers.json`` for the multi-server registry — and
two pieces of process-global memoisation (the tool catalogue cache and the
issued confirmation tokens). A test run must never read the developer's real
files, and one test must never see what the previous one left behind, so every
test gets:

* its own ``HERMES_HOME`` (so a machine with a configured registry does not
  silently redirect every client construction to that install's active server),
* a clean environment for *every* ``REQOGNILOOM_*`` variable — not just the two
  historic names, because the multi-server feature added per-server variables
  (``REQOGNILOOM_API_KEY_<ID>``) that would otherwise leak in from a developer
  shell and make the suite machine-dependent,
* an empty catalogue cache and an empty confirmation-token store.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator

import pytest

_ENV_PREFIX = "REQOGNILOOM_"


def _tools_module_names() -> Iterator[str]:
    """Every loaded instance of the tools module.

    Both import modes exist in one process (the package copy used by
    ``__init__.py`` and the flat copy the dashboard imports), and each keeps its
    own cache and token store — so the fixture has to clear all of them, not one.
    """
    for name in list(sys.modules):
        if "reqogniloom_tools" in name:
            yield name




@pytest.fixture(autouse=True)
def isolated_hermes_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Point ``$HERMES_HOME`` at a fresh temp directory for every test."""
    home = tmp_path_factory.mktemp("hermes-home")
    monkeypatch.setenv("HERMES_HOME", str(home))
    for name in [key for key in os.environ if key.startswith(_ENV_PREFIX)]:
        monkeypatch.delenv(name, raising=False)
    yield home
    assert os.environ.get("HERMES_HOME") == str(home)


@pytest.fixture(autouse=True)
def reset_process_memoisation() -> Iterator[None]:
    """Empty the tool catalogue caches and the issued-token stores around a test."""

    def clear() -> None:
        for name in _tools_module_names():
            module = sys.modules.get(name)
            if module is None:
                continue
            invalidate = getattr(module, "invalidate", None)
            reset = getattr(module, "reset_issued_tokens", None)
            if callable(invalidate):
                invalidate()
            if callable(reset):
                reset()

    clear()
    yield
    clear()
