"""Regenerates ``docs/se/traceability-matrix.md`` from the SE cascade documents.

The traceability matrix used to be hand-maintained and drifted roughly 3x behind
the actual requirement corpus (it claimed "REQ-L1 33/33, REQ-L2 142/142,
lueckenlos" while 20 L2 systems with ~290 REQ-L2 existed). This script makes the
matrix a derived artifact: the requirement documents are the single source of
truth, the matrix is generated from them.

Sources (read-only, never modified):
  * ``docs/se/L0/SN_Stakeholder_Needs.md``            -> REQ-L0 (Stakeholder Needs)
  * ``docs/se/L1/**/L1_*_Requirements.md``            -> REQ-L1
  * ``docs/se/L1/**/L2_*_Requirements.md``            -> REQ-L2 (per L2 system)
  * ``docs/se/L1/**/L3_*_Requirements.md``            -> REQ-L3 (per component)
  * ``docs/se/L1/**/L2_*_Architecture.md``            -> COMP-* and REQ-L2 -> COMP

Parsed per requirement block (``### <REQ-ID><sep><title>``):
  * ``**Implementation State:**`` marker
  * ``**Test Status:**`` marker
  * ``**Traceability:**`` parent links, including ``(mitwirkend)`` annotations
    and range notation (``REQ-L1-001..015``)

Many documents additionally carry summary link tables ("Master Traceability
Matrix", "Traceability-Abschnitt: REQ-L1 -> REQ-L0", ...) that cover requirements
whose inline block has no ``**Traceability:**`` field. Those tables are merged
into the link graph, but only for IDs that the same document also declares as a
``###`` block -- so a table that merely *quotes* foreign IDs cannot inject links.

Usage:
    python3 scripts/generate_traceability_matrix.py           # write the matrix
    python3 scripts/generate_traceability_matrix.py --check   # CI: fail if stale
    python3 scripts/generate_traceability_matrix.py --stdout  # print, write nothing

``--check`` compares everything except the generation timestamp, so a clean tree
stays clean when nothing but the clock has moved.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SE_ROOT = ROOT / "docs/se"
L0_DOC = SE_ROOT / "L0/SN_Stakeholder_Needs.md"
L1_ROOT = SE_ROOT / "L1"
OUTPUT = SE_ROOT / "traceability-matrix.md"
SCRIPT_REL = "scripts/generate_traceability_matrix.py"

# `### REQ-L2-AT-011: Credential Verification` / `### REQ-L0-001 - SN-01: ...`
# The ID is greedy over hyphen-separated segments so `REQ-L3-RO-002-004` stays whole.
_HEADING_RE = re.compile(r"^### +(REQ-L(\d)(?:-[A-Za-z0-9]+)+)(.*)$", re.MULTILINE)
# Separators seen in the corpus: ":", em dash, en dash and one U+FFFD artifact.
_TITLE_SEP_RE = re.compile(r"^[\s:\u2013\u2014\u2012\ufffd-]+")
_FIELD_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z .()-]*?):\*\*[ \t]*(.*)$", re.MULTILINE)
_REQ_ID_RE = re.compile(r"REQ-L\d(?:-[A-Za-z0-9]+)+")
_REQ_RANGE_RE = re.compile(r"(REQ-L\d(?:-[A-Za-z0-9]+)*?-)(\d+)\.\.(\d+)")
_COMP_ID_RE = re.compile(r"COMP-[A-Z]+-\d+")
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$", re.MULTILINE)
_ASSIGNED_SECTION_RE = re.compile(r"^## +\d+\. +Zugeordnete REQ-L2\b", re.MULTILINE)
_L3_ASSIGNED_SECTION_RE = re.compile(r"^## +Zugeordnete L2-Anforderungen\b", re.MULTILINE)
_COMPONENT_SECTION_RE = re.compile(r"^### +Komponenten\b", re.MULTILINE)
_ANY_HEADING_RE = re.compile(r"^#{1,6} ", re.MULTILINE)

# Implementation-State buckets. Anything else is folded into "Sonstige (Freitext)".
KNOWN_IMPL_STATES = (
    "Implemented",
    "Not Implemented",
    "Planned",
    "Backlog",
    "In Progress",
    "Teilweise Implementiert",
    "Deferred",
)
KNOWN_TEST_STATES = ("Covered", "Missing", "Untested")
OTHER_BUCKET = "Sonstige (Freitext)"
UNSET_BUCKET = "(kein Marker)"


@dataclass
class Requirement:
    """One ``### REQ-...`` block of a requirement document."""

    req_id: str
    level: int
    title: str
    system: str
    component: str | None
    source: str
    impl_state: str | None = None
    test_status: str | None = None
    primary_parents: list[str] = field(default_factory=list)
    contributing_parents: list[str] = field(default_factory=list)
    duplicate_of: int = 0
    #: True when the ID only appears in summary tables, never as a ``###`` block.
    table_only: bool = False

    @property
    def all_parents(self) -> list[str]:
        return self.primary_parents + self.contributing_parents

    @property
    def impl_bucket(self) -> str:
        if not self.impl_state:
            return UNSET_BUCKET
        return self.impl_state if self.impl_state in KNOWN_IMPL_STATES else OTHER_BUCKET

    @property
    def test_bucket(self) -> str:
        if not self.test_status:
            return UNSET_BUCKET
        for known in KNOWN_TEST_STATES:
            if self.test_status == known:
                return known
        # "Covered (pytest, Task 3)" / "Teilweise (...)" -> match on the leading word.
        head = self.test_status.split(" ")[0].rstrip(",;")
        return head if head in KNOWN_TEST_STATES else OTHER_BUCKET


