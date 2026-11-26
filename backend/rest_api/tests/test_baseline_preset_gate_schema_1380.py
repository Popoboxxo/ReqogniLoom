"""#1380/#1391 gate: the baseline preset gate is truthful in runtime and schema.

The OpenAPI document advertised ``GET``/``POST /api/v1/baselines/`` (and
``GET /api/v1/baselines/{id}/``) unconditionally, with only the generic
"Resource not found." blanket for ``404``. At runtime the preset gate hides the
whole family in presets that do not enable ``preset_endpoint_key =
"baselines"``, so the schema promised an endpoint that did not exist for that
caller.

#1380 documented that gate. #1391 fixed the *status code* of the flat route's
own parameter: it used to run the gate before validation, so a missing
``?workspace_id=`` reached the gate's tenant-id fallback and answered the same
opaque 404 in every preset — a client error reported as an absent endpoint. The
flat list route now validates first and answers ``400 VALIDATION_ERROR``; the
nested route and the create route keep their historical order.

This module pins all three halves:

* **Runtime** — a missing/malformed parameter on the flat route is a 400 that
  does not echo the value; a preset-disabled workspace and a foreign/unknown
  workspace keep answering the opaque 404; the enabled happy path is untouched.
* **Security** — the 404 stays indistinguishable between "preset disabled" and
  "workspace unknown/foreign": the fix must not turn either into a 400, which
  would recreate the existence oracle #1380 closed.
* **Schema** — the list ``404`` names only the two remaining causes, the list
  ``400`` documents the parameter defect, ``workspace_id`` stays required on the
  flat operation (and absent on the nested one), and the create ``404`` still
  names the omitted-workspace cause it really has.

Empirical proof of the runtime behaviour (measured with the tests below,
``2026-11-25``, project preset = the workspace's ``preset["name"]``):

| Request                                              | Preset   | Status | Body (excerpt)                                                               |
|------------------------------------------------------|----------|--------|-----------------------------------------------------------------------------|
| ``GET /api/v1/baselines/`` (no ``workspace_id``)      | any      | 400    | ``VALIDATION_ERROR``, message names the flat route and both alternatives     |
| ``GET /api/v1/baselines/?workspace_id=<blank>``       | any      | 400    | same message (blank counts as missing)                                       |
| ``GET /api/v1/baselines/?workspace_id=not-a-uuid``    | any      | 400    | ``workspace_id must be a valid UUID`` (value not echoed)                     |
| ``GET /api/v1/baselines/?workspace_id=<minimal>``     | minimal  | 404    | ``{"error": {"code": "NOT_FOUND", "message": "The requested API endpoint does not exist.", ...}}`` |
| ``GET /api/v1/baselines/?workspace_id=<random uuid>`` | any      | 404    | same envelope, byte-identical (no existence oracle)                          |
| ``GET /api/v1/baselines/?workspace_id=<foreign>``     | any      | 404    | same envelope, byte-identical (no existence oracle)                          |
| ``GET /api/v1/baselines/?workspace_id=<standard>``    | standard | 200    | ``{"count":0,...,"results":[]}``                                             |
| ``GET /api/v1/baselines/?workspace_id=<extended>``    | extended | 200    | same empty pagination envelope                                               |
| ``GET /api/v1/workspaces/<extended>/baselines/``      | extended | 200    | nested route unchanged (workspace from the path)                             |
| ``GET /api/v1/workspaces/<minimal>/baselines/``       | minimal  | 404    | nested route keeps the gate first                                            |
| ``POST /api/v1/baselines/`` (enabled workspace)       | extended | 201    | baseline detail + ``ETag``                                                   |
| ``GET /api/v1/baselines/{id}/`` (enabled workspace)   | extended | 200    | baseline detail incl. ``entries``                                            |
| ``POST /api/v1/baselines/`` (no ``workspace_id``)     | any      | 404    | unchanged: the create route still gates before the serializer                |

``request_id`` is an additive correlation id (R2A-001) mirroring the
``X-Request-ID`` header; it holds a fresh UUID per request, so "same envelope,
byte-identical" above compares only code, message and details — the
``request_id`` value varies. Outside a request context the same envelope carries
``null`` instead.

The 404 status, the ``NOT_FOUND`` error code and the envelope shape are shared
with the body ``handler404`` renders for an unrouted path
(:data:`rest_api.not_found.ROUTE_NOT_FOUND_MESSAGE`): the preset gate (1) and an
unknown/foreign workspace (2) are indistinguishable from "no such route", so no
probe tells "hidden by preset" from "route does not exist". That is true of
(1)/(2) only. An unknown baseline id (3) keeps the same status/code/envelope but
answers the message ``"Baseline not found"`` (``BaselineNotFoundError`` via
``_service_error_response``), so it *is* distinguishable from (1)/(2). The
schema description says exactly this, and no change may alter the runtime bodies
(the shared route-miss message is deliberate, GH-443-adjacent contract).
"""
from __future__ import annotations

