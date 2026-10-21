"""The gaps the GH-1396 review found *beside* the parser — findings B1–B3, F8/F9, m3/m4.

``test_if_match_parser_1396.py`` pins the parser itself and the three main
``PATCH`` routes. This module pins the places where a correctly parsed header
was still not *enforced*:

===============================  ===========================================
Finding                          Pinned behaviour
===============================  ===========================================
B1 ``WorkspaceViewSet.partial_    ``{"is_active": false}`` is guarded: stale →
   update`` lifecycle branch       412, weak → 412, malformed → 400, match →
                                   200; an invalid payload writes nothing.
B2 ``close_workspace`` /          The lifecycle methods bump ``version``, so the
   ``reactivate_workspace``        ``ETag`` changes when the representation
                                   does — no endless replay with one tag.
B3 ``GoalViewSet.outdate`` /       malformed → 400, lost precondition → 409,
   ``reactivate``                  match → 200 (never the 500 the escaping
                                   non-``ValueError`` exceptions produced).
F8 ``_BaselineAutoSchema``        Only the ``workspace_id`` *query* parameter
                                   is dropped on the nested route; a path
                                   parameter of the same name survives.
F9 ``BaselineViewSet.partial_      Malformed ``If-Match`` is 400 even when the
   update``                        row does not exist (was 405).
m3 ``resolve_expected_version``   A matching *non-numeric* tag list member is a
                                   mismatch, not a silent unguarded write.
m4 ``if_match_error``             Only ``IfMatchMismatch`` becomes 412; a
                                   programming error is re-raised.
===============================  ===========================================
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.mixins.etag import (
    ETagMixin,
    IfMatchMismatch,
    InvalidIfMatch,
    compute_etag,
)

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_WS_DETAIL = "/api/v1/workspaces/{pk}/"


# ---------------------------------------------------------------------------
# Scenario helpers
# ---------------------------------------------------------------------------


def _scenario(preset: str = "standard") -> tuple[Tenant, User, Workspace]:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"Gap-{suffix}", slug=f"gap-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"gap-{suffix}", email=f"gap-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"Gap WS {suffix}", preset={"name": preset}
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


def _ws_url(workspace: Workspace) -> str:
    return _WS_DETAIL.format(pk=workspace.id)


def _live(workspace: Workspace) -> Workspace:
    return Workspace.unscoped.get(pk=workspace.pk)


# ---------------------------------------------------------------------------
# B1 — the workspace lifecycle branch is behind the precondition
# ---------------------------------------------------------------------------


def test_conditional_close_with_stale_if_match_is_412_and_does_not_close() -> None:
    """The headline B1 case: ``{"is_active": false}`` used to ignore If-Match."""
    _, user, workspace = _scenario()
    client = _client(user)

    resp = client.patch(
        _ws_url(workspace),
        {"is_active": False},
        format="json",
        HTTP_IF_MATCH='"999999"',
    )

    assert resp.status_code == 412, resp.content
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED", resp.content
    fresh = _live(workspace)
    assert fresh.is_active is True, "a stale precondition must not close the workspace"
    assert fresh.closed_at is None, "no close timestamp may be written"


def test_conditional_close_with_weak_tag_is_412_and_does_not_close() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    etag = client.get(_ws_url(workspace))["ETag"]

    resp = client.patch(
        _ws_url(workspace),
        {"is_active": False},
        format="json",
        HTTP_IF_MATCH=f"W/{etag}",
    )

    assert resp.status_code == 412, resp.content
    assert _live(workspace).is_active is True


@pytest.mark.parametrize("header", ["garbage", "", 'W/"1" x'])
def test_conditional_close_with_malformed_if_match_is_400_and_does_not_close(
    header: str,
) -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    resp = client.patch(
        _ws_url(workspace),
        {"is_active": False},
        format="json",
        HTTP_IF_MATCH=header,
    )

    assert resp.status_code == 400, (header, resp.content)
    assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", (header, resp.content)
    assert _live(workspace).is_active is True


def test_conditional_close_with_matching_tag_closes_and_returns_new_etag() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    etag = client.get(_ws_url(workspace))["ETag"]
    assert etag == f'"{_live(workspace).version}"'

    resp = client.patch(
        _ws_url(workspace),
        {"is_active": False},
        format="json",
        HTTP_IF_MATCH=etag,
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["is_active"] is False
    assert body["closed_at"] is not None
    assert resp["ETag"] != etag, "closing changes the representation, so the tag moves"
    assert resp["ETag"] == f'"{_live(workspace).version}"'


def test_invalid_payload_does_not_close_the_workspace() -> None:
    """``{"is_active": false, "name": 123}`` must 400 *before* the close write.

    A workspace name is textual; a JSON number is rejected instead of being
    coerced to ``"123"`` (see ``WorkspaceSerializer.to_internal_value``). The
    point of the case is the ordering: validation precedes the lifecycle branch,
    so the close never lands.
    """
    _, user, workspace = _scenario()
    client = _client(user)

    resp = client.patch(
        _ws_url(workspace),
        {"is_active": False, "name": 123},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR", resp.content
    fresh = _live(workspace)
    assert fresh.is_active is True, "the invalid payload must not close it"
    assert fresh.closed_at is None


# ---------------------------------------------------------------------------
# B2 — the lifecycle methods bump ``version`` (so the ETag moves)
# ---------------------------------------------------------------------------


def test_reactivate_bumps_version_and_changes_the_etag() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    pre_close_etag = client.get(_ws_url(workspace))["ETag"]
    pre_close_version = _live(workspace).version

    closed = client.patch(
        _ws_url(workspace),
        {"is_active": False},
        format="json",
        HTTP_IF_MATCH=pre_close_etag,
    )
    assert closed.status_code == 200, closed.content
    closed_etag = closed["ETag"]
    closed_version = closed.json()["version"]
    assert closed_etag != pre_close_etag, "B2: closing must move the ETag"
    assert closed_version == pre_close_version + 1, closed.json()

    reopened = client.patch(
        _ws_url(workspace),
        {"is_active": True},
        format="json",
    )

    assert reopened.status_code == 200, reopened.content
    assert reopened.json()["is_active"] is True
    assert reopened.json()["closed_at"] is None
    assert reopened["ETag"] != closed_etag, "B2: reopening must move the ETag"
    assert reopened.json()["version"] == closed_version + 1
    # The reopened tag is the one a conditional caller must send next.
    assert reopened["ETag"] == f'"{_live(workspace).version}"'


def test_a_replayed_conditional_close_is_rejected_on_the_second_try() -> None:
    """Without B2 the same tag would keep satisfying the precondition forever."""
    _, user, workspace = _scenario()
    client = _client(user)
    etag = client.get(_ws_url(workspace))["ETag"]

    first = client.patch(
        _ws_url(workspace), {"is_active": False}, format="json", HTTP_IF_MATCH=etag
    )
    assert first.status_code == 200, first.content

    replay = client.patch(
        _ws_url(workspace),
        {"is_active": False},
        format="json",
        HTTP_IF_MATCH=etag,
    )

    assert replay.status_code == 412, replay.content


# ---------------------------------------------------------------------------
# B3 — goal outdate/reactivate map the resolver exceptions instead of 500ing
# ---------------------------------------------------------------------------


def _extended_scenario() -> tuple[Tenant, User, Workspace]:
    return _scenario(preset="extended")


def _initialize_workflow(
    client: APIClient, workspace: Workspace, item_type: str
) -> None:
    resp = client.post(
        "/api/v1/workflows/definition/initialize/",
        {"workspace_id": str(workspace.id), "item_type": item_type},
        format="json",
    )
    assert resp.status_code == 201, resp.content


def _create_goal(client: APIClient, workspace: Workspace) -> dict:
    resp = client.post(
        "/api/v1/goals/",
        {
            "workspace_id": str(workspace.id),
            "title": "Gap goal",
            "description": "a measurable goal",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _goal_revision(client: APIClient, goal_id: str) -> int:
    resp = client.get(f"/api/v1/goals/{goal_id}/transitions/")
    assert resp.status_code == 200, resp.content
    return resp.json()["version"]


def test_goal_outdate_malformed_stale_and_matching_if_match() -> None:
    """B3: all three answers, none of them the old HTTP 500."""
    _, user, workspace = _extended_scenario()
    client = _client(user)
    _initialize_workflow(client, workspace, "Goal")
    goal_id = _create_goal(client, workspace)["id"]
    revision = _goal_revision(client, goal_id)

    malformed = client.post(
        f"/api/v1/goals/{goal_id}/outdate/", {}, format="json", HTTP_IF_MATCH="garbage"
    )
    assert malformed.status_code == 400, malformed.content
    assert malformed.json()["error"]["code"] == "INVALID_IF_MATCH", malformed.content

    stale = client.post(
        f"/api/v1/goals/{goal_id}/outdate/",
        # The preset's change_reason gate runs before the workflow compare, so
        # the conditional request must be otherwise valid to reach the 409.
        {"change_reason": "done"},
        format="json",
        HTTP_IF_MATCH='"999999"',
    )
    assert stale.status_code == 409, stale.content
    assert stale.json()["error"]["code"] == "CONFLICT", stale.content

    # The other half of B3: a weak validator raises ``IfMatchMismatch`` inside
    # the resolver, which used to escape the method as an uncaught exception
    # (HTTP 500) instead of the CR-08 conflict.
    weak = client.post(
        f"/api/v1/goals/{goal_id}/outdate/",
        {"change_reason": "done"},
        format="json",
        HTTP_IF_MATCH=f'W/"{revision}"',
    )
    assert weak.status_code == 409, weak.content
    assert weak.json()["error"]["code"] == "CONFLICT", weak.content

    matching = client.post(
        f"/api/v1/goals/{goal_id}/outdate/",
        {"change_reason": "done"},
        format="json",
        HTTP_IF_MATCH=f'"{revision}"',
    )
    assert matching.status_code == 200, matching.content


def test_goal_reactivate_malformed_stale_and_matching_if_match() -> None:
    _, user, workspace = _extended_scenario()
    client = _client(user)
    _initialize_workflow(client, workspace, "Goal")
    goal_id = _create_goal(client, workspace)["id"]

    archived = client.post(
        f"/api/v1/goals/{goal_id}/outdate/", {"change_reason": "done"}, format="json"
    )
    assert archived.status_code == 200, archived.content
    archived_revision = _goal_revision(client, goal_id)

    malformed = client.post(
        f"/api/v1/goals/{goal_id}/reactivate/",
        {},
        format="json",
        HTTP_IF_MATCH="garbage",
    )
    assert malformed.status_code == 400, malformed.content
    assert malformed.json()["error"]["code"] == "INVALID_IF_MATCH", malformed.content

    stale = client.post(
        f"/api/v1/goals/{goal_id}/reactivate/",
        {},
        format="json",
        HTTP_IF_MATCH='"999999"',
    )
    assert stale.status_code == 409, stale.content
    assert stale.json()["error"]["code"] == "CONFLICT", stale.content

    matching = client.post(
        f"/api/v1/goals/{goal_id}/reactivate/",
        {},
        format="json",
        HTTP_IF_MATCH=f'"{archived_revision}"',
    )
    assert matching.status_code == 200, matching.content


# ---------------------------------------------------------------------------
# F9 — baseline PATCH parses the header before loading the row
# ---------------------------------------------------------------------------


def _baseline(client: APIClient, workspace: Workspace) -> str:
    created = client.post(
        "/api/v1/baselines/",
        {
            "workspace_id": str(workspace.id),
            "scope": "project",
            "name": "Gap baseline",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    return f"/api/v1/baselines/{created.json()['id']}/"


def test_baseline_patch_unknown_id_with_malformed_header_is_400_not_405() -> None:
    _, user, workspace = _extended_scenario()
    client = _client(user)

    resp = client.patch(
        f"/api/v1/baselines/{uuid.uuid4()}/",
        {},
        format="json",
        HTTP_IF_MATCH="garbage",
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", resp.content


def test_baseline_patch_known_id_with_malformed_header_is_400() -> None:
    _, user, workspace = _extended_scenario()
    client = _client(user)
    url = _baseline(client, workspace)

    resp = client.patch(url, {}, format="json", HTTP_IF_MATCH="garbage")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", resp.content


def test_baseline_patch_without_a_header_still_answers_405() -> None:
    """F9 must not change the header-less answer for an immutable resource."""
    _, user, workspace = _extended_scenario()
    client = _client(user)
    url = _baseline(client, workspace)

    resp = client.patch(url, {}, format="json")

    assert resp.status_code == 405, resp.content


# ---------------------------------------------------------------------------
# F8 — the schema filter drops the query parameter only
# ---------------------------------------------------------------------------


def test_schema_filter_keeps_a_path_parameter_named_workspace_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The old filter compared on ``name`` alone, deleting a required path param."""
    from rest_api import views as views_module

    parameters = [
        {"name": "workspace_id", "in": "query", "required": True},
        {"name": "workspace_id", "in": "path", "required": True},
        {"name": "workspace_pk", "in": "path", "required": True},
        {"name": "limit", "in": "query", "required": False},
        {"name": "no_location"},
    ]
    monkeypatch.setattr(
        views_module.ReqLoAutoSchema,
        "_get_parameters",
        lambda self: list(parameters),
    )
    schema = views_module._BaselineAutoSchema()
    schema.method = "GET"
    schema.path = "/api/v1/workspaces/{workspace_pk}/baselines/"

    kept = schema._get_parameters()

    assert {"name": "workspace_id", "in": "query", "required": True} not in kept
    assert {"name": "workspace_id", "in": "path", "required": True} in kept
    assert {"name": "workspace_pk", "in": "path", "required": True} in kept
    assert {"name": "no_location"} in kept


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def _parameters(operation: dict) -> list[dict]:
    return operation.get("parameters", []) or []


