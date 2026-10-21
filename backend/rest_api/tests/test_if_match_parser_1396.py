"""``If-Match`` parsing and evaluation — GH-1396.

Before GH-1396 ``rest_api.mixins.etag`` reduced every ``If-Match`` shape to
"a single strong entity-tag, or ``None``", and ``None`` meant "the client
asserted nothing". A weak validator (``W/"6"``), ``garbage``, an empty value,
``*`` and a tag list therefore all fell through to the legacy
``expected_version`` body field and answered **200**: the client's write
protection was silently dropped.

This suite pins the replacement contract, first as a purely syntactic table
(:func:`parse_if_match`) and then end-to-end on a real endpoint (PATCH
``/api/v1/requirements/{id}/`` with a real DB and JWT), so a regression in the
parser cannot hide behind a mocked mixin:

===============================  ==============================================
``If-Match`` header value        Answer
===============================  ==============================================
absent                           200, body ``expected_version`` fallback intact
present but empty / whitespace   400 ``INVALID_IF_MATCH``
``*``                            200, no revision comparison
matching strong tag              200
stale strong tag                 412 ``PRECONDITION_FAILED``
weak validator (``W/"6"``,      412 — strong comparison can never hold
``w/"6"``)
unquoted / unbalanced quotes     400 ``INVALID_IF_MATCH``
comma inside a quoted tag        one opaque tag: ``"a,b"`` is a single tag, not
(``"a,b"``)                      a list (412 against a numeric ETag, not 400)
tag list, one strong tag matches 200
tag list, no strong tag matches  412
tag list with a malformed entry  400 ``INVALID_IF_MATCH``
lone comma                      400 — documented RFC 9110 § 5.6.1 deviation
===============================  ==============================================
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.mixins.etag import (
    EntityTag,
    IfMatchKind,
    IfMatchMismatch,
    InvalidIfMatch,
    parse_if_match,
    parse_if_match_version,
)
from workflow.services import create_default_workflow

#: Fixture-only signing key; ``placeholder`` is the W1 secret scanner's
#: documented allowlist token — the scanner pattern still matches, the allowlist
#: is what clears it (same shape as test_etag_optimistic_locking_868.py).
_SECRET = "test-secret-placeholder-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def if_match_env(db):
    """Tenant + admin + one workspace, with the admin role scoped to it."""
    tenant = Tenant.objects.create(name="IfMatch T", slug="ifmatch-t", is_active=True)
    admin = User.objects.create(
        username="ifmatchadmin", email="ifmatchadmin@t.test", tenant=tenant
    )
    admin.set_password("ifmatchpass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="IfMatch WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        # Required by the transition tests: a workspace created straight through
        # the ORM has no workflow, and every transition would 404/400 before the
        # If-Match path runs.
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        yield {"tenant": tenant, "admin": admin, "workspace": workspace}
    finally:
        clear_request_tenant()


def _client() -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "ifmatchadmin", "password": "ifmatchpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _requirement(client: APIClient, env: dict) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(env["workspace"].id), "title": "If-Match requirement"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


# ---------------------------------------------------------------------------
# Unit level: the parser is a pure function of the header
# ---------------------------------------------------------------------------

#: ``(header, expected kind, expected tags)`` — the decision matrix, verbatim.
_PARSE_MATRIX: list[tuple[str | None, IfMatchKind, tuple[EntityTag, ...]]] = [
    # absent → no assertion
    (None, IfMatchKind.ABSENT, ()),
    # present but empty / whitespace only → malformed, never "absent"
    ("", IfMatchKind.MALFORMED, ()),
    ("   ", IfMatchKind.MALFORMED, ()),
    ("\t", IfMatchKind.MALFORMED, ()),
    # * → any existing representation
    ("*", IfMatchKind.ANY, ()),
    ("  *  ", IfMatchKind.ANY, ()),
    # a single strong tag
    ('"6"', IfMatchKind.TAGS, (EntityTag("6"),)),
    ('  "6"  ', IfMatchKind.TAGS, (EntityTag("6"),)),
    ('"1"', IfMatchKind.TAGS, (EntityTag("1"),)),
    ('"abc"', IfMatchKind.TAGS, (EntityTag("abc"),)),
    # weak validators are syntactically valid, just never a strong match;
    # ABNF literals are case-insensitive, so ``w/`` is the same weak prefix
    ('W/"6"', IfMatchKind.TAGS, (EntityTag("6", weak=True),)),
    ('W/"1"', IfMatchKind.TAGS, (EntityTag("1", weak=True),)),
    ('w/"6"', IfMatchKind.TAGS, (EntityTag("6", weak=True),)),
    ('w/"1"', IfMatchKind.TAGS, (EntityTag("1", weak=True),)),
    # a comma inside the quotes is part of the opaque value (``etagc``), not a
    # list separator — a ``split(",")`` reported this legal tag as malformed
    ('"a,b"', IfMatchKind.TAGS, (EntityTag("a,b"),)),
    ('"a,b", "6"', IfMatchKind.TAGS, (EntityTag("a,b"), EntityTag("6"))),
    ('"a,b", "c,d"', IfMatchKind.TAGS, (EntityTag("a,b"), EntityTag("c,d"))),
    # ``etagc`` also covers ``obs-text`` (0x80-0xFF). ``\xa0``/``\x85`` are the
    # interesting ones: Python's ``\s`` treats them as whitespace, so the old
    # ``[^"\s]`` class rejected legal tags.
    ('"\x80\xff"', IfMatchKind.TAGS, (EntityTag("\x80\xff"),)),
    ('"\xa0"', IfMatchKind.TAGS, (EntityTag("\xa0"),)),
    ('"\x85"', IfMatchKind.TAGS, (EntityTag("\x85"),)),
    # malformed: unquoted, unbalanced quotes, bare quote, plain words
    ("6", IfMatchKind.MALFORMED, ()),
    ('"6', IfMatchKind.MALFORMED, ()),
    ('6"', IfMatchKind.MALFORMED, ()),
    ('"', IfMatchKind.MALFORMED, ()),
    ("garbage", IfMatchKind.MALFORMED, ()),
    ('"6" "9"', IfMatchKind.MALFORMED, ()),
    # lists — valid grammar, order-independent
    ('"1", "6"', IfMatchKind.TAGS, (EntityTag("1"), EntityTag("6"))),
    ('"1","6"', IfMatchKind.TAGS, (EntityTag("1"), EntityTag("6"))),
    ('  "1" ,  "6"  ', IfMatchKind.TAGS, (EntityTag("1"), EntityTag("6"))),
    ('W/"6", "1"', IfMatchKind.TAGS, (EntityTag("6", weak=True), EntityTag("1"))),
    # a list with a malformed entry is malformed as a whole
    ('"1", garbage', IfMatchKind.MALFORMED, ()),
    ('garbage, "1"', IfMatchKind.MALFORMED, ()),
    ('"1", 6', IfMatchKind.MALFORMED, ()),
    # a header that reduces to zero tags (only separators) is malformed
    (",", IfMatchKind.MALFORMED, ()),
    (", ,", IfMatchKind.MALFORMED, ()),
    # ``*`` may not be combined with tags (RFC 9110 § 13.1.1)
    ('*, "6"', IfMatchKind.MALFORMED, ()),
]


@pytest.mark.parametrize(("header", "kind", "tags"), _PARSE_MATRIX)
def test_parse_if_match_decision_matrix(header, kind, tags):
    parsed = parse_if_match(header)

    assert parsed.kind is kind, f"{header!r} → {parsed.kind} ({parsed.reason})"
    assert parsed.tags == tags, header


def test_parse_if_match_never_reports_malformed_without_a_reason():
    for header, kind, _ in _PARSE_MATRIX:
        parsed = parse_if_match(header)
        if kind is IfMatchKind.MALFORMED:
            assert parsed.reason, f"{header!r} must explain why it is malformed"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ('"3"', 3),
        ('  "3"  ', 3),
        ('"3", "4"', None),  # a list names no single revision
        ('W/"3"', None),  # weak never satisfies If-Match
        ("*", None),
        (None, None),
        ("", None),
        ("3", None),
        ('"abc"', None),
        ("garbage", None),
    ],
)
def test_parse_if_match_version_keeps_its_narrow_contract(header, expected):
    """The old public helper is unchanged — only the enforcement path moved."""
    assert parse_if_match_version(header) == expected


def test_entity_tag_quoted_round_trips():
    assert EntityTag("6").quoted == '"6"'
    assert EntityTag("6", weak=True).quoted == 'W/"6"'


def test_exceptions_do_not_leak_their_reason_into_str():
    """Both exceptions are mapped to registry messages by the view layer."""
    assert str(InvalidIfMatch("garbage is not a tag")) == ""
    assert InvalidIfMatch("garbage").reason == "garbage"
    assert str(IfMatchMismatch("no strong tag")) == ""
    assert IfMatchMismatch("no strong tag").reason == "no strong tag"


# ---------------------------------------------------------------------------
# HTTP level: the same matrix against a real endpoint
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_absent_header_still_writes(if_match_env):
    """Row 1 of the matrix: no header asserted, no version compared."""
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "unconditional write"},
        format="json",
    )

    assert resp.status_code == 200, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_matching_strong_tag_is_200(if_match_env):
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "guarded write"},
        format="json",
        HTTP_IF_MATCH=f'"{item["version"]}"',
    )

    assert resp.status_code == 200, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_stale_strong_tag_is_412(if_match_env):
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "stale write"},
        format="json",
        HTTP_IF_MATCH='"999999"',
    )

    assert resp.status_code == 412, resp.content
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_non_canonical_numeric_tag_is_412(if_match_env):
    """``"06"`` is not ``"6"``: entity-tags compare as opaque strings."""
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "zero-padded tag"},
        format="json",
        HTTP_IF_MATCH=f'"0{item["version"]}"',
    )

    assert resp.status_code == 412, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_weak_tag_matching_the_current_etag_is_412_not_200(if_match_env):
    """The GH-1396 headline: a weak validator can never satisfy If-Match."""
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "weak write"},
        format="json",
        HTTP_IF_MATCH=f'W/"{item["version"]}"',
    )

    assert resp.status_code == 412, resp.content
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED", resp.content
    # Nothing was written.
    fresh = client.get(f"/api/v1/requirements/{item['id']}/")
    assert fresh.json()["description"] != "weak write", fresh.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_lowercase_weak_prefix_is_412_not_400(if_match_env):
    """ABNF literals are case-insensitive: ``w/`` is the same weak prefix."""
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "lowercase weak write"},
        format="json",
        HTTP_IF_MATCH=f'w/"{item["version"]}"',
    )

    assert resp.status_code == 412, resp.content
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED", resp.content
    assert client.get(f"/api/v1/requirements/{item['id']}/").json()["description"] != (
        "lowercase weak write"
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_comma_inside_a_tag_is_one_tag_and_a_412_mismatch(if_match_env):
    """``"a,b"`` is one opaque strong tag, not a two-element list.

    The old ``split(",")`` parser cut it into ``"a`` and ``b"`` and answered
    400; the value is legal ``etagc`` and simply does not match, so it is a
    precondition failure (412).
    """
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "comma tag write"},
        format="json",
        HTTP_IF_MATCH='"a,b"',
    )

    assert resp.status_code == 412, resp.content
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_comma_tag_in_a_list_does_not_swallow_the_matching_tag(if_match_env):
    """The comma tag stays ONE entry, so the second tag still matches."""
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "comma list write"},
        format="json",
        HTTP_IF_MATCH=f'"a,b", "{item["version"]}"',
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["description"] == "comma list write", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_lone_comma_is_400_not_an_empty_list(if_match_env):
    """Documented RFC 9110 § 5.6.1 deviation: empty list -> 400, not 412."""
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "empty list write"},
        format="json",
        HTTP_IF_MATCH=",",
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", resp.content
    assert client.get(f"/api/v1/requirements/{item['id']}/").json()["description"] != (
        "empty list write"
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize("header", ["garbage", "6", '"6', '"', '  "6" "9"'])
def test_malformed_if_match_is_400(if_match_env, header):
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "malformed write"},
        format="json",
        HTTP_IF_MATCH=header,
    )

    assert resp.status_code == 400, (header, resp.content)
    assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", (header, resp.content)
    assert resp.json()["error"]["details"], (header, resp.content)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize("header", ["", "   "])
def test_present_but_empty_if_match_is_400_not_silently_ignored(if_match_env, header):
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "empty header write"},
        format="json",
        HTTP_IF_MATCH=header,
    )

    assert resp.status_code == 400, (header, resp.content)
    assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", (header, resp.content)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_star_is_200_and_skips_the_revision_comparison(if_match_env):
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "any revision"},
        format="json",
        HTTP_IF_MATCH="*",
    )

    assert resp.status_code == 200, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_star_wins_over_a_stale_body_expected_version(if_match_env):
    """The header is authoritative, including when it asserts no revision."""
    client = _client()
    item = _requirement(client, if_match_env)
    stale_body = item["version"]
    assert (
        client.patch(
            f"/api/v1/requirements/{item['id']}/",
            {"description": "session A"},
            format="json",
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/requirements/{item['id']}/").json()["version"] > stale_body

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "session B", "expected_version": stale_body},
        format="json",
        HTTP_IF_MATCH="*",
    )

    assert resp.status_code == 200, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_tag_list_matches_when_any_strong_tag_is_current(if_match_env):
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "list write"},
        format="json",
        HTTP_IF_MATCH=f'"999999", "{item["version"]}"',
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["description"] == "list write", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_tag_list_without_a_current_strong_tag_is_412(if_match_env):
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "list write"},
        format="json",
        HTTP_IF_MATCH='"999999", "999998"',
    )

    assert resp.status_code == 412, resp.content
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_weak_entry_in_a_list_never_matches_but_a_strong_one_still_does(if_match_env):
    client = _client()
    item = _requirement(client, if_match_env)

    weak_only = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "weak only"},
        format="json",
        HTTP_IF_MATCH=f'W/"{item["version"]}", W/"999999"',
    )
    assert weak_only.status_code == 412, weak_only.content

    with_strong = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "strong present"},
        format="json",
        HTTP_IF_MATCH=f'W/"{item["version"]}", "{item["version"]}"',
    )
    assert with_strong.status_code == 200, with_strong.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_tag_list_with_a_malformed_entry_is_400(if_match_env):
    client = _client()
    item = _requirement(client, if_match_env)

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "mixed list"},
        format="json",
        HTTP_IF_MATCH=f'"{item["version"]}", garbage',
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_absent_header_keeps_the_body_expected_version_fallback(if_match_env):
    """Unchanged backward compatibility: no header → body field, 409 on stale."""
    client = _client()
    item = _requirement(client, if_match_env)
    stale_body = item["version"]
    assert (
        client.patch(
            f"/api/v1/requirements/{item['id']}/",
            {"description": "session A"},
            format="json",
        ).status_code
        == 200
    )

    conflict = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "session B", "expected_version": stale_body},
        format="json",
    )

    assert conflict.status_code == 409, conflict.content
    assert conflict.json()["error"]["code"] == "CONFLICT", conflict.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_malformed_header_does_not_write(if_match_env):
    client = _client()
    item = _requirement(client, if_match_env)

    client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "must not land"},
        format="json",
        HTTP_IF_MATCH="garbage",
    )

    fresh = client.get(f"/api/v1/requirements/{item['id']}/")
    assert fresh.json()["description"] != "must not land", fresh.content


# ---------------------------------------------------------------------------
# The other two ETag ViewSets route through the same parser
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize("header", ["garbage", "", 'W/"1"'])
def test_workspace_patch_rejects_what_it_cannot_evaluate(if_match_env, header):
    """WorkspaceViewSet: malformed → 400, weak → 412 — never a silent 200."""
    client = _client()
    url = f"/api/v1/workspaces/{if_match_env['workspace'].id}/"

    resp = client.patch(
        url, {"name": "Renamed"}, format="json", HTTP_IF_MATCH=header
    )

    expected = 400 if header in ("", "garbage") else 412
    assert resp.status_code == expected, (header, resp.content)
    if expected == 400:
        assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", resp.content
    # The rejected write never landed.
    fresh = client.get(url)
    assert fresh.json()["name"] != "Renamed", fresh.content


def _baseline(client: APIClient, env: dict) -> tuple[str, str]:
    created = client.post(
        "/api/v1/baselines/",
        {
            "workspace_id": str(env["workspace"].id),
            "scope": "project",
            "name": "If-Match baseline",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    url = f"/api/v1/baselines/{created.json()['id']}/"
    etag = client.get(url).headers.get("ETag")
    assert etag is not None, "a baseline must expose its timestamp tag"
    return url, etag


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_baseline_patch_malformed_is_400(if_match_env):
    """BaselineViewSet: the 412/405 probe must not swallow a malformed header."""
    client = _client()
    url, _ = _baseline(client, if_match_env)

    resp = client.patch(url, {}, format="json", HTTP_IF_MATCH="garbage")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_baseline_patch_weak_tag_is_412(if_match_env):
    client = _client()
    url, etag = _baseline(client, if_match_env)

    resp = client.patch(url, {}, format="json", HTTP_IF_MATCH=f"W/{etag}")

    assert resp.status_code == 412, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_baseline_patch_accepts_its_iso_timestamp_tag(if_match_env):
    """ISO-timestamp ETags compare as tags, not as integers (issue row 2)."""
    client = _client()
    url, etag = _baseline(client, if_match_env)
    assert not etag.strip('"').isdigit(), "precondition: a timestamp tag"

    resp = client.patch(
        url, {}, format="json", HTTP_IF_MATCH=f'"999", {etag}'
    )

    # The tag matched, so the request reaches the immutability answer.
    assert resp.status_code == 405, resp.content


# ---------------------------------------------------------------------------
# The transition route shares the parser but keeps its 409 (CR-08)
# ---------------------------------------------------------------------------


def _approvable_requirement(client: APIClient, env: dict) -> str:
    """A requirement the standard preset's approval gate will actually accept."""
    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(env["workspace"].id),
            "title": "If-Match transition requirement",
            "description": "Exercised by the GH-1396 transition cases.",
            "acceptance_criteria": "A weak or malformed If-Match is never ignored.",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


