"""Free-text sanitization policy — one rule set for every artifact (#820).

#820 reported the *symptom* (a SQLi-looking ``title`` returned ``201`` while an
XSS-looking ``title`` returned ``400``) and read it as inconsistent validation.
The canonical policy now lives in :mod:`persistence.free_text`; these tests pin
it down end-to-end against a real DB and real JWT:

* **markup is a 400** — on every enrolled free-text field, on every artifact
  type, and on comments (whose ``text`` was an unguarded ``CharField`` until
  #820, i.e. the exact "only a subset is filtered" gap the issue describes);
* **SQL/keyword-shaped text is data**: the ORM parameterises every query, so
  ``'; DROP TABLE users; --`` is stored and returned byte-identically instead
  of being blacklisted for "looking like SQL";
* **ordinary content** (quotes, ``&``, a bare ``<`` as in ``a < b``, umlauts,
  Markdown) is never touched, and no value is ever silently rewritten.
"""
from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from persistence.free_text import (
    HTML_MARKUP_MESSAGE,
    find_free_text_violation,
)

pytestmark = pytest.mark.django_db

#: The #820 repro. Downstream of the ORM this is a bind literal, never SQL.
SQL_SHAPED = "'; DROP TABLE users; --"


def _error_message(payload: dict) -> str:
    """Flatten the unified error envelope down to a searchable string."""
    return str(payload.get("error", payload))


def _field_errors(payload: dict) -> set[str]:
    """Field names carried by the REQ-L2-009 error envelope."""
    details = payload.get("error", {}).get("details") or []
    return {d.get("field") for d in details if isinstance(d, dict)}


def _create(api: APIClient, path: str, body: dict[str, Any]) -> Any:
    return api.post(path, body, format="json")


# ---------------------------------------------------------------------------
# Rule 3 — SQL/keyword-shaped text is plain data
# ---------------------------------------------------------------------------


