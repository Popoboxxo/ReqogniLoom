"""
ARCH-L1-008 PresetConfigEngine — Domain exceptions.

COMP-PC-001 PresetRegistry    (REQ-L3-PC001-003, REQ-L3-PC001-002)
COMP-PC-003 FeatureGateService (REQ-L3-PC003-001, REQ-L3-PC003-003)

All exceptions raised by the presets subsystem.  Callers import from here
so they do not depend on internal module structure.

leaf_id: ARCH-L1-008
req_id : REQ-L2-PC-001, REQ-L2-PC-002, REQ-L2-PC-011, REQ-L2-PC-012
"""
from __future__ import annotations


class PresetError(Exception):
    """Base class for all PresetConfigEngine errors.

    NOTE: ``rest_api.preset_guard.PresetError`` is a distinct, unrelated
    class with the same name (SYSTEMAUDIT-2026-08-27 AP-6 M-1). It wraps
    *any* exception raised while calling into this module's facade
    functions (``get_preset``, ``is_feature_enabled``) — including
    instances of this base class and its subclasses — into its own type.
    An ``except`` clause on one does not catch the other.
    """


class ConfigurationError(PresetError):
    """Raised when a required key is missing from a preset configuration.

    REQ-L3-PC001-001: any missing key raises ConfigurationError, not KeyError.
    """


class ImmutablePresetError(PresetError):
    """Raised when a caller attempts to modify or delete a default preset.

    REQ-L3-PC001-003 / REQ-L2-PC-012.
    """


class ScopeNotAvailableError(PresetError):
    """Raised when a baseline scope is not available for a given preset.

    REQ-L3-PC001-002.
    """


class UnknownFeatureKeyError(PresetError):
    """Raised when an unregistered feature key is queried.

    REQ-L3-PC003-001.
    """


class DowngradeBlockedError(PresetError):
    """Raised when a preset downgrade is blocked due to incompatible data.

    REQ-L3-PC003-003 / REQ-L2-PC-011.
    """


class IncompleteProfileError(PresetError):
    """Raised when a terminology profile is missing a mandatory key.

    REQ-L3-PC002-001.
    """


class CustomPresetNotAllowedError(PresetError):
    """Raised when custom preset creation is attempted outside Extended mode.

    REQ-L3-PC001-004.
    """


class CrossTenantWorkspaceError(PresetError):
    """Raised when a workspace is addressed from a foreign tenant context.

    SYSTEMAUDIT-2026-08-27 SA-15 (§4.1 #6): the gate resolves a
    caller-supplied ``workspace_id`` through the ``unscoped`` escape-hatch
    managers, which do not carry the ``TenantManager`` WHERE clause. Without
    this guard a caller authenticated for tenant A could read (and switch)
    tenant B's preset configuration by guessing/leaking a workspace UUID.

    The error deliberately carries no tenant identifiers in its message so it
    cannot be used as a cross-tenant existence oracle.
    """


__all__ = [
    "PresetError",
    "ConfigurationError",
    "ImmutablePresetError",
    "ScopeNotAvailableError",
    "UnknownFeatureKeyError",
    "DowngradeBlockedError",
    "IncompleteProfileError",
    "CustomPresetNotAllowedError",
    "CrossTenantWorkspaceError",
]
