"""#1388 gate: the OpenAPI document is complete and trustworthy.

Before this change a generation run emitted **124** ``Error [<View>]: unable to
guess serializer … Ignoring view for now`` errors (123 after #1439 gave
``ApiKeyViewSet`` a serializer) over just as many distinct view classes. Those
operations were not dropped from ``paths`` — they were *emptied*: the base
``AutoSchema`` returned ``None``, ``is_basic_type(None)`` is ``True`` in
drf-spectacular 0.30, and every such operation was published as
``200: {description: "No response body"}`` with no request body. The document
claimed 357 paths and 528 operations, but **123 of them described nothing**.
It also carried 9 ``operationId`` collisions and 23 ``could not derive type of
path parameter`` warnings.

Measured on 2026-10-21 (``python manage.py spectacular``):

========================================  ========  =======
Metric                                    before    after
========================================  ========  =======
``unable to guess serializer`` errors         124        0
``could not derive type`` path warnings        23        0
``operationId`` collision warnings              9        0
``could not resolve authenticator`` warnings  148        0
paths                                          357      357
operations                                     528      528
operations whose GET/POST carried no model     123        0
========================================  ========  =======

The path/operation counts are unchanged *on purpose*: the defect was empty
contracts, not missing routes. Every one of those operations now carries either
a real serializer or the explicit, marked permissive fallback
(``x-reqlo-untyped: true``) that this gate pairs with a deliberate allowlist.

Review hardening (same issue, findings F3-F13)
----------------------------------------------

The allowlist itself was a soft gate in three ways, all fixed here:

* the path/operation floors (``>= 357`` / ``>= 528``) let a dropped route hide
  behind an added one — the inventory is now compared **exactly** against the
  committed manifest in ``fixtures/openapi_operations_manifest.json``;
* ``marked > 0`` accepted an unmarked fallback as long as one other operation
  was marked — every fallback-shaped schema must now carry the marker, and the
  number of marked operations must equal the per-view usage the generator
  recorded (``untyped_operation_count``);
* the usage record was keyed by *bare* class name, so a new ``VersionView`` in
  another module would silently satisfy the allowlist — keys are now
  ``<module>.<qualname>`` on both sides.

The review also removed 13 false or cheaply fixable entries (113 -> 100): six
views that *did* run a serializer but were plain ``APIView``s without a
``serializer_class``, the two CSV routes, the suggestion inbox, the version and
user-management endpoints.

The assertions below run the generator once and read drf-spectacular's own
``GENERATOR_STATS`` warning/error collection (not the management command's
stderr), because that is the same collection the CLI summarises and it is
reliable under ``-q``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from drf_spectacular.drainage import GENERATOR_STATS, reset_generator_stats
from drf_spectacular.generators import SchemaGenerator

from rest_api.schema import (
    UNTYPED_VIEW_ALLOWLIST,
    untyped_operation_count,
    untyped_operations_used,
    untyped_views_used,
)

_NON_OPERATION_KEYS = {"parameters", "summary", "description", "servers", "$ref"}

MANIFEST_PATH = Path(__file__).with_name("fixtures") / "openapi_operations_manifest.json"

#: The routes a disambiguation refactor must never lose.
_CRITICAL_PATHS = (
    "/api/v1/baselines/",
    "/api/v1/baselines/{id}/",
    "/api/v1/api-keys/",
    "/api/v1/requirements/{id}/",
    "/api/v1/workspaces/{id}/",
    "/api/v1/workspaces/{workspace_id}/memory/search/",
    "/api/v1/admin/health/",
    "/api/v1/admin/theme-palettes/",
    "/api/v1/admin/banners/global/",
    "/api/v1/workspaces/{workspace_id}/banner/",
    "/api/v1/public/banners/login/",
    "/api/v1/admin/rate-limits/",
)

#: ``operationId`` values that were explicitly disambiguated by #1388.
_EXPLICIT_OPERATION_IDS = {
    "attribute_catalog_list",
    "attribute_defaults_list",
    "attribute_migration_runs_list",
    "diagrams_list",
    "icds_list",
    "interviews_list",
    "requirements_acceptance_criteria_list",
    "workflow_defaults_list",
    "api_keys_list",
}

#: Operations that *always* answer a 4xx, so a 2xx entry would be a lie.
#: ``Baseline`` is immutable: ``PATCH`` is documented as 405 by design and the
#: runtime never returns 2xx (see ``BaselineViewSet.partial_update``).
_ALWAYS_4XX_OPERATIONS = {
    ("/api/v1/baselines/{id}/", "patch"),
}

#: Views deliberately typed by #1388; they must not silently regress to the
#: permissive fallback.
_TYPED_BY_1388 = {
    "GlobalBannerView",
    "GlobalRateLimitsView",
    "PublicLoginBannerView",
    "RateLimitsView",
    "SystemHealthView",
    "TenantThemeDefaultView",
    "ThemePaletteDetailView",
    "ThemePaletteExportView",
    "ThemePaletteListView",
    "UserThemePreferenceView",
    "WorkspaceBannerView",
    "WorkspaceMemorySearchView",
}

#: Views typed by this review: each had an allowlist entry that is no longer
#: needed — either the stated reason was false (the view *did* run a
#: serializer) or the shape was cheap to state. They must never reappear on the
#: fallback list.
_TYPED_BY_API_CONTRACT_REVIEW = {
    "ArtifactCommentsView",
    "LlmSettingsView",
    "PromptTemplateView",
    "ReviewPolicyView",
    "ContextGraphSettingsView",
    "CsvExportView",
    "CsvImportView",
    "VersionView",
    "UserViewSet",
    "SuggestionAcceptView",
    "SuggestionListView",
    "SuggestionRejectView",
    "scope_preview",
}

#: Success statuses the untyped fallback publishes per method (#1388/F4).
#: A hand-written ``APIView`` decides its concrete code in the view body, so
#: publishing one guess was wrong for 95 write operations; the documented set
#: is what the runtime may actually answer.
_FALLBACK_SUCCESS_STATUSES = {
    "post": {"200", "201"},
    "delete": {"200", "204"},
}


def _load_manifest() -> set[tuple[str, str]]:
    """Read the committed (path, method) inventory."""
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {(path, method) for path, method in document["operations"]}


@pytest.fixture(scope="module")
def generated() -> dict:
    """Generate the document once and capture the generator's own diagnostics."""
    reset_generator_stats()
    schema = SchemaGenerator().get_schema(request=None, public=True)
    # ``GeneratorStats`` is a process-wide singleton; reset above scopes these
    # caches to this generation. Both dicts are message -> occurrence count.
    return {
        "schema": schema,
        "errors": tuple(GENERATOR_STATS._error_cache),  # noqa: SLF001
        "warnings": tuple(GENERATOR_STATS._warn_cache),  # noqa: SLF001
        "used": untyped_views_used(),
        "operations": untyped_operations_used(),
        "operation_count": untyped_operation_count(),
    }


