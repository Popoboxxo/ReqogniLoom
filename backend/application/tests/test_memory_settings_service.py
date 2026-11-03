"""Regression tests for ``MemorySettingsService`` serialization (F8).

Plan A T-A0b-6 moved every per-backend value into
``backend_options``/``backend_secrets_encrypted``; the flat REST fields are
derived from those maps. ``_serialize`` therefore decrypts the secret blob to
answer ``*_api_key_is_set``, and must degrade to ``{}`` instead of raising when
``FIELD_ENCRYPTION_KEY`` was rotated (``decrypt_secret`` raises ``InvalidToken``
over ciphertext the current key cannot read). An admin ``GET`` must never 500
over that (the original F8 report).
"""
from __future__ import annotations

import json

import pytest

from application.memory_settings_service import MemorySettingsService
from memory.models import SystemMemorySettings
from persistence.encryption import encrypt_secret

#: A Fernet-shaped token (the ``gAAAA`` prefix is exactly what
#: ``decrypt_secret`` keys on) that is NOT decryptable with the test key.
_UNDECRYPTABLE_CIPHERTEXT = "gAAAA" + "not-a-valid-fernet-token"


def _secrets_blob(**secrets: str) -> str:
    return encrypt_secret(json.dumps({"honcho": secrets, "qdrant": secrets}))


def test_serialize_reports_api_key_set_from_backend_secrets() -> None:
    """``_is_set`` reflects the decrypted map, never the plaintext."""
    row = SystemMemorySettings(
        backend_secrets_encrypted=_secrets_blob(api_key="sk-stored"),
    )

    data = MemorySettingsService._serialize(row)

    assert data["qdrant_api_key_is_set"] is True
    assert data["honcho_api_key_is_set"] is True
    # ...and the secret itself is never part of the envelope.
    assert "qdrant_api_key" not in data
    assert "honcho_api_key" not in data


def test_serialize_derives_flat_option_fields_from_the_map() -> None:
    """The flat compatibility fields survive as derived values (T-A0b-6)."""
    row = SystemMemorySettings(
        backend_options={
            "honcho": {"base_url": "http://honcho.test:8000"},
            "qdrant": {"base_url": "http://qdrant.test:6333", "prefer_grpc": True},
        }
    )

    data = MemorySettingsService._serialize(row)

    assert data["honcho_base_url"] == "http://honcho.test:8000"
    assert data["honcho_base_url_is_override"] is True
    assert data["qdrant_base_url"] == "http://qdrant.test:6333"
    assert data["qdrant_prefer_grpc"] is True
    assert data["qdrant_timeout"] is None
    assert data["qdrant_timeout_is_override"] is False


def test_serialize_survives_undecryptable_blob() -> None:
    """A rotated key degrades the flags instead of raising."""
    row = SystemMemorySettings(backend_secrets_encrypted=_UNDECRYPTABLE_CIPHERTEXT)

    data = MemorySettingsService._serialize(row)

    assert data["qdrant_api_key_is_set"] is False
    assert data["honcho_api_key_is_set"] is False


def test_serialize_empty_or_missing_row_is_not_set() -> None:
    """No ciphertext -> ``False``; a missing row must not raise either."""
    empty = MemorySettingsService._serialize(SystemMemorySettings())
    assert empty["qdrant_api_key_is_set"] is False
    assert empty["honcho_api_key_is_set"] is False

    assert MemorySettingsService._serialize(None)["qdrant_api_key_is_set"] is False
    assert MemorySettingsService._serialize(None)["honcho_api_key_is_set"] is False


@pytest.mark.django_db
def test_get_effective_settings_survives_undecryptable_stored_key() -> None:
    """End-to-end F8: the admin read must not 500 on undecryptable ciphertext."""
    SystemMemorySettings.objects.create(
        backend_secrets_encrypted=_UNDECRYPTABLE_CIPHERTEXT,
    )

    data = MemorySettingsService().get_effective_settings()

    assert data["qdrant_api_key_is_set"] is False
    assert "qdrant_api_key" not in data
