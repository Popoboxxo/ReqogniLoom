"""Tests for the R2S-003 user query façade (``application.user_query_service``).

The service is a verbatim relocation of the six former MCP-tool read
queries. These tests pin the exact filters, ordering, pagination, DTO shape,
fail-closed semantics and the rollout flag — so a future edit cannot
silently change an MCP ``ToolResult`` payload.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.test import override_settings

from application.user_query_service import (
    UserData,
    UserDoesNotExist,
    UserQueryService,
    legacy_caller_is_superuser,
    legacy_get_user,
    legacy_list_user_rows,
    legacy_member_has_active_role,
    service_backed_queries_enabled,
)
from persistence.models import User


def _user(**overrides: object) -> MagicMock:
    """Build a mock whose attributes mirror ``persistence.models.User``."""
    user = MagicMock()
    user.id = uuid4()
    user.username = "alice"
    user.email = "alice@test.local"
    user.is_active = True
    user.is_staff = False
    user.is_superuser = False
    user.tenant_id = uuid4()
    user.created_at = None
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


# ---------------------------------------------------------------------------
# Flag
# ---------------------------------------------------------------------------


def test_service_backed_queries_enabled_defaults_on() -> None:
    """The migration ships with the service-backed path enabled."""
    assert service_backed_queries_enabled() is True


@override_settings(MCP_SERVICE_BACKED_QUERIES=False)
def test_service_backed_queries_can_be_pinned_off() -> None:
    """Operators/tests can select the relocated legacy path."""
    assert service_backed_queries_enabled() is False


# ---------------------------------------------------------------------------
# Exception identity (NOT_FOUND mapping in the tool must stay byte-identical)
# ---------------------------------------------------------------------------


def test_user_does_not_exist_keeps_orm_exception_identity() -> None:
    """The re-export is the *same* exception class the services raise."""
    assert UserDoesNotExist is User.DoesNotExist


# ---------------------------------------------------------------------------
# caller_is_superuser
# ---------------------------------------------------------------------------


def test_caller_is_superuser_true() -> None:
    caller_id = uuid4()
    with patch("application.user_query_service.User") as mock_user:
        mock_user.objects.filter.return_value.first.return_value = _user(
            is_superuser=True
        )
        assert legacy_caller_is_superuser(caller_id) is True
    mock_user.objects.filter.assert_called_once_with(id=caller_id)


def test_caller_is_superuser_false_for_inactive_superuser_flag() -> None:
    with patch("application.user_query_service.User") as mock_user:
        mock_user.objects.filter.return_value.first.return_value = _user(
            is_superuser=False
        )
        assert legacy_caller_is_superuser(uuid4()) is False


def test_caller_is_superuser_missing_row_is_false() -> None:
    with patch("application.user_query_service.User") as mock_user:
        mock_user.objects.filter.return_value.first.return_value = None
        assert legacy_caller_is_superuser(uuid4()) is False


def test_caller_is_superuser_db_error_fails_closed() -> None:
    with patch("application.user_query_service.User") as mock_user:
        mock_user.objects.filter.side_effect = RuntimeError("db down")
        assert legacy_caller_is_superuser(uuid4()) is False


# ---------------------------------------------------------------------------
# member_has_active_role
# ---------------------------------------------------------------------------


def test_member_has_active_role_exact_filter() -> None:
    user_id, workspace_id = uuid4(), uuid4()
    with patch("application.user_query_service.UserRole") as mock_role:
        mock_role.objects.filter.return_value.exists.return_value = True
        assert legacy_member_has_active_role(user_id, workspace_id) is True
    mock_role.objects.filter.assert_called_once_with(
        user_id=user_id,
        workspace_id=workspace_id,
        suspended_at__isnull=True,
    )


# ---------------------------------------------------------------------------
# get_user / DTO shape
# ---------------------------------------------------------------------------


def test_get_user_returns_exact_dto_and_none_when_absent() -> None:
    user_id = uuid4()
    row = _user(id=user_id, username="bob", is_staff=True)
    with patch("application.user_query_service.User") as mock_user:
        mock_user.objects.filter.return_value.first.return_value = row
        dto = legacy_get_user(user_id)
    mock_user.objects.filter.assert_called_once_with(id=user_id)
    assert isinstance(dto, UserData)
    assert dto.id == user_id
    assert dto.username == "bob"
    assert dto.email == "alice@test.local"
    assert dto.is_active is True
    assert dto.is_staff is True
    assert dto.is_superuser is False
    assert dto.tenant_id == row.tenant_id
    assert dto.created_at is None

    with patch("application.user_query_service.User") as mock_user:
        mock_user.objects.filter.return_value.first.return_value = None
        assert legacy_get_user(user_id) is None


# ---------------------------------------------------------------------------
# list_user_rows — ordering + pagination are wire contract
# ---------------------------------------------------------------------------


def test_list_user_rows_order_and_slice() -> None:
    tenant_id = uuid4()
    a, b = _user(username="alice"), _user(username="bob")
    queryset = MagicMock()
    queryset.order_by.return_value.__getitem__.return_value = [a, b]
    with patch("application.user_query_service.User") as mock_user:
        mock_user.objects.filter.return_value = queryset
        rows = legacy_list_user_rows(
            tenant_id=tenant_id, is_active=None, limit=2
        )
    mock_user.objects.filter.assert_called_once_with(tenant_id=tenant_id)
    queryset.order_by.assert_called_once_with("username")
    queryset.order_by.return_value.__getitem__.assert_called_once_with(slice(None, 2))
    assert [row.username for row in rows] == ["alice", "bob"]
    assert all(isinstance(row, UserData) for row in rows)


def test_list_user_rows_applies_is_active_filter() -> None:
    tenant_id = uuid4()
    base_qs = MagicMock()
    active_qs = MagicMock()
    active_qs.order_by.return_value.__getitem__.return_value = [_user()]
    base_qs.filter.return_value = active_qs
    with patch("application.user_query_service.User") as mock_user:
        mock_user.objects.filter.return_value = base_qs
        rows = legacy_list_user_rows(
            tenant_id=tenant_id, is_active=True, limit=10
        )
    base_qs.filter.assert_called_once_with(is_active=True)
    assert len(rows) == 1
    active_qs.order_by.assert_called_once_with("username")


def test_list_user_rows_propagates_db_error() -> None:
    with patch("application.user_query_service.User") as mock_user:
        mock_user.objects.filter.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            legacy_list_user_rows(
                tenant_id=uuid4(), is_active=None, limit=10
            )


# ---------------------------------------------------------------------------
# Facade delegates to the relocated queries (byte-identical by construction)
# ---------------------------------------------------------------------------


def test_facade_delegates_to_legacy_queries() -> None:
    service = UserQueryService()
    caller_id, user_id, workspace_id, tenant_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    with patch(
        "application.user_query_service.legacy_caller_is_superuser",
        return_value=True,
    ) as caller, patch(
        "application.user_query_service.legacy_member_has_active_role",
        return_value=False,
    ) as member, patch(
        "application.user_query_service.legacy_get_user", return_value=None
    ) as get_user, patch(
        "application.user_query_service.legacy_list_user_rows",
        return_value=[],
    ) as list_rows:
        assert service.caller_is_superuser(caller_id) is True
        assert service.member_has_active_role(user_id, workspace_id) is False
        assert service.get_user(user_id) is None
        assert service.list_user_rows(
            tenant_id=tenant_id, is_active=None, limit=5
        ) == []
    caller.assert_called_once_with(caller_id)
    member.assert_called_once_with(user_id, workspace_id)
    get_user.assert_called_once_with(user_id)
    list_rows.assert_called_once_with(
        tenant_id=tenant_id, is_active=None, limit=5
    )
