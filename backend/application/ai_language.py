"""Single source of the language directive for every LLM prompt (E10, §7.6).

Issue #795 first pinned the output language of the content-generating derive
prompts to ``Workspace.language``. That helper lived inside
``AiDerivationService`` and was copied/hand-wired into a handful of sibling
flows -- and several text-producing flows (search summary, quality assessment,
artifact summaries) carried no language directive at all. The result was
language drift: two flows answering the same workspace in two different
languages.

This module replaces those local derivations with ONE resolution and ONE
directive text:

* :func:`resolve_ai_language` -- the explicit workspace setting
  (``Workspace.ai_language``), or ``None`` for ``auto``;
* :func:`effective_ai_language`` -- the resolved ISO 639-1 code, falling back
  from ``auto`` to the content language and finally to ``en``;
* :func:`language_instruction` -- the directive text appended to a rendered
  prompt (the only place that text is built);
* :func:`append_language_instruction` -- appends it exactly once, skipping a
  prompt whose own template already carries a ``{language}`` directive.

``auto`` (the default, and every pre-existing row) reproduces the behaviour of
``AiDerivationService._language_instruction`` byte for byte, so the migration
needs no data change and no prompt snapshot moves.

req_id: REQ-L2-AI-002
"""
from __future__ import annotations

from uuid import UUID

from persistence.models import Workspace

#: Sentinel that means "inherit ``Workspace.language``, then fall back to
#: English". Stored as the default of ``Workspace.ai_language``.
AUTO = "auto"

#: Language codes an explicit setting may take. Anything else (including a
#: hand-edited legacy value) behaves exactly like :data:`AUTO`.
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"de", "en"})

DEFAULT_LANGUAGE = "en"

#: Human-readable language names for the directive. Keyed by ISO 639-1 code;
#: any code not listed here falls back to English, matching
#: ``Workspace.language``'s own factory default.
LANGUAGE_INSTRUCTION_NAMES: dict[str, str] = {
    "de": "German",
    "en": "English",
}

#: The one placeholder a workspace template may use to carry its own language
#: directive. A template containing it receives no second directive.
LANGUAGE_PLACEHOLDER = "{language}"


def _workspace_language_columns(workspace_id: UUID | str | None) -> tuple[str, str]:
    """Return ``(ai_language, content_language)`` for *workspace_id*.

    One primary-key lookup per call: most prompt call sites only hold a
    foreign-key column value, so this is cheaper than threading a fetched
    ``Workspace`` row through every flow. A missing workspace, an empty column
    and an unset RLS scope all answer ``""`` (callers apply their own
    fallback).
    """
    if workspace_id is None:
        return "", ""
    row = (
        Workspace.objects.filter(id=workspace_id)
        .values_list("ai_language", "language")
        .first()
    )
    if row is None:
        return "", ""
    ai_language, content_language = row
    return (
        str(ai_language or "").strip().lower(),
        str(content_language or "").strip().lower(),
    )


def resolve_ai_language(workspace_id: UUID | str | None) -> str | None:
    """Return the explicit AI language for *workspace_id*, or ``None``.

    ``None`` means *auto*: the caller inherits ``Workspace.language`` and then
    English. An unsupported code (anything but ``de``/``en``) degrades to
    ``auto`` instead of raising, so a hand-edited row can never break a prompt.

    Args:
        workspace_id: The workspace whose setting governs the response. ``None``
            returns ``None`` (no resolvable workspace = auto).
    """
    code, _content_language = _workspace_language_columns(workspace_id)
    if code in SUPPORTED_LANGUAGES:
        return code
    return None


def effective_ai_language(workspace_id: UUID | str | None) -> str:
    """Return the ISO 639-1 code every prompt for *workspace_id* must use.

    Resolution order: explicit ``ai_language`` -> ``Workspace.language`` (the
    content language, REQ-133) -> ``en``. Only ``de``/``en`` are supported
    output names; any other content language falls back to English because the
    directive can only name the languages in
    :data:`LANGUAGE_INSTRUCTION_NAMES`.
    """
    code, content_language = _workspace_language_columns(workspace_id)
    if code in SUPPORTED_LANGUAGES:
        return code
    if content_language in LANGUAGE_INSTRUCTION_NAMES:
        return content_language
    return DEFAULT_LANGUAGE


def language_label(workspace_id: UUID | str | None) -> str:
    """Return the human-readable language name for *workspace_id* (e.g. German)."""
    return LANGUAGE_INSTRUCTION_NAMES[effective_ai_language(workspace_id)]


def language_instruction(workspace_id: UUID | str | None) -> str:
    """Return the explicit output-language directive for *workspace_id*.

    The directive is requested for every language -- including English. The
    issue #795 QA session showed an un-instructed provider cannot be trusted
    to default to English on its own (the same ``de`` workspace answered in
    Chinese from one flow and English from another), so "say nothing" is not
    a valid fallback.

    The text is byte-for-byte what ``AiDerivationService._language_instruction``
    produced before S7, so a workspace on ``auto`` keeps every prompt
    snapshot unchanged.

    Returns:
        Directive text to append to a rendered prompt (leading blank line
        included, so it reads as its own paragraph).
    """
    language_name = language_label(workspace_id)
    return _directive_for(language_name)


def _directive_for(language_name: str) -> str:
    return (
        f"\n\nRespond in {language_name}. All generated titles, "
        f"descriptions and other free-text content must be written in "
        f"{language_name}."
    )


def append_language_instruction(
    prompt: str,
    workspace_id: UUID | str | None,
    *,
    template_content: str | None = None,
) -> str:
    """Append :func:`language_instruction` to *prompt*, at most once.

    Two cases must not receive a second directive (§7.6, S7 Step 7):

    * the template already carries its own directive -- signalled by
      ``{language}`` in *template_content*;
    * the rendered prompt already contains this exact directive (e.g. a
      caller appended it before a retry).

    Args:
        prompt: The fully rendered prompt.
        workspace_id: Workspace whose language governs the directive.
        template_content: The *unrendered* template body, when the caller has
            it. A template containing ``{language}`` is treated as already
            instructing the language.
    """
    if template_content is not None and LANGUAGE_PLACEHOLDER in template_content:
        return prompt
    directive = language_instruction(workspace_id)
    if directive in prompt:
        return prompt
    return prompt + directive


__all__ = [
    "AUTO",
    "DEFAULT_LANGUAGE",
    "LANGUAGE_INSTRUCTION_NAMES",
    "LANGUAGE_PLACEHOLDER",
    "SUPPORTED_LANGUAGES",
    "append_language_instruction",
    "effective_ai_language",
    "language_instruction",
    "language_label",
    "resolve_ai_language",
]
