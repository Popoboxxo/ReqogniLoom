"""Least-privilege RLS fixture shared by the S0.2 regression suites.

The default pytest connection authenticates as a superuser, which bypasses
Row-Level Security unconditionally. To make an assertion about RLS actually
mean something, tests must switch the connection to the application role
(``persistence/0048_app_role.py``) while leaving no tenant armed — the exact
condition a Celery worker or a direct, unauthenticated caller starts from.

Import :data:`app_role` into a test module to get a fixture that returns the
:func:`app_role_unarmed` context manager on PostgreSQL (and skips elsewhere)::

    from persistence.tests.rls_app_role import app_role

    def test_something(app_role):
        with app_role():
            ...
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from django.db import connection

from persistence.db_roles import APP_DB_ROLE
from persistence.tenancy import TenantContext


@contextmanager
def app_role_unarmed() -> Iterator[None]:
    """Enter the least-privilege app role with *no* tenant armed anywhere.

    Clears the thread-local :class:`TenantContext`, resets the PostgreSQL
    ``app.current_tenant`` GUC and ``SET ROLE``s to :data:`APP_DB_ROLE`, so
    every tenant-scoped read inside the block is filtered by RLS. The previous
    role, GUC and thread-local context are all restored in ``finally`` — the
    GUC is connection-scoped (session ``SET``, not ``SET LOCAL``; see
    ``persistence/middleware.py``), so an unpaired switch would leak into
    whatever runs next on this connection.
    """
    tenant_was_set = TenantContext.is_set()
    previous = TenantContext.get_tenant() if tenant_was_set else None
    TenantContext.clear_tenant()
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            if previous is not None:
                cursor.execute("SET app.current_tenant = %s", [str(previous)])
            else:
                cursor.execute("RESET app.current_tenant")
        if tenant_was_set and previous is not None:
            TenantContext.set_tenant(previous)
        else:
            TenantContext.clear_tenant()


@pytest.fixture
def app_role():
    """Return :func:`app_role_unarmed` on PostgreSQL; skip on other vendors."""
    if connection.vendor != "postgresql":
        pytest.skip("RLS behaviour requires a PostgreSQL connection")
    return app_role_unarmed


__all__ = ["app_role", "app_role_unarmed"]
