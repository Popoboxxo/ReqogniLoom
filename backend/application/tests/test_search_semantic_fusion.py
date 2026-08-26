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

    def test_dimension_mismatch_short_circuits_before_any_db_query(self, monkeypatch, caplog):
        """Final whole-branch review Finding 5: a dimension mismatch must be
        caught BEFORE issuing the DB query (cheap, no DataError, no
        traceback) -- not caught-and-logged AFTER a doomed pgvector query,
        which used to log a full traceback via ``logger.exception`` on every
        single request under the shipped default config.

        Proven two ways: (1) the Requirement queryset is never even touched
        (patched to raise if called), and (2) no ERROR-level log record is
        produced -- only the low-noise ``logger.debug`` mirroring
        ``RequirementService._generate_and_store_embedding``'s write-side
        guard (Task 12).
        """
        import logging

        from application.search_service import _run_semantic_query
        from persistence.models import Requirement

        def _boom(*args, **kwargs):
            raise AssertionError(
                "Requirement.objects.filter must not be called when the "
                "dimension guard already knows the query embedding cannot "
                "match this column's dimension"
            )

        monkeypatch.setattr(Requirement.objects, "filter", _boom)

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            with caplog.at_level(logging.DEBUG, logger="application.search_service"):
                hits = _run_semantic_query("Requirement", [0.1] * 384, tenant.id, ws.id)

        assert hits == []
        assert not any(record.levelno >= logging.WARNING for record in caplog.records), (
            "dimension mismatch must degrade at DEBUG level, not "
            "WARNING/ERROR/EXCEPTION -- this is an expected, handled "
            "condition under the shipped default config, not an anomaly"
        )
        assert any("dimension mismatch" in record.message for record in caplog.records)

    def test_exact_lexical_match_still_ranks_correctly_when_rrf_activates(self, monkeypatch):
        """Review finding 2: the RRF-vs-_merge_hits scoring-scale seam.

        Two Requirements: ``req_exact`` has an exact title match for the
        query AND a stored embedding that is semantically UNRELATED to it
        (opposite direction -- maximal cosine distance); ``req_semantic`` has
        no keyword overlap at all but a stored embedding that closely matches
        the query embedding. Because a semantic hit exists for this entity
        type (req_semantic), _search_entity_type activates RRF fusion for
        BOTH requirements -- including req_exact, whose lexical score would
        otherwise be pinned at the dominant >= 1.5 tier by _merge_hits.

        This asserts the design decision documented in _rrf_fuse's docstring
        and the Task 9 report actually holds under real RRF arithmetic:
        req_exact appears in ALL THREE rank lists for this type (lexical
        rank 0, full-text rank 0, semantic rank 1 -- last, since its
        embedding is deliberately the worst match) while req_semantic only
        appears in the semantic list (rank 0). Fused:
            req_exact:    3 * 1/(60+rank+1) contributions
                          = 1/61 (lexical) + 1/61 (fulltext) + 1/62 (semantic)
                          ~= 0.0489
            req_semantic: 1/61 (semantic only) ~= 0.0164
        so req_exact must still win. If this assertion ever fails, that is a
        real regression in the scoping decision, not a flaky test -- do not
        loosen it to pass.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req_exact = make_requirement(
                ws,
                title="Unique Exact Phrase Match",
                description="Nothing semantically related here.",
            )
            req_semantic = make_requirement(
                ws,
                title="Totally unrelated requirement title",
                description="Some other unrelated description text.",
            )
            query_vector = [0.9] * 1536
            # Opposite direction -- cosine distance is maximal (~2.0), i.e.
            # as "unrelated" to the query embedding as a vector can be.
            req_exact.embedding = [-0.9] * 1536
            req_exact.save(update_fields=["embedding"])
            req_semantic.embedding = query_vector
            req_semantic.save(update_fields=["embedding"])

            ctx = editor_ctx(tenant, ws)
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: query_vector,
            )

            result = SearchService().search(
                "Unique Exact Phrase Match", ctx, workspace_id=ws.id
            )

        ids_in_order = [hit.id for hit in result.results]
        assert str(req_exact.id) in ids_in_order
        assert str(req_semantic.id) in ids_in_order
        assert ids_in_order.index(str(req_exact.id)) < ids_in_order.index(
            str(req_semantic.id)
        ), (
            "RRF fusion let the exact lexical/title match rank BELOW a "
            "semantic-only match for the same entity type -- the scoping "
            "decision in _rrf_fuse's docstring does not hold here."
        )


@pytest.mark.django_db
class TestEmbeddingGenerationGatedByTypeFilter:
    """Review finding 1: generate_embedding() must not run at all when
    ``effective_types`` contains no embeddable type -- it is not free in
    general (a real network round-trip for the openai provider, model
    inference for sentence-transformers), so a caller filtering to a
    non-embeddable type (e.g. TestCase, which has a _TableSpec but no
    embedding column) must not pay that cost."""

    def test_generate_embedding_not_called_when_type_filter_excludes_embeddable_types(
        self, monkeypatch
    ):
        calls: list[str] = []
        monkeypatch.setattr(
            "application.search_service.generate_embedding",
            lambda text: calls.append(text) or None,
        )
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            SearchService().search(
                "anything", ctx, workspace_id=ws.id, type_filter=["TestCase"]
            )

        assert calls == []

    def test_generate_embedding_is_called_when_type_filter_includes_an_embeddable_type(
        self, monkeypatch
    ):
        calls: list[str] = []
        monkeypatch.setattr(
            "application.search_service.generate_embedding",
            lambda text: calls.append(text) or None,
        )
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            SearchService().search(
                "anything", ctx, workspace_id=ws.id, type_filter=["Requirement"]
            )

        assert calls == ["anything"]


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
