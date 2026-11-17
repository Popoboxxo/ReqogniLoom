"""
ARCH-L1-006 BaselineService — COMP-BL-004 VersionReconstructor.

leaf_id: COMP-BL-004
req_id:  REQ-L2-BL-009, REQ-L3-BL004-001, REQ-L3-BL004-002, REQ-L3-BL004-003

Responsibilities:
  - Reconstruct the historical payload (title, description, content) of an item
    at the version recorded in a given Baseline.
  - Uses AuditLogEntry.payload from persistence.models as the version history source.
  - Optionally caches reconstructed payloads via LRU to avoid repeated DB queries.

Internal Interfaces consumed:
  IF-BL-INT-004: BaselineStore.lookup_item_version(baseline_id, item_id) -> version

External Interfaces consumed:
  IF-BL-EXT-IN-004: AuditLogEntry (Django ORM) — payload at specific version

Architecture:
  docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/Components/
  COMP-BL-004_VersionReconstructor/L3_COMP-BL-004_VersionReconstructor_Architecture.md

Version history note:
  The persistence layer stores AuditLogEntry rows with a ``payload`` JSONField
  that contains entity data at the time of write. VersionReconstructor queries
  AuditLogEntry WHERE object_id = <item_id> AND tenant_id = <tenant>
  (AND object_type = <concrete entity class> when the caller knows it) AND
  payload->>version = <version>, returning title/description/content from the
  payload dict. The optional ``object_type`` predicate is the leading column
  of ``idx_audit_object = (object_type, object_id)`` and prevents a same-id
  entry of a different entity type from satisfying the legacy fallback.

  The delta-index ``version`` is ``Artifact.version``; it does NOT increment
  when a subtype row (Requirement, ArchitectureElement, …) is edited
  (see ``baseline.diff_engine``, issue #398). A live entity that still carries
  that artifact version is therefore NOT proof that its payload is unchanged.
  Since REQ-L2-BL-012 the baseline stores a full field-state snapshot; that
  captured state is authoritative (L1-001). The live entity and audit log are
  only a fallback for legacy baselines whose state column is NULL.

Cache note (L1-001):
  The LRU cache key includes ``baseline_id``. Keying only on
  ``(item_id, version)`` made two baselines with the same artifact version but
  different captured titles alias onto the same cached payload.
"""
from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from datetime import UTC, datetime

from baseline.exceptions import ItemNotInBaselineError, VersionNotFoundError
from baseline.types import ItemPayload

logger = logging.getLogger(__name__)

# LRU cache default size (ADR-L3-BL004-01)
LRU_CACHE_MAX_SIZE = 1000


