# Issue #276 — remove the machine-seeded LlmSettings rows.
#
# ``0026_add_llm_settings`` used to create a ``provider="mock"`` row for every
# tenant that existed when it was applied (that step is gone now, see the
# header comment there). ``llm_adapter.providers._apply_db_settings`` gives an
# existing row unconditional precedence over the environment, so on every
# affected deployment the seeded row silently overrode ``LLM_PROVIDER`` from
# ``.env``: AI features returned mock placeholders and nothing ever errored.
#
# This migration deletes those leftovers so the environment becomes the
# fallback again. It deletes ONLY rows that are byte-for-byte the old seed
# default — provider "mock" with no base_url, no api_key, no model_name, an
# unbumped optimistic-concurrency counter and no created_by/modified_by
# attribution. Any signal that a human touched the row keeps it: an admin who
# deliberately selected "mock" and set, say, a base_url must not lose that
# configuration. The one case that stays ambiguous is an admin who selected
# "mock" and changed nothing else — indistinguishable from the seed by
# construction. Such a row is dropped, and the tenant then follows
# ``LLM_PROVIDER``; that is the intended default behaviour and can be restored
# with a single PUT to /api/v1/llm-settings/.
#
# Operation order matters (mirrors 0037_encrypt_llm_api_key.py):
#   1. Temporarily lift FORCE ROW LEVEL SECURITY on ``pl_llm_settings`` — the
#      FORCE flag binds even the table owner, so a RunPython step with no
#      active ``app.current_tenant`` session variable would match ZERO rows
#      and silently no-op instead of failing.
#   2. Delete the pristine rows.
#   3. Restore FORCE ROW LEVEL SECURITY.

from django.db import migrations

_TABLE = "pl_llm_settings"

_LIFT_FORCE_RLS_SQL = f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;"
_RESTORE_FORCE_RLS_SQL = f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;"

# The exact shape 0026's ``_seed_defaults`` produced. Frozen here rather than
# derived from the model so this migration's behaviour does not change if the
# model's defaults ever do (same rationale as 0027/0037).
SEEDED_DEFAULT_FILTER = {
    "provider": "mock",
    "base_url": "",
    "api_key_encrypted": "",
    "model_name": "",
    "version": 1,
    "created_by_id": None,
    "modified_by_id": None,
}


def remove_seeded_default_rows(apps, schema_editor):
    """Delete LlmSettings rows still identical to 0026's seed default.

    Idempotent: re-running it on an already-cleaned database matches nothing.
    """
    LlmSettings = apps.get_model("persistence", "LlmSettings")
    LlmSettings.objects.filter(**SEEDED_DEFAULT_FILTER).delete()


def _noop_reverse(apps, schema_editor):
    """Reverse: intentionally does nothing.

    Re-seeding would recreate exactly the rows this migration exists to
    remove, so rolling back leaves the table as-is. Any tenant without a row
    simply falls back to the environment configuration.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0055_requirement_workspace_uid_constraint"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_LIFT_FORCE_RLS_SQL, reverse_sql=_RESTORE_FORCE_RLS_SQL
        ),
        migrations.RunPython(remove_seeded_default_rows, _noop_reverse),
        migrations.RunSQL(
            sql=_RESTORE_FORCE_RLS_SQL, reverse_sql=_LIFT_FORCE_RLS_SQL
        ),
    ]
