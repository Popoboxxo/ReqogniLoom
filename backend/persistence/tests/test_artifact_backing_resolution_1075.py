"""Entity -> Artifact resolution must not depend on a hand-maintained list (#1075).

``pl_tracelink`` has only ``source_id``/``target_id``; endpoint *types* are
resolved through the union table ``pl_artifact``. Every specialised table,
however, owns its own primary key **and** a backing ``Artifact`` row with a
**different** primary key. The measured production state was::

    icd_icd gesamt      : 95
    davon in pl_artifact : 0     <-- other UUIDs
    pl_requirement       : 903 rows, 0 of them in pl_artifact
    pl_testcase          :  32 rows, 0 of them in pl_artifact

So a client that read ``GET /icds/{id}/`` held a UUID the trace graph could not
resolve, and ``POST /tracelinks/`` answered 404 for an entity that demonstrably
exists. Requirements only worked because a caller-side resolver happened to
list them.

``persistence.artifact_backing.resolve_backing_artifact_id`` is the registry-
driven fallback. These tests pin:

* an ICD id resolves to its backing Artifact id;
* the *same* divergence exists for Requirement and TestCase (it is one bug, not
  an ICD quirk);
* an id that is **already** an ``Artifact`` id still resolves to itself, so the
  1982 existing artifact-based TraceLinks are untouched by the fallback;
* a cross-tenant entity id does not resolve.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.artifact_backing import (
    ARTIFACT_TYPE_MODELS,
    resolve_backing_artifact_id,
)
from persistence.models import Artifact, Requirement, Tenant, TestCase, TraceLink, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="resolve-1075", slug=f"r1075-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
def workspace(tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def other_tenant() -> Tenant:
    return Tenant.objects.create(
        name="resolve-1075-other", slug=f"r1075o-{uuid.uuid4().hex[:8]}"
    )


def _activate(tenant: Tenant) -> None:
    TenantContext.set_tenant(tenant.id)


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    _activate(tenant)
    return Artifact.objects.create(
        tenant_id=tenant.id, workspace=workspace, artifact_type=artifact_type
    )


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------


def test_icd_entity_id_resolves_to_its_backing_artifact(tenant, workspace):
    """The exact #1075 repro, at the level this change owns.

    `Icd.id` and its backing `Artifact.id` are different UUIDs, and the ICD's
    own UUID appears nowhere in `pl_artifact` — which is exactly why the trace
    graph could not resolve it.
    """
    from icd.models import Icd

    _activate(tenant)
    artifact = _artifact(tenant, workspace, "Icd")
    icd = Icd.objects.create(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        artifact=artifact,
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
        name="IF-1",
    )
    assert icd.id != artifact.id
    assert not Artifact.objects.filter(id=icd.id).exists()

    assert resolve_backing_artifact_id(icd.id) == artifact.id


def test_the_same_divergence_exists_for_requirement_and_testcase(tenant, workspace):
    """It is one bug with three witnesses, not an ICD quirk (#1075 follow-up).

    The issue suspected the parallel rows were ICD-specific; they are not. A
    Requirement and a TestCase each hold an id that is absent from
    `pl_artifact` in exactly the same way, so a resolver that special-cases ICD
    would have left the general hole open.
    """
    requirement_artifact = _artifact(tenant, workspace, "Requirement")
    requirement = Requirement.objects.create(
        tenant_id=tenant.id,
        artifact=requirement_artifact,
        title="R",
        description="d",
    )
    testcase_artifact = _artifact(tenant, workspace, "TestCase")
    testcase = TestCase.objects.create(
        tenant_id=tenant.id, artifact=testcase_artifact, title="TC"
    )

    for entity in (requirement, testcase):
        assert entity.id != entity.artifact_id
        assert not Artifact.objects.filter(id=entity.id).exists()
        assert resolve_backing_artifact_id(entity.id) == entity.artifact_id


def test_an_artifact_id_resolves_to_itself(tenant, workspace):
    """The fallback must never move an id that already works.

    All 1982 production TraceLinks point at `pl_artifact` ids; the resolver is
    a *fallback* behind the existing `pl_artifact` probe, so those keep
    resolving to exactly the same target.
    """
    source = _artifact(tenant, workspace, "Requirement")
    target = _artifact(tenant, workspace, "Requirement")
    link = TraceLink.objects.create(
        tenant_id=tenant.id,
        source=source,
        target=target,
        link_type="derives-from",
    )

    for endpoint in (link.source_id, link.target_id):
        assert Artifact.objects.filter(id=endpoint).exists()
        # The Artifact probe is what the resolver runs after; an artifact id
        # belongs to no subtype table, so the fallback returns None and the
        # caller keeps the id it already had.
        assert resolve_backing_artifact_id(endpoint) is None
    assert str(link.source_id) == str(source.id)


def test_existing_artifact_based_links_survive_the_fallback(tenant, workspace):
    """An artifact-based link is untouched by adding the subtype fallback."""
    first = _artifact(tenant, workspace, "Requirement")
    second = _artifact(tenant, workspace, "TestCase")
    before = set(
        TraceLink.objects.filter(tenant_id=tenant.id).values_list("id", flat=True)
    )
    link = TraceLink.objects.create(
        tenant_id=tenant.id,
        source=first,
        target=second,
        link_type="verifies",
    )

    # Exercise the fallback over the very same ids the existing graph uses.
    for endpoint in (first.id, second.id):
        fallback = resolve_backing_artifact_id(endpoint)
        assert fallback in (None, endpoint)

    after = set(
        TraceLink.objects.filter(tenant_id=tenant.id).values_list("id", flat=True)
    )
    assert after - before == {link.id}
    assert link.source_id == first.id
    assert link.target_id == second.id


def test_a_cross_tenant_entity_id_does_not_resolve(
    tenant, other_tenant, workspace
):
    """No existence oracle across tenants."""
    from icd.models import Icd

    _activate(tenant)
    artifact = _artifact(tenant, workspace, "Icd")
    icd = Icd.objects.create(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        artifact=artifact,
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
        name="IF-x",
    )

    _activate(other_tenant)
    assert resolve_backing_artifact_id(icd.id) is None


def test_an_entity_without_a_backing_row_resolves_to_none(tenant, workspace):
    from icd.models import Icd

    _activate(tenant)
    icd = Icd.objects.create(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        artifact=None,
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
        name="IF-orphan",
    )
    assert resolve_backing_artifact_id(icd.id) is None


def test_unknown_and_malformed_ids_resolve_to_none(tenant):
    _activate(tenant)
    assert resolve_backing_artifact_id(uuid.uuid4()) is None
    assert resolve_backing_artifact_id("not-a-uuid") is None
    assert resolve_backing_artifact_id(None) is None


def test_the_registry_covers_every_type_with_a_backing_artifact():
    """The whole point: no hand-maintained per-type list may be needed."""
    assert "Icd" in ARTIFACT_TYPE_MODELS
    assert "Requirement" in ARTIFACT_TYPE_MODELS
    assert "TestCase" in ARTIFACT_TYPE_MODELS
    from django.apps import apps

    for artifact_type, (app_label, model_name) in ARTIFACT_TYPE_MODELS.items():
        model = apps.get_model(app_label, model_name)
        assert model is not None, artifact_type
        try:
            model._meta.get_field("artifact")
        except Exception:  # noqa: BLE001
            pytest.fail(f"{artifact_type} has no backing 'artifact' field")


def test_candidate_types_restricts_the_probe(tenant, workspace):
    requirement_artifact = _artifact(tenant, workspace, "Requirement")
    requirement = Requirement.objects.create(
        tenant_id=tenant.id,
        artifact=requirement_artifact,
        title="R",
        description="d",
    )

    assert resolve_backing_artifact_id(requirement.id) == requirement_artifact.id
    assert (
        resolve_backing_artifact_id(requirement.id, candidate_types=["Icd"])
        is None
    )
