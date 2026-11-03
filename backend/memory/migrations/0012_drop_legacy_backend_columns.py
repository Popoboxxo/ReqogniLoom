"""Drop the legacy flat backend columns (Plan A T-A0b-6, contract).

Expand/contract finish: ``0010`` added ``backend_options``/
``backend_secrets_encrypted``, ``0011`` backfilled them from the legacy
columns and T-A0b-3 kept both sides in sync until this migration. The maps are
now the single store -- no code reads or writes the flat columns any more.

Reverse
-------
The reverse direction recreates the columns with their historical definitions
(``0003`` for the Honcho pair, ``0008`` for the Qdrant block) and copies the
values back out of the maps. This is what makes a code revert safe without a
hand-written repair: the old release reads the columns again.

The re-add is Django's own ``RemoveField`` reverse, not an explicit
``AddField``: the operation carries the historical field definition and
recreates the column with exactly the old ``null``/``default`` attributes.
``RunPython`` therefore sits FIRST in ``operations`` — reverse runs the list
backwards, so the columns exist again by the time ``restore_legacy_columns``
copies the data (a trailing ``RunPython`` would run against dropped columns).

Decryption is **strict** (same QR-S13 rule as ``0011``): a non-empty
``backend_secrets_encrypted`` that the current key cannot decrypt aborts the
rollback instead of silently dropping a configured API key. An empty blob is
"no secrets configured" and is skipped.

The table is deliberately NOT a ``TenantScopedModel`` (see the model
docstring), so none of this needs an RLS policy.
"""
import json

from django.db import migrations

#: Legacy column -> ``backend_options`` field, per backend.
_OPTION_FIELDS = {
    "honcho": {
        "honcho_base_url": "base_url",
    },
    "qdrant": {
        "qdrant_base_url": "base_url",
        "qdrant_collection_prefix": "collection_prefix",
        "qdrant_distance": "distance",
        "qdrant_timeout": "timeout",
        "qdrant_hnsw_m": "hnsw_m",
        "qdrant_hnsw_ef_construct": "hnsw_ef_construct",
        "qdrant_prefer_grpc": "prefer_grpc",
    },
}

#: Legacy ciphertext column -> (backend, secret field).
_SECRET_FIELDS = {
    "honcho_api_key_encrypted": ("honcho", "api_key"),
    "qdrant_api_key_encrypted": ("qdrant", "api_key"),
}

#: Columns dropped by the forward pass. Their historical definitions live in
#: the project state (0003/0008), so ``RemoveField`` re-adds them on reverse.
_LEGACY_FIELDS = (
    "honcho_base_url",
    "honcho_api_key_encrypted",
    "qdrant_base_url",
    "qdrant_collection_prefix",
    "qdrant_distance",
    "qdrant_timeout",
    "qdrant_hnsw_m",
    "qdrant_hnsw_ef_construct",
    "qdrant_prefer_grpc",
    "qdrant_api_key_encrypted",
)


def restore_legacy_columns(apps, schema_editor):
    """Copy the maps back into the recreated legacy columns (strict decrypt)."""
    from persistence.encryption import decrypt_secret, encrypt_secret

    SystemMemorySettings = apps.get_model("memory", "SystemMemorySettings")
    row = SystemMemorySettings.objects.first()
    if row is None:
        return

    options = row.backend_options or {}
    secrets = {}
    if row.backend_secrets_encrypted:
        # Deliberately not wrapped: InvalidToken must abort the rollback.
        secrets = json.loads(decrypt_secret(row.backend_secrets_encrypted))

    updates: dict[str, object] = {}
    for backend, mapping in _OPTION_FIELDS.items():
        backend_options = options.get(backend) or {}
        for legacy, option in mapping.items():
            value = backend_options.get(option)
            if value is not None:
                updates[legacy] = value

    for legacy, (backend, field) in _SECRET_FIELDS.items():
        value = (secrets.get(backend) or {}).get(field)
        if value:
            updates[legacy] = encrypt_secret(value)

    if updates:
        SystemMemorySettings.objects.filter(pk=row.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("memory", "0011_backfill_backend_options"),
    ]

    operations = [
        # Must stay first: on reverse the columns are recreated by the
        # RemoveField operations below (run backwards) before this restore
        # runs. See the module docstring.
        migrations.RunPython(migrations.RunPython.noop, restore_legacy_columns),
    ] + [
        migrations.RemoveField(model_name="systemmemorysettings", name=name)
        for name in _LEGACY_FIELDS
    ]
