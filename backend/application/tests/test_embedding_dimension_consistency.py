"""Issue #794: the shipped DEFAULT configuration must produce usable embeddings.

The bug was not a crash, an exception or a failing query — every layer behaved
exactly as designed. ``EMBEDDING_PROVIDER`` defaulted to
``sentence-transformers`` (384-dim) while ``Requirement``/``TraceLink``/
``IcdVersion`` (now ``Icd``, Task 28c-2) carried hardcoded ``vector(1536)``
columns, so the width guard
on every write path skipped 100% of writes and the identical guard on the read
path skipped 100% of semantic search passes. Both logged at DEBUG. Net result
on every default deployment: zero stored embeddings and an ``artifact.search``
whose semantic pass could never return a hit — with no error anywhere.

Nothing in the old test suite could catch that, because the tests asserted the
*guard's* behaviour (mismatch -> skip) using the very literals that made the
default configuration mismatched. This module tests the property those tests
could not: **the defaults are mutually consistent**, so the guards are never
reached under a stock install.
"""
from __future__ import annotations

import logging

import pytest

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS


# ---------------------------------------------------------------------------
# Static configuration coherence (no DB, no provider)
# ---------------------------------------------------------------------------


class TestDefaultConfigurationIsCoherent:
    def test_default_provider_output_width_matches_the_column_width(self, monkeypatch):
        """The single assertion that would have caught #794 on day one.

        Reads the shipped default with the environment cleared, so a locally
        exported ``EMBEDDING_PROVIDER`` cannot mask a broken default.
        """
        from llm_adapter.embedding_service import (
            EMBEDDING_PROVIDER_REGISTRY,
            _read_env_config,
        )

        for var in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL_NAME"):
            monkeypatch.delenv(var, raising=False)

        cfg = _read_env_config()
        provider_cls = EMBEDDING_PROVIDER_REGISTRY.get(cfg.provider_name)

        assert provider_cls is not None, (
            f"the shipped default EMBEDDING_PROVIDER={cfg.provider_name!r} is "
            f"not a registered provider — generate_embedding() would swallow "
            f"the lookup error and silently return None forever"
        )
        assert provider_cls.dimensions == EMBEDDING_VECTOR_DIMENSIONS, (
            f"the default provider {cfg.provider_name!r} emits "
            f"{provider_cls.dimensions}-dim vectors but every embedding column "
            f"is vector({EMBEDDING_VECTOR_DIMENSIONS}). With that mismatch no "
            f"embedding is ever persisted and semantic search is dead on "
            f"arrival — this is issue #794 exactly. Fix the pairing, do not "
            f"relax this assertion."
        )

    def test_every_embedding_column_uses_the_single_source_of_truth(self):
        """All five columns must agree. They disagreed (1536 vs 384) precisely
        because each declared its own literal."""
        from icd.models import Icd
        from memory.models import UserTenantMemory, WorkspaceMemory
        from persistence.models import Requirement, TraceLink

        widths = {
            model.__name__: model._meta.get_field("embedding").dimensions
            for model in (
                Requirement,
                TraceLink,
                Icd,
                WorkspaceMemory,
                UserTenantMemory,
            )
        }

        assert set(widths.values()) == {EMBEDDING_VECTOR_DIMENSIONS}, (
            f"embedding columns disagree on their width: {widths}. Every "
            f"VectorField must be sized from "
            f"persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS."
        )

    def test_mock_provider_matches_the_column_width(self):
        """The ``mock`` provider backs local/CI similarity ordering. If its
        width drifts from the columns, every mock-provider test silently
        exercises the skip path instead of the write path."""
        from llm_adapter.embedding_service import EMBEDDING_PROVIDER_REGISTRY

        assert (
            EMBEDDING_PROVIDER_REGISTRY["mock"].dimensions
            == EMBEDDING_VECTOR_DIMENSIONS
        )


