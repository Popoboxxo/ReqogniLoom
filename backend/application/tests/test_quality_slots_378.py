"""Plan B / B5-T2 (#378) — the four memory-free ``quality_*`` prompt slots.

The quality-assessment flow (B5-T3) renders ONE artifact through a
``quality_*`` slot and parses a strict JSON verdict from the answer. Three
properties have to hold for that to be safe, and each is pinned here:

* the slots exist in the canonical registry and demand the JSON contract,
* they are memory-free -- neither a declared ``memory_context`` data variable
  nor a memory lookup at render time (ADR-024 HARD_OFF, Plan A's
  ``MEMORY_HARD_OFF_PREFIXES``), so a score judges the artifact, not what the
  model remembers,
* a workspace override of a slot wins over the factory text, and still
  renders ``{memory_context}`` empty when the override names it.

Slot counts are never hard-coded (D-PROMPT): every check is set membership or
a per-slot parametrisation.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.prompt_resolver import resolve_and_render
from application.prompt_slots import (
    get_prompt_slots,
    get_slot_data_variables,
    is_memory_hard_off,
)
from application.settings_service import SettingsService
from auth_tenancy.context import AuthContext
from llm_adapter.timeouts import (
    SINGLE_ARTIFACT_PURPOSES,
    WORKSPACE_WIDE_PURPOSES,
    resolve_timeout_seconds,
    sync_timeout_seconds,
)
from persistence.models import PromptTemplate, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

QUALITY_SLOTS = (
    "quality_requirement",
    "quality_adr",
    "quality_testcase",
    "quality_risk",
)

#: Criteria the factory bodies must name per entity type (plan §B5-T2:
#: IEEE 29148 for requirements, analogous sets for the other three).
CRITERIA_BY_SLOT = {
    "quality_requirement": (
        "atomic",
        "unambiguous",
        "verifiable",
        "complete",
        "necessary",
        "traceable",
    ),
    "quality_adr": (
        "context",
        "alternatives",
        "consequences",
        "decision",
        "traceability",
    ),
    "quality_testcase": (
        "atomic",
        "reproducible",
        "expected result",
        "independent",
        "traceable",
    ),
    "quality_risk": (
        "cause",
        "probability",
        "impact",
        "mitigation",
        "detection",
    ),
}

#: The JSON keys the response contract must name (B5-T2).
CONTRACT_KEYS = ('"score"', '"reasoning"', '"suggestions"', '"criteria"')


@pytest.fixture
def real_workspace_ctx():
    """Real tenant + workspace, no override (the factory slot body renders)."""
    tenant = Tenant.objects.create(
        name="Quality Spy T", slug="quality-spy-t", is_active=True
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="Quality Spy WS")
        yield AuthContext.system(tenant_id=tenant.id), workspace
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def commissioned_ctx():
    """Real tenant + workspace with a workspace override of one quality slot.

    The override deliberately names ``{memory_context}``: B5 must render it
    empty rather than leaving the placeholder behind (R-B5-2 / KA-B-07).
    """
    tenant = Tenant.objects.create(name="Quality T", slug="quality-t", is_active=True)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Quality WS", preset={"name": "standard"}
        )
        PromptTemplate.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            name="quality_requirement",
            content=(
                "Bewerte streng: {artifact_title}\n"
                "Erinnerung: {memory_context}"
            ),
            version=1,
            is_active=True,
        )
        yield AuthContext.system(tenant_id=tenant.id), workspace
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slot_name", QUALITY_SLOTS)
def test_quality_slot_is_registered(slot_name):
    """Membership only -- the suite never pins a total slot count."""
    slots = get_prompt_slots()

    assert slot_name in slots
    assert slots[slot_name].default_content.strip()


@pytest.mark.parametrize("slot_name", QUALITY_SLOTS)
def test_quality_slot_demands_the_json_contract(slot_name):
    body = get_prompt_slots()[slot_name].default_content

    for key in CONTRACT_KEYS:
        assert key in body, f"{slot_name} does not name {key} in its contract"


@pytest.mark.parametrize(("slot_name", "criteria"), CRITERIA_BY_SLOT.items())
def test_quality_slot_names_its_criteria_set(slot_name, criteria):
    body = get_prompt_slots()[slot_name].default_content.lower()

    for criterion in criteria:
        assert criterion in body, f"{slot_name} does not name {criterion!r}"


# ---------------------------------------------------------------------------
# Memory freedom
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slot_name", QUALITY_SLOTS)
def test_quality_slot_is_memory_hard_off(slot_name):
    assert is_memory_hard_off(slot_name) is True


@pytest.mark.parametrize("slot_name", QUALITY_SLOTS)
def test_quality_slot_declares_no_memory_data_variable(slot_name):
    declared = get_slot_data_variables(slot_name)

    assert declared, f"{slot_name} declares no data variables at all"
    assert "memory_context" not in declared
    assert not [name for name in declared if name.startswith("memory_")]


def test_quality_requirement_declares_the_review_fields():
    assert set(get_slot_data_variables("quality_requirement")) == {
        "artifact_title",
        "artifact_description",
        "acceptance_criteria",
        "rationale",
        "verification_method",
    }


@pytest.mark.parametrize(
    "slot_name", [name for name in QUALITY_SLOTS if name != "quality_requirement"]
)
def test_other_quality_slots_declare_the_generic_field_triple(slot_name):
    assert set(get_slot_data_variables(slot_name)) == {
        "artifact_title",
        "artifact_description",
        "artifact_fields_json",
    }


def test_render_never_consults_the_memory_backend(real_workspace_ctx):
    """Non-invocation is the assertion, so the spy is the single allowed one."""
    ctx, workspace = real_workspace_ctx
    # A real workspace is mandatory: with workspace_id=None, _auto_memory_context
    # returns at prompt_resolver.py:287-289 before the slot policy is consulted,
    # so the assertion below would hold even against the wrong seam.
    with patch(
        "memory.context_builder.build_memory_context_result"
    ) as build_memory_context_result:
        rendered = resolve_and_render(
            "quality_requirement",
            ctx,
            workspace.id,
            artifact_title="CSV-Export",
            artifact_description=(
                "Der Export MUSS alle sichtbaren Zeilen enthalten."
            ),
            acceptance_criteria="Alle sichtbaren Zeilen stehen in der Datei.",
            rationale="Berichtspflicht.",
            verification_method="Test",
        )

    build_memory_context_result.assert_not_called()
    assert "CSV-Export" in rendered
    assert "Alle sichtbaren Zeilen stehen in der Datei." in rendered
    # Nothing memory-shaped reached the prompt.
    assert "<memory>" not in rendered


# ---------------------------------------------------------------------------
# Workspace override + HARD_OFF on top of a custom template
# ---------------------------------------------------------------------------


def test_workspace_override_is_effective(commissioned_ctx):
    ctx, workspace = commissioned_ctx

    states = {
        state["name"]: state
        for state in SettingsService().list_prompt_slots(
            ctx, workspace_id=workspace.id
        )
    }
    state = states["quality_requirement"]

    assert state["effective_scope"] == "workspace"
    assert "Bewerte streng" in state["effective_content"]


def test_quality_slots_are_hard_off(commissioned_ctx):
    """A custom body naming ``{memory_context}`` still renders it empty."""
    ctx, workspace = commissioned_ctx

    rendered = resolve_and_render(
        "quality_requirement",
        ctx,
        workspace.id,
        artifact_title="CSV-Export",
        artifact_description="Der Export MUSS alle sichtbaren Zeilen enthalten.",
        acceptance_criteria="Alle sichtbaren Zeilen stehen in der Datei.",
        rationale="Berichtspflicht.",
        verification_method="Test",
    )

    assert "Bewerte streng: CSV-Export" in rendered
    assert "{memory_context}" not in rendered
    memory_line = rendered.split("Erinnerung: ", 1)[1].split("\n", 1)[0]
    assert memory_line == ""


# ---------------------------------------------------------------------------
# Timeout classification
# ---------------------------------------------------------------------------


def test_quality_assess_uses_the_sync_bucket():
    """One artifact, advisory: short budget, never the workspace-wide one."""
    assert "quality_assess" in SINGLE_ARTIFACT_PURPOSES
    assert "quality_assess" not in WORKSPACE_WIDE_PURPOSES
    assert resolve_timeout_seconds("quality_assess") == sync_timeout_seconds()