def test_nested_baseline_route_keeps_its_workspace_path_parameter(
    openapi_schema: dict,
) -> None:
    operation = openapi_schema["paths"][
        "/api/v1/workspaces/{workspace_pk}/baselines/"
    ]["get"]
    parameters = _parameters(operation)

    assert any(
        p.get("name") == "workspace_pk" and p.get("in") == "path"
        for p in parameters
    ), parameters
    assert not any(
        p.get("name") == "workspace_id" and p.get("in") == "query"
        for p in parameters
    ), parameters


def test_flat_baseline_route_still_requires_workspace_id_query(
    openapi_schema: dict,
) -> None:
    operation = openapi_schema["paths"]["/api/v1/baselines/"]["get"]
    parameter = next(
        (
            p
            for p in _parameters(operation)
            if p.get("name") == "workspace_id" and p.get("in") == "query"
        ),
        None,
    )

    assert parameter is not None, _parameters(operation)
    assert parameter["required"] is True


# ---------------------------------------------------------------------------
# m3 / m4 — the mixin itself
# ---------------------------------------------------------------------------


class _Versioned:
    version = 4


class _Timestamped:
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _request(header: str) -> SimpleNamespace:
    return SimpleNamespace(headers={"If-Match": header}, META={})


def test_tag_list_matching_a_numeric_tag_still_forwards_the_version() -> None:
    mixin = ETagMixin()

    resolved = mixin.resolve_expected_version(
        _request('"999", "4"'), {}, current=lambda: _Versioned()
    )

    assert resolved == 4


