"""GitHub #1081 — auth_tenancy REST adapters must emit the ONE error envelope.

``auth_tenancy`` shipped two local ``_err(code, message, http_status)`` helpers
that answered with the *flat* form::

    {"error": "PERMISSION_DENIED", "message": "..."}

``error`` is a plain string there, so a client branching on
``body.error.code`` — the one shape ``rest_api.serializers.build_error_response``
produces everywhere else — reads ``None`` on exactly these endpoints and
nowhere else in the API. The 403 of
``auth_tenancy.rest_workspace_members`` is the path the issue reported.

This suite pins the canonical shape for both adapters and, separately, that the
language is genuinely threaded from the request so a call site that relies on
the localised registry (instead of the service layer's own text) is correct.
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.errors import PermissionDenied

_MOCK_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_MOCK_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")


def _ctx() -> AuthContext:
    return AuthContext(
        user_id=_MOCK_USER_ID,
        tenant_id=_MOCK_TENANT_ID,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _request(
    method: str = "get", *, accept_language: str = "en", body=None
) -> Request:
    factory = APIRequestFactory()
    raw = getattr(factory, method)(
        f"/api/v1/workspaces/{_WORKSPACE_ID}/members/",
        data=body or {},
        format="json",
        HTTP_ACCEPT_LANGUAGE=accept_language,
    )
    # The views read ``request.data``, so a JSON parser has to be wired for the
    # body-carrying methods (mirrors ``test_item_permission_rest._make_request``).
    request = Request(raw, parsers=[JSONParser()])
    request.auth_context = _ctx()
    request.parser_context = {
        "kwargs": {"workspace_id": str(_WORKSPACE_ID)},
        "args": (),
        "view": None,
    }
    return request


def _assert_canonical(payload: object, *, what: str) -> dict:
    """Assert the single documented envelope and return its inner error dict."""
    assert isinstance(payload, dict), f"{what}: not a JSON object: {payload!r}"
    assert set(payload) == {"error"}, f"{what}: {payload!r}"
    error = payload["error"]
    assert isinstance(error, dict), (
        f"{what}: `error` is {type(error).__name__}, not the nested object — "
        f"this is the flat form #1081 removed: {payload!r}"
    )
    assert set(error) == {"code", "message", "details"}, f"{what}: {error!r}"
    assert isinstance(error["code"], str) and error["code"], f"{what}: {error!r}"
    assert not error["code"].isdigit(), f"{what}: raw HTTP status used as code"
    assert isinstance(error["message"], str) and error["message"], f"{what}: {error!r}"
    assert error["details"] is not None, f"{what}: {error!r}"
    return error


# ---------------------------------------------------------------------------
# rest_workspace_members — the 403 path reported in #1081
# ---------------------------------------------------------------------------


@patch("auth_tenancy.rest_workspace_members.AuthorizationService")
def test_workspace_members_403_uses_the_canonical_envelope(mock_cls):
    mock_cls.return_value.list_workspace_members.side_effect = PermissionDenied()

    from auth_tenancy.rest_workspace_members import WorkspaceMembersView

    view = WorkspaceMembersView()
    view._service = mock_cls.return_value
    response = view.get(_request())

    assert response.status_code == status.HTTP_403_FORBIDDEN
    error = _assert_canonical(response.data, what="members 403")
    assert error["code"] == "PERMISSION_DENIED"
    assert error["message"] == "You are not a member of this workspace."


@patch("auth_tenancy.rest_workspace_members.AuthorizationService")
def test_workspace_members_400_uses_the_canonical_envelope(mock_cls):
    """A malformed workspace_id is a 400 through the same helper."""

    from auth_tenancy.rest_workspace_members import WorkspaceMembersView

    view = WorkspaceMembersView()
    view._service = mock_cls.return_value
    request = _request()
    request.parser_context = {"kwargs": {"workspace_id": "not-a-uuid"}, "args": ()}

    response = view.get(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    error = _assert_canonical(response.data, what="members 400")
    assert error["code"] == "VALIDATION_ERROR"


@patch("auth_tenancy.rest_workspace_members.AuthorizationService")
def test_workspace_members_409_uses_the_canonical_envelope(mock_cls):
    """The last-admin 409 also flows through the same one builder."""

    from auth_tenancy.services.authorization import LastAdminError
    from auth_tenancy.rest_workspace_members import (
        WorkspaceMemberRoleTransitionView,
    )

    mock_cls.return_value.suspend_role.side_effect = LastAdminError(
        "workspace", str(_WORKSPACE_ID)
    )

    view = WorkspaceMemberRoleTransitionView()
    view._service = mock_cls.return_value
    request = _request("post", body={"role": "editor"})
    request.parser_context = {
        "kwargs": {
            "workspace_id": str(_WORKSPACE_ID),
            "user_id": str(_MOCK_USER_ID),
        },
        "args": (),
    }

    response = view.post(request, workspace_id=str(_WORKSPACE_ID), user_id=str(_MOCK_USER_ID))

    assert response.status_code == status.HTTP_409_CONFLICT
    error = _assert_canonical(response.data, what="members 409")
    assert error["code"] == "LAST_ADMIN"


# ---------------------------------------------------------------------------
# rest_item_permission
# ---------------------------------------------------------------------------


@patch("auth_tenancy.rest_item_permission.ItemPermissionService")
def test_item_permission_400_uses_the_canonical_envelope(mock_cls):
    from auth_tenancy.rest_item_permission import ItemPermissionViewSet

    view = ItemPermissionViewSet()
    view._service = mock_cls.return_value
    request = _request("post", body={"user_id": "", "permission_level": "read"})

    response = view.post(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    error = _assert_canonical(response.data, what="permissions 400")
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "Field 'user_id' is required."


@patch("auth_tenancy.rest_item_permission.ItemPermissionService")
def test_item_permission_403_uses_the_canonical_envelope(mock_cls):
    from application.base import PermissionDeniedError
    from auth_tenancy.rest_item_permission import ItemPermissionViewSet

    mock_cls.return_value.grant_permission.side_effect = PermissionDeniedError(
        "not a workspace admin"
    )

    view = ItemPermissionViewSet()
    view._service = mock_cls.return_value
    request = _request(
        "post",
        body={
            "user_id": "00000000-0000-0000-0000-000000000020",
            "permission_level": "read",
        },
    )

    response = view.post(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    error = _assert_canonical(response.data, what="permissions 403")
    assert error["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# The language really comes from the request
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module", "accept_language", "expected_lang_message"),
    [
        (
            "auth_tenancy.rest_workspace_members",
            "en-GB,en;q=0.9",
            "An internal server error occurred.",
        ),
        (
            "auth_tenancy.rest_workspace_members",
            "de-DE,de;q=0.9,en;q=0.5",
            "Ein interner Serverfehler ist aufgetreten.",
        ),
    ],
)
def test_err_helper_threads_accept_language_into_the_registry(
    module, accept_language, expected_lang_message
):
    """``_err`` must derive ``lang`` from the request, not hardcode ``"en"``.

    ``message`` is passed as ``None`` here to exercise the branch where the
    localised registry supplies the text. Every current call site passes the
    service layer's own English string, so this is the only way to prove the
    ``Accept-Language`` header is actually read — a helper that ignored
    ``request`` would still pass every test above.
    """
    import importlib

    _err = importlib.import_module(module)._err

    response = _err(
        _request(accept_language=accept_language),
        "INTERNAL_SERVER_ERROR",
        None,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    error = _assert_canonical(response.data, what=accept_language)
    assert error["code"] == "INTERNAL_SERVER_ERROR"
    assert error["message"] == expected_lang_message
