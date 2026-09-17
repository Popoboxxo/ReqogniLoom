"""Security hardening regressions from GitHub issue #269 (findings 1-4).

Every test here first reproduced the reported *bad* behaviour against the
pre-fix code:

* **Finding 1** — 30 consecutive authenticated ``GET /api/v1/workspaces/``
  returned 30x 200; no throttle applied to authenticated endpoints at all.
* **Finding 2** — the login throttle was per-IP and counted *every* attempt, so
  12 failed logins for a bogus user made the *admin's* correct credentials
  return 429.
* **Finding 3** — ``{"title": "javascript:alert(1)"}`` was stored verbatim and
  ``{"title": "<img src=x onerror=alert(1)>"}`` returned 201 with an empty
  title (silent data loss).
* **Finding 4** — ``POST /glossary/`` stored ``definition`` byte-identically
  including event handlers: stored XSS, because that ViewSet reads
  ``request.data`` and never runs its serializer.

Real DB + real JWT round-trip throughout: these bugs live in the interaction
between the view, the throttle/serializer layer and the service, all of which a
mock would paper over.
"""
from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


def _rest_framework_with_rates(**rates: Any) -> dict:
    """Full ``REST_FRAMEWORK`` dict with only the named throttle rates changed.

    ``override_settings`` replaces a setting wholesale, so the authentication,
    permission and exception-handler wiring has to be carried over — otherwise
    the test would exercise a different stack than production.
    """
    merged = dict(settings.REST_FRAMEWORK)
    merged["DEFAULT_THROTTLE_RATES"] = {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        **rates,
    }
    return merged


@pytest.fixture
def sec_env(db):
    """Tenant + admin (password login capable) + one workspace."""
    tenant = Tenant.objects.create(name="Sec T", slug="sec-t", is_active=True)
    admin = User.objects.create(
        username="secadmin", email="secadmin@t.test", tenant=tenant
    )
    admin.set_password("secpass123")
    admin.save(update_fields=["password"])

    other = User.objects.create(
        username="secother", email="secother@t.test", tenant=tenant
    )
    other.set_password("otherpass123")
    other.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Sec WS", preset={"name": "standard"}
        )
        for user in (admin, other):
            UserRole.objects.create(
                tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
            )
        yield {"tenant": tenant, "admin": admin, "other": other, "workspace": workspace}
    finally:
        clear_request_tenant()


def _login(username: str, password: str) -> Any:
    return APIClient().post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )


def _authed_client() -> APIClient:
    resp = _login("secadmin", "secpass123")
    assert resp.status_code == 200, resp.content
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _error_message(payload: dict) -> str:
    """Flatten the unified error envelope down to a searchable string."""
    return str(payload.get("error", payload))


def _field_errors(payload: dict) -> set[str]:
    """Field names carried by the REQ-L2-RA-009 error envelope."""
    details = payload.get("error", {}).get("details") or []
    return {d.get("field") for d in details if isinstance(d, dict)}


# ---------------------------------------------------------------------------
# Finding 1 — generic rate limiting on authenticated endpoints
# ---------------------------------------------------------------------------


@override_settings(
    **_JWT_OVERRIDES,
    REST_FRAMEWORK=_rest_framework_with_rates(user="3/min"),
)
@pytest.mark.django_db
def test_authenticated_endpoint_is_throttled(sec_env):
    """#269/1: an authenticated caller must eventually receive a 429.

    Pre-fix this loop produced N x 200 for any N — there was no
    ``DEFAULT_THROTTLE_CLASSES`` and no view opted in.
    """
    client = _authed_client()

    statuses = [
        client.get("/api/v1/workspaces/").status_code for _ in range(5)
    ]

    assert statuses[:3] == [200, 200, 200], statuses
    assert 429 in statuses[3:], statuses


