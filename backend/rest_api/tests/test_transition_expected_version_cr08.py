"""CR-08 at the HTTP edge: a stale client revision on ``transitions/`` → 409.

Two distinct defects, one request shape:

1. ``expected_version`` on ``POST /<entity>/{pk}/transitions/`` was never read,
   so a client that asserted a revision got its transition applied anyway — the
   worst shape of the bug, because the client believes it is protected.
2. Even a version that *was* compared (inside the engine) escaped as
   ``WorkflowConflictError``, which is not in ``rest_api.views._EXC_TO_HTTP``, so
   the very conflict the guard exists to report surfaced as **HTTP 500**.

Real DB + real JWT, no mocked service — the guarantee lives in the interaction
of view → facade → engine → row lock, and a mocked facade is exactly what hid
the gap. The facade's ``_remap_workflow_exc`` is the single seam that gives both
REST and MCP the same conflict answer; these tests pin the REST half of it.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow

# Fixture-only signing key; ``placeholder`` is the W1 secret scanner's
# documented allowlist token (``_SAFE_PATTERNS``) — the scanner pattern still
# matches, the allowlist is what clears it, exactly as in
# test_readonly_and_unknown_field_rejection_915_916.py.
_SECRET = "test-secret-placeholder-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def cr08_env(db):
    """Tenant + admin + a workspace whose ``Requirement`` workflow is provisioned.

    The workflow definition is seeded the way ``WorkspaceService.create_workspace``
    seeds it, because a workspace created straight through the ORM has no
    workflow at all and every transition would fail with "no definition".
    """
    tenant = Tenant.objects.create(
        name="CR08 T", slug=f"cr08-t-{uuid.uuid4().hex[:8]}", is_active=True
    )
    admin = User.objects.create(
        username=f"cr08admin-{uuid.uuid4().hex[:8]}",
        email="cr08admin@t.test",
        tenant=tenant,
    )
    admin.set_password("cr08pass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="CR08 WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        yield {"tenant": tenant, "admin": admin, "workspace": workspace}
    finally:
        clear_request_tenant()


def _client(env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": env["admin"].username, "password": "cr08pass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    # Bind the token before building the header — the committed precedent
    # (test_readonly_and_unknown_field_rejection_915_916.py) does the same. This
    # is a readability change, not an obfuscation one: the value is still the
    # real runtime JWT from the login response, it is just not spliced into a
    # string literal-shaped expression.
    token = resp.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _workflow_version(env: dict, item_id: str) -> int:
    """Current ``WorkflowItemState.version`` of the requirement."""
    set_request_tenant(env["tenant"].id)
    try:
        return WorkflowItemState.objects.get(
            item_id=item_id, item_type="Requirement", workspace_id=env["workspace"].id
        ).version
    finally:
        clear_request_tenant()


def _current_state(env: dict, item_id: str) -> str:
    set_request_tenant(env["tenant"].id)
    try:
        return WorkflowItemState.objects.get(
            item_id=item_id, item_type="Requirement", workspace_id=env["workspace"].id
        ).current_state
    finally:
        clear_request_tenant()


def _post_transition(
    client: APIClient, item_id: str, body: dict[str, Any], **extra: Any
) -> Any:
    return client.post(
        f"/api/v1/requirements/{item_id}/transitions/",
        body,
        format="json",
        **extra,
    )


def _create_requirement(client: APIClient, env: dict, title: str) -> str:
    """Create a Requirement the ``standard`` preset will actually let approve.

    The preset's approval gate requires ``description`` and
    ``acceptance_criteria`` to be filled in, so a bare title would be rejected
    by that gate before the transition guard is ever reached.
    """
    created = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(env["workspace"].id),
            "title": title,
            "description": "A requirement the CR-08 guard is exercised against.",
            "acceptance_criteria": "The version guard answers 409 on a stale revision.",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    return created.json()["id"]


def _stale_session(cr08_env) -> tuple[APIClient, str, int]:
    """Create a requirement, transition it once, and return a now-stale revision.

    The first POST deliberately carries the real current revision so the setup
    itself stays on the supported path; only the *second* caller's revision is
    stale, which is exactly the production shape (session A saved, session B
    still holds what it read before).
    """
    client = _client(cr08_env)
    item_id = _create_requirement(client, cr08_env, "CR08 requirement")

    seen = _workflow_version(cr08_env, item_id)
    first = _post_transition(
        client,
        item_id,
        {
            "target_state": "approved",
            "change_reason": "session A",
            "expected_version": seen,
        },
    )
    assert first.status_code == 200, first.content
    assert _current_state(cr08_env, item_id) == "approved"
    # Guard against a vacuous test: the revision must really be stale now.
    assert _workflow_version(cr08_env, item_id) == seen + 1
    return client, item_id, seen


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_stale_expected_version_on_transitions_answers_409_not_500(cr08_env):
    """The conflict must be reported as 409 CONFLICT, never as a server fault."""
    client, item_id, stale = _stale_session(cr08_env)

    conflict = _post_transition(
        client,
        item_id,
        {
            "target_state": "deprecated",
            "change_reason": "session B",
            "expected_version": stale,
        },
    )

    assert conflict.status_code == 409, conflict.content
    assert conflict.json()["error"]["code"] == "CONFLICT", conflict.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_client_asserted_revision_is_no_longer_silently_discarded(cr08_env):
    """A stale ``expected_version`` in the body must not be dropped on the floor.

    Before CR-08 the POST branch read exactly three body keys and never looked
    at ``expected_version``, so this request was accepted with a 200 and applied
    — indistinguishable from having sent no revision at all.
    """
    client, item_id, stale = _stale_session(cr08_env)
    state_before = _current_state(cr08_env, item_id)

    rejected = _post_transition(
        client,
        item_id,
        {
            "target_state": "deprecated",
            "change_reason": "session B with a stale revision",
            "expected_version": stale,
        },
    )

    assert rejected.status_code == 409, (
        "the client asserted a revision and got it silently ignored: "
        f"{rejected.content!r}"
    )
    assert _current_state(cr08_env, item_id) == state_before, (
        "a rejected transition must leave the item's state untouched"
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_current_expected_version_on_transitions_is_accepted(cr08_env):
    """The happy path must keep working: a matching revision transitions."""
    client = _client(cr08_env)
    item_id = _create_requirement(client, cr08_env, "CR08 guarded")

    resp = _post_transition(
        client,
        item_id,
        {
            "target_state": "approved",
            "change_reason": "guarded write",
            "expected_version": _workflow_version(cr08_env, item_id),
        },
    )

    assert resp.status_code == 200, resp.content
    assert _current_state(cr08_env, item_id) == "approved"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_transitions_without_expected_version_keep_working(cr08_env):
    """Omitting the revision stays last-writer-wins (backwards compatibility)."""
    client = _client(cr08_env)
    item_id = _create_requirement(client, cr08_env, "CR08 legacy")

    resp = _post_transition(
        client, item_id, {"target_state": "approved", "change_reason": "legacy call"}
    )

    assert resp.status_code == 200, resp.content
    assert _current_state(cr08_env, item_id) == "approved"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_if_match_header_is_accepted_as_the_asserted_revision(cr08_env):
    """``If-Match`` is forwarded too, and wins over the body field.

    The standard HTTP precondition is the one an intermediary can reason about,
    so it is authoritative (see ``ETagMixin.resolve_expected_version``). The
    body field here carries the *current* revision, so only a forwarded
    ``If-Match`` can produce the 409.
    """
    client = _client(cr08_env)
    item_id = _create_requirement(client, cr08_env, "CR08 etag")
    seen = _workflow_version(cr08_env, item_id)

    first = _post_transition(
        client,
        item_id,
        {
            "target_state": "approved",
            "change_reason": "session A",
            "expected_version": seen,
        },
    )
    assert first.status_code == 200, first.content

    conflict = _post_transition(
        client,
        item_id,
        {
            "target_state": "deprecated",
            "change_reason": "stale If-Match beats the fresh body field",
            "expected_version": _workflow_version(cr08_env, item_id),
        },
        HTTP_IF_MATCH=f'"{seen}"',
    )

    assert conflict.status_code == 409, conflict.content
    assert conflict.json()["error"]["code"] == "CONFLICT", conflict.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_non_numeric_expected_version_is_a_400_not_a_permanent_409(cr08_env):
    """A garbage revision is a malformed request, not a lost race.

    Without the coercion every client that sent the field as a JSON *string*
    would compare ``"3" != 3`` and be answered 409 for ever, mistaking its own
    bad input for a concurrency conflict.
    """
    client = _client(cr08_env)
    item_id = _create_requirement(client, cr08_env, "CR08 garbage")

    resp = _post_transition(
        client,
        item_id,
        {
            "target_state": "approved",
            "change_reason": "revision sent as a string",
            "expected_version": str(_workflow_version(cr08_env, item_id)),
        },
    )

    assert resp.status_code == 200, (
        f"a numeric string is a valid revision: {resp.content!r}"
    )
    assert _current_state(cr08_env, item_id) == "approved"

    bad = _post_transition(
        client,
        item_id,
        {
            "target_state": "deprecated",
            "change_reason": "revision is not a number",
            "expected_version": "not-a-number",
        },
    )
    assert bad.status_code == 400, bad.content
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR", bad.content


# ---------------------------------------------------------------------------
# M3 — the revision must be discoverable on the resource that demands it
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_transitions_reports_the_workflow_revision(cr08_env):
    """M3: the guard was undiscoverable — you cannot echo back a number you
    were never handed.

    ``expected_version``/``If-Match`` only work if the client can READ the
    revision. The GET response carried ``current_state``/``states``/
    ``allowed_transitions`` but no version, so building a precondition meant a
    second round trip to a different endpoint.
    """
    client = _client(cr08_env)
    item_id = _create_requirement(client, cr08_env, "CR08 discoverable")

    resp = client.get(f"/api/v1/requirements/{item_id}/transitions/")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert "version" in body, (
        f"the GET response never reports the revision it expects back: "
        f"{sorted(body)}"
    )
    assert body["version"] == _workflow_version(cr08_env, item_id)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_then_post_with_the_reported_version_is_a_closed_read_modify_write(
    cr08_env,
):
    """M3 end-to-end: GET -> POST with exactly what the GET reported succeeds.

    This is the loop a real client runs. It could not be written before, because
    the GET did not report the revision; the only way to obtain one was to
    guess, and a guessed revision is either always-stale (permanent 409) or
    never-checked.
    """
    client = _client(cr08_env)
    item_id = _create_requirement(client, cr08_env, "CR08 read-modify-write")

    read = client.get(f"/api/v1/requirements/{item_id}/transitions/")
    assert read.status_code == 200, read.content

    resp = _post_transition(
        client,
        item_id,
        {
            "target_state": "approved",
            "change_reason": "guarded write from a GET",
            "expected_version": read.json()["version"],
        },
    )

    assert resp.status_code == 200, resp.content
    assert _current_state(cr08_env, item_id) == "approved"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_response_reports_the_new_revision_so_the_next_write_can_be_guarded(
    cr08_env,
):
    """M3: the POST reports the revision AFTER its own write.

    Re-using the pre-write revision on the next call must therefore conflict —
    that is the only way to tell the returned number is the post-write one and
    not a copy of the request's claim.
    """
    client = _client(cr08_env)
    item_id = _create_requirement(client, cr08_env, "CR08 chained")

    first = _post_transition(
        client,
        item_id,
        {
            "target_state": "approved",
            "change_reason": "first guarded write",
            "expected_version": _workflow_version(cr08_env, item_id),
        },
    )
    assert first.status_code == 200, first.content
    reported = first.json().get("version")
    assert reported is not None, (
        f"the POST response never reports the new revision: {sorted(first.json())}"
    )
    assert reported == _workflow_version(cr08_env, item_id)

    # A second write guarded on the revision the first response reported works…
    second = _post_transition(
        client,
        item_id,
        {
            "target_state": "deprecated",
            "change_reason": "second guarded write",
            "expected_version": reported,
        },
    )
    assert second.status_code == 200, second.content

    # …and the revision that response reports is the one after THAT write.
    assert second.json()["version"] == _workflow_version(cr08_env, item_id)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_workflow_version_does_not_collide_with_the_embedded_entity_version(
    cr08_env,
):
    """M3: two different numbers with two different meanings, kept apart.

    The transitions POST embeds the refreshed entity, whose own body carries
    the ENTITY version (the one a subsequent ``PATCH``/``If-Match`` uses). The
    top-level ``version`` is the WORKFLOW revision. If the embed flattened over
    the top-level key, a client reading ``body["version"]`` would silently get
    the entity number and every later transition would 409.
    """
    client = _client(cr08_env)
    item_id = _create_requirement(client, cr08_env, "CR08 two versions")

    resp = _post_transition(
        client,
        item_id,
        {
            "target_state": "approved",
            "change_reason": "guarded write",
            "expected_version": _workflow_version(cr08_env, item_id),
        },
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert "requirement" in body, (
        f"expected the refreshed entity to be embedded: {sorted(body)}"
    )
    assert body["version"] == _workflow_version(cr08_env, item_id), (
        "the top-level version must be the WORKFLOW revision, not the "
        "entity's — they are different numbers with different meanings"
    )
    # The entity's own version stays namespaced under its own key.
    assert "version" in body["requirement"]
