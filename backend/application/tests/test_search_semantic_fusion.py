"""Tests for the Task 9 semantic search pass + RRF fusion (REQ-L2-VS-004).

``SearchService._search_entity_type`` fuses three passes for "Requirement" --
the only one of the three embeddable types (see
``search_service._EMBEDDABLE_TYPES``) that is also a public ``type_filter``
entity type today: full-text, lexical, and (new) cosine-similarity over
``Requirement.embedding``.

Dimension note: ``Requirement.embedding`` is a hardcoded pgvector
``vector(1536)`` column (persistence/migrations/0024_requirement_embedding.py)
-- Postgres enforces that dimension at the DB level on every INSERT/UPDATE,
so a fixture that wants a *findable* stored embedding must use 1536 floats,
not the 384-dim shape the ``mock``/``sentence-transformers`` providers
produce. ``test_semantically_similar_requirement_found_without_keyword_match``
therefore monkeypatches ``generate_embedding`` directly (bypassing the real
provider machinery) so both the stored and the query vector are consistently
1536-dim -- this proves the *fusion logic* in isolation from which embedding
provider happens to be configured. The dimension-mismatch test below covers
the realistic case (provider dimension != column dimension) explicitly, since
that -- not a clean match -- is what the shipped default configuration
(``EMBEDDING_PROVIDER=sentence-transformers``, 384-dim) actually produces
against these 1536-dim columns.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from application.search_service import SearchService, _run_semantic_query
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)


@pytest.mark.django_db
class TestSemanticFusion:
    def test_semantically_similar_requirement_found_without_keyword_match(self, monkeypatch):
        """A requirement with no keyword overlap with the query is still
        found once a matching-dimension embedding lets the semantic pass
        contribute a hit -- provable only via the new, RRF-fused third pass.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(
                ws,
                title="User authentication flow",
                description="Login and session handling",
            )
            # Matches the real column dimension (1536) -- see module
            # docstring for why this can't be the provider's native 384-dim
            # shape.
            req.embedding = [0.5] * 1536
            req.save(update_fields=["embedding"])

            ctx = editor_ctx(tenant, ws)
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: [0.5] * 1536,
            )
            # Query text has NO keyword overlap with the requirement's title
            # or description -- only the semantic pass can find it.
            result = SearchService().search(
                "credential verification process", ctx, workspace_id=ws.id
            )

        assert any(hit.id == str(req.id) for hit in result.results)

    def test_fusion_does_not_break_existing_keyword_search(self, monkeypatch):
        """REQ-L3-SEARCH-009 regression pin: when the semantic pass
        contributes nothing (no stored embedding here), pure-keyword search
        must produce the same result as before Task 9 (the pre-existing
        max-score merge path, _merge_hits)."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            make_requirement(ws, title="Exact keyword match requirement")
            ctx = editor_ctx(tenant, ws)
            result = SearchService().search("Exact keyword match", ctx, workspace_id=ws.id)

        assert len(result.results) == 1

    def test_semantic_pass_degrades_gracefully_on_dimension_mismatch(self, monkeypatch):
        """REQ-L3-SEARCH-009: the realistic case -- the configured embedding
        provider produces a vector of a different dimension than the stored
        1536-dim column (e.g. the new default, sentence-transformers, is
        384-dim). CosineDistance raises a DB-level error the moment it
        compares against a real, non-NULL stored row; search() must still
        return the fulltext/lexical hits, not propagate the exception (and
        must not poison the surrounding transaction for other entity types
        searched afterwards -- see _run_semantic_query's docstring)."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Exact keyword phrase requirement")
            # A real, correctly-dimensioned stored embedding -- so the
            # queryset actually reaches a non-NULL row and pgvector has to
            # evaluate the (deliberately wrong-dimension) comparison below,
            # instead of short-circuiting on an empty result set.
            req.embedding = [0.2] * 1536
            req.save(update_fields=["embedding"])

            ctx = editor_ctx(tenant, ws)
            # Simulates the real default provider's 384-dim output against
            # the 1536-dim column.
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: [0.1] * 384,
            )

            result = SearchService().search(
                "Exact keyword phrase", ctx, workspace_id=ws.id
            )

        assert any(hit.id == str(req.id) for hit in result.results)


@pytest.mark.django_db
class TestSemanticQueryDirectTraceLinkAndIcdVersion:
    """Direct coverage for ``_run_semantic_query``'s TraceLink/IcdVersion
    branches.

    Neither type is wired into ``SearchService.search()``'s public
    ``type_filter`` surface (see ``search_service._EMBEDDABLE_TYPES``'s
    docstring: they have no fulltext/lexical ``_TableSpec`` and no natural
    "title", so exposing them as new searchable types is a separate product/
    API-surface decision this task deliberately scopes out). These tests
    exist to prove the "Consumes TraceLink.embedding / IcdVersion.embedding"
    part of this task's interface contract is real and correct, independent
    of that wiring decision.
    """

    def test_tracelink_semantic_query_finds_matching_embedding(self):
        from persistence.models import Artifact, TraceLink

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            source = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="requirement"
            )
            target = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="requirement"
            )
            link = TraceLink.objects.create(
                source=source,
                target=target,
                link_type="traces",
                embedding=[0.3] * 1536,
            )

            hits = _run_semantic_query("TraceLink", [0.3] * 1536, tenant.id, ws.id)

        assert any(h.id == str(link.id) for h in hits)
        # workspace_id is resolved through source.workspace_id (TraceLink has
        # no workspace column of its own) -- assert it round-trips correctly.
        hit = next(h for h in hits if h.id == str(link.id))
        assert hit.workspace_id == str(ws.id)

    def test_icdversion_semantic_query_finds_matching_embedding(self):
        from icd.models import Icd, IcdVersion

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            icd = Icd.objects.create(
                workspace_id=ws.id,
                source_element_id=uuid4(),
                target_element_id=uuid4(),
                name="Test ICD",
            )
            # embedding must be set on the INSERT itself: IcdVersion is
            # immutable (BEFORE UPDATE/DELETE trigger, icd/migrations/
            # 0001_initial.py) -- a subsequent .save(update_fields=...) would
            # raise "IcdVersion records are immutable".
            version = IcdVersion.objects.create(
                icd=icd,
                version_number=1,
                semantic_description="A contract description",
                embedding=[0.4] * 1536,
            )

            hits = _run_semantic_query("IcdVersion", [0.4] * 1536, tenant.id, ws.id)

        assert any(h.id == str(version.id) for h in hits)
        hit = next(h for h in hits if h.id == str(version.id))
        assert hit.workspace_id == str(ws.id)
