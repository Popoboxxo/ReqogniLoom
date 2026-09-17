"""Tests for the ``glossary`` / ``shares-term`` generator (Issue #377, Task 5).

Deviation from the plan documented in generators/glossary.py's module
docstring: title-text matching against GlossaryTerm.term/.synonyms, not
``uses-term`` TraceLinks (which no service in this codebase ever creates).
"""
from __future__ import annotations

import pytest

from context_graph.tests.conftest import (
    seed_glossary_term,
    seed_requirement,
    seed_workspace,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _clear():
    from persistence.tenancy import TenantContext

    TenantContext.clear_tenant()


class TestGenerateForArtifact:
    def test_two_artifacts_sharing_a_term_produce_one_edge(self):
        from context_graph.generators.glossary import generate_for_artifact

        tenant, workspace, ctx = seed_workspace("cg-glossary")
        seed_glossary_term(tenant, workspace, term="Autopilot")
        req_a = seed_requirement(tenant, workspace, title="Autopilot shall engage", uid="REQ-A")
        req_b = seed_requirement(tenant, workspace, title="Autopilot shall disengage", uid="REQ-B")

        try:
            candidates_a = generate_for_artifact(req_a.artifact_id)
            candidates_b = generate_for_artifact(req_b.artifact_id)
        finally:
            _clear()

        assert len(candidates_a) == 1
        assert len(candidates_b) == 1
        # Undirected pair, canonicalised — both directions produce the exact
        # same (source, target) so the projector's unique constraint never
        # sees two rows for one pair (see module docstring).
        assert (candidates_a[0].source_id, candidates_a[0].target_id) == (
            candidates_b[0].source_id,
            candidates_b[0].target_id,
        )
        assert candidates_a[0].edge_kind == "shares-term"
        assert candidates_a[0].origin == "derived-glossary"
        assert candidates_a[0].confidence == 1.0
        assert candidates_a[0].evidence["terms"][0]["term_name"] == "Autopilot"

    def test_synonym_match(self):
        from context_graph.generators.glossary import generate_for_artifact

        tenant, workspace, ctx = seed_workspace("cg-glossary-syn")
        seed_glossary_term(tenant, workspace, term="Autopilot", synonyms=["AP", "Cruise Control"])
        req_a = seed_requirement(tenant, workspace, title="AP shall engage", uid="REQ-A")
        req_b = seed_requirement(
            tenant, workspace, title="Cruise Control shall disengage", uid="REQ-B"
        )

        try:
            candidates = generate_for_artifact(req_a.artifact_id)
        finally:
            _clear()

        assert len(candidates) == 1
        assert req_b.artifact_id in (candidates[0].source_id, candidates[0].target_id)

    def test_no_shared_terms_yields_empty(self):
        from context_graph.generators.glossary import generate_for_artifact

        tenant, workspace, ctx = seed_workspace("cg-glossary-none")
        seed_glossary_term(tenant, workspace, term="Autopilot")
        req_a = seed_requirement(tenant, workspace, title="Nothing relevant here", uid="REQ-A")

        try:
            candidates = generate_for_artifact(req_a.artifact_id)
        finally:
            _clear()

        assert candidates == []

    def test_whole_word_match_does_not_match_substring(self):
        """"Autopilot" must not match inside "AutopilotXYZ" (word-boundary regex)."""
        from context_graph.generators.glossary import generate_for_artifact

        tenant, workspace, ctx = seed_workspace("cg-glossary-boundary")
        seed_glossary_term(tenant, workspace, term="Auto")
        req_a = seed_requirement(tenant, workspace, title="Automobile requirements", uid="REQ-A")

        try:
            candidates = generate_for_artifact(req_a.artifact_id)
        finally:
            _clear()

        assert candidates == []

    def test_unknown_artifact_returns_empty(self):
        import uuid

        from context_graph.generators.glossary import generate_for_artifact

        tenant, workspace, ctx = seed_workspace("cg-glossary-unknown")
        try:
            assert generate_for_artifact(uuid.uuid4()) == []
        finally:
            _clear()
