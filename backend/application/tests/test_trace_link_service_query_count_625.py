"""Regression test for #625 — TraceLink creation must not be N+1 on Artifact.

Symptom (found in the Playwright CI job for PR #625): the ``seed_toothbrush``
step between ``migrate`` and the backend start logged 13,000-17,000 individual
``SELECT ... FROM "pl_artifact" WHERE tenant_id = ? AND id = ? ORDER BY id ASC
LIMIT 1`` statements and took ~2.5 minutes — per E2E shard, of which there are
four. Measured locally before the fix: 52,298 queries / 178 s for one
``seed_toothbrush`` run, 13,438 of them that single-row Artifact SELECT.

Root cause was not in the seeder. ``TraceLinkService.create_trace_link`` read
the *same two* endpoint Artifact rows up to six times per link:

  1./2. ``_resolve_artifact_id(source)`` / ``(target)`` — probe "is this
        already an Artifact id?", then discard the row it just read;
  3./4. ``_check_se_semantics`` — re-SELECT both rows for their
        ``artifact_type``/``workspace_id``;
  5./6. ``TraceLinkManager.create`` — ``Artifact.unscoped.get()`` on both for
        the cross-tenant guard;
  (+1)  the ``post_save`` cache-invalidation signal re-resolved the source
        artifact's workspace, and the embedding text triggered up to four more
        single-row reads through the reverse ``requirement`` /
        ``architecture_element`` relations.

The seeder only made it visible: ~1,974 links x ~7 reads. Every REST
``POST /api/v1/trace-links/`` and every MCP ``traceability.create_link`` call
paid the same cost.

The fix keeps each row that is read and passes it down instead of re-reading
it. This test pins the property that matters — the per-link cost is a small
constant, and creating more links does not make each additional link more
expensive.
"""
from __future__ import annotations

import re
import uuid
from unittest.mock import MagicMock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from application.base import ValidationError
from application.trace_link_service import TraceLinkService
from persistence.models import Artifact, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

#: Single-row Artifact lookup — the exact shape that flooded the CI log.
_ARTIFACT_ROW_SELECT = re.compile(
    r'^SELECT .*FROM "pl_artifact".*"pl_artifact"\."id" =', re.IGNORECASE | re.DOTALL
)

#: Upper bound on single-row Artifact SELECTs per create_trace_link() call.
#: Before the fix this was 7. Two remain and are load-bearing:
#: ``_resolve_artifact`` reads each endpoint exactly once (source + target),
#: and TraceLinkManager re-reads them ``unscoped`` for the cross-tenant guard
#: (REQ-L2-TE-011) — deliberately *not* reusing the tenant-scoped rows, since
#: a tenant-scoped read can never observe the foreign-tenant row that guard
#: exists to reject. A regression that reintroduces a redundant read trips
#: this immediately.
MAX_ARTIFACT_ROW_SELECTS_PER_LINK = 4


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="T-625", slug="t-625")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        yield Workspace.objects.create(tenant=tenant, name="WS-625")
    finally:
        TenantContext.clear_tenant()


def _ctx(tenant: Tenant) -> MagicMock:
    ctx = MagicMock()
    ctx.active_roles = ("admin",)
    ctx.tenant_id = tenant.id
    ctx.user_id = None
    return ctx


@pytest.fixture
def se_workspace(tenant: Tenant) -> Workspace:
    """Workspace configured for se_mode, i.e. with the SE endpoint gate live.

    Review M1: no pre-existing test reaches ``check_se_link_semantics()``
    through ``create_trace_link`` — they either patch ``_check_se_semantics``
    out or run in workspaces with no ``WorkspacePresetConfig`` at all (the
    gate then returns early as "dev_mode / unconfigured"). The artifact types
    matter too: the matrix only constrains the exact strings in
    ``SE_CORE_ARTIFACT_TYPES``, so the lowercase ``"requirement"`` used
    elsewhere in this module is permissive by design.
    """
    from presets.models import WorkspacePresetConfig

    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="WS-625-SE")
        WorkspacePresetConfig.objects.create(
            tenant=tenant,
            workspace=workspace,
            active_tier="extended",
            terminology_profile="se_mode",
        )
        yield workspace
    finally:
        TenantContext.clear_tenant()


def _artifact(
    tenant: Tenant, workspace: Workspace, artifact_type: str = "requirement"
) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _artifact_row_selects(captured) -> list[str]:
    return [
        q["sql"]
        for q in captured
        if _ARTIFACT_ROW_SELECT.match(q["sql"].strip())
    ]


