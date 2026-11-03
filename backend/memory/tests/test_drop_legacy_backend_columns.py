"""``memory/0012`` drops the legacy flat backend columns (Plan A T-A0b-6).

The contract migration must be safe in both directions:

* forward removes ``honcho_*``/``qdrant_*`` and leaves the data in
  ``backend_options``/``backend_secrets_encrypted`` untouched;
* reverse recreates the columns (Django's ``RemoveField`` reverse restores the
  historical definition) and copies the maps back, so a code revert reads the
  same configuration it wrote before;
* a ciphertext the current key cannot decrypt aborts the rollback instead of
  silently dropping a configured API key (QR-S13, same rule as ``0011``).

The probe runs the real ``MigrationExecutor`` against the test database and
addresses migrations by *name*, so appending a migration cannot retarget it.
"""
from __future__ import annotations

import json

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from memory.models import SYSTEM_MEMORY_SETTINGS_ID
from persistence.encryption import decrypt_secret, encrypt_secret

PRE_TARGET = ("memory", "0011_backfill_backend_options")
TARGET = ("memory", "0012_drop_legacy_backend_columns")

TABLE = "mem_system_memory_settings"

LEGACY_COLUMNS = {
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
}

OPTIONS = {
    "honcho": {"base_url": "http://honcho:8000"},
    "qdrant": {
        "base_url": "http://qdrant:6333",
        "collection_prefix": "reqlo",
        "distance": "cosine",
        "timeout": 3.5,
        "hnsw_m": 16,
        "hnsw_ef_construct": 64,
        "prefer_grpc": True,
    },
}
SECRETS = {"honcho": {"api_key": "sk-honcho"}, "qdrant": {"api_key": "sk-qdrant"}}


def _columns() -> set[str]:
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, TABLE)
        }


def _migrate(target) -> MigrationExecutor:
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    executor.loader.build_graph()
    return executor


@pytest.mark.django_db(transaction=True)
class TestLegacyColumnDropRoundtrip:
    def _seed_at_pre_target(self) -> None:
        executor = _migrate(PRE_TARGET)
        Historical = executor.loader.project_state(PRE_TARGET).apps.get_model(
            "memory", "SystemMemorySettings"
        )
        Historical.objects.all().delete()
        Historical.objects.create(
            pk=SYSTEM_MEMORY_SETTINGS_ID,
            backend_options=OPTIONS,
            backend_secrets_encrypted=encrypt_secret(
                json.dumps(SECRETS, sort_keys=True)
            ),
        )

    def test_forward_drops_the_columns_and_reverse_restores_the_values(self) -> None:
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            self._seed_at_pre_target()
            assert LEGACY_COLUMNS <= _columns()

            executor = _migrate(TARGET)
            assert LEGACY_COLUMNS.isdisjoint(_columns())
            dropped = executor.loader.project_state(TARGET).apps.get_model(
                "memory", "SystemMemorySettings"
            )
            row = dropped.objects.get(pk=SYSTEM_MEMORY_SETTINGS_ID)
            assert row.backend_options == OPTIONS
            assert json.loads(decrypt_secret(row.backend_secrets_encrypted)) == SECRETS

            _migrate(PRE_TARGET)
            assert LEGACY_COLUMNS <= _columns()
            restored = (
                MigrationExecutor(connection)
                .loader.project_state(PRE_TARGET)
                .apps.get_model("memory", "SystemMemorySettings")
                .objects.get(pk=SYSTEM_MEMORY_SETTINGS_ID)
            )
            assert restored.honcho_base_url == "http://honcho:8000"
            assert restored.qdrant_base_url == "http://qdrant:6333"
            assert restored.qdrant_collection_prefix == "reqlo"
            assert restored.qdrant_distance == "cosine"
            assert restored.qdrant_timeout == 3.5
            assert restored.qdrant_hnsw_m == 16
            assert restored.qdrant_hnsw_ef_construct == 64
            assert restored.qdrant_prefer_grpc is True
            assert decrypt_secret(restored.honcho_api_key_encrypted) == "sk-honcho"
            assert decrypt_secret(restored.qdrant_api_key_encrypted) == "sk-qdrant"
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_undecryptable_secret_aborts_the_rollback(self) -> None:
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            self._seed_at_pre_target()
            _migrate(TARGET)

            Current = (
                MigrationExecutor(connection)
                .loader.project_state(TARGET)
                .apps.get_model("memory", "SystemMemorySettings")
            )
            Current.objects.filter(pk=SYSTEM_MEMORY_SETTINGS_ID).update(
                backend_secrets_encrypted="gAAAA-not-a-real-token"
            )

            with pytest.raises(Exception):
                _migrate(PRE_TARGET)

            # The failed reverse rolled back; the contract state is intact.
            assert LEGACY_COLUMNS.isdisjoint(_columns())
        finally:
            MigrationExecutor(connection).migrate(latest)
