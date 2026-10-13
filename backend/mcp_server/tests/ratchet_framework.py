"""The shared ratchet/baseline framework (#1103 / REQ-193).

Three suites in this repository each freeze a *measured* set against a
*baselined* set, and until now each of them did it in its own private dialect:
the entity-surface parity ratchet had a named dump env var, a stale detector
and a documented recipe; the tool-manifest drift guard had a full comparison
but no re-baseline entry point at all; the design-system ratchet (frontend,
see the TypeScript mirror below) had a monotonic ceiling but no shared schema.
Three dialects mean three places to forget a guard, and the audit that produced
#1103 found exactly that: the two weaker ratchets were one refactor away from
letting a real regression through.

This module lifts all of them onto one contract. It is deliberately small --
it holds no policy of its own, so that a ratchet's *measurement* code stays
readable and only its *bookkeeping* is shared.

The contract (four parts, all enforced here)
--------------------------------------------
1. **Named re-baseline.** Every ratchet owns exactly one env var, listed in the
   table below. A re-baseline is a command a human types; it is never a side
   effect of a normal run (``maybe_rebaseline`` writes only when the env var is
   set, and reads nothing otherwise). Legacy names keep working as documented
   aliases so the recipes already recorded in the repo stay runnable.
2. **Stale detection as a primitive.** :func:`split_baseline` splits a measured
   set against a baselined set into ``new`` (measured, not accepted) and
   ``rotated`` (accepted, no longer reproduces). :func:`assert_no_stale_entries`
   turns the second into a failure that names the entry and the command that
   removes it: a baseline entry that can no longer happen is a claim nobody is
   checking.
3. **Allowed gaps carry reason + issue.** An accepted gap is either a legacy
   plain string containing an ``#\\d+`` marker (the shape the entity-surface
   ratchet has always recorded) or a structured
   ``{"gap": ..., "reason": ..., "issue": ...}`` entry. The reason must be at
   least :data:`GAP_MIN_REASON_LENGTH` characters -- long enough to say why
   *this* gap is acceptable -- and the issue must reference a real tracker
   item. Enforced on baseline load (:func:`load_gaps`) *and* before any dump is
   written (:func:`write_baseline` validates the previous baseline first).
4. **A regression cannot be re-baselined away.** The dump path computes
   ``new = measured - previous_baseline`` and refuses to write anything unless
   every entry in that widening carries a justification supplied by the caller
   (inline, or through ``$RATCHET_JUSTIFY``). A justified dump writes the
   justification into the baseline, so the widening is auditable in the diff
   that produced it. :func:`assert_ceiling_not_raised` adds the counter-shaped
   variant for ratchets whose baseline holds a ceiling rather than a list.

Re-baseline entry points (the one table -- add a ratchet here, nowhere else)
----------------------------------------------------------------------------
======================  =========================  =====================  ========================================================================================================================  ==============================================================
Ratchet                 Canonical env var          Legacy alias (kept)    Command                                                                                                                Writes
======================  =========================  =====================  ========================================================================================================================  ==============================================================
entity-surface-parity   ENTITY_SURFACE_REBASELINE  ENTITY_SURFACE_DUMP    ENTITY_SURFACE_REBASELINE=/tmp/entity-surface.json pytest mcp_server/tests/test_entity_surface_parity.py -q                /tmp/entity-surface.json -- a CANDIDATE entity_surface_baseline.json; copy it over deliberately
design-system           DESIGN_SYSTEM_REBASELINE   DESIGN_SYSTEM_RATCHET_ DESIGN_SYSTEM_REBASELINE=1 npx vitest run src/test/design-system-ratchet.test.ts                                                frontend/src/test/design-system-ratchet.baseline.json, in place
                                                    DUMP
tool-manifest-drift     TOOL_MANIFEST_REBASELINE   --                     TOOL_MANIFEST_REBASELINE=1 pytest mcp_server/tests/test_tool_manifest_drift.py -q                                               docs/agent-templates/tool-manifest.json, regenerated from the live registry
======================  =========================  =====================  ========================================================================================================================  ==============================================================

``<path|1>``: ``1`` means "the committed file this ratchet guards", any other
value writes a candidate elsewhere. The alias column exists because the recipes
already committed in the repo (the ``_comment`` of
``entity_surface_baseline.json``, the header of ``design-system-ratchet.test.ts``)
name the legacy var; they keep working unchanged.

TypeScript mirror
-----------------
``frontend/src/test/ratchet-framework.ts`` implements this same contract for the
frontend ratchets and names this module (path + :data:`CONTRACT_VERSION`) in its
header, so the two stay comparable. It is a *mirror of the contract*, not a
cross-language bridge framework: there is no shared runtime, no codegen and no
dual implementation of any measurement. The only shape difference is that a TS
exemption carries its gap identity in the map key, so its structured form is
``{reason, issue}`` where a Python gap entry is ``{gap, reason, issue}`` -- the
rule behind both is identical.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

__all__ = [
    "CONTRACT_VERSION",
    "GAP_MIN_REASON_LENGTH",
    "ISSUE_PATTERN",
    "JUSTIFICATION_ENV_VAR",
    "JUSTIFY_NEW",
    "JUSTIFY_ROTATED",
    "REBASELINE_ENTRY_POINTS",
    "TS_MIRROR_PATH",
    "BaselineDiff",
    "Gap",
    "GapSchemaError",
    "Justification",
    "RatchetError",
    "RebaselineEntryPoint",
    "UnjustifiedDumpError",
    "assert_ceiling_not_raised",
    "assert_dump_justified",
    "assert_no_stale_entries",
    "assert_no_undocumented_gaps",
    "entry_point",
    "gap_keys",
    "load_gaps",
    "load_justifications",
    "maybe_rebaseline",
    "normalise_gap",
    "rebaseline_hint",
    "resolve_rebaseline_target",
    "split_baseline",
    "unjustified_keys",
    "write_baseline",
]

#: Version of this contract. Bump it when a change is not backwards compatible
#: for both sides (the TS mirror names the same number).
CONTRACT_VERSION = "1.0.0"

#: Where the TypeScript mirror of this contract lives, relative to the repo root.
TS_MIRROR_PATH = "frontend/src/test/ratchet-framework.ts"

#: An accepted gap must say WHY it is acceptable, in at least this many
#: characters. 40 is long enough to name a reason and short enough that nobody
#: has to write an essay; the point is that "too hard" (8 characters) fails.
GAP_MIN_REASON_LENGTH = 40

#: An accepted gap must point at a tracker item. Search, not fullmatch: a
#: justification routinely references two issues ("#1099, #1103").
ISSUE_PATTERN = re.compile(r"#\d+")

#: Inline JSON (or a path to a JSON file) mapping gap key -> justification,
#: read by :func:`load_justifications`. Part of the dump protocol only: a
#: normal run never looks at it.
JUSTIFICATION_ENV_VAR = "RATCHET_JUSTIFY"

#: The widening direction a dump has to justify for a *list-shaped* baseline:
#: a gap the previous baseline did not accept.
JUSTIFY_NEW = "new"

#: The widening direction for a ratchet whose baseline is a DERIVED MIRROR of a
#: live registry rather than a list of accepted gaps. For the tool manifest the
#: danger is not "the manifest documents a tool the registry has" but the
#: opposite: a tool the manifest stops documenting. Every agent template is
#: generated from that manifest, so a tool that silently disappears from it is a
#: contract break (#434) -- and "re-baseline it away" is exactly the escape
#: hatch a ratchet must not offer.
JUSTIFY_ROTATED = "rotated"

#: Env var values that mean "the committed file this ratchet guards".
_SENTINELS = frozenset({"1", "true", "yes"})


class RatchetError(RuntimeError):
    """Base class for every failure this framework raises on its own."""


class GapSchemaError(RatchetError):
    """A baseline entry (or a justification) does not carry reason + issue."""


class UnjustifiedDumpError(RatchetError):
    """A re-baseline tried to widen the accepted set without a justification."""


@dataclass(frozen=True)
class RebaselineEntryPoint:
    """One ratchet's named re-baseline command (see the table in the module docstring)."""

    #: Short id, used to look the entry point up.
    ratchet: str
    #: The suite that implements the ratchet, for error messages.
    suite: str
    #: Canonical env var name (without the ``=<value>`` part).
    canonical_env: str
    #: What the canonical env var's value means.
    placeholder: str
    #: Legacy env var name that keeps working, or ``""``.
    legacy_env: str
    #: The exact command, copy-pasteable, that re-baselines this ratchet.
    command: str
    #: What that command writes, and what the reader has to do with it.
    writes: str
    #: ``JUSTIFY_NEW`` or ``JUSTIFY_ROTATED`` -- which direction of the diff is
    #: a widening for this ratchet.
    justify_direction: str = JUSTIFY_NEW

    @property
    def canonical_form(self) -> str:
        """``ENTITY_SURFACE_REBASELINE=<path>`` -- the table's canonical column."""
        return f"{self.canonical_env}={self.placeholder}"

    @property
    def legacy_form(self) -> str:
        """The alias as it is typed, or ``"--"`` when the ratchet has none."""
        return f"{self.legacy_env}={self.placeholder}" if self.legacy_env else "--"


