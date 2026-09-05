"""The six Layer-2 models are tenant-scoped (Datenmodell-Konsolidierung Phase 2).

Task 15 rebases ``Adr``, ``Risk``, ``Goal``, ``MainGoal``, ``Issue`` and
``ChangeRequest`` onto :class:`persistence.models.TenantScopedModel`, so tenant
isolation stops being a per-call-site ``tenant_id=`` filter and becomes a
property of the default manager (REQ-L3-PL002-001/003, ADR-03).

``ChangeRequestAffectedItem`` is deliberately **not** covered here: it never
received the Task-14 audit-field reconciliation, so moving it needs its own
column-adding migration and is split into a follow-up task.

The behavioural half of this file is the point: structural assertions only prove
the class hierarchy is wired, not that a query under tenant A's context genuinely
cannot see tenant B's rows. Both directions are asserted for every model, plus
the fail-closed case (no context must *raise*, never silently fall back to an
unfiltered read).
"""
from __future__ import annotations

import uuid

import pytest
from django.apps import apps

from persistence.models import TenantScopedModel
from persistence.tenancy import TenantContext, TenantContextNotSetError

MODELS = ["Adr", "Risk", "Goal", "MainGoal", "Issue", "ChangeRequest"]


def _create_row(model_name: str, tenant, workspace, label: str):
    """Create one minimal row of *model_name*, returning its primary key.

    ``Goal``/``MainGoal`` carry a non-nullable ``artifact`` OneToOne, so they get
    a backing :class:`persistence.models.Artifact`; the other four do not need
    one. A tenant context must already be active — that is what the manager
    under test requires.
    """
    from persistence.models import Artifact

    from application.models import Adr, ChangeRequest, Goal, Issue, MainGoal, Risk

    common = {"tenant": tenant, "workspace_id": workspace.id}

    if model_name == "Adr":
        return Adr.objects.create(title=f"ADR {label}", description="d", **common).id
    if model_name == "Risk":
        return Risk.objects.create(title=f"Risk {label}", **common).id
    if model_name == "Issue":
        return Issue.objects.create(title=f"Issue {label}", **common).id
    if model_name == "ChangeRequest":
        return ChangeRequest.objects.create(title=f"CR {label}", **common).id
    if model_name == "Goal":
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Goal"
        )
        return Goal.objects.create(
            artifact=artifact,
            lineage_id=uuid.uuid4(),
            sequence_number=1,
            title=f"Goal {label}",
            **common,
        ).id
    if model_name == "MainGoal":
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="MainGoal"
        )
        return MainGoal.objects.create(
            artifact=artifact,
            sequence_number=1,
            content=f"MainGoal {label}",
            source="manual",
            **common,
        ).id
    raise AssertionError(f"unhandled model {model_name}")


@pytest.fixture
def two_tenants(db):
    """Two fully separate tenants, each owning one row of every model.

    Returns ``{"a": (tenant, {model_name: pk}), "b": (...)}``.
    """
    from persistence.models import Tenant, Workspace

    made = {}
    for label in ("a", "b"):
        tenant = Tenant.objects.create(
            name=f"t-scoped-{label}", slug=f"t-scoped-{label}"
        )
        TenantContext.set_tenant(tenant.id)
        workspace = Workspace.objects.create(tenant=tenant, name=f"ws-{label}")
        made[label] = (
            tenant,
            {name: _create_row(name, tenant, workspace, label) for name in MODELS},
        )
    TenantContext.clear_tenant()
    return made


# ---------------------------------------------------------------------------
# Structural
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model_name", MODELS)
def test_model_inherits_the_tenant_scoped_base(model_name):
    assert issubclass(apps.get_model("application", model_name), TenantScopedModel)


@pytest.mark.parametrize("model_name", MODELS)
def test_tenant_is_a_foreign_key_on_the_same_column(model_name):
    """The FK must reuse the physical ``tenant_id`` column.

    This is what keeps the RLS policies (application/0009, 0013) matching
    without a policy migration — they are written against the column, not the
    Django field.
    """
    field = apps.get_model("application", model_name)._meta.get_field("tenant")

    assert field.many_to_one is True
    assert field.get_attname_column()[1] == "tenant_id"
    assert field.remote_field.model._meta.model_name == "tenant"


