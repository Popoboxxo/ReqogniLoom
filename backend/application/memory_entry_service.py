"""MemoryEntryService — the single façade for memory reads/writes (RFC #1002 PR B).

REST (``memory.memory_rest``) and MCP (``mcp_server.tools.memory``) both go
through this service, mirroring ADR-01's Single-Entry-Point pattern: neither
adapter touches the ``MemoryEntry`` model or a ``MemoryBackend`` directly.

Persistence always goes through the active :class:`~memory.backends.MemoryBackend`
(pgvector or honcho), resolved via ``get_memory_backend()``; the service only
reads the canonical ``mem_memory_entry`` rows to assemble the rich
:data:`MemoryEntryView` (owner ids/provenance a backend ref does not carry).

Every response carries ``backend`` + ``degraded`` (F9): ``degraded`` is derived
from the cached backend health in :mod:`memory.health`, so "the backend is
down" is distinguishable from "nothing is remembered" — a read that returns no
rows still answers ``degraded=True`` while the backend is unhealthy.

Out of scope by decision: ``digest()`` is Phase 3 and deliberately not
implemented here.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from memory.backends import (
    MemoryEntryId,
    MemoryEntryRef,
    _maybe_uuid,
    _tenant_context,
    get_memory_backend,
)
from memory.health import envelope, is_degraded
from memory.models import MemoryEntry
from memory.policy import (
    MemoryPermissionDenied,
    MemoryPolicy,
)
from memory.ratelimit import check_write_rate_limit
from persistence.errors import NotFoundError, ValidationError

from .base import ServiceBase

#: Upper bound on ``page_size`` so a caller cannot turn a listing into a full
#: table dump. Mirrors ``memory_rest.SystemMemoryEntriesListView.MAX_PAGE_SIZE``.
MAX_PAGE_SIZE = 200

#: Default page size when the caller does not supply one.
DEFAULT_PAGE_SIZE = 25

#: Bounded scan used when filtering by ``contributor_user_id`` (an
#: admin-only filter that no ``MemoryBackend.list_entries`` supports). The scan
#: is capped so a pathological contributor query cannot load the whole table;
#: ``total`` is the number of matches *within* this window. Documented
#: trade-off — this is an admin debugging surface, not a paging contract.
CONTRIBUTOR_SCAN_LIMIT = 500

#: Scopes a caller may name. Kept next to the service so a typo fails with a
#: clear ValidationError before any backend call.
VALID_SCOPES = ("user", "workspace", "artifact")


def _as_uuid(value: Any) -> Optional[UUID]:
    """Return *value* as a ``UUID`` when UUID-shaped, else ``None``."""
    return _maybe_uuid(value)


class MemoryEntryService(ServiceBase):
    """Single façade for consolidated memory entries over ``MemoryBackend``."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        ctx: Any,
        *,
        content: str,
        scope: str,
        workspace_id: Any = None,
        artifact_id: Any = None,
        confidence: float = 1.0,
        source_event_id: Any = None,
        change_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create one memory entry for ``scope`` and return its view.

        ``scope="user"`` writes for ``ctx.user_id`` (any authenticated caller);
        ``scope="workspace"`` requires Editor+ in ``workspace_id``;
        ``scope="artifact"`` requires Editor+ in the artifact's workspace. The
        write ratelimit (:mod:`memory.ratelimit`) is enforced *before* the
        backend call.
        """
        content = (content or "").strip()
        if not content:
            raise ValidationError("content must not be empty")
        self._validate_scope(scope)
        self._validate_scope_target(scope, workspace_id, artifact_id)

        with _tenant_context(ctx.tenant_id):
            MemoryPolicy.assert_can_write(
                ctx, scope=scope, workspace_id=workspace_id, artifact_id=artifact_id
            )
            check_write_rate_limit(ctx)
            backend = get_memory_backend()
            scope_id = self._scope_id(ctx, scope, workspace_id, artifact_id)
            ref = backend.write(
                ctx.tenant_id,
                scope,
                scope_id,
                content,
                contributor_user_id=ctx.user_id,
                source_event_id=_as_uuid(source_event_id),
                confidence=confidence,
            )
            entry = self._fetch_entry(ref.entry_id)
            view = self._view(ref=ref, row=entry, scope=scope, scope_id=scope_id)
            self._audit(
                ctx,
                operation="create",
                entity_type="MemoryEntry",
                entity_id=self._entry_uuid(ref.entry_id),
                change_reason=change_reason,
            )
        return view

    def list(
        self,
        ctx: Any,
        *,
        workspace_id: Any = None,
        scope: Optional[str] = None,
        artifact_id: Any = None,
        contributor_user_id: Any = None,
        q: Optional[str] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Dict[str, Any]:
        """Return one page of live entries for a single scope.

        ``scope`` defaults to ``artifact`` when ``artifact_id`` is given, else
        ``workspace`` when ``workspace_id`` is given, else ``user``. Results
        carry the ``backend``/``degraded`` envelope.
        """
        scope = self._default_scope(scope, workspace_id, artifact_id)
        self._validate_scope(scope)
        self._validate_scope_target(scope, workspace_id, artifact_id)
        if contributor_user_id is not None:
            # "Only surfaced to admins": a caller may inspect their own
            # contribution, anyone else only with System-Admin standing.
            if _as_uuid(contributor_user_id) != ctx.user_id and not MemoryPolicy.can_purge(ctx):
                raise MemoryPermissionDenied(
                    "Permission denied: only System-Admins may filter by contributor"
                )

        page = max(1, int(page))
        page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        offset = (page - 1) * page_size

        with _tenant_context(ctx.tenant_id):
            self._assert_can_read_scope(ctx, scope, workspace_id, artifact_id)
            backend = get_memory_backend()
            scope_id = self._scope_id(ctx, scope, workspace_id, artifact_id)
            if contributor_user_id is not None:
                items, total = self._contributor_page(
                    backend,
                    ctx,
                    scope,
                    scope_id,
                    contributor_user_id,
                    q,
                    offset,
                    page_size,
                )
            else:
                refs, total = backend.list_entries(
                    ctx.tenant_id,
                    scope,
                    scope_id,
                    limit=page_size,
                    offset=offset,
                    q=q,
                )
                items = self._views_for_refs(refs, scope=scope, scope_id=scope_id)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            **envelope(),
        }

    def search(
        self,
        ctx: Any,
        *,
        query: str,
        scopes: Any = None,
        workspace_id: Any = None,
        artifact_id: Any = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Semantic search across one or more scopes, merged by distance.

        ``scopes`` defaults to ``artifact`` when ``artifact_id`` is given, else
        ``workspace`` when ``workspace_id`` is given, else ``user``. Every
        requested scope must be readable by the caller (fail-closed).
        """
        query = (query or "").strip()
        if not query:
            raise ValidationError("query must not be empty")
        scope_list = self._normalize_scopes(scopes, workspace_id, artifact_id)
        top_k = max(1, min(int(top_k), MAX_PAGE_SIZE))

        merged: List[Tuple[Optional[float], str, MemoryEntryRef, str, UUID]] = []
        seen: set = set()
        backend_error: Optional[str] = None

        with _tenant_context(ctx.tenant_id):
            for scope in scope_list:
                self._assert_can_read_scope(ctx, scope, workspace_id, artifact_id)
            backend = get_memory_backend()
            for scope in scope_list:
                scope_id = self._scope_id(ctx, scope, workspace_id, artifact_id)
                try:
                    refs = backend.query(
                        ctx.tenant_id, scope, scope_id, query, top_k=top_k
                    )
                except Exception as exc:  # noqa: BLE001 - F9: report, never swallow
                    backend_error = str(exc)
                    continue
                for ref in refs:
                    key = str(ref.entry_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append((ref.distance, key, ref, scope, scope_id))

            merged.sort(key=lambda row: (row[0] is None, row[0] if row[0] is not None else 0.0))
            refs_sorted = [row[2] for row in merged[:top_k]]
            items = self._views_for_refs(refs_sorted, scope=None, scope_id=None)

        degraded = is_degraded() or backend_error is not None
        for item in items:
            item["degraded"] = degraded
            if backend_error is not None:
                item["detail"] = backend_error
        return {"items": items, "query": query, "scopes": scope_list, **envelope()}

    def get(self, ctx: Any, *, entry_id: MemoryEntryId) -> Dict[str, Any]:
        """Return one entry's full view (provenance included)."""
        with _tenant_context(ctx.tenant_id):
            entry = self._resolve_entry(entry_id)
            if entry is None:
                raise NotFoundError(f"Memory entry {entry_id} not found")
            MemoryPolicy.assert_can_read(ctx, entry)
            ref = None
            view = self._view(ref=ref, row=entry, scope=entry.scope, scope_id=None)
        return view

    def forget(
        self, ctx: Any, *, entry_id: MemoryEntryId, change_reason: Optional[str] = None
    ) -> None:
        """Delete one entry (local row + external backend object)."""
        with _tenant_context(ctx.tenant_id):
            entry = self._resolve_entry(entry_id)
            if entry is None:
                raise NotFoundError(f"Memory entry {entry_id} not found")
            MemoryPolicy.assert_can_delete(ctx, entry)
            get_memory_backend().delete_entry(ctx.tenant_id, entry_id)
            self._audit(
                ctx,
                operation="delete",
                entity_type="MemoryEntry",
                entity_id=entry.id,
                change_reason=change_reason,
            )

    def delete_scope(
        self,
        ctx: Any,
        *,
        scope: str,
        workspace_id: Any = None,
        artifact_id: Any = None,
        change_reason: Optional[str] = None,
    ) -> int:
        """Delete every entry of one scope; return the number of rows removed."""
        self._validate_scope(scope)
        self._validate_scope_target(scope, workspace_id, artifact_id)
        with _tenant_context(ctx.tenant_id):
            self._assert_can_delete_scope(ctx, scope, workspace_id, artifact_id)
            scope_id = self._scope_id(ctx, scope, workspace_id, artifact_id)
            removed = get_memory_backend().delete_scope(ctx.tenant_id, scope, scope_id)
            self._audit(
                ctx,
                operation="delete",
                entity_type="MemoryEntry",
                entity_id=scope_id,
                change_reason=(
                    f"{change_reason + ' ' if change_reason else ''}"
                    f"scope={scope} deleted={removed}"
                ),
            )
            return removed

    def promote(
        self,
        ctx: Any,
        *,
        entry_id: MemoryEntryId,
        target_scope: str = "workspace",
        workspace_id: Any = None,
        change_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Promote a ``user``-scoped entry into ``workspace`` scope.

        Writes a new workspace-scoped entry carrying the same content and
        provenance, then marks the original ``superseded_by`` the new entry. The
        target workspace is ``workspace_id`` or, failing that, the active
        request workspace (``ctx.workspace_id``); Editor+ is required.
        """
        if target_scope != "workspace":
            raise ValidationError(
                f"Unsupported promote target_scope: {target_scope!r} (only 'workspace')"
            )
        target_workspace_id = _as_uuid(workspace_id) or getattr(ctx, "workspace_id", None)
        if target_workspace_id is None:
            raise ValidationError("workspace_id is required to promote into workspace scope")

        with _tenant_context(ctx.tenant_id):
            entry = self._resolve_entry(entry_id)
            if entry is None:
                raise NotFoundError(f"Memory entry {entry_id} not found")
            if entry.scope != MemoryEntry.SCOPE_USER or entry.user_id != ctx.user_id:
                raise MemoryPermissionDenied(
                    "Only the owner may promote their own user-scoped memory"
                )
            MemoryPolicy.assert_can_write(
                ctx, scope=MemoryEntry.SCOPE_WORKSPACE, workspace_id=target_workspace_id
            )
            check_write_rate_limit(ctx)
            backend = get_memory_backend()
            ref = backend.write(
                ctx.tenant_id,
                MemoryEntry.SCOPE_WORKSPACE,
                target_workspace_id,
                entry.content,
                contributor_user_id=entry.contributor_user_id or ctx.user_id,
                source_event_id=entry.source_event_id,
                language=entry.language,
                confidence=entry.confidence,
                entity_type=entry.entity_type,
            )
            new_entry = self._fetch_entry(ref.entry_id)
            new_uuid = _as_uuid(ref.entry_id)
            if new_uuid is not None:
                # Same-tenant update through the tenant-scoped manager: the
                # active instance cannot be used because it belongs to the
                # user-scoped row, and ``update()`` also avoids a full save of
                # every provenance column.
                MemoryEntry.objects.filter(id=entry.id).update(superseded_by_id=new_uuid)
            view = self._view(
                ref=ref,
                row=new_entry,
                scope=MemoryEntry.SCOPE_WORKSPACE,
                scope_id=target_workspace_id,
            )
            self._audit(
                ctx,
                operation="update",
                entity_type="MemoryEntry",
                entity_id=entry.id,
                change_reason=(
                    f"{change_reason + ' ' if change_reason else ''}"
                    f"promoted_to=workspace superseded_by={view['entry_id']}"
                ),
            )
        return view

    def health(self) -> Dict[str, Any]:
        """Return the structured backend health envelope."""
        return envelope()

    # ------------------------------------------------------------------
    # Internals — scope + permission plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_scope(scope: str) -> None:
        if scope not in VALID_SCOPES:
            raise ValidationError(
                f"Unknown memory scope: {scope!r} (expected one of {VALID_SCOPES})"
            )

    @staticmethod
    def _validate_scope_target(scope: str, workspace_id: Any, artifact_id: Any) -> None:
        """Enforce the owner-argument contract for *scope*."""
        if scope == MemoryEntry.SCOPE_USER:
            if workspace_id is not None or artifact_id is not None:
                raise ValidationError(
                    "scope='user' must not carry workspace_id or artifact_id"
                )
        elif scope == MemoryEntry.SCOPE_WORKSPACE:
            if workspace_id is None:
                raise ValidationError("workspace_id is required for scope='workspace'")
        elif scope == MemoryEntry.SCOPE_ARTIFACT:
            if artifact_id is None:
                raise ValidationError("artifact_id is required for scope='artifact'")

    @staticmethod
    def _default_scope(
        scope: Optional[str], workspace_id: Any, artifact_id: Any
    ) -> str:
        if scope:
            return scope
        if artifact_id is not None:
            return MemoryEntry.SCOPE_ARTIFACT
        if workspace_id is not None:
            return MemoryEntry.SCOPE_WORKSPACE
        return MemoryEntry.SCOPE_USER

    @staticmethod
    def _normalize_scopes(
        scopes: Any, workspace_id: Any, artifact_id: Any
    ) -> List[str]:
        if scopes is None:
            return [MemoryEntryService._default_scope(None, workspace_id, artifact_id)]
        if isinstance(scopes, str):
            scopes = [scopes]
        normalized = []
        for scope in scopes:
            if scope not in VALID_SCOPES:
                raise ValidationError(
                    f"Unknown memory scope: {scope!r} (expected one of {VALID_SCOPES})"
                )
            if scope not in normalized:
                normalized.append(scope)
        if not normalized:
            raise ValidationError("scopes must not be empty")
        return normalized

    @staticmethod
    def _scope_id(
        ctx: Any, scope: str, workspace_id: Any, artifact_id: Any
    ) -> UUID:
        """Resolve the backend ``scope_id`` for *scope*."""
        if scope == MemoryEntry.SCOPE_USER:
            return ctx.user_id
        if scope == MemoryEntry.SCOPE_WORKSPACE:
            resolved = _as_uuid(workspace_id)
        else:
            resolved = _as_uuid(artifact_id)
        if resolved is None:
            raise ValidationError(f"Invalid id for scope={scope!r}")
        return resolved

    @staticmethod
    def _assert_can_read_scope(
        ctx: Any, scope: str, workspace_id: Any, artifact_id: Any
    ) -> None:
        if not MemoryPolicy.can_read_scope(
            ctx,
            scope=scope,
            user_id=ctx.user_id,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        ):
            raise MemoryPermissionDenied(
                f"Permission denied: cannot read {scope!r}-scoped memory"
            )

    @staticmethod
    def _assert_can_delete_scope(
        ctx: Any, scope: str, workspace_id: Any, artifact_id: Any
    ) -> None:
        if not MemoryPolicy.can_delete_scope(
            ctx,
            scope=scope,
            user_id=ctx.user_id,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        ):
            raise MemoryPermissionDenied(
                f"Permission denied: cannot delete {scope!r}-scoped memory"
            )

    # ------------------------------------------------------------------
    # Internals — persistence + view assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_entry(entry_id: MemoryEntryId) -> Optional[MemoryEntry]:
        """Resolve *entry_id* to its row, tolerating an external backend id.

        A UUID is looked up by primary key; anything else (e.g. a honcho nanoid)
        — and, defensively, a UUID that matched no row — is looked up via
        ``backend_ref``. Requires an active tenant context (RLS-gated table).
        """
        uid = _as_uuid(entry_id)
        if uid is not None:
            row = MemoryEntry.objects.filter(id=uid).first()
            if row is not None:
                return row
        return MemoryEntry.objects.filter(backend_ref=str(entry_id)).first()

    @staticmethod
    def _fetch_entry(entry_id: MemoryEntryId) -> Optional[MemoryEntry]:
        uid = _as_uuid(entry_id)
        if uid is None:
            return None
        return MemoryEntry.objects.filter(id=uid).first()

    @staticmethod
    def _entry_uuid(entry_id: MemoryEntryId) -> UUID:
        """Return a UUID suitable for the audit log.

        A backend that returns a non-UUID id (not possible for the local mirror,
        but the backend contract admits an external id) cannot be represented as
        an audit ``entity_id`` — fall back to a random UUID so the audit write
        (which is mandatory) still succeeds rather than aborting the write.
        """
        uid = _as_uuid(entry_id)
        if uid is not None:
            return uid
        from uuid import uuid4

        return uuid4()

    def _views_for_refs(
        self,
        refs: Sequence[MemoryEntryRef],
        *,
        scope: Optional[str],
        scope_id: Optional[UUID],
    ) -> List[Dict[str, Any]]:
        """Bulk-assemble views for a page of backend refs (one extra query)."""
        rows = self._load_rows(refs)
        env = envelope()
        return [
            self._view(
                ref=ref,
                row=rows.get(str(ref.entry_id)),
                scope=scope,
                scope_id=scope_id,
                env=env,
            )
            for ref in refs
        ]

    @staticmethod
    def _load_rows(refs: Iterable[MemoryEntryRef]) -> Dict[str, MemoryEntry]:
        ids = [uid for uid in (_as_uuid(ref.entry_id) for ref in refs) if uid is not None]
        if not ids:
            return {}
        return {str(entry.id): entry for entry in MemoryEntry.objects.filter(id__in=ids)}

    def _contributor_page(
        self,
        backend: Any,
        ctx: Any,
        scope: str,
        scope_id: UUID,
        contributor_user_id: Any,
        q: Optional[str],
        offset: int,
        page_size: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Admin-only contributor filter over a bounded backend scan."""
        contributor = _as_uuid(contributor_user_id)
        refs, _ = backend.list_entries(
            ctx.tenant_id, scope, scope_id, limit=CONTRIBUTOR_SCAN_LIMIT, offset=0, q=q
        )
        matching = [ref for ref in refs if ref.contributor_user_id == contributor]
        total = len(matching)
        page_refs = matching[offset : offset + page_size]
        return self._views_for_refs(page_refs, scope=scope, scope_id=scope_id), total

    def _view(
        self,
        *,
        ref: Optional[MemoryEntryRef],
        row: Optional[MemoryEntry],
        scope: Optional[str],
        scope_id: Optional[UUID],
        env: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a :data:`MemoryEntryView` from a row, falling back to a ref.

        The canonical row is preferred: it carries owner ids and the full
        provenance. A ref without a local mirror (an external honcho conclusion
        from ``query``) still yields a view, with the fields the backend could
        not provide left null and the requested ``scope``/``scope_id`` used as
        owner hint.
        """
        backend_env = env if env is not None else envelope()
        if row is not None:
            return {
                "entry_id": str(row.id),
                "content": row.content,
                "scope": row.scope,
                "workspace_id": str(row.workspace_id) if row.workspace_id else None,
                "user_id": str(row.user_id) if row.user_id else None,
                "artifact_id": str(row.artifact_id) if row.artifact_id else None,
                "entity_type": row.entity_type or "",
                "contributor_user_id": (
                    str(row.contributor_user_id) if row.contributor_user_id else None
                ),
                "source_event_id": (
                    str(row.source_event_id) if row.source_event_id else None
                ),
                "source_session_id": (
                    str(row.source_session_id) if row.source_session_id else None
                ),
                "confidence": row.confidence,
                "language": row.language or "",
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "superseded_by": (
                    str(row.superseded_by_id) if row.superseded_by_id else None
                ),
                **backend_env,
            }
        if ref is None:
            # ``get`` always resolves a row; this branch is only reachable with
            # a ref-less call, which no caller makes. Defensive empty view.
            return {"entry_id": None, "content": "", "scope": scope, **backend_env}
        owner_scope = ref.scope or scope
        return {
            "entry_id": str(ref.entry_id),
            "content": ref.content,
            "scope": owner_scope,
            "workspace_id": (
                str(scope_id) if owner_scope == MemoryEntry.SCOPE_WORKSPACE else None
            ),
            "user_id": str(scope_id) if owner_scope == MemoryEntry.SCOPE_USER else None,
            "artifact_id": (
                str(scope_id) if owner_scope == MemoryEntry.SCOPE_ARTIFACT else None
            ),
            "entity_type": "",
            "contributor_user_id": (
                str(ref.contributor_user_id) if ref.contributor_user_id else None
            ),
            "source_event_id": None,
            "source_session_id": None,
            "confidence": ref.confidence,
            "language": "",
            "created_at": ref.created_at.isoformat() if ref.created_at else None,
            "superseded_by": ref.superseded_by,
            "backend_ref": ref.backend_ref,
            **backend_env,
        }


__all__ = [
    "MemoryEntryService",
    "MAX_PAGE_SIZE",
    "DEFAULT_PAGE_SIZE",
    "CONTRIBUTOR_SCAN_LIMIT",
    "VALID_SCOPES",
]
