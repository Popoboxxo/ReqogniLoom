"""G2.2 (#1400): index the requirement list query.

The list filters by ``workspace`` and orders by ``(created_at, id)``. A plain
``AddIndex`` would take a write lock on ``pl_requirement`` for the duration of
the build, so the index is created (and reversed) CONCURRENTLY.
"""
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("persistence", "0119_embedding_model_columns"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="requirement",
            index=models.Index(
                fields=["workspace", "created_at", "id"],
                name="idx_req_ws_created",
            ),
        ),
    ]
