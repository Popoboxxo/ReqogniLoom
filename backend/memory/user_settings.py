"""User-level memory settings (Plan A T-A1-4, ADR-024 AC-5).

The self-service policy behind ``/api/v1/memory/me/settings/``: the caller's
own personal memory switches, stored as Q1 (Plan C) *user* level preferences.

Two decisions worth spelling out:

* **Thin facade only.** Every write goes through
  :meth:`application.preference_service.PreferenceService.set_level` with
  ``scope="user"``, every read through its context-free sibling
  :func:`application.preference_service.levels_for`. This module never touches
  ``PreferenceValue`` and never re-implements a key's rules: the slot
  vocabulary — including the HARD_OFF rejection — is owned by the Q1 key
  validator registered in ``memory/apps.py``, so this facade and the generic
  preference surface cannot diverge. A write payload is validated *before* the
  first row is touched, per field, so a rejection can name the field the
  caller sent (the same pre-commit pattern as
  ``memory_rest.WorkspaceMemorySettingsView.put``).
* **Own level only.** There is no ``user_id`` parameter anywhere on this path —
  ``ctx.user_id`` *is* the boundary, so writing another user's switch is
  impossible by construction rather than merely forbidden.

Stored vs. effective
--------------------
Reads answer the **stored user level** (defaults from the registry: ``True`` /
``[]``), not the merged value. That is what makes a ``GET``→``PUT`` round-trip
**promotion-free, not write-free**: a merged ``disabled_slots`` would contain
the tenant-global and workspace disables, and writing it back would promote them
into the caller's personal level. The write itself is not skipped — round-tripping
a default answer creates the caller's two user rows holding that default, and
clearing them back to "inherit" is an explicit ``null``. Same stored-vs-effective
split as ``WorkspaceMemorySettingsView`` (which skips unchanged writes because it
writes an audited workspace level).

``effective.opt_out_allowed`` (only with a ``workspace_id``) reports the
workspace-level ``memory.allow_user_opt_out`` value. ENT-A7 = B: a workspace
that forbids the opt-out does **not** prevent storing ``enabled=false`` — the
flag only says that the switch does not apply there (team memory keeps being
injected, the personal ``user`` scope does not; see
:func:`memory.injection_policy.resolve_injection`).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from application.preference_registry import get_preference_key, validate_preference_value
from application.preference_service import PreferenceService, levels_for
from auth_tenancy.context import AuthContext
from memory.injection_policy import (
    ALLOW_USER_OPT_OUT_KEY,
    DISABLED_SLOTS_KEY,
    USER_ENABLED_KEY,
)
from persistence.errors import ValidationError

__all__ = [
    "SETTINGS_FIELDS",
    "MemoryUserSettingRejected",
    "read_user_settings",
    "write_user_settings",
]


#: Wire field name -> Q1 key. The only two switches this surface owns.
SETTINGS_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("enabled", USER_ENABLED_KEY),
    ("disabled_slots", DISABLED_SLOTS_KEY),
)


class MemoryUserSettingRejected(ValidationError):
    """A rejected wire field, tagged so the view can name it in ``details``.

    Raised only for caller input (wrong type, unknown or hard-off slot). The
    message comes verbatim from the Q1 registry's validator; this class adds
    nothing but the ``field`` the caller actually sent.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def _stored_user_value(*, tenant_id: UUID, user_id: UUID, key: str) -> Any:
    """Return the caller's stored value for *key* at the user level.

    A missing row answers :data:`application.preference_service.UNSET` — the
    caller then applies the registry default; "absent" must never be confused
    with a stored falsy value.
    """
    return levels_for(
        tenant_id=tenant_id,
        workspace_id=None,
        user_id=user_id,
        key=key,
    ).user


def read_user_settings(
    *,
    tenant_id: UUID,
    user_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Return the caller's own memory switches (+ the workspace policy hint).

    Args:
        tenant_id: Owning tenant (Q1 levels are tenant-scoped).
        user_id: The caller. There is no other user's level on this path.
        workspace_id: When given, the payload gains ``effective`` with that
            workspace's ``opt_out_allowed``. Membership is **not** checked
            here — the caller (the REST view) must have established it, because
            only the transport layer knows how to answer a non-member without
            disclosing the workspace's existence (QR-S21).

    Returns:
        ``{"enabled": bool, "disabled_slots": [str, ...]}``, plus
        ``{"effective": {"workspace_id": str, "opt_out_allowed": bool}}`` when
        *workspace_id* is given.
    """
    enabled = _stored_user_value(
        tenant_id=tenant_id, user_id=user_id, key=USER_ENABLED_KEY
    )
    disabled = _stored_user_value(
        tenant_id=tenant_id, user_id=user_id, key=DISABLED_SLOTS_KEY
    )
    payload: dict[str, Any] = {
        # A missing row means "inherit", and this key's only level is the user
        # level, so the registry default is the answer. A hand-edited row of the
        # wrong shape is treated like an absent one (never a 500, and never a
        # truthy coercion of a stray string) — the write path cannot produce one.
        "enabled": enabled if isinstance(enabled, bool) else True,
        "disabled_slots": list(disabled) if isinstance(disabled, list) else [],
    }
    if workspace_id is not None:
        allowed = levels_for(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=None,
            key=ALLOW_USER_OPT_OUT_KEY,
        ).workspace
        payload["effective"] = {
            "workspace_id": str(workspace_id),
            "opt_out_allowed": allowed if isinstance(allowed, bool) else True,
        }
    return payload


def write_user_settings(
    ctx: AuthContext, *, payload: Mapping[str, Any]
) -> dict[str, Any]:
    """Store the supplied fields on the caller's own Q1 **user** level.

    Partial by contract: an omitted field keeps its stored value. A field sent
    as ``null`` resets that level (Q1's documented "inherit" semantics), so the
    response falls back to the registry default.

    Args:
        ctx: Caller identity; ``ctx.user_id`` is the whole write boundary.
        payload: Request body. Only the keys of :data:`SETTINGS_FIELDS` are
            read; anything else is ignored (never a way to reach another key).

    Returns:
        The post-write read payload (see :func:`read_user_settings`, without
        ``effective``: this surface writes no workspace state).

    Raises:
        MemoryUserSettingRejected: a supplied field failed the Q1 key's own
            validation (wrong type, unknown or hard-off slot). Nothing is
            written in that case.
    """
    submitted: dict[str, Any] = {}
    for field, key in SETTINGS_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        try:
            # The registry's validator — the *only* place a slot name is judged
            # (unknown slot, HARD_OFF slot), never duplicated here.
            validate_preference_value(get_preference_key(key), value)
        except ValidationError as exc:
            raise MemoryUserSettingRejected(field, str(exc)) from exc
        submitted[key] = value

    if submitted:
        PreferenceService().set_level(ctx, scope="user", values=submitted)

    return read_user_settings(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
