"""
REST endpoint tests for ReqIF 1.2 import (REQ-147, COMP-AS-008b).

Tests POST /api/v1/workspaces/{id}/import/reqif/

Mirrors test_reqif_export.py's auth/JWT setup and test_csv_import.py's
file-upload patterns. Round-trips through the real GET .../export/reqif/
endpoint (REQ-146) to obtain a document, then POSTs it back via the import
endpoint under test.
"""
from __future__ import annotations

import io
import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, StakeholderNeed, Tenant, User, Workspace
from workflow.models import (
    WorkflowEngineDefinition,
    WorkflowHistoryEntry,
    WorkflowItemState,
)
from workflow.services import create_default_workflow

_SECRET = "test-secret-not-a-real-key"

# The suite pins the v2 contract on explicitly: the production default is
# IMPORT_CONTRACT_V2=False (ADR-014 §5 Phase 1), so every v2 assertion below
# activates the contract through these overrides instead of relying on the
# ambient default. The legacy-rollback test overrides it back to False.
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
    IMPORT_CONTRACT_V2=True,
)

_MALFORMED_REQIF = b"<not-a-valid-reqif><unclosed>"


@pytest.fixture
def reqif_import_admin_user(db):
    """Admin user with two workspaces; workspace_a gets one Need + one Requirement,
    workspace_b starts empty (used as the import target)."""
    tenant = Tenant.objects.create(
        name="Reqif-Import-Rest-T", slug="reqif-import-rest-t", is_active=True
    )
    user = User.objects.create(
        username="reqifimportadmin", email="reqifimportadmin@t.test", tenant=tenant
    )
    user.set_password("reqifpass123")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace_a = Workspace.objects.create(
            tenant=tenant, name="Reqif-Import-WS-A", preset={"name": "standard"}
        )
        workspace_b = Workspace.objects.create(
            tenant=tenant, name="Reqif-Import-WS-B", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace_a, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace_b, role=ROLE_ADMIN
        )

        need_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace_a, artifact_type="StakeholderNeed"
        )
        StakeholderNeed.objects.create(
            tenant=tenant,
            artifact=need_art,
            title="REST Import Need Alpha",
            description="Seeded via ORM for REST import round-trip test",
            category="functional",
            uid="NEED-IMP-001",
        )
        req_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace_a, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=tenant,
            artifact=req_art,
            title="REST Import Req Alpha",
            description="Seeded via ORM for REST import round-trip test",
            category="functional",
            uid="REQ-IMP-001",
        )
    finally:
        clear_request_tenant()

    return user, tenant, workspace_a, workspace_b


def _login(client: APIClient, username: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )
    assert resp.status_code == 200
    return resp.json()["token"]


def _export_reqif(client: APIClient, workspace_id) -> bytes:
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/export/reqif/")
    assert resp.status_code == 200
    return resp.content


