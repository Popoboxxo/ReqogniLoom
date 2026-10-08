"""Issue #1197 — REST async trigger + poll for ``suggest-links``.

Covers ``POST /api/v1/workspaces/<ws>/traceability/suggest-links/?async=true``
(202 + task_id, mirroring requirement_bundle's async branch) and
``GET /api/v1/traceability/suggest-links-status/<task_id>/`` (tenant-scoped
poll, ADR-03). The RBAC fence is unchanged: the dispatch rides on the same POST
view (WRITE-gated), and only the GET poll is added for readers.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from application.traceability_suggest_service import TraceabilitySuggestService
from auth_tenancy.models import ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SUGGEST_URL = "/api/v1/workspaces/{ws}/traceability/suggest-links/"
_STATUS_URL = "/api/v1/traceability/suggest-links-status/{task_id}/"


def _login(username: str, password: str) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return authed


@pytest.fixture
def viewer_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    """A same-tenant user holding only VIEWER in *workspace* (READ, not WRITE)."""
    user = User.objects.create(
        username="suggestlinksviewer",
        email="suggestlinksviewer@t.test",
        tenant=tenant,
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()
    return _login("suggestlinksviewer", "hunter2pass")


@pytest.fixture
def other_tenant_authed_client() -> APIClient:
    other = Tenant.objects.create(
        name="Other SuggestLinks Tenant",
        slug=f"other-suggest-links-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    set_request_tenant(other.id)
    try:
        other_ws = Workspace.objects.create(
            tenant=other, name="Other SuggestLinks WS", preset={"name": "extended"}
        )
        user = User.objects.create(
            username="othersuggestlinks",
            email="othersuggestlinks@t.test",
            tenant=other,
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=other, user=user, workspace=other_ws, role="admin"
        )
    finally:
        clear_request_tenant()
    return _login("othersuggestlinks", "hunter2pass")


@pytest.mark.django_db
class TestSuggestLinksAsyncTrigger:
    def test_async_true_returns_202_with_task_id(
        self, authed_client: APIClient, workspace: Workspace
    ) -> None:
        with patch.object(
            TraceabilitySuggestService, "suggest_links_async", return_value="task-1"
        ) as dispatch:
            resp = authed_client.post(
                _SUGGEST_URL.format(ws=workspace.id) + "?async=true"
            )

        assert resp.status_code == 202
        assert resp.json() == {"task_id": "task-1"}
        dispatch.assert_called_once()

    def test_broker_not_configured_returns_503(
        self, authed_client: APIClient, workspace: Workspace
    ) -> None:
        stub = {"error": {"code": "BROKER_NOT_CONFIGURED", "message": "no broker"}}
        with patch.object(
            TraceabilitySuggestService, "suggest_links_async", return_value=stub
        ):
            resp = authed_client.post(
                _SUGGEST_URL.format(ws=workspace.id) + "?async=true"
            )

        assert resp.status_code == 503

    def test_omitting_async_stays_synchronous(
        self, authed_client: APIClient, workspace: Workspace
    ) -> None:
        fake = MagicMock()
        fake.to_dict.return_value = {"tier": "standard", "suggestions": []}
        with patch.object(
            TraceabilitySuggestService, "suggest_links", return_value=fake
        ) as sync_call, patch.object(
            TraceabilitySuggestService, "suggest_links_async"
        ) as async_call:
            resp = authed_client.post(_SUGGEST_URL.format(ws=workspace.id))

        assert resp.status_code == 200
        assert resp.json() == {"tier": "standard", "suggestions": []}
        sync_call.assert_called_once()
        async_call.assert_not_called()

    def test_viewer_cannot_trigger_the_async_dispatch(
        self, viewer_client: APIClient, workspace: Workspace
    ) -> None:
        """RBAC fence unchanged: dispatching is a POST, so it needs WRITE."""
        with patch.object(
            TraceabilitySuggestService, "suggest_links_async"
        ) as dispatch:
            resp = viewer_client.post(
                _SUGGEST_URL.format(ws=workspace.id) + "?async=true"
            )

        assert resp.status_code == 403
        dispatch.assert_not_called()


@pytest.mark.django_db
class TestSuggestLinksStatusView:
    def test_unknown_task_id_returns_not_found(self, authed_client: APIClient) -> None:
        resp = authed_client.get(_STATUS_URL.format(task_id="never-dispatched"))

        assert resp.status_code == 200
        assert resp.json() == {
            "task_id": "never-dispatched",
            "status": "not_found",
            "result": None,
            "error": None,
        }

    def test_same_tenant_poll_reaches_the_real_status(
        self, authed_client: APIClient, tenant: Tenant
    ) -> None:
        from application.traceability_suggest_service import (
            _TASK_TENANT_CACHE_PREFIX,
        )
        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        cache.set(f"{_TASK_TENANT_CACHE_PREFIX}:own-task", str(tenant.id))
        payload = {"tier": "standard", "suggestions": []}

        with patch.object(
            AsyncTaskDispatcher,
            "get_task_status",
            return_value=TaskStatusResult(
                task_id="own-task", status="done", result=payload
            ),
        ):
            resp = authed_client.get(_STATUS_URL.format(task_id="own-task"))

        assert resp.status_code == 200
        assert resp.json() == {
            "task_id": "own-task",
            "status": "done",
            "result": payload,
            "error": None,
        }

    def test_cross_tenant_poll_is_not_found_and_never_reads_the_backend(
        self,
        other_tenant_authed_client: APIClient,
        tenant: Tenant,
    ) -> None:
        from application.traceability_suggest_service import (
            _TASK_TENANT_CACHE_PREFIX,
        )
        from llm_adapter.dispatcher import AsyncTaskDispatcher

        cache.set(f"{_TASK_TENANT_CACHE_PREFIX}:foreign-task", str(tenant.id))

        with patch.object(AsyncTaskDispatcher, "get_task_status") as get_status:
            resp = other_tenant_authed_client.get(
                _STATUS_URL.format(task_id="foreign-task")
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "not_found"
        get_status.assert_not_called()


@pytest.mark.django_db
class TestSuggestLinksHumanTriggerFailsClosed:
    """ADR-019 Decision 3/4 + review finding 001-09 (WP5).

    ``suggest_links`` now persists a suggestion per eligible finding, so the
    human-bearer REST trigger is out of MVP scope. It must fail closed with
    409 (PRODUCER_CONTEXT_REQUIRED) instead of silently writing an unstamped,
    unreviewed proposal — and before the (expensive) auditor/LLM run.
    """

    def test_sync_human_trigger_returns_409(
        self, authed_client: APIClient, workspace: Workspace
    ) -> None:
        resp = authed_client.post(_SUGGEST_URL.format(ws=workspace.id))

        assert resp.status_code == 409, resp.content
        assert resp.json()["error"]["code"] == "PRODUCER_CONTEXT_REQUIRED"

    def test_async_human_trigger_returns_409(
        self, authed_client: APIClient, workspace: Workspace
    ) -> None:
        resp = authed_client.post(
            _SUGGEST_URL.format(ws=workspace.id) + "?async=true"
        )

        assert resp.status_code == 409, resp.content
        assert resp.json()["error"]["code"] == "PRODUCER_CONTEXT_REQUIRED"
