"""InterviewService._formalize_multi() -- multi-artifact interview formalize.

Plan Task 3 (docs/superpowers/plans/2026-08-24-multi-artifact-interview.md,
lines 385-606). Six binding scenarios:

  1. Multi creation writes provenance rows + trace links and completes the
     session.
  2. A failing adapter mid-proposal rolls back EVERYTHING atomically (no
     orphan artifacts, no provenance rows, session stays in_progress).
  3. A viewer cannot formalize a multi session (central WRITE check).
  4. A viewer cannot smuggle a GlossaryTerm through multi formalize --
     GlossaryService.create() performs no WRITE check of its own, so this
     only passes via the centralized check in formalize().
  5. 'diagram-ref' links are rejected at the proposal-parse level (before
     the atomic block, system-managed link type).
  6. Single-mode formalize() behavior is unchanged.

Fixtures are local (there is no factories.py): same pattern as
test_architecture_decompose.py -- TenantContext.set_tenant/clear_tenant in
try/finally plus AuthContext constructed inline for editor/viewer roles.

Adaptation to real code vs. the plan's sketch: the default Requirement
protocol requires ``title`` AND ``rationale`` (interview_protocol.py factory
default), so the single-mode regression session seeds both collected fields;
with only ``title`` the completeness guard would reject the session before
formalize logic runs.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from application.base import PermissionDeniedError, ValidationError
from application.interview_service import InterviewService, _validate_confirmed_proposal
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    InterviewSession,
    InterviewSessionArtifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures + helpers (local -- no factories.py exists in this repo)
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
    return Tenant.objects.create(name="IV-Multi Tenant", slug="iv-multi-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="IV-Multi-WS")


@pytest.fixture
def editor_user(tenant: Tenant) -> User:
    # Real User row: created Artifacts reference created_by=ctx.user_id, and
    # pytest-django's flush would hit the pl_artifact FK on a phantom id.
    return User.objects.create(
        username="iv-multi-editor", email="editor@example.com", tenant=tenant
    )


@pytest.fixture
def viewer_user(tenant: Tenant) -> User:
    return User.objects.create(
        username="iv-multi-viewer", email="viewer@example.com", tenant=tenant
    )


@pytest.fixture
def editor_ctx(editor_user: User) -> AuthContext:
    return AuthContext(
        user_id=editor_user.id,
        tenant_id=editor_user.tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


@pytest.fixture
def viewer_ctx(viewer_user: User) -> AuthContext:
    return AuthContext(
        user_id=viewer_user.id,
        tenant_id=viewer_user.tenant.id,
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
    )


def _multi_session(tenant: Tenant, ws: Workspace) -> InterviewSession:
    with _active(tenant):
        return InterviewSession.objects.create(
            tenant=tenant,
            workspace=ws,
            artifact_type=None,
            session_kind=InterviewSession.SESSION_KIND_MULTI,
            status=InterviewSession.STATUS_IN_PROGRESS,
        )


class TestFormalizeMulti:
    def test_creates_multiple_artifacts_and_links_them(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        session = _multi_session(tenant, workspace)
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []},
            {
                "type": "Requirement",
                "fields": {"title": "Req B"},
                "links": [{"from": 1, "to": 0, "type": "derives-from"}],
            },
        ]

        result = InterviewService().formalize(
            editor_ctx, session.id, confirmed_proposal=proposal
        )

        assert len(result["created"]) == 2
        assert {c["artifact_type"] for c in result["created"]} == {
            "StakeholderNeed",
            "Requirement",
        }
        assert result["status"] == "completed"
        with _active(tenant):
            # Provenance rows: one InterviewSessionArtifact per created item.
            assert InterviewSessionArtifact.objects.filter(session=session).count() == 2
            # The proposed derives-from edge (Req B -> Need A) was really created.
            assert TraceLink.objects.filter(link_type="derives-from").count() == 1
            session.refresh_from_db()
            assert session.status == InterviewSession.STATUS_COMPLETED

    def test_rollback_on_error_in_third_item(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        session = _multi_session(tenant, workspace)
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []},
            {"type": "Requirement", "fields": {"title": "Req B"}, "links": []},
            # Risk is missing required probability/impact -> KeyError inside
            # the adapter (intentional per interview_artifact_adapters._risk),
            # converted to a ValidationError at the _formalize_multi batch
            # boundary; the whole batch must roll back either way.
            {"type": "Risk", "fields": {"title": "Risk C"}, "links": []},
        ]
        with pytest.raises(ValidationError):
            InterviewService().formalize(editor_ctx, session.id, confirmed_proposal=proposal)

        with _active(tenant):
            assert Requirement.objects.filter(title="Req B").count() == 0
            assert InterviewSessionArtifact.objects.filter(session=session).count() == 0
            session.refresh_from_db()
            assert session.status == InterviewSession.STATUS_IN_PROGRESS

    def test_rejects_item_without_fields_dict(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        # Structure validation runs BEFORE the atomic block: an item without
        # 'fields' is caller input error, not an adapter failure.
        session = _multi_session(tenant, workspace)
        proposal = [{"type": "StakeholderNeed"}]
        with pytest.raises(ValidationError):
            InterviewService().formalize(editor_ctx, session.id, confirmed_proposal=proposal)

        with _active(tenant):
            assert InterviewSessionArtifact.objects.filter(session=session).count() == 0
            session.refresh_from_db()
            assert session.status == InterviewSession.STATUS_IN_PROGRESS

    def test_rejects_out_of_range_link_index(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        # Link endpoints are indices into the proposal item list -- out-of-range
        # values must be rejected up front as ValidationError, not surface as a
        # bare IndexError from created_refs indexing mid-batch.
        session = _multi_session(tenant, workspace)
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []},
            {
                "type": "Requirement",
                "fields": {"title": "Req B"},
                "links": [{"from": 5, "to": 0, "type": "derives-from"}],
            },
        ]
        with pytest.raises(ValidationError):
            InterviewService().formalize(editor_ctx, session.id, confirmed_proposal=proposal)

        with _active(tenant):
            assert Requirement.objects.filter(title="Req B").count() == 0
            assert InterviewSessionArtifact.objects.filter(session=session).count() == 0
            session.refresh_from_db()
            assert session.status == InterviewSession.STATUS_IN_PROGRESS

    def test_viewer_cannot_formalize_multi(
        self, tenant: Tenant, workspace: Workspace, viewer_ctx: AuthContext
    ):
        session = _multi_session(tenant, workspace)
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}
        ]
        with pytest.raises(PermissionDeniedError):
            InterviewService().formalize(viewer_ctx, session.id, confirmed_proposal=proposal)

    def test_viewer_cannot_create_glossary_term_via_multi_formalize(
        self, tenant: Tenant, workspace: Workspace, viewer_ctx: AuthContext
    ):
        # GlossaryService.create() itself enforces no WRITE check -- this is
        # the regression test for the gap the plan's research uncovered.
        session = _multi_session(tenant, workspace)
        proposal = [
            {
                "type": "GlossaryTerm",
                "fields": {"term": "X", "definition": "Y"},
                "links": [],
            }
        ]
        with pytest.raises(PermissionDeniedError):
            InterviewService().formalize(viewer_ctx, session.id, confirmed_proposal=proposal)

    def test_rejects_diagram_ref_link_type(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        session = _multi_session(tenant, workspace)
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []},
            {
                "type": "Requirement",
                "fields": {"title": "Req B"},
                "links": [{"from": 1, "to": 0, "type": "diagram-ref"}],
            },
        ]
        with pytest.raises(ValidationError):
            InterviewService().formalize(editor_ctx, session.id, confirmed_proposal=proposal)

        # Rejected at the proposal-parse level: nothing was created.
        with _active(tenant):
            assert InterviewSessionArtifact.objects.filter(session=session).count() == 0

    def test_single_mode_formalize_unchanged(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        # Regression guard: single-mode call signature/behavior must be
        # untouched. collected_fields carries title AND rationale -- the
        # default Requirement protocol requires both.
        with _active(tenant):
            session = InterviewSession.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type="Requirement",
                session_kind=InterviewSession.SESSION_KIND_SINGLE,
                status=InterviewSession.STATUS_IN_PROGRESS,
                collected_fields={"title": "Solo requirement", "rationale": "Because"},
            )
        result = InterviewService().formalize(editor_ctx, session.id)
        assert "resulting_artifact_ids" in result
        assert len(result["resulting_artifact_ids"]) == 1


class TestProposalLinksHardening:
    """Review-2 fix m1: 'links' may be explicitly null in caller JSON --
    dict.get(key, default) returns None (not the default) for an existing
    null value, so enumerate(None) used to raise a bare TypeError. None now
    normalises to [], any other non-list is a clean ValidationError."""

    def test_null_links_normalise_to_empty_list_in_place(self):
        item = {"type": "StakeholderNeed", "fields": {"title": "N"}, "links": None}
        _validate_confirmed_proposal([item])
        assert item["links"] == []

    def test_missing_links_key_still_accepted(self):
        items = [{"type": "StakeholderNeed", "fields": {"title": "N"}}]
        _validate_confirmed_proposal(items)  # must not raise

    def test_non_list_links_raise_validation_error_not_type_error(self):
        item = {"type": "StakeholderNeed", "fields": {"title": "N"}, "links": "nope"}
        with pytest.raises(ValidationError) as excinfo:
            _validate_confirmed_proposal([item])
        # The failure is the structured ValidationError, never a TypeError.
        assert not isinstance(excinfo.value, TypeError)
        assert "'links' must be a list or null" in str(excinfo.value)

    def test_formalize_accepts_explicit_null_links(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        # End-to-end: links:null flows through formalize() like [] -- both
        # items are created, no trace links are written.
        session = _multi_session(tenant, workspace)
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": None},
            {"type": "Requirement", "fields": {"title": "Req B"}, "links": None},
        ]
        result = InterviewService().formalize(editor_ctx, session.id, confirmed_proposal=proposal)

        assert result["status"] == "completed"
        with _active(tenant):
            assert TraceLink.objects.count() == 0
            assert InterviewSessionArtifact.objects.filter(session=session).count() == 2

    def test_formalize_rejects_non_list_links_cleanly(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        session = _multi_session(tenant, workspace)
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": {"from": 0}}
        ]
        with pytest.raises(ValidationError):
            InterviewService().formalize(editor_ctx, session.id, confirmed_proposal=proposal)

        # Rejected pre-transaction: nothing was created.
        with _active(tenant):
            assert InterviewSessionArtifact.objects.filter(session=session).count() == 0
