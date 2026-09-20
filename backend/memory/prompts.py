"""Factory-default prompt body for the memory consolidation pipeline (Task 5).

Merged into the canonical prompt-slot registry by
``application.prompt_slots.get_prompt_slots`` alongside
``PROMPT_TEMPLATE_DEFAULTS`` / ``INTERVIEW_PROTOCOL_DEFAULTS`` -- see that
module's docstring for the merge rationale. Kept in its own module (like
``application.interview_protocol.INTERVIEW_PROTOCOL_DEFAULTS``) rather than
folded into ``ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS`` so the memory
app owns its own prompt content.

RFC #1002 PR C additions:

* ``{artifact_context}`` -- the calling consolidation task describes the
  artifact an interaction happened in (id + artifact type, see
  ``memory.tasks.consolidate_interaction``). When present, facts that concern
  ONLY that artifact must be tagged ``"scope": "artifact"`` so they land in the
  artifact-scoped slice of the unified store instead of leaking into the
  workspace-wide (or worse, user-wide) slice.
* ``{language}`` -- the workspace's content language (``Workspace.language``).
  The extractor is told to write every fact in that language and to tag each
  fact with the ISO 639-1 code it actually used, so
  ``consolidate_interaction`` can drop language-drifted facts (F11) instead of
  storing a mixed-language corpus.
"""
from __future__ import annotations

from typing import Dict

MEMORY_PROMPT_DEFAULTS: Dict[str, str] = {
    "memory.extract": """\
Extract durable facts or preferences from this interaction that would be
useful to remember in future conversations. Only extract facts that are
genuinely reusable (project decisions, stated preferences, recurring
patterns) -- not one-off details.

Write every fact in the workspace language ({language}). Tag each fact with
the ISO 639-1 code of the language you actually wrote it in, in a
"language" field. Never translate a fact into another language.

Artifact context (may be empty):
{artifact_context}

Respond with a JSON object: {"facts": [{"content": "<fact text>", "scope": "artifact"|"workspace"|"user", "language": "<ISO 639-1 code>"}]}
"scope"="workspace" for project-specific facts, "scope"="user" for facts
about the person's general preferences/working style, and "scope"="artifact"
for facts that concern ONLY the artifact named in the artifact context above
(use "workspace" instead when no artifact context is given).

Interaction:
{interaction_text}
""",
}

__all__ = ["MEMORY_PROMPT_DEFAULTS"]
