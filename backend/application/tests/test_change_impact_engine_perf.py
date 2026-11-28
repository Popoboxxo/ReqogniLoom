"""Performance and query-count guarantees (S4.3).

The traversal is frontier-batched: the query count must grow with
``max_depth`` (a small constant), **not** with the number of nodes. The wall
clock bound is deliberately generous (3 s) so a slow CI box does not flake.
"""
from __future__ import annotations

import time

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from application.change_impact_policy import MAX_DEPTH_KEY, MAX_NODES_KEY
from application.preference_service import PreferenceService
from persistence.tests.factories import ctx_for_user, make_user

from ._change_impact_engine_helpers import (
    add_affected_item,
    engine_env,
    make_artifact,
    make_link,
)

pytestmark = pytest.mark.django_db


def _allow_full_caps(env) -> None:
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
        values={MAX_NODES_KEY: "500", MAX_DEPTH_KEY: "6"},
    )


def _star_graph(env, children: int):
    root = make_artifact(env, "root")
    for index in range(children):
        child = make_artifact(env, f"child{index}")
        make_link(env, child, root, "derives-from")
    add_affected_item(env, root)
    return root


def _measure(children: int) -> tuple[int, float, int]:
    with engine_env() as env:
        _allow_full_caps(env)
        _star_graph(env, children)
        with CaptureQueriesContext(connection) as captured:
            started = time.perf_counter()
            run = env.engine.analyze(env.cr.id, env.ctx)
            elapsed = time.perf_counter() - started
        return len(captured), elapsed, run.node_count


def test_500_nodes_complete_quickly_with_constant_query_count() -> None:
    small_queries, _, small_nodes = _measure(48)
    large_queries, elapsed, large_nodes = _measure(499)

    assert small_nodes == 49  # root + 48
    assert large_nodes == 500  # root + 499, cap reached exactly
    assert elapsed < 3.0

    # Query count is O(max_depth), not O(nodes): ten times the nodes must not
    # add a per-node round trip. A generous constant margin absorbs optional
    # per-type capture queries that only appear with more entity kinds.
    assert large_queries <= small_queries + 8, (
        f"query count grew with the node count: {small_queries} -> "
        f"{large_queries}"
    )
