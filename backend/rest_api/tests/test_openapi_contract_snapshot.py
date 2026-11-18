"""S4.2 / R2S-001 — the content-sensible `views.py` split must not change the wire.

The 15.6k-line `views.py` was split into domain modules with re-export shims.
The pre-existing `(path, method)` manifest gate does NOT catch a changed
``operationId``, request/response content types, response codes, component
``schemas`` or ``securitySchemes``. This test pins all of those against a
committed snapshot so a future Move-Class cannot silently alter the OpenAPI
contract.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from drf_spectacular.generators import SchemaGenerator

FIXTURE = Path(__file__).with_name("fixtures") / "openapi_contract_snapshot.json"
_NON_OPERATION_KEYS = {"parameters", "summary", "description", "servers", "$ref"}


@pytest.fixture(scope="module")
def live_schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


@pytest.fixture(scope="module")
def snapshot() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _extract_operations(schema: dict) -> list[dict]:
    ops: list[dict] = []
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method in _NON_OPERATION_KEYS or not isinstance(operation, dict):
                continue
            ops.append(
                {
                    "method": method,
                    "path": path,
                    "operationId": operation.get("operationId"),
                    "requestContentTypes": sorted(
                        operation.get("requestBody", {})
                        .get("content", {})
                        .keys()
                    ),
                    "responseCodes": sorted(operation.get("responses", {}).keys()),
                }
            )
    return sorted(ops, key=lambda o: (o["path"], o["method"]))


def test_operation_contract_matches_snapshot(live_schema: dict, snapshot: dict) -> None:
    """Every (path, method, operationId, content types, response codes) is pinned."""
    live = _extract_operations(live_schema)
    expected = sorted(
        snapshot["operations"], key=lambda o: (o["path"], o["method"])
    )
    assert live == expected, (
        f"OpenAPI operation contract drifted: live={len(live)} "
        f"snapshot={len(expected)} (the S4.2 views.py split changed the wire)"
    )


def test_component_schemas_match_snapshot(live_schema: dict, snapshot: dict) -> None:
    """All 483 component schema names are pinned."""
    live = set(live_schema.get("components", {}).get("schemas", {}).keys())
    assert live == set(snapshot["schemas"]), "component schema set drifted"


def test_security_schemes_match_snapshot(live_schema: dict, snapshot: dict) -> None:
    """Auth schemes (Bearer + cookie) are pinned — guards against auth-doc drift."""
    live = live_schema.get("components", {}).get("securitySchemes", {})
    assert json.dumps(live, sort_keys=True) == json.dumps(
        json.loads(snapshot["securitySchemes"]), sort_keys=True
    ), "securitySchemes drifted"
