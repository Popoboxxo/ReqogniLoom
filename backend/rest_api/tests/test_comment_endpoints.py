"""REST surface for comments (Menschen-im-System spec §4)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from rest_api.collaboration_views import ArtifactCommentsView, CommentViewSet


def _comment_stub(text="hello"):
    stub = MagicMock()
    stub.id = uuid.uuid4()
    stub.pk = stub.id
    stub.artifact_id = uuid.uuid4()
    stub.author_id = uuid.uuid4()
    stub.author = MagicMock(username="alice")
    stub.text = text
    stub.resolved = False
    stub.resolved_by_id = None
    stub.resolved_by = None
    stub.resolved_at = None
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
    handler. Same pattern as ``test_metrics_views.py`` /
    ``test_diagram_versioning_views.py``.
    """
    from auth_tenancy.context import AuthContext, AuthMethod

    request.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return request


def test_list_comments_returns_serialized_rows(factory):
    artifact_id = uuid.uuid4()
    request = _authed(factory.get(f"/api/v1/artifacts/{artifact_id}/comments/"))

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        svc.return_value.list_for_artifact.return_value = [_comment_stub("hello")]
        response = ArtifactCommentsView.as_view()(request, artifact_id=str(artifact_id))

    assert response.status_code == 200
    assert response.data[0]["text"] == "hello"


def test_list_comments_honours_include_resolved_false(factory):
    artifact_id = uuid.uuid4()
    request = _authed(factory.get(f"/api/v1/artifacts/{artifact_id}/comments/?include_resolved=false"))

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        svc.return_value.list_for_artifact.return_value = []
        ArtifactCommentsView.as_view()(request, artifact_id=str(artifact_id))

    assert svc.return_value.list_for_artifact.call_args.kwargs["include_resolved"] is False


def test_create_comment_returns_201(factory):
    artifact_id = uuid.uuid4()
    request = _authed(
        factory.post(
            f"/api/v1/artifacts/{artifact_id}/comments/", {"text": "hi"}, format="json"
        )
    )

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        svc.return_value.create_comment.return_value = _comment_stub("hi")
        response = ArtifactCommentsView.as_view()(request, artifact_id=str(artifact_id))

    assert response.status_code == 201
    assert response.data["text"] == "hi"


def test_create_comment_rejects_missing_text(factory):
    artifact_id = uuid.uuid4()
    request = _authed(
        factory.post(f"/api/v1/artifacts/{artifact_id}/comments/", {}, format="json")
    )

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ):
        response = ArtifactCommentsView.as_view()(request, artifact_id=str(artifact_id))

    assert response.status_code == 400


def test_resolve_action_returns_the_updated_comment(factory):
    comment_id = uuid.uuid4()
    request = _authed(factory.post(f"/api/v1/comments/{comment_id}/resolve/"))

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        stub = _comment_stub()
        stub.resolved = True
        svc.return_value.resolve_comment.return_value = stub
        response = CommentViewSet.as_view({"post": "resolve"})(request, pk=str(comment_id))

    assert response.status_code == 200
    assert response.data["resolved"] is True


def test_destroy_returns_204(factory):
    comment_id = uuid.uuid4()
    request = _authed(factory.delete(f"/api/v1/comments/{comment_id}/"))

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        svc.return_value.delete_comment.return_value = None
        response = CommentViewSet.as_view({"delete": "destroy"})(request, pk=str(comment_id))

    assert response.status_code == 204


def test_collection_list_returns_405_not_500(factory):
    """``GET /api/v1/comments/`` is router-registered but unimplemented.

    Before the fix it reached ``BaseEntityViewSet.list`` and crashed with an
    HTML 500 (NotImplementedError). It must answer a clean 405 instead.
    """
    request = _authed(factory.get("/api/v1/comments/"))

    response = CommentViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 405
    assert response.data["error"]["code"] == "VALIDATION_ERROR"


def test_collection_create_returns_405_not_500(factory):
    """``POST /api/v1/comments/`` must 405: comments are created per artifact."""
    request = _authed(factory.post("/api/v1/comments/", {"text": "hi"}, format="json"))

    response = CommentViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 405


def test_detail_retrieve_returns_405_not_500(factory):
    """``GET /api/v1/comments/<pk>/`` must 405, not crash the base stub."""
    comment_id = uuid.uuid4()
    request = _authed(factory.get(f"/api/v1/comments/{comment_id}/"))

    response = CommentViewSet.as_view({"get": "retrieve"})(request, pk=str(comment_id))

    assert response.status_code == 405


def test_detail_partial_update_returns_405_not_500(factory):
    """``PATCH /api/v1/comments/<pk>/`` must 405: comments are immutable."""
    comment_id = uuid.uuid4()
    request = _authed(factory.patch(f"/api/v1/comments/{comment_id}/", {}, format="json"))

    response = CommentViewSet.as_view({"patch": "partial_update"})(request, pk=str(comment_id))

    assert response.status_code == 405


def test_module_contains_no_orm_access():
    """rest_api ORM ratchet: views delegate to Layer 2 (ADR-01)."""
    from pathlib import Path

    import rest_api.collaboration_views as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert ".objects." not in source
