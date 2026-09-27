"""A reset that cannot reset is a 409, not a 500 (issue #1082).

``WorkspaceAttributeDefinitionStore.reset`` raises
:class:`AttributeDefinitionConflictError` when the workspace row is *not*
customized **and** already holds its source's content — there is no local
override to discard, because the change lives in the tenant-wide
``ad_global_definition`` row. The exception is a plain ``ValueError`` (via
``AttributeSchemaError``), not a DRF exception, so
``WorkspaceAttributeDefinitionResetView.post`` had no handler for it and the
no-op reset surfaced as a **500**.

The refusal itself is correct and stays; only the HTTP mapping was missing.
``AttributeDefinitionNotFound`` and ``AttributeDefinitionConflictError`` are
disjoint branches (``LookupError`` vs ``ValueError``), so catching the conflict
first is clarity, not necessity — but it is the same order the two existing
CONFLICT sites in this file use.
"""
from __future__ import annotations

import pytest

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore

pytestmark = pytest.mark.django_db

TITLE = {"name": "title", "kind": "core", "type": "text"}


@pytest.fixture
def seeded(tenant_fixture):
    store = GlobalAttributeDefinitionStore()
    for preset in ("minimal", "standard", "extended"):
        store.initialize(tenant_fixture.id, "Risk", preset, [TITLE])
    return store


def _base(workspace_id, item_type: str = "Risk") -> str:
    return f"/api/v1/workspaces/{workspace_id}/attribute-definitions/{item_type}/"


def test_a_no_op_reset_is_409_not_500(
    admin_client, tenant_fixture, workspace_fixture, seeded
) -> None:
    """#1082: the failing case.

    The GET materializes the workspace row as a non-customized copy of the
    global. A reset of that row would change nothing, so the store refuses —
    and the endpoint must say 409 CONFLICT in the canonical envelope.
    """
    base = _base(workspace_fixture.id)
    resolved = admin_client.get(base)
    assert resolved.status_code == 200, resolved.content
    assert resolved.json()["is_customized"] is False

    response = admin_client.post(f"{base}reset/", {}, format="json")

    assert response.status_code == 409, response.content
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["details"] == []
    # The message must point at the row that actually has to be edited,
    # otherwise the operator is back where they started.
    assert "nothing to reset" in body["error"]["message"]
    assert "Delete the attribute from the global default" in (
        body["error"]["message"]
    )


def test_a_real_reset_still_returns_200(
    admin_client, workspace_fixture, seeded
) -> None:
    """The 409 must not swallow the reset that does have work to do."""
    base = _base(workspace_fixture.id)
    admin_client.get(base)
    put = admin_client.put(
        base,
        {"attributes": [TITLE, {"name": "note", "kind": "extended", "type": "text"}]},
        format="json",
    )
    assert put.status_code == 200, put.content

    response = admin_client.post(f"{base}reset/", {}, format="json")

    assert response.status_code == 200, response.content
    assert response.json()["is_customized"] is False
    assert [a["name"] for a in response.json()["attributes"]] == ["title"]


def test_a_stale_non_customized_row_still_resets(
    admin_client, tenant_fixture, workspace_fixture, seeded
) -> None:
    """A non-customized row that *differs* from its source is a real reset.

    The conflict is specifically "not customized AND already equal"; without
    this test a too-broad 409 would silently break genuine re-materialization.
    """
    from attribute_definitions.workspace_definition_store import (
        WorkspaceAttributeDefinitionStore,
    )

    base = _base(workspace_fixture.id)
    admin_client.get(base)
    store = WorkspaceAttributeDefinitionStore()
    row = store.get(tenant_fixture.id, workspace_fixture.id, "Risk")
    row.definition_json = {
        "attributes": [TITLE, {"name": "stale", "kind": "extended", "type": "text"}]
    }
    row.save(update_fields=["definition_json"])

    response = admin_client.post(f"{base}reset/", {}, format="json")

    assert response.status_code == 200, response.content
    assert response.json()["is_customized"] is False
    assert [a["name"] for a in response.json()["attributes"]] == ["title"]


def test_a_definition_without_a_global_is_still_404(
    admin_client, workspace_fixture
) -> None:
    """The conflict handler must not swallow the not-found branch."""
    response = admin_client.post(
        f"{_base(workspace_fixture.id, 'Goal')}reset/", {}, format="json"
    )

    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "NOT_FOUND"
