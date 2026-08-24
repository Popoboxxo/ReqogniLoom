"""Registration checks for the interview.* multi-artifact extensions
(multi-artifact plan Task 6): ``interview.propose`` must be registered in
the tool group's _TOOL_MAP, listed read-only in the registry, and carry a
schema entry.

Pure unit tests -- no DB, no service calls: only class-level registration
state is asserted.
"""
from __future__ import annotations

import pytest

from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES
from mcp_server.tools.interview import InterviewToolGroup


class TestInterviewToolGroupMulti:
    def test_propose_is_registered(self):
        assert "interview.propose" in InterviewToolGroup()._TOOL_MAP

    def test_propose_is_read_only(self):
        assert "interview.propose" in _READ_ONLY_TOOL_NAMES

    def test_propose_has_a_schema(self):
        schemas = {s["name"] for s in InterviewToolGroup()._TOOL_SCHEMAS}
        assert "interview.propose" in schemas
