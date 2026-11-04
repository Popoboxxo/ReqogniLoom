"""C10 / #1410 — the orphan-artifact command reports and soft-deletes safely."""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def orphan_artifact():
    from persistence.models import Artifact, Tenant, Workspace

    tenant = Tenant.objects.create(
        name=f"orphan-{uuid.uuid4().hex}", slug=f"orphan-{uuid.uuid4().hex}"
    )
    workspace = Workspace.unscoped.create(
        tenant=tenant, name=f"orphan-{uuid.uuid4().hex}"
    )
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
    )
    return artifact


def test_report_is_read_only(orphan_artifact, capsys):
    call_command("audit_orphan_artifacts")

    orphan_artifact.refresh_from_db()
    assert orphan_artifact.lifecycle_status == "active"
    out = capsys.readouterr().out
    assert "Orphan artifacts: 1" in out
    assert "Requirement: 1" in out


def test_apply_soft_deletes_the_orphan(orphan_artifact):
    call_command("audit_orphan_artifacts", "--apply")

    orphan_artifact.refresh_from_db()
    assert orphan_artifact.lifecycle_status == "outdated"
