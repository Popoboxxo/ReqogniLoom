"""Change-impact analysis policy — the organisational ceiling (S4.10).

The analysis parameters of the structured change-impact run are **not** code
constants but a two-level configuration on the existing preference mechanism
(ADR-033 ``## Policy-Keys und Ebenen (S0.4)``, spec §4.2.6):

* ``global`` — the tenant-wide default (System Settings),
* ``workspace`` — the per-workspace override,

resolved ``workspace > global > default``. There is deliberately **no** ``user``
level: this is an organisational policy, not a personal preference.

Policy is an organisational ceiling; call parameters can only be more restrictive.

Numbers are stored as ``enum`` string choices because the preference registry has
no numeric ``value_type``; :func:`resolved_policy` types them (``"200"`` → ``200``,
``"0.05"`` → ``0.05``) so a stored string and a stored number cannot drift apart in
:func:`policy_hash` and therefore not in the run fingerprint.

``MAX_PATHS_PER_FINDING`` is a **code constant**, explicitly not a policy key: the
number of example paths kept per finding is an implementation detail of the
algorithm, not something a tenant may tune.

Registration happens in the owning ``application`` app's ``AppConfig.ready()``
through :func:`register_change_impact_policy_keys` (same idiom as
``backend/traceability/apps.py``).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured

from application.preference_registry import (
    PreferenceKey,
    UiEditor,
    ValueType,
    get_preference_key,
    register_preference_key,
)
from auth_tenancy.models import (
    PREFERENCE_SCOPE_GLOBAL,
    PREFERENCE_SCOPE_WORKSPACE,
)
from persistence.errors import ValidationError

# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

TRIGGER_KEY: Final = "change_impact.trigger"
SCHEDULE_INTERVAL_KEY: Final = "change_impact.schedule_interval_hours"
SEMANTIC_EDGES_KEY: Final = "change_impact.semantic_edges"
LLM_ANNOTATION_KEY: Final = "change_impact.llm_annotation"
MAX_DEPTH_KEY: Final = "change_impact.max_depth"
MAX_NODES_KEY: Final = "change_impact.max_nodes"
MIN_WEIGHT_KEY: Final = "change_impact.min_weight"

#: When a run comes into existence. ``on_write`` is debounced by the caller.
TRIGGER_CHOICES: Final[tuple[str, ...]] = (
    "manual",
    "on_submit",
    "on_write",
    "scheduled",
)
TRIGGER_DEFAULT: Final = "manual"

#: Celery-beat scan cadence, only relevant for ``trigger == "scheduled"``.
SCHEDULE_INTERVAL_CHOICES: Final[tuple[str, ...]] = ("6", "12", "24", "168")
SCHEDULE_INTERVAL_DEFAULT: Final = "24"

MAX_DEPTH_CHOICES: Final[tuple[str, ...]] = ("2", "3", "4", "5", "6")
MAX_DEPTH_DEFAULT: Final = "4"

MAX_NODES_CHOICES: Final[tuple[str, ...]] = ("100", "200", "500")
MAX_NODES_DEFAULT: Final = "200"

MIN_WEIGHT_CHOICES: Final[tuple[str, ...]] = ("0.01", "0.05", "0.1", "0.2")
MIN_WEIGHT_DEFAULT: Final = "0.05"

# ---------------------------------------------------------------------------
# Hard caps and code constants
# ---------------------------------------------------------------------------

#: Upper bound on the traversal depth, whatever the policy says.
MAX_DEPTH_HARD_CAP: Final = 6

#: Upper bound on the visited-node count, whatever the policy says.
MAX_NODES_HARD_CAP: Final = 500

#: Example paths kept per finding — a code constant, NOT a policy key.
MAX_PATHS_PER_FINDING: Final = 3

#: Preference levels a policy key may live on (no ``user`` level).
POLICY_LEVELS: Final[frozenset[str]] = frozenset(
    {PREFERENCE_SCOPE_GLOBAL, PREFERENCE_SCOPE_WORKSPACE}
)

#: Source reported when the registry default is the effective value.
SOURCE_DEFAULT: Final = "default"

# ---------------------------------------------------------------------------
# Registry specs
# ---------------------------------------------------------------------------


def _spec(
    *,
    key: str,
    value_type: ValueType,
    default: Any,
    choices: tuple[str, ...] | None = None,
    ui_editor: UiEditor | None = None,
) -> PreferenceKey:
    """Build one policy :class:`PreferenceKey` with the shared level set."""
    return PreferenceKey(
        key=key,
        value_type=value_type,
        default=default,
        levels=POLICY_LEVELS,
        choices=choices,
        ui_editor=ui_editor,
        owner="S4",
    )


#: Every change-impact policy key, in the documented (spec §4.2.6) order.
POLICY_KEY_SPECS: Final[tuple[PreferenceKey, ...]] = (
    _spec(
        key=TRIGGER_KEY,
        value_type="enum",
        default=TRIGGER_DEFAULT,
        choices=TRIGGER_CHOICES,
        ui_editor="select",
    ),
    _spec(
        key=SCHEDULE_INTERVAL_KEY,
        value_type="enum",
        default=SCHEDULE_INTERVAL_DEFAULT,
        choices=SCHEDULE_INTERVAL_CHOICES,
        ui_editor="select",
    ),
    _spec(
        key=SEMANTIC_EDGES_KEY,
        value_type="bool",
        default=False,
        ui_editor="checkbox",
    ),
    _spec(
        key=LLM_ANNOTATION_KEY,
        value_type="bool",
        default=False,
        ui_editor="checkbox",
    ),
    _spec(
        key=MAX_DEPTH_KEY,
        value_type="enum",
        default=MAX_DEPTH_DEFAULT,
        choices=MAX_DEPTH_CHOICES,
        ui_editor="select",
    ),
    _spec(
        key=MAX_NODES_KEY,
        value_type="enum",
        default=MAX_NODES_DEFAULT,
        choices=MAX_NODES_CHOICES,
        ui_editor="select",
    ),
    _spec(
        key=MIN_WEIGHT_KEY,
        value_type="enum",
        default=MIN_WEIGHT_DEFAULT,
        choices=MIN_WEIGHT_CHOICES,
        ui_editor="select",
    ),
)

#: Keys whose typed value is an ``int``.
_INT_KEYS: Final[frozenset[str]] = frozenset(
    {SCHEDULE_INTERVAL_KEY, MAX_DEPTH_KEY, MAX_NODES_KEY}
)

#: Decimal places kept for ``min_weight`` (the choices carry two).
_MIN_WEIGHT_QUANTUM: Final = Decimal("0.0001")


def register_change_impact_policy_keys() -> None:
    """Register every policy key process-wide, idempotently.

    Mirrors the ``traceability`` idiom: a key that is already registered (a
    second ``ready()`` call, a test that pre-registered it) is left untouched
    instead of raising ``ImproperlyConfigured``.
    """
    for spec in POLICY_KEY_SPECS:
        try:
            get_preference_key(spec.key)
        except ValidationError:
            register_preference_key(spec)


# ---------------------------------------------------------------------------
# Typing
# ---------------------------------------------------------------------------


def _coerce_int(raw: Any) -> int | None:
    """Return *raw* as an ``int``, or ``None`` when it cannot be read as one."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        # A JSON number can arrive as ``200.0`` (e.g. a hand-edited legacy row).
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            return None
    return None


