"""Regression test for REST-03: GET /api/v1/search/ without workspace_id.

Before the fix, a missing ``workspace_id`` silently returned an empty result
set with HTTP 200 instead of a 400 validation error, hiding a client-side
mistake (e.g. B009 in the SysEng 2.0 test report).
"""
from __future__ import annotations

import uuid

from rest_framework.test import APIRequestFactory

from rest_api.views import SearchViewSet


def _search_request(params: dict | None = None):
    from auth_tenancy.context import AuthContext, AuthMethod

    factory = APIRequestFactory()
    url = "/api/v1/search/"
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        req = factory.get(f"{url}?{query_string}")
    else:
        req = factory.get(url)
    req.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return req


def test_search_without_workspace_id_returns_400() -> None:
    req = _search_request(params={"q": "foo"})
    view = SearchViewSet.as_view({"get": "list"})
    response = view(req)
    assert response.status_code == 400


def test_search_without_workspace_id_and_without_query_returns_400() -> None:
    req = _search_request()
    view = SearchViewSet.as_view({"get": "list"})
    response = view(req)
    assert response.status_code == 400


def test_search_with_workspace_id_but_empty_query_returns_200_empty_result() -> None:
    """Sanity/no-regression: an empty query with a valid workspace_id is not
    an error — it legitimately yields an empty result set."""
    req = _search_request(params={"workspace_id": str(uuid.uuid4())})
    view = SearchViewSet.as_view({"get": "list"})
    response = view(req)
    assert response.status_code == 200
    assert response.data["results"] == []
