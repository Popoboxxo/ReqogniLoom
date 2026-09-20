"""Issue #871 / #583 — requirement rationale + source as first-class attributes.

IEEE 29148 §5.2.6 asks for a *rationale* on every requirement; INCOSE adds the
requirement's *source/origin*. Both are model fields now (not free text buried
in `description`), surfaced through the definition-driven form because
`introspect_core_attributes` turns them into core attributes.

`owner` and `priority` (also named by #871) already exist as Artifact-level
system fields; the last test pins that they stay introspected, so the issue's
remaining two attributes are covered.
"""
from __future__ import annotations

import pytest

from application.requirement_service import RequirementService
from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    introspect_core_attributes,
)
from persistence.tests.factories import active_tenant, editor_ctx, make_workspace

pytestmark = pytest.mark.django_db


def test_create_persists_rationale_and_source():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)

        req = RequirementService().create_requirement(
            workspace_id=ws.id,
            title="System shall boot in 2s",
            ctx=ctx,
            rationale="Boot latency is the top driver.",
            source="Stakeholder workshop 2026-09-18",
        )

        assert req.rationale == "Boot latency is the top driver."
        assert req.source == "Stakeholder workshop 2026-09-18"

        req.refresh_from_db()
        assert req.rationale == "Boot latency is the top driver."
        assert req.source == "Stakeholder workshop 2026-09-18"


def test_create_defaults_both_to_empty_string():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)

        req = RequirementService().create_requirement(
            workspace_id=ws.id, title="Plain", ctx=ctx
        )

        assert req.rationale == ""
        assert req.source == ""


def test_update_persists_rationale_and_source():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)
        svc = RequirementService()
        req = svc.create_requirement(workspace_id=ws.id, title="R", ctx=ctx)

        svc.update_requirement(
            requirement_id=req.id,
            ctx=ctx,
            rationale="Because it is measurable.",
            source="ISO 29148 review",
        )

        req.refresh_from_db()
        assert req.rationale == "Because it is measurable."
        assert req.source == "ISO 29148 review"


def test_introspection_exposes_rationale_source_owner_priority():
    """#871's four attributes are all introspected as core Requirement attributes.

    rationale/source are new model columns; owner/priority already live on the
    Artifact and arrive via ARTIFACT_LEVEL_CORE_ATTRIBUTES.
    """
    names = {
        attribute["name"]
        for attribute in introspect_core_attributes("Requirement", "standard")
    }
    assert {"rationale", "source", "owner", "priority"} <= names
