"""INT-06 regression tests — OpenAPI / error contract (systemaudit 2026-09).

Focused regression tests for work unit INT-06 (findings 075, 076, 078, 090, 077),
the acceptance criteria of ``INTEGRATION_LLM.md`` §INT-06 and the now-accepted
``ADR-014`` (§1/§5/§7, notably the immediately-allowed ``request_id`` coupling):

* **077** — the error envelope body carries a ``request_id`` (the
  ``X-Request-ID`` response header already exists, ``reqogniloom/middleware.py``);
* **075** — ``COMMON_ERROR_RESPONSES`` (``rest_api/openapi.py``) is no longer a
  dead declaration: the generated schema declares the common 4xx/5xx error
  responses on the operations, with the documented error body schema;
* **078** — the ReqIF import route declares a ``requestBody`` (multipart file
  upload) and the ReqIF export route declares an ``application/xml`` 200 body
  (the two were asymmetric: import-only multipart, export-only XML);
* **090** — the ``cookieAuth`` security scheme is no longer a dead, unreferenced
  auth path in the schema;
* **076** — the ReqIF 1.2 export validates against the ReqIF XSD shipped with
  the pinned ``reqif`` PyPI package (REQ-IF-VERSION fixed ``1.0``, required
  ``LAST-CHANGE``/``MAX-LENGTH`` attributes, unique attribute-definition ids).

The schema tests build the document with ``drf_spectacular.SchemaGenerator``
(the same output as ``GET /api/v1/schema/`` and ``manage.py spectacular``);
no live stack is required.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    User,
    Workspace,
)

# ---------------------------------------------------------------------------
# Optional dependency: the ``reqif`` PyPI package (with its bundled ReqIF XSD)
# and ``xmlschema`` are runtime dependencies of the export path. They are
# present in the backend image; skip the XSD test gracefully if the local env
# is missing them rather than erroring at import time.
# ---------------------------------------------------------------------------

try:  # pragma: no cover - import guard only
    import xmlschema
    from reqif import PATH_TO_REQIF_ROOT
    from reqif.parser import ReqIFParser

    _HAVE_REQIF = True
except Exception:  # noqa: BLE001 - optional dependency guard
    _HAVE_REQIF = False


# ---------------------------------------------------------------------------
# Schema fixture (module-scoped: generation is the expensive part)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    """The generated OpenAPI 3.0 document (same output as GET /api/schema/)."""
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


# ---------------------------------------------------------------------------
# Fixtures: a tenant + workspace + one Need + one Requirement, mirroring the
# seeding pattern of ``rest_api/tests/test_reqif_export.py``.
# ---------------------------------------------------------------------------

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def int06_workspace(db):
    """Admin user with one workspace holding one Need + one Requirement."""
    tenant = Tenant.objects.create(
        name=f"int06-tenant-{uuid.uuid4().hex[:8]}",
        slug=f"int06-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    user = User.objects.create(
        username=f"int06admin-{uuid.uuid4().hex[:6]}",
        email="int06admin@t.test",
        tenant=tenant,
    )
    user.set_password("int06pass123")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Int06-WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
        need_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="StakeholderNeed"
        )
        StakeholderNeed.objects.create(
            tenant=tenant,
            artifact=need_art,
            title="INT06 Need Alpha",
            description="Seeded for INT-06 XSD validation",
            category="functional",
            uid="NEED-INT06-001",
        )
        req_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=tenant,
            artifact=req_art,
            title="INT06 Req Alpha",
            description="Seeded for INT-06 XSD validation",
            category="functional",
            uid="REQ-INT06-001",
        )
    finally:
        clear_request_tenant()

    return user, tenant, workspace


def _login(client: APIClient, username: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    return resp.json()["token"]


# ===========================================================================
# Finding 077 / ADR-014 §1: request_id in the error body
# ===========================================================================


class TestRequestIdInErrorBody:
    """ADR-014 §1/§7: the error envelope body carries ``request_id``.

    The ``X-Request-ID`` response header already exists
    (``reqogniloom/middleware.py``); the immediate, additive fix mirrors the
    same id into the error body of the audited endpoints so a client can
    correlate a 4xx/5xx with the server log without depending on a header
    alone. The wider project-wide body copy is RES-07 (W3); INT-06 (W2) covers
    the audited error paths and declares the field in the published schema.
    """

    @override_settings(**_JWT_OVERRIDES)
    @pytest.mark.django_db
    def test_error_body_request_id_matches_header(self, int06_workspace) -> None:
        """An audited error response exposes the same id in body and header."""
        user, tenant, workspace = int06_workspace
        client = APIClient()
        token = _login(client, user.username, "int06pass123")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # A malformed ReqIF upload without multipart data is a request-level 400.
        resp = client.post(
            f"/api/v1/workspaces/{workspace.id}/import/reqif/",
            data={},
            format="json",
        )

        assert resp.status_code == 400, resp.content
        body = resp.json()
        assert "error" in body
        assert body["error"].get("request_id")
        assert body["error"]["request_id"] == resp["X-Request-ID"]

    def test_error_body_serializer_documents_request_id(self) -> None:
        """The declared error schema exposes ``request_id`` (contract parity)."""
        from rest_api.openapi import ErrorBodySerializer

        ser = ErrorBodySerializer(
            {"code": "VALIDATION_ERROR", "message": "Fail.", "request_id": "abc"}
        )
        assert "request_id" in ser.fields


# ===========================================================================
# Finding 075: COMMON_ERROR_RESPONSES is wired into the generated schema
# ===========================================================================


class TestCommonErrorResponsesWired:
    """Finding 075: the declared error responses must reach the schema.

    ``COMMON_ERROR_RESPONSES`` existed but was referenced nowhere, so 98.4 % of
    operations declared no error case at all. The generated document must now
    describe the common 4xx/5xx errors for the operations.
    """

    def test_an_operation_declares_500(self, openapi_schema: dict) -> None:
        # The audit observed 0 of 439 operations declaring any 5xx.
        operations_with_500 = [
            (path, method)
            for path, item in openapi_schema["paths"].items()
            for method, op in item.items()
            if isinstance(op, dict) and "500" in op.get("responses", {})
        ]
        assert operations_with_500, "no operation declares a 500 response"

    def test_an_operation_declares_400_and_401(self, openapi_schema: dict) -> None:
        for code in ("400", "401", "403", "404"):
            found = [
                path
                for path, item in openapi_schema["paths"].items()
                for method, op in item.items()
                if isinstance(op, dict) and code in op.get("responses", {})
            ]
            assert found, f"no operation declares a {code} response"

    def test_declared_error_response_references_body_schema(
        self, openapi_schema: dict
    ) -> None:
        """At least one declared error response carries a body schema ref."""
        for _path, item in openapi_schema["paths"].items():
            for method, op in item.items():
                if not isinstance(op, dict):
                    continue
                for code, response in op.get("responses", {}).items():
                    if not code.startswith(("4", "5")):
                        continue
                    if "content" in response:
                        return
        pytest.fail("no declared error response references a response body schema")

    def test_common_error_responses_are_registered_as_components(
        self, openapi_schema: dict
    ) -> None:
        components = openapi_schema.get("components", {}).get("schemas", {})
        assert "ErrorResponse" in components
        assert "ErrorBody" in components


# ===========================================================================
# Finding 078: ReqIF import requestBody + export application/xml
# ===========================================================================

_REQIF_IMPORT_PATH = "/api/v1/workspaces/{id}/import/reqif/"
_REQIF_EXPORT_PATH = "/api/v1/workspaces/{id}/export/reqif/"


class TestReqifEndpointSchemas:
    """Finding 078: ReqIF import/export bodies are documented in the schema."""

    def test_reqif_import_declares_request_body(self, openapi_schema: dict) -> None:
        post = openapi_schema["paths"][_REQIF_IMPORT_PATH]["post"]
        assert "requestBody" in post, "ReqIF import has no documented requestBody"
        content = post["requestBody"]["content"]
        assert "multipart/form-data" in content
        # COMPONENT_SPLIT_REQUEST turns the inline serializer into a $ref; the
        # properties live in components.schemas.<name>.
        schema = content["multipart/form-data"]["schema"]
        if "$ref" in schema:
            name = schema["$ref"].rsplit("/", 1)[-1]
            schema = openapi_schema["components"]["schemas"][name]
        props = schema.get("properties", {})
        # ``file`` is the field the view actually reads (request.FILES.get).
        assert "file" in props

    def test_reqif_export_declares_xml_response(self, openapi_schema: dict) -> None:
        get = openapi_schema["paths"][_REQIF_EXPORT_PATH]["get"]
        ok = get["responses"]["200"]
        assert "content" in ok, "ReqIF export 200 declares no response body"
        assert "application/xml" in ok["content"]

    def test_reqif_import_and_export_declare_request_id_error_body(
        self, openapi_schema: dict
    ) -> None:
        """The audited endpoints themselves declare the common error cases."""
        for path in (_REQIF_IMPORT_PATH, _REQIF_EXPORT_PATH):
            op = next(
                iter(
                    o
                    for o in openapi_schema["paths"][path].values()
                    if isinstance(o, dict)
                )
            )
            responses = op.get("responses", {})
            assert "400" in responses
            assert "500" in responses

    def test_import_view_declares_request_id_in_docstring(
        self, openapi_schema: dict
    ) -> None:
        """``request_id`` is named in the published ReqIF contract (#077/ADR-014)."""
        post = openapi_schema["paths"][_REQIF_IMPORT_PATH]["post"]
        description = post.get("description", "")
        assert "request_id" in description


# ===========================================================================
# Finding 090: cookieAuth is referenced (or removed)
# ===========================================================================


class TestCookieAuthSchemeResolved:
    """Finding 090: the schema must not advertise a dead auth path.

    ``cookieAuth`` was auto-generated from ``SessionAuthentication`` but
    referenced by zero operations — a declared auth route that does not exist.
    It is either referenced by the operations that genuinely accept the session
    cookie, or dropped.
    """

    def test_cookie_auth_is_not_a_dead_scheme(self, openapi_schema: dict) -> None:
        schemes = (
            openapi_schema.get("components", {}).get("securitySchemes", {})
        )
        if "cookieAuth" not in schemes:
            return  # removed — acceptable
        referenced = any(
            isinstance(security, dict) and "cookieAuth" in security
            for item in openapi_schema["paths"].values()
            for op in item.values()
            if isinstance(op, dict)
            for security in op.get("security", [])
        )
        assert referenced, "cookieAuth is declared but referenced by no operation"


# ===========================================================================
# Finding 076: the ReqIF export validates against the ReqIF XSD
# ===========================================================================


@pytest.mark.skipif(not _HAVE_REQIF, reason="reqif/xmlschema not installed")
class TestReqifExportXsdConformance:
    """Finding 076: the exported ReqIF 1.2 document is XSD-valid.

    The XSD is the one shipped with the pinned ``reqif`` PyPI package
    (``reqif/reqif_schema/reqif.xsd``). Before the fix the export produced 32
    XSD violations (wrong ``REQ-IF-VERSION``, missing required ``LAST-CHANGE``
    and ``MAX-LENGTH`` attributes, duplicated ``xs:ID`` attribute definitions).
    """

    def _export(self, workspace) -> bytes:
        """Run the REST export and return the raw XML bytes."""
        from rest_api.tests.test_reqif_export import (  # noqa: F401
            _JWT_OVERRIDES as jwt_overrides,
        )

        client = APIClient()
        token = _login(client, "int06exportadmin", "int06pass123")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = client.get(f"/api/v1/workspaces/{workspace.id}/export/reqif/")
        assert resp.status_code == 200, resp.content
        return resp.content

    @override_settings(**_JWT_OVERRIDES)
    @pytest.mark.django_db
    def test_export_validates_against_reqif_xsd(self, int06_workspace) -> None:
        import os

        user, tenant, workspace = int06_workspace
        # The export login uses a separate user so the fixture's user password
        # is independent of the helper's fixed username/password pair.
        set_request_tenant(tenant.id)
        try:
            export_user = User.objects.create(
                username="int06exportadmin",
                email="int06exportadmin@t.test",
                tenant=tenant,
            )
            export_user.set_password("int06pass123")
            export_user.save(update_fields=["password"])
            UserRole.objects.create(
                tenant=tenant,
                user=export_user,
                workspace=workspace,
                role=ROLE_ADMIN,
            )
        finally:
            clear_request_tenant()

        xml_bytes = self._export(workspace)

        xsd_path = os.path.join(
            PATH_TO_REQIF_ROOT, "reqif", "reqif_schema", "reqif.xsd"
        )
        schema = xmlschema.XMLSchema(xsd_path)
        # ``validate`` raises on the first error; ``iter_errors`` collects all.
        errors = list(schema.iter_errors(xml_bytes))
        assert errors == [], (
            f"{len(errors)} ReqIF XSD violation(s): "
            + "; ".join(f"{e.reason} @ {e.path}" for e in errors[:5])
        )

    @override_settings(**_JWT_OVERRIDES)
    @pytest.mark.django_db
    def test_export_still_round_trips(self, int06_workspace) -> None:
        """The stricter export remains parseable by the reqif library."""
        user, tenant, workspace = int06_workspace
        set_request_tenant(tenant.id)
        try:
            export_user = User.objects.create(
                username="int06exportadmin2",
                email="int06exportadmin2@t.test",
                tenant=tenant,
            )
            export_user.set_password("int06pass123")
            export_user.save(update_fields=["password"])
            UserRole.objects.create(
                tenant=tenant,
                user=export_user,
                workspace=workspace,
                role=ROLE_ADMIN,
            )
        finally:
            clear_request_tenant()

        client = APIClient()
        token = _login(client, "int06exportadmin2", "int06pass123")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = client.get(f"/api/v1/workspaces/{workspace.id}/export/reqif/")
        assert resp.status_code == 200

        bundle = ReqIFParser.parse_from_string(resp.content.decode("utf-8"))
        content = bundle.core_content.req_if_content
        assert len(content.spec_objects) == 2
        titles = {
            so.attribute_map["ATTR-TITLE"].value for so in content.spec_objects
        }
        assert titles == {"INT06 Need Alpha", "INT06 Req Alpha"}
