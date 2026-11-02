"""Plan F F3-T5 (PR-F24b) — the WorkItem REST surface (#1374).

Covers the contract the F3 spec fixes for this task:

* **CRUD:** create allocates ``WI-NNN``, reports the tier's initial state
  (``todo``) and emits an ETag; retrieve/list/update/delete/reactivate
  round-trip through ``WorkItemService`` (ADR-01);
* **document is mandatory (E11/O7):** a POST without ``document_id`` answers
  ``400``, and a document from another workspace is refused;
* **KA-F-08 / ETag:** GET/POST/PATCH carry ``ETag: "<version>"``; a stale
  strong ``If-Match`` answers ``412``, a stale body ``expected_version``
  ``409``, and a malformed header answers ``400 INVALID_IF_MATCH``;
* **transition:** the service enforces the tiered graph, rule 10
  (``blocked`` needs a non-empty ``blocked_reason``) and the extended preset's
  human sign-off (``in_review -> done`` is ``approver``/``admin`` only);
* **resume:** ``GET .../resume/`` returns the newest checkpoint and every open
  item, sorted ``(ordinal, id)``;
* **G1.5 soft delete:** ``DELETE`` → ``204``; GET → ``200`` + ``outdated``;
  lists hide the row unless ``?include_deleted=true``; reactivate restores it;
* **versions/diff:** every write records an ``ArtifactVersion``, so
  ``/versions/`` and ``/diff/`` line up with the lock counter;
* **gates:** unknown-field rejection, immutable ``document_id`` and the tenant
  fence.

The workspace fixture runs the Extended preset and the tier-matched
``work_item_extended`` lifecycle, so every transition carries a
``change_reason`` — the stricter (not the laxer) preset.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Document, Tenant, User, Workspace
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

COLLECTION = "/api/v1/work-items/"
IN_PROGRESS = "in_progress"
IN_REVIEW = "in_review"
BLOCKED = "blocked"
DONE = "done"
DROPPED = "dropped"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _work_item_workflow(tenant, workspace):
    """Provision the tier-matched ``work_item_extended`` lifecycle (F3-T2)."""
    set_request_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="work_item_extended",
            item_type="WorkItem",
            tenant_id=tenant.id,
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def document(tenant, workspace) -> Document:
    """A document in *workspace* (the mandatory home of every work item)."""
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Document"
        )
        return Document.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title="Work plan",
            kind=Document.Kind.PLAN,
            body="# Work plan",
        )
    finally:
        clear_request_tenant()


def _payload(workspace: Workspace, document: Document, **overrides) -> dict:
    payload = {
        "workspace_id": str(workspace.id),
        "document_id": str(document.id),
        "kind": "Step",
        "title": "Write the REST surface",
        "body": "## Step\n\nDo the work.",
    }
    payload.update(overrides)
    return payload


def _create(client, workspace, document, **overrides) -> dict:
    response = client.post(
        COLLECTION, _payload(workspace, document, **overrides), format="json"
    )
    assert response.status_code == 201, response.content
    return response.json()


def _transition(client, item_id: str, target: str, **extra):
    body = {"target_state": target, "change_reason": "test transition", **extra}
    return client.post(f"{COLLECTION}{item_id}/transition/", body, format="json")


def _role_client(
    tenant: Tenant, workspace: Workspace, role: str, *, suffix: str
):
    """An authenticated client whose user holds *role* in *workspace* only."""
    from rest_framework.test import APIClient

    user = User.objects.create(
        username=f"wi-{role}-{suffix}",
        email=f"wi-{role}-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
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
        {"username": user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


# ---------------------------------------------------------------------------
# CRUD + ETag
# ---------------------------------------------------------------------------


def test_create_requires_a_document(authed_client, workspace, document) -> None:
    payload = _payload(workspace, document)
    payload.pop("document_id")

    response = authed_client.post(COLLECTION, payload, format="json")

    assert response.status_code == 400, response.content
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any(entry["field"] == "document_id" for entry in error["details"])


def test_create_allocates_uid_reports_initial_state_and_emits_etag(
    authed_client, workspace, document
) -> None:
    response = authed_client.post(
        COLLECTION,
        _payload(workspace, document, progress=25, next_action="continue here"),
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["uid"].startswith("WI-")
    assert body["workspace_id"] == str(workspace.id)
    assert body["document_id"] == str(document.id)
    assert body["kind"] == "Step"
    assert body["status"] == "todo"
    assert body["progress"] == 25
    assert body["next_action"] == "continue here"
    assert body["version"] == 1
    # The backing Artifact makes the item a trace-link endpoint.
    assert body["artifact_id"]
    # #1079-style: a client can PATCH conditionally without a second GET.
    assert response["ETag"] == '"1"'


def test_retrieve_and_patch_roundtrip(authed_client, workspace, document) -> None:
    item = _create(authed_client, workspace, document)

    detail = authed_client.get(f"{COLLECTION}{item['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["status"] == "todo"
    assert detail["ETag"] == '"1"'

    updated = authed_client.patch(
        f"{COLLECTION}{item['id']}/",
        {"title": "Renamed", "progress": 60, "next_action": "next"},
        format="json",
    )
    assert updated.status_code == 200, updated.content
    assert updated.json()["title"] == "Renamed"
    assert updated.json()["progress"] == 60
    assert updated.json()["version"] == 2
    assert updated["ETag"] == '"2"'


def test_list_filters_by_document_and_is_deterministically_ordered(
    authed_client, tenant, workspace, document
) -> None:
    second = _create(authed_client, workspace, document, title="Second", ordinal=1)
    first = _create(authed_client, workspace, document, title="First", ordinal=0)
    other_document = _create_other_document(tenant, workspace)
    foreign = _create(
        authed_client, workspace, other_document, title="Other", ordinal=0
    )

    response = authed_client.get(f"{COLLECTION}?workspace_id={workspace.id}")

    assert response.status_code == 200, response.content
    ids = [row["id"] for row in response.json()["results"]]
    # ``(ordinal, id)`` is the contract (G2.1); the two ordinal-0 rows are
    # ordered by their UUIDs, not by creation time.
    assert ids == [
        row["id"]
        for row in sorted(
            [first, second, foreign], key=lambda item: (item["ordinal"], item["id"])
        )
    ]

    # Determinism: two calls return the same order (G2.1).
    again = authed_client.get(f"{COLLECTION}?workspace_id={workspace.id}")
    assert [row["id"] for row in again.json()["results"]] == ids

    filtered = authed_client.get(
        f"{COLLECTION}?workspace_id={workspace.id}&document_id={document.id}"
    )
    assert filtered.status_code == 200, filtered.content
    assert [row["id"] for row in filtered.json()["results"]] == [
        first["id"],
        second["id"],
    ]


def _create_other_document(tenant: Tenant, workspace: Workspace) -> Document:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Document"
        )
        return Document.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title="Other plan",
            kind=Document.Kind.PLAN,
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# ETag / If-Match (KA-F-08)
# ---------------------------------------------------------------------------


def test_stale_if_match_is_412_and_a_stale_body_version_is_409(
    authed_client, workspace, document
) -> None:
    item = _create(authed_client, workspace, document)
    assert (
        authed_client.patch(
            f"{COLLECTION}{item['id']}/", {"title": "v2"}, format="json"
        ).status_code
        == 200
    )

    stale_header = authed_client.patch(
        f"{COLLECTION}{item['id']}/",
        {"title": "should not land"},
        format="json",
        HTTP_IF_MATCH='"1"',
    )
    assert stale_header.status_code == 412, stale_header.content
    assert stale_header.json()["error"]["code"] == "PRECONDITION_FAILED"

    stale_body = authed_client.patch(
        f"{COLLECTION}{item['id']}/",
        {"title": "should not land either", "expected_version": 1},
        format="json",
    )
    assert stale_body.status_code == 409, stale_body.content
    assert stale_body.json()["error"]["code"] == "CONFLICT"

    unchanged = authed_client.get(f"{COLLECTION}{item['id']}/")
    assert unchanged.json()["title"] == "v2"

    malformed = authed_client.patch(
        f"{COLLECTION}{item['id']}/",
        {"title": "nope"},
        format="json",
        HTTP_IF_MATCH="garbage",
    )
    assert malformed.status_code == 400, malformed.content
    assert malformed.json()["error"]["code"] == "INVALID_IF_MATCH"


def test_conditional_patch_with_the_current_tag_succeeds(
    authed_client, workspace, document
) -> None:
    item = _create(authed_client, workspace, document)
    tag = authed_client.get(f"{COLLECTION}{item['id']}/")["ETag"]

    response = authed_client.patch(
        f"{COLLECTION}{item['id']}/",
        {"title": "guarded"},
        format="json",
        HTTP_IF_MATCH=tag,
    )

    assert response.status_code == 200, response.content
    assert response.json()["title"] == "guarded"


# ---------------------------------------------------------------------------
# Transition — graph, rule 10 and the extended approval gate
# ---------------------------------------------------------------------------


def test_transition_moves_the_item_and_blocked_needs_a_reason(
    authed_client, workspace, document
) -> None:
    item = _create(authed_client, workspace, document)

    moved = _transition(authed_client, item["id"], IN_PROGRESS)
    assert moved.status_code == 200, moved.content
    assert moved.json()["previous_state"] == "todo"
    assert moved.json()["new_state"] == IN_PROGRESS
    assert moved.json()["work_item"]["status"] == IN_PROGRESS

    refused = _transition(authed_client, item["id"], BLOCKED)
    assert refused.status_code == 400, refused.content
    assert refused.json()["error"]["code"] == "VALIDATION_ERROR"

    blocked = _transition(
        authed_client, item["id"], BLOCKED, blocked_reason="waiting on API"
    )
    assert blocked.status_code == 200, blocked.content
    assert blocked.json()["new_state"] == BLOCKED
    assert blocked.json()["work_item"]["blocked_reason"] == "waiting on API"


def test_extended_done_requires_an_approver(
    authed_client, tenant, workspace, document
) -> None:
    editor = _role_client(tenant, workspace, ROLE_EDITOR, suffix=uuid.uuid4().hex[:8])
    item = _create(authed_client, workspace, document)

    assert _transition(editor, item["id"], IN_PROGRESS).status_code == 200
    assert _transition(editor, item["id"], IN_REVIEW).status_code == 200

    refused = _transition(editor, item["id"], DONE)
    assert refused.status_code == 403, refused.content
    assert refused.json()["error"]["code"] == "PERMISSION_DENIED"

    signed_off = _transition(authed_client, item["id"], DONE)
    assert signed_off.status_code == 200, signed_off.content
    assert signed_off.json()["new_state"] == DONE
    assert signed_off.json()["work_item"]["approved_by"]
    assert signed_off.json()["work_item"]["approved_at"]


def test_generic_transitions_post_cannot_bypass_the_service(
    authed_client, workspace, document
) -> None:
    """``POST .../transitions/`` must run the same service as ``transition/``.

    The inherited generic POST calls ``WorkflowFacade`` directly, which would
    skip the extended preset's approval bookkeeping. Delegating keeps
    ``approved_by``/``approved_at`` recorded and returns the refreshed item.
    """
    item = _create(authed_client, workspace, document)

    for target in (IN_PROGRESS, IN_REVIEW):
        moved = authed_client.post(
            f"{COLLECTION}{item['id']}/transitions/",
            {"target_state": target, "change_reason": "via generic route"},
            format="json",
        )
        assert moved.status_code == 200, moved.content

    signed_off = authed_client.post(
        f"{COLLECTION}{item['id']}/transitions/",
        {"target_state": DONE, "change_reason": "signed off"},
        format="json",
    )

    assert signed_off.status_code == 200, signed_off.content
    assert "work_item" in signed_off.json()
    assert signed_off.json()["work_item"]["approved_by"]
    assert signed_off.json()["work_item"]["approved_at"]


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def test_resume_returns_the_newest_checkpoint_and_open_items_sorted(
    authed_client, workspace, document
) -> None:
    late = _create(authed_client, workspace, document, title="Late", ordinal=2)
    first = _create(authed_client, workspace, document, title="First", ordinal=0)
    second = _create(authed_client, workspace, document, title="Second", ordinal=0)
    closed = _create(authed_client, workspace, document, title="Closed", ordinal=1)
    assert _transition(authed_client, closed["id"], DROPPED).status_code == 200

    checkpoint_one = _create(
        authed_client,
        workspace,
        document,
        kind="Checkpoint",
        title="Checkpoint 1",
        next_action="continue with First",
    )
    checkpoint_two = _create(
        authed_client,
        workspace,
        document,
        kind="Checkpoint",
        title="Checkpoint 2",
        next_action="continue with Second",
    )

    response = authed_client.get(
        f"{COLLECTION}resume/?workspace_id={workspace.id}"
        f"&document_id={document.id}&actor=agent:resume"
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["checkpoint"]["id"] == checkpoint_two["id"]
    assert body["checkpoint"]["kind"] == "Checkpoint"
    assert body["checkpoint"]["next_action"] == "continue with Second"

    expected = sorted(
        [late, first, second, checkpoint_one, checkpoint_two],
        key=lambda row: (row["ordinal"], row["id"]),
    )
    assert [entry["id"] for entry in body["open_items"]] == [
        row["id"] for row in expected
    ]
    assert closed["id"] not in {entry["id"] for entry in body["open_items"]}
    for entry in body["open_items"]:
        assert entry["status"] not in {"done", "dropped"}
        assert isinstance(entry["links"], list)
        assert entry["last_activity_at"] is not None


def test_resume_requires_a_document(authed_client, workspace) -> None:
    response = authed_client.get(f"{COLLECTION}resume/?workspace_id={workspace.id}")

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Soft delete / reactivate (G1.5)
# ---------------------------------------------------------------------------


def test_soft_delete_and_reactivate_contract(authed_client, workspace, document) -> None:
    item = _create(authed_client, workspace, document)

    deleted = authed_client.delete(
        f"{COLLECTION}{item['id']}/?change_reason=no longer needed"
    )
    assert deleted.status_code == 204, deleted.content

    # V3: the row survives and reports the soft-delete flag.
    detail = authed_client.get(f"{COLLECTION}{item['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["status"] == "outdated"

    hidden = authed_client.get(f"{COLLECTION}?workspace_id={workspace.id}")
    assert item["id"] not in [row["id"] for row in hidden.json()["results"]]
    visible = authed_client.get(
        f"{COLLECTION}?workspace_id={workspace.id}&include_deleted=true"
    )
    assert item["id"] in [row["id"] for row in visible.json()["results"]]

    restored = authed_client.post(f"{COLLECTION}{item['id']}/reactivate/")
    assert restored.status_code == 200, restored.content
    assert restored.json()["work_item"]["status"] == "todo"

    assert (
        authed_client.get(f"{COLLECTION}{item['id']}/").json()["status"] == "todo"
    )


def test_delete_without_a_reason_is_400_on_the_extended_preset(
    authed_client, workspace, document
) -> None:
    item = _create(authed_client, workspace, document)

    response = authed_client.delete(f"{COLLECTION}{item['id']}/")

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Versions / diff
# ---------------------------------------------------------------------------


def test_versions_and_diff_follow_the_lock_counter(
    authed_client, workspace, document
) -> None:
    item = _create(authed_client, workspace, document, title="Original")
    assert (
        authed_client.patch(
            f"{COLLECTION}{item['id']}/", {"title": "Renamed"}, format="json"
        ).status_code
        == 200
    )

    versions = authed_client.get(f"{COLLECTION}{item['id']}/versions/")
    assert versions.status_code == 200, versions.content
    body = versions.json()
    revisions = body["versions"] if isinstance(body, dict) else body
    numbers = [entry["version"] for entry in revisions]
    assert 1 in numbers and 2 in numbers

    diff = authed_client.get(
        f"{COLLECTION}{item['id']}/diff/?from_version=1&to_version=2"
    )
    assert diff.status_code == 200, diff.content
    changed = {
        entry["name"]: entry
        for entry in diff.json()["fields"]
        if entry.get("status") != "unchanged"
    }
    assert changed["title"]["from"] == "Original"
    assert changed["title"]["to"] == "Renamed"


# ---------------------------------------------------------------------------
# Gates — unknown fields, immutable document, tenant fence
# ---------------------------------------------------------------------------


def test_unknown_field_and_document_change_are_rejected(
    authed_client, tenant, workspace, document
) -> None:
    item = _create(authed_client, workspace, document)
    other_document = _create_other_document(tenant, workspace)

    unknown = authed_client.patch(
        f"{COLLECTION}{item['id']}/", {"nonsense": True}, format="json"
    )
    assert unknown.status_code == 400, unknown.content
    assert unknown.json()["error"]["code"] == "VALIDATION_ERROR"

    moved = authed_client.patch(
        f"{COLLECTION}{item['id']}/",
        {"document_id": str(other_document.id)},
        format="json",
    )
    assert moved.status_code == 400, moved.content
    assert moved.json()["error"]["details"][0]["field"] == "document_id"


def test_foreign_tenant_cannot_read_a_work_item(
    authed_client, workspace, document
) -> None:
    item = _create(authed_client, workspace, document)

    other_tenant = Tenant.objects.create(
        name="Other WorkItem Tenant",
        slug=f"other-wi-{uuid.uuid4().hex[:8]}",
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

    response = client.get(f"{COLLECTION}{item['id']}/")

    # The user holds a real role there, but the object does not exist in that
    # tenant: 404, never a cross-tenant peek (ADR-013 404-vs-403 rule).
    assert response.status_code == 404, response.content


def _foreign_client(tenant: Tenant, workspace: Workspace):
    """An authenticated client whose user belongs to *tenant* only."""
    return _role_client(tenant, workspace, ROLE_ADMIN, suffix=uuid.uuid4().hex[:8])
