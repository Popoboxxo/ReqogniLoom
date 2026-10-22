"""G1.3/#1402 — per-workspace ``uid`` uniqueness for the eight uid models.

Requirement's constraint shipped in persistence/0055; this PR extends the same
partial, workspace-scoped invariant to the other seven. The tests pin both
halves of the migration pair:

* the resulting DB constraints (duplicates rejected, cross-workspace reuse and
  blank uids allowed), and
* the migration's own behaviour (it renames pre-existing collisions, and the
  reverse/forward round-trip is clean).

Rollback/target migration names are used verbatim, never bare numbers (Plan
Index §e rule 4). At the time of writing the predecessor of
``0117_entity_workspace_fk_backfill`` is ``0116_index_hygiene_1411`` — the index
table's expected 0116 was already taken on ``main``, so the whole G1.3 pair
shifted by one (rule 1).
"""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from persistence.models import (
    Adr,
    ArchitectureElement,
    Artifact,
    Issue,
    Risk,
    StakeholderNeed,
    TestCase,
    TestRun,
    Workspace,
)
from persistence.tests.factories import active_tenant, make_workspace

pytestmark = pytest.mark.django_db

_PREREQUISITE = "0117_entity_workspace_fk_backfill"
_CONSTRAINTS = "0118_uid_workspace_unique_constraints"


def _artifact(tenant, workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _build(tenant, workspace, model_name: str, uid: str):
    """Create one row of *model_name* with an explicit uid in *workspace*."""
    if model_name == "TestCase":
        return TestCase.objects.create(
            tenant=tenant,
            artifact=_artifact(tenant, workspace, "TestCase"),
            workspace=workspace,
            title=f"TC {uid}",
            uid=uid,
        )
    if model_name == "ArchitectureElement":
        return ArchitectureElement.objects.create(
            tenant=tenant,
            artifact=_artifact(tenant, workspace, "ArchitectureElement"),
            workspace=workspace,
            title=f"ARCH {uid}",
            uid=uid,
        )
    if model_name == "StakeholderNeed":
        return StakeholderNeed.objects.create(
            tenant=tenant,
            artifact=_artifact(tenant, workspace, "StakeholderNeed"),
            workspace=workspace,
            title=f"NEED {uid}",
            uid=uid,
        )
    if model_name == "TestRun":
        return TestRun.objects.create(
            tenant=tenant, workspace=workspace, name=f"RUN {uid}", uid=uid
        )
    if model_name == "Adr":
        return Adr.objects.create(
            tenant=tenant, workspace_id=workspace.id, title=f"ADR {uid}", uid=uid
        )
    if model_name == "Risk":
        return Risk.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            title=f"RISK {uid}",
            probability="low",
            impact="low",
            uid=uid,
        )
    if model_name == "Issue":
        return Issue.objects.create(
            tenant=tenant, workspace_id=workspace.id, title=f"ISSUE {uid}", uid=uid
        )
    raise AssertionError(f"unknown model {model_name}")


_MODELS = ("TestCase", "ArchitectureElement", "StakeholderNeed", "TestRun", "Adr", "Risk", "Issue")


@pytest.mark.parametrize("model_name", _MODELS)
def test_duplicate_uid_same_workspace_rejected(model_name):
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        _build(tenant, workspace, model_name, "DUP-001")

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _build(tenant, workspace, model_name, "DUP-001")


@pytest.mark.parametrize("model_name", _MODELS)
def test_same_uid_other_workspace_allowed(model_name):
    """ReqIF semantics: the same identifier may exist in another workspace."""
    with active_tenant() as tenant:
        first = make_workspace(tenant, name="WS A")
        second = make_workspace(tenant, name="WS B")

        _build(tenant, first, model_name, "SAME-001")
        _build(tenant, second, model_name, "SAME-001")

        if model_name in {"Adr", "Risk", "Issue"}:
            model = {"Adr": Adr, "Risk": Risk, "Issue": Issue}[model_name]
            workspace_ids = set(
                model.objects.filter(uid="SAME-001").values_list(
                    "workspace_id", flat=True
                )
            )
        else:
            model = {
                "TestCase": TestCase,
                "ArchitectureElement": ArchitectureElement,
                "StakeholderNeed": StakeholderNeed,
                "TestRun": TestRun,
            }[model_name]
            workspace_ids = set(
                model.objects.filter(uid="SAME-001").values_list(
                    "workspace_id", flat=True
                )
            )
        assert workspace_ids == {first.id, second.id}


