"""Plan B / B5-T3 (#378) — REST surface of the quality assessment.

Pins the published contract (201 new / 200 cached, chatty 400/403/404, the spend
throttle) and the security-relevant half: an entity that lives in **another
workspace of the same tenant** is a 404 on both routes, with the provider never
called (KA-B-10 / QR-S08).
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

from application.quality_service import QualityService
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import QualityAssessment, Tenant, User, Workspace
from rest_api.throttling import QualityAssessRateThrottle

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_VERDICT = {
    "score": 0.5,
    "reasoning": "mock reasoning",
    "suggestions": ["tighten the wording"],
    "criteria": {"atomic": 0.5},
}


class _CountingProvider:
    PROVIDER_NAME = "counting"
    MODEL_NAME = "counting-v1"

    def __init__(self, response: str = json.dumps(_VERDICT)) -> None:
        self.response = response
        self.calls: list[str] = []

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.calls.append(prompt)
        return self.response


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="Quality REST", slug=f"quality-rest-{uuid.uuid4().hex[:8]}"
    )


def _workspace(tenant: Tenant, name: str) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(tenant=tenant, name=name, preset={"name": "standard"})
        provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
        return ws
    finally:
        clear_request_tenant()


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return _workspace(tenant, "quality-ws-a")


@pytest.fixture
def other_workspace(tenant: Tenant) -> Workspace:
    return _workspace(tenant, "quality-ws-b")


def _client(tenant: Tenant, workspace: Workspace, role: str) -> APIClient:
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"quality-{role}-{suffix}",
        email=f"quality-{role}-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=role)
    finally:
        clear_request_tenant()
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


@pytest.fixture
def editor_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    return _client(tenant, workspace, ROLE_EDITOR)


@pytest.fixture
def admin_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    return _client(tenant, workspace, ROLE_ADMIN)


@pytest.fixture
def viewer_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    return _client(tenant, workspace, ROLE_VIEWER)


@pytest.fixture
def requirement(tenant: Tenant, workspace: Workspace):
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=(ROLE_EDITOR,),
        auth_method="test",
        api_key_id=None,
    )
    return RequirementService().create_requirement(
        workspace_id=workspace.id, title="The system shall respond", ctx=ctx
    )


@pytest.fixture
def requirement_in_other_workspace(tenant: Tenant, other_workspace: Workspace):
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=(ROLE_EDITOR,),
        auth_method="test",
        api_key_id=None,
    )
    return RequirementService().create_requirement(
        workspace_id=other_workspace.id, title="Belongs to workspace B", ctx=ctx
    )


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> _CountingProvider:
    fake = _CountingProvider()
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: fake)
    return fake


def _assess_url(ws: Workspace) -> str:
    return f"/api/v1/workspaces/{ws.id}/quality/assess/"


def _history_url(ws: Workspace, entity_type: str, entity_id) -> str:
    return f"/api/v1/workspaces/{ws.id}/quality/{entity_type}/{entity_id}/"


def _body(requirement) -> dict:
    return {
        "entity_type": "Requirement",
        "entity_id": str(requirement.id),
    }


def test_assess_answers_201_then_200_cached(
    editor_client: APIClient, workspace, requirement, provider
):
    first = editor_client.post(
        _assess_url(workspace), _body(requirement), format="json"
    )
    assert first.status_code == 201, first.content
    payload = first.json()
    assert set(payload) == {
        "assessment_id",
        "entity_type",
        "entity_id",
        "score",
        "reasoning",
        "suggestions",
        "criteria",
        "prompt_slot",
        "prompt_scope",
        "provider",
        "model",
        "trigger",
        "status",
        "cached",
        "assessed_at",
    }
    assert payload["cached"] is False
    assert payload["score"] == pytest.approx(0.5)

    second = editor_client.post(
        _assess_url(workspace), _body(requirement), format="json"
    )
    assert second.status_code == 200, second.content
    assert second.json()["cached"] is True
    assert second.json()["assessment_id"] == payload["assessment_id"]
    assert len(provider.calls) == 1


def test_assess_unassessable_type_is_400(
    editor_client: APIClient, workspace, requirement
):
    response = editor_client.post(
        _assess_url(workspace),
        {"entity_type": "ArchitectureElement", "entity_id": str(requirement.id)},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_assess_malformed_entity_id_is_400(editor_client: APIClient, workspace):
    response = editor_client.post(
        _assess_url(workspace),
        {"entity_type": "Requirement", "entity_id": "not-a-uuid"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_assess_unknown_entity_is_404(
    editor_client: APIClient, workspace, provider
):
    response = editor_client.post(
        _assess_url(workspace),
        {"entity_type": "Requirement", "entity_id": str(uuid.uuid4())},
        format="json",
    )
    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert provider.calls == []


def test_assess_entity_of_other_workspace_is_404(
    editor_client: APIClient,
    workspace,
    requirement_in_other_workspace,
    provider,
):
    """Workspace A is addressed, the entity lives in workspace B — same tenant."""
    response = editor_client.post(
        _assess_url(workspace),
        {
            "entity_type": "Requirement",
            "entity_id": str(requirement_in_other_workspace.id),
        },
        format="json",
    )
    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert provider.calls == [], "a foreign-workspace entity must never reach the LLM"
    assert QualityAssessment.unscoped.count() == 0


def test_history_entity_of_other_workspace_is_404(
    editor_client: APIClient,
    workspace,
    requirement_in_other_workspace,
    provider,
):
    response = editor_client.get(
        _history_url(workspace, "Requirement", requirement_in_other_workspace.id)
    )
    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert provider.calls == []


def test_history_returns_assessments_and_latest(
    editor_client: APIClient, workspace, requirement, provider
):
    editor_client.post(_assess_url(workspace), _body(requirement), format="json")

    response = editor_client.get(
        _history_url(workspace, "Requirement", requirement.id)
    )
    assert response.status_code == 200, response.content
    payload = response.json()
    assert set(payload) == {"assessments", "count", "latest"}
    assert payload["count"] == len(payload["assessments"])
    assert payload["count"] >= 1
    assert payload["latest"]["assessment_id"] == payload["assessments"][0][
        "assessment_id"
    ]


def test_history_empty_is_200_with_null_latest(
    editor_client: APIClient, workspace, requirement
):
    response = editor_client.get(
        _history_url(workspace, "Requirement", requirement.id)
    )
    assert response.status_code == 200, response.content
    assert response.json() == {"assessments": [], "count": 0, "latest": None}


def test_history_limit_is_validated(editor_client: APIClient, workspace, requirement):
    response = editor_client.get(
        _history_url(workspace, "Requirement", requirement.id), {"limit": "0"}
    )
    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_assess_as_viewer_is_403(viewer_client: APIClient, workspace, requirement):
    response = viewer_client.post(
        _assess_url(workspace), _body(requirement), format="json"
    )
    assert response.status_code == 403, response.content
    assert QualityAssessment.unscoped.count() == 0


def test_history_as_viewer_is_allowed(
    viewer_client: APIClient, workspace, requirement
):
    response = viewer_client.get(
        _history_url(workspace, "Requirement", requirement.id)
    )
    assert response.status_code == 200, response.content


def _rest_framework_with_quality_rate(rate: str) -> dict:
    current = dict(settings.REST_FRAMEWORK)
    current["DEFAULT_THROTTLE_RATES"] = {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        "quality_assess": rate,
    }
    return current


def test_assess_is_throttled(
    editor_client: APIClient, workspace, requirement, provider
):
    with override_settings(REST_FRAMEWORK=_rest_framework_with_quality_rate("1/hour")):
        first = editor_client.post(
            _assess_url(workspace), _body(requirement), format="json"
        )
        assert first.status_code == 201, first.content
        second = editor_client.post(
            _assess_url(workspace), _body(requirement), format="json"
        )
    assert second.status_code == 429, second.content


def test_empty_quality_assess_rate_uses_default(
    editor_client: APIClient, workspace, requirement
):
    """An empty rate means 60/hour, never "unlimited" (KA-B-10)."""
    assert QualityAssessRateThrottle().rate == "60/hour"
    with override_settings(REST_FRAMEWORK=_rest_framework_with_quality_rate("")):
        assert QualityAssessRateThrottle().rate == "60/hour"


def test_assessment_writes_are_audited(
    editor_client: APIClient, workspace, requirement, provider
):
    from audit.models import AuditEntry

    editor_client.post(_assess_url(workspace), _body(requirement), format="json")
    entries = AuditEntry.unscoped.filter(entity_type="QualityAssessment")
    assert entries.exists()
    assert set(entries.values_list("op", flat=True)) == {"create"}
