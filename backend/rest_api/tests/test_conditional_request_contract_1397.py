"""#1397 gate: the schema and the runtime agree about ``412`` / ``If-Match``.

The generated document advertised a ``412`` on four ``PATCH`` operations while
declaring **no** ``If-Match`` request header anywhere — the contract said "this
call can fail its precondition" without naming the input that triggers it. This
module pins the fix as a bidirectional gate over
:data:`rest_api.conditional_requests.CONDITIONAL_REQUEST_OPERATIONS`:

* every ``(path, method)`` that declares ``412`` is in the allowlist, and every
  allowlist entry declares ``412`` — no undeclared failure, no ghost entry;
* every operation in the allowlist declares an optional ``If-Match`` header
  parameter, and no operation *outside* it does (a header on a route that never
  evaluates it would be the mirror-image lie);
* the six families that deliberately do not support conditional requests
  (``UNSUPPORTED_CONDITIONAL_FAMILIES``) declare no ``412`` at all;
* both router spellings of the TestCase view (``testcases`` and the canonical
  ``test-cases``, #1177) document it — they are the same view, so the duplicate
  is intentional, not copy-paste drift;
* for each of the four ViewSets the ``partial_update`` implementation still
  reaches the ``ETagMixin`` seam.

Behaviour is *not* re-tested here: the 412/400 answers per family are already
covered end-to-end with a real database by
``rest_api.tests.test_workspace_etag_412_1244``,
``rest_api.tests.test_baseline_scope_diff_error_paths_rest``,
``rest_api.tests.test_if_match_parser_1396`` and
``rest_api.tests.test_etag_optimistic_locking_868``. This suite is the cheap,
code-level contract check; duplicating those HTTP round-trips would only make it
slow.
"""
from __future__ import annotations

import inspect

import pytest

from rest_api.conditional_requests import (
    CONDITIONAL_REQUEST_OPERATIONS,
    CONDITIONAL_REQUESTS_DESCRIPTION,
    UNSUPPORTED_CONDITIONAL_FAMILIES,
)

#: Everything drf-spectacular emits under a path item besides HTTP operations.
_NON_OPERATION_KEYS = {"parameters", "summary", "description", "servers", "$ref"}

#: The four ViewSets that implement optimistic locking, and the mixin seam each
#: ``partial_update`` must reach. Requirement/TestCase/Workspace forward the
#: resolved revision into the service's row-locked compare; Baseline (immutable,
#: no version counter) evaluates the tag out of band.
_ETAG_SEAMS = [
    ("RequirementViewSet", "resolve_expected_version"),
    ("TestCaseViewSet", "resolve_expected_version"),
    ("WorkspaceViewSet", "resolve_expected_version"),
    ("BaselineViewSet", "check_if_match"),
]


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    """The generated OpenAPI 3.0 document (same output as GET /api/schema/)."""
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def _operations(schema: dict):
    """Yield ``(path, method, operation)`` for every real HTTP operation."""
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in _NON_OPERATION_KEYS or not isinstance(operation, dict):
                continue
            yield path, method, operation


def _operations_declaring(schema: dict, status_code: str) -> set[tuple[str, str]]:
    """The ``(path, method)`` pairs whose responses include *status_code*."""
    return {
        (path, method)
        for path, method, operation in _operations(schema)
        if status_code in operation.get("responses", {})
    }


def _if_match_parameters(operation: dict) -> list[dict]:
    """The operation's ``If-Match`` header parameters (normally zero or one)."""
    return [
        parameter
        for parameter in operation.get("parameters", []) or []
        if parameter.get("in") == "header" and parameter.get("name") == "If-Match"
    ]


def _operations_declaring_if_match(schema: dict) -> set[tuple[str, str]]:
    return {
        (path, method)
        for path, method, operation in _operations(schema)
        if _if_match_parameters(operation)
    }


# ---------------------------------------------------------------------------
# (a) the allowlist is exactly the set of operations that declare 412
# ---------------------------------------------------------------------------


