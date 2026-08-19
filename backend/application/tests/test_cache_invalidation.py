"""Tests for signal-based cache invalidation (REQ-038, BE-7).

leaf_id : cache_invalidation
req_id  : REQ-038

Coverage:
  - Key builders produce the canonical namespaced keys.
  - invalidate_workspace_caches deletes every workspace key from the shared
    cache and is a no-op for None.
  - invalidate_workspace_caches best-effort clears the in-process module caches
    and never raises when a backend is unavailable.
  - _resolve_workspace_id handles the direct-FK, artifact-relation and
    Workspace-self shapes.
  - _on_change forwards the resolved workspace id to the invalidator.
  - register_signals connects post_save/post_delete idempotently.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.test import override_settings

from application import cache_invalidation as ci

WS_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------


def test_key_builders_are_namespaced_and_workspace_scoped():
    assert ci.preset_cache_key(WS_ID) == f"reqogniloom:preset:{WS_ID}"
    assert ci.terminology_cache_key(WS_ID) == f"reqogniloom:terminology:{WS_ID}"
    assert ci.features_cache_key(WS_ID) == f"reqogniloom:features:{WS_ID}"
    assert ci.workflow_def_cache_key(WS_ID) == f"reqogniloom:workflow-def:{WS_ID}"


# ---------------------------------------------------------------------------
# invalidate_workspace_caches — shared cache
# ---------------------------------------------------------------------------


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cache-invalidation-test",
        }
    }
)
def test_invalidate_deletes_all_shared_workspace_keys():
    keys = [
        ci.preset_cache_key(WS_ID),
        ci.terminology_cache_key(WS_ID),
        ci.features_cache_key(WS_ID),
        ci.workflow_def_cache_key(WS_ID),
    ]
    for key in keys:
        cache.set(key, "stale", timeout=300)
    # An unrelated workspace key must survive.
    other = ci.preset_cache_key("other")
    cache.set(other, "keep", timeout=300)

    with patch.object(ci, "_invalidate_in_process"):
        ci.invalidate_workspace_caches(WS_ID)

    for key in keys:
        assert cache.get(key) is None
    assert cache.get(other) == "keep"


def test_invalidate_none_is_noop():
    with patch.object(ci, "cache") as mock_cache, patch.object(
        ci, "_invalidate_in_process"
    ) as mock_inproc:
        ci.invalidate_workspace_caches(None)
    mock_cache.delete_many.assert_not_called()
    mock_inproc.assert_not_called()


def test_invalidate_accepts_uuid_and_stringifies():
    ws_uuid = uuid.uuid4()
    with patch.object(ci, "cache") as mock_cache, patch.object(
        ci, "_invalidate_in_process"
    ) as mock_inproc:
        ci.invalidate_workspace_caches(ws_uuid)
    called_keys = mock_cache.delete_many.call_args[0][0]
    assert ci.preset_cache_key(str(ws_uuid)) in called_keys
    mock_inproc.assert_called_once_with(str(ws_uuid))


def test_invalidate_uses_delete_pattern_when_available():
    mock_cache = MagicMock()
    with patch.object(ci, "cache", mock_cache), patch.object(
        ci, "_invalidate_in_process"
    ):
        ci.invalidate_workspace_caches(WS_ID)
    mock_cache.delete_pattern.assert_called_once()


def test_invalidate_survives_shared_cache_failure():
    mock_cache = MagicMock()
    mock_cache.delete_many.side_effect = RuntimeError("redis down")
    with patch.object(ci, "cache", mock_cache), patch.object(
        ci, "_invalidate_in_process"
    ) as mock_inproc:
        # Must not raise — invalidation may never break the triggering write.
        ci.invalidate_workspace_caches(WS_ID)
    mock_inproc.assert_called_once_with(WS_ID)


# ---------------------------------------------------------------------------
# _invalidate_in_process — best effort, never raises
# ---------------------------------------------------------------------------


def test_in_process_invalidation_clears_reachable_module_caches():
    with patch("presets.gate._invalidate_workspace") as mock_gate, patch(
        "application.preset_policy_service.get_preset_policy_service"
    ) as mock_policy, patch(
        "workflow.transition_validator._definition_cache"
    ) as mock_defcache:
        ci._invalidate_in_process(WS_ID)

    mock_gate.assert_called_once_with(WS_ID)
    mock_policy.return_value.invalidate_cache.assert_called_once_with(WS_ID)
    mock_defcache.clear.assert_called_once_with()


def test_in_process_invalidation_swallows_errors():
    with patch(
        "presets.gate._invalidate_workspace", side_effect=RuntimeError("boom")
    ):
        # A failing sub-cache must not abort the others or raise.
        ci._invalidate_in_process(WS_ID)


# ---------------------------------------------------------------------------
# _resolve_workspace_id
# ---------------------------------------------------------------------------


def test_resolve_direct_workspace_fk():
    instance = SimpleNamespace(workspace_id=WS_ID)
    assert ci._resolve_workspace_id(instance) == WS_ID


def test_resolve_via_artifact_relation():
    instance = SimpleNamespace(
        workspace_id=None, artifact=SimpleNamespace(workspace_id=WS_ID)
    )
    assert ci._resolve_workspace_id(instance) == WS_ID


def test_resolve_workspace_self_by_pk():
    class Workspace:  # name-based branch in the resolver
        workspace_id = None
        artifact = None
        pk = WS_ID

    assert ci._resolve_workspace_id(Workspace()) == WS_ID


def test_resolve_returns_none_when_unresolvable():
    instance = SimpleNamespace(workspace_id=None, artifact=None)
    assert ci._resolve_workspace_id(instance) is None


# ---------------------------------------------------------------------------
# _on_change handler
# ---------------------------------------------------------------------------


def test_on_change_invalidates_resolved_workspace():
    instance = SimpleNamespace(workspace_id=WS_ID)
    with patch.object(ci, "invalidate_workspace_caches") as mock_inv:
        ci._on_change(sender=object, instance=instance)
    mock_inv.assert_called_once_with(WS_ID)


def test_on_change_noop_when_workspace_unresolvable():
    instance = SimpleNamespace(workspace_id=None, artifact=None)
    with patch.object(ci, "invalidate_workspace_caches") as mock_inv:
        ci._on_change(sender=object, instance=instance)
    mock_inv.assert_not_called()


# ---------------------------------------------------------------------------
# register_signals — real connection, idempotent
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_register_signals_connects_save_and_delete_idempotently():
    from persistence.models import (
        ArchitectureElement,
        Artifact,
        Requirement,
        Workspace,
    )
    from presets.models import WorkspacePresetConfig

    watched = [
        Workspace,
        WorkspacePresetConfig,
        Artifact,
        Requirement,
        ArchitectureElement,
    ]

    # ready() already ran at startup; a second call must not duplicate receivers.
    ci.register_signals()
    ci.register_signals()

    for model in watched:
        save_uid = f"{ci._DISPATCH_UID}.save.{model.__name__}"
        delete_uid = f"{ci._DISPATCH_UID}.delete.{model.__name__}"
        save_uids = [r[0][0] for r in post_save.receivers]
        delete_uids = [r[0][0] for r in post_delete.receivers]
        assert save_uids.count(save_uid) == 1
        assert delete_uids.count(delete_uid) == 1


# ---------------------------------------------------------------------------
# _resolve_workspace_id — TraceLink (review M3, #625)
# ---------------------------------------------------------------------------
#
# TraceLink is the one watched model whose workspace is not on the instance:
# it is reached through the source Artifact. #625 added a fast path that reads
# that Artifact from the instance's relation cache when it is already there
# (TraceLinkManager.create builds ``TraceLink(source=source, ...)``, so on
# post_save it always is), falling back to the original values_list query
# otherwise — which is what post_delete and any freshly loaded row get.
#
# Both branches must agree on the answer; only the query count differs. These
# are the only DB-backed tests in this module, hence the local imports.


@pytest.mark.django_db
class TestResolveWorkspaceIdForTraceLink:
    @staticmethod
    def _fixtures():
        from persistence.models import Artifact, Tenant, Workspace
        from persistence.tenancy import TenantContext

        tenant = Tenant.objects.create(name="T-ci-625", slug="t-ci-625")
        TenantContext.set_tenant(tenant.id)
        workspace = Workspace.objects.create(tenant=tenant, name="WS-ci-625")
        source = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        target = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        return tenant, workspace, source, target

    def test_cached_source_relation_costs_no_query(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from persistence.models import TraceLink
        from persistence.tenancy import TenantContext

        try:
            tenant, workspace, source, target = self._fixtures()
            # Exactly the shape TraceLinkManager.create() produces.
            link = TraceLink(
                source=source,
                target=target,
                link_type="traces",
                tenant_id=tenant.id,
            )

            with CaptureQueriesContext(connection) as cap:
                resolved = ci._resolve_workspace_id(link)
        finally:
            TenantContext.clear_tenant()

        assert resolved == str(workspace.id)
        assert len(cap.captured_queries) == 0, (
            "the source Artifact was already in the relation cache but "
            "_resolve_workspace_id queried for it anyway (#625):\n"
            + "\n".join(q["sql"] for q in cap.captured_queries)
        )

    def test_uncached_source_relation_falls_back_to_one_query(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from persistence.models import TraceLink
        from persistence.tenancy import TenantContext

        try:
            tenant, workspace, source, target = self._fixtures()
            saved = TraceLink.objects.create(
                source=source,
                target=target,
                link_type="traces",
                tenant_id=tenant.id,
            )
            # Reload: no select_related, so the relation cache is empty —
            # the post_delete / plain-queryset shape.
            reloaded = TraceLink.objects.get(pk=saved.pk)
            assert "source" not in reloaded._state.fields_cache

            with CaptureQueriesContext(connection) as cap:
                resolved = ci._resolve_workspace_id(reloaded)
        finally:
            TenantContext.clear_tenant()

        assert resolved == str(workspace.id), (
            "the fallback branch disagrees with the cached branch"
        )
        assert len(cap.captured_queries) == 1, (
            "the fallback should be a single values_list lookup, got:\n"
            + "\n".join(q["sql"] for q in cap.captured_queries)
        )
        assert '"pl_artifact"' in cap.captured_queries[0]["sql"]
