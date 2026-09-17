"""Regression tests for issue #460 — REST API consistency bundle.

Four QA findings, one module. Each section states the observed pre-fix
behaviour so a future reader can tell an intentional contract from an
incidental one.

Finding 1  unknown /api/v1/ routes answered with Django's HTML 404 page while
           every other error on the API is a JSON envelope.
Finding 2  a malformed ``?workspace_id=`` was reported as *missing* (or, on
           several endpoints, crashed with HTTP 500).
Finding 3  ``/api/v1/search/`` without ``q`` answered 200 with an empty result
           set, silently hiding a wrong-parameter-name client bug.
Finding 4  ``/api/v1/goals/main/`` was parsed as a detail lookup and answered
           400 "'pk' must be a well-formed UUID" instead of 404.
"""
from __future__ import annotations

import uuid

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

from rest_api.not_found import api_not_found

pytestmark = pytest.mark.django_db


def _envelope(response) -> dict:
    """Return the parsed ``{"code", "message", "details"}`` error body."""
    body = response.json()
    assert set(body) == {"error"}, body
    error = body["error"]
    assert set(error) == {"code", "message", "details"}, error
    return error


# ---------------------------------------------------------------------------
# Finding 1 — JSON envelope for unknown /api/v1/ routes
# ---------------------------------------------------------------------------


def test_unknown_api_v1_route_returns_json_envelope(authed_client):
    response = authed_client.get("/api/v1/does-not-exist/")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert _envelope(response)["code"] == "NOT_FOUND"


def test_unknown_api_v1_route_is_404_for_anonymous_callers_too():
    """The resolver 404ed regardless of auth; requiring auth here would turn a
    typo into a 403 and leak that the fallback exists."""
    response = APIClient().get("/api/v1/does-not-exist/")

    assert response.status_code == 404
    assert _envelope(response)["code"] == "NOT_FOUND"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_unknown_api_v1_route_is_404_for_unsafe_methods(method):
    """The fallback must be ``csrf_exempt``.

    Routing an unsafe method to a real view newly subjects it to
    ``CsrfViewMiddleware``, which would answer 403 for a request that used to
    404 in the resolver — before ``process_view`` ever ran.
    """
    response = getattr(APIClient(), method)("/api/v1/does-not-exist/")

    assert response.status_code == 404
    assert _envelope(response)["code"] == "NOT_FOUND"


def test_unknown_route_body_does_not_echo_the_requested_path():
    """No reflection of caller-controlled input into the response body."""
    payload = "<script>alert(1)</script>"

    response = APIClient().get(f"/api/v1/{payload}/")

    assert response.status_code == 404
    assert payload not in response.content.decode(errors="replace")


def test_missing_trailing_slash_also_yields_the_json_envelope():
    """``APPEND_SLASH=False`` (CR-03) means this never reaches a real route."""
    response = APIClient().get("/api/v1/requirements")

    assert response.status_code == 404
    assert _envelope(response)["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "path",
    [
        "/mcp/does-not-exist/",
        "/admin/does-not-exist/",
        "/does-not-exist/",
    ],
)
def test_non_api_v1_prefixes_keep_djangos_default_404(path):
    """The fallback is scoped to /api/v1/ on purpose.

    ``/admin/`` is a human-facing HTML app and ``/mcp/`` speaks JSON-RPC with
    its own error shape — neither should start emitting the REST envelope.
    """
    response = APIClient().get(path)

    assert response.status_code in (301, 302, 404)
    if response.status_code == 404:
        assert not response["Content-Type"].startswith("application/json")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/version/",
        "/api/v1/schema/",
        "/api/v1/mcp/",
        "/api/schema/",
        "/health/",
    ],
)
def test_real_routes_are_not_swallowed_by_the_fallback(path):
    """The catch-all must sit *after* every genuine pattern.

    ``/api/v1/mcp/`` is the load-bearing case: it is included in the root
    URLconf *after* ``rest_api.urls``, so putting the fallback inside
    ``rest_api/urls.py`` would have shadowed the whole MCP transport.
    """
    response = APIClient().get(path)

    assert response.status_code != 404, f"{path} was swallowed by the fallback"


# ---------------------------------------------------------------------------
# Finding 2 — "missing" vs "malformed" workspace_id
# ---------------------------------------------------------------------------

