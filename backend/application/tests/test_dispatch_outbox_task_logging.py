"""R10-07 (#1404): a DB outage in the outbox poll is one warning, not a traceback.

``dispatch_outbox_events`` runs every beat tick. During a database outage the
generic ``logger.exception`` produced a full traceback per cycle, which buried
the real signal (and made the logs look like an application defect). The
specific ``OperationalError`` branch keeps the reporting honest: one warning
line, no ``exc_info``.
"""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from django.db import OperationalError

from application.tasks import dispatch_outbox_events


def test_db_outage_logs_single_warning(caplog):
    with patch(
        "application.tasks.poll_and_dispatch",
        side_effect=OperationalError("connection refused"),
    ):
        with caplog.at_level(logging.WARNING, logger="application.tasks"):
            result = dispatch_outbox_events()

    assert result == 0
    records = [record for record in caplog.records if record.name == "application.tasks"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "database unavailable" in records[0].getMessage()
    assert records[0].exc_info is None


def test_unexpected_failure_still_logs_a_traceback(caplog):
    with patch(
        "application.tasks.poll_and_dispatch",
        side_effect=RuntimeError("boom"),
    ):
        with caplog.at_level(logging.ERROR, logger="application.tasks"):
            result = dispatch_outbox_events()

    assert result == 0
    records = [record for record in caplog.records if record.name == "application.tasks"]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].exc_info is not None
