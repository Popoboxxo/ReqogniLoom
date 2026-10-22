"""#1439 — ``POST /api/v1/api-keys/`` reports ALL field problems in one response.

Before the fix the hand-rolled ``ApiKeyViewSet.create`` short-circuited on the
first problem, so a caller had to round-trip once per missing field::

    {"principal_type": "agent"}                       -> 400 Field 'name' is required.
    {"principal_type": "agent", "name": "x"}          -> 400 Field 'scope' must be ...
    ...                                                -> ...

Contract pinned here:

* **one** problem -> the historical message byte-for-byte (a lone unknown field
  keeps its historical detail shape too);
* **two or more** -> one ``400`` with ``message == "Request validation failed."``
  and one ``details`` entry per problem, ordered by declaration order
  (unknown keys first, alphabetically).

The route also had no OpenAPI ``requestBody`` and its ``201`` claimed "No
response body"; the last tests assert the generated schema carries both.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.api_key_serializers import (
    AGENT_EXPIRY_REQUIRED_MESSAGE,
    EXPIRES_AT_INVALID_MESSAGE,
    MULTI_FIELD_MESSAGE,
    NAME_REQUIRED_MESSAGE,
    PRINCIPAL_TYPE_INVALID_MESSAGE,
    SCOPE_INVALID_MESSAGE,
    WORKSPACE_IDS_INVALID_MESSAGE,
)

_CREATE_URL = "/api/v1/api-keys/"

_SECRET = "jwt-signing-key-placeholder"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def env(db):
    """Tenant + admin + one workspace — the same shape as the #916 tests."""
    tenant = Tenant.objects.create(name="T-1439", slug="t-1439", is_active=True)
    admin = User.objects.create(username="u1439", email="u1439@t.test", tenant=tenant)
    admin.set_password("pass1439")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS-1439", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "workspace": workspace}
    finally:
        clear_request_tenant()


def _client() -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "u1439", "password": "pass1439"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _post(client: APIClient, payload: dict[str, Any]) -> Any:
    return client.post(_CREATE_URL, payload, format="json")


def _error(resp: Any) -> dict[str, Any]:
    assert resp.status_code == 400, resp.content
    return resp.json()["error"]


def _fields(error: dict[str, Any]) -> list[str]:
    return [detail["field"] for detail in error["details"]]


# ---------------------------------------------------------------------------
# One response, every problem (#1439 case 1)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_agent_with_only_principal_type_reports_all_four_missing_fields(env):
    """The headline case: no round trip per field — all four at once."""
    error = _error(_post(_client(), {"principal_type": "agent"}))

    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == MULTI_FIELD_MESSAGE
    assert _fields(error) == ["name", "scope", "workspace_ids", "expires_at"]
    assert {detail["code"] for detail in error["details"]} == {"required"}
    assert all(detail["errors"] == [detail["message"]] for detail in error["details"])

    assert {detail["message"] for detail in error["details"]} == {
        NAME_REQUIRED_MESSAGE,
        "Agent API keys require an explicit valid scope.",
        "Agent API keys require at least one canonical workspace UUID.",
        AGENT_EXPIRY_REQUIRED_MESSAGE,
    }


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_empty_body_reports_every_applicable_problem(env):
    """``{}`` is a user key, so ``name`` is the only applicable problem."""
    error = _error(_post(_client(), {}))

    assert error["message"] == NAME_REQUIRED_MESSAGE
    assert error["details"] == [
        {
            "field": "name",
            "code": "required",
            "message": NAME_REQUIRED_MESSAGE,
            "errors": [NAME_REQUIRED_MESSAGE],
        }
    ]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_invalid_field_plus_missing_field_are_both_reported(env):
    """A field-level error does not stop the cross-field/report pass."""
    error = _error(_post(_client(), {"scope": "godmode"}))

    assert error["message"] == MULTI_FIELD_MESSAGE
    assert _fields(error) == ["name", "scope"]


# ---------------------------------------------------------------------------
# Single problem — historical message, byte-identical (#1439 case 2)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_single_name_problem_keeps_the_legacy_message(env):
    error = _error(_post(_client(), {"name": "   "}))

    assert error["message"] == "Field 'name' is required."
    assert error["details"] == [
        {
            "field": "name",
            "code": "required",
            "message": NAME_REQUIRED_MESSAGE,
            "errors": [NAME_REQUIRED_MESSAGE],
        }
    ]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_single_principal_type_problem_keeps_the_legacy_message(env):
    error = _error(_post(_client(), {"name": "x", "principal_type": "service"}))

    assert error["message"] == "Field 'principal_type' must be 'user' or 'agent'."
    assert error["details"] == [
        {
            "field": "principal_type",
            "code": "invalid",
            "message": PRINCIPAL_TYPE_INVALID_MESSAGE,
            "errors": [PRINCIPAL_TYPE_INVALID_MESSAGE],
        }
    ]


