"""L2.4: sliding transcript window + LLM compression of the overflow."""
from __future__ import annotations

import uuid

import pytest

from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
from application.prompt_slots import get_prompt_slots


class TestTranscriptSummaryPrompt:
    def test_slot_is_registered_with_its_placeholders(self):
        slots = get_prompt_slots()
        assert "interview.transcript_summary" in slots
        names = set(slots["interview.transcript_summary"].data_variables)
        assert names == {"previous_summary", "overflow_json"}

    def test_factory_default_template_exists_and_uses_both_placeholders(self):
        template = PROMPT_TEMPLATE_DEFAULTS["interview.transcript_summary"]
        assert "{previous_summary}" in template
        assert "{overflow_json}" in template

    def test_chat_turn_slot_gained_the_summary_placeholder(self):
        """The chat prompt must carry the compressed history, or capping the
        transcript would silently drop context instead of condensing it."""
        slots = get_prompt_slots()
        assert "transcript_summary" in set(slots["interview.chat_turn"].data_variables)
        assert "{transcript_summary}" in slots["interview.chat_turn"].default_content
