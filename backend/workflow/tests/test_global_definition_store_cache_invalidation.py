"""GlobalWorkflowDefinitionStore._propagate() cache-invalidation regression.

Code review finding: _propagate() bulk-updates WorkflowEngineDefinition rows
via QuerySet.update() (bypasses save()/signals) but never invalidated
TransitionValidator's in-process _definition_cache for the affected
workspaces, so a worker holding a cached (pre-edit) definition kept
enforcing stale role/gate/transition rules for the rest of its process life.
"""
from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import pytest

from persistence.models import Tenant
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@contextmanager
def _tenant_scope(tenant_id):
    """GlobalWorkflowDefinition / WorkflowEngineDefinition are
    TenantScopedModel (ADR-03) -- mirrors
    test_seed_issue_resolved_auto_approve_target_migration.py's idiom."""
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="gdscache-tenant", slug=f"gdscache-{uuid4().hex[:8]}")


def _workflow_json(states=("Open", "Closed")) -> dict:
    return {"states": list(states), "transitions": []}


def test_add_state_invalidates_cache_for_every_propagated_workspace(tenant):
    from workflow.global_definition_store import GlobalWorkflowDefinitionStore
    from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition
    from workflow.transition_validator import _definition_cache

    with _tenant_scope(tenant.id):
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Issue",
            preset="issue_default",
            workflow_json=_workflow_json(),
        )
        ws_a = uuid4()
        ws_b = uuid4()
        WorkflowEngineDefinition.objects.create(
            tenant=tenant, workspace_id=ws_a, item_type="Issue",
            preset="issue_default", workflow_json=_workflow_json(),
            source_global=global_def, is_customized=False,
        )
        WorkflowEngineDefinition.objects.create(
            tenant=tenant, workspace_id=ws_b, item_type="Issue",
            preset="issue_default", workflow_json=_workflow_json(),
            source_global=global_def, is_customized=False,
        )
        # A customized workspace never gets propagated to and must be
        # unaffected by this global edit (established _propagate() contract).
        ws_customized = uuid4()
        WorkflowEngineDefinition.objects.create(
            tenant=tenant, workspace_id=ws_customized, item_type="Issue",
            preset="issue_default", workflow_json=_workflow_json(states=("Custom",)),
            source_global=global_def, is_customized=True,
        )

        # Prime the cache for all three workspaces with a stale DTO, exactly
        # as TransitionValidator._load_definition would after an earlier
        # transition check -- the load path itself is exercised elsewhere;
        # here we only need *something* keyed correctly to prove invalidation.
        class _StaleDTO:
            pass

        _definition_cache.put(str(ws_a), "Issue", _StaleDTO())
        _definition_cache.put(str(ws_b), "Issue", _StaleDTO())
        _definition_cache.put(str(ws_customized), "Issue", _StaleDTO())

        store = GlobalWorkflowDefinitionStore()
        obj, count = store.add_state(tenant.id, "Issue", "issue_default", "In Review")

        assert count == 2, "only the 2 non-customized rows are propagated"
        assert "In Review" in obj.workflow_json["states"]

        # The two propagated-to workspaces' caches must be gone (load path
        # will miss and re-fetch the now-current definition on next use).
        assert _definition_cache.get(str(ws_a), "Issue") is None
        assert _definition_cache.get(str(ws_b), "Issue") is None
        # The customized workspace was never touched by _propagate() and its
        # cache entry (correctly still describing its own, unrelated,
        # never-changed definition) is left alone.
        assert _definition_cache.get(str(ws_customized), "Issue") is not None
