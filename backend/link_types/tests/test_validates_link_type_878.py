"""#878 / Plan B B2-T1 — the built-in ``validates`` link type (TestCase -> Need).

Four units:

* the catalog contract: ``validates`` links a TestCase to a StakeholderNeed and
  to nothing else;
* the seed migration ``0011_seed_validates_link_type``, exercised through the
  real ``MigrationExecutor`` (names, never numbers) with a real ``Workspace``
  row created *before* the migration runs — a catalog addition must reach an
  existing workspace, not only a freshly provisioned one;
* that migration's reverse guard: unapplying it must abort while a ``validates``
  link still exists, and unapply cleanly once the link is gone;
* the REST through-stitch: the type is reachable end to end through
  ``POST /api/v1/trace-links/``, i.e. it really is in the workspace catalog the
  create path validates against.

KA-G-10: every test here uses a real ``Workspace`` row, never a bare
workspace-id stub — the catalog resolves through ``lt_workspace_definition``,
so a stub has no rows to resolve.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.catalog import validate_link_pair
from link_types.models import WorkspaceLinkTypeDefinition
from link_types.workspace_store import provision_workspace_link_types
from persistence.errors import ValidationError
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, TraceLink, User, Workspace
from persistence.tenancy import TenantContext

_LINK_TYPES_APP = "link_types"
_PRE_TARGET = (_LINK_TYPES_APP, "0010_workspace_definition_workspace_fk")
_SEED = (_LINK_TYPES_APP, "0011_seed_validates_link_type")
_KEY = "validates"
_WANTED_PAIR = {"source_type": "TestCase", "target_type": "StakeholderNeed"}
_PASSWORD = "hunter2pass"


@pytest.fixture
def workspace(db) -> Workspace:
    """A real workspace row with the provisioned built-in catalog."""
    tenant = Tenant.objects.create(
        name="validates-878", slug=f"validates-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    row = Workspace.objects.create(tenant=tenant, name="validates-ws")
    provision_workspace_link_types(workspace_id=row.id, tenant_id=tenant.id)
    yield row
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_validates_allows_testcase_to_need_only(workspace: Workspace) -> None:
    validate_link_pair(
        workspace.id, _KEY, "TestCase", "StakeholderNeed", manual=True
    )

    with pytest.raises(ValidationError) as exc:
        validate_link_pair(
            workspace.id, _KEY, "TestCase", "Requirement", manual=True
        )
    assert "Allowed: TestCase->StakeholderNeed" in str(exc.value)
    # The message must name only the one allowed pair — `verifies` owns the
    # Requirement endpoint, and a single-pair type must not advertise it.
    assert "TestCase->Requirement" not in str(exc.value)


@pytest.mark.django_db(transaction=True)
def test_migration_seeds_existing_workspace() -> None:
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        historical = executor.loader.project_state([_PRE_TARGET]).apps
        TenantModel = historical.get_model("persistence", "Tenant")
        WorkspaceModel = historical.get_model("persistence", "Workspace")
        WorkspaceDefinition = historical.get_model(
            _LINK_TYPES_APP, "WorkspaceLinkTypeDefinition"
        )

        tenant = TenantModel.objects.create(
            name="validates-878-migration", slug=f"val-mig-{uuid.uuid4().hex[:8]}"
        )
        workspace_row = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="pre-existing-ws"
        )
        customized = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=workspace_row.id,
            key="verifies",
            definition_json={"impact_weight": 0.77},
            is_customized=True,
        )
        assert not WorkspaceDefinition.objects.filter(
            tenant_id=tenant.id, key=_KEY
        ).exists()
        # A tenant-invented ``validates`` row predating the built-in of the same
        # name: the seed's ``get_or_create`` must leave it alone on the very key
        # this migration introduces, and must not add a second row for that
        # workspace. A second workspace keeps the assertions on ``workspace_row``
        # unambiguous.
        other_ws = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="custom-validates-ws"
        )
        customized_validates = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=other_ws.id,
            key=_KEY,
            definition_json={"impact_weight": 0.42},
            is_customized=True,
        )

        executor.migrate([_SEED])
        executor.loader.build_graph()
        seeded_apps = executor.loader.project_state([_SEED]).apps
        SeededDefinition = seeded_apps.get_model(
            _LINK_TYPES_APP, "WorkspaceLinkTypeDefinition"
        )
        GlobalDefinition = seeded_apps.get_model(
            _LINK_TYPES_APP, "GlobalLinkTypeDefinition"
        )

        row = SeededDefinition.objects.get(
            tenant_id=tenant.id, workspace_id=workspace_row.id, key=_KEY
        )
        assert row.is_customized is False
        assert row.definition_json["allowed_pairs"] == [_WANTED_PAIR]
        assert row.definition_json["label"]["de"]["downstream"] == "validiert"
        assert GlobalDefinition.objects.filter(
            tenant_id=tenant.id, key=_KEY
        ).exists()

        untouched = SeededDefinition.objects.get(pk=customized.pk)
        assert untouched.definition_json == {"impact_weight": 0.77}
        assert untouched.is_customized is True

        kept_validates = SeededDefinition.objects.get(pk=customized_validates.pk)
        assert kept_validates.definition_json == {"impact_weight": 0.42}
        assert kept_validates.is_customized is True
        assert (
            SeededDefinition.objects.filter(
                tenant_id=tenant.id, workspace_id=other_ws.id, key=_KEY
            ).count()
            == 1
        )
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)


def _seeded_rows(tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> int:
    """Count this tenant's seeded ``validates`` rows in *workspace_id*."""
    return WorkspaceLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant_id, workspace_id=workspace_id, key=_KEY
    ).count()


