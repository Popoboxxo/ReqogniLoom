"""Partial-update command for :meth:`RequirementService.update_requirement` (R2C-003).

The public service entry point still accepts the historical keyword arguments
(compatibility wrapper for one release), but the write path itself consumes
this immutable command. Building the command in one place — the REST view
from ``validated_data``, the compatibility wrapper from legacy kwargs — makes
the "only forward a field the caller actually sent" rule explicit and
testable instead of hiding it in a block of view comments.

Every field defaults to :data:`~application.sentinels.UNSET`. ``UNSET`` means
"leave unchanged"; ``None`` is a real value and, for the nullable fields,
means "clear to NULL". The service resolves two field groups with different
rules (see ``RequirementService._apply_requirement_update``): the legacy
``None``-means-unchanged fields treat both ``UNSET`` and ``None`` as
"unchanged", while the nullable SE/hierarchy fields treat only ``UNSET`` as
"unchanged". That distinction is load-bearing partial-PATCH behaviour
(issue #409, ADR-005) and must not be collapsed.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from application.sentinels import UNSET

__all__ = ["RequirementUpdate"]

#: Legacy service parameters whose default ``None`` meant "leave unchanged".
#: The compatibility wrapper turns those defaults into ``UNSET`` so the command
#: it builds is identical to one built from a real "only sent fields" payload.
#: This list deliberately excludes the nullable fields (where ``None`` means
#: "clear to NULL") — collapsing those would break partial PATCH (issue #409).
_NULL_MEANS_UNSET: tuple[str, ...] = (
    "title",
    "description",
    "acceptance_criteria",
    "rationale",
    "source",
    "category",
    "type",
    "change_reason",
    "suspect",
    "allocation_intent",
    "expected_version",
)

#: Serializer fields the REST PATCH path forwards to the service. Deliberately
#: excludes read-only / transport-only keys (``uid``, ``level``, ``version``,
#: ``suspect``, ``acceptance_criteria_items``, ``level_override``,
#: ``workspace_id``, ...) exactly as the old view did. ``expected_version`` is
#: supplied separately by the view's ETag resolution.
_REST_FORWARDED_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "acceptance_criteria",
    "rationale",
    "source",
    "category",
    "type",
    "complexity_fibonacci",
    "verification_method",
    "allocation_intent",
    "change_reason",
    "custom_fields",
    "parent_id",
)


@dataclass(frozen=True)
class RequirementUpdate:
    """Immutable description of a partial Requirement update.

    ``UNSET`` (the default for every field) means the caller omitted the
    field. Any other value — including ``None`` — was explicitly supplied.
    """

    title: object = UNSET
    description: object = UNSET
    acceptance_criteria: object = UNSET
    rationale: object = UNSET
    source: object = UNSET
    category: object = UNSET
    change_reason: object = UNSET
    type: object = UNSET
    complexity_fibonacci: object = UNSET
    verification_method: object = UNSET
    parent_id: object = UNSET
    uid: object = UNSET
    suspect: object = UNSET
    allocation_intent: object = UNSET
    custom_fields: object = UNSET
    expected_version: object = UNSET

    @classmethod
    def from_kwargs(cls, kwargs: Mapping[str, Any]) -> RequirementUpdate:
        """Build a command from the legacy keyword arguments.

        Only keys actually present in *kwargs* are set; everything else stays
        ``UNSET``. Unknown keys are ignored here — the public service method
        keeps its explicit signature, so an unknown keyword still raises
        ``TypeError`` before this factory is ever reached (REQ-143 / ADR-005).
        """
        known = {f.name for f in fields(cls)}
        return cls(**{name: value for name, value in kwargs.items() if name in known})

    @classmethod
    def from_legacy_kwargs(cls, kwargs: Mapping[str, Any]) -> RequirementUpdate:
        """Build a command from the service's historical keyword parameters.

        Unlike :meth:`from_kwargs`, legacy ``None`` defaults for the
        "null means unchanged" fields become ``UNSET``, so an omitted field is
        represented the same way on every call path. Explicit ``None`` for the
        nullable fields is preserved as the "clear to NULL" value.
        """
        values = dict(kwargs)
        for name in _NULL_MEANS_UNSET:
            if values.get(name) is None:
                values[name] = UNSET
        return cls(**values)

    @classmethod
    def from_validated_data(
        cls,
        data: Mapping[str, Any],
        *,
        expected_version: object = UNSET,
    ) -> RequirementUpdate:
        """Build a command from a REST serializer's ``validated_data``.

        This is the single "only forward when present" place that replaces the
        old view-side sentinel block. An absent field stays ``UNSET`` so the
        service leaves it untouched; an explicitly sent ``null`` is forwarded
        as ``None`` and clears the nullable fields.
        """
        values: dict[str, Any] = {
            name: data[name] for name in _REST_FORWARDED_FIELDS if name in data
        }
        values["expected_version"] = expected_version
        return cls(**values)
