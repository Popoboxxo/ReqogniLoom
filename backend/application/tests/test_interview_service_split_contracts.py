"""R2S-010 split contracts for ``application.interview_service``.

The god-service was split into cohesive mixins. This module pins the parts that
are observable to callers but easy to break silently during a structural move:

* the public import path and the complete method surface of ``InterviewService``;
* identity of the re-exported validation helpers and service constants;
* exception identity/subclass relationships (transport error mapping is by
  exact type in the REST/MCP layers);
* the DTO values carried in interview events and session status/kind fields.

No database is needed: these are import-time contracts.
"""
from __future__ import annotations

from application import interview_service as core
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.interview_formalize_service import InterviewFormalizationMixin
from application.interview_grounding_service import (
    GROUNDING_RANK_PROMPT_TEMPLATE_NAME,
    InterviewGroundingMixin,
)
from application.interview_housekeeping_service import (
    ABANDONED_TTL,
    InterviewHousekeepingMixin,
)
from application.interview_multi_formalize_service import (
    _DIAGRAM_REF_LINK_TYPE,
    _RESERVED_PROPOSAL_FIELDS,
    _SHORT_STRING_FIELDS,
    MAX_PROPOSAL_CONTAINER_ITEMS,
    MAX_PROPOSAL_STRING_LENGTH,
    MAX_PROPOSAL_TITLE_LENGTH,
    InterviewMultiFormalizationMixin,
    _validate_confirmed_proposal,
    validate_confirmed_proposal_fields,
)
from application.interview_session_service import InterviewSessionMixin
from application.interview_transcript_service import (
    TRANSCRIPT_WINDOW_TURNS,
    InterviewTranscriptMixin,
)
from application.models import DomainEventOutbox
from persistence.errors import NotFoundError as PersistenceNotFoundError
from persistence.errors import PermissionDeniedError as PersistencePermissionDeniedError
from persistence.errors import ValidationError as PersistenceValidationError
from persistence.models import InterviewSession

# Captured from the 2776-line service before the split. Adding/removing a name
# here is a deliberate API change and must be accompanied by a transport update.
EXPECTED_METHODS = frozenset({
    "_abandon_stale_sessions", "_apply_extracted_interview_fields",
    "_assert_interview_complete", "_assert_known_session_kind",
    "_assert_session_shape", "_chat_turn_prompt", "_complete_chat_turn",
    "_complete_multi_formalization_workflow",
    "_complete_single_formalization_workflow", "_compress_transcript_if_needed",
    "_create_proposal_items", "_create_proposal_trace_links",
    "_current_phase_and_missing", "_find_protocol_field", "_formalize_multi",
    "_formalize_single", "_generate_multi_chat_turn", "_get_session",
    "_ids_in_engine_state", "_lazily_abandon_if_stale",
    "_lock_in_progress_session", "_merge_ai_scores", "_parse_chat_turn_reply",
    "_parse_score_map", "_rank_candidates_with_ai", "_record_multi_formalization",
    "_record_single_formalization", "_reject_diagram_ref_links",
    "_require_formalization_title", "_resolve_provider", "_serialise_field",
    "_start_multi_session", "_start_single_session", "_structural_candidates",
    "_summarise_transcript_overflow", "_validate_enum_value",
    "_validate_field_value_type", "_validate_number_value",
    "_validate_text_value", "_write_formalization_artifacts",
    "_write_single_artifact", "abandon", "answer", "formalize",
    "generate_chat_turn", "get", "get_state", "grounding_context",
    "list_sessions", "propose", "provenance_session_id", "set_target", "start",
})


def test_public_class_import_path_and_surface_unchanged():
    """Every former ``InterviewService`` method is still reachable on the class."""
    service = core.InterviewService
    assert service.__name__ == "InterviewService"
    assert service.__module__ == "application.interview_service"
    assert issubclass(service, ServiceBase)
    actual = {name for name in dir(service) if not name.startswith("__")}
    owned = actual - {name for name in dir(ServiceBase) if not name.startswith("__")}
    assert owned == EXPECTED_METHODS


