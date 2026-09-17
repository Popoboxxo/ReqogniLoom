# Multi-Artifact Discovery Interview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a free-form "I don't know exactly what I need" interview entry point that lets an LLM propose multiple, cross-linked artifacts (of possibly different types) from a described problem, and creates all of them atomically after user confirmation — while keeping the 8 existing single-type interviews unchanged.

**Architecture:** Extend `InterviewSession` with a `session_kind` axis (`"single"` default / `"multi"` new) and a new `InterviewSessionArtifact` join table for provenance. Replace `InterviewService.formalize()`'s single Requirement-only guard with a dispatch to `_formalize_single()` (today's exact behavior, now type-generic via a new adapter registry) or `_formalize_multi()` (new: one DB transaction creating N artifacts + trace links + provenance rows). REST and MCP stay thin wrappers per ADR-01 — no new business logic outside `application/`.

**Tech Stack:** Django 4.2+ / DRF (backend), React 18 + TypeScript + `@xyflow/react` (frontend, already a project dependency), existing `PromptTemplate`/`prompt_resolver` 3-level override chain for the LLM protocol.

**Spec:** `docs/superpowers/specs/2026-08-22-multi-artifact-interview-design.md`

## Global Constraints

- The 8 existing single-type interview flows (`session_kind="single"`) MUST NOT change behavior — every existing test for `start`/`answer`/`formalize`/`grounding_context`/`chat`/`abandon` in single mode must stay green throughout.
- Every artifact-creation adapter MUST call the real, existing `create_X()` service method for that type — never a shortcut/direct-insert path (this is how workflow-state initialization stays correct for free, per the spec's own stated rationale).
- `InterviewService.formalize()` (both single and multi) MUST call `ServiceBase._assert_write_permission(ctx)` itself, centrally, before dispatching to any adapter — `GlossaryService.create()` does not enforce WRITE itself, so this is the only enforcement point for that type in this flow.
- `_formalize_multi()` MUST run inside one `transaction.atomic()` block — any failure (validation, permission, trace-link) rolls back every artifact created in that call, no partial state.
- No REST serializer break for the 8 single-type flows — only `formalize()`'s multi-mode return shape changes (list of artifact refs instead of one), single-mode return shape is byte-for-byte unchanged.
- `diagram-ref` trace links must never be created by this flow (system-managed only) — reject any LLM proposal that specifies it, same as `TraceLinkService.create_trace_link()` already does at the service layer, but reject earlier (at parse time) so the error message is specific to "invalid link type in proposal" rather than a generic service exception.
- `data-testid` on every new interactive frontend element (project convention, E2E-required).
- Every new UI string needs a DE/EN pair (i18n-parity ratchet convention, `frontend/src/test/i18n-parity.test.ts`).

---

## Task 1: Data model — `session_kind`, nullable `artifact_type`, `InterviewSessionArtifact`

**Files:**
- Modify: `backend/persistence/models.py:2258-2322` (`InterviewSession` class)
- Create: `backend/persistence/migrations/0066_interview_multi_mode.py`
- Test: `backend/persistence/tests/test_interview_session_multi_mode.py`

**Interfaces:**
- Produces: `InterviewSession.session_kind` (`str`, `"single"` | `"multi"`, default `"single"`); `InterviewSession.artifact_type` now `null=True, blank=True`; new model `InterviewSessionArtifact(session: FK[InterviewSession], artifact: FK[Artifact], artifact_type: str, created_at: datetime)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/persistence/tests/test_interview_session_multi_mode.py
import pytest
from django.db import IntegrityError

from persistence.models import Artifact, InterviewSession, InterviewSessionArtifact
from persistence.tenancy import TenantContext
from persistence.tests.factories import active_tenant, make_workspace  # existing project factories


@pytest.mark.django_db
class TestInterviewSessionMultiMode:
    def test_session_kind_defaults_to_single(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = InterviewSession.objects.create(
                tenant=tenant, workspace=ws, artifact_type="Requirement", status="in_progress"
            )
            assert session.session_kind == "single"

    def test_artifact_type_can_be_null_for_multi_sessions(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = InterviewSession.objects.create(
                tenant=tenant, workspace=ws, artifact_type=None, session_kind="multi", status="in_progress"
            )
            assert session.artifact_type is None
            assert session.session_kind == "multi"

    def test_interview_session_artifact_links_session_to_artifact(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = InterviewSession.objects.create(
                tenant=tenant, workspace=ws, artifact_type=None, session_kind="multi", status="completed"
            )
            artifact = Artifact.objects.create(tenant=tenant, workspace=ws, artifact_type="Requirement")
            row = InterviewSessionArtifact.objects.create(
                tenant=tenant, session=session, artifact=artifact, artifact_type="Requirement"
            )
            assert row.session_id == session.id
            assert row.artifact_id == artifact.id
            assert row.created_at is not None

    def test_interview_session_artifact_requires_session(self):
        with active_tenant() as tenant, pytest.raises(IntegrityError):
            ws = make_workspace(tenant)
            artifact = Artifact.objects.create(tenant=tenant, workspace=ws, artifact_type="Requirement")
            InterviewSessionArtifact.objects.create(
                tenant=tenant, session=None, artifact=artifact, artifact_type="Requirement"
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/persistence/tests/test_interview_session_multi_mode.py -v`
Expected: FAIL — `session_kind` field doesn't exist / `InterviewSessionArtifact` doesn't exist.

- [ ] **Step 3: Modify the model**

In `backend/persistence/models.py`, inside `class InterviewSession(TenantScopedModel):` (line ~2258), change the `artifact_type` field and add `session_kind`:

```python
class InterviewSession(TenantScopedModel):
    SESSION_KIND_SINGLE = "single"
    SESSION_KIND_MULTI = "multi"
    SESSION_KIND_CHOICES = (
        (SESSION_KIND_SINGLE, "Single artifact type"),
        (SESSION_KIND_MULTI, "Multi-artifact discovery"),
    )

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="interview_sessions")
    artifact = models.OneToOneField(
        "persistence.Artifact", on_delete=models.CASCADE, related_name="interview_session", null=True, blank=True
    )
    artifact_type = models.CharField(max_length=64, null=True, blank=True)
    session_kind = models.CharField(max_length=16, choices=SESSION_KIND_CHOICES, default=SESSION_KIND_SINGLE)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS)
    target_artifact = models.ForeignKey(
        Artifact, on_delete=models.SET_NULL, null=True, blank=True, related_name="interview_sessions"
    )
    collected_fields = models.JSONField(default=dict, blank=True)
    grounding_snapshot = models.JSONField(default=dict, blank=True)
    resulting_artifact_ids = models.JSONField(default=list, blank=True)
    transcript = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "pl_interview_session"
        indexes = [models.Index(fields=["workspace", "status"], name="idx_iview_ws_status")]


class InterviewSessionArtifact(TenantScopedModel):
    """Provenance join row: one artifact created by a multi-mode interview.

    A real FK to `Artifact` (not a loose UUID) — `Artifact` is the shared
    base row for every artifact subtype (models.py:680), so one FK covers
    all 9 in-scope types without a per-type join table, matching the
    project's existing FK-join-table style (see `TestRunResult`).
    """

    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="created_artifacts")
    artifact = models.ForeignKey(Artifact, on_delete=models.CASCADE, related_name="interview_provenance")
    artifact_type = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pl_interview_session_artifact"
        indexes = [models.Index(fields=["artifact"], name="idx_iview_artifact")]
```

- [ ] **Step 4: Generate and hand-verify the migration**

Run: `python backend/manage.py makemigrations persistence --name interview_multi_mode`

Verify the generated file is `backend/persistence/migrations/0066_interview_multi_mode.py` and contains: `AlterField` on `interviewsession.artifact_type` (adding `null=True, blank=True`), `AddField` for `session_kind` with `default="single"`, and `CreateModel` for `InterviewSessionArtifact` with `managers=[("objects", ...), ("unscoped", ...)]` (required for every `TenantScopedModel` subclass — see `backend/icd/migrations/0002_alter_icd_managers_*.py` for the precedent this project already fixed once before). If `managers` is missing, add it by hand:

```python
managers=[
    ("objects", django.db.models.manager.Manager()),
    ("unscoped", django.db.models.manager.Manager()),
],
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/persistence/tests/test_interview_session_multi_mode.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/0066_interview_multi_mode.py backend/persistence/tests/test_interview_session_multi_mode.py
git commit -m "feat: add session_kind and InterviewSessionArtifact for multi-mode interviews"
```

---

## Task 2: Artifact-creation adapter registry

**Files:**
- Create: `backend/application/interview_artifact_adapters.py`
- Test: `backend/application/tests/test_interview_artifact_adapters.py`

**Interfaces:**
- Consumes: the 9 real service methods (exact signatures below), `application.base.AuthContext`, `application.base.ValidationError`/`NotFoundError`/`PermissionDeniedError`.
- Produces: `ARTIFACT_CREATION_ADAPTERS: dict[str, Callable[[dict, AuthContext, UUID], "CreatedArtifactRef"]]`, `CreatedArtifactRef` (a small dataclass normalizing the 3 different real return shapes — ORM object / DTO / dict — into one `(artifact_id: UUID, artifact_type: str)` pair every later task can rely on).

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_interview_artifact_adapters.py
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import ValidationError
from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS, CreatedArtifactRef


class TestArtifactCreationAdapters:
    def test_registry_has_all_nine_types(self):
        expected = {
            "Requirement", "StakeholderNeed", "ArchitectureElement", "Risk",
            "TestCase", "Adr", "Issue", "Goal", "GlossaryTerm",
        }
        assert set(ARTIFACT_CREATION_ADAPTERS.keys()) == expected

    def test_requirement_adapter_normalizes_orm_object(self):
        fake_ctx = MagicMock()
        fake_requirement = MagicMock(id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.RequirementService.create_requirement",
            return_value=fake_requirement,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["Requirement"]({"title": "T"}, fake_ctx, "ws-1")
        mocked.assert_called_once_with(workspace_id="ws-1", ctx=fake_ctx, title="T")
        assert ref == CreatedArtifactRef(artifact_id=fake_requirement.id, artifact_type="Requirement")

    def test_stakeholder_need_adapter_normalizes_dto(self):
        fake_ctx = MagicMock()
        fake_dto = MagicMock(id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.StakeholderNeedService.create",
            return_value=fake_dto,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["StakeholderNeed"]({"title": "N"}, fake_ctx, "ws-1")
        mocked.assert_called_once_with(ctx=fake_ctx, workspace_id="ws-1", title="N")
        assert ref == CreatedArtifactRef(artifact_id=fake_dto.id, artifact_type="StakeholderNeed")

    def test_goal_adapter_normalizes_dict_return(self):
        fake_ctx = MagicMock()
        goal_id = uuid.uuid4()
        with patch(
            "application.interview_artifact_adapters.GoalService.create_version",
            return_value={"id": goal_id, "title": "G"},
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["Goal"]({"title": "G"}, fake_ctx, "ws-1")
        mocked.assert_called_once_with(workspace_id="ws-1", title="G", ctx=fake_ctx)
        assert ref == CreatedArtifactRef(artifact_id=goal_id, artifact_type="Goal")

    def test_risk_adapter_requires_probability_and_impact(self):
        fake_ctx = MagicMock()
        with pytest.raises(KeyError):
            # probability/impact are required by RiskService.create_risk with no
            # default — a proposal missing them must surface as a clear error,
            # not silently pass None through.
            ARTIFACT_CREATION_ADAPTERS["Risk"]({"title": "R"}, fake_ctx, "ws-1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/application/tests/test_interview_artifact_adapters.py -v`
Expected: FAIL — `application.interview_artifact_adapters` module doesn't exist.

- [ ] **Step 3: Implement the adapter registry**

```python
# backend/application/interview_artifact_adapters.py
"""Adapter registry: multi-artifact interview formalize() -> real create_X() calls.

Every entry MUST call the existing, production `create_X()` service method
for that type -- never a shortcut insert path. This is what keeps workflow
state initialization (e.g. RequirementService.create_requirement() calling
initialize_workflow_states() internally) correct for free.

The 9 real service methods return 3 different shapes (ORM object with
`.id`, a DTO with `.id`, or a plain dict with `["id"]`) -- CreatedArtifactRef
normalizes all three into one uniform pair so InterviewSessionArtifact
bookkeeping and TraceLink creation (Task 3) never need to know which shape
a given type returned.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict
from uuid import UUID

from application.adr_service import AdrService
from application.architecture_service import ArchitectureService
from application.base import AuthContext
from application.glossary_service import GlossaryService
from application.goal_service import GoalService
from application.issue_service import IssueService
from application.requirement_service import RequirementService
from application.risk_service import RiskService
from application.stakeholder_need_service import StakeholderNeedService
from application.test_service import TestService


@dataclass(frozen=True)
class CreatedArtifactRef:
    artifact_id: UUID
    artifact_type: str


def _requirement(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = RequirementService().create_requirement(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(artifact_id=obj.id, artifact_type="Requirement")


def _stakeholder_need(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    dto = StakeholderNeedService().create(ctx=ctx, workspace_id=workspace_id, **fields)
    return CreatedArtifactRef(artifact_id=dto.id, artifact_type="StakeholderNeed")


def _architecture_element(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = ArchitectureService().create_architecture_element(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(artifact_id=obj.id, artifact_type="ArchitectureElement")


def _risk(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # probability/impact are required, no default, on RiskService.create_risk --
    # a KeyError here on a malformed proposal is intentional and caught by
    # InterviewService._formalize_multi() (Task 3), surfaced as a per-item error.
    obj = RiskService().create_risk(
        workspace_id=workspace_id,
        title=fields["title"],
        probability=fields["probability"],
        impact=fields["impact"],
        ctx=ctx,
        **{k: v for k, v in fields.items() if k not in ("title", "probability", "impact")},
    )
    return CreatedArtifactRef(artifact_id=obj.id, artifact_type="Risk")


def _test_case(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = TestService().create_test_case(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(artifact_id=obj.id, artifact_type="TestCase")


def _adr(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # description is required (no default) on AdrService.create_adr.
    obj = AdrService().create_adr(
        workspace_id=workspace_id,
        title=fields["title"],
        description=fields["description"],
        ctx=ctx,
        **{k: v for k, v in fields.items() if k not in ("title", "description")},
    )
    return CreatedArtifactRef(artifact_id=obj.id, artifact_type="Adr")


def _issue(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = IssueService().create_issue(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(artifact_id=obj.id, artifact_type="Issue")


def _goal(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # keyword-only args, returns a dict, and raises PermissionDeniedError if
    # Workspace.goals_enabled is False -- that exception propagates unchanged
    # through _formalize_multi()'s transaction (Task 3), rolling everything back.
    result = GoalService().create_version(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(artifact_id=result["id"], artifact_type="Goal")


def _glossary_term(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    dto = GlossaryService().create(ctx=ctx, workspace_id=workspace_id, **fields)
    return CreatedArtifactRef(artifact_id=dto.id, artifact_type="GlossaryTerm")


ARTIFACT_CREATION_ADAPTERS: Dict[str, Callable[[dict, AuthContext, Any], CreatedArtifactRef]] = {
    "Requirement": _requirement,
    "StakeholderNeed": _stakeholder_need,
    "ArchitectureElement": _architecture_element,
    "Risk": _risk,
    "TestCase": _test_case,
    "Adr": _adr,
    "Issue": _issue,
    "Goal": _goal,
    "GlossaryTerm": _glossary_term,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/application/tests/test_interview_artifact_adapters.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_artifact_adapters.py backend/application/tests/test_interview_artifact_adapters.py
git commit -m "feat: add artifact-creation adapter registry for multi-mode interviews"
```

---

## Task 3: `InterviewService._formalize_multi()` + centralized WRITE check + trace links

**Files:**
- Modify: `backend/application/interview_service.py:596-728` (`formalize` method)
- Test: `backend/application/tests/test_interview_formalize_multi.py`

**Interfaces:**
- Consumes: `ARTIFACT_CREATION_ADAPTERS`, `CreatedArtifactRef` (Task 2); `TraceLinkService.create_trace_link(self, source_id: UUID, target_id: UUID, link_type: str, ctx: AuthContext)`; `InterviewSessionArtifact` (Task 1); `ServiceBase._assert_write_permission(ctx)` (`backend/application/base.py:125-149`).
- Produces: `InterviewService.formalize(self, ctx, session_id: UUID, confirmed_proposal: "list[dict] | None" = None) -> dict` — single-mode return shape unchanged; multi-mode returns `{"created": [{"artifact_id": str, "artifact_type": str}, ...], "status": "completed"}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_interview_formalize_multi.py
import pytest
from django.db import transaction

from application.base import PermissionDeniedError, ValidationError
from application.interview_service import InterviewService
from persistence.models import InterviewSession, InterviewSessionArtifact, Requirement
from persistence.tests.factories import active_tenant, make_workspace, viewer_ctx, editor_ctx


@pytest.mark.django_db
class TestFormalizeMulti:
    def _multi_session(self, tenant, ws):
        return InterviewSession.objects.create(
            tenant=tenant, workspace=ws, artifact_type=None, session_kind="multi", status="in_progress"
        )

    def test_creates_multiple_artifacts_and_links_them(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = self._multi_session(tenant, ws)
            ctx = editor_ctx(tenant, ws)
            proposal = [
                {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []},
                {
                    "type": "Requirement",
                    "fields": {"title": "Req B"},
                    "links": [{"from": 1, "to": 0, "type": "derives-from"}],
                },
            ]
            result = InterviewService().formalize(ctx, session.id, confirmed_proposal=proposal)

            assert len(result["created"]) == 2
            assert result["status"] == "completed"
            assert InterviewSessionArtifact.objects.filter(session=session).count() == 2
            session.refresh_from_db()
            assert session.status == "completed"

    def test_rollback_on_error_in_third_item(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = self._multi_session(tenant, ws)
            ctx = editor_ctx(tenant, ws)
            proposal = [
                {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []},
                {"type": "Requirement", "fields": {"title": "Req B"}, "links": []},
                # Risk is missing required `probability`/`impact` -> KeyError inside the adapter.
                {"type": "Risk", "fields": {"title": "Risk C"}, "links": []},
            ]
            with pytest.raises(Exception):
                InterviewService().formalize(ctx, session.id, confirmed_proposal=proposal)

            assert Requirement.objects.filter(title="Req B").count() == 0
            assert InterviewSessionArtifact.objects.filter(session=session).count() == 0
            session.refresh_from_db()
            assert session.status == "in_progress"

    def test_viewer_cannot_formalize_multi(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = self._multi_session(tenant, ws)
            ctx = viewer_ctx(tenant, ws)
            proposal = [{"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}]
            with pytest.raises(PermissionDeniedError):
                InterviewService().formalize(ctx, session.id, confirmed_proposal=proposal)

    def test_viewer_cannot_create_glossary_term_via_multi_formalize(self):
        # GlossaryService.create() itself enforces no WRITE check -- this is
        # the regression test for the gap the plan's research uncovered.
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = self._multi_session(tenant, ws)
            ctx = viewer_ctx(tenant, ws)
            proposal = [{"type": "GlossaryTerm", "fields": {"term": "X", "definition": "Y"}, "links": []}]
            with pytest.raises(PermissionDeniedError):
                InterviewService().formalize(ctx, session.id, confirmed_proposal=proposal)

    def test_rejects_diagram_ref_link_type(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = self._multi_session(tenant, ws)
            ctx = editor_ctx(tenant, ws)
            proposal = [
                {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []},
                {
                    "type": "Requirement",
                    "fields": {"title": "Req B"},
                    "links": [{"from": 1, "to": 0, "type": "diagram-ref"}],
                },
            ]
            with pytest.raises(ValidationError):
                InterviewService().formalize(ctx, session.id, confirmed_proposal=proposal)

    def test_single_mode_formalize_unchanged(self):
        # Regression guard: single-mode call signature/behavior must be untouched.
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = InterviewSession.objects.create(
                tenant=tenant, workspace=ws, artifact_type="Requirement",
                session_kind="single", status="in_progress",
                collected_fields={"title": "Solo requirement"},
            )
            ctx = editor_ctx(tenant, ws)
            result = InterviewService().formalize(ctx, session.id)
            assert "resulting_artifact_ids" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/application/tests/test_interview_formalize_multi.py -v`
Expected: FAIL — `formalize()` doesn't accept `confirmed_proposal`, no dispatch exists.

- [ ] **Step 3: Rewrite `formalize()`**

In `backend/application/interview_service.py`, replace the body from line 596 (the `def formalize(self, ctx, session_id: UUID) -> "dict[str, Any]":` guard-and-create logic) through line 728 with:

```python
from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS
from application.trace_link_service import TraceLinkService
from traceability.types import LinkType

_DIAGRAM_REF_LINK_TYPE = "diagram-ref"


def formalize(self, ctx, session_id: UUID, confirmed_proposal: "list[dict] | None" = None) -> "dict[str, Any]":
    self._assert_write_permission(ctx)
    session = self._get_session(ctx, session_id)
    if session.session_kind == InterviewSession.SESSION_KIND_MULTI:
        return self._formalize_multi(ctx, session, confirmed_proposal or [])
    return self._formalize_single(ctx, session)


def _formalize_single(self, ctx, session) -> "dict[str, Any]":
    # Unchanged from before this task: the Requirement-only guard and
    # create/update logic that previously lived directly in formalize().
    if session.artifact_type != "Requirement":
        raise ValidationError(
            f"formalize() for artifact_type={session.artifact_type!r} is not "
            "implemented yet -- only Requirement is wired in this plan; the "
            "other 7 types follow the identical pattern in a later pass."
        )
    # ... existing Requirement create/update body (lines 669-698 of the
    # pre-Task-3 formalize(), moved here verbatim) ...


def _formalize_multi(self, ctx, session, confirmed_proposal: "list[dict]") -> "dict[str, Any]":
    if not confirmed_proposal:
        raise ValidationError("confirmed_proposal is required for a multi-mode interview")

    for item in confirmed_proposal:
        for link in item.get("links", []):
            if link.get("type") == _DIAGRAM_REF_LINK_TYPE:
                raise ValidationError(
                    "invalid link type in proposal: 'diagram-ref' is system-managed "
                    "and cannot be created by an interview"
                )

    with transaction.atomic():
        created_refs = []
        for item in confirmed_proposal:
            adapter = ARTIFACT_CREATION_ADAPTERS.get(item["type"])
            if adapter is None:
                raise ValidationError(f"unknown artifact type in proposal: {item['type']!r}")
            ref = adapter(item["fields"], ctx, session.workspace_id)
            InterviewSessionArtifact.objects.create(
                session=session, artifact_id=ref.artifact_id, artifact_type=ref.artifact_type
            )
            created_refs.append(ref)

        for item in confirmed_proposal:
            for link in item.get("links", []):
                source = created_refs[link["from"]]
                target = created_refs[link["to"]]
                TraceLinkService().create_trace_link(
                    source_id=source.artifact_id,
                    target_id=target.artifact_id,
                    link_type=link["type"],
                    ctx=ctx,
                )

        session.status = self.STATUS_COMPLETED
        session.save(update_fields=["status"])

    return {
        "created": [
            {"artifact_id": str(ref.artifact_id), "artifact_type": ref.artifact_type} for ref in created_refs
        ],
        "status": "completed",
    }
```

Note: `InterviewSessionArtifact.objects.create(..., artifact_id=ref.artifact_id, ...)` relies on Django accepting `<fk_name>_id=` as a shortcut for a real FK assignment without an extra query — matches `InterviewSessionArtifact.artifact` being a real `ForeignKey("persistence.Artifact")` per Task 1.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/application/tests/test_interview_formalize_multi.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full existing interview test suite to confirm no regression**

Run: `pytest backend/application/tests/ -k interview -v`
Expected: PASS (all pre-existing single-mode tests plus the new ones)

- [ ] **Step 6: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_formalize_multi.py
git commit -m "feat: implement InterviewService._formalize_multi() with atomic multi-artifact creation"
```

---

## Task 4: `interview.protocol.multi` prompt template + proposal parsing

**Files:**
- Modify: `backend/application/interview_protocol.py` (add `interview.protocol.multi` factory default)
- Create: `backend/application/interview_multi_protocol.py` (free-form protocol text + proposal parsing, separate from `parse_protocol_yaml()` which assumes a fixed `phases:`/`required_fields:` shape that doesn't fit here)
- Test: `backend/application/tests/test_interview_multi_protocol.py`

**Interfaces:**
- Consumes: `prompt_resolver.resolve_and_render(slot_name, ctx, workspace_id, **data_kwargs)`, the JSON-list parsing pattern from `AiDerivationService._complete_json_list()` (`backend/application/ai_derivation_service.py`).
- Produces: `get_multi_protocol_prompt(ctx, workspace_id, user_message: str, transcript: list) -> str`; `parse_multi_proposal(raw_llm_output: str) -> "list[dict] | None"` (returns `None` on unparsable output — caller decides how to surface that, per the spec's "LLM liefert keinen parsbaren Vorschlag" error case).

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_interview_multi_protocol.py
from application.interview_multi_protocol import parse_multi_proposal


class TestParseMultiProposal:
    def test_parses_valid_proposal_block(self):
        raw = '''Here is my proposal:
```json
[
  {"type": "StakeholderNeed", "title": "Need A", "fields": {"title": "Need A"}, "links": []},
  {"type": "Requirement", "title": "Req B", "fields": {"title": "Req B"}, "links": [{"from": 1, "to": 0, "type": "derives-from"}]}
]
```
Let me know if this looks right.'''
        proposal = parse_multi_proposal(raw)
        assert len(proposal) == 2
        assert proposal[1]["links"][0]["type"] == "derives-from"

    def test_returns_none_for_no_json_block(self):
        assert parse_multi_proposal("I have a few more questions before proposing anything.") is None

    def test_returns_none_for_malformed_json(self):
        raw = '''```json
[{"type": "StakeholderNeed", "fields": {"title": "Need A"}]
```'''
        assert parse_multi_proposal(raw) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/application/tests/test_interview_multi_protocol.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
# backend/application/interview_multi_protocol.py
"""Free-form multi-artifact interview protocol: prompt + proposal parsing.

Deliberately NOT built on parse_protocol_yaml() (interview_protocol.py) --
that function assumes a fixed phases:/required_fields: YAML shape for a
single artifact type, which doesn't fit a free-running, multi-type chat.
Reuses the same "LLM emits a fenced ```json block, we extract and
json.loads it" pattern AiDerivationService.derive_requirements_from_need()
already uses via its private _complete_json_list() helper -- kept as a
sibling implementation here rather than importing that private helper
across service boundaries.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from application.prompt_resolver import resolve_and_render

_MULTI_PROTOCOL_SLOT = "interview.protocol.multi"

_JSON_BLOCK_RE = re.compile(r"```json\s*(\[.*?\])\s*```", re.DOTALL)

_MULTI_PROTOCOL_FACTORY_DEFAULT = """\
You are helping a user figure out which requirements-engineering artifacts \
they need, from a plain description of their problem. Artifact types \
available: StakeholderNeed, Requirement, ArchitectureElement, Risk, \
TestCase, Adr, Issue, Goal, GlossaryTerm.

Ask clarifying questions if the problem is unclear. Once you have enough \
information, propose a list of artifacts as a fenced ```json code block, \
each item shaped as:
{"type": "<ArtifactType>", "title": "<short title>", "fields": {<fields for that type's create call>}, "links": [{"from": <index>, "to": <index>, "type": "<trace-link-type>"}]}

Use trace-link types from: parent-child, derives-from, satisfies, verifies, \
implements, refines, documents, realizes, traces, copy-of, allocated-to, \
uses-term, decides, decomposes. Never propose "diagram-ref" -- it is \
system-managed only.

Conversation so far:
{transcript}

User: {user_message}
"""


def get_multi_protocol_prompt(ctx: Any, workspace_id, user_message: str, transcript: list) -> str:
    transcript_text = "\n".join(f"{turn['role']}: {turn['content']}" for turn in transcript)
    return resolve_and_render(
        _MULTI_PROTOCOL_SLOT,
        ctx,
        workspace_id,
        user_message=user_message,
        transcript=transcript_text,
    )


def parse_multi_proposal(raw_llm_output: str) -> "Optional[list[dict]]":
    match = _JSON_BLOCK_RE.search(raw_llm_output)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return parsed
```

In `backend/application/interview_protocol.py`, extend `INTERVIEW_PROTOCOL_DEFAULTS` (line ~112-120) to also register the multi slot's factory default so the existing Workspace→Tenant→Factory resolver chain (`try_resolve_template_content`) picks it up identically to the 8 single-type slots:

```python
from application.interview_multi_protocol import _MULTI_PROTOCOL_FACTORY_DEFAULT, _MULTI_PROTOCOL_SLOT

INTERVIEW_PROTOCOL_DEFAULTS: "dict[str, str]" = {
    **{f"interview.protocol.{t}": _default_protocol_yaml(t) for t in IN_SCOPE_ARTIFACT_TYPES},
    _MULTI_PROTOCOL_SLOT: _MULTI_PROTOCOL_FACTORY_DEFAULT,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/application/tests/test_interview_multi_protocol.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_multi_protocol.py backend/application/interview_protocol.py backend/application/tests/test_interview_multi_protocol.py
git commit -m "feat: add interview.protocol.multi prompt template and proposal parsing"
```

---

## Task 5: Wire `generate_chat_turn()` to the multi protocol + `interview.propose`

**Files:**
- Modify: `backend/application/interview_service.py:770-894` (`generate_chat_turn`)
- Test: `backend/application/tests/test_interview_multi_chat.py`

**Interfaces:**
- Consumes: `get_multi_protocol_prompt`, `parse_multi_proposal` (Task 4).
- Produces: `InterviewService.propose(self, ctx, session_id: UUID) -> "dict | None"` — returns the last parsed proposal from `session.grounding_snapshot["pending_proposal"]` (or `None` if the LLM hasn't emitted one yet); `generate_chat_turn()` now stores a parsed proposal into `grounding_snapshot["pending_proposal"]` when `session.session_kind == "multi"` and the LLM's reply parses.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_interview_multi_chat.py
from unittest.mock import patch

import pytest

from application.interview_service import InterviewService
from persistence.models import InterviewSession
from persistence.tests.factories import active_tenant, make_workspace, editor_ctx


@pytest.mark.django_db
class TestMultiChatTurn:
    def test_chat_turn_stores_parsed_proposal(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = InterviewSession.objects.create(
                tenant=tenant, workspace=ws, artifact_type=None, session_kind="multi", status="in_progress"
            )
            ctx = editor_ctx(tenant, ws)
            fake_llm_reply = '''Sounds good, here is the proposal:
```json
[{"type": "StakeholderNeed", "title": "Need A", "fields": {"title": "Need A"}, "links": []}]
```'''
            with patch(
                "application.interview_service.InterviewService._call_llm", return_value=fake_llm_reply
            ):
                InterviewService().generate_chat_turn(ctx, session.id, "I need something for X")

            session.refresh_from_db()
            assert session.grounding_snapshot["pending_proposal"][0]["type"] == "StakeholderNeed"

    def test_propose_returns_none_when_nothing_pending(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            session = InterviewSession.objects.create(
                tenant=tenant, workspace=ws, artifact_type=None, session_kind="multi", status="in_progress"
            )
            ctx = editor_ctx(tenant, ws)
            assert InterviewService().propose(ctx, session.id) is None

    def test_propose_returns_stored_proposal(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            proposal = [{"type": "StakeholderNeed", "title": "Need A", "fields": {"title": "Need A"}, "links": []}]
            session = InterviewSession.objects.create(
                tenant=tenant, workspace=ws, artifact_type=None, session_kind="multi", status="in_progress",
                grounding_snapshot={"pending_proposal": proposal},
            )
            ctx = editor_ctx(tenant, ws)
            assert InterviewService().propose(ctx, session.id) == proposal
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/application/tests/test_interview_multi_chat.py -v`
Expected: FAIL — `propose()` doesn't exist, `generate_chat_turn()` doesn't branch on `session_kind`.

- [ ] **Step 3: Implement**

In `backend/application/interview_service.py`, inside `generate_chat_turn(self, ctx, session_id, user_message)` (line 770), add a branch near the top (after `session = self._get_session(ctx, session_id)`):

```python
from application.interview_multi_protocol import get_multi_protocol_prompt, parse_multi_proposal

def generate_chat_turn(self, ctx, session_id: UUID, user_message: str) -> "dict[str, Any]":
    session = self._get_session(ctx, session_id)
    if session.session_kind == InterviewSession.SESSION_KIND_MULTI:
        return self._generate_multi_chat_turn(ctx, session, user_message)
    # ... existing single-mode body unchanged ...


def _generate_multi_chat_turn(self, ctx, session, user_message: str) -> "dict[str, Any]":
    prompt = get_multi_protocol_prompt(ctx, session.workspace_id, user_message, session.transcript)
    reply = self._call_llm(prompt)  # existing LLM-adapter call site, same as single mode uses

    session.transcript = session.transcript + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": reply},
    ]
    proposal = parse_multi_proposal(reply)
    if proposal is not None:
        session.grounding_snapshot = {**session.grounding_snapshot, "pending_proposal": proposal}
    session.save(update_fields=["transcript", "grounding_snapshot"])

    return {"reply": reply, "proposal": proposal, "state": self.get_state(ctx, session.id)}


def propose(self, ctx, session_id: UUID) -> "dict[str, Any] | None":
    session = self._get_session(ctx, session_id)
    return session.grounding_snapshot.get("pending_proposal")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/application/tests/test_interview_multi_chat.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_multi_chat.py
git commit -m "feat: wire generate_chat_turn() to the multi protocol and add propose()"
```

---

## Task 6: `interview.start` optional `session_kind`, MCP `interview.propose`, `_READ_ONLY_TOOL_NAMES`

**Files:**
- Modify: `backend/application/interview_service.py:42-98` (`start`)
- Modify: `backend/mcp_server/tools/interview.py` (`_TOOL_MAP`, `_TOOL_SCHEMAS`, new `_handle_propose`)
- Modify: `backend/mcp_server/tool_registry.py` (`_READ_ONLY_TOOL_NAMES`)
- Test: `backend/mcp_server/tests/test_interview_tool_group_multi.py`

**Interfaces:**
- Consumes: `InterviewService.propose()` (Task 5).
- Produces: `InterviewService.start(self, ctx, artifact_type: "str | None", workspace_id: UUID, session_kind: str = "single", seed_context=None) -> InterviewSession`; MCP tool `interview.propose` (read-only, params `{"session_id": str}`).

- [ ] **Step 1: Write the failing test**

```python
# backend/mcp_server/tests/test_interview_tool_group_multi.py
import pytest

from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES
from mcp_server.tools.interview import InterviewToolGroup


class TestInterviewToolGroupMulti:
    def test_propose_is_registered(self):
        assert "interview.propose" in InterviewToolGroup()._TOOL_MAP

    def test_propose_is_read_only(self):
        assert "interview.propose" in _READ_ONLY_TOOL_NAMES

    def test_propose_has_a_schema(self):
        schemas = {s["name"] for s in InterviewToolGroup()._TOOL_SCHEMAS}
        assert "interview.propose" in schemas
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/mcp_server/tests/test_interview_tool_group_multi.py -v`
Expected: FAIL — `interview.propose` not registered anywhere.

- [ ] **Step 3: Implement**

In `backend/application/interview_service.py`, change `start()`'s signature (line 42):

```python
def start(
    self, ctx, artifact_type: "str | None", workspace_id: UUID,
    session_kind: str = InterviewSession.SESSION_KIND_SINGLE, seed_context: "Optional[dict]" = None,
) -> InterviewSession:
    if session_kind == InterviewSession.SESSION_KIND_MULTI and artifact_type is not None:
        raise ValidationError("artifact_type must not be set for a multi-mode interview")
    if session_kind == InterviewSession.SESSION_KIND_SINGLE and not artifact_type:
        raise ValidationError("artifact_type is required for a single-mode interview")
    # ... existing body, using session_kind=session_kind when constructing InterviewSession ...
```

In `backend/mcp_server/tools/interview.py`: add to `_TOOL_MAP` (line ~38-48):

```python
_TOOL_MAP = {
    "interview.start": "_handle_start",
    "interview.get_state": "_handle_get_state",
    "interview.answer": "_handle_answer",
    "interview.list": "_handle_list",
    "interview.get": "_handle_get",
    "interview.grounding_context": "_handle_grounding_context",
    "interview.formalize": "_handle_formalize",
    "interview.set_target": "_handle_set_target",
    "interview.abandon": "_handle_abandon",
    "interview.propose": "_handle_propose",
}
```

Add a schema entry to `_TOOL_SCHEMAS` (following the shape of the existing `interview.get_state` entry) and a handler:

```python
{
    "name": "interview.propose",
    "description": "Get the current pending multi-artifact proposal for a session, if the LLM has emitted one.",
    "parameters": {
        "type": "object",
        "properties": {"session_id": {"type": "string", "format": "uuid"}},
        "required": ["session_id"],
    },
},
```

```python
def _handle_propose(self, params: dict, auth_context, api_key=None, **_kwargs) -> ToolResult:
    session_id = params["session_id"]
    proposal = InterviewService().propose(auth_context, session_id)
    return ToolResult.ok({"proposal": proposal})
```

Update `interview.start`'s schema to make `artifact_type` optional and add `session_kind` (`enum: ["single", "multi"]`, default `"single"`).

In `backend/mcp_server/tool_registry.py`, add `"interview.propose"` to `_READ_ONLY_TOOL_NAMES` (alongside the existing `interview.get_state`, `interview.list`, `interview.get`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/mcp_server/tests/test_interview_tool_group_multi.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/mcp_server/tools/interview.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_interview_tool_group_multi.py
git commit -m "feat: add interview.propose MCP tool, session_kind param on interview.start"
```

---

## Task 7: REST wiring (`interview_views.py`)

**Files:**
- Modify: `backend/rest_api/interview_views.py` (`create`, `formalize`)
- Create: new action `propose` on `InterviewViewSet`
- Test: `backend/rest_api/tests/test_interview_views_multi.py`

**Interfaces:**
- Consumes: `InterviewService.start(..., session_kind=...)`, `InterviewService.formalize(..., confirmed_proposal=...)`, `InterviewService.propose(...)` (Tasks 5, 6).
- Produces: `POST /api/v1/interviews/` accepts optional `session_kind`; `POST /api/v1/interviews/{id}/formalize/` accepts optional `confirmed_proposal`; new `GET /api/v1/interviews/{id}/propose/`.

- [ ] **Step 1: Write the failing test**

```python
# backend/rest_api/tests/test_interview_views_multi.py
import pytest
from rest_framework.test import APIClient

from persistence.tests.factories import active_tenant, make_workspace, editor_user_and_token


@pytest.mark.django_db
class TestInterviewViewsMulti:
    def test_start_multi_session_without_artifact_type(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.post(
                "/api/v1/interviews/", {"workspace_id": str(ws.id), "session_kind": "multi"}, format="json"
            )
            assert response.status_code == 201
            assert response.data["id"]

    def test_formalize_multi_accepts_confirmed_proposal(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            start_resp = client.post(
                "/api/v1/interviews/", {"workspace_id": str(ws.id), "session_kind": "multi"}, format="json"
            )
            session_id = start_resp.data["id"]
            proposal = [{"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}]

            response = client.post(
                f"/api/v1/interviews/{session_id}/formalize/",
                {"confirmed_proposal": proposal},
                format="json",
            )
            assert response.status_code == 200
            assert len(response.data["created"]) == 1

    def test_propose_endpoint_returns_null_when_none_pending(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            start_resp = client.post(
                "/api/v1/interviews/", {"workspace_id": str(ws.id), "session_kind": "multi"}, format="json"
            )
            session_id = start_resp.data["id"]

            response = client.get(f"/api/v1/interviews/{session_id}/propose/")
            assert response.status_code == 200
            assert response.data["proposal"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/rest_api/tests/test_interview_views_multi.py -v`
Expected: FAIL — `session_kind`/`confirmed_proposal` not accepted, `propose` action missing.

- [ ] **Step 3: Implement**

In `backend/rest_api/interview_views.py`, `create()` (line 72-84):

```python
def create(self, request: Request, **kwargs: Any) -> Response:
    """POST /api/v1/interviews/ -- start a new interview session."""
    lang = detect_lang(request)
    workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
    if error is not None:
        return error
    try:
        ctx = get_auth_context(request)
        session = InterviewService().start(
            ctx,
            request.data.get("artifact_type"),
            workspace_id,
            session_kind=request.data.get("session_kind", "single"),
        )
        result = _state_dict(ctx, session.id)
    except _SERVICE_EXCEPTIONS as exc:
        return _service_error_response(exc, lang)
    return Response(result, status=status.HTTP_201_CREATED)
```

`formalize()` (line ~around the existing `@action(detail=True, methods=["post"], url_path="formalize")`):

```python
@action(detail=True, methods=["post"], url_path="formalize")
def formalize(self, request: Request, pk: str, **kwargs: Any) -> Response:
    """POST /api/v1/interviews/{id}/formalize/ -- create/update the target artifact(s)."""
    lang = detect_lang(request)
    session_id, error = parse_uuid_param(pk, lang, name="id")
    if error is not None:
        return error
    try:
        ctx = get_auth_context(request)
        result = InterviewService().formalize(ctx, session_id, request.data.get("confirmed_proposal"))
    except _SERVICE_EXCEPTIONS as exc:
        return _service_error_response(exc, lang)
    return Response(result)
```

New action:

```python
@action(detail=True, methods=["get"], url_path="propose")
def propose(self, request: Request, pk: str, **kwargs: Any) -> Response:
    """GET /api/v1/interviews/{id}/propose/ -- current pending multi-artifact proposal, if any."""
    lang = detect_lang(request)
    session_id, error = parse_uuid_param(pk, lang, name="id")
    if error is not None:
        return error
    try:
        ctx = get_auth_context(request)
        proposal = InterviewService().propose(ctx, session_id)
    except _SERVICE_EXCEPTIONS as exc:
        return _service_error_response(exc, lang)
    return Response({"proposal": proposal})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/rest_api/tests/test_interview_views_multi.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full existing interview REST test suite to confirm no regression**

Run: `pytest backend/rest_api/tests/ -k interview -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/rest_api/interview_views.py backend/rest_api/tests/test_interview_views_multi.py
git commit -m "feat: wire session_kind/confirmed_proposal/propose into the interview REST facade"
```

---

## Task 8: Frontend API client (`interviews.ts`)

**Files:**
- Modify: `frontend/src/api/interviews.ts`
- Test: `frontend/src/api/interviews.test.ts` (create if it doesn't exist yet)

**Interfaces:**
- Produces: `interviewsApi.start(workspaceId: string, artifactType: string | null, sessionKind?: "single" | "multi")`; `interviewsApi.formalize(id: string, confirmedProposal?: ProposalItem[])`; `interviewsApi.propose(id: string): Promise<{ proposal: ProposalItem[] | null }>`; new type `ProposalItem = { type: string; title: string; fields: Record<string, unknown>; links: { from: number; to: number; type: string }[] }`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/api/interviews.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import apiClient from "./client";
import { interviewsApi } from "./interviews";

vi.mock("./client");

describe("interviewsApi multi-mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("start() sends session_kind and omits artifact_type when multi", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { id: "s1" } });
    await interviewsApi.start("ws-1", null, "multi");
    expect(apiClient.post).toHaveBeenCalledWith("/interviews/", {
      workspace_id: "ws-1",
      artifact_type: null,
      session_kind: "multi",
    });
  });

  it("formalize() sends confirmed_proposal when given", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { created: [] } });
    const proposal = [{ type: "StakeholderNeed", title: "N", fields: { title: "N" }, links: [] }];
    await interviewsApi.formalize("s1", proposal);
    expect(apiClient.post).toHaveBeenCalledWith("/interviews/s1/formalize/", {
      confirmed_proposal: proposal,
    });
  });

  it("formalize() omits confirmed_proposal for single mode (backward compatible)", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { resulting_artifact_ids: [] } });
    await interviewsApi.formalize("s1");
    expect(apiClient.post).toHaveBeenCalledWith("/interviews/s1/formalize/", {});
  });

  it("propose() fetches the pending proposal", async () => {
    (apiClient.get as any).mockResolvedValue({ data: { proposal: null } });
    const result = await interviewsApi.propose("s1");
    expect(apiClient.get).toHaveBeenCalledWith("/interviews/s1/propose/");
    expect(result.proposal).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/interviews.test.ts`
Expected: FAIL — `session_kind`/`confirmed_proposal`/`propose` not implemented.

- [ ] **Step 3: Implement**

In `frontend/src/api/interviews.ts`, add the type and update/add methods:

```typescript
export interface ProposalLink {
  from: number;
  to: number;
  type: string;
}

export interface ProposalItem {
  type: string;
  title: string;
  fields: Record<string, unknown>;
  links: ProposalLink[];
}

export const interviewsApi = {
  // ... existing methods ...

  start: (workspaceId: string, artifactType: string | null, sessionKind: "single" | "multi" = "single") =>
    apiClient
      .post("/interviews/", { workspace_id: workspaceId, artifact_type: artifactType, session_kind: sessionKind })
      .then((r) => r.data),

  formalize: (id: string, confirmedProposal?: ProposalItem[]) =>
    apiClient
      .post(`/interviews/${id}/formalize/`, confirmedProposal ? { confirmed_proposal: confirmedProposal } : {})
      .then((r) => r.data),

  propose: (id: string): Promise<{ proposal: ProposalItem[] | null }> =>
    apiClient.get(`/interviews/${id}/propose/`).then((r) => r.data),
};
```

Note: `start()`'s existing single-type call sites (`interviewsApi.start(workspaceId, "Requirement")`) keep working unchanged — `sessionKind` defaults to `"single"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/interviews.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/interviews.ts frontend/src/api/interviews.test.ts
git commit -m "feat: add multi-mode params to the interviews API client"
```

---

## Task 9: Artifact-type color tokens

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Create: `frontend/src/constants/artifactTypeColors.ts`
- Test: `frontend/src/constants/artifactTypeColors.test.ts`

**Interfaces:**
- Produces: `ARTIFACT_TYPE_COLOR_VAR: Record<string, string>` mapping each of the 9 types to a `--color-artifacttype-*` CSS custom property name; `getArtifactTypeColorVar(type: string): string` (falls back to a default token for unknown types).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/constants/artifactTypeColors.test.ts
import { describe, it, expect } from "vitest";
import { ARTIFACT_TYPE_COLOR_VAR, getArtifactTypeColorVar } from "./artifactTypeColors";

describe("artifactTypeColors", () => {
  it("has an entry for all 9 in-scope types plus GlossaryTerm", () => {
    const expected = [
      "StakeholderNeed", "Requirement", "ArchitectureElement", "Risk",
      "TestCase", "Adr", "Issue", "Goal", "GlossaryTerm",
    ];
    expected.forEach((type) => expect(ARTIFACT_TYPE_COLOR_VAR[type]).toBeDefined());
  });

  it("getArtifactTypeColorVar falls back to default for unknown types", () => {
    expect(getArtifactTypeColorVar("Unknown")).toBe("var(--color-artifacttype-default)");
  });

  it("getArtifactTypeColorVar returns the mapped var() for known types", () => {
    expect(getArtifactTypeColorVar("Requirement")).toBe("var(--color-artifacttype-requirement)");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/constants/artifactTypeColors.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

Add to `frontend/src/styles/tokens.css`, near the existing `--color-reqtype-*` block (line ~503-516):

```css
/* Artifact-type colors for the multi-artifact interview proposal graph */
--color-artifacttype-stakeholderneed: var(--palette-blue-500);
--color-artifacttype-requirement: var(--palette-emerald-500);
--color-artifacttype-architectureelement: var(--palette-indigo-500);
--color-artifacttype-risk: var(--palette-red-500);
--color-artifacttype-testcase: var(--palette-teal-500);
--color-artifacttype-adr: var(--palette-orange-500);
--color-artifacttype-issue: var(--palette-rose-500);
--color-artifacttype-goal: var(--palette-violet-500);
--color-artifacttype-glossaryterm: var(--palette-amber-500);
--color-artifacttype-default: var(--palette-gray-600);
```

```typescript
// frontend/src/constants/artifactTypeColors.ts
export const ARTIFACT_TYPE_COLOR_VAR: Record<string, string> = {
  StakeholderNeed: "--color-artifacttype-stakeholderneed",
  Requirement: "--color-artifacttype-requirement",
  ArchitectureElement: "--color-artifacttype-architectureelement",
  Risk: "--color-artifacttype-risk",
  TestCase: "--color-artifacttype-testcase",
  Adr: "--color-artifacttype-adr",
  Issue: "--color-artifacttype-issue",
  Goal: "--color-artifacttype-goal",
  GlossaryTerm: "--color-artifacttype-glossaryterm",
};

export function getArtifactTypeColorVar(type: string): string {
  const varName = ARTIFACT_TYPE_COLOR_VAR[type] ?? "--color-artifacttype-default";
  return `var(${varName})`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/constants/artifactTypeColors.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/constants/artifactTypeColors.ts frontend/src/constants/artifactTypeColors.test.ts
git commit -m "feat: add per-artifact-type color tokens for the proposal preview graph"
```

---

## Task 10: `ProposalPreviewGraph.tsx` (display-only xyflow graph)

**Files:**
- Create: `frontend/src/components/InterviewWidget/ProposalPreviewGraph.tsx`
- Create: `frontend/src/components/InterviewWidget/ProposalPreviewGraph.module.css`
- Test: `frontend/src/components/InterviewWidget/ProposalPreviewGraph.test.tsx`

**Interfaces:**
- Consumes: `ProposalItem` type (Task 8), `getArtifactTypeColorVar` (Task 9).
- Produces: `<ProposalPreviewGraph proposal={ProposalItem[]} />` — pure display, `data-testid="proposal-preview-graph"`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/InterviewWidget/ProposalPreviewGraph.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProposalPreviewGraph } from "./ProposalPreviewGraph";
import type { ProposalItem } from "../../api/interviews";

const proposal: ProposalItem[] = [
  { type: "StakeholderNeed", title: "Need A", fields: { title: "Need A" }, links: [] },
  { type: "Requirement", title: "Req B", fields: { title: "Req B" }, links: [{ from: 1, to: 0, type: "derives-from" }] },
];

describe("ProposalPreviewGraph", () => {
  it("renders one node per proposal item", () => {
    render(<ProposalPreviewGraph proposal={proposal} />);
    expect(screen.getByTestId("proposal-preview-graph")).toBeInTheDocument();
    expect(screen.getByText("Need A")).toBeInTheDocument();
    expect(screen.getByText("Req B")).toBeInTheDocument();
  });

  it("renders a type badge per node", () => {
    render(<ProposalPreviewGraph proposal={proposal} />);
    expect(screen.getByText("StakeholderNeed")).toBeInTheDocument();
    expect(screen.getByText("Requirement")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/InterviewWidget/ProposalPreviewGraph.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/InterviewWidget/ProposalPreviewGraph.tsx
import { useMemo } from "react";
import ReactFlow, { Background, type Edge, type Node, type NodeTypes, type EdgeTypes } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { ProposalItem } from "../../api/interviews";
import { getArtifactTypeColorVar } from "../../constants/artifactTypeColors";
import styles from "./ProposalPreviewGraph.module.css";

// Defined at module scope -- React Flow needs a stable reference for
// NODE_TYPES/EDGE_TYPES across renders, same reasoning as GraphCanvas.tsx.
function ProposalNode({ data }: { data: { title: string; type: string } }) {
  return (
    <div className={styles.node} style={{ borderColor: getArtifactTypeColorVar(data.type) }}>
      <span className={styles.nodeType}>{data.type}</span>
      <span className={styles.nodeTitle}>{data.title}</span>
    </div>
  );
}

const NODE_TYPES: NodeTypes = { proposalNode: ProposalNode };
const EDGE_TYPES: EdgeTypes = {};

interface ProposalPreviewGraphProps {
  proposal: ProposalItem[];
}

export function ProposalPreviewGraph({ proposal }: ProposalPreviewGraphProps): JSX.Element {
  const nodes: Node[] = useMemo(
    () =>
      proposal.map((item, index) => ({
        id: String(index),
        type: "proposalNode",
        position: { x: (index % 3) * 220, y: Math.floor(index / 3) * 120 },
        data: { title: item.title, type: item.type },
        draggable: false,
        selectable: false,
      })),
    [proposal]
  );

  const edges: Edge[] = useMemo(
    () =>
      proposal.flatMap((item, index) =>
        item.links.map((link, linkIndex) => ({
          id: `${index}-${link.from}-${link.to}-${linkIndex}`,
          source: String(link.from),
          target: String(link.to),
          label: link.type,
          selectable: false,
        }))
      ),
    [proposal]
  );

  return (
    <div className={styles.container} data-testid="proposal-preview-graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
      >
        <Background />
      </ReactFlow>
    </div>
  );
}
```

```css
/* frontend/src/components/InterviewWidget/ProposalPreviewGraph.module.css */
.container {
  height: 280px;
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.node {
  padding: 8px 12px;
  border: 2px solid;
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 140px;
}

.nodeType {
  font-size: 11px;
  opacity: 0.7;
}

.nodeTitle {
  font-weight: 600;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/InterviewWidget/ProposalPreviewGraph.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/InterviewWidget/ProposalPreviewGraph.tsx frontend/src/components/InterviewWidget/ProposalPreviewGraph.module.css frontend/src/components/InterviewWidget/ProposalPreviewGraph.test.tsx
git commit -m "feat: add ProposalPreviewGraph display component"
```

---

## Task 11: i18n namespace + retrofit existing 8 buttons

**Files:**
- Modify: `frontend/src/i18n/locales/en.json`, `frontend/src/i18n/locales/de.json`
- Modify: `frontend/src/constants/interviewArtifactTypes.ts`

**Interfaces:**
- Produces: new `"interview"` i18n namespace with `interview.start.<Type>` (8 keys, one per existing type), `interview.multiEntry`, `interview.multi.*` (chat/proposal/confirm/result keys used by Tasks 12-13).

- [ ] **Step 1: Write the failing test**

The project's existing i18n-parity ratchet test already enforces DE/EN key symmetry project-wide — no new test file needed, just run it:

Run: `cd frontend && npx vitest run src/test/i18n-parity.test.ts`
Expected (before this task): PASS today (no `interview.*` keys referenced yet in code) — this task's own Step 3 change is what will make later tasks' new `t("interview....")` calls parity-safe.

- [ ] **Step 2: (n/a — this task adds keys ahead of the components that consume them, so there's nothing to fail yet; verified retroactively in Task 12/13)**

- [ ] **Step 3: Add the namespace**

In both `en.json` and `de.json`, add (English shown, translate literally for `de.json`):

```json
{
  "interview": {
    "start": {
      "StakeholderNeed": "Stakeholder Need",
      "Requirement": "Requirement",
      "ArchitectureElement": "Architecture Element",
      "Risk": "Risk",
      "TestCase": "Test Case",
      "Adr": "ADR",
      "Issue": "Issue",
      "Goal": "Goal"
    },
    "multiEntry": "I'm not sure yet what I need",
    "multi": {
      "chatPlaceholder": "Describe your problem...",
      "send": "Send",
      "proposalHeading": "Proposed artifacts",
      "confirm": "Create these artifacts",
      "resultHeading": "Created artifacts",
      "createdBadge": "Created via interview"
    }
  }
}
```

German (`de.json`):

```json
{
  "interview": {
    "start": {
      "StakeholderNeed": "Stakeholder-Bedarf",
      "Requirement": "Anforderung",
      "ArchitectureElement": "Architekturelement",
      "Risk": "Risiko",
      "TestCase": "Testfall",
      "Adr": "ADR",
      "Issue": "Issue",
      "Goal": "Ziel"
    },
    "multiEntry": "Ich weiß noch nicht genau, was ich brauche",
    "multi": {
      "chatPlaceholder": "Beschreibe dein Problem...",
      "send": "Senden",
      "proposalHeading": "Vorgeschlagene Artefakte",
      "confirm": "Diese Artefakte anlegen",
      "resultHeading": "Angelegte Artefakte",
      "createdBadge": "Angelegt via Interview"
    }
  }
}
```

In `frontend/src/constants/interviewArtifactTypes.ts`, keep `INTERVIEW_ARTIFACT_TYPES` as the raw type strings (used as REST/MCP values), but the button label in `InterviewWidget.tsx` (Task 13) will look up `t(\`interview.start.${type}\`)` instead of rendering the raw string.

- [ ] **Step 4: Run the parity test**

Run: `cd frontend && npx vitest run src/test/i18n-parity.test.ts`
Expected: PASS (new keys are symmetric in both files)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/i18n/locales/en.json frontend/src/i18n/locales/de.json
git commit -m "feat: add interview i18n namespace"
```

---

## Task 12: `InterviewChatPane.tsx` — proposal card + result summary render cases

**Files:**
- Modify: `frontend/src/components/InterviewWidget/InterviewChatPane.tsx`
- Test: `frontend/src/components/InterviewWidget/InterviewChatPane.test.tsx` (extend existing file)

**Interfaces:**
- Consumes: `ProposalPreviewGraph` (Task 10), `interviewsApi.propose`/`.formalize` (Task 8), `interview.multi.*` i18n keys (Task 11).
- Produces: `<InterviewChatPane sessionId session onFormalized={(created) => void} />` now renders a proposal card when `interviewsApi.propose()` returns a non-null proposal, and a result summary after a successful multi-formalize.

- [ ] **Step 1: Write the failing test**

```tsx
// Append to frontend/src/components/InterviewWidget/InterviewChatPane.test.tsx
import { interviewsApi } from "../../api/interviews";
vi.mock("../../api/interviews");

describe("InterviewChatPane multi-mode", () => {
  it("renders the proposal preview and a confirm button when a proposal is pending", async () => {
    (interviewsApi.propose as any).mockResolvedValue({
      proposal: [{ type: "StakeholderNeed", title: "Need A", fields: { title: "Need A" }, links: [] }],
    });
    render(<InterviewChatPane sessionId="s1" session={{ id: "s1", session_kind: "multi" }} onFormalized={vi.fn()} />);
    expect(await screen.findByTestId("proposal-preview-graph")).toBeInTheDocument();
    expect(screen.getByTestId("interview-multi-confirm")).toBeInTheDocument();
  });

  it("confirming calls formalize with the proposal and shows the result summary", async () => {
    const onFormalized = vi.fn();
    (interviewsApi.propose as any).mockResolvedValue({
      proposal: [{ type: "StakeholderNeed", title: "Need A", fields: { title: "Need A" }, links: [] }],
    });
    (interviewsApi.formalize as any).mockResolvedValue({
      created: [{ artifact_id: "a1", artifact_type: "StakeholderNeed" }],
    });
    render(<InterviewChatPane sessionId="s1" session={{ id: "s1", session_kind: "multi" }} onFormalized={onFormalized} />);

    const confirmBtn = await screen.findByTestId("interview-multi-confirm");
    fireEvent.click(confirmBtn);

    expect(await screen.findByTestId("interview-multi-result")).toBeInTheDocument();
    expect(onFormalized).toHaveBeenCalledWith([{ artifact_id: "a1", artifact_type: "StakeholderNeed" }]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/InterviewWidget/InterviewChatPane.test.tsx`
Expected: FAIL — no proposal card / confirm button / result summary exist yet.

- [ ] **Step 3: Implement**

In `InterviewChatPane.tsx`, add state and two new render branches (alongside the existing single transcript-render path):

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { interviewsApi, type ProposalItem } from "../../api/interviews";
import { ProposalPreviewGraph } from "./ProposalPreviewGraph";

// ... inside the component, alongside existing transcript/input state ...
const { t } = useTranslation();
const [pendingProposal, setPendingProposal] = useState<ProposalItem[] | null>(null);
const [createdArtifacts, setCreatedArtifacts] = useState<{ artifact_id: string; artifact_type: string }[] | null>(null);

useEffect(() => {
  if (session.session_kind !== "multi") return;
  interviewsApi.propose(sessionId).then((r) => setPendingProposal(r.proposal));
}, [sessionId, session.session_kind, transcript]); // re-check after every new transcript turn

async function handleConfirmProposal() {
  if (!pendingProposal) return;
  const result = await interviewsApi.formalize(sessionId, pendingProposal);
  setCreatedArtifacts(result.created);
  setPendingProposal(null);
  onFormalized(result.created);
}

// ... in the render, after the transcript list and before/instead of the input row when applicable ...
{pendingProposal && !createdArtifacts && (
  <div className="interview-proposal-card">
    <h3>{t("interview.multi.proposalHeading")}</h3>
    <ProposalPreviewGraph proposal={pendingProposal} />
    <button data-testid="interview-multi-confirm" onClick={handleConfirmProposal}>
      {t("interview.multi.confirm")}
    </button>
  </div>
)}
{createdArtifacts && (
  <div data-testid="interview-multi-result" className="interview-result-summary">
    <h3>{t("interview.multi.resultHeading")}</h3>
    <ul>
      {createdArtifacts.map((ref) => (
        <li key={ref.artifact_id}>
          <span className="badge">{ref.artifact_type}</span>
          <a href={`/artifacts/${ref.artifact_id}`}>{ref.artifact_id}</a>
        </li>
      ))}
    </ul>
  </div>
)}
```

`onFormalized` is a new required prop on `InterviewChatPane` — update its parent (`InterviewWidget.tsx`, Task 13) to pass a handler.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/InterviewWidget/InterviewChatPane.test.tsx`
Expected: PASS (all existing tests + 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/InterviewWidget/InterviewChatPane.tsx frontend/src/components/InterviewWidget/InterviewChatPane.test.tsx
git commit -m "feat: render proposal card and result summary in InterviewChatPane"
```

---

## Task 13: `InterviewWidget.tsx` — multi entry point, WRITE-gate, i18n retrofit

**Files:**
- Modify: `frontend/src/components/InterviewWidget/InterviewWidget.tsx`
- Test: `frontend/src/components/InterviewWidget/InterviewWidget.test.tsx` (extend existing file)

**Interfaces:**
- Consumes: `interviewsApi.start(workspaceId, null, "multi")` (Task 8), `interview.multiEntry`/`interview.start.*` i18n keys (Task 11).
- Produces: a 9th button ("I'm not sure yet what I need") that starts a multi-mode session; the 8 existing buttons now show translated labels instead of raw type strings; a WRITE-permission gate (new — none existed before this task) hiding all 9 buttons for a Viewer.

**Known, deliberately scoped-out gap:** no reusable `useCanWrite()`/role-check hook exists anywhere in `frontend/src` today (verified by a full-repo grep before writing this plan). Building a proper role-resolution hook is out of scope for this feature — it would touch `WorkspaceContext` and every other write-gated UI surface, a much larger refactor. This task adds the minimum local check needed here only: reading `activeWorkspace?.currentUserRole` off `WorkspaceContext` if that field exists, else defaulting to visible (matches today's actual behavior, i.e. does not regress anything that currently works, but does not retroactively fix the pre-existing "no button in this widget was ever gated" gap for the 8 single-type buttons either — flagged explicitly rather than silently expanding scope).

- [ ] **Step 1: Write the failing test**

```tsx
// Append to frontend/src/components/InterviewWidget/InterviewWidget.test.tsx
describe("InterviewWidget multi entry", () => {
  it("renders a 9th button for multi-mode discovery", () => {
    render(<InterviewWidget />);
    expect(screen.getByTestId("interview-widget-start-multi")).toBeInTheDocument();
  });

  it("existing type buttons show translated labels, not raw type strings", () => {
    render(<InterviewWidget />);
    expect(screen.getByText("Requirement")).toBeInTheDocument(); // en.json value happens to match the raw string for this one type
    expect(screen.queryByText("ArchitectureElement")).not.toBeInTheDocument(); // raw string must NOT appear
    expect(screen.getByText("Architecture Element")).toBeInTheDocument(); // translated value
  });

  it("clicking the multi button starts a session with session_kind=multi and null artifact_type", async () => {
    const startSpy = vi.spyOn(interviewsApi, "start").mockResolvedValue({ id: "s1", session_kind: "multi" });
    render(<InterviewWidget />);
    fireEvent.click(screen.getByTestId("interview-widget-start-multi"));
    await waitFor(() => expect(startSpy).toHaveBeenCalledWith(expect.any(String), null, "multi"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/InterviewWidget/InterviewWidget.test.tsx`
Expected: FAIL — no multi button, labels still raw strings.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/InterviewWidget/InterviewWidget.tsx
import { useTranslation } from "react-i18next";
import { INTERVIEW_ARTIFACT_TYPES } from "../../constants/interviewArtifactTypes";
import { interviewsApi } from "../../api/interviews";

// ... inside the component ...
const { t } = useTranslation();

async function startMultiInterview() {
  setStarting(true);
  try {
    const session = await interviewsApi.start(activeWorkspaceId, null, "multi");
    onSessionStarted(session);
  } finally {
    setStarting(false);
  }
}

// ... in the render, alongside the existing .map() over INTERVIEW_ARTIFACT_TYPES ...
{INTERVIEW_ARTIFACT_TYPES.map((type) => (
  <button
    key={type}
    data-testid={`interview-widget-start-${type}`}
    onClick={() => void startInterview(type)}
  >
    {starting ? <Spinner /> : t(`interview.start.${type}`)}
  </button>
))}
<button data-testid="interview-widget-start-multi" onClick={() => void startMultiInterview()}>
  {starting ? <Spinner /> : t("interview.multiEntry")}
</button>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/InterviewWidget/InterviewWidget.test.tsx`
Expected: PASS (all existing tests + 3 new ones)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/InterviewWidget/InterviewWidget.tsx frontend/src/components/InterviewWidget/InterviewWidget.test.tsx
git commit -m "feat: add multi-artifact discovery entry point to InterviewWidget"
```

---

## Task 14: Provenance info block on artifact detail pages

**Files:**
- Modify: `frontend/src/api/interviews.ts` (add `getProvenance`)
- Modify: `backend/rest_api/interview_views.py` (add a provenance lookup action, OR expose it via the artifact's own detail endpoint — see Step 3 for the chosen approach)
- Create: `frontend/src/components/shared/InterviewProvenanceBadge.tsx`
- Test: `backend/rest_api/tests/test_interview_provenance.py`, `frontend/src/components/shared/InterviewProvenanceBadge.test.tsx`

**Interfaces:**
- Produces: `GET /api/v1/interviews/by-artifact/{artifact_id}/` → `{ session_id: str | null }`; `<InterviewProvenanceBadge artifactId={string} />` — renders nothing if no provenance row exists, else a link to the interview transcript.

- [ ] **Step 1: Write the failing backend test**

```python
# backend/rest_api/tests/test_interview_provenance.py
import pytest
from rest_framework.test import APIClient

from persistence.models import InterviewSession, InterviewSessionArtifact, Artifact
from persistence.tests.factories import active_tenant, make_workspace, editor_user_and_token


@pytest.mark.django_db
class TestInterviewProvenanceEndpoint:
    def test_returns_session_id_for_provenanced_artifact(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            session = InterviewSession.objects.create(
                tenant=tenant, workspace=ws, artifact_type=None, session_kind="multi", status="completed"
            )
            artifact = Artifact.objects.create(tenant=tenant, workspace=ws, artifact_type="Requirement")
            InterviewSessionArtifact.objects.create(
                tenant=tenant, session=session, artifact=artifact, artifact_type="Requirement"
            )

            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get(f"/api/v1/interviews/by-artifact/{artifact.id}/")
            assert response.status_code == 200
            assert response.data["session_id"] == str(session.id)

    def test_returns_null_for_non_provenanced_artifact(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            artifact = Artifact.objects.create(tenant=tenant, workspace=ws, artifact_type="Requirement")

            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get(f"/api/v1/interviews/by-artifact/{artifact.id}/")
            assert response.status_code == 200
            assert response.data["session_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/rest_api/tests/test_interview_provenance.py -v`
Expected: FAIL — endpoint doesn't exist.

- [ ] **Step 3: Implement the backend endpoint**

A list-level (non-detail) custom action, since the lookup key is an artifact id, not a session id:

```python
# backend/rest_api/interview_views.py, inside InterviewViewSet
@action(detail=False, methods=["get"], url_path="by-artifact/(?P<artifact_id>[^/.]+)")
def by_artifact(self, request: Request, artifact_id: str, **kwargs: Any) -> Response:
    """GET /api/v1/interviews/by-artifact/{artifact_id}/ -- provenance lookup."""
    lang = detect_lang(request)
    parsed_id, error = parse_uuid_param(artifact_id, lang, name="artifact_id")
    if error is not None:
        return error
    try:
        ctx = get_auth_context(request)
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        row = InterviewSessionArtifact.objects.filter(artifact_id=parsed_id).select_related("session").first()
    except _SERVICE_EXCEPTIONS as exc:
        return _service_error_response(exc, lang)
    return Response({"session_id": str(row.session_id) if row else None})
```

Add the import: `from persistence.models import InterviewSessionArtifact` at the top of `interview_views.py`.

- [ ] **Step 4: Run backend test to verify it passes**

Run: `pytest backend/rest_api/tests/test_interview_provenance.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing frontend test**

```tsx
// frontend/src/components/shared/InterviewProvenanceBadge.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { InterviewProvenanceBadge } from "./InterviewProvenanceBadge";
import { interviewsApi } from "../../api/interviews";

vi.mock("../../api/interviews");

describe("InterviewProvenanceBadge", () => {
  it("renders nothing when no provenance exists", async () => {
    (interviewsApi.getProvenance as any).mockResolvedValue({ session_id: null });
    const { container } = render(<InterviewProvenanceBadge artifactId="a1" />);
    await waitFor(() => expect(interviewsApi.getProvenance).toHaveBeenCalledWith("a1"));
    expect(container.querySelector('[data-testid="interview-provenance-badge"]')).toBeNull();
  });

  it("renders a link when provenance exists", async () => {
    (interviewsApi.getProvenance as any).mockResolvedValue({ session_id: "s1" });
    render(<InterviewProvenanceBadge artifactId="a1" />);
    expect(await screen.findByTestId("interview-provenance-badge")).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run frontend test to verify it fails**

Run: `cd frontend && npx vitest run src/components/shared/InterviewProvenanceBadge.test.tsx`
Expected: FAIL — component and `interviewsApi.getProvenance` don't exist.

- [ ] **Step 7: Implement the frontend piece**

Add to `frontend/src/api/interviews.ts`:

```typescript
getProvenance: (artifactId: string): Promise<{ session_id: string | null }> =>
  apiClient.get(`/interviews/by-artifact/${artifactId}/`).then((r) => r.data),
```

```tsx
// frontend/src/components/shared/InterviewProvenanceBadge.tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { interviewsApi } from "../../api/interviews";

interface InterviewProvenanceBadgeProps {
  artifactId: string;
}

export function InterviewProvenanceBadge({ artifactId }: InterviewProvenanceBadgeProps): JSX.Element | null {
  const { t } = useTranslation();
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    interviewsApi.getProvenance(artifactId).then((r) => {
      if (!cancelled) setSessionId(r.session_id);
    });
    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  if (!sessionId) return null;

  return (
    <a href={`/interviews/${sessionId}`} data-testid="interview-provenance-badge">
      {t("interview.multi.createdBadge")}
    </a>
  );
}
```

- [ ] **Step 8: Run frontend test to verify it passes**

Run: `cd frontend && npx vitest run src/components/shared/InterviewProvenanceBadge.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 9: Commit**

```bash
git add backend/rest_api/interview_views.py backend/rest_api/tests/test_interview_provenance.py frontend/src/api/interviews.ts frontend/src/components/shared/InterviewProvenanceBadge.tsx frontend/src/components/shared/InterviewProvenanceBadge.test.tsx
git commit -m "feat: add interview-provenance lookup endpoint and badge component"
```

**Note for the executor:** wiring `<InterviewProvenanceBadge artifactId={...} />` into each of the 9 artifact detail views (`RequirementDetail`, `NeedDetail`, etc.) is left as follow-up integration work outside this plan's task list — each detail component's exact render location differs enough (9 different files) that it doesn't fit one bite-sized task. Add it to whichever detail view the person picking this up is already touching, or file a small follow-up plan.

---

## Task 15: Full-suite regression check

**Files:** none (verification-only task)

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest backend/ -x -q`
Expected: PASS, zero regressions in previously-green tests.

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS, zero regressions.

- [ ] **Step 3: Run `makemigrations --check` to catch any model/migration drift**

Run: `python backend/manage.py makemigrations --check --dry-run`
Expected: "No changes detected"

- [ ] **Step 4: Commit (if any drift was found and fixed in Steps 1-3)**

```bash
git add -A
git commit -m "fix: resolve regressions found in full-suite verification pass"
```

(Skip this step entirely if Steps 1-3 were clean — no empty commit.)

---

## Deliberately out of scope (v1, per spec)

- Inline editing of the proposal card (refinement only via chat, per spec).
- Multi-mode for non-requirements-like entities (Diagram, Baseline, WorkflowDefinition) — the 9 types are the v1 frame.
- A per-artifact-type permission matrix — the existing single `WRITE` check (now centralized in `formalize()`, Task 3) is reused as-is, no expansion.
- A general-purpose `useCanWrite()`/role-resolution hook for the frontend (Task 13's known gap) — building one is a separate, larger refactor touching every write-gated surface in the app, not scoped to this feature.
- Wiring `InterviewProvenanceBadge` into all 9 artifact detail views (Task 14's note) — the endpoint and component are complete and tested; per-view integration is follow-up work.
