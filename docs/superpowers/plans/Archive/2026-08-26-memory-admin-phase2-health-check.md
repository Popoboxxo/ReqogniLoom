# Memory Admin UI — Phase 2: Health-Check Rows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new rows ("memory_embedding", "memory_backend") to the existing System Health dialog, reusing its already-generic component-list rendering — no new dialog, no new button, no frontend code changes beyond two i18n label entries.

**Architecture:** `MemoryBackend` (ABC in `memory/backends.py`) gets a new abstract method `health_check() -> tuple[bool, str]`, implemented in `PgvectorMemoryBackend` (raw `SELECT 1` against the memory table) and `HonchoMemoryBackend` (a lightweight, SDK-free HTTP reachability check — the `honcho` Python SDK is not an installed dependency, so the check must not import it). Two new component-check functions in `admin_ops/health_rest.py` — `_check_memory_embedding()` (calls the configured `EmbeddingProvider.embed("ping")`, verifies the returned vector length matches `.dimensions`) and `_check_memory_backend()` (calls `get_memory_backend().health_check()`) — follow the exact pattern of the existing `_check_llm_provider()`/`_check_redis()` functions and are appended to `SystemHealthView.get()`'s `components` list.

**Tech Stack:** Django 4.2, existing `EmbeddingProvider`/`MemoryBackend` registries (no new dependencies — `requests` is already a listed dependency, used for the Honcho HTTP check instead of the unverified `honcho` SDK).

**Spec:** `docs/superpowers/specs/2026-08-26-memory-admin-ui-design.md` (Phase 2 section)

## Global Constraints

