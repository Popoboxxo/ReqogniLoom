"""Tests for the consolidation counters (issue #1300).

The counters answer "is the memory learning loop running, from which trigger?"
without a log grep; they are best-effort and must never break the pipeline they
observe (mirroring ``memory.ratelimit``'s fail-open policy).
"""
import pytest
from django.core.cache import cache

from memory.metrics import (
    UNKNOWN_SOURCE,
    consolidation_counts,
    increment_consolidation,
    reset_consolidation_counters,
    total_consolidations,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


class TestConsolidationCounters:
    def test_first_increment_reads_one(self):
        assert increment_consolidation("InterviewChatTurn") == 1

    def test_increments_accumulate_per_source(self):
        increment_consolidation("InterviewChatTurn")
        increment_consolidation("InterviewChatTurn")
        increment_consolidation("InteractionCompleted")

        counts = consolidation_counts()
        assert counts["InterviewChatTurn"] == 2
        assert counts["InteractionCompleted"] == 1
        assert total_consolidations() == 3

    def test_unknown_source_label_is_used_when_blank(self):
        increment_consolidation("")
        assert consolidation_counts()[UNKNOWN_SOURCE] == 1

    def test_reset_clears_every_counter_and_the_registry(self):
        increment_consolidation("InterviewChatTurn")
        reset_consolidation_counters()
        assert consolidation_counts() == {}
        assert total_consolidations() == 0

    def test_cache_failure_is_fail_open(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("redis is down")

        monkeypatch.setattr("memory.metrics.cache.add", _boom)
        # No exception: a cache outage must not break the pipeline it observes.
        assert increment_consolidation("InterviewChatTurn") == 0

    def test_counts_is_empty_when_registry_unreadable(self, monkeypatch):
        increment_consolidation("InterviewChatTurn")

        def _boom(*args, **kwargs):
            raise RuntimeError("redis is down")

        monkeypatch.setattr("memory.metrics.cache.get", _boom)
        assert consolidation_counts() == {}
