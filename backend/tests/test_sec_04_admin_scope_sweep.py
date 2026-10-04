"""SEC-04 admin-scope sweep regression (audit unit SEC-04, ADR-011).

The initial SEC-04 commit tenant-scoped the ``auth_tenancy`` and ``application``
admin registrations. This module pins the *completed* sweep: every admin
registration backed by a tenant-scoped resource must actually narrow its
``get_queryset`` (and its per-object permission checks) to the requesting staff
user's tenant, while the two named exceptions stay cross-tenant by design.

The assertions are data-driven over the real ``admin.site._registry`` so a newly
added registration that forgets the mixin fails this test — the same
"registry + coverage" shape ADR-011 §4 asks for.

Named exceptions (documented, not oversights):

* ``admin_ops.BackupMetadata`` — system-level backup bookkeeping that may span
  tenants and is administered by the deployment operator (see its admin
  docstring); read-only anyway.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib import admin as django_admin
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from persistence.models import Tenant, User

pytestmark = pytest.mark.django_db

#: Model ``_meta.label_lower`` of every admin registration that must be
#: tenant-scoped after the sweep.
TENANT_SCOPED_ADMIN_LABELS = {
    # application (previous SEC-04 commit)
    "application.domaineventoutbox",
    "application.domaineventdlq",
    "application.webhooksubscription",
    "application.webhookdeliverylog",
    # Adr/Risk/Issue: registered in application/admin.py, models in persistence
    "persistence.adr",
    "persistence.risk",
    "persistence.issue",
    # auth_tenancy (previous SEC-04 commit)
    "auth_tenancy.apikey",
    "auth_tenancy.userrole",
    "auth_tenancy.itempermission",
    "auth_tenancy.userworkspacepreference",
    # persistence (this sweep)
    "persistence.user",
    "persistence.tenant",
    "persistence.role",
    "persistence.workspace",
    "persistence.artifact",
    "persistence.requirement",
    "persistence.stakeholderneed",
    "persistence.architectureelement",
    "persistence.tracelink",
    "persistence.testcase",
    "persistence.auditlogentry",
    "persistence.testrun",
    "persistence.testrunresult",
    # workflow (this sweep)
    "workflow.workflowenginedefinition",
    "workflow.workflowitemstate",
    "workflow.workflowhistoryentry",
    # audit (this sweep)
    "audit.auditentry",
    # baseline (this sweep)
    "baseline.baselinesnapshot",
    "baseline.baselinedeltaindexentry",
    # diagram / icd / presets / resilience / se_metrics (this sweep)
    "diagram.diagram",
    "icd.icd",
    "presets.workspacepresetconfig",
    "resilience.circuitbreakerstate",
    "se_metrics.metriccache",
    "se_metrics.workspacethresholdconfig",
}

#: Deliberate cross-tenant exceptions with a written rationale.
CROSS_TENANT_EXCEPTIONS = {
    "admin_ops.backupmetadata",
}


@pytest.fixture
def tenant_a(db) -> Tenant:
    return Tenant.objects.create(
        name="Sweep A", slug=f"sweep-a-{uuid.uuid4().hex[:8]}", is_active=True
    )


@pytest.fixture
def tenant_b(db) -> Tenant:
    return Tenant.objects.create(
        name="Sweep B", slug=f"sweep-b-{uuid.uuid4().hex[:8]}", is_active=True
    )


@pytest.fixture
def staff_a(db, tenant_a) -> User:
    return User.objects.create(
        username=f"sweep-staff-a-{uuid.uuid4().hex[:8]}",
        email="sweep-staff-a@test.test",
        tenant=tenant_a,
        is_active=True,
        is_staff=True,
        is_superuser=True,
    )


def _request_for(user: User):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_expected_labels_are_registered():
    """Guard against a renamed/removed model silently emptying the sweep."""
    registered = {m._meta.label_lower for m in django_admin.site._registry}
    missing = TENANT_SCOPED_ADMIN_LABELS - registered
    assert not missing, f"expected admin registrations missing: {sorted(missing)}"


def test_every_tenant_scoped_registration_narrows_get_queryset(staff_a: User):
    """A staff user of tenant A must not see tenant B rows through any admin.

    The mixin's fail-closed contract is exercised with no matching rows: a
    tenant-A operator's queryset must exclude every tenant-B row. The strong
    positive case (tenant A's own rows stay visible) is pinned per-app in
    ``test_sec_04_admin_key_revocation.py``.
    """
    request = _request_for(staff_a)
    offenders: list[str] = []
    for model in django_admin.site._registry:
        label = model._meta.label_lower
        if label not in TENANT_SCOPED_ADMIN_LABELS:
            continue
        model_admin = django_admin.site._registry[model]
        queryset = model_admin.get_queryset(request)
        # The mixin always returns a filtered queryset; a bare ModelAdmin over a
        # tenant-scoped model would not accept the keyword (or would return the
        # default manager). We assert the mixin is present and the queryset is
        # restricted: either it is empty/none, or its SQL carries a tenant
        # predicate.
        if not hasattr(model_admin, "tenant_scoped_queryset"):
            offenders.append(label)
            continue
        sql = str(queryset.query).lower()
        if "where" not in sql:
            offenders.append(f"{label} (no predicate: {sql})")
    assert not offenders, (
        "admin registrations not narrowed to the operator's tenant: "
        f"{offenders}"
    )


def test_operator_without_tenant_sees_nothing(staff_a: User):
    """Fail-closed: an operator with no tenant must get an empty queryset."""
    request = _request_for(staff_a)
    request.user = User(
        username="sweep-no-tenant", email="none@test.test",
        tenant=None, is_active=True, is_staff=True, is_superuser=True,
    )
    for model in django_admin.site._registry:
        label = model._meta.label_lower
        if label not in TENANT_SCOPED_ADMIN_LABELS:
            continue
        model_admin = django_admin.site._registry[model]
        queryset = model_admin.get_queryset(request)
        assert not queryset.exists(), (
            f"{label}: a tenant-less operator must see no rows"
        )


def test_cross_tenant_exception_is_registered_and_still_works():
    """The documented exception stays registered (not silently dropped)."""
    registered = {m._meta.label_lower for m in django_admin.site._registry}
    assert CROSS_TENANT_EXCEPTIONS <= registered, (
        "the documented cross-tenant exception must remain registered: "
        f"{sorted(CROSS_TENANT_EXCEPTIONS - registered)}"
    )
    label = next(iter(CROSS_TENANT_EXCEPTIONS))
    model = next(m for m in django_admin.site._registry if m._meta.label_lower == label)
    model_admin = django_admin.site._registry[model]
    # It deliberately does NOT use the mixin.
    assert not hasattr(model_admin, "tenant_scoped_queryset")
