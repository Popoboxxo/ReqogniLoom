"""Add ``TestCase.origin`` / ``reviewed`` / ``scenario_kind`` (cluster 5).

Covers #424 (origin + reviewed) and #402's off-nominal category
(``scenario_kind``). Schema-only: three ``AddField`` plus one ``AlterField``,
deliberately **no** ``RunPython`` (spec section 4.2).

The two-step ``origin`` handling is the standard Django idiom for "fill the
existing rows with a sentinel, then default new rows to the real value":

* ``AddField(origin, default="unknown", preserve_default=False)`` emits the
  ``ADD COLUMN ... DEFAULT 'unknown'`` DDL. That column default fills every
  pre-existing row; ``preserve_default=False`` drops it from the migration
  state again so it never leaks into later inserts.
* ``AlterField(origin, default="manual")`` restores the model default.

Pre-existing rows therefore become ``origin="unknown"`` - never claiming they
were manual or reviewed, which is exactly the false-green #424 closes - while
new rows default to ``manual``. ``scenario_kind`` and ``reviewed`` get their
model defaults directly through ``AddField``.

RLS: pure DDL. ``AddField``/``AlterField`` are not filtered by the FORCE ROW
LEVEL SECURITY policies on ``pl_testcase`` (those only apply to DML), and there
is no data statement that could silently match zero rows. That is why this
migration intentionally carries no per-tenant arming.

Reverse: Django's default (three ``RemoveField`` plus a default revert for the
``AlterField``). Unapplying drops the columns and their data, the inherent,
documented semantics of ``AddField``.
"""
from __future__ import annotations

from django.db import migrations, models

from persistence.models import ScenarioKind, TestCaseOrigin


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0098_requirement_rationale_requirement_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="testcase",
            name="origin",
            field=models.CharField(
                max_length=20,
                choices=TestCaseOrigin.choices,
                default="unknown",
                help_text=(
                    "#424: provenance of the test-case content. 'manual' "
                    "(default) and 'ai_generated' are client-writable; "
                    "'unknown' is system/migration-only and grandfathers "
                    "pre-#424 rows."
                ),
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="testcase",
            name="origin",
            field=models.CharField(
                max_length=20,
                choices=TestCaseOrigin.choices,
                default="manual",
                help_text=(
                    "#424: provenance of the test-case content. 'manual' "
                    "(default) and 'ai_generated' are client-writable; "
                    "'unknown' is system/migration-only and grandfathers "
                    "pre-#424 rows."
                ),
            ),
        ),
        migrations.AddField(
            model_name="testcase",
            name="scenario_kind",
            field=models.CharField(
                max_length=20,
                choices=ScenarioKind.choices,
                default="nominal",
                help_text=(
                    "#402: 'nominal' (happy path, default) or 'off_nominal' "
                    "(negative/boundary case) categorisation."
                ),
            ),
        ),
        migrations.AddField(
            model_name="testcase",
            name="reviewed",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "#424: in-content human approval. Only meaningful together "
                    "with 'origin' - an 'ai_generated', unreviewed test case "
                    "does not count as verification evidence. Changed via "
                    "TestService.mark_reviewed."
                ),
            ),
        ),
    ]
