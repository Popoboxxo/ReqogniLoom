"""Graph semantics of the change-impact engine (S4.2/S4.3).

Covers diamond, cycle, fan-out, the ``Artifact.parent_id`` hierarchy union, a
``suspect_rule="none"`` edge, the add/modify/remove direction rules and the
"semantic is never blocking" invariant.
"""
from __future__ import annotations

import logging

import pytest

from application.change_impact_engine import (
    WARNING_CHANGE_SET_ITEM_WITHOUT_TRACE,
)
from application.models import ChangeImpactFinding

from ._change_impact_engine_helpers import (
    add_affected_item,
    engine_env,
    make_artifact,
    make_link,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Shape tests
# ---------------------------------------------------------------------------


def test_diamond_reaches_the_join_node_on_two_paths() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        left = make_artifact(env, "left")
        right = make_artifact(env, "right")
        join = make_artifact(env, "join")
        # derives-from: target -> source, so every source points at its parent.
        make_link(env, left, root, "derives-from")
        make_link(env, right, root, "derives-from")
        make_link(env, join, left, "derives-from")
        make_link(env, join, right, "derives-from")
        add_affected_item(env, root)

        run = env.engine.analyze(env.cr.id, env.ctx)

        findings = {
            finding.artifact_id: finding
            for finding in ChangeImpactFinding.objects.filter(run=run)
        }
        assert set(findings) == {str(left.id), str(right.id), str(join.id)}
        join_finding = findings[str(join.id)]
        assert join_finding.hop_distance == 2
        assert join_finding.chain_count == 2
        assert join_finding.chains.count() == 2
        assert len({chain.path_hash for chain in join_finding.chains.all()}) == 2
        assert run.path_count == 4


def test_cycle_terminates_and_keeps_the_shortest_distance() -> None:
    with engine_env() as env:
        first = make_artifact(env, "first")
        second = make_artifact(env, "second")
        make_link(env, second, first, "derives-from")
        make_link(env, first, second, "derives-from")
        add_affected_item(env, first)

        run = env.engine.analyze(env.cr.id, env.ctx)

        findings = list(ChangeImpactFinding.objects.filter(run=run))
        assert [finding.artifact_id for finding in findings] == [str(second.id)]
        assert findings[0].hop_distance == 1


def test_fan_out_finds_every_child_at_depth_one() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        children = [make_artifact(env, f"child{index}") for index in range(5)]
        for child in children:
            make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        run = env.engine.analyze(env.cr.id, env.ctx)

        findings = list(ChangeImpactFinding.objects.filter(run=run))
        assert {finding.artifact_id for finding in findings} == {
            str(child.id) for child in children
        }
        assert all(finding.hop_distance == 1 for finding in findings)


def test_artifact_parent_hierarchy_is_a_propagation_edge() -> None:
    with engine_env() as env:
        parent = make_artifact(env, "parent")
        child = make_artifact(env, "child", parent=parent)
        grandchild = make_artifact(env, "grandchild", parent=child)
        add_affected_item(env, parent)

        run = env.engine.analyze(env.cr.id, env.ctx)

        findings = {
            finding.artifact_id: finding
            for finding in ChangeImpactFinding.objects.filter(run=run)
        }
        assert set(findings) == {str(child.id), str(grandchild.id)}
        assert findings[str(grandchild.id)].hop_distance == 2
        child_chain = findings[str(child.id)].chains.get()
        assert child_chain.path[0]["link_type"] == "hierarchy"
        assert child_chain.origin == "deterministic"
        assert findings[str(child.id)].via_link_types == ["hierarchy"]


def test_suspect_rule_none_edge_is_skipped() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        referenced = make_artifact(env, "referenced")
        # ``references`` carries suspect_rule="none": no impact propagation.
        make_link(env, root, referenced, "references")
        add_affected_item(env, root)

        run = env.engine.analyze(env.cr.id, env.ctx)

        assert not ChangeImpactFinding.objects.filter(run=run).exists()


# ---------------------------------------------------------------------------
# Change-action semantics
# ---------------------------------------------------------------------------


def test_modify_traverses_the_catalog_direction_from_either_endpoint() -> None:
    with engine_env() as env:
        requirement = make_artifact(env, "requirement")
        test_case = make_artifact(env, "test", artifact_type="TestCase")
        # verifies: target_change_flags_source -> requirement change flags test.
        make_link(env, test_case, requirement, "verifies")
        add_affected_item(env, requirement)

        run = env.engine.analyze(env.cr.id, env.ctx)

        findings = list(ChangeImpactFinding.objects.filter(run=run))
        assert [finding.artifact_id for finding in findings] == [str(test_case.id)]


def test_remove_follows_only_incoming_links() -> None:
    with engine_env() as env:
        requirement = make_artifact(env, "requirement")
        test_case = make_artifact(env, "test", artifact_type="TestCase")
        make_link(env, test_case, requirement, "verifies")

        # Removing the requirement: the verifying test case is affected.
        add_affected_item(env, requirement, action="remove")
        run = env.engine.analyze(env.cr.id, env.ctx)
        assert list(
            ChangeImpactFinding.objects.filter(run=run).values_list(
                "artifact_id", flat=True
            )
        ) == [str(test_case.id)]

    with engine_env() as env:
        requirement = make_artifact(env, "requirement")
        test_case = make_artifact(env, "test", artifact_type="TestCase")
        make_link(env, test_case, requirement, "verifies")

        # Removing the test case: nothing points *at* it, so no finding.
        add_affected_item(env, test_case, action="remove")
        run = env.engine.analyze(env.cr.id, env.ctx)
        assert not ChangeImpactFinding.objects.filter(run=run).exists()


def test_add_without_mandatory_trace_logs_the_s2_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with engine_env() as env:
        added = make_artifact(env, "added")
        add_affected_item(env, added, action="add")

        with caplog.at_level(logging.WARNING):
            run = env.engine.analyze(env.cr.id, env.ctx)

        assert any(
            WARNING_CHANGE_SET_ITEM_WITHOUT_TRACE in record.message
            for record in caplog.records
        )
        # The warning is not a synthetic finding and cannot affect the gate.
        assert not ChangeImpactFinding.objects.filter(run=run).exists()


def test_add_with_allocated_to_edge_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with engine_env() as env:
        added = make_artifact(env, "added")
        element = make_artifact(env, "element", artifact_type="ArchitectureElement")
        make_link(env, added, element, "allocated-to")
        add_affected_item(env, added, action="add")

        with caplog.at_level(logging.WARNING):
            env.engine.analyze(env.cr.id, env.ctx)

        assert not any(
            WARNING_CHANGE_SET_ITEM_WITHOUT_TRACE in record.message
            for record in caplog.records
        )


# ---------------------------------------------------------------------------
# Semantic edges
# ---------------------------------------------------------------------------


def test_semantic_edges_are_opt_in_and_never_blocking() -> None:
    from context_graph.models import ContextEdge

    with engine_env() as env:
        root = make_artifact(env, "root")
        related = make_artifact(env, "related")
        ContextEdge.objects.create(
            tenant=env.tenant,
            source=root,
            target=related,
            edge_kind="related",
            origin="derived-embedding",
            confidence=1.0,
            generator="test-v1",
        )
        add_affected_item(env, root)

        # Policy denies semantic edges by default -> the request cannot enable
        # them (policy is a ceiling).
        run = env.engine.analyze(env.cr.id, env.ctx, include_semantic=True)
        assert run.include_semantic is False
        assert not ChangeImpactFinding.objects.filter(run=run).exists()

    with engine_env() as env:
        root = make_artifact(env, "root")
        related = make_artifact(env, "related")
        ContextEdge.objects.create(
            tenant=env.tenant,
            source=root,
            target=related,
            edge_kind="related",
            origin="derived-embedding",
            confidence=1.0,
            generator="test-v1",
        )
        add_affected_item(env, root)
        _allow_semantic_and_full_policy(env)

        run = env.engine.analyze(env.cr.id, env.ctx)
        assert run.include_semantic is True
        finding = ChangeImpactFinding.objects.get(run=run)
        assert finding.origin == "semantic"
        # weight 1.0 within two hops would be blocking for a deterministic
        # edge; the semantic cap keeps it at warning.
        assert finding.severity != ChangeImpactFinding.Severity.BLOCKING


def _allow_semantic_and_full_policy(env) -> None:
    """Set the workspace policy to allow semantic edges."""
    from application.preference_service import PreferenceService
    from application.change_impact_policy import SEMANTIC_EDGES_KEY
    from persistence.tests.factories import ctx_for_user, make_user

    admin = ctx_for_user(
        env.tenant, make_user(env.tenant), workspace=env.workspace, roles=("admin",)
    )
    PreferenceService().set_level(
        admin,
        scope="workspace",
        workspace_id=env.workspace.id,
        values={SEMANTIC_EDGES_KEY: True},
    )
