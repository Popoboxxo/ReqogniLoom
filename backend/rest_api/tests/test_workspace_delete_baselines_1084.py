"""GitHub #1084 — hard-deleting a workspace that has baselines answered 500.

``POST /api/v1/workspaces/{id}/delete/`` with a *correct* confirmation::

    -> 500 {"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal error occurred."}}
    psycopg2.errors.RaiseException: Baselines are immutable
    application/workspace_service.py:605 in delete_workspace
      BaselineSnapshot.unscoped.filter(workspace_id=workspace_pk).delete()
    django.db.utils.InternalError: Baselines are immutable

Root cause: the cascade issued an unconditional ``BaselineSnapshot.delete()``.
Baselines are append-only — ``bl_raise_immutable`` (``baseline/migrations/
0001_initial.py``) raises on every UPDATE *and* DELETE at the DB level, with no
bypass — so that statement could never succeed. It only ever aborted the
``@atomic_transaction`` and surfaced as an unmapped ``InternalError``, i.e. a
500. The practical effect was that ``/delete/`` was a dead end for exactly the
workspaces worth protecting.

Fix: ``WorkspaceService.delete_workspace`` refuses up front with
``BaselineImmutabilityError`` (a ``ValidationError`` subclass, the same shape
the duplicate-tracelink path already reports). The trigger itself is untouched
and still blocks any direct row DELETE — the guard is a *precondition*, not a
weakened invariant. A second, narrower guard translates a trigger
``InternalError`` from the cascade into the same domain error, so a baseline
inserted between the check and the delete cannot reopen the 500 through the
``Artifact`` CASCADE.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import InternalError
from django.test import override_settings
from rest_framework.test import APIClient

from application.workspace_service import (
    BaselineImmutabilityError,
    WorkspaceService,
)
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "wsdel1084pass"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


def _env(name: str) -> tuple[Tenant, User, Workspace]:
    slug = f"wsdel1084-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    with override_settings(**_JWT_OVERRIDES):
        login = client.post(
            "/api/v1/auth/login/",
            {"username": user.username, "password": _PASSWORD},
            format="json",
        )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _with_baseline(tenant: Tenant, workspace: Workspace) -> str:
    """Attach one baseline to *workspace* and return the owning artifact id.

    Inserted straight through the unscoped manager: the immutability the test is
    about is a DELETE/UPDATE trigger, so an INSERT is unaffected by it.
    """
    from baseline.models import BaselineSnapshot

    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.unscoped.create(
            workspace=workspace, artifact_type="generic", tenant=tenant
        )
        BaselineSnapshot.unscoped.create(
            workspace_id=workspace.id,
            name=f"bl-{uuid.uuid4().hex[:8]}",
            scope="document",
            artifact=artifact,
            tenant=tenant,
        )
        return str(artifact.id)
    finally:
        clear_request_tenant()


def _auth_ctx(user: User, tenant: Tenant) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


# ---------------------------------------------------------------------------
# REST surface
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_delete_with_baselines_answers_4xx_not_500() -> None:
    """#1084: a workspace with baselines must be refused, cleanly."""
    tenant, user, workspace = _env("Has Baselines")
    _with_baseline(tenant, workspace)
    client = _client(user)

    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/",
        {"confirmation": "Has Baselines"},
        format="json",
    )

    assert 400 <= response.status_code < 500, (
        f"expected a 4xx, got {response.status_code}: {response.content!r}"
    )
    assert response.status_code == 409, response.content
    body = response.json()
    assert set(body) == {"error"}, body
    assert set(body["error"]) == {"code", "message", "details"}, body
    assert body["error"]["code"] == "CONFLICT", body
    assert "immutable" in body["error"]["message"].lower(), body
    assert body["error"]["details"] == [{"code": "baselines_immutable"}], body


@override_settings(**_JWT_OVERRIDES)
def test_delete_with_baselines_keeps_workspace_and_baseline() -> None:
    """The refusal must be a no-op, not a half-finished cascade."""
    from baseline.models import BaselineSnapshot

    tenant, user, workspace = _env("Kept Intact")
    artifact_id = _with_baseline(tenant, workspace)
    client = _client(user)

    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/",
        {"confirmation": "Kept Intact"},
        format="json",
    )

    assert response.status_code == 409, response.content
    assert Workspace.unscoped.filter(pk=workspace.pk).exists()
    assert Artifact.unscoped.filter(pk=artifact_id).exists()
    assert BaselineSnapshot.unscoped.filter(workspace_id=workspace.pk).exists()


@override_settings(**_JWT_OVERRIDES)
def test_delete_verb_is_guarded_identically_to_the_post_route() -> None:
    """#265 keeps both verbs on one implementation; both must be guarded."""
    tenant, user, workspace = _env("Delete Verb Guarded")
    _with_baseline(tenant, workspace)
    client = _client(user)

    response = client.delete(
        f"/api/v1/workspaces/{workspace.id}/", {"confirmation": "Delete Verb Guarded"}
    )

    assert response.status_code == 409, response.content
    assert "immutable" in response.json()["error"]["message"].lower()
    assert Workspace.unscoped.filter(pk=workspace.pk).exists()


@override_settings(**_JWT_OVERRIDES)
def test_delete_with_baselines_message_no_longer_says_remove_them_first() -> None:
    """#1199 requirement 1: the 409 must name the real removal path.

    The old wording ended in "remove them first", which no route could satisfy.
    It now points at the audited administrative baseline purge.
    """
    tenant, user, workspace = _env("Actionable Refusal")
    _with_baseline(tenant, workspace)
    client = _client(user)

    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/",
        {"confirmation": "Actionable Refusal"},
        format="json",
    )

    assert response.status_code == 409, response.content
    message = response.json()["error"]["message"].lower()
    assert "remove them first" not in message, message
    assert "purge" in message, message


