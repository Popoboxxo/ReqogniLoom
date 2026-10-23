"""Q1 three-level preference service (Plan C, T-C2-2).

The single Layer-2 facade over :class:`auth_tenancy.models.PreferenceValue`
(ADR-01): REST views, MCP tools and non-request callers (Celery, the Plan A
memory policy) all resolve and write preferences through this module — no
transport layer touches the model.

Levels and precedence
---------------------
A preference key may be stored on three levels, each with its own row per key
(see the model docstring): ``global`` (tenant-wide default), ``workspace``
(per workspace) and ``user`` (account-wide per tenant). An absent row means
*inherit*, never *empty*.

Two combination modes exist, both declared by the key's registry entry:

* ``override`` — the first set level in ``user > workspace > global`` wins,
  else the registry default; ``source`` names the winning level or ``"default"``.
* ``union`` (ordered lists) — the union of every set level plus the registry
  default, deduplicated; ``source`` is ``"merged"``. This makes opt-out lists
  "minimum wins": one level can disable an item, no level can re-enable it.

Context-free callers
--------------------
:func:`levels_for` and :func:`resolve_for` take explicit ids instead of an
:class:`~auth_tenancy.context.AuthContext` (Plan A's injection policy and any
Celery task). Both arm the thread-local tenant for exactly one query and restore
the *previous* state in a ``finally`` block — including when the body raises
(index §f.8, QR-T26/QR-S14). A worker that keeps processing after the call must
not inherit this key's tenant, nor lose the one it already had.

Writes
------
``set_level`` is one atomic operation: every key in the payload is validated
(registered, allowed at this level, correct type/choices, per-key validator)
*before* anything is written, so a payload with one bad entry writes nothing.
``None`` as a value deletes that level's row (reset = inherit).

Workspace and global writes are audited (one entry per changed key, with the
old/new value and the level); user-level writes are self-service like
``display-preferences`` and carry no audit entry.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from django.db import transaction
from django.db.models import Q, QuerySet

from application.base import ServiceBase
from application.preference_registry import (
    PreferenceKey,
    all_preference_keys,
    get_preference_key,
    validate_preference_value,
)
from auth_tenancy.context import AuthContext
from auth_tenancy.models import (
    PREFERENCE_SCOPE_GLOBAL,
    PREFERENCE_SCOPE_USER,
    PREFERENCE_SCOPE_WORKSPACE,
    ROLE_ADMIN,
    PreferenceValue,
)
from persistence.errors import PermissionDeniedError, ValidationError
from persistence.tenancy import TenantContext

LEVEL_GLOBAL: Final = PREFERENCE_SCOPE_GLOBAL
LEVEL_WORKSPACE: Final = PREFERENCE_SCOPE_WORKSPACE
LEVEL_USER: Final = PREFERENCE_SCOPE_USER

#: Levels a caller may write to explicitly. There is no ``default`` store.
WRITABLE_SCOPES: Final[tuple[str, ...]] = (
    LEVEL_GLOBAL,
    LEVEL_WORKSPACE,
    LEVEL_USER,
)

#: Resolution precedence, highest first (``override`` mode).
_PRECEDENCE: Final[tuple[str, ...]] = (LEVEL_USER, LEVEL_WORKSPACE, LEVEL_GLOBAL)

#: Merge order for ``union`` mode, lowest precedence first, then the default
#: (seeded first) — so the result reads "default, then what each level added".
_UNION_ORDER: Final[tuple[str, ...]] = (LEVEL_GLOBAL, LEVEL_WORKSPACE, LEVEL_USER)

SOURCE_DEFAULT: Final = "default"
SOURCE_MERGED: Final = "merged"

#: Audit metadata shared by every workspace/global write.
_AUDIT_OPERATION: Final = "update"
_AUDIT_ENTITY_TYPE: Final = "preference_value"


class _Unset:
    """Type of the :data:`UNSET` sentinel (kept out of the public surface)."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "UNSET"


#: "No row at this level". Distinct from any stored value, including ``False``,
#: ``None`` and ``[]``: a missing row is inheritance, and a stored falsy value is
#: still a set value that wins over lower levels.
UNSET: Final = _Unset()


