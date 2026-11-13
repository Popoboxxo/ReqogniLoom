"""HTTP boundary for the ADR-028 release cascade.

The service contract is covered in ``application/tests/test_release_service.py``;
these tests pin the transport half: status codes, the standardised error
envelope and the executable change-request reference on a 409.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.urls import resolve
from rest_framework.test import APIRequestFactory

from application.base import (
    PermissionDeniedError,
    ReleaseStateError,
    ReleaseTooLargeError,
    ValidationError,
)
from auth_tenancy.context import AuthContext
from rest_api.release_views import (
    RELEASE_TASK_META_CACHE_PREFIX,
    ElementReleaseImpactView,
    ElementReleaseStatusView,
    ElementReleaseView,
    RequirementReleaseView,
)

pytestmark = pytest.mark.django_db

_ELEMENT_ID = uuid.uuid4()
_REQUIREMENT_ID = uuid.uuid4()
_WORKSPACE_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _clear_task_metadata() -> Iterator[None]:
    """The task-ownership records live in the (process-wide) locmem cache."""
    cache.clear()
    yield
    cache.clear()


def _context(roles: tuple[str, ...] = ("admin",)) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=roles,
        auth_method="test",
        api_key_id=None,
    )


def _request(
    method: str,
    *,
    roles: tuple[str, ...] = ("admin",),
    data=None,
    lang="en",
    ctx: AuthContext | None = None,
):
    factory = APIRequestFactory()
    request = getattr(factory, method)(
        "/", data=data or {}, format="json", HTTP_ACCEPT_LANGUAGE=lang
    )
    request.auth_context = ctx or _context(roles)
    return request


def _own_task(task_id: str, ctx: AuthContext) -> None:
    """Seed the ownership record the status route enforces (ADR-03)."""
    cache.set(
        f"{RELEASE_TASK_META_CACHE_PREFIX}:{task_id}",
        {"element_id": str(_ELEMENT_ID), "tenant_id": str(ctx.tenant_id)},
        60,
    )


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


class TestOversizedReleaseIsQueued:
    """GH-1804: a cascade above the sync ceiling answers 202, not 400."""

    def test_an_oversized_release_is_queued_with_a_status_url(self) -> None:
        ctx = _context(("admin",))
        task = MagicMock()
        task.id = "task-abc"

        with (
            patch(
                "rest_api.release_views.ReleaseService.release_element",
                side_effect=ReleaseTooLargeError(
                    6000, 5000, workspace_id=_WORKSPACE_ID
                ),
            ),
            patch(
                "application.tasks.release_element_async.delay", return_value=task
            ) as delay,
        ):
            response = ElementReleaseView.as_view()(
                _request("post", data={"change_reason": "Milestone M1"}, ctx=ctx),
                element_id=_ELEMENT_ID,
            )

        assert response.status_code == 202
        assert response.data["task_id"] == "task-abc"
        assert response.data["status"] == "queued"
        assert response.data["status_url"] == (
            f"/api/v1/architecture/{_ELEMENT_ID}/release-status/task-abc/"
        )

        # Only ids cross the queue boundary — never the context object.
        assert delay.call_args.args == (
            str(ctx.tenant_id),
            str(_WORKSPACE_ID),
            str(_ELEMENT_ID),
            str(ctx.user_id),
            "Milestone M1",
        )
        assert delay.call_args.kwargs["auth_method"] == "test"

        # The ownership record is what makes the poll route tenant-safe.
        assert cache.get(f"{RELEASE_TASK_META_CACHE_PREFIX}:task-abc") == {
            "element_id": str(_ELEMENT_ID),
            "tenant_id": str(ctx.tenant_id),
        }

    def test_the_queued_status_url_resolves_to_the_poll_route(self) -> None:
        task = MagicMock()
        task.id = "task-abc"

        with (
            patch(
                "rest_api.release_views.ReleaseService.release_element",
                side_effect=ReleaseTooLargeError(
                    6000, 5000, workspace_id=_WORKSPACE_ID
                ),
            ),
            patch(
                "application.tasks.release_element_async.delay", return_value=task
            ),
        ):
            response = ElementReleaseView.as_view()(
                _request("post", data={"change_reason": "Milestone M1"}),
                element_id=_ELEMENT_ID,
            )

        match = resolve(response.data["status_url"])
        assert match.url_name == "api-v1-element-release-status"
        assert match.kwargs["element_id"] == _ELEMENT_ID
        assert match.kwargs["task_id"] == "task-abc"

    def test_a_too_large_release_without_a_workspace_is_not_queued(self) -> None:
        """Defensive: without the workspace the worker cannot resolve roles."""
        with (
            patch(
                "rest_api.release_views.ReleaseService.release_element",
                side_effect=ReleaseTooLargeError(6000, 5000),
            ),
            patch(
                "application.tasks.release_element_async.delay"
            ) as delay,
        ):
            response = ElementReleaseView.as_view()(
                _request("post", data={"change_reason": "Milestone M1"}),
                element_id=_ELEMENT_ID,
            )

        assert response.status_code == 400
        assert response.data["error"]["code"] == "RELEASE_TOO_LARGE"
        delay.assert_not_called()


class TestReleaseStatus:
    """GH-1804: polling is tenant- and element-scoped (ADR-03)."""

    def test_an_own_task_reports_success_with_the_result(self) -> None:
        ctx = _context()
        _own_task("task-1", ctx)

        with patch(
            "rest_api.release_views.task_state",
            return_value=("SUCCESS", {"elements_released": 2}, None),
        ):
            response = ElementReleaseStatusView.as_view()(
                _request("get", ctx=ctx), element_id=_ELEMENT_ID, task_id="task-1"
            )

        assert response.status_code == 200
        assert response.data == {
            "task_id": "task-1",
            "state": "SUCCESS",
            "result": {"elements_released": 2},
        }

    def test_an_own_task_reports_failure_with_the_error(self) -> None:
        ctx = _context()
        _own_task("task-1", ctx)

        with patch(
            "rest_api.release_views.task_state",
            return_value=("FAILURE", None, "element is in state 'draft'"),
        ):
            response = ElementReleaseStatusView.as_view()(
                _request("get", ctx=ctx), element_id=_ELEMENT_ID, task_id="task-1"
            )

        assert response.status_code == 200
        assert response.data["state"] == "FAILURE"
        assert response.data["error"] == "element is in state 'draft'"
        assert "result" not in response.data

    def test_a_pending_task_carries_no_result(self) -> None:
        ctx = _context()
        _own_task("task-1", ctx)

        with patch(
            "rest_api.release_views.task_state", return_value=("PENDING", None, None)
        ):
            response = ElementReleaseStatusView.as_view()(
                _request("get", ctx=ctx), element_id=_ELEMENT_ID, task_id="task-1"
            )

        assert response.data == {"task_id": "task-1", "state": "PENDING"}

    def test_an_unknown_task_is_a_404(self) -> None:
        response = ElementReleaseStatusView.as_view()(
            _request("get"), element_id=_ELEMENT_ID, task_id="never-issued"
        )

        assert response.status_code == 404
        assert response.data["error"]["code"] == "NOT_FOUND"

    def test_another_tenants_task_is_a_404(self) -> None:
        _own_task("task-1", _context())  # owned by a different tenant

        response = ElementReleaseStatusView.as_view()(
            _request("get"), element_id=_ELEMENT_ID, task_id="task-1"
        )

        assert response.status_code == 404

    def test_another_elements_task_is_a_404(self) -> None:
        ctx = _context()
        _own_task("task-1", ctx)

        response = ElementReleaseStatusView.as_view()(
            _request("get", ctx=ctx),
            element_id=uuid.uuid4(),
            task_id="task-1",
        )

        assert response.status_code == 404

    def test_an_unknown_task_never_reaches_the_result_backend(self) -> None:
        """A foreign task id must not even be *looked up* (tenant-blind backend)."""
        with patch("rest_api.release_views.task_state") as state:
            response = ElementReleaseStatusView.as_view()(
                _request("get"), element_id=_ELEMENT_ID, task_id="task-1"
            )

        assert response.status_code == 404
        state.assert_not_called()


@pytest.mark.parametrize(
    ("celery_state", "expected"),
    [
        ("SUCCESS", "SUCCESS"),
        ("FAILURE", "FAILURE"),
        ("STARTED", "STARTED"),
        ("RETRY", "STARTED"),
        ("PENDING", "PENDING"),
        ("REVOKED", "PENDING"),
    ],
)
def test_task_state_normalises_the_celery_states(
    celery_state: str, expected: str
) -> None:
    """The published enum is four states; Celery has more (and invents more)."""
    from rest_api.release_views import task_state

    with patch("celery.result.AsyncResult") as async_result:
        async_result.return_value.state = celery_state
        async_result.return_value.result = "payload"

        state, result, error = task_state("task-1")

    assert state == expected
    if expected == "SUCCESS":
        assert result == "payload"
    elif expected == "FAILURE":
        assert error == "payload"
    else:
        assert (result, error) == (None, None)


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
