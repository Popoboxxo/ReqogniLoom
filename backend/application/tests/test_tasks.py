"""
Tests for the application-layer Celery tasks.

req_id : REQ-032

Coverage:
  - dispatch_outbox_events delegates to poll_and_dispatch and returns its count
  - dispatch_outbox_events swallows exceptions (beat loop must not crash) and
    returns 0 on failure
"""
from __future__ import annotations

from unittest.mock import patch

from application.tasks import dispatch_outbox_events


def test_dispatch_outbox_events_returns_processed_count() -> None:
    """Task returns the number of events poll_and_dispatch processed."""
    with patch("application.tasks.poll_and_dispatch", return_value=3) as poll:
        result = dispatch_outbox_events.run()

    poll.assert_called_once_with()
    assert result == 3


def test_dispatch_outbox_events_swallows_exceptions() -> None:
    """Task must not propagate exceptions so the beat loop keeps running."""
    with patch(
        "application.tasks.poll_and_dispatch",
        side_effect=RuntimeError("boom"),
    ):
        result = dispatch_outbox_events.run()

    assert result == 0
