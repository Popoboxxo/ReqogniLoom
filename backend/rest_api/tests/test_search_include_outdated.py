"""REST wiring for ``?include_outdated=`` on ``GET /api/v1/search/`` (P6 / D13).

The service owns the filtering; this module only pins the transport contract:
the flag is parsed (default false, canonical spelling only) and forwarded, and
each serialized hit carries the additive ``status``/``outdated`` fields.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory

from application.search_service import SearchHit, SearchResult
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
                status="outdated",
                outdated=True,
            )
        ],
        total_count=1,
        page=1,
        limit=20,
    )


def _view():
    return SearchViewSet.as_view({"get": "list"})


def test_without_the_flag_the_service_gets_false() -> None:
    workspace_id = str(uuid.uuid4())
    with patch(
        "rest_api.views.SearchService.search", return_value=_result(workspace_id)
    ) as search:
        response = _view()(_request({"q": "Anmeldung", "workspace_id": workspace_id}))

    assert response.status_code == 200
    assert search.call_args.kwargs["include_outdated"] is False


def test_rows_carry_status_and_outdated() -> None:
    workspace_id = str(uuid.uuid4())
    with patch("rest_api.views.SearchService.search", return_value=_result(workspace_id)):
        response = _view()(_request({"q": "Anmeldung", "workspace_id": workspace_id}))

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["status"] == "outdated"
    assert row["outdated"] is True


def test_include_outdated_true_is_forwarded() -> None:
    workspace_id = str(uuid.uuid4())
    with patch(
        "rest_api.views.SearchService.search", return_value=_result(workspace_id)
    ) as search:
        response = _view()(
            _request(
                {
                    "q": "Anmeldung",
                    "workspace_id": workspace_id,
                    "include_outdated": "true",
                }
            )
        )

    assert response.status_code == 200
    assert search.call_args.kwargs["include_outdated"] is True


def test_include_outdated_false_is_forwarded_as_false() -> None:
    workspace_id = str(uuid.uuid4())
    with patch(
        "rest_api.views.SearchService.search", return_value=_result(workspace_id)
    ) as search:
        response = _view()(
            _request(
                {
                    "q": "Anmeldung",
                    "workspace_id": workspace_id,
                    "include_outdated": "false",
                }
            )
        )

    assert response.status_code == 200
    assert search.call_args.kwargs["include_outdated"] is False


def test_include_deleted_true_is_accepted_as_the_shared_alias() -> None:
    workspace_id = str(uuid.uuid4())
    with patch(
        "rest_api.views.SearchService.search", return_value=_result(workspace_id)
    ) as search:
        response = _view()(
            _request(
                {
                    "q": "Anmeldung",
                    "workspace_id": workspace_id,
                    "include_deleted": "true",
                }
            )
        )

    assert response.status_code == 200
    assert search.call_args.kwargs["include_outdated"] is True


@pytest.mark.parametrize("param", ["include_outdated", "include_deleted"])
def test_an_unparseable_include_flag_is_a_validation_error(param: str) -> None:
    """F3: the strict shared validator runs before the lenient parser."""
    workspace_id = str(uuid.uuid4())
    with patch("rest_api.views.SearchService.search") as search:
        response = _view()(
            _request({"q": "Anmeldung", "workspace_id": workspace_id, param: "maybe"})
        )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    search.assert_not_called()
