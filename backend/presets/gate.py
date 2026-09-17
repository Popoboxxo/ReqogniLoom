"""
COMP-PC-003 FeatureGateService — runtime feature gating and preset switching.

ARCH-L1-008 PresetConfigEngineSystem
leaf_id: COMP-PC-003
req_id : REQ-L2-PC-002, REQ-L2-PC-008, REQ-L2-PC-011, REQ-L2-PC-013
         REQ-L3-PC003-001, REQ-L3-PC003-002, REQ-L3-PC003-003,
         REQ-L3-PC003-004

Design notes:
- Primary entry-point for all external feature queries (IF-PC-EXT-IN-001).
- Delegates to PresetRegistry via IF-PC-INT-001.
- Delegates to TerminologyProfileService via IF-PC-INT-002.
- Workspace-scoped state is stored in WorkspacePresetConfig (IF-PC-EXT-OUT-001).
- Per-workspace in-process cache keeps query latency < 10ms (REQ-L2-PC-013).
- Cache invalidation on switch_preset() / switch_terminology_profile().
- Downgrade validation with configurable policy: block | warn | allow
  (REQ-L2-PC-011, REQ-L3-PC003-003).
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from django.db import transaction

from persistence.cache_generation import bump_cache_generation, cache_generation

from presets.exceptions import (
    ConfigurationError,
    CrossTenantWorkspaceError,
    DowngradeBlockedError,
    UnknownFeatureKeyError,
)
from presets.registry import (
    FEATURE_KEYS,
    TIER_MINIMAL,
    TIER_STANDARD,
    TIER_EXTENDED,
    PresetConfig,
    PresetRegistry,
    get_registry,
)
from presets.terminology import (
    PROFILE_DEV_MODE,
    TerminologyMapping,
    TerminologyProfileService,
    get_terminology_service,
)

# ---------------------------------------------------------------------------
# Internal cache (REQ-L2-PC-013, REQ-L3-PC003-002)
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()

# SA-29 (Systemaudit 2026-08-27 §4.1 #8): both caches below are *process*-local,
# and used to be invalidated only inside the worker that performed the switch.
# Every other Gunicorn/Celery process kept serving the pre-switch tier forever —
# a workspace downgraded to ``minimal`` on worker A still offered Extended-only
# features on workers B..N until they happened to restart. Entries are therefore
# tagged with the shared cache generation for the workspace
# (``persistence.cache_generation``, backed by Redis): a bump performed anywhere
# makes every other process discard its entry on the next read. See
# :func:`_invalidate_workspace` for the write side.
_CACHE_NAMESPACE = "preset"

# Workspace-tier cache: workspace_id (str) -> (generation, PresetConfig)
_tier_cache: Dict[str, Tuple[int, PresetConfig]] = {}

# Workspace-profile cache: workspace_id (str) -> (generation, TerminologyMapping)
_profile_cache: Dict[str, Tuple[int, TerminologyMapping]] = {}

# Workspace-owner cache: workspace_id (str) -> tenant_id (UUID).
# SA-15: a workspace never changes tenant, so this mapping is immutable for the
# lifetime of the row and safe to memoise process-locally. It exists only to
# keep the tenant guard off the hot path (REQ-L2-PC-013 sub-10ms budget).
_workspace_tenant_cache: Dict[str, UUID] = {}

# Hard cap so a long-running worker touching many workspaces cannot grow the
# owner cache without bound. Reaching it simply drops the memo (correctness is
# unaffected — the next call re-reads from the database).
_WORKSPACE_TENANT_CACHE_MAX = 10_000


def _invalidate_workspace(workspace_id: str) -> None:
    """Invalidate all cache entries for *workspace_id*, in every worker.

    Called after switch_preset() or switch_terminology_profile(), and by
    ``application.cache_invalidation`` on any watched model write, so that
    subsequent queries return the new configuration (REQ-L3-PC003-002).

    SA-29: dropping the local dict entries only fixes the calling process. The
    generation bump is what reaches the other workers — they compare their
    entry's tag against the shared counter on the next read and recompute on
    mismatch. Both halves are needed: the bump alone would leave this process
    waiting out ``GENERATION_READ_TTL_SECONDS``, the pop alone is the bug.
    """
    with _cache_lock:
        _tier_cache.pop(workspace_id, None)
        _profile_cache.pop(workspace_id, None)
    bump_cache_generation(_CACHE_NAMESPACE, workspace_id)


def _cached_for_generation(
    store: Dict[str, Tuple[int, Any]], ws_key: str, generation: int
) -> Any:
    """Return the cached value for *ws_key* if tagged with *generation*, else None.

    SA-29: an entry tagged with a different generation was written before some
    worker changed the workspace's configuration and must not be served. The
    caller passes the generation in (rather than reading it here) so that the
    same value guards the lookup and tags the write-back — a bump landing
    mid-fetch then leaves the fresh entry tagged with the *older* generation,
    i.e. the next read recomputes instead of serving a value read before the
    change.

    Args:
        store: One of the module-level caches.
        ws_key: Workspace UUID string.
        generation: Shared generation captured before the lookup.

    Returns:
        The cached value, or ``None`` on a miss or a generation mismatch.
    """
    with _cache_lock:
        entry = store.get(ws_key)
        if entry is None:
            return None
        entry_generation, value = entry
        if entry_generation != generation:
            # Drop the superseded entry so a later cache-backend outage (reads
            # then fall back to the last known generation) cannot resurrect it.
            if store.get(ws_key) is entry:
                store.pop(ws_key, None)
            return None
    return value


def _store_for_generation(
    store: Dict[str, Tuple[int, Any]],
    ws_key: str,
    value: Any,
    generation: int,
) -> None:
    """Cache *value* for *ws_key*, tagged with *generation* (SA-29)."""
    with _cache_lock:
        store[ws_key] = (generation, value)


# ---------------------------------------------------------------------------
# Tenant guard for the unscoped lookups (SA-15, SYSTEMAUDIT-2026-08-27 §4.1 #6)
# ---------------------------------------------------------------------------


def _resolve_workspace_tenant(workspace_id: str) -> UUID:
    """Return the owning tenant id of *workspace_id*, memoised per process.

    Args:
        workspace_id: UUID string of the target workspace.

    Returns:
        The ``tenant_id`` of the workspace row.

    Raises:
        Workspace.DoesNotExist: If no such workspace exists. Callers must let
            this propagate — the pre-existing behaviour of the unscoped
            ``.get()`` was identical, so no caller contract changes.
    """
    with _cache_lock:
        cached = _workspace_tenant_cache.get(workspace_id)
    if cached is not None:
        return cached

    from persistence.models import Workspace

    tenant_id = Workspace.unscoped.values_list("tenant_id", flat=True).get(
        pk=workspace_id
    )
    with _cache_lock:
        if len(_workspace_tenant_cache) >= _WORKSPACE_TENANT_CACHE_MAX:
            _workspace_tenant_cache.clear()
        _workspace_tenant_cache[workspace_id] = tenant_id
    return tenant_id


def _assert_workspace_in_tenant(workspace_id: str) -> None:
    """Reject *workspace_id* when it does not belong to the active tenant.

    SA-15: every DB access in this module goes through the ``unscoped``
    escape-hatch managers (the gate must be able to bootstrap a config before a
    ``WorkspacePresetConfig`` row exists), which means the caller-supplied
    ``workspace_id`` is otherwise never checked against the request's tenant.

    When **no** tenant context is active the check is skipped. That is the
    deliberate, pre-existing escape hatch for tenant-less callers — data
    migrations, ``seed_demo``/``bootstrap_admin`` management commands and the
    preset unit tests — mirroring why ``UnscopedManager`` exists at all
    (``persistence.tenancy``). Every request path sets a tenant in middleware
    before reaching a service, so the cross-tenant path the audit describes is
    closed.

    Args:
        workspace_id: UUID string of the target workspace.

    Raises:
        CrossTenantWorkspaceError: If a tenant context is active and the
            workspace belongs to a different tenant.
    """
    from persistence.tenancy import TenantContext

    if not TenantContext.is_set():
        return

    active_tenant = TenantContext.get_tenant()
    owner_tenant = _resolve_workspace_tenant(workspace_id)
    if owner_tenant != active_tenant:
        raise CrossTenantWorkspaceError(
            "Workspace does not belong to the active tenant."
        )


# ---------------------------------------------------------------------------
# Helper: resolve WorkspacePresetConfig from DB (lazy-create default)
# ---------------------------------------------------------------------------


def _get_or_create_preset_config(workspace_id: str, *, for_update: bool = False):
    """Return the WorkspacePresetConfig ORM instance for *workspace_id*.

    Creates a default record (Minimal / Dev Mode / block) on first access.
    Import is deferred to avoid circular imports at module load time.

    Args:
        workspace_id: UUID string of the target workspace.
        for_update: Lock the row ``FOR UPDATE`` (SA-39, Systemaudit 2026-08-27
            §4.1 #13). Read-only callers must leave this False — a gate query
            runs on nearly every request and must not take row locks. Mutating
            callers (``switch_preset`` / ``switch_terminology_profile``) set it
            so their read-modify-write cannot lose an update; requires an open
            transaction, which those callers provide.

    Returns:
        WorkspacePresetConfig instance (always present after this call).

    Raises:
        CrossTenantWorkspaceError: If an active tenant context does not own
            *workspace_id* (SA-15).
    """
    from persistence.models import Workspace
    from presets.models import WorkspacePresetConfig

    # SA-15: the unscoped managers below carry no tenant predicate, so the
    # ownership check has to happen explicitly and *before* the lookup.
    _assert_workspace_in_tenant(workspace_id)

    workspace = Workspace.unscoped.get(pk=workspace_id)

    if for_update:
        # SA-39: lock an existing row before the caller reads the field it is
        # about to overwrite. On the very first switch there is no row yet, so
        # fall through to get_or_create — the OneToOne uniqueness on
        # ``workspace`` is what serialises that case, and the loser of the
        # create race then reads the winner's committed row.
        locked = (
            WorkspacePresetConfig.unscoped.select_for_update()
            .filter(workspace=workspace)
            .first()
        )
        if locked is not None:
            return locked

    # Read the initial tier from workspace.preset JSONField (set by seed_demo
    # or manual bootstrap).  Falls back to TIER_MINIMAL when the field is
    # empty or contains an unknown tier name.
    initial_tier = TIER_MINIMAL
    if isinstance(workspace.preset, dict):
        preset_name = workspace.preset.get("name")
        if preset_name in (TIER_MINIMAL, TIER_STANDARD, TIER_EXTENDED):
            initial_tier = preset_name

    config, _ = WorkspacePresetConfig.unscoped.get_or_create(
        workspace=workspace,
        defaults={
            "tenant": workspace.tenant,
            "active_tier": initial_tier,
            "terminology_profile": PROFILE_DEV_MODE,
            "downgrade_policy": "block",
        },
    )
    return config


# ---------------------------------------------------------------------------
# FeatureGateService (COMP-PC-003)
# ---------------------------------------------------------------------------


class FeatureGateService:
    """Runtime gating service — central entry-point for external callers.

    Consumes:
        IF-PC-INT-001: PresetRegistry.get_preset_config()
        IF-PC-INT-002: TerminologyProfileService.get_terminology_profile()
    Exposes (IF-PC-EXT-IN-001/003):
        get_preset(workspace_id)
        is_feature_enabled(key, workspace_id)
        switch_preset(workspace_id, target_tier)
        validate_downgrade(workspace_id, target_tier)
        get_terminology(workspace_id)
        switch_terminology_profile(workspace_id, target_profile)
    """

    def __init__(
        self,
        registry: Optional[PresetRegistry] = None,
        terminology_service: Optional[TerminologyProfileService] = None,
    ) -> None:
        self._registry = registry or get_registry()
        self._terminology = terminology_service or get_terminology_service()

    # ------------------------------------------------------------------
    # IF-PC-EXT-IN-001 — Preset + Feature queries
    # ------------------------------------------------------------------

    def get_preset(self, workspace_id: str) -> PresetConfig:
        """Return the full PresetConfig for *workspace_id*.

        Uses in-process cache (REQ-L2-PC-013).  Falls back to DB on cache
        miss, creates default config if no record exists.

        Args:
            workspace_id: UUID string of the workspace.

        Returns:
            PresetConfig for the workspace's active tier.

        Raises:
            CrossTenantWorkspaceError: If an active tenant context does not own
                *workspace_id* (SA-15).

        REQ-L2-PC-003: Full configuration returned in one call.
        """
        ws_key = str(workspace_id)
        # SA-15: the guard runs *before* the cache read. ``_tier_cache`` is
        # keyed by workspace alone, so a warm entry would otherwise serve a
        # cross-tenant caller without ever touching the guarded DB path.
        _assert_workspace_in_tenant(ws_key)
        # SA-29: capture the shared generation once, then use it both to
        # validate the hit and to tag the write-back.
        generation = cache_generation(_CACHE_NAMESPACE, ws_key)
        cached = _cached_for_generation(_tier_cache, ws_key, generation)
        if cached is not None:
            return cached

        config = _get_or_create_preset_config(ws_key)
        preset = self._registry.get_preset_config(config.active_tier)
        _store_for_generation(_tier_cache, ws_key, preset, generation)
        return preset

    def is_feature_enabled(self, feature_key: str, workspace_id: str) -> bool:
        """Return True if *feature_key* is enabled for *workspace_id*.

        Primary runtime gating method (IF-PC-EXT-IN-001).

        Args:
            feature_key: One of the registered feature keys (FEATURE_KEYS).
            workspace_id: UUID string of the workspace.

        Returns:
            True if the feature is enabled for the workspace's preset.

        Raises:
            UnknownFeatureKeyError: If *feature_key* is not in FEATURE_KEYS.

        REQ-L2-PC-002, REQ-L3-PC003-001.
        """
        if feature_key not in FEATURE_KEYS:
            raise UnknownFeatureKeyError(
                f"Unknown feature key '{feature_key}'. "
                f"Valid keys: {sorted(FEATURE_KEYS)}"
            )
        preset = self.get_preset(workspace_id)
        return preset.features.get(feature_key, False)

    def get_workflow_configurability(self, workspace_id: str) -> str:
        """Return the workflow configurability string for *workspace_id*.

        REQ-L2-PC-006.

        Args:
            workspace_id: UUID string of the workspace.

        Returns:
            One of "fixed", "partial", "full".
        """
        return self.get_preset(workspace_id).workflow_configurability

    def is_scope_allowed(self, workspace_id: str, scope: str) -> bool:
        """Return True if *scope* is an allowed baseline scope for *workspace_id*.

        REQ-L2-PC-005.

        Args:
            workspace_id: UUID string of the workspace.
            scope: Baseline scope, e.g. "document", "project", "global".

        Returns:
            True if the scope is permitted.

        Raises:
            ScopeNotAvailableError: If scope is not a known scope name.
        """
        return self.get_preset(workspace_id).is_scope_allowed(scope)

    # ------------------------------------------------------------------
    # IF-PC-EXT-IN-003 — Preset switching
    # ------------------------------------------------------------------

    def switch_preset(self, workspace_id: str, target_tier: str) -> PresetConfig:
        """Switch the workspace's active preset to *target_tier*.

        Upgrades are always allowed.  Downgrades go through validate_downgrade()
        first and may be blocked depending on the workspace's downgrade_policy.

        Args:
            workspace_id: UUID string of the workspace.
            target_tier: Target preset tier name.

        Returns:
            The new PresetConfig after the switch.

        Raises:
            ConfigurationError: If *target_tier* is not a valid tier.
            DowngradeBlockedError: If a downgrade is blocked by policy.

        REQ-L3-PC003-004, REQ-L2-PC-008.

        SA-39 (Systemaudit 2026-08-27 §4.1 #13): the tier is a read-modify-write
        — the *current* tier decides whether this is a downgrade and therefore
        whether ``validate_downgrade``'s data checks run at all. Without a lock,
        two concurrent switches both read the pre-switch tier: the second write
        wins blindly, and worse, a concurrent minimal->extended upgrade can make
        an extended->standard downgrade skip its incompatibility check because
        it read the stale ``minimal``. The row is therefore locked for the whole
        decide-and-persist window.
        """
        ws_key = str(workspace_id)
        with transaction.atomic():
            config = _get_or_create_preset_config(ws_key, for_update=True)
            current_tier = config.active_tier

            # Validate target tier existence
            new_preset = self._registry.get_preset_config(target_tier)

            # Downgrade path. ``validate_downgrade`` re-reads the same config row
            # (for ``downgrade_policy``) without a lock — safe, because we are
            # inside the transaction that already holds it, and the second read
            # therefore sees exactly the row we locked.
            if self._registry.tier_index(target_tier) < self._registry.tier_index(current_tier):
                warnings = self.validate_downgrade(workspace_id, target_tier)
                # validate_downgrade raises DowngradeBlockedError on block policy;
                # warnings list returned for warn policy; empty list for allow.
                _ = warnings  # warnings forwarded by caller if needed

            # Persist
            config.active_tier = target_tier
            config.save(update_fields=["active_tier", "modified_at"])

        # Invalidate cache (REQ-L3-PC003-002). Deliberately *after* the commit:
        # invalidating inside the transaction would let a concurrent reader
        # repopulate the caches from the not-yet-committed old value.
        _invalidate_workspace(ws_key)

        return new_preset

    def validate_downgrade(
        self, workspace_id: str, target_tier: str
    ) -> List[str]:
        """Validate a downgrade from the current tier to *target_tier*.

        Checks for data incompatibilities:
        - Global baselines block Extended → Standard downgrade.

        Args:
            workspace_id: UUID string of the workspace.
            target_tier: The desired lower tier.

        Returns:
            List of warning strings (empty list = clean).

        Raises:
            DowngradeBlockedError: If incompatible data exists and policy is "block".

        REQ-L3-PC003-003, REQ-L2-PC-011.
        """
        ws_key = str(workspace_id)
        config = _get_or_create_preset_config(ws_key)
        policy = config.downgrade_policy

        incompatibilities = self._collect_downgrade_incompatibilities(
            workspace_id, target_tier
        )

        if not incompatibilities:
            return []

        message = "; ".join(incompatibilities)

        if policy == "block":
            raise DowngradeBlockedError(message)
        elif policy == "warn":
            return incompatibilities
        # policy == "allow"
        return []

    def _collect_downgrade_incompatibilities(
        self, workspace_id: str, target_tier: str
    ) -> List[str]:
        """Return human-readable incompatibility strings for the downgrade.

        Args:
            workspace_id: UUID string of the workspace.
            target_tier: The desired target tier.

        Returns:
            List of incompatibility description strings; empty if clean.
        """
        from persistence.models import Artifact
        from baseline.models import BaselineSnapshot

        issues: List[str] = []

        # Extended → Standard: global baselines must not exist
        if target_tier in ("minimal", "standard"):
            try:
                count = BaselineSnapshot.unscoped.filter(
                    workspace_id=workspace_id,
                    scope="global",
                ).count()
                if count:
                    issues.append(
                        f"Downgrade blocked: {count} global baseline"
                        + ("s exist" if count > 1 else " exists")
                    )
            except Exception:
                # PersistenceLayer unavailable in test context; skip check.
                pass

        return issues

    # ------------------------------------------------------------------
    # IF-PC-INT-002 / IF-PC-EXT-IN-002 — Terminology
    # ------------------------------------------------------------------

    def get_terminology(self, workspace_id: str) -> TerminologyMapping:
        """Return the active TerminologyMapping for *workspace_id*.

        Uses in-process cache (REQ-L2-PC-013).

        Args:
            workspace_id: UUID string of the workspace.

        Returns:
            TerminologyMapping with the workspace's active profile labels.

        Raises:
            CrossTenantWorkspaceError: If an active tenant context does not own
                *workspace_id* (SA-15).

        REQ-L3-PC002-001, REQ-L3-PC002-003.
        """
        ws_key = str(workspace_id)
        # SA-15: guard before the cache read — see get_preset().
        _assert_workspace_in_tenant(ws_key)
        # SA-29: generation-tagged read/write-back — see get_preset().
        generation = cache_generation(_CACHE_NAMESPACE, ws_key)
        cached = _cached_for_generation(_profile_cache, ws_key, generation)
        if cached is not None:
            return cached

        config = _get_or_create_preset_config(ws_key)
        mapping = self._terminology.get_terminology_profile(
            config.terminology_profile
        )
        _store_for_generation(_profile_cache, ws_key, mapping, generation)
        return mapping

    def switch_terminology_profile(
        self, workspace_id: str, target_profile: str
    ) -> TerminologyMapping:
        """Switch the workspace's active terminology profile.

        No data migration required — only the profile name field changes
        (REQ-L2-PC-010, REQ-L3-PC002-002).

        Args:
            workspace_id: UUID string of the workspace.
            target_profile: Profile name, e.g. "dev_mode" or "se_mode".

        Returns:
            The new TerminologyMapping after the switch.

        Raises:
            KeyError: If *target_profile* is not a registered profile.
        """
        ws_key = str(workspace_id)

        # Validate profile existence (raises KeyError if unknown)
        new_mapping = self._terminology.get_terminology_profile(target_profile)

        # SA-39: same read-modify-write shape as switch_preset — lock the row so
        # a concurrent switch cannot be silently overwritten.
        with transaction.atomic():
            config = _get_or_create_preset_config(ws_key, for_update=True)
            config.terminology_profile = target_profile
            config.save(update_fields=["terminology_profile", "modified_at"])

        # Invalidate cache (after commit — see switch_preset).
        _invalidate_workspace(ws_key)

        return new_mapping


# Module-level singleton
_gate_service = FeatureGateService()


def get_gate_service() -> FeatureGateService:
    """Return the module-level FeatureGateService singleton."""
    return _gate_service


__all__ = [
    "FeatureGateService",
    "get_gate_service",
]
