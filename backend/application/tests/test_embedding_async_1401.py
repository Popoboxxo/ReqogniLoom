"""#1401 / C5-T1 — embeddings are dispatched after the commit, never inline.

``RequirementService.create_requirement``/``update_requirement`` and
``TraceLinkService.create_trace_link`` used to call the embedding provider
inside the request: the requirement paths behind a 3 s watchdog thread (a slow
provider left the row un-embedded, the request still waited), the trace-link
path with no bound at all. A cold provider therefore delayed a plain 201/200
for a value that is only a derived search index.

The ReqIF importer already had the right shape (Plan G G1.2,
``transaction.on_commit`` → ``application.tasks.embed_rows_task``); this wave
routes every writer through that shared implementation
(``application.embedding_dispatch``).

What is pinned here:

* the create/update request path never calls the provider;
* the dispatch happens **only after** the surrounding transaction committed
  (a rolled-back write leaves no job behind — the rows never existed);
* a broker outage degrades to a WARNING and keeps the write successful;
* the lazy read path still works for a requirement created in this new mode
  (``find_similar_requirements`` embeds on demand, #847), which is what makes
  the short "no vector yet" window harmless.

``transaction=True`` is used where ``on_commit`` semantics are the subject:
pytest-django's default rolled-back test transaction never runs the callbacks,
so an ``assert_not_called`` there would prove nothing.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.db import OperationalError, transaction

from application.requirement_service import RequirementService
from application.tasks import embed_rows_task
from application.trace_link_service import TraceLinkService
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)

pytestmark = pytest.mark.django_db

#: Patched at its source module: the services import it lazily inside the
#: method body, so there is no module-level name to intercept.
_GENERATE = "llm_adapter.embedding_service.generate_embedding_with_model"


class TestCreateRequirementDispatch:
    def test_create_enqueues_after_commit_and_never_calls_the_provider(
        self, django_capture_on_commit_callbacks
    ):
        """The 201 path must not contain a provider call at all (#1401)."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with (
                patch(_GENERATE) as provider,
                patch.object(embed_rows_task, "delay") as delay,
                django_capture_on_commit_callbacks(execute=True),
            ):
                requirement = RequirementService().create_requirement(
                    workspace_id=ws.id, title="Dispatch me", ctx=ctx
                )

        provider.assert_not_called()
        delay.assert_called_once()
        model_name, row_ids, dispatch_tenant = delay.call_args.args
        assert model_name == "requirement"
        assert row_ids == [str(requirement.id)]
        assert dispatch_tenant == str(tenant.id), (
            "the worker must re-arm the row's tenant, not the request's guess"
        )

    def test_create_still_writes_the_row_when_the_dispatch_is_mocked(
        self, django_capture_on_commit_callbacks
    ):
        """Enqueueing is a side effect — the row must not depend on it."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with (
                patch.object(embed_rows_task, "delay"),
                django_capture_on_commit_callbacks(execute=True),
            ):
                requirement = RequirementService().create_requirement(
                    workspace_id=ws.id, title="Persisted anyway", ctx=ctx
                )

            requirement.refresh_from_db()

        assert requirement.title == "Persisted anyway"
        # Nothing embedded the row in this test: the vector is the worker's job.
        assert requirement.embedding is None


class TestUpdateRequirementDispatch:
    def test_text_update_enqueues_a_refresh(
        self, django_capture_on_commit_callbacks
    ):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            requirement = make_requirement(ws, title="Before")

            with (
                patch(_GENERATE) as provider,
                patch.object(embed_rows_task, "delay") as delay,
                django_capture_on_commit_callbacks(execute=True),
            ):
                RequirementService().update_requirement(
                    requirement_id=requirement.id, ctx=ctx, title="After"
                )

        provider.assert_not_called()
        delay.assert_called_once()
        assert delay.call_args.args[0] == "requirement"
        assert delay.call_args.args[1] == [str(requirement.id)]

    def test_metadata_only_update_does_not_enqueue(
        self, django_capture_on_commit_callbacks
    ):
        """Unchanged text means unchanged vector — no worker wake-up."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            requirement = make_requirement(ws, title="Untouched")

            with (
                patch.object(embed_rows_task, "delay") as delay,
                django_capture_on_commit_callbacks(execute=True),
            ):
                RequirementService().update_requirement(
                    requirement_id=requirement.id, ctx=ctx, rationale="why not"
                )

        delay.assert_not_called()


class TestTraceLinkDispatch:
    def test_create_trace_link_enqueues_the_link(
        self, django_capture_on_commit_callbacks
    ):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            source = make_requirement(ws, title="Source requirement")
            target = make_requirement(ws, title="Target requirement")
            ctx = editor_ctx(tenant, ws)

            with (
                patch(_GENERATE) as provider,
                patch.object(embed_rows_task, "delay") as delay,
                django_capture_on_commit_callbacks(execute=True),
            ):
                link = TraceLinkService().create_trace_link(
                    source_id=source.id,
                    target_id=target.id,
                    link_type="derives-from",
                    ctx=ctx,
                )

        provider.assert_not_called()
        delay.assert_called_once()
        model_name, row_ids, dispatch_tenant = delay.call_args.args
        assert model_name == "tracelink"
        assert row_ids == [str(link.id)]
        assert dispatch_tenant == str(tenant.id)