def test_mixin_composition_and_responsibility_ownership():
    """The composition order is explicit and each seam owns its methods."""
    mro = [klass.__name__ for klass in core.InterviewService.__mro__]
    assert mro == [
        "InterviewService",
        "InterviewFormalizationMixin",
        "InterviewMultiFormalizationMixin",
        "InterviewGroundingMixin",
        "InterviewSessionMixin",
        "InterviewHousekeepingMixin",
        "InterviewTranscriptMixin",
        "ServiceBase",
        "object",
    ]
    ownership = {
        InterviewFormalizationMixin: ("formalize", "_lock_in_progress_session"),
        InterviewMultiFormalizationMixin: ("_formalize_multi",),
        InterviewGroundingMixin: ("grounding_context", "_resolve_provider"),
        InterviewSessionMixin: ("start", "answer", "_validate_field_value_type"),
        InterviewHousekeepingMixin: ("abandon", "list_sessions", "provenance_session_id"),
        InterviewTranscriptMixin: ("_compress_transcript_if_needed",),
    }
    for mixin, names in ownership.items():
        for name in names:
            member = getattr(mixin, name)
            assert member.__module__ == mixin.__module__, (name, member.__module__)
    # The proposal gate is a module-level helper, not a mixin method.
    assert _validate_confirmed_proposal.__module__ == (
        "application.interview_multi_formalize_service"
    )


def test_module_level_reexports_are_identical_objects():
    """Re-export shims preserve the old import path by identity, not by copy."""
    assert core._validate_confirmed_proposal is _validate_confirmed_proposal
    assert core.validate_confirmed_proposal_fields is validate_confirmed_proposal_fields
    assert core._RESERVED_PROPOSAL_FIELDS is _RESERVED_PROPOSAL_FIELDS
    assert core._SHORT_STRING_FIELDS is _SHORT_STRING_FIELDS
    assert core._DIAGRAM_REF_LINK_TYPE is _DIAGRAM_REF_LINK_TYPE
    assert core.MAX_PROPOSAL_STRING_LENGTH == MAX_PROPOSAL_STRING_LENGTH
    assert core.MAX_PROPOSAL_TITLE_LENGTH == MAX_PROPOSAL_TITLE_LENGTH
    assert core.MAX_PROPOSAL_CONTAINER_ITEMS == MAX_PROPOSAL_CONTAINER_ITEMS
    assert core.GROUNDING_RANK_PROMPT_TEMPLATE_NAME == GROUNDING_RANK_PROMPT_TEMPLATE_NAME
    assert core.ABANDONED_TTL == ABANDONED_TTL
    assert core.TRANSCRIPT_WINDOW_TURNS == TRANSCRIPT_WINDOW_TURNS


def test_exception_identity_and_subclasses_unchanged():
    """REST/MCP map errors by exact type; the split must not create new classes."""
    assert core.ValidationError is ValidationError is PersistenceValidationError
    assert core.NotFoundError is NotFoundError is PersistenceNotFoundError
    assert PermissionDeniedError is PersistencePermissionDeniedError
    assert [base.__name__ for base in ValidationError.__mro__] == [
        "ValidationError", "ValueError", "Exception", "BaseException", "object",
    ]
    assert [base.__name__ for base in NotFoundError.__mro__] == [
        "NotFoundError", "LookupError", "Exception", "BaseException", "object",
    ]
    from application.base import BaselineGateBlockedError

    assert issubclass(BaselineGateBlockedError, ValidationError)
    assert BaselineGateBlockedError not in (
        ValidationError, NotFoundError, PermissionDeniedError,
    )


def test_interview_dto_values_unchanged():
    """Event-type and session status/kind DTO values are wire-visible."""
    assert {
        (event.name, event.value)
        for event in DomainEventOutbox.EventType
        if event.name.startswith("INTERVIEW_")
    } == {
        ("INTERVIEW_ABANDONED", "InterviewAbandoned"),
        ("INTERVIEW_CHAT_TURN", "InterviewChatTurn"),
        ("INTERVIEW_FORMALIZED", "InterviewFormalized"),
    }
    assert InterviewSession.STATUS_IN_PROGRESS == "in_progress"
    assert InterviewSession.STATUS_COMPLETED == "completed"
    assert InterviewSession.STATUS_ABANDONED == "abandoned"
    assert InterviewSession.SESSION_KIND_SINGLE == "single"
    assert InterviewSession.SESSION_KIND_MULTI == "multi"


def test_patch_target_for_provider_resolution_still_resolves():
    """Tests patch ``application.interview_service.InterviewService._resolve_provider``."""
    assert core.InterviewService._resolve_provider is InterviewGroundingMixin._resolve_provider
