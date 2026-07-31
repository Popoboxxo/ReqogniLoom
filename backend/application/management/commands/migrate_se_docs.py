"""ReqFlow self-migration — import docs/se/ into a running ReqFlow instance.

Walks the project's own SE requirements register (``docs/se/``, the L0-L3
V-model documentation produced by the SE-Kaskade agents) and imports it into
ReqFlow as real artifacts (StakeholderNeed, Requirement, ArchitectureElement,
Adr) via the existing :class:`application.import_service.ImportService` —
the same COMP-AS-009 entry point used by the CSV bulk-import REST/MCP tools.
No persistence logic is reimplemented here; this command only parses
markdown into the CSV shape ``ImportService`` expects
(:data:`application.export_service.ENTITY_FIELD_SPECS`) and calls
``import_csv``.

``--format=table`` mode (issue #117): the legacy ``docs/REQUIREMENTS.md``
register predates the SE-Kaskade and uses a flat markdown **table** per
section (``| REQ-ID | Kategorie | Titel | Beschreibung | Status |``) instead
of ``### REQ-Lx-...`` headings, so none of the parsing above applies to it.
``--format=table --file docs/REQUIREMENTS.md`` reads that pipe-table format
and imports every row as a ``Requirement`` through the exact same
``ImportService.import_csv`` entry point (see :meth:`Command._handle_table_import`),
so it gets the same workflow-state wiring (REQ-143 / issue #113) instead of
landing as a workflow-dead artifact.

Document-to-entity mapping (see module-level ``_classify_file``):

* ``docs/se/L0/*.md``            -> StakeholderNeed  (one row per ``### REQ-L0-...`` heading)
* ``docs/se/**/*_Requirements.md`` -> Requirement      (one row per ``### REQ-L[1-3]-...`` heading)
* ``docs/se/**/*_Architecture.md`` -> ArchitectureElement (one row per file)
* ``docs/se/ADR/ADR-*.md``        -> Adr               (one row per file)

TestCase, Risk and Issue are intentionally NOT imported by this command:

* The 6 ``*_TestModel.md`` files mix prose narrative, embedded raw JSON blobs
  and per-component/per-scenario subsections with no consistent structure,
  so a regex-based extractor would risk producing garbage TestCase rows.
* ``docs/se`` has no Risk or Issue register at all (no source documents).

Every file that does not match one of the four mapping rules above — and
every parsed document that yields zero entities (e.g. an empty placeholder
file) — is reported as an explicit WARNING (printed and logged), never
silently skipped.

Idempotency: every persistence/application entity that ``ImportService``
supports round-trips a caller-settable ``uid`` field
(:data:`application.export_service._COMMON_PERSISTENCE_FIELDS` /
``_COMMON_APP_FIELDS``) that is NOT one of ``ImportService``'s special
identity columns, so it is free to use as ReqFlow's own stable identity key.
This command derives ``uid`` deterministically from each source document
(the ``REQ-Lx-...`` heading id, the ``ARCH-Lx-...`` / ``COMP-Xx-NNN`` code, or
the ``ADR-NNN`` filename prefix) and, before every import call, queries the
target workspace for ``uid`` values that already exist so a second run of
this command imports nothing twice.

V-model level mapping: docs/se's own requirement numbering (L1 System / L2
Subsystem / L3 Component) does NOT line up 1:1 with the
``persistence.models.RequirementLevel`` enum (L0_SYSTEM=0 .. L4_MATERIAL=4).
This command maps REQ-L1 -> level 0, REQ-L2 -> level 1, REQ-L3 -> level 2 (see
``_REQ_LEVEL_MAP``); it deliberately leaves L4 unused since docs/se has no L4
documents to import.

Known ImportService quirk (NOT patched here — mitigated in this command
only, per the "do not touch import_service.py without a genuine blocking
defect" instruction): ``ImportService._parse_csv`` strips any *physical* CSV
line starting with ``#`` (a shortcut for stripping ExportService's
terminology-profile comment header) without RFC4180 quoted-multiline-field
awareness. Since docs/se descriptions are full markdown bodies that
routinely contain lines starting with ``#`` (nested headings), every
multi-line text field is passed through :func:`_csv_safe` first, which
turns a leading ``#`` on any embedded line into `` #`` (leading space) so it
no longer looks like a comment line to the naive stripper. This is purely a
caller-side CSV-construction safeguard; it does not change any persisted
content (the leading space is only ever present inside the CSV transport
representation... but note it DOES become part of the stored description,
since ImportService has no way to reverse it — this is disclosed as a
minor, cosmetic, one-time formatting side effect on any embedded markdown
heading line, acceptable for a one-shot documentation migration).

Usage::

    python manage.py migrate_se_docs --dry-run
    python manage.py migrate_se_docs
    python manage.py migrate_se_docs --workspace-id <uuid> --docs-root /app/docs/se

Safe to run repeatedly: rows whose derived ``uid`` already exists in the
target workspace are skipped (counted as "already_imported"), never
duplicated.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from application.export_service import ENTITY_FIELD_SPECS
from application.import_service import ImportService
from application.models import Adr
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Requirement,
    StakeholderNeed,
    TraceLink,
    User,
    Workspace,
)
from traceability.types import LinkType

logger = logging.getLogger(__name__)

# Default target: the seed_demo.py demo workspace (stable id, always present in
# a freshly seeded dev stack). Override with --workspace-id for a real target.
_DEFAULT_WORKSPACE_ID = "6d20f0b9-d2cf-46a0-b916-79f8b417210f"
_DEFAULT_USERNAME = "admin"

# Max rows per ImportService.import_csv() call (mirrors ImportService._MAX_ROWS).
# Chunking defensively even though the largest bucket (Requirement, ~758 rows)
# is currently under this limit.
_MAX_ROWS_PER_CALL = 1000

# ---------------------------------------------------------------------------
# Heading regexes (see docstring above for the corpus verification behind them)
# ---------------------------------------------------------------------------

# Any markdown heading (1-6 '#'), used as a body-capture boundary so that no
# section body ever swallows a subsequent heading of ANY level.
_ANY_HEADING_RE = re.compile(r"^#{1,6}\s")

# "### REQ-L0-001 — SN-01: Title", "### REQ-L1-006: Title",
# "### REQ-L2-AT-017 (vollstaendig): Title" - the segment between the id and
# the final colon varies (absent, em-dash annotation, parenthetical
# annotation), so it is matched non-specifically as "anything but a colon".
_REQ_HEADING_RE = re.compile(r"^### (REQ-L[0-3][\w-]*)[^:]*:\s*(.+)$")

# "> **System:** AiOrchestrationSystem (ARCH-L1-008)"
_ARCH_L1_CODE_RE = re.compile(r"\(ARCH-L1-\d+\)")
_SYSTEM_NAME_RE = re.compile(r"\*\*System:\*\*\s*([\w]+)")
# Component folder name, e.g. "COMP-AS-008_ExportService"
_COMP_FOLDER_RE = re.compile(r"(COMP-[A-Z]+-\d+)_")

_ADR_FILENAME_RE = re.compile(r"^(ADR-\d+)")
_ADR_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+)$", re.MULTILINE)

# docs/se REQ-Lx numbering -> persistence.models.RequirementLevel (see module
# docstring: the two numbering schemes are NOT the same).
_REQ_LEVEL_MAP = {"L1": 0, "L2": 1, "L3": 2}

# ---------------------------------------------------------------------------
# Post-import passes (run AFTER the four CSV entity buckets are imported)
# ---------------------------------------------------------------------------

# Feature 1 — ArchitectureElement hierarchy (parent_id).
# parent_id is a real persistence field (REQ-L1-041) but is deliberately NOT
# part of ENTITY_FIELD_SPECS["ArchitectureElement"], so ImportService cannot
# carry it. This command therefore resolves the parent from the deterministic
# docs/se folder nesting in a second pass.
#
# Service-vs-ORM decision: ArchitectureService.update_architecture_element(...)
# exists and would normally be the right write path, BUT its Extended/Standard
# rigor invariant I2 (parent.get_level() < child.get_level(),
# application.validators) compares the CURRENT tree depth of both elements.
# Right after a flat CSV import every element is a root (level 0), so the very
# first re-parent is always level-0 -> level-0 and I2 rejects it — the service
# path cannot construct a hierarchy from a flat import at all. Teaching it a
# batch/holistic tree-construction mode is disproportionate for a one-shot
# migration, so this pass writes parent_id via a direct, idempotency-guarded
# ORM update (documented batch job — NOT a regular API write path). No version
# bump / domain event is emitted, which also keeps repeated runs side-effect
# free.
_ARCH_ROOT_UID = "ARCH-L1-000"  # docs/se/L1/Gesamtsystem root, has no parent.

# Feature 2 — traceability-matrix.md -> TraceLink pass.
# The consolidated matrix (docs/se/traceability-matrix.md) is read after all
# four entity buckets exist and turned into TraceLinks via TraceLinkService
# (the regular, event-emitting creation path — analogous to ImportService for
# the entity buckets). Link-type + orientation are chosen per matrix section so
# they also satisfy the SE endpoint-semantics matrix
# (traceability.types.SE_LINK_SEMANTICS) and therefore stay valid in se_mode:
#   §1 REQ-L0 -> REQ-L1 : (REQ-L1)   derives-from (REQ-L0)  Requirement->StakeholderNeed
#   §2 REQ-L1 -> REQ-L2 : (REQ-L2)   derives-from (REQ-L1)  Requirement->Requirement
#   §3 REQ-L2 -> Component: (Component) implements (REQ-L2)  ArchitectureElement->Requirement
# The §3 "Test Case" column is intentionally NOT linked: TestCase artifacts are
# not imported by this command (see module docstring), so such an endpoint would
# never resolve. This is a documented, deliberate omission — not a parse gap.
_TRACE_MATRIX_FILENAME = "traceability-matrix.md"

_LINK_DERIVES_FROM = LinkType.DERIVES_FROM.value  # "derives-from"
_LINK_IMPLEMENTS = LinkType.IMPLEMENTS.value  # "implements"

# uid token patterns used by the traceability-matrix parser. Each requires the
# trailing numeric group so bare column headers ("REQ-L0", "REQ-L2") and
# placeholder rows ("... (20 weitere REQ-L2-AS)") never match.
_UID_L0_RE = re.compile(r"REQ-L0-\d+")
_UID_L1_RE = re.compile(r"REQ-L1-\d+")
_UID_L2_RE = re.compile(r"REQ-L2-[A-Z]+-\d+")
_UID_COMP_RE = re.compile(r"COMP-[A-Z]+-\d+")

# Matrix section -> parser spec, keyed by the leading section number.
_MATRIX_SECTION_SPECS = {"1": "L0_L1", "2": "L1_L2", "3": "L2_COMP"}
_MATRIX_HEADING_RE = re.compile(r"^#{2,3}\s+(\d)")

_ADR_STATUS_MAP = {
    "PROPOSED": Adr.Status.IN_REVIEW,
    "DRAFT": Adr.Status.DRAFT,
    "IN REVIEW": Adr.Status.IN_REVIEW,
    "ACCEPTED": Adr.Status.APPROVED,
    "APPROVED": Adr.Status.APPROVED,
    "REJECTED": Adr.Status.REJECTED,
    "SUPERSEDED": Adr.Status.SUPERSEDED,
}


# ---------------------------------------------------------------------------
# Generic markdown helpers
# ---------------------------------------------------------------------------


def _csv_safe(text: Optional[str]) -> str:
    """Guard a multi-line text value against ImportService's naive '#'-strip.

    See module docstring: ``ImportService._parse_csv`` strips any physical
    line starting with '#' before parsing. A markdown body may legitimately
    contain lines starting with '#' (nested headings); inserting a leading
    space after the newline keeps the content intact end-to-end.
    """
    if not text:
        return ""
    return re.sub(r"\n#", "\n #", text)


def _extract_req_sections(text: str) -> List[Tuple[str, str, str]]:
    """Split *text* into ``(uid, title, body)`` tuples for every REQ heading.

    Any heading (1-6 '#') ends the current section's body capture, whether or
    not it matches the REQ pattern — this prevents an organisational
    sub-heading (e.g. "## Offene Punkte") from leaking into the preceding
    requirement's body.
    """
    sections: List[Tuple[str, str, str]] = []
    current_id: Optional[str] = None
    current_title = ""
    body_lines: List[str] = []

    def _flush() -> None:
        if current_id:
            sections.append((current_id, current_title, "\n".join(body_lines).strip()))

    for line in text.splitlines():
        if _ANY_HEADING_RE.match(line):
            _flush()
            body_lines.clear()
            match = _REQ_HEADING_RE.match(line)
            if match:
                current_id = match.group(1)
                current_title = match.group(2).strip()
            else:
                current_id = None
                current_title = ""
            continue
        if current_id:
            body_lines.append(line)
    _flush()
    return sections


def _first_markdown_title(text: str, fallback: str) -> str:
    """Return the text of the first '# ' (H1) heading, skipping any YAML
    frontmatter block (L3 architecture docs are preceded by a
    ``---\\n...\\n---`` frontmatter that never contains an H1)."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _section_body_after(text: str, heading_prefix: str) -> str:
    """Return the body of the first heading whose text starts with
    *heading_prefix*, up to (not including) the next heading of any level.

    Used both for architecture docs ("1." -> "## 1. Verantwortlichkeit") and
    ADR docs ("Kontext" -> "## Kontext", "Entscheidung" -> "## Entscheidung").
    """
    lines = text.splitlines()
    capturing = False
    body: List[str] = []
    for line in lines:
        if _ANY_HEADING_RE.match(line):
            if capturing:
                break
            if line.lstrip("#").strip().startswith(heading_prefix):
                capturing = True
            continue
        if capturing:
            body.append(line)
    return "\n".join(body).strip()


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------


