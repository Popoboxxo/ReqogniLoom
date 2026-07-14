"""REQ-104 (DEEP_SYSTEM_ANALYSIS.md BE-22): VCRM matrix read-model cache.

Covers the Redis-backed cache layer in front of ``generate_vcrm``:
- the matrix is served from the shared cache on a second call (cache hit),
- the cache is invalidated on any TraceLink create/delete (signal handler).

The test suite runs on LocMemCache (settings_test), so invalidation relies on
the deterministic ``delete_many`` path rather than ``delete_pattern``.
"""
from __future__ import annotations

import pytest
from django.core.cache import cache

from traceability import services
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_requirement,
    make_trace_link,
)

pytestmark = pytest.mark.django_db


class TestVCRMMatrixCache:
    """REQ-104: cache hit and signal-based invalidation."""

    def test_matrix_served_from_cache_on_second_call(
        self, monkeypatch, tenant_a, workspace_a
    ):
        """Second call is served from cache — the generator runs only once."""
        cache.clear()
        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, "R-1")

            calls = {"n": 0}
            real = services._vcrm_gen.generate_vcrm

            def counting(*args, **kwargs):
                calls["n"] += 1
                return real(*args, **kwargs)

            monkeypatch.setattr(services._vcrm_gen, "generate_vcrm", counting)

            first = services.generate_vcrm(workspace_a.id)
            second = services.generate_vcrm(workspace_a.id)

        assert calls["n"] == 1  # second call must hit the cache
        assert first.to_dict() == second.to_dict()
        assert (
            cache.get(services.traceability_matrix_cache_key(workspace_a.id))
            is not None
        )

    def test_cache_invalidated_on_tracelink_create(self, tenant_a, workspace_a):
        """Creating a TraceLink clears the cached matrix (post_save signal)."""
        cache.clear()
        with active_tenant(tenant_a):
            source = make_artifact(tenant_a, workspace_a)
            target = make_artifact(tenant_a, workspace_a)

            services.generate_vcrm(workspace_a.id)  # prime the cache
            key = services.traceability_matrix_cache_key(workspace_a.id)
            assert cache.get(key) is not None

            make_trace_link(source, target, tenant_a, link_type="satisfies")

        assert cache.get(key) is None

    def test_cache_invalidated_on_tracelink_delete(self, tenant_a, workspace_a):
        """Deleting a TraceLink clears the cached matrix (post_delete signal)."""
        cache.clear()
        with active_tenant(tenant_a):
            source = make_artifact(tenant_a, workspace_a)
            target = make_artifact(tenant_a, workspace_a)
            link = make_trace_link(source, target, tenant_a, link_type="satisfies")

            services.generate_vcrm(workspace_a.id)  # prime after the create
            key = services.traceability_matrix_cache_key(workspace_a.id)
            assert cache.get(key) is not None

            link.delete()

        assert cache.get(key) is None
