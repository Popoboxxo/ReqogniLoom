"""Password policy on user-driven write paths (N21, beta.29 C2-T4).

Before this change :class:`~auth_tenancy.services.user_account.UserAccountService`
enforced only a minimum length, and the MCP admin tool did the same: Django's
configured ``AUTH_PASSWORD_VALIDATORS`` (similarity, minimum length, common
password, numeric) were never consulted on any user-driven creation path.

The operator paths (``provision_admin`` / ``bootstrap_admin`` / ``self_init`` /
``seed_demo``) are the documented exception — their password comes out of band
from ``SYSTEM_ADMIN_PASSWORD`` and must keep working for disaster recovery
(covered by ``test_bootstrap_admin.py``).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from unittest.mock import MagicMock

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.services.password_policy import (
    PasswordPolicyError,
    validate_new_password,
)
from auth_tenancy.services.user_account import UserAccountService
from persistence.models import Tenant


@pytest.mark.parametrize(
    ("password", "reason_fragment"),
    [
        ("password123", "too common"),
        ("12345678901", "numeric"),
        ("new-user-4711", "too similar"),
        ("short7!", "at least 8"),
    ],
)
def test_validate_new_password_rejects_weak_candidates(
    password, reason_fragment
):
    with pytest.raises(PasswordPolicyError) as excinfo:
        validate_new_password(password, username="new-user-4711", email="nu@t.test")

    joined = " ".join(excinfo.value.messages).lower()
    assert reason_fragment in joined, excinfo.value.messages
    # The rejection never echoes the submitted secret.
    assert password not in joined


def test_validate_new_password_accepts_a_strong_candidate():
    validate_new_password(
        "A-real-Passphrase-2026", username="new-user", email="nu@t.test"
    )


def test_policy_error_is_a_value_error_for_existing_mappings():
    """REST/MCP both map ``ValueError`` → 400/VALIDATION_ERROR."""
    assert issubclass(PasswordPolicyError, ValueError)


@pytest.mark.django_db
def test_user_account_create_applies_the_policy():
    tenant = Tenant.objects.create(name="PW-Policy", slug="pw-policy")
    service = UserAccountService()

    with pytest.raises(PasswordPolicyError) as excinfo:
        service.create(
            actor_is_tenant_admin=True,
            tenant_id=tenant.id,
            username="policy-user",
            email="policy-user@t.test",
            password="12345678901",
        )
    assert any("numeric" in message.lower() for message in excinfo.value.messages)


@pytest.mark.django_db
def test_user_account_create_accepts_a_strong_password(tenant_a):
    user = UserAccountService().create(
        actor_is_tenant_admin=True,
        tenant_id=tenant_a.id,
        username="strong-user",
        email="strong-user@a.test",
        password="A-real-Passphrase-2026",
    )
    assert user.check_password("A-real-Passphrase-2026") is True


def test_mcp_user_create_reports_the_policy_failure_on_the_password_field():
    """The MCP tool answers a structured field error, not a bare sentence."""
    from mcp_server.tools.users import UsersToolGroup

    authz = MagicMock()
    authz.is_tenant_admin.return_value = True
    accounts = MagicMock()
    accounts.create.side_effect = PasswordPolicyError(
        ["This password is too common."], 
    )
    group = UsersToolGroup(authz_service=authz)
    group._accounts = accounts

    ctx = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    result = group.execute_tool(
        tool_name="user.create",
        params={
            "username": "newbie",
            "email": "newbie@t.test",
            "password": "password123",
        },
        auth_context=ctx,
        api_key="reqlo_test_key_placeholder",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.details == {
        "field": "password",
        "errors": ["This password is too common."],
    }