def _coerce_min_weight(raw: Any) -> float | None:
    """Return *raw* as a ``float`` rounded to four decimals, or ``None``."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        raw = str(raw)
    if not isinstance(raw, str):
        return None
    try:
        return float(Decimal(raw.strip()).quantize(_MIN_WEIGHT_QUANTUM))
    except (InvalidOperation, ValueError):
        return None


def _coerce(spec: PreferenceKey, raw: Any) -> Any:
    """Type *raw* according to *spec*; ``None`` means "cannot be typed".

    A hand-edited or legacy row of the wrong shape returns ``None`` so the caller
    can fall back to the registry default — one unreadable value must never break
    a whole run (or the gate that reads the policy).
    """
    if spec.value_type == "bool":
        return raw if isinstance(raw, bool) else None
    if spec.key in _INT_KEYS:
        return _coerce_int(raw)
    if spec.key == MIN_WEIGHT_KEY:
        return _coerce_min_weight(raw)
    # ``trigger`` and any future plain enum: the stored value must be a choice.
    if isinstance(raw, str) and raw in (spec.choices or ()):
        return raw
    return None


def _default_typed(spec: PreferenceKey) -> Any:
    """Return *spec*'s default, typed (registration already validated it)."""
    typed = _coerce(spec, spec.default)
    if typed is None:  # pragma: no cover - register_preference_key validated it
        raise ImproperlyConfigured(
            f"Policy key {spec.key!r}: default {spec.default!r} cannot be typed"
        )
    return typed


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolved_policy(
    *, tenant_id: UUID, workspace_id: UUID | None
) -> dict[str, Any]:
    """Resolve every policy key for one (tenant, workspace).

    Returns:
        ``{"effective": {key: typed value}, "source": {key: source}}`` where
        ``source`` is ``"workspace"`` / ``"global"`` / ``"default"`` per key.

    Raises:
        ValidationError: a policy key is not registered (programming error — the
            ``ready()`` hook is missing), or the tenancy ids are invalid.
    """
    # Local import: ``preference_service`` pulls in ServiceBase and the models,
    # while this module is imported from ``AppConfig.ready()``.
    from application.preference_service import resolve_for

    effective: dict[str, Any] = {}
    source: dict[str, str] = {}
    for spec in POLICY_KEY_SPECS:
        value, value_source = resolve_for(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=None,  # policy keys have no user level
            key=spec.key,
        )
        typed = _coerce(spec, value)
        if typed is None:
            # Unreadable stored value: fall back to the registry default and say
            # so, instead of raising for a single bad row.
            typed = _default_typed(spec)
            value_source = SOURCE_DEFAULT
        effective[spec.key] = typed
        source[spec.key] = value_source
    return {"effective": effective, "source": source}


