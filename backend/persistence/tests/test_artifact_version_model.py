"""Generic content-revision table (Datenmodell-Konsolidierung Phase 5)."""
import pytest
from django.db import IntegrityError, connection

from persistence.models import ArtifactVersion


@pytest.fixture
def artifact(db):
    from persistence.models import Artifact, Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-version")
    TenantContext.set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-version")
    return Tenant.objects.get(pk=tenant.id), Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )


def test_table_name():
    assert ArtifactVersion._meta.db_table == "pl_artifact_version"


def test_revision_is_not_the_lock_counter():
    field_names = {f.name for f in ArtifactVersion._meta.local_fields}
    assert "revision" in field_names


@pytest.mark.django_db
def test_revision_is_unique_per_artifact(artifact):
    tenant, art = artifact
    ArtifactVersion.objects.create(
        tenant=tenant, artifact=art, revision=1, payload={"title": "A"}
    )

    with pytest.raises(IntegrityError):
        ArtifactVersion.objects.create(
            tenant=tenant, artifact=art, revision=1, payload={"title": "B"}
        )


@pytest.mark.django_db
def test_payload_round_trips(artifact):
    tenant, art = artifact
    row = ArtifactVersion.objects.create(
        tenant=tenant,
        artifact=art,
        revision=1,
        payload={"title": "A", "steps": [{"n": 1}]},
        change_reason="initial",
    )
    row.refresh_from_db()

    assert row.payload["steps"] == [{"n": 1}]
    assert row.change_reason == "initial"


@pytest.mark.django_db
def test_rls_policy_exists():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT policyname FROM pg_policies WHERE tablename = 'pl_artifact_version'"
        )
        policies = {row[0] for row in cursor.fetchall()}

    assert "pl_artifact_version_tenant_isolation" in policies
