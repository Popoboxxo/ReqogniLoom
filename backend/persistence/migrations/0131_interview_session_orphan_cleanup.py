"""C5 / #1412 — null orphan InterviewSession.artifact references.

The measured QS corpus contained interview sessions whose ``artifact_id``
pointed at a row that no longer exists (4 of 32 at the time of the report).
The FK is enforced today, so this is a legacy-data cleanup: detach the orphan
rows instead of deleting the session (the transcript is still valuable).
"""
from __future__ import annotations

from django.db import migrations


def _null_orphan_artifacts(apps, schema_editor):
    schema_editor.execute(
        """
        UPDATE pl_interview_session s
        SET artifact_id = NULL
        WHERE s.artifact_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM pl_artifact a WHERE a.id = s.artifact_id
          )
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0130_milestone_rls_policy"),
    ]

    operations = [
        migrations.RunPython(_null_orphan_artifacts, migrations.RunPython.noop),
    ]