class LruPayloadCache:
    """Simple LRU cache keyed on (baseline_id, item_id, version).

    L1-001: ``baseline_id`` is part of the key because the recorded ``version``
    is ``Artifact.version`` and can be identical across two baselines whose
    captured titles differ. Without it the second baseline returned the first
    one's payload.

    ``baseline_id`` is optional for backward compatibility with direct callers
    that seed/inspect the cache without a baseline (e.g. the LRU unit tests).
    Such an entry is stored under a wildcard key and is used as a fallback on
    lookup; production calls through :meth:`get_item_at_baseline` always pass a
    real ``baseline_id`` to both ``put`` and ``get`` and never create wildcards.

    Evicts the least-recently-used entry when max_size is exceeded.
    Thread-safety: not required — Django runs single-threaded per request
    in WSGI mode (one cache instance per singleton VersionReconstructor).

    REQ-L3-BL004-003.
    """

    _WILDCARD_BASELINE = "*"

    def __init__(self, max_size: int = LRU_CACHE_MAX_SIZE) -> None:
        self._max_size = max_size
        # OrderedDict maintains insertion order; we move accessed items to end.
        self._cache: OrderedDict[tuple[str, str, int], ItemPayload] = OrderedDict()

    @classmethod
    def _key(
        cls, item_id: str, version: int, baseline_id: uuid.UUID | str | None
    ) -> tuple[str, str, int]:
        """Build the cache key for one payload."""
        scope = (
            cls._WILDCARD_BASELINE
            if baseline_id is None
            else str(baseline_id)
        )
        return (scope, item_id, version)

    def get(
        self,
        item_id: str,
        version: int,
        baseline_id: uuid.UUID | str | None = None,
    ) -> ItemPayload | None:
        """Return the cached payload for *baseline_id*, or None on miss.

        Args:
            item_id: String UUID of the item.
            version: Recorded delta-index version.
            baseline_id: Baseline whose snapshot the payload belongs to. An
                unscoped wildcard entry is consulted when no scoped hit exists.
        """
        key = self._key(item_id, version, baseline_id)
        if key not in self._cache:
            wildcard = self._key(item_id, version, None)
            if baseline_id is None or wildcard not in self._cache:
                return None
            key = wildcard
        # Move to most-recently-used end
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(
        self,
        payload: ItemPayload,
        baseline_id: uuid.UUID | str | None = None,
    ) -> None:
        """Insert *payload* into the cache, evicting the LRU entry if needed.

        Args:
            payload: Reconstructed payload to cache.
            baseline_id: Baseline whose snapshot the payload belongs to. When
                omitted the payload is stored under the unscoped wildcard key.
        """
        key = self._key(payload.item_id, payload.version, baseline_id)
        if key in self._cache:
            self._cache.move_to_end(key)
            return
        self._cache[key] = payload
        if len(self._cache) > self._max_size:
            # Evict LRU (first item)
            self._cache.popitem(last=False)


