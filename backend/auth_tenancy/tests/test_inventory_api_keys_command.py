"""CR-03 — read-only API-key inventory command: safety and classification tests.

The two properties that matter more than any classification detail are asserted
here as properties, not as proxies. Each is pinned by a *named* mechanism, and
none of them claims more than the test underneath it actually checks:

* **Read-only**, from three independent angles, one per test:
  ``test_command_does_not_change_any_key_row`` takes a full before/after
  snapshot of every ``ApiKey`` row (including ``modified_at`` and ``version``,
  which any write would bump); ``test_command_issues_no_write_statements``
  captures the SQL and fails on any ``INSERT``/``UPDATE``/``DELETE``/DDL;
  ``test_command_never_reaches_a_key_writing_service`` patches five
  instance-level mutators and asserts none was reached — that last one covers
  only those five, so it is deliberately not the sole read-only proof.
* **No secret output.** Every fixture key is created with a synthetic
  ``key_hash`` sentinel, and the test asserts that the sentinel — and *every*
  8-character window of it, so not even a prefix, fragment or truncation can
  pass — is absent from stdout and from the ``--output`` file, in all three
  formats.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from auth_tenancy.management.commands.inventory_api_keys import (
    _REASON_BY_RULE as COMMAND_REASON_BY_RULE,
)
from auth_tenancy.management.commands.inventory_api_keys import (
    EXPIRY_STATE_EXPIRED,
    EXPIRY_STATE_FUTURE,
    EXPIRY_STATE_NO_EXPIRY,
    FENCE_STATE_DEFECTIVE,
    FENCE_STATE_SET,
    FENCE_STATE_UNSET,
    INVENTORY_COLUMNS,
    LEGACY_KEY_ROTATION_RULE,
    NEW_KEY_CONTRACT_RULES,
    REASON_PRE_RULE,
    build_payload,
    classify_expiry,
    classify_workspace_fence,
    collect_inventory,
    is_canonical_workspace_id,
    render_csv,
    render_json,
    render_text,
    unsatisfied_rules,
)
from auth_tenancy.models import ApiKey
from auth_tenancy.services.authentication import AuthenticationService
from persistence.models import Tenant, User

# Every attribute snapshotted around a run. ``modified_at``/``version`` are
# included precisely because they change on *any* write, even a no-op save.
SNAPSHOT_FIELDS = (
    "name",
    "key_hash",
    "scope",
    "principal_type",
    "agent_label",
    "workspace_ids",
    "expires_at",
    "created_at",
    "last_used_at",
    "revoked_at",
    "modified_at",
    "version",
)

#: Synthetic, unmistakable, and shaped like a real ``key_hash`` so a leak of the
#: version prefix ("sha256p1:") would also be caught. Not a real credential.
FAKE_HASH_PREFIX = "sha256p1:SENTINEL-KEY-HASH-MUST-NOT-LEAK-"

#: The command's rule-id -> rotation-reason mapping, written out here as a
#: literal so the expectations below are pinned by this file rather than
#: imported from the implementation they check.
REASON_BY_RULE = {
    "explicit-canonical-scope": "no-canonical-scope",
    "workspace-fence-set": "no-workspace-fence",
    "expiry-decision-recorded": "no-expiry-decision",
}

#: One entry per way a stored ``workspace_ids`` value can fail to be a canonical
#: lower-case hyphenated UUID. Every value is built inside the test from a fresh
#: ``uuid4()``, so no literal UUID-shaped string is baked into this file.
FENCE_ENTRY_KINDS = (
    "canonical",
    "non-uuid-token",
    "empty-string",
    "bare-hex-without-hyphens",
    "upper-case-uuid",
    "whitespace-padded",
)

#: ``(case id, rule id, attributes breaking exactly that rule)`` for the
#: future-facing classification. ``workspace-fence-set`` appears twice on
#: purpose — once with the fence missing, once with it present but defective —
#: so both future-facing fence shapes are pinned.
FUTURE_FACING_CASES = (
    ("missing-canonical-scope", "explicit-canonical-scope", {"scope": "write"}),
    ("missing-fence", "workspace-fence-set", {"workspace_ids": []}),
    (
        "defective-fence",
        "workspace-fence-set",
        {"workspace_ids": ["workspace-alpha"]},
    ),
    ("no-expiry-decision", "expiry-decision-recorded", {"expires_at": None}),
)


def _fake_hash(tag: str) -> str:
    return f"{FAKE_HASH_PREFIX}{tag}"


def _fence_entry(kind: str) -> str:
    """Return one fence entry of the given non-canonicality *kind*."""
    canonical = str(uuid4())
    return {
        "canonical": canonical,
        "non-uuid-token": "workspace-alpha",
        "empty-string": "",
        "bare-hex-without-hyphens": canonical.replace("-", ""),
        "upper-case-uuid": canonical.upper(),
        "whitespace-padded": f" {canonical} ",
    }[kind]


def _make_key(
    tenant: Tenant,
    user: User,
    name: str,
    *,
    tag: str,
    scope: str = "read_only",
    principal_type: str = "user",
    agent_label: str = "",
    workspace_ids: list[str] | None = None,
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
    last_used_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> ApiKey:
    """Create one inventory fixture row.

    ``created_at`` is written with a follow-up ``.update()`` because the column
    is ``auto_now_add``. That is test-side fixture setup, never the command.
    """
    key = ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name=name,
        key_hash=_fake_hash(tag),
        scope=scope,
        principal_type=principal_type,
        agent_label=agent_label,
        workspace_ids=list(workspace_ids or []),
        expires_at=expires_at,
        last_used_at=last_used_at,
        revoked_at=revoked_at,
    )
    if created_at is not None:
        ApiKey.unscoped.filter(pk=key.pk).update(created_at=created_at)
        key.refresh_from_db()
    return key


def _snapshot() -> dict[str, tuple]:
    return {
        str(key.pk): tuple(getattr(key, field) for field in SNAPSHOT_FIELDS)
        for key in ApiKey.unscoped.all().order_by("created_at", "pk")
    }


def _utc(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=dt_timezone.utc)


def _day_after_the_rule(hour: int = 9) -> datetime:
    """A UTC timestamp strictly after the rule's effective calendar day.

    Derived from the rule constant rather than hard-coded, so these tests keep
    meaning "after the effective date" if the dated rule name ever moves.
    """
    day = LEGACY_KEY_ROTATION_RULE.effective_date + timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, tzinfo=dt_timezone.utc)


def _compliant_attributes(fence: list[str] | None = None) -> dict:
    """Attributes satisfying every new-key contract rule, fenced by default."""
    return {
        "scope": "read_only",
        "workspace_ids": [str(uuid4())] if fence is None else fence,
        "expires_at": timezone.now() + timedelta(days=30),
    }


def _run(*args: str) -> str:
    out = StringIO()
    call_command("inventory_api_keys", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


def _windows(text: str, size: int) -> set[str]:
    return {text[i : i + size] for i in range(len(text) - size + 1)}


def _leaks(output: str, secret: str, size: int = 8) -> list[str]:
    return sorted(w for w in _windows(secret, size) if w in output)


@pytest.fixture
def owner(db):
    tenant = Tenant.objects.create(
        name="Inventory Tenant", slug="inventory-tenant", is_active=True
    )
    user = User.objects.create(
        username="inventory-owner", email="inventory-owner@example.test", tenant=tenant
    )
    return tenant, user


@pytest.fixture
def keys(owner):
    """The fixture set the report sample is built from.

    One compliant new-style key (created on/after the rule date, canonical
    scope, fenced, explicit future expiry), one key with an empty workspace
    fence, one key with no expiry, one expired key and one revoked key.
    """
    tenant, user = owner
    now = timezone.now()
    fence = [str(uuid4())]
    on_or_after_rule = _utc(2026, 9, 26, 9)
    before_rule = _utc(2026, 9, 20, 9)
    return {
        "compliant": _make_key(
            tenant,
            user,
            "compliant-agent",
            tag="A",
            principal_type="agent",
            agent_label="Claude Code",
            scope="read_only",
            workspace_ids=fence,
            expires_at=now + timedelta(days=30),
            created_at=on_or_after_rule,
            last_used_at=now - timedelta(hours=6),
        ),
        "empty_fence": _make_key(
            tenant,
            user,
            "legacy-no-fence",
            tag="B",
            scope="write",
            workspace_ids=[],
            expires_at=now + timedelta(days=45),
            created_at=before_rule,
        ),
        "no_expiry": _make_key(
            tenant,
            user,
            "legacy-no-expiry",
            tag="C",
            scope="author",
            workspace_ids=fence,
            expires_at=None,
            created_at=before_rule,
        ),
        "expired": _make_key(
            tenant,
            user,
            "expired-agent",
            tag="D",
            principal_type="agent",
            agent_label="Rotated Bot",
            scope="read_only",
            workspace_ids=fence,
            expires_at=now - timedelta(days=2),
            created_at=before_rule,
            last_used_at=now - timedelta(days=3),
        ),
        "revoked": _make_key(
            tenant,
            user,
            "retired-key",
            tag="E",
            scope="read",
            workspace_ids=[],
            expires_at=now + timedelta(days=90),
            created_at=before_rule,
            revoked_at=now - timedelta(days=10),
        ),
    }


# --------------------------------------------------------------------------
# 1. Read-only
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_command_does_not_change_any_key_row(keys):
    before = _snapshot()

    _run()

    assert _snapshot() == before


@pytest.mark.django_db
def test_command_issues_no_write_statements(keys):
    with CaptureQueriesContext(connection) as captured:
        _run()

    statements = [
        query["sql"].lstrip().upper()
        for query in captured.captured_queries
        if query["sql"].lstrip().upper().split(" ", 1)[0]
        in {"INSERT", "UPDATE", "DELETE", "TRUNCATE", "ALTER", "DROP", "CREATE"}
    ]
    assert statements == []
    assert len(captured.captured_queries) > 0


@pytest.mark.django_db
def test_command_never_reaches_a_key_writing_service(keys):
    """Assert that none of the patched instance-level key mutators is reached.

    Exactly five mutators are patched, and all five must go uncalled:
    ``AuthenticationService.create_api_key`` and ``AuthenticationService
    .revoke_api_key`` — the only two key-writing methods that exist on that
    service — plus ``ApiKey.unscoped.create``, ``ApiKey.save`` and
    ``ApiKey.delete``.

    What this test does **not** cover, because nothing is patched for it:

    * the queryset-level bulk write paths — ``QuerySet.update``,
      ``QuerySet.delete``, ``bulk_update`` and ``bulk_create`` all bypass
      ``Model.save`` and ``Model.delete`` entirely, so a call to one of them
      would sail straight past the ``save``/``delete`` patches above;
    * ``ApiKey.objects.create`` on the tenant-scoped default manager — only
      the ``unscoped`` manager's ``create`` is patched;
    * raw SQL issued through a connection cursor;
    * any service method other than the two named above: the patches rule out
      "these two writers", not "any writer anywhere".

    None of those gaps is actually unaccounted for in this file — they are
    closed by the neighbouring tests rather than by this one:
    ``test_command_issues_no_write_statements`` captures the SQL and fails on
    any ``INSERT``/``UPDATE``/``DELETE``/DDL, which is what a queryset bulk
    write or a raw statement would produce; and
    ``test_command_does_not_change_any_key_row`` compares a full before/after
    snapshot of every row, so a write that slipped past both of the above would
    still be caught by its effect on the data.
    """
    with (
        patch.object(
            AuthenticationService, "create_api_key", autospec=True
        ) as create,
        patch.object(
            AuthenticationService, "revoke_api_key", autospec=True
        ) as revoke,
        patch.object(
            ApiKey.unscoped, "create", autospec=True
        ) as orm_create,
        patch.object(ApiKey, "save", autospec=True) as save,
        patch.object(ApiKey, "delete", autospec=True) as delete,
    ):
        _run()

    create.assert_not_called()
    revoke.assert_not_called()
    orm_create.assert_not_called()
    save.assert_not_called()
    delete.assert_not_called()


@pytest.mark.django_db
def test_command_offers_no_write_flag():
    from django.core.management.base import CommandError

    for flag in ("--fix", "--apply", "--rotate", "--write", "--revoke"):
        with pytest.raises(CommandError, match="unrecognized arguments"):
            call_command("inventory_api_keys", flag, stdout=StringIO())


# --------------------------------------------------------------------------
# 2. No secret material in any output
# --------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("output_format", ["text", "json", "csv"])
def test_no_key_hash_fragment_reaches_stdout(keys, output_format):
    output = _run("--format", output_format)

    for key in keys.values():
        assert _leaks(output, key.key_hash) == []
        assert key.key_hash not in output
        assert key.key_hash[:8] not in output
        assert key.key_hash[-8:] not in output


@pytest.mark.django_db
@pytest.mark.parametrize("output_format", ["text", "json", "csv"])
def test_no_key_hash_fragment_reaches_the_output_file(keys, output_format, tmp_path):
    target = tmp_path / f"inventory.{output_format}"

    _run("--format", output_format, "--output", str(target))

    written = target.read_text(encoding="utf-8")
    for key in keys.values():
        assert _leaks(written, key.key_hash) == []
        assert key.key_hash not in written
    assert "key_hash" not in written.lower()


@pytest.mark.django_db
@pytest.mark.parametrize("output_format", ["text", "json", "csv"])
def test_the_leak_detector_actually_detects_a_leak(output_format):
    """Positive control: the window scan above is not vacuously green."""
    secret = _fake_hash("POSITIVE-CONTROL")

    assert _leaks(f"oops: {secret}", secret) != []
    assert _leaks("nothing to see here", secret) == []


@pytest.mark.django_db
@pytest.mark.parametrize("output_format", ["text", "json", "csv"])
def test_secret_presence_is_reported_as_a_boolean_only(keys, output_format):
    output = _run("--format", output_format)
    payload = build_payload(collect_inventory())

    assert all(isinstance(e["secret_present"], bool) for e in payload["keys"])
    assert {e["secret_present"] for e in payload["keys"]} == {True}
    assert payload["disclosure"] == {
        "secret_material_emitted": False,
        "secret_present_is_boolean_only": True,
        "capability_judgements_emitted": False,
    }
    # The only secret-derived token any format may emit is that boolean itself.
    if output_format == "text":
        assert output.count("secret present") == len(payload["keys"])
    elif output_format == "csv":
        assert "secret_present" in output
    else:
        assert '"secret_present": true' in output


# --------------------------------------------------------------------------
# 3. Rotation classification, including the boundary date
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_rule_constant_carries_an_explicit_auditable_date():
    assert LEGACY_KEY_ROTATION_RULE.name.endswith(
        LEGACY_KEY_ROTATION_RULE.effective_date.isoformat()
    )
    assert LEGACY_KEY_ROTATION_RULE.effective_date == datetime(
        2026, 9, 25
    ).date()
    assert LEGACY_KEY_ROTATION_RULE.source_reference.startswith("CR-03")


@pytest.mark.django_db
@pytest.mark.parametrize("output_format", ["text", "json", "csv"])
def test_every_format_prints_the_rule_and_its_date(keys, output_format):
    output = _run("--format", output_format)

    assert LEGACY_KEY_ROTATION_RULE.name in output
    assert LEGACY_KEY_ROTATION_RULE.effective_date.isoformat() in output


@pytest.mark.django_db
def test_a_key_created_one_second_before_the_rule_date_is_a_candidate(owner):
    tenant, user = owner
    fence = [str(uuid4())]
    compliant = dict(
        scope="read_only",
        workspace_ids=fence,
        expires_at=timezone.now() + timedelta(days=30),
    )
    before = _make_key(
        tenant,
        user,
        "one-second-before",
        tag="F",
        created_at=_utc(2026, 9, 24, 23) + timedelta(minutes=59, seconds=59),
        **compliant,
    )
    on_the_day = _make_key(
        tenant,
        user,
        "on-the-day",
        tag="G",
        created_at=_utc(2026, 9, 25, 0),
        **compliant,
    )
    after = _make_key(
        tenant,
        user,
        "after-the-day",
        tag="H",
        created_at=_utc(2026, 9, 26, 0),
        **compliant,
    )
    entries = {e["key_id"]: e for e in collect_inventory()}

    assert entries[str(before.pk)]["rotation_candidate"] is True
    assert entries[str(before.pk)]["rotation_reasons"] == [REASON_PRE_RULE]
    assert entries[str(before.pk)]["unsatisfied_rules"] == []

    assert entries[str(on_the_day.pk)]["rotation_candidate"] is False
    assert entries[str(on_the_day.pk)]["rotation_reasons"] == []

    assert entries[str(after.pk)]["rotation_candidate"] is False
    assert entries[str(after.pk)]["rotation_reasons"] == []


@pytest.mark.django_db
def test_a_compliant_key_on_the_rule_date_is_not_a_candidate(keys):
    entries = {e["key_id"]: e for e in collect_inventory()}
    entry = entries[str(keys["compliant"].pk)]

    assert entry["rotation_candidate"] is False
    assert entry["rotation_reasons"] == []
    assert entry["unsatisfied_rules"] == []


@pytest.mark.django_db
def test_each_contract_rule_produces_its_own_rotation_reason(keys):
    entries = {e["key_id"]: e for e in collect_inventory()}

    empty_fence = entries[str(keys["empty_fence"].pk)]
    assert empty_fence["unsatisfied_rules"] == [
        "explicit-canonical-scope",
        "workspace-fence-set",
    ]
    assert empty_fence["rotation_reasons"] == [
        REASON_PRE_RULE,
        "no-canonical-scope",
        "no-workspace-fence",
    ]

    no_expiry = entries[str(keys["no_expiry"].pk)]
    assert no_expiry["unsatisfied_rules"] == ["expiry-decision-recorded"]
    assert no_expiry["rotation_reasons"] == [REASON_PRE_RULE, "no-expiry-decision"]

    revoked = entries[str(keys["revoked"].pk)]
    assert revoked["unsatisfied_rules"] == [
        "explicit-canonical-scope",
        "workspace-fence-set",
    ]
    assert revoked["rotation_reasons"] == [
        REASON_PRE_RULE,
        "no-canonical-scope",
        "no-workspace-fence",
    ]


@pytest.mark.django_db
def test_every_documented_contract_rule_is_detected_on_its_own():
    for rule_id in NEW_KEY_CONTRACT_RULES:
        assert _rules_for_only(rule_id) == [rule_id]


def _rules_for_only(rule_id: str) -> list[str]:
    """Return the unsatisfied rules for a key that fails only *rule_id*."""
    fence = [str(uuid4())]
    kw = {
        "scope": "read_only",
        "workspace_ids": fence,
        "expires_at": timezone.now() + timedelta(days=1),
    }
    if rule_id == "explicit-canonical-scope":
        kw["scope"] = "write"
    elif rule_id == "workspace-fence-set":
        kw["workspace_ids"] = []
    elif rule_id == "expiry-decision-recorded":
        kw["expires_at"] = None
    else:  # pragma: no cover - guards a typo in NEW_KEY_CONTRACT_RULES
        raise AssertionError(rule_id)
    return unsatisfied_rules(**kw)


# --------------------------------------------------------------------------
# 3b. Future-facing classification: the rule has two independent triggers
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_future_facing_helper_agrees_with_the_boundary_date_it_claims():
    """Keep ``_day_after_the_rule`` on the far side of the pinned boundary.

    ``test_a_key_created_one_second_before_the_rule_date_is_a_candidate`` pins
    the boundary with hard-coded timestamps; this stops the derived helper the
    future-facing tests use from quietly drifting onto the effective day itself
    or before it.
    """
    created = _day_after_the_rule()

    assert created.date() > LEGACY_KEY_ROTATION_RULE.effective_date
    assert created.date() == _utc(2026, 9, 26, 9).date()


@pytest.mark.django_db
def test_a_future_dated_compliant_key_is_not_a_rotation_candidate(owner):
    """The pre-date trigger must not fire for a key that satisfies every rule."""
    tenant, user = owner
    key = _make_key(
        tenant,
        user,
        "future-compliant",
        tag="J",
        created_at=_day_after_the_rule(),
        **_compliant_attributes(),
    )
    entry = {e["key_id"]: e for e in collect_inventory()}[str(key.pk)]

    assert entry["created_at"][:10] > (
        LEGACY_KEY_ROTATION_RULE.effective_date.isoformat()
    )
    assert entry["unsatisfied_rules"] == []
    assert entry["workspace_fence_state"] == FENCE_STATE_SET
    assert entry["rotation_candidate"] is False
    assert entry["rotation_reasons"] == []
    assert REASON_PRE_RULE not in entry["rotation_reasons"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("case_id", "rule_id", "broken"),
    FUTURE_FACING_CASES,
    ids=[case[0] for case in FUTURE_FACING_CASES],
)
def test_a_future_dated_key_failing_exactly_one_rule_is_a_candidate(
    owner, case_id, rule_id, broken
):
    """The contract trigger alone makes a future-dated key a candidate.

    The reason must be the one derived from the rule that failed, and must
    explicitly *not* be the pre-rule reason: a key created after the effective
    date is not pre-dated, so attributing it to the date would misstate why it
    landed on the list.
    """
    tenant, user = owner
    key = _make_key(
        tenant,
        user,
        f"future-{case_id}",
        tag="L",
        created_at=_day_after_the_rule(),
        **{**_compliant_attributes(), **broken},
    )
    entry = {e["key_id"]: e for e in collect_inventory()}[str(key.pk)]

    assert entry["unsatisfied_rules"] == [rule_id]
    assert entry["rotation_candidate"] is True
    assert entry["rotation_reasons"] == [REASON_BY_RULE[rule_id]]
    assert REASON_PRE_RULE not in entry["rotation_reasons"]


@pytest.mark.django_db
def test_the_two_rotation_triggers_are_independent(owner):
    """Both triggers at once still reports both, neither masking the other."""
    tenant, user = owner
    key = _make_key(
        tenant,
        user,
        "before-the-day-and-no-expiry",
        tag="M",
        created_at=_utc(2026, 9, 20, 9),
        scope="write",
        workspace_ids=[],
        expires_at=None,
    )
    entry = {e["key_id"]: e for e in collect_inventory()}[str(key.pk)]

    assert entry["rotation_reasons"][0] == REASON_PRE_RULE
    assert set(entry["rotation_reasons"]) == {
        REASON_PRE_RULE,
        "no-canonical-scope",
        "no-workspace-fence",
        "no-expiry-decision",
    }


# --------------------------------------------------------------------------
# 3c. Workspace fence: canonicality, not just non-emptiness
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", FENCE_ENTRY_KINDS)
def test_only_a_canonical_entry_is_reported_canonical(kind):
    assert is_canonical_workspace_id(_fence_entry(kind)) is (kind == "canonical")


@pytest.mark.parametrize("value", [None, 7, True, ["nested"], {"a": "b"}, "  "])
def test_a_fence_entry_that_is_not_a_uuid_string_is_never_canonical(value):
    assert is_canonical_workspace_id(value) is False


def test_the_fence_classification_has_exactly_three_states():
    canonical = str(uuid4())
    mixed = [canonical, "workspace-alpha"]

    assert classify_workspace_fence([]) == FENCE_STATE_UNSET
    assert classify_workspace_fence([canonical]) == FENCE_STATE_SET
    assert classify_workspace_fence([canonical, str(uuid4())]) == FENCE_STATE_SET
    assert classify_workspace_fence(["workspace-alpha"]) == FENCE_STATE_DEFECTIVE
    # A mixed fence is defective, not set: the rule is a conjunction over all
    # entries, so one entry that is not a workspace id sinks the whole fence.
    assert classify_workspace_fence(mixed) == FENCE_STATE_DEFECTIVE


@pytest.mark.django_db
@pytest.mark.parametrize("kind", FENCE_ENTRY_KINDS)
def test_a_fence_is_only_set_when_every_entry_is_a_canonical_uuid(owner, kind):
    tenant, user = owner
    key = _make_key(
        tenant,
        user,
        f"fence-{kind}",
        tag="O",
        created_at=_day_after_the_rule(),
        **{**_compliant_attributes(), "workspace_ids": [_fence_entry(kind)]},
    )
    entry = {e["key_id"]: e for e in collect_inventory()}[str(key.pk)]
    is_canonical = kind == "canonical"

    assert entry["workspace_fence_state"] == (
        FENCE_STATE_SET if is_canonical else FENCE_STATE_DEFECTIVE
    )
    assert ("workspace-fence-set" in entry["unsatisfied_rules"]) is not is_canonical
    assert entry["rotation_candidate"] is not is_canonical


@pytest.mark.django_db
@pytest.mark.parametrize("fence", [[], None])
def test_an_unset_or_empty_fence_is_unsatisfied(owner, fence):
    """Both spellings of "no fence" are reported as ``unset`` and unsatisfied.

    ``ApiKey.workspace_ids`` is ``NOT NULL``, so ``None`` and ``[]`` are the
    same stored value: an empty list. The field's own default is ``list``, so
    "unset" and "empty" are not two different stored states here — they are two
    ways of asking for the one state that exists, and both must be unsatisfied.
    """
    tenant, user = owner
    key = _make_key(
        tenant,
        user,
        "fence-empty",
        tag="P",
        created_at=_day_after_the_rule(),
        **{**_compliant_attributes(), "workspace_ids": fence},
    )
    entry = {e["key_id"]: e for e in collect_inventory()}[str(key.pk)]

    assert entry["workspace_ids"] == []
    assert entry["workspace_fence_state"] == FENCE_STATE_UNSET
    assert entry["unsatisfied_rules"] == ["workspace-fence-set"]
    assert entry["rotation_reasons"] == ["no-workspace-fence"]


@pytest.mark.django_db
@pytest.mark.xfail(
    reason=(
        "ApiKey.workspace_ids is NOT NULL, so a JSON null in the column is not "
        "reachable - documented here so nobody re-adds a test for it."
    ),
    strict=True,
)
def test_a_json_null_fence_column_would_be_reported_as_unset(owner):
    tenant, user = owner
    key = _make_key(
        tenant,
        user,
        "fence-null",
        tag="Q",
        created_at=_day_after_the_rule(),
        **_compliant_attributes(),
    )
    ApiKey.unscoped.filter(pk=key.pk).update(workspace_ids=None)
    entry = {e["key_id"]: e for e in collect_inventory()}[str(key.pk)]

    assert entry["workspace_fence_state"] == FENCE_STATE_UNSET
    assert entry["unsatisfied_rules"] == ["workspace-fence-set"]


@pytest.mark.django_db
def test_a_mixed_fence_is_defective_and_still_a_candidate(owner):
    tenant, user = owner
    mixed = [str(uuid4()), _fence_entry("non-uuid-token")]
    key = _make_key(
        tenant,
        user,
        "fence-mixed",
        tag="R",
        created_at=_day_after_the_rule(),
        **{**_compliant_attributes(), "workspace_ids": mixed},
    )
    entry = {e["key_id"]: e for e in collect_inventory()}[str(key.pk)]

    # The observed values are reported verbatim; only the classification moves.
    assert entry["workspace_ids"] == mixed
    assert entry["workspace_fence_state"] == FENCE_STATE_DEFECTIVE
    assert entry["unsatisfied_rules"] == ["workspace-fence-set"]
    assert entry["rotation_candidate"] is True
    assert entry["rotation_reasons"] == ["no-workspace-fence"]
    assert REASON_PRE_RULE not in entry["rotation_reasons"]


@pytest.mark.django_db
def test_a_defective_fence_reaches_every_renderer_and_the_totals(owner):
    tenant, user = owner
    _make_key(
        tenant,
        user,
        "fence-canonical-only",
        tag="S",
        created_at=_day_after_the_rule(),
        **_compliant_attributes(),
    )
    _make_key(
        tenant,
        user,
        "fence-defective",
        tag="T",
        created_at=_day_after_the_rule(),
        **{**_compliant_attributes(), "workspace_ids": [_fence_entry("upper-case-uuid")]},
    )
    inventory = collect_inventory()

    assert {e["name"]: e["workspace_fence_state"] for e in inventory} == {
        "fence-canonical-only": FENCE_STATE_SET,
        "fence-defective": FENCE_STATE_DEFECTIVE,
    }

    # A defective fence must not be dropped from the totals: it is counted as
    # having no usable workspace fence, same as an unset one.
    assert build_payload(inventory)["totals"]["no_workspace_fence"] == 1

    json_output = render_json(inventory)
    assert json.loads(json_output)["totals"]["no_workspace_fence"] == 1
    assert f'"workspace_fence_state": "{FENCE_STATE_DEFECTIVE}"' in json_output

    text_output = render_text(inventory)
    assert "DEFECTIVE: 1 non-canonical entry" in text_output
    assert "1 without workspace fence" in text_output

    csv_rows = [
        row
        for row in _csv_lines(render_csv(inventory))
        if row and not row[0].startswith("#")
    ]
    header, body = csv_rows[0], csv_rows[1:]
    assert {row[header.index("workspace_fence_state")] for row in body} == {
        FENCE_STATE_SET,
        FENCE_STATE_DEFECTIVE,
    }


def test_the_rotation_rule_name_date_and_reason_mapping_are_unchanged():
    assert LEGACY_KEY_ROTATION_RULE.name == "CR-03-LEGACY-API-KEY-ROTATION/2026-09-25"
    assert LEGACY_KEY_ROTATION_RULE.effective_date == datetime(2026, 9, 25).date()
    assert list(NEW_KEY_CONTRACT_RULES) == [
        "explicit-canonical-scope",
        "workspace-fence-set",
        "expiry-decision-recorded",
    ]
    # Pinning the command's own mapping against the literal above: the
    # fence-canonicality fix must not have renamed or re-derived a reason.
    assert dict(COMMAND_REASON_BY_RULE) == REASON_BY_RULE


# --------------------------------------------------------------------------
# 4. Expiry: "no expiry set" is not "expired"
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_expired_and_no_expiry_are_distinguished(keys):
    entries = {e["key_id"]: e for e in collect_inventory()}

    no_expiry = entries[str(keys["no_expiry"].pk)]
    assert no_expiry["expires_at"] is None
    assert no_expiry["expiry_state"] == EXPIRY_STATE_NO_EXPIRY
    assert no_expiry["status"] == "active"
    assert no_expiry["not_revoked"] is True

    expired = entries[str(keys["expired"].pk)]
    assert expired["expiry_state"] == EXPIRY_STATE_EXPIRED
    assert expired["status"] == "expired"
    # Expired is NOT revoked: the report must not conflate the two states.
    assert expired["not_revoked"] is True
    assert expired["revoked_at"] is None

    compliant = entries[str(keys["compliant"].pk)]
    assert compliant["expiry_state"] == EXPIRY_STATE_FUTURE
    assert compliant["status"] == "active"


@pytest.mark.django_db
def test_revocation_outranks_expiry_in_the_reported_status(keys):
    entries = {e["key_id"]: e for e in collect_inventory()}
    revoked = entries[str(keys["revoked"].pk)]

    assert revoked["status"] == "revoked"
    assert revoked["not_revoked"] is False
    assert revoked["expiry_state"] == EXPIRY_STATE_FUTURE


def test_classify_expiry_matches_the_models_own_is_expired_semantics():
    now = _utc(2026, 9, 25, 12)

    assert classify_expiry(None, now) == EXPIRY_STATE_NO_EXPIRY
    assert classify_expiry(now - timedelta(seconds=1), now) == EXPIRY_STATE_EXPIRED
    assert classify_expiry(now, now) == EXPIRY_STATE_EXPIRED
    assert classify_expiry(now + timedelta(seconds=1), now) == EXPIRY_STATE_FUTURE


# --------------------------------------------------------------------------
# 5. Report shape, coverage and the absence of capability stamping
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_fixture_key_appears_in_the_text_report(keys):
    output = _run()

    for name in (
        "compliant-agent",
        "legacy-no-fence",
        "legacy-no-expiry",
        "expired-agent",
        "retired-key",
    ):
        assert name in output
    assert "ROTATION CANDIDATES (4)" in output
    assert "unsatisfied rules: all satisfied" in output


@pytest.mark.django_db
def test_json_report_is_machine_readable_and_diffable(keys):
    payload = json.loads(_run("--format", "json"))

    assert payload["read_only"] is True
    assert payload["rotation_rule"] == LEGACY_KEY_ROTATION_RULE.as_dict()
    assert payload["columns"] == list(INVENTORY_COLUMNS)
    assert payload["totals"] == {
        "keys": 5,
        "rotation_candidates": 4,
        "revoked": 1,
        "expired": 1,
        "no_expiry_set": 1,
        "never_used": 3,
        "no_workspace_fence": 2,
    }
    assert str(keys["compliant"].pk) not in payload["rotation_candidate_key_ids"]
    assert str(keys["expired"].pk) in payload["rotation_candidate_key_ids"]
    assert all(set(e) == set(INVENTORY_COLUMNS) for e in payload["keys"])


@pytest.mark.django_db
def test_csv_report_has_a_flat_header_without_secret_columns(keys):
    output = _run("--format", "csv")
    lines = _csv_lines(output)
    data_rows = [row for row in lines if row and not row[0].startswith("#")]
    header, body = data_rows[0], data_rows[1:]

    assert header == list(INVENTORY_COLUMNS)
    assert "secret_present" in header
    assert "key_hash" not in header
    assert len(body) == 5
    # Lists are flattened, never JSON-encoded, so the file stays a flat table.
    fence_row = next(row for row in body if row[header.index("name")] == "compliant-agent")
    assert fence_row[header.index("workspace_ids")].count(";") == 0
    assert fence_row[header.index("secret_present")] == "true"
    assert fence_row[header.index("rotation_candidate")] == "false"


@pytest.mark.django_db
def test_inventory_uses_the_real_model_fields(keys):
    entries = {e["key_id"]: e for e in collect_inventory()}

    for key in keys.values():
        entry = entries[str(key.pk)]
        assert entry["name"] == key.name
        assert entry["scope"] == key.scope
        assert entry["principal_type"] == key.principal_type
        assert entry["agent_label"] == key.agent_label
        assert entry["workspace_ids"] == [str(w) for w in key.workspace_ids]
        assert entry["tenant_id"] == str(key.tenant_id)
        assert entry["owner_user_id"] == str(key.user_id)
        assert entry["tenant_slug"] == key.tenant.slug
        assert entry["created_at"] == key.created_at.isoformat()
        assert entry["last_used_at"] == (
            key.last_used_at.isoformat() if key.last_used_at else None
        )
        assert entry["revoked_at"] == (
            key.revoked_at.isoformat() if key.revoked_at else None
        )
        assert entry["expires_at"] == (
            key.expires_at.isoformat() if key.expires_at else None
        )
        assert entry["not_revoked"] is (key.revoked_at is None)


@pytest.mark.django_db
def test_last_used_signal_is_reported_and_never_substituted(keys):
    entries = {e["key_id"]: e for e in collect_inventory()}

    used = entries[str(keys["compliant"].pk)]
    never = entries[str(keys["empty_fence"].pk)]

    assert used["usage_state"] == "used"
    assert used["last_used_at"] is not None
    assert never["usage_state"] == "never_used"
    assert never["last_used_at"] is None


@pytest.mark.django_db
@pytest.mark.parametrize("output_format", ["text", "json", "csv"])
def test_no_capability_verdict_is_stamped_on_any_key(keys, output_format):
    output = _run("--format", output_format).lower()

    for verdict in ("invalid", "broken", "insecure", "compromised", "usab"):
        assert verdict not in output
    for column in INVENTORY_COLUMNS:
        assert "valid" not in column
        assert "capab" not in column


@pytest.mark.django_db
def test_tenant_filter_narrows_the_inventory(keys, owner):
    other = Tenant.objects.create(
        name="Other Tenant", slug="other-inventory-tenant", is_active=True
    )
    other_user = User.objects.create(
        username="other-owner", email="other-owner@example.test", tenant=other
    )
    _make_key(
        other,
        other_user,
        "other-tenant-key",
        tag="Z",
        created_at=_utc(2026, 9, 21, 8),
    )

    assert len(collect_inventory()) == 6
    scoped = collect_inventory(tenant_id=other.id)

    assert [e["name"] for e in scoped] == ["other-tenant-key"]
    assert json.loads(_run("--format", "json", "--tenant-id", str(other.id)))[
        "tenant_filter"
    ] == str(other.id)


@pytest.mark.django_db
def test_invalid_tenant_id_is_rejected_before_any_query(keys):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="must be a UUID"):
        call_command("inventory_api_keys", "--tenant-id", "not-a-uuid", stdout=StringIO())


@pytest.mark.django_db
def test_an_empty_installation_reports_nothing_and_still_prints_the_rule():
    output = _run("--format", "json")

    payload = json.loads(output)
    assert payload["keys"] == []
    assert payload["totals"]["keys"] == 0
    assert LEGACY_KEY_ROTATION_RULE.name in output


@pytest.mark.django_db
def test_renderers_agree_on_the_same_inventory(keys):
    inventory = collect_inventory()

    assert json.loads(render_json(inventory))["keys"] == inventory
    assert render_text(inventory).count("rotation:") == len(inventory)
    csv_output = render_csv(inventory)
    assert csv_output.splitlines()[0].startswith("# rotation rule:")
    assert [row for row in _csv_lines(csv_output) if row and not row[0].startswith("#")][
        0
    ] == list(INVENTORY_COLUMNS)


def _csv_lines(text: str) -> list[list[str]]:
    return list(csv.reader(StringIO(text)))
