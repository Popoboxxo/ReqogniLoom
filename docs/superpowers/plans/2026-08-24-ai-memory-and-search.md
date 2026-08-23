# AI Memory and Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-tier AI long-term memory (per-workspace, per-user-tenant-wide) and extend search with a cross-workspace scope and a semantic pass — self-contained by default (in-process embeddings, self-hosted Postgres/pgvector), with Ollama, OpenAI, and Honcho as optional, pluggable external backends.

**Architecture:** New `memory` Django app (Layer 2, placed like `context_graph`), following that app's exact scaffolding (RLS migration pair, event-bus projector, Celery task, admin rebuild command). A new `EmbeddingProvider` registry replaces `embedding_service.py`'s if/elif chain. A new `MemoryBackend` abstraction (`PgvectorMemoryBackend` default, `HonchoMemoryBackend` optional) mirrors the existing `_PROVIDER_REGISTRY`/`register_provider()`/`get_provider()` pattern in `llm_adapter/providers.py`. `SearchService` gets a `scope` parameter and a semantic fusion pass, reusing existing embedding infrastructure.

**Tech Stack:** Django 4.2+ (backend), `pgvector` (already installed), `sentence-transformers` (new dependency, in-process), Celery (existing queue infrastructure, one new queue).

**Spec:** `docs/superpowers/specs/2026-08-24-ai-memory-and-search-design.md`

## Global Constraints

- `EMBEDDING_PROVIDER` and `MEMORY_BACKEND` are read directly via `os.environ.get(...)` in their respective provider-registry modules — NOT centralized in `reqogniloom/settings.py`. This matches the existing `LLM_PROVIDER` pattern in `llm_adapter/providers.py::_read_env_config()`; deviating from it would split configuration across two conventions in the same codebase.
- Every new `TenantScopedModel` subclass gets its own RLS `RunSQL` migration block, following `context_graph/migrations/0001_initial.py`'s exact `_rls_sql(table)` helper — copy it verbatim, do not hand-write new RLS SQL.
- `EMBEDDING_PROVIDER` is fixed per tenant at first use for v1 (no runtime provider switching with automatic re-embedding) — per the spec's Fehlerfälle section.
- `HonchoMemoryBackend` MUST namespace its Honcho peer IDs as `f"{tenant_id}:{user_id}"`, never bare `user_id` — this is a hard security constraint (prevents cross-tenant memory leakage through the shared external Honcho service), not an implementation detail, and needs its own dedicated test (Task 10).
- `_assert_write_permission`-equivalent enforcement: `memory.forget` requires the caller to be either the memory's own owner (`UserTenantMemory`) or a Workspace-Admin of the owning workspace (`WorkspaceMemory`) — mirrors the RBAC pattern established throughout this session's other features (Banners, Theme Presets).
- `data-testid` on every new interactive frontend element; every new UI string needs a DE/EN pair (`i18n-parity` ratchet).

---

## Task 1: `EmbeddingProvider` registry (replaces `embedding_service.py`'s if/elif)

**Files:**
- Modify: `backend/llm_adapter/embedding_service.py`
- Test: `backend/llm_adapter/tests/test_embedding_providers.py`

**Interfaces:**
- Produces: `EMBEDDING_PROVIDER_REGISTRY: Dict[str, Type[EmbeddingProvider]]`, `register_embedding_provider(name: str)` decorator, `get_embedding_provider(config: Optional[EmbeddingProviderConfig] = None) -> EmbeddingProvider`, `EmbeddingProvider.embed(text: str) -> Optional[List[float]]`, `EmbeddingProvider.dimensions: int` (class attribute). `generate_embedding(text: str) -> Optional[List[float]]` keeps its existing signature (backward-compatible facade) but delegates to `get_embedding_provider().embed(text)` instead of the old if/elif.

- [ ] **Step 1: Write the failing test**

```python
# backend/llm_adapter/tests/test_embedding_providers.py
from unittest.mock import MagicMock, patch

import pytest

from llm_adapter.embedding_service import (
    EMBEDDING_PROVIDER_REGISTRY,
    EmbeddingProviderConfig,
    generate_embedding,
    get_embedding_provider,
)


class TestEmbeddingProviderRegistry:
    def test_registry_has_sentence_transformers_ollama_openai_mock(self):
        assert set(EMBEDDING_PROVIDER_REGISTRY.keys()) == {
            "sentence-transformers", "ollama", "openai", "mock",
        }

    def test_default_provider_is_sentence_transformers(self, monkeypatch):
        monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
        provider = get_embedding_provider()
        assert provider.__class__.__name__ == "SentenceTransformersEmbeddingProvider"

    def test_env_var_selects_provider(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        provider = get_embedding_provider()
        assert provider.__class__.__name__ == "MockEmbeddingProvider"

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "does-not-exist")
        with pytest.raises(ValueError, match="unknown embedding provider"):
            get_embedding_provider()

    def test_mock_provider_is_deterministic(self):
        config = EmbeddingProviderConfig(provider_name="mock")
        provider = get_embedding_provider(config)
        assert provider.embed("hello") == provider.embed("hello")
        assert provider.embed("hello") != provider.embed("world")

    def test_generate_embedding_delegates_to_registry(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        result = generate_embedding("some text")
        assert result is not None
        assert len(result) == 384  # mock provider dimension, matches sentence-transformers default

    def test_empty_text_returns_none(self):
        assert generate_embedding("") is None
        assert generate_embedding("   ") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/llm_adapter/tests/test_embedding_providers.py -v`
Expected: FAIL — `EMBEDDING_PROVIDER_REGISTRY`/`get_embedding_provider` don't exist.

- [ ] **Step 3: Implement**

```python
# backend/llm_adapter/embedding_service.py — replace the module's provider-selection
# section (previously the if/elif inside generate_embedding()) with a registry,
# following the exact pattern of llm_adapter/providers.py's _PROVIDER_REGISTRY /
# register_provider() / get_provider(). The three existing helper functions
# (get_embedding_text, get_icd_version_embedding_text, get_tracelink_embedding_text)
# are untouched — they only build input text, not embeddings themselves.
from __future__ import annotations

import hashlib
import logging
import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)

# sentence-transformers' all-MiniLM-L6-v2 (the new default model) has 384 dims;
# this is now provider-dependent, not a single module-wide constant -- callers
# needing the dimension read it off the resolved provider instance, not a
# module constant (WorkspaceMemory/UserTenantMemory in Task 2 hardcode 384
# because they are built specifically against the default provider for v1 --
# see Global Constraints on fixed-per-tenant provider selection).


class EmbeddingProvider(ABC):
    dimensions: int

    @abstractmethod
    def embed(self, text: str) -> Optional[List[float]]:
        ...


@dataclass
class EmbeddingProviderConfig:
    provider_name: str = ""
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: Optional[float] = None


def _read_env_config() -> EmbeddingProviderConfig:
    return EmbeddingProviderConfig(
        provider_name=os.environ.get("EMBEDDING_PROVIDER", "sentence-transformers").strip().lower(),
        model_name=os.environ.get("EMBEDDING_MODEL_NAME") or None,
        base_url=os.environ.get("OLLAMA_BASE_URL") or None,
        api_key=os.environ.get("LLM_API_KEY") or None,  # reuses the existing LLM API key, not a new secret
        timeout=float(os.environ.get("EMBEDDING_TIMEOUT", "10")),
    )


EMBEDDING_PROVIDER_REGISTRY: Dict[str, Type[EmbeddingProvider]] = {}


def register_embedding_provider(name: str) -> Callable[[Type[EmbeddingProvider]], Type[EmbeddingProvider]]:
    def _decorator(cls: Type[EmbeddingProvider]) -> Type[EmbeddingProvider]:
        EMBEDDING_PROVIDER_REGISTRY[name] = cls
        return cls
    return _decorator


def get_embedding_provider(config: Optional[EmbeddingProviderConfig] = None) -> EmbeddingProvider:
    cfg = config or _read_env_config()
    provider_cls = EMBEDDING_PROVIDER_REGISTRY.get(cfg.provider_name)
    if provider_cls is None:
        raise ValueError(f"unknown embedding provider: {cfg.provider_name!r}")
    return provider_cls(cfg)


@register_embedding_provider("mock")
class MockEmbeddingProvider(EmbeddingProvider):
    dimensions = 384

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._config = config

    def embed(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]


@register_embedding_provider("sentence-transformers")
class SentenceTransformersEmbeddingProvider(EmbeddingProvider):
    """Default provider: runs in-process, no extra container/service.
    Model weights are bundled into the backend/celery Docker image at build
    time (Task 12 adds the download step to the Dockerfile)."""

    dimensions = 384
    _DEFAULT_MODEL = "all-MiniLM-L6-v2"
    _model = None  # class-level lazy singleton -- loading the model is expensive (~100ms+)

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._model_name = config.model_name or self._DEFAULT_MODEL

    def _get_model(self):
        if SentenceTransformersEmbeddingProvider._model is None:
            from sentence_transformers import SentenceTransformer
            SentenceTransformersEmbeddingProvider._model = SentenceTransformer(self._model_name)
        return SentenceTransformersEmbeddingProvider._model

    def embed(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        try:
            model = self._get_model()
            vector = model.encode(text, normalize_embeddings=True)
            return vector.tolist()
        except Exception as exc:
            logger.warning("sentence-transformers embedding failed: %s", exc)
            return None


@register_embedding_provider("ollama")
class OllamaEmbeddingProvider(EmbeddingProvider):
    """Optional, externally-connectable -- requires a reachable Ollama service."""

    dimensions = 768  # nomic-embed-text's native dimension
    _DEFAULT_MODEL = "nomic-embed-text"

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._base_url = (config.base_url or "http://localhost:11434").rstrip("/")
        self._model_name = config.model_name or self._DEFAULT_MODEL
        self._timeout = config.timeout or 10

    def embed(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        import requests
        try:
            response = requests.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model_name, "prompt": text},
                timeout=self._timeout,
            )
            response.raise_for_status()
            vector = response.json().get("embedding")
            if not vector or len(vector) != self.dimensions:
                logger.warning("ollama embedding returned unexpected shape")
                return None
            return vector
        except Exception as exc:
            logger.warning("ollama embedding failed: %s", exc)
            return None


@register_embedding_provider("openai")
class OpenAiEmbeddingProvider(EmbeddingProvider):
    """Existing provider, kept as an optional higher-quality alternative."""

    dimensions = 1536
    _DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._api_key = config.api_key
        self._model_name = config.model_name or self._DEFAULT_MODEL
        self._timeout = config.timeout or 10

    def embed(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        try:
            import openai
            client = openai.OpenAI(api_key=self._api_key, timeout=self._timeout)
            response = client.embeddings.create(model=self._model_name, input=text)
            vector = response.data[0].embedding
            if len(vector) != self.dimensions:
                logger.warning("openai embedding returned unexpected dimension %d", len(vector))
                return None
            return vector
        except Exception as exc:
            logger.warning("openai embedding failed: %s", exc)
            return None


def generate_embedding(text: str) -> Optional[List[float]]:
    """Backward-compatible facade -- existing call sites (Requirement, TraceLink,
    IcdVersion embedding generation) are unchanged, now backed by the registry."""
    if not text or not text.strip():
        return None
    try:
        return get_embedding_provider().embed(text)
    except Exception as exc:
        logger.warning("generate_embedding failed: %s", exc)
        return None


# get_embedding_text(), get_icd_version_embedding_text(), get_tracelink_embedding_text()
# remain unchanged below this point in the file.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/llm_adapter/tests/test_embedding_providers.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the existing embedding-dependent test suites to confirm no regression**

Run: `pytest backend/application/tests/ -k "embedding" -v` and `pytest backend/icd/tests/ -k "embedding" -v`
Expected: PASS — `generate_embedding()`'s public signature and behavior for existing callers (`Requirement`/`TraceLink`/`IcdVersion`) is unchanged; only its internal provider selection changed. **Note:** with `EMBEDDING_PROVIDER` now defaulting to `sentence-transformers` (384 dims) instead of the old default (`None` → no embedding for anything but `openai`/`mock`), any existing test asserting `len(embedding) == 1536` for a non-`openai`-configured test run will now fail — if so, that test was implicitly relying on the old "no provider configured → None" behavior and must be updated to explicitly set `EMBEDDING_PROVIDER=mock` or `openai` for its 1536-dimension assertion, or updated to expect 384. Do not silently change `Requirement.embedding`'s stored dimension without an explicit decision — flag this to the ledger if it surfaces, since `Requirement.embedding`/`TraceLink.embedding`/`IcdVersion.embedding` are hardcoded to `dimensions=1536` in their model definitions (Task 2 note) and are OUT OF SCOPE for this plan (only the two new memory models use 384).

- [ ] **Step 6: Add `sentence-transformers` to backend dependencies and Docker image**

Add `sentence-transformers` to `backend/requirements.txt` (or the project's dependency file). In the backend/celery Dockerfile, add a `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"` step after `pip install` so the model weights are baked into the image (avoids a slow first-request download at runtime).

