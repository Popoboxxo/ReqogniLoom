"""Error-path REST coverage for ArchitectureElementViewSet (views.py).

leaf_id : COMP-RA-AE (ArchitectureElementViewSet)
req_id  : REQ-L2-RA-001, REQ-L1-042, REQ-L1-044, REQ-L1-090, REQ-L1-091,
          REQ-L3-RF004-004, REQ-171

``test_architecture_element_viewset_rest.py`` pins the CRUD happy paths and the
soft-delete contract. This module drives the same ViewSet through the real
middleware stack for the branches that suite leaves open:

- service-error mapping on every handler — the three mapped domain errors get
  their status, anything unexpected becomes a masked 500 with no internals in
  the body;
- the attribute-definition guard in front of ``create`` (spec section 5);
- the hierarchy invariants on ``PATCH`` (dangling parent, the single-root I5
  guard behind an explicit detach, and the re-parent happy path);
- the ``?from_version=`` / ``?depth=`` parsing guards on ``diff`` and
  ``requirement-bundle``;
- the compressed-bundle branches — async dispatch without a configured broker
  (503) and the mapped errors surfacing from the compression service;
- the workflow transition echo of the refreshed entity (GH-443).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from application.services import (
    ArchitectureService,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_BASE = "/api/v1/architecture/"

#: Required, non-core attribute used to open the definition guard branch.
_REQUIRED_EXTENDED = {
    "name": "sap_id",
    "kind": "extended",
    "type": "text",
    "required": True,
}


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"AE-{suffix}", slug=f"ae-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"ae-{suffix}", email=f"ae-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="AE WS", preset={"name": "extended"}
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


def _create_element(client: APIClient, workspace: Workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "AE element",
        "description": "a subsystem",
        "element_type": "component",
        **overrides,
    }
    resp = client.post(_BASE, payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


# ---------------------------------------------------------------------------
# create — service error mapping and the attribute-definition guard
# ---------------------------------------------------------------------------


def test_create_with_unknown_workspace_is_404_not_a_crash() -> None:
    """A workspace_id that resolves to nothing is a mapped 404."""
    _, user, _ = _scenario()
    resp = _client(user).post(
        _BASE,
        {"workspace_id": str(uuid.uuid4()), "title": "Orphan"},
        format="json",
    )
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_create_with_dangling_parent_id_is_rejected() -> None:
    """I3: a parent_id that names no element in the workspace never persists."""
    _, user, workspace = _scenario()
    resp = _client(user).post(
        _BASE,
        {
            "workspace_id": str(workspace.id),
            "title": "Child of nothing",
            "parent_id": str(uuid.uuid4()),
        },
        format="json",
    )
    assert resp.status_code in (400, 404), resp.content
    assert "error" in resp.json()


def test_create_without_a_required_extended_attribute_is_400(
    tenant_fixture, workspace_fixture, admin_client
) -> None:
    """The spec-section-5 definition guard answers 400 naming the attribute."""
    GlobalAttributeDefinitionStore().initialize(
        tenant_fixture.id,
        "ArchitectureElement",
        "standard",
        [_REQUIRED_EXTENDED],
    )

    resp = admin_client.post(
        _BASE,
        {"workspace_id": str(workspace_fixture.id), "title": "No sap id"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "sap_id" in resp.json()["error"]["message"]


def test_create_maps_an_unexpected_error_to_a_masked_500() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ArchitectureService,
        "create_architecture_element",
        side_effect=RuntimeError("db exploded"),
    ):
        resp = _client(user).post(
            _BASE,
            {"workspace_id": str(workspace.id), "title": "Boom"},
            format="json",
        )

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "db exploded" not in resp.content.decode()


# ---------------------------------------------------------------------------
# list — service error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (ValidationError("workspace unreadable"), 400),
        (NotFoundError("workspace gone"), 404),
        (PermissionDeniedError("no access"), 403),
    ],
)
def test_list_maps_mapped_service_errors(exc: Exception, expected_status: int) -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ArchitectureService, "list_architecture_elements", side_effect=exc
    ):
        resp = _client(user).get(f"{_BASE}?workspace_id={workspace.id}")

    assert resp.status_code == expected_status, resp.content
    assert "error" in resp.json()


def test_list_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ArchitectureService,
        "list_architecture_elements",
        side_effect=RuntimeError("boom"),
    ):
        resp = _client(user).get(f"{_BASE}?workspace_id={workspace.id}")

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


def test_retrieve_maps_an_unexpected_value_error_to_404() -> None:
    """A non-domain ValueError from the service is the 404 branch, not a 500."""
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch.object(
        ArchitectureService,
        "get_architecture_element",
        side_effect=ValueError("malformed id"),
    ):
        resp = _client(user).get(f"{_BASE}{created['id']}/")

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# partial_update — guards, hierarchy invariants and sentinel forwarding
# ---------------------------------------------------------------------------


def test_patch_with_an_unknown_field_is_400() -> None:
    """An undeclared key is refused instead of silently dropped (#269)."""
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)

    resp = _client(user).patch(
        f"{_BASE}{created['id']}/", {"no_such_field": 1}, format="json"
    )

    assert resp.status_code == 400, resp.content
    details = {d["field"] for d in resp.json()["error"]["details"]}
    assert "no_such_field" in details