@dataclass(frozen=True)
class PreferenceLevels:
    """The three stored levels of one key; each is the value or :data:`UNSET`.

    ``global_`` carries the trailing underscore because ``global`` is a Python
    keyword. Use :meth:`get` rather than reaching for the attributes by name.
    """

    global_: Any
    workspace: Any
    user: Any

    def get(self, level: str) -> Any:
        """Return the value stored at *level*, or :data:`UNSET`.

        Raises:
            ValidationError: *level* is not a known level name.
        """
        if level == LEVEL_GLOBAL:
            return self.global_
        if level == LEVEL_WORKSPACE:
            return self.workspace
        if level == LEVEL_USER:
            return self.user
        raise ValidationError(
            f"Unknown preference level {level!r}; expected one of "
            f"{list(WRITABLE_SCOPES)}"
        )


# ---------------------------------------------------------------------------
# Context-free reads
# ---------------------------------------------------------------------------


def levels_for(
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    user_id: UUID | None,
    key: str,
) -> PreferenceLevels:
    """Return the stored levels of *key* for one (tenant, workspace, user).

    Exactly one query (``key=…`` plus the per-level target clauses); levels the
    key does not allow, and targets that are not given, are never queried.

    Tenant hygiene: the previous thread-local tenant is restored in a
    ``finally``, so a Celery worker neither leaks this tenant to its next task
    nor loses the tenant it already had — even when the call raises.

    Raises:
        ValidationError: *key* is not registered (raised inside the guarded
            block, so the tenant is restored either way).
    """
    was_set = TenantContext.is_set()
    previous = TenantContext.get_tenant() if was_set else None
    TenantContext.set_tenant(tenant_id)
    try:
        spec = get_preference_key(key)
        return _read_levels(spec, workspace_id=workspace_id, user_id=user_id)
    finally:
        if was_set and previous is not None:
            TenantContext.set_tenant(previous)
        else:
            TenantContext.clear_tenant()


def resolve_for(
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    user_id: UUID | None,
    key: str,
) -> tuple[Any, str]:
    """Resolve one key's effective value and its source.

    Returns:
        ``(value, source)`` where ``source`` is ``"user"`` / ``"workspace"`` /
        ``"global"`` / ``"default"`` for ``override`` keys and ``"merged"`` for
        ``union`` keys.

    Raises:
        ValidationError: *key* is not registered.
    """
    spec = get_preference_key(key)
    levels = levels_for(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=user_id,
        key=key,
    )
    return _resolve(spec, levels)


# ---------------------------------------------------------------------------
# Level reading / resolution helpers
# ---------------------------------------------------------------------------


def _target_clauses(
    spec: PreferenceKey, *, workspace_id: UUID | None, user_id: UUID | None
) -> Q | None:
    """Build the single-query predicate for *spec*'s allowed levels.

    Returns ``None`` when no level of *spec* is addressable for this target
    (e.g. a user-only key resolved without a ``user_id``) — the caller then
    answers all-``UNSET`` without a query.
    """
    clause: Q | None = None
    if LEVEL_GLOBAL in spec.levels:
        clause = Q(scope=LEVEL_GLOBAL)
    if LEVEL_WORKSPACE in spec.levels and workspace_id is not None:
        workspace_clause = Q(scope=LEVEL_WORKSPACE, workspace_id=workspace_id)
        clause = workspace_clause if clause is None else clause | workspace_clause
    if LEVEL_USER in spec.levels and user_id is not None:
        user_clause = Q(scope=LEVEL_USER, user_id=user_id)
        clause = user_clause if clause is None else clause | user_clause
    return clause


def _read_levels(
    spec: PreferenceKey, *, workspace_id: UUID | None, user_id: UUID | None
) -> PreferenceLevels:
    """Read *spec*'s levels in one query (tenant-scoped default manager)."""
    clause = _target_clauses(spec, workspace_id=workspace_id, user_id=user_id)
    if clause is None:
        return PreferenceLevels(UNSET, UNSET, UNSET)
    stored = {
        scope: value
        for scope, value in PreferenceValue.objects.filter(key=spec.key)
        .filter(clause)
        .values_list("scope", "value")
    }
    return PreferenceLevels(
        global_=stored.get(LEVEL_GLOBAL, UNSET),
        workspace=stored.get(LEVEL_WORKSPACE, UNSET),
        user=stored.get(LEVEL_USER, UNSET),
    )


