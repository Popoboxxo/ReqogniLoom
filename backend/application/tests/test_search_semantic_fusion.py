"""Tests for the Task 9 semantic search pass + RRF fusion (REQ-L2-VS-004).

``SearchService._search_entity_type`` fuses three passes for "Requirement":
full-text, lexical, and cosine-similarity over ``Requirement.embedding``.
Requirement is the type with the most fusion coverage here; since T-A3-3 all
three embeddable types (``search_service._EMBEDDABLE_TYPES``) are also public
``type_filter`` entity types, with TraceLink/Icd covered in
``test_search_tracelink_icd.py``.

Dimension note (rewritten for #794): every embedding column is sized from
``persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS``, and Postgres
enforces that width at the DB level on every INSERT/UPDATE. These fixtures
therefore derive their vector lengths from that constant (:data:`_DIM`) rather
than from a literal — the literals they used to carry (1536 for the stored
vector, 384 for "the shape the default provider actually produces") were a
*record of the bug*: they encoded a configuration in which the stored and
generated widths could never agree, so the semantic pass was dead on every
default deployment.

:data:`_MISMATCHED_DIM` is a deliberately wrong width, used by the tests that
still need to prove graceful degradation when an operator points
``EMBEDDING_PROVIDER`` at a provider whose native width differs from the
columns'.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from application.search_service import SearchService, _run_semantic_query
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)

#: The real, DB-enforced column width. Derived, never a literal, so these
#: fixtures cannot silently drift away from the schema again (#794).
_DIM = EMBEDDING_VECTOR_DIMENSIONS

#: A width no embedding column has — simulates a misconfigured provider.
_MISMATCHED_DIM = EMBEDDING_VECTOR_DIMENSIONS + 8


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
            # Matches the real, DB-enforced column dimension -- see the
            # module docstring.
            req.embedding = [0.5] * _DIM
            req.save(update_fields=["embedding"])

            ctx = editor_ctx(tenant, ws)
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: [0.5] * _DIM,
            )
            # Query text has NO keyword overlap with the requirement's title
            # or description -- only the semantic pass can find it.
            result = SearchService().search(
                "credential verification process", ctx, workspace_id=ws.id
            )

        assert any(hit.id == str(req.id) for hit in result.results)

    def test_semantic_scores_are_cosine_similarity_in_unit_interval(self):
        """Issue #827: ``1 - CosineDistance`` is clamped into [0, 1] — a
        maximally dissimilar (opposite-direction) embedding scores 0.0, not
        the negative value the raw formula would produce, and an identical
        embedding scores 1.0."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            identical = make_requirement(ws, title="Identical embedding")
            identical.embedding = [0.3] * _DIM
            identical.save(update_fields=["embedding"])
            opposite = make_requirement(ws, title="Opposite embedding")
            opposite.embedding = [-0.3] * _DIM
            opposite.save(update_fields=["embedding"])

            hits = _run_semantic_query("Requirement", [0.3] * _DIM, tenant.id, ws.id)

        scores = {h.id: h.relevance_score for h in hits}
        assert scores[str(identical.id)] == pytest.approx(1.0, abs=1e-4)
        assert scores[str(opposite.id)] == pytest.approx(0.0, abs=1e-4)
        assert all(0.0 <= score <= 1.0 for score in scores.values())

    def test_filtered_semantic_search_is_not_starved_by_other_workspaces(self):
        """Issue #977: a workspace filter must not drop the matching row.

        With HNSW's defaults the index yields ~``ef_search`` (40) *global*
        candidates and the ``workspace_id`` filter is applied afterwards, so a
        small workspace could get an empty result even though its nearest row
        existed. Seed more than 40 competitors in another workspace and assert
        the single matching row still comes back. This is the deterministic
        core of the pgvector flake in ``set-1-core``.
        """
        with active_tenant() as tenant:
            target_ws = make_workspace(tenant)
            other_ws = make_workspace(tenant)
            target = make_requirement(target_ws, title="Target in filtered workspace")
            target.embedding = [0.3] * _DIM
            target.save(update_fields=["embedding"])
            for index in range(60):  # > hnsw.ef_search default (40)
                decoy = make_requirement(other_ws, title=f"Decoy {index}")
                decoy.embedding = [0.3] * _DIM
                decoy.save(update_fields=["embedding"])

            hits = _run_semantic_query(
                "Requirement", [0.3] * _DIM, tenant.id, target_ws.id
            )

        assert [h.id for h in hits] == [str(target.id)]

    def test_rrf_fused_search_scores_stay_in_unit_interval(self, monkeypatch):
        """Issue #827: the third, RRF-fused code path must also emit scores
        within [0, 1] — never a raw ``sum(1/(_RRF_K+rank+1))``."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Fusion bounds requirement")
            req.embedding = [0.5] * _DIM
            req.save(update_fields=["embedding"])
            ctx = editor_ctx(tenant, ws)
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: [0.5] * _DIM,
            )
            result = SearchService().search(
                "Fusion bounds", ctx, workspace_id=ws.id
            )

        assert result.results
        assert any(hit.id == str(req.id) for hit in result.results)
        assert all(0.0 <= hit.relevance_score <= 1.0 for hit in result.results)

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
        """REQ-L3-SEARCH-009: the misconfigured case -- the configured
        embedding provider produces a vector of a different width than the
        stored column (e.g. ``EMBEDDING_PROVIDER=ollama``, 768-dim, against
        384-dim columns). CosineDistance raises a DB-level error the moment it
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
            req.embedding = [0.2] * _DIM
            req.save(update_fields=["embedding"])

            ctx = editor_ctx(tenant, ws)
            # Simulates a non-default provider whose native width does not
            # match the columns'.
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: [0.1] * _MISMATCHED_DIM,
            )

            result = SearchService().search(
                "Exact keyword phrase", ctx, workspace_id=ws.id
            )

        assert any(hit.id == str(req.id) for hit in result.results)

    def test_dimension_mismatch_short_circuits_before_any_db_query(self, monkeypatch, caplog):
        """Final whole-branch review Finding 5: a dimension mismatch must be
        caught BEFORE issuing the DB query (cheap, no DataError, no
        traceback) -- not caught-and-logged AFTER a doomed pgvector query,
        which used to log a full traceback via ``logger.exception``.

        Proven two ways: (1) the Requirement queryset is never even touched
        (patched to raise if called), and (2) the skip is reported at
        WARNING, not swallowed at DEBUG.

        #794 inverted the level assertion here. This branch used to be the
        *shipped default* path, so a DEBUG line was argued to be the
        low-noise choice; in practice that meant the single observable
        symptom of a completely dead semantic search was a log record nobody
        would ever see at production log levels. The columns now match the
        default provider, so reaching this branch at all means a real
        misconfiguration and must be visible.
        """
        import logging

        from application.search_service import _run_semantic_query
        from llm_adapter import embedding_service
        from persistence.models import Requirement

        def _boom(*args, **kwargs):
            raise AssertionError(
                "Requirement.objects.filter must not be called when the "
                "dimension guard already knows the query embedding cannot "
                "match this column's dimension"
            )

        monkeypatch.setattr(Requirement.objects, "filter", _boom)
        # warn_dimension_mismatch dedupes per process; clear the ledger so
        # this test sees the first-occurrence WARNING regardless of which
        # tests ran before it in the same session.
        monkeypatch.setattr(embedding_service, "_warned_dimension_mismatches", set())

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            with caplog.at_level(logging.DEBUG, logger="llm_adapter.embedding_service"):
                hits = _run_semantic_query("Requirement", [0.1] * _MISMATCHED_DIM, tenant.id, ws.id)

        assert hits == []
        assert any(record.levelno == logging.WARNING for record in caplog.records), (
            "a dimension mismatch is now always a misconfiguration and must "
            "be reported at WARNING -- silently degrading at DEBUG is exactly "
            "how #794 stayed invisible"
        )
        assert not any(record.levelno >= logging.ERROR for record in caplog.records), (
            "the guard must short-circuit cleanly, not surface as an "
            "exception/traceback from a doomed pgvector query"
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
            query_vector = [0.9] * _DIM
            # Opposite direction -- cosine distance is maximal (~2.0), i.e.
            # as "unrelated" to the query embedding as a vector can be.
            req_exact.embedding = [-0.9] * _DIM
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

    def test_exact_uid_ranks_first_under_rrf(self, monkeypatch):
        """T-A3-2 / A-L21: an exact uid hit must outrank the RRF list.

        ``REQ-012`` matches the target's uid exactly (lexical tier only -- the
        row carries no embedding). A second, semantically closer requirement
        sits at semantic rank 0 and its title sorts alphabetically first.
        Both accumulate the same single RRF contribution (1/61), so the
        global ``(-score, title)`` tiebreaker used to put the *neighbour*
        first. The exact uid match is pinned above the fused list instead and
        appears exactly once.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            target = make_requirement(
                ws,
                title="Zebra identifier row",
                description="",
                uid="REQ-012",
            )
            neighbour = make_requirement(
                ws,
                title="Alpha semantic neighbour",
                description="",
                uid="REQ-012-NEIGHBOUR",
            )
            query_vector = [0.7] * _DIM
            neighbour.embedding = query_vector
            neighbour.save(update_fields=["embedding"])

            ctx = editor_ctx(tenant, ws)
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: query_vector,
            )
            result = SearchService().search(
                "REQ-012", ctx, workspace_id=ws.id, type_filter=["Requirement"]
            )

        ids_in_order = [hit.id for hit in result.results]
        assert ids_in_order.count(str(target.id)) == 1, (
            "the exact uid hit must appear exactly once -- pinned hits are "
            "removed from the RRF lists they would otherwise be counted in"
        )
        assert ids_in_order[0] == str(target.id), (
            "the exact uid match was not pinned to rank 1 under RRF "
            f"(order: {ids_in_order})"
        )
        assert result.results[0].relevance_score == 1.0

    def test_pin_wins_over_rrf_max_tie(self, monkeypatch):
        """Review finding F1: a full RRF maximum must not displace a pin.

        ``_rrf_fuse`` normalizes by the theoretical maximum
        ``len(rank_lists) / (_RRF_K + 1)``, so a **non-pinned** hit that ranks
        first in all three lists scores exactly 1.0 — the same value a pinned
        exact-uid hit carries. The global ``(-score, title)`` sort then decided
        alphabetically, so the pin lost whenever a rival's title sorted earlier.
        That is the original A-L21 symptom, reachable again through RRF's own
        arithmetic rather than through a scoring scale seam.

        The rival is deliberately NOT pinned and sits at rank 0 in every list
        once the pin is filtered out of them:

        * lexical — title prefix tier (``REQ-012-A`` starts with ``REQ-012``),
          2.5/3.0 ≈ 0.83, i.e. below the 0.9 pin cut;
        * full-text — its description carries the query token as its own word;
        * semantic — its embedding *is* the query vector.

        Its title sorts before the pin's (``REQ-012-A`` < ``Zebra ...``), which
        is what made the tie decide the wrong way.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            target = make_requirement(
                ws, title="Zebra identifier row", description="", uid="REQ-012"
            )
            rival = make_requirement(
                ws,
                title="REQ-012-A",
                description="REQ-012 cross reference.",
            )
            query_vector = [0.7] * _DIM
            rival.embedding = query_vector
            rival.save(update_fields=["embedding"])

            ctx = editor_ctx(tenant, ws)
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: query_vector,
            )
            result = SearchService().search(
                "REQ-012", ctx, workspace_id=ws.id, type_filter=["Requirement"]
            )

        ids_in_order = [hit.id for hit in result.results]
        assert ids_in_order.count(str(target.id)) == 1
        rival_hit = next(hit for hit in result.results if hit.id == str(rival.id))
        assert rival_hit.relevance_score == pytest.approx(1.0), (
            "precondition: the unpinned rival must actually reach the RRF "
            "theoretical maximum, otherwise this test does not exercise the "
            f"tie it is about (score: {rival_hit.relevance_score})"
        )
        assert ids_in_order[0] == str(target.id), (
            "a rival sitting at the RRF maximum (1.0) displaced the pinned "
            f"exact-uid match — pinning is not guaranteed (order: {ids_in_order})"
        )
        assert result.results[0].relevance_score == 1.0


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
class TestSemanticQueryDirectTraceLinkAndIcd:
    """Direct coverage for ``_run_semantic_query``'s TraceLink/Icd branches.

    These tests stay at the semantic-pass level (no ``SearchService.search``
    round trip): the public, permission-scoped search surface for both types is
    covered in ``test_search_tracelink_icd.py``. They pin the raw pass's
    contract -- TraceLink resolves its workspace through ``source``, Icd uses
    its own ``workspace_id`` -- independently of the fusion/visibility layers.
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
                link_type="references",
                embedding=[0.3] * _DIM,
            )

            hits = _run_semantic_query("TraceLink", [0.3] * _DIM, tenant.id, ws.id)

        assert any(h.id == str(link.id) for h in hits)
        # workspace_id is resolved through source.workspace_id (TraceLink has
        # no workspace column of its own) -- assert it round-trips correctly.
        hit = next(h for h in hits if h.id == str(link.id))
        assert hit.workspace_id == str(ws.id)

    def test_icd_semantic_query_finds_matching_embedding(self):
        """Task 28c-2: the embedding lives on the mutable Icd row now.

        It used to sit on the immutable IcdVersion, which is why it had to be
        assigned on the INSERT itself; the header can simply be updated.
        """
        from icd.models import Icd

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            icd = Icd.objects.create(
                workspace_id=ws.id,
                source_element_id=uuid4(),
                target_element_id=uuid4(),
                name="Test ICD",
                semantic_description="A contract description",
                embedding=[0.4] * _DIM,
            )

            hits = _run_semantic_query("Icd", [0.4] * _DIM, tenant.id, ws.id)

        assert any(h.id == str(icd.id) for h in hits)
        hit = next(h for h in hits if h.id == str(icd.id))
        assert hit.workspace_id == str(ws.id)


class TestQdrantEntitySemantics:
    """T-A2-6: the counter-check to A-L19.

    The pgvector semantic pass only reaches the three entity types that carry
    an ``embedding`` column. In Qdrant mode ``query_entities`` supplies semantic
    hits for the types WITHOUT one -- here a ``StakeholderNeed`` that shares no
    term with the query, so neither the full-text nor the lexical pass can find
    it.
    """

    @pytest.mark.django_db(transaction=True)
    def test_qdrant_mode_returns_stakeholder_need_semantic_hit(self, monkeypatch):
        from application.vector_port import QdrantVectorPort
        from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
        from persistence.models import Artifact, StakeholderNeed
        from persistence.qdrant_config import (
            build_collection_alias,
            resolve_qdrant_config,
        )

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="StakeholderNeed"
            )
            need = StakeholderNeed.objects.create(
                tenant=tenant, artifact=artifact, title="Mobile push"
            )

            client = FakeQdrantClient()
            client.upsert(
                collection_name=build_collection_alias(
                    "reqlo", tenant.id, workspace_id=ws.id, scope="workspace"
                ),
                points=[
                    FakeQdrantModels.PointStruct(
                        id=str(need.id),
                        vector={
                            "dense": [1.0] * _DIM,
                            "bm25": FakeQdrantModels.Document(
                                text="mobile push", model="qdrant/bm25"
                            ),
                        },
                        payload={
                            "entity_id": str(need.id),
                            "entity_type": "StakeholderNeed",
                            "tenant_id": str(tenant.id),
                            "workspace_id": str(ws.id),
                        },
                    )
                ],
            )
            port = QdrantVectorPort(
                client=client,
                models_module=FakeQdrantModels,
                config=resolve_qdrant_config(
                    base_url="http://qdrant.test", collection_prefix="reqlo"
                ),
            )
            monkeypatch.setattr(
                "application.search_service.get_fallback_vector_port", lambda: port
            )
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: [1.0] * _DIM,
            )

            ctx = editor_ctx(tenant, ws)
            # No term overlap with the need's title: only the semantic pass can
            # produce this hit.
            result = SearchService().search(
                "smartphone alerts", ctx, workspace_id=ws.id,
                type_filter=["StakeholderNeed"],
            )

        assert [hit.id for hit in result.results] == [str(need.id)]
        assert result.results[0].artifact_type == "StakeholderNeed"
        assert result.vector_backend == "qdrant"
        assert result.degraded is False
        assert result.degraded_reason == ""


class TestDegradedFallbackVisibility:
    """QR-S07 on the DEGRADED path (T-A2-7): fallback hits are READ-checked.

    ``FallbackVectorPort`` serves a Qdrant outage from ``PgVectorVectorPort``,
    which ignores ``ctx`` -- so without an explicit gate the degraded response
    carries hits the Qdrant path would have dropped (item-level ``none`` rules,
    ``OUTDATED`` rows). That made the permission set depend on whether the
    server-side BM25 inference happened to fail: any client able to trigger the
    outage picked the weaker set. ``SearchService`` now routes the hits of a
    degraded fallback through ``hydrate_vector_hits``.

    ``mode="vector"`` isolates the semantic pass, so a dropped hit here can only
    come from the fallback gate (Requirement is not ``permission_scoped``).
    """

    @staticmethod
    def _outage_port():
        from types import SimpleNamespace

        from application.vector_port import FallbackVectorPort, QdrantVectorPort
        from memory.tests.qdrant_fakes import FakeQdrantModels
        from persistence.qdrant_config import resolve_qdrant_config

        def _unreachable(**_kwargs):
            from application.vector_port import QdrantBackendUnavailableError

            raise QdrantBackendUnavailableError("qdrant is unreachable")

        primary = QdrantVectorPort(
            client=SimpleNamespace(query_points=_unreachable),
            models_module=FakeQdrantModels,
            config=resolve_qdrant_config(base_url="http://qdrant.test"),
        )
        return FallbackVectorPort(primary)

    @pytest.mark.django_db(transaction=True)
    def test_fallback_drops_item_denied_hit(self, monkeypatch):
        from auth_tenancy.models import ItemPermission
        from persistence.tests.factories import ctx_for_user, make_user

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            denied = make_requirement(ws, title="Item-level denied")
            denied.embedding = [0.3] * _DIM
            denied.save(update_fields=["embedding"])
            visible = make_requirement(ws, title="Visible")
            visible.embedding = [0.3] * _DIM
            visible.save(update_fields=["embedding"])

            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("editor",))
            ItemPermission.objects.create(
                tenant=tenant,
                user=user,
                workspace=ws,
                artifact_id=denied.artifact_id,
                permission_level="none",
            )
            port = self._outage_port()
            monkeypatch.setattr(
                "application.search_service.get_fallback_vector_port", lambda: port
            )
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: [0.3] * _DIM,
            )

            result = SearchService().search(
                "anything",
                ctx,
                workspace_id=ws.id,
                type_filter=["Requirement"],
                mode="vector",
            )

        ids = {hit.id for hit in result.results}
        assert str(denied.id) not in ids  # the degraded path must not bypass READ
        assert str(visible.id) in ids
        assert result.degraded is True
        assert result.degraded_reason == "qdrant_unavailable"
        assert result.vector_backend == "pgvector"

    @pytest.mark.django_db(transaction=True)
    def test_fallback_drops_outdated_hit(self, monkeypatch):
        from persistence.models import Artifact, LifecycleStatus

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            outdated = make_requirement(ws, title="Soft-deleted")
            outdated.embedding = [0.3] * _DIM
            outdated.save(update_fields=["embedding"])
            live = make_requirement(ws, title="Live")
            live.embedding = [0.3] * _DIM
            live.save(update_fields=["embedding"])
            Artifact.objects.filter(id=outdated.artifact_id).update(
                lifecycle_status=LifecycleStatus.OUTDATED
            )

            ctx = editor_ctx(tenant, ws)
            port = self._outage_port()
            monkeypatch.setattr(
                "application.search_service.get_fallback_vector_port", lambda: port
            )
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: [0.3] * _DIM,
            )

            result = SearchService().search(
                "anything",
                ctx,
                workspace_id=ws.id,
                type_filter=["Requirement"],
                mode="vector",
            )

        ids = {hit.id for hit in result.results}
        assert str(outdated.id) not in ids  # pgvector alone keeps OUTDATED rows
        assert str(live.id) in ids
        assert result.degraded is True


class TestCrossTypeSemanticFailureIsReported:
    """T-A2-7: a failing cross-type leg must not look like "no results".

    ``_port_entity_hits`` used to swallow the exception and return ``{}``
    without touching ``degraded`` -- so a Qdrant-side failure was
    indistinguishable, on the wire, from a backend that has no cross-type index
    at all (pgvector). The request served partial semantic results; it now says
    so with a reason of its own.
    """

    @pytest.mark.django_db(transaction=True)
    def test_cross_type_query_failure_sets_distinct_degraded_reason(self, monkeypatch):
        class _FailingEntityPort:
            """Cross-type queries fail; nothing else is exercised here."""

            supports_entity_queries = True
            degraded = False
            degraded_reason = ""
            vector_backend = "qdrant"

            def query_entities(self, **_kwargs):
                raise RuntimeError("collection is broken")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            port = _FailingEntityPort()
            monkeypatch.setattr(
                "application.search_service.get_fallback_vector_port", lambda: port
            )
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: [0.3] * _DIM,
            )

            result = SearchService().search(
                "anything",
                ctx,
                workspace_id=ws.id,
                type_filter=["StakeholderNeed"],
                mode="vector",
            )

        assert result.degraded is True
        # Distinct from the outage token: no fallback happened, so the backend
        # keeps its name and only the semantic cross-type leg is missing.
        assert result.degraded_reason == "cross_type_query_failed"
        assert result.vector_backend == "qdrant"
        assert result.results == []
