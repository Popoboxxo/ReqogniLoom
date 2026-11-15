"""Issue #1793 (S6) — REST read paths and manual refresh of stored summaries.

Three routes over the S5 table:

    GET  /api/v1/workspaces/<id>/summaries/
    GET  /api/v1/workspaces/<id>/summaries/<artifact_type>/
    POST /api/v1/workspaces/<id>/summaries/<artifact_type>/refresh/

Pinned here: the spec §6.6 field set on list and detail, ``stale`` exactly when
``generated_at`` is older than twice the workspace cadence (or the sweep is
off), the empty-type answer (``text=null``, ``item_count=0``, ``reason=null``),
the authorization shape (foreign tenant 404, no role 403, refresh needs write),
and that a refresh under a switched-off on-demand flag answers 200 with
``outcome="skipped:flag_off"`` instead of spending a provider call.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from application.artifact_summary_service import (
    SUMMARY_PAYLOAD_KEYS,
    ArtifactSummaryService,
)
from application.summary_support import TYPE_ROSTER_KIND, upsert_summary
from auth_tenancy.models import ROLE_EDITOR, ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import ArtifactSummary, Tenant, User, Workspace
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_STORED_TEXT = "Zehn Anforderungen betreffen die Anmeldung."

_CACHE_OVERRIDE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "artifact-summary-rest-1793",
        }
    },
    ARTIFACT_SUMMARY_ENABLED=True,
    ARTIFACT_SUMMARY_SWEEP_ENABLED=True,
    SUMMARY_DAILY_TOKEN_LIMIT=0,
)


@pytest.fixture(autouse=True)
def _cache() -> Iterator[None]:
    with _CACHE_OVERRIDE:
        cache.clear()
        try:
            yield
        finally:
            cache.clear()
            clear_request_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="Summary REST 1793", slug=f"summary-1793-{uuid.uuid4().hex[:8]}"
    )


def _workspace(tenant: Tenant, name: str, **kwargs) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return make_workspace(tenant, name=name, **kwargs)
    finally:
        clear_request_tenant()


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return _workspace(
        tenant, "summary-1793-ws", summary_sweep_interval_minutes=1440
    )


def _client(tenant: Tenant, workspace: Workspace | None, role: str | None) -> APIClient:
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"summary-1793-{suffix}",
        email=f"summary-1793-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    if workspace is not None and role is not None:
        set_request_tenant(tenant.id)
        try:
            UserRole.objects.create(
                tenant=tenant, user=user, workspace=workspace, role=role
            )
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
def editor(tenant: Tenant, workspace: Workspace) -> APIClient:
    return _client(tenant, workspace, ROLE_EDITOR)


@pytest.fixture
def viewer(tenant: Tenant, workspace: Workspace) -> APIClient:
    return _client(tenant, workspace, ROLE_VIEWER)


def _stored(
    workspace: Workspace,
    artifact_type: str = "Requirement",
    *,
    text: str = _STORED_TEXT,
    item_count: int = 10,
    generated_at=None,
    status: str = ArtifactSummary.Status.OK,
) -> ArtifactSummary:
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        return upsert_summary(
            workspace=workspace,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type=artifact_type,
            values={
                "text": text,
                "content_hash": "a" * 64,
                "input_digest": {"item_count": item_count},
                "status": status,
                "reason": "",
                "provider": "counting",
                "generated_at": generated_at or timezone.now(),
            },
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def test_list_answers_the_documented_field_set(
    editor: APIClient, workspace: Workspace
) -> None:
    _stored(workspace, "Requirement")
    _stored(workspace, "Risk", text="risks", item_count=3)

    response = editor.get(f"/api/v1/workspaces/{workspace.id}/summaries/")

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["workspace_id"] == str(workspace.id)
    assert payload["count"] == 2
    assert payload["truncated"] is False
    assert [row["artifact_type"] for row in payload["summaries"]] == [
        "Requirement",
        "Risk",
    ]
    assert set(payload["summaries"][0]) == set(SUMMARY_PAYLOAD_KEYS)
    assert payload["summaries"][0]["text"] == _STORED_TEXT
    assert payload["summaries"][0]["item_count"] == 10
    assert payload["summaries"][0]["stale"] is False


def test_detail_returns_one_type(editor: APIClient, workspace: Workspace) -> None:
    _stored(workspace, "Requirement")

    response = editor.get(
        f"/api/v1/workspaces/{workspace.id}/summaries/Requirement/"
    )

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["artifact_type"] == "Requirement"
    assert payload["text"] == _STORED_TEXT
    assert payload["summary_kind"] == TYPE_ROSTER_KIND


def test_an_empty_type_is_not_an_error(editor: APIClient, workspace: Workspace) -> None:
    response = editor.get(f"/api/v1/workspaces/{workspace.id}/summaries/Risk/")

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["text"] is None
    assert payload["item_count"] == 0
    assert payload["reason"] is None
    assert payload["stale"] is False


def test_a_state_past_twice_the_cadence_is_stale(
    editor: APIClient, workspace: Workspace
) -> None:
    _stored(workspace, "Requirement", generated_at=timezone.now() - timedelta(days=3))

    payload = editor.get(
        f"/api/v1/workspaces/{workspace.id}/summaries/Requirement/"
    ).json()

    assert payload["stale"] is True
    assert payload["reason"] == "stale"


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_a_foreign_tenant_workspace_is_a_404(tenant: Tenant, workspace: Workspace) -> None:
    other = Tenant.objects.create(
        name="Other 1793", slug=f"other-1793-{uuid.uuid4().hex[:8]}"
    )
    foreign = _workspace(other, "foreign-1793")
    editor = _client(tenant, workspace, ROLE_EDITOR)

    response = editor.get(f"/api/v1/workspaces/{foreign.id}/summaries/")

    assert response.status_code == 404, response.content


def test_a_caller_without_a_role_is_a_403(tenant: Tenant, workspace: Workspace) -> None:
    outsider = _client(tenant, None, None)

    response = outsider.get(f"/api/v1/workspaces/{workspace.id}/summaries/")

    assert response.status_code == 403, response.content


# ---------------------------------------------------------------------------
# Manual refresh
# ---------------------------------------------------------------------------


def test_refresh_under_a_switched_off_flag_is_a_200_skip(
    editor: APIClient, workspace: Workspace
) -> None:
    with override_settings(ARTIFACT_SUMMARY_ENABLED=False):
        response = editor.post(
            f"/api/v1/workspaces/{workspace.id}/summaries/Requirement/refresh/"
        )

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["outcome"] == "skipped:flag_off"
    assert payload["text"] is None


def test_a_viewer_may_read_but_not_refresh(
    viewer: APIClient, workspace: Workspace
) -> None:
    read = viewer.get(f"/api/v1/workspaces/{workspace.id}/summaries/")
    refresh = viewer.post(
        f"/api/v1/workspaces/{workspace.id}/summaries/Requirement/refresh/"
    )

    assert read.status_code == 200, read.content
    assert refresh.status_code == 403, refresh.content


def test_refresh_runs_through_the_sweeper_and_answers_outcome(
    editor: APIClient, workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from application.artifact_summary_sweep import ArtifactSummarySweeper

    seen: dict[str, object] = {}

    def _run(self, **kwargs):
        seen.update(kwargs)
        return "skipped:no_agent_key"

    monkeypatch.setattr(ArtifactSummarySweeper, "run_for_scope", _run)

    response = editor.post(
        f"/api/v1/workspaces/{workspace.id}/summaries/Requirement/refresh/"
    )

    assert response.status_code == 200, response.content
    assert response.json()["outcome"] == "skipped:no_agent_key"
    assert seen["manual"] is True
    assert seen["trigger"] == "manual"
    assert seen["artifact_type"] == "Requirement"


def test_refresh_is_throttled_on_the_shared_scope(
    editor: APIClient, workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ArtifactSummaryService, "refresh_type_summary", lambda *a, **k: {}
    )
    current = dict(settings.REST_FRAMEWORK)
    current["DEFAULT_THROTTLE_RATES"] = {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        "artifact_summary": "1/hour",
    }
    url = f"/api/v1/workspaces/{workspace.id}/summaries/Requirement/refresh/"

    with override_settings(REST_FRAMEWORK=current):
        first = editor.post(url)
        second = editor.post(url)

    assert first.status_code == 200, first.content
    assert second.status_code == 429, second.content
    assert second["Retry-After"]
