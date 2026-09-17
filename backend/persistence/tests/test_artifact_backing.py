"""Shared Artifact-backing helper (Datenmodell-Konsolidierung Phase 3)."""
import uuid

import pytest
from django.db import transaction

from persistence.artifact_backing import ArtifactBackingError, ensure_artifact


@pytest.fixture
def diagram_env(db):
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    from diagram.models import Diagram

    tenant = Tenant.objects.create(name="t-backing", slug="t-backing")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-backing")
    diagram = Diagram.objects.create(
        tenant=tenant,
        name="D1",
        diagram_type="block",
        workspace_id=workspace.id,
    )
    orphan = Diagram.objects.create(
        tenant=tenant, name="D2", diagram_type="block", workspace_id=None
    )
    return tenant, workspace, diagram, orphan


@pytest.mark.django_db
def test_creates_the_artifact_row(diagram_env):
    from persistence.models import Artifact

    _tenant, _workspace, diagram, _orphan = diagram_env

    with transaction.atomic():
        artifact_id = ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )

    artifact = Artifact.objects.get(pk=artifact_id)
    assert artifact.artifact_type == "Diagram"
    diagram.refresh_from_db()
    assert diagram.artifact_id == artifact_id


@pytest.mark.django_db
def test_is_idempotent(diagram_env):
    from persistence.models import Artifact

    _tenant, _workspace, diagram, _orphan = diagram_env

    with transaction.atomic():
        first = ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )
    with transaction.atomic():
        second = ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )

    assert first == second
    assert Artifact.objects.filter(artifact_type="Diagram").count() == 1


@pytest.mark.django_db
def test_missing_workspace_raises(diagram_env):
    _tenant, _workspace, _diagram, orphan = diagram_env

    with pytest.raises(ArtifactBackingError) as excinfo:
        with transaction.atomic():
            ensure_artifact(orphan, artifact_type="Diagram", workspace_id=None)

    assert "workspace" in str(excinfo.value)


@pytest.mark.django_db(transaction=True)
def test_requires_an_open_transaction(diagram_env):
    # `transaction=True` is required here: the default `django_db` marker
    # wraps the whole test body in an outer atomic block for rollback
    # (pytest-django `db` fixture), which would make
    # ``transaction.get_connection().in_atomic_block`` true even without an
    # explicit ``with transaction.atomic():`` below — masking the very case
    # this test exercises.
    from django.db.transaction import TransactionManagementError

    _tenant, _workspace, diagram, _orphan = diagram_env

    with pytest.raises((TransactionManagementError, ArtifactBackingError)):
        ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )


@pytest.mark.django_db
def test_custom_field_name_is_honoured(diagram_env):
    _tenant, _workspace, diagram, _orphan = diagram_env

    with transaction.atomic():
        artifact_id = ensure_artifact(
            diagram,
            artifact_type="Diagram",
            workspace_id=diagram.workspace_id,
            field_name="artifact",
        )

    assert isinstance(artifact_id, uuid.UUID)