def test_patch_with_a_dangling_parent_id_is_400() -> None:
    """REQ-L1-044: the serializer runs the hierarchy invariant on update."""
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)

    resp = _client(user).patch(
        f"{_BASE}{created['id']}/",
        {"parent_id": str(uuid.uuid4())},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    details = {d["field"] for d in resp.json()["error"]["details"]}
    assert "parent_id" in details


def test_patch_reparents_an_element_onto_a_higher_level() -> None:
    """Re-parent happy path: parent_id reaches the service and is persisted.

    I2 requires the new parent to sit on a strictly lower level, so the deepest
    node is the one moved (here: a grandchild up to the root).
    """
    _, user, workspace = _scenario()
    client = _client(user)
    root = _create_element(client, workspace, title="Root")
    child = _create_element(client, workspace, title="Child", parent_id=root["id"])
    grandchild = _create_element(
        client, workspace, title="Grandchild", parent_id=child["id"]
    )

    resp = client.patch(
        f"{_BASE}{grandchild['id']}/",
        {"parent_id": root["id"], "change_reason": "re-parent onto the root"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["parent_id"] == root["id"]


def test_patch_detaching_a_child_would_create_a_second_root() -> None:
    """I5: one root per workspace — the explicit detach is a mapped 400."""
    _, user, workspace = _scenario()
    client = _client(user)
    root = _create_element(client, workspace, title="Root")
    child = _create_element(client, workspace, title="Child", parent_id=root["id"])

    resp = client.patch(
        f"{_BASE}{child['id']}/", {"parent_id": None}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert "error" in resp.json()


def test_patch_forwards_asil_level_and_make_or_buy_when_present() -> None:
    """Presence-checked forwarding: an explicit value must reach the column."""
    _, user, workspace = _scenario()
    client = _client(user)
    created = _create_element(client, workspace, asil_level="QM")

    resp = client.patch(
        f"{_BASE}{created['id']}/",
        {"asil_level": "C", "make_or_buy": "Buy", "change_reason": "review"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["asil_level"] == "C"
    assert resp.json()["make_or_buy"] == "Buy"


# ---------------------------------------------------------------------------
# destroy — unexpected error mapping
# ---------------------------------------------------------------------------


def test_delete_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch.object(
        ArchitectureService,
        "delete_architecture_element",
        side_effect=RuntimeError("outdate failed"),
    ):
        resp = _client(user).delete(f"{_BASE}{created['id']}/")

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# allocation-coverage — error mapping (REQ-L1-042)
# ---------------------------------------------------------------------------


def test_allocation_coverage_maps_an_unexpected_value_error_to_404() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch(
        "application.trace_link_service.TraceLinkService.get_allocation_coverage",
        side_effect=ValueError("bad id"),
    ):
        resp = _client(user).get(f"{_BASE}{created['id']}/allocation-coverage/")

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_allocation_coverage_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch(
        "application.trace_link_service.TraceLinkService.get_allocation_coverage",
        side_effect=RuntimeError("boom"),
    ):
        resp = _client(user).get(f"{_BASE}{created['id']}/allocation-coverage/")

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# diff — guard + error mapping (REQ-L1-090 / REQ-L1-091)
# ---------------------------------------------------------------------------


def test_diff_of_an_unknown_element_is_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"{_BASE}{uuid.uuid4()}/diff/")
    assert resp.status_code == 404, resp.content


def test_diff_rejects_a_non_integer_version() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)

    resp = _client(user).get(f"{_BASE}{created['id']}/diff/?from_version=abc")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_diff_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch(
        "rest_api.views.ArtifactDiffService.diff", side_effect=RuntimeError("boom")
    ):
        resp = _client(user).get(f"{_BASE}{created['id']}/diff/")

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# versions — guard + error mapping
# ---------------------------------------------------------------------------


def test_versions_of_an_unknown_element_is_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"{_BASE}{uuid.uuid4()}/versions/")
    assert resp.status_code == 404, resp.content


def test_versions_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch(
        "rest_api.views.ArtifactDiffService.list_versions",
        side_effect=RuntimeError("boom"),
    ):
        resp = _client(user).get(f"{_BASE}{created['id']}/versions/")

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# requirement-bundle — parsing guards and the compressed branches
# ---------------------------------------------------------------------------


def test_requirement_bundle_rejects_a_non_integer_depth() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)

    resp = _client(user).get(f"{_BASE}{created['id']}/requirement-bundle/?depth=soon")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_requirement_bundle_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch(
        "rest_api.views.RequirementBundleQueryService.get_bundle",
        side_effect=RuntimeError("boom"),
    ):
        resp = _client(user).get(f"{_BASE}{created['id']}/requirement-bundle/")

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


def test_requirement_bundle_compressed_without_a_broker_is_503() -> None:
    """A dispatch that cannot enqueue reports 503, not a fake task_id."""
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch(
        "application.bundle_compression_service.BundleCompressionService.compress_async",
        return_value={"error": {"code": "SERVICE_UNAVAILABLE"}},
    ):
        resp = _client(user).get(
            f"{_BASE}{created['id']}/requirement-bundle/"
            "?mode=compressed&async=true"
        )

    assert resp.status_code == 503, resp.content


def test_requirement_bundle_compressed_maps_a_not_found_error() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch(
        "application.bundle_compression_service.BundleCompressionService.compress",
        side_effect=NotFoundError("workspace gone"),
    ):
        resp = _client(user).get(
            f"{_BASE}{created['id']}/requirement-bundle/?mode=compressed"
        )

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_requirement_bundle_compressed_maps_a_validation_error() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch(
        "application.bundle_compression_service.BundleCompressionService.compress",
        side_effect=ValidationError("nothing to compress"),
    ):
        resp = _client(user).get(
            f"{_BASE}{created['id']}/requirement-bundle/?mode=compressed"
        )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_requirement_bundle_compressed_maps_an_unexpected_error_to_500() -> None:
    _, user, workspace = _scenario()
    created = _create_element(_client(user), workspace)
    with patch(
        "application.bundle_compression_service.BundleCompressionService.compress",
        side_effect=RuntimeError("llm down"),
    ):
        resp = _client(user).get(
            f"{_BASE}{created['id']}/requirement-bundle/?mode=compressed"
        )

    assert resp.status_code == 500, resp.content
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# workflow transitions — the refreshed-entity echo (REQ-171)
# ---------------------------------------------------------------------------


def test_transition_echoes_the_refreshed_element() -> None:
    """POST transitions/ re-serialises the element after the state change."""
    _, user, workspace = _scenario()
    client = _client(user)
    created = _create_element(client, workspace, title="Transition me")

    init = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": "ArchitectureElement"},
        format="json",
    )
    assert init.status_code == 201, init.content

    available = client.get(f"{_BASE}{created['id']}/transitions/")
    assert available.status_code == 200, available.content
    allowed = available.json()["allowed_transitions"]
    assert allowed, available.content
    target_state = allowed[0]["target_state"]

    resp = client.post(
        f"{_BASE}{created['id']}/transitions/",
        {"target_state": target_state, "change_reason": "review round"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["new_state"] == target_state
    assert body["architecture_element"]["id"] == created["id"]
    assert body["architecture_element"]["title"] == "Transition me"
