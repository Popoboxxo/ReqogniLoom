"""Fingerprint semantics (S4.4, spec §4.3.5).

The fingerprint is a *content image*: a no-op save must not make a run stale
(``version`` is excluded), while a lifecycle, catalog, policy or graph change
must. A missing capture row is fail-closed.
"""
from __future__ import annotations

import copy

import pytest

from application.change_impact_engine import (
    compute_affected_items_hash,
    compute_content_hash,
    compute_gate_fingerprint,
    compute_graph_fingerprint,
    compute_path_hash,
)
from application.models import ChangeImpactFinding
from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore
from persistence.tests.factories import make_requirement

from ._change_impact_engine_helpers import (
    add_affected_item,
    engine_env,
    make_artifact,
    make_link,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_content_hash_excludes_version_status_suspect_baseline() -> None:
    base = {"title": "A", "description": "B", "version": 1}
    assert compute_content_hash(base) == compute_content_hash(
        {**base, "version": 2}
    )
    assert compute_content_hash(base) != compute_content_hash(
        {**base, "title": "changed"}
    )
    excluded_only = compute_content_hash(
        {"version": 3, "status": "draft", "suspect": True, "baseline": "x"}
    )
    assert excluded_only == ""


def test_path_hash_is_order_sensitive_and_direction_aware() -> None:
    hop_a = {
        "artifact_id": "AAA",
        "link_id": "LLL1",
        "link_type": "verifies",
        "direction": "backward",
    }
    hop_b = {
        "artifact_id": "BBB",
        "link_id": "LLL2",
        "link_type": "derives-from",
        "direction": "forward",
    }
    assert compute_path_hash([hop_a, hop_b]) != compute_path_hash([hop_b, hop_a])
    assert compute_path_hash([hop_a]) == compute_path_hash(
        [{**hop_a, "artifact_id": "aaa"}]
    )


def test_graph_and_gate_fingerprint_helpers_are_deterministic() -> None:
    root = make_node("root", "hash-root")
    node = make_node("node", "hash-node", suspect=True)
    edges = [("l1", "verifies", root.artifact_id, node.artifact_id, "")]
    graph = compute_graph_fingerprint(
        algorithm_version="v1",
        roots=[root],
        nodes=[root, node],
        edges=edges,
        hierarchy_edges=[],
        catalog_hash="c",
        policy_hash_value="p",
    )
    gate = compute_gate_fingerprint(
        algorithm_version="v1",
        roots=[root],
        nodes=[root, node],
        edges=edges,
        hierarchy_edges=[],
        catalog_hash="c",
        policy_hash_value="p",
    )
    assert graph != gate  # the gate image carries ``suspect``
    assert graph == compute_graph_fingerprint(
        algorithm_version="v1",
        roots=[root],
        nodes=[node, root],
        edges=list(reversed(edges)),
        hierarchy_edges=[],
        catalog_hash="c",
        policy_hash_value="p",
    )
    assert compute_affected_items_hash([root]) != compute_affected_items_hash(
        [node]
    )


def make_node(artifact_id: str, content_hash: str, *, suspect: bool = False):
    from application.change_impact_engine import NodeState

    return NodeState(
        artifact_id=artifact_id,
        artifact_type="Requirement",
        content_hash=content_hash,
        lifecycle_status="active",
        workflow_state="draft",
        suspect=suspect,
    )


# ---------------------------------------------------------------------------
# Golden hash
# ---------------------------------------------------------------------------


def test_golden_fingerprint_for_a_fixed_small_graph() -> None:
    from uuid import UUID

    from persistence.models import Artifact, TraceLink

    with engine_env() as env:
        # Fixed UUIDs: the fingerprint necessarily includes artifact and link
        # ids, so a reproducible golden digest needs a reproducible graph.
        root = Artifact.objects.create(
            id=UUID(int=101),
            tenant=env.tenant,
            workspace=env.workspace,
            artifact_type="Requirement",
        )
        child = Artifact.objects.create(
            id=UUID(int=102),
            tenant=env.tenant,
            workspace=env.workspace,
            artifact_type="Requirement",
        )
        TraceLink.objects.create(
            id=UUID(int=201),
            tenant=env.tenant,
            source=child,
            target=root,
            link_type="derives-from",
        )
        add_affected_item(env, root)

        run = env.engine.analyze(env.cr.id, env.ctx)

        assert run.graph_fingerprint == GOLDEN_GRAPH
        assert run.gate_fingerprint == GOLDEN_GATE


#: Golden digests for the fixed graph above (fixed artifact/link UUIDs, bare
#: artifacts, default policy). They pin the fingerprint *composition*, so an
#: accidental change to a hashed field or to the canonicalisation fails here
#: instead of silently invalidating every stored run.
GOLDEN_GRAPH = "3c068d7082b31bd593f0439aeb2a551b3a8c6c07d46c81c78da6b88b5d18b418"
GOLDEN_GATE = "8136d73f85d64fdb67f1cdda0368548a2e36425e3bef2751a447474f4e213310"


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def test_no_op_save_does_not_change_the_gate_fingerprint() -> None:
    with engine_env() as env:
        requirement = make_requirement(env.workspace)
        root = requirement.artifact
        child = make_artifact(env, "child")
        make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        first = env.engine.analyze(env.cr.id, env.ctx)

        requirement.title = requirement.title
        requirement.save()  # bumps the optimistic-lock counter only
        second = env.engine.analyze(env.cr.id, env.ctx, force=True)

        assert second.gate_fingerprint == first.gate_fingerprint
        assert second.graph_fingerprint == first.graph_fingerprint


def test_lifecycle_status_change_changes_the_gate_fingerprint() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        child = make_artifact(env, "child")
        make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        first = env.engine.analyze(env.cr.id, env.ctx)

        root.lifecycle_status = "outdated"
        root.save(update_fields=["lifecycle_status"])
        second = env.engine.analyze(env.cr.id, env.ctx, force=True)

        assert second.gate_fingerprint != first.gate_fingerprint
        assert second.graph_fingerprint != first.graph_fingerprint


def test_new_node_and_edge_change_the_gate_fingerprint() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        child = make_artifact(env, "child")
        make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        first = env.engine.analyze(env.cr.id, env.ctx)

        make_artifact(env, "extra")
        extra = env.artifacts["extra"]
        make_link(env, extra, root, "derives-from")

        second = env.engine.analyze(env.cr.id, env.ctx, force=True)
        assert second.gate_fingerprint != first.gate_fingerprint


def test_catalog_change_changes_the_gate_fingerprint() -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        child = make_artifact(env, "child")
        make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        first = env.engine.analyze(env.cr.id, env.ctx)

        store = WorkspaceLinkTypeDefinitionStore()
        row = store.get(env.tenant.id, env.workspace.id, "derives-from")
        definition = copy.deepcopy(row.definition_json)
        definition["impact_weight"] = 0.5
        store.update(env.tenant.id, env.workspace.id, "derives-from", definition)

        second = env.engine.analyze(env.cr.id, env.ctx, force=True)
        assert second.catalog_hash != first.catalog_hash
        assert second.gate_fingerprint != first.gate_fingerprint


def test_policy_change_changes_the_gate_fingerprint() -> None:
    from application.change_impact_policy import MAX_DEPTH_KEY
    from application.preference_service import PreferenceService
    from persistence.tests.factories import ctx_for_user, make_user

    with engine_env() as env:
        artifacts = _short_chain(env)
        add_affected_item(env, artifacts[-1])

        first = env.engine.analyze(env.cr.id, env.ctx)

        admin = ctx_for_user(
            env.tenant,
            make_user(env.tenant),
            workspace=env.workspace,
            roles=("admin",),
        )
        PreferenceService().set_level(
            admin,
            scope="workspace",
            workspace_id=env.workspace.id,
            values={MAX_DEPTH_KEY: "2"},
        )
        second = env.engine.analyze(env.cr.id, env.ctx, force=True)

        assert second.policy_hash != first.policy_hash
        assert second.gate_fingerprint != first.gate_fingerprint


def _short_chain(env):
    from ._change_impact_engine_helpers import chain

    return chain(env, "node", 3)


# ---------------------------------------------------------------------------
# Fail-closed capture
# ---------------------------------------------------------------------------


def test_incomplete_capture_fails_the_run_without_findings(monkeypatch) -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        child = make_artifact(env, "child")
        make_link(env, child, root, "derives-from")
        add_affected_item(env, root)

        monkeypatch.setattr(
            "application.change_impact_engine.capture_states",
            lambda delta_index, tenant_id: {},
        )

        run = env.engine.analyze(env.cr.id, env.ctx)

        assert run.status == "failed"
        assert run.error == "capture_incomplete"
        assert not ChangeImpactFinding.objects.filter(run=run).exists()


def test_empty_workflow_state_fails_the_run(monkeypatch) -> None:
    with engine_env() as env:
        root = make_artifact(env, "root")
        add_affected_item(env, root)
        monkeypatch.setattr(
            "application.change_impact_engine.state_reader.current_states",
            lambda *args, **kwargs: {},
        )
        monkeypatch.setattr(
            "application.change_impact_engine.state_reader.initial_state",
            lambda item_type: "",
        )

        run = env.engine.analyze(env.cr.id, env.ctx)

        assert run.status == "failed"
        assert run.error == "capture_incomplete"