class TestAllowlistMatchesTheSchema:
    """Bidirectional: no undeclared ``412`` and no allowlist entry without one."""

    def test_allowlist_has_the_expected_five_path_method_pairs(self) -> None:
        """Four ViewSets, five paths — ``testcases`` is routed twice."""
        assert CONDITIONAL_REQUEST_OPERATIONS == {
            ("/api/v1/baselines/{id}/", "patch"),
            ("/api/v1/requirements/{id}/", "patch"),
            ("/api/v1/test-cases/{id}/", "patch"),
            ("/api/v1/testcases/{id}/", "patch"),
            ("/api/v1/workspaces/{id}/", "patch"),
        }

    def test_no_operation_declares_412_without_being_allowlisted(
        self, openapi_schema: dict
    ) -> None:
        declared = _operations_declaring(openapi_schema, "412")
        assert declared - CONDITIONAL_REQUEST_OPERATIONS == set(), (
            "these operations advertise a 412 that the allowlist does not cover"
        )

    def test_every_allowlisted_operation_declares_412(
        self, openapi_schema: dict
    ) -> None:
        declared = _operations_declaring(openapi_schema, "412")
        assert CONDITIONAL_REQUEST_OPERATIONS - declared == set(), (
            "these allowlisted operations no longer declare a 412"
        )

    def test_the_schema_actually_has_five_412_paths(self, openapi_schema: dict) -> None:
        """Regression count for #1397 (was 5 before the fix, stays 5)."""
        assert len(_operations_declaring(openapi_schema, "412")) == 5


# ---------------------------------------------------------------------------
# (b) the header the 412 is conditioned on is declared — and optional
# ---------------------------------------------------------------------------


class TestIfMatchParameterDeclared:
    """A ``412`` without a documented ``If-Match`` is the defect #1397 fixes."""

    def test_every_conditional_operation_declares_the_header(
        self, openapi_schema: dict
    ) -> None:
        declared = _operations_declaring_if_match(openapi_schema)
        assert CONDITIONAL_REQUEST_OPERATIONS - declared == set(), (
            "these operations declare a 412 without declaring the If-Match header"
        )

    def test_the_header_is_optional_on_every_conditional_operation(
        self, openapi_schema: dict
    ) -> None:
        for path in sorted({p for p, _ in CONDITIONAL_REQUEST_OPERATIONS}):
            operation = openapi_schema["paths"][path]["patch"]
            (parameter,) = _if_match_parameters(operation)
            # Omitting the header must stay legal: it is what selects the
            # expected_version body fallback (stale -> 409, not 412).
            assert parameter.get("required", False) is False, path
            assert parameter["schema"]["type"] == "string", path

    def test_the_header_description_is_actionable(
        self, openapi_schema: dict
    ) -> None:
        """The description has to be actionable, not just present.

        All five facts a client needs: what the tag is (``ETag``), that
        comparison is strong, what ``*`` means, that a mismatch is a 412 and a
        malformed value a 400 ``INVALID_IF_MATCH``, and that omitting the header
        falls back to the body's ``expected_version``.
        """
        for path in sorted({p for p, _ in CONDITIONAL_REQUEST_OPERATIONS}):
            operation = openapi_schema["paths"][path]["patch"]
            (parameter,) = _if_match_parameters(operation)
            description = parameter["description"]
            assert "ETag" in description, path
            assert "strong" in description.lower(), path
            assert "``*``" in description, path
            assert "412" in description, path
            assert "400" in description, path
            assert "INVALID_IF_MATCH" in description, path
            assert "expected_version" in description, path

    def test_no_operation_outside_the_allowlist_declares_the_header(
        self, openapi_schema: dict
    ) -> None:
        """The inverse lie: a header on a route that never evaluates it."""
        declared = _operations_declaring_if_match(openapi_schema)
        assert declared - CONDITIONAL_REQUEST_OPERATIONS == set(), (
            "these operations declare If-Match but are not allowlisted as "
            "honouring it; extend rest_api.conditional_requests in the same "
            "change (with a real check_if_match call), or drop the parameter"
        )

    def test_the_412_description_says_what_produced_it(
        self, openapi_schema: dict
    ) -> None:
        operation = openapi_schema["paths"]["/api/v1/requirements/{id}/"]["patch"]
        description = operation["responses"]["412"]["description"].lower()
        assert "if-match" in description
        assert "etag" in description
        # The 409 split must be discoverable too: a body-only stale version is
        # not a 412.
        assert "409" in description


# ---------------------------------------------------------------------------
# (c) the families that do NOT support conditional requests stay silent
# ---------------------------------------------------------------------------