@override_settings(
    **_JWT_OVERRIDES,
    REST_FRAMEWORK=_rest_framework_with_rates(user="3/min"),
)
@pytest.mark.django_db
def test_user_throttle_is_scoped_per_user_not_per_ip(sec_env):
    """One user exhausting their bucket must not lock out another user.

    Same class of defect as finding 2, guarded here for the generic throttle:
    the key is the auth-context user id, so a shared source IP is irrelevant.
    """
    exhausting = _authed_client()
    for _ in range(5):
        exhausting.get("/api/v1/workspaces/")

    other_login = _login("secother", "otherpass123")
    assert other_login.status_code == 200, other_login.content
    other = APIClient()
    other.credentials(HTTP_AUTHORIZATION=f"Bearer {other_login.json()['token']}")

    assert other.get("/api/v1/workspaces/").status_code == 200


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_default_rates_do_not_throttle_normal_usage(sec_env):
    """The configured default must not break ordinary paginated browsing.

    Guards against a future tightening that would make bulk/pagination tests
    flaky: 30 requests is what the issue reporter used, and it must pass.
    """
    client = _authed_client()

    assert all(
        client.get("/api/v1/workspaces/").status_code == 200 for _ in range(30)
    )


# ---------------------------------------------------------------------------
# Finding 2 — login throttle must not lock out correct credentials
# ---------------------------------------------------------------------------


@override_settings(
    **_JWT_OVERRIDES,
    REST_FRAMEWORK=_rest_framework_with_rates(login="3/min", login_ip="1000/min"),
)
@pytest.mark.django_db
def test_failed_logins_for_one_user_do_not_block_another(sec_env):
    """#269/2: the reported auth-DoS — bogus attempts blocked the real admin."""
    for _ in range(6):
        _login("attacker-does-not-exist", "wrong")

    resp = _login("secadmin", "secpass123")

    assert resp.status_code == 200, resp.content


@override_settings(
    **_JWT_OVERRIDES,
    REST_FRAMEWORK=_rest_framework_with_rates(login="3/min", login_ip="1000/min"),
)
@pytest.mark.django_db
def test_repeated_failures_against_same_username_are_throttled(sec_env):
    """Brute-force protection is still in place for the *targeted* account."""
    statuses = [_login("secadmin", "wrong-password").status_code for _ in range(5)]

    assert statuses[:3] == [401, 401, 401], statuses
    assert 429 in statuses[3:], statuses


@override_settings(
    **_JWT_OVERRIDES,
    REST_FRAMEWORK=_rest_framework_with_rates(login="3/min", login_ip="1000/min"),
)
@pytest.mark.django_db
def test_successful_login_clears_the_failure_counter(sec_env):
    """A user who mistypes twice, succeeds, then mistypes again is not locked."""
    for _ in range(2):
        assert _login("secadmin", "wrong-password").status_code == 401

    assert _login("secadmin", "secpass123").status_code == 200

    # Bucket cleared: three more failures still fit before the cap.
    assert [
        _login("secadmin", "wrong-password").status_code for _ in range(3)
    ] == [401, 401, 401]


@override_settings(
    **_JWT_OVERRIDES,
    REST_FRAMEWORK=_rest_framework_with_rates(login="1000/min", login_ip="4/min"),
)
@pytest.mark.django_db
def test_credential_spraying_across_usernames_is_capped_per_ip(sec_env):
    """The per-IP counter still stops one host spraying many usernames.

    Each attempt uses a different username, so the per-(IP, username) bucket
    never fills — only ``login_ip`` can catch this.
    """
    statuses = [_login(f"sprayed-user-{i}", "wrong").status_code for i in range(6)]

    assert statuses[:4] == [401, 401, 401, 401], statuses
    assert 429 in statuses[4:], statuses


