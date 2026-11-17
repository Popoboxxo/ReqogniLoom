#!/usr/bin/env python3
"""Idempotent migration helper for minimal YAML frontmatter on SE documents.

Every ``docs/se/**/*.md`` file that lacks a leading ``---`` frontmatter block
receives the normative minimal keys (``type``, ``scope``, ``status``, ``date``,
``author_agent``). Requirement files additionally receive ``open_adrs: []``.
Existing frontmatter is never rewritten; for requirement files only the single
``open_adrs: []`` line is inserted when it is missing.

Scope guards:

* ``docs/se/ADR/**`` is excluded entirely (owned by the ADR workstream).
* The seven S6.1 ``REQ-L2-RF-209..215`` files never receive a generated
  frontmatter block (they already carry a hand-written one); they only receive
  the ``open_adrs: []`` key required by the AGENTS.md REQ rule.
* Bodies are preserved byte-for-byte; only frontmatter is prepended/inserted.

Re-running the helper is a no-op.

Usage::

    python3 scripts/add_se_frontmatter.py [--root docs/se] [--dry-run] [--check]
"""
from __future__ import annotations

import argparse
import codecs
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

BOM = codecs.BOM_UTF8
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "docs" / "se"
FALLBACK_DATE = "2026-11-17"
AUTHOR_AGENT = "se-migration"
EXCLUDED_TOP_DIRS = frozenset({"ADR"})
S61_PREFIXES = tuple(f"REQ-L2-RF-{number}_" for number in range(209, 216))
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
OPEN_ADRS_RE = re.compile(r"^\s*open_adrs\s*:", re.MULTILINE)


@dataclass
class MigrationResult:
    """Counters collected during one migration run."""

    scanned: int = 0
    frontmatter_added: list[Path] = field(default_factory=list)
    open_adrs_added: list[Path] = field(default_factory=list)
    excluded: list[Path] = field(default_factory=list)

    @property
    def changed(self) -> int:
        """Return the number of files modified in this run."""
        return len(self.frontmatter_added) + len(self.open_adrs_added)


def read_text(path: Path) -> str:
    """Read a file as UTF-8 with any leading BOM stripped."""
    raw = path.read_bytes()
    if raw.startswith(BOM):
        raw = raw[len(BOM) :]
    return raw.decode("utf-8")


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text verbatim (a stripped BOM is never re-added)."""
    path.write_bytes(text.encode("utf-8"))


def newline_of(text: str) -> str:
    """Return the dominant newline sequence of ``text``."""
    return "\r\n" if "\r\n" in text else "\n"


def frontmatter_block(text: str) -> list[str] | None:
    """Return the leading frontmatter lines (fences included), or ``None``."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n").strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n").strip() == "---":
            return lines[: index + 1]
    return None


def is_req_name(name: str) -> bool:
    """Return whether a filename identifies a requirement document."""
    lowered = name.lower()
    return (
        lowered.endswith("_requirements.md")
        or lowered == "requirements.md"
        or lowered.startswith("req-")
        or lowered.startswith("sn_")
        or "anforderungen" in lowered
        or "stakeholder" in lowered
    )


def in_l01(relative_path: Path) -> bool:
    """Return whether a repository-relative path lives under ``L0/`` or ``L1/``."""
    return bool(relative_path.parts) and relative_path.parts[0] in {"L0", "L1"}


def derive_type(relative_path: Path) -> str:
    """Derive the SE document type from the path and filename."""
    name = relative_path.name.lower()
    parts = {part.lower() for part in relative_path.parts}

    if "adr" in parts:
        return "ADR"
    if "reviews" in parts or "review" in name or "critic" in name:
        return "REVIEW"
    if is_req_name(relative_path.name):
        return "REQ"
    if "architecture" in name or name.endswith("_arch.md"):
        return "ARCH"
    if (
        name.endswith("_testmodel.md")
        or name.startswith("testplan")
        or "verification" in name
        or "validation" in name
        or "vv" in parts
        or name.startswith("vv_")
    ):
        return "VV-DOC"
    if "traceab" in name:
        return "TRACE"
    if "strateg" in name:
        return "STRATEGY"
    # Audits, reports, analyses and registries have no dedicated SE type;
    # STRATEGY is the conservative informational bucket from the AGENTS.md enum.
    return "STRATEGY"