class TestUnsupportedFamiliesDoNotAdvertise412:
    """Adding ETag to these would be a behaviour change, not a contract fix."""

    def test_the_unsupported_map_covers_six_families(self) -> None:
        assert len(UNSUPPORTED_CONDITIONAL_FAMILIES) == 6
        for reason in UNSUPPORTED_CONDITIONAL_FAMILIES.values():
            assert reason.strip(), "every family needs a one-line reason"

    @pytest.mark.parametrize("path", sorted(UNSUPPORTED_CONDITIONAL_FAMILIES))
    def test_family_declares_no_412(self, openapi_schema: dict, path: str) -> None:
        assert path in openapi_schema["paths"], f"{path} vanished from the schema"
        operation = openapi_schema["paths"][path]["patch"]
        assert "412" not in operation["responses"], path
        assert _if_match_parameters(operation) == [], path

    @pytest.mark.parametrize("path", sorted(UNSUPPORTED_CONDITIONAL_FAMILIES))
    def test_family_does_not_emit_an_etag_contract(
        self, openapi_schema: dict, path: str
    ) -> None:
        """A schema-declared ``ETag`` header here would advertise the very
        predicate these routes do not implement. (The generated document does
        not declare the ``ETag`` response header on any route, so this is the
        negative guard for the day one is added to a non-conditional family.)
        """
        for method in ("get", "patch"):
            operation = openapi_schema["paths"][path].get(method)
            if operation is None:
                continue
            headers = {
                header.lower()
                for header in operation.get("responses", {})
                .get("200", {})
                .get("headers", {})
            }
            assert "etag" not in headers, (path, method)

    def test_the_supported_set_and_the_unsupported_map_are_disjoint(self) -> None:
        supported_paths = {path for path, _ in CONDITIONAL_REQUEST_OPERATIONS}
        assert supported_paths & set(UNSUPPORTED_CONDITIONAL_FAMILIES) == set()


# ---------------------------------------------------------------------------
# (d) the TestCase alias pair is intentional
# ---------------------------------------------------------------------------


class TestTestCaseAliasPair:
    """``TestCaseViewSet`` is registered twice (``rest_api/urls.py``).

    ``testcases`` is the legacy spelling kept because ``frontend/src/api/
    testcases.ts`` and older MCP callers use it; ``test-cases`` is the canonical
    kebab-case route added in #1177. drf-spectacular documents each registration
    as its own path, so both must carry the same precondition contract — this is
    the one legitimate duplicate in the allowlist.
    """

    ALIASES = ("/api/v1/testcases/{id}/", "/api/v1/test-cases/{id}/")

    @pytest.mark.parametrize("path", ALIASES)
    def test_alias_declares_412_and_the_header(
        self, openapi_schema: dict, path: str
    ) -> None:
        operation = openapi_schema["paths"][path]["patch"]
        assert "412" in operation["responses"], path
        (parameter,) = _if_match_parameters(operation)
        assert parameter.get("required", False) is False, path

    def test_both_aliases_are_allowlisted_together(self) -> None:
        assert {(path, "patch") for path in self.ALIASES} <= (
            CONDITIONAL_REQUEST_OPERATIONS
        )


# ---------------------------------------------------------------------------
# (e) runtime parity — the decorators describe code that really runs
# ---------------------------------------------------------------------------


class TestRuntimeParity:
    """The declared header must reach the mixin that enforces it.

    Code-level only: the four ``partial_update`` implementations are checked
    against the ``ETagMixin`` seam they use. The end-to-end 412 answers are
    covered by ``test_workspace_etag_412_1244``,
    ``test_baseline_scope_diff_error_paths_rest`` and
    ``test_if_match_parser_1396`` (see this module's docstring).
    """

    @pytest.mark.parametrize(("viewset_name", "seam"), _ETAG_SEAMS)
    def test_partial_update_reaches_the_etag_mixin(
        self, viewset_name: str, seam: str
    ) -> None:
        from rest_api import views
        from rest_api.mixins.etag import ETagMixin

        viewset_cls = getattr(views, viewset_name)
        assert issubclass(viewset_cls, ETagMixin), viewset_name

        source = inspect.getsource(viewset_cls.partial_update)
        assert seam in source, (
            f"{viewset_name}.partial_update no longer calls {seam}(); the "
            "declared If-Match parameter and 412 response would be a lie"
        )

    def test_the_conditional_description_is_published(
        self, openapi_schema: dict
    ) -> None:
        """Deliverable 3: the summary comes from the allowlist module."""
        assert CONDITIONAL_REQUESTS_DESCRIPTION in openapi_schema["info"]["description"]
