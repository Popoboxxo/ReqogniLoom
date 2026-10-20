"""
SE-Auditor REST endpoints (SysEng 2.0 Phase 3) — HTTP boundary tests.

Covers:
  GET  /api/v1/workspaces/<id>/audit/            -> findings + remediation
  POST /api/v1/workspaces/<id>/audit/remediate/  -> Adopt (200) + refusal (422)

Uses APIRequestFactory with a pre-attached AuthContext (unit-style boundary
tests, mirroring rest_api/tests/test_change_request_api.py) against real data,
so the endpoints exercise the AuditService end to end.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator

import pytest
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from rest_api.audit_views import (
    WorkspaceAuditAiReviewView,
    WorkspaceAuditRemediateView,
    WorkspaceAuditView,
)
from traceability.audit.registry import TRACE_P5
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Audit API Tenant", slug="audit-api-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="audit-api-user", email="audit-api@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    # The audit endpoint derives the rigor tier from the workspace preset (no
    # tier query param by design). Switch to Extended so the extended-only
    # TRACE-P5 rule is active and the endpoint behaviour is deterministic.
    from link_types.workspace_store import provision_workspace_link_types
    from presets.services import switch_preset

    with _active(tenant):
        ws = Workspace.objects.create(tenant=tenant, name="Audit-API-WS")
        switch_preset(str(ws.id), "extended")
        # This module shadows the conftest `workspace` fixture, so it needs
        # its own provisioning: link validation is always-on and an
        # unprovisioned workspace has an empty catalog that rejects every
        # trace link — including the ones TRACE-P5 remediation writes.
        provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
        return ws


def _ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _p5_scenario(tenant, workspace):
    """Parent -decomposes-> child, no derives-from: raises exactly TRACE-P5."""
    def _req(title):
        # PascalCase, as RequirementService writes it: the link-type catalog
        # matches allowed_pairs on the exact artifact_type string, so a
        # lowercase "requirement" makes the remediation link uncreatable.
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(tenant=tenant, artifact=art, title=title)

    parent = _req("Parent")
    child = _req("Child")
    TraceLink.objects.create(
        tenant=tenant,
        source=parent.artifact,
        target=child.artifact,
        link_type=LinkType.DECOMPOSES.value,
    )
    return parent, child


def _untraced_requirements(tenant, workspace, count: int) -> None:
    """Create *count* root Requirements, each raising one TRACE-P1 blocker.

    A Requirement with no ``derives-from`` link is exactly the smallest
    reproducible audit violation used by the waiver tests, and it gives this
    module a deterministic multi-finding result set without a large fixture.
    """
    for i in range(count):
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=tenant, artifact=art, title=f"Untraced {i}"
        )


def _make_icd(tenant, workspace) -> None:
    """Create one unanchored ICD — the only IFC-001 WARNING in the workspace."""
    import uuid

    from icd.models import Icd

    art = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Icd"
    )
    Icd.objects.create(
        tenant=tenant,
        artifact=art,
        workspace_id=workspace.id,
        name="Filter ICD",
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
    )


class TestAuditGetEndpoint:
    def test_get_returns_200_with_findings(self, tenant, workspace, user):
        with _active(tenant):
            _p5_scenario(tenant, workspace)
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 200
        body = resp.data
        assert "findings" in body and body["counts"]["total"] >= 1
        # #1382: counts is ground truth, page_counts the returned window.
        assert body["counts"]["total"] == body["total_findings_available"]
        assert body["page_counts"]["total"] == len(body["findings"])
        rule_ids = {f["rule_id"] for f in body["findings"]}
        assert TRACE_P5 in rule_ids

    def test_get_rejects_document_scope_without_artifact(self, tenant, workspace, user):
        with _active(tenant):
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=document"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 400

    def test_get_with_limit_returns_a_windowed_response(self, tenant, workspace, user):
        """#622: ?limit=&offset= page past the default truncation cap."""
        with _active(tenant):
            _p5_scenario(tenant, workspace)
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project&limit=1&offset=0"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 200
        body = resp.data
        assert len(body["findings"]) == 1
        assert body["offset"] == 0
        # #1382: the cursor is always present (null when no next window).
        assert "next_offset" in body
        assert body["page_counts"]["total"] == len(body["findings"])

    def test_get_without_limit_omits_pagination_effect(self, tenant, workspace, user):
        """No ?limit= must behave exactly as before #622 (offset always 0)."""
        with _active(tenant):
            _p5_scenario(tenant, workspace)
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 200
        assert resp.data["offset"] == 0

    def test_get_rejects_non_integer_limit(self, tenant, workspace, user):
        with _active(tenant):
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project&limit=not-a-number"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 400

    def test_get_rejects_non_integer_offset(self, tenant, workspace, user):
        with _active(tenant):
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project&limit=10&offset=abc"
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditView.as_view()(req, workspace_id=str(workspace.id))

        assert resp.status_code == 400


