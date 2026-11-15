"""Issue #1792 (S1) — REST surface of the on-demand artifact summary.

Pins the published contract (the ten fields of spec §5.7), the deliberate
"200 with a reason" degradation paths, the depth/refresh query contract and the
authorization half: a foreign tenant's artifact is a 404 (no existence leak), a
caller without a role or with an item-level deny is a 403 -- and neither ever
reaches a provider.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from application.artifact_summary_service import (
    DEGRADED_BUDGET_EXHAUSTED,
    DEGRADED_DISABLED,
    DEGRADED_PROVIDER_UNAVAILABLE,
)
from auth_tenancy.models import ROLE_EDITOR, ROLE_VIEWER, ItemPermission, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, TraceLink, User
from persistence.tests.factories import make_requirement, make_workspace
from rest_api.throttling import ArtifactSummaryRateThrottle

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_SUMMARY_TEXT = "Zwei Anforderungen betreffen die Anmeldung."

_CACHE_OVERRIDE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "artifact-summary-rest-test",
        }
    },
    ARTIFACT_SUMMARY_ENABLED=True,
)

_SUMMARY_FIELDS = {
    "artifact_id",
    "artifact_type",
    "summary",
    "degraded",
    "degraded_reason",
    "cache_hit",
    "trace_depth",
    "neighbour_count",
    "omitted_neighbours",
    "generated_at",
}


class _CountingProvider:
    PROVIDER_NAME = "counting"

    def __init__(self, text: str = _SUMMARY_TEXT) -> None:
        self.text = text
        self.calls: list[str] = []

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.calls.append(prompt)
        return self.text


class _RaisingProvider(_CountingProvider):
    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.calls.append(prompt)
        raise RuntimeError("provider down")


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
        name="Summary REST", slug=f"summary-rest-{uuid.uuid4().hex[:8]}"
    )


def _workspace(tenant: Tenant, name: str):
    set_request_tenant(tenant.id)
    try:
        return make_workspace(tenant, name=name)
    finally:
        clear_request_tenant()


@pytest.fixture
def workspace(tenant: Tenant):
    return _workspace(tenant, "summary-ws-a")


def _client(tenant: Tenant, workspace, role: str) -> tuple[APIClient, User]:
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"summary-{role}-{suffix}",
        email=f"summary-{role}-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
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
    return client, user


@pytest.fixture
def editor(tenant: Tenant, workspace) -> tuple[APIClient, User]:
    return _client(tenant, workspace, ROLE_EDITOR)


@pytest.fixture
def viewer(tenant: Tenant, workspace) -> tuple[APIClient, User]:
    return _client(tenant, workspace, ROLE_VIEWER)


@pytest.fixture
def requirement(workspace):
    set_request_tenant(workspace.tenant_id)
    try:
        return make_requirement(
            workspace,
            uid="REQ-L1-001",
            title="Anmeldung per OAuth",
            description="Das System authentifiziert Nutzer per OAuth 2.0.",
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> _CountingProvider:
    fake = _CountingProvider()
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: fake)
    return fake


def _url(artifact_id) -> str:
    return f"/api/v1/artifacts/{artifact_id}/summary/"


def test_summary_answers_the_documented_field_set(
    editor: tuple[APIClient, User], requirement, provider: _CountingProvider
) -> None:
    client, _user = editor

    response = client.get(_url(requirement.artifact_id))

    assert response.status_code == 200, response.content
    payload = response.json()
    assert set(payload) == _SUMMARY_FIELDS
    assert payload["artifact_id"] == str(requirement.artifact_id)
    assert payload["artifact_type"] == "Requirement"
    assert payload["summary"] == _SUMMARY_TEXT
    assert payload["degraded"] is False
    assert payload["degraded_reason"] is None
    assert payload["cache_hit"] is False
    assert payload["trace_depth"] == 1
    assert len(provider.calls) == 1


def test_second_call_is_a_cache_hit_without_a_provider_call(
    editor: tuple[APIClient, User], requirement, provider: _CountingProvider
) -> None:
    client, _user = editor

    client.get(_url(requirement.artifact_id))
    second = client.get(_url(requirement.artifact_id))

    assert second.status_code == 200, second.content
    assert second.json()["cache_hit"] is True
    assert len(provider.calls) == 1


def test_refresh_regenerates(
    editor: tuple[APIClient, User], requirement, provider: _CountingProvider
) -> None:
    client, _user = editor

    client.get(_url(requirement.artifact_id))
    refreshed = client.get(_url(requirement.artifact_id), {"refresh": "true"})

    assert refreshed.status_code == 200, refreshed.content
    assert refreshed.json()["cache_hit"] is False
    assert len(provider.calls) == 2


def test_depth_is_reported_and_clamped(
    editor: tuple[APIClient, User], requirement, provider: _CountingProvider
) -> None:
    client, _user = editor

    assert client.get(_url(requirement.artifact_id), {"depth": "2"}).json()[
        "trace_depth"
    ] == 2
    assert client.get(_url(requirement.artifact_id), {"depth": "0"}).json()[
        "trace_depth"
    ] == 1
    assert client.get(_url(requirement.artifact_id), {"depth": "7"}).json()[
        "trace_depth"
    ] == 2


def test_neighbour_count_and_omitted_neighbours_cap_at_twenty(
    editor: tuple[APIClient, User], tenant: Tenant, workspace, requirement, provider
) -> None:
    client, _user = editor
    set_request_tenant(tenant.id)
    try:
        for index in range(21):
            neighbour = make_requirement(
                workspace, uid=f"REQ-L1-{index + 100:03d}", title=f"Neighbour {index}"
            )
            TraceLink.objects.create(
                tenant=tenant,
                source=requirement.artifact,
                target=neighbour.artifact,
                link_type="derives-from",
                rationale=f"Rationale {index}",
            )
    finally:
        clear_request_tenant()

    payload = client.get(_url(requirement.artifact_id)).json()

    assert payload["neighbour_count"] == 20
    assert payload["omitted_neighbours"] == 1


@override_settings(ARTIFACT_SUMMARY_ENABLED=False)
def test_flag_off_is_200_disabled_without_a_provider_call(
    editor: tuple[APIClient, User], requirement, provider: _CountingProvider
) -> None:
    client, _user = editor

    response = client.get(_url(requirement.artifact_id))

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["degraded"] is True
    assert payload["degraded_reason"] == DEGRADED_DISABLED
    assert payload["summary"] is None
    assert provider.calls == []


def test_provider_error_is_200_provider_unavailable(
    editor: tuple[APIClient, User], requirement, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _user = editor
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: _RaisingProvider()
    )

    response = client.get(_url(requirement.artifact_id))

    assert response.status_code == 200, response.content
    assert response.json()["degraded"] is True
    assert response.json()["degraded_reason"] == DEGRADED_PROVIDER_UNAVAILABLE
    assert response.json()["summary"] is None


def test_budget_exhaustion_is_200_budget_exhausted(
    editor: tuple[APIClient, User],
    requirement,
    provider: _CountingProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _user = editor
    monkeypatch.setattr(
        "llm_adapter.token_tracking.is_over_daily_limit", lambda *a, **k: True
    )

    response = client.get(_url(requirement.artifact_id))

    assert response.status_code == 200, response.content
    assert response.json()["degraded_reason"] == DEGRADED_BUDGET_EXHAUSTED
    assert provider.calls == []


def test_unknown_artifact_is_404(
    editor: tuple[APIClient, User], provider: _CountingProvider
) -> None:
    client, _user = editor

    response = client.get(_url(uuid.uuid4()))

    assert response.status_code == 404, response.content
    assert provider.calls == []


def test_foreign_tenant_artifact_is_404(
    editor: tuple[APIClient, User],
    requirement,
    provider: _CountingProvider,
) -> None:
    """Another tenant's artifact is indistinguishable from a missing one."""
    other = Tenant.objects.create(
        name="Summary REST Other", slug=f"summary-rest-other-{uuid.uuid4().hex[:8]}"
    )
    other_workspace = _workspace(other, "summary-ws-other")
    foreign_client, _ = _client(other, other_workspace, ROLE_EDITOR)

    response = foreign_client.get(_url(requirement.artifact_id))

    assert response.status_code == 404, response.content
    assert provider.calls == []


