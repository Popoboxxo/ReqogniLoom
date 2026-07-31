"""
Tests for GET /api/v1/version/ — deployed build/commit metadata.

Covers the env-var-first, git-fallback resolution order in
``reqogniloom.version._resolve_commit_sha``. The git fallback is mocked so the
suite never depends on the actual repo's ``.git`` state (a CI/build
container legitimately ships without one).

#74: the public response intentionally does NOT include the full commit SHA
or the build timestamp (both would let an unauthenticated caller pinpoint the
exact deployed revision / build time). Only ``app_version`` and the
truncated ``commit_short`` are public.
"""
from __future__ import annotations

from unittest.mock import patch

from rest_framework.test import APIClient


def _get_version():
    """GET /api/v1/version/ with a fresh, unauthenticated client."""
    return APIClient().get("/api/v1/version/")


class TestVersionEndpoint:
    """GET /api/v1/version/ is public and exposes minimal build metadata."""

    def test_no_auth_required(self) -> None:
        """The endpoint responds 200 without any credentials (AllowAny)."""
        resp = _get_version()
        assert resp.status_code == 200

    def test_full_commit_and_build_time_never_exposed(self, monkeypatch) -> None:
        """#74: the full commit SHA and build timestamp must never leak."""
        monkeypatch.setenv("GIT_COMMIT_SHA", "a1b2c3d4e5f6789")
        monkeypatch.setenv("BUILD_TIME", "2026-07-16T12:00:00Z")

        body = _get_version().json()

        assert "commit" not in body
        assert "build_time" not in body
        assert body["commit_short"] == "a1b2c3d"

    def test_env_absent_and_git_unavailable_returns_unknown(self, monkeypatch) -> None:
        """No env var + no usable .git -> commit_short = 'unknown'."""
        monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)
        monkeypatch.delenv("BUILD_TIME", raising=False)

        with patch(
            "reqogniloom.version.subprocess.run",
            side_effect=FileNotFoundError("git not installed"),
        ):
            resp = _get_version()

        body = resp.json()
        assert body["commit_short"] == "unknown"

    def test_env_absent_but_git_available_uses_git_sha(self, monkeypatch) -> None:
        """No env var, but `git rev-parse HEAD` succeeds -> truncated to 7 chars."""
        monkeypatch.delenv("GIT_COMMIT_SHA", raising=False)

        fake_result = type(
            "FakeCompletedProcess", (), {"stdout": "deadbeefcafef00d1234\n"}
        )()
        with patch("reqogniloom.version.subprocess.run", return_value=fake_result):
            resp = _get_version()

        body = resp.json()
        assert body["commit_short"] == "deadbee"


class TestAppVersion:
    """`app_version` resolution: APP_VERSION env -> root VERSION file -> 'unknown'."""

    def test_app_version_env_var_present(self, monkeypatch) -> None:
        """APP_VERSION env var is used verbatim (authoritative for a built image)."""
        monkeypatch.setenv("APP_VERSION", "1.2.3")

        body = _get_version().json()

        assert body["app_version"] == "1.2.3"

    def test_app_version_from_file_when_env_absent(self, monkeypatch) -> None:
        """No APP_VERSION env var -> read the root VERSION file (dev fallback)."""
        monkeypatch.delenv("APP_VERSION", raising=False)

        with patch("reqogniloom.version.Path.read_text", return_value="0.2.0\n"):
            body = _get_version().json()

        assert body["app_version"] == "0.2.0"

    def test_app_version_missing_file_falls_back_to_unknown(self, monkeypatch) -> None:
        """No env var + no VERSION file -> 'unknown', endpoint stays 200."""
        monkeypatch.delenv("APP_VERSION", raising=False)

        with patch(
            "reqogniloom.version.Path.read_text",
            side_effect=FileNotFoundError("no VERSION file"),
        ):
            resp = _get_version()

        assert resp.status_code == 200
        assert resp.json()["app_version"] == "unknown"
