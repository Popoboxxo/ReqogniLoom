"""REST surface for notifications (Menschen-im-System spec §5)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from rest_api.collaboration_views import NotificationViewSet


def _notification_stub(kind="assigned", read=False):
    stub = MagicMock()
    stub.id = uuid.uuid4()
    stub.pk = stub.id
    stub.kind = kind
    stub.artifact_id = uuid.uuid4()
    stub.message = "you were assigned"
    stub.read = read
    stub.created_at = None
    return stub


@pytest.fixture
def factory():
    return APIRequestFactory()


def _authed(request):
    """Attach a real ``AuthContext`` so DRF's default ``RbacPermission`` passes.

    ``APIRequestFactory`` requests carry no ``auth_context``, and
    ``RbacPermission.has_permission`` reads ``request.auth_context`` during
    ``initial()`` — without it every call below 401s before reaching the
    handler. Same pattern as ``test_comment_endpoints.py``.
    """
    from auth_tenancy.context import AuthContext, AuthMethod

    request.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return request


def test_list_returns_rows_and_the_unread_count(factory):
    request = _authed(factory.get("/api/v1/notifications/"))

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.list_for_user.return_value = [_notification_stub()]
        svc.return_value.unread_count.return_value = 1
        response = NotificationViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert response.data["unread_count"] == 1
    assert response.data["notifications"][0]["kind"] == "assigned"


def test_list_forwards_unread_only_and_limit(factory):
    request = _authed(factory.get("/api/v1/notifications/?unread_only=true&limit=5"))

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.list_for_user.return_value = []
        svc.return_value.unread_count.return_value = 0
        NotificationViewSet.as_view({"get": "list"})(request)

    kwargs = svc.return_value.list_for_user.call_args.kwargs
    assert kwargs["unread_only"] is True
    assert kwargs["limit"] == 5


def test_list_ignores_a_non_numeric_limit(factory):
    request = _authed(factory.get("/api/v1/notifications/?limit=abc"))

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.list_for_user.return_value = []
        svc.return_value.unread_count.return_value = 0
        response = NotificationViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert svc.return_value.list_for_user.call_args.kwargs["limit"] == 50


def test_read_action_marks_one_notification(factory):
    notification_id = uuid.uuid4()
    request = _authed(factory.post(f"/api/v1/notifications/{notification_id}/read/"))

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.mark_read.return_value = _notification_stub(read=True)
        response = NotificationViewSet.as_view({"post": "read"})(request, pk=str(notification_id))

    assert response.status_code == 200
    assert response.data["read"] is True


def test_mark_all_read_returns_the_count(factory):
    request = _authed(factory.post("/api/v1/notifications/mark-all-read/"))

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.mark_all_read.return_value = 4
        response = NotificationViewSet.as_view({"post": "mark_all_read"})(request)

    assert response.status_code == 200
    assert response.data["marked"] == 4
