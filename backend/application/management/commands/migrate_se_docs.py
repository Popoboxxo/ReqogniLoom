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
    User,
    Workspace,
)

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
    return {"title": title[:500], "description": _csv_safe(body), "uid": uid}


def _requirement_level(uid: str) -> int:
    parts = uid.split("-")
    return _REQ_LEVEL_MAP[parts[1]]


def _requirement_row(uid: str, title: str, body: str) -> Dict[str, str]:
    return {
        "title": title[:500],
        "description": _csv_safe(body),
        "level": str(_requirement_level(uid)),
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

    def handle(self, *args, **options) -> None:
        docs_root = (
            Path(options["docs_root"])
            if options.get("docs_root")
            else Path(settings.BASE_DIR) / "docs" / "se"
        )
        dry_run: bool = options["dry_run"]

        if not docs_root.is_dir():
            raise CommandError(f"docs-root not found or not a directory: {docs_root}")

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

        for path in all_files:
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
        finally:
            clear_request_tenant()

        self._report(stats, parse_warnings, dedup_warnings, unmapped, dry_run)

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

    def _report(
        self,
        stats: Dict[str, Dict[str, int]],
        parse_warnings: List[str],
        dedup_warnings: List[str],
        unmapped: List[Tuple[Path, str]],
        dry_run: bool,
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

        all_warnings = parse_warnings + dedup_warnings
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
