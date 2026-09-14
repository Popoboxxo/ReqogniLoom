"""AWMS transform registry — named, testable value transformations (spec §5).

Every transform is a stateless ``value -> TransformOutcome`` function. The
registry is the *only* way a plan names a transformation (``transform:`` /
``value_map``); a plan can never reference arbitrary Python (spec §4 forbids
hooks).

Contract every transform must honour: report ``applied`` / ``skipped`` /
``failed`` — **never silently**. A skipped transform (e.g. ``enum_map`` with no
matching key and no fallback) leaves the target untouched and the run report
names the value that was skipped, so an operator can see the un-mapped residue.

The module is Django-free so a transform can be unit-tested in isolation and
the registry can be extended by Teil B with a plain ``register(...)`` call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable
from uuid import UUID

#: Transform status vocabulary (spec §5): a transform must say which it did.
APPLIED = "applied"
SKIPPED = "skipped"
FAILED = "failed"

_WHITESPACE_RE = re.compile(r"\s+")
_PARAGRAPH_RE = re.compile(r"\n\s*\n")

#: Begründungs-Marker of §5.1's main case. Case-insensitive; the marker itself
#: is removed from the extracted text.
_RATIONALE_MARKERS: tuple[str, ...] = (
    "begründung:",
    "begruendung:",
    "begründung ",
    "rationale:",
    "rationale ",
    "weil ",
)


@dataclass
class TransformContext:
    """Everything a transform may read beyond the value itself.

    ``link_resolver`` is injected by the engine for ``link_derive`` (which needs
    the TraceLink graph). It is ``None`` in a pure unit test — the transform then
    reports ``skipped`` instead of reaching for the ORM.
    """

    options: dict[str, Any] = field(default_factory=dict)
    value_map: dict[str, Any] | None = None
    fallback: Any = None
    link_resolver: Callable[[Any], "TransformOutcome"] | None = None


@dataclass
class TransformOutcome:
    """Result of one transform application."""

    status: str
    value: Any = None
    message: str = ""

    @property
    def applied(self) -> bool:
        return self.status == APPLIED

    @property
    def ok(self) -> bool:
        return self.status in (APPLIED, SKIPPED)


TransformFn = Callable[[Any, TransformContext], TransformOutcome]


class TransformRegistry:
    """A name -> transform mapping with a fail-closed lookup."""

    def __init__(self) -> None:
        self._transforms: dict[str, TransformFn] = {}

    def register(self, name: str, fn: TransformFn) -> None:
        """Register (or replace) a transform by name."""
        if not name or not isinstance(name, str):
            raise ValueError("transform name must be a non-empty string")
        if not callable(fn):
            raise TypeError(f"transform '{name}' must be callable")
        self._transforms[name] = fn

    def get(self, name: str) -> TransformFn:
        """Return the transform, or raise ``KeyError`` for an unknown name."""
        try:
            return self._transforms[name]
        except KeyError as exc:
            raise KeyError(
                f"unknown transform {name!r}; registered: {sorted(self._transforms)}"
            ) from exc

    def names(self) -> frozenset[str]:
        return frozenset(self._transforms)


# ---------------------------------------------------------------------------
# Built-ins (spec §5 table)
# ---------------------------------------------------------------------------


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def identity(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Return the value unchanged (the default)."""
    return TransformOutcome(APPLIED, value)