def test_item_level_deny_is_403(
    editor: tuple[APIClient, User],
    tenant: Tenant,
    workspace,
    requirement,
    provider: _CountingProvider,
) -> None:
    client, user = editor
    set_request_tenant(tenant.id)
    try:
        ItemPermission.objects.create(
            tenant=tenant,
            user=user,
            workspace=workspace,
            artifact_id=requirement.artifact_id,
            permission_level="none",
        )
    finally:
        clear_request_tenant()

    response = client.get(_url(requirement.artifact_id))

    assert response.status_code == 403, response.content
    assert provider.calls == []


def test_malformed_bool_is_400(
    editor: tuple[APIClient, User], requirement, provider: _CountingProvider
) -> None:
    client, _user = editor

    response = client.get(_url(requirement.artifact_id), {"refresh": "maybe"})

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert provider.calls == []


def test_malformed_depth_is_400(
    editor: tuple[APIClient, User], requirement, provider: _CountingProvider
) -> None:
    client, _user = editor

    response = client.get(_url(requirement.artifact_id), {"depth": "abc"})

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert provider.calls == []


def test_malformed_artifact_id_never_reaches_the_service(
    editor: tuple[APIClient, User], provider: _CountingProvider
) -> None:
    client, _user = editor

    response = client.get("/api/v1/artifacts/not-a-uuid/summary/")

    assert response.status_code == 404, response.content
    assert provider.calls == []


def _rest_framework_with_summary_rate(rate: str) -> dict:
    current = dict(settings.REST_FRAMEWORK)
    current["DEFAULT_THROTTLE_RATES"] = {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        "artifact_summary": rate,
    }
    return current


def test_the_second_call_is_throttled_with_retry_after(
    editor: tuple[APIClient, User], requirement, provider: _CountingProvider
) -> None:
    client, _user = editor

    with override_settings(
        REST_FRAMEWORK=_rest_framework_with_summary_rate("1/hour")
    ):
        first = client.get(_url(requirement.artifact_id))
        second = client.get(_url(requirement.artifact_id))

    assert first.status_code == 200, first.content
    assert second.status_code == 429, second.content
    assert second["Retry-After"], "a 429 must tell the caller when to retry"
    assert len(provider.calls) == 1


def test_empty_summary_rate_uses_the_default_never_unlimited() -> None:
    """An empty rate means 60/hour, never "unlimited" (same rule as #378)."""
    assert ArtifactSummaryRateThrottle().rate == "60/hour"
    with override_settings(REST_FRAMEWORK=_rest_framework_with_summary_rate("")):
        assert ArtifactSummaryRateThrottle().rate == "60/hour"


def test_provider_answer_is_json_serialisable_text_stripped(
    editor: tuple[APIClient, User], requirement, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _user = editor
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider",
        lambda *a, **k: _CountingProvider(text="  Zusammenfassung.  "),
    )

    payload = client.get(_url(requirement.artifact_id)).json()

    assert payload["summary"] == "Zusammenfassung."
    assert json.dumps(payload)  # the whole body stays JSON-serialisable
