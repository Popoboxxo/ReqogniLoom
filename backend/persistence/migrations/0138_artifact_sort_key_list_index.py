"""P1: index the workspace-scoped requirement list ordered by ``sort_key``.

The requirement list reads ``pl_requirement`` filtered by workspace and orders
by ``pl_artifact.sort_key COLLATE "C" NULLS LAST, created_at, id``, joining on
the unique ``pl_requirement.artifact_id``. Without an index on the ordering key
the planner materialises the whole join and sorts it (Seq Scan on
``pl_artifact`` + Sort) — the old ``idx_req_ws_created`` (workspace, created_at,
id) cannot serve an order whose first key lives in the other table.

``(sort_key, id)`` is the only shape that can serve it: PostgreSQL walks the
index in sort_key order, nested-loops into ``pl_requirement`` by its unique
``artifact_id`` and stops at LIMIT (an ``Incremental Sort`` only re-orders ties
inside one sort key). A ``(workspace_id, sort_key, id)`` index does *not* help:
the workspace predicate is on ``pl_requirement``, so the planner can neither
seek nor walk this artifact index in workspace-scoped sort_key order and falls
back to the same full sort. The ordered walk is only chosen when the queried
workspace holds a large share of the artifact table; with many equally sized
workspaces the planner may keep hashing one workspace's rows and sorting them,
which is also correct (and cheap, because it is bounded by that workspace).

Created CONCURRENTLY: a plain ``AddIndex`` would lock writes on ``pl_artifact``
for the whole build.
"""
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("persistence", "0137_tracelink_membership_sort_key"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="artifact",
            index=models.Index(fields=["sort_key", "id"], name="idx_artifact_sort_id"),
        ),
    ]
