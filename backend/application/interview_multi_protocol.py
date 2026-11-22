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
GlossaryTerm is intentionally not offered as an artifact type in the prompt
below. The original reason ("GlossaryTerm has no Artifact FK") is obsolete --
Datenmodell-Konsolidierung Phase 3 (PR #880) gave it a backing Artifact row,
and ``ARTIFACT_CREATION_ADAPTERS["GlossaryTerm"]`` creates a real term today.
What remains is a scope decision, not a technical block: glossary terms are
managed on the glossary surface, and GlossaryTerm is deliberately absent from
``IN_SCOPE_ARTIFACT_TYPES`` (so single-kind ``start()`` rejects it too).
Consequence: nothing rejects a GlossaryTerm item a caller puts into a
hand-built ``confirmed_proposal`` -- the registry entry handles it -- the
prompt simply never proposes one.
"""
from __future__ import annotations

import json
import re
from typing import Any

from application.interview_proposal_errors import (
    _RESERVED_PROPOSAL_FIELDS,
    ProposalValidationError,
)
from application.prompt_resolver import resolve_and_render
from link_types.catalog import resolve_catalog
from persistence.errors import ValidationError

_MULTI_PROTOCOL_SLOT = "interview.protocol.multi"

_JSON_BLOCK_RE = re.compile(r"```json\s*(\[.*?\])\s*```", re.DOTALL)

# AI-005 proposal-size limits at the PARSE boundary: a model reply is untrusted
# input, so cap its size before it can reach the formalize write path. Values
# mirror the service-layer ceilings in interview_service.py; malformed or
# oversized payloads return None (same contract as no-fence/malformed JSON).
MAX_RAW_LLM_OUTPUT_LENGTH = 200_000
MAX_PROPOSAL_ITEMS = 50
MAX_PROPOSAL_FIELDS_PER_ITEM = 50
MAX_PROPOSAL_LINKS_PER_ITEM = 50
MAX_PROPOSAL_STRING_LENGTH = 5_000


def _proposal_within_limits(parsed: list[dict]) -> bool:
    """Check the size/shape ceilings on a parsed proposal list.

    Deliberately shallow: the authoritative field allowlist + type/length gate
    lives in the service layer (interview_service.validate_confirmed_proposal_
    fields). This only stops an absurdly large model reply from ever becoming a
    pending proposal.
    """
    if not parsed or len(parsed) > MAX_PROPOSAL_ITEMS:
        return False
    for item in parsed:
        if not isinstance(item, dict):
            return False
        fields = item.get("fields")
        if not isinstance(fields, dict) or len(fields) > MAX_PROPOSAL_FIELDS_PER_ITEM:
            return False
        for key, value in fields.items():
            if not isinstance(key, str) or len(key) > 200:
                return False
            if isinstance(value, str) and len(value) > MAX_PROPOSAL_STRING_LENGTH:
                return False
        links = item.get("links")
        if links is not None:
            if not isinstance(links, list) or len(links) > MAX_PROPOSAL_LINKS_PER_ITEM:
                return False
    return True


# Issue #1990: the LLM prompt used to ask for a top-level ``title`` next to
# ``fields``. ``formalize`` only reads ``item["fields"]``, so that title was
# silently lost (or the whole item rejected for lacking a ``fields`` dict).
# The canonical item shape has exactly these keys; ``title`` is a legacy
# alias we normalise into ``fields`` rather than a second source of truth.
_ITEM_ALLOWED_KEYS: frozenset[str] = frozenset({"type", "title", "fields", "links"})


def normalize_proposal_items(proposal: list[dict]) -> list[dict]:
    """Return copies of *proposal* in the shape ``formalize`` accepts.

    A legacy top-level ``title`` is folded into ``fields["title"]`` when the
    latter is absent (an explicit ``fields`` value always wins). The original
    top-level key is kept for backwards compatibility with callers that
    compare the readout to what they stored -- ``formalize`` ignores it.

    Every other top-level key is REJECTED with a machine-readable reason
    (:class:`ProposalValidationError`) instead of being silently dropped:
    server-owned names (``priority``/``status``/...) get ``RESERVED_FIELD``,
    anything else gets ``UNEXPECTED_ITEM_FIELD``. Silently ignoring a key the
    model emitted is how server-owned values and typos survived into the
    proposal long enough to fail at write time.

    Nothing is mutated in place; the stored ``grounding_snapshot`` stays
    untouched and the normalised copy is safe to hand to ``formalize``.
    """
    normalised: list[dict] = []
    for index, item in enumerate(proposal):
        if not isinstance(item, dict):
            raise ProposalValidationError(
                f"proposal item #{index} must be a dict, got {type(item).__name__}",
                code="INVALID_PROPOSAL_SHAPE",
                item_index=index,
            )
        for key in item:
            if not isinstance(key, str) or key in _ITEM_ALLOWED_KEYS:
                continue
            code = "RESERVED_FIELD" if key in _RESERVED_PROPOSAL_FIELDS else "UNEXPECTED_ITEM_FIELD"
            raise ProposalValidationError(
                f"proposal item #{index}: top-level field {key!r} is not part of the "
                "canonical {type, fields, links} shape",
                code=code,
                item_index=index,
                field=key,
            )
        fields = item.get("fields")
        if fields is not None and not isinstance(fields, dict):
            raise ProposalValidationError(
                f"proposal item #{index}: 'fields' must be a dict",
                code="INVALID_PROPOSAL_SHAPE",
                item_index=index,
                field="fields",
            )
        new_item = dict(item)
        if isinstance(fields, dict) and "title" not in fields and "title" in item:
            new_item["fields"] = {**fields, "title": item["title"]}
        normalised.append(new_item)
    return normalised


def validate_proposal_link_pairs(proposal: list[dict], workspace_id) -> None:
    """Check every proposed link against the workspace link-type catalog.

    Issue #1990: structural link validation (``from``/``to`` indices and a
    string ``type``) never checked ``allowed_pairs``, so an LLM-proposed
    ``realizes`` from ArchitectureElement to Requirement only failed *after*
    the artifacts had been created, inside the write transaction. Resolving
    the endpoints to their proposal item types here lets the readout reject
    the bad edge before it is ever shown as confirmable.

    Endpoint indices are range-checked defensively so this helper is safe to
    call standalone; the formalize path still runs the authoritative
    structural validation first.
    """
    from link_types.catalog import validate_link_pair

    for index, item in enumerate(proposal):
        if not isinstance(item, dict):
            raise ProposalValidationError(
                f"proposal item #{index} must be a dict, got {type(item).__name__}",
                code="INVALID_PROPOSAL_SHAPE",
                item_index=index,
            )
        for link_index, link in enumerate(item.get("links") or []):
            if not isinstance(link, dict):
                continue  # structural validation owns this case
            source = link.get("from")
            target = link.get("to")
            link_type = link.get("type")
            if (
                not isinstance(source, int)
                or isinstance(source, bool)
                or not isinstance(target, int)
                or isinstance(target, bool)
                or not 0 <= source < len(proposal)
                or not 0 <= target < len(proposal)
                or not isinstance(link_type, str)
            ):
                # Out-of-range/malformed endpoints are a shape error, not a
                # pair mismatch; the caller's structure gate reports them.
                raise ProposalValidationError(
                    f"proposal item #{index}, link #{link_index}: invalid link endpoints",
                    code="INVALID_LINK_PAIR",
                    item_index=index,
                    field=f"links[{link_index}]",
                )
            try:
                validate_link_pair(
                    workspace_id,
                    link_type,
                    proposal[source]["type"],
                    proposal[target]["type"],
                    manual=True,
                )
            except ValidationError as exc:
                raise ProposalValidationError(
                    str(exc),
                    code="INVALID_LINK_PAIR",
                    item_index=index,
                    field=f"links[{link_index}]",
                    details={
                        "link_type": link_type,
                        "source_type": proposal[source]["type"],
                        "target_type": proposal[target]["type"],
                    },
                ) from exc


_MULTI_PROTOCOL_FACTORY_DEFAULT = """\
You are helping a user figure out which requirements-engineering artifacts \
they need, from a plain description of their problem. Artifact types \
available: StakeholderNeed, Requirement, ArchitectureElement, Risk, \
TestCase, Adr, Issue, Goal.

