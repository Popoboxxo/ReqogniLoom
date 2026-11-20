"""Regression tests for the weak-secret gate (audit finding #2).

Security audit finding #2 (MEDIUM, CWE-798/CWE-1188): ``_get_required_secret``
only rejected EMPTY values, so a deployment that copied ``.env.example``
verbatim booted with a publicly known ``SECRET_KEY`` (signs MFA challenges,
workflow seals and import fingerprints) and ``AUTH_JWT_SECRET`` (every HS256
access token, including its ``tenant_id``/``user_id`` claims).

Chosen semantics — documented here because they are load-bearing:

* The gate is **production-only**: it is keyed on ``DJANGO_ENV`` (the existing
  deployment switch, default ``production``) and exempts the test settings
  module. It is deliberately NOT keyed on ``DEBUG``: pytest-django imports
  ``reqogniloom.settings`` with ``DJANGO_ENV`` unset while requesting
  ``DEBUG=True``, so ``DEBUG`` is False in the suite and a ``DEBUG``-based gate
  would reject the suite's intentionally short fixtures.
* A secret is weak when it is shorter than 32 characters after stripping, or
  when it contains a known placeholder marker (``change-me``, ``dev-secret``,
  ``test-secret``, …), case-insensitively.
* ``DEBUG=True`` therefore implies tolerance in practice: it can only be True in
  a non-production ``DJANGO_ENV``, which is exactly what disables the gate.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

from reqogniloom import settings as project_settings

# ``settings.py`` lives in ``backend/reqogniloom`` -> parents[1] is the backend
# directory both on the CI runner and inside the test image (mounted at /app).
BACKEND_DIR = Path(project_settings.__file__).resolve().parents[1]

WEAK_VALUES = [
    # What .env.example ships (before and after this change).
    "CHANGE-ME-generate-with-secrets-token-urlsafe-64",
    "CHANGE-ME-IN-PRODUCTION-use-a-long-random-string",
    # The dev overlay / CI fixtures.
    "dev-secret-key-change-in-production",
    "ci-test-secret-key",
    "test-secret-key-for-pytest-do-not-use-in-production",
    # Classic documentation placeholders.
    "changeme",
    "change_me",
    "your-secret-key",
    "insecure-development-key",
    "replace-me",
    # Long enough, but still a placeholder.
    "CHANGE-ME-" + "x" * 60,
    # Too short, no marker.
    "a" * 31,
    "   ",
]


def _find_env_example() -> Path:
    """Locate ``.env.example``.

    Present on a CI runner and on a developer host (walk up from ``backend/``);
    the docker test stack mounts only ``./backend`` and ``./docs``, so there the
    path can be injected with ``REQOGNILOOM_ENV_EXAMPLE`` and the coupling test
    is skipped rather than silently passing on a wrong path.
    """
    override = os.environ.get("REQOGNILOOM_ENV_EXAMPLE")
    if override:
        candidate = Path(override)
        assert candidate.is_file(), f"REQOGNILOOM_ENV_EXAMPLE is not a file: {candidate}"
        return candidate
    for parent in (BACKEND_DIR, *BACKEND_DIR.parents):
        candidate = parent / ".env.example"
        if candidate.is_file():
            return candidate
    pytest.skip(
        ".env.example is not reachable from the test runtime "
        f"(searched upwards from {BACKEND_DIR}); run this module on the host, "
        "from a full checkout, or set REQOGNILOOM_ENV_EXAMPLE."
    )


@pytest.fixture(scope="module")
def env_example() -> Iterator[Path]:
    yield _find_env_example()


def _env_example_value(path: Path, key: str) -> str:
    """Return the last uncommented ``key=`` value from ``.env.example``."""
    text = path.read_text(encoding="utf-8")
    matches = re.findall(rf"^{re.escape(key)}=(.*)$", text, flags=re.MULTILINE)
    assert matches, f"{key} is missing from .env.example"
    return matches[-1].strip()


@pytest.mark.parametrize("value", WEAK_VALUES)
def test_known_weak_values_are_detected(value: str) -> None:
    assert project_settings._is_weak_secret(value) is True


@pytest.mark.parametrize(
    "value",
    [
        # Deterministic literals, NOT ``secrets.token_*``: a random value in a
        # parametrize list makes pytest-xdist workers collect different test
        # ids ("Different tests were collected between gw0 and gw1"). The
        # runtime subprocess tests below may still generate random secrets.
        "9bOyYICG9xRhCczy8KyQ5pdacKtiV0trdzveCAYmZonCtdMcBAoX_69GjGUAYNtN-xLLoVXKaxCKI0-WehP1UQ",
        "2e5c4a0f4e38fdd86577ac51d09755beddb7d4dfabc516ba3b8839dd86905327",
        "a" * project_settings._SECRET_MIN_LENGTH,
        "7f3c9a1e5b8d2046f1a7c3e9b5d2084a6c1e9f3b7d5a2c8e4f6b0d9a3c7e5f1b",
    ],
)
def test_random_values_are_accepted(value: str) -> None:
    assert project_settings._is_weak_secret(value) is False
    # No exception for a strong value even in production.
    project_settings._validate_secret_strength("SECRET_KEY", value, enforce=True)


@pytest.mark.parametrize("key", ["SECRET_KEY", "AUTH_JWT_SECRET"])
def test_env_example_placeholders_are_rejected(env_example: Path, key: str) -> None:
    """A copy-pasted ``.env`` must not pass as a valid production config.

    The placeholder stays non-empty (``scripts/setup.sh`` replaces values by
    their ``CHANGE-ME`` prefix), so the *value* has to carry the rejection —
    which is what the weak-secret gate is for.
    """
    value = _env_example_value(env_example, key)

    assert value, f"{key} must stay a visible CHANGE-ME placeholder"
    assert value.startswith("CHANGE-ME"), (
        "scripts/setup.sh only generates values that start with CHANGE-ME"
    )
    assert project_settings._is_weak_secret(value) is True

    with pytest.raises(ImproperlyConfigured, match=f"{key} is set to a weak"):
        project_settings._validate_secret_strength(key, value, enforce=True)


def test_production_context_rejects_placeholder_end_to_end(env_example: Path) -> None:
    """The full decision chain: production env + placeholder -> ImproperlyConfigured."""
    enforce = project_settings._is_production_secret_context(
        "production", "reqogniloom.settings"
    )
    assert enforce is True
    with pytest.raises(ImproperlyConfigured) as excinfo:
        project_settings._validate_secret_strength(
            "AUTH_JWT_SECRET",
            _env_example_value(env_example, "AUTH_JWT_SECRET"),
            enforce=enforce,
        )

    message = str(excinfo.value)
    assert "AUTH_JWT_SECRET" in message
    assert "token_urlsafe(64)" in message
    assert "DJANGO_ENV=development" in message


@pytest.mark.parametrize(
    ("django_env", "settings_module", "expected"),
    [
        ("production", "reqogniloom.settings", True),
        # The shipped default when the variable is unset is "production".
        ("production", "", True),
        # Test settings module: exempt (fixed test DB/cache, DEBUG forced True).
        ("production", "reqogniloom.settings_test", False),
        ("production", "settings_test", False),
        ("development", "reqogniloom.settings", False),
        ("dev", "reqogniloom.settings", False),
        ("local", "reqogniloom.settings", False),
        ("test", "reqogniloom.settings", False),
    ],
)
def test_enforcement_gate(
    django_env: str, settings_module: str, expected: bool
) -> None:
    assert (
        project_settings._is_production_secret_context(django_env, settings_module)
        is expected
    )


def test_debug_true_context_tolerates_weak_values() -> None:
    """Dev/test deployments keep working with their short local values.

    ``DEBUG=True`` only survives in a non-production ``DJANGO_ENV`` (settings.py
    forces DEBUG=False in production), and that is exactly the condition that
    disables the gate — so a weak value is tolerated without a special case.
    """
    enforce = project_settings._is_production_secret_context(
        "development", "reqogniloom.settings"
    )
    assert enforce is False
    project_settings._validate_secret_strength(
        "SECRET_KEY", "dev-secret-key-change-in-production", enforce=enforce
    )


def test_test_suite_process_is_not_enforced() -> None:
    """Guard: the suite itself must never trip the production gate."""
    assert project_settings._SECRET_STRENGTH_ENFORCED is False
    # Whatever value the ambient environment provides, the suite is exempt.
    project_settings._validate_secret_strength(
        "SECRET_KEY",
        project_settings.SECRET_KEY,
        enforce=project_settings._SECRET_STRENGTH_ENFORCED,
    )


def test_dockerfile_build_sentinel_is_the_only_exemption() -> None:
    """The image build injects throwaway secrets; only that exact value passes.

    ``backend/Dockerfile`` runs ``manage.py collectstatic`` with
    ``SECRET_KEY=build-only-dummy`` (importable settings only, never baked into
    the image environment). The exemption must stay pinned to that sentinel: a
    lookalike value is still rejected, so this cannot silently widen into a
    "any build-ish string is fine" hole.
    """
    dockerfile = BACKEND_DIR / "Dockerfile"
    assert dockerfile.is_file(), f"Dockerfile not found at {dockerfile}"
    text = dockerfile.read_text(encoding="utf-8")

    assert project_settings._BUILD_ONLY_SECRETS == frozenset({"build-only-dummy"})
    for sentinel in project_settings._BUILD_ONLY_SECRETS:
        assert f"SECRET_KEY={sentinel}" in text, (
            "the build sentinel moved or changed in backend/Dockerfile — update "
            "_BUILD_ONLY_SECRETS together with it"
        )
        assert project_settings._is_weak_secret(sentinel) is False

    assert project_settings._is_weak_secret("build-only-dummy-2") is True
    assert project_settings._is_weak_secret("BUILD-ONLY-DUMMY") is True


def test_import_fails_in_production_with_placeholder_secret(env_example: Path) -> None:
    """Import-level proof: the gate fires before Django finishes starting."""
    env = _isolated_settings_env(
        secret_key=_env_example_value(env_example, "SECRET_KEY")
    )

    result = _import_settings(env)

    assert result.returncode != 0
    assert "weak or placeholder value" in result.stderr
    assert "SECRET_KEY" in result.stderr


def test_import_succeeds_in_production_with_strong_secrets() -> None:
    env = _isolated_settings_env(secret_key=secrets.token_urlsafe(64))

    result = _import_settings(env)

    assert result.returncode == 0, result.stderr


def _isolated_settings_env(*, secret_key: str) -> dict[str, str]:
    """Environment for a production-context settings import in a subprocess."""
    env = dict(os.environ)
    env.update(
        {
            "DJANGO_ENV": "production",
            "DEBUG": "False",
            "DJANGO_SETTINGS_MODULE": "reqogniloom.settings",
            "SECRET_KEY": secret_key,
            "AUTH_JWT_SECRET": secrets.token_urlsafe(64),
            # Required at import time; generated per call so nothing is stored.
            "FIELD_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "DB_PASSWORD": "subprocess-test-password",
        }
    )
    return env


def _import_settings(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "import reqogniloom.settings"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
