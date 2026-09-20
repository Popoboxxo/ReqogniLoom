"""``MemoryBackend`` abstraction + default ``PgvectorMemoryBackend``.

Provider-agnostic read/write facade over the unified memory table
(``MemoryEntry``, RFC #1002 PR A), mirroring the registry pattern already used
by ``llm_adapter.providers`` (LLM providers) and
``llm_adapter.embedding_service`` (embedding providers): a
``Dict[str, Type[...]]`` registry populated via a ``@register_*`` decorator,
resolved at call time from an environment variable so tests can swap
implementations with ``monkeypatch.setenv``.

``scope``/``scope_id`` convention: ``scope="workspace"`` pairs with
``scope_id=workspace_id``; ``scope="user"`` with ``scope_id=user_id``;
``scope="artifact"`` with ``scope_id=artifact_id``. :func:`_scope_filter`
translates that pair into the single ORM filter dict every backend query builds
on.

Contract shape
--------------
Two generations of methods coexist on :class:`MemoryBackend`:

* the original facade -- :meth:`MemoryBackend.upsert`, :meth:`MemoryBackend.
  query`, :meth:`MemoryBackend.list_recent`, :meth:`MemoryBackend.forget`,
  :meth:`MemoryBackend.health_check`;
* the canonical-store API introduced by RFC #1002 -- :meth:`MemoryBackend.
  write`, :meth:`MemoryBackend.list_entries`, :meth:`MemoryBackend.count`,
  :meth:`MemoryBackend.delete_entry`, :meth:`MemoryBackend.delete_scope`,
  :meth:`MemoryBackend.health`.

Both are abstract so every backend implements the full surface (the old ones
typically delegate to the new ones); that keeps every existing caller
(``memory.tasks``, ``memory.context_builder``, ``mcp_server.tools.memory``)
source-compatible.

Correction vs. the implementation-plan draft (same class of bug as Task 2's
``auth_tenancy.User`` FK mistake -- see ``memory/migrations/0001_initial.py``
module docstring): the draft activated the tenant with a bare
``TenantContext.set_tenant(tenant_id)`` call. That only satisfies the
Django-ORM side (``persistence.tenancy.TenantManager`` filters/auto-injects
``tenant_id`` in Python) -- it never issues ``SET app.current_tenant`` on the
connection, so Postgres RLS's ``WITH CHECK`` (INSERT) and ``USING`` (SELECT)
policies on ``mem_memory_entry`` would reject or silently hide every row
whenever this backend runs without an already-active request/test tenant
context -- e.g. a Celery consolidation task or an MCP tool invocation with no
surrounding request. This is the exact bug already fixed once in
``llm_adapter.tasks.run_capability`` (see its ``#444``/``#522`` comments);
:func:`_tenant_context` below reuses ``persistence.middleware.
set_request_tenant``/``clear_request_tenant`` (which arm both isolation
layers) and the same "don't clear a context we did not open" nesting guard,
instead of the plan's bare ``TenantContext.set_tenant``.
"""
from __future__ import annotations

import contextlib
import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Iterator, List, Optional, Tuple, Type, Union
from uuid import UUID

from pgvector.django import CosineDistance

from llm_adapter.embedding_service import generate_embedding
from memory.models import MemoryEntry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.tenancy import TenantContext


#: Identifier of a persisted memory entry, as issued by the *active* backend.
#:
#: Every backend's :meth:`MemoryBackend.write` issues ReqogniLoom's own UUID
#: primary key (``MemoryEntry.id``). ``MemoryEntryId`` still admits ``str``
#: because a raw external id (e.g. a 21-character Honcho nanoid carried in
#: ``MemoryEntry.backend_ref``) is a legitimate input to
#: :meth:`MemoryBackend.delete_entry`/``forget``: those resolve it defensively
#: by ``backend_ref`` when it is not parseable as a UUID. Consumers must treat
#: it as an opaque token: stringify it for transport (``mcp_server.tools.
#: memory`` already does) and never feed it to a Django ``.filter(id=...)``
#: without first confirming it is UUID-shaped (see :func:`resolve_memory_entry_
#: owner` and ``memory.honcho_backend._maybe_uuid``).
MemoryEntryId = Union[UUID, str]

