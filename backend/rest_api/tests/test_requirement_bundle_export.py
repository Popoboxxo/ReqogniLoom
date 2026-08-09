"""REST tests for the Requirement Bundle Export raw endpoints (Plan 1 Task 5)."""
from __future__ import annotations

import uuid

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

    def test_invalid_mode_returns_400(self, authed_client, architecture_element):
        resp = authed_client.get(
            f"/api/v1/architecture/{architecture_element.id}/requirement-bundle/?mode=bogus"
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
