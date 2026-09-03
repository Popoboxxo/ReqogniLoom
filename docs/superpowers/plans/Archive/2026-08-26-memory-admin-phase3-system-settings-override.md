# Memory Admin UI — Phase 3: System-Settings-Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a System-Admin override `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL_NAME`/`OLLAMA_BASE_URL`/`EMBEDDING_TIMEOUT`/`MEMORY_BACKEND`/`HONCHO_BASE_URL`/`HONCHO_API_KEY` at runtime via a DB-backed override row, with environment variables staying the fallback when no override is set. Extends the existing (currently read-only, `PUT` hard-503^H^H501) `SystemMemorySettingsView`.

**Architecture:** New model `SystemMemorySettings` (`backend/memory/models.py`) — a genuine process-wide singleton (see Ruling 1 below), read by a new `application/memory_settings_service.py::MemorySettingsService` and overlaid onto env config at the exact two call sites that currently read `os.environ` directly for this feature: `llm_adapter/embedding_service.py::_read_env_config()` (embedding provider) and `memory/backends.py::get_memory_backend()` / `memory/honcho_backend.py::HonchoMemoryBackend.__init__()` (memory backend). The overlay pattern mirrors the already-shipped, already-reviewed `llm_adapter/providers.py::_apply_db_settings()` (overlays tenant-scoped `LlmSettings` onto env `ProviderConfig`) almost verbatim — same best-effort try/except, same "row wins only for fields that are actually set" semantics, same "GET never creates a row" precedent (issue #276, cited in `LlmSettings`'s docstring).

**Tech Stack:** Django 4.2 (new migration), existing `EncryptedTextField`-equivalent pattern (`persistence.encryption.encrypt_secret`/`decrypt_secret`, the same functions `LlmSettings.api_key` already uses — there is no `EncryptedTextField` model field class in this codebase; the spec's pseudo-code name is aspirational, not a real import), DRF serializers, React 18 + TS (existing `SystemSettings.tsx` "memory" tab).

**Spec:** `docs/superpowers/specs/2026-08-26-memory-admin-ui-design.md` (Phase 3 section)

## Rulings (plan-vs-spec conflicts resolved before execution — do not re-litigate these during implementation; if new evidence contradicts one, ledger it and escalate per the ruling process, don't silently reverse it)

1. **`SystemMemorySettings` is NOT `TenantScopedModel`.** The spec's own field list (`embedding_provider`, `memory_backend`, ...) has zero tenant dimension — it exists to override `EMBEDDING_PROVIDER`/`MEMORY_BACKEND` env vars, and both `get_embedding_provider()` and `get_memory_backend()` are process-global functions with **no tenant parameter** (verified: neither takes a `tenant_id` argument anywhere in `llm_adapter/embedding_service.py` or `memory/backends.py`). Every other "system settings" model in this codebase (`LlmSettings`, `TenantThemeDefault`, `Banner`) IS `TenantScopedModel` — but those all back per-tenant-configurable behavior; this one backs a shared-process resource (one embedding model loaded once per worker, one backend client). Making it tenant-scoped would require threading `tenant_id` through every embedding/backend call site (a much larger, riskier change the spec explicitly says is NOT needed: "Diese Stelle ist die einzige, die angefasst werden muss"). Ruling: plain `AuditableModel` subclass (UUID pk, audit fields, no `tenant` FK), singleton enforced by forcing `self.pk` to a fixed constant UUID in `save()`. This is a genuinely new pattern in this codebase (no direct precedent) — flagged here explicitly so a reviewer doesn't need to hunt for one. Cost if wrong: a migration + one model rewrite; no data loss risk since Phase 3 has not shipped yet.
2. **No RLS on the new table.** The project's Global Constraint "new tenant-scoped tables require RLS in the same migration" does not apply — this table has no `tenant` column (Ruling 1). Do not add RLS SQL to the migration.
3. **Auth gate stays view-level, unchanged.** `SystemMemorySettingsView` already gates GET/PUT via its own module-level `_is_system_admin(ctx)` helper (`ctx.has_role("admin") or AuthorizationService().is_tenant_admin(...)`) — unlike `MemoryAdminService` (Phase 1), which asserts inside the service. This view predates Phase 1's newer convention. Ruling: keep gating in the view (apply the same existing `_is_system_admin` check to the new POST reset view too), and let `MemorySettingsService`'s methods trust the caller — this matches `LlmSettingsView`/`ReviewPolicyView`/`PromptTemplateView`, which all gate in the view without a service-side duplicate check. Do not invent a second, subtly-different gate.
4. **Effective-value response shape.** The spec says GET gets `is_override: bool` "je Feld" but doesn't specify the exact JSON shape. Ruling: flat top-level fields carrying the *effective* value (override-or-env, so an admin sees what's actually active) plus one sibling `<field>_is_override: bool` per overridable field — mirrors this codebase's existing `api_key_is_set` sibling-boolean idiom (`LlmSettingsSerializer`) rather than inventing nested per-field objects.
5. **Provider/backend choice validation is a hardcoded list, not a live registry read.** `EMBEDDING_PROVIDER_REGISTRY`/`MEMORY_BACKEND_REGISTRY` are populated by decorators at *module* import time; relying on them in a serializer risks depending on import order. The four provider names (`sentence-transformers`, `ollama`, `mock`) and two backend names (`pgvector`, `honcho`) are stable and already hardcoded as string literals throughout the codebase (e.g. `_read_env_config()`'s own default string, `MEMORY_BACKEND_REGISTRY` decorator arguments) — hardcode the same literals in the serializer `ChoiceField`, matching `LlmProvider.choices`' precedent of a static enum rather than a registry read.

## Global Constraints

- `SystemMemorySettings.objects.first()` reads must NEVER create a row as a side effect (issue #276 precedent, cited in `LlmSettings`'s own docstring: a machine-created row would silently pin defaults forever). Only the PUT/reset paths call `get_or_create`/`save()`.
- Every DB-overlay read (in `embedding_service.py`, `memory/backends.py`, `memory/honcho_backend.py`) MUST lazily `from memory.models import SystemMemorySettings` **inside the function body**, never at module top-level — `llm_adapter` and `memory` importing each other at module scope risks a circular import (mirrors `_apply_db_settings`'s existing lazy `from persistence.models import LlmSettings` inside its function body, not at the top of `llm_adapter/providers.py`).
- Every DB-overlay read MUST be wrapped in a broad `try/except Exception: return <untouched input>` — no active tenant context, no DB connection, or a missing table (fresh test DB before migrations run) must never break embedding/backend resolution; environment stays the source of truth on any failure. Mirrors `_apply_db_settings`'s own `except Exception` docstring note verbatim.
- `honcho_api_key` is NEVER returned as plaintext by any endpoint — only `honcho_api_key_is_set: bool`/`honcho_api_key_is_override: bool` (mirrors `LlmSettings.api_key`/`api_key_is_set`). It is write-only on PUT (accepted, never echoed).
- No new Django app, no new top-level URL prefix — extends the existing `memory` app (`memory/models.py`, `memory/memory_rest.py`) and existing `/api/v1/system/memory-settings/` route family in `rest_api/urls.py`.
- Changing `embedding_provider` or `memory_backend` via PUT must NOT trigger any re-embedding/migration side effect (explicit Non-Goal in the spec) — it only changes which provider/backend the NEXT read resolves to; existing stored vectors are untouched.
- Every new frontend-visible string needs a matching key in BOTH `frontend/src/i18n/locales/de.json` and `frontend/src/i18n/locales/en.json` (checked by `frontend/src/test/i18n-parity.test.ts`).
- Backend tests run via: `docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python -m pytest <paths> -v"`. Frontend tests via: `docker exec reqogniloom-frontend-1 npx vitest run <path>`. Never run tests on the host (unrelated host-level dependency conflict).

---

### Task 1: Backend — `SystemMemorySettings` model, migration, and DB-overlay read paths

**Files:**
- Modify: `backend/memory/models.py` (add `SystemMemorySettings`)
- Create: `backend/memory/migrations/0003_system_memory_settings.py`
- Modify: `backend/llm_adapter/embedding_service.py` (add `_apply_db_settings()` + `_read_config()`; change `get_embedding_provider()` to use it)
- Modify: `backend/memory/backends.py` (overlay `MEMORY_BACKEND` resolution in `get_memory_backend()`)
- Modify: `backend/memory/honcho_backend.py` (overlay `honcho_base_url`/`honcho_api_key` resolution in `__init__`)
- Test: `backend/memory/tests/test_models.py` if it exists, else append to `backend/memory/tests/test_pgvector_backend.py`'s file — **check first which test file already covers `memory/models.py` conventions** (`grep -rn "class TestWorkspaceMemorySettings\|WorkspaceMemorySettings" backend/memory/tests/*.py` to find the right home) and follow its exact fixture style.
- Test: `backend/llm_adapter/tests/test_embedding_service.py` (find via `grep -rln "_read_env_config\|EmbeddingProviderConfig" backend/llm_adapter/tests/*.py` — append to whichever file already covers `embedding_service.py`)
- Test: `backend/memory/tests/test_pgvector_backend.py` / `backend/memory/tests/test_honcho_backend.py` (already exist from Phase 2 — append override-resolution tests)

**Interfaces:**
- Consumes: `persistence.models.AuditableModel` (base class), `persistence.encryption.encrypt_secret`/`decrypt_secret` (the `LlmSettings.api_key` property pattern — read that property/setter pair in `persistence/models.py` around line 1834 before writing this), `llm_adapter.providers._apply_db_settings` (the pattern to mirror, `backend/llm_adapter/providers.py` line ~126).
- Produces: `memory.models.SystemMemorySettings` (singleton model, 7 nullable override fields + encrypted `honcho_api_key` property), `llm_adapter.embedding_service._apply_db_settings(cfg) -> EmbeddingProviderConfig`, `llm_adapter.embedding_service._read_config() -> EmbeddingProviderConfig` (now the thing `get_embedding_provider(config=None)` calls instead of `_read_env_config()` directly — `_read_env_config()` itself stays unchanged, still used by `_read_config()` internally and by anything else already calling it directly).

- [ ] **Step 1: Add the `SystemMemorySettings` model**

In `backend/memory/models.py`, add near the top of the file (after imports, before `WorkspaceMemorySettings` or at the end — match the file's existing ordering)imports:

```python
from uuid import UUID

from persistence.encryption import decrypt_secret, encrypt_secret
from persistence.models import AuditableModel
```

(Check the file's existing import block first — `AuditableModel`/`Workspace`/etc. may already be imported under different names; do not duplicate an import.)

Add the model:

```python
SYSTEM_MEMORY_SETTINGS_ID = UUID("00000000-0000-0000-0000-000000000001")


class SystemMemorySettings(AuditableModel):
    """Process-wide singleton: DB override for the memory feature's
    environment configuration (Memory Admin UI Phase 3, spec 2026-08-26).

    Deliberately NOT ``TenantScopedModel`` — see Phase 3 plan Ruling 1.
    ``get_embedding_provider()``/``get_memory_backend()`` are process-global
    functions with no tenant parameter; this table backs exactly the env
    vars they already read (``EMBEDDING_PROVIDER``, ``MEMORY_BACKEND``, ...).

    Every field is nullable: ``NULL`` means "no override, environment wins".
    Singleton enforced by ``save()`` always forcing the same primary key —
    there is only ever one row, created lazily on first write (issue #276
    precedent: reads never create a row, only PUT/reset do).
    """

    embedding_provider = models.CharField(max_length=32, null=True, blank=True)
    embedding_model_name = models.CharField(max_length=128, null=True, blank=True)
    ollama_base_url = models.CharField(max_length=255, null=True, blank=True)
    embedding_timeout = models.PositiveIntegerField(null=True, blank=True)
    memory_backend = models.CharField(max_length=32, null=True, blank=True)
    honcho_base_url = models.CharField(max_length=255, null=True, blank=True)
    # Fernet ciphertext, mirrors LlmSettings.api_key_encrypted. Never read/write
    # directly -- use the honcho_api_key property below.
    honcho_api_key_encrypted = models.TextField(blank=True, default="")

    class Meta:
        db_table = "mem_system_memory_settings"

    def save(self, *args, **kwargs) -> None:
        self.pk = SYSTEM_MEMORY_SETTINGS_ID
        super().save(*args, **kwargs)

    @property
    def honcho_api_key(self) -> str:
        return decrypt_secret(self.honcho_api_key_encrypted)

    @honcho_api_key.setter
    def honcho_api_key(self, value: str) -> None:
        self.honcho_api_key_encrypted = encrypt_secret(value or "")
```

Confirm `models` (the `django.db.models` module alias) is already imported at the top of `memory/models.py` under that exact name before using `models.CharField` etc. — match whatever import alias the file already uses.

- [ ] **Step 2: Write the migration**

Create `backend/memory/migrations/0003_system_memory_settings.py`. Base it on `backend/memory/migrations/0002_workspace_memory_settings.py`'s structure but WITHOUT any RLS SQL (Ruling 2) and WITHOUT a `tenant` field:

```python
# Memory Admin UI Phase 3 — SystemMemorySettings (Spec 2026-08-26).
#
# Deliberately NOT a tenant-scoped table (see Phase 3 plan Ruling 1/2): this
# is a process-wide singleton overriding EMBEDDING_PROVIDER/MEMORY_BACKEND
# env vars, which are themselves process-global (no tenant dimension). No
# RLS is added -- there is no tenant_id column to filter on.
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("memory", "0002_workspace_memory_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemMemorySettings",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("embedding_provider", models.CharField(blank=True, max_length=32, null=True)),
                ("embedding_model_name", models.CharField(blank=True, max_length=128, null=True)),
                ("ollama_base_url", models.CharField(blank=True, max_length=255, null=True)),
                ("embedding_timeout", models.PositiveIntegerField(blank=True, null=True)),
                ("memory_backend", models.CharField(blank=True, max_length=32, null=True)),
                ("honcho_base_url", models.CharField(blank=True, max_length=255, null=True)),
                ("honcho_api_key_encrypted", models.TextField(blank=True, default="")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "mem_system_memory_settings"},
        ),
    ]
```

Run `docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python manage.py makemigrations --check --dry-run memory"` — if Django wants to generate a DIFFERENT migration than the one just hand-written (e.g. a different field ordering or an extra operation), reconcile by running `python manage.py makemigrations memory` for real and adjusting the hand-written file to match Django's own output rather than fighting it, then re-verify `--check --dry-run` is clean.

- [ ] **Step 3: Overlay `SystemMemorySettings` onto `EmbeddingProviderConfig`**

In `backend/llm_adapter/embedding_service.py`, add after `_read_env_config()`:

```python
def _apply_db_settings(cfg: EmbeddingProviderConfig) -> EmbeddingProviderConfig:
    """Overlay a persisted SystemMemorySettings override onto an env-based
    config (Memory Admin UI Phase 3). Mirrors llm_adapter.providers's own
    _apply_db_settings for LlmSettings -- same best-effort semantics: any
    failure (no row, DB unavailable) leaves cfg untouched, env stays the
    fallback. Lazy import avoids a memory<->llm_adapter circular import.
    """
    try:
        from memory.models import SystemMemorySettings

        row = SystemMemorySettings.objects.first()
        if row is None:
            return cfg
        if row.embedding_provider:
            cfg.provider_name = row.embedding_provider
        if row.embedding_model_name:
            cfg.model_name = row.embedding_model_name
        if row.ollama_base_url:
            cfg.base_url = row.ollama_base_url
        if row.embedding_timeout:
            cfg.timeout = float(row.embedding_timeout)
        return cfg
    except Exception:  # noqa: BLE001 - settings are best-effort; env is the fallback.
        logger.debug("SystemMemorySettings lookup skipped; falling back to environment.")
        return cfg


def _read_config() -> EmbeddingProviderConfig:
    return _apply_db_settings(_read_env_config())
```

Change `get_embedding_provider()`:

```python
def get_embedding_provider(config: Optional[EmbeddingProviderConfig] = None) -> EmbeddingProvider:
    cfg = config or _read_config()
    provider_cls = EMBEDDING_PROVIDER_REGISTRY.get(cfg.provider_name)
    if provider_cls is None:
        raise ValueError(f"unknown embedding provider: {cfg.provider_name!r}")
    return provider_cls(cfg)
```

(Only the `cfg = config or _read_env_config()` line changes to `cfg = config or _read_config()` — nothing else in the function.)

- [ ] **Step 4: Overlay `SystemMemorySettings` onto `get_memory_backend()`**

In `backend/memory/backends.py`, replace `get_memory_backend()`:

```python
def get_memory_backend() -> MemoryBackend:
    """Resolve the active MemoryBackend. SystemMemorySettings.memory_backend
    (Phase 3) wins if set; otherwise MEMORY_BACKEND env var (default pgvector).
    """
    name = _resolve_memory_backend_name()
    backend_cls = MEMORY_BACKEND_REGISTRY.get(name)
    if backend_cls is None:
        raise ValueError(f"unknown memory backend: {name!r}")
    return backend_cls()


def _resolve_memory_backend_name() -> str:
    try:
        from memory.models import SystemMemorySettings

        row = SystemMemorySettings.objects.first()
        if row is not None and row.memory_backend:
            return row.memory_backend.strip().lower()
    except Exception:  # noqa: BLE001 - settings are best-effort; env is the fallback.
        pass
    return os.environ.get("MEMORY_BACKEND", "pgvector").strip().lower()
```

- [ ] **Step 5: Overlay `SystemMemorySettings` onto `HonchoMemoryBackend`**

In `backend/memory/honcho_backend.py`, replace `__init__`:

```python
    def __init__(self) -> None:
        base_url, api_key = self._resolve_config()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = None

    @staticmethod
    def _resolve_config() -> tuple[str, Optional[str]]:
        """SystemMemorySettings override (Phase 3) wins over env vars if set."""
        try:
            from memory.models import SystemMemorySettings

            row = SystemMemorySettings.objects.first()
            if row is not None:
                base_url = row.honcho_base_url or os.environ.get("HONCHO_BASE_URL", "")
                api_key = row.honcho_api_key or os.environ.get("HONCHO_API_KEY")
                return base_url, api_key
        except Exception:  # noqa: BLE001 - settings are best-effort; env is the fallback.
            pass
        return os.environ.get("HONCHO_BASE_URL", ""), os.environ.get("HONCHO_API_KEY")
```

Delete the two lines this replaces (`self._base_url = os.environ.get(...)` / `self._api_key = os.environ.get(...)`) — keep `self._client = None` as the last line of `__init__`.

- [ ] **Step 6: Write tests for the overlay behavior**

For `embedding_service.py` (in whichever test file already covers it — find it first):

```python
class TestEmbeddingServiceDbOverride:
    @pytest.mark.django_db
    def test_db_override_wins_over_env(self, monkeypatch):
        from memory.models import SystemMemorySettings

        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        SystemMemorySettings.objects.create(embedding_provider="mock")
        cfg = _read_config()
        assert cfg.provider_name == "mock"

    @pytest.mark.django_db
    def test_falls_back_to_env_when_no_override_row(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        cfg = _read_config()
        assert cfg.provider_name == "mock"

    @pytest.mark.django_db
    def test_falls_back_to_env_when_field_is_null(self, monkeypatch):
        from memory.models import SystemMemorySettings

        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        SystemMemorySettings.objects.create()  # every field NULL
        cfg = _read_config()
        assert cfg.provider_name == "mock"
```

For `memory/backends.py` (append to `test_pgvector_backend.py`):

```python
class TestGetMemoryBackendDbOverride:
    @pytest.mark.django_db
    def test_db_override_wins_over_env(self, monkeypatch):
        from memory.models import SystemMemorySettings

        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        SystemMemorySettings.objects.create(memory_backend="honcho")
        assert isinstance(get_memory_backend(), HonchoMemoryBackend)
```

(Import `HonchoMemoryBackend` at the top of the test file if not already imported.)

For `memory/honcho_backend.py` (append to `test_honcho_backend.py`):

```python
class TestHonchoBackendDbOverride:
    @pytest.mark.django_db
    def test_db_override_base_url_wins_over_env(self, monkeypatch):
        from memory.models import SystemMemorySettings

        monkeypatch.setenv("HONCHO_BASE_URL", "http://env-honcho.invalid")
        SystemMemorySettings.objects.create(honcho_base_url="http://db-honcho.invalid")
        backend = HonchoMemoryBackend()
        assert backend._base_url == "http://db-honcho.invalid"

    @pytest.mark.django_db
    def test_falls_back_to_env_when_no_override_row(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://env-honcho.invalid")
        backend = HonchoMemoryBackend()
        assert backend._base_url == "http://env-honcho.invalid"
```

Run all touched test files, expect PASS. Then run the full `memory` and `llm_adapter` suites once to catch any regression from the `get_embedding_provider()`/`get_memory_backend()` signature-preserving change:

`docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python -m pytest memory/ llm_adapter/ -q 2>&1 | tail -40"`

- [ ] **Step 7: Commit**

```bash
git add backend/memory/models.py backend/memory/migrations/0003_system_memory_settings.py backend/llm_adapter/embedding_service.py backend/memory/backends.py backend/memory/honcho_backend.py backend/memory/tests/ backend/llm_adapter/tests/
git commit -m "feat: add SystemMemorySettings DB override for memory embedding/backend config"
```

(Use the exact test file paths actually touched in Step 6.)

---

### Task 2: Backend — `MemorySettingsService`, extended REST view, reset endpoint

**Files:**
- Create: `backend/application/memory_settings_service.py`
- Modify: `backend/memory/memory_rest.py` (extend `SystemMemorySettingsView.get`/`.put`, add `SystemMemorySettingsResetView`)
- Modify: `backend/rest_api/urls.py` (import + wire the new reset URL)
- Modify: `backend/memory/tests/test_memory_rest.py` (extend `TestMemorySettingsRest`, matching its exact `APIClient`/`active_tenant()`/`admin_user_and_token`/`editor_user_and_token` style — read the whole existing class first, lines 1-100, before writing new tests)

**Interfaces:**
- Consumes: `memory.models.SystemMemorySettings` (Task 1), `auth_tenancy.services.AuthorizationService` (already imported in `memory/memory_rest.py` for the existing `_is_system_admin`), `persistence.transactions.atomic_transaction`.
- Produces: `application.memory_settings_service.MemorySettingsService` with three public methods: `get_effective_settings() -> dict`, `update_settings(data: dict) -> dict`, `reset_settings() -> dict` — none take `ctx` (Ruling 3: the view already gates via `_is_system_admin`, the service trusts its caller, matching `LlmSettingsView`'s sibling views' pattern of not re-checking permission in the service layer). New `PUT`/`POST` routes: `PUT /api/v1/system/memory-settings/` (now real, was 501), `POST /api/v1/system/memory-settings/reset/` (new).

- [ ] **Step 1: Write `MemorySettingsService`**

Create `backend/application/memory_settings_service.py`:

```python
"""MemorySettingsService — System-Admin read/write of the process-wide
SystemMemorySettings override (Memory Admin UI Phase 3, spec 2026-08-26).

No ctx-based permission check in this service (Phase 3 plan Ruling 3):
the caller (SystemMemorySettingsView / SystemMemorySettingsResetView) already
gates via its own module-level _is_system_admin(ctx), matching the existing
LlmSettingsView/ReviewPolicyView/PromptTemplateView precedent of gating in
the view rather than duplicating the check in the service.
"""
from __future__ import annotations

from typing import Any, Optional

from memory.models import SYSTEM_MEMORY_SETTINGS_ID, SystemMemorySettings
from persistence.transactions import atomic_transaction

_OVERRIDABLE_FIELDS = (
    "embedding_provider",
    "embedding_model_name",
    "ollama_base_url",
    "embedding_timeout",
    "memory_backend",
    "honcho_base_url",
)


class MemorySettingsService:
    """Read/write the singleton SystemMemorySettings row."""

    @staticmethod
    def _serialize(row: Optional[SystemMemorySettings]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field in _OVERRIDABLE_FIELDS:
            value = getattr(row, field, None) if row is not None else None
            data[field] = value
            data[f"{field}_is_override"] = value is not None
        data["honcho_api_key_is_set"] = bool(row.honcho_api_key) if row is not None else False
        return data

    def get_effective_settings(self) -> dict[str, Any]:
        """Read-only: never creates a row (issue #276 precedent)."""
        row = SystemMemorySettings.objects.first()
        return self._serialize(row)

    @atomic_transaction
    def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        row, _ = SystemMemorySettings.objects.get_or_create(pk=SYSTEM_MEMORY_SETTINGS_ID)

        old_provider = row.embedding_provider
        old_backend = row.memory_backend

        for field in _OVERRIDABLE_FIELDS:
            if field in data:
                setattr(row, field, data[field])
        if "honcho_api_key" in data and data["honcho_api_key"]:
            row.honcho_api_key = data["honcho_api_key"]
        row.save()

        result = self._serialize(row)
        warnings = []
        if "embedding_provider" in data and data["embedding_provider"] != old_provider:
            warnings.append(
                "Embedding provider changed. Existing embeddings were NOT re-indexed "
                "and remain in the previous provider's vector space; re-indexing is manual."
            )
        if "memory_backend" in data and data["memory_backend"] != old_backend:
            warnings.append(
                "Memory backend changed. Existing entries in the previous backend are "
                "NOT migrated automatically."
            )
        result["warning"] = " ".join(warnings) if warnings else None
        return result

    @atomic_transaction
    def reset_settings(self) -> dict[str, Any]:
        row, _ = SystemMemorySettings.objects.get_or_create(pk=SYSTEM_MEMORY_SETTINGS_ID)
        for field in _OVERRIDABLE_FIELDS:
            setattr(row, field, None)
        row.honcho_api_key_encrypted = ""
        row.save()
        result = self._serialize(row)
        result["warning"] = None
        return result


__all__ = ["MemorySettingsService"]
```

Verify `persistence.transactions.atomic_transaction` is usable as a plain method decorator (it already decorates `MemoryAdminService.delete_workspace_memory`, an instance method — copy that exact usage).

- [ ] **Step 2: Extend `SystemMemorySettingsView` and add the reset view**

In `backend/memory/memory_rest.py`, replace the whole `SystemMemorySettingsView` class body (keep the class, replace `get`/`put`):

```python
class SystemMemorySettingsView(APIView):
    """``/api/v1/system/memory-settings/`` — System-Admin only.

    GET returns the effective configuration (SystemMemorySettings DB
    override, falling back to env vars per field) plus an
    ``<field>_is_override`` flag per field so the UI can show what deviates
    from the default (Memory Admin UI Phase 3, spec 2026-08-26). PUT applies
    a partial override; omitted fields are left unchanged, a field sent as
    ``null`` clears that field's override back to env. A response ``warning``
    (non-null only when embedding_provider/memory_backend actually changed)
    tells the caller existing embeddings were not migrated automatically.
    """

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_system_admin(ctx):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        effective = MemorySettingsService().get_effective_settings()
        return Response(_with_env_fallback(effective))

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_system_admin(ctx):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = SystemMemorySettingsWriteSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = MemorySettingsService().update_settings(dict(ser.validated_data))
        return Response(_with_env_fallback(result))


class SystemMemorySettingsResetView(APIView):
    """``POST /api/v1/system/memory-settings/reset/`` — System-Admin only.

    Clears every SystemMemorySettings override field back to NULL, so the
    effective configuration falls back entirely to environment variables.
    """

    permission_classes = [HasOperationPermission]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_system_admin(ctx):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        result = MemorySettingsService().reset_settings()
        return Response(_with_env_fallback(result))
```

Add these helpers/imports near the top of `memory/memory_rest.py` (module level, above `SystemMemorySettingsView`):

```python
from application.memory_settings_service import MemorySettingsService
from rest_framework import serializers


class SystemMemorySettingsWriteSerializer(serializers.Serializer):
    embedding_provider = serializers.ChoiceField(
        choices=["sentence-transformers", "ollama", "mock"], required=False, allow_null=True
    )
    embedding_model_name = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=128)
    ollama_base_url = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    embedding_timeout = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    memory_backend = serializers.ChoiceField(
        choices=["pgvector", "honcho"], required=False, allow_null=True
    )
    honcho_base_url = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    honcho_api_key = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=512)


def _with_env_fallback(effective: dict) -> dict:
    """Fill in the env-var value for every field the DB override left None,
    so the response's top-level fields are always the ACTUAL effective
    configuration (override-or-env), not just the raw override row.
    """
    import os

    env_defaults = {
        "embedding_provider": os.environ.get("EMBEDDING_PROVIDER", "sentence-transformers"),
        "embedding_model_name": os.environ.get("EMBEDDING_MODEL_NAME"),
        "ollama_base_url": os.environ.get("OLLAMA_BASE_URL"),
        "embedding_timeout": int(os.environ.get("EMBEDDING_TIMEOUT", "10")),
        "memory_backend": os.environ.get("MEMORY_BACKEND", "pgvector"),
        "honcho_base_url": os.environ.get("HONCHO_BASE_URL"),
    }
    out = dict(effective)
    for field, env_value in env_defaults.items():
        if out.get(field) is None:
            out[field] = env_value
    return out
```

Check `memory/memory_rest.py`'s existing top-of-file imports before adding these — `serializers` and `Response`/`status`/`APIView`/`Request` are almost certainly already imported (the file already defines other views); do not duplicate.

Remove the now-dead `NOT_IMPLEMENTED` 501 branch entirely (it's replaced by the real `put` above) and remove the `os` import from inside the old `get` if it becomes unused elsewhere in the file (check with `grep -n "os\." memory/memory_rest.py` first — the file may still need `os` for other views).

- [ ] **Step 3: Wire the URL**

In `backend/rest_api/urls.py`, add `SystemMemorySettingsResetView` to the existing `from memory.memory_rest import (...)` block (alphabetical, matching the existing style), and add a new `path()` immediately after the existing `system/memory-settings/` entry:

```python
    path(
        "system/memory-settings/reset/",
        SystemMemorySettingsResetView.as_view(),
        name="system-memory-settings-reset",
    ),
```

- [ ] **Step 4: Write/extend tests**

Read `backend/memory/tests/test_memory_rest.py` lines 1-100 in full first (it already has `test_system_memory_settings_shows_active_config`/`test_system_memory_settings_denies_non_admin` in `TestMemorySettingsRest`). The existing `test_system_memory_settings_shows_active_config` asserted an EXACT two-key response (`{"embedding_provider": ..., "memory_backend": ...}`); it will need updating since the response now has many more keys — change its assertions to check the two original keys are still present with the expected values (`response.data["embedding_provider"] == "sentence-transformers"`), not an exact-dict equality, so the new fields don't break it.

Append to `TestMemorySettingsRest`:

```python
    def test_put_sets_db_override(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/",
                {"embedding_provider": "mock"},
                format="json",
            )
            assert response.status_code == 200
            assert response.data["embedding_provider"] == "mock"
            assert response.data["embedding_provider_is_override"] is True

            get_response = client.get("/api/v1/system/memory-settings/")
            assert get_response.data["embedding_provider"] == "mock"

    def test_put_changing_provider_returns_warning(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/",
                {"embedding_provider": "mock"},
                format="json",
            )
            assert response.data["warning"] is not None

    def test_put_unchanged_provider_no_warning(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_TIMEOUT", "10")
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/",
                {"embedding_timeout": 20},
                format="json",
            )
            assert response.data["warning"] is None

    def test_honcho_api_key_never_returned_plaintext(self):
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            put_response = client.put(
                "/api/v1/system/memory-settings/",
                {"honcho_api_key": "super-secret-value"},
                format="json",
            )
            assert "honcho_api_key" not in put_response.data
            assert put_response.data["honcho_api_key_is_set"] is True

            get_response = client.get("/api/v1/system/memory-settings/")
            assert "honcho_api_key" not in get_response.data
            assert get_response.data["honcho_api_key_is_set"] is True

    def test_reset_clears_all_overrides(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            client.put("/api/v1/system/memory-settings/", {"embedding_provider": "mock"}, format="json")

            reset_response = client.post("/api/v1/system/memory-settings/reset/")
            assert reset_response.status_code == 200
            assert reset_response.data["embedding_provider"] == "sentence-transformers"
            assert reset_response.data["embedding_provider_is_override"] is False

    def test_put_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/", {"embedding_provider": "mock"}, format="json"
            )
            assert response.status_code == 403

    def test_reset_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.post("/api/v1/system/memory-settings/reset/")
            assert response.status_code == 403

    def test_put_rejects_unknown_provider(self):
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/memory-settings/", {"embedding_provider": "not-a-real-provider"}, format="json"
            )
            assert response.status_code == 400
```

Run: `docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python -m pytest memory/tests/test_memory_rest.py -v 2>&1 | tail -60"` — expect PASS (old and new).

- [ ] **Step 5: Commit**

```bash
git add backend/application/memory_settings_service.py backend/memory/memory_rest.py backend/rest_api/urls.py backend/memory/tests/test_memory_rest.py
git commit -m "feat: implement PUT/reset for system memory settings override"
```

---

### Task 3: Frontend — System Settings override form in the Memory tab

**Files:**
- Create: `frontend/src/api/system-memory-settings.ts`
- Create: `frontend/src/components/SystemSettings/MemorySystemSettingsSection.tsx`
- Create: `frontend/src/components/SystemSettings/MemorySystemSettingsSection.module.css` (copy `MemoryManagementSection.module.css`'s class names/structure, adjust as needed)
- Create: `frontend/src/components/SystemSettings/MemorySystemSettingsSection.test.tsx` (mirror `MemoryManagementSection.test.tsx`'s mocking/testing style — read it first)
- Modify: `frontend/src/components/SystemSettings/SystemSettings.tsx` (mount the new section inside the existing `"memory"` tab, alongside `MemoryManagementSection`)
- Modify: `frontend/src/i18n/locales/de.json` and `frontend/src/i18n/locales/en.json` (new `systemSettings.memorySettings.*` keys)

**Interfaces:**
- Consumes: `apiClient` (`frontend/src/api/client.ts`), `Dialog` (`frontend/src/components/shared/Dialog.tsx` — used by `MemoryManagementSection` for its delete-confirm dialog, reuse the same component for the provider/backend-change confirm dialog).
- Produces: `systemMemorySettingsApi` (`get`/`update`/`reset`), `MemorySystemSettingsSection` component, mounted as a second block inside `SystemSettings.tsx`'s existing `activeTab === "memory"` branch (below or above `<MemoryManagementSection />` — pick above, since settings apply globally and the workspace table is the per-workspace detail view beneath it).

- [ ] **Step 1: Write the API client**

Create `frontend/src/api/system-memory-settings.ts`:

```typescript
/**
 * ARCH-L1-001 ReactFrontend — System Memory Settings API (Memory Admin UI
 * Phase 3, spec 2026-08-26).
 *
 * Wraps /api/v1/system/memory-settings/ (GET/PUT) and its /reset/ POST.
 * System-Admin only. `honcho_api_key` is write-only end-to-end -- GET/PUT
 * responses only ever carry `honcho_api_key_is_set`.
 */

import { apiClient } from "./client";

export type EmbeddingProviderName = "sentence-transformers" | "ollama" | "mock";
export type MemoryBackendName = "pgvector" | "honcho";

/** Effective (override-or-env) configuration, with per-field override flags. */
export interface SystemMemorySettings {
  embedding_provider: EmbeddingProviderName;
  embedding_provider_is_override: boolean;
  embedding_model_name: string | null;
  embedding_model_name_is_override: boolean;
  ollama_base_url: string | null;
  ollama_base_url_is_override: boolean;
  embedding_timeout: number;
  embedding_timeout_is_override: boolean;
  memory_backend: MemoryBackendName;
  memory_backend_is_override: boolean;
  honcho_base_url: string | null;
  honcho_base_url_is_override: boolean;
  honcho_api_key_is_set: boolean;
  warning: string | null;
}

export interface SystemMemorySettingsUpdate {
  embedding_provider?: EmbeddingProviderName | null;
  embedding_model_name?: string | null;
  ollama_base_url?: string | null;
  embedding_timeout?: number | null;
  memory_backend?: MemoryBackendName | null;
  honcho_base_url?: string | null;
  honcho_api_key?: string;
}

export const systemMemorySettingsApi = {
  async get(): Promise<SystemMemorySettings> {
    return apiClient.get<SystemMemorySettings>("/system/memory-settings/");
  },
  async update(payload: SystemMemorySettingsUpdate): Promise<SystemMemorySettings> {
    return apiClient.put<SystemMemorySettings>("/system/memory-settings/", payload);
  },
  async reset(): Promise<SystemMemorySettings> {
    return apiClient.post<SystemMemorySettings>("/system/memory-settings/reset/", {});
  },
};
```

Check `apiClient`'s actual method names (`get`/`put`/`post`) against `frontend/src/api/client.ts` before assuming this signature — `llm-settings.ts` above confirms `get`/`patch`; confirm `put` and `post` also exist with the same generic-typed signature (they're used elsewhere, e.g. `memory-settings.ts`'s `update` uses `apiClient.put`).

- [ ] **Step 2: Write the component**

Create `frontend/src/components/SystemSettings/MemorySystemSettingsSection.tsx`. Structure: a read-only summary of the 6 non-secret fields (each showing effective value + an "override" badge when `*_is_override` is true), an editable form (provider/backend as `<select>`, the rest as text/number inputs, honcho_api_key as a password-style input that's always empty on load per Global Constraint), a "Save" button, and a "Reset to defaults" button. Confirm-before-submit: if the form's pending `embedding_provider` or `memory_backend` value differs from the currently loaded effective value, show a `Dialog` confirm step ("Embeddings/backend data will not be re-indexed/migrated automatically — continue?") before calling `.update()`; the PUT itself is the confirm dialog's action, not a second network round-trip.

```typescript
/**
 * Memory Admin UI Phase 3 (spec 2026-08-26) — System-Admin override form for
 * the memory feature's embedding provider / memory backend configuration.
 * Mounted in the "memory" tab of SystemSettings, above MemoryManagementSection.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  systemMemorySettingsApi,
  type EmbeddingProviderName,
  type MemoryBackendName,
  type SystemMemorySettings,
  type SystemMemorySettingsUpdate,
} from "../../api/system-memory-settings";
import { Dialog } from "../shared/Dialog";
import styles from "./MemorySystemSettingsSection.module.css";

const EMBEDDING_PROVIDERS: EmbeddingProviderName[] = ["sentence-transformers", "ollama", "mock"];
const MEMORY_BACKENDS: MemoryBackendName[] = ["pgvector", "honcho"];

export function MemorySystemSettingsSection(): JSX.Element {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<SystemMemorySettings | null>(null);
  const [form, setForm] = useState<SystemMemorySettingsUpdate>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingWarningConfirm, setPendingWarningConfirm] = useState(false);

  const reload = useCallback((): void => {
    systemMemorySettingsApi
      .get()
      .then((s) => {
        setSettings(s);
        setForm({});
        setLoadError(null);
      })
      .catch((err: unknown) => {
        console.error("MemorySystemSettingsSection: failed to load settings", err);
        setLoadError(t("systemSettings.memorySettings.loadError"));
      });
  }, [t]);

  useEffect(() => {
    reload();
  }, [reload]);

  const isRiskyChange = useCallback((): boolean => {
    if (!settings) return false;
    const providerChanged =
      form.embedding_provider !== undefined && form.embedding_provider !== settings.embedding_provider;
    const backendChanged =
      form.memory_backend !== undefined && form.memory_backend !== settings.memory_backend;
    return providerChanged || backendChanged;
  }, [form, settings]);

  const doSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    try {
      const result = await systemMemorySettingsApi.update(form);
      setSettings(result);
      setForm({});
      setPendingWarningConfirm(false);
    } catch (err) {
      console.error("MemorySystemSettingsSection: failed to save settings", err);
      setSaveError(t("systemSettings.memorySettings.saveError"));
    } finally {
      setIsSaving(false);
    }
  }, [form, t]);

  const handleSaveClick = useCallback((): void => {
    if (isRiskyChange()) {
      setPendingWarningConfirm(true);
      return;
    }
    void doSave();
  }, [isRiskyChange, doSave]);

  const handleReset = useCallback(async (): Promise<void> => {
    if (!window.confirm(t("systemSettings.memorySettings.resetConfirm"))) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      const result = await systemMemorySettingsApi.reset();
      setSettings(result);
      setForm({});
    } catch (err) {
      console.error("MemorySystemSettingsSection: failed to reset settings", err);
      setSaveError(t("systemSettings.memorySettings.saveError"));
    } finally {
      setIsSaving(false);
    }
  }, [t]);

  if (loadError) {
    return (
      <p role="alert" data-testid="memory-system-settings-error" className={styles.error}>
        {loadError}
      </p>
    );
  }
  if (!settings) {
    return <p data-testid="memory-system-settings-loading">{t("loading", "Loading...")}</p>;
  }

  return (
    <section className={styles.section} data-testid="memory-system-settings-section">
      <h3>{t("systemSettings.memorySettings.heading")}</h3>
      <p className={styles.hint}>{t("systemSettings.memorySettings.hint")}</p>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.embeddingProvider")}
        <select
          data-testid="memory-settings-embedding-provider"
          value={form.embedding_provider ?? settings.embedding_provider}
          onChange={(e) =>
            setForm((f) => ({ ...f, embedding_provider: e.target.value as EmbeddingProviderName }))
          }
        >
          {EMBEDDING_PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        {settings.embedding_provider_is_override && (
          <span data-testid="embedding-provider-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.memoryBackend")}
        <select
          data-testid="memory-settings-backend"
          value={form.memory_backend ?? settings.memory_backend}
          onChange={(e) => setForm((f) => ({ ...f, memory_backend: e.target.value as MemoryBackendName }))}
        >
          {MEMORY_BACKENDS.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
        {settings.memory_backend_is_override && (
          <span data-testid="memory-backend-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.honchoApiKey")}
        <input
          type="password"
          data-testid="memory-settings-honcho-api-key"
          placeholder={
            settings.honcho_api_key_is_set
              ? t("systemSettings.memorySettings.secretSetPlaceholder")
              : t("systemSettings.memorySettings.secretUnsetPlaceholder")
          }
          value={form.honcho_api_key ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, honcho_api_key: e.target.value }))}
        />
      </label>

      {saveError && (
        <p role="alert" data-testid="memory-system-settings-save-error" className={styles.error}>
          {saveError}
        </p>
      )}
      {settings.warning && (
        <p role="alert" data-testid="memory-system-settings-warning" className={styles.warning}>
          {settings.warning}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          data-testid="memory-settings-save-btn"
          disabled={isSaving || Object.keys(form).length === 0}
          onClick={handleSaveClick}
        >
          {isSaving ? "…" : t("actions.save", "Save")}
        </button>
        <button type="button" data-testid="memory-settings-reset-btn" disabled={isSaving} onClick={() => void handleReset()}>
          {t("systemSettings.memorySettings.resetButton")}
        </button>
      </div>

      {pendingWarningConfirm && (
        <Dialog
          title={t("systemSettings.memorySettings.confirmTitle")}
          onClose={() => setPendingWarningConfirm(false)}
          size="sm"
          testId="memory-settings-confirm-dialog"
          footer={
            <div className={styles.dialogFooter}>
              <button type="button" onClick={() => setPendingWarningConfirm(false)}>
                {t("actions.cancel", "Cancel")}
              </button>
              <button type="button" data-testid="memory-settings-confirm-btn" disabled={isSaving} onClick={() => void doSave()}>
                {isSaving ? "…" : t("systemSettings.memorySettings.confirmButton")}
              </button>
            </div>
          }
        >
          <p>{t("systemSettings.memorySettings.confirmBody")}</p>
        </Dialog>
      )}
    </section>
  );
}
```

Read `MemoryManagementSection.module.css` first and reuse its class names (`section`/`hint`/`error`/`dialogFooter`) in the new `.module.css` file for visual consistency; add `field`/`overrideBadge`/`actions`/`warning` as new classes.

- [ ] **Step 3: Mount the section in `SystemSettings.tsx`**

In `frontend/src/components/SystemSettings/SystemSettings.tsx`, add the import next to the existing `MemoryManagementSection` import, and add `<MemorySystemSettingsSection />` immediately above `<MemoryManagementSection />` inside the existing `{activeTab === "memory" && (...)}` block (read the exact current JSX around line 166 first — the existing line is `{activeTab === "memory" && <MemoryManagementSection />}`; change it to a fragment wrapping both components in the settings-then-overview order).

- [ ] **Step 4: Add i18n keys**

Add to both `frontend/src/i18n/locales/de.json` and `frontend/src/i18n/locales/en.json`, inside `systemSettings` as a new sibling object `memorySettings` (mirroring the existing `systemSettings.memory.*` flat-dotted convention already used by `MemoryManagementSection` — read that block first to match nesting exactly):

DE:
```json
"memorySettings": {
  "heading": "Systemweite Speicher-Konfiguration",
  "hint": "Überschreibt die Umgebungsvariablen-Konfiguration für Embedding-Provider und Memory-Backend zur Laufzeit. Nicht gesetzte Felder verwenden weiterhin die Umgebungsvariable.",
  "embeddingProvider": "Embedding-Provider",
  "memoryBackend": "Memory-Backend",
  "honchoApiKey": "Honcho API-Key",
  "secretSetPlaceholder": "•••••••• (gesetzt, zum Ändern überschreiben)",
  "secretUnsetPlaceholder": "Nicht gesetzt",
  "overrideBadge": "Überschrieben",
  "resetButton": "Auf Standard zurücksetzen",
  "resetConfirm": "Alle System-Overrides zurücksetzen? Die Umgebungsvariablen-Konfiguration gilt danach wieder vollständig.",
  "confirmTitle": "Änderung bestätigen",
  "confirmBody": "Bestehende Embeddings/Memory-Einträge werden NICHT automatisch neu indiziert oder migriert. Fortfahren?",
  "confirmButton": "Trotzdem speichern",
  "loadError": "Konfiguration konnte nicht geladen werden.",
  "saveError": "Speichern fehlgeschlagen."
}
```

EN:
```json
"memorySettings": {
  "heading": "System-wide Memory Configuration",
  "hint": "Overrides the environment-variable configuration for the embedding provider and memory backend at runtime. Fields left unset keep using the environment variable.",
  "embeddingProvider": "Embedding Provider",
  "memoryBackend": "Memory Backend",
  "honchoApiKey": "Honcho API Key",
  "secretSetPlaceholder": "•••••••• (set, overwrite to change)",
  "secretUnsetPlaceholder": "Not set",
  "overrideBadge": "Overridden",
  "resetButton": "Reset to defaults",
  "resetConfirm": "Reset all system overrides? The environment-variable configuration will fully apply again.",
  "confirmTitle": "Confirm change",
  "confirmBody": "Existing embeddings/memory entries will NOT be automatically re-indexed or migrated. Continue?",
  "confirmButton": "Save anyway",
  "loadError": "Failed to load configuration.",
  "saveError": "Failed to save."
}
```

- [ ] **Step 5: Write component tests**

Read `MemoryManagementSection.test.tsx` first for its exact mocking convention (likely `vi.mock("../../api/memoryAdmin", ...)`), then write `MemorySystemSettingsSection.test.tsx` mocking `systemMemorySettingsApi` with tests for: initial load renders effective values, changing provider + save shows confirm dialog (not an immediate PUT call), confirming the dialog calls `.update()`, changing a non-risky field (e.g. `embedding_timeout` — note this field has no input in the Step 2 minimal form; if omitted from the JSX, drop this particular test case and instead use `honcho_api_key` as the non-risky-change test field) saves without a confirm dialog, reset button calls `.reset()` after `window.confirm`.

Run: `docker exec reqogniloom-frontend-1 npx vitest run src/components/SystemSettings/MemorySystemSettingsSection.test.tsx`
Also run: `docker exec reqogniloom-frontend-1 npx vitest run src/test/i18n-parity.test.ts`
Also run the existing `SystemSettings.tsx`/`MemoryManagementSection.test.tsx` suites to catch a mounting regression: `docker exec reqogniloom-frontend-1 npx vitest run src/components/SystemSettings/`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/system-memory-settings.ts frontend/src/components/SystemSettings/MemorySystemSettingsSection.tsx frontend/src/components/SystemSettings/MemorySystemSettingsSection.module.css frontend/src/components/SystemSettings/MemorySystemSettingsSection.test.tsx frontend/src/components/SystemSettings/SystemSettings.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: add system memory settings override UI"
```

---

## Post-Plan Note

This plan implements Phase 3 only. Phases 4-5 (user self-service, visualization) are separate future plans against the same spec (`docs/superpowers/specs/2026-08-26-memory-admin-ui-design.md`) and are NOT part of this plan's scope. A follow-up ticket should be filed for automatic re-indexing after a provider/backend switch (explicit Non-Goal in the spec, already flagged there as a future ticket candidate) — do not implement it as part of this plan.

Also worth filing as follow-ups (found during Phase 2, deliberately deferred, still unresolved): `HonchoMemoryBackend` is never actually registered/importable in a real running process (pre-existing bug, unrelated to this phase's scope); an SSRF-safe scheme/host allowlist for `honcho_base_url` now that it is admin-UI-settable (this phase makes that gap concretely exploitable for the first time — a System-Admin can now point `HONCHO_BASE_URL` at an internal address via the UI, where previously it required container/env access — flag this explicitly to the final whole-branch reviewer, do not silently accept it as in-scope-but-skipped).
