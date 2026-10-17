"""Proof that the shared ratchet contract holds (#1103 / REQ-193).

These are the framework's own tests, and the one that carries the issue's
acceptance criterion is
:func:`test_a_genuine_regression_cannot_be_rebaselined_away`: a re-baseline
must never be a way to make a real regression disappear.

Everything runs against ``tmp_path``. No test here ever touches a committed
baseline — a suite that rewrites its own fixture while proving that the
framework refuses to rewrite fixtures would prove nothing.
"""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from mcp_server.tests.ratchet_framework import (
    CONTRACT_VERSION,
    GAP_MIN_REASON_LENGTH,
    JUSTIFICATION_ENV_VAR,
    JUSTIFY_NEW,
    JUSTIFY_ROTATED,
    REBASELINE_ENTRY_POINTS,
    TS_MIRROR_PATH,
    BaselineDiff,
    GapSchemaError,
    RatchetError,
    RebaselineEntryPoint,
    UnjustifiedDumpError,
    assert_ceiling_not_raised,
    assert_dump_justified,
    assert_no_stale_entries,
    assert_no_undocumented_gaps,
    entry_point,
    gap_keys,
    load_gaps,
    load_justifications,
    maybe_rebaseline,
    normalise_gap,
    rebaseline_hint,
    resolve_rebaseline_target,
    split_baseline,
    unjustified_keys,
    write_baseline,
)

#: A gap the previous baseline does not accept — i.e. a genuine regression in
#: the shape #1080 was: an entity a transport can no longer reach.
REGRESSION = (
    "test_run: TestRun is REST-exposed at 'test-runs' but MCP has no "
    "'test.run_list' tool (issue #1080 class: entity unreachable over MCP)"
)

#: Long enough to satisfy the reason rule, and specific to the element.
ACCEPTED_REASON = (
    "TestRun is intentionally REST-only while the batch approval flow lands; "
    "agents read runs through the report export until #1103 is closed"
)

#: Too short to say anything — the shape the rule exists to reject.
LAZY_REASON = "too hard"


@pytest.fixture(autouse=True)
def _no_rebaseline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A normal run, unless a test opts in.

    The framework reads its env vars through ``os.environ``; without this a
    stray variable in a developer's shell could make a "normal run" write.
    """
    for point in REBASELINE_ENTRY_POINTS:
        monkeypatch.delenv(point.canonical_env, raising=False)
        monkeypatch.delenv(point.legacy_env, raising=False)
    monkeypatch.delenv(JUSTIFICATION_ENV_VAR, raising=False)


def _previous() -> dict[str, Any]:
    """A baseline document in the shape the entity-surface ratchet stores."""
    return {
        "_comment": ["known REST/MCP entity-surface gaps", "Regenerate with: ..."],
        "measured_at": {"version": "1.8.0-beta.18", "commit": "7b585bb4"},
        "violations": [],
    }


def _justified(justify: object | None = None) -> dict[str, dict[str, str]]:
    if justify is None:
        justify = {"reason": ACCEPTED_REASON, "issue": "#1103"}
    assert isinstance(justify, dict)
    return {REGRESSION: justify}


# ---------------------------------------------------------------------------
# The acceptance criterion of #1103
# ---------------------------------------------------------------------------


def test_a_genuine_regression_cannot_be_rebaselined_away(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-baseline refuses an unjustified widening and records a justified one."""
    point = entry_point("entity-surface-parity")
    target = tmp_path / "candidate-baseline.json"
    previous = _previous()
    document = dict(previous)

    # (1) Unjustified: the dump is refused and NOTHING is written. The
    # regression therefore cannot enter the baseline, so the very next run
    # still fails on it — "just re-baseline it" is not a way out.
    monkeypatch.delenv(JUSTIFICATION_ENV_VAR, raising=False)
    with pytest.raises(UnjustifiedDumpError) as refusal:
        write_baseline(
            point=point,
            target=target,
            measured={REGRESSION},
            previous=previous,
            document=document,
        )
    assert not target.exists(), "a refused dump must not write the target"
    assert REGRESSION in str(refusal.value)
    assert str(GAP_MIN_REASON_LENGTH) in str(refusal.value)
    assert rebaseline_hint(point) in str(refusal.value)

    diff_after_refusal = split_baseline({REGRESSION}, set())
    assert diff_after_refusal.new == (REGRESSION,), (
        "the regression must still be an undocumented gap, i.e. the next run "
        "is red"
    )
    with pytest.raises(AssertionError):
        assert_no_undocumented_gaps(diff_after_refusal, point)

    # (2) Justified: the dump is written and reads back with the justification
    # attached, so the widening is auditable in the diff that produced it.
    monkeypatch.setenv(
        JUSTIFICATION_ENV_VAR,
        json.dumps({REGRESSION: {"reason": ACCEPTED_REASON, "issue": "#1103"}}),
    )
    write_baseline(
        point=point,
        target=target,
        measured={REGRESSION},
        previous=previous,
        document=document,
    )
    assert target.is_file()
    written = json.loads(target.read_text(encoding="utf-8"))

    entries = written["violations"]
    assert len(entries) == 1
    assert entries[0]["gap"] == REGRESSION
    assert entries[0]["reason"] == ACCEPTED_REASON
    assert entries[0]["issue"] == "#1103"
    # The rest of the document survives, so a candidate file is a drop-in.
    assert written["_comment"] == previous["_comment"]
    assert written["measured_at"] == previous["measured_at"]

    # (3) The following run accepts what the justified dump wrote — and still
    # rejects the uninstrumented reading of it as a plain gap.
    reloaded = gap_keys(entries)
    assert split_baseline({REGRESSION}, reloaded) == BaselineDiff(new=(), rotated=())


