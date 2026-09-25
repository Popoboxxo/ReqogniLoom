"""GH-913 — an agent may not approve the artifact it proposed.

Rule 0 (spec §4.3) used to fire only while the item sat in the ``proposed``
state, which left the gate open for good: the transition out of ``proposed``
belongs to the *human* confirmer, and from the next state on the same agent
that authored the proposal could walk its own artifact to ``approved`` (the
release note promise "agent-authored workflow items can never be confirmed by
the same agent" held only for as long as nobody had confirmed anything).

These tests drive the real HTTP + service + DB stack — the exact reproduction
from the issue — and pin the two halves of the contract:

* the agent that proposed the artifact is refused with ``403 PERMISSION_DENIED``
  (not a 500, not a silent 200) on ``-> approved``, and
* a human still approves it normally.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ApiKey, UserRole
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.services import create_default_workflow

_SECRET = "test-secret-not-a-real-key-913"
_PASSWORD = "gh913pass123456"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_AGENT_LABEL = "Hermes QA Bot"


@pytest.fixture
def approval_env(db):
    """Tenant + admin + an Extended workspace wired to a Requirement workflow.

    Extended is the tier from the issue's reproduction: it is the only default
    preset whose graph has the ``in_review -> approved`` gate (and the only one
    that makes ``change_reason`` mandatory), so it is where an agent had a
    second door into self-approval after the human confirmation.
    """
    tenant = Tenant.objects.create(name="GH913 T", slug="gh913-t", is_active=True)
    admin = User.objects.create(
        username="gh913admin", email="gh913admin@t.test", tenant=tenant
    )
    admin.set_password(_PASSWORD)
    admin.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="GH913 WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        plaintext = generate_api_key_plaintext()
        key = ApiKey.objects.create(
            tenant=tenant,
            user=admin,
            name="gh913-bot",
            key_hash=hash_api_key(plaintext),
            principal_type="agent",
            agent_label=_AGENT_LABEL,
            workspace_ids=[str(workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )
    finally:
        clear_request_tenant()

    yield {
        "tenant": tenant,
        "workspace": workspace,
        "admin": admin,
        "key": key,
        "agent_key": plaintext,
    }


def _human_client(env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "gh913admin", "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _agent_client(env: dict) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {env['agent_key']}")
    return client


def _propose(client: APIClient, env: dict, title: str) -> dict[str, Any]:
    """An agent POSTs a Requirement — the engine seeds it into ``proposed``."""
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(env["workspace"].id), "title": title},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _transition(
    client: APIClient, req_id: str, target: str, workspace_id: str
) -> Any:
    return client.post(
        f"/api/v1/requirements/{req_id}/transitions/?workspace_id={workspace_id}",
        {"target_state": target, "change_reason": f"move to {target} (GH-913)"},
        format="json",
    )


def _state(client: APIClient, req_id: str) -> str:
    resp = client.get(f"/api/v1/requirements/{req_id}/transitions/")
    assert resp.status_code == 200, resp.content
    return resp.json()["current_state"]


def _confirm_and_review(
    human: APIClient, req_id: str, workspace_id: str
) -> None:
    """The human half of the flow: leave ``proposed``, then submit for review."""
    resp = _transition(human, req_id, "draft", workspace_id)
    assert resp.status_code == 200, resp.content
    resp = _transition(human, req_id, "in_review", workspace_id)
    assert resp.status_code == 200, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_agent_cannot_self_approve_after_human_confirmation(approval_env):
    """The issue's exact reproduction, ending in 403 instead of a self-approval."""
    agent = _agent_client(approval_env)
    human = _human_client(approval_env)
    req_id = _propose(agent, approval_env, "GH913 self-approval")["id"]

    # (2) the agent's own proposal is already protected in the proposed state
    resp = _transition(agent, req_id, "draft", str(approval_env["workspace"].id))
    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"

    # (3) a human confirms and submits it for review
    _confirm_and_review(human, req_id, str(approval_env["workspace"].id))

    # (4) the agent may still do ordinary work on the artifact
    resp = agent.patch(
        f"/api/v1/requirements/{req_id}/?workspace_id={approval_env['workspace'].id}",
        {
            "description": "Extended tier needs a description to approve.",
            "acceptance_criteria": "Given a confirmed proposal, when the agent "
            "approves, then the request is refused.",
            "change_reason": "fill the approval prerequisites",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.content

    # (5) ... but it must never be the one to approve it
    resp = _transition(agent, req_id, "approved", str(approval_env["workspace"].id))
    assert resp.status_code == 403, resp.content
    body = resp.json()["error"]
    assert body["code"] == "PERMISSION_DENIED"
    assert "may not approve or verify" in body["message"]
    assert "internal error" not in body["message"].lower()

    # the artifact is untouched by the refused attempt
    assert _state(human, req_id) == "in_review"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_human_can_still_approve_an_agent_proposal(approval_env):
    """The guard must not over-block the human flow it exists to protect."""
    agent = _agent_client(approval_env)
    human = _human_client(approval_env)
    req_id = _propose(agent, approval_env, "GH913 human approval")["id"]

    _confirm_and_review(human, req_id, str(approval_env["workspace"].id))

    resp = agent.patch(
        f"/api/v1/requirements/{req_id}/?workspace_id={approval_env['workspace'].id}",
        {
            "description": "Extended tier needs a description to approve.",
            "acceptance_criteria": "Human approval is the intended path.",
            # #272 (spec §7.2): the Extended approval gate now also requires
            # verification_method — without it the human transition below is
            # refused with MANDATORY_FIELDS_MISSING instead of 200.
            "verification_method": "Test",
            "change_reason": "fill the approval prerequisites",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.content

    resp = _transition(human, req_id, "approved", str(approval_env["workspace"].id))
    assert resp.status_code == 200, resp.content
    assert resp.json()["new_state"] == "approved"
