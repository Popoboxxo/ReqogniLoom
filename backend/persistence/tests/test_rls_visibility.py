"""``persistence.rls_visibility``: the probe behind every cross-corpus count.

The embedding-provenance advisory (``/health/?verbose=1``) and the warn-mode
drift sample both decide *what an aggregate means* from this probe. A broken
probe must degrade to "unknown", never to a confident count, so both branches
are pinned here:

* a role that can see past RLS (the test cluster's owner/superuser role) is
  reported as ``corpus`` — this is the only test that executes the real SQL, so
  a typo in it fails here instead of silently turning every count into
  ``unknown``;
* a probe that cannot run is fail-closed (``shadowed``), not optimistic.
"""
from __future__ import annotations

import pytest
from django.db import connection

from persistence.rls_visibility import (
    COUNT_SCOPE_CORPUS,
    COUNT_SCOPE_SHADOWED,
    can_see_beyond_tenant,
    count_scope,
)

pytestmark = pytest.mark.django_db


def test_privileged_test_role_sees_the_whole_corpus() -> None:
    """The test cluster connects as the owner/superuser, so RLS does not bind."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = current_user"
        )
        row = cursor.fetchone()
    assert row and row[0], "the test database is expected to use a privileged role"

    assert count_scope() == COUNT_SCOPE_CORPUS
    assert can_see_beyond_tenant() is True


def test_a_broken_probe_is_fail_closed(monkeypatch) -> None:
    """An unprovable visibility is reported as shadowed — never as corpus-wide."""
    from persistence import rls_visibility

    class _ExplodingConnection:
        def cursor(self):
            raise RuntimeError("connection lost")

    monkeypatch.setattr(
        rls_visibility, "connections", {"default": _ExplodingConnection()}
    )

    assert count_scope() == COUNT_SCOPE_SHADOWED
    assert can_see_beyond_tenant() is False