def test_a_regression_supplied_as_a_mapping_argument_is_refused_or_recorded(
    tmp_path: Path,
) -> None:
    """The caller may hand justifications in directly, not only via the env var."""
    point = entry_point("entity-surface-parity")
    target = tmp_path / "candidate.json"
    previous = _previous()

    with pytest.raises(UnjustifiedDumpError):
        write_baseline(
            point=point,
            target=target,
            measured={REGRESSION},
            previous=previous,
            justify={},
        )
    assert not target.exists()

    write_baseline(
        point=point,
        target=target,
        measured={REGRESSION},
        previous=previous,
        justify=_justified(),
    )
    assert gap_keys(json.loads(target.read_text(encoding="utf-8"))["violations"]) == {
        REGRESSION
    }


def test_the_justification_env_var_accepts_a_file_and_inline_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``$RATCHET_JUSTIFY`` is a path or inline JSON — both decode to a mapping."""
    payload = {REGRESSION: {"reason": ACCEPTED_REASON, "issue": "#1103"}}
    inline = json.dumps(payload)
    monkeypatch.setenv(JUSTIFICATION_ENV_VAR, inline)
    assert load_justifications() == payload

    justification_file = tmp_path / "justify.json"
    justification_file.write_text(inline, encoding="utf-8")
    monkeypatch.setenv(JUSTIFICATION_ENV_VAR, str(justification_file))
    assert load_justifications() == payload

    monkeypatch.setenv(JUSTIFICATION_ENV_VAR, json.dumps([payload]))
    with pytest.raises(GapSchemaError):
        load_justifications()


def test_a_dump_drops_stale_entries_and_keeps_the_accepted_ones(
    tmp_path: Path,
) -> None:
    """The re-baseline is the strict-shrink half of the ratchet, automated."""
    point = entry_point("entity-surface-parity")
    target = tmp_path / "candidate.json"
    stale = "glossary: GlossaryEntry is REST-exposed at 'glossary' but MCP has no tool"
    previous = {
        "violations": [{"gap": stale, "reason": ACCEPTED_REASON, "issue": "#1102"}],
    }

    diff = write_baseline(
        point=point,
        target=target,
        measured=set(),
        previous=previous,
        document=dict(previous),
        justify={},
    )
    assert diff == BaselineDiff(new=(), rotated=(stale,))
    assert json.loads(target.read_text(encoding="utf-8"))["violations"] == []


# ---------------------------------------------------------------------------
# Part 1 -- named, explicit entry points
# ---------------------------------------------------------------------------


def test_every_ratchet_declares_a_named_entry_point() -> None:
    """The table is the registry: unique ids, a canonical var, a real command."""
    ids = [point.ratchet for point in REBASELINE_ENTRY_POINTS]
    assert len(ids) == len(set(ids))
    assert set(ids) == {
        "entity-surface-parity",
        "design-system",
        "tool-manifest-drift",
    }
    for point in REBASELINE_ENTRY_POINTS:
        assert point.canonical_env in point.command
        assert point.suite and point.writes
        assert point.justify_direction in (JUSTIFY_NEW, JUSTIFY_ROTATED)
        assert "=1" in point.command or point.placeholder == "<path>"


def test_rebaseline_stays_a_named_explicit_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no env var set a normal run writes nothing and reads no dump."""
    point = entry_point("entity-surface-parity")
    sentinel = tmp_path / "baseline.json"
    sentinel.write_text(json.dumps(_previous()), encoding="utf-8")

    def _explode(**_: object) -> None:  # pragma: no cover - must never run
        raise AssertionError("a normal run must not reach the dump path")

    monkeypatch.setattr(
        "mcp_server.tests.ratchet_framework.write_baseline", _explode
    )
    assert resolve_rebaseline_target(point, default_path=sentinel) is None
    assert maybe_rebaseline(
        point, measured={REGRESSION}, previous=_previous(), document=_previous()
    ) is None
    assert load_justifications() == {}
    assert list(tmp_path.iterdir()) == [sentinel]
    assert json.loads(sentinel.read_text(encoding="utf-8"))["violations"] == []


