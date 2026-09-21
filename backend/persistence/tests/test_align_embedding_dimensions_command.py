"""Tests for ``manage.py align_embedding_dimensions`` (#1018, #1019).

The command is the persistent, image-deployment counterpart to the
``makemigrations`` + ``migrate`` path: it resizes the *physical* pgvector
columns (and their HNSW indexes) to
``persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS`` directly, so
nothing has to be written to the container filesystem.

The schema DDL runs inside the test transaction (PostgreSQL DDL is
transactional), so every change here is rolled back when the test ends — the
suite's 384 default is restored for the next test.
"""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from persistence.embedding_schema import column_type, embedding_columns

#: Empirically confirmed against the migrated schema: four models carry a
#: ``VectorField`` (the plan's "five" counted the retired ``IcdVersion``, which
#: Task 28c-2 dropped). Discovery must find exactly these — a missing one means
#: an embedding column would silently stay at the wrong width.
_EXPECTED_LABELS = {
    "Requirement.embedding",
    "TraceLink.embedding",
    "Icd.embedding",
    "MemoryEntry.embedding",
}

#: The HNSW index that backs each column above.
_EXPECTED_INDEXES = {
    "pl_req_embedding_hnsw",
    "pl_tracelink_embedding_hnsw",
    "icd_embedding_hnsw",
    "mem_entry_embedding_hnsw",
}


def _run() -> str:
    out = StringIO()
    call_command("align_embedding_dimensions", stdout=out, stderr=out)
    return out.getvalue()


def _column_types() -> dict[str, str]:
    with connection.cursor() as cursor:
        return {
            column.label: column_type(cursor, column.table, column.column)
            for column in embedding_columns()
        }


def _hnsw_index_defs() -> dict[str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE indexname = ANY(%s)",
            [sorted(_EXPECTED_INDEXES)],
        )
        return dict(cursor.fetchall())


@pytest.mark.django_db
class TestAlignEmbeddingDimensions:
    def test_registry_discovers_every_embedding_column(self) -> None:
        assert {column.label for column in embedding_columns()} == _EXPECTED_LABELS

    def test_default_run_is_a_no_op_when_columns_already_match(self) -> None:
        """The shipped default target (384) matches the migrated schema, so the
        command must change nothing and say so — that is the idempotency
        guarantee a deploy relies on."""
        output = _run()

        assert "idempotent no-op" in output
        assert set(_column_types().values()) == {"vector(384)"}

    def test_resizes_every_column_and_reindexes_every_hnsw_index(
        self, monkeypatch
    ) -> None:
        import persistence.management.commands.align_embedding_dimensions as cmd

        monkeypatch.setattr(cmd, "EMBEDDING_VECTOR_DIMENSIONS", 768)

        output = _run()

        assert set(_column_types().values()) == {"vector(768)"}
        assert "reindexed 4 HNSW index/indices" in output

        index_defs = _hnsw_index_defs()
        assert set(index_defs) == _EXPECTED_INDEXES
        for definition in index_defs.values():
            assert "hnsw" in definition.lower()
            assert "vector_cosine_ops" in definition

    def test_reports_nothing_discarded_when_no_vectors_are_stored(
        self, monkeypatch
    ) -> None:
        """The all-NULL branch must say so explicitly instead of warning about a
        data loss that cannot happen (fresh deployment / freshly backfilled)."""
        import persistence.management.commands.align_embedding_dimensions as cmd

        monkeypatch.setattr(cmd, "EMBEDDING_VECTOR_DIMENSIONS", 768)

        output = _run()

        assert "nothing is discarded" in output
        assert "DISCARDS" not in output
        assert set(_column_types().values()) == {"vector(768)"}

    def test_dry_run_reports_the_plan_without_changing_the_schema(
        self, monkeypatch
    ) -> None:
        """``--dry-run`` must print the plan + non-NULL counts and return before
        any DDL: schema and stored vectors stay exactly as they were."""
        import persistence.management.commands.align_embedding_dimensions as cmd
        from persistence.models import Requirement
        from persistence.tests.factories import (
            active_tenant,
            make_requirement,
            make_workspace,
        )

        monkeypatch.setattr(cmd, "EMBEDDING_VECTOR_DIMENSIONS", 768)

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            requirement = make_requirement(workspace)
            Requirement.unscoped.filter(pk=requirement.pk).update(
                embedding=[0.1] * 384
            )

            out = StringIO()
            call_command(
                "align_embedding_dimensions",
                "--dry-run",
                stdout=out,
                stderr=out,
            )
            output = out.getvalue()

            assert "vector(384) -> vector(768)" in output
            assert "Requirement.embedding: 1 row(s)" in output
            assert "--dry-run: no changes made" in output
            # Nothing ran: the schema is untouched and the vector survives.
            assert set(_column_types().values()) == {"vector(384)"}
            assert (
                Requirement.unscoped.get(pk=requirement.pk).embedding is not None
            )

    def test_second_run_is_a_no_op(self, monkeypatch) -> None:
        import persistence.management.commands.align_embedding_dimensions as cmd

        monkeypatch.setattr(cmd, "EMBEDDING_VECTOR_DIMENSIONS", 768)

        first = _run()
        second = _run()

        assert "vector(384) -> vector(768)" in first
        assert "idempotent no-op" not in first
        assert "idempotent no-op" in second
        assert set(_column_types().values()) == {"vector(768)"}

    def test_warns_loudly_and_counts_rows_before_discarding_vectors(
        self, monkeypatch
    ) -> None:
        import persistence.management.commands.align_embedding_dimensions as cmd
        from persistence.models import Requirement
        from persistence.tests.factories import active_tenant, make_requirement, make_workspace

        monkeypatch.setattr(cmd, "EMBEDDING_VECTOR_DIMENSIONS", 768)

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            requirement = make_requirement(workspace)
            Requirement.unscoped.filter(pk=requirement.pk).update(
                embedding=[0.1] * 384
            )
            assert Requirement.unscoped.get(pk=requirement.pk).embedding is not None

            output = _run()

            assert "DISCARDS" in output
            assert "Requirement.embedding: 1 row(s)" in output
            assert "backfill_embeddings" in output
            # The cast really discarded the old-width vector rather than
            # aborting the resize halfway.
            assert Requirement.unscoped.get(pk=requirement.pk).embedding is None

    def test_raises_when_a_column_is_absent_and_tells_you_to_migrate(
        self, monkeypatch
    ) -> None:
        import persistence.management.commands.align_embedding_dimensions as cmd

        real = embedding_columns()
        ghost = real[0]._replace(
            label="Ghost.embedding", table="pl_does_not_exist", column="embedding"
        )
        monkeypatch.setattr(cmd, "embedding_columns", lambda: [ghost, *real[1:]])

        with pytest.raises(CommandError, match="migrate"):
            _run()
