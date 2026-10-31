"""The Issue/Risk vocabulary are regular catalog built-ins (#1374).

Plan F, F1.1-T2 (``docs/plans/2026-10-21-plan-f-dokumente-baselines.md``),
decision ENT-F1 = b: ``blocks``, ``resolves`` and ``threatens`` stop being
aliases of ``references`` and become own built-in link types with pinned
endpoint pairs.

Vocabulary mapping (also documented in ``link_types/builtin.py``):

  - ``blocked-by``   = the upstream label of ``blocks`` — no own type
  - ``mitigated-by`` = the upstream label of ``mitigates`` — no own type
  - ``caused-by`` / ``related-to`` → ``references`` — no own type

Two groups of tests live here:

* pair validation against a provisioned workspace (the catalog contract), and
* the seed migration ``0013_seed_issue_risk_link_types``, exercised through the
  real ``MigrationExecutor`` with migration *names* (never bare numbers) and a
  real ``Workspace`` row created *before* the migration runs — a catalog
  addition must reach an existing workspace, not only a freshly provisioned
  one (KA-G-10).

``BUILTIN_LINK_TYPES`` already carries the three keys, so a freshly provisioned
workspace is covered by the first group; the migration group pins the
backfill for pre-existing workspaces and the tenant-global rows.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from link_types.catalog import validate_link_pair
from link_types.models import (
    GlobalLinkTypeDefinition,
    WorkspaceLinkTypeDefinition,
)
from persistence.errors import ValidationError
from persistence.models import Artifact, Tenant, TraceLink, Workspace
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

_LINK_TYPES_APP = "link_types"
_PRE_TARGET = (_LINK_TYPES_APP, "0012_seed_performs_and_satisfies_function_pair")
_SEED = (_LINK_TYPES_APP, "0013_seed_issue_risk_link_types")
_NEW_KEYS = ("blocks", "resolves", "threatens")
_EXPECTED_PAIRS = {
    "blocks": [("Issue", "*")],
    "resolves": [("*", "Issue")],
    "threatens": [("Risk", "*")],
}
_EXPECTED_WEIGHTS = {"blocks": 0.5, "resolves": 0.3, "threatens": 0.5}


@pytest.fixture
def env(db):
    """Tenant + provisioned workspace (real rows; ``make_workspace`` seeds the catalog).

    The tenant context stays active for the test body: ``validate_link_pair``
    reads the tenant-scoped ``WorkspaceLinkTypeDefinition`` rows.
    """
    tenant = Tenant.objects.create(name="issue-risk-linktypes", slug="issue-risk-linktypes")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = make_workspace(tenant, name="issue-risk-linktypes-ws")
        yield {"tenant": tenant, "workspace": workspace}
    finally:
        TenantContext.clear_tenant()


def test_blocks_allows_issue_to_anything(env):
    """``blocks`` runs Issue -> ``*``: an Issue blocks anything, not the reverse."""
    validate_link_pair(
        env["workspace"].id, "blocks", "Issue", "Requirement", manual=True
    )


def test_blocks_rejects_the_reversed_pair(env):
    with pytest.raises(ValidationError, match="Allowed:"):
        validate_link_pair(
            env["workspace"].id, "blocks", "Requirement", "Issue", manual=True
        )


def test_resolves_allows_anything_to_issue(env):
    """``resolves`` runs ``*`` -> Issue: the artifact is resolved *by* an Issue."""
    validate_link_pair(
        env["workspace"].id, "resolves", "Requirement", "Issue", manual=True
    )


def test_resolves_rejects_the_reversed_pair(env):
    with pytest.raises(ValidationError, match="Allowed:"):
        validate_link_pair(
            env["workspace"].id, "resolves", "Issue", "Requirement", manual=True
        )


def test_threatens_allows_risk_to_anything(env):
    """``threatens`` runs Risk -> ``*``, mirroring ``mitigates``' direction."""
    validate_link_pair(
        env["workspace"].id, "threatens", "Risk", "Requirement", manual=True
    )


def test_threatens_rejects_the_reversed_pair(env):
    with pytest.raises(ValidationError, match="Allowed:"):
        validate_link_pair(
            env["workspace"].id, "threatens", "Requirement", "Risk", manual=True
        )


# ---------------------------------------------------------------------------
# Seed migration 0013_seed_issue_risk_link_types
# ---------------------------------------------------------------------------


def _pairs(definition: dict) -> list[tuple[str, str]]:
    return [
        (pair["source_type"], pair["target_type"])
        for pair in definition["allowed_pairs"]
    ]


def _seeded_rows(tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> int:
    """Count this tenant's seeded Issue/Risk rows in *workspace_id*."""
    return WorkspaceLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant_id, workspace_id=workspace_id, key__in=_NEW_KEYS
    ).count()


