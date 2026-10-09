"""Issue #1113 — guard e2e against data-testid values the frontend no longer has.

Playwright never errors on a missing selector: ``click()`` on a
``[data-testid=...]`` that matches nothing waits out its timeout and fails ten
seconds later with a *timeout* message, not with a message about the drift.
That is how the two #985 dismissal pins kept clicking
``notification-bell-toggle`` for a full release cycle after ADR-009 removed the
notification bell — every failure looked like a flaky overlay test, not like a
deleted component.

This module makes that drift visible statically: it extracts every
*statically knowable* data-testid literal referenced anywhere under ``e2e/``
and checks it against the data-testid attributes ``frontend/src/**`` renders.
The data-testid axis is the mandatory one (AGENTS.md); role/label/text
selectors are deliberately out of scope.

What is checked and what cannot be — the documented limitation:

* e2e side — literal ``getByTestId('x')`` and ``[data-testid="x"]``
  references. Template literals (``getByTestId(`row-${id}`)``), helper-call
  references (``getByTestId(needRow(id))``) and non-equality attribute
  selectors (``[data-testid^=...]``, ``[data-testid$=...]``) are *counted* and
  skipped: they cannot be resolved without executing the code.
* frontend side — the allowed set is built from every channel that feeds a
  rendered ``data-testid``: the attribute itself (``data-testid="x"``), every
  ``*TestId*``-named channel (``testId`` prop, ``saveTestId`` destructuring
  default, ``{ testId: 'create-req-btn' }`` config object) and ``*TestIds``
  maps (``fieldTestIds={{ title: 'req-new-title-input' }}``). Composed ids
  come from templates on testid-context lines: a single-interpolation
  template (``data-testid={`artifact-field-${name}`}``) becomes a
  prefix/suffix pattern, and a template anchored on a carrier variable
  (``data-testid={`${testId}-confirm`}`` with ``testId="artifact-form-delete-confirm"``,
  or ``data-testid={`${optionTestIdPrefix}-option-${key}`}`` with
  ``optionTestIdPrefix="create-trace-link-type"``) is joined with that
  carrier's literal values across ``frontend/src``.

Both pattern kinds anchor on a static literal, so a removed component loses
its whole id family and is still caught — ``notification-bell-toggle`` has no
pattern to hide behind. What a pattern cannot catch is a renamed *member* of
a surviving family (e.g. a renamed option key inside a surviving listbox) or
any id composed from runtime data with no static anchor at all; those
mentions are counted and reported as skipped, not silently passed.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

import pytest

#: JS/TS suffixes on both sides of the check.
_SOURCE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})

#: Generated or vendored trees whose content is not hand-maintained source.
#: e2e/playwright-report and e2e/test-results in particular serialize
#: selectors into records that must never feed the allowed set.
_SKIPPED_DIRS = frozenset(
    {"node_modules", "dist", "playwright-report", "test-results", ".git"}
)

#: Same escape hatch as test_version_drift_workflow_security.py: point the
#: check at a checkout when the test file itself lives somewhere else.
_REPO_ROOT_ENV = "REQLO_REPO_ROOT"

#: The historical rot this guard exists for (ADR-009 / PR #1111, CHANGELOG
#: v1.8.0-beta.17): e2e pins clicked it for a full release cycle. It must
#: never reappear in e2e/, so its absence is asserted directly.
_HISTORICAL_TESTID = "notification-bell-toggle"

#: Quote characters that may delimit a literal in JS/TSX.
_QUOTES = "'\"`"

# ---------------------------------------------------------------------------
# e2e side — reference extraction
# ---------------------------------------------------------------------------

#: ``getByTestId('value')`` — also with double quotes or a backtick template.
#: The closing paren is deliberately not required: the call often carries a
#: second options argument (``getByTestId('x', { timeout: 5000 })``).
_GET_BY_TESTID = re.compile(rf"getByTestId\(\s*([{_QUOTES}])([^{_QUOTES}]*)\1")

#: ``data-testid='value'`` — also matches the inside of ``[data-testid="v"]``
#: locator selectors and the JSX expression form ``data-testid={'v'}``. The
#: ``=`` is spelled out, so ``[data-testid^=...]`` prefix matches and
#: ``[data-testid$=...]`` suffix matches do NOT match: those are partial-match
#: selectors whose operand is not a full id.
_DATA_TESTID = re.compile(
    rf"data-testid\s*=\s*\{{?\s*([{_QUOTES}])([^{_QUOTES}]*)\1"
)

#: Counters for the *mentions* that carry no resolvable literal.
_GET_BY_TESTID_CALL = re.compile(r"getByTestId\(")
_DATA_TESTID_MENTION = re.compile(r"data-testid")

# ---------------------------------------------------------------------------
# frontend side — definition extraction
# ---------------------------------------------------------------------------

#: Every channel whose *name* marks it as a testid carrier — the ``testId``
#: prop itself plus ``saveTestId``, ``confirmTestId``, ``optionTestIdPrefix``
#: and friends — in all three binding shapes: JSX attribute
#: (``testId="x"`` / ``testId={'x'}``), config-object property
#: (``testId: 'x'``) and destructuring default (``saveTestId = "artifact-form-save"``).
#: Values bound to a channel whose name also contains "prefix" are prefixes,
#: not full ids.
_TESTID_CHANNEL = re.compile(
    rf"(?<![-\w])([A-Za-z_]\w*)\s*(?:=|:)\s*\{{?\s*([{_QUOTES}])([^{_QUOTES}]*)\2"
)

#: ``fieldTestIds={{ title: 'req-new-title-input' }}`` — map values that flow
#: into the ``testId`` prop and render as data-testid attributes.
_TESTID_MAP = re.compile(r"[Tt]est[Ii]ds\s*=\s*\{\{([^}]*)\}\}")
_MAP_VALUE = re.compile(rf"[{_QUOTES}]([^{_QUOTES}]+)[{_QUOTES}]")

#: A template literal anywhere in the file — only templates on a line that
#: mentions ``testid`` in any casing are interpreted, so unrelated template
#: literals never contribute to the allowed set.
_TEMPLATE_LITERAL = re.compile(r"`([^`]*)`")
_TESTID_CONTEXT_LINE = re.compile(r"(?i)testid")

#: ``${...}`` — one interpolation. The whole expression is consumed (not just
#: ``${``) so splitting a template on it leaves plain literal segments behind.
_INTERPOLATION = re.compile(r"\$\{[^}]*\}")

#: A bare identifier interpolation expression (``${name}``) — a property path
#: like ``${item.id}`` is not a resolvable carrier reference.
_IDENTIFIER = re.compile(r"^\w+$")


def _is_testid_channel(name: str) -> bool:
    lowered = name.lower()
    return "testid" in lowered


def _is_prefix_carrier(name: str) -> bool:
    lowered = name.lower()
    return "testid" in lowered and "prefix" in lowered


class Reference(NamedTuple):
    """One statically-resolvable testid reference found in e2e/."""

    value: str
    source: str


@dataclass(frozen=True)
class Definition:
    """The frontend's allowed set: exact ids plus derived patterns."""

    exact: Set[str] = field(default_factory=set)
    patterns: Set[Tuple[str, str]] = field(default_factory=set)

    def allows(self, value: str) -> bool:
        if value in self.exact:
            return True
        return any(
            len(value) >= len(prefix) + len(suffix)
            and value.startswith(prefix)
            and value.endswith(suffix)
            for prefix, suffix in self.patterns
        )


