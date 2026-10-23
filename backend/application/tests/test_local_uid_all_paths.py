"""G1.1 — the local readable ``uid`` is allocated on *every* create path.

Issue #1386 (ReqIF import and seed_toothbrush wrote no ``uid``) and #1402
(uid uniqueness needs a per-row workspace to constrain against).

The eight services that call :func:`application.local_uid.generate_local_uid`
explicitly are not the only writers: the ReqIF importer, ``seed_toothbrush`` and
any future direct-ORM path bypassed them. These tests pin the root-cause fix —
one ``pre_save`` receiver for the eight uid models — rather than the individual
patches it replaces.

DB-marker convention mirrors ``test_reqif_import_service.py``: module-level
``pytestmark = pytest.mark.django_db`` and an explicitly armed tenant.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from django.apps import apps
from django.core.management import call_command

from application.local_uid import (
    UID_MODELS,
    UID_PREFIXES,
    assign_local_uid,
)
from application.reqif_export_service import ReqifExportService
from application.reqif_import_service import ReqifImportService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    TestCase,
    UidSequence,
    Workspace,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mock_embedding_provider(monkeypatch):
    """Pin the mock embedding provider so this module stays hermetic.

    ``.env`` ships ``EMBEDDING_PROVIDER=sentence-transformers`` and the test
    compose stack loads it through ``env_file``; ``settings_test`` pins
    ``LLM_PROVIDER`` but not ``EMBEDDING_PROVIDER``. Without this pin
    ``seed_toothbrush`` -> ``create_requirement`` ->
    ``_generate_and_store_embedding`` runs a real CPU sentence-transformers
    encode and the module takes minutes instead of seconds.

    ``get_embedding_provider`` re-reads the environment on every call and holds
    no cached provider instance, so setting the variable is sufficient — the
    same pattern ``test_backfill_embeddings_command.py`` uses.
    """
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    return ctx


@pytest.fixture
def tenant():
    tenant = Tenant.objects.create(
        name="G1.1 UID Tenant", slug=f"g11-uid-{uuid.uuid4().hex[:10]}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        yield tenant
    finally:
        clear_request_tenant()


def _workspace(tenant: Tenant, name: str) -> Workspace:
    return Workspace.objects.create(tenant=tenant, name=name)


def test_reqif_import_assigns_local_uid(tenant):
    """An imported entity gets a *local* uid; the ReqIF identity stays external.

    The source workspace carries an explicit ``REQ-042``. ReqIF export writes it
    as ``ATTR-UID``; import must store that on ``Artifact.reqif_uid`` and let the
    receiver allocate a fresh local ``REQ-001`` — never copy the source value.
    """
    source = _workspace(tenant, "ReqIF UID Source")
    target = _workspace(tenant, "ReqIF UID Target")

    need_artifact = Artifact.objects.create(
        tenant=tenant, workspace=source, artifact_type="StakeholderNeed"
    )
    StakeholderNeed.objects.create(
        tenant=tenant,
        artifact=need_artifact,
        title="Source Need",
        uid="NEED-042",
    )
    req_artifact = Artifact.objects.create(
        tenant=tenant, workspace=source, artifact_type="Requirement"
    )
    Requirement.objects.create(
        tenant=tenant,
        artifact=req_artifact,
        title="Source Requirement",
        uid="REQ-042",
    )

    reqif_text = ReqifExportService().export_reqif(
        workspace_id=source.id, ctx=_ctx(tenant.id)
    ).content
    ReqifImportService().import_reqif(
        reqif_text=reqif_text,
        workspace_id=target.id,
        ctx=_ctx(tenant.id),
    )

    imported_req = Requirement.objects.get(artifact__workspace_id=target.id)
    imported_need = StakeholderNeed.objects.get(artifact__workspace_id=target.id)

    assert imported_req.uid == "REQ-001"
    assert imported_need.uid == "NEED-001"
    # External identity is untouched by the local allocation.
    assert imported_req.artifact.reqif_uid == "REQ-042"
    assert imported_need.artifact.reqif_uid == "NEED-042"


def test_direct_orm_create_assigns_uid_and_workspace(tenant):
    """A plain ``TestCase.objects.create`` gets a local uid (and a workspace).

    ``workspace`` is asserted on Requirement, which already carries the
    denormalized FK in this PR; TestCase/ArchitectureElement/StakeholderNeed
    receive the same field and assertion in G1.3 (PR 3).
    """
    workspace = _workspace(tenant, "Direct ORM WS")

    first_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="TestCase"
    )
    first = TestCase.objects.create(
        tenant=tenant, artifact=first_artifact, title="Direct one"
    )
    second_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="TestCase"
    )
    second = TestCase.objects.create(
        tenant=tenant, artifact=second_artifact, title="Direct two"
    )
    explicit_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="TestCase"
    )
    explicit = TestCase.objects.create(
        tenant=tenant, artifact=explicit_artifact, title="Explicit", uid="X-1"
    )

    assert first.uid == "TC-001"
    assert second.uid == "TC-002"
    assert explicit.uid == "X-1"

    requirement_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    requirement = Requirement.objects.create(
        tenant=tenant, artifact=requirement_artifact, title="Direct requirement"
    )
    assert requirement.workspace_id == workspace.id


def test_seed_toothbrush_needs_have_uid(tenant):
    """The demo seed writes StakeholderNeeds through the ORM — all get a uid.

    Live QA measured 0/20 needs with a uid before G1.1 (G-L4); this asserts the
    gap is closed at the source rather than by a data backfill alone.
    """
    call_command("seed_toothbrush")

    needs = StakeholderNeed.unscoped.filter(tenant_id=tenant.id)
    assert needs.exists(), "seed_toothbrush must create needs"
    assert not needs.filter(uid__isnull=True).exists()
    assert not needs.filter(uid="").exists()


def test_raw_fixture_load_does_not_allocate(tenant):
    """``raw=True`` (fixture loading) must not touch the uid sequence."""
    workspace = _workspace(tenant, "Raw fixture WS")
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    instance = Requirement(tenant=tenant, artifact=artifact, title="Fixture row")

    assign_local_uid(sender=Requirement, instance=instance, raw=True)

    assert instance.uid is None
    assert (
        UidSequence.unscoped.filter(workspace_id=workspace.id).count() == 0
    ), "fixture loading must not consume a local uid number"


def test_uid_models_and_prefixes_in_sync():
    """Every uid model has a prefix and a ``uid`` field — and vice versa.

    Set-membership, not a total count: Plan F adds Document/WorkItem to both
    collections in its own PR.
    """
    model_names = set()
    for label in UID_MODELS:
        model = apps.get_model(label)
        model_names.add(model.__name__)
        assert any(
            field.name == "uid" for field in model._meta.get_fields()
        ), f"{label} is registered in UID_MODELS but has no uid field"

    assert model_names == set(UID_PREFIXES), (
        "UID_MODELS and UID_PREFIXES disagree: "
        f"models-only={sorted(model_names - set(UID_PREFIXES))}, "
        f"prefixes-only={sorted(set(UID_PREFIXES) - model_names)}"
    )