Do not propose GlossaryTerm artifacts; glossary terms are managed on the \
glossary surface, not proposed by an interview.

Ask clarifying questions if the problem is unclear. Once you have enough \
information, propose a list of artifacts as a fenced ```json code block, \
each item shaped as:
{"type": "<ArtifactType>", "fields": {<fields for that type's create call>}, "links": [{"from": <index>, "to": <index>, "type": "<trace-link-type>"}]}

Put EVERY field — including `title` — inside `fields`; do not emit a \
top-level `title` or any other top-level key besides `type`, `fields` and \
`links`. Server-owned fields (`status`, `owner`, `reporter`, `priority`, ids, \
timestamps, version, ctx) are not allowed. Do not set `type` inside `fields`.

Use trace-link types from the workspace's link-type catalog, which is supplied \
in the prompt context as `available_link_types`. Never propose a type that is \
not in that list, and only use a type whose allowed endpoint pair matches the \
two items you are linking (an index's item type is its source/target type).

available_link_types: {available_link_types}

Relevant memory from earlier sessions (may be empty):
{memory_context}

Conversation so far:
{transcript}

User: {user_message}
"""


def _available_link_types(workspace_id) -> str:
    """Comma-separated, manually creatable link-type keys of *workspace_id*.

    Read from the per-workspace catalog rather than hardcoded: the catalog is
    tenant-extensible, so any literal list in the prompt goes stale the moment
    a workspace adds or deactivates a type. ``system_owned`` keys (such as the
    reconciler-owned ``diagram-ref``) are filtered out — the LLM must never
    propose one.
    """
    catalog = resolve_catalog(workspace_id)
    keys = sorted(
        key
        for key, definition in catalog.items()
        if definition.get("manual_creatable", True)
        and not definition.get("system_owned", False)
    )
    return ", ".join(keys)


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
        available_link_types=_available_link_types(workspace_id),
    )


def parse_multi_proposal(raw_llm_output: str) -> list[dict] | None:
    """Extract the fenced ```json list from an LLM reply.

    Returns the parsed list of artifact-proposal dicts, or ``None`` when the
    output has no JSON fence, malformed JSON, a non-list payload, or a payload
    exceeding the AI-005 proposal-size ceilings (item/field/link counts and
    string lengths) -- the caller decides how to surface that ("LLM liefert
    keinen parsbaren Vorschlag"). Field-name allowlisting and per-value
    type/length validation happen later, in the service write path.
    """
    if len(raw_llm_output) > MAX_RAW_LLM_OUTPUT_LENGTH:
        return None
    match = _JSON_BLOCK_RE.search(raw_llm_output)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    # Issue #1990: fold a legacy top-level ``title`` into ``fields`` at the
    # parse boundary so the chat response and the stored pending proposal are
    # already in the shape ``formalize`` accepts. Reserved/foreign top-level
    # keys are rejected here with a machine-readable reason instead of being
    # silently dropped. Link-pair validation needs the workspace catalog and
    # runs at readout (propose) and at the formalize write gate.
    normalised = normalize_proposal_items(parsed)
    if not _proposal_within_limits(normalised):
        return None
    return normalised
