"""GH-1881 — the Issue workflow speaks lowercase snake_case, end to end.

Reproduction from the issue::

    GET /api/v1/issues/{id}/transitions/
    {"current_state": "Open",
     "states": ["Open", "proposed", "In Progress", "Resolved", "Closed",
                "Wontfix", "rejected"]}

``proposed``/``rejected`` are injected by the engine in lowercase, so the graph
carried two vocabularies at once. A client that sent ``in_progress`` — the
spelling every other artifact type accepts — was answered
``400 Transition not allowed: 'Open' → 'in_progress' is not defined``; only the
exact label with a space worked.

These tests drive the real HTTP + service + DB stack (tenant, workspace, Issue
workflow definition, JWT login) and pin the three halves of the contract:

* ``GET .../transitions/`` answers a lowercase-snake vocabulary for every Issue,
* a transition to ``in_progress`` succeeds,
* the old Title-Case label is refused with a clear 400 (never a 500, never a
  silent 200).
"""
from __future__ import annotations

import re

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.services import create_default_workflow

_PASSWORD = "gh1881pass123456"
SNAKE_CASE_STATE = re.compile(r"^[a-z][a-z0-9_]*$")


@pytest.fixture
def issue_env(db):
    """Tenant + admin + a standard workspace wired to the Issue workflow."""
    tenant = Tenant.objects.create(name="GH1881 T", slug="gh1881-t", is_active=True)
    admin = User.objects.create(
        username="gh1881admin", email="gh1881admin@t.test", tenant=tenant
    )
    admin.set_password(_PASSWORD)
    admin.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="GH1881 WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="issue_default",
            item_type="Issue",
            tenant_id=tenant.id,
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "gh1881admin", "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return {"client": client, "workspace": workspace}


def _create_issue(env: dict, title: str = "Login button broken") -> str:
    resp = env["client"].post(
        "/api/v1/issues/",
        {"workspace_id": str(env["workspace"].id), "title": title},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


def _get_transitions(env: dict, issue_id: str) -> dict:
    resp = env["client"].get(f"/api/v1/issues/{issue_id}/transitions/")
    assert resp.status_code == 200, resp.content
    return resp.json()


def _post_transition(env: dict, issue_id: str, target_state: str) -> object:
    return env["client"].post(
        f"/api/v1/issues/{issue_id}/transitions/",
        {"target_state": target_state},
        format="json",
    )


def test_transitions_endpoint_answers_a_lowercase_snake_vocabulary(issue_env) -> None:
    issue_id = _create_issue(issue_env)
    body = _get_transitions(issue_env, issue_id)

    assert body["current_state"] == "open"
    for state in body["states"]:
        assert SNAKE_CASE_STATE.match(state), (
            f"state {state!r} from GET .../transitions/ is not lowercase "
            "snake_case — the Issue graph must not mix vocabularies (GH-1881)"
        )
    # Every target a client may POST is spelled in the same vocabulary.
    for transition in body["allowed_transitions"]:
        assert SNAKE_CASE_STATE.match(transition["target_state"])


def test_transition_to_in_progress_succeeds(issue_env) -> None:
    """The exact request from the issue: ``in_progress`` on a fresh Issue."""
    issue_id = _create_issue(issue_env)
    resp = _post_transition(issue_env, issue_id, "in_progress")

    assert resp.status_code == 200, resp.content
    assert resp.json()["previous_state"] == "open"
    assert resp.json()["new_state"] == "in_progress"
    assert _get_transitions(issue_env, issue_id)["current_state"] == "in_progress"


def test_old_title_case_label_is_refused_with_a_clear_message(issue_env) -> None:
    """``"In Progress"`` must fail *legibly*, not 500 and not pass silently."""
    issue_id = _create_issue(issue_env)
    resp = _post_transition(issue_env, issue_id, "In Progress")

    assert resp.status_code == 400, resp.content
    message = resp.json()["error"]["message"]
    assert "Transition not allowed" in message
    assert "In Progress" in message
    # The item did not move.
    assert _get_transitions(issue_env, issue_id)["current_state"] == "open"


def test_issue_payload_reports_the_lowercase_status(issue_env) -> None:
    """The list/detail projection uses the same engine vocabulary as
    ``transitions/`` — one spelling per artifact, everywhere."""
    issue_id = _create_issue(issue_env)
    resp = issue_env["client"].get(f"/api/v1/issues/{issue_id}/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "open"
