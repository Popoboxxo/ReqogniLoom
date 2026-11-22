"""Issue #1970 — free-text fields reject numeric input instead of coercing.

DRF's ``CharField`` silently turns ``title=123`` into ``"123"``. The MCP
``requirement.create`` handler had the same bug via an explicit ``str(title)``.
Both boundaries are now strict; this module pins the REST half at the
serializer and HTTP envelope levels.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework import serializers

from rest_api.serializers_common import SanitizedCharField
from rest_api.serializers_entity import RequirementSerializer, StakeholderNeedSerializer


@pytest.mark.parametrize("value", [123, 12.5, True])
def test_sanitized_char_field_rejects_non_string(value: object) -> None:
    field = SanitizedCharField(max_length=500)
    with pytest.raises(serializers.ValidationError):
        field.run_validation(value)


def test_sanitized_char_field_accepts_string() -> None:
    field = SanitizedCharField(max_length=500)
    assert field.run_validation("A real title") == "A real title"


@pytest.mark.parametrize(
    "serializer_cls",
    [RequirementSerializer, StakeholderNeedSerializer],
)
def test_title_declarations_are_strict(serializer_cls: type) -> None:
    """The two ``title = SanitizedCharField(max_length=500)`` sites at
    serializers_entity.py:159/382 inherit the strict rule from the shared field.
    """
    serializer = serializer_cls(
        data={
            "workspace_id": str(uuid.uuid4()),
            "title": 456,
        }
    )
    assert serializer.is_valid() is False
    assert "title" in serializer.errors
