"""Bounded traversal and determinism (S4.3 caps).

The cap values are code/hard caps; the tests use *more restrictive* call
parameters, which the policy ceiling allows.
"""
from __future__ import annotations

import pytest

from application.models import ChangeImpactFinding

from ._change_impact_engine_helpers import (
    add_affected_item,
    chain,
    engine_env,
    make_artifact,
    make_link,
)

pytestmark = pytest.mark.django_db


def test_depth_cap_truncates_and_reports_the_reason() -> None:
    with engine_env() as env:
        artifacts = chain(env, "node", 6)
        add_affected_item(env, artifacts[-1])  # root = deepest target

        run = env.engine.analyze(env.cr.id, env.ctx, max_depth=2)

        assert run.truncated is True
        assert run.truncated_reason == "depth"
        assert run.status == "completed"
        findings = list(ChangeImpactFinding.objects.filter(run=run))
        assert {finding.hop_distance for finding in findings} == {1, 2}
        assert len(findings) == 2


def test_node_cap_truncates_deterministically() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        children = [make_artifact(env, f"child{index}") for index in range(6)]
        for child in children:
            make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        run = env.engine.analyze(env.cr.id, env.ctx, max_nodes=3)

        assert run.truncated is True
        assert run.truncated_reason == "nodes"
        assert run.node_count <= 3
        # Deterministic selection: the lexicographically smallest ids survive
        # (the traversal walks a sorted frontier).
        expected = sorted(str(child.id) for child in children)[:2]
        assert sorted(
            ChangeImpactFinding.objects.filter(run=run).values_list(
                "artifact_id", flat=True
            )
        ) == expected


def test_repeat_run_is_byte_identical_in_order_and_fingerprints() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        for index in range(4):
            child = make_artifact(env, f"child{index}")
            make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        first = env.engine.analyze(env.cr.id, env.ctx)
        second = env.engine.analyze(env.cr.id, env.ctx, force=True)

        assert first.id != second.id
        assert first.graph_fingerprint == second.graph_fingerprint
        assert first.gate_fingerprint == second.gate_fingerprint
        assert first.affected_items_hash == second.affected_items_hash
        assert first.visited_node_ids == second.visited_node_ids

        def snapshot(run):
            return [
                (
                    finding.artifact_id,
                    finding.severity,
                    finding.weight,
                    finding.hop_distance,
                    [(chain.path_hash, chain.weight) for chain in finding.chains.all()],
                )
                for finding in ChangeImpactFinding.objects.filter(run=run).order_by(
                    "artifact_id"
                )
            ]

        assert snapshot(first) == snapshot(second)


def test_identical_run_is_reused_without_force() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        child = make_artifact(env, "child")
        make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        first = env.engine.analyze(env.cr.id, env.ctx)
        second = env.engine.analyze(env.cr.id, env.ctx)

        assert first.id == second.id
        assert ChangeImpactFinding.objects.filter(run=first).count() == 1


def test_changed_graph_is_not_reused() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        first_child = make_artifact(env, "first")
        make_link(env, first_child, root, "derives-from")
        add_affected_item(env, root)

        first = env.engine.analyze(env.cr.id, env.ctx)

        second_child = make_artifact(env, "second")
        make_link(env, second_child, root, "derives-from")

        second = env.engine.analyze(env.cr.id, env.ctx)
        assert second.id != first.id
        assert second.graph_fingerprint != first.graph_fingerprint


def test_explicit_roots_are_not_gate_eligible() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        child = make_artifact(env, "child")
        make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        run = env.engine.analyze(env.cr.id, env.ctx, root_item_ids=[root.id])

        assert run.roots_source == "explicit"
        assert run.gate_eligible is False
        assert run.root_item_ids == [str(root.id)]


def test_change_set_roots_are_gate_eligible() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        add_affected_item(env, root)

        run = env.engine.analyze(env.cr.id, env.ctx)

        assert run.roots_source == "change_set"
        assert run.gate_eligible is True


def test_foreign_explicit_root_raises_without_leaking_existence() -> None:
    from application.base import ValidationError

    with engine_env() as env:
        root = make_artifact(env, "root")
        add_affected_item(env, root)
        foreign = _uuid4()

        with pytest.raises(ValidationError) as excinfo:
            env.engine.analyze(env.cr.id, env.ctx, root_item_ids=[foreign])

        assert str(foreign) not in str(excinfo.value)


def _uuid4():
    from uuid import uuid4

    return uuid4()
