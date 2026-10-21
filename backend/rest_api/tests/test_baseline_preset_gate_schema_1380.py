"""#1380 gate: the baseline preset gate is truthful in the published schema.

The OpenAPI document advertised ``GET``/``POST /api/v1/baselines/`` (and
``GET /api/v1/baselines/{id}/``) unconditionally, with only the generic
"Resource not found." blanket for ``404``. At runtime the preset gate hides the
whole family in presets that do not enable ``preset_endpoint_key =
"baselines"``, and the flat collection route cannot even resolve a preset when
``workspace_id`` is omitted. The schema therefore promised an endpoint that does
not exist for that caller.

This module pins both halves of the fix:

* **Runtime** — the 404 conditions really exist, and the preset-enabled happy
  path is untouched (the fix documents the gate; it does not open or weaken it).
* **Schema** — the generated document now names the preset condition on the
  ``404`` of all three operations, uses one shared description, and declares
  ``workspace_id`` as a required query parameter on ``list``.

Empirical proof of the runtime behaviour (measured with the tests below,
``2026-10-21``, project preset = the workspace's ``preset["name"]``):

| Request                                             | Preset   | Status | Body (measured, excerpt)                                                     |
|-----------------------------------------------------|----------|--------|------------------------------------------------------------------------------|
| ``GET /api/v1/baselines/?workspace_id=<minimal>``    | minimal  | 404    | ``{"error": {"code": "NOT_FOUND", "message": "The requested API endpoint does not exist.", "details": []}}`` |
| ``GET /api/v1/baselines/`` (no ``workspace_id``)     | minimal  | 404    | same envelope, byte-identical                                                |
| ``GET /api/v1/baselines/`` (no ``workspace_id``)     | standard | 404    | same envelope, byte-identical                                                |
| ``GET /api/v1/baselines/`` (no ``workspace_id``)     | extended | 404    | same envelope, byte-identical                                                |
| ``GET /api/v1/baselines/?workspace_id=<standard>``   | standard | 200    | ``{"count":0,"next":null,"previous":null,"page_size":25,"max_page_size":100,"results":[]}`` |
| ``GET /api/v1/baselines/?workspace_id=<extended>``   | extended | 200    | same empty pagination envelope                                               |
| ``POST /api/v1/baselines/`` (enabled workspace)      | extended | 201    | ``{"id": "...", "workspace_id": "...", "scope": "project", "version": 1, ...}`` + ``ETag`` |
| ``GET /api/v1/baselines/{id}/`` (enabled workspace)  | extended | 200    | baseline detail incl. ``entries``                                            |
| ``POST /api/v1/baselines/`` (no ``workspace_id``)    | any      | 404    | same opaque envelope, answered before serializer validation                  |

The 404 body is the *same* envelope ``handler404`` renders for an unrouted path
(:data:`rest_api.not_found.ROUTE_NOT_FOUND_MESSAGE`): a hidden endpoint, an
unknown/missing workspace and an unknown baseline id are deliberately
indistinguishable, so no probe can tell "hidden by preset" from "does not
exist". Both resolvers share that body by design and this change must not
alter it.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.not_found import ROUTE_NOT_FOUND_MESSAGE

pytestmark = pytest.mark.django_db


#: The collection path whose operations this gate is about.
_COLLECTION_PATH = "/api/v1/baselines/"
#: The detail path (read-only in this module — ``retrieve`` gates on the row's
#: own workspace, so it needs no ``workspace_id``).
_DETAIL_PATH = "/api/v1/baselines/{id}/"

_OPAQUE_404_MESSAGE = ROUTE_NOT_FOUND_MESSAGE["en"]


# ---------------------------------------------------------------------------
# Runtime helpers
# ---------------------------------------------------------------------------


def _workspace_with_admin(tenant: Tenant, user: User, tier: str) -> Workspace:
    """Create a workspace of *tier* in *tenant* and make *user* its admin."""
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant,
            name=f"gate1380-{tier}-{uuid.uuid4().hex[:8]}",
            preset={"name": tier},
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
        return workspace
    finally:
        clear_request_tenant()


def _assert_opaque_404(response) -> None:
    """The body is the shared route-miss envelope, verbatim."""
    assert response.status_code == 404, response.content
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == _OPAQUE_404_MESSAGE


# ---------------------------------------------------------------------------
# Runtime: the gate exists (and is not weakened)
# ---------------------------------------------------------------------------


class TestBaselinePresetGateRuntime:
    """Proves the 404 conditions the schema now documents."""

    def test_minimal_preset_collection_answers_404(
        self, authed_client: APIClient, tenant: Tenant
    ) -> None:
        """(a) ``?workspace_id=<minimal workspace>`` -> 404."""
        user = User.objects.get(username="bundleadmin")
        minimal = _workspace_with_admin(tenant, user, "minimal")

        response = authed_client.get(
            _COLLECTION_PATH, {"workspace_id": str(minimal.id)}
        )

        _assert_opaque_404(response)

    @pytest.mark.parametrize("tier", ["minimal", "standard", "extended"])
    def test_missing_workspace_id_answers_404_in_every_preset(
        self, authed_client: APIClient, tenant: Tenant, tier: str
    ) -> None:
        """(b) no ``workspace_id`` -> 404 in *every* preset.

        The gate substitutes the caller's tenant id for the missing workspace
        id, which resolves to no workspace at all — so the preset tier of the
        tenant's workspaces cannot rescue the request. Parametrised over all
        three tiers to pin that this is *not* a minimal-preset behaviour.
        """
        user = User.objects.get(username="bundleadmin")
        _workspace_with_admin(tenant, user, tier)

        response = authed_client.get(_COLLECTION_PATH)

        _assert_opaque_404(response)

    @pytest.mark.parametrize("tier", ["standard", "extended"])
    def test_baseline_enabled_preset_still_answers_200(
        self, authed_client: APIClient, tenant: Tenant, tier: str
    ) -> None:
        """(c) a preset that enables baselines keeps answering 200.

        Guards against the one wrong fix for #1380: opening the gate so the
        documented endpoint always exists. The gate stays closed; only its
        documentation changed.
        """
        user = User.objects.get(username="bundleadmin")
        workspace = _workspace_with_admin(tenant, user, tier)

        response = authed_client.get(
            _COLLECTION_PATH, {"workspace_id": str(workspace.id)}
        )

        assert response.status_code == 200, response.content
        assert "results" in response.json()

    def test_create_and_detail_happy_path_unchanged(
        self, authed_client: APIClient, workspace: Workspace
    ) -> None:
        """``POST`` -> 201 and ``GET {id}`` -> 200 on an enabled workspace.

        ``workspace`` (the shared fixture) is ``extended``, where baselines are
        enabled. The ``override_reason`` is unrelated to this gate: it only
        waives the SE-Auditor's finding rules for the empty fixture workspace.
        """
        created = authed_client.post(
            _COLLECTION_PATH,
            {
                "workspace_id": str(workspace.id),
                "scope": "project",
                "name": f"gate1380-{uuid.uuid4().hex[:8]}",
                "override_reason": "accepted deviation for gate fixture",
            },
            format="json",
        )
        assert created.status_code == 201, created.content
        baseline_id = created.json()["id"]

        detail = authed_client.get(f"/api/v1/baselines/{baseline_id}/")

        assert detail.status_code == 200, detail.content
        assert detail.json()["id"] == baseline_id

    def test_create_without_workspace_id_answers_404(
        self, authed_client: APIClient
    ) -> None:
        """The create route's own ``workspace_id`` prerequisite, same body.

        ``POST /api/v1/baselines/`` has no workspace in its path either, so an
        omitted body ``workspace_id`` reaches the same tenant-id fallback and
        answers the same opaque 404 — before the serializer runs.
        """
        response = authed_client.post(
            _COLLECTION_PATH, {"scope": "project"}, format="json"
        )

        _assert_opaque_404(response)


# ---------------------------------------------------------------------------
# Schema: one shared, preset-aware 404 and a required workspace_id
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def baseline_openapi() -> dict:
    """The generated OpenAPI 3.0 document (same output as ``GET /api/schema/``)."""
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def _operation(schema: dict, path: str, method: str) -> dict:
    return schema["paths"][path][method]


def _parameter(operation: dict, name: str, location: str = "query") -> dict | None:
    for parameter in operation.get("parameters", []) or []:
        if parameter.get("name") == name and parameter.get("in") == location:
            return parameter
    return None


class TestBaselinePresetGateSchema:
    """The published contract states the preset condition instead of hiding it."""

    @pytest.mark.parametrize(
        ("path", "method"),
        [
            (_COLLECTION_PATH, "get"),
            (_COLLECTION_PATH, "post"),
            (_DETAIL_PATH, "get"),
        ],
    )
    def test_operation_documents_the_preset_gate(
        self, baseline_openapi: dict, path: str, method: str
    ) -> None:
        """Each operation's own description names the preset condition."""
        operation = _operation(baseline_openapi, path, method)
        description = operation.get("description", "").lower()
        assert "preset" in description, operation.get("description")
        assert "minimal" in description, operation.get("description")
        assert "404" in description, operation.get("description")

    @pytest.mark.parametrize(
        ("path", "method"),
        [
            (_COLLECTION_PATH, "get"),
            (_COLLECTION_PATH, "post"),
            (_DETAIL_PATH, "get"),
        ],
    )
    def test_404_is_preset_specific_not_the_generic_blanket(
        self, baseline_openapi: dict, path: str, method: str
    ) -> None:
        """The 404 names the three causes instead of "Resource not found."."""
        response = _operation(baseline_openapi, path, method)["responses"]["404"]
        description = response["description"]

        assert description != "Resource not found."
        lowered = description.lower()
        assert "preset" in lowered
        assert "minimal" in lowered
        assert "workspace" in lowered
        assert "baseline" in lowered
        # Still the standard error envelope, not a bare description.
        assert response["content"]["application/json"]["schema"]

    def test_all_three_404s_share_one_description(
        self, baseline_openapi: dict
    ) -> None:
        """One shared constant, not three drifting copies (#1380)."""
        descriptions = {
            _operation(baseline_openapi, path, method)["responses"]["404"][
                "description"
            ]
            for path, method in [
                (_COLLECTION_PATH, "get"),
                (_COLLECTION_PATH, "post"),
                (_DETAIL_PATH, "get"),
            ]
        }
        assert len(descriptions) == 1

    def test_list_requires_workspace_id_query_parameter(
        self, baseline_openapi: dict
    ) -> None:
        """``list`` declares the prerequisite that keeps the gate resolvable.

        Evidence: without the parameter the request answers 404 in *every*
        preset (see ``test_missing_workspace_id_answers_404_in_every_preset``),
        because the gate falls back to the tenant id. The schema therefore
        marks it ``required`` instead of leaving a caller to discover the
        fallback at runtime.
        """
        operation = _operation(baseline_openapi, _COLLECTION_PATH, "get")
        parameter = _parameter(operation, "workspace_id")

        assert parameter is not None, operation.get("parameters")
        assert parameter["required"] is True
        assert parameter["schema"].get("format") == "uuid"
        assert "required" in parameter["description"].lower()

    def test_detail_get_does_not_demand_workspace_id(
        self, baseline_openapi: dict
    ) -> None:
        """``retrieve`` gates on the row's own workspace — no query prerequisite."""
        operation = _operation(baseline_openapi, _DETAIL_PATH, "get")
        assert _parameter(operation, "workspace_id") is None

    def test_nested_collection_route_has_no_workspace_id_parameter(
        self, baseline_openapi: dict
    ) -> None:
        """The nested route takes the workspace from its path, not the query.

        ``BaselineViewSet.list`` serves both routes. Publishing the flat
        route's required ``workspace_id`` here would be the mirror image of
        #1380: a requirement the endpoint does not have. ``_BaselineAutoSchema``
        removes it for the nested operation only.
        """
        operation = _operation(
            baseline_openapi, "/api/v1/workspaces/{workspace_pk}/baselines/", "get"
        )

        assert _parameter(operation, "workspace_id") is None
        assert _parameter(operation, "workspace_pk", "path") is not None