@dataclass(frozen=True)
class DriftReport:
    """Outcome of one scan run."""

    missing: Dict[str, List[str]] = field(default_factory=dict)
    referenced: int = 0
    dynamic_references_skipped: int = 0
    frontend_definitions_skipped: int = 0
    e2e_files: int = 0
    frontend_files: int = 0

    @property
    def clean(self) -> bool:
        return not self.missing


def _looks_like_repo_root(path: Path) -> bool:
    return (path / "frontend" / "src").is_dir() and (path / "e2e").is_dir()


def _find_repo_root() -> Optional[Path]:
    """Locate the checkout root, or None when only ``backend/`` is mounted.

    The docker-compose backend-test service mounts ``backend/`` alone at
    ``/app`` (testing/docker-compose.test.yml), so e2e/ and frontend/ do not
    exist there. CI runs against a full checkout, which is where this guard
    is meant to bite.
    """
    override = os.environ.get(_REPO_ROOT_ENV)
    candidates = [Path(override).expanduser().resolve()] if override else []
    candidates += list(Path(__file__).resolve().parents)
    for candidate in candidates:
        if _looks_like_repo_root(candidate):
            return candidate
    return None


def collect_source_files(root: Path) -> List[Path]:
    """Yield JS/TS files under ``root``, skipping generated/vendored trees."""
    found: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIPPED_DIRS]
        found.extend(
            Path(dirpath) / name
            for name in filenames
            if Path(name).suffix in _SOURCE_SUFFIXES
        )
    return sorted(found)