REBASELINE_ENTRY_POINTS: Tuple[RebaselineEntryPoint, ...] = (
    RebaselineEntryPoint(
        ratchet="entity-surface-parity",
        suite="backend/mcp_server/tests/test_entity_surface_parity.py",
        canonical_env="ENTITY_SURFACE_REBASELINE",
        placeholder="<path>",
        legacy_env="ENTITY_SURFACE_DUMP",
        command=(
            "ENTITY_SURFACE_REBASELINE=/tmp/entity-surface.json "
            "pytest mcp_server/tests/test_entity_surface_parity.py -q"
        ),
        writes=(
            "/tmp/entity-surface.json -- a CANDIDATE entity_surface_baseline.json; "
            "the committed file is only ever replaced by a deliberate copy"
        ),
    ),
    RebaselineEntryPoint(
        ratchet="design-system",
        suite="frontend/src/test/design-system-ratchet.test.ts",
        canonical_env="DESIGN_SYSTEM_REBASELINE",
        placeholder="<path|1>",
        legacy_env="DESIGN_SYSTEM_RATCHET_DUMP",
        command=(
            "DESIGN_SYSTEM_REBASELINE=1 npx vitest run "
            "src/test/design-system-ratchet.test.ts"
        ),
        writes=(
            "frontend/src/test/design-system-ratchet.baseline.json, in place; "
            "a <path> value writes a candidate instead"
        ),
    ),
    RebaselineEntryPoint(
        ratchet="tool-manifest-drift",
        suite="backend/mcp_server/tests/test_tool_manifest_drift.py",
        canonical_env="TOOL_MANIFEST_REBASELINE",
        placeholder="<path|1>",
        legacy_env="",
        command=(
            "TOOL_MANIFEST_REBASELINE=1 pytest "
            "mcp_server/tests/test_tool_manifest_drift.py -q"
        ),
        writes=(
            "docs/agent-templates/tool-manifest.json, regenerated from the live "
            "registry via export_tool_manifest; in Docker docs/ is mounted "
            "read-only, so write a <path> candidate and copy it in"
        ),
        justify_direction=JUSTIFY_ROTATED,
    ),
)


