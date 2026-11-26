"""P2.10 (m-15) — the WorkItem ``transitions/`` GET must not swallow defects.

The GET branch enriched the parent's (already 200) response with the WorkItem's
entity revision inside a bare ``except Exception: return response``. That is
correct for the three *expected* misses — after ``super().transitions()``
answered 200 the enrichment is best-effort, and an item that vanished or became
unreadable between the two reads must not turn a readable transition list into
a 404/403. It is wrong for anything else: a genuine defect produced a response
that silently lacked ``workflow_version``, so the client built its POST
precondition from the engine revision instead of the entity revision and got a
409/412 with no clue why.

Contract pinned here — the same one ``test_document_transitions_error_paths``
pins for ``DocumentViewSet``:

* ``NotFoundError`` / ``PermissionDeniedError`` / ``ValueError`` while
  re-reading → the parent's 200 answer, unenriched;
* any other exception → the canonical masked 5xx envelope
  (``INTERNAL_SERVER_ERROR``, no traceback, no ``str(exc)``), logged exactly
  once with ``exc_info`` by ``_service_error_response``;
* the happy path still injects ``workflow_version`` (engine revision) and
  ``version`` (WorkItem revision) — two independently bookkept numbers.
"""
from __future__ import annotations

import logging

import pytest

from application.base import NotFoundError, PermissionDeniedError
from application.work_item_service import WorkItemService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Document, Workspace
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

COLLECTION = "/api/v1/work-items/"
IN_PROGRESS = "in_progress"


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
        "title": "Transition enrichment subject",
        "body": "## Step\n\nDo the work.",
    }
    payload.update(overrides)
    return payload


def _create(client, workspace: Workspace, document: Document) -> dict:
    response = client.post(
        COLLECTION, _payload(workspace, document), format="json"
    )
    assert response.status_code == 201, response.content
    return response.json()


def _fail_on_nth_get(monkeypatch, exc: BaseException, nth: int = 2) -> None:
    """Make the *nth* ``WorkItemService.get_work_item`` call raise *exc*.

    The GET route reads the item twice: once in the parent's
    ``_resolve_workflow_target`` and once in the enrichment block. Only the
    second read is under test — letting the first fail would exercise the
    parent's own error path instead, which is not what m-15 is about.
    """
    original = WorkItemService.get_work_item
    calls = {"count": 0}

    def flaky(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == nth:
            raise exc
        return original(self, *args, **kwargs)

    monkeypatch.setattr(WorkItemService, "get_work_item", flaky)


# ---------------------------------------------------------------------------
# Expected misses keep the parent's 200
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(NotFoundError("gone"), id="not-found"),
        pytest.param(PermissionDeniedError("nope"), id="permission-denied"),
        pytest.param(ValueError("malformed id"), id="value-error"),
    ],
)
def test_expected_enrichment_failure_keeps_the_parent_answer(
    authed_client, workspace, document, monkeypatch, exc
) -> None:
    item = _create(authed_client, workspace, document)
    _fail_on_nth_get(monkeypatch, exc, nth=2)

    response = authed_client.get(f"{COLLECTION}{item['id']}/transitions/")

    assert response.status_code == 200, response.content
    body = response.json()
    # The parent's shape survives untouched: an unenriched answer, not an error.
    assert body["current_state"] == "todo"
    assert "version" in body
    assert "current_state" in body and "allowed_transitions" in body
    assert "workflow_version" not in body, (
        "an enrichment miss must skip the enrichment, not half-apply it"
    )


# ---------------------------------------------------------------------------
# Unexpected failures are masked and logged once
# ---------------------------------------------------------------------------


def test_unexpected_enrichment_failure_is_a_masked_5xx_logged_once(
    authed_client, workspace, document, monkeypatch, caplog
) -> None:
    item = _create(authed_client, workspace, document)
    secret = "internal-detail-that-must-not-leak"
    _fail_on_nth_get(monkeypatch, RuntimeError(secret), nth=2)

    # Only the service-error logger: Django's request logger is not involved
    # because the view returns the envelope instead of raising.
    with caplog.at_level(logging.ERROR, logger="rest_api.views_common"):
        response = authed_client.get(f"{COLLECTION}{item['id']}/transitions/")

    assert response.status_code == 500, response.content
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    rendered = response.content.decode()
    assert secret not in rendered, "the exception message leaked into the body"
    assert "Traceback" not in rendered
    assert "RuntimeError" not in rendered

    logged = [
        record
        for record in caplog.records
        if record.name == "rest_api.views_common" and record.levelno >= logging.ERROR
    ]
    assert len(logged) == 1, f"expected exactly one log record, got {logged!r}"
    assert logged[0].exc_info is not None, (
        "the 5xx must be logged with exc_info so the cause is diagnosable"
    )
    assert "Unhandled exception in service layer" in logged[0].getMessage()


# ---------------------------------------------------------------------------
# Happy path: two independently bookkept revisions, both injected
# ---------------------------------------------------------------------------


def test_happy_path_injects_workflow_version_and_item_version(
    authed_client, workspace, document
) -> None:
    item = _create(authed_client, workspace, document)
    assert item["version"] == 1

    # A PATCH bumps the *entity* revision only — the workflow revision still
    # counts the one state the create wrote. That is what separates the two
    # keys, and why the client must read both.
    patched = authed_client.patch(
        f"{COLLECTION}{item['id']}/", {"title": "Renamed"}, format="json"
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["version"] == 2

    fresh = authed_client.get(f"{COLLECTION}{item['id']}/transitions/")
    assert fresh.status_code == 200, fresh.content
    fresh_body = fresh.json()
    assert "workflow_version" in fresh_body, sorted(fresh_body)
    assert fresh_body["workflow_version"] == 1
    assert fresh_body["version"] == 2

    moved = authed_client.post(
        f"{COLLECTION}{item['id']}/transitions/",
        {"target_state": IN_PROGRESS, "change_reason": "start"},
        format="json",
    )
    assert moved.status_code == 200, moved.content

    after = authed_client.get(f"{COLLECTION}{item['id']}/transitions/")
    assert after.status_code == 200, after.content
    body = after.json()
    # The transition advanced both counters; the keys keep their own meaning
    # (engine revision vs. the ETag the POST's expected_version guards).
    assert body["workflow_version"] == 2, body
    assert body["version"] == 3, body
