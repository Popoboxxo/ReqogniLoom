"""View-level tests for ``AdrViewSet.supersede`` (REQ-L3-ADR-005).

Systemaudit 2026-08-27 AP-5 review (F3): ``POST /api/v1/adrs/{pk}/supersede/``
(UI-32) was added with no dedicated REST-level test — the closest sibling
action with test coverage is ``diff`` (``test_artifact_versioning_audit.py``),
which drives the same "real DB + real APIClient + real error-mapping ladder"
pattern this module follows.

Fixture setup mirrors ``test_artifact_versioning_audit.py``'s
tenant/workspace/client trio (not the module-scoped ``conftest.py`` fixtures
of the same name, which skip ``provision_workspace_defaults`` and therefore
have no ADR workflow definition — the supersede action's own
``AdrService.transition_status`` call requires one to move the ADR through
Draft -> In Review -> Approved -> Superseded).
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from application.models import Adr
from application.workspace_provisioning import provision_workspace_defaults
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.models import TraceLink
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_PASSWORD = "adr-views-pass-2026"


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="adr-views-test", slug=f"adr-views-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
def workspace(tenant: Tenant) -> PersistenceWorkspace:
    """A fully provisioned workspace (real ``adr_default`` workflow definition)."""
    TenantContext.set_tenant(tenant.id)
    try:
        ws = PersistenceWorkspace.objects.create(
            tenant=tenant, name="ADR Views WS", preset={"name": "standard"}
        )
        provision_workspace_defaults(
            workspace_id=ws.id, tenant_id=tenant.id, requirement_preset="standard"
        )
        return ws
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def client(tenant: Tenant, workspace: PersistenceWorkspace) -> APIClient:
    """An ``APIClient`` authenticated as a workspace admin via JWT."""
    username = f"adr-views-{uuid.uuid4().hex[:8]}"
    user = User.objects.create(
        username=username, email=f"{username}@example.com", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    TenantContext.set_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        TenantContext.clear_tenant()

    login = APIClient().post(
        "/api/v1/auth/login/",
        {"username": username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return authed


def _create_adr(client: APIClient, workspace_id: str, title: str) -> str:
    resp = client.post(
        "/api/v1/adrs/",
        {
            "workspace_id": workspace_id,
            "title": title,
            "description": "v1",
            "context": "ctx",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


def _advance_to_approved(client: APIClient, adr_id: str) -> None:
    """Draft -> In Review -> Approved, per ``_adr_transitions()``."""
    resp = client.post(
        f"/api/v1/adrs/{adr_id}/transitions/",
        {"target_state": "In Review"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    resp = client.post(
        f"/api/v1/adrs/{adr_id}/transitions/",
        {"target_state": "Approved", "change_reason": "review complete"},
        format="json",
    )
    assert resp.status_code == 200, resp.content


def test_supersede_success_sets_status_and_creates_decides_tracelink(
    client: APIClient, workspace: PersistenceWorkspace
) -> None:
    """A successful supersede call transitions the ADR and records the
    'decides' TraceLink (successor -> superseded), per
    ``AdrService.transition_status``."""
    ws_id = str(workspace.id)
    old_id = _create_adr(client, ws_id, "Old Decision")
    new_id = _create_adr(client, ws_id, "New Decision")
    _advance_to_approved(client, old_id)

    resp = client.post(
        f"/api/v1/adrs/{old_id}/supersede/",
        {"superseded_by_id": new_id, "change_reason": "replaced by New Decision"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == Adr.Status.SUPERSEDED.value

    # ORM assertions run under an explicit TenantContext — Adr/TraceLink are
    # tenant-scoped models (persistence.tenancy.TenantScopedModel) and raise
    # TenantContextNotSetError otherwise (AuthAndTenancy, ARCH-L1-011);
    # inside a request this is set by AuthTenancyAuthentication, but these
    # queries run directly against the ORM after the response returned.
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        old_adr = Adr.objects.get(id=old_id)
        new_adr = Adr.objects.get(id=new_id)
        assert old_adr.status == Adr.Status.SUPERSEDED.value
        # There is no dedicated `superseded_by` column (REQ-L3-ADR-005) — the
        # 'decides' TraceLink (source=successor, target=superseded) is the
        # single source of truth the frontend's "Abgelöst durch" lookup
        # resolves against (see AdrForm.tsx's useEffect on
        # `supersededByLink`).
        assert TraceLink.objects.filter(
            source_id=new_adr.artifact_id,
            target_id=old_adr.artifact_id,
            link_type="decides",
        ).exists()
    finally:
        TenantContext.clear_tenant()


def test_supersede_missing_superseded_by_id_returns_400(
    client: APIClient, workspace: PersistenceWorkspace
) -> None:
    ws_id = str(workspace.id)
    adr_id = _create_adr(client, ws_id, "Some Decision")

    resp = client.post(f"/api/v1/adrs/{adr_id}/supersede/", {}, format="json")

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    # The ADR must be left untouched — a rejected request must not have any
    # side effect on its status.
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        assert Adr.objects.get(id=adr_id).status == Adr.Status.DRAFT.value
    finally:
        TenantContext.clear_tenant()


def test_supersede_malformed_uuid_returns_400_not_500(
    client: APIClient, workspace: PersistenceWorkspace
) -> None:
    """A malformed ``superseded_by_id`` must map to a 400 VALIDATION_ERROR,
    not raise ``ValueError`` uncaught into a 500 (the failure mode the
    ``diff``/``versions`` actions' identical ``except ValueError`` ladder
    already guards against elsewhere in this ViewSet)."""
    ws_id = str(workspace.id)
    adr_id = _create_adr(client, ws_id, "Some Other Decision")

    resp = client.post(
        f"/api/v1/adrs/{adr_id}/supersede/",
        {"superseded_by_id": "not-a-uuid", "change_reason": "irrelevant"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        assert Adr.objects.get(id=adr_id).status == Adr.Status.DRAFT.value
    finally:
        TenantContext.clear_tenant()