# One entry per endpoint family that reads ``?workspace_id=``. ``/needs/`,
# ``/testcases/``, ``/tracelinks/``, ``/test-runs/`` and friends answered
# HTTP 500 before the fix: the raw string reached the ORM, which raised
# ``django.core.exceptions.ValidationError`` from inside ``QuerySet.filter()``
# where the generic ``except Exception`` mapped it to INTERNAL_SERVER_ERROR.
WORKSPACE_SCOPED_PATHS = [
    "/api/v1/requirements/",
    "/api/v1/needs/",
    "/api/v1/architecture/",
    "/api/v1/testcases/",
    "/api/v1/artifacts/",
    "/api/v1/tracelinks/",
    "/api/v1/adrs/",
    "/api/v1/risks/",
    "/api/v1/issues/",
    "/api/v1/goals/",
    "/api/v1/main-goals/",
    "/api/v1/change-requests/",
    "/api/v1/test-runs/",
    "/api/v1/diagrams/",
    "/api/v1/icds/",
    "/api/v1/glossary/",
    "/api/v1/users/me/preferences/",
]


@pytest.mark.parametrize("path", WORKSPACE_SCOPED_PATHS)
def test_malformed_workspace_id_is_400_and_says_so(authed_client, path):
    response = authed_client.get(f"{path}?workspace_id=kaputt")

    assert response.status_code == 400, (
        f"{path} returned {response.status_code} for a malformed workspace_id"
    )
    error = _envelope(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "workspace_id must be a valid UUID"


@pytest.mark.parametrize("path", WORKSPACE_SCOPED_PATHS)
def test_absent_workspace_id_still_says_required(authed_client, path):
    """The other half of the distinction — this message must stay accurate."""
    response = authed_client.get(path)

    assert response.status_code == 400
    error = _envelope(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "workspace_id is required"


@pytest.mark.parametrize("path", WORKSPACE_SCOPED_PATHS)
def test_blank_workspace_id_counts_as_absent(authed_client, path):
    """``?workspace_id=`` supplies the key with an empty value."""
    response = authed_client.get(f"{path}?workspace_id=")

    assert response.status_code == 400
    assert _envelope(response)["message"] == "workspace_id is required"


@pytest.mark.parametrize("path", WORKSPACE_SCOPED_PATHS)
def test_valid_workspace_id_is_unaffected(authed_client, workspace, path):
    """No-regression: the happy path must still reach the view."""
    response = authed_client.get(f"{path}?workspace_id={workspace.id}")

    assert response.status_code == 200, (
        f"{path} returned {response.status_code} for a valid workspace_id: "
        f"{response.content[:300]!r}"
    )


def test_malformed_workspace_id_in_a_request_body_is_also_400(authed_client):
    """``MainGoalViewSet.generate`` reads ``workspace_id`` from the body."""
    response = authed_client.post(
        "/api/v1/main-goals/generate/", {"workspace_id": "kaputt"}, format="json"
    )

    assert response.status_code == 400
    assert _envelope(response)["message"] == "workspace_id must be a valid UUID"


def test_test_run_create_reports_a_malformed_workspace_id_as_400_not_500(authed_client):
    """``POST /api/v1/test-runs/`` was the last ``UUID()``-inside-a-broad-try site.

    The ``ValueError`` was caught by ``except Exception`` and mapped onto
    INTERNAL_SERVER_ERROR.
    """
    response = authed_client.post(
        "/api/v1/test-runs/", {"workspace_id": "kaputt", "name": "run"}, format="json"
    )

    assert response.status_code == 400
    assert _envelope(response)["message"] == "workspace_id must be a valid UUID"


def test_test_run_create_still_reports_a_missing_name(authed_client, workspace):
    """No-regression on the other half of the split combined check."""
    response = authed_client.post(
        "/api/v1/test-runs/", {"workspace_id": str(workspace.id)}, format="json"
    )

    assert response.status_code == 400
    assert _envelope(response)["message"] == "name is required"


def test_workflow_definition_uses_the_same_invalid_uuid_wording(authed_client):
    """The two endpoints that already distinguished the cases used different
    wording ("must be a UUID"); one message for one condition, API-wide."""
    response = authed_client.get(
        "/api/v1/workflows/definition/?workspace_id=kaputt&item_type=Requirement"
    )

    assert response.status_code == 400
    assert _envelope(response)["message"] == "workspace_id must be a valid UUID"


def test_malformed_workspace_id_never_echoes_the_offending_value(authed_client):
    """Same reflection guard as the malformed-path-UUID check (issue #271)."""
    payload = "<script>alert(1)</script>"

    response = authed_client.get(f"/api/v1/requirements/?workspace_id={payload}")

    assert response.status_code == 400
    assert payload not in response.content.decode(errors="replace")


def test_baseline_list_keeps_the_preset_gate_in_front_of_the_check(authed_client):
    """BaselineViewSet is the one call site with a gate before the validation.

    ``PresetGateMixin`` decides whether the endpoint exists for this workspace
    at all, so it deliberately still runs first and on the raw value — an
    unresolvable workspace makes it raise ``Http404`` before the parameter is
    ever parsed. The status therefore stays 404 (not the 400 the other list
    endpoints give); what this asserts is that the *envelope* is JSON, which
    it was not before ``handler404`` was wired up.
    """
    response = authed_client.get("/api/v1/baselines/?workspace_id=kaputt")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert _envelope(response)["code"] == "NOT_FOUND"


def test_baseline_list_with_a_valid_workspace_id_still_works(authed_client, workspace):
    """No-regression: reordering nothing means the happy path is untouched."""
    response = authed_client.get(f"/api/v1/baselines/?workspace_id={workspace.id}")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Finding 3 — /search/ must not answer 200 for a query it never ran
# ---------------------------------------------------------------------------


def test_search_without_q_returns_400(authed_client, workspace):
    """The reported shape: ``?search=`` instead of ``?q=``.

    The wrong parameter name used to be ignored and the endpoint answered 200
    with ``query: ""`` — indistinguishable from a genuine zero-hit search.
    """
    response = authed_client.get(
        f"/api/v1/search/?workspace_id={workspace.id}&search=Monitoring"
    )

    assert response.status_code == 400
    error = _envelope(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "q is required"


@pytest.mark.parametrize("q", ["", "   "])
def test_search_with_blank_q_returns_400(authed_client, workspace, q):
    response = authed_client.get(
        f"/api/v1/search/?workspace_id={workspace.id}&q={q}"
    )

    assert response.status_code == 400
    assert _envelope(response)["message"] == "q is required"


def test_search_workspace_id_is_validated_before_q(authed_client):
    """A caller missing both parameters is told about workspace_id first —
    matching every sibling list endpoint's ordering."""
    response = authed_client.get("/api/v1/search/")

    assert response.status_code == 400
    assert _envelope(response)["message"] == "workspace_id is required"


def test_search_with_q_still_works(authed_client, workspace):
    """No-regression: a real query is unaffected and still reports its terms."""
    response = authed_client.get(
        f"/api/v1/search/?workspace_id={workspace.id}&q=Monitoring"
    )

    assert response.status_code == 200
    assert response.json()["query"] == "Monitoring"


# ---------------------------------------------------------------------------
# Finding 4 — /goals/main/ is not a route, so it must 404
# ---------------------------------------------------------------------------


def test_goals_main_returns_404_not_a_uuid_validation_error(authed_client, workspace):
    """``main`` is a non-existent route, not a malformed id.

    The aggregated goal lives at ``/api/v1/main-goals/current/``; nothing is
    registered under ``goals/main/``, so the honest answer is 404.
    """
    response = authed_client.get(f"/api/v1/goals/main/?workspace_id={workspace.id}")

    assert response.status_code == 404
    assert _envelope(response)["code"] == "NOT_FOUND"


def test_goals_detail_with_unknown_uuid_still_returns_404(authed_client):
    """No-regression: ``lookup_value_regex`` must not break the detail route."""
    response = authed_client.get(f"/api/v1/goals/{uuid.uuid4()}/")

    assert response.status_code == 404


@pytest.mark.parametrize("prefix", ["goals", "needs"])
def test_detail_route_accepts_uppercase_uuids(prefix):
    """``lookup_value_regex`` must not be lowercase-only.

    UUIDs are case-insensitive and ``uuid.UUID()`` parses either case, so a
    caller echoing back an id in upper case addresses the same object. A
    lowercase-only character class declines the segment at *routing* time, so
    the request falls through to the ``/api/v1/`` catch-all and the caller is
    told the endpoint does not exist — for an id that does.
    """
    upper = str(uuid.uuid4()).upper()

    match = resolve(f"/api/v1/{prefix}/{upper}/")

    assert match.func is not api_not_found


def test_goals_list_still_routes(authed_client, workspace):
    response = authed_client.get(f"/api/v1/goals/?workspace_id={workspace.id}")

    assert response.status_code == 200


def test_main_goals_current_action_still_routes(authed_client, workspace):
    """The real endpoint a caller reaching for ``goals/main/`` wants."""
    response = authed_client.get(
        f"/api/v1/main-goals/current/?workspace_id={workspace.id}"
    )

    assert response.status_code == 200


def test_requirements_detail_keeps_the_issue_271_400_contract(authed_client):
    """The goals-only regex must not leak into the generic malformed-pk rule.

    Issue #271 deliberately answers 400 (not 404) for a malformed detail pk so
    "you sent garbage" stays distinguishable from "it is gone".
    """
    response = authed_client.get("/api/v1/requirements/not-a-uuid/")

    assert response.status_code == 400
    assert _envelope(response)["code"] == "VALIDATION_ERROR"
