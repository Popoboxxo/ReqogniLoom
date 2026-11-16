"""``GET /api/v1/artifacts/table/`` (Tabellenansicht S1, Task 1.6).

Pins the transport, not the service (``application/tests/test_table_query_service.py``):

* route resolution (the collection path is not swallowed by ``artifacts/<pk>/``),
* the paginated row shape the frontend ``ArtifactTable`` reads,
* the JSON ``filters``/``sort`` parameters and their 400 forms,
* the unknown-query-parameter guard and the ``page_size`` cap,
* workspace scoping (no rows from another workspace),
* 403 for a caller without a read role, and the item-level ``none`` rule that
  hides a row *and* the count for one user only,
* no ``ETag`` (this route is not one of the conditional-request families).
"""
from __future__ import annotations

import json
import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import (
    ITEM_PERMISSION_NONE,
    ROLE_EDITOR,
    ItemPermission,
    UserRole,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

TABLE = "/api/v1/artifacts/table/"
_PASSWORD = "hunter2pass"


def _requirement(tenant, workspace, title, *, uid=None) -> Requirement:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            title=title,
            uid=uid or f"R-{title}",
            description=f"d {title}",
        )
    finally:
        clear_request_tenant()


def _client_for(tenant, workspace, *, role: str | None = ROLE_EDITOR) -> tuple[APIClient, User]:
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"tbl-{suffix}", email=f"tbl-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    if role is not None:
        set_request_tenant(tenant.id)
        try:
            UserRole.objects.create(
                tenant=tenant, user=user, workspace=workspace, role=role
            )
        finally:
            clear_request_tenant()
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client, user


def _params(workspace, **overrides):
    params = {"workspace_id": str(workspace.id), "item_type": "Requirement"}
    params.update(overrides)
    return params


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_table_returns_page_with_row_shape(authed_client, tenant, workspace):
    requirement = _requirement(tenant, workspace, "Alpha")

    response = authed_client.get(TABLE, _params(workspace))

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) >= {
        "count",
        "next",
        "previous",
        "page_size",
        "max_page_size",
        "results",
    }
    assert body["count"] == 1
    row = body["results"][0]
    assert set(row) == {"id", "artifact_id", "item_type", "version", "values", "locked"}
    assert row["id"] == str(requirement.id)
    assert row["artifact_id"] == str(requirement.artifact_id)
    assert row["item_type"] == "Requirement"
    assert row["values"]["title"] == "Alpha"
    assert row["locked"] is None


def test_table_filters_and_sort_json(authed_client, tenant, workspace):
    _requirement(tenant, workspace, "Alpha")
    _requirement(tenant, workspace, "Alpaka")
    _requirement(tenant, workspace, "Beta")

    response = authed_client.get(
        TABLE,
        _params(
            workspace,
            filters=json.dumps({"title": {"op": "contains", "value": "Alp"}}),
            sort=json.dumps([{"field": "title", "dir": "desc"}]),
        ),
    )

    assert response.status_code == 200, response.content
    titles = [row["values"]["title"] for row in response.json()["results"]]
    assert titles == ["Alpha", "Alpaka"]


def test_table_page_size_is_capped_at_100(authed_client, tenant, workspace):
    for index in range(3):
        _requirement(tenant, workspace, f"Row{index}")

    response = authed_client.get(TABLE, _params(workspace, page_size="500"))

    assert response.status_code == 200
    body = response.json()
    assert body["page_size"] == 100
    assert body["max_page_size"] == 100


def test_table_excludes_outdated_by_default(authed_client, tenant, workspace):
    _requirement(tenant, workspace, "Active")
    gone = _requirement(tenant, workspace, "Gone")
    set_request_tenant(tenant.id)
    try:
        Artifact.objects.filter(id=gone.artifact_id).update(
            lifecycle_status="outdated"
        )
    finally:
        clear_request_tenant()

    assert authed_client.get(TABLE, _params(workspace)).json()["count"] == 1
    included = authed_client.get(TABLE, _params(workspace, include_deleted="true"))
    assert included.json()["count"] == 2


