"""Unit tests for scripts/release_digests.py (#2076)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "release_digests", Path(__file__).with_name("release_digests.py")
)
release_digests = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_digests)

DIGEST = "sha256:" + "a" * 64
COMPOSE = f"""
services:
  backend:
    image: ghcr.io/popoboxxo/reqogniloom-backend:1.9.0-beta.8@sha256:{'b' * 64}
  frontend:
    image: ghcr.io/popoboxxo/reqogniloom-frontend:1.9.0-beta.8@sha256:{'c' * 64}
"""


def test_resolve_rewrites_tag_and_digest() -> None:
    calls: list[str] = []

    def digest_for(image: str) -> str:
        calls.append(image)
        return DIGEST

    updated = release_digests.resolve(COMPOSE, "1.9.0-beta.9", digest_for)

    assert "reqogniloom-backend:1.9.0-beta.9@" + DIGEST in updated
    assert "reqogniloom-frontend:1.9.0-beta.9@" + DIGEST in updated
    assert "1.9.0-beta.8" not in updated
    assert calls == [
        "ghcr.io/popoboxxo/reqogniloom-backend:1.9.0-beta.9",
        "ghcr.io/popoboxxo/reqogniloom-frontend:1.9.0-beta.9",
    ]


def test_check_reports_a_tag_that_does_not_match_version() -> None:
    problems = release_digests.check(
        COMPOSE, "1.9.0-beta.9", lambda image: DIGEST, registry=False
    )
    assert any("tagged '1.9.0-beta.8'" in problem for problem in problems)


def test_check_reports_a_stale_digest() -> None:
    def digest_for(image: str) -> str:
        return DIGEST

    text = COMPOSE.replace("1.9.0-beta.8", "1.9.0-beta.9")
    problems = release_digests.check(text, "1.9.0-beta.9", digest_for)
    assert any("registry manifest is" in problem for problem in problems)


def test_check_accepts_a_fully_consistent_pin() -> None:
    text = release_digests.resolve(COMPOSE, "1.9.0-beta.9", lambda image: DIGEST)
    assert release_digests.check(text, "1.9.0-beta.9", lambda image: DIGEST) == []
