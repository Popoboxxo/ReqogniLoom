"""GitHub #1081 — two error-envelope shapes side by side.

The dominant form is the nested envelope every explicit error emits::

    {"error": {"code": "NOT_FOUND", "message": "...", "details": []}}

Two shapes broke that:

1. ``{"error": "PERMISSION_DENIED", "message": "..."}`` — ``error`` is a plain
   string, so a client branching on ``body.error.code`` reads ``None``.
2. ``{"error": {"code": "401", ...}}`` — the *status number* used as the code,
   a value no other layer ever emits.

This suite pins three things:

* the handler no longer produces a numeric code (#1, fixed in
  ``rest_api.error_envelope``);
* the canonical shape is what the endpoints answer with;
* **no new flat-form builder can be introduced anywhere in the backend** — an
  AST scan over every module. Known offenders outside ``rest_api/`` are listed
  in :data:`_KNOWN_FLAT_ENVELOPE_OWNERS`; each of them is a
  ``def _err(code, message, http_status)`` helper that should be deleted in
   favour of ``rest_api.serializers.build_error_response``. Deleting an entry
   from that set is the owner's follow-up; leaving it is a tracked debt, adding
   a new file to it is a failure this test catches.
"""
from __future__ import annotations

import ast
import pathlib

import pytest
from django.test import override_settings
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIClient

from rest_api.error_envelope import reqogniloom_exception_handler
from rest_api.serializers import build_error_response

#: ``backend/`` root, derived from this file's location
#: (``backend/rest_api/tests/<this file>.py``).
_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Modules outside ``rest_api/`` that still build a flat
#: ``{"error": "<code>", "message": ...}`` HTTP body. Each is a one-line fix:
#: replace the local ``_err`` body (or the literal) with
#: ``Response(build_error_response(code, lang, message=message), status=...)``.
#: Issue #1081 asks for exactly ONE envelope; these are the remaining two and
#: they are owned outside this change's file scope.
#:
#: The two ``mcp_server`` entries are the JSON-RPC / SSE transport, which has its
#: own documented error format and its own clients; unifying it with the REST
#: envelope is a separate decision, not a #1081 side effect.
#:
#: The REST adapters that used to be listed here (``admin_ops/banner_rest.py``,
#: ``admin_ops/health_rest.py``, ``admin_ops/rest.py``,
#: ``auth_tenancy/rest_item_permission.py`` and
#: ``auth_tenancy/rest_workspace_members.py``) have since been migrated to
#: ``build_error_response`` and were removed from this set — see
#: :func:`test_backend_wide_scan_has_no_new_offenders`, which fails on a stale
#: entry so a fixed file can never keep masking a new one.
_KNOWN_FLAT_ENVELOPE_OWNERS = frozenset(
    {
        # MCP JSON-RPC / SSE transport (deliberately a separate format):
        "mcp_server/throttling.py",
        "mcp_server/views.py",
    }
)

#: Response constructors that put a body on the wire. A flat error dict literal
#: only counts as an *envelope* when it sits in a function that builds one of
#: these — an MCP JSON-RPC result dict, a Celery task return value or a log
#: payload that merely happens to have an "error" key is not a REST error
#: envelope and must not be reported here.
_RESPONSE_CALLS = frozenset({"Response", "JsonResponse", "HttpResponse"})


# ---------------------------------------------------------------------------
# Shape helpers
# ---------------------------------------------------------------------------


def _assert_canonical_envelope(payload: object, *, what: str) -> dict:
    """Assert the single documented envelope and return its inner error dict.

    ``details`` is asserted to be *present* but not to a fixed type: the two
    producers legitimately differ (``build_error_response`` emits a list, the
    DRF handler hands through the raw ``response.data`` mapping). Collapsing
    that is a real follow-up, but it is not what #1081 reported and doing it
    here would silently break every reader of the handler's ``details``.
    """
    assert isinstance(payload, dict), f"{what}: not a JSON object: {payload!r}"
    assert set(payload) == {"error"}, f"{what}: {payload!r}"
    error = payload["error"]
    assert isinstance(error, dict), (
        f"{what}: `error` is {type(error).__name__}, not the nested object — "
        f"this is the flat form #1081 removed: {payload!r}"
    )
    assert set(error) == {"code", "message", "details"}, f"{what}: {error!r}"
    assert isinstance(error["code"], str) and error["code"], f"{what}: {error!r}"
    assert not error["code"].isdigit(), (
        f"{what}: code {error['code']!r} is the raw HTTP status; clients match "
        f"on the named codes (REQ-L2-RA-004)"
    )
    assert isinstance(error["message"], str) and error["message"], f"{what}: {error!r}"
    assert error["details"] is not None, f"{what}: {error!r}"
    return error


# ---------------------------------------------------------------------------
# 1. The handler itself never emits a numeric code
# ---------------------------------------------------------------------------


