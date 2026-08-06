"""Pytest configuration and shared fixtures for the ReqFlow backend suite.

The scaffolding fixtures that once lived here (``db_access``, ``single_tenant``,
``api_client``) were never referenced by any test and have been removed
(REQ-068). Cross-cutting fixtures now live in the per-app
``<app>/tests/conftest.py`` files closest to the tests that use them.

Add a fixture here only when it is genuinely shared across multiple app test
suites, and document what it provides directly above its definition.
"""
from __future__ import annotations

from typing import Iterator

import pytest

from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    """Ensure no ``TenantContext`` bleeds between tests (#360).

    ``TenantContext`` (persistence/tenancy.py) is thread-local storage that
    dozens of test modules across nearly every app (application, llm_adapter,
    mcp_server, persistence, rest_api, workflow, ...) set directly via
    ``TenantContext.set_tenant(...)``. Several of those apps had no per-app
    ``conftest.py`` autouse fixture guaranteeing cleanup, and pytest fixtures
    defined inside a single test module never apply outside that module. When
    the full suite ran combined (not per-file), a tenant id left set by one
    app's test could leak into an unrelated test elsewhere — e.g. into
    ``llm_adapter/tests/test_tenant_settings_propagation.py::
    test_tenant_context_cleared_after_task``, which asserts that
    ``TenantContext.get_tenant()`` raises once no context is active.

    Promoting the clear-before/after pattern here (the one root conftest that
    every backend test module inherits from) closes that gap project-wide
    instead of only for one app. Per-app fixtures that already clear the
    context (e.g. persistence/tests/conftest.py, mcp_server/tests/conftest.py)
    are unaffected — clearing an already-cleared thread-local is a no-op.
    """
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()
