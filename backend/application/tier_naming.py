"""Relative tier naming layer (ADR-028 D2/D6/D7, concept #1670).

The ladder stores stable ``tier_key`` values; the *display* name follows the
position relative to the branch depth:

* position 1            -> system label ("System")
* position == depth     -> component label ("Component")
* anything in between   -> subsystem label ("Subsystem"), numbered from the
                           second middle tier on so a deep branch stays readable

Labels are workspace-overridable preferences (global default, workspace
override) — renaming never touches ``tier_key`` and therefore never touches
stored data, ReqIF exports or baselines.

D8 (a separate ``module`` tier below Component) is deliberately **not** part of
this module: adding it changes the seeded ladder and the leaf-relative
computation, which is a migration decision of its own.
"""

from __future__ import annotations

from uuid import UUID

NAMING_SYSTEM_KEY = "allocation.naming.system"
NAMING_SUBSYSTEM_KEY = "allocation.naming.subsystem"
NAMING_COMPONENT_KEY = "allocation.naming.component"


def naming_defaults() -> dict[str, str]:
    """Registry defaults, in the language-less form the preferences store."""
    return {
        NAMING_SYSTEM_KEY: "System",
        NAMING_SUBSYSTEM_KEY: "Subsystem",
        NAMING_COMPONENT_KEY: "Component",
    }


def _label(*, tenant_id: UUID | None, workspace_id: UUID | None, key: str) -> str:
    default = naming_defaults()[key]
    if tenant_id is None:
        return default
    from application.preference_service import resolve_for

    try:
        value, _source = resolve_for(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=None,
            key=key,
        )
    except Exception:  # noqa: BLE001 - a missing registry entry must not break display
        return default
    return str(value) if value else default


def tier_label_for(
    *,
    position: int,
    depth: int,
    tenant_id: UUID | None = None,
    workspace_id: UUID | None = None,
    number_middle: bool = True,
) -> str | None:
    """Return the display label for one ladder position of a *depth*-level branch.

    ``position`` is 0-based (``Requirement.level - 1``); ``depth`` is the number
    of tiers the branch uses. Returns ``None`` for positions outside the branch —
    the caller shows nothing rather than a wrong name.

    D6: the label is relative; the stored ``tier_key`` is not affected.
    """
    if depth < 1 or position < 0 or position >= depth:
        return None

    if position == 0:
        return _label(tenant_id=tenant_id, workspace_id=workspace_id, key=NAMING_SYSTEM_KEY)

    if position == depth - 1:
        return _label(
            tenant_id=tenant_id, workspace_id=workspace_id, key=NAMING_COMPONENT_KEY
        )

    label = _label(
        tenant_id=tenant_id, workspace_id=workspace_id, key=NAMING_SUBSYSTEM_KEY
    )
    # Only number when there are several middle tiers; a single one reads
    # better without a suffix.
    if number_middle and depth >= 4:
        return f"{label} {position}"
    return label