# ---------------------------------------------------------------------------
# Bad requests
# ---------------------------------------------------------------------------


def test_table_invalid_filter_is_400_with_field_name(authed_client, workspace):
    response = authed_client.get(
        TABLE,
        _params(
            workspace,
            filters=json.dumps({"removed_attribute": {"op": "contains", "value": "x"}}),
        ),
    )

    assert response.status_code == 400
    assert "removed_attribute" in response.content.decode()


def test_table_malformed_json_is_400_naming_the_parameter(authed_client, workspace):
    response = authed_client.get(TABLE, _params(workspace, filters="{not json"))
    assert response.status_code == 400
    assert "filters" in response.content.decode()


def test_table_unknown_param_is_400(authed_client, workspace):
    response = authed_client.get(TABLE, _params(workspace, nope="1"))
    assert response.status_code == 400


def test_table_missing_item_type_is_400(authed_client, workspace):
    response = authed_client.get(TABLE, {"workspace_id": str(workspace.id)})
    assert response.status_code == 400


def test_table_unsupported_item_type_is_400(authed_client, workspace):
    response = authed_client.get(TABLE, _params(workspace, item_type="Goal"))
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Scoping and rights
# ---------------------------------------------------------------------------


def test_table_rows_from_another_workspace_are_absent(authed_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        other = Workspace.objects.create(tenant=tenant, name="other-ws")
    finally:
        clear_request_tenant()
    _requirement(tenant, workspace, "Mine")
    _requirement(tenant, other, "Theirs")

    response = authed_client.get(TABLE, _params(workspace))
    assert response.status_code == 200
    assert [row["values"]["title"] for row in response.json()["results"]] == ["Mine"]


def test_table_callers_workspace_is_not_bypassed(authed_client, tenant, workspace):
    """A foreign-tenant workspace id answers a denial, never rows."""
    foreign = Tenant.objects.create(name="foreign-tbl", slug="foreign-tbl")
    set_request_tenant(foreign.id)
    try:
        foreign_workspace = Workspace.objects.create(tenant=foreign, name="fw")
    finally:
        clear_request_tenant()
    _requirement(foreign, foreign_workspace, "Secret")

    response = authed_client.get(
        TABLE,
        {"workspace_id": str(foreign_workspace.id), "item_type": "Requirement"},
    )

    assert response.status_code in (403, 404)
    assert "Secret" not in response.content.decode()


def test_table_user_without_roles_is_403(tenant, workspace):
    client, _user = _client_for(tenant, workspace, role=None)
    response = client.get(TABLE, _params(workspace))
    assert response.status_code == 403


def test_table_item_level_none_rule_hides_row_and_count_for_one_user(
    authed_client, tenant, workspace
):
    _requirement(tenant, workspace, "Visible")
    hidden = _requirement(tenant, workspace, "Hidden")

    client, user = _client_for(tenant, workspace)
    set_request_tenant(tenant.id)
    try:
        ItemPermission.objects.create(
            tenant=tenant,
            user=user,
            workspace=workspace,
            artifact_id=hidden.artifact_id,
            permission_level=ITEM_PERMISSION_NONE,
        )
    finally:
        clear_request_tenant()

    mine = client.get(TABLE, _params(workspace)).json()
    everybody_else = authed_client.get(TABLE, _params(workspace)).json()

    assert mine["count"] == 1
    assert [row["values"]["title"] for row in mine["results"]] == ["Visible"]
    assert everybody_else["count"] == 2


# ---------------------------------------------------------------------------
# Routing / contract
# ---------------------------------------------------------------------------


def test_route_resolves_to_the_table_view():
    from django.urls import resolve

    from rest_api.table_views import TableQueryView

    assert resolve(TABLE).func.cls is TableQueryView


def test_table_publishes_no_etag(authed_client, tenant, workspace):
    _requirement(tenant, workspace, "Alpha")
    response = authed_client.get(TABLE, _params(workspace))
    assert "ETag" not in response.headers