# ---------------------------------------------------------------------------
# Success path — export from A, import into B
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_creates_entities_in_target_workspace(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_content = _export_reqif(client, workspace_a.id)

    reqif_file = io.BytesIO(reqif_content)
    reqif_file.name = "export.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["dry_run"] is False
    assert body["needs"]["created"] == 1
    assert body["requirements"]["created"] == 1
    assert body["needs"]["errors"] == []
    assert body["requirements"]["errors"] == []

    set_request_tenant(tenant.id)
    try:
        assert (
            StakeholderNeed.objects.filter(
                artifact__workspace=workspace_b, artifact__reqif_uid="NEED-IMP-001"
            ).count()
            == 1
        )
        assert (
            Requirement.objects.filter(
                artifact__workspace=workspace_b, artifact__reqif_uid="REQ-IMP-001"
            ).count()
            == 1
        )
    finally:
        clear_request_tenant()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_reimport_same_document_is_idempotent(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_content = _export_reqif(client, workspace_a.id)

    for _ in range(2):
        reqif_file = io.BytesIO(reqif_content)
        reqif_file.name = "export.reqif"
        resp = client.post(
            f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
            {"file": reqif_file},
            format="multipart",
        )
        assert resp.status_code == 200

    body = resp.json()
    # ADR-014 §3: identical content on re-import is an idempotent skip.
    assert body["needs"]["created"] == 0
    assert body["needs"]["updated"] == 0
    assert body["needs"]["skipped"] == 1
    assert body["requirements"]["created"] == 0
    assert body["requirements"]["updated"] == 0
    assert body["requirements"]["skipped"] == 1
    assert body["success"] is True
    set_request_tenant(tenant.id)
    try:
        assert (
            StakeholderNeed.objects.filter(artifact__workspace=workspace_b).count()
            == 1
        )
        assert (
            Requirement.objects.filter(artifact__workspace=workspace_b).count() == 1
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_dry_run_does_not_persist(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_content = _export_reqif(client, workspace_a.id)
    reqif_file = io.BytesIO(reqif_content)
    reqif_file.name = "export.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/?dry_run=true",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["needs"]["created"] == 1
    assert body["requirements"]["created"] == 1

    set_request_tenant(tenant.id)
    try:
        assert (
            StakeholderNeed.objects.filter(artifact__workspace=workspace_b).count()
            == 0
        )
        assert (
            Requirement.objects.filter(artifact__workspace=workspace_b).count() == 0
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_malformed_xml_returns_422_parse_error(reqif_import_admin_user):
    """ADR-014 §2 / REQ-L2-RQ-001 AC5: an invalid .reqif file is a file-level
    PARSE_ERROR answered with 422 + structured details (not a 400)."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_file = io.BytesIO(_MALFORMED_REQIF)
    reqif_file.name = "broken.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["contract"] == "v2"
    assert body["counts"]["failed"] == 1
    assert body["items"][0]["cause"]["code"] == "PARSE_ERROR"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_without_file_returns_400(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {},
        format="multipart",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_empty_file_returns_400(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_file = io.BytesIO(b"")
    reqif_file.name = "empty.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_unknown_workspace_returns_404(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_content = _export_reqif(client, workspace_a.id)
    reqif_file = io.BytesIO(reqif_content)
    reqif_file.name = "export.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 404


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_requires_auth(reqif_import_admin_user):
    """Unauthenticated request is rejected (401 or 403, matches test_reqif_export.py)."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()

    reqif_file = io.BytesIO(_MALFORMED_REQIF)
    reqif_file.name = "broken.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# ADR-014 contract v2: 207/422 mapping, skipped-only, Idempotency-Key
# ---------------------------------------------------------------------------


def _upload(client: APIClient, workspace_id, content: bytes, **extra):
    reqif_file = io.BytesIO(content)
    reqif_file.name = "export.reqif"
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
        **extra,
    )


def _counts_in_workspace(tenant, workspace_id) -> tuple:
    set_request_tenant(tenant.id)
    try:
        return (
            StakeholderNeed.objects.filter(artifact__workspace_id=workspace_id).count(),
            Requirement.objects.filter(artifact__workspace_id=workspace_id).count(),
        )
    finally:
        clear_request_tenant()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_partial_failure_returns_207(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    mutated = content.replace(
        b'THE-VALUE="REST Import Req Alpha"',
        b'THE-VALUE="' + b"X" * 501 + b'"',
        1,
    )
    assert mutated != content

    resp = _upload(client, workspace_b.id, mutated)

    assert resp.status_code == 207
    body = resp.json()
    assert body["success"] is False
    assert body["contract"] == "v2"
    assert body["counts"]["failed"] == 1
    assert body["counts"]["succeeded"] >= 1
    failed = [i for i in body["items"] if i["status"] == "failed"]
    assert failed and failed[0]["cause"]["code"] == "INVALID_VALUE"
    # The failing object was rolled back to its savepoint; the valid need stays.
    need_count, req_count = _counts_in_workspace(tenant, workspace_b.id)
    assert need_count == 1
    assert req_count == 0


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_total_failure_returns_422(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    long_title = 'THE-VALUE="' + "X" * 501 + '"'
    mutated = content.replace(b'THE-VALUE="REST Import Need Alpha"', long_title.encode())
    mutated = mutated.replace(b'THE-VALUE="REST Import Req Alpha"', long_title.encode())
    assert mutated != content

    resp = _upload(client, workspace_b.id, mutated)

    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["counts"]["succeeded"] == 0
    assert body["counts"]["failed"] >= 1
    assert body["items"]  # errors/items never empty on total failure


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_skipped_only_returns_200_success(reqif_import_admin_user):
    """A second identical upload is a skipped-only no-op: success with 200."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    assert _upload(client, workspace_b.id, content).status_code == 200

    resp = _upload(client, workspace_b.id, content)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["counts"]["failed"] == 0
    assert body["counts"]["succeeded"] == 0
    assert body["counts"]["skipped"] >= 2


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_idempotency_key_replay_does_not_write(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)

    first = _upload(
        client, workspace_b.id, content, HTTP_IDEMPOTENCY_KEY="reqif-idem-1"
    )
    assert first.status_code == 200
    assert first.json()["idempotent_replay"] is False
    before = _counts_in_workspace(tenant, workspace_b.id)

    replay = _upload(
        client, workspace_b.id, content, HTTP_IDEMPOTENCY_KEY="reqif-idem-1"
    )
    assert replay.status_code == 200
    body = replay.json()
    assert body["idempotent_replay"] is True
    assert body["success"] is True
    after = _counts_in_workspace(tenant, workspace_b.id)
    assert after == before  # no second write effect


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_idempotency_key_reused_with_different_payload_returns_409(
    reqif_import_admin_user,
):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    assert (
        _upload(client, workspace_b.id, content, HTTP_IDEMPOTENCY_KEY="reqif-idem-2")
        .status_code
        == 200
    )

    other = content.replace(
        b'THE-VALUE="REST Import Req Alpha"',
        b'THE-VALUE="REST Import Req Beta"',
        1,
    )
    assert other != content
    resp = _upload(
        client, workspace_b.id, other, HTTP_IDEMPOTENCY_KEY="reqif-idem-2"
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_idempotency_key_too_long_returns_400(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    resp = _upload(
        client, workspace_b.id, content, HTTP_IDEMPOTENCY_KEY="k" * 256
    )
    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_legacy_fallback_when_contract_v2_disabled(
    reqif_import_admin_user,
):
    """IMPORT_CONTRACT_V2=false restores the pre-ADR response (ADR-014 §5)."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    with override_settings(IMPORT_CONTRACT_V2=False):
        resp = _upload(client, workspace_b.id, content)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "contract" not in body
    assert "counts" not in body


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_legacy_fallback_ignores_entity_type(reqif_import_admin_user):
    """F10: under the legacy rollback the ``entity_type`` field is ignored,
    exactly as before v2 — the rollback stays complete."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    reqif_file = io.BytesIO(content)
    reqif_file.name = "export.reqif"
    with override_settings(IMPORT_CONTRACT_V2=False):
        resp = client.post(
            f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
            {"file": reqif_file, "entity_type": "NotARealType"},
            format="multipart",
        )

    assert resp.status_code == 200


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_inactive_entity_type_returns_400(reqif_import_admin_user):
    """F10: a type the ReqIF importer cannot act on is refused, not silently
    ignored (ArchitectureElement/TestCase have no ReqIF path)."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    reqif_file = io.BytesIO(content)
    reqif_file.name = "export.reqif"
    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file, "entity_type": "TestCase"},
        format="multipart",
    )

    assert resp.status_code == 400
    assert "error" in resp.json()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_accepts_matching_entity_type(reqif_import_admin_user):
    """F10: a ReqIF-representable type stays accepted for compatibility."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    reqif_file = io.BytesIO(content)
    reqif_file.name = "export.reqif"
    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file, "entity_type": "Requirement"},
        format="multipart",
    )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# W1 cross-branch: SEC-02/SEC-03 workspace fence x INT-01 ReqIF import
#
# `test_sec02_sec03_workspace_fence.py` fences *generic* detail/create routes;
# the ReqIF import is a workspace-named POST whose target workspace is resolved
# from the URL `pk` (the `workspaces/<uuid:pk>` route marker), not from a
# `workspace_id` kwarg. Nothing pinned that the shared fence actually reaches
# this route and gates the write, so a regression could let a fenced key import
# into a workspace it was explicitly fenced out of.
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_fenced_api_key_blocks_foreign_and_allows_own_workspace(
    reqif_import_admin_user,
):
    """SEC-03 x INT-01: the API-key workspace fence gates the import write.

    The key's owner IS a member of both workspaces, so RBAC alone would admit
    the foreign import; only the workspace fence can deny it. That makes this
    assertion isolate the fence decision from the generic RBAC gate.
    """
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    content = _export_reqif(client, workspace_a.id)

    key = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="reqif-fence-api-key",
        principal_type="agent",
        scope="write",
        workspace_ids=[str(workspace_a.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    fenced = APIClient()
    fenced.credentials(HTTP_X_API_KEY=key.plaintext)

    before_b = _counts_in_workspace(tenant, workspace_b.id)
    denied = _upload(fenced, workspace_b.id, content)

    assert denied.status_code == 403, denied.content
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
    # The denial is enforced before the view: `build_auth_context` narrows a
    # fenced key's roles to () outside its workspaces, and `enforce_request_scope`
    # applies the shared `workspace_fence_denial` as defence in depth. Either way
    # the foreign target is rejected — never silently chosen.
    assert _counts_in_workspace(tenant, workspace_b.id) == before_b, (
        "a fenced key must not write into the workspace it is fenced out of"
    )

    # The fenced workspace is admitted: the URL pk resolves as the target and
    # the fence check passes, so the import reaches the service (200).
    allowed = _upload(fenced, workspace_a.id, content)

    assert allowed.status_code == 200, allowed.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_denies_caller_without_role_in_target_workspace(
    reqif_import_admin_user,
):
    """SEC-02 x INT-01: a non-member cannot write via the import route.

    The caller holds a role in workspace A only; importing into B is denied and
    B stays untouched. Importing into the workspace they DO belong to still
    succeeds, so the denial is target-scoped, not a blanket block.
    """
    _user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    admin = APIClient()
    admin_token = _login(admin, "reqifimportadmin", "reqifpass123")
    admin.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
    content = _export_reqif(admin, workspace_a.id)

    outsider = User.objects.create(
        username="reqif-outsider", email="reqif-outsider@t.test", tenant=tenant
    )
    outsider.set_password("outsiderpass123")
    outsider.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=outsider, workspace=workspace_a, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    token = _login(client, "reqif-outsider", "outsiderpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    before_b = _counts_in_workspace(tenant, workspace_b.id)
    denied = _upload(client, workspace_b.id, content)

    assert denied.status_code == 403, denied.content
    assert _counts_in_workspace(tenant, workspace_b.id) == before_b

    allowed = _upload(client, workspace_a.id, content)

    assert allowed.status_code == 200, allowed.content


# ---------------------------------------------------------------------------
# W1 cross-branch: DATA-03 CAS (expected_version) x INT-01 import write
#
# DATA-03 pins `expected_version` on the service/transition paths; the ReqIF
# import writes `WorkflowItemState` directly through the shared CAS writer. The
# combination — does a revision bumped by an import make a stale `transitions/`
# precondition conflict, and does the failed compare roll back cleanly — was
# untested.
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_bumps_workflow_version_and_stale_expected_version_conflicts(
    reqif_import_admin_user,
):
    """DATA-03 x INT-01: an import revision is observable through the CAS gate.

    Workspace A's requirement is put into ``in_review`` before the export, so
    importing into workspace B must CAS-move the fresh row off its initial
    ``draft`` state and bump its workflow revision. A transition asserting the
    pre-import revision must answer 409 without mutating the row; the revision
    the import left behind must succeed.
    """
    _user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # Real state machines on both sides: the import's state write and the
    # transition CAS both need a WorkflowEngineDefinition to operate on.
    set_request_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace_a.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        create_default_workflow(
            workspace_id=workspace_b.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        req_a = Requirement.objects.get(artifact__workspace=workspace_a)
        definition_a = WorkflowEngineDefinition.objects.get(
            workspace_id=workspace_a.id, item_type="Requirement"
        )
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=req_a.id,
            item_type="Requirement",
            workspace_id=workspace_a.id,
            definition=definition_a,
            current_state="in_review",
        )
    finally:
        clear_request_tenant()

    content = _export_reqif(client, workspace_a.id)
    imported = _upload(client, workspace_b.id, content)

    assert imported.status_code == 200, imported.content

    set_request_tenant(tenant.id)
    try:
        req_b = Requirement.objects.get(artifact__workspace=workspace_b)
        state = WorkflowItemState.objects.get(
            item_id=req_b.id, item_type="Requirement"
        )
        assert state.current_state == "in_review"
        # Created at the definition's initial state ("draft", revision 1) and
        # CAS-moved once -> revision 2. This is the revision the import exposes.
        assert state.version == 2
        history_before = WorkflowHistoryEntry.objects.filter(
            item_state=state
        ).count()
        # The fixture's workspaces use the "standard" rigor preset, whose
        # approval gate requires acceptance_criteria. Fill it so the *success*
        # case exercises the CAS compare rather than the mandatory-field gate.
        req_b.acceptance_criteria = "Met by the W1 cross-branch integration test."
        req_b.save(update_fields=["acceptance_criteria"])
    finally:
        clear_request_tenant()

    # A client that read revision 1 before the import is now stale.
    stale = client.post(
        f"/api/v1/requirements/{req_b.id}/transitions/",
        {
            "target_state": "approved",
            "change_reason": "advance",
            "expected_version": 1,
        },
        format="json",
    )

    assert stale.status_code == 409, stale.content
    assert stale.json()["error"]["code"] == "CONFLICT"

    # The rejected transition rolled back cleanly: the import's write survives,
    # no history entry was appended and the revision is unchanged.
    set_request_tenant(tenant.id)
    try:
        state.refresh_from_db()
        assert state.version == 2
        assert state.current_state == "in_review"
        assert (
            WorkflowHistoryEntry.objects.filter(item_state=state).count()
            == history_before
        )
    finally:
        clear_request_tenant()

    # The revision the import left behind succeeds.
    ok = client.post(
        f"/api/v1/requirements/{req_b.id}/transitions/",
        {
            "target_state": "approved",
            "change_reason": "advance",
            "expected_version": 2,
        },
        format="json",
    )

    assert ok.status_code == 200, ok.content
    assert ok.json()["new_state"] == "approved"
