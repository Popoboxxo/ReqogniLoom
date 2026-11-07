"""P1 Task 1.2: the ``Artifact.sort_key`` migration and its backfill.

Runs the real ``MigrationExecutor`` against the test database, addressing
migrations by name so appending a migration cannot retarget the probe.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

PRE_TARGET = ("persistence", "0131_interview_session_orphan_cleanup")
TARGET = ("persistence", "0132_artifact_sort_key")

TABLE = "pl_artifact"
COLUMN = "sort_key"


def _columns() -> set[str]:
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, TABLE)
        }


def _migrate(target) -> MigrationExecutor:
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    executor.loader.build_graph()
    return executor


@pytest.mark.django_db(transaction=True)
def test_sort_key_migration_forward_backward_and_idempotence() -> None:
    try:
        pre = _migrate(PRE_TARGET)
        assert COLUMN not in _columns()

        apps = pre.loader.project_state(PRE_TARGET).apps
        Tenant = apps.get_model("persistence", "Tenant")
        Workspace = apps.get_model("persistence", "Workspace")
        Artifact = apps.get_model("persistence", "Artifact")

        tenant = Tenant.objects.create(name="sk-tenant", slug="sk-tenant")
        workspace = Workspace.objects.create(tenant=tenant, name="sk-ws")
        parent = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )

        # Three children, created in a scrambled order and then given distinct
        # created_at timestamps C0 < C1 < C2.
        timestamps = [timezone.now() + timedelta(seconds=i) for i in range(3)]
        children: dict[int, object] = {}
        for index in (2, 0, 1):
            children[index] = Artifact.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type="Requirement",
                parent=parent,
            )
        for index, child in children.items():
            Artifact.objects.filter(pk=child.pk).update(created_at=timestamps[index])

        # A non-ordered type must stay NULL.
        adr = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Adr"
        )

        post = _migrate(TARGET)
        assert COLUMN in _columns()

        post_artifact = post.loader.project_state(TARGET).apps.get_model(
            "persistence", "Artifact"
        )
        rows = list(
            post_artifact.objects.filter(parent_id=parent.pk).order_by("sort_key")
        )
        expected = sorted(
            timestamps,
        )
        assert len(rows) == 3
        assert all(row.sort_key is not None for row in rows)
        assert [row.created_at for row in rows] == expected
        keys = [row.sort_key for row in rows]
        assert keys == sorted(keys)
        assert len(keys) == len(set(keys))
        assert post_artifact.objects.get(pk=adr.pk).sort_key is None

        # Re-applying the migration must not change anything.
        post = _migrate(TARGET)
        post_artifact = post.loader.project_state(TARGET).apps.get_model(
            "persistence", "Artifact"
        )
        rerun = list(
            post_artifact.objects.filter(parent_id=parent.pk).order_by("sort_key")
        )
        assert [row.sort_key for row in rerun] == keys

        # Reverse removes the column again.
        _migrate(PRE_TARGET)
        assert COLUMN not in _columns()
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
