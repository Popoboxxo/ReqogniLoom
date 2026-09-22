"""Regression tests for the explicit ``tenant_id`` defense-in-depth predicate on
RequirementBundleQueryService's raw-SQL architecture-tree walk (issue #433).

Requirements:
- REQ-L2-PL-010 (PostgreSQL Row-Level Security — acceptance criterion
  "ORM-Bypass-Test: Raw SQL ohne App-Kontext liefert keine Fremddaten")
- ADR-PL-03 (defense-in-depth: RLS is the *second* of two tenant-isolation
  layers, never the only one a query path may rely on)

Why this file exists
--------------------
``_ARCH_TREE_CTE`` (``requirement_bundle_service.py``) and its two call sites —
the main ``get_bundle`` query and the ``depth=None`` truncation probe — filter
``pl_tracelink`` by ``tenant_id`` explicitly, on top of the tables' ``FORCE ROW
LEVEL SECURITY`` policies. A whole-branch review mutation-tested that addition
(neutered every predicate to ``%s::uuid IS NOT NULL``, preserving parameter
arity) and found the existing suite still green — "51 passed, nothing fails" —
i.e. the hardening had zero regression coverage. These tests close that gap:
deleting or neutering any of the three predicates — including a text-preserving
semantic neutralisation of the main query's ``req_link.tenant_id`` guard — makes
at least one test here fail.

How the predicate is isolated from RLS (approach + justification)
-----------------------------------------------------------------
``pytest`` connects as the migration/bootstrap DB role (``.env`` ``DB_USER``,
``reqflow``), which the Docker Postgres image creates as a **superuser**. A
superuser bypasses RLS unconditionally, ``FORCE`` or not, so during the test run
RLS is *not* enforcing isolation and the explicit predicate is the only thing
narrowing these raw-SQL queries by tenant. That premise is asserted up front by
:class:`TestRLSBypassPrecondition`, so the behavioural tests below cannot be
silently vacuous if the role ever changes.

Both available strategies from the issue are used, deliberately:

1. **SQL-level assertions** (deterministic, independent of DB privileges): the
   shared CTE's text stays verbatim in the module constant, so the recursive
   term's predicate is asserted directly; the two inline call sites are captured
   at runtime with ``connection.execute_wrapper`` and asserted there, including
   the tenant id the placeholders are actually bound to.
2. **Behavioural assertions with adversarially seeded cross-tenant rows**:
   every tenant-scoped write path (and RLS) normally prevents a tenant-B link
   from targeting a tenant-A element, so such rows are seeded deliberately via
   the ``unscoped`` escape-hatch manager to model exactly the condition the
   predicate exists to survive — RLS not isolating. Without the predicate those
   rows become reachable from tenant A's root and the behavioural tests fail.

Note on ``get_bundle``'s *result*: the raw-SQL ``rows`` are re-filtered a few
lines later by ``Requirement.unscoped.filter(..., tenant_id=ctx.tenant_id)``
(``requirement_bundle_service.py``), so a requirement whose *own* tenant differs
from the caller's never reaches ``BundleResult.items`` — which is exactly why a
naive two-tenant test would not notice the main query's predicate being
neutered. That guard is therefore covered at the result level by a scenario the
downstream filter cannot mask: a ``TraceLink`` row carrying a foreign tenant
whose *endpoints* both belong to the caller (see
:class:`TestMainJoinTenantPredicateIsLoadBearing`). The walk-level guards
(``arch_tree`` contents and the directly-returned ``truncated_at_depth`` flag)
cover the shared CTE recursive term and the truncation probe.
"""
from __future__ import annotations

import contextlib
import re
from typing import Iterator
from uuid import UUID

import pytest
from django.db import connection

from application.requirement_bundle_service import (
    MAX_DEPTH,
    RequirementBundleQueryService,
    _ARCH_TREE_CTE,
)
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.types import LinkType

# PostgreSQL-only module: every assertion is built on raw SQL with
# PostgreSQL-specific syntax (``%s::uuid``, ``WITH RECURSIVE``) and on the
# ``pg_user`` catalogue. Mirror the sibling
# ``application/tests/test_rls_policies.py`` guard so a non-PostgreSQL backend
# skips cleanly instead of erroring at collection/first query.
_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

