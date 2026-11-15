"""Document field edit policy — who may write which field, and why not.

Slice R2 of ``docs/superpowers/plans/2026-11-15-document-view-on-document.md``:
the document reading view reports, per field, whether the caller may write it.
That answer must be **the same truth** the write path enforces, or the surface
would invent an affordance the service then rejects. This module is therefore a
pure function: no ORM access, no ``ctx``, no Django import. The caller resolves
the inputs (write permission, ``owner_mode``, the freeze list, the attribute
catalog) and this module applies the rules in one fixed order.

Rules, in this order (first match wins):

1. ``can_write=False`` -> ``PERMISSION`` (the RBAC matrix or an item-level rule
   denies writes; rights are restricting, never broadening — plan §0).
2. ``owner_mode == "repo_external"`` -> ``REPO_EXTERNAL`` (the content lives in
   an external repository; this server never writes it — ADR-026 ENT-F5).
3. field in ``frozen_fields`` -> ``FIELD_FROZEN`` (ADR-026 F-2: a release freezes
   authored content; ``doc_date`` and ``custom_fields`` stay writable unless
   they are themselves in the freeze list).
4. otherwise -> editable.

``kind`` is **not** part of :data:`EDITABLE_FIELDS_V1`: the kind is the
document's classification, not authored content, and the reading view never
edits it inline (plan O2 = (a)). The generic ``PATCH /documents/{id}/`` path may
still accept ``kind`` before a release; that is an explicit API decision, not an
inline affordance the surface should offer.

``custom_fields`` follows the attribute catalog: when the caller passes
``allowed_custom_fields`` (a sequence, possibly empty), the field is only
editable if that catalog is non-empty; ``None`` means "catalog unknown" and the
field stays editable rather than blocking a write the backend would accept.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CODE_FIELD_FROZEN",
    "CODE_PERMISSION",
    "CODE_REPO_EXTERNAL",
    "EDITABLE_FIELDS_V1",
    "FieldPermission",
    "resolve_field_permissions",
]

#: The document fields the reading view may report as editable, in wire order.
#: ``kind`` is deliberately absent — see the module docstring.
EDITABLE_FIELDS_V1: tuple[str, ...] = (
    "title",
    "description",
    "body",
    "doc_date",
    "custom_fields",
)

CODE_PERMISSION = "PERMISSION"
CODE_REPO_EXTERNAL = "REPO_EXTERNAL"
CODE_FIELD_FROZEN = "FIELD_FROZEN"

_DETAILS: Mapping[str, str] = {
    CODE_PERMISSION: "You do not have write permission for this document.",
    CODE_REPO_EXTERNAL: (
        "This document is owned by an external repository and is read-only here."
    ),
    CODE_FIELD_FROZEN: "This field is frozen by the document's release.",
}

_NO_CUSTOM_FIELDS_DETAIL = (
    "The attribute catalog defines no custom field for this document."
)


@dataclass(frozen=True)
class FieldPermission:
    """One field's write verdict.

    Attributes:
        editable: Whether a write to this field would be accepted.
        locked: ``None`` when editable, otherwise
            ``{"code": "FIELD_FROZEN"|"PERMISSION"|"REPO_EXTERNAL",
            "detail": str}`` — a machine-readable reason plus a human sentence.
    """

    editable: bool
    locked: Mapping[str, Any] | None


def _locked(code: str, detail: str | None = None) -> FieldPermission:
    return FieldPermission(
        editable=False,
        locked={"code": code, "detail": detail or _DETAILS[code]},
    )


def resolve_field_permissions(
    document: Any,
    *,
    can_write: bool,
    owner_mode: str,
    frozen_fields: Sequence[str],
    allowed_custom_fields: Sequence[str] | None,
) -> dict[str, FieldPermission]:
    """Resolve a :class:`FieldPermission` for every field in the policy.

    Pure: the returned mapping depends only on the arguments, so the reading
    surface and any future write caller share one rule and the rule is testable
    without a database.

    Args:
        document: The ``Document`` (or a stand-in exposing ``owner_mode``). Only
            used as a fallback when ``owner_mode`` is empty; no query is made.
        can_write: Whether the caller may write this document at all (RBAC
            matrix **and** item-level rule merged by
            :class:`~application.effective_permission_service.EffectivePermissionService`).
        owner_mode: ``"loom"`` or ``"repo_external"``.
        frozen_fields: Field names the release froze.
        allowed_custom_fields: Keys the attribute catalog allows, or ``None``
            when the catalog is unknown (the field is then not blocked).

    Returns:
        Mapping of field name -> :class:`FieldPermission`, in
        :data:`EDITABLE_FIELDS_V1` order.
    """
    effective_owner_mode = owner_mode or getattr(document, "owner_mode", "loom")
    frozen = {str(name) for name in (frozen_fields or ())}
    allowed = (
        None
        if allowed_custom_fields is None
        else {str(name) for name in allowed_custom_fields}
    )

    permissions: dict[str, FieldPermission] = {}
    for name in EDITABLE_FIELDS_V1:
        if not can_write:
            permissions[name] = _locked(CODE_PERMISSION)
        elif effective_owner_mode == "repo_external":
            permissions[name] = _locked(CODE_REPO_EXTERNAL)
        elif name in frozen:
            permissions[name] = _locked(CODE_FIELD_FROZEN)
        elif name == "custom_fields" and allowed is not None and not allowed:
            permissions[name] = _locked(CODE_PERMISSION, _NO_CUSTOM_FIELDS_DETAIL)
        else:
            permissions[name] = FieldPermission(editable=True, locked=None)
    return permissions