# ---------------------------------------------------------------------------
# The schema actually enforces it (real DB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSchemaMatchesTheDeclaredWidth:
    """The ORM's declared ``dimensions`` is what every guard compares against,
    but Postgres enforces the *column's* ``vector(N)``. If the migration ever
    drifts from the model, the guards would pass and the INSERT would fail —
    so assert against ``information_schema``, not the model."""

    @pytest.mark.parametrize(
        "table",
        ["pl_requirement", "pl_tracelink", "icd_icd", "mem_workspace_memory"],
    )
    def test_column_is_typed_to_the_ssot_width(self, table):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                WHERE c.relname = %s AND a.attname = 'embedding'
                  AND NOT a.attisdropped
                """,
                [table],
            )
            row = cursor.fetchone()

        assert row is not None, f"{table} has no embedding column"
        assert row[0] == f"vector({EMBEDDING_VECTOR_DIMENSIONS})", (
            f"{table}.embedding is {row[0]} but the model declares "
            f"vector({EMBEDDING_VECTOR_DIMENSIONS}) — a migration is missing"
        )


# ---------------------------------------------------------------------------
# End to end: default config -> stored embedding -> semantic hit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDefaultConfigProducesSearchableEmbeddings:
    """The user-visible symptom of #794 was ``artifact.search`` returning
    nothing semantic. This walks the whole chain with the ``mock`` provider —
    i.e. through the real ``generate_embedding`` facade and the real provider
    registry, not a monkeypatched stub — so a future width drift in either the
    provider or the column breaks it."""

    def test_created_requirement_gets_a_stored_embedding(self, monkeypatch):
        from application.requirement_service import RequirementService
        from persistence.tests.factories import active_tenant, editor_ctx, make_workspace

        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            requirement = RequirementService().create_requirement(
                workspace_id=ws.id,
                title="Recover the audit trail after a failed import",
                description="The system shall retain partial import telemetry.",
                ctx=ctx,
            )
            requirement.refresh_from_db()

        assert requirement.embedding is not None, (
            "no embedding was persisted under a coherent provider/column "
            "pairing — issue #794 has regressed"
        )
        assert len(requirement.embedding) == EMBEDDING_VECTOR_DIMENSIONS

    def test_semantic_pass_returns_a_hit_with_no_keyword_overlap(self, monkeypatch):
        """The end of the chain: a stored embedding written by the real
        provider is findable through ``SearchService`` by a query that shares
        no keyword with it, i.e. only the semantic pass can produce it."""
        from application.requirement_service import RequirementService
        from application.search_service import SearchService
        from persistence.tests.factories import active_tenant, editor_ctx, make_workspace

        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        # The mock provider is a deterministic hash->PRNG, so an identical
        # text yields an identical vector (cosine distance 0). Search for the
        # requirement's own embedding text under a query string that shares no
        # token with its title, proving the hit came from the vector pass.
        semantic_text = "Zwiebelfisch Klabautermann Rhabarberbarbara"

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            requirement = RequirementService().create_requirement(
                workspace_id=ws.id, title=semantic_text, ctx=ctx
            )
            requirement.refresh_from_db()
            assert requirement.embedding is not None

            # Query text with zero lexical overlap; monkeypatch only the
            # *query* embedding so it equals the stored one.
            monkeypatch.setattr(
                "application.search_service.generate_embedding",
                lambda text: list(requirement.embedding),
            )
            result = SearchService().search(
                "completely unrelated query tokens", ctx, workspace_id=ws.id
            )

        assert any(hit.id == str(requirement.id) for hit in result.results), (
            "the semantic pass produced no hit for a requirement whose stored "
            "embedding is identical to the query embedding — the read side of "
            "#794 has regressed"
        )


# ---------------------------------------------------------------------------
# A residual mismatch must be LOUD, not silent
# ---------------------------------------------------------------------------


class TestMismatchIsVisible:
    """#794's second half: resizing the columns fixes the default, but an
    operator can still point ``EMBEDDING_PROVIDER`` at a provider of a
    different native width (ollama/nomic-embed-text is 768). That must not
    degrade the way the default did."""

    def test_first_skip_logs_at_warning_then_dedupes_to_debug(self, monkeypatch, caplog):
        from llm_adapter import embedding_service

        monkeypatch.setattr(embedding_service, "_warned_dimension_mismatches", set())

        with caplog.at_level(logging.DEBUG, logger="llm_adapter.embedding_service"):
            embedding_service.warn_dimension_mismatch("UnitUnderTest", 768, 384)
            embedding_service.warn_dimension_mismatch("UnitUnderTest", 768, 384)

        levels = [r.levelno for r in caplog.records]
        assert levels.count(logging.WARNING) == 1, (
            "the first occurrence must be a WARNING — a DEBUG-only signal is "
            "how #794 stayed invisible for an entire release line"
        )
        assert levels.count(logging.DEBUG) == 1, (
            "subsequent identical occurrences must dedupe to DEBUG so a bulk "
            "backfill does not emit one WARNING per row"
        )

    def test_system_check_reports_a_provider_column_mismatch(self, monkeypatch):
        from llm_adapter.checks import (
            EMBEDDING_DIMENSION_MISMATCH,
            check_embedding_dimensions,
        )

        assert check_embedding_dimensions() == [], (
            "the stock configuration must be clean — a warning here means the "
            "shipped defaults do not line up"
        )

        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")  # 1536-dim
        warnings = check_embedding_dimensions()

        assert [w.id for w in warnings] == [EMBEDDING_DIMENSION_MISMATCH]
        assert "1536" in warnings[0].msg
        assert str(EMBEDDING_VECTOR_DIMENSIONS) in warnings[0].msg

    def test_system_check_reports_an_unknown_provider(self, monkeypatch):
        """A typo in ``EMBEDDING_PROVIDER`` disables embeddings entirely and is
        otherwise completely silent: ``generate_embedding`` catches the
        registry ``ValueError`` and returns ``None``."""
        from llm_adapter.checks import (
            EMBEDDING_PROVIDER_UNKNOWN,
            check_embedding_dimensions,
        )

        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformer")  # missing 's'
        warnings = check_embedding_dimensions()

        assert [w.id for w in warnings] == [EMBEDDING_PROVIDER_UNKNOWN]
