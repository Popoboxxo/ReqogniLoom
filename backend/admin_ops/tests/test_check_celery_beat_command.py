"""Tests for the functional celery-beat healthcheck command (ADR-010 §3, RES-05).

``python manage.py check_celery_beat`` must exit non-zero when the
beat-scheduled heartbeat is missing, stale or unreadable, and zero when it is
fresh. This is what replaces the old ``pgrep -f 'celery.*beat'`` compose probe:
a hung-but-alive beat process must turn the container unhealthy.
"""
from __future__ import annotations

import time

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from admin_ops import celery_beat_heartbeat as heartbeat


def test_fresh_heartbeat_passes(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        heartbeat, "read_heartbeat_timestamp", lambda: time.time()
    )

    call_command("check_celery_beat")

    assert "heartbeat ok" in capsys.readouterr().out


def test_missing_heartbeat_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(heartbeat, "read_heartbeat_timestamp", lambda: None)

    with pytest.raises(CommandError, match="no celery beat heartbeat"):
        call_command("check_celery_beat")


def test_stale_heartbeat_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    stale = time.time() - (heartbeat.HEARTBEAT_STALE_AFTER_SECONDS + 5)
    monkeypatch.setattr(heartbeat, "read_heartbeat_timestamp", lambda: stale)

    with pytest.raises(CommandError, match="stale"):
        call_command("check_celery_beat")


def test_unreadable_heartbeat_fails_without_leaking_the_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom() -> float:
        raise RuntimeError("redis://svc:supersecret@cache.internal:6379/0")

    monkeypatch.setattr(heartbeat, "read_heartbeat_timestamp", _boom)

    with pytest.raises(CommandError) as excinfo:
        call_command("check_celery_beat")

    # Only the static message is printed by manage.py; the driver text (possible
    # DSN) stays in the chained cause and never in the operator-facing message.
    assert "cache.internal" not in str(excinfo.value)
    assert "unreadable" in str(excinfo.value)
