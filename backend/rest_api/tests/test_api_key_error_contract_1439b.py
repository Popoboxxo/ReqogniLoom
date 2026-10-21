"""#1439 review — the API-key ``400`` error contract, both detail variants.

The #1439 implementation emitted two different ``details`` shapes behind one
route and one status while publishing only one of them (F1), and its new
``{field, code, message}`` entry dropped the project-wide ``errors`` list that
generic clients read (M1). This module pins the corrected contract:

* every non-legacy detail entry carries ``field``, ``code``, ``message`` **and**
  ``errors`` (one message, identical to ``message``);
* a lone unknown field keeps the historical body byte-for-byte, bare
  ``{field, errors}`` entry included;
* the published ``400`` schema accepts both runtime shapes (``details.items``
  is a ``oneOf``) and the inner error object is a structural superset of the
  canonical envelope body;
* the two validation-surface restorations (F10): a non-string ``name`` is a
  ``400`` again, an empty-string ``expires_at`` means "absent" again.

The runtime body is validated against the *generated* schema, not a hand-copy
of it, so a future schema edit that stops describing the emitted bodies fails
here.
"""
from __future__ import annotations

from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.api_key_serializers import (
    EXPIRES_AT_INVALID_MESSAGE,
    MULTI_FIELD_MESSAGE,
    NAME_REQUIRED_MESSAGE,
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
    """Tenant + admin + one workspace — the shape of the #1439 tests."""
    tenant = Tenant.objects.create(name="T-1439b", slug="t-1439b", is_active=True)
    admin = User.objects.create(username="u1439b", email="u1439b@t.test", tenant=tenant)
    admin.set_password("pass1439b")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS-1439b", preset={"name": "standard"}
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
        {"username": "u1439b", "password": "pass1439b"},
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


# ---------------------------------------------------------------------------
# M1 — every non-legacy detail entry keeps the project-wide ``errors`` list
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_multi_error_entries_carry_field_errors_message_and_code(env):
    """One response, every problem — each entry complete for generic clients."""
    error = _error(_post(_client(), {"principal_type": "agent", "agent_identity": "x"}))

    assert error["message"] == MULTI_FIELD_MESSAGE
    assert [detail["field"] for detail in error["details"]] == [
        "agent_identity",  # unknown keys first, alphabetically
        "name",
        "scope",
        "workspace_ids",
        "expires_at",
    ]
    for detail in error["details"]:
        assert set(detail) == {"field", "code", "message", "errors"}, detail
        # Non-empty list, one message, and it is the same message — the
        # project-wide detail shape generic clients read `errors[0]` from.
        assert detail["errors"] == [detail["message"]], detail
        assert detail["errors"][0], detail

    unknown = error["details"][0]
    assert unknown["code"] == "unknown_field"
    assert unknown["message"] == "Unknown field 'agent_identity'."
    assert {detail["code"] for detail in error["details"][1:]} == {"required"}


# ---------------------------------------------------------------------------
# F1 — the lone-unknown-field body stays byte-identical
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_lone_unknown_field_body_is_byte_identical(env):
    """The historical body, asserted in full (not just its detail entry)."""
    resp = _post(_client(), {"name": "ok", "agent_identity": "x"})

    assert resp.status_code == 400, resp.content
    assert resp.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Unknown field 'agent_identity'.",
            "details": [
                {
                    "field": "agent_identity",
                    "errors": ["Unknown field 'agent_identity'."],
                }
            ],
        }
    }


# ---------------------------------------------------------------------------
# F10 — validation surface restored (no drift beyond multi-error reporting)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_non_string_name_is_a_400_not_a_201(env):
    """``{"name": 123}`` must not be coerced to ``"123"`` and accepted."""
    resp = _post(_client(), {"name": 123})

    error = _error(resp)
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
def test_empty_string_expires_at_is_treated_as_absent(env):
    """The pre-serializer ``if raw_expires_at:`` ignored ``""``; so does this."""
    resp = _post(_client(), {"name": "empty-expiry", "expires_at": ""})

    assert resp.status_code == 201, resp.content
    assert resp.json()["name"] == "empty-expiry"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_whitespace_only_expires_at_stays_an_error(env):
    """Only ``""`` is "absent"; a whitespace value was an error before, too."""
    error = _error(_post(_client(), {"name": "x", "expires_at": "   "}))

    assert error["message"] == EXPIRES_AT_INVALID_MESSAGE


# ---------------------------------------------------------------------------
# F1/M1 — the published 400 schema accepts BOTH runtime shapes
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


def _validator(schema: dict, component: str):
    """A jsonschema validator for one component of the generated document.

    ``#``-relative ``$ref``s resolve against the validator's root schema, so the
    component is wrapped in a root that carries both the ``$ref`` and the
    document's ``components`` — the emitted body is validated against the
    generated schema itself, not a copy.
    """
    jsonschema = pytest.importorskip("jsonschema")
    root = {
        "$ref": f"#/components/schemas/{component}",
        "components": schema["components"],
    }
    return jsonschema.Draft202012Validator(root)


def test_published_400_schema_accepts_both_runtime_bodies(env, openapi_schema):
    """Both legitimate bodies validate: multi-error and lone unknown field."""
    client = _client()
    multi = _post(client, {"principal_type": "agent", "agent_identity": "x"})
    lone_unknown = _post(client, {"name": "ok", "agent_identity": "x"})

    assert multi.status_code == 400, multi.content
    assert lone_unknown.status_code == 400, lone_unknown.content

    validator = _validator(openapi_schema, "ApiKeyErrorResponse")
    validator.validate(multi.json())
    validator.validate(lone_unknown.json())


def test_published_details_items_declares_both_detail_variants(openapi_schema):
    """``details.items`` is a oneOf with the required-ness each shape emits."""
    envelope = _resolve(
        openapi_schema, {"$ref": "#/components/schemas/ApiKeyErrorResponse"}
    )
    error_schema = _resolve(openapi_schema, envelope["properties"]["error"])
    details = error_schema["properties"]["details"]
    assert details["type"] == "array"

    item = _resolve(openapi_schema, details["items"])
    assert len(item["oneOf"]) == 2, item
    variants = [_resolve(openapi_schema, branch) for branch in item["oneOf"]]

    by_required = {frozenset(variant.get("required", ())): variant for variant in variants}
    assert set(by_required) == {
        frozenset({"field", "errors"}),
        frozenset({"field", "code", "message", "errors"}),
    }

    legacy = by_required[frozenset({"field", "errors"})]
    assert set(legacy["properties"]) == {"field", "errors"}

    additive = by_required[frozenset({"field", "code", "message", "errors"})]
    assert set(additive["properties"]) == {"field", "code", "message", "errors"}
    assert additive["properties"]["code"]["enum"] == [
        "required",
        "invalid",
        "unknown_field",
    ]


def test_error_component_is_a_structural_superset_of_the_canonical_envelope(
    openapi_schema,
):
    """F12: same body keys as ``ErrorBody`` — no invented ``request_id`` body.

    ``rest_api/error_envelope.py`` adds no ``request_id``; the canonical schema
    (``rest_api/openapi.py`` ``ErrorBody``) declares it optional/nullable, so
    this component does too, and the runtime body simply omits it.
    """
    components = openapi_schema["components"]["schemas"]
    canonical = components["ErrorBody"]
    api_key = components["ApiKeyValidationError"]

    assert set(canonical["properties"]) <= set(api_key["properties"])
    assert set(api_key["properties"]) == {"code", "message", "details", "request_id"}
    assert "request_id" not in api_key.get("required", ())
    assert api_key["properties"]["request_id"].get("nullable") is True