def _workflow_version(client: APIClient, item_id: str) -> int:
    resp = client.get(f"/api/v1/requirements/{item_id}/transitions/")
    assert resp.status_code == 200, resp.content
    return resp.json()["version"]


def _transition(client: APIClient, item_id: str, **extra):
    return client.post(
        f"/api/v1/requirements/{item_id}/transitions/",
        {"target_state": "approved", "change_reason": "GH-1396"},
        format="json",
        **extra,
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_transition_weak_tag_is_409_not_200(if_match_env):
    """Same parser, different mapping: a lost precondition here is CR-08's 409."""
    client = _client()
    item_id = _approvable_requirement(client, if_match_env)
    version = _workflow_version(client, item_id)

    resp = _transition(client, item_id, HTTP_IF_MATCH=f'W/"{version}"')

    assert resp.status_code == 409, resp.content
    assert resp.json()["error"]["code"] == "CONFLICT", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_transition_malformed_tag_is_400(if_match_env):
    client = _client()
    item_id = _approvable_requirement(client, if_match_env)

    resp = _transition(client, item_id, HTTP_IF_MATCH="garbage")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "INVALID_IF_MATCH", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_transition_star_still_proceeds(if_match_env):
    client = _client()
    item_id = _approvable_requirement(client, if_match_env)

    resp = _transition(client, item_id, HTTP_IF_MATCH="*")

    assert resp.status_code == 200, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_transition_tag_list_compares_against_the_workflow_revision(if_match_env):
    client = _client()
    item_id = _approvable_requirement(client, if_match_env)
    version = _workflow_version(client, item_id)

    matching = _transition(
        client, item_id, HTTP_IF_MATCH=f'"999999", "{version}"'
    )
    assert matching.status_code == 200, matching.content

    fresh = _approvable_requirement(client, if_match_env)
    mismatched = _transition(client, fresh, HTTP_IF_MATCH='"999999", "999998"')
    assert mismatched.status_code == 409, mismatched.content
