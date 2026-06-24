"""
ARCH-L1-006 BaselineService — Domain exceptions.

leaf_id: COMP-BL-001, COMP-BL-002, COMP-BL-003, COMP-BL-004
req_id:  REQ-L2-BL-002, REQ-L2-BL-003, REQ-L2-BL-004, REQ-L2-BL-005, REQ-L2-BL-006, REQ-L2-BL-009

All exception messages are treated as stable interface contracts — callers
match on the message string as specified in the acceptance criteria.
"""
from __future__ import annotations


class BaselineError(Exception):
    """Base class for all BaselineService errors."""


class BaselineImmutableError(BaselineError):
    """Raised when a mutation of an existing Baseline is attempted.

    REQ-L2-BL-002: UPDATE or DELETE of a persisted snapshot raises this.
    Message: "Baselines are immutable"
    """

    def __init__(self, message: str = "Baselines are immutable") -> None:
        super().__init__(message)


class DuplicateBaselineIdError(BaselineError):
    """Raised on INSERT with a baseline_id that already exists.

    REQ-L2-BL-002 acceptance criterion: INSERT with duplicate ID.
    Message: "Duplicate baseline ID"
    """

    def __init__(self, message: str = "Duplicate baseline ID") -> None:
        super().__init__(message)


class DuplicateBaselineNameError(BaselineError):
    """Raised when a name already exists within the same workspace.

    REQ-L2-BL-005: "Baseline name must be unique"
    """

    def __init__(self, message: str = "Baseline name must be unique") -> None:
        super().__init__(message)


class EmptyBaselineNameError(BaselineError):
    """Raised when the supplied name is blank.

    REQ-L2-BL-005: "Baseline name must not be empty"
    """

    def __init__(self, message: str = "Baseline name must not be empty") -> None:
        super().__init__(message)


class BaselineNotFoundError(BaselineError):
    """Raised on get() when the baseline_id does not exist.

    REQ-L2-BL-006: "Baseline not found"
    """

    def __init__(self, message: str = "Baseline not found") -> None:
        super().__init__(message)


class ScopeMismatchError(BaselineError):
    """Raised by DiffEngine when two baselines have different scopes.

    REQ-L2-BL-003: "Cannot diff baselines of different scopes"
    """

    def __init__(
        self, message: str = "Cannot diff baselines of different scopes"
    ) -> None:
        super().__init__(message)


class ScopeNotAllowedError(BaselineError):
    """Raised by DeltaIndexBuilder when the preset blocks the requested scope.

    REQ-L2-BL-004: Minimal / Standard do not allow all scopes.
    """

    def __init__(self, scope: str, preset: str = "") -> None:
        detail = f" for preset '{preset}'" if preset else ""
        super().__init__(
            f"Scope '{scope}' is not available{detail}"
        )


class ItemNotInBaselineError(BaselineError):
    """Raised when get_item_at_baseline is called for an item not in the baseline.

    REQ-L2-BL-009: "Item not part of this baseline"
    """

    def __init__(self, message: str = "Item not part of this baseline") -> None:
        super().__init__(message)


class VersionNotFoundError(BaselineError):
    """Raised when the requested version is not found in the version history.

    REQ-L2-BL-009: "Version not found in history"
    """

    def __init__(self, message: str = "Version not found in history") -> None:
        super().__init__(message)


__all__ = [
    "BaselineError",
    "BaselineImmutableError",
    "DuplicateBaselineIdError",
    "DuplicateBaselineNameError",
    "EmptyBaselineNameError",
    "BaselineNotFoundError",
    "ScopeMismatchError",
    "ScopeNotAllowedError",
    "ItemNotInBaselineError",
    "VersionNotFoundError",
]
