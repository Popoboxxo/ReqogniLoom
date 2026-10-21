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

The assertions below run the generator once and read drf-spectacular's own
``GENERATOR_STATS`` warning/error collection (not the management command's
stderr), because that is the same collection the CLI summarises and it is
reliable under ``-q``.
"""
from __future__ import annotations

import pytest
from drf_spectacular.drainage import GENERATOR_STATS, reset_generator_stats
from drf_spectacular.generators import SchemaGenerator

from rest_api.schema import UNTYPED_VIEW_ALLOWLIST, untyped_views_used

_NON_OPERATION_KEYS = {"parameters", "summary", "description", "servers", "$ref"}

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


@pytest.fixture(scope="module")
def generated() -> tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]:
    """Generate the document once and capture the generator's own diagnostics."""
    reset_generator_stats()
    schema = SchemaGenerator().get_schema(request=None, public=True)
    # ``GeneratorStats`` is a process-wide singleton; reset above scopes these
    # caches to this generation. Both dicts are message -> occurrence count.
    errors = tuple(GENERATOR_STATS._error_cache)  # noqa: SLF001 - public-ish API
    warnings = tuple(GENERATOR_STATS._warn_cache)  # noqa: SLF001 - public-ish API
    return schema, errors, warnings, untyped_views_used()


def _operations(schema: dict):
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in _NON_OPERATION_KEYS or not isinstance(operation, dict):
                continue
            yield path, method, operation


# ---------------------------------------------------------------------------
# (a) no serializer-guess errors
# ---------------------------------------------------------------------------


class TestNoSerializerGuessErrors:
    """A view without a serializer must be allowlisted, not error-logged."""

    def test_generator_emits_no_serializer_guess_error(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        _, errors, _, _ = generated
        offenders = [e for e in errors if "unable to guess serializer" in e]
        assert offenders == [], (
            "these views still fall back without being allowlisted; either add "
            "a serializer or add a reason to UNTYPED_VIEW_ALLOWLIST:\n"
            + "\n".join(offenders)
        )

    def test_generator_emits_no_errors_at_all(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        _, errors, _, _ = generated
        assert errors == ()


# ---------------------------------------------------------------------------
# (b) path parameter types are explicit
# ---------------------------------------------------------------------------


class TestPathParameterTypes:
    def test_no_underivable_path_parameters(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        _, _, warnings, _ = generated
        offenders = [
            w for w in warnings if "could not derive type of path parameter" in w
        ]
        assert offenders == [], (
            "declare the parameter explicitly with @extend_schema or a typed "
            "converter:\n" + "\n".join(offenders)
        )


# ---------------------------------------------------------------------------
# (c) operationId collisions are gone
# ---------------------------------------------------------------------------


class TestOperationIds:
    def test_no_collision_warnings(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        _, _, warnings, _ = generated
        offenders = [w for w in warnings if "has collisions" in w]
        assert offenders == []

    def test_no_duplicate_operation_id_in_the_document(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        schema = generated[0]
        ids = [op["operationId"] for _, _, op in _operations(schema)]
        duplicates = {value for value in ids if ids.count(value) > 1}
        assert duplicates == set()

    def test_the_disambiguated_list_operations_keep_their_explicit_id(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        schema = generated[0]
        ids = {op["operationId"] for _, _, op in _operations(schema)}
        assert _EXPLICIT_OPERATION_IDS - ids == set()


# ---------------------------------------------------------------------------
# (d) nothing was lost
# ---------------------------------------------------------------------------


class TestNoOperationLost:
    def test_path_and_operation_counts_do_not_shrink(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        schema = generated[0]
        operations = list(_operations(schema))
        # Before #1388: 357 paths / 528 operations. These are floors, not
        # targets: a new endpoint must never make the count go down.
        assert len(schema["paths"]) >= 357
        assert len(operations) >= 528

    @pytest.mark.parametrize("path", _CRITICAL_PATHS)
    def test_critical_path_is_present(
        self,
        generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]],
        path: str,
    ) -> None:
        assert path in generated[0]["paths"], f"{path} vanished from the schema"


# ---------------------------------------------------------------------------
# (e) the fallback allowlist is exact
# ---------------------------------------------------------------------------


class TestUntypedAllowlist:
    def test_every_used_fallback_is_allowlisted(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        _, _, _, used = generated
        missing = used - set(UNTYPED_VIEW_ALLOWLIST)
        assert missing == set(), (
            "these views used the permissive fallback without a deliberate "
            "allowlist entry — add a serializer or document the reason:\n"
            f"{sorted(missing)}"
        )

    def test_every_allowlisted_view_actually_used_the_fallback(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        _, _, _, used = generated
        stale = set(UNTYPED_VIEW_ALLOWLIST) - used
        assert stale == set(), (
            "these allowlist entries no longer fall back (a serializer was "
            "added) — remove them so the list stays a gate:\n"
            f"{sorted(stale)}"
        )

    def test_every_allowlist_entry_has_a_reason(self) -> None:
        for view, reason in UNTYPED_VIEW_ALLOWLIST.items():
            assert isinstance(reason, str) and reason.strip(), view

    def test_high_value_views_are_typed_not_allowlisted(self) -> None:
        assert _TYPED_BY_1388 - set(UNTYPED_VIEW_ALLOWLIST) == _TYPED_BY_1388


# ---------------------------------------------------------------------------
# (f) every operation documents a success response
# ---------------------------------------------------------------------------


class TestSuccessResponses:
    def test_every_operation_has_responses(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        schema = generated[0]
        missing = [
            (path, method)
            for path, method, operation in _operations(schema)
            if not operation.get("responses")
        ]
        assert missing == []

    def test_every_operation_has_a_2xx_except_the_documented_always_4xx_set(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        schema = generated[0]
        without_2xx = {
            (path, method)
            for path, method, operation in _operations(schema)
            if not any(code.startswith("2") for code in operation["responses"])
        }
        assert without_2xx == set(_ALWAYS_4XX_OPERATIONS), (
            "an operation without a 2xx must be a deliberate, documented "
            "always-fails route; got "
            f"{sorted(without_2xx - set(_ALWAYS_4XX_OPERATIONS))}"
        )

    def test_the_fallback_operations_are_marked(
        self, generated: tuple[dict, tuple[str, ...], tuple[str, ...], frozenset[str]]
    ) -> None:
        schema = generated[0]
        # At least the admin health/backup family must carry the marker; an
        # untyped operation that silently advertises an empty body is exactly
        # the defect this issue fixes.
        marked = sum(
            1
            for _, _, operation in _operations(schema)
            for response in operation["responses"].values()
            if "$ref" not in response
            and any(
                media.get("schema", {}).get("x-reqlo-untyped") is True
                for media in (response.get("content") or {}).values()
            )
        )
        assert marked > 0
