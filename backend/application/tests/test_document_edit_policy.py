"""``resolve_field_permissions`` — the pure R2 field edit policy.

Slice R2 of ``docs/superpowers/plans/2026-11-15-document-view-on-document.md``.
The policy decides, per document field, whether a write would be accepted and —
when it would not — which of the three reasons applies. It has no ORM and no
``ctx``, so every rule is pinned here without a database.

The load-bearing assertions are the *order* of the reasons (permission beats
freeze) and that ``kind`` is never part of the editable set: the reading view
must not offer an affordance the write path would reject, and must not offer one
it should not (classification is not inline-editable content).
"""
from __future__ import annotations

from types import SimpleNamespace

from application.document_edit_policy import (
    CODE_FIELD_FROZEN,
    CODE_PERMISSION,
    CODE_REPO_EXTERNAL,
    EDITABLE_FIELDS_V1,
    FieldPermission,
    resolve_field_permissions,
)

DOCUMENT = SimpleNamespace(owner_mode="loom")


def _resolve(**overrides):
    kwargs = {
        "can_write": True,
        "owner_mode": "loom",
        "frozen_fields": (),
        "allowed_custom_fields": None,
    }
    kwargs.update(overrides)
    return resolve_field_permissions(DOCUMENT, **kwargs)


def _editable(result):
    return {name for name, permission in result.items() if permission.editable}


def _locked_codes(result):
    return {
        name: permission.locked["code"]
        for name, permission in result.items()
        if permission.locked is not None
    }


# ---------------------------------------------------------------------------
# Permission and ownership
# ---------------------------------------------------------------------------


def test_reader_has_no_editable_fields() -> None:
    result = _resolve(can_write=False)

    assert set(result) == set(EDITABLE_FIELDS_V1)
    assert _editable(result) == set()
    assert _locked_codes(result) == {
        name: CODE_PERMISSION for name in EDITABLE_FIELDS_V1
    }


def test_repo_external_is_read_only() -> None:
    result = _resolve(owner_mode="repo_external")

    assert _editable(result) == set()
    assert _locked_codes(result) == {
        name: CODE_REPO_EXTERNAL for name in EDITABLE_FIELDS_V1
    }


# ---------------------------------------------------------------------------
# Freeze
# ---------------------------------------------------------------------------


def test_frozen_fields_are_locked() -> None:
    result = _resolve(frozen_fields=("title", "description", "body"))

    assert _editable(result) == {"doc_date", "custom_fields"}
    assert _locked_codes(result) == {
        "title": CODE_FIELD_FROZEN,
        "description": CODE_FIELD_FROZEN,
        "body": CODE_FIELD_FROZEN,
    }


def test_doc_date_stays_editable_when_frozen() -> None:
    """ADR-026 F-2: the document date is derived metadata, not frozen content."""
    result = _resolve(frozen_fields=("title", "description", "body", "kind"))

    assert result["doc_date"] == FieldPermission(editable=True, locked=None)


# ---------------------------------------------------------------------------
# Custom fields follow the attribute catalog
# ---------------------------------------------------------------------------


def test_custom_fields_follow_attribute_catalog() -> None:
    # Unknown catalog: do not block a write the backend would accept.
    assert _resolve(allowed_custom_fields=None)["custom_fields"].editable is True
    # Known, non-empty catalog: the field is editable.
    assert _resolve(allowed_custom_fields=["team", "owner"])[
        "custom_fields"
    ].editable is True
    # Known, empty catalog: no custom field may be written.
    empty = _resolve(allowed_custom_fields=[])
    assert empty["custom_fields"].editable is False
    assert empty["custom_fields"].locked is not None


# ---------------------------------------------------------------------------
# The editable set itself
# ---------------------------------------------------------------------------


def test_kind_is_not_in_the_editable_set() -> None:
    result = _resolve()

    assert "kind" not in result
    assert set(result) == set(EDITABLE_FIELDS_V1)
    assert "kind" not in _editable(result)


def test_locked_code_order_permission_before_freeze() -> None:
    """A viewer on a released document is denied by permission first."""
    result = _resolve(
        can_write=False,
        frozen_fields=("title", "description", "body"),
    )

    assert _locked_codes(result) == {
        name: CODE_PERMISSION for name in EDITABLE_FIELDS_V1
    }
