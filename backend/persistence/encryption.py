"""Field-level symmetric encryption helpers (REQ-081).

Wraps :class:`cryptography.fernet.Fernet` using the application-wide
``FIELD_ENCRYPTION_KEY`` setting (see ``reqogniloom/settings.py``, which fails
fast at startup if the key is missing). Currently used by
:class:`persistence.models.LlmSettings` to store provider API keys as
ciphertext instead of plaintext.

Every Fernet token starts with the base64 encoding of the fixed version byte
(``0x80``), which always renders as the literal prefix ``gAAAA``. That
prefix lets callers (and the accompanying data migration) tell an encrypted
value apart from legacy/plaintext data without keeping extra state, which is
what makes both :func:`decrypt_secret` and the data migration idempotent.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

ENCRYPTED_PREFIX = "gAAAA"


def _fernet() -> Fernet:
    """Build a :class:`Fernet` instance from the configured encryption key."""
    key = settings.FIELD_ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt ``plaintext`` and return the Fernet token as text.

    Empty input is returned unchanged — there is no value in encrypting the
    "unset" sentinel, and it keeps ``bool(value)`` checks working on the
    stored column exactly as they did before encryption was introduced.
    """
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    """Decrypt ``value`` and return the plaintext.

    Empty input is returned unchanged. Values that do not carry the Fernet
    token prefix are treated as legacy/unencrypted data — e.g. a row the data
    migration has not (yet) touched, or a plaintext value set directly in a
    test fixture — and are returned as-is instead of raising, so callers
    never see a crash for data written before REQ-081.
    """
    if not value:
        return ""
    if not value.startswith(ENCRYPTED_PREFIX):
        return value
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Looked encrypted (prefix matched) but failed to decrypt — most
        # likely FIELD_ENCRYPTION_KEY was rotated without re-encrypting the
        # stored data. Fail loudly rather than silently treating ciphertext
        # as a usable secret.
        raise


__all__ = ["ENCRYPTED_PREFIX", "encrypt_secret", "decrypt_secret"]
