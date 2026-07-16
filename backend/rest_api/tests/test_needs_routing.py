"""URL routing tests for StakeholderNeedViewSet (REQ-128).

The DRF router's default pk pattern ([^/.]+) matched custom action segments
such as "derive-requirements" as a pk value, so
GET /api/v1/needs/derive-requirements/ reached retrieve() and 500ed while
parsing the pk as a UUID. Constraining lookup_value_regex to a UUID pattern
makes that path 404 at routing time instead.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.urls import Resolver404, resolve
from rest_framework.test import APIRequestFactory

from rest_api.views import StakeholderNeedViewSet


def test_non_uuid_detail_segment_does_not_resolve() -> None:
    """A non-UUID segment must not match the needs detail route (REQ-128)."""
    with pytest.raises(Resolver404):
        resolve("/api/v1/needs/derive-requirements/")


def test_uuid_detail_segment_resolves_to_viewset() -> None:
    """A valid UUID still resolves to the StakeholderNeedViewSet (REQ-128)."""
    match = resolve("/api/v1/needs/00000000-0000-0000-0000-000000000001/")
    assert match.func.cls.__name__ == "StakeholderNeedViewSet"
    assert match.kwargs["pk"] == "00000000-0000-0000-0000-000000000001"


def _needs_request(method: str = "get", params: dict | None = None):
    from auth_tenancy.context import AuthContext, AuthMethod

    factory = APIRequestFactory()
    req_fn = getattr(factory, method)
    url = "/api/v1/needs/"
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        req = req_fn(f"{url}?{query_string}")
    else:
        req = req_fn(url)
    req.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return req


def test_flat_list_route_with_workspace_id_query_param_returns_200() -> None:
    """Regression (issue #5): GET /api/v1/needs/?workspace_id=... 500ed with
    KeyError('workspace_pk') because list() only read the nested-route kwarg."""
    ws_id = str(uuid.uuid4())
    req = _needs_request(params={"workspace_id": ws_id})
    view = StakeholderNeedViewSet.as_view({"get": "list"})
    with patch(
        "application.stakeholder_need_service.StakeholderNeedService.list_by_workspace",
        return_value=[],
    ):
        response = view(req)
    assert response.status_code == 200


def test_flat_list_route_without_workspace_id_returns_400() -> None:
    req = _needs_request()
    view = StakeholderNeedViewSet.as_view({"get": "list"})
    response = view(req)
    assert response.status_code == 400
