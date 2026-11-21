"""Machine-readable validation errors for multi-artifact interview proposals.

Issue #1990: a proposal returned by ``interview.propose`` used to carry an
LLM-authored shape (top-level ``title``, server-owned fields, links the
workspace's link-type catalog does not allow) that ``interview.formalize``
only rejected much later, inside its write transaction. Callers had to hand-
edit the proposal before it would round-trip.

:class:`ProposalValidationError` keeps the rejection reason machine-readable
via ``code``/``details`` (in addition to a human-readable message) so a UI or
an agent can branch on *why* a proposal was refused instead of parsing prose.
It subclasses :class:`persistence.errors.ValidationError`, so every existing
``except ValidationError`` transport seam keeps working unchanged.
"""
from __future__ import annotations

from typing import Any

from persistence.errors import ValidationError


class ProposalValidationError(ValidationError):
    """A multi-artifact proposal rejected at parse, readout or write time.

    ``code`` is a stable reason token (``RESERVED_FIELD``,
    ``INVALID_LINK_PAIR``, ...). ``details`` carries optional structured
    context such as the offending item index or field name. The message is
    prefixed with ``[code]`` so the reason survives plain string logging.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        item_index: int | None = None,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.item_index = item_index
        self.field = field
        self.details: dict[str, Any] = dict(details or {})
        if item_index is not None:
            self.details["item_index"] = item_index
        if field is not None:
            self.details["field"] = field


__all__ = ["ProposalValidationError"]
