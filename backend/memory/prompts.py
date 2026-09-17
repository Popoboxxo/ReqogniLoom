"""Factory-default prompt body for the memory consolidation pipeline (Task 5).

Merged into the canonical prompt-slot registry by
``application.prompt_slots.get_prompt_slots`` alongside
``PROMPT_TEMPLATE_DEFAULTS`` / ``INTERVIEW_PROTOCOL_DEFAULTS`` -- see that
module's docstring for the merge rationale. Kept in its own module (like
``application.interview_protocol.INTERVIEW_PROTOCOL_DEFAULTS``) rather than
folded into ``ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS`` so the memory
app owns its own prompt content.
"""
from __future__ import annotations

from typing import Dict

MEMORY_PROMPT_DEFAULTS: Dict[str, str] = {
    "memory.extract": """\
Extract durable facts or preferences from this interaction that would be
useful to remember in future conversations. Only extract facts that are
genuinely reusable (project decisions, stated preferences, recurring
patterns) -- not one-off details.

Respond with a JSON object: {"facts": [{"content": "<fact text>", "scope": "workspace"|"user"}]}
"scope"="workspace" for project-specific facts, "scope"="user" for facts
about the person's general preferences/working style.

Interaction:
{interaction_text}
""",
}

__all__ = ["MEMORY_PROMPT_DEFAULTS"]