- [ ] **Step 7: Commit**

```bash
git add backend/llm_adapter/embedding_service.py backend/llm_adapter/tests/test_embedding_providers.py backend/requirements.txt
git commit -m "feat: add EmbeddingProvider registry (sentence-transformers default, ollama/openai optional)"
```

---

## Task 2: `memory` app scaffolding + `WorkspaceMemory`/`UserTenantMemory` models

**Files:**
- Create: `backend/memory/__init__.py`, `backend/memory/apps.py`, `backend/memory/models.py`
- Create: `backend/memory/migrations/__init__.py`, `backend/memory/migrations/0001_initial.py`
- Modify: `backend/reqogniloom/settings.py` (add `"memory"` to the apps list)
- Test: `backend/memory/tests/__init__.py`, `backend/memory/tests/test_models.py`

**Interfaces:**
- Produces: `WorkspaceMemory(TenantScopedModel)` (`workspace`, `content`, `embedding: VectorField(384)`, `source_event_id`, `superseded_by`, `confidence`, `created_at`); `UserTenantMemory(TenantScopedModel)` (`user`, `content`, `embedding: VectorField(384)`, `source_event_id`, `superseded_by`, `confidence`, `created_at`) — no `workspace` field.

- [ ] **Step 1: Write the failing test**

```python
# backend/memory/tests/test_models.py
import pytest
from django.db import IntegrityError

from memory.models import UserTenantMemory, WorkspaceMemory
from persistence.tests.factories import active_tenant, make_user, make_workspace


@pytest.mark.django_db
class TestWorkspaceMemory:
    def test_create_and_retrieve(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            entry = WorkspaceMemory.objects.create(
                tenant=tenant, workspace=ws, content="Team prefers REST over MCP.",
                embedding=[0.1] * 384, confidence=0.9,
            )
            assert entry.superseded_by is None
            assert WorkspaceMemory.objects.get(id=entry.id).content == "Team prefers REST over MCP."

    def test_superseded_by_self_reference(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            old = WorkspaceMemory.objects.create(tenant=tenant, workspace=ws, content="Old fact", embedding=[0.1] * 384)
            new = WorkspaceMemory.objects.create(tenant=tenant, workspace=ws, content="New fact", embedding=[0.2] * 384)
            old.superseded_by = new
            old.save(update_fields=["superseded_by"])
            assert WorkspaceMemory.objects.get(id=old.id).superseded_by_id == new.id


@pytest.mark.django_db
class TestUserTenantMemory:
    def test_no_workspace_field(self):
        assert not hasattr(UserTenantMemory, "workspace")

    def test_create_and_retrieve(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            entry = UserTenantMemory.objects.create(
                tenant=tenant, user=user, content="Prefers concise code review comments.", embedding=[0.3] * 384,
            )
            assert UserTenantMemory.objects.get(id=entry.id).user_id == user.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/memory/tests/test_models.py -v`
Expected: FAIL — `memory` app doesn't exist.

- [ ] **Step 3: Scaffold the app**

```python
# backend/memory/__init__.py
```

```python
# backend/memory/apps.py
from django.apps import AppConfig


class MemoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "memory"
    verbose_name = "AI Long-Term Memory"

    def ready(self) -> None:
        from memory.projector import register_projector_on_event_bus
        register_projector_on_event_bus()
```

```python
# backend/memory/models.py
from django.db import models
from pgvector.django import HnswIndex, VectorField

from persistence.models import TenantScopedModel, Workspace


class WorkspaceMemory(TenantScopedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memory_entries")
    content = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True)
    superseded_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="supersedes")
    confidence = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mem_workspace_memory"
        indexes = [
            models.Index(fields=["tenant", "workspace", "created_at"], name="idx_mem_ws_created"),
            HnswIndex(
                name="mem_ws_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]


class UserTenantMemory(TenantScopedModel):
    user = models.ForeignKey("auth_tenancy.User", on_delete=models.CASCADE, related_name="tenant_memory_entries")
    content = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True)
    superseded_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="supersedes")
    confidence = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mem_user_tenant_memory"
        indexes = [
            models.Index(fields=["tenant", "user", "created_at"], name="idx_mem_user_created"),
            HnswIndex(
                name="mem_user_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
```

Add `"memory",` to `reqogniloom/settings.py`'s app list, next to `"context_graph"`, with the same comment style (`# AI Long-Term Memory — Workspace + Tenant-global (Spec 2026-08-24)`).