import json
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
#: The nested collection route (issue #49) — workspace in the path.
_NESTED_COLLECTION_TEMPLATE = "/api/v1/workspaces/{workspace_id}/baselines/"

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


def _body_without_request_id(response) -> dict:
    """The error envelope minus the per-request correlation id."""
    body = json.loads(response.content.decode())
    body["error"].pop("request_id", None)
    return body


# ---------------------------------------------------------------------------
# Runtime: the flat route validates the parameter before the gate (#1391)
# ---------------------------------------------------------------------------


class TestBaselineFlatRouteParameterValidation:
    """A client-side parameter defect is a 400, never the gate's opaque 404."""

    @pytest.mark.parametrize("tier", ["minimal", "standard", "extended"])
    def test_missing_workspace_id_answers_400_in_every_preset(
        self, authed_client: APIClient, tenant: Tenant, tier: str
    ) -> None:
        """(a) no ``workspace_id`` -> 400 in *every* preset.

        Parametrised over all three tiers to pin that the answer does not depend
        on the preset: validation runs before the gate, so the workspace's tier
        cannot change it.
        """
        user = User.objects.get(username="bundleadmin")
        _workspace_with_admin(tenant, user, tier)

        response = authed_client.get(_COLLECTION_PATH)

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_blank_workspace_id_answers_the_same_400(
        self, authed_client: APIClient
    ) -> None:
        """A blank value is "not supplied", not a malformed UUID."""
        missing = authed_client.get(_COLLECTION_PATH)
        blank = authed_client.get(_COLLECTION_PATH, {"workspace_id": "   "})

        assert blank.status_code == 400, blank.content
        assert _body_without_request_id(blank) == _body_without_request_id(missing)

    def test_missing_parameter_message_names_the_alternatives(
        self, authed_client: APIClient
    ) -> None:
        """The message must be actionable: the flat and nested spellings both."""
        response = authed_client.get(_COLLECTION_PATH)
        message = response.json()["error"]["message"]

        assert "workspace_id is required" in message
        assert "flat" in message
        assert "?workspace_id=<uuid>" in message
        assert "/api/v1/workspaces/<workspace_id>/baselines/" in message

    def test_malformed_workspace_id_answers_validation_error(
        self, authed_client: APIClient
    ) -> None:
        """A non-UUID value keeps the shared ``parse_workspace_id`` wording."""
        response = authed_client.get(
            _COLLECTION_PATH, {"workspace_id": "not-a-uuid"}
        )

        assert response.status_code == 400, response.content
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["message"] == "workspace_id must be a valid UUID"

    def test_malformed_workspace_id_is_not_echoed(
        self, authed_client: APIClient
    ) -> None:
        """Reflection hazard (#271 family): the 400 must not repeat the input."""
        marker = f"probe-{uuid.uuid4().hex}"

        response = authed_client.get(_COLLECTION_PATH, {"workspace_id": marker})

        assert response.status_code == 400, response.content
        assert marker not in response.content.decode()


# ---------------------------------------------------------------------------
# Runtime: the gate exists (and is not weakened, #1380)
# ---------------------------------------------------------------------------