def trim(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Normalize whitespace: collapse runs and strip the ends."""
    if not isinstance(value, str):
        return TransformOutcome(SKIPPED, value, "not a string")
    cleaned = _WHITESPACE_RE.sub(" ", value).strip()
    if cleaned == value:
        return TransformOutcome(APPLIED, cleaned, "already normalized")
    return TransformOutcome(APPLIED, cleaned)


def enum_map(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Map via ``value_map``, else ``fallback``, else skip (spec §5)."""
    mapping = ctx.value_map or {}
    key = str(value)
    if key in mapping:
        return TransformOutcome(APPLIED, mapping[key], f"mapped {key!r}")
    if ctx.fallback is not None:
        return TransformOutcome(APPLIED, ctx.fallback, f"fallback for {key!r}")
    return TransformOutcome(SKIPPED, value, f"no mapping for {key!r} and no fallback")


def first_paragraph(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Return the first non-empty paragraph."""
    if not isinstance(value, str) or not value.strip():
        return TransformOutcome(SKIPPED, value, "empty text")
    for paragraph in _PARAGRAPH_RE.split(value):
        if paragraph.strip():
            return TransformOutcome(APPLIED, paragraph.strip())
    return TransformOutcome(SKIPPED, value, "no non-empty paragraph")


def extract_rationale(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Extract the rationale section from free text (spec §5.1, main case).

    Recognises the marker vocabulary ("Begründung:", "Rationale:", "weil …")
    case-insensitively. Without a marker the first paragraph is returned and the
    outcome says so — "kein blindes Verschieben" still needs *some* text, and
    the report marks which rows fell back to the heuristic.
    """
    if not isinstance(value, str) or not value.strip():
        return TransformOutcome(SKIPPED, value, "empty text")
    lowered = value.lower()
    for marker in _RATIONALE_MARKERS:
        index = lowered.find(marker)
        if index == -1:
            continue
        extracted = value[index + len(marker):].strip()
        if extracted:
            return TransformOutcome(APPLIED, extracted, f"marker {marker!r}")
    paragraph = first_paragraph(value, ctx)
    if paragraph.applied:
        return TransformOutcome(APPLIED, paragraph.value, "no marker; first paragraph")
    return TransformOutcome(SKIPPED, value, "no rationale marker and no paragraph")


def join_values(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Join a list with ``options.separator`` (default ``", "``)."""
    if not isinstance(value, (list, tuple)):
        return TransformOutcome(FAILED, value, "value is not a list")
    separator = ctx.options.get("separator", ", ")
    if not isinstance(separator, str):
        return TransformOutcome(FAILED, value, "separator must be a string")
    return TransformOutcome(APPLIED, separator.join(str(item) for item in value))


def split_values(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Split a string with ``options.separator`` (default ``","``)."""
    if not isinstance(value, str):
        return TransformOutcome(FAILED, value, "value is not a string")
    separator = ctx.options.get("separator", ",")
    if not isinstance(separator, str) or not separator:
        return TransformOutcome(FAILED, value, "separator must be a non-empty string")
    parts = [part.strip() for part in value.split(separator)]
    return TransformOutcome(APPLIED, [part for part in parts if part])


def to_number(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Convert to int when exact, else float; fail on anything else."""
    if isinstance(value, bool):
        return TransformOutcome(FAILED, value, "bool is not a number")
    if isinstance(value, (int, float)):
        return TransformOutcome(APPLIED, value)
    try:
        text = str(value).strip()
        return TransformOutcome(APPLIED, int(text))
    except (TypeError, ValueError):
        try:
            return TransformOutcome(APPLIED, float(str(value).strip()))
        except (TypeError, ValueError):
            return TransformOutcome(FAILED, value, f"cannot parse {value!r} as number")


def to_enum(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Validate the value against ``options.allowed`` (a list), applying fallback."""
    allowed = ctx.options.get("allowed")
    if allowed is None:
        return TransformOutcome(APPLIED, value, "no allowed list configured")
    if not isinstance(allowed, (list, tuple, set)):
        return TransformOutcome(FAILED, value, "'allowed' must be a list")
    if value in allowed:
        return TransformOutcome(APPLIED, value)
    if ctx.fallback is not None:
        return TransformOutcome(APPLIED, ctx.fallback, f"fallback for {value!r}")
    return TransformOutcome(SKIPPED, value, f"{value!r} not in allowed values")


def to_date(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Normalize an ISO date/date-time string to ``YYYY-MM-DD``."""
    if isinstance(value, datetime):
        return TransformOutcome(APPLIED, value.date().isoformat())
    if isinstance(value, date):
        return TransformOutcome(APPLIED, value.isoformat())
    if not isinstance(value, str) or not value.strip():
        return TransformOutcome(SKIPPED, value, "empty or non-string date")
    text = value.strip()
    try:
        return TransformOutcome(APPLIED, date.fromisoformat(text).isoformat())
    except ValueError:
        pass
    try:
        return TransformOutcome(APPLIED, datetime.fromisoformat(text).date().isoformat())
    except ValueError:
        return TransformOutcome(FAILED, value, f"cannot parse {value!r} as date")


def to_actor(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Normalize a legacy owner/assignee value to actor wire form (spec §8).

    ``Risk.owner``/``Issue.assignee_id``/``ChangeRequest.requestor_id`` and the
    ``created_by_name`` columns are the pre-Actor carriers (matrix §0/§6/§7/§11).
    The write adapter and the DB-free validator both speak the actor value form
    of spec section 4, so a migration plan converts a legacy value here rather
    than handing a raw string/UUID to the FK write.

    Recognised inputs (never touching the ORM — Django-free contract):

    * an already-formed ``{"kind": ...}`` mapping -> returned unchanged;
    * a ``User``/``Actor`` instance (an FK read) -> ``{"kind": "user", "id": pk}``;
    * a UUID (str or :class:`uuid.UUID`) -> ``{"kind": "user", "id": <uuid>}``;
    * anything else non-empty -> ``{"kind": "external", "name": <text>}``.

    A UUID that no longer resolves to a User is *not* decided here: the engine's
    actor resolver falls back to an external actor named after the raw text, so
    a dangling id degrades to a reviewable external placeholder instead of
    aborting the whole migration.
    """
    if value is None:
        return TransformOutcome(SKIPPED, value, "empty actor source")
    if isinstance(value, dict):
        if not value.get("kind"):
            return TransformOutcome(SKIPPED, value, "actor mapping without 'kind'")
        return TransformOutcome(APPLIED, dict(value), "already in actor form")
    # A type model's FK read yields a User (for owner_user) or an Actor (for an
    # actor target); both expose ``pk``.
    pk = getattr(value, "pk", None)
    if pk is not None:
        return TransformOutcome(APPLIED, {"kind": "user", "id": str(pk)}, "instance")
    text = value.strip() if isinstance(value, str) else str(value).strip()
    if not text:
        return TransformOutcome(SKIPPED, value, "empty actor source")
    try:
        UUID(text)
    except (ValueError, AttributeError, TypeError):
        return TransformOutcome(
            APPLIED, {"kind": "external", "name": text}, "external name"
        )
    return TransformOutcome(APPLIED, {"kind": "user", "id": text}, "user id")


def link_derive(value: Any, ctx: TransformContext) -> TransformOutcome:
    """Pull a value over a TraceLink chain (spec §5, ``derive_from_link``).

    The trace traversal is injected as ``ctx.link_resolver`` so the registry
    stays Django-free; without a resolver (pure unit test) the transform reports
    ``skipped`` rather than importing the ORM.
    """
    if ctx.link_resolver is None:
        return TransformOutcome(SKIPPED, value, "no link resolver available")
    return ctx.link_resolver(value)


def build_default_registry() -> TransformRegistry:
    """Return a registry pre-loaded with the spec §5 built-ins."""
    registry = TransformRegistry()
    registry.register("identity", identity)
    registry.register("trim", trim)
    registry.register("enum_map", enum_map)
    registry.register("first_paragraph", first_paragraph)
    registry.register("extract_rationale", extract_rationale)
    registry.register("join", join_values)
    registry.register("split", split_values)
    registry.register("to_number", to_number)
    registry.register("to_enum", to_enum)
    registry.register("to_date", to_date)
    registry.register("to_actor", to_actor)
    registry.register("link_derive", link_derive)
    return registry


#: Process-wide default registry. Teil B may register additional transforms on
#: it (or on a private instance) without touching the engine.
DEFAULT_REGISTRY = build_default_registry()

#: Names the plan validator accepts. Imported by ``migration_plan``; a transform
#: registered later on a private registry is not part of the declarative
#: contract and would be rejected — deliberately, so a plan file cannot name a
#: transform no deployment has.
TRANSFORM_NAMES: frozenset[str] = DEFAULT_REGISTRY.names()


__all__ = [
    "APPLIED",
    "DEFAULT_REGISTRY",
    "FAILED",
    "SKIPPED",
    "TRANSFORM_NAMES",
    "TransformContext",
    "TransformFn",
    "TransformOutcome",
    "TransformRegistry",
    "build_default_registry",
    "enum_map",
    "extract_rationale",
    "first_paragraph",
    "identity",
    "join_values",
    "link_derive",
    "split_values",
    "to_actor",
    "to_date",
    "to_enum",
    "to_number",
    "trim",
]
