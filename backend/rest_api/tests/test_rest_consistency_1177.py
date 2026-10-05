"""Issue #1177 — REST contract consistency (bugfix-hub bundle B4).

The five measured inconsistencies on the public REST surface, pinned here where
they are code-enforced:

* **#2** — ``GET /api/v1/reviews/`` collection root (previously 404) is wired to
  the same pending-review source as ``/api/v1/reviews/pending/``.
* **#3** — canonical kebab-case multi-word paths plus backward-compatible
  un-hyphenated aliases: both spellings resolve to the same ``ViewSet``.
* **#4** — ``/openapi.json`` (JSON) is served, alongside the ``/api/openapi.json``
  alias and the kept ``/api/schema/`` + no-slash ``/api/schema``.
* **#5** — the schema endpoints answer with the correct OpenAPI ``Content-Type``
  and a parseable document (YAML by default, JSON via ``Accept``).

Finding #1 (the ``/users/`` paginated envelope) and the drf-spectacular renderer
behaviour behind #5 were **already satisfied** in the tree (INT-05,
``test_int05_pagination_status_codes.py`` / ``test_user_management_views.py``,
and drf-spectacular's ``OpenApiYamlRenderer.media_type``). The schema assertions
below lock #5 so it cannot silently regress; the alias/envelope shape is asserted
by the family of tests this module links to.

The routing assertions are pure URLconf checks (no DB); the schema checks drive
the real HTTP stack.
"""
from __future__ import annotations

import json

import pytest
import yaml
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

#: Canonical kebab-case spelling and its backward-compatible alias, per
#: finding #3. The first entry of each pair is canonical; the second the legacy
#: un-hyphenated path that must keep working.
_ALIAS_ROUTES = [
    ("testcase-list", "/api/v1/testcases/"),          # legacy alias
    ("test-case-list", "/api/v1/test-cases/"),        # canonical (#1177)
    ("tracelink-list", "/api/v1/tracelinks/"),        # legacy alias
    ("trace-link-list", "/api/v1/trace-links/"),      # canonical (fix #233)
    ("test-run-list", "/api/v1/test-runs/"),          # canonical
    ("testrun-list", "/api/v1/testruns/"),            # legacy alias (#1177)
    ("main-goal-list", "/api/v1/main-goals/"),        # canonical
    ("maingoal-list", "/api/v1/maingoals/"),          # legacy alias (#1177)
    ("change-request-list", "/api/v1/change-requests/"),  # canonical
    ("changerequest-list", "/api/v1/changerequests/"),    # legacy alias (#1177)
]


# ---------------------------------------------------------------------------
# #2 — the reviews collection root
# ---------------------------------------------------------------------------


def test_reviews_collection_root_is_registered() -> None:
    """``GET /api/v1/reviews/`` exists and sits at the collection URL."""
    assert reverse("api-v1-reviews") == "/api/v1/reviews/"


def test_reviews_collection_root_delegates_to_the_pending_view() -> None:
    """The root and ``pending/`` share one handler.

    A request without credentials is gated by authentication *before* the
    workspace check runs, so an anonymous probe answers the same status on both
    URLs (``401``), never a ``404``. Identical status and body across the two
    URLs is the proof that the root delegates to the same data source rather
    than 404-ing (the #1177 symptom) or shipping a second, weaker list; the
    authenticated ``200`` equivalence (same rows, same envelope) lives in
    ``test_review_pending_1089.py::test_collection_root_answers_like_the_flat_pending_route``.
    """
    client = APIClient()
    root = client.get("/api/v1/reviews/")
    pending = client.get("/api/v1/reviews/pending/")

    assert root.status_code != 404, root.content
    assert root.status_code == pending.status_code, (root.status_code, pending.status_code)
    assert root.json() == pending.json()


# ---------------------------------------------------------------------------
# #3 — canonical paths + aliases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_name", "expected_path"), _ALIAS_ROUTES)
def test_each_spelling_resolves_to_its_path(url_name: str, expected_path: str) -> None:
    assert reverse(url_name) == expected_path


@pytest.mark.parametrize(("url_name", "expected_path"), _ALIAS_ROUTES)
def test_each_spelling_is_routed_not_404(url_name: str, expected_path: str) -> None:
    """Both spellings reach a real view (401/403 auth gate, never the JSON 404).

    A missing ``/api/v1/`` route is answered by ``rest_api.not_found`` with a
    JSON ``404``; a wired-but-protected route answers ``401``/``403`` before any
    handler runs. ``404`` here would mean the alias silently does not exist.
    """
    resp = APIClient().get(expected_path)
    assert resp.status_code != 404, (expected_path, resp.content)
    assert resp.status_code in (200, 401, 403), (expected_path, resp.content)


# ---------------------------------------------------------------------------
# #4 + #5 — OpenAPI access points and content types
# ---------------------------------------------------------------------------


def _openapi_json_urls() -> list[str]:
    return ["/openapi.json", "/api/openapi.json"]


@pytest.mark.parametrize("url", _openapi_json_urls())
def test_json_openapi_is_served_with_json_content_type(url: str) -> None:
    resp = APIClient().get(url)

    assert resp.status_code == 200, (url, resp.content[:200])
    content_type = resp["Content-Type"]
    # drf-spectacular's OpenApiJsonRenderer media type, or a plain JSON type.
    assert "application/vnd.oai.openapi+json" in content_type or (
        content_type.startswith("application/json")
    ), content_type
    assert content_type != "application/yaml"
    document = json.loads(resp.content)
    assert document.get("openapi"), document.keys()


def test_yaml_schema_content_type_and_document() -> None:
    """``/api/schema/`` defaults to YAML with the OpenAPI media type."""
    resp = APIClient().get("/api/schema/")

    assert resp.status_code == 200, resp.content[:200]
    content_type = resp["Content-Type"]
    assert content_type.startswith("application/vnd.oai.openapi"), content_type
    assert "+json" not in content_type, content_type
    document = yaml.safe_load(resp.content)
    assert document.get("openapi"), document.keys()


def test_schema_negotiates_json_via_accept() -> None:
    resp = APIClient().get("/api/schema/", HTTP_ACCEPT="application/json")

    assert resp.status_code == 200, resp.content[:200]
    # drf-spectacular's own renderer answers application/vnd.oai.openapi+json;
    # DRF's JSONRenderer can win negotiation and answer application/json. Both
    # are the JSON document (the contract allows either), so assert on the
    # parseable body plus a JSON media type rather than one exact string.
    assert "json" in resp["Content-Type"], resp["Content-Type"]
    document = json.loads(resp.content)
    assert document.get("openapi"), document.keys()


def test_schema_no_slash_alias_answers_directly() -> None:
    """APPEND_SLASH is disabled (CR-03), so the bare path needs its own route."""
    resp = APIClient().get("/api/schema")

    assert resp.status_code == 200, resp.content[:200]
    assert resp["Content-Type"].startswith("application/vnd.oai.openapi")