@override_settings(**_JWT_OVERRIDES)
def test_force_parameter_is_rejected_not_silently_ignored() -> None:
    """#1199 requirement 4: ``?force=true`` never had an effect.

    It used to be dropped on the floor, so a caller believed it had opted into
    a cascade the server never performed. The request is now refused with a 400
    naming the only path — the audited admin baseline purge — instead of hiding
    an undocumented deletion path behind a query flag.
    """
    tenant, user, workspace = _env("No Force")
    _with_baseline(tenant, workspace)
    client = _client(user)

    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/?force=true",
        {"confirmation": "No Force"},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "force" in response.json()["error"]["message"].lower(), response.json()
    assert Workspace.unscoped.filter(pk=workspace.pk).exists()


@override_settings(**_JWT_OVERRIDES)
def test_delete_without_baselines_still_succeeds_with_204() -> None:
    """The counter-test: the guard must not block an ordinary workspace."""
    _, user, workspace = _env("No Baselines")
    client = _client(user)

    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/",
        {"confirmation": "No Baselines"},
        format="json",
    )

    assert response.status_code == 204, response.content
    assert not Workspace.unscoped.filter(pk=workspace.pk).exists()


@override_settings(**_JWT_OVERRIDES)
def test_captcha_mismatch_still_reports_its_own_details_code() -> None:
    """The new branch must not swallow the pre-existing 409 semantics."""
    _, user, workspace = _env("Wrong Confirmation")
    client = _client(user)
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/delete/",
        {"confirmation": "not the name"},
        format="json",
    )

    assert response.status_code == 409, response.content
    assert response.json()["error"]["details"] == [
        {"code": "confirmation_mismatch"}
    ], response.json()
    assert Workspace.unscoped.filter(pk=workspace.pk).exists()


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------


def test_service_raises_a_validation_error_subclass(db) -> None:
    """The refusal must be a domain error a Layer-2 caller can handle.

    ``ValidationError`` is what the duplicate-tracelink path raises for the same
    class of "the request is well-formed but the state forbids it" (#126), so
    every existing ``except ValidationError`` keeps working.
    """
    from application.base import ValidationError

    assert issubclass(BaselineImmutabilityError, ValidationError)

    tenant, user, workspace = _env("Service Level")
    _with_baseline(tenant, workspace)
    ctx = _auth_ctx(user, tenant)
    set_request_tenant(tenant.id)
    try:
        with pytest.raises(BaselineImmutabilityError, match=r"(?i)immutable"):
            WorkspaceService().delete_workspace(workspace.id, "Service Level", ctx)
    finally:
        clear_request_tenant()

    assert Workspace.unscoped.filter(pk=workspace.pk).exists()


def test_preflight_does_not_depend_on_a_live_tenant_context(db) -> None:
    """The guard reads the unscoped manager, so it cannot be defeated by a
    missing thread-local tenant — the same reason the cascade uses
    ``.unscoped``."""
    tenant, user, workspace = _env("No Tenant Context")
    _with_baseline(tenant, workspace)
    ctx = _auth_ctx(user, tenant)
    # Deliberately no set_request_tenant() around the call.
    with pytest.raises(BaselineImmutabilityError, match=r"(?i)immutable"):
        WorkspaceService().delete_workspace(workspace.id, "No Tenant Context", ctx)

    assert Workspace.unscoped.filter(pk=workspace.pk).exists()


def test_concurrent_baseline_trigger_is_translated_not_raised_as_500(db) -> None:
    """Safety net: a baseline created after the pre-flight still 4xxs.

    Simulates the TOCTOU window by letting the raw cascade hit the real
    trigger, and pins that (a) the trigger still fires, and (b) the guarded
    ``delete_workspace`` reports the domain error rather than a 500.
    """
    from django.db import transaction

    tenant, user, workspace = _env("Race Window")
    artifact_id = _with_baseline(tenant, workspace)
    ctx = _auth_ctx(user, tenant)
    service = WorkspaceService()

    set_request_tenant(tenant.id)
    try:
        # A savepoint keeps the broken transaction from leaking out of the
        # block, so the following assertions can still query.
        with transaction.atomic(), pytest.raises(
            InternalError, match=r"(?i)immutable"
        ):
            service._cascade_delete_workspace_rows(workspace.pk)

        # Nothing was half-deleted: the guarded delete rolls the cascade back.
        with pytest.raises(BaselineImmutabilityError, match=r"(?i)immutable"):
            service.delete_workspace(workspace.id, "Race Window", ctx)
    finally:
        clear_request_tenant()

    assert Workspace.unscoped.filter(pk=workspace.pk).exists()
    assert Artifact.unscoped.filter(pk=artifact_id).exists()


def test_immutability_trigger_still_blocks_a_direct_row_delete(db) -> None:
    """The guard is a precondition; the DB invariant is untouched."""
    from django.db import transaction

    from baseline.models import BaselineSnapshot

    tenant, _, workspace = _env("Trigger Intact")
    _with_baseline(tenant, workspace)

    set_request_tenant(tenant.id)
    try:
        snapshot = BaselineSnapshot.unscoped.filter(workspace_id=workspace.pk).first()
        assert snapshot is not None
        with transaction.atomic(), pytest.raises(InternalError, match=r"(?i)immutable"):
            BaselineSnapshot.unscoped.filter(pk=snapshot.pk).delete()
    finally:
        clear_request_tenant()

    assert BaselineSnapshot.unscoped.filter(pk=snapshot.pk).exists()