@pytest.mark.django_db(transaction=True)
def test_migration_seeds_issue_risk_link_types_on_existing_workspace() -> None:
    """0012 -> 0013 adds three rows per pre-existing workspace, customized stays."""
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        historical = executor.loader.project_state([_PRE_TARGET]).apps
        TenantModel = historical.get_model("persistence", "Tenant")
        WorkspaceModel = historical.get_model("persistence", "Workspace")
        GlobalDefinition = historical.get_model(_LINK_TYPES_APP, "GlobalLinkTypeDefinition")
        WorkspaceDefinition = historical.get_model(
            _LINK_TYPES_APP, "WorkspaceLinkTypeDefinition"
        )

        tenant = TenantModel.objects.create(
            name="issue-risk-1374", slug=f"issue-risk-{uuid.uuid4().hex[:8]}"
        )
        workspace_row = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="pre-existing-ws"
        )
        customized_ws = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="customized-ws"
        )

        # A workspace that already tailored `blocks` made a decision; the seed
        # must neither overwrite it nor add a second row for that key.
        customized = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=customized_ws.id,
            key="blocks",
            definition_json={"impact_weight": 0.42},
            is_customized=True,
        )

        # Pre-#1374 state: only the customized `blocks` row is present, and the
        # tenant has no global template for any of the three keys.
        assert [
            row.pk
            for row in WorkspaceDefinition.objects.filter(
                tenant_id=tenant.id, key__in=_NEW_KEYS
            )
        ] == [customized.pk]
        assert not GlobalDefinition.objects.filter(
            tenant_id=tenant.id, key__in=_NEW_KEYS
        ).exists()

        executor.migrate([_SEED])
        executor.loader.build_graph()
        seeded_apps = executor.loader.project_state([_SEED]).apps
        SeededWorkspaceDefinition = seeded_apps.get_model(
            _LINK_TYPES_APP, "WorkspaceLinkTypeDefinition"
        )
        SeededGlobalDefinition = seeded_apps.get_model(
            _LINK_TYPES_APP, "GlobalLinkTypeDefinition"
        )

        seeded = {
            key: SeededWorkspaceDefinition.objects.get(
                tenant_id=tenant.id, workspace_id=workspace_row.id, key=key
            )
            for key in _NEW_KEYS
        }
        for key, row in seeded.items():
            assert row.is_customized is False
            assert _pairs(row.definition_json) == _EXPECTED_PAIRS[key]
            assert row.definition_json["impact_weight"] == _EXPECTED_WEIGHTS[key]
            assert row.definition_json["coverage_relevant"] is False
            assert row.definition_json["suspect_rule"] == "none"
            assert row.source_global_id is not None

            global_row = SeededGlobalDefinition.objects.get(
                tenant_id=tenant.id, key=key
            )
            assert _pairs(global_row.definition_json) == _EXPECTED_PAIRS[key]

        assert (
            seeded["blocks"].definition_json["label"]["de"]["downstream"]
            == "blockiert"
        )
        assert (
            seeded["resolves"].definition_json["label"]["en"]["upstream"]
            == "is resolved by"
        )
        assert (
            seeded["threatens"].definition_json["label"]["de"]["upstream"]
            == "wird bedroht durch"
        )

        # The customized row is untouched, and no second `blocks` row was added.
        untouched = SeededWorkspaceDefinition.objects.get(pk=customized.pk)
        assert untouched.is_customized is True
        assert untouched.definition_json == {"impact_weight": 0.42}
        assert (
            SeededWorkspaceDefinition.objects.filter(
                tenant_id=tenant.id, workspace_id=customized_ws.id, key="blocks"
            ).count()
            == 1
        )
        # ... while the two keys it did not customize were still seeded there.
        assert (
            SeededWorkspaceDefinition.objects.filter(
                tenant_id=tenant.id,
                workspace_id=customized_ws.id,
                key__in=("resolves", "threatens"),
            ).count()
            == 2
        )
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)


@pytest.mark.django_db(transaction=True)
def test_reverse_refuses_to_orphan_an_issue_risk_link_then_cleans_up() -> None:
    """Dropping a type would leave links on a key no catalog can resolve."""
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()

        tenant = Tenant.objects.create(
            name="issue-risk-1374-reverse",
            slug=f"issue-risk-rev-{uuid.uuid4().hex[:8]}",
        )
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(tenant=tenant, name="reverse-ws")
            customized = WorkspaceLinkTypeDefinition.unscoped.create(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                key="resolves",
                definition_json={"impact_weight": 0.42},
                is_customized=True,
            )
            issue = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Issue"
            )
            requirement = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            )
            link = TraceLink.objects.create(
                tenant=tenant, source=issue, target=requirement, link_type="blocks"
            )

            executor.migrate([_SEED])
            executor.loader.build_graph()
            # The pre-existing customized `resolves` row kept its slot, so the
            # seed only added the two missing keys next to it.
            assert _seeded_rows(tenant.id, workspace.id) == 3

            with pytest.raises(RuntimeError, match="1 TraceLink row") as exc:
                executor.migrate([_PRE_TARGET])
            assert "blocks" in str(exc.value)
            # ... and the refused reverse left the catalog untouched.
            assert _seeded_rows(tenant.id, workspace.id) == 3

            link.delete()
        finally:
            TenantContext.clear_tenant()

        # A refused migration leaves the session's transaction state undefined,
        # so the follow-up migrations start on a freshly opened connection.
        connection.close()
        executor = MigrationExecutor(connection)
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        assert _seeded_rows(tenant.id, workspace.id) == 1
        assert WorkspaceLinkTypeDefinition.unscoped.filter(
            pk=customized.pk, is_customized=True
        ).exists()
        assert not GlobalLinkTypeDefinition.unscoped.filter(
            tenant_id=tenant.id, key__in=_NEW_KEYS
        ).exists()

        executor.migrate([_SEED])
        executor.loader.build_graph()
        assert _seeded_rows(tenant.id, workspace.id) == 3
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)
