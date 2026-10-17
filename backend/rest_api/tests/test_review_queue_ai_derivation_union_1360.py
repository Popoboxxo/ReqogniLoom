"""Issue #1360 (W12c) — the review-queue union covers the AI-derivation types.

What this file verifies (the plan's "Review-Queue-Union, verifiziert"): the
"Review later" outcome promises the derivation shows up under Reviews →
"Nur KI-Vorschläge". That queue is a **live union**
(:class:`application.review_queue_service.ReviewQueueService`): items in front
of a real approval gate *plus* items in the ``proposed`` state — the latter
matched by state name alone, for every workflow-tracked item type. This test
pins that promise for the three derivations whose write seam W12a exposed
(glossary, ADR, risk) and for the requirement decomposition of #1368:

* a proposal persisted through the flows' own write seams
  (``persist_glossary_drafts`` / ``persist_adr_draft`` / ``persist_risk_drafts``
  / ``persist_decomposed_requirements`` — exactly what the UI's Confirm and
  "Review later" call) is returned by
  ``GET /api/v1/workspaces/{id}/reviews/pending/?state=proposed``;
* ``?item_type=`` narrows to the type, proving the rows carry the expected
  workflow item type;
* nothing is dropped silently: all four types are present in one response.

The drafts are handed in directly (no provider call), so this suite is
deterministic regardless of the environment's configured LLM provider.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.context import AuthContext
from auth_tenancy.models import ROLE_EDITOR, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Adr,
    ArchitectureElement,
    Artifact,
    GlossaryTerm,
    Requirement,
    Risk,
    Tenant,
    User,
    Workspace,
)
from workflow.services import create_default_workflow

_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": "test-secret-not-a-real-key-1360",
    "AUTH_JWT_ISSUER": "reqflow",
    "AUTH_JWT_AUDIENCE": "reqflow-api",
    "AUTH_JWT_TTL_SECONDS": 3600,
}

_PASSWORD = "hunter2pass-1360"

pytestmark = pytest.mark.django_db


def _provision(workspace: Workspace, item_type: str) -> None:
    set_request_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="extended",
            item_type=item_type,
            tenant_id=workspace.tenant_id,
        )
    finally:
        clear_request_tenant()


def _make_user(tenant: Tenant, username: str) -> User:
    user = User.objects.create(
        username=username, email=f"{username}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return user


def _login(user: User) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=("editor",),
        auth_method="test",
        tenant_name="queue-union-1360",
    )


@pytest.fixture
def env():
    tenant = Tenant.objects.create(
        name="Queue union tenant", slug=f"qu-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Queue union WS", preset={"name": "extended"}
        )
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
    finally:
        clear_request_tenant()
    for item_type in ("GlossaryTerm", "Adr", "Risk", "Requirement"):
        _provision(workspace, item_type)

    editor = _make_user(tenant, "qu-editor")
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()
    return {"tenant": tenant, "workspace": workspace, "editor": editor}


def _persist_all_four(env) -> dict[str, str]:
    """Run the four write seams the UI's save actions call; return id per type."""
    from application.ai_derivation_service import AiDerivationService

    ctx = _ctx(env["editor"])
    workspace = env["workspace"]
    service = AiDerivationService()
    set_request_tenant(env["tenant"].id)
    try:
        # The source requirement the decomposition derives from.
        from application.requirement_service import RequirementService

        parent = RequirementService().create_requirement(
            workspace_id=workspace.id,
            title="Parent requirement",
            description="Decomposable.",
            ctx=ctx,
        )

        glossary = service.persist_glossary_drafts(
            ctx,
            workspace_id=workspace.id,
            preview={"drafts": [{"term": "Loom", "definition": "A weaving machine."}]},
        )
        adr = service.persist_adr_draft(
            ctx,
            workspace_id=workspace.id,
            preview={"draft": {"title": "Use Postgres", "description": "Decision."}},
        )

        element_artifact = Artifact.objects.create(
            workspace=workspace,
            artifact_type="ArchitectureElement",
            tenant_id=env["tenant"].id,
        )
        element = ArchitectureElement.objects.create(
            artifact=element_artifact, tenant_id=env["tenant"].id, title="Subsystem A"
        )
        risks = service.persist_risk_drafts(
            ctx,
            architecture_element_id=element.id,
            preview={"drafts": [{"title": "Latency risk"}]},
        )
        decomposition = service.persist_decomposed_requirements(
            ctx,
            requirement_id=parent.id,
            drafts=[{"title": "Child one", "description": "", "rationale": ""}],
        )
    finally:
        clear_request_tenant()

    return {
        # Every write seam must have produced a reviewable proposal, or the
        # union assertion below would be vacuous.
        "GlossaryTerm": glossary["written"][0]["id"],
        "Adr": adr["written"]["id"],
        "Risk": risks["written"][0]["id"],
        "Requirement": decomposition["created"][0]["id"],
    }


def _pending_ids(client: APIClient, workspace_id, *, item_type: str | None = None) -> set[str]:
    query = "?state=proposed"
    if item_type:
        query += f"&item_type={item_type}"
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/reviews/pending/{query}")
    assert resp.status_code == 200, resp.content
    return {row["item_id"] for row in resp.json()["results"]}


@override_settings(**_JWT_OVERRIDES)
def test_every_ai_derivation_write_seam_lands_in_the_pending_queue(env):
    created = _persist_all_four(env)
    client = _login(env["editor"])

    ids = _pending_ids(client, env["workspace"].id)

    for item_type, item_id in created.items():
        assert item_id in ids, (
            f"a {item_type} proposal persisted through the derivation write "
            "seam must surface in Reviews → 'Nur KI-Vorschläge' (#1360)"
        )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("item_type", ["GlossaryTerm", "Adr", "Risk", "Requirement"])
def test_item_type_filter_resolves_the_derivation_types(env, item_type):
    created = _persist_all_four(env)
    client = _login(env["editor"])

    ids = _pending_ids(client, env["workspace"].id, item_type=item_type)

    assert created[item_type] in ids


@override_settings(**_JWT_OVERRIDES)
def test_the_proposals_are_really_in_the_proposed_state(env):
    """The union's second set is state-name-based; prove the rows are it."""
    created = _persist_all_four(env)

    set_request_tenant(env["tenant"].id)
    try:
        from workflow import state_reader

        assert state_reader.current_state("GlossaryTerm", created["GlossaryTerm"]) == "proposed"
        assert state_reader.current_state("Adr", created["Adr"]) == "proposed"
        assert state_reader.current_state("Risk", created["Risk"]) == "proposed"
        assert state_reader.current_state("Requirement", created["Requirement"]) == "proposed"

        # …and the rows really exist as their own entity types.
        assert GlossaryTerm.objects.filter(id=created["GlossaryTerm"]).exists()
        assert Adr.objects.filter(id=created["Adr"]).exists()
        assert Risk.objects.filter(id=created["Risk"]).exists()
        assert Requirement.objects.filter(id=created["Requirement"]).exists()
    finally:
        clear_request_tenant()