class TestCreateTraceLinkIsNotArtifactNPlusOne:
    def test_single_create_reads_each_endpoint_a_bounded_number_of_times(
        self, tenant, workspace
    ):
        """One link creation must not re-read its two endpoints six times."""
        svc = TraceLinkService()
        ctx = _ctx(tenant)
        TenantContext.set_tenant(tenant.id)
        try:
            source = _artifact(tenant, workspace)
            target = _artifact(tenant, workspace)

            with CaptureQueriesContext(connection) as cap:
                svc.create_trace_link(
                    source_id=source.id,
                    target_id=target.id,
                    link_type="traces",
                    ctx=ctx,
                )
        finally:
            TenantContext.clear_tenant()

        row_selects = _artifact_row_selects(cap.captured_queries)
        assert len(row_selects) <= MAX_ARTIFACT_ROW_SELECTS_PER_LINK, (
            f"create_trace_link issued {len(row_selects)} single-row "
            f"pl_artifact SELECTs (budget {MAX_ARTIFACT_ROW_SELECTS_PER_LINK}) "
            "— an endpoint Artifact is being re-read instead of reused "
            "(#625):\n" + "\n".join(row_selects)
        )

    def test_per_link_cost_does_not_grow_with_the_number_of_links(
        self, tenant, workspace
    ):
        """The Nth link must cost the same as the first.

        This is the property the CI log actually violated: cycle detection
        materialized every existing TraceLink of the same type *with both
        endpoint Artifacts joined in* (``select_related("source", "target")``),
        so per-link work grew linearly and total work quadratically. Comparing
        a late creation against an early one catches that without asserting a
        brittle absolute number.
        """
        svc = TraceLinkService()
        ctx = _ctx(tenant)
        TenantContext.set_tenant(tenant.id)
        try:
            first_source = _artifact(tenant, workspace)
            first_target = _artifact(tenant, workspace)
            with CaptureQueriesContext(connection) as cap_first:
                svc.create_trace_link(
                    source_id=first_source.id,
                    target_id=first_target.id,
                    link_type="traces",
                    ctx=ctx,
                )

            # Build up a graph of the same link type.
            for _ in range(25):
                svc.create_trace_link(
                    source_id=_artifact(tenant, workspace).id,
                    target_id=_artifact(tenant, workspace).id,
                    link_type="traces",
                    ctx=ctx,
                )

            last_source = _artifact(tenant, workspace)
            last_target = _artifact(tenant, workspace)
            with CaptureQueriesContext(connection) as cap_last:
                svc.create_trace_link(
                    source_id=last_source.id,
                    target_id=last_target.id,
                    link_type="traces",
                    ctx=ctx,
                )
        finally:
            TenantContext.clear_tenant()

        assert len(cap_last.captured_queries) == len(cap_first.captured_queries), (
            "creating a link into a populated graph issued "
            f"{len(cap_last.captured_queries)} queries vs "
            f"{len(cap_first.captured_queries)} for the first link — per-link "
            "cost still scales with the graph size (#625)"
        )

        # ...and the rows that query returns must not scale either: the
        # cycle-detection SELECT is the only unbounded read in the whole
        # create path (it spans every link of this type in the tenant), so it
        # must read the two FK id columns and nothing else. Identified by
        # being filtered on link_type rather than on a single link id — the
        # embedding re-read is also a pl_tracelink SELECT, but it is bounded
        # (WHERE id = ...) and legitimately joins its endpoints for the title.
        cycle_selects = [
            q["sql"]
            for q in cap_last.captured_queries
            if '"pl_tracelink"' in q["sql"]
            and q["sql"].strip().upper().startswith("SELECT")
            and '"pl_tracelink"."link_type" =' in q["sql"]
            and '"pl_tracelink"."id" =' not in q["sql"]
        ]
        assert cycle_selects, "create_trace_link never ran cycle detection"
        # Review L2: the rewrite swapped the tenant-scoped default manager for
        # a hand-built queryset. Pin that it is still tenant-scoped — dropping
        # the predicate would leak foreign-tenant edges into cycle detection
        # (REQ-L2-TE-011) without failing any behavioural test.
        assert '"pl_tracelink"."tenant_id" =' in cycle_selects[0], (
            "the cycle-detection SELECT lost its tenant predicate:\n"
            + cycle_selects[0]
        )
        assert not any('"pl_artifact"' in sql for sql in cycle_selects), (
            "the cycle-detection SELECT still joins pl_artifact — every "
            "existing link now drags two Artifact rows into memory on every "
            "single write (#625):\n" + "\n".join(cycle_selects)
        )
        assert not any('"embedding"' in sql for sql in cycle_selects), (
            "the cycle-detection SELECT fetches the 1536-dim embedding "
            "column (#571 F7 regression):\n" + "\n".join(cycle_selects)
        )