- No new Django migration, no new model, no new REST endpoint, no new frontend component — this phase only adds to two existing backend files and two locale files.
- `HonchoMemoryBackend.health_check()` MUST NOT call `self._ensure_client()` or otherwise `import honcho` — that SDK is not in `backend/requirements.txt` and doing so would raise `ImportError` on every health check when `MEMORY_BACKEND=honcho` is configured (verified: `grep -n honcho backend/requirements.txt` returns nothing). Use `requests` (already a dependency) for a plain HTTP reachability check against `HONCHO_BASE_URL` instead.
- Every check function must be wrapped so a failing dependency reports a `"down"`/`"degraded"` row, never raises past `SystemHealthView.get()` — mirrors every existing check function's own try/except-guarded pattern in `admin_ops/health_rest.py`.
- Every check must complete quickly (bounded timeout) — mirrors `_CHECK_TIMEOUT_S = 1.0` already defined in `admin_ops/health_rest.py`; reuse that same constant, do not invent a second timeout constant.
- The frontend `SystemHealthDialog.tsx` needs NO code change — it already iterates `snapshot.components` generically (verified by reading the component's render code). Only add the two new component-name translation keys to both locale files (`systemHealth.componentNames.memory_embedding` / `.memory_backend`), matching the existing nested-object shape of `systemHealth.componentNames` in both `de.json` and `en.json` (different shape than the flat-dotted `systemSettings.*` convention used elsewhere — do not conflate the two).
- Every new frontend-visible string needs a matching key in BOTH `frontend/src/i18n/locales/de.json` and `frontend/src/i18n/locales/en.json` (checked by `frontend/src/test/i18n-parity.test.ts`).

---

### Task 1: Backend — `MemoryBackend.health_check()` + two new `SystemHealthView` checks

**Files:**
- Modify: `backend/memory/backends.py` (add abstract method + `PgvectorMemoryBackend` implementation)
- Modify: `backend/memory/honcho_backend.py` (add `HonchoMemoryBackend` implementation)
- Modify: `backend/admin_ops/health_rest.py` (add two check functions, wire into `SystemHealthView.get()`)
- Modify: `frontend/src/i18n/locales/de.json` and `frontend/src/i18n/locales/en.json` (two new component-name labels)
- Test: `backend/memory/tests/test_pgvector_backend.py` (existing, append `TestPgvectorMemoryBackendHealthCheck`)
- Test: `backend/memory/tests/test_honcho_backend.py` (existing, append `TestHonchoMemoryBackendHealthCheck`)
- Test: `backend/admin_ops/tests/test_health_rest.py` (existing, append `TestSystemHealthMemoryComponents`)

**Interfaces:**
- Consumes: `EmbeddingProvider` (`llm_adapter.embedding_service.get_embedding_provider() -> EmbeddingProvider`, instance has `.dimensions: int` and `.embed(text: str) -> Optional[List[float]]`), `MemoryBackend`/`get_memory_backend()`/`register_memory_backend` (`memory.backends`), existing check-function pattern in `admin_ops/health_rest.py` (`STATUS_OK`, `STATUS_DEGRADED`, `STATUS_DOWN`, `_CHECK_TIMEOUT_S`).
- Produces: `MemoryBackend.health_check(self) -> tuple[bool, str]` (abstract method, `True`/detail-message on success, `False`/error-message on failure) implemented by both `PgvectorMemoryBackend` and `HonchoMemoryBackend`. `_check_memory_embedding() -> dict[str, str]` and `_check_memory_backend() -> dict[str, str]` in `admin_ops/health_rest.py`, each returning the same `{"name": ..., "status": ..., "detail": ...}` shape as every other check function, appended to `SystemHealthView.get()`'s `components` list after `_check_llm_provider()`.

- [ ] **Step 1: Write the failing backend tests**

Append this test class to the existing `backend/memory/tests/test_pgvector_backend.py` (read it first for its exact import/fixture style — it already imports `PgvectorMemoryBackend` and uses `@pytest.mark.django_db`):

```python
class TestPgvectorMemoryBackendHealthCheck:
    def test_health_check_ok_when_table_reachable(self):
        backend = PgvectorMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is True
        assert "reachable" in detail.lower() or "ok" in detail.lower()
```

Append this test class to the existing `backend/memory/tests/test_honcho_backend.py` (read it first for its exact import/fixture style — it already imports `HonchoMemoryBackend`):

```python
class TestHonchoMemoryBackendHealthCheck:
    def test_health_check_down_when_base_url_not_configured(self, monkeypatch):
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
        backend = HonchoMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is False
        assert "not configured" in detail.lower()

    def test_health_check_reports_down_on_connection_failure(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho-does-not-exist.invalid:9999")
        backend = HonchoMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is False

    def test_health_check_does_not_import_honcho_sdk(self, monkeypatch):
        """Guards Global Constraint: must never attempt `import honcho` (uninstalled SDK)."""
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
        backend = HonchoMemoryBackend()
        # If health_check() called _ensure_client(), this would raise ImportError
        # (honcho is not installed) instead of returning a normal (False, ...) tuple.
        ok, detail = backend.health_check()
        assert isinstance(ok, bool)
```

`backend/admin_ops/tests/test_health_rest.py` already exists with an established pattern you MUST follow exactly — read the whole file first. Key facts about it, so you don't have to rediscover them:
- Tests call `SystemHealthView().get(request)` directly (no HTTP client), building the request via the file's own `_make_request(auth: AuthContext | None) -> Request` helper.
- Fixtures come from `backend/admin_ops/tests/conftest.py`: `admin_ctx`, `regular_ctx`, `tenant_a` (all already defined — do not redefine them).
- `active_tenant` is imported via `from .conftest import active_tenant` and used as `with active_tenant(tenant_a): ...`.
- `_patch_infra_checks()` mocks `_check_redis`/`_check_celery_worker`/`_check_celery_beat`/`_check_mcp_server` only — `_check_database` and `_check_llm_provider` are deliberately left real (fast, no external network). Follow this same policy for the two new checks: do NOT mock them, but DO set `EMBEDDING_PROVIDER=mock` (via `monkeypatch.setenv`, EVERY test that calls the view) so `_check_memory_embedding` never loads a real ML model (slow) — `MEMORY_BACKEND` needs no override since `pgvector`'s `health_check()` is a fast, already-available-in-tests real `SELECT 1`.
- **`test_admin_gets_200_with_expected_shape`'s existing exact-list assertion will break** once the two new checks are wired in (Step 5) — you MUST update it in the same commit:
  ```python
        assert names == [
            "database",
            "redis",
            "celery_worker",
            "celery_beat",
            "mcp_server",
            "llm_provider",
            "memory_embedding",
            "memory_backend",
        ]
  ```
  Also add `monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")` as the first line of that test's body (add `monkeypatch` to its parameter list).

Append this new test class at the end of the file:

```python
class TestSystemHealthMemoryComponents:
    """The two new memory-admin-phase-2 component checks."""

    def test_memory_embedding_ok_with_mock_provider(
        self, admin_ctx: AuthContext, tenant_a, monkeypatch
    ) -> None:
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        patches = _patch_infra_checks()
        for p in patches:
            p.start()
        try:
            with active_tenant(tenant_a):
                request = _make_request(admin_ctx)
                response = SystemHealthView().get(request)
        finally:
            for p in patches:
                p.stop()

        component = next(
            c for c in response.data["components"] if c["name"] == "memory_embedding"
        )
        assert component["status"] == STATUS_OK

    def test_memory_backend_ok_with_pgvector(
        self, admin_ctx: AuthContext, tenant_a, monkeypatch
    ) -> None:
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        patches = _patch_infra_checks()
        for p in patches:
            p.start()
        try:
            with active_tenant(tenant_a):
                request = _make_request(admin_ctx)
                response = SystemHealthView().get(request)
        finally:
            for p in patches:
                p.stop()

        component = next(
            c for c in response.data["components"] if c["name"] == "memory_backend"
        )
        assert component["status"] == STATUS_OK
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python -m pytest memory/tests/test_pgvector_backend.py memory/tests/test_honcho_backend.py admin_ops/tests/test_health_rest.py -v 2>&1 | tail -40"` (adjust the exact file list to whichever files you actually created/appended to in Step 1).
Expected: FAIL — `health_check` is not a method on either backend yet; the two component names don't appear in the health response yet.

- [ ] **Step 3: Implement `MemoryBackend.health_check()` and `PgvectorMemoryBackend`'s implementation**

In `backend/memory/backends.py`, add the abstract method to the `MemoryBackend` ABC (add it after the existing `forget` abstract method):

```python
    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Return ``(is_healthy, detail_message)`` for this backend.

        A quick, bounded connectivity check — never raises; callers (the
        System Health dashboard) treat any exception as equivalent to
        ``(False, str(exc))``.
        """
        ...
```

Add the implementation to `PgvectorMemoryBackend` (add it as the last method in that class, after `forget`):

```python
    def health_check(self) -> tuple[bool, str]:
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM mem_workspace_memory LIMIT 1")
            return True, "mem_workspace_memory table reachable"
        except Exception as exc:
            return False, str(exc)
```

- [ ] **Step 4: Implement `HonchoMemoryBackend.health_check()`**

In `backend/memory/honcho_backend.py`, add this method to `HonchoMemoryBackend` (add it as the last method in the class, after `forget`). Do NOT call `self._ensure_client()` anywhere in this method — see Global Constraints.

```python
    def health_check(self) -> tuple[bool, str]:
        if not self._base_url:
            return False, "HONCHO_BASE_URL is not configured"
        try:
            import requests  # noqa: PLC0415 - lazy import, matches this repo's health-check convention

            requests.get(self._base_url, timeout=1.0)
            return True, f"{self._base_url} reachable"
        except Exception as exc:
            return False, str(exc)
```

- [ ] **Step 5: Implement the two new health-check functions in `admin_ops/health_rest.py`**

Add these two functions immediately after the existing `_check_llm_provider()` function (before `_recent_audit_events`):

```python
def _check_memory_embedding() -> dict[str, str]:
    """Check the configured EmbeddingProvider by embedding a short string."""
    try:
        from llm_adapter.embedding_service import get_embedding_provider  # noqa: PLC0415

        provider = get_embedding_provider()
        vector = provider.embed("ping")
        if vector is None:
            return {
                "name": "memory_embedding",
                "status": STATUS_DOWN,
                "detail": "embed() returned no vector",
            }
        if len(vector) != provider.dimensions:
            return {
                "name": "memory_embedding",
                "status": STATUS_DEGRADED,
                "detail": f"expected {provider.dimensions} dims, got {len(vector)}",
            }
        return {
            "name": "memory_embedding",
            "status": STATUS_OK,
            "detail": f"{provider.dimensions}-dim vector returned",
        }
    except Exception as exc:  # noqa: BLE001 - provider unreachable/misconfigured
        logger.warning("System health: memory embedding check failed - %s", exc)
        return {"name": "memory_embedding", "status": STATUS_DOWN, "detail": str(exc)}


def _check_memory_backend() -> dict[str, str]:
    """Check the configured MemoryBackend via its own health_check()."""
    try:
        from memory.backends import get_memory_backend  # noqa: PLC0415

        backend = get_memory_backend()
        ok, detail = backend.health_check()
        return {
            "name": "memory_backend",
            "status": STATUS_OK if ok else STATUS_DOWN,
            "detail": detail,
        }
    except Exception as exc:  # noqa: BLE001 - backend unreachable/misconfigured
        logger.warning("System health: memory backend check failed - %s", exc)
        return {"name": "memory_backend", "status": STATUS_DOWN, "detail": str(exc)}
```

Then modify `SystemHealthView.get()`'s `components` list to append the two new checks after `_check_llm_provider()`:

```python
        components = [
            _check_database(),
            _check_redis(),
            _check_celery_worker(),
            _check_celery_beat(),
            _check_mcp_server(),
            _check_llm_provider(),
            _check_memory_embedding(),
            _check_memory_backend(),
        ]
```

Also update the class docstring's example JSON (in `SystemHealthView`'s docstring) to include the two new rows — add `{"name": "memory_embedding", "status": "ok", "detail": "..."}` and `{"name": "memory_backend", "status": "ok", "detail": "..."}` after the `llm_provider` line in the example.

