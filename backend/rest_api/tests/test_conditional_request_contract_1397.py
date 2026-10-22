"""#1397 gate: the schema and the runtime agree about ``412`` / ``If-Match``.

The generated document advertised a ``412`` on four ``PATCH`` operations while
declaring **no** ``If-Match`` request header anywhere — the contract said "this
call can fail its precondition" without naming the input that triggers it. This
module pins the fix as a bidirectional gate over
:data:`rest_api.conditional_requests.CONDITIONAL_REQUEST_OPERATIONS`:

* every ``(path, method)`` that declares ``412`` is in the allowlist, and every
  allowlist entry declares ``412`` — no undeclared failure, no ghost entry;
* every operation in the allowlist declares an optional ``If-Match`` header
  parameter, and no operation *outside* the two documented sets does (a header
  on a route that never evaluates it would be the mirror-image lie);
* the six core artifact families that deliberately do not support conditional
  requests (``UNSUPPORTED_CONDITIONAL_FAMILIES``) declare no ``412`` and no
  ``If-Match`` parameter either;
* the five ``POST`` actions that evaluate ``If-Match`` against the *workflow*
  revision are recorded in ``CONDITIONAL_ACTION_OPERATIONS``, declare no ``412``
  (they answer ``409``) and are not silently absent from both maps;
* both router spellings of the TestCase view (``testcases`` and the canonical
  ``test-cases``, #1177) document it — they are the same view, so the duplicate
  is intentional, not copy-paste drift;
* each of the four ``PATCH`` implementations *really invokes* the ``ETagMixin``
  seam (the mixin method is patched and the view is driven with a request),
  while an unsupported family's ``PATCH`` does not — a source-substring match
  could not tell a real call from a mention in a comment.

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

import uuid
from unittest import mock

import pytest
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from rest_api.conditional_requests import (
    CONDITIONAL_ACTION_OPERATIONS,
    CONDITIONAL_REQUEST_OPERATIONS,
    CONDITIONAL_REQUESTS_DESCRIPTION,
    UNSUPPORTED_CONDITIONAL_FAMILIES,
)
from rest_api.mixins.etag import ETagMixin

#: Everything drf-spectacular emits under a path item besides HTTP operations.
_NON_OPERATION_KEYS = {"parameters", "summary", "description", "servers", "$ref"}

#: The six core artifact families whose detail ``PATCH`` stays non-conditional.
_CORE_ARTIFACT_FAMILIES = {
    "/api/v1/adrs/{id}/",
    "/api/v1/architecture/{id}/",
    "/api/v1/change-requests/{id}/",
    "/api/v1/issues/{id}/",
    "/api/v1/needs/{id}/",
    "/api/v1/risks/{id}/",
}

#: The five ``POST`` implementations that evaluate ``If-Match`` (six paths: the
#: ChangeRequest transition is routed twice, see docs §7).
_ACTION_PATHS = {
    "/api/v1/adrs/{id}/supersede/",
    "/api/v1/change-requests/{id}/transition/",
    "/api/v1/changerequests/{id}/transition/",
    "/api/v1/goals/{id}/outdate/",
    "/api/v1/goals/{id}/reactivate/",
    "/api/v1/main-goals/{id}/approve/",
}


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
        """The inverse lie: a header on a route that never evaluates it.

        The ``POST`` actions in ``CONDITIONAL_ACTION_OPERATIONS`` are allowed to
        declare it too — they do evaluate it (against the workflow revision) —
        but they must not declare ``412``; that is asserted in
        ``TestActionOperations``.
        """
        declared = _operations_declaring_if_match(openapi_schema)
        allowed = CONDITIONAL_REQUEST_OPERATIONS | set(CONDITIONAL_ACTION_OPERATIONS)
        assert declared - allowed == set(), (
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

    def test_the_unsupported_map_covers_the_six_core_artifact_families(self) -> None:
        """The prose claims the six core families — the map must contain them.

        ``glossary`` is artifact-shaped but not one of the six, and the legacy
        ``changerequests`` spelling is the same view as ``change-requests``
        (docs §7); both are kept so neither escapes the gate.
        """
        assert _CORE_ARTIFACT_FAMILIES <= set(UNSUPPORTED_CONDITIONAL_FAMILIES)
        assert "/api/v1/glossary/{id}/" in UNSUPPORTED_CONDITIONAL_FAMILIES
        assert "/api/v1/changerequests/{id}/" in UNSUPPORTED_CONDITIONAL_FAMILIES
        for reason in UNSUPPORTED_CONDITIONAL_FAMILIES.values():
            assert reason.strip(), "every family needs a one-line reason"

    def test_every_unsupported_path_declares_neither_412_nor_if_match(
        self, openapi_schema: dict
    ) -> None:
        """Exhaustive over the map, not only over the parametrized rows above."""
        for path in sorted(UNSUPPORTED_CONDITIONAL_FAMILIES):
            assert path in openapi_schema["paths"], f"{path} vanished from the schema"
            operation = openapi_schema["paths"][path]["patch"]
            assert "412" not in operation.get("responses", {}), path
            assert _if_match_parameters(operation) == [], path

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
# (c2) the POST actions that evaluate If-Match — 400/409, never 412
# ---------------------------------------------------------------------------


class TestActionOperations:
    """Five ``POST`` actions guard the workflow revision, not the entity ETag.

    They are neither "supported PATCH" (no ``412``) nor "ignore If-Match" (they
    evaluate it), so they need their own machine-checkable set. The gate below
    makes that middle ground impossible: an action operation either declares the
    header or is explicitly mapped, and no action ever advertises ``412``.
    """

    def test_the_action_map_names_the_five_implementations_plus_the_alias(
        self,
    ) -> None:
        assert set(CONDITIONAL_ACTION_OPERATIONS) == {
            (path, "post") for path in _ACTION_PATHS
        }
        # Five view implementations, six paths: ChangeRequest is routed twice.
        assert len({path for path, _ in CONDITIONAL_ACTION_OPERATIONS}) == 6
        for reason in CONDITIONAL_ACTION_OPERATIONS.values():
            assert reason.strip(), "every action needs its contract spelled out"

    @pytest.mark.parametrize("path", sorted(_ACTION_PATHS))
    def test_action_operation_exists_and_declares_no_412(
        self, openapi_schema: dict, path: str
    ) -> None:
        """Their mismatch answer is 409 CONFLICT (CR-08), so a 412 would lie.

        The document names the ``400`` they can answer; the ``409`` is recorded
        in ``CONDITIONAL_ACTION_OPERATIONS`` and in
        ``docs/api/REST-CONVENTIONS.md`` §1 rather than declared as a response
        here, because these routes predate this contract and their response set
        is not part of the drift gate.
        """
        assert path in openapi_schema["paths"], f"{path} vanished from the schema"
        operation = openapi_schema["paths"][path]["post"]
        assert "412" not in operation.get("responses", {}), path
        assert "400" in operation.get("responses", {}), path

    @pytest.mark.parametrize("path", sorted(_ACTION_PATHS))
    def test_action_either_declares_if_match_or_is_named_in_the_map(
        self, openapi_schema: dict, path: str
    ) -> None:
        """No silent middle ground between "documented" and "declared"."""
        operation = openapi_schema["paths"][path]["post"]
        declared = bool(_if_match_parameters(operation))
        mapped = (path, "post") in CONDITIONAL_ACTION_OPERATIONS
        assert declared or mapped, (
            f"{path} evaluates If-Match at runtime (see "
            "rest_api/views.py special-route resolvers) but is neither documented "
            "with the parameter nor named in CONDITIONAL_ACTION_OPERATIONS"
        )

    def test_action_paths_are_not_in_the_patch_allowlist(self) -> None:
        assert {path for path, _ in CONDITIONAL_REQUEST_OPERATIONS} & _ACTION_PATHS == (
            set()
        )


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
# (e) runtime parity — the mixin method is really *invoked*, not merely named
# ---------------------------------------------------------------------------

#: A syntactically valid pk; every service call is patched, so it is never
#: parsed.
_PK = str(uuid.uuid4())


def _request(data: dict, header: str | None = None) -> Request:
    """A DRF request with *data* and, optionally, an ``If-Match`` header."""
    django_request = APIRequestFactory().patch("/", data, format="json")
    if header is not None:
        django_request.META["HTTP_IF_MATCH"] = header
    # A directly-constructed DRF Request has no parsers; the real view is
    # normally handed one by ``initialize_request``.
    return Request(django_request, parsers=[JSONParser()])


class TestRuntimeParity:
    """The declared header must reach the mixin that enforces it.

    Real invocation, not a source-substring match: the ``ETagMixin`` seam is
    patched and ``partial_update`` is actually driven with a request. A name
    that only appears in a comment, or a call that is unreachable, fails these
    tests. The service call is made to raise so the invocation stops right after
    the seam — the HTTP outcome is covered by the end-to-end suites named in the
    module docstring.
    """

    def test_requirement_patch_invokes_the_seam(self) -> None:
        from rest_api import views

        view = views.RequirementViewSet()
        with (
            mock.patch.object(views, "get_auth_context", return_value=object()),
            mock.patch.object(
                views.RequirementViewSet,
                "_validate_patch_payload",
                return_value=None,
            ),
            mock.patch.object(views.RequirementViewSet, "_svc") as svc,
            mock.patch.object(
                ETagMixin, "resolve_expected_version", autospec=True, return_value=None
            ) as seam,
        ):
            svc.return_value.update_requirement.side_effect = RuntimeError("stop")
            view.partial_update(_request({"description": "x"}), pk=_PK)

        seam.assert_called_once()

    def test_test_case_patch_invokes_the_seam(self) -> None:
        from rest_api import views

        view = views.TestCaseViewSet()
        with (
            mock.patch.object(views, "get_auth_context", return_value=object()),
            mock.patch.object(
                views.TestCaseViewSet, "_validate_patch_payload", return_value=None
            ),
            mock.patch.object(views.TestCaseViewSet, "_svc") as svc,
            mock.patch.object(
                ETagMixin, "resolve_expected_version", autospec=True, return_value=None
            ) as seam,
        ):
            svc.return_value.update_test_case.side_effect = RuntimeError("stop")
            view.partial_update(_request({"description": "x"}), pk=_PK)

        seam.assert_called_once()

    def test_workspace_patch_invokes_the_seam(self) -> None:
        from rest_api import views

        view = views.WorkspaceViewSet()
        with (
            mock.patch.object(views, "get_auth_context", return_value=object()),
            mock.patch.object(views.WorkspaceViewSet, "_svc") as svc,
            mock.patch.object(
                ETagMixin, "resolve_expected_version", autospec=True, return_value=None
            ) as seam,
        ):
            # The empty patch reaches the "no recognised field" branch, whose
            # read happens *after* the seam was resolved.
            svc.return_value.get_workspace.side_effect = RuntimeError("stop")
            view.partial_update(_request({}), pk=_PK)

        seam.assert_called_once()

    def test_baseline_patch_invokes_the_seam(self) -> None:
        from rest_api import views

        view = views.BaselineViewSet()
        with (
            mock.patch.object(views, "get_auth_context", return_value=object()),
            mock.patch.object(views.BaselineViewSet, "_svc") as svc,
            mock.patch.object(
                ETagMixin, "check_if_match", autospec=True, return_value=None
            ) as seam,
        ):
            svc.return_value.get_baseline.return_value = object()
            view.partial_update(_request({}, header='"1"'), pk=_PK)

        seam.assert_called_once()

    def test_unsupported_family_patch_never_invokes_the_seam(self) -> None:
        """A ``PATCH`` on a non-conditional family ignores the header entirely."""
        from rest_api import views

        view = views.AdrViewSet()
        with (
            mock.patch.object(views, "get_auth_context", return_value=object()),
            mock.patch.object(
                views.AdrViewSet, "_validate_patch_payload", return_value=None
            ),
            mock.patch.object(views.AdrViewSet, "_svc") as svc,
            mock.patch.object(
                ETagMixin, "resolve_expected_version", autospec=True
            ) as seam,
        ):
            svc.return_value.update_adr.side_effect = RuntimeError("stop")
            view.partial_update(_request({"description": "x"}, header='"1"'), pk=_PK)

        # The request really reached the write path — the assertion above is not
        # passing because of an early 400.
        svc.return_value.update_adr.assert_called_once()
        seam.assert_not_called()

    def test_the_conditional_description_is_published(
        self, openapi_schema: dict
    ) -> None:
        """Deliverable 3: the summary comes from the allowlist module."""
        assert CONDITIONAL_REQUESTS_DESCRIPTION in openapi_schema["info"]["description"]
