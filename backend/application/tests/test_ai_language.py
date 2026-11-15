"""S7 (spec §7.6/E10) — ONE language setting for every LLM prompt.

The unit tests pin the resolution order and the directive text. The ratchet
test at the bottom is the real point of S7: it enumerates every prompt path
of spec §7.6 and fails the moment a new flow appends its own language
instruction (or a path drops the central one), so the next flow cannot drift
back to a local heuristic.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from application.ai_language import (
    LANGUAGE_INSTRUCTION_NAMES,
    append_language_instruction,
    effective_ai_language,
    language_instruction,
    resolve_ai_language,
)
from persistence.models import Tenant
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

_BACKEND = Path(__file__).resolve().parents[2]

#: The directive text exactly as ``AiDerivationService._language_instruction``
#: emitted it before S7 (issue #795). ``auto`` must reproduce it byte for byte.
_PRE_S7_DIRECTIVE = (
    "\n\nRespond in German. All generated titles, descriptions and other "
    "free-text content must be written in German."
)


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="ai-language-tenant", slug="ai-language-tenant")


@pytest.fixture(autouse=True)
def _tenant_scope(tenant: Tenant):
    """RLS needs an active tenant for every workspace lookup in this module."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


def _workspace(tenant: Tenant, **kwargs):
    return make_workspace(tenant, **kwargs)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_explicit_ai_language_wins(tenant: Tenant) -> None:
    ws = _workspace(tenant, language="de", ai_language="en")
    assert resolve_ai_language(ws.id) == "en"
    assert effective_ai_language(ws.id) == "en"


def test_auto_inherits_the_content_language(tenant: Tenant) -> None:
    ws = _workspace(tenant, language="de", ai_language="auto")
    assert resolve_ai_language(ws.id) is None
    assert effective_ai_language(ws.id) == "de"


def test_auto_without_content_language_falls_back_to_english(tenant: Tenant) -> None:
    ws = _workspace(tenant, language="", ai_language="auto")
    assert resolve_ai_language(ws.id) is None
    assert effective_ai_language(ws.id) == "en"


def test_unknown_setting_behaves_like_auto(tenant: Tenant) -> None:
    """A hand-edited/unknown code must never raise or leave the model blank."""
    ws = _workspace(tenant, language="de", ai_language="fr")
    assert resolve_ai_language(ws.id) is None
    assert effective_ai_language(ws.id) == "de"


def test_unknown_workspace_falls_back_to_auto(tenant: Tenant) -> None:
    import uuid

    assert resolve_ai_language(uuid.uuid4()) is None
    assert effective_ai_language(uuid.uuid4()) == "en"
    assert resolve_ai_language(None) is None


# ---------------------------------------------------------------------------
# Directive text
# ---------------------------------------------------------------------------


def test_auto_directive_is_byte_identical_to_pre_s7(tenant: Tenant) -> None:
    ws = _workspace(tenant, language="de", ai_language="auto")
    assert language_instruction(ws.id) == _PRE_S7_DIRECTIVE


def test_english_is_explicit_never_assumed(tenant: Tenant) -> None:
    ws = _workspace(tenant, language="en", ai_language="auto")
    assert language_instruction(ws.id) == (
        "\n\nRespond in English. All generated titles, descriptions and other "
        "free-text content must be written in English."
    )


def test_directive_names_every_supported_language(tenant: Tenant) -> None:
    for code in ("de", "en"):
        ws = _workspace(tenant, language="de", ai_language=code)
        assert LANGUAGE_INSTRUCTION_NAMES[code] in language_instruction(ws.id)


# ---------------------------------------------------------------------------
# Append helper — exactly one directive
# ---------------------------------------------------------------------------


def test_append_adds_the_directive_once(tenant: Tenant) -> None:
    ws = _workspace(tenant, language="de")
    once = append_language_instruction("PROMPT", ws.id)
    twice = append_language_instruction(once, ws.id)
    assert once == "PROMPT" + _PRE_S7_DIRECTIVE
    assert twice == once
    assert twice.count("Respond in German") == 1


