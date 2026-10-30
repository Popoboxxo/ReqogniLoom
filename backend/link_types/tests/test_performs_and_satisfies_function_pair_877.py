"""#877 / Plan B B3-T3 — the ``performs`` seed + ``satisfies`` function pair.

Exercised through the real ``MigrationExecutor`` (names, never numbers) with a
real ``Workspace`` row created *before* the migration runs — a catalog addition
must reach an existing workspace, not only a freshly provisioned one. It pins
the seeded ``performs`` definition, the additive pair merge (order preserved,
customized rows untouched) and the reverse guard (abort while a ``performs``
link exists; the pair merge itself is a deliberate noop).
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from link_types.models import WorkspaceLinkTypeDefinition
from persistence.models import Artifact, Tenant, TraceLink, Workspace
from persistence.tenancy import TenantContext

_APP = "link_types"
_PRE_TARGET = (_APP, "0011_seed_validates_link_type")
_SEED = (_APP, "0012_seed_performs_and_satisfies_function_pair")
_KEY = "performs"
_SATISFIES = "satisfies"
_OLD_SATISFIES_PAIRS = [
    {"source_type": "Requirement", "target_type": "Goal"},
    {"source_type": "StakeholderNeed", "target_type": "Goal"},
]


def _pairs(definition: dict) -> list[tuple[str, str]]:
    return [
        (pair["source_type"], pair["target_type"])
        for pair in definition["allowed_pairs"]
    ]


@pytest.mark.django_db(transaction=True)
def test_migration_seeds_performs_and_merges_the_satisfies_pair() -> None:
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()
        historical = executor.loader.project_state([_PRE_TARGET]).apps
        TenantModel = historical.get_model("persistence", "Tenant")
        WorkspaceModel = historical.get_model("persistence", "Workspace")
        GlobalDefinition = historical.get_model(_APP, "GlobalLinkTypeDefinition")
        WorkspaceDefinition = historical.get_model(
            _APP, "WorkspaceLinkTypeDefinition"
        )

        tenant = TenantModel.objects.create(
            name="performs-877", slug=f"perf-mig-{uuid.uuid4().hex[:8]}"
        )
        workspace_row = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="pre-existing-ws"
        )
        other_ws = WorkspaceModel.objects.create(
            tenant_id=tenant.id, name="customized-ws"
        )

        # Pre-#877 state: both rows already exist with the shipped pairs.
        GlobalDefinition.objects.create(
            tenant_id=tenant.id,
            key=_SATISFIES,
            definition_json={"allowed_pairs": list(_OLD_SATISFIES_PAIRS)},
        )
        WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=workspace_row.id,
            key=_SATISFIES,
            definition_json={"allowed_pairs": list(_OLD_SATISFIES_PAIRS)},
            is_customized=False,
        )
        # A workspace that tailored ``satisfies`` is a decision, not a gap.
        customized = WorkspaceDefinition.objects.create(
            tenant_id=tenant.id,
            workspace_id=other_ws.id,
            key=_SATISFIES,
            definition_json={
                "allowed_pairs": [
                    {"source_type": "Requirement", "target_type": "Risk"}
                ]
            },
            is_customized=True,
        )

        assert not WorkspaceDefinition.objects.filter(
            tenant_id=tenant.id, key=_KEY
        ).exists()

        executor.migrate([_SEED])
        executor.loader.build_graph()
        seeded_apps = executor.loader.project_state([_SEED]).apps
        SeededWorkspaceDefinition = seeded_apps.get_model(
            _APP, "WorkspaceLinkTypeDefinition"
        )
        SeededGlobalDefinition = seeded_apps.get_model(
            _APP, "GlobalLinkTypeDefinition"
        )

        performs = SeededWorkspaceDefinition.objects.get(
            tenant_id=tenant.id, workspace_id=workspace_row.id, key=_KEY
        )
        assert performs.is_customized is False
        assert _pairs(performs.definition_json) == [
            ("ArchitectureElement", "ArchitectureElement:function")
        ]
        assert performs.definition_json["coverage_relevant"] is False
        assert performs.definition_json["impact_weight"] == 0.8
        assert performs.definition_json["label"]["de"]["downstream"] == "führt aus"
        assert SeededGlobalDefinition.objects.filter(
            tenant_id=tenant.id, key=_KEY
        ).exists()

        # Additive merge: the shipped pairs keep their order, the function pair
        # is appended exactly once.
        merged_workspace = SeededWorkspaceDefinition.objects.get(
            tenant_id=tenant.id, workspace_id=workspace_row.id, key=_SATISFIES
        )
        assert _pairs(merged_workspace.definition_json) == [
            ("Requirement", "Goal"),
            ("StakeholderNeed", "Goal"),
            ("Requirement", "ArchitectureElement:function"),
        ]
        merged_global = SeededGlobalDefinition.objects.get(
            tenant_id=tenant.id, key=_SATISFIES
        )
        assert _pairs(merged_global.definition_json) == _pairs(
            merged_workspace.definition_json
        )

        untouched = SeededWorkspaceDefinition.objects.get(pk=customized.pk)
        assert untouched.is_customized is True
        assert untouched.definition_json == {
            "allowed_pairs": [{"source_type": "Requirement", "target_type": "Risk"}]
        }
    finally:
        # Always restore the schema for every other test in the suite.
        executor = MigrationExecutor(connection)
        executor.migrate(latest_target)


@pytest.mark.django_db(transaction=True)
def test_reverse_refuses_to_orphan_a_performs_link() -> None:
    """Dropping the type would leave links on a key no catalog can resolve."""
    executor = MigrationExecutor(connection)
    latest_target = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([_PRE_TARGET])
        executor.loader.build_graph()

        tenant = Tenant.objects.create(
            name="performs-877-reverse", slug=f"perf-rev-{uuid.uuid4().hex[:8]}"
        )
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(tenant=tenant, name="reverse-ws")
            component = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
            )
            function = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
            )
            link = TraceLink.objects.create(
                tenant=tenant, source=component, target=function, link_type=_KEY
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


def _seeded_rows(tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> int:
    """Count this tenant's seeded ``performs`` rows in *workspace_id*."""
    return WorkspaceLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant_id, workspace_id=workspace_id, key=_KEY
    ).count()