@pytest.mark.parametrize("model_name", MODELS)
def test_the_manual_uuid_duplicates_are_gone(model_name):
    """The hand-rolled ``*_id`` UUID columns must not survive as field names.

    Note ``_meta.local_fields`` also contains fields inherited from an abstract
    base (Django copies them onto the concrete model), so it cannot be used to
    tell "declared here" from "inherited" — only these three *names* are
    unambiguous evidence of a leftover manual duplicate, because the base class
    exposes them as FK attnames, never as field names.
    """
    local = {f.name for f in apps.get_model("application", model_name)._meta.local_fields}

    assert {"tenant_id", "created_by_id", "modified_by_id"}.isdisjoint(local)


@pytest.mark.parametrize("model_name", MODELS)
@pytest.mark.parametrize("field_name", ["id", "version", "created_at", "modified_at"])
def test_audit_fields_match_the_base_class(model_name, field_name):
    """The inherited shape must be the base's, not a leftover local override.

    Catches e.g. a surviving ``modified_at = DateTimeField(null=True)``, which
    would look inherited in ``local_fields`` but keep the column nullable.
    """
    from persistence.models import AuditableModel

    model = apps.get_model("application", model_name)
    _n, _p, _a, own = model._meta.get_field(field_name).deconstruct()
    _n, _p, _a, base = AuditableModel._meta.get_field(field_name).deconstruct()

    assert own == base


@pytest.mark.parametrize("model_name", MODELS)
def test_workspace_id_stays_a_plain_uuid_field(model_name):
    """Decision D-5: ``workspace_id`` is deliberately NOT converted to a FK."""
    field = apps.get_model("application", model_name)._meta.get_field("workspace_id")

    assert field.get_internal_type() == "UUIDField"
    assert field.is_relation is False


@pytest.mark.parametrize("model_name", MODELS)
def test_base_manager_is_unscoped(model_name):
    """Django internals (cascade collection, refresh_from_db) must not be scoped.

    ``base_manager_name`` is declared on ``TenantScopedModel.Meta``, which these
    models do not inherit (they declare their own ``Meta``); it resolves through
    ``Options.base_manager``'s MRO fallback instead. Asserted because that
    fallback is invisible in the model source.
    """
    model = apps.get_model("application", model_name)

    assert model._meta.base_manager.name == "unscoped"


@pytest.mark.parametrize("model_name", MODELS)
def test_tenant_indexes_reference_the_field_not_the_attname(model_name):
    """``Index(fields=["tenant_id"])`` passes system checks but fails at DDL time.

    ``_check_local_fields`` accepts an attname, ``Index.create_sql`` does not
    (``Options.get_field`` is keyed on ``field.name``). So a stale ``tenant_id``
    here would only surface during ``migrate``.
    """
    model = apps.get_model("application", model_name)

    for index in model._meta.indexes:
        assert "tenant_id" not in index.fields, (
            f"{model_name}.Meta index {index.name} references the attname "
            "'tenant_id'; use the field name 'tenant'"
        )


# ---------------------------------------------------------------------------
# Behavioural — the actual isolation proof
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", MODELS)
def test_objects_is_tenant_filtered(two_tenants, model_name):
    """Under tenant A's context, tenant B's rows are invisible."""
    model = apps.get_model("application", model_name)
    tenant_a, ids_a = two_tenants["a"]
    _tenant_b, ids_b = two_tenants["b"]
    TenantContext.set_tenant(tenant_a.id)

    visible = set(model.objects.values_list("id", flat=True))

    assert ids_a[model_name] in visible
    assert ids_b[model_name] not in visible


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", MODELS)
def test_objects_is_tenant_filtered_the_other_way_too(two_tenants, model_name):
    """Symmetry check — proves the filter tracks the context, not row order."""
    model = apps.get_model("application", model_name)
    _tenant_a, ids_a = two_tenants["a"]
    tenant_b, ids_b = two_tenants["b"]
    TenantContext.set_tenant(tenant_b.id)

    visible = set(model.objects.values_list("id", flat=True))

    assert ids_b[model_name] in visible
    assert ids_a[model_name] not in visible


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", MODELS)
def test_objects_without_a_context_fails_closed(two_tenants, model_name):
    """No context must raise, never fall back to an unfiltered read."""
    model = apps.get_model("application", model_name)
    TenantContext.clear_tenant()

    with pytest.raises(TenantContextNotSetError):
        list(model.objects.all())


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", MODELS)
def test_unscoped_still_crosses_tenants(two_tenants, model_name):
    """The documented escape hatch keeps working (baseline/state_capture.py)."""
    model = apps.get_model("application", model_name)
    tenant_a, ids_a = two_tenants["a"]
    _tenant_b, ids_b = two_tenants["b"]
    TenantContext.set_tenant(tenant_a.id)

    visible = set(model.unscoped.values_list("id", flat=True))

    assert {ids_a[model_name], ids_b[model_name]} <= visible