class TestAuditPaginationContract:
    """#1383: ``page_size`` alias, strict validation, disjoint windows.

    ``limit`` stays the backward-compatible alias; both must be validated
    rather than clamped, and #1382's count semantics must survive the window.
    """

    def _get(self, tenant, workspace, user, query: str = ""):
        with _active(tenant):
            req = APIRequestFactory().get(
                f"/api/v1/workspaces/{workspace.id}/audit/?scope=project{query}"
            )
            req.auth_context = _ctx(user)
            return WorkspaceAuditView.as_view()(
                req, workspace_id=str(workspace.id)
            )

    def test_page_size_is_an_alias_of_limit(self, tenant, workspace, user):
        with _active(tenant):
            _untraced_requirements(tenant, workspace, 8)

        by_page_size = self._get(tenant, workspace, user, "&page_size=5")
        by_limit = self._get(tenant, workspace, user, "&limit=5")

        assert by_page_size.status_code == 200, by_page_size.data
        assert by_limit.status_code == 200, by_limit.data
        assert by_page_size.data == by_limit.data
        assert len(by_page_size.data["findings"]) == 5
        assert by_page_size.data["page_counts"]["total"] == 5
        # Ground truth is not the window size.
        assert by_page_size.data["counts"]["total"] >= 8

    def test_offset_windows_are_disjoint(self, tenant, workspace, user, monkeypatch):
        from application.audit_service import AuditService

        monkeypatch.setattr(AuditService, "MAX_REPORT_FINDINGS", 5)
        with _active(tenant):
            _untraced_requirements(tenant, workspace, 12)

        first = self._get(tenant, workspace, user, "&page_size=5&offset=0")
        second = self._get(tenant, workspace, user, "&page_size=5&offset=5")

        assert first.status_code == 200, first.data
        assert second.status_code == 200, second.data
        assert len(first.data["findings"]) == 5
        assert len(second.data["findings"]) == 5
        first_keys = {f["finding_key"] for f in first.data["findings"]}
        second_keys = {f["finding_key"] for f in second.data["findings"]}
        assert first_keys.isdisjoint(second_keys)
        # #1382: identical ground truth on every page.
        assert first.data["counts"] == second.data["counts"]
        assert first.data["counts"]["total"] == first.data["total_findings_available"]
        assert first.data["next_offset"] == 5
        assert second.data["next_offset"] == 10

    @pytest.mark.parametrize(
        "query",
        [
            "&page_size=abc",
            "&page_size=0",
            "&page_size=-1",
            "&offset=-1",
            "&limit=1.5",
            # An offset without a window has no meaning: reject, do not ignore.
            "&offset=1",
        ],
    )
    def test_invalid_pagination_values_are_rejected(
        self, tenant, workspace, user, query
    ):
        resp = self._get(tenant, workspace, user, query)

        assert resp.status_code == 400, resp.data
        assert resp.data["error"]["code"] == "VALIDATION_ERROR"

    def test_conflicting_page_size_and_limit_are_rejected(
        self, tenant, workspace, user
    ):
        resp = self._get(tenant, workspace, user, "&page_size=5&limit=9")

        assert resp.status_code == 400, resp.data
        assert resp.data["error"]["code"] == "VALIDATION_ERROR"

    def test_equal_page_size_and_limit_are_accepted(self, tenant, workspace, user):
        with _active(tenant):
            _untraced_requirements(tenant, workspace, 8)

        resp = self._get(tenant, workspace, user, "&page_size=5&limit=5")

        assert resp.status_code == 200, resp.data
        assert len(resp.data["findings"]) == 5

    def test_offset_zero_without_a_page_size_is_accepted(
        self, tenant, workspace, user
    ):
        with _active(tenant):
            _untraced_requirements(tenant, workspace, 2)

        resp = self._get(tenant, workspace, user, "&offset=0")

        assert resp.status_code == 200, resp.data
        assert resp.data["offset"] == 0
        assert resp.data["next_offset"] is None

    @pytest.mark.parametrize(
        "query",
        [
            # Empty values are not "absent" — they are malformed integers.
            "&page_size=",
            "&limit=",
            # FR-10: repeated parameters are ambiguous, so reject them.
            "&page_size=1&page_size=2",
            "&limit=1&limit=2",
            "&offset=1&offset=2",
        ],
    )
    def test_empty_or_repeated_pagination_values_are_rejected(
        self, tenant, workspace, user, query
    ):
        resp = self._get(tenant, workspace, user, query)

        assert resp.status_code == 400, resp.data
        assert resp.data["error"]["code"] == "VALIDATION_ERROR"

    def test_a_repeated_include_suppressed_is_rejected(
        self, tenant, workspace, user
    ):
        """#1382/FR-10: ``include_suppressed`` is repeat-unsafe like the paging args.

        Two values are ambiguous, so the parser answers 400 instead of silently
        picking one (the single-value and case-insensitive paths are covered in
        ``test_audit_waivers_569_rest.py``).
        """
        resp = self._get(
            tenant,
            workspace,
            user,
            "&include_suppressed=true&include_suppressed=false",
        )

        assert resp.status_code == 400, resp.data
        assert resp.data["error"]["code"] == "VALIDATION_ERROR"
        assert "at most once" in resp.data["error"]["message"]

    def test_a_filter_reaches_a_match_outside_the_cap(
        self, tenant, workspace, user, monkeypatch
    ):
        """#1382/FR-02 regression: filter before the cap, not after it.

        Ten BLOCKER findings fill a cap of three, so the single IFC-001
        WARNING is dropped by the default BLOCKER-preferred cap. The old
        run-then-filter path therefore reported ``counts.total == 0`` while the
        match existed; the service-side filter must report (and return) it.
        """
        from application.audit_service import AuditService

        monkeypatch.setattr(AuditService, "MAX_REPORT_FINDINGS", 3)
        with _active(tenant):
            _untraced_requirements(tenant, workspace, 10)
            _make_icd(tenant, workspace)

        resp = self._get(tenant, workspace, user, "&rule_id=IFC-001")

        assert resp.status_code == 200, resp.data
        body = resp.data
        assert {f["rule_id"] for f in body["findings"]} == {"IFC-001"}
        assert body["counts"]["total"] == len(body["findings"]) == 1
        assert body["counts"]["warnings"] == 1
        assert body["counts"]["blockers"] == 0
        assert body["page_counts"]["total"] == 1


