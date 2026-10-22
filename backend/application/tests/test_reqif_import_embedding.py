"""G1.2 — ReqIF-imported requirements are embedded after the import commits.

Issue #1386: the importer wrote Requirements through the ORM, bypassing
``RequirementService._generate_and_store_embedding`` — imported requirements
never had a vector, so semantic search could not see them. The fix enqueues the
shared embedding task via ``transaction.on_commit`` instead of embedding on the
request thread (a provider cold start must not sit inside the HTTP response).

``transaction=True`` is deliberate: pytest-django's default ``django_db`` wraps
each test in a rolled-back transaction, in which ``on_commit`` callbacks never
run. These tests must observe the *committed* import, like production.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from django.db import OperationalError

from application.reqif_export_service import ReqifExportService
from application.reqif_import_service import ReqifImportService
from application.tasks import embed_rows_task
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    Workspace,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    return ctx


@pytest.fixture
def workspaces(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    tenant = Tenant.objects.create(
        name="G1.2 Import Tenant",
        slug=f"g12-import-{uuid.uuid4().hex[:10]}",
        is_active=True,
    )
    set_request_tenant(tenant.id)
    try:
        source = Workspace.objects.create(tenant=tenant, name="ReqIF Embed Source")
        target = Workspace.objects.create(tenant=tenant, name="ReqIF Embed Target")

        need_artifact = Artifact.objects.create(
            tenant=tenant, workspace=source, artifact_type="StakeholderNeed"
        )
        StakeholderNeed.objects.create(
            tenant=tenant, artifact=need_artifact, title="Embedded Need"
        )
        req_artifact = Artifact.objects.create(
            tenant=tenant, workspace=source, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=tenant,
            artifact=req_artifact,
            title="Requirement to embed",
            description="A body long enough to produce a stable embedding.",
        )
        yield tenant, source, target
    finally:
        clear_request_tenant()


def _export_and_import(source: Workspace, target: Workspace, tenant_id):
    reqif_text = ReqifExportService().export_reqif(
        workspace_id=source.id, ctx=_ctx(tenant_id)
    ).content
    return ReqifImportService().import_reqif(
        reqif_text=reqif_text,
        workspace_id=target.id,
        ctx=_ctx(tenant_id),
    )


def test_import_enqueues_embedding_after_commit(workspaces):
    """Every imported requirement carries an embedding once the import commits."""
    tenant, source, target = workspaces

    result = _export_and_import(source, target, tenant.id)

    assert result.success
    imported = Requirement.objects.filter(artifact__workspace_id=target.id)
    assert imported.exists(), "the fixture must round-trip at least one requirement"
    assert not imported.filter(embedding__isnull=True).exists(), (
        "ReqIF import must embed its requirements via the after-commit task"
    )


def test_import_survives_broker_failure(workspaces, monkeypatch, caplog):
    """A broker outage leaves the import successful and logs a warning.

    The rows are persisted (that is the contract: a missing vector is
    recoverable with ``backfill_embeddings``), so a queue failure must never
    turn a 200 into a 500.
    """
    tenant, source, target = workspaces

    def _broker_down(*args, **kwargs):
        raise OperationalError("broker unreachable")

    monkeypatch.setattr(embed_rows_task, "delay", _broker_down)

    with caplog.at_level("WARNING"):
        result = _export_and_import(source, target, tenant.id)

    assert result.success
    assert result.requirements.created + result.requirements.updated > 0
    assert Requirement.objects.filter(artifact__workspace_id=target.id).exists()
    assert any(
        "could not enqueue embedding" in record.getMessage()
        for record in caplog.records
    ), "the fallback path must be visible in the log"
