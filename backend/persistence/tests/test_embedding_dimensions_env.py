"""Issue #826: ``EMBEDDING_VECTOR_DIMENSIONS`` is operator-configurable.

Before #826 the width was a hardcoded literal in
``persistence.embedding_dimensions``: switching ``EMBEDDING_PROVIDER`` to a
provider of a different native width (``ollama`` 768, ``openai`` 1536) could
only be made to work by editing source. #826 resolves the width from the
``EMBEDDING_VECTOR_DIMENSIONS`` environment variable instead, while keeping the
default at the shipped provider's 384 and keeping migration history immutable.

Two facts this module pins down:

* resolution is strict — a non-integer, zero or negative value fails loudly at
  import (``ImproperlyConfigured``), it is never silently coerced;
* the value really reaches the model fields — a fresh process started with
  ``EMBEDDING_VECTOR_DIMENSIONS=768`` declares ``vector(768)``, and
  ``makemigrations --check`` then reports the ``AlterField`` operations needed
  to resize the schema.

Everything is exercised in a subprocess on purpose: model fields bind
``EMBEDDING_VECTOR_DIMENSIONS`` at import time, so an in-process reload would
not reflect what a freshly started backend/celery/migrate container does.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from persistence.embedding_dimensions import (
    DEFAULT_EMBEDDING_VECTOR_DIMENSIONS,
    EMBEDDING_VECTOR_DIMENSIONS,
    EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR,
    _resolve_embedding_vector_dimensions,
)

#: Long enough for a cold ``django.setup()`` in the CI container.
_SUBPROCESS_TIMEOUT_SECONDS = 300


def _run_env(
    code: str,
    *,
    embedding_dimensions: str | None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a fresh interpreter with a controlled environment."""
    env = os.environ.copy()
    env.pop(EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR, None)
    env.setdefault("DJANGO_SETTINGS_MODULE", "reqogniloom.settings_test")
    if embedding_dimensions is not None:
        env[EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR] = embedding_dimensions
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(settings.BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
    )


# ---------------------------------------------------------------------------
# Resolution rules (pure, no Django setup needed)
# ---------------------------------------------------------------------------


class TestResolutionRules:
    def test_defaults_to_384_when_unset(self, monkeypatch):
        monkeypatch.delenv(EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR, raising=False)

        assert (
            _resolve_embedding_vector_dimensions()
            == DEFAULT_EMBEDDING_VECTOR_DIMENSIONS
            == 384
        )

    def test_blank_value_is_treated_as_unset(self, monkeypatch):
        """``EMBEDDING_VECTOR_DIMENSIONS=`` in a .env is "not configured", not
        an error — matching how ``EMBEDDING_MODEL_NAME=`` is handled."""
        monkeypatch.setenv(EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR, "   ")

        assert _resolve_embedding_vector_dimensions() == DEFAULT_EMBEDDING_VECTOR_DIMENSIONS

    @pytest.mark.parametrize("raw,expected", [("768", 768), ("1536", 1536), ("384", 384)])
    def test_positive_integer_is_honoured(self, monkeypatch, raw, expected):
        monkeypatch.setenv(EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR, raw)

        assert _resolve_embedding_vector_dimensions() == expected

    @pytest.mark.parametrize("raw", ["not-a-number", "3.14", "384dims"])
    def test_non_integer_fails_loudly(self, monkeypatch, raw):
        monkeypatch.setenv(EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR, raw)

        with pytest.raises(ImproperlyConfigured) as excinfo:
            _resolve_embedding_vector_dimensions()

        assert EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR in str(excinfo.value)

    @pytest.mark.parametrize("raw", ["0", "-1", "-768"])
    def test_non_positive_fails_loudly(self, monkeypatch, raw):
        monkeypatch.setenv(EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR, raw)

        with pytest.raises(ImproperlyConfigured) as excinfo:
            _resolve_embedding_vector_dimensions()

        message = str(excinfo.value)
        assert EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR in message
        assert "positive" in message

    def test_default_constant_matches_the_shipped_suite(self):
        """Guard against a silent default change: the in-suite binding must be
        384 independent of any developer's shell environment."""
        assert EMBEDDING_VECTOR_DIMENSIONS == DEFAULT_EMBEDDING_VECTOR_DIMENSIONS == 384


