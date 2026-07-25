"""Shared pytest fixtures for the rest_api app test suite."""
from __future__ import annotations

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    """Clear the shared cache before every test in this app.

    #72: ``LoginRateThrottle`` (rest_api/auth_views.py) counts requests via
    Django's cache backend, which is Redis-backed and shared across test runs
    (REQ-033/BE-2 — not a per-process LocMemCache). Without clearing it here,
    throttle counters accumulate across tests in the same session and
    unrelated tests that call the login endpoint repeatedly start receiving
    429 responses instead of the expected 200/401.
    """
    cache.clear()
    yield
    cache.clear()