@pytest.mark.parametrize("model_name", _MODELS)
def test_blank_uid_not_constrained(model_name):
    """Two blank uids are allowed — the constraint is partial."""
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)

        _build(tenant, workspace, model_name, "")
        _build(tenant, workspace, model_name, "")


@pytest.mark.django_db(transaction=True)
def test_migration_dedupes_existing_collisions(transactional_db):
    """Pre-existing duplicates are renamed by the migration, never deleted."""
    tenant_name = f"G1.3 dedupe {uuid.uuid4().hex[:8]}"
    from persistence.models import Tenant

    tenant = Tenant.objects.create(name=tenant_name, slug=tenant_name, is_active=True)
    from persistence.middleware import clear_request_tenant, set_request_tenant

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="Dedupe WS")

        # Step 1: move the persistence app back to the state *before* the
        # constraints, so duplicates can exist at all.
        executor = MigrationExecutor(connection)
        executor.migrate([("persistence", _PREREQUISITE)])
        old_apps = executor.loader.project_state(
            [("persistence", _PREREQUISITE)]
        ).apps
        OldArtifact = old_apps.get_model("persistence", "Artifact")
        OldTestCase = old_apps.get_model("persistence", "TestCase")

        artifact_id = uuid.uuid4()
        OldArtifact.objects.create(
            id=artifact_id,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact_type="TestCase",
        )
        OldTestCase.objects.create(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            artifact_id=artifact_id,
            workspace_id=workspace.id,
            title="Oldest duplicate",
            uid="TC-001",
            version=1,
        )
        second_artifact = uuid.uuid4()
        OldArtifact.objects.create(
            id=second_artifact,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact_type="TestCase",
        )
        OldTestCase.objects.create(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            artifact_id=second_artifact,
            workspace_id=workspace.id,
            title="Later duplicate",
            uid="TC-001",
            version=1,
        )

        # Step 2: forward again — the dedupe step must rename the later row.
        executor = MigrationExecutor(connection)
        executor.migrate([("persistence", _CONSTRAINTS)])

        uids = sorted(
            TestCase.objects.filter(workspace_id=workspace.id).values_list(
                "uid", flat=True
            )
        )
        assert uids == ["TC-001", "TC-001 (2)"]
    finally:
        clear_request_tenant()


@pytest.mark.django_db(transaction=True)
def test_migration_reverse_roundtrip(transactional_db):
    """``0117`` → ``0118`` → ``0117`` → ``0118`` is clean by name."""
    executor = MigrationExecutor(connection)
    executor.migrate([("persistence", _PREREQUISITE)])
    executor = MigrationExecutor(connection)
    executor.migrate([("persistence", _CONSTRAINTS)])
    executor = MigrationExecutor(connection)
    executor.migrate([("persistence", _PREREQUISITE)])
    executor = MigrationExecutor(connection)
    executor.migrate([("persistence", _CONSTRAINTS)])

    # The constraint exists again after the final forward pass.
    from django.db import connection as live_connection

    with live_connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint WHERE conname LIKE 'uq_%_workspace_uid'"
        )
        names = {row[0] for row in cursor.fetchall()}

    assert {
        "uq_requirement_workspace_uid",
        "uq_testcase_workspace_uid",
        "uq_architecture_element_workspace_uid",
        "uq_stakeholder_need_workspace_uid",
        "uq_test_run_workspace_uid",
        "uq_adr_workspace_uid",
        "uq_risk_workspace_uid",
        "uq_issue_workspace_uid",
    } <= names