@pytest.mark.django_db(transaction=True)
def test_reverse_refuses_to_orphan_a_validates_link() -> None:
    """Unapplying the seed must abort while a ``validates`` link exists.

    Dropping the type would leave those links on a key that no workspace catalog
    can resolve — silent data loss — so the reverse counts them first and raises
    instead. Once the links are gone the reverse is clean again, and re-applying
    the seed restores the row.
    """
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()

        tenant = Tenant.objects.create(
            name="validates-878-reverse", slug=f"val-rev-{uuid.uuid4().hex[:8]}"
        )
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(tenant=tenant, name="reverse-ws")
            testcase = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="TestCase"
            )
            need = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="StakeholderNeed"
            )
            link = TraceLink.objects.create(
                tenant=tenant, source=testcase, target=need, link_type=_KEY
            )

            executor.migrate([_SEED])
            executor.loader.build_graph()
            assert _seeded_rows(tenant.id, workspace.id) == 1

            with pytest.raises(RuntimeError, match="1 TraceLink row") as exc:
                executor.migrate([_PRE_TARGET])
            assert _KEY in str(exc.value)
            # ... and the refused reverse left the catalog untouched.
            assert _seeded_rows(tenant.id, workspace.id) == 1

            link.delete()
        finally:
            TenantContext.clear_tenant()

        # A refused migration leaves the session's transaction state undefined,
        # so the follow-up migrations start on a freshly opened connection.
        connection.close()
        executor = MigrationExecutor(connection)
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        assert _seeded_rows(tenant.id, workspace.id) == 0

        executor.migrate([_SEED])
        executor.loader.build_graph()
        assert _seeded_rows(tenant.id, workspace.id) == 1
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)


def _rest_scenario() -> tuple[Tenant, User, Workspace]:
    """Tenant + admin user + one extended workspace with a seeded catalog."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"T-{suffix}", slug=f"val-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"val-{suffix}", email=f"val-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Validates WS", preset={"name": "extended"}
        )
        # Link validation is always-on: an unprovisioned workspace has an empty
        # link-type catalog and rejects every trace link.
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _artifact(
    tenant: Tenant, workspace: Workspace, artifact_type: str
) -> Artifact:
    set_request_tenant(tenant.id)
    try:
        return Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type=artifact_type
        )
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_rest_create_accepts_a_testcase_to_need_validation() -> None:
    tenant, user, workspace = _rest_scenario()
    testcase = _artifact(tenant, workspace, "TestCase")
    need = _artifact(tenant, workspace, "StakeholderNeed")

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")

    response = client.post(
        "/api/v1/trace-links/",
        {
            "source_id": str(testcase.id),
            "target_id": str(need.id),
            "link_type": _KEY,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["link_type"] == _KEY
