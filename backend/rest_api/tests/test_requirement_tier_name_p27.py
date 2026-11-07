"""P2.7: ``tier_name`` on the Requirement payload (V4/V5 naming layer).

The display name is resolved from the workspace's tier ladder through the
stable ``tier_key``. One ladder read per request supplies a
``{tier_key: name}`` map to the serializer, so the list endpoint's query count
does not grow with the number of requirements.
"""
from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from persistence.models import Artifact, Requirement, WorkspaceTier
from rest_api.views import _dto_from_orm
from rest_api.serializers import RequirementSerializer

pytestmark = pytest.mark.django_db


def _tier(tenant, workspace, key: str, name: dict, position: int, rule: str, from_end=None):
    return WorkspaceTier.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        tier_key=key,
        name=name,
        position=position,
        rule=rule,
        from_end=from_end,
    )


def _requirement(tenant, workspace, *, title: str, tier_key: str | None, uid: str):
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        sort_key="a0",
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=uid,
        tier_key=tier_key,
    )


def _three_name_ladder(tenant, workspace):
    _tier(tenant, workspace, "erste", {"de": "Erste", "en": "First"}, 0, "first")
    _tier(tenant, workspace, "dazwischen", {"de": "Mitte", "en": "Middle"}, 1, "middle")
    _tier(tenant, workspace, "letzte", {"de": "Letzte", "en": "Last"}, 2, "from_end", 0)


def _six_entry_ladder(tenant, workspace):
    """A valid six-entry ladder: one first, one middle, four from-the-end."""
    names = [
        ("p0", {"de": "System", "en": "System"}, "first", None),
        ("p1", {"de": "Teilsystem", "en": "Subsystem"}, "middle", None),
        ("p2", {"de": "Baugruppe", "en": "Assembly"}, "from_end", 3),
        ("p3", {"de": "Baugruppe 2", "en": "Assembly 2"}, "from_end", 2),
        ("p4", {"de": "Vorletzte", "en": "Second to last"}, "from_end", 1),
        ("p5", {"de": "Letzte", "en": "Last"}, "from_end", 0),
    ]
    for position, (key, name, rule, from_end) in enumerate(names):
        _tier(tenant, workspace, key, name, position, rule, from_end)


def test_tier_name_resolves_three_entry_ladder(tenant, workspace, authed_client):
    _three_name_ladder(tenant, workspace)
    req = _requirement(tenant, workspace, title="R1", tier_key="dazwischen", uid="R-1")

    response = authed_client.get(f"/api/v1/requirements/{req.id}/")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["tier_key"] == "dazwischen"
    assert body["tier_name"] == "Middle"


def test_tier_name_resolves_six_entry_ladder(tenant, workspace, authed_client):
    _six_entry_ladder(tenant, workspace)
    req = _requirement(tenant, workspace, title="R2", tier_key="p3", uid="R-2")

    response = authed_client.get(f"/api/v1/requirements/{req.id}/")

    assert response.status_code == 200, response.content
    assert response.json()["tier_name"] == "Assembly 2"


def test_tier_name_is_null_when_unresolved(tenant, workspace, authed_client):
    _three_name_ladder(tenant, workspace)
    no_tier = _requirement(tenant, workspace, title="R3", tier_key=None, uid="R-3")
    unknown_tier = _requirement(
        tenant, workspace, title="R4", tier_key="not-in-ladder", uid="R-4"
    )

    for req in (no_tier, unknown_tier):
        response = authed_client.get(f"/api/v1/requirements/{req.id}/")
        assert response.status_code == 200, response.content
        assert response.json()["tier_name"] is None


def test_tier_name_is_null_without_ladder_map_in_context(tenant, workspace):
    """Nested/secondary serialisations must not query the ladder themselves."""
    from persistence.tenancy import TenantContext

    _three_name_ladder(tenant, workspace)
    req = _requirement(tenant, workspace, title="R5", tier_key="erste", uid="R-5")

    # The workflow-state mixin reads through the tenant-scoped manager, so a
    # direct serializer call needs the context the request path installs.
    TenantContext.set_tenant(tenant.id)
    try:
        payload = RequirementSerializer(_dto_from_orm(req)).data
    finally:
        TenantContext.clear_tenant()

    assert payload["tier_key"] == "erste"
    assert payload["tier_name"] is None


def test_create_and_update_responses_carry_tier_name(tenant, workspace, authed_client):
    _three_name_ladder(tenant, workspace)

    created = authed_client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace.id), "title": "Fresh requirement"},
        format="json",
    )
    assert created.status_code == 201, created.content
    # A brand-new requirement has no tier yet, but the key is present.
    assert created.json()["tier_name"] is None

    req = _requirement(tenant, workspace, title="R6", tier_key="letzte", uid="R-6")
    patched = authed_client.patch(
        f"/api/v1/requirements/{req.id}/",
        {"description": "changed", "change_reason": "tier_name regression check"},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["tier_name"] == "Last"


def test_list_resolves_tier_name_from_one_ladder_read(tenant, workspace, authed_client):
    _three_name_ladder(tenant, workspace)
    expected = {
        "erste": "First",
        "dazwischen": "Middle",
        "letzte": "Last",
    }
    for index, tier_key in enumerate(expected):
        _requirement(
            tenant, workspace, title=f"List {index}", tier_key=tier_key, uid=f"L-{index}"
        )

    response = authed_client.get(
        f"/api/v1/requirements/?workspace_id={workspace.id}&page_size=100"
    )

    assert response.status_code == 200, response.content
    results = response.json()["results"]
    assert len(results) == 3
    assert {row["tier_key"]: row["tier_name"] for row in results} == expected


def test_list_query_count_is_independent_of_requirement_count(
    tenant, workspace, authed_client
):
    _three_name_ladder(tenant, workspace)
    for index in range(5):
        _requirement(
            tenant, workspace, title=f"Q{index}", tier_key="erste", uid=f"Q-{index}"
        )

    url = f"/api/v1/requirements/?workspace_id={workspace.id}&page_size=500"

    # Warm-up: ladder seeding, permission and preset caches.
    assert authed_client.get(url).status_code == 200
    with CaptureQueriesContext(connection) as small:
        assert authed_client.get(url).status_code == 200

    for index in range(5, 25):
        _requirement(
            tenant, workspace, title=f"Q{index}", tier_key="erste", uid=f"Q-{index}"
        )

    with CaptureQueriesContext(connection) as large:
        response = authed_client.get(url)
    assert response.status_code == 200
    assert len(response.json()["results"]) == 25

    assert len(large.captured_queries) == len(small.captured_queries), (
        "tier_name must not add a query per requirement: "
        f"5 rows -> {len(small.captured_queries)} queries, "
        f"25 rows -> {len(large.captured_queries)} queries"
    )