def _classify_file(path: Path, docs_root: Path) -> str:
    """Return the entity-type bucket key for *path*, or "UNMAPPED"."""
    try:
        rel_parts = path.relative_to(docs_root).parts
    except ValueError:
        rel_parts = path.parts
    name = path.name
    if rel_parts and rel_parts[0] == "L0":
        return "StakeholderNeed"
    if name.endswith("_Requirements.md"):
        return "Requirement"
    if name.endswith("_Architecture.md"):
        return "ArchitectureElement"
    if path.parent.name == "ADR" and name.startswith("ADR-"):
        return "Adr"
    return "UNMAPPED"


def _unmapped_reason(path: Path) -> str:
    """Best-effort human-readable reason why *path* has no mapping rule."""
    name = path.name
    if name.endswith("_TestModel.md"):
        return (
            "TestCase not auto-imported: test-model docs mix prose, embedded "
            "JSON and per-component/per-scenario sections inconsistently — "
            "extracting individual TestCases here risks corrupt data."
        )
    if name.endswith("_Backlog.md"):
        return "backlog/placeholder document, not a formal requirements source."
    return (
        "no entity-type mapping rule for this document (not a "
        "*_Requirements.md, *_Architecture.md, docs/se/ADR/ADR-*.md, or "
        "docs/se/L0/*.md file)."
    )


