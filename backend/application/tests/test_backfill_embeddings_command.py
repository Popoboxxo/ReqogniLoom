"""Tests for ``manage.py backfill_embeddings`` (#794).

Fixing the column widths only helps rows written *after* the fix — embeddings
have never had a backfill path, because they are generated opportunistically
on create/update. Without this command, every artifact that already existed
when #794 was fixed stays permanently un-embedded and semantic
``artifact.search`` keeps returning nothing for the entire existing corpus.
"""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.tests.factories import active_tenant, make_requirement, make_workspace


def _run(**kwargs) -> str:
    out = StringIO()
    call_command("backfill_embeddings", stdout=out, stderr=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
class TestBackfillEmbeddings:
    def test_fills_a_requirement_that_had_no_embedding(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            # make_requirement bypasses RequirementService, so this row is in
            # exactly the state a pre-#794 deployment's rows are in: real
            # content, no embedding.
            req = make_requirement(ws, title="Un-embedded legacy requirement")
            assert req.embedding is None

            output = _run(tenant=str(tenant.id), model="requirement")
            req.refresh_from_db()

        assert req.embedding is not None
        assert len(req.embedding) == EMBEDDING_VECTOR_DIMENSIONS
        assert "embedded=1" in output

    def test_dry_run_reports_without_writing(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Dry run requirement")

            output = _run(tenant=str(tenant.id), model="requirement", dry_run=True)
            req.refresh_from_db()

        assert req.embedding is None
        assert "1 row(s) to embed" in output
        assert "embedded=0" in output

    def test_skips_rows_that_already_have_an_embedding(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        sentinel = [0.25] * EMBEDDING_VECTOR_DIMENSIONS

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Already embedded requirement")
            req.embedding = sentinel
            req.save(update_fields=["embedding"])

            _run(tenant=str(tenant.id), model="requirement")
            req.refresh_from_db()

        assert [round(v, 4) for v in req.embedding] == [round(v, 4) for v in sentinel]

    def test_force_regenerates_an_existing_embedding(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        sentinel = [0.25] * EMBEDDING_VECTOR_DIMENSIONS

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Force re-embed requirement")
            req.embedding = sentinel
            req.save(update_fields=["embedding"])

            _run(tenant=str(tenant.id), model="requirement", force=True)
            req.refresh_from_db()

        assert [round(v, 4) for v in req.embedding] != [round(v, 4) for v in sentinel]

    def test_aborts_loudly_on_a_dimension_mismatch(self, monkeypatch):
        """The whole point of #794: a run that cannot possibly write anything
        must say so, not report success having skipped every row."""
        monkeypatch.setattr(
            "llm_adapter.embedding_service.generate_embedding",
            lambda text: [0.1] * (EMBEDDING_VECTOR_DIMENSIONS + 8),
        )

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Mismatch requirement")

            with pytest.raises(CommandError, match="Dimension mismatch"):
                _run(tenant=str(tenant.id), model="requirement")

            req.refresh_from_db()

        assert req.embedding is None

    def test_aborts_when_the_provider_returns_nothing(self, monkeypatch):
        monkeypatch.setattr(
            "llm_adapter.embedding_service.generate_embedding", lambda text: None
        )

        with active_tenant() as tenant:
            with pytest.raises(CommandError, match="returned no vector"):
                _run(tenant=str(tenant.id), model="requirement")

    def test_unknown_tenant_is_rejected(self, monkeypatch):
        import uuid

        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with pytest.raises(CommandError, match="No tenant with id"):
            _run(tenant=str(uuid.uuid4()))