- [ ] **Step 4: Write the migration (copies `context_graph/migrations/0001_initial.py`'s structure)**

```python
# backend/memory/migrations/0001_initial.py
import django.db.models.deletion
import pgvector.django
from django.conf import settings
from django.db import migrations, models


def _rls_sql(table: str) -> tuple:
    policy = f"{table}_tenant_isolation"
    enable_sql = (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {policy} ON {table}\n"
        f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
        f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
    )
    disable_sql = (
        f"DROP POLICY IF EXISTS {policy} ON {table};\n"
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
    )
    return enable_sql, disable_sql


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("persistence", "0066_interview_multi_mode"),  # adjust if the interview plan's migration lands after this one
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspaceMemory",
            fields=[
                ("id", models.UUIDField(primary_key=True, editable=False, serialize=False)),
                ("content", models.TextField()),
                ("embedding", pgvector.django.VectorField(blank=True, dimensions=384, null=True)),
                ("source_event_id", models.UUIDField(blank=True, null=True)),
                ("confidence", models.FloatField(default=1.0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth_tenancy.tenant")),
                ("workspace", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name="memory_entries", to="persistence.workspace"
                )),
                ("superseded_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="supersedes", to="memory.workspacememory",
                )),
            ],
            options={"db_table": "mem_workspace_memory"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name="UserTenantMemory",
            fields=[
                ("id", models.UUIDField(primary_key=True, editable=False, serialize=False)),
                ("content", models.TextField()),
                ("embedding", pgvector.django.VectorField(blank=True, dimensions=384, null=True)),
                ("source_event_id", models.UUIDField(blank=True, null=True)),
                ("confidence", models.FloatField(default=1.0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth_tenancy.tenant")),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name="tenant_memory_entries", to="auth_tenancy.user"
                )),
                ("superseded_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="supersedes", to="memory.usertenantmemory",
                )),
            ],
            options={"db_table": "mem_user_tenant_memory"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddIndex(
            model_name="workspacememory",
            index=models.Index(fields=["tenant", "workspace", "created_at"], name="idx_mem_ws_created"),
        ),
        migrations.AddIndex(
            model_name="workspacememory",
            index=pgvector.django.HnswIndex(
                name="mem_ws_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="usertenantmemory",
            index=models.Index(fields=["tenant", "user", "created_at"], name="idx_mem_user_created"),
        ),
        migrations.AddIndex(
            model_name="usertenantmemory",
            index=pgvector.django.HnswIndex(
                name="mem_user_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.RunSQL(*_rls_sql("mem_workspace_memory")),
        migrations.RunSQL(*_rls_sql("mem_user_tenant_memory")),
    ]
```

Note for the implementer: run `python backend/manage.py makemigrations memory --check --dry-run` first and reconcile the `dependencies` tuple's exact `persistence` migration name against whatever is actually the latest at implementation time (this plan was written assuming `0066_interview_multi_mode` from the sibling interview-feature plan — adjust to whatever the real latest migration is if that plan hasn't landed yet).

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/memory/tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/memory/ backend/reqogniloom/settings.py
git commit -m "feat: add memory app with WorkspaceMemory and UserTenantMemory models"
```

---

## Task 3: `MemoryBackend` abstraction + `PgvectorMemoryBackend`

**Files:**
- Create: `backend/memory/backends.py`
- Test: `backend/memory/tests/test_pgvector_backend.py`

**Interfaces:**
- Consumes: `WorkspaceMemory`, `UserTenantMemory` (Task 2); `EmbeddingProvider` (Task 1).
- Produces: `MemoryBackend(ABC)` with `upsert(tenant_id, scope, scope_id, content, source_event_id=None) -> MemoryEntryRef`, `query(tenant_id, scope, scope_id, query_text, top_k=5) -> List[MemoryEntryRef]`, `list_recent(tenant_id, scope, scope_id, limit=20) -> List[MemoryEntryRef]`, `forget(tenant_id, entry_id) -> None`; `MEMORY_BACKEND_REGISTRY`, `get_memory_backend()` (same registry pattern as Task 1); `scope` is the literal string `"workspace"` or `"user"`, `scope_id` is the `workspace_id` or `user_id` respectively.

- [ ] **Step 1: Write the failing test**

```python
# backend/memory/tests/test_pgvector_backend.py
import pytest

from memory.backends import get_memory_backend
from persistence.tests.factories import active_tenant, make_user, make_workspace