def entry_point(point: Union[RebaselineEntryPoint, str]) -> RebaselineEntryPoint:
    """Resolve a ratchet id (or pass through an entry point)."""
    if isinstance(point, RebaselineEntryPoint):
        return point
    for candidate in REBASELINE_ENTRY_POINTS:
        if candidate.ratchet == point:
            return candidate
    known = ", ".join(p.ratchet for p in REBASELINE_ENTRY_POINTS)
    raise RatchetError(f"unknown ratchet {point!r}; known ratchets: {known}")


def rebaseline_hint(point: Union[RebaselineEntryPoint, str]) -> str:
    """The copy-pasteable command, for failure messages that offer a way out."""
    return entry_point(point).command


# ---------------------------------------------------------------------------
# Part 1 -- the named re-baseline entry point
# ---------------------------------------------------------------------------


def resolve_rebaseline_target(
    point: Union[RebaselineEntryPoint, str],
    *,
    default_path: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[Path]:
    """Return where a re-baseline should write, or ``None`` for a normal run.

    The canonical env var wins; the documented legacy alias is honoured so the
    recipes already committed in the repo keep working. A value of ``1`` (or
    ``true`` / ``yes``) means "the committed file this ratchet guards" and
    needs *default_path*.
    """
    resolved = entry_point(point)
    environ = os.environ if env is None else env
    raw = ""
    for name in (resolved.canonical_env, resolved.legacy_env):
        if name and environ.get(name):
            raw = environ[name]
            break
    if not raw.strip():
        return None
    if raw.strip().lower() in _SENTINELS:
        if default_path is None:
            raise RatchetError(
                f"${resolved.canonical_form} asks for the committed file, but this "
                "ratchet declares no default path. Point the variable at an "
                f"explicit path instead: {resolved.canonical_form}"
            )
        return Path(default_path)
    return Path(raw).expanduser()


# ---------------------------------------------------------------------------
# Part 2 -- stale detection primitive
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineDiff:
    """A measured set split against a baselined set."""

    #: Measured now, absent from the baseline -- a gap nobody has accepted.
    new: Tuple[str, ...]
    #: Baselined, absent from the measurement -- a claim that is no longer true.
    rotated: Tuple[str, ...]


def split_baseline(
    measured: Iterable[str], baselined: Iterable[str]
) -> BaselineDiff:
    """Split *measured* against *baselined* into (new, rotated).

    Both sides are keyed sets: a ratchet's measurement must be idempotent per
    key, otherwise the diff cannot say which entry is the new one.
    """
    live: Set[str] = set(measured)
    known: Set[str] = set(baselined)
    return BaselineDiff(new=tuple(sorted(live - known)), rotated=tuple(sorted(known - live)))


def assert_no_undocumented_gaps(
    diff: BaselineDiff, point: Union[RebaselineEntryPoint, str]
) -> None:
    """Fail when the measurement produced a gap the baseline does not accept."""
    resolved = entry_point(point)
    if not diff.new:
        return
    listed = "\n".join(f"    {key}" for key in diff.new)
    raise AssertionError(
        f"{len(diff.new)} gap(s) not accepted by the {resolved.ratchet} baseline:\n"
        f"{listed}\n"
        "Fix the defect (that is what the ratchet is for), or accept the gap "
        "deliberately with\n"
        f"    {resolved.command}\n"
        "and justify it in the baseline that command produces."
    )


def assert_no_stale_entries(
    diff: BaselineDiff, point: Union[RebaselineEntryPoint, str]
) -> None:
    """Fail when an accepted gap no longer reproduces.

    The strict-shrink half of a ratchet: an entry that can no longer happen has
    to be deleted, because a baseline entry nobody checks is how a gate stops
    being a gate.
    """
    resolved = entry_point(point)
    if not diff.rotated:
        return
    listed = "\n".join(f"    {key}" for key in diff.rotated)
    raise AssertionError(
        f"{len(diff.rotated)} baselined gap(s) no longer reproduce in the "
        f"{resolved.ratchet} ratchet:\n"
        f"{listed}\n"
        "Delete them from the baseline -- a claim nobody is checking is worse "
        "than no claim. Re-baseline wholesale with:\n"
        f"    {resolved.command}"
    )


# ---------------------------------------------------------------------------
# Part 3 -- reason + issue on every accepted gap
# ---------------------------------------------------------------------------

#: What a caller may hand over as "why this gap is acceptable".
Justification = Union[str, Mapping[str, Any]]


@dataclass(frozen=True)
class Gap:
    """One accepted gap, normalised out of whatever shape the baseline stored."""

    #: The measurement key the gap is accepted under.
    key: str
    #: Why it is acceptable (>= GAP_MIN_REASON_LENGTH characters).
    reason: str
    #: The tracker item that accepts it.
    issue: str
    #: True when the baseline still stores this gap as a bare string.
    legacy: bool = False

    def as_entry(self) -> Union[str, Dict[str, str]]:
        """The shape this gap is written back in."""
        if self.legacy:
            return self.key
        return {"gap": self.key, "reason": self.reason, "issue": self.issue}


def _check_reason(reason: Any, label: str) -> Optional[str]:
    """Return a problem string, or None when *reason* is substantive enough."""
    if not isinstance(reason, str) or not reason.strip():
        return f"{label}: reason must be a non-empty string"
    if len(reason.strip()) < GAP_MIN_REASON_LENGTH:
        return (
            f"{label}: reason is {len(reason.strip())} characters and must be at "
            f"least {GAP_MIN_REASON_LENGTH} — it has to say why THIS gap is "
            "acceptable, not restate the rule"
        )
    return None


def _check_issue(issue: Any, label: str) -> Optional[str]:
    """Return a problem string, or None when *issue* references a tracker item."""
    if not isinstance(issue, str) or not ISSUE_PATTERN.search(issue):
        return f"{label}: issue must reference a tracker item (e.g. '#1103')"
    return None


def _validate_gap_entry(entry: Any) -> Tuple[Optional[Gap], Optional[str]]:
    """Classify one baseline entry as (gap, None) or (None, problem)."""
    if isinstance(entry, str):
        if not ISSUE_PATTERN.search(entry):
            return (
                None,
                "legacy string entry carries no issue marker (expected an '#NNN' "
                "reference in the text); rewrite it as "
                '{"gap": ..., "reason": ..., "issue": ...}',
            )
        return Gap(key=entry, reason=entry, issue=entry, legacy=True), None
    if isinstance(entry, Mapping):
        gap = entry.get("gap")
        if not isinstance(gap, str) or not gap.strip():
            return None, "structured entry needs a non-empty 'gap' key"
        label = f"gap {gap!r}"
        for problem in (
            _check_reason(entry.get("reason"), label),
            _check_issue(entry.get("issue"), label),
        ):
            if problem is not None:
                return None, problem
        return (
            Gap(
                key=gap,
                reason=str(entry["reason"]).strip(),
                issue=str(entry["issue"]),
            ),
            None,
        )
    return None, f"entry must be a string or a mapping, got {type(entry).__name__}"


def normalise_gap(entry: Any, *, source: str = "") -> Gap:
    """Validate one baseline entry and return it as a :class:`Gap`."""
    gap, problem = _validate_gap_entry(entry)
    if problem is not None:
        where = f"{source}: " if source else ""
        raise GapSchemaError(f"{where}{problem}")
    assert gap is not None  # _validate_gap_entry never returns (None, None)
    return gap


def load_gaps(entries: Sequence[Any], *, source: str = "") -> List[Gap]:
    """Validate every entry of a baseline's gap list, reporting all problems at once.

    Enforced on LOAD: a baseline that carries an unjustified accepted gap fails
    here, before any comparison runs.
    """
    gaps: List[Gap] = []
    problems: List[str] = []
    for index, entry in enumerate(entries):
        gap, problem = _validate_gap_entry(entry)
        if problem is not None:
            where = f"{source} entry {index}" if source else f"entry {index}"
            problems.append(f"  {where}: {problem}")
        else:
            assert gap is not None
            gaps.append(gap)
    if problems:
        raise GapSchemaError(
            f"{len(problems)} invalid accepted gap(s) in {source or 'the baseline'}:\n"
            + "\n".join(problems)
            + f"\nEvery accepted gap needs a reason of at least "
            f"{GAP_MIN_REASON_LENGTH} characters and an '#NNN' issue reference."
        )
    return gaps


def gap_keys(entries: Sequence[Any], *, source: str = "") -> Set[str]:
    """The set of accepted gap keys in a baseline's gap list."""
    return {gap.key for gap in load_gaps(entries, source=source)}


# ---------------------------------------------------------------------------
# Part 4 -- a justified dump, so a regression cannot be re-baselined away
# ---------------------------------------------------------------------------


def load_justifications(
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, Justification]:
    """Read ``$RATCHET_JUSTIFY`` -- the justifications a dump has to carry.

    The value is either a path to a JSON file or inline JSON; both must decode
    to an object mapping gap key -> justification (a reason string, or
    ``{"reason": ..., "issue": ...}``).
    """
    environ = os.environ if env is None else env
    raw = (environ.get(JUSTIFICATION_ENV_VAR) or "").strip()
    if not raw:
        return {}
    text = ""
    try:
        candidate = Path(raw).expanduser()
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8")
        else:
            text = raw
    except (OSError, ValueError):
        # Inline JSON is the common case, and a long one is not a filename:
        # ENAMETOOLONG must not be mistaken for "this file does not exist".
        text = raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - operator error
        raise GapSchemaError(
            f"${JUSTIFICATION_ENV_VAR} is neither a readable JSON file nor inline "
            f"JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise GapSchemaError(
            f"${JUSTIFICATION_ENV_VAR} must decode to an object mapping gap key "
            f"-> justification, got {type(data).__name__}"
        )
    return data


def _justification_parts(value: Justification) -> Tuple[str, str, Optional[str]]:
    """Split a justification into (reason, issue, problem)."""
    if isinstance(value, str):
        problem = _check_reason(value, "justification") or _check_issue(value, "justification")
        return value.strip(), value.strip(), problem
    if isinstance(value, Mapping):
        reason = value.get("reason")
        issue = value.get("issue")
        problems = [
            problem
            for problem in (
                _check_reason(reason, "justification"),
                _check_issue(issue, "justification"),
            )
            if problem is not None
        ]
        return str(reason or "").strip(), str(issue or ""), problems[0] if problems else None
    return "", "", f"justification must be a string or a mapping, got {type(value).__name__}"


def unjustified_keys(
    diff: BaselineDiff,
    point: Union[RebaselineEntryPoint, str],
    justify: Optional[Mapping[str, Justification]] = None,
) -> List[str]:
    """The widening entries that lack a usable justification.

    "Widening" is :data:`JUSTIFY_NEW` for a ratchet whose baseline lists accepted
    gaps, and :data:`JUSTIFY_ROTATED` for one whose baseline is a derived mirror
    of a live registry (see :data:`JUSTIFY_ROTATED`).
    """
    resolved = entry_point(point)
    justifications = load_justifications() if justify is None else justify
    widening = (
        diff.rotated if resolved.justify_direction == JUSTIFY_ROTATED else diff.new
    )
    problems: List[str] = []
    for key in widening:
        if key not in justifications:
            problems.append(f"    {key}: no justification supplied")
            continue
        _, _, problem = _justification_parts(justifications[key])
        if problem is not None:
            problems.append(f"    {key}: {problem}")
    return problems


def assert_dump_justified(
    diff: BaselineDiff,
    point: Union[RebaselineEntryPoint, str],
    justify: Optional[Mapping[str, Justification]] = None,
) -> None:
    """Refuse a dump that widens the accepted set without justification.

    This is the guard #1103 asks for: the dump path computes
    ``new = measured - previous_baseline`` and hard-fails unless every entry in
    that set carries a reason plus an issue, so "just re-baseline it" is never a
    way to make a genuine regression disappear.
    """
    resolved = entry_point(point)
    problems = unjustified_keys(diff, resolved, justify)
    if not problems:
        return
    listed = "\n".join(problems)
    example = (
        f"    {JUSTIFICATION_ENV_VAR}='"
        + json.dumps({"<gap key>": {"reason": "...", "issue": "#NNN"}})
        + "' \\"
    )
    raise UnjustifiedDumpError(
        f"refusing to re-baseline {resolved.ratchet}: {len(problems)} widened "
        f"entr(y/ies) without a justification\n"
        f"{listed}\n"
        f"A re-baseline is how a widening becomes auditable, so it must state why "
        f"each new entry is acceptable — in at least {GAP_MIN_REASON_LENGTH} "
        "characters, with an '#NNN' issue reference.\n"
        f"Supply them via ${JUSTIFICATION_ENV_VAR} (inline JSON or a path to a "
        "JSON file), one entry per widened key:\n"
        f"{example}\n"
        f"        {resolved.command}\n"
        "Or fix the defect instead — that is what the ratchet is for."
    )


def write_baseline(
    *,
    point: Union[RebaselineEntryPoint, str],
    target: Path,
    measured: Iterable[str],
    previous: Optional[Mapping[str, Any]] = None,
    justify: Optional[Mapping[str, Justification]] = None,
    document: Optional[Mapping[str, Any]] = None,
    gaps_key: str = "violations",
) -> BaselineDiff:
    """Write a re-baselined gap list, refusing an unjustified widening.

    The written set is *measured*: entries that no longer reproduce are dropped
    (that is the point of a re-baseline) and entries that are new carry the
    justification that made them acceptable. Nothing is written unless every
    new entry is justified, so a refused dump leaves the target untouched.
    """
    resolved = entry_point(point)
    justifications = load_justifications() if justify is None else justify
    previous_entries: Sequence[Any] = ()
    if previous is not None:
        raw = previous.get(gaps_key, [])
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            previous_entries = list(raw)
    known = {
        gap.key: gap
        for gap in load_gaps(previous_entries, source=f"{resolved.ratchet} baseline")
    }
    measured_keys = set(measured)
    diff = split_baseline(measured_keys, known)
    assert_dump_justified(diff, resolved, justifications)

    entries: List[Union[str, Dict[str, str]]] = []
    for key in sorted(measured_keys):
        existing = known.get(key)
        if existing is not None:
            entries.append(existing.as_entry())
            continue
        reason, issue, problem = _justification_parts(justifications[key])
        assert problem is None  # assert_dump_justified already checked this
        entries.append({"gap": key, "reason": reason, "issue": issue})

    out: Dict[str, Any] = dict(document or {})
    out[gaps_key] = entries
    # Provenance: the widening is auditable in the diff that produced it.
    out["rebaselined_by"] = resolved.command
    out["contract"] = f"ratchet-framework/{CONTRACT_VERSION}"
    target.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return diff


def maybe_rebaseline(
    point: Union[RebaselineEntryPoint, str],
    *,
    measured: Iterable[str],
    previous: Optional[Mapping[str, Any]] = None,
    document: Optional[Mapping[str, Any]] = None,
    target: Optional[Path] = None,
    default_path: Optional[Path] = None,
    justify: Optional[Mapping[str, Justification]] = None,
    gaps_key: str = "violations",
    env: Optional[Mapping[str, str]] = None,
) -> Optional[BaselineDiff]:
    """Write a re-baseline -- and ONLY when the named env var asks for one.

    The whole of part 1 in one call: a normal run resolves no target, reads no
    dump and writes no file. A ratchet therefore cannot re-baseline by accident,
    because the only code path that writes is behind an env var a human typed.
    """
    resolved_target = target or resolve_rebaseline_target(
        point, default_path=default_path, env=env
    )
    if resolved_target is None:
        return None
    return write_baseline(
        point=point,
        target=resolved_target,
        measured=measured,
        previous=previous,
        justify=justify,
        document=document,
        gaps_key=gaps_key,
    )


def assert_ceiling_not_raised(
    check: str,
    previous_max: int,
    measured: int,
    baseline_exists: bool,
) -> None:
    """Monotonicity guard for a ceiling-shaped baseline (``maxViolations``).

    Mirrored by the TS side as ``assertBaselineNotRaised``. A re-baseline may
    keep or lower a ceiling, never raise it: a fresh violation is fixed or
    explicitly exempted, so it can never be silently absorbed into the number.
    The one legal increase is the bootstrap run that creates a missing baseline
    file, otherwise the gate could never be installed.
    """
    if not baseline_exists:
        return
    if measured > previous_max:
        raise AssertionError(
            f'refusing to raise the "{check}" baseline from {previous_max} to '
            f"{measured}: the ratchet is monotonically non-increasing "
            "(#1103 / REQ-193).\n"
            "Fix the new violation(s), or exempt them individually with a "
            "substantive reason. Never raise the ceiling."
        )
