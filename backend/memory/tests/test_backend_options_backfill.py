"""``memory/0011`` backfills the legacy columns into the backend maps.

Plan A T-A0b-3. Exercised against the historical model registry the RunPython
functions really receive (built via ``MigrationExecutor``), so the test does not
depend on the live model's custom ``save()``/properties.

Two properties matter: a round trip preserves the configuration, and a
ciphertext the current key cannot decrypt aborts the migration instead of
silently dropping a configured API key (QR-S13).

Since ``0012_drop_legacy_backend_columns`` the live schema no longer has the
legacy columns, so each test first migrates the database DOWN to ``0011`` --
otherwise the historical model's INSERT would reference dropped columns.
"""
from importlib import import_module
import json

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from memory.models import SYSTEM_MEMORY_SETTINGS_ID
from persistence.encryption import decrypt_secret, encrypt_secret

MIGRATION = ("memory", "0011_backfill_backend_options")


def _module():
    # Module name starts with a digit, so import by string.
    return import_module("memory.migrations.0011_backfill_backend_options")


@pytest.fixture
def at_0011():
    """Migrate the test DB to ``0011`` for the duration of one test."""
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
    executor = MigrationExecutor(connection)
    executor.migrate([MIGRATION])
    executor.loader.build_graph()
    try:
        yield executor.loader.project_state(MIGRATION).apps
    finally:
        MigrationExecutor(connection).migrate(latest)


def _create_legacy_row(SystemMemorySettings):
    SystemMemorySettings.objects.all().delete()
    return SystemMemorySettings.objects.create(
        pk=SYSTEM_MEMORY_SETTINGS_ID,
        honcho_base_url="http://honcho:8000",
        honcho_api_key_encrypted=encrypt_secret("sk-honcho"),
        qdrant_base_url="http://qdrant:6333",
        qdrant_collection_prefix="reqlo",
        qdrant_distance="cosine",
        qdrant_timeout=3.5,
        qdrant_hnsw_m=16,
        qdrant_hnsw_ef_construct=64,
        qdrant_prefer_grpc=True,
        qdrant_api_key_encrypted=encrypt_secret("sk-qdrant"),
    )


@pytest.mark.django_db(transaction=True)
def test_forward_then_backward_preserves_the_configuration(at_0011):
    SystemMemorySettings = at_0011.get_model("memory", "SystemMemorySettings")
    _create_legacy_row(SystemMemorySettings)

    _module().forwards(at_0011, None)

    row = SystemMemorySettings.objects.get(pk=SYSTEM_MEMORY_SETTINGS_ID)
    assert row.backend_options["honcho"]["base_url"] == "http://honcho:8000"
    assert row.backend_options["qdrant"] == {
        "base_url": "http://qdrant:6333",
        "collection_prefix": "reqlo",
        "distance": "cosine",
        "timeout": 3.5,
        "hnsw_m": 16,
        "hnsw_ef_construct": 64,
        "prefer_grpc": True,
    }
    secrets = json.loads(decrypt_secret(row.backend_secrets_encrypted))
    assert secrets == {
        "honcho": {"api_key": "sk-honcho"},
        "qdrant": {"api_key": "sk-qdrant"},
    }

    _module().backwards(at_0011, None)

    row.refresh_from_db()
    assert row.honcho_base_url == "http://honcho:8000"
    assert row.qdrant_base_url == "http://qdrant:6333"
    assert row.qdrant_prefer_grpc is True
    assert decrypt_secret(row.honcho_api_key_encrypted) == "sk-honcho"
    assert decrypt_secret(row.qdrant_api_key_encrypted) == "sk-qdrant"


@pytest.mark.django_db(transaction=True)
def test_undecryptable_legacy_secret_aborts_the_backfill(at_0011):
    SystemMemorySettings = at_0011.get_model("memory", "SystemMemorySettings")
    SystemMemorySettings.objects.all().delete()
    SystemMemorySettings.objects.create(
        pk=SYSTEM_MEMORY_SETTINGS_ID,
        honcho_base_url="http://honcho:8000",
        honcho_api_key_encrypted="gAAAA-not-a-real-token",
    )

    with pytest.raises(Exception):
        _module().forwards(at_0011, None)
