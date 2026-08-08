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

    def test_format_markdown(self, authed_client, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(
            f"/api/v1/architecture/{root.id}/requirement-bundle/?format=markdown"
        )
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/markdown")
        assert resp.content.decode().startswith("#")

    def test_format_csv(self, authed_client, architecture_element, requirement_allocated_to):
        root = architecture_element
        requirement_allocated_to(root)
        resp = authed_client.get(f"/api/v1/architecture/{root.id}/requirement-bundle/?format=csv")
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

    def test_unknown_root_returns_404(self, authed_client):
        resp = authed_client.get(f"/api/v1/architecture/{uuid.uuid4()}/requirement-bundle/")
        assert resp.status_code == 404

    def test_depth_over_max_returns_400(self, authed_client, architecture_element):
        resp = authed_client.get(
            f"/api/v1/architecture/{architecture_element.id}/requirement-bundle/?depth=99"
        )
        assert resp.status_code == 400


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
