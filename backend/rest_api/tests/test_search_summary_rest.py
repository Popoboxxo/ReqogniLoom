"""REST wiring for the optional AI summary of ``GET /api/v1/search/`` (#18).

Mirrors the MCP surface: opt-in only, strict boolean, additive fields, a
provider problem degrades instead of failing the search.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory

from application.search_service import SearchHit, SearchResult
from application.search_summary_service import SearchSummary
from rest_api.views import SearchViewSet

pytestmark = pytest.mark.django_db


def _request(params: dict | None = None):
    from auth_tenancy.context import AuthContext, AuthMethod

    factory = APIRequestFactory()
    url = "/api/v1/search/"
    if params:
        query_string = "&".join(f"{key}={value}" for key, value in params.items())
        url = f"{url}?{query_string}"
    request = factory.get(url)
    request.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return request


def _result(workspace_id: str) -> SearchResult:
    return SearchResult(
        results=[
            SearchHit(
                id="00000000-0000-0000-0000-000000000001",
                artifact_type="Requirement",
                title="Anmeldung",
                description="Die Anmeldung nutzt OAuth.",
                relevance_score=0.9,
                workspace_id=workspace_id,
            )
        ],
        total_count=1,
        page=1,
        limit=20,
    )


def _view():
    return SearchViewSet.as_view({"get": "list"})


def test_without_the_flag_the_response_is_unchanged() -> None:
    workspace_id = str(uuid.uuid4())
    with patch("rest_api.views.SearchService.search", return_value=_result(workspace_id)):
        response = _view()(_request({"q": "Anmeldung", "workspace_id": workspace_id}))

    assert response.status_code == 200
    assert "ai_summary" not in response.data
    assert "summary_degraded" not in response.data


def test_include_summary_adds_both_fields() -> None:
    workspace_id = str(uuid.uuid4())
    with patch(
        "rest_api.views.SearchService.search", return_value=_result(workspace_id)
    ), patch(
        "application.search_summary_service.SearchSummaryService.summarize",
        return_value=SearchSummary(
            text="Eine Anforderung betrifft die Anmeldung.",
            degraded=False,
            cache_hit=False,
            hit_count=1,
        ),
    ):
        response = _view()(
            _request(
                {
                    "q": "Anmeldung",
                    "workspace_id": workspace_id,
                    "include_summary": "true",
                }
            )
        )

    assert response.status_code == 200
    assert response.data["ai_summary"] == "Eine Anforderung betrifft die Anmeldung."
    assert response.data["summary_degraded"] is False


def test_a_degraded_summary_keeps_the_search_successful() -> None:
    workspace_id = str(uuid.uuid4())
    with patch(
        "rest_api.views.SearchService.search", return_value=_result(workspace_id)
    ), patch(
        "application.search_summary_service.SearchSummaryService.summarize",
        return_value=SearchSummary(text=None, degraded=True, cache_hit=False, hit_count=1),
    ):
        response = _view()(
            _request(
                {
                    "q": "Anmeldung",
                    "workspace_id": workspace_id,
                    "include_summary": "true",
                }
            )
        )

    assert response.status_code == 200
    assert response.data["ai_summary"] is None
    assert response.data["summary_degraded"] is True
    assert response.data["results"][0]["title"] == "Anmeldung"


def test_a_non_boolean_include_summary_is_a_validation_error() -> None:
    workspace_id = str(uuid.uuid4())
    response = _view()(
        _request(
            {
                "q": "Anmeldung",
                "workspace_id": workspace_id,
                "include_summary": "maybe",
            }
        )
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