def extract_e2e_references(text: str, relpath: str) -> Tuple[List[Reference], int]:
    """Collect literal testid references from one e2e file's text.

    Returns the references plus the number of dynamic mentions that were
    skipped: interpolated templates, helper-call arguments and partial-match
    attribute selectors. None of them can be resolved without executing the
    code, so they are counted (for visibility) instead of crashing or being
    guessed at.
    """
    references: List[Reference] = []
    dynamic = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        interpolated = 0
        literals = 0
        for regex in (_GET_BY_TESTID, _DATA_TESTID):
            for match in regex.finditer(line):
                value = match.group(2)
                if not value:
                    continue
                if _INTERPOLATION.search(value):
                    interpolated += 1
                    continue
                references.append(Reference(value, f"{relpath}:{lineno}"))
                literals += 1
        mentions = len(_GET_BY_TESTID_CALL.findall(line)) + len(
            _DATA_TESTID_MENTION.findall(line)
        )
        # Every mention resolved to a literal is checked; the rest are dynamic.
        # Interpolated matches are counted once here and excluded from the
        # mentions balance so they are not tallied twice.
        dynamic += interpolated + max(0, mentions - interpolated - literals)
    return references, dynamic


def collect_carriers(frontend_texts: Sequence[str]) -> Dict[str, Set[str]]:
    """Map testid-channel names to the literal values bound to them.

    A single frontend file rarely binds and consumes the same channel: the
    value is bound at the JSX call site (``testId="system-health-dialog"``)
    and consumed in the child component's template
    (``data-testid={`${testId}-overlay`}``), so the map is built across all
    of ``frontend/src``. Prefix-carrying channels (``optionTestIdPrefix``)
    are included here too — their values are prefixes that template anchors
    join with, not full ids.
    """
    carriers: Dict[str, Set[str]] = {}
    for text in frontend_texts:
        for match in _TESTID_CHANNEL.finditer(text):
            name, value = match.group(1), match.group(3)
            if value and _is_testid_channel(name):
                carriers.setdefault(name, set()).add(value)
    return carriers


