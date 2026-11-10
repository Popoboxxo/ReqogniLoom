#!/usr/bin/env python3
"""Check that repo paths named in an implementation plan still exist.

Plans under ``docs/superpowers/plans/`` name files by path. Code moves on, so a
plan can silently refer to something that was removed (e.g. a deleted module).
Run this before starting a phase::

    python scripts/check_plan_refs.py docs/superpowers/plans/<plan>.md [--root .]

Only backticked paths that start with a known top-level directory are checked.
Lines that declare new files (``- Create:``, ``- Test:``, ``- Generated``) and
paths marked as scratch (``.tmp/``) are skipped. Exit code 1 lists the missing
paths, 0 means every referenced path exists.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: Top-level directories whose paths are checked.
TOP_LEVEL = (
    "backend", "frontend", "docs", "scripts", "integrations", "dist",
    ".github", "e2e", "deploy", "testing", "promptfoo",
)
#: Lines that name files the plan itself creates or that tooling generates.
_SKIP_LINE = re.compile(r"^\s*-\s*(Create|Test|Generated)\b")
_PATH = re.compile(r"`((?:%s)/[A-Za-z0-9_./\-]+)(?::\d+(?:-\d+)?)?`" % "|".join(map(re.escape, TOP_LEVEL)))


def referenced_paths(text: str) -> list[str]:
    """Return the checkable paths in *text*, in order, without duplicates."""
    seen: dict[str, None] = {}
    for line in text.splitlines():
        if _SKIP_LINE.match(line):
            continue
        for match in _PATH.finditer(line):
            path = match.group(1)
            if "<" in path or "*" in path or path.endswith("/"):
                continue
            seen.setdefault(path)
    return list(seen)


def missing_paths(text: str, root: Path) -> list[str]:
    """Return the referenced paths that do not exist below *root*."""
    return [p for p in referenced_paths(text) if not (root / p).exists()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    missing = missing_paths(args.plan.read_text(encoding="utf-8"), args.root)
    for path in missing:
        print(f"MISSING {path}")
    if missing:
        print(f"{len(missing)} path(s) in {args.plan} do not exist below {args.root}", file=sys.stderr)
        return 1
    print(f"ok: all referenced paths in {args.plan} exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