# ---------------------------------------------------------------------------
# Unknown + missing fields in the SAME response (#916 contract preserved)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_unknown_field_and_missing_field_share_one_response(env):
    error = _error(_post(_client(), {"agent_identity": "x"}))

    assert error["message"] == MULTI_FIELD_MESSAGE
    assert _fields(error) == ["agent_identity", "name"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_lone_unknown_field_keeps_the_legacy_body(env):
    """The historical ``Unknown field '<key>'.`` response, detail shape included."""
    resp = _post(_client(), {"name": "ok", "agent_identity": "x"})
    assert resp.status_code == 400, resp.content
    error = resp.json()["error"]

    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "Unknown field 'agent_identity'."
    assert error["details"] == [
        {"field": "agent_identity", "errors": ["Unknown field 'agent_identity'."]}
    ]


# ---------------------------------------------------------------------------
# Individual invalid cases still name the right field (#1439 coverage)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "field", "code", "message"),
    [
        (
            {"name": "x", "principal_type": "service"},
            "principal_type",
            "invalid",
            PRINCIPAL_TYPE_INVALID_MESSAGE,
        ),
        (
            {"name": "x", "scope": "godmode"},
            "scope",
            "invalid",
            SCOPE_INVALID_MESSAGE,
        ),
        (
            {"name": "x", "workspace_ids": "not-a-list"},
            "workspace_ids",
            "invalid",
            WORKSPACE_IDS_INVALID_MESSAGE,
        ),
        (
            {"name": "x", "workspace_ids": ["not-a-uuid"]},
            "workspace_ids",
            "invalid",
            WORKSPACE_IDS_INVALID_MESSAGE,
        ),
        (
            {"name": "x", "expires_at": "not-a-date"},
            "expires_at",
            "invalid",
            EXPIRES_AT_INVALID_MESSAGE,
        ),
    ],
)
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_individual_invalid_field_is_reported(
    env, payload: dict[str, Any], field: str, code: str, message: str
) -> None:
    error = _error(_post(_client(), payload))

    assert error["message"] == message
    assert error["details"] == [
        {"field": field, "code": code, "message": message, "errors": [message]}
    ]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_agent_past_expiry_is_reported_as_the_agent_rule(env):
    payload = {
        "name": "past-expiry",
        "principal_type": "agent",
        "scope": "read",
        "workspace_ids": [str(env["workspace"].id)],
        "expires_at": (timezone.now() - timedelta(seconds=1)).isoformat(),
    }

    error = _error(_post(_client(), payload))

    assert error["message"] == AGENT_EXPIRY_REQUIRED_MESSAGE
    assert error["details"] == [
        {
            "field": "expires_at",
            "code": "invalid",
            "message": AGENT_EXPIRY_REQUIRED_MESSAGE,
            "errors": [AGENT_EXPIRY_REQUIRED_MESSAGE],
        }
    ]


# ---------------------------------------------------------------------------
# Valid request — 201 payload unchanged (#1439 regression guard)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_valid_agent_key_returns_the_unchanged_201_payload(env):
    resp = _post(
        _client(),
        {
            "name": "my-agent",
            "principal_type": "agent",
            "agent_label": "QA Agent",
            "scope": "read",
            "workspace_ids": [str(env["workspace"].id)],
            "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
        },
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert set(body) == {
        "id",
        "name",
        "plaintext",
        "warning",
        "principal_type",
        "agent_label",
        "scope",
    }
    assert body["name"] == "my-agent"
    assert body["plaintext"].startswith("reqlo_")
    assert body["warning"] == "Save this key now — it will not be shown again."
    assert body["principal_type"] == "agent"
    assert body["agent_label"] == "QA Agent"
    assert body["scope"] == "read"


# ---------------------------------------------------------------------------
# OpenAPI: requestBody + real 201 body (#1439 case 3)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def _resolve(schema: dict, node: dict) -> dict:
    while "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        node = schema["components"]["schemas"][name]
    return node


def _create_operation(schema: dict) -> dict:
    return schema["paths"]["/api/v1/api-keys/"]["post"]


def test_openapi_documents_the_create_request_body(openapi_schema: dict) -> None:
    operation = _create_operation(openapi_schema)

    assert "requestBody" in operation, (  # the #1439 gap: no body at all
        "POST /api/v1/api-keys/ must advertise its request body"
    )
    body = _resolve(
        openapi_schema,
        operation["requestBody"]["content"]["application/json"]["schema"],
    )
    assert set(body["properties"]) == {
        "name",
        "principal_type",
        "scope",
        "workspace_ids",
        "expires_at",
        "agent_label",
    }
    assert body.get("required") == ["name"]


def test_openapi_documents_the_201_response_body(openapi_schema: dict) -> None:
    operation = _create_operation(openapi_schema)

    content = operation["responses"]["201"].get("content")
    assert content, "201 must carry a response schema, not 'No response body'"
    body = _resolve(openapi_schema, content["application/json"]["schema"])
    assert set(body["properties"]) == {
        "id",
        "name",
        "plaintext",
        "warning",
        "principal_type",
        "agent_label",
        "scope",
    }