def extract_frontend_definitions(
    text: str, carriers: Dict[str, Set[str]]
) -> Tuple[Definition, int]:
    """Collect the allowed set from one frontend file's text.

    Returns the definition plus the number of templates that were too dynamic
    to derive a pattern from (unanchored multi-interpolation, or anchored on
    an expression this scan cannot resolve).
    """
    exact: Set[str] = set()
    patterns: Set[Tuple[str, str]] = set()
    skipped = 0

    for match in _DATA_TESTID.finditer(text):
        value = match.group(2)
        if value and not _INTERPOLATION.search(value):
            exact.add(value)

    for match in _TESTID_MAP.finditer(text):
        for value in _MAP_VALUE.findall(match.group(1)):
            exact.add(value)

    for match in _TESTID_CHANNEL.finditer(text):
        name, value = match.group(1), match.group(3)
        if value and _is_testid_channel(name) and not _is_prefix_carrier(name):
            exact.add(value)

    for match in _TEMPLATE_LITERAL.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line = text[line_start : line_end if line_end != -1 else len(text)]
        if not _TESTID_CONTEXT_LINE.search(line):
            continue
        inner = match.group(1)
        if not _INTERPOLATION.search(inner):
            if inner:
                exact.add(inner)
            continue
        segments = _INTERPOLATION.split(inner)
        expressions = _INTERPOLATION.findall(inner)
        first = expressions[0][2:-1].strip()
        anchored = _IDENTIFIER.match(first) and first in carriers
        if anchored and len(segments) == 2:
            head, tail = segments
            for carrier in carriers[first]:
                if carrier + head:
                    patterns.add((carrier + head, tail))
            continue
        if anchored and len(segments) > 2:
            tail = "".join(segments[2:])
            for carrier in carriers[first]:
                prefix = carrier + segments[0] + segments[1]
                if prefix:
                    patterns.add((prefix, tail))
            continue
        if len(segments) != 2 or not segments[0]:
            skipped += 1
            continue
        patterns.add((segments[0], segments[1]))

    return Definition(exact=exact, patterns=patterns), skipped


def scan_drift(
    e2e_files: Sequence[Path], frontend_files: Sequence[Path]
) -> DriftReport:
    """Cross-check e2e references against frontend definitions."""
    texts = [
        path.read_text(encoding="utf-8", errors="ignore") for path in frontend_files
    ]
    carriers = collect_carriers(texts)

    exact: Set[str] = set()
    patterns: Set[Tuple[str, str]] = set()
    frontend_skipped = 0
    for text in texts:
        file_definition, skipped = extract_frontend_definitions(text, carriers)
        exact |= file_definition.exact
        patterns |= file_definition.patterns
        frontend_skipped += skipped
    definition = Definition(exact=exact, patterns=patterns)

    missing: Dict[str, List[str]] = {}
    referenced = 0
    dynamic = 0
    for path in e2e_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        references, skipped = extract_e2e_references(text, path.as_posix())
        dynamic += skipped
        for reference in references:
            referenced += 1
            if not definition.allows(reference.value):
                missing.setdefault(reference.value, []).append(reference.source)

    return DriftReport(
        missing=missing,
        referenced=referenced,
        dynamic_references_skipped=dynamic,
        frontend_definitions_skipped=frontend_skipped,
        e2e_files=len(e2e_files),
        frontend_files=len(frontend_files),
    )


def render_report(report: DriftReport, repo_root: Optional[Path] = None) -> str:
    """Human-readable summary — the actionable part is the missing list."""

    def _rel(source: str) -> str:
        if repo_root is None:
            return source
        path, _, lineno = source.rpartition(":")
        return f"{Path(path).relative_to(repo_root).as_posix()}:{lineno}"

    lines = [
        "E2E data-testid drift check (issue #1113):",
        f"  scanned {report.e2e_files} e2e + {report.frontend_files} frontend files",
        f"  {report.referenced} literal testid reference(s) resolved and checked",
        f"  {report.dynamic_references_skipped} dynamic e2e reference(s) "
        "skipped (template/helper-call/partial selector — not statically "
        "resolvable)",
        f"  {report.frontend_definitions_skipped} dynamic frontend template(s) "
        "skipped (unanchored multi-interpolation — not statically derivable)",
    ]
    if report.clean:
        lines.append("  no drift: every referenced data-testid literal exists")
        return "\n".join(lines)

    lines.append(
        f"  DRIFT — {len(report.missing)} referenced id(s) do not exist in "
        "frontend/src:"
    )
    for value in sorted(report.missing):
        sources = ", ".join(_rel(source) for source in report.missing[value])
        lines.append(f"    - {value!r} referenced in {sources}")
    lines.append(
        "  Playwright cannot catch this at runtime — a missing selector only\n"
        "  times out. Re-point each selector at a live data-testid, or remove\n"
        "  the pin if its component is gone (cf. ADR-009)."
    )
    return "\n".join(lines)