def _operations(schema: dict):
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in _NON_OPERATION_KEYS or not isinstance(operation, dict):
                continue
            yield path, method, operation


def _allowlisted(view_name: str) -> bool:
    """Whether *view_name* is allowlisted, matched on the qualified suffix."""
    return any(
        key == view_name or key.endswith(f".{view_name}")
        for key in UNTYPED_VIEW_ALLOWLIST
    )


def _looks_like_fallback(schema: object) -> bool:
    """Whether *schema* is the permissive #1388 fallback (marker or not).

    Deliberately keyed on the description/``additionalProperties`` pair rather
    than the marker: the point of the gate is to catch a fallback that lost its
    ``x-reqlo-untyped`` marker, so the detector must not depend on it.
    """
    if not isinstance(schema, dict):
        return False
    description = schema.get("description") or ""
    return (
        schema.get("type") == "object"
        and schema.get("additionalProperties") is True
        and "Permissive fallback" in description
    )


def _iter_reachable_schemas(node: object, document: dict, seen: set[int] | None = None):
    """Yield every schema dict reachable from *node*, following ``$ref``.

    A paginated untyped list publishes its fallback through the
    ``Paginated…`` component (``results.items``), so an inline-only scan would
    silently miss it. Following one level of ``#/components/schemas/`` refs is
    enough to reach those item schemas without resolving the whole document.
    """
    seen = set() if seen is None else seen
    stack: list[object] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if id(current) in seen:
                continue
            seen.add(id(current))
            yield current
            ref = current.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                component = (
                    (document.get("components") or {}).get("schemas", {}).get(
                        ref.rsplit("/", 1)[-1]
                    )
                )
                if component is not None:
                    stack.append(component)
            stack.extend(
                value for value in current.values() if isinstance(value, (dict, list))
            )
        elif isinstance(current, list):
            stack.extend(
                value for value in current if isinstance(value, (dict, list))
            )


