"""Free-form multi-artifact interview protocol: prompt + proposal parsing.

Deliberately NOT built on parse_protocol_yaml() (interview_protocol.py) --
that function assumes a fixed phases:/required_fields: YAML shape for a
single artifact type, which doesn't fit a free-running, multi-type chat.
Reuses the same "LLM emits a fenced ```json block, we extract and
json.loads it" pattern AiDerivationService.derive_requirements_from_need()
already uses via its private _complete_json_list() helper -- kept as a
sibling implementation here rather than importing that private helper
across service boundaries.

Note (deliberate deviation from the factory default's sibling slots):
GlossaryTerm is intentionally not offered as an artifact type. GlossaryTerm
has no Artifact FK, so the multi-artifact formalization adapters cannot
attach provenance/TraceLinks to one and reject it fail-fast.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from application.prompt_resolver import resolve_and_render

_MULTI_PROTOCOL_SLOT = "interview.protocol.multi"

_JSON_BLOCK_RE = re.compile(r"```json\s*(\[.*?\])\s*```", re.DOTALL)

_MULTI_PROTOCOL_FACTORY_DEFAULT = """\
You are helping a user figure out which requirements-engineering artifacts \
they need, from a plain description of their problem. Artifact types \
available: StakeholderNeed, Requirement, ArchitectureElement, Risk, \
TestCase, Adr, Issue, Goal.

Do not propose GlossaryTerm artifacts; glossary terms cannot be created \
through a multi-artifact interview.

Ask clarifying questions if the problem is unclear. Once you have enough \
information, propose a list of artifacts as a fenced ```json code block, \
each item shaped as:
{"type": "<ArtifactType>", "title": "<short title>", "fields": {<fields for that type's create call>}, "links": [{"from": <index>, "to": <index>, "type": "<trace-link-type>"}]}

Use trace-link types from: parent-child, derives-from, satisfies, verifies, \
implements, refines, documents, realizes, traces, copy-of, allocated-to, \
uses-term, decides, decomposes. Never propose "diagram-ref" -- it is \
system-managed only.

Conversation so far:
{transcript}

User: {user_message}
"""


def get_multi_protocol_prompt(ctx: Any, workspace_id, user_message: str, transcript: list) -> str:
    """Render the multi-artifact interview protocol for this chat turn.

    ``transcript`` holds role/content dicts; rendered as ``"<role>: <content>"``
    lines and injected together with *user_message* as template variables.
    """
    transcript_text = "\n".join(f"{turn['role']}: {turn['content']}" for turn in transcript)
    return resolve_and_render(
        _MULTI_PROTOCOL_SLOT,
        ctx,
        workspace_id,
        user_message=user_message,
        transcript=transcript_text,
    )


def parse_multi_proposal(raw_llm_output: str) -> "Optional[list[dict]]":
    """Extract the fenced ```json list from an LLM reply.

    Returns the parsed list of artifact-proposal dicts, or ``None`` when the
    output has no JSON fence, malformed JSON, or a non-list payload -- the
    caller decides how to surface that ("LLM liefert keinen parsbaren
    Vorschlag").
    """
    match = _JSON_BLOCK_RE.search(raw_llm_output)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return parsed