def _resolve(spec: PreferenceKey, levels: PreferenceLevels) -> tuple[Any, str]:
    """Apply *spec*'s mode to *levels* and return ``(value, source)``."""
    if spec.mode == "union":
        merged: list[str] = []
        seen: set[str] = set()

        def _extend(values: Any) -> None:
            # A hand-edited row of the wrong shape must never break a read: it
            # is skipped exactly like an absent one.
            if not isinstance(values, list):
                return
            for item in values:
                if item not in seen:
                    seen.add(item)
                    merged.append(item)

        _extend(copy.deepcopy(list(spec.default or [])))
        for level in _UNION_ORDER:
            value = levels.get(level)
            if value is not UNSET:
                _extend(value)
        if spec.choices:
            rank = {choice: index for index, choice in enumerate(spec.choices)}
            # Stable sort: items outside ``choices`` (only possible through a
            # hand-edited row) keep their insertion order at the end.
            merged.sort(key=lambda item: rank.get(item, len(rank)))
        return merged, SOURCE_MERGED

    for level in _PRECEDENCE:
        value = levels.get(level)
        if value is not UNSET:
            return copy.deepcopy(value), level
    return copy.deepcopy(spec.default), SOURCE_DEFAULT


# ---------------------------------------------------------------------------
# Service facade
# ---------------------------------------------------------------------------