#: The three supported scopes. Kept as a module constant so both backends and
#: ``_scope_filter`` validate against one vocabulary instead of three
#: hand-maintained copies.
VALID_MEMORY_SCOPES = ("user", "workspace", "artifact")


@dataclass
class MemoryEntryRef:
    """Backend-agnostic view of a persisted memory entry.

    ``entry_id`` is ALWAYS ReqogniLoom's own UUID for a locally-canonical row;
    a raw external id only appears here when a similarity query found an
    external object with no local mirror (then ``distance`` is ``None`` and
    ``backend_ref`` is unset).

    ``distance`` is the backend's similarity metric to whatever query produced
    this ref (e.g. cosine distance for :meth:`MemoryBackend.query`; lower =
    more similar), or ``None`` when the ref was not produced by a similarity
    query (``write``/``upsert``/``list_recent``/``list_entries``/``delete``) or
    the backend could not compute one. Every extra field is optional and
    defaulted so existing callers/tests that construct a ``MemoryEntryRef``
    positionally keep working.
    """

    entry_id: MemoryEntryId
    content: str
    confidence: float = 1.0
    distance: Optional[float] = None
    scope: Optional[str] = None
    backend_ref: Optional[str] = None
    contributor_user_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    superseded_by: Optional[str] = None


@dataclass
class MemoryHealth:
    """Structured health result for a memory backend (RFC #1002).

    ``degraded`` is ``True`` whenever the backend is answering but cannot do
    its full job (e.g. the embedding endpoint is unconfigured) -- callers that
    only care about ``ok`` can ignore it, callers that render a dashboard can
    distinguish "down" from "up but degraded".
    """

    ok: bool
    backend: str
    detail: str
    degraded: bool = False


class MemoryBackend(ABC):
    """Provider-agnostic read/write facade for consolidated memory facts."""

    # -- canonical-store API (RFC #1002) ---------------------------------

    @abstractmethod
    def write(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        *,
        contributor_user_id: Optional[UUID] = None,
        source_event_id: Optional[UUID] = None,
        source_session_id: Optional[UUID] = None,
        language: str = "",
        confidence: float = 1.0,
        entity_type: str = "",
        backend_ref: Optional[str] = None,
    ) -> MemoryEntryRef:
        """Persist ``content`` as a new memory entry for ``scope``/``scope_id``.

        Returns a ref whose ``entry_id`` is ReqogniLoom's own UUID primary key,
        never the external backend's id (that travels in ``backend_ref``).
        """
        ...

    @abstractmethod
    def list_entries(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        *,
        limit: int = 25,
        offset: int = 0,
        q: Optional[str] = None,
    ) -> Tuple[List[MemoryEntryRef], int]:
        """Return ``(page, total)`` of live entries, newest first.

        ``total`` is the count of ALL live entries matching ``q`` (not just the
        returned page); ``q`` is a case-insensitive substring filter on
        ``content``. Live = not superseded by a newer entry.
        """
        ...

    @abstractmethod
    def count(self, tenant_id: UUID, scope: str, scope_id: UUID) -> int:
        """Return the number of live entries for ``scope``/``scope_id``."""
        ...

    @abstractmethod
    def delete_entry(self, tenant_id: UUID, entry_id: MemoryEntryId) -> bool:
        """Delete one entry, returning whether a local row was removed.

        ``entry_id`` may be our UUID or, defensively, a raw external id (looked
        up via ``backend_ref``).
        """
        ...

    @abstractmethod
    def delete_scope(self, tenant_id: UUID, scope: str, scope_id: UUID) -> int:
        """Delete every entry for ``scope``/``scope_id``; return rows removed."""
        ...

    @abstractmethod
    def health(self) -> MemoryHealth:
        """Return a structured health result; never raises."""
        ...

    # -- legacy facade (delegates to the canonical-store API) ------------

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