pytestmark = [pytest.mark.django_db, _pg_only]

# The aliases the guarded predicates are written against (the ``_ARCH_TREE_CTE``
# recursive term and the two call sites in requirement_bundle_service.py).
# ``_tenant_predicate_matches`` tolerates whitespace changes but deliberately
# pins the alias, the ``tenant_id`` column and the ``%s::uuid`` cast form: this
# is a regression ratchet whose job is to fail when this specific guard is
# *removed*, so a refactor that renames the alias or drops the explicit cast is
# expected to update these guards as well (a deliberate false-red, see
# TestGeneratedSqlCarriesTenantPredicate). Text-preserving *semantic*
# neutralisation is covered behaviourally, not by these text assertions — see
# TestMainJoinTenantPredicateIsLoadBearing.
_CTE_ALIAS = "tl"
_REQ_JOIN_ALIAS = "req_link"


def _tenant_predicate_matches(sql: str, alias: str) -> list[str]:
    """Return occurrences of ``<alias>.tenant_id = %s::uuid`` in *sql*."""
    return re.findall(rf"\b{re.escape(alias)}\.tenant_id\s*=\s*%s::uuid\b", sql)


_ALLOCATED_TO = LinkType.ALLOCATED_TO.value


# ---------------------------------------------------------------------------
# Fixtures + helpers
#
# Entities are created directly against the ORM, mirroring the established
# pattern in test_requirement_bundle_service.py: the service-layer invariants
# (e.g. "at most one root ArchitectureElement per workspace") govern the
# structural parent_id tree, not the ALLOCATED_TO allocation graph this service
# walks. The two tenants in each test are fully independent (own Workspace,
# ArchitectureElement, Requirement and ALLOCATED_TO TraceLink rows).
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant_a() -> Tenant:
    return Tenant.objects.create(name="Bundle Tenant A", slug="bundle-tenant-a")


@pytest.fixture
def tenant_b() -> Tenant:
    return Tenant.objects.create(name="Bundle Tenant B", slug="bundle-tenant-b")


@pytest.fixture
def workspace_a(tenant_a: Tenant) -> Workspace:
    return _make_workspace(tenant_a, "Bundle WS A")


@pytest.fixture
def workspace_b(tenant_b: Tenant) -> Workspace:
    return _make_workspace(tenant_b, "Bundle WS B")


@pytest.fixture
def ctx_a(tenant_a: Tenant) -> AuthContext:
    return _ctx_for(tenant_a, "a")


def _make_workspace(tenant: Tenant, name: str) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name=name)


def _ctx_for(tenant: Tenant, tag: str) -> AuthContext:
    user = User.objects.create(
        username=f"bundle-user-{tag}",
        email=f"bundle-{tag}@example.com",
        tenant=tenant,
    )
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
        api_key_id=None,
        tenant_name=tenant.name,
    )


def _make_element(tenant: Tenant, workspace: Workspace, title: str) -> ArchitectureElement:
    # Artifact is created inline (not via a helper that opens its own
    # ``_active`` block): ``_active``'s ``finally`` clears the thread-local, so
    # nesting two of them would clear the outer context on the inner exit.
    with _active(tenant):
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
        )
        return ArchitectureElement.objects.create(
            tenant=tenant, artifact=artifact, title=title, parent=None
        )


def _make_requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    with _active(tenant):
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant, artifact=artifact, title=title
        )


def _link(tenant: Tenant, source, target) -> TraceLink:
    """A tenant-consistent ALLOCATED_TO edge (source -> target)."""
    with _active(tenant):
        return TraceLink.objects.create(
            tenant=tenant,
            source=source.artifact,
            target=target.artifact,
            link_type=_ALLOCATED_TO,
        )


def _cross_tenant_link(link_tenant: Tenant, source, target) -> TraceLink:
    """Seed a link whose row-level ``tenant_id`` does not match its endpoints.

    This is the adversarial row the defense-in-depth predicate exists for: in
    production RLS would reject such a write, and the ORM tenant manager would
    not produce it — but the raw-SQL walk must still not trust the table to be
    well-formed. Seeded via ``unscoped`` on purpose (RLS is bypassed by the
    superuser test connection, see module docstring).
    """
    return TraceLink.unscoped.create(
        tenant=link_tenant,
        source=source.artifact,
        target=target.artifact,
        link_type=_ALLOCATED_TO,
    )


