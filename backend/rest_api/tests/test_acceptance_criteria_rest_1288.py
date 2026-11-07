"""#1288 / #1289 — REST surface: structured acceptance criteria + level override."""
from __future__ import annotations

from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Requirement, RequirementLevelSource, Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def env(db):
    tenant = Tenant.objects.create(name="W9 env", slug="w9-env", is_active=True)
    admin = User.objects.create(
        username="w9admin", email="w9@t.test", tenant=tenant
    )
    admin.set_password("w9pass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="W9 WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "workspace": workspace, "username": admin.username}
    finally:
        clear_request_tenant()


def _client(env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": env["username"], "password": "w9pass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create(
    client: APIClient, workspace_id: Any, title: str = "Req", **fields: Any
) -> dict:
    payload = {"workspace_id": str(workspace_id), "title": title, **fields}
    resp = client.post("/api/v1/requirements/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_level_override_sets_a_manual_level(env):
    client = _client(env)
    req = _create(client, env["workspace"].id)
    resp = client.patch(
        f"/api/v1/requirements/{req['id']}/",
        {"level_override": 3},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["level"] == 3
    assert resp.json()["level_source"] == "manual"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_level_override_null_clears_the_manual_level(env):
    """Clearing the override re-derives through the P2/V6 source order.

    A requirement with neither an allocation nor a parent falls through to the
    type default (step 4 of the documented order), so the provenance is
    ``derived_type`` — not the legacy coarse ``derived`` value. The V6 split
    (derived_allocation / derived_hierarchy / derived_type / unresolved) is
    asserted end-to-end by the two sibling tests below.
    """
    client = _client(env)
    req = _create(client, env["workspace"].id)
    client.patch(
        f"/api/v1/requirements/{req['id']}/", {"level_override": 3}, format="json"
    )
    resp = client.patch(
        f"/api/v1/requirements/{req['id']}/", {"level_override": None}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["level_source"] == "derived_type"
    stored = Requirement.unscoped.get(id=req["id"])
    assert stored.level_source == RequirementLevelSource.DERIVED_TYPE


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_level_source_derived_hierarchy_for_a_child(env):
    """V6 order step 3: a requirement below a parent derives one tier down."""
    client = _client(env)
    parent = _create(client, env["workspace"].id, title="Parent")
    child = _create(
        client,
        env["workspace"].id,
        title="Child",
        parent_id=parent["artifact_id"],
    )
    client.patch(
        f"/api/v1/requirements/{child['id']}/", {"level_override": 3}, format="json"
    )
    resp = client.patch(
        f"/api/v1/requirements/{child['id']}/", {"level_override": None}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["level_source"] == "derived_hierarchy"
    # Parent resolves to the type-default first tier (position 1), the child is
    # one position further down the ladder (position 2).
    assert resp.json()["level"] == 2
    assert (
        Requirement.unscoped.get(id=child["id"]).level_source
        == RequirementLevelSource.DERIVED_HIERARCHY
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_level_source_derived_allocation_wins_over_hierarchy(env):
    """V6 order step 2 beats step 3: the allocated element's tier wins."""
    from persistence.models import ArchitectureElement, Artifact, TraceLink

    client = _client(env)
    parent = _create(client, env["workspace"].id, title="Parent")
    req = _create(
        client,
        env["workspace"].id,
        title="Allocated",
        parent_id=parent["artifact_id"],
    )
    # A requirement with a parent already derives from the hierarchy.
    assert (
        Requirement.unscoped.get(id=req["id"]).level_source
        == RequirementLevelSource.DERIVED_HIERARCHY
    )

    tenant, workspace = env["tenant"], env["workspace"]
    element_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    ArchitectureElement.objects.create(
        tenant=tenant,
        artifact=element_artifact,
        workspace=workspace,
        title="Subsystem",
        description="d",
        element_type="subsystem",
    )
    TraceLink.objects.create(
        tenant=tenant,
        source_id=Requirement.unscoped.get(id=req["id"]).artifact_id,
        target_id=element_artifact.id,
        link_type="allocated-to",
    )

    client.patch(
        f"/api/v1/requirements/{req['id']}/", {"level_override": 3}, format="json"
    )
    resp = client.patch(
        f"/api/v1/requirements/{req['id']}/", {"level_override": None}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["level_source"] == "derived_allocation"
    assert resp.json()["level"] == 1
    assert (
        Requirement.unscoped.get(id=req["id"]).level_source
        == RequirementLevelSource.DERIVED_ALLOCATION
    )


def _seed_criteria(env: dict, req_id: str, items: list[dict]) -> None:
    Requirement.unscoped.filter(id=req_id).update(acceptance_criteria_items=items)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_and_patch_a_single_criterion(env):
    client = _client(env)
    req = _create(client, env["workspace"].id)
    _seed_criteria(
        env,
        req["id"],
        [{"text": "a", "fulfilled": False}, {"text": "b", "fulfilled": False}],
    )

    listed = client.get(f"/api/v1/requirements/{req['id']}/acceptance-criteria/")
    assert listed.status_code == 200, listed.content
    assert listed.json()["total"] == 2

    one = client.get(f"/api/v1/requirements/{req['id']}/acceptance-criteria/1/")
    assert one.status_code == 200, one.content
    assert one.json()["criterion"]["text"] == "b"

    patched = client.patch(
        f"/api/v1/requirements/{req['id']}/acceptance-criteria/0/",
        {"fulfilled": True},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["criterion"]["fulfilled"] is True


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_out_of_range_criterion_index_is_404(env):
    client = _client(env)
    req = _create(client, env["workspace"].id)
    _seed_criteria(env, req["id"], [{"text": "a", "fulfilled": False}])
    resp = client.get(f"/api/v1/requirements/{req['id']}/acceptance-criteria/4/")
    assert resp.status_code == 404, resp.content
