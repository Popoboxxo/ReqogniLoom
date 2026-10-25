"""Backfill ``backend_options``/``backend_secrets_encrypted`` from the legacy
flat columns (Plan A T-A0b-3, #1316).

Expand step: the legacy columns stay authoritative for old code until the
contract migration (T-A0b-6) drops them, so this migration only copies.

Decryption is **strict** (QR-S13): a non-empty ciphertext that the current key
cannot decrypt aborts the migration instead of silently dropping a configured
API key. An empty ciphertext is "not configured" and is skipped.
"""
import json

from django.db import migrations

#: Legacy column -> backend_options field, per backend.
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


def _decrypt_or_empty(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    from persistence.encryption import decrypt_secret

    # Deliberately not wrapped: InvalidToken must abort the migration.
    return decrypt_secret(ciphertext)


def forwards(apps, schema_editor):
    from persistence.encryption import encrypt_secret

    SystemMemorySettings = apps.get_model("memory", "SystemMemorySettings")
    row = SystemMemorySettings.objects.first()
    if row is None:
        return

    options: dict[str, dict] = {}
    for backend, mapping in _OPTION_FIELDS.items():
        values = {
            target: getattr(row, source)
            for source, target in mapping.items()
            if getattr(row, source) is not None
        }
        if values:
            options[backend] = values

    secrets: dict[str, dict] = {}
    for source, (backend, field) in _SECRET_FIELDS.items():
        plaintext = _decrypt_or_empty(getattr(row, source) or "")
        if plaintext:
            secrets.setdefault(backend, {})[field] = plaintext

    updates = {}
    if options:
        updates["backend_options"] = options
    if secrets:
        updates["backend_secrets_encrypted"] = encrypt_secret(
            json.dumps(secrets, sort_keys=True, separators=(",", ":"))
        )
    if updates:
        SystemMemorySettings.objects.filter(pk=row.pk).update(**updates)


def backwards(apps, schema_editor):
    from persistence.encryption import encrypt_secret

    SystemMemorySettings = apps.get_model("memory", "SystemMemorySettings")
    row = SystemMemorySettings.objects.first()
    if row is None:
        return

    options = row.backend_options or {}
    updates = {}
    for backend, mapping in _OPTION_FIELDS.items():
        for source, target in mapping.items():
            value = (options.get(backend) or {}).get(target)
            if value is not None:
                updates[source] = value

    try:
        secrets = json.loads(row.backend_secrets_encrypted or "{}")
    except (TypeError, ValueError):
        secrets = {}
    for source, (backend, field) in _SECRET_FIELDS.items():
        value = (secrets.get(backend) or {}).get(field)
        if value:
            updates[source] = encrypt_secret(value)

    if updates:
        SystemMemorySettings.objects.filter(pk=row.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("memory", "0010_systemmemorysettings_backend_options"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