class TestBaselinePresetGateRuntime:
    """Proves the 404 conditions the schema documents — and only those."""

    def test_minimal_preset_collection_answers_404(
        self, authed_client: APIClient, tenant: Tenant
    ) -> None:
        """(1) ``?workspace_id=<minimal workspace>`` -> 404 (preset disabled)."""
        user = User.objects.get(username="bundleadmin")
        minimal = _workspace_with_admin(tenant, user, "minimal")

        response = authed_client.get(
            _COLLECTION_PATH, {"workspace_id": str(minimal.id)}
        )

        _assert_opaque_404(response)

    def test_unknown_workspace_answers_404(
        self, authed_client: APIClient
    ) -> None:
        """(2a) a well-formed but unknown workspace id -> 404."""
        response = authed_client.get(
            _COLLECTION_PATH, {"workspace_id": str(uuid.uuid4())}
        )

        _assert_opaque_404(response)

    def test_foreign_workspace_answers_404(
        self, authed_client: APIClient
    ) -> None:
        """(2b) another tenant's workspace id -> 404, same body as unknown."""
        other = Tenant.objects.create(
            name=f"gate1380-foreign-{uuid.uuid4().hex[:8]}",
            slug=f"gate1380-foreign-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        set_request_tenant(other.id)
        try:
            foreign = Workspace.objects.create(
                tenant=other,
                name=f"gate1380-foreign-ws-{uuid.uuid4().hex[:8]}",
                preset={"name": "extended"},
            )
        finally:
            clear_request_tenant()

        response = authed_client.get(
            _COLLECTION_PATH, {"workspace_id": str(foreign.id)}
        )
        unknown = authed_client.get(
            _COLLECTION_PATH, {"workspace_id": str(uuid.uuid4())}
        )

        _assert_opaque_404(response)
        # Security assertion (#1380): foreign and unknown are indistinguishable.
        assert _body_without_request_id(response) == _body_without_request_id(unknown)

    def test_404_is_not_the_generic_blanket(self, authed_client: APIClient) -> None:
        """The gate's 404 is the route-miss body — not a described row-miss."""
        response = authed_client.get(
            _COLLECTION_PATH, {"workspace_id": str(uuid.uuid4())}
        )

        assert response.json()["error"]["message"] == _OPAQUE_404_MESSAGE
        assert response.json()["error"]["message"] != "Baseline not found"

    @pytest.mark.parametrize("tier", ["standard", "extended"])
    def test_baseline_enabled_preset_still_answers_200(
        self, authed_client: APIClient, tenant: Tenant, tier: str
    ) -> None:
        """(c) a preset that enables baselines keeps answering 200.

        Guards against the one wrong fix for #1380: opening the gate so the
        documented endpoint always exists. The gate stays closed; only its
        documentation and the parameter's status code changed.
        """
        user = User.objects.get(username="bundleadmin")
        workspace = _workspace_with_admin(tenant, user, tier)

        response = authed_client.get(
            _COLLECTION_PATH, {"workspace_id": str(workspace.id)}
        )

        assert response.status_code == 200, response.content
        assert "results" in response.json()

    def test_nested_route_keeps_the_gate_first(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        """The nested route is untouched: enabled -> 200, minimal -> 404.

        Only the flat route validates before the gate (#1391); the nested route
        still takes the workspace from the path and gates first.
        """
        user = User.objects.get(username="bundleadmin")
        minimal = _workspace_with_admin(tenant, user, "minimal")

        enabled = authed_client.get(
            _NESTED_COLLECTION_TEMPLATE.format(workspace_id=workspace.id)
        )
        disabled = authed_client.get(
            _NESTED_COLLECTION_TEMPLATE.format(workspace_id=minimal.id)
        )

        assert enabled.status_code == 200, enabled.content
        _assert_opaque_404(disabled)

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

    def test_create_without_workspace_id_still_answers_404(
        self, authed_client: APIClient
    ) -> None:
        """The create route's own prerequisite — deliberately unchanged (#1391).

        ``POST /api/v1/baselines/`` has no workspace in its path either, so an
        omitted body ``workspace_id`` reaches the same tenant-id fallback and
        answers the same opaque 404 — before the serializer runs. #1391 covers
        the list route only.
        """
        response = authed_client.post(
            _COLLECTION_PATH, {"scope": "project"}, format="json"
        )

        _assert_opaque_404(response)


# ---------------------------------------------------------------------------
# Schema: one preset-aware 404 per route, a 400 for the parameter, and a
# required workspace_id
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
        """The 404 names the real causes instead of "Resource not found."."""
        response = _operation(baseline_openapi, path, method)["responses"]["404"]
        description = response["description"]

        assert description != "Resource not found."
        lowered = description.lower()
        assert "preset" in lowered
        assert "minimal" in lowered
        assert "workspace" in lowered
        # Still the standard error envelope, not a bare description.
        assert response["content"]["application/json"]["schema"]

    def test_list_404_names_only_the_two_remaining_causes(
        self, baseline_openapi: dict
    ) -> None:
        """#1391: the flat list no longer 404s for a missing parameter."""
        description = _operation(baseline_openapi, _COLLECTION_PATH, "get")[
            "responses"
        ]["404"]["description"].lower()

        assert "(1)" in description and "preset" in description
        assert "(2)" in description and "workspace" in description
        assert "(3)" not in description, "the list route has no third cause"
        assert "400" in description and "validation_error" in description
        assert "omitted or malformed" in description

    def test_create_404_still_names_the_omitted_workspace_cause(
        self, baseline_openapi: dict
    ) -> None:
        """``POST`` keeps the pre-serializer gate, so its 404 text keeps the cause."""
        description = _operation(baseline_openapi, _COLLECTION_PATH, "post")[
            "responses"
        ]["404"]["description"].lower()

        assert "omitted or empty" in description
        assert "create" in description

    def test_detail_404_names_the_unknown_baseline_cause(
        self, baseline_openapi: dict
    ) -> None:
        """(3) keeps its own distinguishable message — the gate does not hide it."""
        description = _operation(baseline_openapi, _DETAIL_PATH, "get")[
            "responses"
        ]["404"]["description"].lower()

        assert "baseline not found" in description
        assert "(3)" in description
        # The detail route has no omitted-parameter cause (it takes no query
        # parameter) — only ``create`` keeps that sentence.
        assert "omitted or empty" not in description

    def test_404_description_does_not_over_promise_non_disclosure(
        self, baseline_openapi: dict
    ) -> None:
        """F7: the same status/code/envelope does not mean the same *message*.

        Cause (3) answers ``"Baseline not found"`` while (1)/(2) use the
        route-miss text, so a claim that the route "does not disclose which
        condition applied" is false. The description must state the real
        contract: 404 means "not available here", never "does not exist".
        """
        description = _operation(
            baseline_openapi, _DETAIL_PATH, "get"
        )["responses"]["404"]["description"].lower()

        assert "baseline not found" in description
        assert "requested api endpoint does not exist" in description
        assert "not available here" in description
        assert "does not disclose" not in description
        assert "opaque body" not in description

    def test_list_documents_the_parameter_400(self, baseline_openapi: dict) -> None:
        """#1391: the list operation publishes the 400 it now really answers."""
        response = _operation(baseline_openapi, _COLLECTION_PATH, "get")[
            "responses"
        ]["400"]
        description = response["description"].lower()

        assert response["content"]["application/json"]["schema"]
        assert "workspace_id" in description
        assert "required" in description
        assert "valid uuid" in description
        assert "does not echo" in description
        # The tag cause (F4.2) survives the edit.
        assert "tag" in description

    def test_list_requires_workspace_id_query_parameter(
        self, baseline_openapi: dict
    ) -> None:
        """``list`` declares the prerequisite that the flat route enforces.

        Evidence: without the parameter the flat route answers 400 and the
        nested route does not need it (see the runtime tests above), so the flat
        operation marks it ``required`` while the nested operation drops it.
        """
        operation = _operation(baseline_openapi, _COLLECTION_PATH, "get")
        parameter = _parameter(operation, "workspace_id")

        assert parameter is not None, operation.get("parameters")
        assert parameter["required"] is True
        assert parameter["schema"].get("format") == "uuid"
        assert "required" in parameter["description"].lower()
        assert "400" in parameter["description"]

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
