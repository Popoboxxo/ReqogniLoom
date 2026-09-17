"""ServiceBase._audit records the caller's real actor_type (spec §3)."""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from application.base import ServiceBase
from auth_tenancy.context import AuthContext, AuthMethod


def _ctx(actor_type: str, agent_label: str = "") -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type=actor_type,
        agent_label=agent_label,
    )


def test_human_actor_type_is_user():
    with patch("audit.services.log_write") as log_write:
        ServiceBase._audit(
            ctx=_ctx("user"),
            operation="create",
            entity_type="Requirement",
            entity_id=uuid4(),
        )
    assert log_write.call_args.kwargs["actor_type"] == "user"


def test_agent_actor_type_and_client_name():
    with patch("audit.services.log_write") as log_write:
        ServiceBase._audit(
            ctx=_ctx("agent", "Claude Code"),
            operation="create",
            entity_type="Requirement",
            entity_id=uuid4(),
        )
    kwargs = log_write.call_args.kwargs
    assert kwargs["actor_type"] == "agent"
    assert kwargs["details"]["client_name"] == "Claude Code"


def test_agent_client_name_does_not_clobber_existing_details():
    with patch("audit.services.log_write") as log_write:
        ServiceBase._audit(
            ctx=_ctx("agent", "Claude Code"),
            operation="create",
            entity_type="Requirement",
            entity_id=uuid4(),
            details={"uid": "REQ-1"},
        )
    details = log_write.call_args.kwargs["details"]
    assert details["uid"] == "REQ-1"
    assert details["client_name"] == "Claude Code"