def _assert_cross_tenant_link_persisted(link_tenant: Tenant, source, target) -> None:
    """Prove the adversarial foreign-tenant row really exists (review finding N1).

    ``items == []`` (or "element absent from ``arch_tree``") is ambiguous on its
    own: a row filtered out by the tenant predicate and a row that was never
    written look identical. Asserting persistence makes each behavioural test
    self-contained instead of leaning on the external mutation probe for its
    non-vacuity.
    """
    persisted = TraceLink.unscoped.filter(
        tenant=link_tenant,
        source=source.artifact,
        target=target.artifact,
        link_type=_ALLOCATED_TO,
    ).exists()
    assert persisted, (
        "Adversarial cross-tenant TraceLink row was not persisted; the "
        "assertions below would be vacuous."
    )


def _seed_simple_graph(
    tenant: Tenant, workspace: Workspace, label: str
) -> tuple[ArchitectureElement, Requirement]:
    """One root element with one directly allocated requirement."""
    root = _make_element(tenant, workspace, f"{label} root")
    requirement = _make_requirement(tenant, workspace, f"{label} requirement")
    _link(tenant, requirement, root)
    return root, requirement


@contextlib.contextmanager
def _captured_statements() -> Iterator[list[tuple[str, object]]]:
    """Record every SQL statement (sql, params) executed inside the block."""
    captured: list[tuple[str, object]] = []

    def _wrapper(execute, sql: str, params: object, many: bool, context: dict):
        captured.append((sql, params))
        return execute(sql, params, many, context)

    with connection.execute_wrapper(_wrapper):
        yield captured


def _run_arch_tree(
    ctx: AuthContext, root_artifact_id: UUID, cap: int
) -> list[tuple]:
    """Execute the shared CTE alone and return its (element_artifact_id, depth) rows."""
    RequirementBundleQueryService._set_tenant_context(ctx)
    with connection.cursor() as cursor:
        cursor.execute(
            _ARCH_TREE_CTE
            + " SELECT element_artifact_id, depth FROM arch_tree ORDER BY depth;",
            [str(root_artifact_id), _ALLOCATED_TO, str(ctx.tenant_id), cap],
        )
        return cursor.fetchall()


# ---------------------------------------------------------------------------
# Premise: the pytest connection bypasses RLS
# ---------------------------------------------------------------------------