def _scope_filter(scope: str, scope_id: UUID) -> dict:
    """Return the ORM filter selecting ``scope``'s owner column.

    Single source of truth for the scope -> owner-column mapping that the
    unified ``MemoryEntry`` table replaced two separate tables with.
    """
    if scope == MemoryEntry.SCOPE_USER:
        return {"scope": scope, "user_id": scope_id}
    if scope == MemoryEntry.SCOPE_WORKSPACE:
        return {"scope": scope, "workspace_id": scope_id}
    if scope == MemoryEntry.SCOPE_ARTIFACT:
        return {"scope": scope, "artifact_id": scope_id}
    raise ValueError(f"unknown memory scope: {scope!r}")


def _maybe_uuid(value: object) -> Optional[UUID]:
    """Return *value* as a ``UUID``, or ``None`` when it is not UUID-shaped.

    Guards every ``.filter(id=...)`` built from a caller-supplied entry id:
    ``MemoryEntryId`` may legitimately be an external (non-UUID) id, which a
    raw ``UUIDField`` lookup would reject with ``ValidationError``.
    """
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _cosine_distance(a: Optional[list], b: Optional[list]) -> Optional[float]:
    """Return cosine distance (``1 - cosine similarity``) between two vectors.

    ``None`` when either vector is missing/empty or their widths differ --
    callers (Honcho's in-process distance, the #F5 fix) treat that as "no
    distance available", never as zero.
    """
    if a is None or b is None:
        return None
    try:
        va = [float(x) for x in a]
        vb = [float(x) for x in b]
    except (TypeError, ValueError):
        return None
    if not va or len(va) != len(vb):
        return None
    dot = sum(x * y for x, y in zip(va, vb))
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(y * y for y in vb))
    if norm_a == 0 or norm_b == 0:
        return None
    return 1.0 - (dot / (norm_a * norm_b))


def resolve_memory_entry_owner(entry_id: MemoryEntryId) -> Optional[MemoryEntry]:
    """Resolve *entry_id* to its owning :class:`MemoryEntry` row.

    Returns the row, or ``None`` when it is not UUID-shaped or no row matches.
    The table is RLS-gated, so this MUST be called with an active tenant
    context (see :func:`_tenant_context`) around it -- kept in this module
    (rather than the caller, e.g. an MCP tool) so ``mcp_server/tools/*.py``
    never needs a direct ``.objects`` access (ADR-01, issue #124 ratchet).
    """
    uid = _maybe_uuid(entry_id)
    if uid is None:
        return None
    return MemoryEntry.objects.filter(id=uid).first()


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


def _ref_from_entry(entry: MemoryEntry, *, distance: Optional[float] = None) -> MemoryEntryRef:
    """Build a :class:`MemoryEntryRef` from a canonical ``MemoryEntry`` row."""
    return MemoryEntryRef(
        entry_id=entry.id,
        content=entry.content,
        confidence=entry.confidence,
        distance=distance,
        scope=entry.scope,
        backend_ref=entry.backend_ref,
        contributor_user_id=entry.contributor_user_id,
        created_at=entry.created_at,
        superseded_by=str(entry.superseded_by_id) if entry.superseded_by_id else None,
    )


