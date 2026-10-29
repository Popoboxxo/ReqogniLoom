"""Central slot-level memory-injection policy (Plan A T-A1-2, ADR-024 AC-3/AC-4).

One place decides whether a prompt slot may receive retrieved memory. Before
this module the answer was spread over three ad-hoc checks (the resolver's
``memory_context`` declaration check, ``context_builder``'s workspace-toggle
lookup and the two bypass consumers), so a workspace switch could not reach
every consumer and a user switch did not exist at all.

The decision is a pure function of Q1 (Plan C's three-level preference store)
plus the ``WorkspaceMemorySettings.enabled`` facade column:

    not hard_off
    AND slot ∉ system.disabled_slots          (tenant-global level)
    AND ws.enabled                            (the existing column)
    AND slot ∉ ws.disabled_slots              (workspace level)
    AND (user.enabled OR NOT ws.allow_user_opt_out)
    AND slot ∉ user.disabled_slots            (user level)

``memory.disabled_slots`` is a ``union`` key, but the *levels* are read
separately (``levels_for``) so a blocked slot can name the level that blocked
it instead of a single merged "disabled". ``ws.enabled`` stays the column it
always was (``WorkspaceMemorySettings``); the Q1 keys are only the new
slot/opt-out dimensions, which is why this PR needs no migration.

Failure mode: memory is an enhancement, never a hard requirement (the same
contract ``context_builder`` follows), so a broken Q1 lookup yields
``inject=False, reason="policy_unavailable"`` — the AI call continues without
memory instead of failing. Nothing in this module raises for a lookup failure.

The one non-obvious fail direction is the slot vocabulary: an unknown
``slot_name`` (typo, rename, never a memory consumer) answers
``inject=False, reason="slot_missing"``. It must not fail open, because no level
of ``memory.disabled_slots`` could ever name such a slot — every per-slot
switch would be silently bypassed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final, Literal
from uuid import UUID

from application.preference_service import levels_for, resolve_for
from application.prompt_slots import get_prompt_slots, is_memory_hard_off
from persistence.errors import ValidationError
from persistence.tenancy import TenantContext

logger = logging.getLogger(__name__)

#: Q1 keys owned by Plan A (registered in ``memory/apps.py``).
DISABLED_SLOTS_KEY: Final = "memory.disabled_slots"
ALLOW_USER_OPT_OUT_KEY: Final = "memory.allow_user_opt_out"
USER_ENABLED_KEY: Final = "memory.enabled"

#: Render order of the memory sections (artifact only when the caller has one).
RENDER_SCOPES: Final[tuple[str, ...]] = ("artifact", "workspace", "user")

InjectionReason = Literal[
    "ok",
    "hard_off",
    "system_disabled",
    "workspace_disabled",
    "workspace_slot_disabled",
    "user_opted_out",
    "user_slot_disabled",
    "policy_unavailable",
    "slot_missing",
]


def _memory_consumer_slots() -> frozenset[str]:
    """Every slot the policy governs: registry ``memory_context`` slots + AI review.

    ``audit.ai_review`` builds its prompt outside the slot registry (the review
    prompt is a plain module constant), so it cannot declare the data variable
    and is added explicitly. HARD_OFF slots never declare ``memory_context``
    (that is what T-A1-1 enforces), so they cannot leak in through the registry.
    """
    declared = {
        name
        for name, spec in get_prompt_slots().items()
        if "memory_context" in spec.data_variables
    }
    return frozenset(declared | {"audit.ai_review"})


#: The complete, derived slot vocabulary. Not hand-maintained: adding a
#: ``memory_context`` slot to :mod:`application.prompt_slots` opts it in here.
MEMORY_CONSUMER_SLOTS: frozenset[str] = _memory_consumer_slots()


@dataclass(frozen=True)
class InjectionDecision:
    """The policy's answer for one (tenant, workspace, user, slot).

    Attributes:
        inject: Whether the caller may search/render memory at all.
        scopes: Scopes to search, in render order. Always ``()`` when
            ``inject`` is ``False``; ``"user"`` is removed when the workspace
            forbids opting out while the user has opted out (ENT-A7 = B:
            personal memory is never injected against the user's wish).
        reason: Why. ``"ok"`` on the only injecting outcome.
    """

    inject: bool
    scopes: tuple[str, ...]
    reason: InjectionReason


def _contains(values: Any, item: str) -> bool:
    """Return whether the (union-resolved) level value names *item*."""
    return isinstance(values, list) and item in values


def _workspace_enabled(tenant_id: UUID, workspace_id: UUID) -> bool:
    """Read the ``WorkspaceMemorySettings.enabled`` facade column.

    Missing row = feature ON, exactly like the REST GET and the projector. The
    tenant is armed for the single query and the previous thread-local state is
    restored in a ``finally`` — the same hygiene contract ``levels_for``
    follows, so a Celery caller neither leaks nor loses its tenant.
    """
    from memory.models import WorkspaceMemorySettings

    was_set = TenantContext.is_set()
    previous = TenantContext.get_tenant() if was_set else None
    TenantContext.set_tenant(tenant_id)
    try:
        enabled = (
            WorkspaceMemorySettings.objects.filter(workspace_id=workspace_id)
            .values_list("enabled", flat=True)
            .first()
        )
    finally:
        if was_set and previous is not None:
            TenantContext.set_tenant(previous)
        else:
            TenantContext.clear_tenant()
    return True if enabled is None else enabled


def resolve_injection(
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    user_id: UUID | None,
    slot_name: str | None,
) -> InjectionDecision:
    """Decide whether *slot_name* may receive memory for this caller.

    Args:
        tenant_id: Owning tenant (Q1 levels are tenant-scoped).
        workspace_id: Target workspace (the ``WorkspaceMemorySettings`` row and
            the workspace Q1 level).
        user_id: The calling user, or ``None`` for a context-free caller (the
            user level and the ``user`` scope are then skipped).
        slot_name: The prompt slot. Empty/``None`` or a name outside
            :data:`MEMORY_CONSUMER_SLOTS` is a policy bypass attempt and answers
            ``slot_missing`` without any lookup (fail closed: an unknown slot
            can never be named by a disable list, so failing open would ignore
            every per-slot switch).

    Returns:
        The :class:`InjectionDecision`; never raises on a lookup failure.
    """
    if not slot_name:
        return InjectionDecision(inject=False, scopes=(), reason="slot_missing")
    if is_memory_hard_off(slot_name):
        return InjectionDecision(inject=False, scopes=(), reason="hard_off")
    if slot_name not in MEMORY_CONSUMER_SLOTS:
        # Fail CLOSED for an unknown name (a typo, a rename, a slot that never
        # declared memory_context). Otherwise a misspelled slot would silently
        # bypass every per-slot disable, because no level could ever name it.
        return InjectionDecision(inject=False, scopes=(), reason="slot_missing")

    try:
        system_levels = levels_for(
            tenant_id=tenant_id,
            workspace_id=None,
            user_id=None,
            key=DISABLED_SLOTS_KEY,
        )
        workspace_levels = levels_for(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=None,
            key=DISABLED_SLOTS_KEY,
        )
        user_levels = (
            levels_for(
                tenant_id=tenant_id,
                workspace_id=None,
                user_id=user_id,
                key=DISABLED_SLOTS_KEY,
            )
            if user_id is not None
            else None
        )
        allow_user_opt_out, _ = resolve_for(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=None,
            key=ALLOW_USER_OPT_OUT_KEY,
        )
        user_enabled, _ = (
            resolve_for(
                tenant_id=tenant_id,
                workspace_id=None,
                user_id=user_id,
                key=USER_ENABLED_KEY,
            )
            if user_id is not None
            else (True, "default")
        )
        workspace_enabled = _workspace_enabled(tenant_id, workspace_id)
    except Exception as exc:  # noqa: BLE001 -- fail-safe by contract, see module docstring
        logger.warning(
            "memory injection policy unavailable (%s: %s); not injecting memory",
            type(exc).__name__,
            exc,
        )
        return InjectionDecision(inject=False, scopes=(), reason="policy_unavailable")

    if _contains(system_levels.global_, slot_name):
        return InjectionDecision(inject=False, scopes=(), reason="system_disabled")
    if not workspace_enabled:
        return InjectionDecision(inject=False, scopes=(), reason="workspace_disabled")
    if _contains(workspace_levels.workspace, slot_name):
        return InjectionDecision(
            inject=False, scopes=(), reason="workspace_slot_disabled"
        )

    user_opted_out = user_enabled is False
    if user_opted_out and allow_user_opt_out:
        return InjectionDecision(inject=False, scopes=(), reason="user_opted_out")
    # Checked outside the opt-out branch: a slot the user disabled at the user
    # level stays disabled even when the workspace forbids the global opt-out.
    if user_levels is not None and _contains(user_levels.user, slot_name):
        return InjectionDecision(inject=False, scopes=(), reason="user_slot_disabled")

    scopes = RENDER_SCOPES
    if user_opted_out:
        # ENT-A7 = B: the workspace may enforce injection, but never the
        # personal ``user`` scope the user switched off.
        scopes = tuple(scope for scope in scopes if scope != "user")
    return InjectionDecision(inject=True, scopes=scopes, reason="ok")


def validate_disabled_slots(value: Any) -> None:
    """Validate a ``memory.disabled_slots`` write against the slot vocabulary.

    Called by the Q1 registry on every write (and on the default), so the REST
    facade and the generic preference surface share one validation path.

    Raises:
        ValidationError: the list names a HARD_OFF slot (message contains
            ``slot is hard-off``) or a slot that is not a memory consumer.
    """
    items = [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
    hard_off = sorted({item for item in items if is_memory_hard_off(item)})
    if hard_off:
        raise ValidationError(
            f"slot is hard-off and cannot be disabled: {hard_off}"
        )
    unknown = sorted({item for item in items if item not in MEMORY_CONSUMER_SLOTS})
    if unknown:
        raise ValidationError(
            f"Unknown memory slot(s) {unknown}; expected a subset of "
            f"{sorted(MEMORY_CONSUMER_SLOTS)}"
        )


__all__ = [
    "ALLOW_USER_OPT_OUT_KEY",
    "DISABLED_SLOTS_KEY",
    "MEMORY_CONSUMER_SLOTS",
    "RENDER_SCOPES",
    "USER_ENABLED_KEY",
    "InjectionDecision",
    "InjectionReason",
    "resolve_injection",
    "validate_disabled_slots",
]