def _operation_schemas(operation: dict, document: dict):
    """Yield the schema dicts behind an operation's request and responses."""
    roots: list[object] = [operation.get("responses") or {}, operation.get("requestBody") or {}]
    seen: set[int] = set()
    for root in roots:
        yield from _iter_reachable_schemas(root, document, seen)


def _has_fallback_response(operation: dict, document: dict) -> bool:
    """Whether the operation's *responses* fall back (request-only is exempt).

    ``LoginView`` declares its 200 explicitly and only falls back for the
    request body, so its success status is knowable and correct — the F4 rule
    ("publish every status the view may answer") applies to a fallback
    *response*, which is the one that cannot be typed.
    """
    seen: set[int] = set()
    return any(
        _looks_like_fallback(schema)
        for schema in _iter_reachable_schemas(
            operation.get("responses") or {}, document, seen
        )
    )


def _marked_operations(schema: dict) -> set[tuple[str, str]]:
    """Every operation carrying at least one marked fallback schema."""
    marked: set[tuple[str, str]] = set()
    for path, method, operation in _operations(schema):
        if any(
            candidate.get("x-reqlo-untyped") is True
            for candidate in _operation_schemas(operation, schema)
        ):
            marked.add((path, method))
    return marked


# ---------------------------------------------------------------------------
# (a) no serializer-guess errors
# ---------------------------------------------------------------------------


class TestNoSerializerGuessErrors:
    """A view without a serializer must be allowlisted, not error-logged."""

    def test_generator_emits_no_serializer_guess_error(self, generated: dict) -> None:
        offenders = [e for e in generated["errors"] if "unable to guess serializer" in e]
        assert offenders == [], (
            "these views still fall back without being allowlisted; either add "
            "a serializer or add a reason to UNTYPED_VIEW_ALLOWLIST:\n"
            + "\n".join(offenders)
        )

    def test_generator_emits_no_errors_at_all(self, generated: dict) -> None:
        assert generated["errors"] == ()

    def test_generator_emits_no_warnings_at_all(self, generated: dict) -> None:
        assert generated["warnings"] == ()


# ---------------------------------------------------------------------------
# (b) path parameter types are explicit
# ---------------------------------------------------------------------------


class TestPathParameterTypes:
    def test_no_underivable_path_parameters(self, generated: dict) -> None:
        offenders = [
            w
            for w in generated["warnings"]
            if "could not derive type of path parameter" in w
        ]
        assert offenders == [], (
            "declare the parameter explicitly with @extend_schema or a typed "
            "converter:\n" + "\n".join(offenders)
        )


# ---------------------------------------------------------------------------
# (c) operationId collisions are gone
# ---------------------------------------------------------------------------


class TestOperationIds:
    def test_no_collision_warnings(self, generated: dict) -> None:
        offenders = [w for w in generated["warnings"] if "has collisions" in w]
        assert offenders == []

    def test_no_duplicate_operation_id_in_the_document(self, generated: dict) -> None:
        ids = [op["operationId"] for _, _, op in _operations(generated["schema"])]
        duplicates = {value for value in ids if ids.count(value) > 1}
        assert duplicates == set()

    def test_the_disambiguated_list_operations_keep_their_explicit_id(
        self, generated: dict
    ) -> None:
        ids = {op["operationId"] for _, _, op in _operations(generated["schema"])}
        assert _EXPLICIT_OPERATION_IDS - ids == set()