- [ ] **Step 6: Add the two locale keys**

In `frontend/src/i18n/locales/de.json`, inside the existing `"systemHealth": { "componentNames": { ... } }` object, add two new entries as siblings of the existing `celery_worker`/`mcp_server`/`llm_provider` keys:

```json
    "memory_embedding": "Memory-Embedding",
    "memory_backend": "Memory-Backend"
```

In `frontend/src/i18n/locales/en.json`, same location, English text:

```json
    "memory_embedding": "Memory Embedding",
    "memory_backend": "Memory Backend"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python -m pytest memory/tests/test_pgvector_backend.py memory/tests/test_honcho_backend.py admin_ops/tests/test_health_rest.py -v 2>&1 | tail -60"` (adjust file list to what you actually created).
Expected: PASS (all tests, old and new).

Also run: `docker exec reqogniloom-frontend-1 npx vitest run src/test/i18n-parity.test.ts` — must still pass (de.json/en.json key sets identical).

- [ ] **Step 8: Commit**

```bash
git add backend/memory/backends.py backend/memory/honcho_backend.py backend/admin_ops/health_rest.py frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json backend/memory/tests/ backend/admin_ops/tests/
git commit -m "feat: add memory embedding/backend rows to System Health dashboard"
```

(Use the exact test file paths you actually touched in Step 1 rather than a blanket `tests/` glob if `git add` would otherwise pick up unrelated files.)

---

## Post-Plan Note

This plan implements Phase 2 only. Phases 3-5 (settings override, user self-service, visualization) are separate future plans against the same spec (`docs/superpowers/specs/2026-08-26-memory-admin-ui-design.md`) and are NOT part of this plan's scope.