class VersionReconstructor:
    """COMP-BL-004: Reconstruct historical item payloads from audit history.

    Sequence for get_item_at_baseline(baseline_id, item_id):
      1. Lookup version from BaselineStore (IF-BL-INT-004) — also proves the
         baseline and item belong to the caller's tenant.
      2. Check LRU cache (keyed by baseline_id as well as item/version).
      3. Load the captured full state via BaselineStore.load_states and build
         the payload from it (L1-001 — this is the authoritative snapshot).
      4. Only for a legacy entry with no captured state: try the live entity
         (keyed on Artifact.version, the recorded delta-index version), then
         the AuditLogEntry payload query.
      5. Cache and return ItemPayload.

    REQ-L2-BL-009, ADR-L3-BL004-01, ADR-L3-BL004-02.
    """

    def __init__(
        self,
        store=None,
        cache: LruPayloadCache | None = None,
    ) -> None:
        if store is None:
            from baseline.store import get_store
            store = get_store()
        self._store = store
        self._cache = cache if cache is not None else LruPayloadCache()

    def get_item_at_baseline(
        self,
        baseline_id: uuid.UUID,
        item_id: str,
        tenant_id: uuid.UUID,
        *,
        object_type: str | None = None,
    ) -> ItemPayload:
        """Return the item payload as it was at baseline creation time.

        IF-BL-EXT-IN-001 (called from ApplicationService / services facade).

        Args:
            baseline_id: UUID of the target baseline.
            item_id: String UUID of the item (Artifact/Requirement).
            tenant_id: Active tenant UUID (row-level isolation). Gates not
                just the baseline lookup itself but also this method's own
                subsequent ``.unscoped`` entity/audit-log lookups below
                (_try_live_entity/_load_from_audit_log) — those trust that
                item_id only reaches them after being proven, via a
                tenant-scoped lookup_item_version, to belong to a baseline
                owned by this tenant.
            object_type: Concrete audit entity class (e.g. ``"Requirement"``)
                used as an additional ``object_type`` predicate on the legacy
                audit-log fallback (L1-006). When the caller resolved the
                concrete entity it can supply this so a same-id entry of a
                different entity type cannot satisfy the reconstruction. The
                delta index only records the generic ``"item"`` kind and a
                legacy entry has a NULL captured state, so this concrete class
                is otherwise not derivable inside this call chain (see the
                follow-up note in :meth:`_load_from_audit_log`).

        Returns:
            ItemPayload with title, description, content as captured at
            baseline creation time (not the live, possibly edited payload).

        Raises:
            BaselineNotFoundError: (from BaselineStore) baseline does not
                exist for this tenant.
            ItemNotInBaselineError: item_id is not part of this baseline.
            VersionNotFoundError: version not found in the audit history
                (legacy entries only).
        """
        # Step 1: Get recorded version from BaselineStore (IF-BL-INT-004)
        # Propagates ItemNotInBaselineError / BaselineNotFoundError directly.
        version = self._store.lookup_item_version(baseline_id, item_id, tenant_id)

        # Step 2: LRU cache check (REQ-L3-BL004-003). L1-001: the baseline id
        # is part of the key so equal artifact versions cannot alias.
        cached = self._cache.get(item_id, version, baseline_id=baseline_id)
        if cached is not None:
            return cached

        # Step 3 (L1-001): STATE FIRST. The recorded version is
        # Artifact.version, which does not move when a subtype row is edited
        # (diff_engine.py:43-60). Trusting a live entity that still carries
        # that version returned the *edited* payload. The captured full state
        # (REQ-L2-BL-012) is the only source that still holds the baseline-time
        # values. ``load_states`` is tenant-scoped by its own baseline check.
        states = self._store.load_states(baseline_id, tenant_id, item_ids=[item_id])
        state = states.get(item_id) if isinstance(states, dict) else None
        # Only a real dict is a usable snapshot; a NULL state (legacy entry) or
        # an unexpected shape is treated as "no captured state" below.
        if not isinstance(state, dict):
            state = None

        if state is not None:
            payload = self._payload_from_state(
                item_id, state, fallback_version=version
            )
        else:
            # Step 4 — legacy entry (state IS NULL): no captured values exist,
            # so no entity version is available from the snapshot. The recorded
            # ``version`` is Artifact.version (delta index), so the live-entity
            # fallback compares against the live artifact's version — the
            # original, pre-L1-001 behaviour. Entity-version matching is only
            # possible on the state-present path (Step 3), where the snapshot
            # itself supplies the entity's own version.
            payload = self._try_live_entity(item_id, version)
            if payload is None:
                # L1-006: thread the caller-supplied entity class into the
                # unscoped audit query so a same-id entry of a different
                # object_type cannot satisfy the fallback. Pass the argument
                # only when actually known: direct callers of the legacy
                # fallback (and its unit tests) rely on the 3-arg signature.
                if object_type is not None:
                    payload = self._load_from_audit_log(
                        item_id, version, tenant_id, object_type=object_type
                    )
                else:
                    payload = self._load_from_audit_log(item_id, version, tenant_id)
            if payload is None:
                raise VersionNotFoundError()

        # Step 5: Cache and return
        self._cache.put(payload, baseline_id=baseline_id)
        return payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _payload_from_state(
        item_id: str, state: dict, *, fallback_version: int
    ) -> ItemPayload:
        """Build an :class:`ItemPayload` from a captured full-state snapshot.

        Args:
            item_id: String UUID of the item (the artifact id for subtype rows).
            state: ``BaselineDeltaIndexEntry.state`` dict. ``state_capture``
                stores the entity's own version under ``"version"`` (e.g.
                ``req.version`` at state_capture.py:262) and the label under
                ``"title"``; glossary terms use ``"term"`` instead.
            fallback_version: Recorded delta-index version, used when the
                state carries no usable version (e.g. a bare artifact hull).

        Returns:
            ItemPayload holding the captured (baseline-time) values.
        """
        raw_version = state.get("version")
        # bool is an int subclass — exclude it explicitly (mirrors
        # ``diff_engine._effective_version``). A captured ``True`` is not a
        # usable entity version and must fall back to the recorded one.
        entity_version = (
            raw_version
            if isinstance(raw_version, int) and not isinstance(raw_version, bool)
            else fallback_version
        )
        title = (
            state.get("title")
            or state.get("term")
            or state.get("name")
            or f"item:{item_id}"
        )
        content = state.get("content") or state.get("body")
        return ItemPayload(
            item_id=item_id,
            version=entity_version,
            title=str(title),
            description=state.get("description"),
            content=str(content) if content is not None else None,
            reconstructed_at=datetime.now(tz=UTC),
        )

    def _try_live_entity(
        self, item_id: str, version: int
    ) -> ItemPayload | None:
        """Return a live entity payload when its ARTIFACT version matches.

        Legacy fallback only — state-present baselines never reach this method,
        and are the only path where the captured state supplies the *entity's*
        own version (via ``_payload_from_state``). For a legacy (state NULL)
        entry there is no captured entity version: the ``version`` recorded in
        the delta index is ``Artifact.version``, so the comparison must be
        against ``req.artifact.version`` / ``ae.artifact.version`` (the original,
        pre-L1-001 behaviour). Comparing the subtype's own ``req.version`` here
        would reject every legacy baseline whose entity version had moved
        independently of the artifact version, raising ``VersionNotFoundError``
        instead of returning the historical payload.

        Returns None if the live entity is not found or its artifact version
        differs, so the caller falls through to the audit log.
        """
        try:
            item_uuid = uuid.UUID(item_id)
        except (ValueError, AttributeError):
            return None

        # Try Requirement first (most common entity type)
        try:
            from persistence.models import Requirement

            req = Requirement.unscoped.filter(
                artifact_id=item_uuid
            ).select_related("artifact").first()
            if req is not None and req.artifact.version == version:
                return ItemPayload(
                    item_id=item_id,
                    version=version,
                    title=req.title,
                    description=req.description or None,
                    content=None,
                    reconstructed_at=datetime.now(tz=UTC),
                )
        except Exception:
            logger.debug("Live Requirement probe failed; trying next entity type", exc_info=True)

        # Try ArchitectureElement
        try:
            from persistence.models import ArchitectureElement

            ae = ArchitectureElement.unscoped.filter(
                artifact_id=item_uuid
            ).select_related("artifact").first()
            if ae is not None and ae.artifact.version == version:
                return ItemPayload(
                    item_id=item_id,
                    version=version,
                    title=ae.title,
                    description=ae.description or None,
                    content=None,
                    reconstructed_at=datetime.now(tz=UTC),
                )
        except Exception:
            logger.debug("ArchitectureElement probe failed; trying next", exc_info=True)

        # Try bare Artifact
        try:
            from persistence.models import Artifact

            art = Artifact.unscoped.filter(id=item_uuid).first()
            if art is not None and art.version == version:
                return ItemPayload(
                    item_id=item_id,
                    version=version,
                    title=str(art),
                    description=None,
                    content=None,
                    reconstructed_at=datetime.now(tz=UTC),
                )
        except Exception:
            logger.debug("Live Artifact probe failed; trying next entity type", exc_info=True)

        # Try GlossaryTerm
        try:
            from persistence.models import GlossaryTerm

            gt = GlossaryTerm.objects.filter(id=item_uuid).first()
            if gt is not None and gt.version == version:
                return ItemPayload(
                    item_id=item_id,
                    version=version,
                    title=gt.term,
                    description=gt.definition,
                    content=None,
                    reconstructed_at=datetime.now(tz=UTC),
                )
        except Exception:
            logger.debug("GlossaryTerm probe failed; trying audit log", exc_info=True)

        return None

    def _load_from_audit_log(
        self,
        item_id: str,
        version: int,
        tenant_id: uuid.UUID,
        *,
        object_type: str | None = None,
    ) -> ItemPayload | None:
        """Query AuditLogEntry for the entity payload at the specified version.

        The AuditLogEntry.payload JSONField is expected to contain the entity
        snapshot at the time of the write operation. A matching entry is one
        where object_id = item_id AND payload['version'] == version. That
        payload version is the ENTITY version (e.g. ``req.version``), not the
        ``Artifact.version`` recorded in the delta index — the match is
        therefore on the entity version by construction. This path is the
        legacy fallback for entries whose captured state column is NULL.

        Returns None if no matching entry is found (caller raises VersionNotFoundError).

        Args:
            item_id: String UUID of the item whose history is searched.
            version: Entity version the payload must carry.
            tenant_id: Owning tenant. Parsed defensively alongside ``item_id``
                and applied as an explicit ``tenant_id`` predicate on the
                ``unscoped`` audit query — ``unscoped`` escapes the ORM tenant
                manager but not this explicit anchor, so a legacy
                reconstruction can never read another tenant's audit payload.
            object_type: Concrete audit entity class (e.g. ``"Requirement"``).
                When supplied, applied as an explicit ``object_type`` predicate
                so a same-id entry of a different entity type cannot satisfy
                the fallback and the leading column of ``idx_audit_object`` is
                used. When ``None`` the query falls back to the tenant-anchored
                ``(object_id, tenant_id)`` lookup only — FOLLOW-UP: the concrete
                class is not derivable here because the delta index stores only
                the generic ``"item"`` kind (not the domain class) and a legacy
                entry's captured state is NULL, while the production caller
                (:func:`baseline.services.get_item_at_baseline`) does not pass a
                type. Broadening that caller/delta index to carry the concrete
                audit class would let this predicate be made unconditional.

        IF-BL-EXT-IN-004 (AuditLog/VersionHistory access).
        """
        try:
            item_uuid = uuid.UUID(item_id)
            tenant_uuid = uuid.UUID(str(tenant_id))
        except (ValueError, AttributeError):
            return None

        try:
            from persistence.models import AuditLogEntry

            # Query audit log entries for this entity, ordered by id DESC
            # (most recent first) to find the entry whose payload.version matches.
            # The explicit tenant predicate is mandatory: a superuser test
            # connection (or a misconfigured worker) otherwise bypasses RLS on
            # this ``unscoped`` queryset and could return a foreign payload.
            # L1-006: the object_type predicate (when the concrete class is
            # known) additionally excludes a same-id entry of another entity
            # type and exercises the leading column of idx_audit_object
            # (object_type, object_id).
            filters: dict[str, object] = {
                "object_id": item_uuid,
                "tenant_id": tenant_uuid,
            }
            if object_type is not None:
                filters["object_type"] = object_type
            entries = AuditLogEntry.unscoped.filter(**filters).order_by("-id")

            for entry in entries:
                payload_data = entry.payload or {}
                entry_version = payload_data.get("version")

                if entry_version == version:
                    title = (
                        payload_data.get("title")
                        or payload_data.get("name")
                        or payload_data.get("term")
                        or f"item:{item_id}"
                    )
                    return ItemPayload(
                        item_id=item_id,
                        version=version,
                        title=str(title),
                        description=payload_data.get("description"),
                        content=payload_data.get("content"),
                        reconstructed_at=datetime.now(tz=UTC),
                    )
        except Exception:
            logger.debug("Audit-log reconstruction probe failed", exc_info=True)

        return None


# Module-level singleton — lazily initialized to avoid Django import at module load
_reconstructor: VersionReconstructor | None = None


def get_reconstructor() -> VersionReconstructor:
    """Return the module-level VersionReconstructor singleton (lazy init)."""
    global _reconstructor
    if _reconstructor is None:
        _reconstructor = VersionReconstructor()
    return _reconstructor


__all__ = [
    "LruPayloadCache",
    "VersionReconstructor",
    "get_reconstructor",
]