# ---------------------------------------------------------------------------
# (d) nothing was lost — the inventory is exact
# ---------------------------------------------------------------------------


class TestNoOperationLost:
    def test_operation_inventory_matches_the_committed_manifest(
        self, generated: dict
    ) -> None:
        """Exact equality in both directions (review finding m8).

        A floor let a dropped route pass whenever another one was added. The
        manifest is the committed inventory: changing a route now requires
        updating it deliberately (see its ``_comment``), which is the point.
        """
        actual = {(path, method) for path, method, _ in _operations(generated["schema"])}
        expected = _load_manifest()
        assert actual == expected, (
            "the published operation inventory drifted from "
            f"{MANIFEST_PATH.name}; missing: {sorted(expected - actual)}; "
            f"unexpected: {sorted(actual - expected)}"
        )

    def test_manifest_is_not_empty(self) -> None:
        assert len(_load_manifest()) > 0

    @pytest.mark.parametrize("path", _CRITICAL_PATHS)
    def test_critical_path_is_present(self, generated: dict, path: str) -> None:
        assert path in generated["schema"]["paths"], f"{path} vanished from the schema"


# ---------------------------------------------------------------------------
# (e) the fallback allowlist is exact
# ---------------------------------------------------------------------------


class TestUntypedAllowlist:
    def test_every_used_fallback_is_allowlisted(self, generated: dict) -> None:
        missing = generated["used"] - set(UNTYPED_VIEW_ALLOWLIST)
        assert missing == set(), (
            "these views used the permissive fallback without a deliberate "
            "allowlist entry — add a serializer or document the reason:\n"
            f"{sorted(missing)}"
        )

    def test_every_allowlisted_view_actually_used_the_fallback(
        self, generated: dict
    ) -> None:
        stale = set(UNTYPED_VIEW_ALLOWLIST) - generated["used"]
        assert stale == set(), (
            "these allowlist entries no longer fall back (a serializer was "
            "added) — remove them so the list stays a gate:\n"
            f"{sorted(stale)}"
        )

    def test_every_allowlist_entry_has_a_reason(self) -> None:
        for view, reason in UNTYPED_VIEW_ALLOWLIST.items():
            assert isinstance(reason, str) and reason.strip(), view

    def test_allowlist_keys_are_module_qualified(self) -> None:
        """A bare key cannot distinguish two same-named views (finding m6)."""
        bare = [
            key
            for key in UNTYPED_VIEW_ALLOWLIST
            if "." not in key
        ]
        assert bare == [], (
            "allowlist keys must be '<module>.<qualname>' so a same-named class "
            f"in another module cannot satisfy them; got {bare}"
        )

    def test_high_value_views_are_typed_not_allowlisted(self) -> None:
        regressions = {
            view
            for view in _TYPED_BY_1388 | _TYPED_BY_API_CONTRACT_REVIEW
            if _allowlisted(view)
        }
        assert regressions == set()

    def test_the_review_typed_views_left_the_allowlist(self, generated: dict) -> None:
        """The six false-reason entries plus the cheaply typed ones (F5/M2)."""
        still_falling_back = {
            view
            for view in _TYPED_BY_API_CONTRACT_REVIEW
            if any(key.endswith(f".{view}") for key in generated["used"])
        }
        assert still_falling_back == set()


# ---------------------------------------------------------------------------
# (f) every operation documents a success response
# ---------------------------------------------------------------------------


