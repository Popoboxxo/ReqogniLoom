"""Plan F F2-T5 (PR-F18a) — the Document REST surface.

Covers the contract ADR-026 and the F2 spec fix for this task:

* CRUD: create allocates ``DOC-NNN``, reports ``Entwurf`` and emits an ETag;
  retrieve/list/update/delete/reactivate round-trip through
  ``DocumentService`` (ADR-01);
* **KA-F-08 / ETag:** GET/POST/PATCH carry ``ETag: "<version>"``; a stale
  strong ``If-Match`` answers ``412``, a stale body ``expected_version``
  answers ``409``, and a malformed header answers ``400 INVALID_IF_MATCH``;
* **F-3 freeze:** a PATCH touching a frozen field answers ``409
  FIELD_FROZEN`` with a per-field ``details`` list, while ``doc_date`` and
  ``custom_fields`` stay writable (F-2);
* **Gates G-1…G-4:** a release refused by rule 9 answers ``409
  DOCUMENT_GATE_FAILED`` with structured details (G-4 here);
* **G1.5 soft delete:** ``DELETE`` → ``204``; GET → ``200`` + ``outdated``;
  lists hide the row unless ``?include_deleted=true``; reactivate restores it;
* **G2.1 ordering:** the list follows ``-modified_at, id`` deterministically;
* **R-X-1:** ``/api/v1/trace-links/`` honours the ``link_type`` filter on both
  the workspace-wide and the per-artifact branch;
* tenant fence: another tenant cannot read a document.

The workspace fixture runs the Extended preset, so every transition carries a
``change_reason`` — that is the stricter (not the laxer) preset and proves the
gate wiring.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, TraceLink, User, Workspace
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

COLLECTION = "/api/v1/documents/"
RELEASE_STATE = "Freigegeben"
REVIEW_STATE = "In Prüfung"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _document_workflow(tenant, workspace):
    """Provision the ``document_default`` workflow the transitions need."""
    set_request_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=tenant.id,
        )
    finally:
        clear_request_tenant()


def _payload(workspace, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "title": "System Spec",
        "kind": "Spec",
        "description": "How the system behaves",
        "body": "# System Spec\n\nContent.",
    }
    payload.update(overrides)
    return payload


def _create(client, workspace, **overrides) -> dict:
    response = client.post(COLLECTION, _payload(workspace, **overrides), format="json")
    assert response.status_code == 201, response.content
    return response.json()


def _transition(client, document_id: str, target: str, **extra) -> object:
    body = {"target_state": target, "change_reason": "test transition", **extra}
    return client.post(
        f"{COLLECTION}{document_id}/transitions/", body, format="json"
    )


def _in_review(client, doc: dict) -> None:
    response = _transition(client, doc["id"], REVIEW_STATE)
    assert response.status_code == 200, response.content


# ---------------------------------------------------------------------------
# CRUD + ETag
# ---------------------------------------------------------------------------


def test_create_allocates_uid_reports_initial_state_and_emits_etag(
    authed_client, workspace
) -> None:
    response = authed_client.post(COLLECTION, _payload(workspace), format="json")

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["uid"].startswith("DOC-")
    assert body["workspace_id"] == str(workspace.id)
    assert body["status"] == "Entwurf"
    assert body["version"] == 1
    assert body["frozen_at"] is None
    assert body["frozen_fields"] == []
    # The backing Artifact makes the document a trace-link endpoint.
    assert body["artifact_id"]
    # #1079-style: a client can PATCH conditionally without a second GET.
    assert response["ETag"] == '"1"'


def test_retrieve_returns_etag_and_the_engine_status(authed_client, workspace) -> None:
    doc = _create(authed_client, workspace)

    response = authed_client.get(f"{COLLECTION}{doc['id']}/")

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "Entwurf"
    assert response["ETag"] == '"1"'


def test_update_increments_version_and_returns_the_new_etag(
    authed_client, workspace
) -> None:
    doc = _create(authed_client, workspace)

    response = authed_client.patch(
        f"{COLLECTION}{doc['id']}/", {"title": "Renamed"}, format="json"
    )

    assert response.status_code == 200, response.content
    assert response.json()["title"] == "Renamed"
    assert response.json()["version"] == 2
    assert response["ETag"] == '"2"'


def test_list_is_deterministically_ordered_and_hides_deleted(
    authed_client, workspace
) -> None:
    first = _create(authed_client, workspace, title="First")
    second = _create(authed_client, workspace, title="Second")
    third = _create(authed_client, workspace, title="Third")
    # Touch `first` so -modified_at puts it ahead of the untouched rows.
    assert (
        authed_client.patch(
            f"{COLLECTION}{first['id']}/", {"title": "First updated"}, format="json"
        ).status_code
        == 200
    )

    response = authed_client.get(f"{COLLECTION}?workspace_id={workspace.id}")

    assert response.status_code == 200, response.content
    ids = [row["id"] for row in response.json()["results"]]
    assert ids[0] == first["id"]
    assert set(ids) == {first["id"], second["id"], third["id"]}

    # Determinism: two calls return the same order (G2.1).
    again = authed_client.get(f"{COLLECTION}?workspace_id={workspace.id}")
    assert [row["id"] for row in again.json()["results"]] == ids

    assert (
        authed_client.delete(
            f"{COLLECTION}{third['id']}/?change_reason=obsolete"
        ).status_code
        == 204
    )
    hidden = authed_client.get(f"{COLLECTION}?workspace_id={workspace.id}")
    assert third["id"] not in [row["id"] for row in hidden.json()["results"]]

    visible = authed_client.get(
        f"{COLLECTION}?workspace_id={workspace.id}&include_deleted=true"
    )
    assert third["id"] in [row["id"] for row in visible.json()["results"]]


# ---------------------------------------------------------------------------
# ETag / If-Match (KA-F-08)
# ---------------------------------------------------------------------------


def test_stale_if_match_is_412_and_a_stale_body_version_is_409(
    authed_client, workspace
) -> None:
    doc = _create(authed_client, workspace)
    assert (
        authed_client.patch(
            f"{COLLECTION}{doc['id']}/", {"title": "v2"}, format="json"
        ).status_code
        == 200
    )

    stale_header = authed_client.patch(
        f"{COLLECTION}{doc['id']}/",
        {"title": "should not land"},
        format="json",
        HTTP_IF_MATCH='"1"',
    )
    assert stale_header.status_code == 412, stale_header.content
    assert stale_header.json()["error"]["code"] == "PRECONDITION_FAILED"

    stale_body = authed_client.patch(
        f"{COLLECTION}{doc['id']}/",
        {"title": "should not land either", "expected_version": 1},
        format="json",
    )
    assert stale_body.status_code == 409, stale_body.content
    assert stale_body.json()["error"]["code"] == "CONFLICT"

    unchanged = authed_client.get(f"{COLLECTION}{doc['id']}/")
    assert unchanged.json()["title"] == "v2"

    malformed = authed_client.patch(
        f"{COLLECTION}{doc['id']}/",
        {"title": "nope"},
        format="json",
        HTTP_IF_MATCH="garbage",
    )
    assert malformed.status_code == 400, malformed.content
    assert malformed.json()["error"]["code"] == "INVALID_IF_MATCH"


def test_conditional_patch_with_the_current_tag_succeeds(
    authed_client, workspace
) -> None:
    doc = _create(authed_client, workspace)
    tag = authed_client.get(f"{COLLECTION}{doc['id']}/")["ETag"]

    response = authed_client.patch(
        f"{COLLECTION}{doc['id']}/",
        {"title": "guarded"},
        format="json",
        HTTP_IF_MATCH=tag,
    )

    assert response.status_code == 200, response.content
    assert response.json()["title"] == "guarded"


# ---------------------------------------------------------------------------
# Freeze F-3 and gates G-1…G-4
# ---------------------------------------------------------------------------


def test_patch_of_a_frozen_field_is_409_field_frozen(authed_client, workspace) -> None:
    doc = _create(authed_client, workspace)
    _in_review(authed_client, doc)
    released = _transition(authed_client, doc["id"], RELEASE_STATE)
    assert released.status_code == 200, released.content
    assert released.json()["document"]["status"] == RELEASE_STATE
    assert released.json()["document"]["frozen_at"] is not None

    blocked = authed_client.patch(
        f"{COLLECTION}{doc['id']}/", {"title": "rewritten"}, format="json"
    )
    assert blocked.status_code == 409, blocked.content
    error = blocked.json()["error"]
    assert error["code"] == "FIELD_FROZEN"
    assert error["details"] == [{"field": "title"}]

    # F-2: doc_date and custom_fields stay writable while frozen.
    assert (
        authed_client.patch(
            f"{COLLECTION}{doc['id']}/", {"doc_date": "2026-11-02"}, format="json"
        ).status_code
        == 200
    )
    assert (
        authed_client.patch(
            f"{COLLECTION}{doc['id']}/",
            {"custom_fields": {"owner_team": "platform"}},
            format="json",
        ).status_code
        == 200
    )


def test_release_gate_failure_is_409_document_gate_failed(
    authed_client, workspace
) -> None:
    # Extended/standard presets require `body` for every kind (G-4).
    doc = _create(authed_client, workspace, body="")
    _in_review(authed_client, doc)

    refused = _transition(authed_client, doc["id"], RELEASE_STATE)

    assert refused.status_code == 409, refused.content
    error = refused.json()["error"]
    assert error["code"] == "DOCUMENT_GATE_FAILED"
    assert any(entry["gate"] == "G-4" for entry in error["details"])


def test_reopen_lifts_the_freeze_and_allows_the_edit(authed_client, workspace) -> None:
    doc = _create(authed_client, workspace)
    _in_review(authed_client, doc)
    assert _transition(authed_client, doc["id"], RELEASE_STATE).status_code == 200

    reopened = _transition(authed_client, doc["id"], REVIEW_STATE)
    assert reopened.status_code == 200, reopened.content
    assert reopened.json()["document"]["frozen_at"] is None
    assert reopened.json()["version"] == 2

    assert (
        authed_client.patch(
            f"{COLLECTION}{doc['id']}/", {"title": "new version"}, format="json"
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# Soft delete / reactivate (G1.5)
# ---------------------------------------------------------------------------


def test_soft_delete_and_reactivate_contract(authed_client, workspace) -> None:
    doc = _create(authed_client, workspace)

    deleted = authed_client.delete(
        f"{COLLECTION}{doc['id']}/?change_reason=no longer needed"
    )
    assert deleted.status_code == 204, deleted.content

    # V3: the row survives and reports the soft-delete flag.
    detail = authed_client.get(f"{COLLECTION}{doc['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["status"] == "outdated"

    restored = authed_client.post(f"{COLLECTION}{doc['id']}/reactivate/")
    assert restored.status_code == 200, restored.content
    assert restored.json()["document"]["status"] == "Entwurf"

    assert (
        authed_client.get(f"{COLLECTION}{doc['id']}/").json()["status"]
        == "Entwurf"
    )


def test_delete_without_a_reason_is_400_on_the_extended_preset(
    authed_client, workspace
) -> None:
    doc = _create(authed_client, workspace)

    response = authed_client.delete(f"{COLLECTION}{doc['id']}/")

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Workflow transitions + ETag on the transition route
# ---------------------------------------------------------------------------


def test_transition_post_uses_the_document_service_and_guards_the_entity_version(
    authed_client, workspace
) -> None:
    doc = _create(authed_client, workspace)

    transitions = authed_client.get(f"{COLLECTION}{doc['id']}/transitions/")
    assert transitions.status_code == 200, transitions.content
    assert transitions.json()["current_state"] == "Entwurf"
    # On the Document route `version` is the entity revision (the ETag source).
    assert transitions.json()["version"] == 1

    stale = authed_client.post(
        f"{COLLECTION}{doc['id']}/transitions/",
        {"target_state": REVIEW_STATE, "change_reason": "review"},
        format="json",
        HTTP_IF_MATCH='"99"',
    )
    assert stale.status_code == 412, stale.content

    moved = _transition(authed_client, doc["id"], REVIEW_STATE)
    assert moved.status_code == 200, moved.content
    assert moved.json()["previous_state"] == "Entwurf"
    assert moved.json()["new_state"] == REVIEW_STATE


# ---------------------------------------------------------------------------
# Trace-link filter (R-X-1)
# ---------------------------------------------------------------------------


def test_tracelink_list_honours_the_link_type_filter(
    authed_client, workspace, tenant
) -> None:
    source = _create(authed_client, workspace, title="Source doc")
    target = _create(authed_client, workspace, title="Target doc")

    set_request_tenant(tenant.id)
    try:
        link = TraceLink.objects.create(
            tenant=tenant,
            source_id=source["artifact_id"],
            target_id=target["artifact_id"],
            link_type="references",
        )
    finally:
        clear_request_tenant()

    filtered = authed_client.get(
        f"/api/v1/trace-links/?workspace_id={workspace.id}&link_type=references"
    )
    assert filtered.status_code == 200, filtered.content
    ids = [row["id"] for row in filtered.json()["results"]]
    assert str(link.id) in ids
    assert all(row["link_type"] == "references" for row in filtered.json()["results"])

    empty = authed_client.get(
        f"/api/v1/trace-links/?workspace_id={workspace.id}&link_type=verifies"
    )
    assert empty.status_code == 200, empty.content
    assert empty.json()["results"] == []

    # The per-artifact branch honours the same filter.
    per_artifact = authed_client.get(
        f"/api/v1/trace-links/?workspace_id={workspace.id}"
        f"&artifact_id={source['artifact_id']}&link_type=references"
    )
    assert per_artifact.status_code == 200, per_artifact.content
    assert [row["id"] for row in per_artifact.json()["results"]] == [str(link.id)]


# ---------------------------------------------------------------------------
# Tenant fence
# ---------------------------------------------------------------------------


def test_foreign_tenant_cannot_read_a_document(
    authed_client, workspace, tenant
) -> None:
    doc = _create(authed_client, workspace)

    other_tenant = Tenant.objects.create(
        name="Other Document Tenant",
        slug=f"other-doc-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    set_request_tenant(other_tenant.id)
    try:
        other_workspace = Workspace.objects.create(
            tenant=other_tenant, name="Other WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()
    client = _foreign_client(other_tenant, other_workspace)

    response = client.get(f"{COLLECTION}{doc['id']}/")

    # The user holds a real role (so RBAC lets the read through) but in another
    # tenant: the object does not exist there, so the answer is 404 — never a
    # cross-tenant peek (ADR-013 404-vs-403 rule).
    assert response.status_code == 404, response.content


def _foreign_client(tenant: Tenant, workspace: Workspace):
    """An authenticated client whose user belongs to *tenant* only."""
    from rest_framework.test import APIClient

    user = User.objects.create(
        username=f"foreign-{uuid.uuid4().hex[:8]}",
        email=f"foreign-{uuid.uuid4().hex[:8]}@t.test",
        tenant=tenant,
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client
