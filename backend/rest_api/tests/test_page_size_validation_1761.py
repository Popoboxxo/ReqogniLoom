"""Regression tests for issue #1761 — an unusable ``page_size`` must be a 400.

Reported defect (LOW): ``?page_size=0``, a negative value, a non-numeric value
or an empty value was *silently* replaced by the pagination default. The caller
asked for something it did not get and the response (200, a normal first page)
gave no hint that its parameter had been rewritten. A client computing a fetch
loop from the value it sent could not tell the difference from a genuine short
page — the same observability gap #571 fixed for the *upper* clamp.

Fix: ``StandardPagination.get_page_size`` validates an explicitly supplied
value and raises :class:`rest_api.serializers.InvalidPageSize`, which answers
``400 VALIDATION_ERROR`` with a ``page_size`` entry in ``error.details`` (the
envelope every explicit error of this API uses, REQ-071 / REQ-L2-RA-009).

Deliberately unchanged:

* an **absent** parameter still yields the default (25) — nothing about
  ``GET /api/v1/requirements/`` changes for callers that never send it;
* an **over-large** value is still clamped to ``max_page_size`` (#571) — that
  path is a valid request, only its slice size is bounded.

The tests cover three layers: the paginator itself (fast, no DB), a real
ViewSet through DRF dispatch with an ``APIRequestFactory`` request, and the
black-box HTTP transport through JWT auth. The last one includes
``/api/v1/needs/`` on purpose: that view nests ``_paginate`` inside its broad
``except Exception`` guard, so it is the regression test for the
``_service_error_response`` re-raise that keeps the 400 from turning into a
500.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from rest_api.serializers import InvalidPageSize, StandardPagination
from rest_api.views import RequirementViewSet

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Values that are usable as a page size, and the value each must resolve to.
_VALID_PAGE_SIZES = [
    ("1", 1),
    ("25", 25),
    ("100", 100),
    # #571 clamp, unchanged by #1761: a valid but over-large request is
    # bounded, not rejected.
    ("101", 100),
    ("5000", 100),
]

#: Values that cannot be used as a page size. Each must answer 400.
_INVALID_PAGE_SIZES = [
    "0",
    "-1",
    "-100",
    "abc",
    "1.5",
    "",
    "%20%20",
]


def _drf_request(query: str = "") -> Request:
    """A DRF ``Request`` for ``/api/v1/requirements/`` plus *query*."""
    url = f"/api/v1/requirements/{f'?{query}' if query else ''}"
    return Request(APIRequestFactory().get(url))


def _assert_invalid_page_size(exc: InvalidPageSize) -> None:
    """Pin the 400 envelope shape and its field reference."""
    assert exc.status_code == 400
    body: dict[str, Any] = exc.detail
    error = body["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"]
    details = error["details"]
    assert len(details) == 1, details
    assert details[0]["field"] == "page_size"
    assert details[0]["errors"], "the field entry must say what is wrong"
    assert "integer" in details[0]["errors"][0].lower(), details


# ---------------------------------------------------------------------------
# Layer 1 — the paginator itself
# ---------------------------------------------------------------------------


class TestGetPageSize:
    """``StandardPagination.get_page_size`` (issue #1761)."""

    def test_absent_parameter_keeps_the_default(self) -> None:
        """No behaviour change for callers that never send ``page_size``."""
        assert StandardPagination().get_page_size(_drf_request()) == 25

    @pytest.mark.parametrize(("raw", "expected"), _VALID_PAGE_SIZES)
    def test_usable_value_is_applied(self, raw: str, expected: int) -> None:
        paginator = StandardPagination()

        assert paginator.get_page_size(_drf_request(f"page_size={raw}")) == expected
        # The envelope must still report what was actually applied (#571).
        assert paginator._effective_page_size == expected

    @pytest.mark.parametrize("raw", _INVALID_PAGE_SIZES)
    def test_unusable_value_answers_400_instead_of_the_default(
        self, raw: str
    ) -> None:
        with pytest.raises(InvalidPageSize) as excinfo:
            StandardPagination().get_page_size(_drf_request(f"page_size={raw}"))

        _assert_invalid_page_size(excinfo.value)

    def test_invalid_value_does_not_record_an_effective_page_size(self) -> None:
        """A rejected request must not leave a half-resolved size behind."""
        paginator = StandardPagination()

        with pytest.raises(InvalidPageSize):
            paginator.get_page_size(_drf_request("page_size=0"))

        assert not hasattr(paginator, "_effective_page_size")


# ---------------------------------------------------------------------------
# Layer 2 — a real ViewSet through DRF dispatch (APIRequestFactory + auth ctx)
# ---------------------------------------------------------------------------


class _FakeRequirementSerializer:
    """Stand-in for ``RequirementSerializer``: echoes the page, no DB access."""

    def __init__(self, data: Any, many: bool = False) -> None:
        self.data = data


def _view_request(query: str) -> Any:
    """Build an authenticated request for ``RequirementViewSet.list``."""
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.tenancy import TenantContext

    request = APIRequestFactory().get(
        f"/api/v1/requirements/?workspace_id={uuid.uuid4()}&{query}"
    )
    context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    request.auth_context = context
    TenantContext.set_tenant(context.tenant_id)
    return request


class TestPageSizeValidationThroughListView:
    """``GET /api/v1/requirements/?page_size=...`` via the real ViewSet."""

    def _call(self, query: str) -> Any:
        service = MagicMock()
        service.list_requirements.return_value = []
        with (
            patch("rest_api.views.RequirementViewSet._svc", return_value=service),
            patch("rest_api.views.RequirementSerializer", _FakeRequirementSerializer),
        ):
            return RequirementViewSet.as_view({"get": "list"})(_view_request(query))

    def test_zero_page_size_answers_400_with_field_detail(self) -> None:
        response = self._call("page_size=0")

        assert response.status_code == 400, response.data
        body = response.data
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["details"][0]["field"] == "page_size"

    @pytest.mark.parametrize("raw", ["-1", "abc", ""])
    def test_other_unusable_values_answer_400(self, raw: str) -> None:
        response = self._call(f"page_size={raw}")

        assert response.status_code == 400, response.data
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_default_page_size_still_answers_200(self) -> None:
        response = self._call("")

        assert response.status_code == 200, response.data
        assert response.data["page_size"] == 25

    def test_valid_and_clamped_values_still_answer_200(self) -> None:
        valid = self._call("page_size=10")
        clamped = self._call("page_size=5000")

        assert valid.status_code == 200, valid.data
        assert valid.data["page_size"] == 10
        assert clamped.status_code == 200, clamped.data
        assert clamped.data["page_size"] == 100


# ---------------------------------------------------------------------------
# Layer 3 — black-box HTTP through JWT auth (real view, real envelope)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPageSizeValidationOverHttp:
    """The wire contract, through the real auth + exception-handler stack."""

    def test_requirements_zero_page_size_answers_400(self, authed_client, workspace):
        response = authed_client.get(
            f"/api/v1/requirements/?workspace_id={workspace.id}&page_size=0"
        )

        assert response.status_code == 400, response.content
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["details"][0]["field"] == "page_size"

    def test_requirements_absent_page_size_answers_200(
        self, authed_client, workspace
    ):
        response = authed_client.get(
            f"/api/v1/requirements/?workspace_id={workspace.id}"
        )

        assert response.status_code == 200, response.content
        assert response.json()["page_size"] == 25

    def test_needs_zero_page_size_answers_400_not_500(
        self, authed_client, workspace
    ):
        """``StakeholderNeedViewSet.list`` paginates inside its broad
        ``except Exception`` guard. Before the ``_service_error_response``
        re-raise, the 400 would have been rewritten into a 500.
        """
        response = authed_client.get(
            f"/api/v1/needs/?workspace_id={workspace.id}&page_size=0"
        )

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