# ---------------------------------------------------------------------------
# Per-entity row builders
# ---------------------------------------------------------------------------


def _stakeholder_need_row(uid: str, title: str, body: str) -> Dict[str, str]:
    # Source documents (docs/se/L0/*.md) do not track status; draft is the
    # conscious default for newly imported StakeholderNeeds.
    return {
        "title": title[:500],
        "description": _csv_safe(body),
        "status": "draft",
        "uid": uid,
    }


def _requirement_level(uid: str) -> int:
    parts = uid.split("-")
    return _REQ_LEVEL_MAP[parts[1]]


def _requirement_row(uid: str, title: str, body: str) -> Dict[str, str]:
    # Source documents (docs/se/**/*_Requirements.md) do not track status; draft
    # is the conscious default for newly imported Requirements.
    return {
        "title": title[:500],
        "description": _csv_safe(body),
        "level": str(_requirement_level(uid)),
        "status": "draft",
        "uid": uid,
    }


def _architecture_uid(
    path: Path, text: str, warnings: List[str]
) -> Tuple[str, str]:
    """Derive a stable ``(uid, element_type)`` pair for an Architecture.md file."""
    if path.name == "L1_Gesamtsystem_Architecture.md":
        return "ARCH-L1-000", "subsystem"
    comp_match = _COMP_FOLDER_RE.search(path.parent.name)
    if comp_match:
        return comp_match.group(1), "component"
    code_match = _ARCH_L1_CODE_RE.search(text[:2000])
    if code_match:
        return code_match.group(0).strip("()"), "subsystem"
    # Fallback: no embedded ARCH-L1-xxx code (e.g. VectorSearchServiceSystem).
    # Derive a stable synthetic uid from the "System:" name so idempotency
    # still holds across reruns.
    system_match = _SYSTEM_NAME_RE.search(text[:2000])
    slug = system_match.group(1) if system_match else path.stem
    fallback_uid = f"ARCH-L2-{slug}"
    warnings.append(
        f"{path}: no '(ARCH-L1-xxx)' code found in header; using fallback "
        f"uid '{fallback_uid}' derived from the System: name."
    )
    return fallback_uid, "subsystem"


def _architecture_row(
    uid: str, title: str, body: str, element_type: str
) -> Dict[str, str]:
    return {
        "title": title[:500],
        "description": _csv_safe(body),
        "element_type": element_type,
        "uid": uid,
    }


def _adr_row(
    uid: str, title: str, description: str, context: str, consequences: str, status: str
) -> Dict[str, str]:
    return {
        "title": title[:200],
        "description": _csv_safe(description),
        "context": _csv_safe(context),
        "consequences": _csv_safe(consequences),
        "status": status,
        "uid": uid,
    }


# ---------------------------------------------------------------------------
# Per-file parsers -> (uid, row) list + warnings
# ---------------------------------------------------------------------------


def _parse_stakeholder_need_file(
    path: Path,
) -> Tuple[List[Tuple[str, Dict[str, str]]], List[str]]:
    text = path.read_text(encoding="utf-8")
    rows = [
        (uid, _stakeholder_need_row(uid, title, body))
        for uid, title, body in _extract_req_sections(text)
        if uid.startswith("REQ-L0")
    ]
    warnings: List[str] = []
    if not rows:
        warnings.append(f"{path}: no REQ-L0 stakeholder-need headings found (0 entries).")
    return rows, warnings


def _parse_requirement_file(
    path: Path,
) -> Tuple[List[Tuple[str, Dict[str, str]]], List[str]]:
    text = path.read_text(encoding="utf-8")
    rows = [
        (uid, _requirement_row(uid, title, body))
        for uid, title, body in _extract_req_sections(text)
        if not uid.startswith("REQ-L0")
    ]
    warnings: List[str] = []
    if not rows:
        warnings.append(f"{path}: no REQ-L[1-3] requirement headings found (0 entries).")
    return rows, warnings