def _repo_scan() -> Tuple[DriftReport, Path]:
    """Scan the real checkout; skips the calling test when it is unavailable."""
    repo_root = _find_repo_root()
    if repo_root is None:
        pytest.skip(
            "full repository checkout not available (e2e/ or frontend/src/ "
            "unreachable from this test — backend-only mount); set "
            f"${_REPO_ROOT_ENV} to run this guard against a checkout"
        )
    report = scan_drift(
        collect_source_files(repo_root / "e2e"),
        collect_source_files(repo_root / "frontend" / "src"),
    )
    return report, repo_root


def test_no_drift_between_e2e_and_frontend() -> None:
    """Every e2e data-testid literal must exist in frontend/src (issue #1113)."""
    report, repo_root = _repo_scan()
    assert report.clean, render_report(report, repo_root)


def test_historical_notification_bell_id_stays_out_of_e2e() -> None:
    """The ADR-009 id must not creep back into e2e (the original bug class)."""
    repo_root = _find_repo_root()
    if repo_root is None:
        pytest.skip(
            "full repository checkout not available (e2e/ or frontend/src/ "
            "unreachable from this test — backend-only mount); set "
            f"${_REPO_ROOT_ENV} to run this guard against a checkout"
        )
    offenders = [
        path.relative_to(repo_root).as_posix()
        for path in collect_source_files(repo_root / "e2e")
        if _HISTORICAL_TESTID in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, (
        f"e2e references {_HISTORICAL_TESTID!r} in {offenders} — that "
        "component was removed by ADR-009; pin the current component instead"
    )


def test_literal_references_are_caught_in_a_fixture(tmp_path) -> None:
    """Negative case: a deliberately stale testid must be reported."""
    e2e_file = tmp_path / "stale.spec.ts"
    e2e_file.write_text(
        "await page.getByTestId('notification-bell-toggle').click();\n",
        encoding="utf-8",
    )
    frontend_file = tmp_path / "Component.tsx"
    frontend_file.write_text(
        'const x = <button data-testid="assistant-toggle" />;\n',
        encoding="utf-8",
    )
    report = scan_drift([e2e_file], [frontend_file])
    assert not report.clean
    assert "notification-bell-toggle" in report.missing
    assert report.missing["notification-bell-toggle"][0].endswith("stale.spec.ts:1")
    assert "notification-bell-toggle" in render_report(report, tmp_path)


def test_matching_literal_passes_in_a_fixture(tmp_path) -> None:
    """Positive case: literal references against literal definitions."""
    e2e_file = tmp_path / "ok.spec.ts"
    e2e_file.write_text(
        "await page.getByTestId('assistant-toggle').click();\n"
        "await page.locator('[data-testid=\"assistant-panel\"]').waitFor();\n",
        encoding="utf-8",
    )
    frontend_file = tmp_path / "Component.tsx"
    frontend_file.write_text(
        "const x = (\n"
        '  <div data-testid="assistant-toggle">\n'
        "    <span data-testid={'assistant-panel'} />\n"
        "  </div>\n"
        ");\n",
        encoding="utf-8",
    )
    report = scan_drift([e2e_file], [frontend_file])
    assert report.clean, render_report(report, tmp_path)
    assert report.referenced == 2


def test_dynamic_references_are_skipped_not_falsely_reported(tmp_path) -> None:
    """Templates, helper calls and partial selectors must not crash or flag."""
    e2e_file = tmp_path / "dynamic.spec.ts"
    e2e_file.write_text(
        "await page.getByTestId(`icd-item-${icdId}`).click();\n"
        "await page.getByTestId(needRow(created.id)).waitFor();\n"
        "await page.locator('[data-testid^=\"workflow-state-node-\"]').first()"
        ".click();\n"
        "await page.locator(`[data-testid=\"${prefix}-count\"]`).waitFor();\n",
        encoding="utf-8",
    )
    frontend_file = tmp_path / "Dynamic.tsx"
    frontend_file.write_text(
        "const a = <li data-testid={`icd-item-${item.id}`} />;\n",
        encoding="utf-8",
    )
    report = scan_drift([e2e_file], [frontend_file])
    assert report.clean, render_report(report, tmp_path)
    assert report.referenced == 0
    assert report.dynamic_references_skipped == 4


def test_template_definition_allows_static_prefix_but_still_constrains(
    tmp_path,
) -> None:
    """A two-sided template constrains head and tail, not just the prefix."""
    frontend_file = tmp_path / "Prompts.tsx"
    frontend_file.write_text(
        "const t = <input data-testid={`prompt-${slot}-input`} />;\n",
        encoding="utf-8",
    )
    ok = tmp_path / "ok.spec.ts"
    ok.write_text(
        "await page.getByTestId('prompt-system-input').fill('x');\n",
        encoding="utf-8",
    )
    assert scan_drift([ok], [frontend_file]).clean

    stale = tmp_path / "stale.spec.ts"
    stale.write_text(
        "await page.getByTestId('prompt-system-legacy').fill('x');\n",
        encoding="utf-8",
    )
    report = scan_drift([stale], [frontend_file])
    assert not report.clean
    assert "prompt-system-legacy" in report.missing


def test_prefix_only_template_anchors_on_the_prefix(tmp_path) -> None:
    """``artifact-field-${name}`` has no tail — any member matches (documented)."""
    frontend_file = tmp_path / "Form.tsx"
    frontend_file.write_text(
        "const t = <input data-testid={`artifact-field-${name}`} />;\n",
        encoding="utf-8",
    )
    e2e_file = tmp_path / "ok.spec.ts"
    e2e_file.write_text(
        "await page.getByTestId('artifact-field-title').fill('x');\n",
        encoding="utf-8",
    )
    assert scan_drift([e2e_file], [frontend_file]).clean


def test_computed_testid_template_is_anchored(tmp_path) -> None:
    """A template computed into the testId channel anchors a pattern."""
    frontend_file = tmp_path / "Form.tsx"
    frontend_file.write_text(
        "const testId = fieldTestIds?.[name] ?? `artifact-field-${name}`;\n"
        "const control = root.querySelector(`[data-testid=\"${testId}\"]`);\n",
        encoding="utf-8",
    )
    e2e_file = tmp_path / "editor.spec.ts"
    e2e_file.write_text(
        "await page.getByTestId('artifact-field-element_type').fill('x');\n",
        encoding="utf-8",
    )
    assert scan_drift([e2e_file], [frontend_file]).clean


def test_testid_map_values_are_part_of_the_allowed_set(tmp_path) -> None:
    """fieldTestIds map values render as data-testid and must be allowed."""
    frontend_file = tmp_path / "Editors.tsx"
    frontend_file.write_text(
        "const x = (\n"
        "  <ArtifactForm\n"
        "    fieldTestIds={{ title: 'req-new-title-input', save: "
        "'req-new-save-btn' }}\n"
        "  />\n"
        ");\n",
        encoding="utf-8",
    )
    e2e_file = tmp_path / "editor.spec.ts"
    e2e_file.write_text(
        "await page.locator('[data-testid=\"req-new-title-input\"]').fill('x');\n"
        "await page.locator('[data-testid=\"req-new-save-btn\"]').click();\n",
        encoding="utf-8",
    )
    assert scan_drift([e2e_file], [frontend_file]).clean


def test_config_object_testid_property_is_part_of_the_allowed_set(
    tmp_path,
) -> None:
    """Action toolbars configure ids as ``{ testId: 'create-req-btn' }``."""
    frontend_file = tmp_path / "Editors.tsx"
    frontend_file.write_text(
        "const actions = [{ testId: 'create-req-btn', label: 'New' }];\n",
        encoding="utf-8",
    )
    e2e_file = tmp_path / "editor.spec.ts"
    e2e_file.write_text(
        "await page.getByTestId('create-req-btn').click();\n",
        encoding="utf-8",
    )
    assert scan_drift([e2e_file], [frontend_file]).clean


def test_prefix_carrier_template_is_joined_across_files(tmp_path) -> None:
    """``${optionTestIdPrefix}-option-${key}`` joins the prop literal value."""
    consumer = tmp_path / "listbox.tsx"
    consumer.write_text(
        "const options = rows.map((row) => (\n"
        "  <li\n"
        "    data-testid={`${optionTestIdPrefix}-option-${row.key}`}\n"
        "  />\n"
        "));\n",
        encoding="utf-8",
    )
    producer = tmp_path / "dialog.tsx"
    producer.write_text(
        'const dialog = <Listbox optionTestIdPrefix="create-trace-link-type" />;\n',
        encoding="utf-8",
    )
    e2e_file = tmp_path / "tracelink.spec.ts"
    e2e_file.write_text(
        "await page.getByTestId('create-trace-link-type-option-allocated-to')"
        ".click();\n",
        encoding="utf-8",
    )
    report = scan_drift([e2e_file], [consumer, producer])
    assert report.clean, render_report(report, tmp_path)


def test_dialog_suffix_composition_is_joined_across_files(tmp_path) -> None:
    """``${testId}-confirm`` joins with the caller's testId literal value."""
    consumer = tmp_path / "ConfirmDialog.tsx"
    consumer.write_text(
        "const confirm = <button data-testid={`${testId}-confirm`} />;\n"
        "const overlay = <div data-testid={`${testId}-overlay`} />;\n",
        encoding="utf-8",
    )
    producer = tmp_path / "Form.tsx"
    producer.write_text(
        "const dialog = (\n"
        "  <ConfirmDialog\n"
        '    testId="artifact-form-delete-confirm"\n'
        "  />\n"
        ");\n",
        encoding="utf-8",
    )
    e2e_file = tmp_path / "delete.spec.ts"
    e2e_file.write_text(
        "await page.getByTestId('artifact-form-delete-confirm-confirm').click();\n",
        encoding="utf-8",
    )
    report = scan_drift([e2e_file], [consumer, producer])
    assert report.clean, render_report(report, tmp_path)


def test_generated_and_vendored_trees_are_not_scanned(tmp_path) -> None:
    """node_modules / playwright-report content must not feed either side."""
    e2e_root = tmp_path / "e2e"
    (e2e_root / "node_modules").mkdir(parents=True)
    (e2e_root / "node_modules" / "vendor.spec.ts").write_text(
        "await page.getByTestId('vendored-missing').click();\n",
        encoding="utf-8",
    )
    (e2e_root / "real.spec.ts").write_text(
        "await page.getByTestId('real-toggle').click();\n",
        encoding="utf-8",
    )
    frontend_root = tmp_path / "frontend"
    (frontend_root / "src").mkdir(parents=True)
    (frontend_root / "src" / "C.tsx").write_text(
        'const x = <b data-testid="real-toggle" />;\n',
        encoding="utf-8",
    )
    report = scan_drift(
        collect_source_files(e2e_root), collect_source_files(frontend_root)
    )
    assert report.clean
    assert report.e2e_files == 1
