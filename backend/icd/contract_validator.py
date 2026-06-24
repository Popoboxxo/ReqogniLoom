"""
IcdManagement — ContractValidator (COMP-ICD-002).

leaf_id: COMP-ICD-002
req_id:  REQ-L1-028, REQ-L2-ICD-002, REQ-L2-ICD-003
arch_id: ARCH-L1-014
IF:      IF-ICD-INT-001 (IcdManager -> ContractValidator)

Stateless module that enforces Design-by-Contract rules between two IcdVersion
snapshots. Detects breaking changes according to the Liskov Substitution Principle
covariance/contravariance rules:

  Rule 1 (Contravariance of preconditions):
    Preconditions may only be WEAKENED (removed), never STRENGTHENED (added).
    Adding a new precondition breaks existing callers.

  Rule 2 (Covariance of postconditions):
    Postconditions may only be STRENGTHENED (added), never WEAKENED (removed).
    Removing a postcondition breaks existing consumers.

  Rule 3 (Invariants must be preserved):
    Invariants may not be removed. They represent structural guarantees.

ADR-ICD-01: Validation logic is isolated here so IcdManager stays focused on
versioning/persistence and this logic is independently testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Result types (IF-ICD-INT-001 return contract)
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of a contract compatibility check.

    Attributes:
        is_breaking: True when at least one breaking change was detected.
        breaking_changes: Human-readable descriptions of each breaking change.
        is_valid_syntax: True when the payload passed structural validation.
        syntax_errors: Structural validation errors (only non-empty when
            is_valid_syntax is False).
    """

    is_breaking: bool = False
    breaking_changes: list[str] = field(default_factory=list)
    is_valid_syntax: bool = True
    syntax_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# COMP-ICD-002: ContractValidator
# ---------------------------------------------------------------------------

class ContractValidator:
    """Stateless Design-by-Contract validator for ICD versions.

    leaf_id: COMP-ICD-002
    req_id:  REQ-L2-ICD-002, REQ-L2-ICD-003
    IF:      IF-ICD-INT-001 (called by IcdManager)

    No state is held between calls. All methods are class-level for clarity;
    they may be called on an instance or via the module-level singleton.
    """

    # Required fields for structural validation (REQ-L2-ICD-002)
    _REQUIRED_FIELDS = (
        "direction",
        "interface_type",
        "semantic_description",
        "preconditions",
        "postconditions",
        "invariants",
    )

    def validate_syntax(self, payload: dict[str, Any]) -> ValidationResult:
        """Check that a payload contains all required Design-by-Contract fields.

        Structural validation only — does not compare against any prior version.
        Empty values are allowed; absence of a key is an error.

        Args:
            payload: Raw dict representing the proposed ICD version data.

        Returns:
            ValidationResult with is_valid_syntax=True when all fields present.

        req_id: REQ-L2-ICD-002
        """
        errors: list[str] = []
        for field_name in self._REQUIRED_FIELDS:
            if field_name not in payload:
                errors.append(f"Missing required field: '{field_name}'")

        list_fields = ("preconditions", "postconditions", "invariants")
        for field_name in list_fields:
            value = payload.get(field_name)
            if value is not None and not isinstance(value, list):
                errors.append(
                    f"Field '{field_name}' must be a list, got {type(value).__name__}"
                )

        return ValidationResult(
            is_breaking=False,
            breaking_changes=[],
            is_valid_syntax=len(errors) == 0,
            syntax_errors=errors,
        )

    def validate_contract(
        self,
        old_preconditions: list[str],
        old_postconditions: list[str],
        old_invariants: list[str],
        new_preconditions: list[str],
        new_postconditions: list[str],
        new_invariants: list[str],
    ) -> ValidationResult:
        """Semantically compare two IcdVersion contract snapshots for breaking changes.

        Applies three LSP-derived rules:

        Rule 1 (Contravariance): New preconditions added → breaking.
          Callers are not obligated to satisfy requirements that did not exist.
        Rule 2 (Covariance): Old postconditions removed → breaking.
          Consumers rely on previously-guaranteed postconditions.
        Rule 3 (Invariant preservation): Old invariants removed → breaking.
          Invariants are structural guarantees that must be maintained.

        Args:
            old_preconditions:  Preconditions from the current (old) IcdVersion.
            old_postconditions: Postconditions from the current (old) IcdVersion.
            old_invariants:     Invariants from the current (old) IcdVersion.
            new_preconditions:  Proposed new preconditions.
            new_postconditions: Proposed new postconditions.
            new_invariants:     Proposed new invariants.

        Returns:
            ValidationResult — is_breaking=True and populated breaking_changes when
            any rule is violated.

        req_id: REQ-L2-ICD-003
        IF:     IF-ICD-INT-001
        """
        breaking: list[str] = []

        old_pre_set = set(old_preconditions)
        new_pre_set = set(new_preconditions)
        old_post_set = set(old_postconditions)
        new_post_set = set(new_postconditions)
        old_inv_set = set(old_invariants)
        new_inv_set = set(new_invariants)

        # Rule 1: Preconditions added (strengthened) → breaking
        added_preconditions = new_pre_set - old_pre_set
        for item in sorted(added_preconditions):
            breaking.append(
                f"Precondition added (contravariance violation): '{item}'"
            )

        # Rule 2: Postconditions removed (weakened) → breaking
        removed_postconditions = old_post_set - new_post_set
        for item in sorted(removed_postconditions):
            breaking.append(
                f"Postcondition removed (covariance violation): '{item}'"
            )

        # Rule 3: Invariants removed → breaking
        removed_invariants = old_inv_set - new_inv_set
        for item in sorted(removed_invariants):
            breaking.append(
                f"Invariant removed (invariant preservation violation): '{item}'"
            )

        return ValidationResult(
            is_breaking=len(breaking) > 0,
            breaking_changes=breaking,
            is_valid_syntax=True,
            syntax_errors=[],
        )


# Module-level singleton — IcdManager uses this instance (IF-ICD-INT-001)
_validator = ContractValidator()


def get_validator() -> ContractValidator:
    """Return the module-level ContractValidator singleton.

    leaf_id: COMP-ICD-002
    """
    return _validator


__all__ = [
    "ContractValidator",
    "ValidationResult",
    "get_validator",
]