@register_memory_backend("pgvector")
class PgvectorMemoryBackend(MemoryBackend):
    """Default backend: pgvector-backed cosine-similarity search over the
    unified ``mem_memory_entry`` table, using the active
    :mod:`llm_adapter.embedding_service` provider (``EMBEDDING_PROVIDER`` env
    var) to embed content/queries.
    """

    # -- canonical-store API --------------------------------------------

    def write(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        *,
        contributor_user_id: Optional[UUID] = None,
        source_event_id: Optional[UUID] = None,
        source_session_id: Optional[UUID] = None,
        language: str = "",
        confidence: float = 1.0,
        entity_type: str = "",
        backend_ref: Optional[str] = None,
    ) -> MemoryEntryRef:
        embedding = generate_embedding(content)
        with _tenant_context(tenant_id):
            entry = MemoryEntry.objects.create(
                tenant_id=tenant_id,
                content=content,
                embedding=embedding,
                contributor_user_id=contributor_user_id,
                source_event_id=source_event_id,
                source_session_id=source_session_id,
                language=language,
                confidence=confidence,
                entity_type=entity_type,
                backend_ref=backend_ref,
                **_scope_filter(scope, scope_id),
            )
            return _ref_from_entry(entry)

    def list_entries(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        *,
        limit: int = 25,
        offset: int = 0,
        q: Optional[str] = None,
    ) -> Tuple[List[MemoryEntryRef], int]:
        with _tenant_context(tenant_id):
            qs = MemoryEntry.objects.filter(
                **_scope_filter(scope, scope_id), superseded_by__isnull=True
            )
            if q:
                qs = qs.filter(content__icontains=q)
            total = qs.count()
            rows = qs.order_by("-created_at")[max(0, offset) : max(0, offset) + max(0, limit)]
            return [_ref_from_entry(e) for e in rows], total

    def count(self, tenant_id: UUID, scope: str, scope_id: UUID) -> int:
        with _tenant_context(tenant_id):
            return MemoryEntry.objects.filter(
                **_scope_filter(scope, scope_id), superseded_by__isnull=True
            ).count()

    def delete_entry(self, tenant_id: UUID, entry_id: MemoryEntryId) -> bool:
        uid = _maybe_uuid(entry_id)
        with _tenant_context(tenant_id):
            if uid is not None:
                deleted, _ = MemoryEntry.objects.filter(id=uid).delete()
                if deleted:
                    return True
            # Defensive fallback: accept a UUID-shaped value that only matches
            # a stored ``backend_ref`` too, mirroring the honcho backend.
            deleted, _ = MemoryEntry.objects.filter(backend_ref=str(entry_id)).delete()
            return deleted > 0

    def delete_scope(self, tenant_id: UUID, scope: str, scope_id: UUID) -> int:
        with _tenant_context(tenant_id):
            deleted, _ = MemoryEntry.objects.filter(**_scope_filter(scope, scope_id)).delete()
            return deleted

    def health(self) -> MemoryHealth:
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM mem_memory_entry LIMIT 1")
            return MemoryHealth(
                ok=True, backend="pgvector", detail="mem_memory_entry table reachable"
            )
        except Exception as exc:  # noqa: BLE001 - any failure is a "down" detail
            return MemoryHealth(ok=False, backend="pgvector", detail=str(exc), degraded=True)

    # -- legacy facade ---------------------------------------------------

    def upsert(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        source_event_id: Optional[UUID] = None,
    ) -> MemoryEntryRef:
        return self.write(
            tenant_id, scope, scope_id, content, source_event_id=source_event_id
        )

    def query(
        self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5
    ) -> List[MemoryEntryRef]:
        query_embedding = generate_embedding(query_text)
        if query_embedding is None:
            return []
        with _tenant_context(tenant_id):
            qs = (
                MemoryEntry.objects.filter(
                    **_scope_filter(scope, scope_id),
                    superseded_by__isnull=True,
                    embedding__isnull=False,
                )
                .annotate(distance=CosineDistance("embedding", query_embedding))
                .order_by("distance")[:top_k]
            )
            return [_ref_from_entry(e, distance=e.distance) for e in qs]

    def list_recent(
        self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20
    ) -> List[MemoryEntryRef]:
        with _tenant_context(tenant_id):
            qs = MemoryEntry.objects.filter(
                **_scope_filter(scope, scope_id), superseded_by__isnull=True
            ).order_by("-created_at")[:limit]
            return [_ref_from_entry(e) for e in qs]

    def forget(self, tenant_id: UUID, entry_id: MemoryEntryId) -> None:
        self.delete_entry(tenant_id, entry_id)

    def health_check(self) -> tuple[bool, str]:
        result = self.health()
        return result.ok, result.detail


__all__ = [
    "MemoryEntryId",
    "MemoryEntryRef",
    "MemoryHealth",
    "MemoryBackend",
    "MEMORY_BACKEND_REGISTRY",
    "VALID_MEMORY_SCOPES",
    "register_memory_backend",
    "get_memory_backend",
    "resolve_memory_entry_owner",
    "PgvectorMemoryBackend",
]
