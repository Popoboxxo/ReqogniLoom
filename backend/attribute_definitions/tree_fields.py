"""Tree-display field vocabulary (Issue #1257).

The navigation tree (``shared/WorkspaceTree``) used to render one fixed field
combination per artifact type: the readable ``uid``, the workflow ``status``,
the V-model ``level`` and (in the row's attribute line) ``updated_at`` /
``category``. Issue #1257 makes that combination configurable on three levels
(global → workspace → personal, precedence ``user > workspace > global``) and
per artifact type.

This module is the one authoritative catalogue of the *field keys* such a
configuration may select. It is deliberately Django-free — like
``attribute_definitions.schema`` — so it can be imported by the pure
configuration store, by the REST/MCP serializers and by unit tests without a
configured Django app registry.

Key provenance (issue #1257 point 2 — "keys from the Attribute-v3 catalogue,
do not reinvent")
-----------------------------------------------------------------------------------------
The ``key`` values are the *wire field names* the attribute v3 catalogue and the
artifact list payloads already use (``category``, ``owner``, ``priority``,
``verification_method``, …), so a configuration entry names a field the backend
already knows how to render. Custom (extended) attributes are not enumerated
here — they are workspace-specific and resolved by the caller through
:func:`merge_tree_fields` — but the validator accepts any snake_case key, so a
custom attribute can be configured without a code change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: Ordered width tokens a tree field may carry. ``full`` spans the row, ``half``
#: shares it with a sibling; the vocabulary mirrors the attribute-layout engine's
#: ``ATTRIBUTE_SPANS`` (schema.py) reduced to the two widths a compact tree row
#: can meaningfully express.
TREE_FIELD_WIDTHS: frozenset[str] = frozenset({"full", "half"})

#: Default width of a field whose entry omits one — matches the pre-#1257
#: rendering where every attribute line entry occupied the row.
DEFAULT_TREE_FIELD_WIDTH = "full"

#: A custom-attribute key is a snake_case identifier (same shape the attribute
#: `schema.validate_new_attribute_name` enforces), so a typo or a piece of prose
#: can never be persisted as a field key.
_CUSTOM_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class TreeFieldSpec:
    """Metadata for one built-in tree field.

    Attributes:
        key: Canonical field key (matches the artifact list payload field name
            wherever one exists).
        label_key: i18n key the frontend resolves before falling back to
            ``label``.
        label: English fallback label (the product UI is German; this is the
            untranslated default only).
        width: Default width token (see :data:`TREE_FIELD_WIDTHS`).
        system: ``True`` for a built-in field shipped by the catalogue,
            ``False`` for one merged in from a workspace's attribute
            definition.
    """

    key: str
    label_key: str
    label: str
    width: str
    system: bool = True

    def to_catalog_entry(self) -> dict[str, Any]:
        """Return the JSON-safe catalogue entry for this field."""
        return {
            "key": self.key,
            "label_key": self.label_key,
            "label": self.label,
            "width": self.width,
            "system": self.system,
        }


#: The built-in tree fields, in the order a *default* catalogue presents them.
#: Order here is discovery order only — a stored configuration's own list order
#: is what the tree renders (issue #1257 "inkl. Reihenfolge").
SYSTEM_TREE_FIELDS: tuple[TreeFieldSpec, ...] = (
    TreeFieldSpec("uid", "treeDisplay.field.uid", "ID", "half"),
    TreeFieldSpec("level", "treeDisplay.field.level", "V-Model level", "half"),
    TreeFieldSpec("status", "treeDisplay.field.status", "Status", "half"),
    TreeFieldSpec("updated_at", "treeDisplay.field.updated_at", "Last changed", "half"),
    TreeFieldSpec("category", "treeDisplay.field.category", "Category", "half"),
    TreeFieldSpec("owner", "treeDisplay.field.owner", "Owner", "half"),
    TreeFieldSpec("priority", "treeDisplay.field.priority", "Priority", "half"),
    TreeFieldSpec("version", "treeDisplay.field.version", "Version", "half"),
    TreeFieldSpec(
        "verification_method",
        "treeDisplay.field.verification_method",
        "Verification method",
        "half",
    ),
    TreeFieldSpec(
        "complexity_fibonacci",
        "treeDisplay.field.complexity_fibonacci",
        "Complexity (Fibonacci)",
        "half",
    ),
)

_SYSTEM_BY_KEY: dict[str, TreeFieldSpec] = {spec.key: spec for spec in SYSTEM_TREE_FIELDS}

#: The pre-#1257 fixed combination, in its rendered order. A configuration that
#: is absent on every level resolves to this (issue #1257 point 5 — an existing
#: user's tree does not change). ``uid``/``level``/``status`` are what
#: ``WorkspaceTree``'s own label rendered; ``updated_at`` is the one the
#: artifact row's attribute line carried; ``version`` is what ``<ArtifactRow>``
#: has rendered since ch. 12.4 (from v2 on) — leaving it out of the default
#: would silently drop the version badge from every artifact list, which is
#: exactly the "no visible change" guarantee this tuple exists for.
DEFAULT_TREE_DISPLAY_FIELDS: tuple[str, ...] = (
    "uid",
    "level",
    "status",
    "updated_at",
    "version",
)


class TreeFieldError(ValueError):
    """Raised when a tree-field configuration payload is malformed.

    Subclasses :class:`ValueError` so a caller that only catches the base class
    (the same shape ``AttributeSchemaError`` has) keeps working; the service
    maps it to a 400 / ``VALIDATION_ERROR``.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def system_field_keys() -> tuple[str, ...]:
    """Return every built-in tree field key, in catalogue order."""
    return tuple(spec.key for spec in SYSTEM_TREE_FIELDS)


