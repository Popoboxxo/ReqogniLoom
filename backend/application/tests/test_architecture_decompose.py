"""
ArchitectureDecomposeService (SysEng 2.0 N1) — Draft-Staging copilot tests.

UMSETZUNGSPLAN_SYSENG_2.0.md §3.1 + §4 Phase 4a. Covers the three acceptance
criteria:

  * Draft is staged (generate writes nothing); commit is transactional and its
    output passes the SE-Auditor (ARCH-003/TRACE-P4/P5 verified by the real
    RuleEngine).
  * Preset gating: N1 is blocked in the ``minimal`` rigor preset.
  * Partial-commit rollback: a simulated failure mid-commit leaves no orphaned
    architecture elements. A separate test proves the post-commit auditor gate
    also rolls back the whole batch when the generated graph would violate
    TRACE-P5/ARCH-003.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from application.architecture_decompose_service import (
    ArchitectureDecomposeService,
    DecompositionAuditError,
    DecompositionNotAvailableError,
)
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from auth_tenancy.context import AuthContext
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
from presets.services import switch_preset
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures + helpers
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
def tenant() -> Tenant:
    return Tenant.objects.create(name="N1 Tenant", slug="n1-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="n1-user", email="n1@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="N1-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="N1 Tenant",
    )


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _requirement(tenant, workspace, title: str = "Req") -> Requirement:
    art = _artifact(tenant, workspace, "Requirement")
    return Requirement.objects.create(tenant=tenant, artifact=art, title=title)


def _arch(tenant, workspace, title: str = "AE") -> ArchitectureElement:
    art = _artifact(tenant, workspace, "ArchitectureElement")
    return ArchitectureElement.objects.create(tenant=tenant, artifact=art, title=title)


def _allocate(tenant, req: Requirement, arch: ArchitectureElement) -> TraceLink:
    """Create the allocated-to link req -> arch (the N1 anchor)."""
    return TraceLink.objects.create(
        tenant=tenant,
        source=req.artifact,
        target=arch.artifact,
        link_type=LinkType.ALLOCATED_TO.value,
    )


def _seed_anchored_element(tenant, workspace):
    """Root ArchitectureElement + an allocated anchor Requirement."""
    root = _arch(tenant, workspace, "Payment Subsystem")
    anchor = _requirement(tenant, workspace, "Handle payments")
    _allocate(tenant, anchor, root)
    return root, anchor


# ---------------------------------------------------------------------------
# Preset gating (acceptance criterion #2)
# ---------------------------------------------------------------------------


class TestPresetGating:
    def test_generate_blocked_in_minimal_preset(self, tenant, workspace, ctx):
        # A fresh workspace defaults to the minimal preset.
        with _active(tenant):
            root, _ = _seed_anchored_element(tenant, workspace)
            with pytest.raises(DecompositionNotAvailableError):
                ArchitectureDecomposeService().generate_draft(ctx, root.id)

    def test_commit_blocked_in_minimal_preset(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            draft = ArchitectureDecomposeService().generate_draft(ctx, root.id)
            # Downgrade so commit must refuse.
            switch_preset(str(workspace.id), "minimal")
            with pytest.raises(DecompositionNotAvailableError):
                ArchitectureDecomposeService().commit_draft(ctx, draft)


# ---------------------------------------------------------------------------
# Draft staging — generate writes nothing (acceptance criterion #1, part a)
# ---------------------------------------------------------------------------


class TestGenerateDraft:
    def test_generate_produces_nodes_without_persisting(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, anchor = _seed_anchored_element(tenant, workspace)

            before = ArchitectureElement.objects.count()
            draft = ArchitectureDecomposeService().generate_draft(
                ctx, root.id, max_breadth=2, max_depth=1
            )

            assert draft.root_element_id == str(root.id)
            assert draft.parent_requirement_id == str(anchor.id)
            assert len(draft.nodes) == 2
            # Nothing persisted: no new ArchitectureElement / Requirement rows.
            assert ArchitectureElement.objects.count() == before
            # every node carries a derived requirement
            for node in draft.nodes:
                assert node.requirement.title

    def test_generate_over_daily_token_limit_raises_and_never_calls_provider(
        self, tenant, workspace, ctx, monkeypatch, settings
    ):
        """Code review regression: architecture.decompose (N1) bypassed
        REQ-106 entirely -- no is_over_daily_limit() check existed at all
        before this fix, unlike every other free-form LLM flow."""
        from application.ai_derivation_service import LlmResponseError
        from persistence.models import TokenUsageRecord

        settings.TENANT_TOKEN_LIMIT_PER_DAY = 100
        with _active(tenant):
            TokenUsageRecord.objects.create(
                provider="mock", capability="arch_decompose_tree",
                input_tokens=150, output_tokens=0,
            )
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        from unittest.mock import MagicMock

        stub_provider = MagicMock()
        stub_provider.complete.return_value = "[]"
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: stub_provider
        )

        with _active(tenant):
            with pytest.raises(LlmResponseError):
                ArchitectureDecomposeService().generate_draft(
                    ctx, root.id, max_breadth=2, max_depth=1
                )
        # Load-bearing: the budget check runs BEFORE the provider is ever
        # called, not just that some exception was eventually raised.
        stub_provider.complete.assert_not_called()

    def test_generate_records_estimated_token_counts_not_zero(
        self, tenant, workspace, ctx, monkeypatch
    ):
        """SA-26: architecture.decompose (N1) used to hardcode input_tokens=0
        on record_token_usage(), leaving the daily budget (REQ-106) blind to
        this flow's real spend. Both sides must now be estimated from the
        actual prompt/completion via approximate_token_count()."""
        from unittest.mock import MagicMock

        from llm_adapter.token_tracking import approximate_token_count

        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)

        stub_provider = MagicMock()
        stub_provider.complete.return_value = '[{"title": "Child A"}]'
        monkeypatch.setattr(
            "llm_adapter.providers.get_provider", lambda *a, **k: stub_provider
        )
        record_mock = MagicMock()
        monkeypatch.setattr(
            "llm_adapter.token_tracking.record_token_usage", record_mock
        )

        with _active(tenant):
            ArchitectureDecomposeService().generate_draft(
                ctx, root.id, max_breadth=2, max_depth=1
            )

        record_mock.assert_called_once()
        _, kwargs = record_mock.call_args
        sent_prompt = stub_provider.complete.call_args[0][0]
        assert kwargs["input_tokens"] == approximate_token_count(sent_prompt)
        assert kwargs["output_tokens"] == approximate_token_count(
            '[{"title": "Child A"}]'
        )
        assert kwargs["input_tokens"] > 0
        assert kwargs["output_tokens"] > 0

    def test_generate_requires_anchor_requirement(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root = _arch(tenant, workspace, "Orphan Subsystem")  # no allocation
            with pytest.raises(ValidationError):
                ArchitectureDecomposeService().generate_draft(ctx, root.id)

    def test_generate_recursive_depth_flattens_children(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            draft = ArchitectureDecomposeService().generate_draft(
                ctx, root.id, max_breadth=2, max_depth=2
            )
            # 2 top-level + 2*2 second-level = 6 nodes; children reference parents.
            assert len(draft.nodes) == 6
            top = [n for n in draft.nodes if n.parent_temp_id is None]
            assert len(top) == 2
            child = [n for n in draft.nodes if n.parent_temp_id is not None]
            assert len(child) == 4
            temp_ids = {n.temp_id for n in draft.nodes}
            assert all(n.parent_temp_id in temp_ids for n in child)


# ---------------------------------------------------------------------------
# Transactional commit + auditor pass (acceptance criteria #1 + #3)
# ---------------------------------------------------------------------------


class TestCommitDraft:
    def test_commit_persists_links_and_passes_auditor(self, tenant, workspace, ctx):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, anchor = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

            result = svc.commit_draft(ctx, draft)

            assert result.root_element_id == str(root.id)
            assert len(result.created_element_ids) == 2
            assert len(result.created_requirement_ids) == 2
            # 3 links per node (allocated-to + decomposes + derives-from).
            assert len(result.created_link_ids) == 6
            assert set(result.verified_rules) == {"ARCH-003", "TRACE-P4", "TRACE-P5"}

            # Children hang off the root element (TRACE-P4: parent resolves).
            children = ArchitectureElement.objects.filter(parent_id=root.id)
            assert children.count() == 2

            # Each child requirement carries derives-from -> anchor (TRACE-P5).
            for req_id in result.created_requirement_ids:
                child_req = Requirement.objects.get(id=req_id)
                assert TraceLink.objects.filter(
                    source_id=child_req.artifact_id,
                    target_id=anchor.artifact_id,
                    link_type=LinkType.DERIVES_FROM.value,
                ).exists()

            # The real RuleEngine reports no N1-relevant blocker on the output.
            from traceability.audit import RuleEngine, Severity

            findings = RuleEngine().run(
                tier="extended",
                workspace_id=str(workspace.id),
                tenant_id=str(tenant.id),
            ).findings
            new_reqs = set(result.created_requirement_ids)
            offenders = [
                f
                for f in findings
                if f.rule_id in {"ARCH-003", "TRACE-P4", "TRACE-P5"}
                and f.severity is Severity.BLOCKER
            ]
            # None of the three rules fire on the freshly generated subtree.
            assert offenders == [] or all(
                not new_reqs.intersection(f.artifact_ids) for f in offenders
            )

    def test_commit_requires_write_permission(self, tenant, workspace, user):
        viewer = AuthContext(
            user_id=user.id,
            tenant_id=user.tenant.id,
            active_roles=("viewer",),
            auth_method="test",
            api_key_id=None,
            tenant_name="N1 Tenant",
        )
        editor = AuthContext(
            user_id=user.id,
            tenant_id=user.tenant.id,
            active_roles=("editor",),
            auth_method="test",
            api_key_id=None,
            tenant_name="N1 Tenant",
        )
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            draft = ArchitectureDecomposeService().generate_draft(editor, root.id)
            with pytest.raises(PermissionDeniedError):
                ArchitectureDecomposeService().commit_draft(viewer, draft)


# ---------------------------------------------------------------------------
# Rollback guarantees (acceptance criterion #1, part b)
# ---------------------------------------------------------------------------


class TestRollback:
    def test_partial_failure_leaves_no_orphans(
        self, tenant, workspace, ctx, monkeypatch
    ):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

            before_elems = ArchitectureElement.objects.count()
            before_reqs = Requirement.objects.count()

            # Fail during requirement creation of the SECOND node — the first
            # node's ArchitectureElement is already created at that point.
            real_create = svc._requirements.create_requirement
            state = {"calls": 0}

            def _flaky_create(*args, **kwargs):
                state["calls"] += 1
                if state["calls"] == 2:
                    raise RuntimeError("simulated requirement failure")
                return real_create(*args, **kwargs)

            monkeypatch.setattr(
                svc._requirements, "create_requirement", _flaky_create
            )

            with pytest.raises(RuntimeError):
                svc.commit_draft(ctx, draft)

            # Full rollback: no new architecture elements or requirements remain.
            assert ArchitectureElement.objects.count() == before_elems
            assert Requirement.objects.count() == before_reqs

    def test_auditor_failure_rolls_back_whole_batch(
        self, tenant, workspace, ctx, monkeypatch
    ):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

            before_elems = ArchitectureElement.objects.count()

            # Neuter the derives-from link so the committed graph violates
            # TRACE-P5/ARCH-003 (this mimics the raw decompose() output). The
            # post-commit auditor must catch it and roll everything back.
            def _link_no_derivation(ctx_, result, *, child_req_id, child_element_id, parent_req_id):
                alloc = svc._trace.allocate(
                    requirement_id=child_req_id,
                    architecture_element_id=child_element_id,
                    ctx=ctx_,
                )
                svc._record_link(result, alloc)
                dec = svc._trace.create_trace_link(
                    source_id=parent_req_id,
                    target_id=child_req_id,
                    link_type=LinkType.DECOMPOSES.value,
                    ctx=ctx_,
                )
                svc._record_link(result, dec)
                # intentionally NO derives-from link

            monkeypatch.setattr(svc, "_link_node", _link_no_derivation)

            with pytest.raises(DecompositionAuditError) as excinfo:
                svc.commit_draft(ctx, draft)

            assert excinfo.value.findings  # findings reported
            # Whole batch rolled back — no new architecture elements remain.
            assert ArchitectureElement.objects.count() == before_elems


# ---------------------------------------------------------------------------
# Issue #366 — the Artifact tree must mirror what commit_draft creates
# ---------------------------------------------------------------------------


class TestCommitPopulatesArtifactTree:
    """``artifact.get_tree`` walks ``pl_artifact.parent_id`` (recursive CTE).

    commit_draft used to leave that column NULL for every element and
    requirement it created, so ``get_tree`` reported the freshly decomposed
    root as childless even though the elements and their TraceLinks existed.
    """

    def test_commit_links_child_element_artifacts_under_the_root(
        self, tenant, workspace, ctx
    ):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=2)

            result = svc.commit_draft(ctx, draft)

            for element_id in result.created_element_ids:
                element = ArchitectureElement.objects.select_related(
                    "artifact", "parent"
                ).get(id=element_id)
                assert element.parent_id is not None
                assert element.artifact.parent_id == element.parent.artifact_id

    def test_commit_links_child_requirement_artifacts_under_their_parent(
        self, tenant, workspace, ctx
    ):
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, anchor = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

            result = svc.commit_draft(ctx, draft)

            # Mirrors RequirementService.decompose(): a derived requirement's
            # Artifact hangs under the parent requirement's Artifact.
            for req_id in result.created_requirement_ids:
                child_req = Requirement.objects.select_related("artifact").get(
                    id=req_id
                )
                assert child_req.artifact.parent_id == anchor.artifact_id

    def test_get_tree_returns_the_committed_subtree(self, tenant, workspace, ctx):
        from application.artifact_service import ArtifactService

        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=2)
            result = svc.commit_draft(ctx, draft)

            tree = ArtifactService().get_tree(
                root_id=root.id, workspace_id=workspace.id, ctx=ctx
            )

            def _flatten(node):
                yield node.id
                for child in node.children:
                    yield from _flatten(child)

            seen = set(_flatten(tree))
            created_artifact_ids = {
                ArchitectureElement.objects.get(id=eid).artifact_id
                for eid in result.created_element_ids
            }
            assert created_artifact_ids <= seen
            assert tree.children, "root must no longer be reported as childless"


# ---------------------------------------------------------------------------
# Issue #365 — which links commit_draft emits, and which it deliberately does
# not (element->element hierarchy is an FK tree, not a TraceLink).
# ---------------------------------------------------------------------------


class TestCommitTraceLinkVisibility:
    def test_created_links_are_returned_by_traceability_query(
        self, tenant, workspace, ctx
    ):
        """Every link commit_draft reports must be queryable afterwards."""
        from application.trace_link_service import TraceLinkService

        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, anchor = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=1)
            result = svc.commit_draft(ctx, draft)

            trace = TraceLinkService()
            for req_id in result.created_requirement_ids:
                found = trace.list_links_for_entity(
                    entity_id=req_id, direction="upstream", ctx=ctx
                ) + trace.list_links_for_entity(
                    entity_id=req_id, direction="downstream", ctx=ctx
                )
                types = {link.link_type for link in found}
                assert LinkType.ALLOCATED_TO.value in types
                assert LinkType.DECOMPOSES.value in types
                assert LinkType.DERIVES_FROM.value in types

            # The anchor sees the decomposition from its own side, too.
            anchor_links = trace.list_links_for_entity(
                entity_id=anchor.id, direction="downstream", ctx=ctx
            )
            assert {
                link.link_type for link in anchor_links
            } >= {LinkType.DECOMPOSES.value}

    def test_element_to_element_hierarchy_is_not_a_trace_link(
        self, tenant, workspace, ctx
    ):
        """Documented invariant (#365): architecture hierarchy is an FK tree.

        ``ArchitectureElement.parent`` (plus the mirrored ``Artifact.parent``)
        is the single representation of element hierarchy; no TraceLink is
        emitted for a parent-element -> child-element edge. See
        ``traceability.types.SE_LINK_SEMANTICS`` (no ArchitectureElement pair
        for ``derives-from``) and ``CrossCuttingToolGroup._handle_change_impact``,
        which walks the FK tree explicitly for exactly this reason.
        """
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=1)
            result = svc.commit_draft(ctx, draft)

            child_artifact_ids = {
                ArchitectureElement.objects.get(id=eid).artifact_id
                for eid in result.created_element_ids
            }
            assert not TraceLink.objects.filter(
                source_id=root.artifact_id, target_id__in=child_artifact_ids
            ).exists()
            # ...but the hierarchy is fully discoverable via the FK tree.
            assert set(
                ArchitectureElement.objects.filter(parent_id=root.id).values_list(
                    "artifact_id", flat=True
                )
            ) == {
                ArchitectureElement.objects.get(id=eid).artifact_id
                for eid in result.created_element_ids
                if ArchitectureElement.objects.get(id=eid).parent_id == root.id
            }


# ---------------------------------------------------------------------------
# Issues #363 / #364 — reported regressions; these tests exist to prove they
# do NOT reproduce on the current code.
# ---------------------------------------------------------------------------


class TestReportedRegressionsDoNotReproduce:
    def test_commit_reuses_the_root_element_and_creates_no_duplicate(
        self, tenant, workspace, ctx
    ):
        """#363: commit_draft must reuse ``root_element_id``, never re-create it."""
        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=2, max_depth=1)

            result = svc.commit_draft(ctx, draft)

            assert result.root_element_id == str(root.id)
            # No second element carries the root's title, and the root is still
            # the only element without a parent.
            assert (
                ArchitectureElement.objects.filter(title=root.title).count() == 1
            )
            roots = list(
                ArchitectureElement.objects.filter(
                    artifact__workspace_id=workspace.id, parent_id__isnull=True
                ).values_list("id", flat=True)
            )
            assert roots == [root.id]
            assert str(root.id) not in result.created_element_ids

    def test_commit_with_a_missing_root_element_raises_instead_of_creating_one(
        self, tenant, workspace, ctx
    ):
        """#363, hostile variant: a dangling root_element_id must 404."""
        import uuid as _uuid

        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=1, max_depth=1)
            draft.root_element_id = str(_uuid.uuid4())

            before = ArchitectureElement.objects.count()
            with pytest.raises(NotFoundError):
                svc.commit_draft(ctx, draft)
            assert ArchitectureElement.objects.count() == before

    def test_draft_node_with_blank_title_is_rejected(self):
        """#364, part a: a node without a title never reaches the DB."""
        from application.architecture_decompose_service import DraftNode

        with pytest.raises(ValidationError):
            DraftNode.from_dict(
                {"temp_id": "n1", "title": "   ", "requirement": {"title": ""}}
            )

    def test_commit_never_persists_a_blank_titled_requirement(
        self, tenant, workspace, ctx
    ):
        """#364, part b: empty requirement fields fall back to the node title."""
        from application.architecture_decompose_service import (
            DraftNode,
            DraftRequirement,
        )

        with _active(tenant):
            switch_preset(str(workspace.id), "extended")
            root, _ = _seed_anchored_element(tenant, workspace)
            svc = ArchitectureDecomposeService()
            draft = svc.generate_draft(ctx, root.id, max_breadth=1, max_depth=1)
            # Hostile draft: every requirement field blanked out.
            draft.nodes = [
                DraftNode(
                    temp_id="n1",
                    parent_temp_id=None,
                    title="Telemetry Component",
                    description="",
                    element_type="component",
                    requirement=DraftRequirement(
                        title="", description="", rationale=""
                    ),
                )
            ]

            result = svc.commit_draft(ctx, draft)

            assert len(result.created_requirement_ids) == 1
            created = Requirement.objects.get(id=result.created_requirement_ids[0])
            assert created.title.strip() == "Telemetry Component"
            assert not Requirement.objects.filter(title="").exists()