def test_sql_shaped_title_is_accepted_and_round_trips(authed_client, workspace):
    """#820: ``'; DROP TABLE users; --`` must be stored verbatim, not rejected.

    The old report treated the missing SQL blacklist as a hole. It is not one:
    the ORM parameterises the INSERT/SELECT, so the string can never terminate
    a statement. Rejecting it would lose legitimate prose (a requirement that
    quotes an attack string is exactly what this tool is for).
    """
    resp = _create(
        authed_client,
        "/api/v1/requirements/",
        {"workspace_id": str(workspace.id), "title": SQL_SHAPED},
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["title"] == SQL_SHAPED

    detail = authed_client.get(f"/api/v1/requirements/{resp.json()['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["title"] == SQL_SHAPED


def test_sql_shaped_text_round_trips_on_a_second_artifact_type(
    authed_client, workspace
):
    """The policy is one seam: a second entity behaves identically."""
    payload = f"Check that {SQL_SHAPED} is escaped, not executed"
    resp = _create(
        authed_client,
        "/api/v1/needs/",
        {
            "workspace_id": str(workspace.id),
            "title": "Need quoting an attack string",
            "description": payload,
        },
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["description"] == payload

    detail = authed_client.get(f"/api/v1/needs/{resp.json()['id']}/")
    assert detail.json()["description"] == payload


# ---------------------------------------------------------------------------
# Rules 1-2 — markup / script URIs are rejected, consistently
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("endpoint", "extra", "field"),
    [
        ("/api/v1/requirements/", {"title": "<script>alert(1)</script>"}, "title"),
        (
            "/api/v1/needs/",
            {"description": "<img src=x onerror=alert(1)>"},
            "description",
        ),
        (
            "/api/v1/glossary/",
            {"term": "MarkupTerm", "definition": "<svg onload=alert(1)>"},
            "definition",
        ),
        (
            "/api/v1/testcases/",
            {"description": "[x](javascript:alert(1))"},
            "description",
        ),
    ],
)
def test_markup_and_script_uris_are_rejected_on_every_artifact_type(
    authed_client, workspace, endpoint, extra, field
):
    """Rules 1-2 apply per enrolled field, not only to ``Requirement.title``."""
    body = {"workspace_id": str(workspace.id)}
    if endpoint != "/api/v1/glossary/":
        body["title"] = "Guarded entity"
    body.update(extra)

    resp = _create(authed_client, endpoint, body)

    assert resp.status_code == 400, (endpoint, resp.content)
    assert "disallowed content" in _error_message(resp.json())
    assert field in _field_errors(resp.json())


def test_markup_in_a_comment_is_rejected(authed_client, workspace):
    """#820 consistency: ``Comment.text`` was the last unguarded prose field.

    Before the fix the same ``<img ...>`` payload was a 400 on a requirement
    title and a stored 201 on a comment — one policy per endpoint.
    """
    need = _create(
        authed_client,
        "/api/v1/needs/",
        {"workspace_id": str(workspace.id), "title": "Commented need"},
    )
    assert need.status_code == 201, need.content
    artifact_id = need.json()["artifact_id"]

    resp = _create(
        authed_client,
        f"/api/v1/artifacts/{artifact_id}/comments/",
        {"text": "<img src=x onerror=alert(1)>"},
    )

    assert resp.status_code == 400, resp.content
    assert "disallowed content" in _error_message(resp.json())
    assert "text" in _field_errors(resp.json())

    listing = authed_client.get(f"/api/v1/artifacts/{artifact_id}/comments/")
    assert listing.status_code == 200
    assert listing.json() == []


def test_sql_shaped_comment_text_is_accepted_and_round_trips(authed_client, workspace):
    """The comment path obeys rule 3 too — no SQL blacklist anywhere."""
    need = _create(
        authed_client,
        "/api/v1/needs/",
        {"workspace_id": str(workspace.id), "title": "Command injection probe"},
    )
    artifact_id = need.json()["artifact_id"]

    resp = _create(
        authed_client,
        f"/api/v1/artifacts/{artifact_id}/comments/",
        {"text": f"Broken query: {SQL_SHAPED}"},
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["text"] == f"Broken query: {SQL_SHAPED}"


# ---------------------------------------------------------------------------
# Guardrails — legitimate content is never mangled or rejected
# ---------------------------------------------------------------------------


def test_ordinary_content_survives_the_guard(authed_client, workspace):
    """Quotes, ``&``, a bare ``<``, umlauts and Markdown must pass untouched."""
    title = 'Müller & Söhne: "a < b" — 5 ≥ 3'
    description = (
        "**Fett**, `code`, [Link](https://example.com), 100 % & mehr.\n"
        "- Punkt 1\n- Punkt 2"
    )

    resp = _create(
        authed_client,
        "/api/v1/requirements/",
        {
            "workspace_id": str(workspace.id),
            "title": title,
            "description": description,
        },
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["title"] == title
    assert resp.json()["description"] == description


def test_rejection_does_not_leak_an_internal_exception(authed_client, workspace):
    """A 400 with the standard envelope — no traceback, no stack text."""
    resp = _create(
        authed_client,
        "/api/v1/requirements/",
        {"workspace_id": str(workspace.id), "title": "<script>alert(1)</script>"},
    )

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body.get("error", {}).get("code") == "VALIDATION_ERROR"
    assert "Traceback" not in str(body)


def test_detection_core_classifies_the_policy_examples():
    """The policy's three rules, asserted on the shared core (no DB needed)."""
    # Rule 3 — data, accepted verbatim.
    assert find_free_text_violation(SQL_SHAPED) is None
    assert find_free_text_violation('he said "hi" & left') is None
    assert find_free_text_violation("a < b") is None
    assert find_free_text_violation("Müller — Söhne") is None
    assert find_free_text_violation("Java Script: an overview") is None

    # Rule 1 — markup.
    assert find_free_text_violation("<b>x</b>") == HTML_MARKUP_MESSAGE
    assert find_free_text_violation("if <input> is empty") == HTML_MARKUP_MESSAGE
    assert find_free_text_violation(["ok", "<script>x</script>"]) is not None
    assert find_free_text_violation({"k": "<img src=x>"}) is not None

    # Rule 2 — script-capable URIs.
    assert find_free_text_violation("javascript:alert(1)") is not None
    assert find_free_text_violation("&#106;avascript:alert(1)") is not None
