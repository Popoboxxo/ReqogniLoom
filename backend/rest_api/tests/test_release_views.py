"""HTTP boundary for the ADR-028 release cascade.

The service contract is covered in ``application/tests/test_release_service.py``;
these tests pin the transport half: status codes, the standardised error
envelope and the executable change-request reference on a 409.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from application.base import PermissionDeniedError, ReleaseStateError, ValidationError
from auth_tenancy.context import AuthContext
from rest_api.release_views import (
    ElementReleaseImpactView,
    ElementReleaseView,
    RequirementReleaseView,
)

pytestmark = pytest.mark.django_db

_ELEMENT_ID = uuid.uuid4()
_REQUIREMENT_ID = uuid.uuid4()


def _context(roles: tuple[str, ...] = ("admin",)) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=roles,
        auth_method="test",
        api_key_id=None,
    )


def _request(method: str, *, roles: tuple[str, ...] = ("admin",), data=None, lang="en"):
    factory = APIRequestFactory()
    request = getattr(factory, method)(
        "/", data=data or {}, format="json", HTTP_ACCEPT_LANGUAGE=lang
    )
    request.auth_context = _context(roles)
    return request


def test_impact_returns_the_service_payload() -> None:
    payload = {
        "element_id": str(_ELEMENT_ID),
        "release_state": "released",
        "allowed_source_states": ["approved", "verified"],
        "descendant_elements": 1,
        "requirements_total": 2,
        "requirements_releasable": 2,
        "requirements_by_state": {"approved": 2},
        "content_freeze": True,
        "async_required": False,
        "conflicts": 0,
    }
    impact = MagicMock()
    impact.to_dict.return_value = payload

    with patch(
        "rest_api.release_views.ReleaseService.impact", return_value=impact
    ):
        response = ElementReleaseImpactView.as_view()(
            _request("get"), element_id=_ELEMENT_ID
        )

    assert response.status_code == 200
    assert response.data == payload


def test_impact_is_reachable_without_any_release_configuration() -> None:
    with patch(
        "rest_api.release_views.ReleaseService.impact",
        side_effect=ValidationError("The workspace defines no release state."),
    ):
        response = ElementReleaseImpactView.as_view()(
            _request("get"), element_id=_ELEMENT_ID
        )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"


def test_release_element_returns_the_cascade_result() -> None:
    payload = {
        "element_id": str(_ELEMENT_ID),
        "release_state": "released",
        "elements_released": 2,
        "requirements_released": 3,
        "content_freeze": True,
    }
    with patch(
        "rest_api.release_views.ReleaseService.release_element", return_value=payload
    ) as service:
        response = ElementReleaseView.as_view()(
            _request("post", data={"change_reason": "Milestone M1"}),
            element_id=_ELEMENT_ID,
        )

    assert response.status_code == 200
    assert response.data == payload
    assert service.call_args.kwargs["change_reason"] == "Milestone M1"
    assert service.call_args.kwargs["element_id"] == _ELEMENT_ID


def test_release_from_a_wrong_state_is_a_409_with_a_change_request_reference() -> None:
    with patch(
        "rest_api.release_views.ReleaseService.release_element",
        side_effect=ReleaseStateError("element is in state 'draft'"),
    ):
        response = ElementReleaseView.as_view()(
            _request("post", data={"change_reason": "Release"}), element_id=_ELEMENT_ID
        )

    assert response.status_code == 409
    error = response.data["error"]
    assert error["code"] == "RELEASE_NOT_ALLOWED"
    (detail,) = error["details"]
    assert detail["required_action"] == "create_change_request"
    assert detail["reason"] == "element is in state 'draft'"
    assert str(_ELEMENT_ID) in detail["change_request_url"]


def test_requirement_release_conflict_points_at_the_requirement() -> None:
    with patch(
        "rest_api.release_views.ReleaseService.release_requirement",
        side_effect=ReleaseStateError("requirement is in state 'draft'"),
    ):
        response = RequirementReleaseView.as_view()(
            _request("post", data={"change_reason": "Release"}), requirement_id=_REQUIREMENT_ID
        )

    assert response.status_code == 409
    (detail,) = response.data["error"]["details"]
    assert detail["field"] == "requirement_id"
    assert str(_REQUIREMENT_ID) in detail["change_request_url"]


def test_the_conflict_message_is_localised() -> None:
    with patch(
        "rest_api.release_views.ReleaseService.release_element",
        side_effect=ReleaseStateError("state conflict"),
    ):
        response = ElementReleaseView.as_view()(
            _request("post", lang="de", data={"change_reason": "Release"}), element_id=_ELEMENT_ID
        )

    assert response.data["error"]["code"] == "RELEASE_NOT_ALLOWED"
    # The headline is localised; the service's precise reason stays in details.
    assert "freigegeben" in response.data["error"]["message"].lower()
    assert response.data["error"]["details"][0]["reason"] == "state conflict"


def test_missing_release_configuration_is_a_400_not_a_409() -> None:
    with patch(
        "rest_api.release_views.ReleaseService.release_element",
        side_effect=ValidationError("no freeze_on_enter state configured"),
    ):
        response = ElementReleaseView.as_view()(
            _request("post", data={"change_reason": "Release"}), element_id=_ELEMENT_ID
        )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"


def test_the_role_denial_surfaces_as_403() -> None:
    with patch(
        "rest_api.release_views.ReleaseService.release_element",
        side_effect=PermissionDeniedError("Releasing requires approver or admin."),
    ):
        response = ElementReleaseView.as_view()(
            _request("post", roles=("viewer",), data={"change_reason": "Release"}), element_id=_ELEMENT_ID
        )

    assert response.status_code == 403
    assert response.data["error"]["code"] == "PERMISSION_DENIED"


def test_requirement_release_returns_the_no_op_result() -> None:
    payload = {
        "requirement_id": str(_REQUIREMENT_ID),
        "release_state": "released",
        "released": False,
        "reason": "already released",
    }
    with patch(
        "rest_api.release_views.ReleaseService.release_requirement", return_value=payload
    ):
        response = RequirementReleaseView.as_view()(
            _request("post", data={"change_reason": "Release"}), requirement_id=_REQUIREMENT_ID
        )

    assert response.status_code == 200
    assert response.data["released"] is False


def test_a_release_without_a_change_reason_is_rejected_before_the_service() -> None:
    with patch(
        "rest_api.release_views.ReleaseService.release_element"
    ) as service:
        response = ElementReleaseView.as_view()(
            _request("post"), element_id=_ELEMENT_ID
        )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert response.data["error"]["details"][0]["field"] == "change_reason"
    service.assert_not_called()
