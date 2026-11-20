"""Guard that deploy and CI service images are pinned by manifest digest.

DEP-003 pins the first-party GHCR images referenced by the deploy Compose
files; DEP-009 pins the third-party service images used by CI and the TLS
example. A pinned reference keeps a human-readable tag but appends
``@sha256:<64 hex>`` so a registry tag move cannot silently change what runs.

This module intentionally checks the *format* of every pin (64 lowercase hex
digits). The concrete digest values are resolved from the registry and recorded
inline next to each image; the drift they guard against is a naked/moving tag,
not a specific build.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# A pin is a digest reference ending the image value (tag kept as a hint).
DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")

# Matches both ``image: value`` and list-style ``- image: value``.
IMAGE_LINE_RE = re.compile(r"^\s*(?:-\s*)?image:\s*(?P<value>.+?)\s*$")

FIRST_PARTY_PREFIX = "ghcr.io/popoboxxo/"

DEPLOY_COMPOSE_FILES = sorted(
    (REPO_ROOT / "deploy").glob("docker-compose*.yml")
)
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _image_values(path: Path) -> list[str]:
    """Return the normalised image value of every ``image:`` line in *path*."""
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = IMAGE_LINE_RE.match(line)
        if match is None:
            continue
        value = match.group("value").strip()
        # Drop a trailing YAML comment and optional surrounding quotes.
        value = value.split(" #", 1)[0].strip().strip("'\"")
        if value:
            values.append(value)
    return values


def _collect_matches(
    path: Path,
    predicate: Callable[[str], bool],
    errors: list[str],
) -> list[str]:
    """Collect image values matching *predicate*, recording unpinned ones."""
    matched: list[str] = []
    for value in _image_values(path):
        if not predicate(value):
            continue
        matched.append(value)
        if DIGEST_RE.search(value) is None:
            errors.append(
                f"{path.relative_to(REPO_ROOT)}: unpinned image {value!r}"
            )
    return matched


def test_first_party_images_are_digest_pinned() -> None:
    """Every first-party GHCR image in deploy/CI carries a 64-hex digest."""
    errors: list[str] = []
    matched: list[str] = []

    for path in [*DEPLOY_COMPOSE_FILES, CI_WORKFLOW]:
        matched.extend(
            _collect_matches(
                path, lambda value: FIRST_PARTY_PREFIX in value, errors
            )
        )

    assert not errors, (
        "First-party images missing @sha256 pins:\n" + "\n".join(errors)
    )
    # Guards against a vacuous pass if the file set or prefix ever changes.
    assert len(matched) >= 9, (
        f"expected >= 9 first-party refs, found {len(matched)}"
    )


@pytest.mark.parametrize(
    ("relative_path", "image_marker", "expected_min"),
    [
        (".github/workflows/ci.yml", "pgvector/pgvector:pg16", 2),
        (".github/workflows/ci.yml", "redis:7-alpine", 1),
        ("deploy/docker-compose.tls.example.yml", "caddy:2-alpine", 1),
    ],
)
def test_ci_and_example_images_are_digest_pinned(
    relative_path: str,
    image_marker: str,
    expected_min: int,
) -> None:
    """CI/example third-party service images carry a 64-hex digest."""
    path = REPO_ROOT / relative_path
    assert path.is_file(), f"missing {relative_path}"

    errors: list[str] = []
    matched = _collect_matches(
        path, lambda value: value.startswith(image_marker), errors
    )

    assert not errors, (
        f"{relative_path}: unpinned images:\n" + "\n".join(errors)
    )
    assert len(matched) >= expected_min, (
        f"expected >= {expected_min} refs for {image_marker}, "
        f"found {len(matched)}"
    )


def test_honcho_runtime_patch_is_wired_into_both_engine_services() -> None:
    """#1247: the upstream #1441 backport must be mounted AND executed.

    The pinned vendor image stays untouched; both `honcho` and `honcho-deriver`
    mount the patch read-only and their entrypoint shims execute it before
    ``src.config`` is imported. A missing mount or invocation silently restores
    the ``400 MissingSessionID`` dialectic regression.
    """
    compose = (REPO_ROOT / "deploy" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    patch = REPO_ROOT / "deploy" / "honcho-patch" / "apply_patch.py"
    assert patch.is_file(), f"missing runtime backport: {patch}"

    assert compose.count("./deploy/honcho-patch:/tmp/honcho-patch:ro") >= 2, (
        "both honcho and honcho-deriver must mount the patch directory"
    )
    assert compose.count('exec(compile(open(_patch).read(), _patch, "exec"))') >= 2, (
        "both entrypoint shims must execute the backport before importing config"
    )
    text = patch.read_text(encoding="utf-8")
    for anchor in (
        "def with_opencode_session_header(",
        "with_opencode_session_header(effective_config, telemetry)",
        "x-opencode-session",
        "already applied",
    ):
        assert anchor in text, f"patch script lost anchor {anchor!r}"
