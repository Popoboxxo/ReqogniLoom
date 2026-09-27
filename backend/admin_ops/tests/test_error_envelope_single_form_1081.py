"""GitHub #1081 — admin_ops REST adapters must emit the ONE error envelope.

Three admin_ops modules shipped their own flat error body::

    {"error": "PERMISSION_DENIED", "message": "..."}   # rest.py, banner_rest.py
    {"error": "PERMISSION_DENIED", "message": "..."}   # health_rest.py (inline 403)

``error`` is a plain string there, so a client branching on
``body.error.code`` — the one shape ``rest_api.serializers.build_error_response``
produces everywhere else — reads ``None`` on the backup/restore, banner and
health surfaces and nowhere else in the API.

``admin_ops.theme_rest`` was already migrated and is the reference for the
builder + import shape these modules now follow. This suite pins the canonical
shape for all three offenders and, separately, that the language is genuinely
threaded from the request.
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from application.base import NotFoundError, PermissionDeniedError
from auth_tenancy.context import AuthContext, AuthMethod

_MOCK_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_MOCK_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")


def _admin_ctx() -> AuthContext:
    return AuthContext(
        user_id=_MOCK_USER_ID,
        tenant_id=_MOCK_TENANT_ID,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _request(
    method: str,
    url: str,
    *,
    body=None,
    query: str = "",
    accept_language: str = "en",
    kwargs: dict | None = None,
) -> Request:
    full = f"{url}{query}"
    factory = APIRequestFactory()
    if method == "GET":
        raw = factory.get(full, HTTP_ACCEPT_LANGUAGE=accept_language)
    elif method in {"POST", "PUT"}:
        # APIRequestFactory exposes lower-cased verb names only.
        raw = getattr(factory, method.lower())(
            full, data=body or {}, format="json", HTTP_ACCEPT_LANGUAGE=accept_language
        )
    else:  # pragma: no cover - only the methods used here
        raise ValueError(method)

    request = Request(raw, parsers=[JSONParser()])
    request.auth_context = _admin_ctx()
    request.parser_context = {"kwargs": kwargs or {}, "args": (), "view": None}
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
# admin_ops.rest — backup / restore
# ---------------------------------------------------------------------------


def test_backups_bad_filter_400_uses_the_canonical_envelope():
    """A rejected query filter is answered before the service is reached."""
    from admin_ops.rest import BackupListCreateView

    view = BackupListCreateView()
    view._service = None  # never called: validation rejects first

    response = view.get(
        _request("GET", "/api/v1/admin/backups/", query="?status=bogus")
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    error = _assert_canonical(response.data, what="backups list 400")
    assert error["code"] == "VALIDATION_ERROR"
    assert "status" in error["message"]


def test_backups_403_uses_the_canonical_envelope():
    """No auth context at all — the defensive backstop in the view body."""
    from admin_ops.rest import BackupListCreateView

    view = BackupListCreateView()
    view._service = None  # never reached: the backstop answers first

    request = _request("GET", "/api/v1/admin/backups/")
    request.auth_context = None

    response = view.get(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    error = _assert_canonical(response.data, what="backups 403")
    assert error["code"] == "PERMISSION_DENIED"
    assert error["message"] == "Authentication required."


@patch("admin_ops.rest.BackupService")
def test_backups_404_uses_the_canonical_envelope(mock_cls):
    from admin_ops.rest import BackupListCreateView

    mock_cls.return_value.list_backups.side_effect = NotFoundError("No such backup.")

    view = BackupListCreateView()
    view._service = mock_cls.return_value

    response = view.get(_request("GET", "/api/v1/admin/backups/"))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    error = _assert_canonical(response.data, what="backups 404")
    assert error["code"] == "NOT_FOUND"
    assert error["message"] == "No such backup."


@patch("admin_ops.rest.AdminRestoreService")
def test_restore_403_uses_the_canonical_envelope(mock_cls):
    from admin_ops.rest import AdminRestoreView

    mock_cls.return_value.restore.side_effect = PermissionDeniedError(
        "Not allowed to restore."
    )

    view = AdminRestoreView()
    view._service = mock_cls.return_value
    response = view.post(
        _request(
            "POST",
            "/api/v1/admin/restore/",
            body={
                "backup_id": "00000000-0000-0000-0000-000000000099",
                "confirmation_text": "RESTORE",
            },
        )
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    error = _assert_canonical(response.data, what="restore 403")
    assert error["code"] == "PERMISSION_DENIED"
    assert error["message"] == "Not allowed to restore."


# ---------------------------------------------------------------------------
# admin_ops.banner_rest
# ---------------------------------------------------------------------------


@patch("admin_ops.banner_rest.AuthorizationService")
@patch("admin_ops.banner_rest.BannerService")
def test_global_banner_400_uses_the_canonical_envelope(authz_cls, banner_cls):
    from admin_ops.banner_rest import GlobalBannerView

    authz_cls.return_value.is_tenant_admin.return_value = True

    view = GlobalBannerView()
    view._service = banner_cls.return_value
    view._authz = authz_cls.return_value

    response = view.put(
        _request(
            "PUT",
            "/api/v1/admin/banners/global/",
            body={"level": "info", "message": "x", "show_on_login_page": "nope"},
        )
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    error = _assert_canonical(response.data, what="global banner 400")
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "Field 'show_on_login_page' must be a boolean."


@patch("admin_ops.banner_rest.AuthorizationService")
@patch("admin_ops.banner_rest.BannerService")
def test_workspace_banner_400_uses_the_canonical_envelope(authz_cls, banner_cls):
    from admin_ops.banner_rest import WorkspaceBannerView

    authz_cls.return_value.is_tenant_admin.return_value = True

    view = WorkspaceBannerView()
    view._service = banner_cls.return_value
    view._authz = authz_cls.return_value

    response = view.put(
        _request(
            "PUT",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/banner/",
            body={"level": "bogus", "message": "x"},
            kwargs={"workspace_id": str(_WORKSPACE_ID)},
        )
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    error = _assert_canonical(response.data, what="workspace banner 400")
    assert error["code"] == "VALIDATION_ERROR"
    assert "level" in error["message"]


# ---------------------------------------------------------------------------
# admin_ops.health_rest — the inline defensive 403
# ---------------------------------------------------------------------------


def test_health_403_uses_the_canonical_envelope():
    """The defensive backstop, not the RBAC gate.

    ``HasOperationPermission`` normally denies before the view body runs, so
    this path needs an explicit no-auth-context request to reach — which is
    exactly the path that used to answer the flat string form.
    """
    from admin_ops.health_rest import SystemHealthView

    view = SystemHealthView()
    request = _request("GET", "/api/v1/admin/health/")
    request.auth_context = None

    response = view.get(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    error = _assert_canonical(response.data, what="health 403")
    assert error["code"] == "PERMISSION_DENIED"
    assert error["message"] == "Authentication required."


# ---------------------------------------------------------------------------
# The language really comes from the request
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module", ["admin_ops.rest", "admin_ops.banner_rest"]
)
@pytest.mark.parametrize(
    ("accept_language", "expected"),
    [
        ("en-GB,en;q=0.9", "An internal server error occurred."),
        ("de-DE,de;q=0.9,en;q=0.5", "Ein interner Serverfehler ist aufgetreten."),
    ],
)
def test_err_helper_threads_accept_language_into_the_registry(
    module, accept_language, expected
):
    """``_err`` must derive ``lang`` from the request, not hardcode ``"en"``.

    ``message`` is passed as ``None`` to exercise the branch where the
    localised registry supplies the text. Every real call site passes the
    service layer's own English string, so this is the only assertion that
    would notice a helper ignoring ``request``.
    """
    import importlib

    _err = importlib.import_module(module)._err

    response = _err(
        _request("GET", "/api/v1/admin/backups/", accept_language=accept_language),
        "INTERNAL_SERVER_ERROR",
        None,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    error = _assert_canonical(response.data, what=f"{module} {accept_language}")
    assert error["code"] == "INTERNAL_SERVER_ERROR"
    assert error["message"] == expected
