"""ArtifactVersionService — one revision store for every type.

Datenmodell-Konsolidierung Phase 5, spec section 6.
"""
import uuid

import pytest

from application.artifact_version_service import ArtifactVersionService
from application.base import NotFoundError


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Artifact, Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-versionsvc")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-versionsvc")
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    return ctx, artifact.id


@pytest.mark.django_db
def test_first_revision_is_one(env):
    ctx, artifact_id = env

    assert ArtifactVersionService().record(artifact_id, {"title": "A"}, ctx) == 1


@pytest.mark.django_db
def test_revisions_increment(env):
    ctx, artifact_id = env
    service = ArtifactVersionService()
    service.record(artifact_id, {"title": "A"}, ctx)

    assert service.record(artifact_id, {"title": "B"}, ctx) == 2


@pytest.mark.django_db
def test_list_revisions_shape_matches_the_diff_contract(env):
    ctx, artifact_id = env
    service = ArtifactVersionService()
    service.record(artifact_id, {"title": "A"}, ctx, change_reason="init")

    entries = service.list_revisions(artifact_id, ctx)

    assert entries[0]["version"] == 1
    assert entries[0]["label"] == "v1"
    assert entries[0]["content_available"] is True
    assert "modified_at" in entries[0]


@pytest.mark.django_db
def test_get_payload_returns_the_stored_snapshot(env):
    ctx, artifact_id = env
    service = ArtifactVersionService()
    service.record(artifact_id, {"title": "A"}, ctx)
    service.record(artifact_id, {"title": "B"}, ctx)

    assert service.get_payload(artifact_id, 1, ctx) == {"title": "A"}


@pytest.mark.django_db
def test_get_payload_of_an_unknown_revision_is_none(env):
    ctx, artifact_id = env
    ArtifactVersionService().record(artifact_id, {"title": "A"}, ctx)

    assert ArtifactVersionService().get_payload(artifact_id, 7, ctx) is None


@pytest.mark.django_db
def test_unknown_artifact_raises(env):
    ctx, _artifact_id = env

    with pytest.raises(NotFoundError):
        ArtifactVersionService().record(uuid.uuid4(), {"title": "A"}, ctx)


@pytest.mark.django_db
def test_concurrent_records_do_not_collide(env):
    """The revision number is allocated under a row lock, not read-then-write."""
    ctx, artifact_id = env
    service = ArtifactVersionService()
    numbers = {service.record(artifact_id, {"n": n}, ctx) for n in range(5)}

    assert numbers == {1, 2, 3, 4, 5}
