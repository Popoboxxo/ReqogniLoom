"""Canonical prompt-slot registry (spec §3.2).

Before this module the factory defaults lived in three places that each knew
about a different subset: ``persistence.models.PROMPT_TEMPLATE_DEFAULTS`` (3
entries), ``application.ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS`` (the
11-slot merge) and ``application.interview_protocol.INTERVIEW_PROTOCOL_DEFAULTS``
(one per in-scope artifact type). This module merges them into ONE lookup and
adds the piece the spec asks for: which ``data`` variables each slot's render
call supplies (``PromptSlotSpec.data_variables``).

``config`` variables are deliberately NOT declared per slot — they are
resolved wholesale for the active tenant/workspace on every render call (see
``application.prompt_resolver.resolve_and_render``), so an admin can
reference a newly created ``config`` variable in any prompt body without a
developer "enabling" it first.

The two source registries are imported lazily inside :func:`get_prompt_slots`
because ``ai_derivation_service`` imports back into ``application/*`` — the
same lazy-import idiom ``SettingsService._all_prompt_defaults`` already uses
for this exact cycle.

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class PromptSlotSpec:
    """One prompt slot: its factory body plus the data variables it is fed."""

    name: str
    default_content: str
    data_variables: Tuple[str, ...]


#: Every ``interview.protocol.<Type>`` slot is rendered with the same set.
#:
#: ``memory_context`` (RFC #1002 PR C) is part of this shared set because the
#: multi-artifact protocol (``interview.protocol.multi``) is rendered through
#: ``prompt_resolver.resolve_and_render`` and must receive memory like every
#: other AI slot. The per-type YAML protocol slots are only *parsed* as YAML
#: (``interview_protocol.get_protocol`` via ``try_resolve_template_content``),
#: never rendered, so declaring the variable there is inert for them.
INTERVIEW_PROTOCOL_DATA_VARIABLES: Tuple[str, ...] = (
    "artifact_type",
    "phase_name",
    "collected_fields_json",
    "missing_fields_json",
    "grounding_snapshot_json",
    "memory_context",
)

#: Data variables per named slot. Code-bound by definition: the values come
#: from the service that builds the render call, so this map only changes
#: together with that code (spec §3.2 — no junction table).
#:
#: RFC #1002 PR C: every content-generating AI slot declares
#: ``memory_context`` so ``prompt_resolver.resolve_and_render`` auto-computes
#: (and injects) the retrieved workspace/artifact/user memory block for it.
#: The one deliberate exception is ``interview.transcript_summary`` -- it
#: compacts an already-supplied transcript and must not introduce outside
#: facts into that digest, so it stays memory-free.
_DATA_VARIABLES_BY_SLOT: Dict[str, Tuple[str, ...]] = {
    "need_to_sysreq": ("need_title", "need_description", "memory_context"),
    "sysreq_to_arch_assign": (
        "req_title",
        "req_description",
        "arch_elements_json",
        "memory_context",
    ),
    "sysreq_decompose_next_level": (
        "req_title",
        "req_description",
        "arch_elements_json",
        "memory_context",
    ),
    "goal_aggregate": ("goals", "memory_context"),
    "testcase_derive": ("req_title", "req_description", "memory_context"),
    "architecture_to_risk": ("ae_title", "ae_description", "memory_context"),
    "workspace_to_glossary": ("workspace_text", "memory_context"),
    "decision_to_adr": ("decision_description", "memory_context"),
    "bundle_compression": ("bundle_markdown", "memory_context"),
    "interview.grounding_rank": (
        "answers_text",
        "candidates_json",
        "memory_context",
    ),
    "interview.chat_turn": (
        "artifact_type",
        "transcript_json",
        # L2.4: the compressed digest of turns that fell out of the sliding
        # window. A workspace-custom chat_turn template that omits this
        # placeholder still renders (render_template substitutes placeholders
        # individually and ignores unused values) -- it just loses the older
        # context, which is the pre-L2.4 behaviour, not a crash.
        "transcript_summary",
        "current_phase_fragment",
        "missing_fields_json",
        "grounding_snapshot_json",
        "user_message",
        # memory plan Task 6: single-mode generate_chat_turn() only -- see
        # InterviewService.generate_chat_turn's build_memory_context() call.
        "memory_context",
    ),
    "interview.transcript_summary": ("previous_summary", "overflow_json"),
    "architecture_decompose_tree": ("element_title", "memory_context"),
    # RFC #1002 PR C: the extractor itself gets the artifact context (so it can
    # scope facts to an artifact) and the workspace language (so facts are
    # emitted in one language and tagged with it). Deliberately NOT
    # memory_context -- feeding retrieved memory back into the extractor that
    # writes memory is a feedback loop, not context.
    "memory.extract": ("interaction_text", "artifact_context", "language"),
}


def get_prompt_slots() -> Dict[str, PromptSlotSpec]:
    """Return the merged factory registry, keyed by slot name.

    Rebuilt per call (cheap dict comprehension over ~20 entries) so a test
    that monkeypatches one of the source registries sees the change — caching
    it would pin whatever the first caller observed.
    """
    from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
    from application.architecture_decompose_service import (
        ARCH_DECOMPOSE_PROMPT_TEMPLATE,
    )
    from application.interview_protocol import INTERVIEW_PROTOCOL_DEFAULTS
    from memory.prompts import MEMORY_PROMPT_DEFAULTS

    merged: Dict[str, str] = {
        **PROMPT_TEMPLATE_DEFAULTS,
        **INTERVIEW_PROTOCOL_DEFAULTS,
        **MEMORY_PROMPT_DEFAULTS,
        # Spec §4: N1 no longer bypasses the catalog — its prompt is a regular
        # slot, editable through AiPromptsSection like every other one.
        "architecture_decompose_tree": ARCH_DECOMPOSE_PROMPT_TEMPLATE,
    }
    slots: Dict[str, PromptSlotSpec] = {}
    for name, content in merged.items():
        if name.startswith("interview.protocol."):
            data_variables = INTERVIEW_PROTOCOL_DATA_VARIABLES
        else:
            data_variables = _DATA_VARIABLES_BY_SLOT.get(name, ())
        slots[name] = PromptSlotSpec(
            name=name, default_content=content, data_variables=data_variables
        )
    return slots


def get_slot_default(name: str) -> str | None:
    """Return the factory body for *name*, or ``None`` for an unknown slot."""
    spec = get_prompt_slots().get(name)
    return spec.default_content if spec is not None else None


def get_slot_data_variables(name: str) -> Tuple[str, ...]:
    """Return the declared data variables of *name* (empty for unknown slots)."""
    spec = get_prompt_slots().get(name)
    return spec.data_variables if spec is not None else ()


__all__ = [
    "INTERVIEW_PROTOCOL_DATA_VARIABLES",
    "PromptSlotSpec",
    "get_prompt_slots",
    "get_slot_data_variables",
    "get_slot_default",
]
