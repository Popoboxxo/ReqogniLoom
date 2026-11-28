"""OpenAPI contract fixes for #2078/#2089.

The generic transitions action serves GET and POST from one method; without a
scoped schema spectacular inferred the entity request. These assertions pin the
corrected contract so a future refactor cannot quietly reintroduce it.
"""
from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator


@pytest.fixture(scope="module")
def schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/documents/{id}/transitions/",
        "/api/v1/work-items/{id}/transitions/",
        "/api/v1/requirements/{id}/transitions/",
    ],
)
def test_transition_post_uses_the_transition_request_schema(schema, path):
    ref = schema["paths"][path]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert ref == "#/components/schemas/WorkflowTransitionRequestRequest"


def test_test_run_results_uses_the_result_schema(schema):
    ref = schema["paths"]["/api/v1/test-runs/{id}/results/"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/TestRunResultRequest"


@pytest.mark.parametrize("path", ["/api/v1/diagrams/", "/api/v1/artifacts/"])
def test_workspace_id_is_marked_required(schema, path):
    params = {
        param["name"]: param
        for param in schema["paths"][path]["get"].get("parameters", [])
    }
    assert params["workspace_id"]["required"] is True