class TestRLSBypassPrecondition:
    """Asserts the environment premise the behavioural tests rely on.

    The suite connects as a superuser (``.env`` ``DB_USER``), and superusers
    bypass RLS unconditionally. If the test overlay ever switches to the
    least-privilege ``reqogniloom_app`` role, RLS would start masking the
    cross-tenant rows and the isolation tests would pass for the wrong reason —
    this assertion makes that change fail loudly instead.

    Three situations are told apart rather than conflated: (a) backend is not
    PostgreSQL — the module-level ``_pg_only`` marker (mirroring
    ``application/tests/test_rls_policies.py``) skips the whole module; (b)
    PostgreSQL but the connected role cannot be resolved — first assert; (c) the
    role exists but is not a superuser — second assert.
    """

    def test_test_connection_is_a_superuser_so_rls_is_bypassed(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT usesuper FROM pg_user WHERE usename = current_user")
            row = cursor.fetchone()

        assert row is not None, (
            "PostgreSQL backend, but current_user could not be resolved from "
            "pg_user. The RLS-bypass premise cannot be verified; re-evaluate "
            "these tests before trusting a green run."
        )
        assert row[0] is True, (
            "Backend is PostgreSQL and the role exists, but the pytest "
            "connection is NOT a superuser — so Row-Level Security is actually "
            "enforced and the explicit tenant_id predicate in "
            "requirement_bundle_service.py is not the only tenant filter. The "
            "behavioural tests would then pass for the wrong reason. "
            "Re-evaluate them before trusting a green run."
        )


# ---------------------------------------------------------------------------
# SQL-level guards (deterministic; independent of DB privileges)
# ---------------------------------------------------------------------------


class TestGeneratedSqlCarriesTenantPredicate:
    """Guards the predicate's presence in the generated SQL text.

    ``test_shared_cte_recursive_term_filters_by_tenant`` needs no database at
    all (the CTE is a module constant); the call-site test drives the real
    service and captures what it actually executed.

    Deliberate coupling (review finding F2): these assertions pin the alias
    names (``tl`` / ``req_link``), the ``%s::uuid`` cast form and the
    placeholder indices. That is intentional for a deletion ratchet — a
    legitimate refactor (alias rename, ``CAST(%s AS uuid)``, placeholder
    reordering) produces a false-red that must be resolved by updating the guard,
    not by weakening it. Whitespace is tolerated. Text-preserving *semantic*
    neutralisation (e.g. appending ``OR TRUE``) is deliberately NOT this test's
    job: it is covered behaviourally in
    :class:`TestMainJoinTenantPredicateIsLoadBearing` (main query) and
    :class:`TestArchTreeWalkTenantIsolation` /
    :class:`TestTruncationProbeTenantIsolation` (shared CTE term / probe).
    """

    def test_shared_cte_recursive_term_filters_by_tenant(self) -> None:
        matches = _tenant_predicate_matches(_ARCH_TREE_CTE, _CTE_ALIAS)
        assert matches, (
            "The recursive term of _ARCH_TREE_CTE no longer filters "
            "pl_tracelink by tenant_id. This is the shared text both call "
            "sites execute, so removing it removes the guard everywhere."
        )
        assert len(matches) == 1, (
            "Expected exactly one explicit tenant_id predicate in the shared "
            "CTE recursive term."
        )

    def test_both_query_call_sites_filter_by_tenant_and_bind_the_context_tenant(
        self, tenant_a: Tenant, workspace_a: Workspace, ctx_a: AuthContext
    ) -> None:
        """The main query AND the truncation probe both carry the predicate.

        Capturing at runtime (rather than asserting on a source slice) proves
        the predicate survives into the statement PostgreSQL actually receives,
        and that the placeholder is bound to the *authenticated* tenant id.
        """
        root, _ = _seed_simple_graph(tenant_a, workspace_a, "SQL guard")

        with _captured_statements() as captured:
            RequirementBundleQueryService().get_bundle(
                ctx_a, root_id=root.id, workspace_id=workspace_a.id, depth=None
            )

        arch_tree_statements = [
            (sql, params) for sql, params in captured if "arch_tree" in sql
        ]
        assert len(arch_tree_statements) == 2, (
            "Expected the main query and the depth=None truncation probe, both "
            f"of which share _ARCH_TREE_CTE; captured {len(arch_tree_statements)} "
            "arch_tree statements: "
            f"{[sql.splitlines()[0] for sql, _ in arch_tree_statements]}"
        )

        main = [item for item in arch_tree_statements if "SELECT DISTINCT ON" in item[0]]
        probe = [item for item in arch_tree_statements if "SELECT EXISTS (" in item[0]]
        assert len(main) == 1 and len(probe) == 1, (
            "Could not identify the main query and the truncation probe "
            "unambiguously from the captured statements."
        )

        main_sql, main_params = main[0]
        probe_sql, probe_params = probe[0]

        assert _tenant_predicate_matches(main_sql, _CTE_ALIAS), (
            "Main query lost the CTE recursive term's tenant predicate."
        )
        assert _tenant_predicate_matches(main_sql, _REQ_JOIN_ALIAS), (
            "Main query lost its Requirement-join tenant predicate "
            "(req_link.tenant_id)."
        )
        assert _tenant_predicate_matches(probe_sql, _CTE_ALIAS), (
            "Truncation probe lost the CTE recursive term's tenant predicate."
        )

        # Placeholder order (see _ARCH_TREE_CTE docstring): index 2 is the CTE's
        # tenant placeholder in both statements; index 5 is the main query's
        # second (req_link) placeholder. Deliberately pinned (F2): reordering the
        # placeholders is a contract change and must update this guard.
        assert str(main_params[2]) == str(ctx_a.tenant_id)
        assert str(main_params[5]) == str(ctx_a.tenant_id)
        assert str(probe_params[2]) == str(ctx_a.tenant_id)


# ---------------------------------------------------------------------------
# Behavioural guards (RLS bypassed by the superuser test connection)
# ---------------------------------------------------------------------------


class TestArchTreeWalkTenantIsolation:
    """The walk itself must never include reachable cross-tenant elements."""

    def test_arch_tree_walk_excludes_reachable_cross_tenant_element(
        self,
        tenant_a: Tenant,
        tenant_b: Tenant,
        workspace_a: Workspace,
        workspace_b: Workspace,
        ctx_a: AuthContext,
    ) -> None:
        """A tenant-B element linked onto tenant A's root must not be walked.

        Tenant B seeds an ALLOCATED_TO edge targeting tenant A's root (the
        adversarial row from the module docstring). Tenant A's own child IS
        walked. Without the explicit predicate, the recursion follows tenant B's
        edge as well and leaks ``elem_b`` into ``arch_tree``.
        """
        root_a = _make_element(tenant_a, workspace_a, "A root")
        child_a = _make_element(tenant_a, workspace_a, "A child")
        _link(tenant_a, child_a, root_a)

        elem_b = _make_element(tenant_b, workspace_b, "B element")
        _cross_tenant_link(tenant_b, elem_b, root_a)
        _assert_cross_tenant_link_persisted(tenant_b, elem_b, root_a)

        rows = _run_arch_tree(ctx_a, root_a.artifact_id, MAX_DEPTH)
        walked = {row[0] for row in rows}

        assert walked == {root_a.artifact_id, child_a.artifact_id}
        assert elem_b.artifact_id not in walked, (
            "arch_tree followed an ALLOCATED_TO edge belonging to another "
            "tenant — the recursive term's tenant_id predicate is not filtering."
        )


class TestTruncationProbeTenantIsolation:
    """The predicate also protects the directly-returned truncation flag."""

    def test_truncation_probe_ignores_cross_tenant_edge_beyond_cap(
        self,
        tenant_a: Tenant,
        tenant_b: Tenant,
        workspace_a: Workspace,
        workspace_b: Workspace,
        ctx_a: AuthContext,
    ) -> None:
        """A cross-tenant edge at the cap boundary must not flip truncation.

        Tenant A has a hierarchy exactly MAX_DEPTH deep that terminates
        naturally, so nothing was cut off: ``truncated_at_depth`` must be False.
        Tenant B adds an element allocated to the boundary element; without the
        probe's tenant predicate that foreign edge looks like a real child
        beyond the cap and flips the flag to True.

        ``truncated_at_depth`` is returned straight to the caller, so unlike the
        leaked requirement ids (re-filtered downstream) it is an end-to-end
        observable consequence of the predicate.
        """
        root_a = _make_element(tenant_a, workspace_a, "Boundary root")
        current = root_a
        for level in range(1, MAX_DEPTH + 1):
            next_element = _make_element(tenant_a, workspace_a, f"Boundary L{level}")
            _link(tenant_a, next_element, current)
            current = next_element
        boundary = current  # sits at depth == MAX_DEPTH

        elem_b = _make_element(tenant_b, workspace_b, "B extra child")
        _cross_tenant_link(tenant_b, elem_b, boundary)
        _assert_cross_tenant_link_persisted(tenant_b, elem_b, boundary)

        result = RequirementBundleQueryService().get_bundle(
            ctx_a, root_id=root_a.id, workspace_id=workspace_a.id, depth=None
        )

        assert result.truncated_at_depth is False, (
            "The truncation probe counted an ALLOCATED_TO edge owned by another "
            "tenant as a child beyond the depth cap — the probe's tenant_id "
            "predicate is not filtering."
        )


class TestMainJoinTenantPredicateIsLoadBearing:
    """The main query's own ``req_link.tenant_id`` predicate (review finding F1).

    :class:`TestBundleQueryTenantIsolation` cannot detect the main JOIN
    predicate being neutered: it seeds a *tenant-B requirement*, which the
    downstream ``Requirement.unscoped.filter(..., tenant_id=ctx.tenant_id)``
    re-filter discards anyway. This scenario removes that masking — the link row
    carries a foreign tenant while **both endpoints belong to the querying
    tenant**, so the downstream filter (which checks the Requirement's own
    tenant, not the link's) still matches, and only the main query's
    ``req_link.tenant_id = %s::uuid`` can keep the row out of the result.

    A separate control graph (tenant-consistent edge, same shape) proves the
    empty adversarial result is the predicate's doing and not a broken fixture.
    The control uses different endpoints on purpose: ``uq_tracelink_edge`` is a
    tenant-agnostic unique constraint on ``(source_id, target_id, link_type)``,
    so a local and a foreign row cannot coexist for the same edge.
    """

    def test_foreign_tenant_link_with_local_endpoints_is_not_returned(
        self,
        tenant_a: Tenant,
        tenant_b: Tenant,
        workspace_a: Workspace,
        ctx_a: AuthContext,
    ) -> None:
        service = RequirementBundleQueryService()

        # Control (non-vacuity): a tenant-consistent edge IS returned.
        root_control = _make_element(tenant_a, workspace_a, "A control root")
        req_control = _make_requirement(tenant_a, workspace_a, "A control requirement")
        _link(tenant_a, req_control, root_control)
        control = service.get_bundle(
            ctx_a, root_id=root_control.id, workspace_id=workspace_a.id, depth=None
        )
        assert {item.requirement_id for item in control.items} == {req_control.id}, (
            "Control graph was not returned — the assertion below would be "
            "vacuous, not evidence about the tenant predicate."
        )

        # Adversarial: the ONLY ALLOCATED_TO edge is a tenant-B row whose
        # endpoints are both tenant A's (see _cross_tenant_link). With the
        # predicate the main query sees no edge; without it the edge is followed,
        # req_a survives the downstream tenant filter (its own tenant IS A) and
        # items becomes non-empty.
        root_a = _make_element(tenant_a, workspace_a, "A root")
        req_a = _make_requirement(tenant_a, workspace_a, "A requirement")
        _cross_tenant_link(tenant_b, req_a, root_a)
        _assert_cross_tenant_link_persisted(tenant_b, req_a, root_a)

        result = service.get_bundle(
            ctx_a, root_id=root_a.id, workspace_id=workspace_a.id, depth=None
        )
        assert result.items == [], (
            "The main query followed an ALLOCATED_TO TraceLink row owned by "
            "another tenant: req_link.tenant_id is not filtering."
        )


class TestBundleQueryTenantIsolation:
    """End-to-end acceptance: a tenant-A-scoped query never returns tenant-B rows."""

    def test_bundle_query_scoped_to_tenant_a_never_returns_tenant_b_requirement(
        self,
        tenant_a: Tenant,
        tenant_b: Tenant,
        workspace_a: Workspace,
        workspace_b: Workspace,
        ctx_a: AuthContext,
    ) -> None:
        """Each tenant owns ArchitectureElement/Requirement/ALLOCATED_TO rows.

        The assertion is the issue's literal acceptance criterion. Note it is
        also guaranteed by the downstream
        ``Requirement.unscoped.filter(..., tenant_id=ctx.tenant_id)`` re-filter
        (see module docstring), so on its own it would NOT fail under the
        predicate mutation — the mutation-visible guards are
        :class:`TestArchTreeWalkTenantIsolation` /
        :class:`TestTruncationProbeTenantIsolation` (shared CTE term / probe) and
        :class:`TestMainJoinTenantPredicateIsLoadBearing` (the main query's own
        ``req_link.tenant_id``). This test keeps the public seam honest alongside
        them.
        """
        root_a, req_a = _seed_simple_graph(tenant_a, workspace_a, "A")
        root_b, req_b = _seed_simple_graph(tenant_b, workspace_b, "B")

        result = RequirementBundleQueryService().get_bundle(
            ctx_a, root_id=root_a.id, workspace_id=workspace_a.id, depth=None
        )

        requirement_ids = {item.requirement_id for item in result.items}
        assert requirement_ids == {req_a.id}
        assert req_b.id not in requirement_ids, (
            "Tenant A's bundle returned tenant B's Requirement."
        )
        assert all(
            item.found_under_element_id != req_b.artifact_id for item in result.items
        ), "Tenant B's element surfaced as an allocation target for tenant A."

        # Sanity: the tenant-B graph is real and reachable only through its own
        # root — querying as tenant B returns tenant B's requirement.
        ctx_b = _ctx_for(tenant_b, "b")
        result_b = RequirementBundleQueryService().get_bundle(
            ctx_b, root_id=root_b.id, workspace_id=workspace_b.id, depth=None
        )
        assert {item.requirement_id for item in result_b.items} == {req_b.id}
