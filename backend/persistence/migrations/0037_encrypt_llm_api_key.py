# REQ-081 — encrypt LlmSettings.api_key at rest.
#
# Operation order matters:
#   1. Temporarily lift FORCE ROW LEVEL SECURITY on ``pl_llm_settings`` so the
#      data migration (step 4) can iterate every tenant's row in one pass —
#      mirrors the "seed before FORCE RLS" ordering used by 0026_add_llm_settings
#      (COMP-PL-006's FORCE flag binds even the table owner, so without lifting
#      it a RunPython step with no active ``app.current_tenant`` session
#      variable would see zero rows).
#   2. Rename the ``api_key`` column to ``api_key_encrypted`` — the column now
#      holds ciphertext, not plaintext, and the name should say so.
#   3. Widen the column from CharField(512) to TextField: a Fernet token is
#      noticeably longer than the plaintext it wraps.
#   4. Encrypt every existing plaintext value in place. Idempotent: rows whose
#      value already carries the Fernet token prefix (``gAAAA``) are left
#      untouched, so re-running this migration after a partial failure never
#      double-encrypts.
#   5. Restore FORCE ROW LEVEL SECURITY.

from django.conf import settings
from django.db import migrations, models

from cryptography.fernet import Fernet

_TABLE = "pl_llm_settings"

# Fernet tokens always start with the base64 encoding of the fixed version
# byte (0x80), i.e. the literal prefix "gAAAA". Duplicated here (rather than
# imported from persistence.encryption) so this migration's behaviour is
# frozen in time and does not depend on that module's implementation changing
# later — the same rationale 0027_add_prompt_template.py uses for freezing
# its default prompt constants.
_ENCRYPTED_PREFIX = "gAAAA"

_LIFT_FORCE_RLS_SQL = f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;"
_RESTORE_FORCE_RLS_SQL = f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;"


def _fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def _encrypt_existing_keys(apps, schema_editor):
    """Encrypt every plaintext ``api_key_encrypted`` value in place."""
    LlmSettings = apps.get_model("persistence", "LlmSettings")
    fernet = _fernet()
    for row in LlmSettings.objects.all().iterator():
        value = row.api_key_encrypted
        if not value or value.startswith(_ENCRYPTED_PREFIX):
            continue
        row.api_key_encrypted = fernet.encrypt(value.encode("utf-8")).decode(
            "utf-8"
        )
        row.save(update_fields=["api_key_encrypted"])


def _decrypt_existing_keys(apps, schema_editor):
    """Reverse: decrypt back to plaintext (best-effort, for rollback)."""
    LlmSettings = apps.get_model("persistence", "LlmSettings")
    fernet = _fernet()
    for row in LlmSettings.objects.all().iterator():
        value = row.api_key_encrypted
        if not value or not value.startswith(_ENCRYPTED_PREFIX):
            continue
        row.api_key_encrypted = fernet.decrypt(value.encode("utf-8")).decode(
            "utf-8"
        )
        row.save(update_fields=["api_key_encrypted"])


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0036_workspace_language"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_LIFT_FORCE_RLS_SQL, reverse_sql=_RESTORE_FORCE_RLS_SQL
        ),
        migrations.RenameField(
            model_name="llmsettings",
            old_name="api_key",
            new_name="api_key_encrypted",
        ),
        migrations.AlterField(
            model_name="llmsettings",
            name="api_key_encrypted",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Encrypted provider API key (Fernet ciphertext, REQ-081). "
                    "Never returned via the REST API. Access via the "
                    "`api_key` property, not this field."
                ),
            ),
        ),
        migrations.RunPython(
            _encrypt_existing_keys, _decrypt_existing_keys
        ),
        migrations.RunSQL(
            sql=_RESTORE_FORCE_RLS_SQL, reverse_sql=_LIFT_FORCE_RLS_SQL
        ),
    ]