@dataclass
class Component:
    """One ``COMP-*`` row of an L2 architecture document."""

    comp_id: str
    name: str
    system: str
    source: str
    #: False when only a ``Components/COMP-*`` directory exists, with no row in
    #: the L2 architecture document's component table.
    declared_in_architecture: bool = True


def natural_key(value: str) -> tuple[object, ...]:
    """Sort key that orders ``REQ-L2-AS-9`` before ``REQ-L2-AS-10``."""
    return tuple(
        (1, int(part), "") if part.isdigit() else (0, 0, part)
        for part in re.split(r"(\d+)", value)
        if part
    )


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def expand_ranges(text: str) -> str:
    """Rewrite ``REQ-L1-001..015`` into the explicit comma-separated ID list."""

    def _expand(match: re.Match[str]) -> str:
        prefix, start, end = match.group(1), match.group(2), match.group(3)
        width = len(start)
        first, last = int(start), int(end)
        if last < first or last - first > 200:  # guard against nonsense ranges
            return match.group(0)
        return ", ".join(f"{prefix}{n:0{width}d}" for n in range(first, last + 1))

    return _REQ_RANGE_RE.sub(_expand, text)


def parse_traceability(value: str) -> tuple[list[str], list[str]]:
    """Split a ``**Traceability:**`` value into primary and contributing parents.

    A parent counts as *contributing* when its own comma-segment carries the
    ``(mitwirkend)`` annotation used throughout the L2 documents.
    """
    primary: list[str] = []
    contributing: list[str] = []
    for segment in expand_ranges(value).split(","):
        ids = _REQ_ID_RE.findall(segment)
        if not ids:
            continue
        bucket = contributing if "mitwirkend" in segment.lower() else primary
        for req_id in ids:
            if req_id not in bucket:
                bucket.append(req_id)
    # An ID listed both ways is primary.
    contributing = [i for i in contributing if i not in primary]
    return primary, contributing


