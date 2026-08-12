"""REST tests for the Requirement Bundle Export raw endpoints (Plan 1 Task 5)."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestRequirementBundleEndpoint:
    def test_default_depth_zero_json(
        self, authed_client: APIClient, workspace, architecture_element, requirement_allocated_to
    ):
        root = architecture_element
        req = requirement_allocated_to(root)

        resp = authed_client.get(f"/api/v1/architecture/{root.id}/requirement-bundle/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["truncated_at_depth"] is False
        assert len(body["items"]) == 1
        assert body["items"][0]["requirement_id"] == str(req.id)

    def test_depth_param_is_respected(
        self, authed_client, architecture_element, child_architecture_element, requirement_allocated_to
    ):
        root = architecture_element
        child = child_architecture_element(root)
        requirement_allocated_to(child)

        resp0 = authed_client.get(f"/api/v1/architecture/{root.id}/requirement-bundle/?depth=0")
        assert resp0.json()["items"] == []

        resp1 = authed_client.get(f"/api/v1/architecture/{root.id}/requirement-bundle/?depth=1")
        assert len(resp1.json()["items"]) == 1

    def test_output_format_markdown(self, authed_client, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?output_format=markdown"
        )
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/markdown")
        assert resp.content.decode().startswith("#")

    def test_output_format_csv(self, authed_client, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?output_format=csv"
        )
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/csv")

    def test_custom_filter_mode_requires_fields(self, authed_client, architecture_element):
        resp = authed_client.get(
            f"/api/v1/architecture/{architecture_element.id}/requirement-bundle/?filter_mode=custom"
        )
        assert resp.status_code == 400

    def test_custom_filter_mode_with_fields(
        self, authed_client, architecture_element, requirement_allocated_to
    ):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?filter_mode=custom&fields=title,status"
        )
        assert resp.status_code == 200
        assert set(resp.json()["items"][0]["fields"].keys()) == {"title", "status"}

    def test_custom_filter_mode_with_unknown_field_returns_400(
        self, authed_client, architecture_element, requirement_allocated_to
    ):
        """Parity with the MCP tool's
        test_export_custom_filter_mode_unknown_field_returns_validation_error:
        an unknown field name is rejected by the shared service method, and
        REST must surface it as a 400 VALIDATION_ERROR rather than a 500.
        """
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/"
            "?filter_mode=custom&fields=title,not_a_real_field"
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "not_a_real_field" in resp.json()["error"]["message"]

    def test_unknown_root_returns_404(self, authed_client):
        resp = authed_client.get(f"/api/v1/architecture/{uuid.uuid4()}/requirement-bundle/")
        assert resp.status_code == 404

    def test_depth_over_max_returns_400(self, authed_client, architecture_element):
        resp = authed_client.get(
            f"/api/v1/architecture/{architecture_element.id}/requirement-bundle/?depth=99"
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestRequirementBundleContentNegotiation:
    """Regression tests: the action's output format is an app-level concern
    (``?output_format=``) and must never be driven by DRF content
    negotiation.

    Before the fix, ``renderer_classes`` declared stub markdown/CSV renderers
    whose ``render()`` returned the payload dict unchanged. DRF's
    ``DefaultContentNegotiation`` selected them from the ``Accept`` header
    *before* the action body ran, and ``HttpResponse`` then iterated the dict
    into its concatenated key names - a ``200 OK`` with a corrupted body and
    no error signal. ``?format=xml`` produced a bare ``404`` from
    ``filter_renderers``, pre-empting the action's own 400.
    """

    def test_accept_csv_header_is_not_hijacked(
        self, authed_client, architecture_element, requirement_allocated_to
    ):
        root = architecture_element
        req = requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/", HTTP_ACCEPT="text/csv"
        )
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("application/json")
        body = resp.json()
        assert body["items"][0]["requirement_id"] == str(req.id)

    def test_accept_markdown_header_is_not_hijacked(
        self, authed_client, architecture_element, requirement_allocated_to
    ):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/",
            HTTP_ACCEPT="text/markdown",
        )
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("application/json")
        assert "items" in resp.json()

    def test_drf_reserved_format_param_is_ignored(
        self, authed_client, architecture_element, requirement_allocated_to
    ):
        """``?format=`` is DRF's reserved URL_FORMAT_OVERRIDE, not this
        action's parameter; it must neither select an output format nor 404."""
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?format=csv"
        )
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("application/json")
        assert "items" in resp.json()

    def test_invalid_output_format_returns_validation_error(
        self, authed_client, architecture_element
    ):
        resp = authed_client.get(
            f"/api/v1/architecture/{architecture_element.id}/requirement-bundle/"
            "?output_format=xml"
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
class TestAttributeSchemaEndpoint:
    def test_lists_requirement_schema(self, authed_client):
        resp = authed_client.get("/api/v1/attribute-schema/?entity_type=Requirement")
        assert resp.status_code == 200
        names = {row["attribute_name"] for row in resp.json()}
        assert "title" in names
        assert "status" in names

    def test_without_entity_type_returns_all(self, authed_client):
        resp = authed_client.get("/api/v1/attribute-schema/")
        assert resp.status_code == 200
        entity_types = {row["entity_type"] for row in resp.json()}
        assert "Requirement" in entity_types


@pytest.mark.django_db
class TestRequirementBundleCompressedMode:
    """Requirement Bundle Export, Plan 2 Task 4: `?mode=compressed` branch of
    the shared `requirement_bundle` action, plus the new async polling
    endpoint."""

    def test_mode_compressed_sync_returns_text(self, authed_client, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?mode=compressed"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "text" in body
        assert "cache_hit" in body
        # Issue #442: tests run on LLM_PROVIDER=mock, which cannot compress
        # anything — the response must say so instead of passing the
        # placeholder off as an AI compression.
        assert body["provider"] == "mock"
        assert body["is_mock_fallback"] is True
        assert body["text"].startswith("[MOCK FALLBACK] ")

    def test_mode_compressed_async_returns_task_id(self, authed_client, architecture_element, requirement_allocated_to, monkeypatch):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?mode=compressed&async=true"
        )
        assert resp.status_code == 202
        assert "task_id" in resp.json()

    def test_bundle_compression_status_endpoint(self, authed_client):
        resp = authed_client.get("/api/v1/bundle-compression-status/nonexistent-task-id/")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("pending", "not_found")

    def test_bundle_compression_status_exposes_flat_text_field(self, authed_client):
        """Issue #448: the async status payload must carry the completion on
        the same single-level ``text`` field ``?mode=compressed`` returns,
        while keeping the deprecated ``result`` envelope for old clients."""
        resp = authed_client.get("/api/v1/bundle-compression-status/nonexistent-task-id/")
        assert resp.status_code == 200
        assert set(resp.json()) == {
            "task_id", "status", "result", "error",
            "text", "is_mock_fallback", "provider",
        }

    def test_invalid_mode_returns_400(self, authed_client, architecture_element):
        resp = authed_client.get(
            f"/api/v1/architecture/{architecture_element.id}/requirement-bundle/?mode=bogus"
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.fixture
def other_tenant_authed_client() -> APIClient:
    """A second, unrelated tenant's authenticated APIClient (code review
    round 1 finding, ADR-03): used to prove a task_id dispatched by one
    tenant cannot be polled by another via
    GET /api/v1/bundle-compression-status/{task_id}/, since Celery's result
    backend has no concept of tenant on its own."""
    from auth_tenancy.models import ROLE_ADMIN, UserRole
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, User, Workspace

    other_tenant = Tenant.objects.create(
        name="Other Bundle Tenant",
        slug=f"other-bundle-tenant-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    set_request_tenant(other_tenant.id)
    try:
        other_workspace = Workspace.objects.create(
            tenant=other_tenant, name="Other Bundle WS", preset={"name": "extended"}
        )
        user = User.objects.create(
            username="otherbundleadmin", email="otherbundleadmin@t.test", tenant=other_tenant
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=other_tenant, user=user, workspace=other_workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "otherbundleadmin", "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@pytest.mark.django_db
class TestBundleCompressionStatusTenantOwnership:
    """ADR-03, code review round 1 finding: BundleCompressionStatusView must
    not let one tenant poll another tenant's task_id."""

    def _dispatch_task_id(self, authed_client, architecture_element, requirement_allocated_to, monkeypatch):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        root = architecture_element
        requirement_allocated_to(root)

        from llm_adapter import tasks

        fake_task_id = "fake-task-id"
        mock_async_result = MagicMock()
        mock_async_result.id = fake_task_id

        with patch.object(tasks.run_capability, "apply_async", return_value=mock_async_result):
            resp = authed_client.get(
                f"/api/v1/architecture/{root.id}/requirement-bundle/?mode=compressed&async=true"
            )
        assert resp.status_code == 202
        return resp.json()["task_id"]

    def test_cross_tenant_poll_returns_not_found(
        self, authed_client, other_tenant_authed_client, architecture_element,
        requirement_allocated_to, monkeypatch,
    ):
        task_id = self._dispatch_task_id(
            authed_client, architecture_element, requirement_allocated_to, monkeypatch
        )

        from llm_adapter.dispatcher import AsyncTaskDispatcher

        with patch.object(AsyncTaskDispatcher, "get_task_status") as mock_get_status:
            resp = other_tenant_authed_client.get(
                f"/api/v1/bundle-compression-status/{task_id}/"
            )

        assert resp.status_code == 200
        body = resp.json()
        # Load-bearing: identical to a genuinely-unknown task_id's response
        # -- a cross-tenant probe must not be able to distinguish "exists,
        # not yours" from "doesn't exist".
        assert body["status"] == "not_found"
        assert body["task_id"] == task_id
        mock_get_status.assert_not_called()

    def test_same_tenant_poll_reaches_the_real_status(
        self, authed_client, architecture_element, requirement_allocated_to, monkeypatch,
    ):
        task_id = self._dispatch_task_id(
            authed_client, architecture_element, requirement_allocated_to, monkeypatch
        )

        from llm_adapter.dispatcher import AsyncTaskDispatcher, TaskStatusResult

        with patch.object(
            AsyncTaskDispatcher, "get_task_status",
            return_value=TaskStatusResult(task_id=task_id, status="pending"),
        ):
            resp = authed_client.get(f"/api/v1/bundle-compression-status/{task_id}/")

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
