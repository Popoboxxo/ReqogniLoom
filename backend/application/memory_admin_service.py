"""MemoryAdminService — System-Admin operations over consolidated memory
(Memory Admin UI Phase 1 + Phase 5, spec 2026-08-26).

Every public method runs only inside an already-active request-scoped tenant
context (reached exclusively via a real HTTP request through
``AuthTenancyAuthentication``, never from Celery) — this mirrors
``memory/memory_rest.py``'s existing views and its module docstring's
explicit warning against a bare ``TenantContext.set_tenant(...)`` call:
that call only satisfies the Django-ORM side and never arms Postgres RLS.
Since this service is never invoked outside a request, no such call is
needed here at all.

Phase 5 adds two read-only visualization methods, :meth:`MemoryAdminService.
list_entries` and :meth:`MemoryAdminService.get_projection`. Both operate on
LIVE entries only (``superseded_by__isnull=True``): ``superseded_by`` marks a
fact replaced by a newer one without deleting the historical row, and a
visualization answering "what does the AI currently remember" must show live
facts, not consolidation history (Phase 5 plan Ruling 5).

Id serialization: unlike :meth:`list_workspace_overview` (which returns raw
``uuid.UUID`` values that its view stringifies), the two Phase 5 methods
return already-stringified ids. ``get_projection``'s result is cached
verbatim in Redis and handed straight back to the caller on a hit, so the
wire shape has to be produced once, at the point the value is built — not in
a view-level coercion loop that a cached response would have to repeat.
``list_entries`` follows the same convention so both new endpoints agree.
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.db.models import Count, Max

from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserRole
from auth_tenancy.services import AuthorizationService
from llm_adapter.embedding_service import generate_embedding
from memory.backends import get_memory_backend
from memory.health import is_degraded
from memory.models import MemoryEntry, WorkspaceMemorySettings
from persistence.models import Artifact, User, Workspace
from persistence.transactions import atomic_transaction

from .base import NotFoundError, PermissionDeniedError, ServiceBase, ValidationError

# Two entries land in the same cluster when their cosine similarity reaches
# this value, transitively (Phase 5 plan Ruling 8). Module-level constant, not
# a magic number inlined into the clustering call.
CLUSTER_SIMILARITY_THRESHOLD = 0.85

# Above this many embedded entries the projection is computed on a
# deterministic sample instead (Phase 5 plan Ruling 9). Also the bound that
# keeps the O(n^2) similarity matrix affordable.
MAX_PROJECTION_POINTS = 5000

# Same value/rationale as ``application.context_service._CACHE_TTL_SECONDS``:
# short-lived cache for an expensive-to-recompute read model. Invalidation is
# TTL-only plus the watermark in the cache key (Phase 5 plan Ruling 10) —
# memory writes never bust this cache explicitly.
_CACHE_TTL_SECONDS = 300


def _deterministic_sample(rows: list[Any], max_size: int) -> tuple[list[Any], bool]:
    """Return ``(sample, was_sampled)`` — every ``ceil(total/max_size)``-th row.

    Deterministic by construction: *rows* is expected to already be in a
    stable order (``created_at``, then ``id`` as tiebreaker), so the same
    dataset always yields the same sample. Guarantees ``len(sample) <=
    max_size`` for every ``total`` (Phase 5 plan Ruling 9).
    """
    total = len(rows)
    if total <= max_size:
        return rows, False
    # floor (not ceil) division for the stride: ceil-rounding the step
    # overshoots as soon as total exceeds max_size by even one row (e.g.
    # total=5001, max_size=5000 -> ceil gives step=2, halving the sample to
    # ~2501 instead of the ~5000 intended). A floor step can in turn yield
    # slightly MORE than max_size rows when total isn't an exact multiple,
    # so the explicit [:max_size] slice enforces the hard cap either way.
    step = max(1, total // max_size)
    return rows[::step][:max_size], True


def _pca_2d(matrix: Any) -> Any:
    """Project ``(N, D)`` *matrix* onto its first two principal components.

    Mean-centres, then takes the top-2 right singular vectors of the SVD.
    Note the sign of a singular vector is not deterministic across
    numpy/BLAS builds — callers (and tests) may rely on relative structure,
    never on absolute coordinate values.
    """
    import numpy as np

    centered = matrix - matrix.mean(axis=0, keepdims=True)
    _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
    coords = centered @ vt[:2].T
    if coords.shape[1] < 2:
        # Degenerate input (e.g. every vector identical in a 1-D space):
        # pad so the caller always gets an (N, 2) result.
        padding = np.zeros((coords.shape[0], 2 - coords.shape[1]), dtype=coords.dtype)
        coords = np.hstack([coords, padding])
    return coords


def _cluster_ids(matrix: Any, threshold: float) -> list[int]:
    """Union-find connected components over the cosine-similarity graph.

    The pairwise similarity is computed as a single vectorized
    ``normalized @ normalized.T`` matrix product — never a Python-level
    double loop over entries, which would be unusably slow at the
    :data:`MAX_PROJECTION_POINTS` bound (Phase 5 plan Ruling 8). Neighbour
    extraction stays vectorized per row (``np.nonzero`` on a row slice)
    rather than materializing ~12.5M ``triu_indices`` pairs.

    ``cluster_id`` is an arbitrary but stable integer per connected
    component, numbered in order of first appearance.
    """
    import numpy as np

    n = matrix.shape[0]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    # A zero vector has no direction; treat its norm as 1 so the division is
    # safe and it simply ends up dissimilar to everything (similarity 0).
    norms[norms == 0] = 1.0
    normalized = matrix / norms
    similarity = normalized @ normalized.T

    parent = list(range(n))

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    for i in range(n):
        neighbours = np.nonzero(similarity[i, i + 1:] >= threshold)[0]
        if neighbours.size == 0:
            continue
        root_i = find(i)
        for offset in neighbours.tolist():
            root_j = find(i + 1 + offset)
            if root_j != root_i:
                parent[root_j] = root_i

    mapping: dict[int, int] = {}
    ids: list[int] = []
    for i in range(n):
        root = find(i)
        if root not in mapping:
            mapping[root] = len(mapping)
        ids.append(mapping[root])
    return ids


class MemoryAdminService(ServiceBase):
    """System-Admin-only read/delete operations over workspace + user memory."""

    @staticmethod
    def _assert_system_admin(ctx: AuthContext) -> None:
        """System-Admin check: tenant-wide admin only (NOT workspace-scoped
        ``has_role("admin")``, which on an endpoint with a ``workspace_id`` URL
        kwarg means "admin of that one workspace" — see auth_tenancy.workspace_scope).
        """
        if AuthorizationService().is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id):
            return
        raise PermissionDeniedError("System-Admin role required")

    @staticmethod
    def _member_ids(workspace_id: UUID) -> list[UUID]:
        """Current (non-suspended) member user ids of *workspace_id*."""
        return list(
            UserRole.objects.filter(workspace_id=workspace_id, suspended_at__isnull=True)
            .values_list("user_id", flat=True)
            .distinct()
        )

    def list_workspace_overview(self, ctx: AuthContext) -> list[dict[str, Any]]:
        """Return one overview row per workspace in the active tenant.

        Relies on ``Workspace.objects``/``WorkspaceMemorySettings.objects``
        (both ``TenantScopedModel`` managers) already being scoped to the
        active tenant context — no manual ``tenant_id`` filter needed for
        reads (only writes need it explicitly, see
        ``WorkspaceMemorySettingsView.put``'s comment on ``update_or_create``).
        """
        self._assert_system_admin(ctx)

        settings_by_ws = {
            s.workspace_id: s.enabled for s in WorkspaceMemorySettings.objects.all()
        }
        degraded = is_degraded()

        overview: list[dict[str, Any]] = []
        for ws in Workspace.objects.all().order_by("name"):
            ws_agg = MemoryEntry.objects.filter(
                scope=MemoryEntry.SCOPE_WORKSPACE, workspace_id=ws.id
            ).aggregate(count=Count("id"), last=Max("created_at"))
            ws_count = ws_agg["count"]
            last_ws = ws_agg["last"]

            member_ids = self._member_ids(ws.id)
            if member_ids:
                user_agg = MemoryEntry.objects.filter(
                    scope=MemoryEntry.SCOPE_USER, user_id__in=member_ids
                ).aggregate(count=Count("id"), last=Max("created_at"))
                user_count = user_agg["count"]
                last_user = user_agg["last"]
            else:
                user_count = 0
                last_user = None

            # RFC #1002 PR B: the artifact tier this workspace owns, plus the
            # distinct contributors across the two team-owned tiers.
            artifact_count = MemoryEntry.objects.filter(
                scope=MemoryEntry.SCOPE_ARTIFACT, artifact__workspace_id=ws.id
            ).count()
            contributors = set(
                MemoryEntry.objects.filter(
                    scope=MemoryEntry.SCOPE_WORKSPACE, workspace_id=ws.id
                ).values_list("contributor_user_id", flat=True)
            )
            if member_ids:
                contributors |= set(
                    MemoryEntry.objects.filter(
                        scope=MemoryEntry.SCOPE_USER, user_id__in=member_ids
                    ).values_list("contributor_user_id", flat=True)
                )
            contributors.discard(None)

            candidates = [d for d in (last_ws, last_user) if d is not None]
            last_consolidated = max(candidates) if candidates else None

            overview.append(
                {
                    "workspace_id": ws.id,
                    "workspace_name": ws.name,
                    "enabled": settings_by_ws.get(ws.id, True),
                    "workspace_entry_count": ws_count,
                    "user_entry_count": user_count,
                    "by_scope": {
                        "workspace": ws_count,
                        "user": user_count,
                        "artifact": artifact_count,
                    },
                    "contributor_count": len(contributors),
                    "degraded": degraded,
                    "last_consolidated_at": last_consolidated,
                }
            )
        return overview

    @atomic_transaction
    def delete_workspace_memory(self, ctx: AuthContext, workspace_id: UUID) -> dict[str, Any]:
        """Delete every memory tier for *workspace_id* through the backend.

        RFC #1002 PR B (F4 / DSGVO): deletion now goes through
        ``MemoryBackend.delete_scope`` for each scope the workspace owns, so the
        EXTERNAL backend is purged too — deleting only the local mirror (the
        pre-PR behaviour) left the user's content on a Honcho instance. Purged
        scopes:

        * ``workspace`` — the workspace's own entries;
        * ``artifact`` — every entry scoped to one of the workspace's artifacts;
        * ``user`` — the ``scope="user"`` entries of the workspace's CURRENT
          members (never a non-member, even if they have other memberships).

        The per-scope counters returned by the backend are audited.
        """
        self._assert_system_admin(ctx)

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        member_ids = self._member_ids(workspace_id)
        artifact_ids = list(
            Artifact.objects.filter(workspace_id=workspace_id).values_list("id", flat=True)
        )
        backend = get_memory_backend()

        ws_deleted = backend.delete_scope(ctx.tenant_id, "workspace", workspace_id)
        artifact_deleted = 0
        for artifact_id in artifact_ids:
            artifact_deleted += backend.delete_scope(ctx.tenant_id, "artifact", artifact_id)
        user_deleted = 0
        for member_id in member_ids:
            user_deleted += backend.delete_scope(ctx.tenant_id, "user", member_id)

        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="MemoryEntry",
            entity_id=workspace_id,
            change_reason=(
                f"workspace_memory_deleted={ws_deleted} "
                f"artifact_memory_deleted={artifact_deleted} "
                f"user_memory_deleted={user_deleted} "
                f"affected_member_ids={[str(uid) for uid in member_ids]}"
            ),
        )

        return {
            "workspace_id": workspace_id,
            "workspace_memory_deleted": ws_deleted,
            "artifact_memory_deleted": artifact_deleted,
            "user_memory_deleted": user_deleted,
        }

    # ------------------------------------------------------------------
    # Phase 5 — visualization (read-only)
    # ------------------------------------------------------------------

    def _scoped_querysets(self, scope: str, workspace_id: UUID | None) -> tuple[Any, Any]:
        """Return ``(workspace-scope qs, user-scope qs)`` for *scope*, live
        (non-superseded) ``MemoryEntry`` rows only.

        ``scope="workspace"`` = that workspace's own ``scope="workspace"`` rows
        plus its CURRENT members' ``scope="user"`` rows — the exact same
        member scoping :meth:`delete_workspace_memory` applies, via the shared
        :meth:`_member_ids` helper.

        ``scope="global"`` just drops the workspace filter; it never crosses a
        tenant boundary, because both managers are ``TenantScopedModel``
        managers already scoped to the active tenant (Phase 5 plan Ruling 4).
        """
        if scope == "workspace":
            if workspace_id is None:
                raise ValidationError("workspace_id is required for scope=workspace")
            if not Workspace.objects.filter(id=workspace_id).exists():
                raise NotFoundError(f"Workspace {workspace_id} not found")
            member_ids = self._member_ids(workspace_id)
            ws_qs = MemoryEntry.objects.filter(
                scope=MemoryEntry.SCOPE_WORKSPACE,
                workspace_id=workspace_id,
                superseded_by__isnull=True,
            )
            user_qs = (
                MemoryEntry.objects.filter(
                    scope=MemoryEntry.SCOPE_USER,
                    user_id__in=member_ids,
                    superseded_by__isnull=True,
                )
                if member_ids
                else MemoryEntry.objects.none()
            )
        elif scope == "global":
            ws_qs = MemoryEntry.objects.filter(
                scope=MemoryEntry.SCOPE_WORKSPACE, superseded_by__isnull=True
            )
            user_qs = MemoryEntry.objects.filter(
                scope=MemoryEntry.SCOPE_USER, superseded_by__isnull=True
            )
        else:
            raise ValidationError(f"Unknown scope: {scope!r}")
        return ws_qs, user_qs

    @staticmethod
    def _owner_labels(
        workspace_ids: set[UUID], user_ids: set[UUID]
    ) -> tuple[dict[UUID, str], dict[UUID, str]]:
        """Batch-resolve owner labels: workspace ``name`` / user ``email``.

        Two queries per call regardless of row count (Phase 5 plan Ruling 7 —
        no N+1). ``User`` is deliberately NOT filtered by tenant: it does not
        inherit ``TenantScopedModel`` (its ``tenant`` is nullable, see
        ``persistence.models.User``'s docstring), and the ids passed in were
        already read out of the tenant-scoped ``MemoryEntry`` rows, so
        the tenant boundary was enforced upstream. Filtering on
        ``User.tenant`` here would instead silently drop the label of a
        tenant-less platform user who does have memory in this tenant.
        """
        ws_labels = {
            ws_id: name
            for ws_id, name in Workspace.objects.filter(id__in=workspace_ids).values_list(
                "id", "name"
            )
        }
        user_labels = {
            user_id: email
            for user_id, email in User.objects.filter(id__in=user_ids).values_list(
                "id", "email"
            )
        }
        return ws_labels, user_labels

    def _scoped_targets(
        self, scope: str, workspace_id: UUID | None
    ) -> list[tuple[str, UUID, str]]:
        """Return ``(scope, owner_id, owner_type)`` rows backing a merged listing.

        ``scope="workspace"`` = that workspace's own ``scope="workspace"``
        entries plus its CURRENT members' ``scope="user"`` entries — the exact
        member scoping :meth:`delete_workspace_memory` applies, via the shared
        :meth:`_member_ids` helper.

        ``scope="global"`` enumerates every workspace plus every user that owns
        user-scoped memory in the tenant. The user-id enumeration is the only
        ORM touch here and selects ids only (``values_list``), never content:
        the backend contract has no "distinct owners" query, so the set of
        owners has to be discovered somewhere. It never crosses a tenant
        boundary — ``MemoryEntry``/``Workspace`` are tenant-scoped managers.
        """
        if scope == "workspace":
            if workspace_id is None:
                raise ValidationError("workspace_id is required for scope=workspace")
            if not Workspace.objects.filter(id=workspace_id).exists():
                raise NotFoundError(f"Workspace {workspace_id} not found")
            targets: list[tuple[str, UUID, str]] = [
                (MemoryEntry.SCOPE_WORKSPACE, workspace_id, "workspace")
            ]
            targets += [
                (MemoryEntry.SCOPE_USER, member_id, "user")
                for member_id in self._member_ids(workspace_id)
            ]
            return targets
        if scope == "global":
            targets = [
                (MemoryEntry.SCOPE_WORKSPACE, ws_id, "workspace")
                for ws_id in Workspace.objects.values_list("id", flat=True)
            ]
            user_ids = (
                MemoryEntry.objects.filter(scope=MemoryEntry.SCOPE_USER)
                .values_list("user_id", flat=True)
                .distinct()
            )
            targets += [
                (MemoryEntry.SCOPE_USER, user_id, "user") for user_id in user_ids if user_id
            ]
            return targets
        raise ValidationError(f"Unknown scope: {scope!r}")

    def list_entries(
        self,
        ctx: AuthContext,
        scope: str,
        workspace_id: UUID | None = None,
        page: int = 1,
        page_size: int = 25,
        q: str | None = None,
    ) -> dict[str, Any]:
        """Return one page of live entries across BOTH team-owned tiers.

        RFC #1002 PR B: content now comes from ``MemoryBackend.list_entries``
        (backend-agnostic — a honcho deployment lists from its local mirror the
        same way pgvector lists from the table), one call per scoped owner. The
        merge, sort and page slice are the same as before: the newest
        ``offset + page_size`` rows of each target are enough for a merged
        top-K. Totals are read with ``limit=0`` so an out-of-range page never
        projects a content column.
        """
        self._assert_system_admin(ctx)

        targets = self._scoped_targets(scope, workspace_id)
        backend = get_memory_backend()

        page = max(1, int(page))
        page_size = max(1, int(page_size))

        count = 0
        for target_scope, owner_id, _owner_type in targets:
            _refs, total = backend.list_entries(
                ctx.tenant_id, target_scope, owner_id, limit=0, offset=0, q=q
            )
            count += total

        offset = (page - 1) * page_size
        if offset >= count:
            # Short-circuits an out-of-range page, and caps the per-target
            # slice below at ``count + page_size`` — without it a large
            # ``page`` would become an effectively unbounded fetch.
            return {"results": [], "count": count, "page": page, "page_size": page_size}
        end = offset + page_size

        merged: list[dict[str, Any]] = []
        for target_scope, owner_id, owner_type in targets:
            refs, _total = backend.list_entries(
                ctx.tenant_id, target_scope, owner_id, limit=end, offset=0, q=q
            )
            for ref in refs:
                merged.append(
                    {
                        "id": str(ref.entry_id),
                        "content": ref.content,
                        "created_at": ref.created_at,
                        "confidence": ref.confidence,
                        "owner_type": owner_type,
                        "owner_id": str(owner_id),
                        "_owner_pk": owner_id,
                    }
                )

        merged.sort(
            key=lambda row: (
                row["created_at"] or datetime.min.replace(tzinfo=dt_timezone.utc),
                row["id"],
            ),
            reverse=True,
        )
        results = merged[offset:end]

        ws_labels, user_labels = self._owner_labels(
            {r["_owner_pk"] for r in results if r["owner_type"] == "workspace"},
            {r["_owner_pk"] for r in results if r["owner_type"] == "user"},
        )
        for row in results:
            owner_pk = row.pop("_owner_pk")
            row["owner_label"] = (
                ws_labels.get(owner_pk, "") if row["owner_type"] == "workspace"
                else user_labels.get(owner_pk, "")
            )

        return {
            "results": results,
            "count": count,
            "page": page,
            "page_size": page_size,
        }

    def get_projection(
        self,
        ctx: AuthContext,
        scope: str,
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Return a 2D PCA projection + similarity clustering of the scoped
        memory contents.

        RFC #1002 PR B: embeddings are computed on the fly via
        ``llm_adapter.embedding_service.generate_embedding`` from each entry's
        ``content`` — NOT read from the raw pgvector ``embedding`` column. That
        is what makes the projection backend-agnostic: the local mirror's
        embedding column is only best-effort populated (the honcho backend
        leaves it NULL when no local embedding provider is configured), while
        the configured embedding provider is always available to the admin
        surface.

        Entries whose content cannot be embedded (an empty provider result)
        cannot be placed in a projection at all — they are dropped from
        ``points`` and reported via ``excluded_no_embedding`` so the UI can
        explain the missing rows instead of the counts silently not adding up.
        """
        self._assert_system_admin(ctx)

        ws_qs, user_qs = self._scoped_querysets(scope, workspace_id)

        # Cheap aggregates only, computed BEFORE the expensive embedding +
        # linear algebra so that a cache hit costs a few small queries rather
        # than a full PCA. The watermark covers the live row counts and the
        # newest timestamp, so a new row (or a changed content set) invalidates
        # the entry (Phase 5 plan Ruling 10).
        ws_agg = ws_qs.aggregate(count=Count("id"), last=Max("created_at"))
        user_agg = user_qs.aggregate(count=Count("id"), last=Max("created_at"))
        last_candidates = [d for d in (ws_agg["last"], user_agg["last"]) if d is not None]
        last_created = max(last_candidates) if last_candidates else None
        watermark = (
            f"{ws_agg['count'] + user_agg['count']}:"
            f"{last_created.isoformat() if last_created else 'none'}"
        )
        cache_key = (
            f"mem:proj:{ctx.tenant_id}:{scope}:{workspace_id or 'global'}:{watermark}"
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        rows: list[dict[str, Any]] = []
        excluded_no_embedding = 0
        for entry in ws_qs.only("id", "workspace", "content", "created_at"):
            embedding = generate_embedding(entry.content)
            if embedding is None:
                excluded_no_embedding += 1
                continue
            rows.append(
                {
                    "id": str(entry.id),
                    "sort_key": (entry.created_at, entry.id),
                    "embedding": embedding,
                    "owner_type": "workspace",
                    "owner_id": str(entry.workspace_id),
                    "owner_pk": entry.workspace_id,
                }
            )
        for entry in user_qs.only("id", "user", "content", "created_at"):
            embedding = generate_embedding(entry.content)
            if embedding is None:
                excluded_no_embedding += 1
                continue
            rows.append(
                {
                    "id": str(entry.id),
                    "sort_key": (entry.created_at, entry.id),
                    "embedding": embedding,
                    "owner_type": "user",
                    "owner_id": str(entry.user_id),
                    "owner_pk": entry.user_id,
                }
            )
        rows.sort(key=lambda row: row["sort_key"])

        total_size = len(rows)
        sample, sampled = _deterministic_sample(rows, MAX_PROJECTION_POINTS)

        ws_labels, user_labels = self._owner_labels(
            {r["owner_pk"] for r in sample if r["owner_type"] == "workspace"},
            {r["owner_pk"] for r in sample if r["owner_type"] == "user"},
        )

        def _label(row: dict[str, Any]) -> str:
            if row["owner_type"] == "workspace":
                return ws_labels.get(row["owner_pk"], "")
            return user_labels.get(row["owner_pk"], "")

        if not sample:
            coords: list[tuple[float, float]] = []
            clusters: list[int] = []
        elif len(sample) == 1:
            # A single vector has no variance to decompose and no pair to
            # compare — short-circuit rather than hand numpy a degenerate
            # shape.
            coords = [(0.0, 0.0)]
            clusters = [0]
        else:
            # Imported lazily on purpose: numpy is only a TRANSITIVE
            # dependency here (via sentence-transformers/torch). A
            # module-level import would make a numpy-less deployment fail to
            # build the whole REST URLconf — this way the blast radius of a
            # missing numpy is this one endpoint, not the entire API.
            import numpy as np

            # float32 matches pgvector's own storage precision and halves the
            # memory of the (N, N) similarity matrix at the 5000-row bound.
            matrix = np.asarray([np.asarray(r["embedding"], dtype=np.float32) for r in sample])
            projected = _pca_2d(matrix)
            coords = [(float(x), float(y)) for x, y in projected]
            clusters = _cluster_ids(matrix, CLUSTER_SIMILARITY_THRESHOLD)

        points = [
            {
                "id": row["id"],
                "x": coords[i][0],
                "y": coords[i][1],
                "cluster_id": clusters[i],
                "owner_type": row["owner_type"],
                "owner_id": row["owner_id"],
                "owner_label": _label(row),
            }
            for i, row in enumerate(sample)
        ]

        result = {
            "points": points,
            "sampled": sampled,
            "sample_size": len(sample),
            "total_size": total_size,
            "excluded_no_embedding": excluded_no_embedding,
        }
        cache.set(cache_key, result, _CACHE_TTL_SECONDS)
        return result


__all__ = [
    "MemoryAdminService",
    "CLUSTER_SIMILARITY_THRESHOLD",
    "MAX_PROJECTION_POINTS",
]