def _parse_architecture_file(
    path: Path, warnings: List[str]
) -> Tuple[str, Dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    uid, element_type = _architecture_uid(path, text, warnings)
    title = _first_markdown_title(text, fallback=path.stem)
    body = _section_body_after(text, "1.")
    if not body:
        warnings.append(
            f"{path}: no '## 1. ...' responsibility section found; description left empty."
        )
    return uid, _architecture_row(uid, title, body, element_type)


def _parse_adr_file(
    path: Path, warnings: List[str]
) -> Optional[Tuple[str, Dict[str, str]]]:
    text = path.read_text(encoding="utf-8")
    match = _ADR_FILENAME_RE.match(path.name)
    if not match:
        warnings.append(f"{path}: filename does not start with 'ADR-<number>', skipped.")
        return None
    uid = match.group(1)
    title = _first_markdown_title(text, fallback=path.stem)
    status_match = _ADR_STATUS_RE.search(text)
    raw_status = status_match.group(1).strip() if status_match else ""
    status = _ADR_STATUS_MAP.get(raw_status.upper(), Adr.Status.DRAFT)
    if raw_status and raw_status.upper() not in _ADR_STATUS_MAP:
        warnings.append(
            f"{path}: unrecognized ADR status '{raw_status}', defaulting to Draft."
        )
    context = _section_body_after(text, "Kontext")
    consequences = _section_body_after(text, "Entscheidung")
    # description holds the full source document so nothing is lost even
    # though context/consequences already extract the structured highlights.
    row = _adr_row(uid, title, text, context, consequences, status)
    return uid, row


# ---------------------------------------------------------------------------
# --format=table parser (issue #117): docs/REQUIREMENTS.md-style pipe tables
# ---------------------------------------------------------------------------

# A data row's REQ-ID cell, e.g. "REQ-001". Deliberately distinct from
# _REQ_HEADING_RE's "REQ-L[0-3]..." scheme: docs/REQUIREMENTS.md predates the
# SE-Kaskade V-model numbering and uses flat "REQ-NNN" ids.
_REQ_TABLE_ID_RE = re.compile(r"^REQ-\d+$")

# A markdown table separator row, e.g. "|---|:---:|---|".
_TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")

# Unescaped-pipe splitter: splits on '|' not preceded by a backslash, so a
# literal '|' inside a cell (escaped as '\|', the standard markdown
# convention docs/REQUIREMENTS.md itself uses) is not mistaken for a column
# boundary.
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def _split_table_row(line: str) -> List[str]:
    """Split a ``| a | b | c |`` markdown table row into stripped cells.

    Honours ``\\|`` as an escaped, non-splitting pipe and drops the empty
    leading/trailing cells produced by the row's bounding ``|`` characters.
    """
    parts = _UNESCAPED_PIPE_RE.split(line)
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip().replace("\\|", "|") for p in parts]


def _is_table_separator_row(cells: List[str]) -> bool:
    return bool(cells) and all(_TABLE_SEPARATOR_CELL_RE.match(c) for c in cells)


def _requirement_table_row(
    uid: str, category: str, title: str, description: str, status: str
) -> Dict[str, str]:
    """Build an ImportService CSV row for one docs/REQUIREMENTS.md table row.

    ``status`` is passed through verbatim (not defaulted to "draft" like the
    docs/se headings parser): unlike docs/se, this register DOES track a
    per-requirement status. ImportService itself maps the raw text onto the
    workspace's WorkflowEngineDefinition states (or a safe fallback) — see
    ``application.import_service._insert_rows`` / ``reqif_import_service._map_status``
    — so this command does not need to know about workflow states at all.
    ``level`` (V-model L0-L4) is deliberately left unset: docs/REQUIREMENTS.md
    predates that numbering and none of its rows can be mapped to it without
    guessing (persistence.models.RequirementLevel: NULL = "not yet assigned").
    """
    return {
        "title": title[:500],
        "description": _csv_safe(description),
        "category": category,
        "status": status,
        "uid": uid,
    }