# ---------------------------------------------------------------------------
# The value reaches the model fields (fresh process)
# ---------------------------------------------------------------------------

_MODEL_DIMENSIONS_CODE = """
import django

django.setup()

from icd.models import Icd
from memory.models import UserTenantMemory, WorkspaceMemory
from persistence.models import Requirement, TraceLink

for model in (Requirement, TraceLink, Icd, WorkspaceMemory, UserTenantMemory):
    print(f"DIM {model.__name__}={model._meta.get_field('embedding').dimensions}")
"""

_EXPECTED_MODELS = (
    "Requirement",
    "TraceLink",
    "Icd",
    "WorkspaceMemory",
    "UserTenantMemory",
)


class TestModelFieldsFollowTheEnvironment:
    @pytest.mark.parametrize("value", ["768", "1536"])
    def test_every_embedding_field_uses_the_configured_width(self, value):
        result = _run_env(_MODEL_DIMENSIONS_CODE, embedding_dimensions=value)

        assert result.returncode == 0, result.stderr
        observed = {
            line.split("=")[0].removeprefix("DIM "): int(line.split("=")[1])
            for line in result.stdout.splitlines()
            if line.startswith("DIM ")
        }
        assert set(observed) == set(_EXPECTED_MODELS)
        assert set(observed.values()) == {int(value)}, (
            f"EMBEDDING_VECTOR_DIMENSIONS={value} did not reach every embedding "
            f"field: {observed}"
        )

    def test_default_process_declares_384(self):
        result = _run_env(_MODEL_DIMENSIONS_CODE, embedding_dimensions=None)

        assert result.returncode == 0, result.stderr
        assert "DIM Requirement=384" in result.stdout

    def test_invalid_value_aborts_a_fresh_process(self):
        """The failure must happen at import, before any model/migration code
        runs on a bogus width."""
        result = _run_env(
            "import django; django.setup(); "
            "from persistence.models import Requirement",
            embedding_dimensions="not-a-number",
        )

        assert result.returncode != 0
        assert "ImproperlyConfigured" in result.stderr
        assert EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR in result.stderr


# ---------------------------------------------------------------------------
# Migration autodetection: at 768, makemigrations wants to resize the columns
# ---------------------------------------------------------------------------


def _run_makemigrations(*, embedding_dimensions: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop(EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR, None)
    env.setdefault("DJANGO_SETTINGS_MODULE", "reqogniloom.settings_test")
    if embedding_dimensions is not None:
        env[EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR] = embedding_dimensions
    return subprocess.run(
        [
            sys.executable,
            "manage.py",
            "makemigrations",
            "--check",
            "--dry-run",
            "--skip-checks",
        ],
        cwd=Path(settings.BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
    )


class TestMakemigrationsReflectsTheConfiguredWidth:
    def test_default_is_clean(self):
        """The pinned migration history must be consistent with the 384 default,
        otherwise every deployment would ship pending migrations."""
        result = _run_makemigrations(embedding_dimensions=None)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "No changes detected" in (result.stdout + result.stderr)

    def test_768_wants_to_alter_every_embedding_column(self):
        result = _run_makemigrations(embedding_dimensions="768")
        combined = (result.stdout + result.stderr)

        assert result.returncode == 1, combined
        assert "Alter field embedding on" in combined
        for model_name in ("requirement", "tracelink", "icd", "workspacememory", "usertenantmemory"):
            assert f"embedding on {model_name}" in combined, (
                f"no AlterField was detected for {model_name}.embedding at 768; "
                f"output was:\n{combined}"
            )
        # The autodetector summary names the fields but not the new width; the
        # value itself is covered by TestModelFieldsFollowTheEnvironment.
