"""Issue #847: lazy embedding generation on the ``find_similar_requirements`` path.

Before #847, a requirement whose ``embedding`` column was still NULL (created
before embeddings existed, or whose best-effort write path failed) made
``RequirementService.find_similar_requirements`` hard-fail with a
``ValidationError`` -> HTTP 400 ``VALIDATION_ERROR``. The request could never
succeed for that artifact, even though the embedding could have been generated
on demand.

After #847 the service generates the embedding lazily, persists it via the
existing dimension-guarded helper, and uses the freshly persisted vector as the
pgvector query vector (the queryset's ``CosineDistance`` must never receive
``None``). When no vector can be produced -- provider unconfigured, generation
failure, or dimension mismatch -- it degrades to an empty result (HTTP 200),
logging a WARNING instead of raising.

Dimension note (mirrors ``test_search_semantic_fusion.py``): every embedding
column is sized from
``persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS``, derived here
as :data:`_DIM`, never a literal. :data:`_MISMATCHED_DIM` simulates a
misconfigured provider whose native width differs from the column's.

``generate_embedding`` is patched at its source module
(``llm_adapter.embedding_service``) because the service imports it lazily inside
the method body -- there is no module-level name to intercept.
"""
from __future__ import annotations

import pytest

from application.requirement_service import RequirementService
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)

#: The real, DB-enforced column width (single source of truth, #794).
_DIM = EMBEDDING_VECTOR_DIMENSIONS

#: A width no embedding column has -- simulates a misconfigured provider.
_MISMATCHED_DIM = EMBEDDING_VECTOR_DIMENSIONS + 8

_GENERATE_EMBEDDING = "llm_adapter.embedding_service.generate_embedding"


@pytest.mark.django_db
class TestFindSimilarRequirementsLazyEmbedding:
    """#847: generate-persist-search, or degrade to ``[]`` -- never raise."""

    def test_missing_embedding_is_generated_persisted_and_used_as_query_vector(
        self, monkeypatch
    ):
        """(a) No stored embedding -> generate + persist + search succeeds.

        The freshly generated vector must also become the query vector: a
        second requirement seeded with the same vector is the closest hit and
        must rank above one seeded with the opposite vector.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            query_req = make_requirement(ws, title="Query without an embedding")
            closest = make_requirement(ws, title="Closest neighbour")
            farthest = make_requirement(ws, title="Farthest neighbour")

            query_vector = [1.0] * _DIM
            # Same direction -> cosine distance 0.
            closest.embedding = list(query_vector)
            closest.save(update_fields=["embedding"])
            # Opposite direction -> cosine distance 2 (maximally dissimilar).
            farthest.embedding = [-1.0] * _DIM
            farthest.save(update_fields=["embedding"])

            ctx = editor_ctx(tenant, ws)
            monkeypatch.setattr(
                _GENERATE_EMBEDDING, lambda text: list(query_vector)
            )

            results = RequirementService().find_similar_requirements(
                requirement_id=query_req.id, ctx=ctx, workspace_id=ws.id
            )

            # Refresh inside the active tenant context (Requirement is
            # TenantScopedModel; the manager filters on the ambient tenant).
            query_req.refresh_from_db()
            persisted = query_req.embedding

        assert persisted is not None, (
            "the lazily generated embedding was not persisted -- a subsequent "
            "call would regenerate it and the search used a different vector"
        )
        assert len(persisted) == _DIM

        ids = [hit.id for hit in results]
        assert closest.id in ids
        assert farthest.id in ids
        assert ids.index(closest.id) < ids.index(farthest.id), (
            "the freshly generated vector was not used as the query vector -- "
            "the closest neighbour did not rank first"
        )

    def test_provider_unavailable_returns_empty_without_raising(self, monkeypatch):
        """(b) Provider unconfigured -> ``[]``, no exception, embedding stays NULL.

        A neighbour with a valid ``_DIM`` embedding is seeded on purpose: if the
        service had *not* degraded before issuing the query (e.g. by searching
        with a ``None`` vector or a wrong vector), that neighbour would be a
        legitimate hit and the result would not be empty. An empty result
        alongside a searchable neighbour is therefore unambiguous evidence of
        graceful degradation, not a genuinely empty search.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Requirement with no provider")
            neighbour = make_requirement(ws, title="Searchable neighbour")
            neighbour.embedding = [1.0] * _DIM
            neighbour.save(update_fields=["embedding"])
            ctx = editor_ctx(tenant, ws)

            monkeypatch.setattr(_GENERATE_EMBEDDING, lambda text: None)

            results = RequirementService().find_similar_requirements(
                requirement_id=req.id, ctx=ctx, workspace_id=ws.id
            )

            req.refresh_from_db()
            persisted = req.embedding

        assert results == []
        assert persisted is None

    def test_dimension_mismatch_returns_empty_and_writes_nothing(self, monkeypatch):
        """(c) Mismatched width -> ``[]``, no exception, nothing written.

        The dimension guard in ``_generate_and_store_embedding`` must skip the
        write (a mismatched vector is a pgvector ``DataError`` that would
        poison the ambient transaction).

        As in (b), a neighbour with a valid ``_DIM`` embedding is seeded so the
        empty result proves degradation rather than a genuinely empty search.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Requirement with a mismatched width")
            neighbour = make_requirement(ws, title="Searchable neighbour")
            neighbour.embedding = [1.0] * _DIM
            neighbour.save(update_fields=["embedding"])
            ctx = editor_ctx(tenant, ws)

            monkeypatch.setattr(
                _GENERATE_EMBEDDING, lambda text: [0.1] * _MISMATCHED_DIM
            )

            results = RequirementService().find_similar_requirements(
                requirement_id=req.id, ctx=ctx, workspace_id=ws.id
            )

            req.refresh_from_db()
            persisted = req.embedding

        assert results == []
        assert persisted is None

    def test_second_call_does_not_regenerate_an_existing_embedding(self, monkeypatch):
        """(d) Idempotent: once persisted, a later call reuses the stored vector.

        A neighbour seeded with the same ``[0.5] * _DIM`` vector is a valid hit,
        so both calls must return it -- the search genuinely ran both times,
        while ``len(calls) == 1`` proves the second call did not re-embed.
        """
        calls: list[str] = []

        def _fake_generate(text: str):
            calls.append(text)
            return [0.5] * _DIM

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Idempotent requirement")
            neighbour = make_requirement(ws, title="Idempotent neighbour")
            neighbour.embedding = [0.5] * _DIM
            neighbour.save(update_fields=["embedding"])
            ctx = editor_ctx(tenant, ws)
            monkeypatch.setattr(_GENERATE_EMBEDDING, _fake_generate)

            svc = RequirementService()
            first = svc.find_similar_requirements(
                requirement_id=req.id, ctx=ctx, workspace_id=ws.id
            )
            second = svc.find_similar_requirements(
                requirement_id=req.id, ctx=ctx, workspace_id=ws.id
            )

        first_ids = [hit.id for hit in first]
        assert neighbour.id in first_ids, (
            "the seeded neighbour was not returned -- the search did not run, "
            "so idempotency below would be vacuous"
        )
        assert [hit.id for hit in second] == first_ids
        assert len(calls) == 1, (
            "an artifact that already has a stored embedding must not be "
            "re-embedded on every similarity query"
        )
