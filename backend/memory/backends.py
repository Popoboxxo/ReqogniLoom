"""``MemoryBackend`` abstraction + default ``PgvectorMemoryBackend`` (Task 3).

Provider-agnostic read/write facade over the Task 2 memory tables
(``WorkspaceMemory``, ``UserTenantMemory``), mirroring the registry pattern
already used by ``llm_adapter.providers`` (LLM providers) and
``llm_adapter.embedding_service`` (embedding providers): a
``Dict[str, Type[...]]`` registry populated via a ``@register_*`` decorator,
resolved at call time from an environment variable so tests can swap
implementations with ``monkeypatch.setenv``.

``scope``/``scope_id`` convention (Task 2 model split): ``scope="workspace"``
pairs with ``scope_id=workspace_id`` (-> ``WorkspaceMemory``); ``scope="user"``
pairs with ``scope_id=user_id`` (-> ``UserTenantMemory``, tenant-wide, no
workspace field).

Correction vs. the implementation-plan draft (same class of bug as Task 2's
``auth_tenancy.User`` FK mistake -- see ``memory/migrations/0001_initial.py``
module docstring): the draft activated the tenant with a bare
``TenantContext.set_tenant(tenant_id)`` call. That only satisfies the
Django-ORM side (``persistence.tenancy.TenantManager`` filters/auto-injects
``tenant_id`` in Python) -- it never issues ``SET app.current_tenant`` on the
connection, so Postgres RLS's ``WITH CHECK`` (INSERT) and ``USING`` (SELECT)
policies on ``mem_workspace_memory``/``mem_user_tenant_memory`` would reject
or silently hide every row whenever this backend runs without an
already-active request/test tenant context -- e.g. a future Celery
consolidation task (Task 5) or an MCP tool invocation with no surrounding
request. This is the exact bug already fixed once in
``llm_adapter.tasks.run_capability`` (see its ``#444``/``#522`` comments);
:func:`_tenant_context` below reuses ``persistence.middleware.
set_request_tenant``/``clear_request_tenant`` (which arm both isolation
layers) and the same "don't clear a context we did not open" nesting guard,
instead of the plan's bare ``TenantContext.set_tenant``.
"""
from __future__ import annotations

import contextlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, Iterator, List, Optional, Type, Union
from uuid import UUID

from pgvector.django import CosineDistance

from llm_adapter.embedding_service import generate_embedding
from memory.models import UserTenantMemory, WorkspaceMemory
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.tenancy import TenantContext


#: Identifier of a persisted memory entry, as issued by the *active* backend.
#:
#: ``PgvectorMemoryBackend`` issues Django ``UUIDField`` primary keys, but a
#: backend is free to use the external service's own id format and generally
#: has no way to force one: Honcho, for instance, issues 21-character nanoids
#: (``src/models.py``: ``mapped_column(TEXT, default=generate_nanoid)``, with a
#: ``length(public_id) = 21`` / ``^[A-Za-z0-9_-]+$`` check constraint), which
#: are not parseable as UUIDs. Typing this as a bare ``UUID`` therefore baked a
#: pgvector-specific assumption into the provider-agnostic facade.
#:
#: Consumers must treat this as an opaque token: stringify it for transport
#: (``mcp_server.tools.memory`` already does) and never feed it to a Django
#: ``.filter(id=...)`` without first confirming the active backend is the one
#: that issued it (see :func:`resolve_memory_entry_owner`).
MemoryEntryId = Union[UUID, str]


@dataclass
class MemoryEntryRef:
    """Backend-agnostic view of a persisted memory entry.

    ``distance`` is the backend's similarity metric to whatever query
    produced this ref (e.g. cosine distance for :meth:`MemoryBackend.query`;
    lower = more similar), or ``None`` when the ref was not produced by a
    similarity query (``upsert``/``list_recent``/``forget``) or the backend
    does not expose one. Optional and defaulted for backward compatibility
    with existing callers/tests that construct a ``MemoryEntryRef`` directly.
    """

    entry_id: MemoryEntryId
    content: str
    confidence: float = 1.0
    distance: Optional[float] = None