def is_system_tree_field(key: str) -> bool:
    """Return whether *key* is a built-in tree field."""
    return key in _SYSTEM_BY_KEY


def is_valid_tree_field_key(key: Any, extra_keys: Iterable[str] = ()) -> bool:
    """Return whether *key* names a selectable tree field.

    A system key or an explicitly supplied extra key (a workspace's custom
    attribute names) is valid; anything else must still look like a snake_case
    attribute identifier, so a custom attribute the caller did not enumerate is
    accepted while prose is not.
    """
    if not isinstance(key, str) or not key:
        return False
    if is_system_tree_field(key) or key in set(extra_keys):
        return True
    return bool(_CUSTOM_KEY_RE.match(key))


def field_catalog(extra_keys: Sequence[str] = ()) -> list[dict[str, Any]]:
    """Return the selectable fields as JSON-safe catalogue entries.

    Built-in fields first (catalogue order), then any *extra_keys* not already
    covered (workspace custom attributes), each with ``system: False``. Keys are
    de-duplicated while order is preserved.
    """
    entries = [spec.to_catalog_entry() for spec in SYSTEM_TREE_FIELDS]
    seen = set(_SYSTEM_BY_KEY)
    for key in extra_keys:
        if not isinstance(key, str) or not key or key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "key": key,
                "label_key": f"treeDisplay.field.{key}",
                "label": key,
                "width": DEFAULT_TREE_FIELD_WIDTH,
                "system": False,
            }
        )
    return entries


def merge_tree_fields(
    customization: Any,
    base: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return a stored field selection, or *base*, normalized to full entries.

    A stored configuration is a list of either plain keys (``"status"``) or
    partial entries (``{"key": "status", "width": "half"}``). This shapes either
    into a full ``{"key", "width"}`` list, dropping entries with an unknown
    width or a missing key. It performs no validation (the write path does that);
    it exists so a reader can project a *stored* row without re-validating and
    without raising on a hand-edited row.
    """
    if not isinstance(customization, (list, tuple)):
        return [dict(entry) for entry in base]
    base_by_key = {str(entry.get("key")): entry for entry in base}
    result: list[dict[str, Any]] = []
    for raw in customization:
        if isinstance(raw, str):
            key, width = raw, None
        elif isinstance(raw, Mapping):
            key = raw.get("key")
            width = raw.get("width")
        else:
            continue
        if not isinstance(key, str) or not key:
            continue
        resolved_width = width if width in TREE_FIELD_WIDTHS else None
        if resolved_width is None:
            resolved_width = (
                base_by_key.get(key, {}).get("width") or DEFAULT_TREE_FIELD_WIDTH
            )
        result.append({"key": key, "width": resolved_width})
    return result


def normalize_tree_fields(
    raw: Any, extra_keys: Iterable[str] = ()
) -> list[dict[str, Any]]:
    """Validate and normalize a caller-supplied field list, or raise.

    Accepts the same two entry shapes :func:`merge_tree_fields` reads — a bare
    key string or ``{"key": <str>, "width": "full"|"half"}`` — and returns a
    canonical ``[{"key", "width"}, …]`` list in the caller's order.

    Raises:
        TreeFieldError: *raw* is not a list, an entry is not a string/object, a
            key is empty/unknown/not snake_case, a width is not in
            :data:`TREE_FIELD_WIDTHS`, or a key repeats (a duplicate would render
            the same field twice and make the order ambiguous).
    """
    if not isinstance(raw, (list, tuple)):
        raise TreeFieldError(["tree display fields must be a list"])

    extra = set(extra_keys)
    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, entry in enumerate(raw):
        if isinstance(entry, str):
            key, width = entry, DEFAULT_TREE_FIELD_WIDTH
        elif isinstance(entry, Mapping):
            key = entry.get("key")
            width = entry.get("width", DEFAULT_TREE_FIELD_WIDTH)
        else:
            errors.append(f"fields[{index}] must be a string or an object")
            continue

        if not isinstance(key, str) or not key:
            errors.append(f"fields[{index}].key must be a non-empty string")
            continue
        if not is_valid_tree_field_key(key, extra):
            errors.append(f"fields[{index}]: unknown tree field {key!r}")
            continue
        if key in seen:
            errors.append(f"fields[{index}]: duplicate tree field {key!r}")
            continue
        if not isinstance(width, str) or width not in TREE_FIELD_WIDTHS:
            errors.append(
                f"fields[{index}].width must be one of "
                f"{sorted(TREE_FIELD_WIDTHS)}"
            )
            continue

        seen.add(key)
        normalized.append({"key": key, "width": width})

    if errors:
        raise TreeFieldError(errors)
    return normalized


__all__ = [
    "DEFAULT_TREE_DISPLAY_FIELDS",
    "DEFAULT_TREE_FIELD_WIDTH",
    "SYSTEM_TREE_FIELDS",
    "TREE_FIELD_WIDTHS",
    "TreeFieldError",
    "TreeFieldSpec",
    "field_catalog",
    "is_system_tree_field",
    "is_valid_tree_field_key",
    "merge_tree_fields",
    "normalize_tree_fields",
    "system_field_keys",
]
