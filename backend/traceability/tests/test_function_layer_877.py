"""#877 / Plan B B3-T3 — the functional architecture layer.

``performs`` (element -> function) and the ``satisfies`` function pair
(Requirement -> ``ArchitectureElement:function``) are pinned end to end: both
edges are creatable through ``POST /api/v1/trace-links/`` in a real workspace
catalog, a non-function target is a 400 naming ``ArchitectureElement:function``,
the ``satisfies`` pair does not widen to components, and the audit-rule fix
(review finding R-B3-1) holds — TRACE-P3 accepts the incoming ``satisfies`` as
justification for a **function** element (otherwise every function blocks the
baseline) while a component without ``allocated-to`` stays a BLOCKER, and
ARCH-003 emits nothing for a function that has no allocation.

KA-G-10: every test uses a real ``Workspace`` row (and a real
``ArchitectureElement`` row where the sub-type tag must be derived).
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

import traceability.audit.rules.decomposition_consistency  # noqa: F401  (registers ARCH-003)
import traceability.audit.rules.trace_derivation_allocation  # noqa: F401  (registers TRACE-P3)
from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from traceability.audit import RuleEngine
from traceability.audit.registry import ARCH_003, TRACE_P3
from traceability.tests.conftest import (
    active_tenant,
    make_requirement,
    make_trace_link,
)

_PASSWORD = "hunter2pass"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _rest_scenario() -> tuple[Tenant, User, Workspace]:
    """Tenant + admin user + one extended workspace with a seeded catalog."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"T-{suffix}", slug=f"fn-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"fn-{suffix}", email=f"fn-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Function WS", preset={"name": "extended"}
        )
        # Link validation is always-on: an unprovisioned workspace has an empty
        # link-type catalog and rejects every trace link.
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _element_rows(
    tenant: Tenant,
    workspace: Workspace,
    *,
    element_type: str = "component",
    parent: ArchitectureElement | None = None,
    title: str = "Element",
) -> tuple[Artifact, ArchitectureElement]:
    """A real ``ArchitectureElement`` (sub-type rows drive the ``Typ:Subtag``).

    REST-path helper: the ORM is reached outside a tenant context, so the
    request tenant is armed and cleared around the two inserts.
    """
    set_request_tenant(tenant.id)
    try:
        return _element(tenant, workspace, element_type, parent, title)
    finally:
        clear_request_tenant()


def _element(
    tenant: Tenant,
    workspace: Workspace,
    element_type: str = "component",
    parent: ArchitectureElement | None = None,
    title: str = "Element",
) -> tuple[Artifact, ArchitectureElement]:
    """Same row, for callers already running inside ``active_tenant``."""
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    element = ArchitectureElement.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact=artifact,
        title=title,
        element_type=element_type,
        parent=parent,
    )
    return artifact, element


def _requirement_artifact(
    tenant: Tenant, workspace: Workspace, title: str = "Req"
) -> Artifact:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=tenant, workspace=workspace, artifact=artifact, title=title
        )
        return artifact
    finally:
        clear_request_tenant()


def _findings(result, rule_id: str) -> list:
    return [f for f in result.findings if f.rule_id == rule_id]


