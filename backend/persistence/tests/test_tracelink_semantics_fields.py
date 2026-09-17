"""New TraceLink semantics fields and Artifact.copied_from."""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from persistence.models import Artifact, Tenant, Workspace

    tenant = Tenant.objects.create(name="semantics-fields")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")

    def artifact(kind: str = "Requirement") -> Artifact:
        # Artifact itself has no "title" field (that lives on the per-type
        # companion model, e.g. Requirement.title); the bare Artifact row is
        # all TraceLink/copied_from need here.
        return Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type=kind
        )

    yield {"tenant": tenant, "workspace": ws, "artifact": artifact}
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_new_trace_link_fields_default_to_empty(env):
    from persistence.models import TraceLink

    link = TraceLink.objects.create(
        tenant=env["tenant"],
        source=env["artifact"](),
        target=env["artifact"](),
        link_type="derives-from",
    )
    assert link.rationale == ""
    assert link.suspect_flagged_at is None
    assert link.suspect_source_change is None


@pytest.mark.django_db
def test_rationale_round_trips(env):
    from persistence.models import TraceLink

    link = TraceLink.objects.create(
        tenant=env["tenant"],
        source=env["artifact"](),
        target=env["artifact"](),
        link_type="derives-from",
        rationale="Derived during the 2026-Q3 decomposition workshop.",
    )
    link.refresh_from_db()
    assert link.rationale.startswith("Derived during")


@pytest.mark.django_db
def test_suspect_marker_fields_round_trip(env):
    from persistence.models import TraceLink

    audit_id = uuid.uuid4()
    now = timezone.now()
    link = TraceLink.objects.create(
        tenant=env["tenant"],
        source=env["artifact"](),
        target=env["artifact"](),
        link_type="derives-from",
        suspect_flagged_at=now,
        suspect_source_change=audit_id,
    )
    link.refresh_from_db()
    assert link.suspect_flagged_at == now
    assert link.suspect_source_change == audit_id


@pytest.mark.django_db
def test_copied_from_links_two_artifacts(env):
    original = env["artifact"]()
    copy = env["artifact"]()
    copy.copied_from = original
    copy.save(update_fields=["copied_from"])
    copy.refresh_from_db()
    assert copy.copied_from_id == original.id
    assert list(original.copies.all()) == [copy]


@pytest.mark.django_db
def test_deleting_the_original_keeps_the_copy(env):
    original = env["artifact"]()
    copy = env["artifact"]()
    copy.copied_from = original
    copy.save(update_fields=["copied_from"])
    original.delete()
    copy.refresh_from_db()
    assert copy.copied_from_id is None


@pytest.mark.django_db
def test_workspace_decomposition_default_is_no_longer_a_retired_type():
    from persistence.models import Workspace

    field = Workspace._meta.get_field("decomposition_link_type")
    assert field.default == "decomposes"