def policy_hash(policy_effective: Mapping[str, Any]) -> str:
    """Return the SHA-256 of the canonical-JSON typed policy.

    The typed value is hashed (``200`` and ``"200"`` therefore hash identically),
    and ``sort_keys`` makes the digest independent of dict insertion order — a
    requirement of the two run fingerprints that include the policy.
    """
    canonical = json.dumps(
        dict(policy_effective),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Clamping (policy as ceiling)
# ---------------------------------------------------------------------------


def _assert_int(key: str, value: Any) -> None:
    """Raise ``ValidationError`` unless *value* is a genuine ``int`` request."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(
            f"Change-impact parameter {key!r} must be an integer, "
            f"got {type(value).__name__}"
        )


def _assert_bool(key: str, value: Any) -> None:
    """Raise ``ValidationError`` unless *value* is a genuine ``bool`` request."""
    if not isinstance(value, bool):
        raise ValidationError(
            f"Change-impact parameter {key!r} must be a boolean, "
            f"got {type(value).__name__}"
        )


def _ceiling(effective: Mapping[str, Any], key: str) -> Any:
    """Return the typed policy ceiling for *key* (registry default if absent)."""
    spec = get_preference_key(key)
    typed = _coerce(spec, effective.get(key))
    return _default_typed(spec) if typed is None else typed


def clamp_parameters(
    *,
    effective: Mapping[str, Any],
    max_depth: int | None = None,
    max_nodes: int | None = None,
    include_semantic: bool | None = None,
    include_llm: bool | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Restrict ``request`` parameters to the policy ceiling.

    Policy is an organisational ceiling; call parameters can only be more
    restrictive. A request can never *raise* a limit or *enable* a feature the
    policy forbids, and every parameter that had to be narrowed is named in the
    returned ``clamped`` list (the transport reports it as ``policy.clamped``).

    Args:
        effective: The typed effective policy (:func:`resolved_policy`'s
            ``"effective"`` map); a missing key falls back to its default.
        max_depth: Requested traversal depth, or ``None`` to take the policy.
        max_nodes: Requested node cap, or ``None`` to take the policy.
        include_semantic: Requested semantic-edge opt-in, or ``None`` for policy.
        include_llm: Requested LLM-annotation opt-in, or ``None`` for policy.

    Returns:
        ``(parameters, clamped)`` with ``parameters`` holding the four resolved
        keys and ``clamped`` the sorted key names that were narrowed.

    Raises:
        ValidationError: a given request value is not an ``int`` / ``bool``.
    """
    clamped: list[str] = []
    parameters: dict[str, Any] = {}

    depth_ceiling = min(_ceiling(effective, MAX_DEPTH_KEY), MAX_DEPTH_HARD_CAP)
    if max_depth is None:
        parameters[MAX_DEPTH_KEY] = depth_ceiling
    else:
        _assert_int(MAX_DEPTH_KEY, max_depth)
        parameters[MAX_DEPTH_KEY] = min(max_depth, depth_ceiling, MAX_DEPTH_HARD_CAP)
        if parameters[MAX_DEPTH_KEY] != max_depth:
            clamped.append(MAX_DEPTH_KEY)

    nodes_ceiling = min(_ceiling(effective, MAX_NODES_KEY), MAX_NODES_HARD_CAP)
    if max_nodes is None:
        parameters[MAX_NODES_KEY] = nodes_ceiling
    else:
        _assert_int(MAX_NODES_KEY, max_nodes)
        parameters[MAX_NODES_KEY] = min(max_nodes, nodes_ceiling, MAX_NODES_HARD_CAP)
        if parameters[MAX_NODES_KEY] != max_nodes:
            clamped.append(MAX_NODES_KEY)

    parameters[SEMANTIC_EDGES_KEY] = _resolve_flag(
        effective,
        key=SEMANTIC_EDGES_KEY,
        requested=include_semantic,
        clamped=clamped,
    )
    parameters[LLM_ANNOTATION_KEY] = _resolve_flag(
        effective,
        key=LLM_ANNOTATION_KEY,
        requested=include_llm,
        clamped=clamped,
    )

    clamped.sort()
    return parameters, clamped


def _resolve_flag(
    effective: Mapping[str, Any],
    *,
    key: str,
    requested: bool | None,
    clamped: list[str],
) -> bool:
    """Return ``requested and policy``; report a clamp only when it narrowed.

    ``policy True + request False`` is allowed (more restrictive) and therefore
    never appears in ``clamped``.
    """
    ceiling = _ceiling(effective, key)
    if requested is None:
        return ceiling
    _assert_bool(key, requested)
    if requested and not ceiling:
        clamped.append(key)
        return False
    return requested and ceiling


__all__ = [
    "LLM_ANNOTATION_KEY",
    "MAX_DEPTH_CHOICES",
    "MAX_DEPTH_DEFAULT",
    "MAX_DEPTH_HARD_CAP",
    "MAX_DEPTH_KEY",
    "MAX_NODES_CHOICES",
    "MAX_NODES_DEFAULT",
    "MAX_NODES_HARD_CAP",
    "MAX_NODES_KEY",
    "MAX_PATHS_PER_FINDING",
    "MIN_WEIGHT_CHOICES",
    "MIN_WEIGHT_DEFAULT",
    "MIN_WEIGHT_KEY",
    "POLICY_KEY_SPECS",
    "POLICY_LEVELS",
    "SCHEDULE_INTERVAL_CHOICES",
    "SCHEDULE_INTERVAL_DEFAULT",
    "SCHEDULE_INTERVAL_KEY",
    "SEMANTIC_EDGES_KEY",
    "SOURCE_DEFAULT",
    "TRIGGER_CHOICES",
    "TRIGGER_DEFAULT",
    "TRIGGER_KEY",
    "clamp_parameters",
    "policy_hash",
    "register_change_impact_policy_keys",
    "resolved_policy",
]