def split_blocks(text: str) -> list[tuple[str, int, str, str]]:
    """Yield ``(req_id, level, title, body)`` for every ``### REQ-...`` heading."""
    matches = list(_HEADING_RE.finditer(text))
    blocks: list[tuple[str, int, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        # Stop at the next heading of any level so sibling sections don't leak in.
        next_heading = _ANY_HEADING_RE.search(body)
        if next_heading:
            body = body[: next_heading.start()]
        title = _TITLE_SEP_RE.sub("", match.group(3)).strip()
        blocks.append((match.group(1), int(match.group(2)), title, body))
    return blocks


def iter_tables(text: str) -> list[list[list[str]]]:
    """Group consecutive ``|...|`` lines into tables of cell lists."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped[1:-1].split("|")]
            if all(set(c) <= set("-: ") for c in cells):  # separator row
                continue
            current.append(cells)
            continue
        if current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def parse_link_tables(
    text: str, own_ids: set[str] | None
) -> dict[str, tuple[list[str], list[str]]]:
    """Harvest parent links from summary tables such as the Master Traceability Matrix.

    Only rows whose first cell is an ID declared as a ``###`` block in the *same*
    document are considered, and only parents exactly one level above are kept.
    A column whose header mentions "mitwirkend" is read as contributing.

    ``own_ids=None`` lifts the block-declaration filter -- used to recover
    requirements that exist *only* as table rows.
    """
    links: dict[str, tuple[list[str], list[str]]] = {}
    for table in iter_tables(text):
        if len(table) < 2:
            continue
        header = [c.lower() for c in table[0]]
        if not header or "req-l" not in header[0].lower():
            continue
        contributing_cols = {
            i for i, cell in enumerate(header) if "mitwirkend" in cell or "mitw." in cell
        }
        for row in table[1:]:
            if not row:
                continue
            own = _REQ_ID_RE.findall(row[0])
            if len(own) != 1 or (own_ids is not None and own[0] not in own_ids):
                continue
            req_id = own[0]
            level = int(req_id[5])
            parent_prefix = f"REQ-L{level - 1}-"
            primary, contributing = links.setdefault(req_id, ([], []))
            for column, cell in enumerate(row[1:], start=1):
                for segment in expand_ranges(cell).split(","):
                    for parent in _REQ_ID_RE.findall(segment):
                        if not parent.startswith(parent_prefix):
                            continue
                        bucket = (
                            contributing
                            if column in contributing_cols
                            or "mitwirkend" in segment.lower()
                            else primary
                        )
                        if parent not in bucket:
                            bucket.append(parent)
    return links


def parse_requirement_doc(
    path: Path, system: str, component: str | None
) -> list[Requirement]:
    text = path.read_text(encoding="utf-8")
    blocks = split_blocks(text)
    table_links = parse_link_tables(text, {block[0] for block in blocks})
    requirements: list[Requirement] = []
    for req_id, level, title, body in blocks:
        req = Requirement(
            req_id=req_id,
            level=level,
            title=title,
            system=system,
            component=component,
            source=rel(path),
        )
        for name, value in _FIELD_RE.findall(body):
            key = name.strip().lower()
            value = value.strip()
            if key == "implementation state":
                req.impl_state = value or None
            elif key == "test status":
                req.test_status = value or None
            elif key == "traceability":
                primary, contributing = parse_traceability(value)
                req.primary_parents = primary
                req.contributing_parents = contributing
        table_primary, table_contributing = table_links.get(req_id, ([], []))
        for parent in table_primary:
            if parent not in req.primary_parents:
                req.primary_parents.append(parent)
        for parent in table_contributing:
            if parent not in req.primary_parents and parent not in req.contributing_parents:
                req.contributing_parents.append(parent)
        req.primary_parents.sort(key=natural_key)
        req.contributing_parents.sort(key=natural_key)
        requirements.append(req)
    return requirements


def table_rows(text: str) -> list[list[str]]:
    """Return the cells of every markdown table row in *text*."""
    rows: list[list[str]] = []
    for match in _TABLE_ROW_RE.finditer(text):
        cells = [c.strip() for c in match.group(1).split("|")]
        if all(set(c) <= set("-: ") for c in cells):  # separator row
            continue
        rows.append(cells)
    return rows


def section_slice(text: str, match: re.Match[str] | None) -> str:
    """Return the body of the section opened by *match*, up to the next heading."""
    if match is None:
        return ""
    following = re.compile(r"^#{1,3} ", re.MULTILINE).search(text, match.end())
    return text[match.end() : following.start() if following else len(text)]


def parse_architecture_doc(path: Path, system: str) -> tuple[
    list[Component], dict[str, list[str]]
]:
    """Extract the component catalogue and the REQ-L2 -> COMP assignment table."""
    text = path.read_text(encoding="utf-8")

    components: list[Component] = []
    comp_section = section_slice(text, _COMPONENT_SECTION_RE.search(text))
    seen: set[str] = set()
    for cells in table_rows(comp_section):
        if not cells or not cells[0].startswith("COMP-"):
            continue
        comp_id = cells[0]
        if comp_id in seen:
            continue
        seen.add(comp_id)
        components.append(
            Component(
                comp_id=comp_id,
                name=cells[1] if len(cells) > 1 else "",
                system=system,
                source=rel(path),
            )
        )

    assignments: dict[str, list[str]] = {}
    assign_section = section_slice(text, _ASSIGNED_SECTION_RE.search(text))
    for cells in table_rows(assign_section):
        if not cells or not cells[0].startswith("REQ-L2-"):
            continue
        req_ids = _REQ_ID_RE.findall(cells[0])
        comp_ids = _COMP_ID_RE.findall(" ".join(cells[1:]))
        for req_id in req_ids:
            bucket = assignments.setdefault(req_id, [])
            for comp_id in comp_ids:
                if comp_id not in bucket:
                    bucket.append(comp_id)

    # Some architecture docs carry the REQ-L2 assignment as a 5th column of the
    # component table instead of (or in addition to) the assignment section.
    for cells in table_rows(comp_section):
        if not cells or not cells[0].startswith("COMP-"):
            continue
        for req_id in _REQ_ID_RE.findall(" ".join(cells[2:])):
            if req_id.startswith("REQ-L2-"):
                bucket = assignments.setdefault(req_id, [])
                if cells[0] not in bucket:
                    bucket.append(cells[0])

    return components, assignments


@dataclass
class Corpus:
    """Everything parsed out of the SE cascade, keyed by ID."""

    requirements: dict[str, Requirement] = field(default_factory=dict)
    components: dict[str, Component] = field(default_factory=dict)
    #: REQ-L2 -> COMP, declared in the L2 architecture documents (primary source).
    assignments: dict[str, list[str]] = field(default_factory=dict)
    #: REQ-L2 -> COMP, derived from the L3 component documents (fallback source).
    assignments_via_l3: dict[str, list[str]] = field(default_factory=dict)
    systems: list[str] = field(default_factory=list)
    systems_without_architecture: list[str] = field(default_factory=list)
    duplicate_ids: list[tuple[str, str, int]] = field(default_factory=list)
    req_doc_count: int = 0
    arch_doc_count: int = 0

    def by_level(self, level: int) -> list[Requirement]:
        return sorted(
            (r for r in self.requirements.values() if r.level == level),
            key=lambda r: natural_key(r.req_id),
        )


def _register(corpus: Corpus, requirements: list[Requirement]) -> None:
    for req in requirements:
        existing = corpus.requirements.get(req.req_id)
        if existing is None:
            corpus.requirements[req.req_id] = req
            continue
        # Duplicate heading -- the docs restate requirements in "Erweiterung"
        # sections. Merge instead of overwrite (the later block is usually the
        # fuller prose but the earlier one may hold the only status marker) and
        # report the collision in the anomaly section.
        corpus.duplicate_ids.append((req.req_id, req.source, existing.duplicate_of + 2))
        existing.duplicate_of += 1
        existing.impl_state = req.impl_state or existing.impl_state
        existing.test_status = req.test_status or existing.test_status
        for parent in req.primary_parents:
            if parent not in existing.primary_parents:
                existing.primary_parents.append(parent)
        for parent in req.contributing_parents:
            if (
                parent not in existing.primary_parents
                and parent not in existing.contributing_parents
            ):
                existing.contributing_parents.append(parent)
        existing.primary_parents.sort(key=natural_key)
        existing.contributing_parents.sort(key=natural_key)


def collect() -> Corpus:
    corpus = Corpus()

    if L0_DOC.exists():
        _register(corpus, parse_requirement_doc(L0_DOC, "Gesamtsystem", None))
        corpus.req_doc_count += 1

    for path in sorted(L1_ROOT.rglob("L1_*_Requirements.md")):
        _register(corpus, parse_requirement_doc(path, "Gesamtsystem", None))
        corpus.req_doc_count += 1

    l2_root = L1_ROOT / "Gesamtsystem/L2"
    corpus.systems = sorted(p.name for p in l2_root.iterdir() if p.is_dir())

    for system in corpus.systems:
        system_dir = l2_root / system

        req_paths = sorted(system_dir.glob("L2_*_Requirements.md"))
        for path in req_paths:
            _register(corpus, parse_requirement_doc(path, system, None))
            corpus.req_doc_count += 1

        arch_paths = sorted(system_dir.glob("L2_*_Architecture.md"))
        if not arch_paths:
            corpus.systems_without_architecture.append(system)
        for path in arch_paths:
            components, assignments = parse_architecture_doc(path, system)
            for component in components:
                corpus.components.setdefault(component.comp_id, component)
            for req_id, comp_ids in assignments.items():
                bucket = corpus.assignments.setdefault(req_id, [])
                for comp_id in comp_ids:
                    if comp_id not in bucket:
                        bucket.append(comp_id)
            corpus.arch_doc_count += 1

        _recover_table_only_requirements(corpus, system, req_paths)

        # A `Components/COMP-*` directory is a component too, even when the
        # architecture document's table has not caught up with it.
        components_dir = system_dir / "Components"
        if components_dir.is_dir():
            for path in sorted(p for p in components_dir.iterdir() if p.is_dir()):
                match = _COMP_ID_RE.match(path.name)
                if not match or match.group(0) in corpus.components:
                    continue
                corpus.components[match.group(0)] = Component(
                    comp_id=match.group(0),
                    name=path.name[len(match.group(0)) :].lstrip("_ ") or "—",
                    system=system,
                    source=rel(path),
                    declared_in_architecture=False,
                )

        for path in sorted(system_dir.rglob("L3_*_Requirements.md")):
            comp_dir = next(
                (p.name for p in path.parents if p.name.startswith("COMP-")), None
            )
            comp_id = None
            if comp_dir:
                match = _COMP_ID_RE.match(comp_dir)
                comp_id = match.group(0) if match else comp_dir
            l3_requirements = parse_requirement_doc(path, system, comp_id)
            _register(corpus, l3_requirements)
            corpus.req_doc_count += 1
            if comp_id:
                _derive_assignments_from_l3(corpus, path, comp_id, l3_requirements)

    return corpus


def _recover_table_only_requirements(
    corpus: Corpus, system: str, req_paths: list[Path]
) -> None:
    """Register REQ-L2 that a system only lists in tables, never as a ``###`` block.

    McpServerSystem is the live example: its requirements document lost the
    REQ-L2-MC-001..013 blocks but still carries them in the local traceability
    matrix, and the architecture document assigns them to components. Dropping
    them would silently shrink the matrix -- exactly the failure this generator
    exists to prevent -- so they are carried as stubs and flagged in section 5.
    """
    declared = {r.req_id for r in corpus.by_level(2) if r.system == system}
    prefixes = {r.split("-")[2] for r in declared}
    if not prefixes:
        return

    candidates: dict[str, tuple[list[str], list[str]]] = {}
    for path in req_paths:
        text = path.read_text(encoding="utf-8")
        for req_id, links in parse_link_tables(text, None).items():
            if req_id.startswith("REQ-L2-") and req_id.split("-")[2] in prefixes:
                candidates.setdefault(req_id, links)
    for req_id in corpus.assignments:
        if req_id.startswith("REQ-L2-") and req_id.split("-")[2] in prefixes:
            candidates.setdefault(req_id, ([], []))

    source = rel(req_paths[0]) if req_paths else ""
    for req_id, (primary, contributing) in sorted(
        candidates.items(), key=lambda item: natural_key(item[0])
    ):
        if req_id in corpus.requirements:
            continue
        # Skip pure placeholder rows ("(reserviert)"): no parent, no component.
        if not primary and not contributing and not corpus.assignments.get(req_id):
            continue
        corpus.requirements[req_id] = Requirement(
            req_id=req_id,
            level=2,
            title="(kein `###`-Block im Quelldokument)",
            system=system,
            component=None,
            source=source,
            primary_parents=sorted(primary, key=natural_key),
            contributing_parents=sorted(
                (p for p in contributing if p not in primary), key=natural_key
            ),
            table_only=True,
        )


def _derive_assignments_from_l3(
    corpus: Corpus, path: Path, comp_id: str, requirements: list[Requirement]
) -> None:
    """Fallback REQ-L2 -> COMP source: the L3 component document itself.

    Used only where the L2 architecture document has no assignment row. Two
    signals: the doc-level "Zugeordnete L2-Anforderungen" table, and the REQ-L2
    parents declared by the component's own L3 requirements.
    """
    text = path.read_text(encoding="utf-8")
    req_ids: list[str] = []

    section = section_slice(text, _L3_ASSIGNED_SECTION_RE.search(text))
    for cells in table_rows(section):
        if cells and cells[0].startswith("REQ-L2-"):
            req_ids.extend(_REQ_ID_RE.findall(cells[0]))

    for req in requirements:
        req_ids.extend(p for p in req.all_parents if p.startswith("REQ-L2-"))

    for req_id in req_ids:
        bucket = corpus.assignments_via_l3.setdefault(req_id, [])
        if comp_id not in bucket:
            bucket.append(comp_id)


def system_of(corpus: Corpus, req_id: str) -> str | None:
    req = corpus.requirements.get(req_id)
    return req.system if req else None


def build_children_index(corpus: Corpus) -> dict[str, dict[str, list[str]]]:
    """Reverse the parent links: ``parent_id -> {"primary": [...], "contributing": [...]}``."""
    index: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"primary": [], "contributing": []}
    )
    for req in corpus.requirements.values():
        for parent in req.primary_parents:
            index[parent]["primary"].append(req.req_id)
        for parent in req.contributing_parents:
            index[parent]["contributing"].append(req.req_id)
    for entry in index.values():
        entry["primary"].sort(key=natural_key)
        entry["contributing"].sort(key=natural_key)
    return index


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def id_list(ids: list[str], limit: int = 0) -> str:
    if not ids:
        return "—"
    if limit and len(ids) > limit:
        return ", ".join(ids[:limit]) + f", … (+{len(ids) - limit})"
    return ", ".join(ids)


def pct(part: int, total: int) -> str:
    return f"{100.0 * part / total:.0f}%" if total else "—"


def components_for(corpus: Corpus, req_id: str) -> tuple[list[str], bool]:
    """Return ``(component_ids, via_l3_fallback)`` for a REQ-L2."""
    declared = corpus.assignments.get(req_id)
    if declared:
        return sorted(declared, key=natural_key), False
    derived = corpus.assignments_via_l3.get(req_id)
    if derived:
        return sorted(derived, key=natural_key), True
    return [], False


def render_section_1(corpus: Corpus, children: dict[str, dict[str, list[str]]]) -> list[str]:
    lines = [
        "## 1. REQ-L0 → REQ-L1 (Stakeholder Need → System-Anforderung)",
        "",
        f"> Quelle: `{rel(L0_DOC)}` (REQ-L0-Bestand) und die `**Traceability:**`-Felder",
        "> der REQ-L1-Bloecke (Rueckwaerts-Aufloesung).",
        "",
        "| REQ-L0 | SN | Titel | Impl. State | REQ-L1 IDs |",
        "|--------|----|-------|-------------|------------|",
    ]
    for req in corpus.by_level(0):
        kids = children.get(req.req_id, {"primary": [], "contributing": []})
        linked = kids["primary"] + [
            i for i in kids["contributing"] if i not in kids["primary"]
        ]
        linked = [i for i in sorted(set(linked), key=natural_key) if i.startswith("REQ-L1-")]
        sn_match = re.match(r"^(SN-\d+)\s*:\s*(.*)$", req.title)
        sn_id = sn_match.group(1) if sn_match else "—"
        title = sn_match.group(2) if sn_match else req.title
        lines.append(
            f"| {req.req_id} | {sn_id} | {escape_cell(title)} | {req.impl_bucket} "
            f"| {id_list(linked)} |"
        )
    lines.append("")
    return lines


def render_section_2(corpus: Corpus, children: dict[str, dict[str, list[str]]]) -> list[str]:
    lines = [
        "## 2. REQ-L1 → REQ-L2 (System → Subsystem)",
        "",
        "> Rueckwaerts aufgeloest aus den `**Traceability:**`-Feldern der REQ-L2-Bloecke.",
        "> `primaer` = REQ-L2 ohne `(mitwirkend)`-Annotation; mitwirkende Links sind nur",
        "> gezaehlt, nicht ausgeschrieben.",
        "",
        "| REQ-L1 | Titel | Impl. State | Primaere L2-Systeme | REQ-L2 (primaer) | mitw. |",
        "|--------|-------|-------------|---------------------|------------------|-------|",
    ]
    for req in corpus.by_level(1):
        kids = children.get(req.req_id, {"primary": [], "contributing": []})
        primary = [i for i in kids["primary"] if i.startswith("REQ-L2-")]
        contributing = [i for i in kids["contributing"] if i.startswith("REQ-L2-")]
        systems = sorted({s for s in (system_of(corpus, i) for i in primary) if s})
        if not systems:
            systems = sorted({s for s in (system_of(corpus, i) for i in contributing) if s})
        lines.append(
            f"| {req.req_id} | {escape_cell(req.title)} | {req.impl_bucket} "
            f"| {', '.join(systems) if systems else '—'} "
            f"| {id_list(primary)} | {len(contributing) or '—'} |"
        )
    lines.append("")
    return lines


def render_section_3(corpus: Corpus) -> list[str]:
    lines = [
        "## 3. REQ-L2 → Component (Subsystem → Komponente)",
        "",
        "> Je L2-System: alle REQ-L2 des Systems mit der in `L2_*_Architecture.md`",
        "> (§ *Zugeordnete REQ-L2*) deklarierten Komponente sowie den im Requirement-",
        "> Dokument gesetzten Status-Markern.",
        ">",
        "> `(via L3)` = im Architektur-Dokument nicht zugeordnet, sondern aus dem",
        "> L3-Komponenten-Dokument abgeleitet (§ *Zugeordnete L2-Anforderungen* bzw.",
        "> REQ-L3-Parent-Links).",
        "",
    ]
    for index, system in enumerate(corpus.systems, start=1):
        reqs = [r for r in corpus.by_level(2) if r.system == system]
        comps = sorted(
            (c for c in corpus.components.values() if c.system == system),
            key=lambda c: natural_key(c.comp_id),
        )
        l3_count = len([r for r in corpus.by_level(3) if r.system == system])
        lines.append(
            f"### 3.{index} {system} ({len(reqs)} REQ-L2 → {len(comps)} Komponenten, "
            f"{l3_count} REQ-L3)"
        )
        lines.append("")
        if comps:
            lines.append(
                "*Komponenten:* "
                + ", ".join(
                    f"{c.comp_id} ({escape_cell(c.name)})"
                    + ("" if c.declared_in_architecture else " ⚠ nur Verzeichnis")
                    for c in comps
                )
            )
        else:
            lines.append(
                "*Komponenten:* — (kein `L2_*_Architecture.md` vorhanden)"
                if system in corpus.systems_without_architecture
                else "*Komponenten:* —"
            )
        lines.append("")
        if not reqs:
            lines.append("Keine REQ-L2 dokumentiert.")
            lines.append("")
            continue
        lines.append("| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |")
        lines.append("|--------|-------|---------------|-------------|-------------|")
        for req in reqs:
            comp_ids, via_l3 = components_for(corpus, req.req_id)
            rendered = id_list(comp_ids) + (" (via L3)" if via_l3 else "")
            lines.append(
                f"| {req.req_id} | {escape_cell(req.title)} | {rendered} "
                f"| {req.impl_bucket} | {req.test_bucket} |"
            )
        lines.append("")
    return lines


def render_section_4(corpus: Corpus, children: dict[str, dict[str, list[str]]]) -> list[str]:
    def has_child(req: Requirement, child_level: int) -> bool:
        kids = children.get(req.req_id)
        if not kids:
            return False
        prefix = f"REQ-L{child_level}-"
        return any(i.startswith(prefix) for i in kids["primary"] + kids["contributing"])

    levels = [
        ("REQ-L0 (Stakeholder Needs)", corpus.by_level(0), 1, None),
        ("REQ-L1 (System)", corpus.by_level(1), 2, 0),
        ("REQ-L2 (Subsystem)", corpus.by_level(2), 3, 1),
        ("REQ-L3 (Komponente)", corpus.by_level(3), None, 2),
    ]

    lines = [
        "## 4. Coverage Summary",
        "",
        "> *Zerlegt* = mindestens ein Kind-Requirement der naechsten Ebene verweist per",
        "> `**Traceability:**` zurueck. *Parent-Link* = das Requirement deklariert selbst",
        "> mindestens einen Parent. Beides misst die **Dokumentations**-Traceability, nicht",
        "> die Implementierung.",
        ">",
        "> Der niedrige Zerlegungsgrad auf REQ-L2 ist erwartbar: die meisten L2-Systeme",
        "> sind als Leaf-AE deklariert (*keine L3-Zerlegung*), REQ-L3 existiert nur fuer",
        "> die tatsaechlich weiter zerlegten Komponenten.",
        "",
        "| Ebene | Gesamt | mit Parent-Link | zerlegt (Kind-Links) | Zerlegungsgrad |",
        "|-------|--------|-----------------|----------------------|----------------|",
    ]
    for label, reqs, child_level, parent_level in levels:
        total = len(reqs)
        with_parent = (
            "—"
            if parent_level is None
            else str(
                len([r for r in reqs if any(
                    p.startswith(f"REQ-L{parent_level}-") for p in r.all_parents
                )])
            )
        )
        if child_level is None:
            decomposed, ratio = "—", "—"
        else:
            count = len([r for r in reqs if has_child(r, child_level)])
            decomposed, ratio = str(count), pct(count, total)
        lines.append(f"| {label} | {total} | {with_parent} | {decomposed} | {ratio} |")

    comps = sorted(corpus.components.values(), key=lambda c: natural_key(c.comp_id))
    assigned = {
        c
        for source in (corpus.assignments, corpus.assignments_via_l3)
        for ids in source.values()
        for c in ids
    }
    with_req = len([c for c in comps if c.comp_id in assigned])
    lines.append(
        f"| Components (COMP-*) | {len(comps)} | {with_req} | — | {pct(with_req, len(comps))} |"
    )
    lines.append("")

    lines.append("### 4.1 Implementation State (aus den Quelldokumenten uebernommen)")
    lines.append("")
    buckets = list(KNOWN_IMPL_STATES) + [OTHER_BUCKET, UNSET_BUCKET]
    header = ["Ebene"] + buckets + ["Summe"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for label, reqs, _, _ in levels:
        counts = {b: 0 for b in buckets}
        for req in reqs:
            counts[req.impl_bucket] += 1
        lines.append(
            "| "
            + " | ".join(
                [label] + [str(counts[b]) for b in buckets] + [str(len(reqs))]
            )
            + " |"
        )
    lines.append("")
    lines.append(
        "> Die Marker werden **unveraendert** aus den Requirement-Dokumenten uebernommen."
        " Ob ein Marker den tatsaechlichen Code-Stand trifft, prueft dieses Skript nicht."
    )
    lines.append("")

    lines.append("### 4.2 Test Status (aus den Quelldokumenten uebernommen)")
    lines.append("")
    test_buckets = list(KNOWN_TEST_STATES) + [OTHER_BUCKET, UNSET_BUCKET]
    header = ["Ebene"] + test_buckets + ["Summe"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for label, reqs, _, _ in levels:
        counts = {b: 0 for b in test_buckets}
        for req in reqs:
            counts[req.test_bucket] += 1
        lines.append(
            "| "
            + " | ".join(
                [label] + [str(counts[b]) for b in test_buckets] + [str(len(reqs))]
            )
            + " |"
        )
    lines.append("")

    lines.append("### 4.3 System-Zusammenfassung")
    lines.append("")
    lines.append(
        "| System | REQ-L2 | Komponenten | REQ-L3 | REQ-L2 Implemented | REQ-L2 Test Covered |"
    )
    lines.append("|--------|--------|-------------|--------|---|---|")
    total_l2 = total_comp = total_l3 = total_impl = total_cov = 0
    for system in corpus.systems:
        reqs = [r for r in corpus.by_level(2) if r.system == system]
        comps = [c for c in corpus.components.values() if c.system == system]
        l3 = [r for r in corpus.by_level(3) if r.system == system]
        impl = len([r for r in reqs if r.impl_bucket == "Implemented"])
        covered = len([r for r in reqs if r.test_bucket == "Covered"])
        total_l2 += len(reqs)
        total_comp += len(comps)
        total_l3 += len(l3)
        total_impl += impl
        total_cov += covered
        lines.append(
            f"| {system} | {len(reqs)} | {len(comps)} | {len(l3)} | {impl} | {covered} |"
        )
    lines.append(
        f"| **Gesamt** | **{total_l2}** | **{total_comp}** | **{total_l3}** "
        f"| **{total_impl}** | **{total_cov}** |"
    )
    lines.append("")
    return lines


def render_section_5(corpus: Corpus, children: dict[str, dict[str, list[str]]]) -> list[str]:
    known_ids = set(corpus.requirements)

    def undecomposed(level: int, child_prefix: str) -> list[str]:
        out = []
        for req in corpus.by_level(level):
            kids = children.get(req.req_id, {"primary": [], "contributing": []})
            if not any(
                i.startswith(child_prefix) for i in kids["primary"] + kids["contributing"]
            ):
                out.append(req.req_id)
        return out

    l0_open = undecomposed(0, "REQ-L1-")
    l1_open = undecomposed(1, "REQ-L2-")
    l2_no_arch_comp = [
        r.req_id for r in corpus.by_level(2) if not corpus.assignments.get(r.req_id)
    ]
    l2_no_comp = [
        r.req_id for r in corpus.by_level(2) if not components_for(corpus, r.req_id)[0]
    ]
    table_only = [r.req_id for r in corpus.by_level(2) if r.table_only]
    l1_no_parent = [
        r.req_id
        for r in corpus.by_level(1)
        if not any(p.startswith("REQ-L0-") for p in r.all_parents)
    ]
    l2_no_parent = [
        r.req_id
        for r in corpus.by_level(2)
        if not any(p.startswith("REQ-L1-") for p in r.all_parents)
    ]
    dangling: dict[str, list[str]] = defaultdict(list)
    for req in sorted(corpus.requirements.values(), key=lambda r: natural_key(r.req_id)):
        for parent in req.all_parents:
            if parent not in known_ids:
                dangling[parent].append(req.req_id)
    assigned_comps = {
        comp_id
        for source in (corpus.assignments, corpus.assignments_via_l3)
        for ids in source.values()
        for comp_id in ids
    }
    orphan_comps = sorted(
        (c.comp_id for c in corpus.components.values() if c.comp_id not in assigned_comps),
        key=natural_key,
    )
    assigned_unknown = sorted(
        (c for c in assigned_comps if c not in corpus.components), key=natural_key
    )
    undeclared_comps = sorted(
        (
            c.comp_id
            for c in corpus.components.values()
            if not c.declared_in_architecture
        ),
        key=natural_key,
    )

    lines = [
        "## 5. Luecken und Auffaelligkeiten",
        "",
        "> Maschinell erkannt. Kein Qualitaetsurteil — nur Stellen, an denen die",
        "> Dokumenten-Kette bricht.",
        "",
        "| Befund | Anzahl | IDs |",
        "|--------|--------|-----|",
        f"| REQ-L0 ohne REQ-L1-Zerlegung | {len(l0_open)} | {id_list(l0_open, 40)} |",
        f"| REQ-L1 ohne REQ-L0-Parent | {len(l1_no_parent)} | {id_list(l1_no_parent, 40)} |",
        f"| REQ-L1 ohne REQ-L2-Zerlegung | {len(l1_open)} | {id_list(l1_open, 40)} |",
        f"| REQ-L2 ohne REQ-L1-Parent | {len(l2_no_parent)} | {id_list(l2_no_parent, 40)} |",
        f"| REQ-L2 ohne Zuordnung im Architektur-Dokument | {len(l2_no_arch_comp)} "
        f"| {id_list(l2_no_arch_comp, 40)} |",
        f"| REQ-L2 ohne Komponente (auch nach L3-Ableitung) | {len(l2_no_comp)} "
        f"| {id_list(l2_no_comp, 40)} |",
        f"| Komponenten ohne REQ-L2-Zuordnung | {len(orphan_comps)} "
        f"| {id_list(orphan_comps, 40)} |",
        f"| Komponenten ohne Zeile im Architektur-Dokument | {len(undeclared_comps)} "
        f"| {id_list(undeclared_comps, 40)} |",
        f"| Zugeordnete, aber voellig unbekannte Komponenten | {len(assigned_unknown)} "
        f"| {id_list(assigned_unknown, 40)} |",
        f"| Verweise auf nicht existierende REQ-IDs | {len(dangling)} "
        f"| {id_list(sorted(dangling, key=natural_key), 40)} |",
        f"| REQ-L2 nur in Tabellen, ohne `###`-Block | {len(table_only)} "
        f"| {id_list(table_only, 40)} |",
        f"| L2-Systeme ohne Architektur-Dokument | {len(corpus.systems_without_architecture)} "
        f"| {id_list(corpus.systems_without_architecture, 40)} |",
        f"| Doppelt vergebene REQ-IDs (gleiche Datei) | {len(corpus.duplicate_ids)} "
        f"| {id_list(sorted({i for i, _, _ in corpus.duplicate_ids}, key=natural_key), 40)} |",
        "",
    ]
    if dangling:
        lines.append(
            "**Nicht existierende Parent-IDs im Detail:** "
            + "; ".join(
                f"`{parent}` (referenziert von "
                f"{id_list(sorted(dangling[parent], key=natural_key), 6)})"
                for parent in sorted(dangling, key=natural_key)
            )
        )
        lines.append("")
    if corpus.duplicate_ids:
        lines.append(
            "**Doppelte REQ-IDs:** dieselbe ID taucht mehrfach als `###`-Ueberschrift im"
            " selben Dokument auf (meist durch nachtraeglich angehaengte"
            " *Erweiterung*-Abschnitte). Diese Matrix zaehlt solche IDs **einmal** und"
            " fuehrt die Bloecke zusammen (Marker: letzter gesetzter Wert gewinnt;"
            " Parent-Links: Vereinigung). Betroffene Dokumente: "
            + ", ".join(
                f"`{source}`"
                for source in sorted({source for _, source, _ in corpus.duplicate_ids})
            )
            + "."
        )
        lines.append("")
    return lines


def render(corpus: Corpus, timestamp: str) -> str:
    children = build_children_index(corpus)
    lines = [
        "# ReqogniLoom Traceability Matrix",
        "",
        "> **AUTOGENERIERT — NICHT MANUELL EDITIEREN.**",
        f"> Generiert von `{SCRIPT_REL}` am {timestamp} aus"
        f" {corpus.req_doc_count} Requirement-Dokumenten und"
        f" {corpus.arch_doc_count} Architektur-Dokumenten.",
        f"> Neu erzeugen: `python3 {SCRIPT_REL}` — Aenderungen gehoeren in die",
        "> Quelldokumente unter `docs/se/L0/` und `docs/se/L1/`, nicht in diese Datei.",
        ">",
        "> Traceability-Kette der SE-Kaskade:",
        "> **REQ-L0 → REQ-L1 → REQ-L2 → Component → REQ-L3**",
        ">",
        "> Quellen:",
        f"> - `{rel(L0_DOC)}` (REQ-L0 / Stakeholder Needs)",
        "> - `docs/se/L1/**/L1_*_Requirements.md` (REQ-L1)",
        "> - `docs/se/L1/**/L2_*_Requirements.md` (REQ-L2)",
        "> - `docs/se/L1/**/L3_*_Requirements.md` (REQ-L3)",
        "> - `docs/se/L1/**/L2_*_Architecture.md` (COMP-* und REQ-L2 → Component)",
        ">",
        "> **Notation:** `—` = im Quelldokument nicht verknuepft / nicht zutreffend.",
        "> Alle Status-Marker sind unveraendert aus den Quelldokumenten uebernommen.",
        "",
        "---",
        "",
    ]
    lines += render_section_1(corpus, children)
    lines += ["---", ""]
    lines += render_section_2(corpus, children)
    lines += ["---", ""]
    lines += render_section_3(corpus)
    lines += ["---", ""]
    lines += render_section_4(corpus, children)
    lines += ["---", ""]
    lines += render_section_5(corpus, children)
    return "\n".join(lines).rstrip("\n") + "\n"


_STAMP_RE = re.compile(r"^> Generiert von .*$", re.MULTILINE)


def strip_stamp(text: str) -> str:
    """Blank the timestamp line so two runs can be compared byte-for-byte."""
    return _STAMP_RE.sub("> Generiert von <stamp>", text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the checked-in matrix differs (timestamp ignored)",
    )
    parser.add_argument(
        "--stdout", action="store_true", help="print the matrix instead of writing it"
    )
    args = parser.parse_args(argv)

    corpus = collect()
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rendered = render(corpus, timestamp)

    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    if args.check:
        if not OUTPUT.exists():
            print(f"{rel(OUTPUT)} missing — run: python3 {SCRIPT_REL}", file=sys.stderr)
            return 1
        current = OUTPUT.read_text(encoding="utf-8")
        if strip_stamp(current) != strip_stamp(rendered):
            print(
                f"{rel(OUTPUT)} is stale — run: python3 {SCRIPT_REL}", file=sys.stderr
            )
            return 1
        print(f"{rel(OUTPUT)} is up to date.")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(
        f"{rel(OUTPUT)} written: "
        f"{len(corpus.by_level(0))} REQ-L0, {len(corpus.by_level(1))} REQ-L1, "
        f"{len(corpus.by_level(2))} REQ-L2, {len(corpus.by_level(3))} REQ-L3, "
        f"{len(corpus.components)} Components, {len(corpus.systems)} L2-Systeme "
        f"(aus {corpus.req_doc_count} Requirement- und "
        f"{corpus.arch_doc_count} Architektur-Dokumenten)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