class TestResolveArtifactStillResolvesEveryEntityType:
    """The refactor must not narrow _resolve_artifact_id's contract."""

    def test_artifact_id_resolves_to_itself_and_returns_the_row(
        self, tenant, workspace
    ):
        svc = TraceLinkService()
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = _artifact(tenant, workspace)
            resolved_id, resolved_row = svc._resolve_artifact(artifact.id)
            assert resolved_id == artifact.id
            assert resolved_row is not None
            assert resolved_row.id == artifact.id
            # Public/legacy shape unchanged for every other caller.
            assert svc._resolve_artifact_id(artifact.id) == artifact.id
        finally:
            TenantContext.clear_tenant()

    def test_requirement_id_still_resolves_and_costs_no_extra_query(
        self, tenant, workspace
    ):
        """The entity probes deliberately return no Artifact row.

        Only step 1 (``entity_id`` *is* an Artifact id) hands the row back —
        it is the one probe that reads ``pl_artifact`` anyway. The business
        entity probes stay exactly as cheap as before the #625 fix (no extra
        join added for a row this path does not need), and the caller falls
        back to its own lookup.
        """
        from persistence.models import Requirement

        svc = TraceLinkService()
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = _artifact(tenant, workspace)
            req = Requirement.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact=artifact,
                title="R-625",
            )
            with CaptureQueriesContext(connection) as cap:
                resolved_id, resolved_row = svc._resolve_artifact(req.id)
        finally:
            TenantContext.clear_tenant()

        assert resolved_id == artifact.id
        assert resolved_row is None
        # Artifact probe (miss) + Requirement probe (hit) — nothing more.
        assert len(cap.captured_queries) == 2, (
            "resolving a Requirement id should take exactly two probes:\n"
            + "\n".join(q["sql"] for q in cap.captured_queries)
        )

    def test_unknown_id_still_raises_not_found(self, tenant):
        from application.base import NotFoundError

        svc = TraceLinkService()
        TenantContext.set_tenant(tenant.id)
        try:
            with pytest.raises(NotFoundError):
                svc._resolve_artifact(uuid.uuid4())
        finally:
            TenantContext.clear_tenant()


class TestSeGateStillFiresOnTheReusePath:
    """Review M1: the SE endpoint gate must still reject on the fast path.

    ``create_trace_link`` now hands ``_check_se_semantics`` the Artifact rows
    it already read instead of letting it re-SELECT them. That is exactly the
    branch a mistake would hide in: if the reused rows were wrong, missing, or
    silently dropped, the gate would wave everything through and no existing
    test would notice — the whole repo's coverage of this gate goes through
    the *fetch* branch or skips the gate entirely.

    ``implements`` is constrained to ArchitectureElement -> Requirement
    (traceability.types.SE_LINK_SEMANTICS), which gives one clean reject and
    one clean accept over the same code path.
    """

    def test_implements_requirement_to_requirement_is_rejected(
        self, tenant, se_workspace
    ):
        svc = TraceLinkService()
        ctx = _ctx(tenant)
        TenantContext.set_tenant(tenant.id)
        try:
            source = _artifact(tenant, se_workspace, "Requirement")
            target = _artifact(tenant, se_workspace, "Requirement")

            with CaptureQueriesContext(connection) as cap:
                with pytest.raises(ValidationError, match="SE mode"):
                    svc.create_trace_link(
                        source_id=source.id,
                        target_id=target.id,
                        link_type="implements",
                        ctx=ctx,
                    )
        finally:
            TenantContext.clear_tenant()

        # The rejection must come from the reused rows, not from a re-read:
        # only the two _resolve_artifact probes may touch pl_artifact, since
        # the link never reaches TraceLinkManager's unscoped guard.
        assert len(_artifact_row_selects(cap.captured_queries)) == 2, (
            "the SE gate re-read its endpoints instead of reusing them"
        )

    def test_implements_architecture_to_requirement_is_accepted(
        self, tenant, se_workspace
    ):
        svc = TraceLinkService()
        ctx = _ctx(tenant)
        TenantContext.set_tenant(tenant.id)
        try:
            source = _artifact(tenant, se_workspace, "ArchitectureElement")
            target = _artifact(tenant, se_workspace, "Requirement")

            link = svc.create_trace_link(
                source_id=source.id,
                target_id=target.id,
                link_type="implements",
                ctx=ctx,
            )
        finally:
            TenantContext.clear_tenant()

        assert link is not None
        assert str(link.source_id) == str(source.id)
        assert str(link.target_id) == str(target.id)

    def test_mismatched_reused_artifact_is_ignored_not_trusted(
        self, tenant, se_workspace
    ):
        """Review M2: the id stays authoritative, the passed-in row does not.

        A caller handing over the wrong instance must not steer the gate. Here
        the *ids* describe a legal ArchitectureElement -> Requirement link
        while the *objects* describe an illegal Requirement -> Requirement
        one; trusting the objects would raise, so a clean create proves the
        mismatch was detected and the rows re-read from the ids.
        """
        svc = TraceLinkService()
        ctx = _ctx(tenant)
        TenantContext.set_tenant(tenant.id)
        try:
            source = _artifact(tenant, se_workspace, "ArchitectureElement")
            target = _artifact(tenant, se_workspace, "Requirement")
            impostor = _artifact(tenant, se_workspace, "Requirement")

            svc._check_se_semantics(
                source.id,
                target.id,
                "implements",
                source_artifact=impostor,
                target_artifact=target,
            )
        finally:
            TenantContext.clear_tenant()
