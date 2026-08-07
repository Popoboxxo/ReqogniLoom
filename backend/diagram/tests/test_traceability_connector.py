"""
COMP-DS-004 TraceabilityConnector — Unit and integration tests.

Covers:
  REQ-L2-DS-004 / REQ-L3-TC-001: 'documents' TraceLink creation
  REQ-L3-TC-001: Errors from TraceabilityEngine propagated transparently
  REQ-L2-DS-004: TraceLink can bind a Diagram to a Requirement/Architecture
  Codeberg #353 Task 3 / #392: shadow-Artifact resolution (_resolve_artifact_id)

IF-DS-INT-003: create_document_link(diagram_id, target_id)
IF-L1-034: delegates to traceability.services.create_trace_link

TestCreateDocumentLink: pure unit tests (no DB) — use mocks only.
TestCreateDocumentLinkWithManagerIntegration: requires Django DB.
TestResolveArtifactId: DB-backed tests for the shadow-Artifact mechanism
    (idempotency, transaction participation).

Note: the end-to-end #392 regression test (MCP diagram.create + target_id
persisting a real 'documents' TraceLink, nothing mocked) lives in
mcp_server/tests/test_diagram_tool_group.py, next to the other MCP-level
diagram.create tests — see TestDiagramCreateTargetIdTraceLink there.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from diagram.traceability_connector import TraceabilityConnector, _resolve_artifact_id
from traceability.exceptions import TargetNotFoundError


# TestCreateDocumentLink uses only mocks — no DB marker needed.


@pytest.fixture
def connector() -> TraceabilityConnector:
    return TraceabilityConnector()


class TestCreateDocumentLink:
    """REQ-L3-TC-001: create_document_link delegates to TraceabilityEngine.

    #392 fix: create_document_link now resolves diagram_id -> Diagram ->
    shadow Artifact id (via _resolve_artifact_id) before delegating to
    create_trace_link. Both steps are mocked here to keep these pure unit
    tests DB-free — the real DB-backed proof lives in TestResolveArtifactId
    and TestDiagramCreateTargetIdTraceLink (mcp_server tests).
    """

    def test_link_type_is_documents(self, connector: TraceabilityConnector) -> None:
        """The link_type is hard-coded to 'documents' (REQ-L3-TC-001)."""
        assert connector.LINK_TYPE == "documents"

    def test_delegates_to_create_trace_link(self, connector: TraceabilityConnector) -> None:
        diagram_id = uuid.uuid4()
        target_id = uuid.uuid4()
        resolved_artifact_id = uuid.uuid4()
        mock_diagram = MagicMock()
        mock_link = MagicMock()

        with patch(
            "diagram.traceability_connector.Diagram.objects.get",
            return_value=mock_diagram,
        ) as mock_get, patch(
            "diagram.traceability_connector._resolve_artifact_id",
            return_value=resolved_artifact_id,
        ) as mock_resolve, patch(
            "diagram.traceability_connector.create_trace_link",
            return_value=mock_link,
        ) as mock_create:
            result = connector.create_document_link(
                diagram_id=diagram_id,
                target_id=target_id,
            )

        mock_get.assert_called_once_with(id=diagram_id)
        mock_resolve.assert_called_once_with(mock_diagram)
        mock_create.assert_called_once_with(
            source_id=resolved_artifact_id,
            target_id=target_id,
            link_type="documents",
            created_by_id=None,
        )
        assert result is mock_link

    def test_propagates_created_by_id(self, connector: TraceabilityConnector) -> None:
        diagram_id = uuid.uuid4()
        target_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        with patch(
            "diagram.traceability_connector.Diagram.objects.get",
            return_value=MagicMock(),
        ), patch(
            "diagram.traceability_connector._resolve_artifact_id",
            return_value=uuid.uuid4(),
        ), patch(
            "diagram.traceability_connector.create_trace_link",
            return_value=MagicMock(),
        ) as mock_create:
            connector.create_document_link(
                diagram_id=diagram_id,
                target_id=target_id,
                created_by_id=actor_id,
            )

        assert mock_create.call_args.kwargs["created_by_id"] == actor_id

    def test_propagates_traceability_engine_errors(
        self, connector: TraceabilityConnector
    ) -> None:
        """REQ-L3-TC-001: errors from TraceabilityEngine are propagated transparently."""
        with patch(
            "diagram.traceability_connector.Diagram.objects.get",
            return_value=MagicMock(),
        ), patch(
            "diagram.traceability_connector._resolve_artifact_id",
            return_value=uuid.uuid4(),
        ), patch(
            "diagram.traceability_connector.create_trace_link",
            side_effect=TargetNotFoundError("Target not found"),
        ):
            with pytest.raises(TargetNotFoundError, match="Target not found"):
                connector.create_document_link(
                    diagram_id=uuid.uuid4(),
                    target_id=uuid.uuid4(),
                )


@pytest.mark.django_db
class TestCreateDocumentLinkWithManagerIntegration:
    """REQ-L2-DS-004: Documents TraceLink created when target_id provided."""

    def test_create_diagram_with_trace_link(
        self, tenant_a, workspace_a
    ) -> None:
        """Creating a diagram with target_id triggers documents TraceLink.

        workspace_id is now required for this scenario (#392 fix): the shadow
        Artifact that backs the TraceLink source needs a real workspace FK.
        """
        from diagram.manager import DiagramManager
        from diagram.tests.conftest import active_tenant, VALID_MERMAID_BLOCK

        manager = DiagramManager()
        target_id = uuid.uuid4()

        with patch("diagram.traceability_connector.create_trace_link") as mock_create:
            with active_tenant(tenant_a):
                manager.create_diagram(
                    name="Diagram with TraceLink",
                    diagram_type="block",
                    payload_format="mermaid",
                    content=VALID_MERMAID_BLOCK,
                    tenant=tenant_a,
                    workspace_id=workspace_a.id,
                    target_id=target_id,
                )

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["link_type"] == "documents"
        assert call_kwargs["target_id"] == target_id


# ---------------------------------------------------------------------------
# Codeberg #353 Task 3 / #392: shadow-Artifact resolution
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestResolveArtifactId:
    """DB-backed tests for _resolve_artifact_id (shadow-Artifact mechanism)."""

    def test_idempotent_second_call_returns_same_artifact_id(
        self, tenant_a, workspace_a
    ) -> None:
        """Second _resolve_artifact_id call on the same Diagram must not
        create a second shadow Artifact."""
        from diagram.models import Diagram
        from diagram.tests.conftest import active_tenant
        from persistence.models import Artifact

        with active_tenant(tenant_a):
            diagram = Diagram.objects.create(
                name="Idempotency Diagram",
                diagram_type="block",
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

            first_id = _resolve_artifact_id(diagram)

            diagram.refresh_from_db()
            second_id = _resolve_artifact_id(diagram)

            assert first_id == second_id
            assert Artifact.objects.filter(artifact_type="Diagram").count() == 1

    def test_rollback_of_outer_transaction_rolls_back_shadow_artifact(
        self, tenant_a, workspace_a
    ) -> None:
        """The lazy shadow-Artifact creation participates in the caller's
        transaction — a rollback of the outer operation also rolls back the
        shadow Artifact creation (no orphaned Artifact row survives)."""
        from django.db import transaction

        from diagram.models import Diagram
        from diagram.tests.conftest import active_tenant
        from persistence.models import Artifact

        with active_tenant(tenant_a):
            diagram = Diagram.objects.create(
                name="Rollback Diagram",
                diagram_type="block",
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

            class _BoomError(Exception):
                pass

            with pytest.raises(_BoomError):
                with transaction.atomic():
                    _resolve_artifact_id(diagram)
                    raise _BoomError("simulated failure after shadow-Artifact create")

            diagram.refresh_from_db()
            assert diagram.artifact_id is None
            assert Artifact.objects.filter(artifact_type="Diagram").count() == 0

    def test_raises_when_diagram_has_no_workspace(self, tenant_a) -> None:
        """A Diagram without workspace_id cannot back a TraceLink: Artifact's
        workspace FK is non-nullable."""
        from diagram.models import Diagram
        from diagram.tests.conftest import active_tenant
        from traceability.exceptions import TraceLinkError

        with active_tenant(tenant_a):
            diagram = Diagram.objects.create(
                name="Workspace-less Diagram",
                diagram_type="block",
                tenant=tenant_a,
            )

            with pytest.raises(TraceLinkError):
                _resolve_artifact_id(diagram)


# ---------------------------------------------------------------------------
# Codeberg #353 Task 3, code-review round 1: race-condition regression
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
class TestResolveArtifactIdConcurrency:
    """Proves select_for_update() actually serializes concurrent callers.

    Review finding: the original read-then-write had no locking, so two
    concurrent callers resolving the same Diagram could both observe
    ``artifact_id is None`` and both INSERT a shadow Artifact (last writer
    wins, one Artifact silently orphaned). The single-threaded idempotency
    test above cannot catch this — it never has two callers in flight at
    once. This test uses two real threads, each with its own DB connection
    and its own transaction (``transaction=True`` / TransactionTestCase
    semantics — a plain ``django_db`` test shares one connection and cannot
    exhibit a genuine row-lock wait), to force the race and assert the lock
    actually blocks the second caller.
    """

    def test_concurrent_calls_produce_exactly_one_shadow_artifact(
        self, tenant_a, workspace_a
    ) -> None:
        import threading
        import time
        from unittest.mock import patch

        from django.db import close_old_connections, transaction

        from diagram.models import Diagram
        from diagram.tests.conftest import active_tenant
        from persistence.models import Artifact
        from persistence.tenancy import TenantContext

        with active_tenant(tenant_a):
            diagram = Diagram.objects.create(
                name="Concurrency Diagram",
                diagram_type="block",
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )
        diagram_id = diagram.id
        tenant_id = tenant_a.id

        # Synchronization: thread A signals lock_acquired once it is inside
        # Artifact creation (i.e. it is holding the row lock acquired by its
        # select_for_update()); it then blocks on `proceed` so thread B has
        # a real window to attempt (and, if the fix works, be forced to
        # wait for) the same lock.
        lock_acquired = threading.Event()
        proceed = threading.Event()
        results: dict[str, object] = {}
        errors: list[BaseException] = []

        real_create = Artifact.objects.create

        def _slow_create(*args, **kwargs):
            lock_acquired.set()
            proceed.wait(timeout=5)
            return real_create(*args, **kwargs)

        def _worker_a() -> None:
            close_old_connections()
            try:
                TenantContext.set_tenant(tenant_id)
                with transaction.atomic():
                    d = Diagram.objects.get(pk=diagram_id)
                    with patch.object(
                        Artifact.objects, "create", side_effect=_slow_create
                    ):
                        results["a"] = _resolve_artifact_id(d)
            except BaseException as exc:  # noqa: BLE001 - surfaced on main thread
                errors.append(exc)
            finally:
                TenantContext.clear_tenant()
                close_old_connections()

        def _worker_b() -> None:
            close_old_connections()
            try:
                TenantContext.set_tenant(tenant_id)
                # Only start racing once thread A actually holds the lock
                # (is inside Artifact creation), otherwise this thread might
                # simply win the race instead of proving mutual exclusion.
                assert lock_acquired.wait(timeout=5), "thread A never reached create()"
                with transaction.atomic():
                    d = Diagram.objects.get(pk=diagram_id)
                    started = time.monotonic()
                    results["b"] = _resolve_artifact_id(d)
                    results["b_waited"] = time.monotonic() - started
            except BaseException as exc:  # noqa: BLE001 - surfaced on main thread
                errors.append(exc)
            finally:
                TenantContext.clear_tenant()
                close_old_connections()

        thread_a = threading.Thread(target=_worker_a)
        thread_b = threading.Thread(target=_worker_b)

        thread_a.start()
        thread_b.start()
        # Give thread B time to actually queue up on select_for_update()
        # (blocked, holding its own transaction open) before we let thread A
        # finish and commit.
        assert lock_acquired.wait(timeout=5), "thread A never reached create()"
        time.sleep(0.3)
        proceed.set()

        thread_a.join(timeout=10)
        thread_b.join(timeout=10)

        assert not thread_a.is_alive(), "thread A did not finish in time"
        assert not thread_b.is_alive(), "thread B did not finish in time"
        assert not errors, f"worker thread(s) raised: {errors!r}"

        assert results["a"] == results["b"], (
            "both concurrent callers must resolve to the SAME shadow "
            "Artifact id — this is exactly the race the code review flagged"
        )
        assert results["b_waited"] >= 0.25, (
            "thread B should have BLOCKED on select_for_update() while "
            "thread A held the row lock (observed wait: "
            f"{results['b_waited']!r}s) — a wait this short means the lock "
            "did not actually serialize the two callers"
        )

        with active_tenant(tenant_a):
            assert Artifact.objects.filter(artifact_type="Diagram").count() == 1
