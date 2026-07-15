"""
REQ-081 — LlmSettings.api_key encryption at rest.

Covers:
- The ``api_key`` property encrypts on write and decrypts on read; the raw
  ``api_key_encrypted`` column never holds plaintext.
- ``persistence.encryption`` helpers: roundtrip, empty-string passthrough,
  and legacy-plaintext passthrough on decrypt (data not yet migrated).
- The data migration's encrypt step (0037_encrypt_llm_api_key) is idempotent:
  a plaintext row is encrypted once; an already-encrypted row is left
  untouched on a repeated pass.

Uses the same ``set_request_tenant`` pattern as
``rest_api/tests/test_llm_settings.py`` — LlmSettings is RLS-protected
(FORCE ROW LEVEL SECURITY), so both the app-layer TenantContext and the
``app.current_tenant`` DB session variable must be active.
"""
from __future__ import annotations

import importlib

import pytest

from persistence.encryption import ENCRYPTED_PREFIX, decrypt_secret, encrypt_secret
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import LlmSettings, Tenant

# Imported by dotted module path because migration filenames (e.g.
# "0037_encrypt_llm_api_key") are not valid Python identifiers and cannot be
# imported with a normal ``import`` statement.
_migration = importlib.import_module(
    "persistence.migrations.0037_encrypt_llm_api_key"
)


@pytest.fixture
def llm_encryption_tenant(db):
    """A tenant with an active request-scoped context (app layer + RLS)."""
    tenant = Tenant.objects.create(name="Enc T", slug="enc-t", is_active=True)
    set_request_tenant(tenant.id)
    try:
        yield tenant
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Model property
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_api_key_is_encrypted_at_rest(llm_encryption_tenant):
    """Setting ``api_key`` stores ciphertext; the getter returns plaintext."""
    row = LlmSettings.objects.create(
        tenant_id=llm_encryption_tenant.id,
        provider="anthropic",
        api_key="sk-secret-value",
    )
    assert row.api_key_encrypted != "sk-secret-value"
    assert row.api_key_encrypted.startswith(ENCRYPTED_PREFIX)
    assert row.api_key == "sk-secret-value"

    # Re-fetching from the DB decrypts transparently too.
    fetched = LlmSettings.objects.get(pk=row.pk)
    assert fetched.api_key == "sk-secret-value"
    assert fetched.api_key_encrypted.startswith(ENCRYPTED_PREFIX)


@pytest.mark.django_db
def test_api_key_empty_stays_empty(llm_encryption_tenant):
    """An unset api_key is not encrypted — it stays a blank string."""
    row = LlmSettings.objects.create(
        tenant_id=llm_encryption_tenant.id, provider="mock"
    )
    assert row.api_key_encrypted == ""
    assert row.api_key == ""


# ---------------------------------------------------------------------------
# persistence.encryption helpers (no DB required)
# ---------------------------------------------------------------------------


def test_encrypt_secret_roundtrip():
    token = encrypt_secret("sk-abc123")
    assert token.startswith(ENCRYPTED_PREFIX)
    assert token != "sk-abc123"
    assert decrypt_secret(token) == "sk-abc123"


def test_encrypt_decrypt_empty_string_passthrough():
    assert encrypt_secret("") == ""
    assert decrypt_secret("") == ""


def test_decrypt_secret_legacy_plaintext_passthrough():
    """Values without the Fernet prefix are returned as-is (pre-REQ-081 data)."""
    assert decrypt_secret("sk-legacy-plaintext") == "sk-legacy-plaintext"


# ---------------------------------------------------------------------------
# Data migration idempotency (0037_encrypt_llm_api_key)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_migration_encrypts_plaintext_and_skips_already_encrypted(
    llm_encryption_tenant,
):
    """The migration's encrypt step is idempotent.

    Simulates the pre-migration state by writing directly to
    ``api_key_encrypted`` (bypassing the ``api_key`` property, which would
    encrypt immediately). Running the migration's encrypt function then
    encrypts the plaintext row and leaves an already-encrypted row
    untouched; running it a second time changes nothing further.
    """
    from django.apps import apps as real_apps

    plaintext_row = LlmSettings.objects.create(
        tenant_id=llm_encryption_tenant.id, provider="anthropic"
    )
    plaintext_row.api_key_encrypted = "sk-plaintext-legacy"
    plaintext_row.save(update_fields=["api_key_encrypted"])

    # uq_llm_settings_tenant allows only one LlmSettings row per tenant, so
    # the already-encrypted row needs its own tenant. Created via unscoped to
    # stay independent of the request-tenant context of the fixture.
    already_encrypted_value = encrypt_secret("sk-already-encrypted")
    tenant_two = Tenant.objects.create(name="Enc T2", slug="enc-t2", is_active=True)
    encrypted_row = LlmSettings.unscoped.create(
        tenant_id=tenant_two.id, provider="openai"
    )
    encrypted_row.api_key_encrypted = already_encrypted_value
    encrypted_row.save(update_fields=["api_key_encrypted"])

    _migration._encrypt_existing_keys(real_apps, None)

    plaintext_row.refresh_from_db()
    # refresh_from_db would be scoped to the fixture tenant's context, so the
    # cross-tenant row is reloaded explicitly via the unscoped manager.
    encrypted_reloaded = LlmSettings.unscoped.get(pk=encrypted_row.pk)

    assert plaintext_row.api_key_encrypted.startswith(ENCRYPTED_PREFIX)
    assert plaintext_row.api_key == "sk-plaintext-legacy"
    # Already-encrypted row is untouched — identical ciphertext as before.
    assert encrypted_reloaded.api_key_encrypted == already_encrypted_value

    # Running it again is a no-op — the ciphertext does not change.
    first_pass_ciphertext = plaintext_row.api_key_encrypted
    _migration._encrypt_existing_keys(real_apps, None)
    plaintext_row.refresh_from_db()
    assert plaintext_row.api_key_encrypted == first_pass_ciphertext
