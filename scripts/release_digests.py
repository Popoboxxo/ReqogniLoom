#!/usr/bin/env python3
"""Resolve/verify the GHCR manifest digests pinned in deploy/docker-compose.yml.

Run this **after** the release images are published and **before** the release
tag is created (see docs/DEPLOY_RUNBOOK.md):

    python3 scripts/release_digests.py resolve --version 1.9.0-beta.9
    python3 scripts/release_digests.py check   --version 1.9.0-beta.9

``resolve`` rewrites every first-party backend/frontend reference to
``ghcr.io/popoboxxo/reqogniloom-<name>:<version>@sha256:<manifest digest>``.
``check`` verifies that the tag equals VERSION and (when a registry lookup is
possible) that the digest matches the published manifest. This closes the
#2076 regression where a tag announced beta.8 while the pinned digest still
pointed at beta.2.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"
VERSION_FILE = REPO_ROOT / "VERSION"
FIRST_PARTY = ("backend", "frontend")
_REF = re.compile(
    r"(ghcr\.io/popoboxxo/reqogniloom-(?:backend|frontend))"
    r":([^@\s]+)"
    r"(@sha256:[0-9a-f]{64})?"
)


def manifest_digest(image: str) -> str:
    """Return the registry manifest digest for *image* (``sha256:...``).

    Uses ``docker manifest inspect`` (available anywhere Docker is); a release
    machine is expected to be logged in to GHCR.
    """
    result = subprocess.run(
        ["docker", "manifest", "inspect", image],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"cannot inspect {image}: {result.stderr.strip() or 'docker failed'}"
        )
    payload = json.loads(result.stdout or "{}")
    descriptor = payload.get("Descriptor") if isinstance(payload, dict) else None
    digest = (descriptor or {}).get("digest") or payload.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        # A multi-arch manifest list is an array; docker still reports the
        # top-level digest only with --verbose, which the caller may not use.
        raise RuntimeError(f"no manifest digest in `docker manifest inspect {image}`")
    return digest


def resolve(text: str, version: str, digest_for=manifest_digest) -> str:
    """Rewrite every first-party image reference to *version* + its digest."""

    def _replace(match: re.Match[str]) -> str:
        repo, _tag, _digest = match.group(1), match.group(2), match.group(3)
        return f"{repo}:{version}@{digest_for(f'{repo}:{version}')}"

    return _REF.sub(_replace, text)


def check(text: str, version: str, digest_for=manifest_digest, *, registry: bool = True) -> list[str]:
    """Return a list of problems; an empty list means the pins are consistent."""
    problems: list[str] = []
    for match in _REF.finditer(text):
        repo, tag, digest = match.group(1), match.group(2), match.group(3)
        if tag != version:
            problems.append(f"{repo} is tagged {tag!r}, expected {version!r}")
        if digest is None:
            problems.append(f"{repo}:{tag} has no @sha256 digest")
        elif registry:
            try:
                expected = digest_for(f"{repo}:{version}")
            except Exception as exc:  # noqa: BLE001 — reported, not raised
                problems.append(f"{repo}:{version}: cannot verify digest ({exc})")
            else:
                if digest != f"@{expected}":
                    problems.append(
                        f"{repo}:{version} pins {digest}, registry manifest is {expected}"
                    )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("resolve", "check"))
    parser.add_argument("--version", default=VERSION_FILE.read_text().strip())
    parser.add_argument("--file", type=Path, default=COMPOSE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    text = args.file.read_text(encoding="utf-8")
    if args.action == "resolve":
        updated = resolve(text, args.version)
        if args.dry_run:
            print(updated)
            return 0
        args.file.write_text(updated, encoding="utf-8")
        print(f"updated {args.file.relative_to(REPO_ROOT)} for {args.version}")
        return 0

    problems = check(text, args.version)
    for problem in problems:
        print(f"ERROR {problem}")
    if problems:
        return 1
    print(f"OK: first-party digests match {args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
