"""End-to-end: change request + real trace links + persistence + chains (S4.5).

Unlike the graph tests this uses the production ``TraceLinkService`` so the
catalog validation, workspace fence and real Requirement entities are all in
play.
"""
from __future__ import annotations

import pytest

from application.models import ChangeImpactFinding
from application.trace_link_service import TraceLinkService
from persistence.tests.factories import make_requirement

from ._change_impact_engine_helpers import add_affected_item, engine_env

pytestmark = pytest.mark.django_db


def test_real_change_request_produces_persisted_findings_and_chains() -> None:
    with engine_env() as env:
        parent = make_requirement(env.workspace, title="Parent requirement")
        child = make_requirement(env.workspace, title="Derived requirement")
        TraceLinkService().create_trace_link(
            source_id=child.artifact_id,
            target_id=parent.artifact_id,
            link_type="derives-from",
            ctx=env.ctx,
            rationale="child derives from parent",
        )
        add_affected_item(env, parent.artifact, action="modify")

        run = env.engine.analyze(env.cr.id, env.ctx)

        assert run.status == "completed"
        assert run.gate_eligible is True
        assert run.roots_source == "change_set"
        assert run.algorithm_version == "v1"
        assert run.node_count == 2
        assert run.edge_count == 1
        assert run.path_count == 1
        assert run.finished_at is not None
        assert run.baseline_id is None

        finding = ChangeImpactFinding.objects.get(run=run)
        assert finding.artifact_id == str(child.artifact_id)
        assert finding.entity_type == "Requirement"
        assert finding.hop_distance == 1
        assert finding.via_link_types == ["derives-from"]
        assert finding.origin == "deterministic"
        assert finding.chain_count == 1
        assert str(finding.weight) == "1.0000"

        chain = finding.chains.get()
        assert chain.root_artifact_id == str(parent.artifact_id)
        assert chain.hop_distance == 1
        assert len(chain.path) == 1
        assert chain.path[0]["link_type"] == "derives-from"
        assert chain.path[0]["direction"] == "backward"
        assert chain.path[0]["artifact_id"] == str(child.artifact_id)


def test_run_records_the_workspace_fence_and_frontier() -> None:
    with engine_env() as env:
        parent = make_requirement(env.workspace)
        child = make_requirement(env.workspace)
        TraceLinkService().create_trace_link(
            source_id=child.artifact_id,
            target_id=parent.artifact_id,
            link_type="derives-from",
            ctx=env.ctx,
        )
        add_affected_item(env, parent.artifact)

        run = env.engine.analyze(env.cr.id, env.ctx)

        assert run.workspace_id == env.workspace.id
        assert set(run.visited_node_ids) == {
            str(parent.artifact_id),
            str(child.artifact_id),
        }
        assert run.root_item_ids == [str(parent.artifact_id)]


def test_foreign_tenant_change_request_is_not_found() -> None:
    from uuid import uuid4

    from application.base import NotFoundError

    with engine_env() as env:
        with pytest.raises(NotFoundError):
            env.engine.analyze(uuid4(), env.ctx)
