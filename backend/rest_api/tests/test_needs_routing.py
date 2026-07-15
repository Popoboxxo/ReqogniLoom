"""URL routing tests for StakeholderNeedViewSet (REQ-128).

The DRF router's default pk pattern ([^/.]+) matched custom action segments
such as "derive-requirements" as a pk value, so
GET /api/v1/needs/derive-requirements/ reached retrieve() and 500ed while
parsing the pk as a UUID. Constraining lookup_value_regex to a UUID pattern
makes that path 404 at routing time instead.
"""
from __future__ import annotations

import pytest
from django.urls import Resolver404, resolve


def test_non_uuid_detail_segment_does_not_resolve() -> None:
    """A non-UUID segment must not match the needs detail route (REQ-128)."""
    with pytest.raises(Resolver404):
        resolve("/api/v1/needs/derive-requirements/")


def test_uuid_detail_segment_resolves_to_viewset() -> None:
    """A valid UUID still resolves to the StakeholderNeedViewSet (REQ-128)."""
    match = resolve("/api/v1/needs/00000000-0000-0000-0000-000000000001/")
    assert match.func.cls.__name__ == "StakeholderNeedViewSet"
    assert match.kwargs["pk"] == "00000000-0000-0000-0000-000000000001"