def _parse_requirements_table_file(
    path: Path,
) -> Tuple[List[Tuple[str, Dict[str, str]]], List[str]]:
    """Parse a docs/REQUIREMENTS.md-style file into ``(uid, row)`` tuples.

    Recognises every markdown table row whose first cell matches
    ``REQ-<number>`` (see :data:`_REQ_TABLE_ID_RE`), regardless of which of
    the file's (possibly many) ``| REQ-ID | Kategorie | Titel | Beschreibung |
    Status |`` tables it belongs to — header and separator rows are skipped
    by content, not by table-boundary tracking, so multiple same-shaped
    tables in one file all contribute rows.

    A small number of source rows contain an unescaped ``|`` inside the
    Beschreibung cell (e.g. an inline URL or markdown table), which produces
    more than 5 cells; those extra cells are folded back into the
    description column (cells[2] is Titel, the last cell is always Status)
    rather than being dropped or misaligning the columns.
    """
    text = path.read_text(encoding="utf-8")
    rows: List[Tuple[str, Dict[str, str]]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_table_row(stripped)
        if len(cells) < 5:
            continue
        req_id = cells[0]
        if req_id.upper() == "REQ-ID":
            continue  # header row
        if _is_table_separator_row(cells):
            continue
        if not _REQ_TABLE_ID_RE.match(req_id):
            continue  # not a requirement data row (prose, other table, etc.)
        category, title = cells[1], cells[2]
        status = cells[-1]
        description = " | ".join(cells[3:-1])
        rows.append((req_id, _requirement_table_row(req_id, category, title, description, status)))

    warnings: List[str] = []
    if not rows:
        warnings.append(f"{path}: no 'REQ-<number>' requirement table rows found (0 entries).")
    return rows, warnings


def _write_csv(rows: List[Dict[str, str]], entity_type: str) -> str:
    """Serialise *rows* to CSV using the exact column order ImportService
    expects (application.export_service.ENTITY_FIELD_SPECS[entity_type])."""
    fieldnames = [col for col, _kind in ENTITY_FIELD_SPECS[entity_type]]
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, extrasaction="ignore", quoting=csv.QUOTE_ALL
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def _existing_uids(entity_type: str, workspace_id) -> set:
    """Return the set of ``uid`` values already present for *entity_type* in
    the target workspace (idempotency check). Must run inside an active
    tenant context (persistence.middleware.set_request_tenant)."""
    if entity_type == "StakeholderNeed":
        qs = StakeholderNeed.objects.filter(artifact__workspace_id=workspace_id)
    elif entity_type == "Requirement":
        qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
    elif entity_type == "ArchitectureElement":
        qs = ArchitectureElement.objects.filter(artifact__workspace_id=workspace_id)
    elif entity_type == "Adr":
        qs = Adr.objects.filter(workspace_id=workspace_id)
    else:
        return set()
    return set(qs.exclude(uid__isnull=True).exclude(uid="").values_list("uid", flat=True))


# ---------------------------------------------------------------------------
# Feature 1 — ArchitectureElement hierarchy resolution (folder-structure based)
# ---------------------------------------------------------------------------


def _resolve_architecture_parents(
    entries: List[Tuple[str, str, Path]]
) -> Tuple[Dict[str, Optional[str]], List[str]]:
    """Resolve each ArchitectureElement's parent uid from the folder nesting.

    *entries* is the deduplicated ``(uid, element_type, path)`` list gathered
    while parsing the ``*_Architecture.md`` files. Resolution is purely
    structural and deterministic:

    * the root (``ARCH-L1-000``) has no parent;
    * a subsystem's parent is the root Gesamtsystem element;
    * a component's parent is the L2 subsystem whose directory
      (``.../L2/<System>``) is the nearest ancestor of the component file
      (``.../L2/<System>/Components/COMP-.../L3_..._Architecture.md``).

    Returns a ``{uid: parent_uid_or_None}`` mapping plus warnings for any
    element whose structural parent could not be determined.
    """
    warnings: List[str] = []
    root_present = any(uid == _ARCH_ROOT_UID for uid, _etype, _path in entries)

    # Index every non-root subsystem by the directory that contains its file;
    # a component's parent is the subsystem whose directory is its ancestor.
    subsystem_dir_to_uid: Dict[Path, str] = {}
    for uid, element_type, path in entries:
        if uid == _ARCH_ROOT_UID or element_type == "component":
            continue
        subsystem_dir_to_uid[path.parent] = uid

    parent_of: Dict[str, Optional[str]] = {}
    for uid, element_type, path in entries:
        if uid == _ARCH_ROOT_UID:
            parent_of[uid] = None
        elif element_type == "component":
            parent_uid: Optional[str] = None
            for ancestor in path.parents:
                if ancestor in subsystem_dir_to_uid:
                    parent_uid = subsystem_dir_to_uid[ancestor]
                    break
            if parent_uid is None:
                warnings.append(
                    f"{path}: component '{uid}' has no resolvable L2 subsystem "
                    f"parent in the folder structure; parent left unset."
                )
            parent_of[uid] = parent_uid
        else:
            parent_of[uid] = _ARCH_ROOT_UID if root_present else None
            if not root_present:
                warnings.append(
                    f"{path}: subsystem '{uid}' cannot be linked to root "
                    f"'{_ARCH_ROOT_UID}' (root architecture file not parsed); "
                    f"parent left unset."
                )
    return parent_of, warnings


# ---------------------------------------------------------------------------
# Feature 2 — traceability-matrix.md parsing + uid->artifact index
# ---------------------------------------------------------------------------


def _parse_trace_matrix(text: str) -> List[Tuple[str, str, str]]:
    """Parse ``traceability-matrix.md`` into ``(source_uid, target_uid, link_type)``.

    The current section is tracked from the leading number of each ``##``/``###``
    heading (see :data:`_MATRIX_SECTION_SPECS`); only markdown table rows
    (lines starting with ``|``) inside a recognised section are examined.

    Link source/target orientation and link type follow the SE endpoint
    semantics documented at module level. Cells marked ``—`` yield no uid token
    and are therefore skipped implicitly, as are placeholder ``...`` rows and
    column headers (the uid regexes require a trailing number).
    """
    triples: List[Tuple[str, str, str]] = []
    spec: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        heading = _MATRIX_HEADING_RE.match(line)
        if heading:
            spec = _MATRIX_SECTION_SPECS.get(heading.group(1))
            continue
        if spec is None or not line.startswith("|"):
            continue
        if spec == "L0_L1":
            source = _UID_L0_RE.search(line)
            if source:
                for target in _UID_L1_RE.findall(line):
                    triples.append((target, source.group(0), _LINK_DERIVES_FROM))
        elif spec == "L1_L2":
            source = _UID_L1_RE.search(line)
            if source:
                for target in _UID_L2_RE.findall(line):
                    triples.append((target, source.group(0), _LINK_DERIVES_FROM))
        elif spec == "L2_COMP":
            source = _UID_L2_RE.search(line)
            if source:
                for component in _UID_COMP_RE.findall(line):
                    triples.append((component, source.group(0), _LINK_IMPLEMENTS))
    return triples


def _uid_artifact_index(workspace_id) -> Dict[str, object]:
    """Return a ``{uid: artifact_id}`` map over all four imported entity types.

    Used by the trace-link pass to resolve a matrix uid to the backing Artifact
    id that :class:`TraceLinkService` links. Must run inside an active tenant
    context. On the (source-data) chance that a uid is reused across entity
    types, the first occurrence wins.
    """
    index: Dict[str, object] = {}

    def _add(pairs) -> None:
        for uid, artifact_id in pairs:
            if uid and artifact_id and uid not in index:
                index[uid] = artifact_id

    _add(
        StakeholderNeed.objects.filter(artifact__workspace_id=workspace_id)
        .exclude(uid__isnull=True)
        .exclude(uid="")
        .values_list("uid", "artifact_id")
    )
    _add(
        Requirement.objects.filter(artifact__workspace_id=workspace_id)
        .exclude(uid__isnull=True)
        .exclude(uid="")
        .values_list("uid", "artifact_id")
    )
    _add(
        ArchitectureElement.objects.filter(artifact__workspace_id=workspace_id)
        .exclude(uid__isnull=True)
        .exclude(uid="")
        .values_list("uid", "artifact_id")
    )
    _add(
        Adr.objects.filter(workspace_id=workspace_id)
        .exclude(uid__isnull=True)
        .exclude(uid="")
        .exclude(artifact_id__isnull=True)
        .values_list("uid", "artifact_id")
    )
    return index


class Command(BaseCommand):
    """Import docs/se/ into a ReqFlow workspace via ImportService (COMP-AS-009)."""

    help = "Idempotently import docs/se/ (SE requirements register) into a ReqFlow workspace."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--docs-root",
            dest="docs_root",
            default=None,
            help="Path to docs/se (default: <BASE_DIR>/docs/se, i.e. /app/docs/se in the container).",
        )
        parser.add_argument(
            "--workspace-id",
            dest="workspace_id",
            default=_DEFAULT_WORKSPACE_ID,
            help="Target workspace UUID (default: the seed_demo.py demo workspace).",
        )
        parser.add_argument(
            "--username",
            dest="username",
            default=_DEFAULT_USERNAME,
            help="Actor username for the synthetic AuthContext (default: 'admin').",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Parse and classify only; report counts without writing anything.",
        )
        parser.add_argument(
            "--format",
            dest="format",
            choices=["docs", "table"],
            default="docs",
            help=(
                "'docs' (default): walk --docs-root's '### REQ-Lx-...' heading "
                "documents. 'table' (issue #117): parse a single markdown-table "
                "file (e.g. docs/REQUIREMENTS.md) into Requirement rows instead."
            ),
        )
        parser.add_argument(
            "--file",
            dest="file",
            default=None,
            help=(
                "--format=table only: path to the markdown-table file "
                "(default: <BASE_DIR>/docs/REQUIREMENTS.md)."
            ),
        )

    def handle(self, *args, **options) -> None:
        if options["format"] == "table":
            self._handle_table_import(options)
            return

        docs_root = (
            Path(options["docs_root"])
            if options.get("docs_root")
            else Path(settings.BASE_DIR) / "docs" / "se"
        )
        dry_run: bool = options["dry_run"]

        if not docs_root.is_dir():
            raise CommandError(f"docs-root not found or not a directory: {docs_root}")

        workspace, ctx = self._resolve_workspace_and_ctx(options)

        all_files = sorted(docs_root.rglob("*.md"))
        self.stdout.write(f"Scanning {len(all_files)} markdown files under {docs_root} ...")

        buckets: Dict[str, List[Tuple[str, Dict[str, str], Path]]] = {
            "StakeholderNeed": [],
            "Requirement": [],
            "ArchitectureElement": [],
            "Adr": [],
        }
        unmapped: List[Tuple[Path, str]] = []
        parse_warnings: List[str] = []
        # (uid, element_type, path) for the Feature 1 parent-resolution pass.
        arch_files: List[Tuple[str, str, Path]] = []

        for path in all_files:
            # traceability-matrix.md is consumed by the Feature 2 trace-link
            # pass below, not by the entity-type classification — so it is
            # neither imported as an entity nor reported as UNMAPPED here.
            if path.name == _TRACE_MATRIX_FILENAME:
                continue
            bucket = _classify_file(path, docs_root)
            if bucket == "StakeholderNeed":
                rows, warns = _parse_stakeholder_need_file(path)
                parse_warnings.extend(warns)
                buckets["StakeholderNeed"].extend((uid, row, path) for uid, row in rows)
            elif bucket == "Requirement":
                rows, warns = _parse_requirement_file(path)
                parse_warnings.extend(warns)
                buckets["Requirement"].extend((uid, row, path) for uid, row in rows)
            elif bucket == "ArchitectureElement":
                warns: List[str] = []
                uid, row = _parse_architecture_file(path, warns)
                parse_warnings.extend(warns)
                buckets["ArchitectureElement"].append((uid, row, path))
                arch_files.append((uid, row["element_type"], path))
            elif bucket == "Adr":
                warns = []
                parsed = _parse_adr_file(path, warns)
                parse_warnings.extend(warns)
                if parsed is not None:
                    uid, row = parsed
                    buckets["Adr"].append((uid, row, path))
            else:
                unmapped.append((path, _unmapped_reason(path)))

        # ---------- Intra-run duplicate-uid resolution (first occurrence wins) ----------
        # docs/se has a handful of genuine ID-reuse cases in the source
        # (e.g. REQ-L1-085 used for two different requirements, REQ-L2-AT-017
        # restated with a "(vollstaendig)" annotation later in the same file).
        # These are source-data issues, not something this command silently
        # "fixes" — the first occurrence (deterministic file/heading order)
        # wins and every later duplicate is reported.
        dedup_warnings: List[str] = []
        deduped_buckets: Dict[str, List[Tuple[str, Dict[str, str]]]] = {}
        for entity_type, entries in buckets.items():
            seen: Dict[str, Path] = {}
            deduped: List[Tuple[str, Dict[str, str]]] = []
            for uid, row, path in entries:
                if uid in seen:
                    dedup_warnings.append(
                        f"{entity_type} uid '{uid}' also found in {path} "
                        f"(first occurrence from {seen[uid]} wins); duplicate skipped."
                    )
                    continue
                seen[uid] = path
                deduped.append((uid, row))
            deduped_buckets[entity_type] = deduped

        # Deduplicate the architecture-file list (first occurrence per uid wins,
        # mirroring the bucket dedup) for the Feature 1 parent-resolution pass.
        seen_arch_uids: set = set()
        arch_entries: List[Tuple[str, str, Path]] = []
        for uid, element_type, path in arch_files:
            if uid in seen_arch_uids:
                continue
            seen_arch_uids.add(uid)
            arch_entries.append((uid, element_type, path))

        # ---------- Idempotency filter + import ----------
        stats: Dict[str, Dict[str, int]] = {}
        set_request_tenant(workspace.tenant_id)
        try:
            for entity_type, entries in deduped_buckets.items():
                existing = _existing_uids(entity_type, workspace.id)
                new_rows = [row for uid, row in entries if uid not in existing]
                stats[entity_type] = {
                    "parsed": len(entries),
                    "already_imported": len(entries) - len(new_rows),
                    "new": len(new_rows),
                    "imported": 0,
                    "failed": 0,
                }

                if dry_run or not new_rows:
                    continue

                imported, failed = self._import_entity_rows(
                    ImportService(), entity_type, new_rows, workspace.id, ctx
                )
                stats[entity_type]["imported"] = imported
                stats[entity_type]["failed"] = failed

            # ---------- Feature 1: ArchitectureElement hierarchy (parent_id) ----------
            # Runs AFTER the CSV import so every ArchitectureElement exists.
            parent_stats, parent_warnings = self._apply_parents(
                arch_entries, workspace, ctx, dry_run
            )

            # ---------- Feature 2: trace links from traceability-matrix.md ----------
            # Runs last: source AND target artifacts of every link must already
            # be present across all four entity buckets.
            trace_stats, trace_warnings = self._apply_trace_links(
                docs_root, workspace, ctx, dry_run
            )
        finally:
            clear_request_tenant()

        self._report(
            stats,
            parse_warnings,
            dedup_warnings,
            unmapped,
            dry_run,
            parent_stats,
            parent_warnings,
            trace_stats,
            trace_warnings,
        )

    def _resolve_workspace_and_ctx(self, options) -> Tuple[Workspace, AuthContext]:
        """Resolve the target ``Workspace`` and build a synthetic admin ``AuthContext``.

        Shared by both ``--format=docs`` and ``--format=table``.
        """
        try:
            workspace = Workspace.unscoped.get(id=options["workspace_id"])
        except Workspace.DoesNotExist as exc:
            raise CommandError(f"Workspace {options['workspace_id']} does not exist.") from exc

        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError(
                f"User '{options['username']}' does not exist (run seed_demo first?)."
            ) from exc

        ctx = AuthContext(
            user_id=user.id,
            tenant_id=workspace.tenant_id,
            active_roles=(ROLE_ADMIN,),
            auth_method=AuthMethod.BEARER_TOKEN,
            tenant_name=getattr(workspace.tenant, "name", ""),
        )
        return workspace, ctx

    def _handle_table_import(self, options) -> None:
        """``--format=table`` entry point (issue #117).

        Parses a single markdown-table file (default: docs/REQUIREMENTS.md)
        into Requirement rows and imports them via the same
        ``ImportService.import_csv`` path as ``--format=docs``, so imported
        rows get the same workflow-state wiring (REQ-143 / issue #113)
        instead of landing as workflow-dead artifacts. Idempotent: rows whose
        ``uid`` (the REQ-ID) already exists in the target workspace are
        skipped, mirroring the docs/se ``--format=docs`` behaviour.
        """
        file_path = (
            Path(options["file"])
            if options.get("file")
            else Path(settings.BASE_DIR) / "docs" / "REQUIREMENTS.md"
        )
        dry_run: bool = options["dry_run"]

        if not file_path.is_file():
            raise CommandError(f"--file not found or not a file: {file_path}")

        workspace, ctx = self._resolve_workspace_and_ctx(options)

        self.stdout.write(f"Parsing requirement table rows from {file_path} ...")
        entries, parse_warnings = _parse_requirements_table_file(file_path)

        # First-occurrence-wins uid dedup, mirroring --format=docs.
        dedup_warnings: List[str] = []
        seen: Dict[str, bool] = {}
        deduped: List[Tuple[str, Dict[str, str]]] = []
        for uid, row in entries:
            if uid in seen:
                dedup_warnings.append(
                    f"Requirement uid '{uid}' found more than once in {file_path}; "
                    f"first occurrence wins, duplicate skipped."
                )
                continue
            seen[uid] = True
            deduped.append((uid, row))

        set_request_tenant(workspace.tenant_id)
        try:
            existing = _existing_uids("Requirement", workspace.id)
            new_rows = [row for uid, row in deduped if uid not in existing]
            stats = {
                "Requirement": {
                    "parsed": len(deduped),
                    "already_imported": len(deduped) - len(new_rows),
                    "new": len(new_rows),
                    "imported": 0,
                    "failed": 0,
                }
            }

            if not dry_run and new_rows:
                imported, failed = self._import_entity_rows(
                    ImportService(), "Requirement", new_rows, workspace.id, ctx
                )
                stats["Requirement"]["imported"] = imported
                stats["Requirement"]["failed"] = failed
        finally:
            clear_request_tenant()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Import summary (--format=table) ==="))
        s = stats["Requirement"]
        line = (
            f"  Requirement: parsed={s['parsed']} "
            f"already_imported={s['already_imported']} new={s['new']}"
        )
        if not dry_run:
            line += f" imported={s['imported']} failed={s['failed']}"
        self.stdout.write(line)

        all_warnings = parse_warnings + dedup_warnings
        if all_warnings:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"WARNINGS ({len(all_warnings)}):"))
            for w in all_warnings:
                self.stdout.write(self.style.WARNING(f"  - {w}"))
                logger.warning("migrate_se_docs --format=table: %s", w)

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.NOTICE("Dry-run: no data was written."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))

    def _import_entity_rows(
        self,
        importer: ImportService,
        entity_type: str,
        rows: List[Dict[str, str]],
        workspace_id,
        ctx: AuthContext,
    ) -> Tuple[int, int]:
        """Import *rows* for *entity_type* in chunks of _MAX_ROWS_PER_CALL.

        Returns (imported_count, failed_count).
        """
        imported = 0
        failed = 0
        for start in range(0, len(rows), _MAX_ROWS_PER_CALL):
            chunk = rows[start : start + _MAX_ROWS_PER_CALL]
            csv_text = _write_csv(chunk, entity_type)
            result = importer.import_csv(csv_text, entity_type, workspace_id, ctx)
            if result.success:
                imported += result.imported_count
            else:
                failed += len(chunk)
                error_preview = [
                    f"row {e.row_number} [{e.field}]: {e.message}" for e in result.errors[:5]
                ]
                self.stderr.write(
                    self.style.ERROR(
                        f"  ! {entity_type} import chunk failed "
                        f"(status={result.status}): {error_preview}"
                    )
                )
                logger.error(
                    "migrate_se_docs: %s import chunk failed status=%s errors=%s",
                    entity_type,
                    result.status,
                    error_preview,
                )
        return imported, failed

    def _apply_parents(
        self,
        arch_entries: List[Tuple[str, str, Path]],
        workspace,
        ctx: AuthContext,
        dry_run: bool,
    ) -> Tuple[Dict[str, int], List[str]]:
        """Feature 1: write ArchitectureElement.parent_id from folder structure.

        Writes ``parent_id`` via a direct, idempotency-guarded ORM update — a
        deliberate choice for this one-shot migration batch job, NOT a regular
        write path. See the module-level Feature 1 note for the full rationale:
        the ArchitectureService invariant I2 compares the elements' *current*
        tree depth and therefore rejects the first re-parent of two freshly
        imported level-0 elements, so the domain service cannot construct a
        hierarchy from a flat import. The write is skipped when ``parent_id``
        already matches, so a repeated run performs no writes.

        Must run inside an active tenant context. Returns ``(stats, warnings)``.
        """
        parent_of, warnings = _resolve_architecture_parents(arch_entries)
        stats = {"with_parent": 0, "already_set": 0, "assigned": 0, "unresolved": 0}

        elements = {
            el.uid: el
            for el in ArchitectureElement.objects.filter(
                artifact__workspace_id=workspace.id
            )
            .exclude(uid__isnull=True)
            .exclude(uid="")
        }

        for uid, parent_uid in parent_of.items():
            if parent_uid is None:
                continue
            stats["with_parent"] += 1
            element = elements.get(uid)
            parent = elements.get(parent_uid)
            if element is None or parent is None:
                stats["unresolved"] += 1
                missing = uid if element is None else parent_uid
                warnings.append(
                    f"parent link {uid} -> {parent_uid}: '{missing}' not found "
                    f"among imported ArchitectureElements; skipped."
                )
                continue
            if element.parent_id == parent.id:
                stats["already_set"] += 1
                continue
            if dry_run:
                continue
            # Direct ORM update (batch migration only — see module note). A bare
            # .update() avoids version churn and domain events, keeping reruns
            # side-effect free.
            ArchitectureElement.objects.filter(id=element.id).update(
                parent_id=parent.id
            )
            element.parent_id = parent.id  # keep the local cache consistent
            stats["assigned"] += 1
        return stats, warnings

    def _apply_trace_links(
        self,
        docs_root: Path,
        workspace,
        ctx: AuthContext,
        dry_run: bool,
    ) -> Tuple[Dict[str, int], List[str]]:
        """Feature 2: create TraceLinks from ``traceability-matrix.md``.

        Uses :meth:`TraceLinkService.create_trace_link` — the regular,
        event-emitting creation path (analogous to ImportService for the four
        entity buckets) — and skips any triple that already exists
        (idempotency). Unresolvable uids are reported as warnings, never fatal.

        Must run inside an active tenant context. Returns ``(stats, warnings)``.
        """
        warnings: List[str] = []
        stats = {
            "parsed": 0,
            "resolved": 0,
            "already_linked": 0,
            "new": 0,
            "created": 0,
            "failed": 0,
            "unresolved": 0,
        }

        matrix_path = docs_root / _TRACE_MATRIX_FILENAME
        if not matrix_path.is_file():
            warnings.append(
                f"{matrix_path}: traceability matrix not found; "
                f"no trace links imported."
            )
            return stats, warnings

        triples = _parse_trace_matrix(matrix_path.read_text(encoding="utf-8"))
        # Intra-run dedup (identical source/target/type tuples collapse to one).
        seen: set = set()
        deduped: List[Tuple[str, str, str]] = []
        for triple in triples:
            if triple in seen:
                continue
            seen.add(triple)
            deduped.append(triple)
        stats["parsed"] = len(deduped)

        index = _uid_artifact_index(workspace.id)
        service = None
        for source_uid, target_uid, link_type in deduped:
            source_id = index.get(source_uid)
            target_id = index.get(target_uid)
            if source_id is None or target_id is None:
                stats["unresolved"] += 1
                missing = [
                    u
                    for u, resolved in ((source_uid, source_id), (target_uid, target_id))
                    if resolved is None
                ]
                warnings.append(
                    f"trace-link {source_uid} --{link_type}--> {target_uid}: "
                    f"unresolved uid(s) {missing}; skipped."
                )
                continue
            stats["resolved"] += 1
            if TraceLink.objects.filter(
                source_id=source_id, target_id=target_id, link_type=link_type
            ).exists():
                stats["already_linked"] += 1
                continue
            stats["new"] += 1
            if dry_run:
                continue
            try:
                if service is None:
                    from application.trace_link_service import TraceLinkService

                    service = TraceLinkService()
                service.create_trace_link(
                    source_id=source_id,
                    target_id=target_id,
                    link_type=link_type,
                    ctx=ctx,
                )
                stats["created"] += 1
            except Exception as exc:  # noqa: BLE001 — report, never abort the batch
                stats["failed"] += 1
                warnings.append(
                    f"trace-link {source_uid} --{link_type}--> {target_uid}: "
                    f"creation failed ({exc}); skipped."
                )
        return stats, warnings

    def _report(
        self,
        stats: Dict[str, Dict[str, int]],
        parse_warnings: List[str],
        dedup_warnings: List[str],
        unmapped: List[Tuple[Path, str]],
        dry_run: bool,
        parent_stats: Dict[str, int],
        parent_warnings: List[str],
        trace_stats: Dict[str, int],
        trace_warnings: List[str],
    ) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Import summary ==="))
        for entity_type, s in stats.items():
            line = (
                f"  {entity_type}: parsed={s['parsed']} "
                f"already_imported={s['already_imported']} new={s['new']}"
            )
            if not dry_run:
                line += f" imported={s['imported']} failed={s['failed']}"
            self.stdout.write(line)

        # ---------- Feature 1: ArchitectureElement hierarchy ----------
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("=== ArchitectureElement hierarchy (parent_id) ===")
        )
        ps = parent_stats
        parent_line = (
            f"  parents: with_parent={ps['with_parent']} "
            f"already_set={ps['already_set']} unresolved={ps['unresolved']}"
        )
        if dry_run:
            would = ps["with_parent"] - ps["already_set"] - ps["unresolved"]
            parent_line += f" would_assign={would}"
        else:
            parent_line += f" assigned={ps['assigned']}"
        self.stdout.write(parent_line)

        # ---------- Feature 2: trace links ----------
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("=== Trace links (traceability-matrix.md) ===")
        )
        ts = trace_stats
        trace_line = (
            f"  trace_links: parsed={ts['parsed']} resolved={ts['resolved']} "
            f"already_linked={ts['already_linked']} unresolved={ts['unresolved']} "
            f"new={ts['new']}"
        )
        if not dry_run:
            trace_line += f" created={ts['created']} failed={ts['failed']}"
        self.stdout.write(trace_line)

        all_warnings = (
            parse_warnings + dedup_warnings + parent_warnings + trace_warnings
        )
        if all_warnings:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"WARNINGS ({len(all_warnings)}):"))
            for w in all_warnings:
                self.stdout.write(self.style.WARNING(f"  - {w}"))
                logger.warning("migrate_se_docs: %s", w)

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                f"UNMAPPED documents ({len(unmapped)}) — no entity-type mapping, not imported:"
            )
        )
        for path, reason in unmapped:
            msg = f"{path}: {reason}"
            self.stdout.write(self.style.WARNING(f"  - {msg}"))
            logger.warning("migrate_se_docs UNMAPPED: %s", msg)

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.NOTICE("Dry-run: no data was written."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