class PreferenceService(ServiceBase):
    """Read/write the three-level preference store (Q1).

    Note: ``auth_tenancy.services.PreferenceService`` is an unrelated, older
    service for ``UserWorkspacePreference`` (feature visibility). This one is the
    Q1 facade and lives in Layer 2, per Plan C.
    """

    # ------------------------------------------------------------------
    # Effective resolution
    # ------------------------------------------------------------------

    def effective(
        self,
        ctx: AuthContext,
        *,
        workspace_id: UUID | None = None,
        keys: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return the effective value and source of every selected key.

        Args:
            ctx: Caller identity; ``ctx.user_id`` supplies the user level.
            workspace_id: Target workspace, or ``None`` for the caller's
                account-wide view (user + global only).
            keys: Restrict the answer to these keys; ``None`` = all registered
                keys. An unregistered key is caller input and raises.

        Returns:
            ``{"workspace_id": str | None, "values": {key: {"value": …,
            "source": …}}}`` with keys sorted, so the payload is deterministic.

        Raises:
            ValidationError: a key in *keys* is not registered.
        """
        self._set_tenant_context(ctx)
        specs = self._selected_keys(keys)
        values: dict[str, Any] = {}
        for spec in specs:
            levels = levels_for(
                tenant_id=ctx.tenant_id,
                workspace_id=workspace_id,
                user_id=ctx.user_id,
                key=spec.key,
            )
            value, source = _resolve(spec, levels)
            values[spec.key] = {"value": value, "source": source}
        return {
            "workspace_id": str(workspace_id) if workspace_id is not None else None,
            "values": values,
        }

    # ------------------------------------------------------------------
    # One level
    # ------------------------------------------------------------------

    def get_level(
        self,
        ctx: AuthContext,
        *,
        scope: str,
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Return one level's *stored* values (not the resolved value).

        Only keys that actually have a row at that level appear — "not set" is
        expressed by absence, never by a fabricated empty value. The user level
        is always the caller's own (``ctx.user_id`` is the whole boundary).

        Returns:
            ``{"scope": scope, "workspace_id": str | None, "values": {key: value}}``
            with keys sorted.

        Raises:
            ValidationError: unknown scope, or ``scope="workspace"`` without a
                ``workspace_id``.
        """
        self._assert_scope(scope)
        self._assert_level_target(scope, workspace_id)
        self._set_tenant_context(ctx)
        stored = (
            self._level_queryset(scope, workspace_id, ctx)
            .order_by("key")
            .values_list("key", "value")
        )
        return {
            "scope": scope,
            "workspace_id": str(workspace_id) if workspace_id is not None else None,
            "values": {key: value for key, value in stored},
        }

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def set_level(
        self,
        ctx: AuthContext,
        *,
        scope: str,
        values: Mapping[str, Any],
        workspace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Store (or reset) *values* on one level, atomically.

        ``None`` as a value resets that key at this level by deleting the row, so
        resolution falls back to the next level. The whole payload is validated
        before the first write: an unknown key, a wrong type, a value outside
        ``choices``, a failing per-key validator or a level the key does not
        allow all reject the call and leave the store untouched.

        Permissions (``ENT-C3 = B``): the user level is self-service; the
        workspace level requires :attr:`Operation.WORKSPACE_CONFIG` (admin tier);
        the global level requires the ``admin`` role (the REST/MCP layer adds the
        API-key capability gate on top).

        Returns:
            The written level, in :meth:`get_level`'s shape.

        Raises:
            ValidationError: invalid scope/target/payload (nothing written).
            PermissionDeniedError: missing write authority for this level.
        """
        self._assert_scope(scope)
        self._assert_level_target(scope, workspace_id)
        if not isinstance(values, Mapping):
            raise ValidationError(
                "'values' must be an object mapping preference keys to values"
            )
        self._set_tenant_context(ctx)
        self._assert_level_write_permission(ctx, scope)
        writes = self._validated_writes(values, scope)

        with transaction.atomic():
            for spec, value in writes:
                self._write_one(ctx, scope, workspace_id, spec, value)

        return self.get_level(ctx, scope=scope, workspace_id=workspace_id)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _selected_keys(self, keys: list[str] | None) -> tuple[PreferenceKey, ...]:
        """Resolve the ``keys`` filter to specs, sorted and de-duplicated."""
        if keys is None:
            return all_preference_keys()
        by_key: dict[str, PreferenceKey] = {}
        for key in keys:
            spec = get_preference_key(key)
            by_key[spec.key] = spec
        return tuple(by_key[name] for name in sorted(by_key))

    @staticmethod
    def _assert_scope(scope: str) -> None:
        if scope not in WRITABLE_SCOPES:
            raise ValidationError(
                f"Unknown preference scope {scope!r}; expected one of "
                f"{list(WRITABLE_SCOPES)}"
            )

    @staticmethod
    def _assert_level_target(scope: str, workspace_id: UUID | None) -> None:
        if scope == LEVEL_WORKSPACE and workspace_id is None:
            raise ValidationError("scope 'workspace' requires a workspace_id")

    def _assert_level_write_permission(self, ctx: AuthContext, scope: str) -> None:
        """Enforce the write gate of *scope* (see :meth:`set_level`)."""
        if scope == LEVEL_USER:
            # Self-service: ``ctx.user_id`` is the whole boundary — the caller
            # can only ever write their own (account-wide) row.
            return
        if scope == LEVEL_WORKSPACE:
            # Imported lazily for the same circular-import reason as
            # ``ServiceBase._assert_write_permission``.
            from auth_tenancy.services.authorization import (
                AuthorizationService,
                Operation,
            )

            decision = AuthorizationService().decide_access(
                ctx.active_roles, Operation.WORKSPACE_CONFIG
            )
            if not decision.allow:
                raise PermissionDeniedError(
                    "Permission denied: a workspace-wide preference requires "
                    f"the workspace_config operation, user has {ctx.active_roles}"
                )
            return
        self._assert_permission(ctx, ROLE_ADMIN)

    @staticmethod
    def _validated_writes(
        values: Mapping[str, Any], scope: str
    ) -> list[tuple[PreferenceKey, Any]]:
        """Validate the whole payload up front; return ``(spec, value)`` pairs.

        Nothing is written here — a failing entry therefore cannot leave a
        half-applied payload behind.
        """
        writes: list[tuple[PreferenceKey, Any]] = []
        for key, value in values.items():
            if not isinstance(key, str):
                raise ValidationError(
                    f"Preference keys must be strings, got {type(key).__name__}"
                )
            spec = get_preference_key(key)
            if scope not in spec.levels:
                raise ValidationError(
                    f"Preference key {key!r} cannot be set at level {scope!r}; "
                    f"allowed levels: {sorted(spec.levels)}"
                )
            if value is not None:
                validate_preference_value(spec, value)
            writes.append((spec, value))
        return writes

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def _level_queryset(
        self, scope: str, workspace_id: UUID | None, ctx: AuthContext
    ) -> QuerySet[PreferenceValue]:
        """QuerySet narrowed to one level of one caller (tenant-scoped manager)."""
        queryset = PreferenceValue.objects.filter(scope=scope)
        if scope == LEVEL_WORKSPACE:
            queryset = queryset.filter(workspace_id=workspace_id)
        elif scope == LEVEL_USER:
            queryset = queryset.filter(user_id=ctx.user_id)
        return queryset

    def _stored_value(
        self, scope: str, workspace_id: UUID | None, ctx: AuthContext, key: str
    ) -> Any:
        """Return the level's current value for *key*, or :data:`UNSET`."""
        row = (
            self._level_queryset(scope, workspace_id, ctx)
            .filter(key=key)
            .values_list("value", flat=True)
            .first()
        )
        return UNSET if row is None else row

    def _write_one(
        self,
        ctx: AuthContext,
        scope: str,
        workspace_id: UUID | None,
        spec: PreferenceKey,
        value: Any,
    ) -> None:
        """Upsert or delete one (level, key) row, auditing workspace/global."""
        audited = scope != LEVEL_USER

        if value is None:
            # Reset = delete the row. The previous value is only needed for the
            # audit trail, and only when a row was actually removed.
            old = self._stored_value(scope, workspace_id, ctx, spec.key) if audited else UNSET
            deleted, _ = (
                self._level_queryset(scope, workspace_id, ctx)
                .filter(key=spec.key)
                .delete()
            )
            if deleted and audited:
                self._audit_write(ctx, scope, workspace_id, spec.key, old, None)
            return

        old = self._stored_value(scope, workspace_id, ctx, spec.key) if audited else UNSET
        target: dict[str, Any] = {
            "tenant_id": ctx.tenant_id,
            "scope": scope,
            "key": spec.key,
        }
        if scope == LEVEL_WORKSPACE:
            target["workspace_id"] = workspace_id
        elif scope == LEVEL_USER:
            target["user_id"] = ctx.user_id
        # ``update_or_create``'s create path goes through ``QuerySet.create``,
        # which bypasses ``TenantManager.create``'s auto-inject — so ``tenant_id``
        # is passed explicitly (same reason as ``TreeDisplayConfigService``).
        PreferenceValue.objects.update_or_create(**target, defaults={"value": value})

        if audited:
            self._audit_write(ctx, scope, workspace_id, spec.key, old, value)

    def _audit_write(
        self,
        ctx: AuthContext,
        scope: str,
        workspace_id: UUID | None,
        key: str,
        old: Any,
        new: Any,
    ) -> None:
        """Write one ``preference_value`` audit entry for a workspace/global write.

        One entry per changed key: the ``details`` shape carries a single
        ``key``/``old``/``new`` triple, so a multi-key PATCH produces one entry
        per key rather than an entry whose triple would have to be a list.
        """
        entity_id = workspace_id if scope == LEVEL_WORKSPACE else ctx.tenant_id
        self._audit(
            ctx,
            _AUDIT_OPERATION,
            _AUDIT_ENTITY_TYPE,
            entity_id,
            details={
                "scope": scope,
                "workspace_id": str(workspace_id) if workspace_id is not None else None,
                "key": key,
                "old": None if old is UNSET else old,
                "new": new,
            },
        )


__all__ = [
    "LEVEL_GLOBAL",
    "LEVEL_USER",
    "LEVEL_WORKSPACE",
    "SOURCE_DEFAULT",
    "SOURCE_MERGED",
    "UNSET",
    "WRITABLE_SCOPES",
    "PreferenceLevels",
    "PreferenceService",
    "levels_for",
    "resolve_for",
]