@override_settings(
    **_JWT_OVERRIDES,
    REST_FRAMEWORK=_rest_framework_with_rates(login="3/min", login_ip="1000/min"),
)
@pytest.mark.django_db
def test_successful_logins_never_consume_the_failure_budget(sec_env):
    """Only failures are counted — an active user is never throttled out."""
    assert all(
        _login("secadmin", "secpass123").status_code == 200 for _ in range(10)
    )


# ---------------------------------------------------------------------------
# Finding 3 — the sanitizer must reject instead of silently emptying
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_html_markup_in_title_is_rejected_not_silently_stripped(sec_env):
    """#269/3: pre-fix this returned 201 with ``title == ''`` (data loss)."""
    client = _authed_client()

    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "title": "<img src=x onerror=alert(1)>",
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "disallowed content" in _error_message(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_javascript_uri_in_title_is_rejected(sec_env):
    """#269/3: ``javascript:`` survived verbatim and MarkdownPreview renders
    descriptions into real ``<a href>`` elements."""
    client = _authed_client()

    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "title": "javascript:alert(1)",
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "disallowed content" in _error_message(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        "&#106;avascript:alert(1)",  # entity-encoded scheme
        "java\tscript:alert(1)",  # control character inside the scheme
        "[click](JavaScript:alert(1))",  # markdown link, mixed case
    ],
)
def test_obfuscated_javascript_uris_are_rejected(sec_env, payload):
    """The scheme check normalises entities and control characters first."""
    client = _authed_client()

    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(sec_env["workspace"].id), "title": payload},
        format="json",
    )

    assert resp.status_code == 400, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_plain_text_free_text_is_still_accepted(sec_env):
    """The guard must not turn ordinary prose into a 400."""
    client = _authed_client()

    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "title": "System shall respond in < 200 ms",
            "description": "Uses A & B; see chapter 3.1 (95% percentile).",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["title"] == "System shall respond in < 200 ms"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_scheme_check_does_not_fire_on_a_plain_space(sec_env):
    """A space inside the scheme is not an obfuscation, it is normal prose.

    Control characters are collapsed before the scheme match (browsers strip
    TAB/LF/CR from URLs), but U+0020 deliberately is not — otherwise a heading
    like "Java Script: an overview" would be a 400 for no security gain.
    """
    client = _authed_client()

    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "title": "Java Script: an overview",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content