# ---------------------------------------------------------------------------
# REST: performs / satisfies through the workspace catalog
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_component_performs_function() -> None:
    tenant, user, workspace = _rest_scenario()
    component, _ = _element_rows(tenant, workspace, title="Sensor")
    function, _ = _element_rows(
        tenant, workspace, element_type="function", title="Measure"
    )

    response = _client(user).post(
        "/api/v1/trace-links/",
        {
            "source_id": str(component.id),
            "target_id": str(function.id),
            "link_type": "performs",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["link_type"] == "performs"


@pytest.mark.django_db
def test_performs_rejects_non_function_target() -> None:
    tenant, user, workspace = _rest_scenario()
    component, _ = _element_rows(tenant, workspace, title="Sensor")
    other_component, _ = _element_rows(tenant, workspace, title="Actuator")

    response = _client(user).post(
        "/api/v1/trace-links/",
        {
            "source_id": str(component.id),
            "target_id": str(other_component.id),
            "link_type": "performs",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "ArchitectureElement:function" in response.content.decode()


@pytest.mark.django_db
def test_requirement_satisfies_function() -> None:
    tenant, user, workspace = _rest_scenario()
    requirement = _requirement_artifact(tenant, workspace)
    function, _ = _element_rows(
        tenant, workspace, element_type="function", title="Measure"
    )

    response = _client(user).post(
        "/api/v1/trace-links/",
        {
            "source_id": str(requirement.id),
            "target_id": str(function.id),
            "link_type": "satisfies",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["link_type"] == "satisfies"


@pytest.mark.django_db
def test_requirement_satisfies_component_rejected() -> None:
    """The function pair must not widen ``satisfies`` to every element type."""
    tenant, user, workspace = _rest_scenario()
    requirement = _requirement_artifact(tenant, workspace)
    component, _ = _element_rows(tenant, workspace, title="Sensor")

    response = _client(user).post(
        "/api/v1/trace-links/",
        {
            "source_id": str(requirement.id),
            "target_id": str(component.id),
            "link_type": "satisfies",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "ArchitectureElement:function" in response.content.decode()


# ---------------------------------------------------------------------------
# Audit: TRACE-P3 / ARCH-003 with the functional layer
# ---------------------------------------------------------------------------


def _run(tenant: Tenant, workspace: Workspace):
    return RuleEngine().run(
        tier="extended",
        workspace_id=str(workspace.id),
        tenant_id=str(tenant.id),
    )


@pytest.mark.django_db
def test_trace_p3_accepts_satisfies_for_function(tenant_a, workspace_a) -> None:
    """R-B3-1: a function is justified by an incoming ``satisfies``.

    The component beside it carries no ``allocated-to``, so it must still be a
    TRACE-P3 BLOCKER — the widening is limited to function elements.
    """
    with active_tenant(tenant_a):
        root_artifact, root = _element(
            tenant_a, workspace_a, element_type="subsystem", title="System"
        )
        function_artifact, _function = _element(
            tenant_a,
            workspace_a,
            element_type="function",
            parent=root,
            title="Measure",
        )
        component_artifact, _component = _element(
            tenant_a, workspace_a, parent=root, title="Sensor"
        )
        requirement_artifact, _requirement = make_requirement(
            tenant_a, workspace_a, title="Measure the signal"
        )
        # ``make_trace_link`` bypasses the catalog — the rule only checks that
        # the edge exists (endpoint legality is the catalog's job).
        make_trace_link(
            requirement_artifact, function_artifact, tenant_a, "satisfies"
        )

        result = _run(tenant_a, workspace_a)

    flagged = {
        artifact_id
        for finding in _findings(result, TRACE_P3)
        for artifact_id in finding.artifact_ids
    }
    assert str(function_artifact.id) not in flagged
    assert str(component_artifact.id) in flagged
    # Sanity: the root has no allocation either and stays flagged.
    assert str(root_artifact.id) in flagged


@pytest.mark.django_db
def test_arch_003_ignores_function_without_allocation(tenant_a, workspace_a) -> None:
    """A function element is not allocated a Requirement, so ARCH-003 is silent.

    ARCH-003 fires on a decomposition edge only when a Requirement allocated to
    the child fails to derive from a Requirement of the parent. A function with
    no allocation has nothing to reconcile, and its incoming ``satisfies`` is
    not an allocation — the rule must not invent a finding.
    """
    with active_tenant(tenant_a):
        _root_artifact, root = _element(
            tenant_a, workspace_a, element_type="subsystem", title="System"
        )
        function_artifact, _function = _element(
            tenant_a,
            workspace_a,
            element_type="function",
            parent=root,
            title="Measure",
        )
        requirement_artifact, _requirement = make_requirement(
            tenant_a, workspace_a, title="Measure"
        )
        make_trace_link(
            requirement_artifact, function_artifact, tenant_a, "satisfies"
        )

        result = _run(tenant_a, workspace_a)

    assert _findings(result, ARCH_003) == []