class TestSuccessResponses:
    def test_every_operation_has_responses(self, generated: dict) -> None:
        missing = [
            (path, method)
            for path, method, operation in _operations(generated["schema"])
            if not operation.get("responses")
        ]
        assert missing == []

    def test_every_operation_has_a_2xx_except_the_documented_always_4xx_set(
        self, generated: dict
    ) -> None:
        without_2xx = {
            (path, method)
            for path, method, operation in _operations(generated["schema"])
            if not any(code.startswith("2") for code in operation["responses"])
        }
        assert without_2xx == set(_ALWAYS_4XX_OPERATIONS), (
            "an operation without a 2xx must be a deliberate, documented "
            "always-fails route; got "
            f"{sorted(without_2xx - set(_ALWAYS_4XX_OPERATIONS))}"
        )

    def test_untyped_writes_publish_the_statuses_the_runtime_can_answer(
        self, generated: dict
    ) -> None:
        """F4: the fallback no longer asserts one possibly-wrong success code."""
        schema = generated["schema"]
        offenders: dict[tuple[str, str], set[str]] = {}
        for path, method, operation in _operations(schema):
            expected = _FALLBACK_SUCCESS_STATUSES.get(method)
            if not expected or not _has_fallback_response(operation, schema):
                continue
            advertised = {
                code for code in operation["responses"] if code.startswith("2")
            }
            if advertised != expected:
                offenders[(path, method)] = advertised
        assert offenders == {}, (
            "untyped writes must advertise exactly "
            f"{_FALLBACK_SUCCESS_STATUSES}; got {offenders}"
        )

    def test_the_review_acceptance_routes_advertise_201(self, generated: dict) -> None:
        """Acceptance for F4: both named create routes publish 201."""
        schema = generated["schema"]
        for path in (
            "/api/v1/attribute-catalog/",
            "/api/v1/artifacts/{artifact_id}/comments/",
        ):
            operation = schema["paths"][path]["post"]
            assert "201" in operation["responses"], (
                f"POST {path} answers 201 at runtime but the schema says "
                f"{sorted(operation['responses'])}"
            )


# ---------------------------------------------------------------------------
# (g) the marker cannot be lost silently (F4/m8)
# ---------------------------------------------------------------------------


class TestUntypedMarker:
    def test_every_fallback_schema_is_marked(self, generated: dict) -> None:
        """No unmarked fallback may exist — ``marked > 0`` was too weak.

        Walks the whole document (paths and components), so a fallback nested
        inside a paginated envelope is covered as well.
        """
        schema = generated["schema"]
        seen: set[int] = set()
        roots = (
            schema.get("paths", {}),
            (schema.get("components") or {}).get("schemas", {}),
        )
        unmarked = [
            (node.get("description") or "")[:120]
            for root in roots
            for node in _iter_reachable_schemas(root, schema, seen)
            if _looks_like_fallback(node) and node.get("x-reqlo-untyped") is not True
        ]
        assert unmarked == [], (
            "these fallback schemas lost the x-reqlo-untyped marker:\n"
            + "\n".join(unmarked)
        )

    def test_marked_operation_count_matches_the_recorded_usage(
        self, generated: dict
    ) -> None:
        """The document's marked operations == what the generator recorded."""
        marked = _marked_operations(generated["schema"])
        expected = generated["operation_count"]
        assert expected > 0
        assert len(marked) == expected, (
            f"the document marks {len(marked)} fallback operations but the "
            f"allowlisted views produced {expected}"
        )
        assert expected == sum(len(ops) for ops in generated["operations"].values())

    def test_every_allowlisted_view_contributed_at_least_one_fallback(
        self, generated: dict
    ) -> None:
        empty = {
            view for view, ops in generated["operations"].items() if not ops
        }
        assert empty == set()


# ---------------------------------------------------------------------------
# (h) the conditional-request response half is published (F3)
# ---------------------------------------------------------------------------


#: Operations whose responses carry an ``ETag`` header, mapped to the statuses
#: that must declare it. Covers every route the ``If-Match`` 412 set applies
#: to, plus the baseline 201 create (which is immutable afterwards, so its
#: create response is the only place a client can learn the tag).
_ETAG_HEADER_OPERATIONS = {
    ("/api/v1/requirements/{id}/", "get"): {"200"},
    ("/api/v1/requirements/{id}/", "patch"): {"200"},
    ("/api/v1/testcases/{id}/", "get"): {"200"},
    ("/api/v1/testcases/{id}/", "patch"): {"200"},
    ("/api/v1/workspaces/{id}/", "get"): {"200"},
    ("/api/v1/workspaces/{id}/", "patch"): {"200"},
    ("/api/v1/baselines/{id}/", "get"): {"200"},
    ("/api/v1/baselines/", "post"): {"201"},
    ("/api/v1/workspaces/{workspace_pk}/baselines/", "post"): {"201"},
}