def test_aliases_still_resolve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Canonical var and documented legacy alias resolve to the same target."""
    for point in REBASELINE_ENTRY_POINTS:
        assert point.canonical_env in point.command
        canonical_target = tmp_path / f"{point.ratchet}-canonical.json"
        monkeypatch.setenv(point.canonical_env, str(canonical_target))
        resolved = resolve_rebaseline_target(point)
        assert resolved == canonical_target, point.ratchet
        monkeypatch.delenv(point.canonical_env)

        if not point.legacy_env:
            continue
        monkeypatch.setenv(point.legacy_env, str(canonical_target))
        assert resolve_rebaseline_target(point) == canonical_target, point.legacy_env
        # The canonical var wins when both are set.
        monkeypatch.setenv(point.canonical_env, str(canonical_target))
        assert resolve_rebaseline_target(point) == canonical_target
        monkeypatch.delenv(point.canonical_env)
        monkeypatch.delenv(point.legacy_env)

    # "<path|1>" ratchets may point at the committed file they guard.
    design_system = entry_point("design-system")
    committed = tmp_path / "design-system-ratchet.baseline.json"
    monkeypatch.setenv(design_system.canonical_env, "1")
    assert resolve_rebaseline_target(design_system, default_path=committed) == committed
    monkeypatch.setenv(design_system.legacy_env, "1")
    assert resolve_rebaseline_target(design_system, default_path=committed) == committed

    # A "1" with no default to point at is an error, not a silent no-op.
    monkeypatch.delenv(design_system.legacy_env)
    with pytest.raises(RatchetError):
        resolve_rebaseline_target(design_system)


def test_the_typescript_mirror_declares_the_same_contract() -> None:
    """The mirror names this module and contract version — pin both.

    Skipped where the frontend tree is not part of the checkout: the backend
    test container mounts ``backend/`` and ``docs/`` only, so the mirror is
    unreachable there by design. In a full checkout (host, CI) the pin runs and
    fails on a contract-version mismatch.
    """
    here = Path(__file__).resolve()
    mirror: Path | None = None
    for ancestor in here.parents:
        candidate = ancestor / TS_MIRROR_PATH
        if candidate.is_file():
            mirror = candidate
            break
    if mirror is None:
        pytest.skip(f"{TS_MIRROR_PATH} is not part of this checkout")
    text = mirror.read_text(encoding="utf-8")
    assert "mcp_server/tests/ratchet_framework.py" in text
    assert CONTRACT_VERSION in text
    for point in REBASELINE_ENTRY_POINTS:
        assert point.canonical_env in text, point.ratchet


# ---------------------------------------------------------------------------
# Part 2 -- stale detection primitive
# ---------------------------------------------------------------------------


def test_split_baseline_names_new_and_rotated_in_both_directions() -> None:
    diff = split_baseline({"a", "b"}, {"b", "c"})
    assert diff == BaselineDiff(new=("a",), rotated=("c",))
    assert split_baseline({"a"}, {"a"}) == BaselineDiff(new=(), rotated=())


def test_stale_entry_fails_loudly() -> None:
    """A baselined entry that no longer reproduces fails, and names the entry."""
    point = entry_point("entity-surface-parity")
    stale = "issue: Issue is REST-exposed at 'issues' but MCP has no 'issue.query' tool"
    diff = split_baseline({"still-reproducing"}, {stale, "still-reproducing"})

    with pytest.raises(AssertionError) as failure:
        assert_no_stale_entries(diff, point)
    message = str(failure.value)
    assert stale in message
    assert "still-reproducing" not in message
    assert "no longer reproduce" in message
    assert rebaseline_hint(point) in message

    # An empty rotation is fine — that is the normal, strict-shrinking state.
    assert_no_stale_entries(split_baseline({"live"}, {"live"}), point)


def test_the_two_halves_of_the_primitive_are_independent() -> None:
    """A new gap and a rotated gap are different findings and fail separately."""
    point = entry_point("entity-surface-parity")
    diff = split_baseline({"new-gap"}, {"rotated-gap"})
    with pytest.raises(AssertionError, match="not accepted"):
        assert_no_undocumented_gaps(diff, point)
    with pytest.raises(AssertionError, match="no longer reproduce"):
        assert_no_stale_entries(diff, point)
    assert unjustified_keys(diff, point, {}) == ["    new-gap: no justification supplied"]


def test_a_derived_mirror_justifies_the_other_direction() -> None:
    """The manifest ratchet guards the tool that DISAPPEARED from the mirror."""
    point = entry_point("tool-manifest-drift")
    assert point.justify_direction == JUSTIFY_ROTATED
    diff = split_baseline({"requirement.create"}, {"events.dlq_replay"})
    # A tool the manifest documents but the registry no longer has (#434).
    assert diff.rotated == ("events.dlq_replay",)
    assert diff.new == ("requirement.create",)
    assert unjustified_keys(diff, point, {}) == [
        "    events.dlq_replay: no justification supplied"
    ]
    with pytest.raises(UnjustifiedDumpError):
        assert_dump_justified(diff, point, {})
    # Documenting a new tool needs nobody's permission — but only while nothing
    # disappears: `events.dlq_replay` must stay in the measured set, otherwise
    # this fixture is the widening above wearing a different hat.
    assert_dump_justified(
        split_baseline({"new.tool", "events.dlq_replay"}, {"events.dlq_replay"}), point, {}
    )


# ---------------------------------------------------------------------------
# Part 3 -- reason + issue on every accepted gap
# ---------------------------------------------------------------------------


def test_gap_schema_requires_reason_and_issue() -> None:
    """No reason, a lazy reason, or no issue link: rejected on load and on dump."""
    point = entry_point("entity-surface-parity")
    too_short = {"gap": "a", "reason": LAZY_REASON, "issue": "#1103"}
    no_issue = {"gap": "a", "reason": ACCEPTED_REASON, "issue": "see the wiki"}
    good = {"gap": "a", "reason": ACCEPTED_REASON, "issue": "#1103"}
    legacy_ok = "glossary is REST-only by design (#1099)"

    # Load path: the legacy string is accepted BECAUSE it carries the marker.
    assert normalise_gap(legacy_ok).legacy is True
    assert load_gaps([good, legacy_ok]) == [
        normalise_gap(good),
        normalise_gap(legacy_ok),
    ]

    invalid_as_gap = (
        too_short,
        no_issue,
        {"gap": "", "reason": ACCEPTED_REASON, "issue": "#1103"},
        {"reason": ACCEPTED_REASON, "issue": "#1103"},
        "no issue marker in this legacy string",
        17,
        {"gap": "a", "reason": ACCEPTED_REASON, "issue": None},
    )
    for bad in invalid_as_gap:
        with pytest.raises(GapSchemaError):
            normalise_gap(bad, source="load")

    # The same rule on the dump path. A justification is a gap entry minus its
    # key, so the key is not an escape hatch: a widening still has to say why.
    invalid_as_justification = (
        too_short,
        {"reason": LAZY_REASON, "issue": "#1103"},
        {"reason": ACCEPTED_REASON},
        {"reason": ACCEPTED_REASON, "issue": "see the wiki"},
        "no issue marker in this legacy string",
        17,
        None,
    )
    for bad in invalid_as_justification:
        with pytest.raises(UnjustifiedDumpError):
            assert_dump_justified(split_baseline({REGRESSION}, set()), point, {REGRESSION: bad})

    # Every problem in a list is reported, not just the first one.
    with pytest.raises(GapSchemaError) as failure:
        load_gaps([too_short, no_issue], source="entity_surface_baseline.json")
    message = str(failure.value)
    assert "2 invalid accepted gap(s)" in message
    assert too_short["gap"] in message and no_issue["gap"] in message


def test_a_justified_dump_cannot_smuggle_an_unjustified_entry_in(
    tmp_path: Path,
) -> None:
    """The previous baseline is validated before a dump writes anything."""
    point = entry_point("entity-surface-parity")
    target = tmp_path / "candidate.json"
    previous = {
        "violations": [{"gap": "old", "reason": LAZY_REASON, "issue": "#1102"}],
    }
    with pytest.raises(GapSchemaError) as failure:
        write_baseline(
            point=point,
            target=target,
            measured={"old", REGRESSION},
            previous=previous,
            justify=_justified(),
        )
    assert "old" in str(failure.value)
    assert not target.exists()


def test_the_reason_floor_is_not_negotiable_by_whitespace() -> None:
    padded = {"gap": "a", "reason": " " * 60, "issue": "#1103"}
    with pytest.raises(GapSchemaError):
        normalise_gap(padded)


# ---------------------------------------------------------------------------
# Part 4b -- the counter-shaped ratchet (mirrored on the TS side)
# ---------------------------------------------------------------------------


def test_ceiling_guard_is_monotonically_non_increasing() -> None:
    """A re-baseline keeps or lowers a ceiling, never raises it."""
    assert_ceiling_not_raised("emoji-as-ui-glyph", 5, 5, True)
    assert_ceiling_not_raised("emoji-as-ui-glyph", 5, 3, True)
    # The bootstrap run that creates a missing baseline may raise it, otherwise
    # the gate could never be installed.
    assert_ceiling_not_raised("emoji-as-ui-glyph", 0, 6, False)
    with pytest.raises(AssertionError, match="monotonically non-increasing"):
        assert_ceiling_not_raised("emoji-as-ui-glyph", 5, 6, True)


def test_entry_points_are_frozen_data() -> None:
    """The table is a constant, not something a suite can edit at runtime."""
    with pytest.raises(FrozenInstanceError):
        REBASELINE_ENTRY_POINTS[0].canonical_env = "NOPE"  # type: ignore[misc]
    assert isinstance(entry_point("design-system"), RebaselineEntryPoint)
    with pytest.raises(RatchetError):
        entry_point("no-such-ratchet")