class TestRollbackDropsTheDispatch:
    """A rolled-back write must not leave an embedding job behind."""

    @pytest.mark.django_db(transaction=True)
    def test_rolled_back_create_enqueues_nothing(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with patch.object(embed_rows_task, "delay") as delay:
                with transaction.atomic():
                    RequirementService().create_requirement(
                        workspace_id=ws.id, title="Gone", ctx=ctx
                    )
                    assert delay.call_count == 0, (
                        "delay must not fire inside the transaction"
                    )
                    transaction.set_rollback(True)

                assert delay.call_count == 0, (
                    "a rolled-back create must not enqueue embedding work"
                )

    @pytest.mark.django_db(transaction=True)
    def test_committed_create_enqueues_exactly_once(self, monkeypatch):
        """Control: the same patch point does fire on the committed path."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with patch.object(embed_rows_task, "delay") as delay:
                RequirementService().create_requirement(
                    workspace_id=ws.id, title="Committed", ctx=ctx
                )

        assert delay.call_count == 1


class TestBrokerOutage:
    def test_create_survives_a_broker_outage(
        self, django_capture_on_commit_callbacks, caplog
    ):
        """A broker outage is a WARNING, never a failed create.

        The row is durable and the vector is recoverable with
        ``manage.py backfill_embeddings --model requirement`` — turning that
        into a 500 would trade a derived search index for a lost write.
        """

        def _broker_down(*args, **kwargs):
            raise OperationalError("broker unreachable")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with (
                patch.object(embed_rows_task, "delay", _broker_down),
                caplog.at_level("WARNING"),
                django_capture_on_commit_callbacks(execute=True),
            ):
                requirement = RequirementService().create_requirement(
                    workspace_id=ws.id, title="Survives", ctx=ctx
                )

            requirement.refresh_from_db()

        assert requirement.title == "Survives"
        assert any(
            "could not enqueue embedding" in record.getMessage()
            for record in caplog.records
        ), "the fallback path must be visible in the log"
        assert any(
            "backfill_embeddings" in record.getMessage() for record in caplog.records
        ), "the warning must name the repair command"


class TestLazyReadPathStillWorks:
    def test_find_similar_embeds_a_freshly_created_requirement(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        """The window between commit and worker run is covered by the lazy path.

        ``create_requirement`` no longer embeds inline, so the row this test
        just wrote has no vector. ``find_similar_requirements`` (#847) must
        still answer — by generating and persisting one on demand — instead of
        degrading to an empty result.
        """
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            neighbour = make_requirement(ws, title="Existing neighbour")

            # The worker never runs here: the dispatch is swallowed, so the
            # fresh requirement really has no embedding.
            with (
                patch.object(embed_rows_task, "delay"),
                django_capture_on_commit_callbacks(execute=True),
            ):
                fresh = RequirementService().create_requirement(
                    workspace_id=ws.id, title="Fresh without a vector", ctx=ctx
                )
            fresh.refresh_from_db()
            assert fresh.embedding is None, "precondition: nothing embedded it"

            query_vector = [0.5] * EMBEDDING_VECTOR_DIMENSIONS
            neighbour.embedding = list(query_vector)
            neighbour.save(update_fields=["embedding"])

            monkeypatch.setattr(
                "llm_adapter.embedding_service.generate_embedding",
                lambda text: list(query_vector),
            )
            similar = RequirementService().find_similar_requirements(
                fresh.id, ctx, workspace_id=ws.id
            )

            fresh.refresh_from_db()

        assert fresh.embedding is not None, "the read path must persist the vector"
        assert [hit.id for hit in similar] == [neighbour.id]


class TestEmbedRowsGuard:
    """#1401 made ``embed_rows`` the single write sink; keep the #794 guard."""

    def test_dimension_mismatch_is_skipped_instead_of_raising(self, monkeypatch):
        from application.embedding_backfill import embed_rows

        monkeypatch.setattr(
            "llm_adapter.embedding_service.generate_embedding",
            lambda text: [0.1] * (EMBEDDING_VECTOR_DIMENSIONS + 8),
        )

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            requirement = make_requirement(ws, title="Mismatched provider")

            written = embed_rows("requirement", [requirement.id])
            requirement.refresh_from_db()

        assert written == 0
        assert requirement.embedding is None

    def test_unknown_row_ids_are_a_no_op(self):
        from application.embedding_backfill import embed_rows

        with active_tenant():
            assert embed_rows("requirement", [uuid.uuid4()]) == 0
