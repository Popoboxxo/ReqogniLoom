"""Tests for the ReviewPolicy persistence model (Phase 5, REQ-L2-RV-001).

``ReviewPolicy`` is a ``TenantScopedModel``, whose default manager requires an
active ``TenantContext`` (ARCH-L1-011) -- same convention as
``test_prompt_template_model.py`` and ``test_entity_schema.py``.
"""
from __future__ import annotations

import pytest

from persistence.models import ReviewPolicy, Tenant
from persistence.tests.conftest import active_tenant


@pytest.mark.django_db
def test_review_policy_defaults_and_scope():
    tenant = Tenant.objects.create(name="t1", slug="t1")
    with active_tenant(tenant):
        row = ReviewPolicy.objects.create(
            tenant=tenant, workspace_id=None, mode="review_all", min_confidence=0.9
        )
    assert row.workspace_id is None
    assert row.mode == "review_all"
    assert row.min_confidence == 0.9
