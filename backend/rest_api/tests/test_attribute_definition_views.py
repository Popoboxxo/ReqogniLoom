"""REST surface for attribute definitions (spec section 5)."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore

TITLE = {"name": "title", "kind": "core", "type": "text"}


@pytest.fixture
def seeded(tenant_fixture):
    store = GlobalAttributeDefinitionStore()
    for preset in ("minimal", "standard", "extended"):
        store.initialize(tenant_fixture.id, "Risk", preset, [TITLE])
    return store


@pytest.mark.django_db
def test_get_global_returns_an_uninitialized_stub_instead_of_404(admin_client) -> None:
    response = admin_client.get("/api/v1/attribute-defaults/Icd/minimal/")
    assert response.status_code == 200
    assert response.json()["initialized"] is False
    assert response.json()["attributes"] == []


@pytest.mark.django_db
def test_get_global_requires_admin(editor_client, seeded) -> None:
    response = editor_client.get("/api/v1/attribute-defaults/Risk/standard/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_globals(admin_client, seeded) -> None:
    response = admin_client.get("/api/v1/attribute-defaults/?item_type=Risk")
    assert response.status_code == 200
    assert len(response.json()["definitions"]) == 3


@pytest.mark.django_db
def test_put_global_updates_and_reports_the_propagated_count(admin_client, seeded) -> None:
    response = admin_client.put(
        "/api/v1/attribute-defaults/Risk/standard/",
        {"attributes": [dict(TITLE, required=True)]},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attributes"][0]["required"] is True
    assert body["propagated_workspace_count"] == 0
    assert body["version"] == 2


@pytest.mark.django_db
def test_put_global_rejects_a_core_rename_with_400(admin_client, seeded) -> None:
    response = admin_client.put(
        "/api/v1/attribute-defaults/Risk/standard/",
        {"attributes": [{"name": "headline", "kind": "core", "type": "text"}]},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_put_global_of_an_uninitialized_row_is_404(admin_client) -> None:
    response = admin_client.put(
        "/api/v1/attribute-defaults/Icd/minimal/",
        {"attributes": [TITLE]},
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_put_global_without_an_attributes_key_is_400(admin_client, seeded) -> None:
    response = admin_client.put(
        "/api/v1/attribute-defaults/Risk/standard/", {}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_post_global_creates_an_extended_attribute(admin_client, seeded) -> None:
    response = admin_client.post(
        "/api/v1/attribute-defaults/Risk/standard/",
        {"name": "risk_comment", "kind": "extended", "type": "text"},
        format="json",
    )
    assert response.status_code == 201
    assert "risk_comment" in [a["name"] for a in response.json()["attributes"]]


@pytest.mark.django_db
def test_post_global_rejects_a_colliding_name_with_400(admin_client, seeded) -> None:
    response = admin_client.post(
        "/api/v1/attribute-defaults/Risk/standard/",
        {"name": "title", "kind": "extended", "type": "text"},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_post_global_requires_admin(editor_client, seeded) -> None:
    response = editor_client.post(
        "/api/v1/attribute-defaults/Risk/standard/",
        {"name": "risk_comment", "kind": "extended", "type": "text"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_delete_global_removes_an_extended_attribute(admin_client, tenant_fixture) -> None:
    GlobalAttributeDefinitionStore().initialize(
        tenant_fixture.id, "Risk", "standard",
        [TITLE, {"name": "note", "kind": "extended", "type": "text"}],
    )
    response = admin_client.delete(
        "/api/v1/attribute-defaults/Risk/standard/?name=note"
    )
    assert response.status_code == 200
    assert "note" not in [a["name"] for a in response.json()["attributes"]]


@pytest.mark.django_db
def test_delete_global_rejects_a_core_attribute_with_400(admin_client, seeded) -> None:
    response = admin_client.delete(
        "/api/v1/attribute-defaults/Risk/standard/?name=title"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_get_workspace_definition_is_open_to_a_non_admin(
    editor_client, workspace_fixture, seeded
) -> None:
    response = editor_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
    )
    assert response.status_code == 200
    assert response.json()["is_customized"] is False


@pytest.mark.django_db
def test_put_workspace_definition_requires_admin(
    editor_client, workspace_fixture, seeded
) -> None:
    response = editor_client.put(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/",
        {"attributes": [TITLE]},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_put_then_reset_workspace_definition(
    admin_client, workspace_fixture, seeded
) -> None:
    base = f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
    admin_client.get(base)
    put = admin_client.put(
        base,
        {"attributes": [TITLE, {"name": "note", "kind": "extended", "type": "text"}]},
        format="json",
    )
    assert put.status_code == 200
    assert put.json()["is_customized"] is True

    reset = admin_client.post(f"{base}reset/", {}, format="json")
    assert reset.status_code == 200
    assert reset.json()["is_customized"] is False
    assert [a["name"] for a in reset.json()["attributes"]] == ["title"]


@pytest.mark.django_db
def test_post_workspace_creates_a_workspace_only_attribute(
    admin_client, workspace_fixture, seeded
) -> None:
    response = admin_client.post(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/",
        {"name": "risk_comment", "kind": "extended", "type": "text"},
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["is_customized"] is True
    assert "risk_comment" in [a["name"] for a in body["attributes"]]


@pytest.mark.django_db
def test_post_workspace_requires_admin(editor_client, workspace_fixture, seeded) -> None:
    response = editor_client.post(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/",
        {"name": "risk_comment", "kind": "extended", "type": "text"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_delete_workspace_rejects_a_core_attribute_with_400(
    admin_client, workspace_fixture, seeded
) -> None:
    response = admin_client.delete(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/?name=title"
    )
    assert response.status_code == 400  # 'title' is kind="core"


@pytest.mark.django_db
def test_delete_workspace_removes_an_extended_attribute(
    admin_client, workspace_fixture, seeded
) -> None:
    admin_client.post(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/",
        {"name": "risk_comment", "kind": "extended", "type": "text"},
        format="json",
    )
    response = admin_client.delete(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
        f"?name=risk_comment"
    )
    assert response.status_code == 200
    assert "risk_comment" not in [a["name"] for a in response.json()["attributes"]]


@pytest.mark.django_db
def test_get_usage_count_of_an_unreferenced_attribute_is_zero(
    admin_client, workspace_fixture, seeded
) -> None:
    response = admin_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/usage/"
        f"?name=note"
    )
    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.django_db
def test_get_usage_count_requires_admin(editor_client, workspace_fixture, seeded) -> None:
    response = editor_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/usage/"
        f"?name=note"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_get_usage_count_without_a_name_is_400(
    admin_client, workspace_fixture, seeded
) -> None:
    response = admin_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/usage/"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_workspace_definition_without_a_global_is_404(
    admin_client, workspace_fixture
) -> None:
    response = admin_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Goal/"
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_unknown_workspace_uuid_is_404(admin_client, seeded) -> None:
    response = admin_client.get(
        f"/api/v1/workspaces/{uuid.uuid4()}/attribute-definitions/Risk/"
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cross-tenant isolation (code review, Task 10). ``authed_client`` is an admin
# of the *Bundle* tenant while ``workspace_fixture`` belongs to
# ``tenant_fixture`` — i.e. two genuinely different tenants, no extra fixture
# needed. A workspace that exists but is owned by someone else is 403, never a
# 500 and never a 200.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_foreign_tenant_workspace_is_403_not_500(
    authed_client, workspace_fixture, seeded
) -> None:
    response = authed_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_a_warm_cache_entry_is_not_served_across_tenants(
    admin_client, authed_client, workspace_fixture, seeded
) -> None:
    """The owner's read warms ``attribute_def_cache_key`` (keyed by workspace
    alone); a foreign tenant must still be rejected instead of getting a 200
    off that entry. Same trap ``presets.gate.get_preset`` guards for its own
    ``_tier_cache`` (SA-15)."""
    warm = admin_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
    )
    assert warm.status_code == 200

    response = authed_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
    )
    assert response.status_code == 403, (
        "cross-tenant read served from the shared cache: "
        f"{response.content[:200]!r}"
    )
