"""F4.2 — BaselineTag model + facade semantics (real DB).

Plan F (2026-10-21), F4.2. Tags are *metadata*, not content: adding, changing or
removing one must never touch ``bl_baseline_snapshot`` (whose DB trigger raises
on every UPDATE), and the denormalised ``workspace_id`` on the tag row is
derived exclusively from ``baseline.workspace_id`` (QR-S09 a) — never from
request data.

Requirements:
- REQ-L2-BL-001 (baseline persistence), REQ-L2-BL-002 (immutability),
- REQ-L2-PL-010 (tenant isolation).
"""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction
from django.test.utils import CaptureQueriesContext
from django.db import connection

from application.base import ValidationError
from application.baseline_facade import BaselineFacade
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_EDITOR, UserRole
from baseline.models import BaselineSnapshot, BaselineTag
from baseline.services import purge_baseline
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db


def _env(tier: str = "standard"):
    """Create tenant + workspace + editor + one direct baseline snapshot."""
    slug = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"tag-{slug}", slug=f"tag-{slug}")
    user = User.objects.create(
        username=f"tag-{slug}", email=f"tag-{slug}@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"tag-ws-{slug}", preset={"name": tier}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
        )
        baseline = BaselineSnapshot.unscoped.create(
            tenant=tenant,
            workspace_id=workspace.id,
            scope="project",
            name=f"tag-baseline-{slug}",
        )
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(ROLE_EDITOR,),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    return tenant, user, workspace, baseline, ctx


def _snapshot_updates(queries) -> list[str]:
    return [
        q["sql"]
        for q in queries
        if q["sql"].lstrip().upper().startswith('UPDATE "BL_BASELINE_SNAPSHOT"')
    ]


def test_set_tags_does_not_update_the_baseline_snapshot() -> None:
    """Tags live in their own table; the immutable snapshot is never UPDATEd."""
    _, _, _, baseline, ctx = _env()
    facade = BaselineFacade()

    with CaptureQueriesContext(connection) as captured:
        labels = facade.set_tags(baseline.id, ["Release", "RC1"], ctx)

    assert labels == ["RC1", "Release"]
    assert _snapshot_updates(captured.captured_queries) == []
    assert set(
        BaselineTag.unscoped.filter(baseline_id=baseline.id).values_list(
            "label", flat=True
        )
    ) == {"Release", "RC1"}


def test_tag_workspace_derived_from_baseline() -> None:
    """The tag's workspace_id is a copy of the baseline's, never caller input."""
    _, _, workspace, baseline, ctx = _env()

    BaselineFacade().set_tags(baseline.id, ["Release"], ctx)

    tag = BaselineTag.unscoped.get(baseline_id=baseline.id)
    assert tag.workspace_id == workspace.id
    # The facade signature has no workspace parameter at all — a request cannot
    # even express a conflicting value.
    with pytest.raises(TypeError):
        BaselineFacade().set_tags(  # type: ignore[call-arg]
            baseline.id, ["RC1"], ctx, workspace_id=str(uuid.uuid4())
        )


def test_replace_set_is_case_insensitive_and_sorted() -> None:
    _, _, _, baseline, ctx = _env()
    facade = BaselineFacade()

    facade.set_tags(baseline.id, ["release", "Release", "RC1"], ctx)
    assert facade.set_tags(baseline.id, ["alpha"], ctx) == ["alpha"]

    remaining = list(
        BaselineTag.unscoped.filter(baseline_id=baseline.id).values_list(
            "label", flat=True
        )
    )
    assert remaining == ["alpha"]


def test_unique_constraint_is_case_insensitive() -> None:
    tenant, _, workspace, baseline, _ = _env()
    BaselineTag.unscoped.create(
        tenant=tenant,
        baseline=baseline,
        workspace_id=workspace.id,
        label="Release",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        BaselineTag.unscoped.create(
            tenant=tenant,
            baseline=baseline,
            workspace_id=workspace.id,
            label="release",
        )


def test_validation_rejects_bad_labels() -> None:
    _, _, _, baseline, ctx = _env()
    facade = BaselineFacade()

    with pytest.raises(ValidationError):
        facade.set_tags(baseline.id, ["bad\nlabel"], ctx)
    with pytest.raises(ValidationError):
        facade.set_tags(baseline.id, [""], ctx)
    with pytest.raises(ValidationError):
        facade.set_tags(baseline.id, ["x" * 65], ctx)
    with pytest.raises(ValidationError):
        facade.set_tags(baseline.id, [f"tag-{i}" for i in range(21)], ctx)


def test_admin_purge_removes_tags_via_cascade() -> None:
    tenant, _, _, baseline, ctx = _env()
    BaselineFacade().set_tags(baseline.id, ["Release"], ctx)
    assert BaselineTag.unscoped.filter(baseline_id=baseline.id).count() == 1

    purge_baseline(baseline.id, tenant.id)

    assert BaselineTag.unscoped.filter(baseline_id=baseline.id).count() == 0
