"""Regression tests for ``MemorySettingsService`` serialization (F8).

``_serialize`` must derive the ``*_api_key_is_set`` flags from the PRESENCE of
the stored ciphertext column, never by decrypting it. A rotated
``FIELD_ENCRYPTION_KEY`` makes ``decrypt_secret`` raise ``InvalidToken`` over
already-stored tokens (see ``persistence.encryption``); going through the
decrypting ``SystemMemorySettings.<provider>_api_key`` property therefore
turned every admin ``GET /api/v1/system/memory-settings/`` into a 500. The flag
answers "is a key stored", not "is it decryptable right now", so reading the
column directly is both correct and side-effect free.
"""
from __future__ import annotations

import pytest

from application.memory_settings_service import MemorySettingsService
from memory.models import SystemMemorySettings

#: A Fernet-shaped token (the ``gAAAA`` prefix is exactly what
#: ``decrypt_secret`` keys on) that is NOT decryptable with the test key -- the
#: old property-based code raised ``InvalidToken`` over it.
_UNDECRYPTABLE_CIPHERTEXT = "gAAAA" + "not-a-valid-fernet-token"


def test_serialize_reports_api_key_set_without_decrypting() -> None:
    """``_is_set`` is True for a stored (even undecryptable) ciphertext."""
    row = SystemMemorySettings(
        qdrant_api_key_encrypted=_UNDECRYPTABLE_CIPHERTEXT,
        honcho_api_key_encrypted=_UNDECRYPTABLE_CIPHERTEXT,
    )

    data = MemorySettingsService._serialize(row)

    assert data["qdrant_api_key_is_set"] is True
    assert data["honcho_api_key_is_set"] is True
    # ...and the secret itself is never part of the envelope.
    assert "qdrant_api_key" not in data
    assert "honcho_api_key" not in data


def test_serialize_does_not_call_decrypt(monkeypatch) -> None:
    """Prove the decrypting property is never touched during serialization."""
    from memory import models as memory_models

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("_serialize must not decrypt the stored API key")

    monkeypatch.setattr(memory_models, "decrypt_secret", _boom)

    row = SystemMemorySettings(
        qdrant_api_key_encrypted=_UNDECRYPTABLE_CIPHERTEXT,
        honcho_api_key_encrypted=_UNDECRYPTABLE_CIPHERTEXT,
    )

    data = MemorySettingsService._serialize(row)

    assert data["qdrant_api_key_is_set"] is True
    assert data["honcho_api_key_is_set"] is True


def test_serialize_empty_or_missing_row_is_not_set() -> None:
    """No ciphertext -> ``False``; a missing row must not raise either."""
    empty = MemorySettingsService._serialize(SystemMemorySettings())
    assert empty["qdrant_api_key_is_set"] is False
    assert empty["honcho_api_key_is_set"] is False

    assert MemorySettingsService._serialize(None)["qdrant_api_key_is_set"] is False
    assert MemorySettingsService._serialize(None)["honcho_api_key_is_set"] is False


@pytest.mark.django_db
def test_get_effective_settings_survives_undecryptable_stored_key() -> None:
    """End-to-end F8: the admin read must not 500 on undecryptable ciphertext.

    A row whose ciphertext was encrypted under a since-rotated key would raise
    ``InvalidToken`` on every GET under the old property-based serialization.
    """
    SystemMemorySettings.objects.create(
        qdrant_api_key_encrypted=_UNDECRYPTABLE_CIPHERTEXT,
    )

    data = MemorySettingsService().get_effective_settings()

    assert data["qdrant_api_key_is_set"] is True
    assert "qdrant_api_key" not in data