def derive_scope(path: Path) -> str:
    """Derive a lowercase, slugified scope from the document's cell filename."""
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
    return slug or "se"


def derive_date(path: Path, text: str) -> str:
    """Prefer an ISO date in the body, then the file mtime, then the fallback."""
    match = DATE_RE.search("\n".join(text.splitlines()[:60]))
    if match:
        return match.group(1)
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    except OSError:
        return FALLBACK_DATE


def build_frontmatter(path: Path, text: str, *, newline: str) -> str:
    """Build the minimal frontmatter block (including fences) for ``path``."""
    fields = [
        f"type: {derive_type(path)}",
        f"scope: {derive_scope(path)}",
        "status: draft",
        f"date: {derive_date(path, text)}",
        f"author_agent: {AUTHOR_AGENT}",
    ]
    if is_req_name(path.name):
        fields.append("open_adrs: []")
    return "---" + newline + newline.join(fields) + newline + "---" + newline


def insert_open_adrs(text: str, *, newline: str) -> str | None:
    """Insert ``open_adrs: []`` into an existing frontmatter block.

    Returns ``None`` when no insertion was needed (no frontmatter or key already
    present). All other bytes of ``text`` are preserved exactly.
    """
    lines = frontmatter_block(text)
    if lines is None:
        return None
    if OPEN_ADRS_RE.search("".join(lines)):
        return None
    prefix = "".join(lines)
    closing = len(lines) - 1
    new_prefix = (
        "".join(lines[:closing])
        + f"open_adrs: []{newline}"
        + "".join(lines[closing:])
    )
    return new_prefix + text[len(prefix) :]


def is_s61(name: str) -> bool:
    """Return whether ``name`` is one of the seven hand-written S6.1 REQ docs."""
    return any(name.startswith(prefix) for prefix in S61_PREFIXES)


def is_excluded(relative_path: Path) -> bool:
    """Return whether the file is owned by another workstream."""
    return bool(relative_path.parts) and relative_path.parts[0] in EXCLUDED_TOP_DIRS


def migrate(root: Path, *, dry_run: bool = False) -> MigrationResult:
    """Apply the idempotent frontmatter migration below ``root``.

    ``root`` is the SE documents directory (``docs/se`` by default). The
    function is public so the guard test can exercise idempotence on a temp copy.
    """
    result = MigrationResult()
    if not root.is_dir():
        return result

    for path in sorted(root.rglob("*.md")):
        relative_path = path.relative_to(root)
        result.scanned += 1
        if is_excluded(relative_path):
            result.excluded.append(path)
            continue

        text = read_text(path)
        newline = newline_of(text)
        block = frontmatter_block(text)

        if block is None:
            if is_s61(path.name):
                result.excluded.append(path)
                continue
            new_text = build_frontmatter(relative_path, text, newline=newline) + text
            if not dry_run:
                write_text(path, new_text)
            result.frontmatter_added.append(path)
            continue

        if is_req_name(path.name) and in_l01(relative_path):
            new_text = insert_open_adrs(text, newline=newline)
            if new_text is not None:
                if not dry_run:
                    write_text(path, new_text)
                result.open_adrs_added.append(path)

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="SE documents directory (default: %(default)s)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any change would be made (no writes)",
    )
    args = parser.parse_args(argv)

    dry_run = args.dry_run or args.check
    result = migrate(args.root, dry_run=dry_run)
    print(
        f"scanned={result.scanned} frontmatter_added={len(result.frontmatter_added)} "
        f"open_adrs_added={len(result.open_adrs_added)} excluded={len(result.excluded)}"
    )
    if args.check and result.changed:
        print("check failed: migration would modify files", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