def test_handler_maps_status_to_a_named_code() -> None:
    context = {"view": None, "request": None}

    not_found = reqogniloom_exception_handler(NotFound(), context)
    assert not_found is not None
    error = _assert_canonical_envelope(not_found.data, what="NotFound")
    assert error["code"] == "NOT_FOUND"
    assert not_found.status_code == 404

    invalid = reqogniloom_exception_handler(
        ValidationError({"title": ["This field is required."]}), context
    )
    assert invalid is not None
    error = _assert_canonical_envelope(invalid.data, what="ValidationError")
    assert error["code"] == "VALIDATION_ERROR"
    assert invalid.status_code == 400
    assert error["details"] == {"title": ["This field is required."]}


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (400, "VALIDATION_ERROR"),
        (401, "AUTHENTICATION_REQUIRED"),
        (403, "PERMISSION_DENIED"),
        (404, "NOT_FOUND"),
        (409, "CONFLICT"),
        (429, "RATE_LIMITED"),
        (500, "INTERNAL_SERVER_ERROR"),
        (503, "SERVICE_UNAVAILABLE"),
    ],
)
def test_every_registry_status_resolves_to_a_named_code(
    status_code: int, expected: str
) -> None:
    """A DRF ``APIException`` carries no ``code``; the status must supply one."""
    from rest_framework.exceptions import APIException

    exc = APIException()
    exc.status_code = status_code
    response = reqogniloom_exception_handler(
        exc, {"view": None, "request": None}
    )
    assert response is not None
    error = _assert_canonical_envelope(response.data, what=str(status_code))
    assert error["code"] == expected
    # The code must exist in the message registry too, so code and message
    # never come from two different vocabularies.
    from rest_api.serializers import get_error_message

    assert get_error_message(expected) != expected


def test_unknown_status_keeps_the_numeric_fallback() -> None:
    """A status outside the registry must not invent a new public code."""
    from rest_framework.exceptions import APIException

    exc = APIException()
    exc.status_code = 418
    response = reqogniloom_exception_handler(
        exc, {"view": None, "request": None}
    )
    assert response is not None
    assert response.data["error"]["code"] == "418"


# ---------------------------------------------------------------------------
# 2. The live surface
# ---------------------------------------------------------------------------


@override_settings(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)
@pytest.mark.django_db
def test_unauthenticated_response_uses_the_named_code() -> None:
    """The exact shape the issue reported as ``{"code": "401", ...}``."""
    response = APIClient().get("/api/v1/requirements/")

    assert response.status_code == 401, response.content
    assert "application/json" in response.headers.get("Content-Type", "")
    error = _assert_canonical_envelope(
        response.json(), what="401 requirements"
    )
    assert error["code"] == "AUTHENTICATION_REQUIRED"


@override_settings(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)
@pytest.mark.django_db
def test_build_error_response_stays_the_single_builder() -> None:
    error = _assert_canonical_envelope(
        build_error_response("NOT_FOUND", "en"), what="build_error_response"
    )
    assert error == {"code": "NOT_FOUND", "message": error["message"], "details": []}


# ---------------------------------------------------------------------------
# 3. No module may reintroduce the flat form
# ---------------------------------------------------------------------------


def _flat_envelope_hits(path: pathlib.Path) -> list[tuple[int, str]]:
    """Lines where a *response-building* function uses ``{"error": <non-dict>}``.

    Two deliberate narrowings, each avoiding a class of false positive that
    would otherwise bloat the allow-list until it stopped guarding anything:

    * AST-based, so a docstring or comment *describing* the flat form (there are
      several — they are the documentation of this issue) never counts.
    * Restricted to functions that also construct an HTTP response (see
      :data:`_RESPONSE_CALLS`), because "error" is also a perfectly ordinary
      key in a Celery task result, a log record and an MCP JSON-RPC envelope,
      none of which is a REST error envelope.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
        return []

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_is_response_call(sub) for sub in ast.walk(node)):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Dict):
                continue
            for key, value in zip(sub.keys, sub.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "error"
                    and not isinstance(value, ast.Dict)
                ):
                    hits.append((sub.lineno, ast.unparse(value)[:60]))
    return hits


def _is_response_call(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in _RESPONSE_CALLS
        if isinstance(func, ast.Attribute):
            return func.attr in _RESPONSE_CALLS
    return False


def _scan_backend() -> dict[str, list[tuple[int, str]]]:
    offenders: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(_BACKEND_ROOT.rglob("*.py")):
        rel = path.relative_to(_BACKEND_ROOT).as_posix()
        hits = _flat_envelope_hits(path)
        if hits:
            offenders[rel] = hits
    return offenders


def test_rest_api_builds_no_flat_envelope() -> None:
    """No file under ``rest_api/`` may build the flat form.

    ``rest_api`` owns the canonical builder and the DRF exception handler, so
    this is the directory where a second shape is actually reachable from new
    code. It is clean today; the test keeps it that way.
    """
    offenders = {
        rel: hits
        for rel, hits in _scan_backend().items()
        if rel.startswith("rest_api/")
    }
    assert offenders == {}, f"flat `{{\"error\": <str>}}` envelope in rest_api: {offenders}"


def test_backend_wide_scan_has_no_new_offenders() -> None:
    """Repo-wide guard with the known out-of-scope offenders allow-listed.

    The two files in :data:`_KNOWN_FLAT_ENVELOPE_OWNERS` are the remaining
    #1081 debt outside this change's file scope (the MCP JSON-RPC / SSE
    transport). A third one is a regression, not debt.
    """
    offenders = _scan_backend()
    unexpected = set(offenders) - _KNOWN_FLAT_ENVELOPE_OWNERS
    assert unexpected == set(), (
        "new flat `{\"error\": <str>}` envelope builders outside "
        f"rest_api: {unexpected}"
    )
    # And every allow-listed owner must still be one — otherwise the entry is
    # stale and should be removed, not left to mask a regression.
    stale = _KNOWN_FLAT_ENVELOPE_OWNERS - set(offenders)
    assert stale == set(), (
        f"these files no longer build a flat envelope; remove them from "
        f"_KNOWN_FLAT_ENVELOPE_OWNERS: {sorted(stale)}"
    )