class TestAuditRemediateEndpoint:
    def test_post_adopts_trace_p5_and_returns_200(self, tenant, workspace, user):
        with _active(tenant):
            parent, child = _p5_scenario(tenant, workspace)
            req = APIRequestFactory().post(
                f"/api/v1/workspaces/{workspace.id}/audit/remediate/",
                data={
                    "rule_id": TRACE_P5,
                    "artifact_ids": [str(child.artifact_id), str(parent.artifact_id)],
                },
                format="json",
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditRemediateView.as_view()(
                req, workspace_id=str(workspace.id)
            )

            assert resp.status_code == 200
            assert resp.data["applied"] is True
            assert resp.data["finding_resolved"] is True
            assert TraceLink.objects.filter(
                source_id=child.artifact_id,
                target_id=parent.artifact_id,
                link_type=LinkType.DERIVES_FROM.value,
            ).exists()

    def test_post_returns_422_when_not_auto_remediable(self, tenant, workspace, user):
        with _active(tenant):
            # TRACE-P4 has no registered remediation -> 422 (manual/Modify).
            req = APIRequestFactory().post(
                f"/api/v1/workspaces/{workspace.id}/audit/remediate/",
                data={"rule_id": "TRACE-P4", "artifact_ids": ["not-a-real-id"]},
                format="json",
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditRemediateView.as_view()(
                req, workspace_id=str(workspace.id)
            )

        assert resp.status_code == 422

    def test_post_validates_missing_artifact_ids(self, tenant, workspace, user):
        with _active(tenant):
            req = APIRequestFactory().post(
                f"/api/v1/workspaces/{workspace.id}/audit/remediate/",
                data={"rule_id": TRACE_P5, "artifact_ids": []},
                format="json",
            )
            req.auth_context = _ctx(user)
            resp = WorkspaceAuditRemediateView.as_view()(
                req, workspace_id=str(workspace.id)
            )

        assert resp.status_code == 400


class TestAuditAiReviewEndpointErrorMasking:
    """CWE-209 regression (DEEP_DIVE_REVIEW C-1, ``audit_views.py:241``):
    ``AiReviewResponseError`` (e.g. an LLM transport failure) must not leak
    its raw message to the client, but the real exception must still be
    logged for operators.

    Also verifies the Task 5 deviation fix: this call site previously had NO
    ``logger.exception`` at all (unlike the finding's blanket claim that
    logging was present everywhere) — this test would fail on ``caplog.text``
    if that gap were not closed.
    """

    def test_post_masks_internal_exception_but_logs_it(
        self, tenant, workspace, user, caplog
    ):
        from unittest.mock import patch

        from application.ai_review_service import AiReviewResponseError

        sensitive_detail = (
            "AnthropicError: connection refused to https://internal-llm-proxy"
            ".corp.local:8443 (api_key=sk-live-REDACTED-but-not-really)"
        )

        with _active(tenant):
            req = APIRequestFactory().post(
                f"/api/v1/workspaces/{workspace.id}/audit/ai-review/"
            )
            req.auth_context = _ctx(user)
            with patch(
                "rest_api.audit_views.AiReviewService.review",
                side_effect=AiReviewResponseError(sensitive_detail),
            ):
                with caplog.at_level("ERROR"):
                    resp = WorkspaceAuditAiReviewView.as_view()(
                        req, workspace_id=str(workspace.id)
                    )

        assert resp.status_code == 500
        body = str(resp.data)
        assert sensitive_detail not in body
        assert resp.data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert sensitive_detail in caplog.text
