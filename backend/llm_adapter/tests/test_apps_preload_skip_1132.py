"""#1132: celery-beat must not preload the sentence-transformers embedding model.

``celery ... beat`` only schedules tasks; it never embeds, so its Django boot
must skip ``LlmAdapterConfig.ready()``'s eager model preload. The preload cost
beat ~407 MiB anon steady state (deploy/docker-compose.yml, celery-beat memory
rationale). Detection lives in ``_is_celery_beat_invocation`` -- an exact argv
token match, not a substring, so ``check_celery_beat`` and ``worker -B`` are
not misclassified.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from llm_adapter.apps import (
    _is_celery_beat_invocation,
    _PRELOAD_SKIP_COMMANDS,
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "argv",
    [
        ["celery", "-A", "reqogniloom", "beat", "-l", "info"],
        ["celery", "beat", "-A", "reqogniloom"],
        # The exact compose command (deploy/docker-compose.yml:1040):
        [
            "/usr/local/bin/celery",
            "-A",
            "reqogniloom",
            "beat",
            "-l",
            "info",
            "--scheduler",
            "django_celery_beat.schedulers:DatabaseScheduler",
        ],
    ],
)
def test_detects_beat_invocations(argv: list[str]) -> None:
    assert _is_celery_beat_invocation(argv) is True


@pytest.mark.parametrize(
    "argv",
    [
        ["celery", "-A", "reqogniloom", "worker", "--loglevel=info"],
        # Embedded beat (`-B`) runs inside a worker that DOES execute tasks, so
        # it must keep the preload -- only the bare `beat` token counts.
        ["celery", "-A", "reqogniloom", "worker", "-B"],
        # Management command name is one word, not the `beat` token.
        ["python", "manage.py", "check_celery_beat"],
        ["celery", "-A", "reqogniloom", "inspect", "ping"],
    ],
)
def test_does_not_misclassify_non_beat_argv(argv: list[str]) -> None:
    assert _is_celery_beat_invocation(argv) is False


def test_check_celery_beat_still_in_skip_set() -> None:
    """The probe skip (RES-05) must survive the #1132 change."""
    assert "check_celery_beat" in _PRELOAD_SKIP_COMMANDS


def test_should_skip_preload_true_for_beat_without_pytest() -> None:
    """Real-process regression: beat argv -> preload skipped, even outside pytest.

    Runs a bare interpreter (``pytest`` absent from ``sys.modules``, so the
    test-only short-circuit in ``_should_skip_preload`` does not mask the
    result) with a ``celery ... beat`` argv.
    """
    code = (
        "import sys\n"
        "sys.argv = ['celery', '-A', 'reqogniloom', 'beat', '-l', 'info']\n"
        "from llm_adapter.apps import LlmAdapterConfig\n"
        "print(LlmAdapterConfig._should_skip_preload())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"