class TestEtagResponseHeader:
    def test_each_etag_route_declares_the_response_header(self, generated: dict) -> None:
        schema = generated["schema"]
        missing: list[str] = []
        for (path, method), statuses in _ETAG_HEADER_OPERATIONS.items():
            operation = schema["paths"].get(path, {}).get(method)
            assert operation is not None, f"{method.upper()} {path} is missing"
            for code in statuses:
                headers = operation["responses"].get(code, {}).get("headers") or {}
                if "ETag" not in headers:
                    missing.append(f"{method.upper()} {path} -> {code}")
        assert missing == []

    def test_no_response_declares_an_etag_on_a_non_etag_route(
        self, generated: dict
    ) -> None:
        """The header is declared per route, not injected globally."""
        offenders = [
            f"{method.upper()} {path}"
            for path, method, operation in _operations(generated["schema"])
            for response in operation["responses"].values()
            if isinstance(response, dict) and "ETag" in (response.get("headers") or {})
            # The same view is published under several router spellings.
            if (path.replace("test-cases", "testcases"), method)
            not in _ETAG_HEADER_OPERATIONS
        ]
        assert offenders == []


# ---------------------------------------------------------------------------
# (i) paginated / media-type metadata the review found missing (F6, M3)
# ---------------------------------------------------------------------------


class TestKnowableMetadata:
    def test_suggestions_list_publishes_its_parameters_and_envelope(
        self, generated: dict
    ) -> None:
        operation = generated["schema"]["paths"]["/api/v1/suggestions/"]["get"]
        names = {p["name"] for p in operation.get("parameters") or []}
        assert {"workspace_id", "page", "page_size"} <= names
        ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.rsplit("/", 1)[-1].startswith("Paginated"), (
            "GET /api/v1/suggestions/ must publish the StandardPagination "
            f"envelope, got {ref}"
        )

    def test_csv_export_advertises_text_csv(self, generated: dict) -> None:
        operation = generated["schema"]["paths"][
            "/api/v1/workspaces/{id}/export/csv/"
        ]["get"]
        content = operation["responses"]["200"]["content"]
        assert "text/csv" in content
        assert "application/json" not in content

    def test_csv_import_accepts_only_multipart(self, generated: dict) -> None:
        schema = generated["schema"]
        operation = schema["paths"]["/api/v1/workspaces/{id}/import/csv/"]["post"]
        content = operation["requestBody"]["content"]
        assert list(content) == ["multipart/form-data"]
        component = content["multipart/form-data"]["schema"]["$ref"].rsplit("/", 1)[-1]
        properties = schema["components"]["schemas"][component]["properties"]
        assert {"file", "entity_type"} <= set(properties)
        # ADR-014 §2: every count-derived outcome is a documented response.
        assert {"200", "201", "207", "422"} <= set(operation["responses"])


# ---------------------------------------------------------------------------
# (j) the session-cookie scheme names the cookie the server reads (F13)
# ---------------------------------------------------------------------------


class TestSessionCookieScheme:
    def test_cookie_auth_names_the_real_cookie(self, generated: dict) -> None:
        schemes = generated["schema"]["components"]["securitySchemes"]
        cookie = schemes.get("cookieAuth")
        assert cookie is not None, "cookieAuth disappeared from the document"
        assert cookie["name"] == "reqogniloom_access", (
            "the runtime reads the httpOnly reqogniloom_access cookie "
            "(auth_tenancy/rest.py ACCESS_COOKIE_NAME); publishing "
            f"{cookie['name']!r} advertises a cookie the server ignores"
        )

    def test_cookie_auth_is_still_referenced(self, generated: dict) -> None:
        referenced = any(
            "cookieAuth" in security
            for _, _, operation in _operations(generated["schema"])
            for security in operation.get("security", [])
            if isinstance(security, dict)
        )
        assert referenced