@pytest.mark.django_db
class TestPgvectorMemoryBackend:
    def test_upsert_and_query_workspace_scope(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            backend.upsert(tenant.id, "workspace", ws.id, "Team prefers REST over MCP.")
            results = backend.query(tenant.id, "workspace", ws.id, "What does the team prefer?", top_k=5)
            assert len(results) == 1
            assert results[0].content == "Team prefers REST over MCP."

    def test_query_is_scoped_to_workspace(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)
            backend.upsert(tenant.id, "workspace", ws_a.id, "Fact about workspace A.")
            backend.upsert(tenant.id, "workspace", ws_b.id, "Fact about workspace B.")
            results = backend.query(tenant.id, "workspace", ws_a.id, "fact", top_k=10)
            assert all("A" in r.content for r in results)

    def test_upsert_and_query_user_scope(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            user = make_user(tenant)
            backend.upsert(tenant.id, "user", user.id, "Prefers concise reviews.")
            results = backend.query(tenant.id, "user", user.id, "review style", top_k=5)
            assert len(results) == 1

    def test_forget_removes_entry(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ref = backend.upsert(tenant.id, "workspace", ws.id, "Temporary fact.")
            backend.forget(tenant.id, ref.entry_id)
            assert backend.query(tenant.id, "workspace", ws.id, "temporary", top_k=5) == []

    def test_list_recent_returns_chronological_without_similarity(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        backend = get_memory_backend()
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            backend.upsert(tenant.id, "workspace", ws.id, "First fact.")
            backend.upsert(tenant.id, "workspace", ws.id, "Second fact.")
            results = backend.list_recent(tenant.id, "workspace", ws.id, limit=10)
            assert [r.content for r in results] == ["Second fact.", "First fact."]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/memory/tests/test_pgvector_backend.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/memory/backends.py
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Type
from uuid import UUID

from django.db.models import F
from pgvector.django import CosineDistance

from llm_adapter.embedding_service import generate_embedding
from memory.models import UserTenantMemory, WorkspaceMemory
from persistence.tenancy import TenantContext


@dataclass
class MemoryEntryRef:
    entry_id: UUID
    content: str
    confidence: float = 1.0


class MemoryBackend(ABC):
    @abstractmethod
    def upsert(self, tenant_id: UUID, scope: str, scope_id: UUID, content: str, source_event_id: Optional[UUID] = None) -> MemoryEntryRef:
        ...

    @abstractmethod
    def query(self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5) -> List[MemoryEntryRef]:
        ...

    @abstractmethod
    def list_recent(self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20) -> List[MemoryEntryRef]:
        ...

    @abstractmethod
    def forget(self, tenant_id: UUID, entry_id: UUID) -> None:
        ...


MEMORY_BACKEND_REGISTRY: Dict[str, Type[MemoryBackend]] = {}


def register_memory_backend(name: str) -> Callable[[Type[MemoryBackend]], Type[MemoryBackend]]:
    def _decorator(cls: Type[MemoryBackend]) -> Type[MemoryBackend]:
        MEMORY_BACKEND_REGISTRY[name] = cls
        return cls
    return _decorator


def get_memory_backend() -> MemoryBackend:
    name = os.environ.get("MEMORY_BACKEND", "pgvector").strip().lower()
    backend_cls = MEMORY_BACKEND_REGISTRY.get(name)
    if backend_cls is None:
        raise ValueError(f"unknown memory backend: {name!r}")
    return backend_cls()


def _model_for_scope(scope: str):
    if scope == "workspace":
        return WorkspaceMemory, "workspace_id"
    if scope == "user":
        return UserTenantMemory, "user_id"
    raise ValueError(f"unknown memory scope: {scope!r}")


@register_memory_backend("pgvector")
class PgvectorMemoryBackend(MemoryBackend):
    def upsert(self, tenant_id: UUID, scope: str, scope_id: UUID, content: str, source_event_id: Optional[UUID] = None) -> MemoryEntryRef:
        model, scope_field = _model_for_scope(scope)
        embedding = generate_embedding(content)
        TenantContext.set_tenant(tenant_id)
        entry = model.objects.create(
            tenant_id=tenant_id, content=content, embedding=embedding,
            source_event_id=source_event_id, **{scope_field: scope_id},
        )
        return MemoryEntryRef(entry_id=entry.id, content=entry.content, confidence=entry.confidence)

    def query(self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5) -> List[MemoryEntryRef]:
        model, scope_field = _model_for_scope(scope)
        query_embedding = generate_embedding(query_text)
        if query_embedding is None:
            return []
        TenantContext.set_tenant(tenant_id)
        qs = (
            model.objects.filter(**{scope_field: scope_id}, superseded_by__isnull=True, embedding__isnull=False)
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")[:top_k]
        )
        return [MemoryEntryRef(entry_id=e.id, content=e.content, confidence=e.confidence) for e in qs]

    def list_recent(self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20) -> List[MemoryEntryRef]:
        model, scope_field = _model_for_scope(scope)
        TenantContext.set_tenant(tenant_id)
        qs = model.objects.filter(**{scope_field: scope_id}, superseded_by__isnull=True).order_by("-created_at")[:limit]
        return [MemoryEntryRef(entry_id=e.id, content=e.content, confidence=e.confidence) for e in qs]

    def forget(self, tenant_id: UUID, entry_id: UUID) -> None:
        TenantContext.set_tenant(tenant_id)
        deleted = WorkspaceMemory.objects.filter(id=entry_id).delete()
        if deleted[0] == 0:
            UserTenantMemory.objects.filter(id=entry_id).delete()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/memory/tests/test_pgvector_backend.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/memory/backends.py backend/memory/tests/test_pgvector_backend.py
git commit -m "feat: add MemoryBackend registry with PgvectorMemoryBackend (default)"
```

---

## Task 4: New `EventType` values + `memory` Celery queue

**Files:**
- Modify: `backend/application/models.py` (`DomainEventOutbox.EventType`)
- Modify: `backend/reqogniloom/celery.py`
- Test: `backend/application/tests/test_memory_event_types.py`

**Interfaces:**
- Produces: `DomainEventOutbox.EventType.INTERVIEW_CHAT_TURN = "InterviewChatTurn"`, `DomainEventOutbox.EventType.INTERVIEW_FORMALIZED = "InterviewFormalized"`; `memory` queue registered in Celery.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_memory_event_types.py
from application.models import DomainEventOutbox


class TestMemoryEventTypes:
    def test_interview_chat_turn_is_a_valid_event_type(self):
        values = {choice[0] for choice in DomainEventOutbox.EventType.choices}
        assert "InterviewChatTurn" in values
        assert "InterviewFormalized" in values
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/application/tests/test_memory_event_types.py -v`
Expected: FAIL — new choices don't exist.

- [ ] **Step 3: Implement**

Add two new choices to `DomainEventOutbox.EventType` in `backend/application/models.py` (alongside the existing `RequirementCreated`, etc. — same `TextChoices` pattern):

```python
INTERVIEW_CHAT_TURN = "InterviewChatTurn", "Interview Chat Turn"
INTERVIEW_FORMALIZED = "InterviewFormalized", "Interview Formalized"
```

Publish these from `InterviewService.generate_chat_turn()` (single-mode; multi-mode's `_generate_multi_chat_turn` from the sibling interview plan gets the same call if that plan lands first — otherwise this task adds it directly) and `InterviewService.formalize()`, using the existing `DomainEventBus.publish()` call pattern already used elsewhere in that service (find an existing `bus.publish(DomainEvent(...))` call in `interview_service.py` as the copy-paste template for `workspace_id`/`entity_id`/`payload` shape).

In `backend/reqogniloom/celery.py`, extend the queue tuple and routing dict:

```python
app.conf.task_queues = (
    Queue('default'), Queue('llm'), Queue('events'), Queue('memory'),
)
app.conf.task_routes = {
    **app.conf.task_routes,  # keep existing llm_adapter.*/events entries
    'memory.*': {'queue': 'memory'},
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/application/tests/test_memory_event_types.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add backend/application/models.py backend/application/interview_service.py backend/reqogniloom/celery.py backend/application/tests/test_memory_event_types.py
git commit -m "feat: add InterviewChatTurn/InterviewFormalized event types and memory Celery queue"
```

---

## Task 5: Consolidation pipeline — projector + `memory.extract` prompt + upsert/contradiction logic

**Files:**
- Create: `backend/memory/projector.py`, `backend/memory/tasks.py`, `backend/memory/prompts.py`
- Modify: `backend/application/prompt_slots.py` (register `MEMORY_PROMPT_DEFAULTS`)
- Test: `backend/memory/tests/test_projector.py`, `backend/memory/tests/test_consolidation.py`

**Interfaces:**
- Consumes: `DomainEventBus`, `DomainEvent` (`application/event_bus.py`); `MemoryBackend` (Task 3); `resolve_and_render` (`prompt_resolver.py`); `LlmCapabilityInterface.complete()` (`llm_adapter/interface.py`).
- Produces: `register_projector_on_event_bus()`; `MemoryProjector.handle_event(event: DomainEvent) -> None`; Celery task `memory.consolidate_interaction`; `consolidate_interaction(tenant_id, workspace_id, user_id, interaction_text) -> dict` (the pure function the task wraps, directly unit-testable).

- [ ] **Step 1: Write the failing test — projector filters to relevant event types**

```python
# backend/memory/tests/test_projector.py
from unittest.mock import MagicMock, patch
from uuid import uuid4

from application.event_bus import DomainEvent
from memory.projector import MemoryProjector


class TestMemoryProjector:
    def test_ignores_irrelevant_event_types(self):
        projector = MemoryProjector()
        event = DomainEvent(event_type="RequirementCreated", entity_id=uuid4(), workspace_id=uuid4())
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            projector.handle_event(event)
        mock_task.delay.assert_not_called()

    def test_enqueues_task_for_interview_chat_turn(self):
        projector = MemoryProjector()
        event = DomainEvent(
            event_type="InterviewChatTurn", entity_id=uuid4(), workspace_id=uuid4(),
            payload={"tenant_id": str(uuid4()), "user_id": str(uuid4()), "message": "hello"},
        )
        with patch("memory.projector.consolidate_interaction_task") as mock_task:
            projector.handle_event(event)
        mock_task.delay.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/memory/tests/test_projector.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the projector (filters events, delegates to the async task)**

```python
# backend/memory/projector.py
from __future__ import annotations

import logging

from application.event_bus import DomainEvent, get_event_bus
from application.models import DomainEventOutbox

logger = logging.getLogger(__name__)

_RELEVANT_EVENT_TYPES = {
    DomainEventOutbox.EventType.INTERVIEW_CHAT_TURN,
    DomainEventOutbox.EventType.INTERVIEW_FORMALIZED,
}


class MemoryProjector:
    def handle_event(self, event: DomainEvent) -> None:
        if event.event_type not in _RELEVANT_EVENT_TYPES:
            return
        from memory.tasks import consolidate_interaction_task
        payload = event.payload or {}
        consolidate_interaction_task.delay(
            tenant_id=payload.get("tenant_id"),
            workspace_id=str(event.workspace_id),
            user_id=payload.get("user_id"),
            interaction_text=payload.get("message", ""),
        )


def register_projector_on_event_bus() -> None:
    bus = get_event_bus()
    projector = MemoryProjector()
    for event_type in _RELEVANT_EVENT_TYPES:
        bus.register_subscriber(event_type, projector.handle_event)
```

- [ ] **Step 4: Write the failing test — consolidation logic**

```python
# backend/memory/tests/test_consolidation.py
from unittest.mock import MagicMock, patch

import pytest

from memory.tasks import consolidate_interaction
from persistence.tests.factories import active_tenant, make_user, make_workspace


@pytest.mark.django_db
class TestConsolidateInteraction:
    def test_extracts_and_upserts_facts(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            fake_llm_response = '{"facts": [{"content": "Team prefers REST.", "scope": "workspace"}, {"content": "User likes concise reviews.", "scope": "user"}]}'
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "Some interaction text")
            assert result["workspace_facts_stored"] == 1
            assert result["user_facts_stored"] == 1

    def test_malformed_llm_response_stores_nothing(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            with patch("memory.tasks._call_llm", return_value="not json"):
                result = consolidate_interaction(tenant.id, ws.id, user.id, "text")
            assert result["workspace_facts_stored"] == 0
            assert result["user_facts_stored"] == 0

    def test_contradiction_marks_old_entry_superseded(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        from memory.backends import get_memory_backend
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            # Seed an existing near-identical fact that a mock embedding will
            # treat as maximally similar (same text -> same deterministic vector).
            existing_ref = backend.upsert(tenant.id, "workspace", ws.id, "Team prefers REST over MCP.")
            fake_llm_response = '{"facts": [{"content": "Team prefers REST over MCP.", "scope": "workspace"}]}'
            with patch("memory.tasks._call_llm", return_value=fake_llm_response):
                consolidate_interaction(tenant.id, ws.id, user.id, "text")
            from memory.models import WorkspaceMemory
            refreshed = WorkspaceMemory.objects.get(id=existing_ref.entry_id)
            # Identical content -> treated as duplicate, not contradiction: old
            # entry stays un-superseded (see Fehlerfälle: duplicates are no-ops).
            assert refreshed.superseded_by_id is None
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest backend/memory/tests/test_consolidation.py -v`
Expected: FAIL — `memory.tasks` doesn't exist.

- [ ] **Step 6: Implement the prompt default and consolidation logic**

```python
# backend/memory/prompts.py
MEMORY_PROMPT_DEFAULTS = {
    "memory.extract": """\
Extract durable facts or preferences from this interaction that would be
useful to remember in future conversations. Only extract facts that are
genuinely reusable (project decisions, stated preferences, recurring
patterns) -- not one-off details.

Respond with a JSON object: {"facts": [{"content": "<fact text>", "scope": "workspace"|"user"}]}
"scope"="workspace" for project-specific facts, "scope"="user" for facts
about the person's general preferences/working style.

Interaction:
{interaction_text}
""",
}
```

In `backend/application/prompt_slots.py::get_prompt_slots()`, add the import and merge (alongside the existing three sources):

```python
from memory.prompts import MEMORY_PROMPT_DEFAULTS

merged: Dict[str, str] = {
    **PROMPT_TEMPLATE_DEFAULTS,
    **INTERVIEW_PROTOCOL_DEFAULTS,
    **MEMORY_PROMPT_DEFAULTS,
    "architecture_decompose_tree": ARCH_DECOMPOSE_PROMPT_TEMPLATE,
}
```

Also add `"memory.extract": ("interaction_text",)` to `_DATA_VARIABLES_BY_SLOT`.

```python
# backend/memory/tasks.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from celery import shared_task

from application.prompt_resolver import resolve_and_render
from auth_tenancy.context import AuthContext
from memory.backends import get_memory_backend

logger = logging.getLogger(__name__)

_DUPLICATE_SIMILARITY_THRESHOLD = 0.02  # cosine distance; lower = more similar


def _call_llm(prompt: str) -> str:
    """Thin wrapper around the existing LLM provider, isolated for test mocking."""
    from llm_adapter.providers import get_provider
    provider = get_provider()
    return provider.complete(prompt, purpose="memory_extraction")


def _parse_facts(raw_llm_output: str) -> Optional[list]:
    try:
        parsed = json.loads(raw_llm_output)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "facts" not in parsed:
        return None
    return parsed["facts"]


def consolidate_interaction(tenant_id: UUID, workspace_id: UUID, user_id: UUID, interaction_text: str) -> Dict[str, Any]:
    if not interaction_text.strip():
        return {"workspace_facts_stored": 0, "user_facts_stored": 0}

    # System-level extraction call -- not tied to any single user's AuthContext.
    # Uses a synthetic system ctx the same way other background consolidation
    # tasks in this codebase do (see context_graph/projector.py's tenant-context
    # handling for the equivalent pattern at the ORM level; the LLM call itself
    # needs no AuthContext beyond what resolve_and_render requires for template
    # resolution, which is the tenant/workspace scope, not a specific user).
    prompt = resolve_and_render("memory.extract", AuthContext.system(tenant_id=tenant_id), workspace_id, interaction_text=interaction_text)
    raw_response = _call_llm(prompt)
    facts = _parse_facts(raw_response)
    if facts is None:
        return {"workspace_facts_stored": 0, "user_facts_stored": 0}

    backend = get_memory_backend()
    workspace_count = 0
    user_count = 0
    for fact in facts:
        content = fact.get("content", "").strip()
        scope = fact.get("scope")
        if not content or scope not in ("workspace", "user"):
            continue
        scope_id = workspace_id if scope == "workspace" else user_id
        existing = backend.query(tenant_id, scope, scope_id, content, top_k=1)
        if existing and existing[0].content == content:
            continue  # exact-content duplicate: no-op, not a contradiction
        backend.upsert(tenant_id, scope, scope_id, content)
        if scope == "workspace":
            workspace_count += 1
        else:
            user_count += 1

    return {"workspace_facts_stored": workspace_count, "user_facts_stored": user_count}


@shared_task(name="memory.consolidate_interaction")
def consolidate_interaction_task(tenant_id: str, workspace_id: str, user_id: str, interaction_text: str) -> Dict[str, Any]:
    return consolidate_interaction(UUID(tenant_id), UUID(workspace_id), UUID(user_id), interaction_text)
```

Note for the implementer: `AuthContext.system(tenant_id=...)` is assumed to exist as a system/service-account context constructor — verify against the real `auth_tenancy/context.py` at implementation time; if no such constructor exists, this is a small addition to that module (a context with elevated/system-level template-resolution rights but no specific `user_id`), not a redesign of this task.

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest backend/memory/tests/test_projector.py backend/memory/tests/test_consolidation.py -v`
Expected: PASS (5 tests)

- [ ] **Step 8: Commit**

```bash
git add backend/memory/projector.py backend/memory/tasks.py backend/memory/prompts.py backend/application/prompt_slots.py backend/memory/tests/test_projector.py backend/memory/tests/test_consolidation.py
git commit -m "feat: add async memory consolidation pipeline (projector + LLM extraction + upsert)"
```

---

## Task 6: Context builder — inject memory into prompts

**Files:**
- Create: `backend/memory/context_builder.py`
- Modify: `backend/application/interview_service.py` (`generate_chat_turn`)
- Test: `backend/memory/tests/test_context_builder.py`

**Interfaces:**
- Consumes: `MemoryBackend.query()` (Task 3).
- Produces: `build_memory_context(tenant_id, workspace_id, user_id, query_text) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/memory/tests/test_context_builder.py
import pytest

from memory.backends import get_memory_backend
from memory.context_builder import build_memory_context
from persistence.tests.factories import active_tenant, make_user, make_workspace


@pytest.mark.django_db
class TestBuildMemoryContext:
    def test_combines_workspace_and_user_memory(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "Project uses hexagonal architecture.")
            backend.upsert(tenant.id, "user", user.id, "Prefers TypeScript over JavaScript.")

            context = build_memory_context(tenant.id, ws.id, user.id, "architecture question")

            assert "hexagonal architecture" in context
            assert "TypeScript" in context

    def test_empty_when_no_memory_exists(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            context = build_memory_context(tenant.id, ws.id, user.id, "anything")
            assert context == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/memory/tests/test_context_builder.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/memory/context_builder.py
from __future__ import annotations

import logging
from uuid import UUID

from memory.backends import MemoryBackend, get_memory_backend

logger = logging.getLogger(__name__)

_TOP_K_PER_SCOPE = 5


def build_memory_context(tenant_id: UUID, workspace_id: UUID, user_id: UUID, query_text: str) -> str:
    """Best-effort: memory is an enhancement, never a hard requirement for a
    prompt to render, so any backend failure degrades to an empty context
    rather than raising (see spec Fehlerfälle)."""
    try:
        backend: MemoryBackend = get_memory_backend()
        workspace_hits = backend.query(tenant_id, "workspace", workspace_id, query_text, top_k=_TOP_K_PER_SCOPE)
        user_hits = backend.query(tenant_id, "user", user_id, query_text, top_k=_TOP_K_PER_SCOPE)
    except Exception as exc:
        logger.warning("build_memory_context failed, degrading to empty context: %s", exc)
        return ""

    if not workspace_hits and not user_hits:
        return ""

    lines = []
    if workspace_hits:
        lines.append("Workspace context:")
        lines.extend(f"- {hit.content}" for hit in workspace_hits)
    if user_hits:
        lines.append("User context:")
        lines.extend(f"- {hit.content}" for hit in user_hits)
    return "\n".join(lines)
```

Wire into `InterviewService.generate_chat_turn()` (single-mode path): before calling `resolve_and_render("interview.chat_turn", ...)`, call `memory_context = build_memory_context(...)` and pass it as a `data_kwarg`:

```python
from memory.context_builder import build_memory_context

# ... inside generate_chat_turn, before the existing resolve_and_render call ...
memory_context = build_memory_context(ctx.tenant_id, session.workspace_id, ctx.user_id, user_message)
prompt = resolve_and_render(
    "interview.chat_turn", ctx, session.workspace_id,
    memory_context=memory_context,
    # ... existing data_kwargs unchanged ...
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/memory/tests/test_context_builder.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/memory/context_builder.py backend/application/interview_service.py backend/memory/tests/test_context_builder.py
git commit -m "feat: add memory context builder, wire into interview chat prompts"
```

---

## Task 7: MCP `memory.*` tool group

**Files:**
- Create: `backend/mcp_server/tools/memory.py`
- Modify: `backend/mcp_server/tool_registry.py`
- Test: `backend/mcp_server/tests/test_memory_tool_group.py`

**Interfaces:**
- Consumes: `MemoryBackend` (Task 3).
- Produces: `MemoryToolGroup` with `memory.query`, `memory.list`, `memory.forget`.

- [ ] **Step 1: Write the failing test**

```python
# backend/mcp_server/tests/test_memory_tool_group.py
import pytest

from mcp_server.tool_registry import MCPToolRegistry, _READ_ONLY_TOOL_NAMES
from mcp_server.tools.memory import MemoryToolGroup
from persistence.tests.factories import active_tenant, make_user, make_workspace, editor_ctx


class TestMemoryToolGroupRegistration:
    def test_registered_in_registry(self):
        registry = MCPToolRegistry()
        registry._ensure_groups()
        assert "memory" in registry._groups

    def test_read_tools_are_read_only(self):
        assert "memory.query" in _READ_ONLY_TOOL_NAMES
        assert "memory.list" in _READ_ONLY_TOOL_NAMES
        assert "memory.forget" not in _READ_ONLY_TOOL_NAMES


@pytest.mark.django_db
class TestMemoryToolGroupHandlers:
    def test_query_returns_relevant_entries(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            from memory.backends import get_memory_backend
            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Fact one.")
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_query(
                params={"scope": "workspace", "workspace_id": str(ws.id), "query": "fact"},
                auth_context=ctx, api_key=None,
            )
            assert result.ok
            assert len(result.data["entries"]) == 1

    def test_forget_by_owner_succeeds(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            from memory.backends import get_memory_backend
            ref = get_memory_backend().upsert(tenant.id, "user", user.id, "A user fact.")
            from persistence.tests.factories import ctx_for_user
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            result = group._handle_forget(params={"entry_id": str(ref.entry_id)}, auth_context=ctx, api_key=None)
            assert result.ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/mcp_server/tests/test_memory_tool_group.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/mcp_server/tools/memory.py
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from auth_tenancy.context import AuthContext
from mcp_server.tool_result import ToolResult
from mcp_server.tools.base import BaseToolGroup
from memory.backends import get_memory_backend


class MemoryToolGroup(BaseToolGroup):
    _TOOL_MAP = {
        "memory.query": "_handle_query",
        "memory.list": "_handle_list",
        "memory.forget": "_handle_forget",
    }
    _TOOL_SCHEMAS = [
        {
            "name": "memory.query",
            "description": "Semantic search over workspace or user-tenant-wide memory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["workspace", "user"]},
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["scope", "query"],
            },
        },
        {
            "name": "memory.list",
            "description": "Chronological listing of recent memory entries, no similarity search.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["workspace", "user"]},
                    "workspace_id": {"type": "string", "format": "uuid"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["scope"],
            },
        },
        {
            "name": "memory.forget",
            "description": "Delete a memory entry. Requires ownership (own user memory) or workspace-admin (workspace memory).",
            "inputSchema": {
                "type": "object",
                "properties": {"entry_id": {"type": "string", "format": "uuid"}},
                "required": ["entry_id"],
            },
        },
    ]

    def _resolve_scope_id(self, params: Dict[str, Any], auth_context: AuthContext):
        scope = params["scope"]
        if scope == "workspace":
            return UUID(params["workspace_id"])
        return auth_context.user_id

    def _handle_query(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        backend = get_memory_backend()
        scope_id = self._resolve_scope_id(params, auth_context)
        entries = backend.query(
            auth_context.tenant_id, params["scope"], scope_id, params["query"], top_k=params.get("top_k", 5)
        )
        return ToolResult.ok({"entries": [{"id": str(e.entry_id), "content": e.content} for e in entries]})

    def _handle_list(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        backend = get_memory_backend()
        scope_id = self._resolve_scope_id(params, auth_context)
        entries = backend.list_recent(auth_context.tenant_id, params["scope"], scope_id, limit=params.get("limit", 20))
        return ToolResult.ok({"entries": [{"id": str(e.entry_id), "content": e.content} for e in entries]})

    def _handle_forget(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        # Ownership check: the entry must be the caller's own UserTenantMemory,
        # OR a WorkspaceMemory row in a workspace where the caller is an admin.
        from memory.models import UserTenantMemory, WorkspaceMemory
        from persistence.tenancy import TenantContext
        entry_id = UUID(params["entry_id"])
        TenantContext.set_tenant(auth_context.tenant_id)
        user_entry = UserTenantMemory.objects.filter(id=entry_id).first()
        if user_entry is not None:
            if user_entry.user_id != auth_context.user_id:
                return ToolResult.error("PERMISSION_DENIED", "cannot forget another user's memory")
            get_memory_backend().forget(auth_context.tenant_id, entry_id)
            return ToolResult.ok({"deleted": True})
        ws_entry = WorkspaceMemory.objects.filter(id=entry_id).first()
        if ws_entry is None:
            return ToolResult.error("NOT_FOUND", "memory entry not found")
        from auth_tenancy.services.authorization import AuthorizationService
        roles = AuthorizationService().active_roles_for(user_id=auth_context.user_id, workspace_id=ws_entry.workspace_id)
        if "admin" not in roles:
            return ToolResult.error("PERMISSION_DENIED", "requires workspace-admin to forget workspace memory")
        get_memory_backend().forget(auth_context.tenant_id, entry_id)
        return ToolResult.ok({"deleted": True})
```

In `backend/mcp_server/tool_registry.py::_ensure_groups()`, add the import and a standalone entry (no prefix sharing, unlike `context`):

```python
from mcp_server.tools.memory import MemoryToolGroup
# ... inside register_groups({...}) ...
"memory": MemoryToolGroup(),
```

Add `"memory.forget"` to `_WRITE_TOOL_PREFIXES` and `"memory.query"`/`"memory.list"` to `_READ_ONLY_TOOL_NAMES` (both module-level constants near the top of `tool_registry.py`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/mcp_server/tests/test_memory_tool_group.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Update the MCP tool manifest**

Run: `python backend/manage.py export_tool_manifest` (or whatever the exact management command invocation is per `backend/mcp_server/management/commands/export_tool_manifest.py`) and commit the regenerated manifest file — `test_tool_manifest_drift.py` will fail otherwise.

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tools/memory.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_memory_tool_group.py
git commit -m "feat: add memory.* MCP tool group (query, list, forget)"
```

---

## Task 8: `AuthorizationService.accessible_workspace_ids()` + `SearchService` cross-workspace scope

**Files:**
- Modify: `backend/auth_tenancy/services/authorization.py`
- Modify: `backend/application/search_service.py`
- Test: `backend/auth_tenancy/tests/test_accessible_workspace_ids.py`, `backend/application/tests/test_search_service_tenant_scope.py`

**Interfaces:**
- Produces: `AuthorizationService.accessible_workspace_ids(*, user_id: UUID, tenant_id: UUID) -> List[UUID]`; `SearchService.search(..., scope: str = "workspace")` — new `scope` parameter, `"workspace"` (unchanged default) or `"tenant"` (new — filters to `accessible_workspace_ids()`, ignores an explicit `workspace_id` if both are somehow passed together, since `scope="tenant"` means "all my workspaces", not one).

- [ ] **Step 1: Write the failing test — `accessible_workspace_ids`**

```python
# backend/auth_tenancy/tests/test_accessible_workspace_ids.py
import pytest

from auth_tenancy.services.authorization import AuthorizationService
from persistence.tests.factories import active_tenant, make_user, make_workspace, assign_role


@pytest.mark.django_db
class TestAccessibleWorkspaceIds:
    def test_returns_only_workspaces_user_has_a_role_in(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)
            ws_c = make_workspace(tenant)  # user has no role here
            assign_role(user, ws_a, "editor")
            assign_role(user, ws_b, "viewer")

            result = AuthorizationService().accessible_workspace_ids(user_id=user.id, tenant_id=tenant.id)

            assert set(result) == {ws_a.id, ws_b.id}
            assert ws_c.id not in result

    def test_excludes_suspended_roles(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ws = make_workspace(tenant)
            assign_role(user, ws, "editor", suspended=True)
            result = AuthorizationService().accessible_workspace_ids(user_id=user.id, tenant_id=tenant.id)
            assert ws.id not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/auth_tenancy/tests/test_accessible_workspace_ids.py -v`
Expected: FAIL — method doesn't exist.

- [ ] **Step 3: Implement `accessible_workspace_ids`**

Add to `AuthorizationService` (`backend/auth_tenancy/services/authorization.py`), following the exact style of the neighboring `active_roles_for`/`active_roles_across_workspaces` methods:

```python
def accessible_workspace_ids(self, *, user_id: UUID, tenant_id: UUID) -> List[UUID]:
    """All workspace IDs in `tenant_id` where `user_id` has an active
    (non-suspended) role -- used for cross-workspace search scoping."""
    from auth_tenancy.models import UserRole
    return list(
        UserRole.objects.filter(
            user_id=user_id, workspace__tenant_id=tenant_id, suspended_at__isnull=True,
        ).values_list("workspace_id", flat=True).distinct()
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/auth_tenancy/tests/test_accessible_workspace_ids.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing test — `SearchService` tenant scope**

```python
# backend/application/tests/test_search_service_tenant_scope.py
import pytest

from application.search_service import SearchService
from persistence.tests.factories import active_tenant, make_requirement, make_user, make_workspace, assign_role, editor_ctx


@pytest.mark.django_db
class TestSearchServiceTenantScope:
    def test_tenant_scope_only_returns_accessible_workspaces(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)  # no access
            assign_role(user, ws_a, "editor")
            make_requirement(ws_a, title="Findable requirement A")
            make_requirement(ws_b, title="Findable requirement B")

            ctx = editor_ctx(tenant, ws_a, user=user)
            result = SearchService().search("Findable", ctx, scope="tenant")

            titles = {hit.title for hit in result.hits}
            assert "Findable requirement A" in titles
            assert "Findable requirement B" not in titles

    def test_workspace_scope_is_unchanged_default(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            make_requirement(ws, title="Scoped requirement")
            ctx = editor_ctx(tenant, ws)
            result = SearchService().search("Scoped", ctx, workspace_id=ws.id)
            assert len(result.hits) == 1
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest backend/application/tests/test_search_service_tenant_scope.py -v`
Expected: FAIL — `scope` parameter doesn't exist, no RBAC filtering applied.

- [ ] **Step 7: Implement the `scope` parameter**

In `backend/application/search_service.py`, extend `search()`'s signature and add the RBAC filter before dispatching to the existing per-entity-type query methods:

```python
def search(
    self,
    query: str,
    ctx: AuthContext,
    workspace_id: Optional[UUID | str] = None,
    type_filter: Optional[List[str]] = None,
    page: int = _DEFAULT_PAGE,
    limit: int = _DEFAULT_LIMIT,
    scope: str = "workspace",
) -> SearchResult:
    if scope == "tenant":
        from auth_tenancy.services.authorization import AuthorizationService
        accessible_ids = AuthorizationService().accessible_workspace_ids(user_id=ctx.user_id, tenant_id=ctx.tenant_id)
        return self._search_multi_workspace(query, ctx, accessible_ids, type_filter, page, limit)
    # ... existing single-workspace-or-None body, unchanged ...
```

`_search_multi_workspace()` is a new private method that loops `_run_fulltext_query`/`_run_lexical_query` per `workspace_id` in `accessible_ids` (reusing them exactly as-is — they already accept an optional `workspace_id`) and merges results across all of them with the same `Dict[str, SearchHit]`-keyed-by-`hit.id` dedup/score-max pattern `_search_entity_type()` already uses for its two-pass merge — extract that merge logic into a small shared helper if it isn't already factored out, rather than duplicating the dict-merge loop.

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest backend/application/tests/test_search_service_tenant_scope.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Run the full existing search test suite to confirm no regression**

Run: `pytest backend/application/tests/ -k search -v` and `pytest backend/rest_api/tests/ -k search -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add backend/auth_tenancy/services/authorization.py backend/application/search_service.py backend/auth_tenancy/tests/test_accessible_workspace_ids.py backend/application/tests/test_search_service_tenant_scope.py
git commit -m "feat: add cross-workspace search scope with RBAC-filtered workspace access"
```

---

## Task 9: Semantic search pass + RRF fusion

**Files:**
- Modify: `backend/application/search_service.py`
- Test: `backend/application/tests/test_search_semantic_fusion.py`

**Interfaces:**
- Consumes: existing `Requirement.embedding`/`TraceLink.embedding`/`IcdVersion.embedding`; `WorkspaceMemory`/`UserTenantMemory.embedding` (Task 2); `generate_embedding()` (Task 1).
- Produces: `SearchService._run_semantic_query(entity_type, spec, query_embedding, tenant_id, workspace_id) -> List[SearchHit]`; RRF fusion combining fulltext + lexical + semantic rank lists in `_search_entity_type()`.

**Note on scope:** this task only adds a semantic pass over entity types that already HAVE an `embedding` field today (`Requirement`, `TraceLink` via its own record, `IcdVersion`) — extending embeddings to the other 6 searchable entity types (`ArchitectureElement`, `TestCase`, `StakeholderNeed`, `Adr`, `Risk`, `Issue`, `ChangeRequest`, `Goal`, `GlossaryTerm`) is explicitly out of scope for this plan (see spec's out-of-scope section implicitly — those types never had embeddings before this feature and adding them is a much larger, separate migration effort per type).

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_search_semantic_fusion.py
import pytest

from application.search_service import SearchService
from persistence.tests.factories import active_tenant, make_requirement, make_workspace, editor_ctx


@pytest.mark.django_db
class TestSemanticFusion:
    def test_semantically_similar_requirement_found_without_keyword_match(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="User authentication flow", description="Login and session handling")
            req.embedding = [0.5] * 384
            req.save(update_fields=["embedding"])

            ctx = editor_ctx(tenant, ws)
            # Query text has NO keyword overlap with the requirement's title/description
            # but is semantically related -- only the fusion's semantic pass can find it.
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("application.search_service.generate_embedding", lambda text: [0.5] * 384)
                result = SearchService().search("credential verification process", ctx, workspace_id=ws.id)

            assert any(hit.id == str(req.id) for hit in result.hits)

    def test_fusion_does_not_break_existing_keyword_search(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            make_requirement(ws, title="Exact keyword match requirement")
            ctx = editor_ctx(tenant, ws)
            result = SearchService().search("Exact keyword match", ctx, workspace_id=ws.id)
            assert len(result.hits) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/application/tests/test_search_semantic_fusion.py -v`
Expected: FAIL — no semantic pass exists yet.

- [ ] **Step 3: Implement**

Add a semantic pass and RRF fusion in `search_service.py`:

```python
from pgvector.django import CosineDistance
from llm_adapter.embedding_service import generate_embedding

_EMBEDDABLE_TYPES = {"Requirement", "TraceLink", "IcdVersion"}
_RRF_K = 60  # standard RRF constant


def _run_semantic_query(self, entity_type: str, spec, query_embedding, tenant_id, workspace_id) -> List["SearchHit"]:
    if entity_type not in _EMBEDDABLE_TYPES or query_embedding is None:
        return []
    model = spec.model  # existing per-entity-type model reference already used by the fulltext/lexical passes
    qs = model.objects.filter(tenant_id=tenant_id, embedding__isnull=False)
    if workspace_id is not None:
        qs = qs.filter(workspace_id=workspace_id)
    qs = qs.annotate(distance=CosineDistance("embedding", query_embedding)).order_by("distance")[:50]
    return [
        SearchHit(id=str(obj.id), title=getattr(obj, "title", ""), entity_type=entity_type, relevance_score=1.0 - obj.distance)
        for obj in qs
    ]


def _rrf_fuse(self, *rank_lists: List["SearchHit"]) -> List["SearchHit"]:
    """Reciprocal Rank Fusion: combines N independently-ranked lists into one,
    scored by sum(1 / (RRF_K + rank_in_each_list)) -- a hit appearing near the
    top of multiple lists outranks one appearing only in a single list."""
    scores: Dict[str, float] = {}
    hits_by_id: Dict[str, "SearchHit"] = {}
    for rank_list in rank_lists:
        for rank, hit in enumerate(rank_list):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            hits_by_id[hit.id] = hit
    ordered_ids = sorted(scores, key=lambda hit_id: -scores[hit_id])
    return [hits_by_id[hit_id] for hit_id in ordered_ids]
```

Wire `_run_semantic_query` into `_search_entity_type()` as a third pass alongside the existing fulltext/lexical calls, and replace that method's current two-way dict-merge with a call to `_rrf_fuse(fulltext_hits, lexical_hits, semantic_hits)`. Compute `query_embedding = generate_embedding(query)` once in `search()` (not per entity type) and thread it through.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/application/tests/test_search_semantic_fusion.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full search test suite to confirm no regression**

Run: `pytest backend/application/tests/ -k search -v` and `pytest backend/rest_api/tests/ -k search -v`
Expected: PASS — the RRF fusion must produce the same relative top-1 winner as before for pure-keyword queries (test from Step 1's second case pins this).

- [ ] **Step 6: Commit**

```bash
git add backend/application/search_service.py backend/application/tests/test_search_semantic_fusion.py
git commit -m "feat: add semantic search pass with RRF fusion (Requirement/TraceLink/IcdVersion)"
```

---

## Task 10: `HonchoMemoryBackend` (optional external backend) + tenant-namespacing security test

**Files:**
- Create: `backend/memory/honcho_backend.py`
- Test: `backend/memory/tests/test_honcho_backend.py`

**Interfaces:**
- Consumes: `MemoryBackend` ABC (Task 3).
- Produces: `HonchoMemoryBackend(MemoryBackend)`, registered as `"honcho"` in `MEMORY_BACKEND_REGISTRY`.

**Note:** Honcho's Python SDK/HTTP API surface is NOT verified against real code in this repo (it is an external service) — this task's implementation is written against Honcho's documented `workspace`/`peer`/`session`/`message` primitives (matching this session's own live experience operating Honcho as an MCP plugin: `get_representation`, `create_conclusion`, dialectic `chat()`). The implementer MUST verify the exact SDK method names/signatures against the installed `honcho` Python package's actual API before finalizing — do not assume this task's code compiles as-is without that check.

- [ ] **Step 1: Write the failing test — the tenant-namespacing security constraint**

```python
# backend/memory/tests/test_honcho_backend.py
from unittest.mock import MagicMock, patch
from uuid import uuid4

from memory.honcho_backend import HonchoMemoryBackend


class TestHonchoPeerNamespacing:
    def test_peer_id_is_namespaced_by_tenant(self):
        tenant_id = uuid4()
        user_id = uuid4()
        backend = HonchoMemoryBackend()
        peer_id = backend._peer_id(tenant_id, user_id)
        assert peer_id == f"{tenant_id}:{user_id}"

    def test_different_tenants_same_user_id_get_different_peers(self):
        tenant_a = uuid4()
        tenant_b = uuid4()
        user_id = uuid4()
        backend = HonchoMemoryBackend()
        assert backend._peer_id(tenant_a, user_id) != backend._peer_id(tenant_b, user_id)

    def test_upsert_user_scope_uses_namespaced_peer(self):
        backend = HonchoMemoryBackend()
        tenant_id = uuid4()
        user_id = uuid4()
        with patch.object(backend, "_client") as mock_client:
            backend.upsert(tenant_id, "user", user_id, "some fact")
            call_kwargs = mock_client.peers.get_or_create.call_args
            assert call_kwargs.kwargs.get("id") == f"{tenant_id}:{user_id}" or call_kwargs.args[0] == f"{tenant_id}:{user_id}"

    def test_workspace_scope_uses_namespaced_honcho_workspace(self):
        backend = HonchoMemoryBackend()
        tenant_id = uuid4()
        workspace_id = uuid4()
        honcho_ws_id = backend._workspace_id(tenant_id, workspace_id)
        assert str(tenant_id) in honcho_ws_id
        assert str(workspace_id) in honcho_ws_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/memory/tests/test_honcho_backend.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/memory/honcho_backend.py
"""Optional, externally-connectable memory backend. Requires HONCHO_BASE_URL
(and optionally HONCHO_API_KEY) to be set; enabled via MEMORY_BACKEND=honcho.

SECURITY CONSTRAINT (verified by test_honcho_backend.py -- do not weaken):
Honcho's `peer` primitive has no tenant boundary of its own -- it is a flat
namespace on the Honcho side. Every peer/workspace ID this backend sends to
Honcho MUST be prefixed with the ReqogniLoom tenant_id, or a user_id that
happens to collide across two different ReqogniLoom tenants (e.g. two
different companies both importing a CSV of user IDs starting from 1) would
silently share one memory profile on the external service -- a real
cross-tenant data leak.
"""
from __future__ import annotations

import os
from typing import List
from uuid import UUID

from memory.backends import MemoryBackend, MemoryEntryRef, register_memory_backend


@register_memory_backend("honcho")
class HonchoMemoryBackend(MemoryBackend):
    def __init__(self) -> None:
        self._base_url = os.environ.get("HONCHO_BASE_URL", "").rstrip("/")
        self._api_key = os.environ.get("HONCHO_API_KEY")
        self.__client = None

    @property
    def _client(self):
        if self.__client is None:
            from honcho import Honcho  # external SDK -- verify exact import path at implementation time
            self.__client = Honcho(base_url=self._base_url, api_key=self._api_key)
        return self.__client

    def _peer_id(self, tenant_id: UUID, user_id: UUID) -> str:
        return f"{tenant_id}:{user_id}"

    def _workspace_id(self, tenant_id: UUID, workspace_id: UUID) -> str:
        return f"{tenant_id}:{workspace_id}"

    def upsert(self, tenant_id: UUID, scope: str, scope_id: UUID, content: str, source_event_id=None) -> MemoryEntryRef:
        if scope == "user":
            peer = self._client.peers.get_or_create(id=self._peer_id(tenant_id, scope_id))
            self._client.create_conclusion(peer=peer, content=content)  # exact SDK call TBD, verify against installed package
        else:
            honcho_ws = self._client.workspaces.get_or_create(id=self._workspace_id(tenant_id, scope_id))
            self._client.create_conclusion(workspace=honcho_ws, content=content)
        # Honcho's own ID is the entry_id -- exact return shape TBD, verify at implementation time.
        return MemoryEntryRef(entry_id=scope_id, content=content)

    def query(self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5) -> List[MemoryEntryRef]:
        raise NotImplementedError("verify Honcho's dialectic chat()/search API before implementing")

    def list_recent(self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20) -> List[MemoryEntryRef]:
        raise NotImplementedError("verify Honcho's conclusion-listing API before implementing")

    def forget(self, tenant_id: UUID, entry_id: UUID) -> None:
        raise NotImplementedError("verify Honcho's deletion API before implementing")
```

Note for the implementer: `query()`/`list_recent()`/`forget()` are left as `NotImplementedError` stubs in this plan because their exact Honcho SDK calls could not be verified against real, installed code (Honcho is external to this repo) — filling them in is a follow-up task once the SDK is actually added as a dependency and its real method signatures are confirmed (e.g. by testing against a running Honcho instance, the same way this session's own Honcho MCP plugin access could serve as a live reference for the real API shape). Do not guess these three methods' bodies; the namespacing methods (`_peer_id`/`_workspace_id`) and `upsert()`'s namespacing usage are the load-bearing security contract this task must get right, and are fully specified above.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/memory/tests/test_honcho_backend.py -v`
Expected: PASS (4 tests) — these test only the namespacing helper methods and `upsert()`'s use of them, not the unimplemented `query`/`list_recent`/`forget`.

- [ ] **Step 5: Commit**

```bash
git add backend/memory/honcho_backend.py backend/memory/tests/test_honcho_backend.py
git commit -m "feat: add HonchoMemoryBackend skeleton with tenant-namespaced peer/workspace IDs"
```

---

## Task 11: Settings endpoints + minimal frontend toggle

**Files:**
- Create: `backend/memory/memory_rest.py`
- Modify: `backend/rest_api/urls.py`
- Create: `frontend/src/components/WorkspaceSettings/MemorySettingsSection.tsx`, `.module.css`
- Test: `backend/memory/tests/test_memory_rest.py`, `frontend/src/components/WorkspaceSettings/MemorySettingsSection.test.tsx`

**Interfaces:**
- Produces: `GET/PUT /api/v1/workspaces/{id}/memory-settings/` (enable/disable per-workspace, any workspace member can view, editor+ can toggle), `GET/PUT /api/v1/system/memory-settings/` (System-Admin only — `EMBEDDING_PROVIDER`/`MEMORY_BACKEND` are read-only here for v1, env-configured only; this endpoint exposes the CURRENT active configuration for visibility, matching the Theme Presets spec's "system config viewable but not editable" precedent, not a live-switchable control).

- [ ] **Step 1: Write the failing test**

```python
# backend/memory/tests/test_memory_rest.py
import pytest
from rest_framework.test import APIClient

from persistence.tests.factories import active_tenant, editor_user_and_token, admin_user_and_token, make_workspace


@pytest.mark.django_db
class TestMemorySettingsRest:
    def test_get_workspace_memory_settings_default_enabled(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get(f"/api/v1/workspaces/{ws.id}/memory-settings/")
            assert response.status_code == 200
            assert response.data["enabled"] is True

    def test_editor_can_disable(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(f"/api/v1/workspaces/{ws.id}/memory-settings/", {"enabled": False}, format="json")
            assert response.status_code == 200
            assert response.data["enabled"] is False

    def test_system_memory_settings_shows_active_config(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/system/memory-settings/")
            assert response.status_code == 200
            assert response.data["embedding_provider"] == "sentence-transformers"
            assert response.data["memory_backend"] == "pgvector"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/memory/tests/test_memory_rest.py -v`
Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Implement**

Add a small `WorkspaceMemorySettings(TenantScopedModel)` model to `memory/models.py` (`workspace` OneToOne, `enabled` BooleanField default `True`) with its own migration (append to Task 2's `0001_initial.py` if this task runs before that migration is applied anywhere, otherwise a new `0002_workspace_memory_settings.py` — the implementer decides based on actual execution order), then:

```python
# backend/memory/memory_rest.py
from __future__ import annotations

import os
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_tenancy.services.authorization import AuthorizationService
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


class WorkspaceMemorySettingsView(APIView):
    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        from memory.models import WorkspaceMemorySettings
        settings_row = WorkspaceMemorySettings.objects.filter(workspace_id=workspace_id).first()
        return Response({"enabled": settings_row.enabled if settings_row else True})

    def put(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        roles = AuthorizationService().active_roles_for(user_id=ctx.user_id, workspace_id=workspace_id)
        if "editor" not in roles and "admin" not in roles:
            return Response(build_error_response("PERMISSION_DENIED", lang), status=status.HTTP_403_FORBIDDEN)
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        from memory.models import WorkspaceMemorySettings
        settings_row, _ = WorkspaceMemorySettings.objects.update_or_create(
            tenant_id=ctx.tenant_id, workspace_id=workspace_id, defaults={"enabled": request.data.get("enabled", True)}
        )
        return Response({"enabled": settings_row.enabled})


class SystemMemorySettingsView(APIView):
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        is_admin = ctx.has_role("admin") or AuthorizationService().is_tenant_admin(ctx.user_id, ctx.tenant_id)
        if not is_admin:
            return Response(build_error_response("PERMISSION_DENIED", lang), status=status.HTTP_403_FORBIDDEN)
        return Response({
            "embedding_provider": os.environ.get("EMBEDDING_PROVIDER", "sentence-transformers"),
            "memory_backend": os.environ.get("MEMORY_BACKEND", "pgvector"),
        })
```

Wire both views in `backend/rest_api/urls.py`:

```python
from memory.memory_rest import SystemMemorySettingsView, WorkspaceMemorySettingsView

urlpatterns += [
    path("workspaces/<uuid:workspace_id>/memory-settings/", WorkspaceMemorySettingsView.as_view(), name="workspace-memory-settings"),
    path("system/memory-settings/", SystemMemorySettingsView.as_view(), name="system-memory-settings"),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/memory/tests/test_memory_rest.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing frontend test**

```tsx
// frontend/src/components/WorkspaceSettings/MemorySettingsSection.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemorySettingsSection } from "./MemorySettingsSection";
import apiClient from "../../api/client";

vi.mock("../../api/client");

describe("MemorySettingsSection", () => {
  it("shows the current enabled state", async () => {
    (apiClient.get as any).mockResolvedValue({ data: { enabled: true } });
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    expect(toggle).toBeChecked();
  });

  it("toggling calls the PUT endpoint", async () => {
    (apiClient.get as any).mockResolvedValue({ data: { enabled: true } });
    (apiClient.put as any).mockResolvedValue({ data: { enabled: false } });
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    fireEvent.click(toggle);
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith("/workspaces/ws-1/memory-settings/", { enabled: false }));
  });
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/MemorySettingsSection.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 7: Implement**

```tsx
// frontend/src/components/WorkspaceSettings/MemorySettingsSection.tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import apiClient from "../../api/client";
import styles from "./MemorySettingsSection.module.css";

interface MemorySettingsSectionProps {
  workspaceId: string;
}

export function MemorySettingsSection({ workspaceId }: MemorySettingsSectionProps): JSX.Element {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState<boolean>(true);

  useEffect(() => {
    apiClient.get(`/workspaces/${workspaceId}/memory-settings/`).then((r) => setEnabled(r.data.enabled));
  }, [workspaceId]);

  function handleToggle() {
    const next = !enabled;
    setEnabled(next);
    apiClient.put(`/workspaces/${workspaceId}/memory-settings/`, { enabled: next });
  }

  return (
    <section className={styles.section}>
      <h3>{t("workspaceSettings.memory.heading")}</h3>
      <label>
        <input type="checkbox" data-testid="memory-settings-toggle" checked={enabled} onChange={handleToggle} />
        {t("workspaceSettings.memory.enableLabel")}
      </label>
    </section>
  );
}
```

```css
/* frontend/src/components/WorkspaceSettings/MemorySettingsSection.module.css */
.section {
  padding: 12px 0;
}
```

Add i18n keys (`workspaceSettings.memory.heading`/`.enableLabel`, DE+EN) and mount `<MemorySettingsSection workspaceId={...} />` inside `WorkspaceSettings.tsx`.

- [ ] **Step 8: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/MemorySettingsSection.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 9: Commit**

```bash
git add backend/memory/memory_rest.py backend/memory/models.py backend/rest_api/urls.py frontend/src/components/WorkspaceSettings/MemorySettingsSection.tsx frontend/src/components/WorkspaceSettings/MemorySettingsSection.module.css frontend/src/components/WorkspaceSettings/MemorySettingsSection.test.tsx frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/de.json
git commit -m "feat: add memory settings endpoints and workspace toggle UI"
```

---

## Task 12: Docker/dependency wiring + full-suite regression check

**Files:**
- Modify: `backend/requirements.txt` (or equivalent), backend/celery Dockerfile
- Create: `docker-compose.override.example.yml` (documentation only — shows how to plug in an external Ollama or Honcho service; NOT wired into `docker-compose.yml` itself, per the "self-contained by default" constraint)

- [ ] **Step 1: Verify the default path needs zero new mandatory services**

Run: `docker-compose config` — confirm no new service was accidentally added to the base `docker-compose.yml` (Task 1's `sentence-transformers` dependency lives inside the existing `backend`/`celery` images, not a new container).

- [ ] **Step 2: Write the documentation example for optional external backends**

```yaml
# docker-compose.override.example.yml
# Copy to docker-compose.override.yml and uncomment what you need.
# Neither service is required by default -- ReqogniLoom's memory/embedding
# features work fully self-contained without either of these.

# services:
#   ollama:
#     image: ollama/ollama:latest
#     ports: ["11434:11434"]
#     volumes: ["ollama_data:/root/.ollama"]
#
#   backend:
#     environment:
#       EMBEDDING_PROVIDER: ollama
#       OLLAMA_BASE_URL: http://ollama:11434
#
#   # For an external Honcho instance (not self-hosted here):
#   # backend:
#   #   environment:
#   #     MEMORY_BACKEND: honcho
#   #     HONCHO_BASE_URL: https://your-honcho-instance.example.com
#   #     HONCHO_API_KEY: ${HONCHO_API_KEY}

# volumes:
#   ollama_data:
```

- [ ] **Step 3: Run the full backend test suite**

Run: `pytest backend/ -x -q`
Expected: PASS

- [ ] **Step 4: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 5: `makemigrations --check`**

Run: `python backend/manage.py makemigrations --check --dry-run`
Expected: "No changes detected"

- [ ] **Step 6: Verify the MCP tool manifest has no drift**

Run: `pytest backend/mcp_server/tests/test_tool_manifest_drift.py -v`
Expected: PASS

- [ ] **Step 7: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "fix: resolve regressions found in full-suite verification pass"
```

---

## Deliberately out of scope (v1, per spec)

- Cross-**tenant** search/memory — explicitly excluded regardless of backend (hard constraint, not a v2 candidate to loosen casually).
- Runtime `EMBEDDING_PROVIDER` switching with automatic re-embedding of existing data.
- A full, working `HonchoMemoryBackend` (`query`/`list_recent`/`forget` are left as verified-unimplemented stubs — Task 10's own note explains why: no real Honcho SDK access to verify signatures against in this repo).
- Extending vector embeddings to the 6 entity types that don't have them today (`ArchitectureElement`, `TestCase`, `StakeholderNeed`, `Adr`, `Risk`, `Issue`, `ChangeRequest`, `Goal`, `GlossaryTerm`) — Task 9 only adds the semantic pass for the 3 types that already have embeddings.
- Cross-Encoder re-ranking of search results (spec's own stated v2 follow-up).
- An in-app UI for manually editing/browsing individual memory entries beyond the workspace enable/disable toggle (Task 11) — no memory-entry list/delete UI in v1 (the `memory.forget` MCP tool exists for programmatic/admin use, but no frontend wraps it yet).
