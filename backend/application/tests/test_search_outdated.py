"""P6 / D13: ``artifact.search`` excludes outdated artifacts by default.

The single lifecycle filter of :mod:`application.search_service`
(:func:`_filter_outdated_hits`) is exercised here for a workflow type with a
``status`` column (Requirement), one without (ArchitectureElement), a
``TraceLink``, the ``scope="tenant"`` path, the ``total_count`` contract and the
fail-closed degradation policy.

Every search runs in ``keyword`` mode so the semantic leg cannot interfere and
the assertions stay deterministic.
"""
from __future__ import annotations

import logging

import pytest

from application.search_service import SearchService
from persistence.models import ArchitectureElement, Artifact, LifecycleStatus
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)


def _make_outdated(requirement) -> None:
    requirement.artifact.lifecycle_status = LifecycleStatus.OUTDATED
    requirement.artifact.save(update_fields=["lifecycle_status"])


def _make_architecture_element(tenant, workspace, *, title: str):
    """Create an ArchitectureElement with its backing Artifact."""
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    return ArchitectureElement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
    )


@pytest.mark.django_db
class TestSearchOutdatedFilter:
    def test_outdated_requirement_hidden_by_default(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            req = make_requirement(ws, title="Legacy login flow", uid="REQ-OUT-1")
            _make_outdated(req)

            result = SearchService().search(
                "Legacy login flow",
                ctx,
                workspace_id=ws.id,
                type_filter=["Requirement"],
                mode="keyword",
            )

        assert str(req.id) not in [hit.id for hit in result.results]
        assert result.total_count == 0

    def test_outdated_requirement_returned_with_include_outdated(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            req = make_requirement(ws, title="Legacy login flow", uid="REQ-OUT-2")
            _make_outdated(req)

            result = SearchService().search(
                "Legacy login flow",
                ctx,
                workspace_id=ws.id,
                type_filter=["Requirement"],
                mode="keyword",
                include_outdated=True,
            )

        hits = [hit for hit in result.results if hit.id == str(req.id)]
        assert hits, "outdated requirement must be returned with include_outdated=True"
        assert hits[0].outdated is True
        assert hits[0].status == "outdated"

    def test_visible_hit_reports_its_workflow_status(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            req = make_requirement(ws, title="Active login flow", uid="REQ-OUT-3")

            result = SearchService().search(
                "Active login flow",
                ctx,
                workspace_id=ws.id,
                type_filter=["Requirement"],
                mode="keyword",
            )

        hits = [hit for hit in result.results if hit.id == str(req.id)]
        assert hits, "visible requirement must be returned"
        assert hits[0].outdated is False
        # The workflow projection (or its type's initial state) is non-empty.
        assert hits[0].status

    def test_second_type_is_filtered_too(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            element = _make_architecture_element(
                tenant, ws, title="Legacy auth component"
            )
            element.artifact.lifecycle_status = LifecycleStatus.OUTDATED
            element.artifact.save(update_fields=["lifecycle_status"])

            hidden = SearchService().search(
                "Legacy auth component",
                ctx,
                workspace_id=ws.id,
                type_filter=["ArchitectureElement"],
                mode="keyword",
            )
            shown = SearchService().search(
                "Legacy auth component",
                ctx,
                workspace_id=ws.id,
                type_filter=["ArchitectureElement"],
                mode="keyword",
                include_outdated=True,
            )

        assert str(element.id) not in [hit.id for hit in hidden.results]
        hits = [hit for hit in shown.results if hit.id == str(element.id)]
        assert hits, "outdated element must be returned with include_outdated=True"
        assert hits[0].outdated is True
        assert hits[0].status == "outdated"

    def test_outdated_total_count_reflects_filter(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            make_requirement(ws, title="Token rotation one", uid="REQ-OUT-4")
            outdated = make_requirement(ws, title="Token rotation two", uid="REQ-OUT-5")
            _make_outdated(outdated)

            default = SearchService().search(
                "Token rotation",
                ctx,
                workspace_id=ws.id,
                type_filter=["Requirement"],
                mode="keyword",
            )
            with_outdated = SearchService().search(
                "Token rotation",
                ctx,
                workspace_id=ws.id,
                type_filter=["Requirement"],
                mode="keyword",
                include_outdated=True,
            )

        assert default.total_count == 1
        assert with_outdated.total_count == 2

    def test_tenant_scope_hides_outdated_by_default(self):
        """The filter also covers the ``scope="tenant"`` multi-workspace path."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            req = make_requirement(ws, title="Tenant scoped legacy", uid="REQ-TEN-1")
            _make_outdated(req)

            hidden = SearchService().search(
                "Tenant scoped legacy",
                ctx,
                scope="tenant",
                type_filter=["Requirement"],
                mode="keyword",
            )
            shown = SearchService().search(
                "Tenant scoped legacy",
                ctx,
                scope="tenant",
                type_filter=["Requirement"],
                mode="keyword",
                include_outdated=True,
            )

        assert str(req.id) not in [hit.id for hit in hidden.results]
        assert hidden.total_count == 0
        hits = [hit for hit in shown.results if hit.id == str(req.id)]
        assert hits, "outdated requirement must be returned with include_outdated=True"
        assert hits[0].outdated is True

    def test_outdated_tracelink_returned_with_include_outdated(self):
        """TraceLink keeps the flag computed by ``_filter_tracelink_hits``."""
        from application.tests.test_search_tracelink_icd import _make_link

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            src = make_requirement(ws, title="Source requirement", uid="REQ-LK-1")
            tgt = make_requirement(ws, title="Retired target", uid="REQ-LK-2")
            _make_outdated(tgt)
            link = _make_link(tenant, src, tgt)

            hidden = SearchService().search(
                "references",
                ctx,
                workspace_id=ws.id,
                type_filter=["TraceLink"],
                mode="keyword",
            )
            shown = SearchService().search(
                "references",
                ctx,
                workspace_id=ws.id,
                type_filter=["TraceLink"],
                mode="keyword",
                include_outdated=True,
            )

        assert str(link.id) not in [hit.id for hit in hidden.results]
        hits = [hit for hit in shown.results if hit.id == str(link.id)]
        assert hits, "outdated link must be returned with include_outdated=True"
        assert hits[0].outdated is True
        assert hits[0].status == "outdated"

    def test_outdated_lookup_failure_drops_the_type_fail_closed(
        self, monkeypatch, caplog
    ):
        """F1: a failing outdated lookup must hide the type's hits, never leak."""

        def _boom(*_args, **_kwargs):
            raise RuntimeError("workflow state store unavailable")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            make_requirement(ws, title="Token flow legacy", uid="REQ-OUT-6")
            make_requirement(ws, title="Token flow live", uid="REQ-OUT-7")
            monkeypatch.setattr("workflow.state_reader.outdated_ids", _boom)

            with caplog.at_level(logging.WARNING):
                result = SearchService().search(
                    "Token flow",
                    ctx,
                    workspace_id=ws.id,
                    type_filter=["Requirement"],
                    mode="keyword",
                )

        assert result.results == []
        assert result.total_count == 0
        assert any(
            "outdated lookup failed" in record.getMessage()
            and "Requirement" in record.getMessage()
            for record in caplog.records
        )

    def test_outdated_lookup_is_chunked(self, monkeypatch):
        """N1: the ``__in`` intersection is batched, never one unbounded list."""
        from unittest.mock import patch

        from workflow import state_reader

        monkeypatch.setattr("application.search_service._LIFECYCLE_CHUNK_SIZE", 2)

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            reqs = [
                make_requirement(ws, title=f"Chunked token {index}", uid=f"REQ-CHK-{index}")
                for index in range(5)
            ]
            _make_outdated(reqs[0])

            with patch(
                "workflow.state_reader.outdated_ids", wraps=state_reader.outdated_ids
            ) as outdated_ids:
                result = SearchService().search(
                    "Chunked token",
                    ctx,
                    workspace_id=ws.id,
                    type_filter=["Requirement"],
                    mode="keyword",
                )

        assert result.total_count == 4
        # 5 hit ids at chunk size 2 -> 3 calls (2 + 2 + 1); a regression to one
        # unbounded ``__in`` would collapse this to a single call.
        assert outdated_ids.call_count >= 3
