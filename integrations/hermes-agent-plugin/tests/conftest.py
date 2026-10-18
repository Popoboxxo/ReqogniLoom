"""Pytest fixtures shared by the plugin's tests.

The plugin keeps *state* in ``$HERMES_HOME/reqogniloom/`` — ``state.json`` for
the interview/listen mode, ``servers.json`` for the multi-server registry. A test
run must never read or write the developer's real files, and one test must never
see what the previous one left behind, so every test gets its own ``HERMES_HOME``.

Without this, a machine that has a configured registry (the normal case for a
live install) would silently redirect every client construction in the test suite
to that install's active server.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture(autouse=True)
def isolated_hermes_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point ``$HERMES_HOME`` at a fresh temp directory for every test."""
    home = tmp_path_factory.mktemp("hermes-home")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("REQOGNILOOM_BASE_URL", raising=False)
    monkeypatch.delenv("REQOGNILOOM_API_KEY", raising=False)
    yield home
    # Nothing to clean up: the temp directory is pytest's.
    assert os.environ.get("HERMES_HOME") == str(home)
