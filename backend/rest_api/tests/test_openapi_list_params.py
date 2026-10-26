"""E2.9 / G-L16: list query parameters are declared, and ``?status=`` filters.

``/api/v1/testcases/?status=`` used to be silently ignored while the OpenAPI
declared only ``page``/``page_size``. The rule now: a parameter that the
handler evaluates is declared; one that it does not evaluate is not advertised
(and must not be silently swallowed by a list that does support it).
"""
from __future__ import annotations

import re

import pytest
from drf_spectacular.generators import SchemaGenerator

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, TestCase

pytestmark = pytest.mark.django_db


def _schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


def test_every_soft_deletable_list_declares_include_deleted():
    paths = _schema()["paths"]

    # A soft-deleting DELETE handler declares the ``change_reason`` query
    # parameter (Plan G G1.5). Use that structural signal instead of a
    # hand-maintained path list: a new soft-deleting viewset is covered
    # automatically.
    soft_delete_detail_paths = [
        path
        for path, operations in paths.items()
        if path.endswith("/{id}/")
        and "delete" in operations
        and any(
            parameter.get("name") == "change_reason"
            for parameter in operations["delete"].get("parameters", [])
        )
    ]
    assert soft_delete_detail_paths, "no soft-deletable routes found in the schema"

    for detail_path in soft_delete_detail_paths:
        collection_path = detail_path.removesuffix("{id}/")
        assert collection_path in paths, collection_path
        declared = {
            parameter["name"]
            for parameter in paths[collection_path]["get"].get("parameters", [])
        }
        assert "include_deleted" in declared, (
            f"{collection_path} evaluates include_deleted but does not declare it"
        )
        assert "workspace_id" in declared, collection_path


def test_status_is_declared_only_where_the_service_filters():
    paths = _schema()["paths"]
    for path in (
        "/api/v1/requirements/",
        "/api/v1/testcases/",
        "/api/v1/change-requests/",
    ):
        declared = {
            parameter["name"] for parameter in paths[path]["get"].get("parameters", [])
        }
        assert "status" in declared, f"{path} filters status but does not declare it"

    # ADRs do not filter on status; advertising it would repeat the silent
    # no-op the other way round.
    adr_parameters = {
        parameter["name"]
        for parameter in paths["/api/v1/adrs/"]["get"].get("parameters", [])
    }
    assert "status" not in adr_parameters


def test_testcase_status_filter_is_applied(tenant, workspace, authed_client):
    from workflow import state_reader

    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="TestCase"
        )
        test_case = TestCase.objects.create(
            tenant=tenant, artifact=artifact, title="E2.9 status filter"
        )
        initial_state = state_reader.initial_state("TestCase")
    finally:
        clear_request_tenant()
    base = f"/api/v1/testcases/?workspace_id={workspace.id}&page_size=100"

    matching = authed_client.get(f"{base}&status={initial_state}")
    assert matching.status_code == 200, matching.content
    assert str(test_case.id) in {
        row["id"] for row in matching.json()["results"]
    }

    unknown = authed_client.get(f"{base}&status=not-a-real-state")
    assert unknown.status_code == 200, unknown.content
    assert unknown.json()["results"] == [], (
        "a status that matches nothing must return no rows — an ignored "
        "parameter would return the row above"
    )