# ---------------------------------------------------------------------------
# Finding 4 — sanitization must cover every free-text field, not requirements
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_glossary_definition_rejects_stored_xss(sec_env):
    """#269/4: stored XSS — ``GlossaryTermViewSet.create`` bypasses the serializer."""
    client = _authed_client()

    resp = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "term": "XSSTerm",
            "definition": "<img src=x onerror=alert(1)>",
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "disallowed content" in _error_message(resp.json())

    listing = client.get(
        f"/api/v1/glossary/?workspace_id={sec_env['workspace'].id}"
    )
    assert listing.status_code == 200
    assert listing.json()["count"] == 0


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_glossary_patch_rejects_stored_xss(sec_env):
    """The bypass existed on the update path too, not only on create."""
    client = _authed_client()
    created = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "term": "SafeTerm",
            "definition": "A perfectly ordinary definition.",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    term_id = created.json()["id"]

    resp = client.patch(
        f"/api/v1/glossary/{term_id}/",
        {"definition": "<script>alert(1)</script>"},
        format="json",
    )

    assert resp.status_code == 400, resp.content

    unchanged = client.get(f"/api/v1/glossary/{term_id}/")
    assert unchanged.json()["definition"] == "A perfectly ordinary definition."


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize(
    ("endpoint", "payload_extra", "field"),
    [
        ("/api/v1/adrs/", {"context": "<b>x</b>"}, "context"),
        ("/api/v1/risks/", {"description": "<svg onload=alert(1)>"}, "description"),
        ("/api/v1/issues/", {"description": "<iframe src=x>"}, "description"),
        ("/api/v1/needs/", {"description": "<img src=x onerror=1>"}, "description"),
    ],
)
def test_free_text_guard_covers_every_entity(sec_env, endpoint, payload_extra, field):
    """#269/4 asked for consistency: the guard is one seam, not per-entity code."""
    client = _authed_client()

    resp = client.post(
        endpoint,
        {
            "workspace_id": str(sec_env["workspace"].id),
            "title": "Guarded entity",
            **payload_extra,
        },
        format="json",
    )

    assert resp.status_code == 400, (endpoint, resp.content)
    assert field in _error_message(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_rejection_uses_the_standard_error_envelope(sec_env):
    """The 400 must be shaped like every other validation error.

    The SPA's ``extractErrorMessage`` reads ``error.details[0].errors[0]``; a
    raw DRF ``{"field": [...]}`` body would fall through to the stringified
    exception repr and show the user an ``ErrorDetail(...)`` dump.
    """
    client = _authed_client()

    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "title": "<b>x</b>",
            "description": "javascript:alert(1)",
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert _field_errors(body) == {"title", "description"}


@override_settings(
    **_JWT_OVERRIDES,
    REST_FRAMEWORK=_rest_framework_with_rates(user=None),
)
@pytest.mark.django_db
def test_empty_rate_setting_disables_the_throttle(sec_env):
    """An operator can switch a limit off via an empty env value.

    ``API_RATE_LIMIT_USER=`` maps to ``None`` in ``DEFAULT_THROTTLE_RATES``;
    DRF then treats the scope as unlimited instead of raising.
    """
    client = _authed_client()

    assert all(
        client.get("/api/v1/workspaces/").status_code == 200 for _ in range(40)
    )


@pytest.mark.django_db
def test_glossary_term_is_a_declared_free_text_field():
    """Guard the seam itself: the ViewSet-level check is driven by the
    serializer's ``SanitizedCharField`` declarations, so a field that silently
    loses that declaration would silently lose its protection."""
    from rest_api.sanitization import collect_free_text_field_names
    from rest_api.serializers import GlossaryTermSerializer

    guarded = collect_free_text_field_names(GlossaryTermSerializer)

    assert {"term", "definition"} <= guarded


# ---------------------------------------------------------------------------
# Finding 4 (extended) — the remaining free-text fields on GlossaryTerm
#
# ``term``/``definition`` were the two the issue named. Auditing the rest of
# the serializer found two more user-authored fields that reached the DB raw:
# ``abbreviation`` (a plain ``CharField``) and ``synonyms`` (a ``JSONField``
# holding a *list of strings* — the guard only inspected scalars, so every
# element slipped through).
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_glossary_abbreviation_rejects_stored_xss(sec_env):
    """``abbreviation`` is user-authored prose too, and was unguarded."""
    client = _authed_client()

    resp = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "term": "AbbrTerm",
            "definition": "A perfectly ordinary definition.",
            "abbreviation": "<img src=x onerror=alert(1)>",
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "abbreviation" in _field_errors(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_glossary_synonyms_list_items_are_guarded(sec_env):
    """A payload nested inside a JSON *list* must be caught, not skipped.

    This is the sharp edge of the ``JSONField`` case: the scalar guard returned
    ``None`` for any non-``str`` input, so ``["<img src=x onerror=alert(1)>"]``
    was persisted byte-identically — the exact finding-4 bug, one nesting level
    down.
    """
    client = _authed_client()

    resp = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "term": "SynTerm",
            "definition": "A perfectly ordinary definition.",
            "synonyms": ["harmless", "<img src=x onerror=alert(1)>"],
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "synonyms" in _field_errors(resp.json())

    listing = client.get(
        f"/api/v1/glossary/?workspace_id={sec_env['workspace'].id}"
    )
    assert listing.json()["count"] == 0


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_glossary_synonyms_reject_dangerous_uri_scheme(sec_env):
    """Finding 3's scheme rule must apply inside the list as well."""
    client = _authed_client()

    resp = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "term": "SynSchemeTerm",
            "definition": "A perfectly ordinary definition.",
            "synonyms": ["javascript:alert(1)"],
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "synonyms" in _field_errors(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_glossary_accepts_ordinary_synonyms_and_abbreviation(sec_env):
    """The guard must not turn legitimate glossary data into a 400."""
    client = _authed_client()

    resp = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(sec_env["workspace"].id),
            "term": "Requirement",
            "definition": "A documented need that a design must satisfy.",
            "abbreviation": "REQ",
            "synonyms": ["Anforderung", "Need"],
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["synonyms"] == ["Anforderung", "Need"]
    assert resp.json()["abbreviation"] == "REQ"


@pytest.mark.django_db
def test_all_glossary_free_text_fields_are_declared():
    """Extends the seam guard to the fields added here."""
    from rest_api.sanitization import collect_free_text_field_names
    from rest_api.serializers import GlossaryTermSerializer

    guarded = collect_free_text_field_names(GlossaryTermSerializer)

    assert {"term", "definition", "abbreviation", "synonyms"} <= guarded


def test_violation_scan_descends_into_lists_and_dicts():
    """Unit-level contract for the nested scan the JSON fields depend on."""
    from rest_api.sanitization import find_free_text_violation

    assert find_free_text_violation(["ok", "<b>x</b>"]) is not None
    assert find_free_text_violation(["ok", "javascript:alert(1)"]) is not None
    assert find_free_text_violation({"k": "<script>x</script>"}) is not None
    assert find_free_text_violation(["ok", "fine"]) is None
    assert find_free_text_violation([]) is None
    assert find_free_text_violation({"k": ["deep", "<b>x</b>"]}) is not None


# ---------------------------------------------------------------------------
# Finding 4 (follow-up) — Artifact.custom_fields
#
# #290 turned ``CustomFieldsSerializerMixin.custom_fields`` from an inert class
# attribute into a live, writable field. That closed a silent-drop bug and
# opened a stored-XSS one in the same commit: the map round-trips
# byte-identically into the SPA, the PDF/ReqIF exporters and MCP responses, and
# nothing inspected it. Both halves of the map are guarded — see
# ``persistence.custom_fields.validate_custom_fields`` for why the *keys* count
# as user input too (they are not constrained by CustomFieldDefinition).
# ---------------------------------------------------------------------------


_CF_ENTITY_PAYLOADS: dict[str, tuple[str, dict[str, Any]]] = {
    "requirement": ("/api/v1/requirements/", {"title": "CF sec requirement"}),
    "need": ("/api/v1/needs/", {"title": "CF sec need"}),
    "architecture": (
        "/api/v1/architecture/",
        {"title": "CF sec element", "element_type": "block"},
    ),
    "testcase": ("/api/v1/testcases/", {"title": "CF sec testcase"}),
}


def _cf_payload(sec_env: dict, entity: str, custom_fields: dict) -> tuple[str, dict]:
    path, extra = _CF_ENTITY_PAYLOADS[entity]
    return path, {
        "workspace_id": str(sec_env["workspace"].id),
        **extra,
        "custom_fields": custom_fields,
    }


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize("entity", sorted(_CF_ENTITY_PAYLOADS))
@pytest.mark.parametrize(
    "custom_fields",
    [
        {"owner": "<img src=x onerror=alert(1)>"},
        {"link": "javascript:alert(1)"},
        {"note": "&#106;avascript:alert(1)"},
    ],
    ids=["html-markup", "javascript-uri", "obfuscated-uri"],
)
def test_custom_fields_value_rejects_stored_xss(sec_env, entity, custom_fields):
    """A payload in a custom-field *value* must 400, on every artifact type."""
    client = _authed_client()
    path, payload = _cf_payload(sec_env, entity, custom_fields)

    resp = client.post(path, payload, format="json")

    assert resp.status_code == 400, (entity, resp.content)
    assert "custom_fields" in _field_errors(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_custom_fields_key_rejects_stored_xss(sec_env):
    """Keys are attacker-controlled too — the SPA renders them as labels.

    ``Artifact.custom_fields`` accepts any key the caller sends; the
    ``CustomFieldDefinition`` schema (REQ-066) governs a *different* table and
    constrains nothing here. So a key is user-authored free text at write time.
    """
    client = _authed_client()
    path, payload = _cf_payload(
        sec_env, "requirement", {"<img src=x onerror=alert(1)>": "harmless"}
    )

    resp = client.post(path, payload, format="json")

    assert resp.status_code == 400, resp.content
    assert "custom_fields" in _field_errors(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_custom_fields_patch_rejects_stored_xss_and_keeps_stored_value(sec_env):
    """PATCH is the reported UI path; a rejection must not mutate the record."""
    client = _authed_client()
    path, payload = _cf_payload(sec_env, "requirement", {"owner": "alice"})
    created = client.post(path, payload, format="json")
    assert created.status_code == 201, created.content
    req_id = created.json()["id"]

    resp = client.patch(
        f"{path}{req_id}/",
        {"custom_fields": {"owner": "<script>alert(1)</script>"}},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "custom_fields" in _field_errors(resp.json())
    fresh = client.get(f"{path}{req_id}/")
    assert fresh.json()["custom_fields"] == {"owner": "alice"}


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_legitimate_custom_fields_still_save(sec_env):
    """The guard must not turn ordinary custom fields into a 400 (#290 stays fixed)."""
    client = _authed_client()
    path, payload = _cf_payload(
        sec_env,
        "requirement",
        {"owner": "alice", "sprint": 7, "done": False, "note": None,
         "url": "https://example.test/spec?a=1&b=2"},
    )

    resp = client.post(path, payload, format="json")

    assert resp.status_code == 201, resp.content
    assert resp.json()["custom_fields"]["owner"] == "alice"
    fresh = client.get(f"{path}{resp.json()['id']}/")
    assert fresh.json()["custom_fields"]["url"] == "https://example.test/spec?a=1&b=2"


@pytest.mark.django_db
def test_custom_fields_is_a_declared_free_text_field():
    """Seam guard: losing the ``SanitizedJSONField`` declaration would silently
    disable the ViewSet-level check for the handlers that skip the serializer."""
    from rest_api.sanitization import collect_free_text_field_names
    from rest_api.serializers import (
        ArchitectureElementSerializer,
        ArtifactSerializer,
        RequirementSerializer,
        StakeholderNeedSerializer,
        TestCaseSerializer,
    )

    for serializer_cls in (
        ArtifactSerializer,
        RequirementSerializer,
        StakeholderNeedSerializer,
        ArchitectureElementSerializer,
        TestCaseSerializer,
    ):
        assert "custom_fields" in collect_free_text_field_names(serializer_cls), (
            serializer_cls.__name__
        )


def test_validate_custom_fields_rejects_markup_outside_rest():
    """The authoritative check sits in the persistence layer, not in DRF.

    ``validate_custom_fields`` is the single intake every write path passes
    (REST, MCP tools, direct service calls, ReqIF import), so guarding it there
    closes the non-REST surfaces at the same time — the DRF field only adds the
    field-scoped 400 envelope on top.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError

    from persistence.custom_fields import validate_custom_fields

    with pytest.raises(DjangoValidationError):
        validate_custom_fields({"owner": "<img src=x onerror=alert(1)>"})
    with pytest.raises(DjangoValidationError):
        validate_custom_fields({"link": "javascript:alert(1)"})
    with pytest.raises(DjangoValidationError):
        validate_custom_fields({"<b>key</b>": "harmless"})

    assert validate_custom_fields({"owner": "alice", "sprint": 7}) == {
        "owner": "alice",
        "sprint": 7,
    }