class MemoryBackend(ABC):
    """Provider-agnostic read/write facade for consolidated memory facts."""

    @abstractmethod
    def upsert(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        source_event_id: Optional[UUID] = None,
    ) -> MemoryEntryRef:
        """Persist ``content`` as a new memory entry for ``scope``/``scope_id``."""
        ...

    @abstractmethod
    def query(
        self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5
    ) -> List[MemoryEntryRef]:
        """Return the ``top_k`` entries most semantically similar to ``query_text``."""
        ...

    @abstractmethod
    def list_recent(
        self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20
    ) -> List[MemoryEntryRef]:
        """Return the ``limit`` most recently created entries, newest first."""
        ...

    @abstractmethod
    def forget(self, tenant_id: UUID, entry_id: MemoryEntryId) -> None:
        """Permanently delete the entry identified by ``entry_id``.

        ``entry_id`` must be an id this same backend issued (see
        :data:`MemoryEntryId`) — ids are not portable between backends.
        """
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Return ``(is_healthy, detail_message)`` for this backend.

        A quick, bounded connectivity check — never raises; callers (the
        System Health dashboard) treat any exception as equivalent to
        ``(False, str(exc))``.
        """
        ...


MEMORY_BACKEND_REGISTRY: Dict[str, Type[MemoryBackend]] = {}


def register_memory_backend(name: str) -> Callable[[Type[MemoryBackend]], Type[MemoryBackend]]:
    """Class decorator registering a :class:`MemoryBackend` under ``name``."""

    def _decorator(cls: Type[MemoryBackend]) -> Type[MemoryBackend]:
        MEMORY_BACKEND_REGISTRY[name] = cls
        return cls

    return _decorator


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


def _model_for_scope(scope: str):
    """Return the ``(Model, scope_field_name)`` pair for ``scope``."""
    if scope == "workspace":
        return WorkspaceMemory, "workspace_id"
    if scope == "user":
        return UserTenantMemory, "user_id"
    raise ValueError(f"unknown memory scope: {scope!r}")


def resolve_memory_entry_owner(
    entry_id: UUID,
) -> tuple[Optional[UserTenantMemory], Optional[WorkspaceMemory]]:
    """Resolve *entry_id* to its owning row, for forget-permission checks.

    Returns ``(user_entry, None)`` if *entry_id* is a ``UserTenantMemory`` row,
    ``(None, ws_entry)`` if it is a ``WorkspaceMemory`` row, or ``(None, None)``
    if neither table has a matching row. Both underlying tables are RLS-gated,
    so this MUST be called with an active tenant context (see
    :func:`_tenant_context`) around it -- kept in this module (rather than the
    caller, e.g. an MCP tool) so ``mcp_server/tools/*.py`` never needs a
    direct ``.objects`` access (ADR-01, issue #124 ratchet).
    """
    user_entry = UserTenantMemory.objects.filter(id=entry_id).first()
    if user_entry is not None:
        return user_entry, None
    ws_entry = WorkspaceMemory.objects.filter(id=entry_id).first()
    return None, ws_entry


@contextlib.contextmanager
def _tenant_context(tenant_id: UUID) -> Iterator[None]:
    """Activate ``tenant_id`` for both isolation layers (see module docstring).

    Mirrors the nesting guard in ``llm_adapter.tasks.run_capability`` (#522):
    always (re-)arm the RLS session variable via ``set_request_tenant`` so it
    matches ``tenant_id`` regardless of any pre-existing context, but only
    tear it down on exit if this call is the one that first activated it --
    clearing a context we did not open would disarm the *caller's* isolation
    (e.g. a request or a test's ``active_tenant()``) for whatever runs after
    this call returns.
    """
    tenant_was_set = TenantContext.is_set()
    set_request_tenant(tenant_id)
    try:
        yield
    finally:
        if not tenant_was_set and TenantContext.is_set():
            clear_request_tenant()


@register_memory_backend("pgvector")
class PgvectorMemoryBackend(MemoryBackend):
    """Default backend: pgvector-backed cosine-similarity search over the
    Task 2 memory tables, using the active :mod:`llm_adapter.embedding_service`
    provider (``EMBEDDING_PROVIDER`` env var) to embed content/queries.
    """

    def upsert(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        source_event_id: Optional[UUID] = None,
    ) -> MemoryEntryRef:
        model, scope_field = _model_for_scope(scope)
        embedding = generate_embedding(content)
        with _tenant_context(tenant_id):
            entry = model.objects.create(
                tenant_id=tenant_id,
                content=content,
                embedding=embedding,
                source_event_id=source_event_id,
                **{scope_field: scope_id},
            )
            return MemoryEntryRef(entry_id=entry.id, content=entry.content, confidence=entry.confidence)

    def query(
        self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5
    ) -> List[MemoryEntryRef]:
        model, scope_field = _model_for_scope(scope)
        query_embedding = generate_embedding(query_text)
        if query_embedding is None:
            return []
        with _tenant_context(tenant_id):
            qs = (
                model.objects.filter(
                    **{scope_field: scope_id}, superseded_by__isnull=True, embedding__isnull=False
                )
                .annotate(distance=CosineDistance("embedding", query_embedding))
                .order_by("distance")[:top_k]
            )
            return [
                MemoryEntryRef(
                    entry_id=e.id, content=e.content, confidence=e.confidence, distance=e.distance
                )
                for e in qs
            ]

    def list_recent(
        self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20
    ) -> List[MemoryEntryRef]:
        model, scope_field = _model_for_scope(scope)
        with _tenant_context(tenant_id):
            qs = (
                model.objects.filter(**{scope_field: scope_id}, superseded_by__isnull=True)
                .order_by("-created_at")[:limit]
            )
            return [
                MemoryEntryRef(entry_id=e.id, content=e.content, confidence=e.confidence) for e in qs
            ]

    def forget(self, tenant_id: UUID, entry_id: MemoryEntryId) -> None:
        with _tenant_context(tenant_id):
            deleted, _ = WorkspaceMemory.objects.filter(id=entry_id).delete()
            if deleted == 0:
                UserTenantMemory.objects.filter(id=entry_id).delete()

    def health_check(self) -> tuple[bool, str]:
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM mem_workspace_memory LIMIT 1")
            return True, "mem_workspace_memory table reachable"
        except Exception as exc:
            return False, str(exc)


__all__ = [
    "MemoryEntryId",
    "MemoryEntryRef",
    "MemoryBackend",
    "MEMORY_BACKEND_REGISTRY",
    "register_memory_backend",
    "get_memory_backend",
    "PgvectorMemoryBackend",
]