def test_append_skips_a_template_that_instructs_the_language_itself(
    tenant: Tenant,
) -> None:
    """Spec §7.6/S7 Step 7: a ``{language}`` template gets no second command."""
    ws = _workspace(tenant, language="de")
    prompt = "Write every fact in the workspace language (de)."
    assert (
        append_language_instruction(
            prompt, ws.id, template_content="Write every fact in ({language})."
        )
        == prompt
    )


# ---------------------------------------------------------------------------
# Ratchet — every prompt path of spec §7.6 uses the one source
# ---------------------------------------------------------------------------

#: path (spec §7.6 row) -> file that renders the prompt -> marker proving the
#: file routes its language through ``application.ai_language``.
_PROMPT_PATHS: dict[str, tuple[str, tuple[str, ...]]] = {
    "derivation (need_to_sysreq, sysreq_decompose_next_level, testcase_derive, "
    "architecture_to_risk, workspace_to_glossary, decision_to_adr)": (
        "application/ai_derivation_service.py",
        ("append_language_directive=True",),
    ),
    "goal_aggregate": (
        "application/main_goal_service.py",
        ("append_language_directive=True",),
    ),
    "architecture_decompose": (
        "application/architecture_decompose_service.py",
        ("append_language_directive=True",),
    ),
    "ai_review": (
        "application/ai_review_service.py",
        ("append_language_instruction(",),
    ),
    "include_summary (SearchSummaryService)": (
        "application/search_summary_service.py",
        ("append_language_directive=True", "effective_ai_language("),
    ),
    "quality_assessment": (
        "application/quality_service.py",
        ("append_language_directive=True", "effective_ai_language("),
    ),
    "artifact_summary / artifact_type_summary": (
        "application/artifact_summary_service.py",
        ("append_language_directive=True", "effective_ai_language("),
    ),
    "memory.extract": (
        "memory/tasks.py",
        ("resolve_ai_language(",),
    ),
}


@pytest.mark.parametrize("path", sorted(_PROMPT_PATHS), ids=sorted(_PROMPT_PATHS))
def test_every_prompt_path_uses_the_central_language_source(path: str) -> None:
    relative, markers = _PROMPT_PATHS[path]
    source = (_BACKEND / relative).read_text(encoding="utf-8")
    for marker in markers:
        assert marker in source, f"{relative} no longer routes through {marker}"


def _python_sources() -> list[Path]:
    return [
        path
        for path in _BACKEND.rglob("*.py")
        if "__pycache__" not in path.parts
        and "migrations" not in path.parts
        and "tests" not in path.parts
    ]


#: A local helper name from before S7 -- ``append_language_instruction`` (the
#: sanctioned helper) must not match, hence the lookbehind.
_LOCAL_DIRECTIVE_HELPER = re.compile(r"(?<!append)_language_instruction")


def test_no_module_builds_its_own_language_directive() -> None:
    """A second directive source is the drift this ratchet exists to prevent."""
    offenders: list[str] = []
    for path in _python_sources():
        if path.name == "ai_language.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "Respond in " in source or _LOCAL_DIRECTIVE_HELPER.search(source):
            offenders.append(str(path.relative_to(_BACKEND)))
    assert offenders == []


#: Files allowed to read ``Workspace.language`` directly. ``ai_language`` reads
#: it as the ``auto`` fallback; ``memory/tasks.py`` also keeps a direct read for
#: its F11 enforcement fallback, but only *after* ``resolve_ai_language``
#: returned ``None`` (the ratchet test above pins that call site).
_DIRECT_LANGUAGE_READERS = {"ai_language.py", "tasks.py"}


def test_no_prompt_path_reads_the_content_language_directly() -> None:
    """Only ``ai_language`` may translate ``Workspace.language`` into a prompt.

    A direct ``values_list("language"`` anywhere else means a new local
    derivation -- exactly the drift the ratchet exists to catch.
    """
    offenders = [
        str(path.relative_to(_BACKEND))
        for path in _python_sources()
        if path.name not in _DIRECT_LANGUAGE_READERS
        and 'values_list("language"' in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