def test_tag_list_matching_a_timestamp_tag_is_a_mismatch_not_an_unguarded_write(
) -> None:
    """m3: returning ``None`` here told the service "compare nothing"."""
    mixin = ETagMixin()
    timestamp = compute_etag(_Timestamped())
    assert timestamp is not None and not timestamp.strip('"').isdigit()

    with pytest.raises(IfMatchMismatch):
        mixin.resolve_expected_version(
            _request(f'"888", {timestamp}'), {}, current=lambda: _Timestamped()
        )


def test_if_match_error_does_not_turn_a_programming_error_into_412() -> None:
    """m4: only ``IfMatchMismatch`` may answer 412."""
    mixin = ETagMixin()
    request = SimpleNamespace(META={})

    with pytest.raises(TypeError):
        mixin.if_match_error(request, TypeError("boom"))

    invalid = mixin.if_match_error(request, InvalidIfMatch("not a tag"))
    assert invalid.status_code == 400
    assert invalid.data["error"]["code"] == "INVALID_IF_MATCH"

    mismatch = mixin.if_match_error(request, IfMatchMismatch("stale"))
    assert mismatch.status_code == 412
    assert mismatch.data["error"]["code"] == "PRECONDITION_FAILED"


# ---------------------------------------------------------------------------
# Header-less callers are unchanged
# ---------------------------------------------------------------------------


def test_headerless_metadata_patch_is_unchanged() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    before = _live(workspace).version

    resp = client.patch(_ws_url(workspace), {"name": "Renamed"}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["name"] == "Renamed"
    assert resp.json()["version"] == before + 1
    assert resp["ETag"] == f'"{_live(workspace).version}"'


def test_headerless_lifecycle_patch_still_closes() -> None:
    _, user, workspace = _scenario()
    client = _client(user)

    resp = client.patch(_ws_url(workspace), {"is_active": False}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["is_active"] is False
    assert resp.json()["closed_at"] is not None


def test_headerless_stale_body_expected_version_keeps_its_409() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    stale = _live(workspace).version
    assert (
        client.patch(_ws_url(workspace), {"name": "First"}, format="json").status_code
        == 200
    )

    resp = client.patch(
        _ws_url(workspace),
        {"name": "Second", "expected_version": stale},
        format="json",
    )

    assert resp.status_code == 409, resp.content
    assert resp.json()["error"]["code"] == "CONFLICT", resp.content
