"""
Tests for GET /api/v1/version/ — deployed build/commit metadata.

Covers the env-var-first, git-fallback resolution order in
``reqflow.version._resolve_commit_sha``. The git fallback is mocked so the
suite never depends on the actual repo's ``.git`` state (a CI/build
container legitimately ships without one).
"""
from __future__ import annotations

from unittest.mock import patch

from rest_framework.test import APIClient


def _get_version():
    """GET /api/v1/version/ with a fresh, unauthenticated client."""
    return APIClient().get("/api/v1/version/")


class TestVersionEndpoint:
    """GET /api/v1/version/ is public and exposes build metadata."""

    def test_no_auth_required(self) -> None:
        """The endpoint responds 200 without any credentials (AllowAny)."""
        resp = _get_version()
        assert resp.status_code == 200

    def test_env_vars_present(self, monkeypatch) -> None:
        """GIT_COMMIT_SHA/BUILD_TIME env vars are echoed back verbatim/truncated."""
        monkeypatch.setenv("GIT_COMMIT_SHA", "a1b2c3d4e5f6789")
        monkeypatch.setenv("BUILD_TIME", "2026-07-16T12:00:00Z")

        resp = _get_version()

        body = resp.json()
        assert body["commit"] == "a1b2c3d4e5f6789"
        assert body["commit_short"] == "a1b2c3d"
        assert body["build_time"] == "2026-07-16T12:00:00Z"

    def test_env_absent_and_git_unavailable_returns_unknown(self, monkeypatch) -> None:
        """No env var + no usable .git -> commit/commit_short = 'unknown', build_time = null."""
        monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)
        monkeypatch.delenv("BUILD_TIME", raising=False)

        with patch(
            "reqflow.version.subprocess.run",
            side_effect=FileNotFoundError("git not installed"),
        ):
            resp = _get_version()

        body = resp.json()
        assert body["commit"] == "unknown"
        assert body["commit_short"] == "unknown"
        assert body["build_time"] is None

    def test_env_absent_but_git_available_uses_git_sha(self, monkeypatch) -> None:
        """No env var, but `git rev-parse HEAD` succeeds -> uses that SHA (dev fallback)."""
        monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)

        fake_result = type(
            "FakeCompletedProcess", (), {"stdout": "deadbeefcafef00d1234\n"}
        )()
        with patch("reqflow.version.subprocess.run", return_value=fake_result):
            resp = _get_version()

        body = resp.json()
        assert body["commit"] == "deadbeefcafef00d1234"
        assert body["commit_short"] == "deadbee"
