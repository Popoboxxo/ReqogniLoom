"""Issue #1564: rewrite legacy ``TestCase.steps`` into the typed shape.

The typed shape is ``{"id", "step_type", "text"}``; see
``application.test_steps``. Existing rows carry the legacy LLM pair
``{"step", "expected_result"}``. The same normaliser is used here and on every
read path, which is what makes this migration safe to re-run and keeps a
partially migrated database readable.

Deliberately irreversible: the legacy pair is lossy (a ``when``/``then`` pair
cannot be folded back into ``{step, expected_result}`` without guessing), and a
reverse would rewrite content nobody asked to change.
"""
from __future__ import annotations

from django.db import migrations

from application.base import ValidationError
from application.test_steps import normalize_steps

_BATCH_SIZE = 500


def _lift_row_security(schema_editor) -> None:
    """Fail loudly instead of silently migrating zero rows under RLS.

    ``pl_test_case`` is tenant-scoped, and migrations set no tenant GUC. With
    ``FORCE ROW LEVEL SECURITY`` an unguarded loop would walk an empty result
    set and report success. ``row_security = off`` turns that into an error for
    a non-bypassing role and is a no-op for a superuser/BYPASSRLS connection.
    Same guard as ``icd/0011_backfill_current_content``.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def forwards(apps, schema_editor) -> None:
    _lift_row_security(schema_editor)
    TestCase = apps.get_model("persistence", "TestCase")

    for test_case in TestCase.objects.all().iterator(chunk_size=_BATCH_SIZE):
        raw = test_case.steps or []
        try:
            normalized = normalize_steps(raw, testcase_id=test_case.id)
        except ValidationError:
            # Unknown shape: never guess. The dry-run command lists these rows
            # by id so a human can fix them; the migration leaves them as-is.
            continue
        if normalized == raw:
            continue
        test_case.steps = normalized
        test_case.save(update_fields=["steps"])


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0143_requirement_released_tier_key"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
