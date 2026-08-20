# Interview-Management-Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend engine for cross-host structured interviews — a protocol config store, a resumable session model, an `interview.*` MCP tool group, AI-assisted grounding, and formalization logic that creates/updates real artifacts — plus the host-packaging plumbing so every AI host (Claude Code, Opencode, Antigravity) picks it up automatically.

**Architecture:** Reuse `PromptTemplate`'s existing 3-level override chain for protocol config instead of a new model. Add one new tenant-scoped model (`InterviewSession`) that carries real server-side turn state, so a session survives across hosts. One new MCP tool group (`interview.*`) is the only access path; formalization is pure orchestration of existing artifact services, no new write path. AI-assisted grounding follows `BundleCompressionService`'s existing `_resolve_provider`/`_call_provider` free-form-completion pattern (not the `ALLOWED_CAPABILITIES`/`CapabilityRouter` structured-method pattern — that pattern is for named per-capability provider methods; grounding just needs one more free-text completion call with audit/token-tracking, exactly what `BundleCompressionService` already does for a different prompt).

**Tech Stack:** Django 4.2+ / DRF, PostgreSQL 16 + RLS, `llm_adapter` provider abstraction, MCP JSON-RPC 2.0 tool groups, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-14-interview-management-engine-design.md` (Spec 1 of 3; this plan implements it in full, including its two later amendments — field `type` in protocol config, `transcript` field, section 4.1 REST facade note).

## Global Constraints

- All artifact types except `MainGoal` are in scope: `Requirement`, `ArchitectureElement`, `StakeholderNeed`, `Risk`, `TestCase`, `Adr`, `Issue`, `Goal` (spec §1). `artifact_type` values are PascalCase, matching `Artifact.artifact_type` elsewhere in the codebase (spec §3.1, corrected).
- `InterviewSession` is `TenantScopedModel` — RLS applies exactly like every other tenant-scoped table (spec §3.2).
- No new write path for artifact creation/update — `interview.formalize` only orchestrates existing services (spec §5).
- Grounding is fail-open: without a configured LLM provider it falls back to structural filtering only, never blocks (spec §6).
- MCP write tools (`interview.start`, `.answer`, `.formalize`) go through the existing `_WRITE_TOOL_PREFIXES` RBAC/audit gate in `backend/mcp_server/tool_registry.py` (spec §4).
- Host packaging reuses the existing `dist/agent-skills/` → build-script → per-host-plugin pipeline; no new packaging mechanism (spec §7).
- This plan does NOT include the REST facade (`/api/v1/interviews/...`, spec §4.1) or the `interview.chat_turn` LLM capability — those are Spec 3's plan (native web widget), which depends on this plan's MCP tool group and services being in place first. This plan also does NOT include Spec 2's Hermes-plugin work (separate repo area, separate plan).

---

## Task 1: `InterviewSession` model + migration

**Files:**
- Modify: `backend/persistence/models.py` (add `InterviewSession` near `TokenUsageRecord`/`PromptTemplate`, same file every other tenant-scoped model lives in)
- Create: `backend/persistence/migrations/0XXX_add_interview_session.py` (run `python manage.py makemigrations persistence` to get the real next number — do not hand-guess it)
- Test: `backend/persistence/tests/test_interview_session_model.py`

**Interfaces:**
- Produces: `persistence.models.InterviewSession` — fields `id` (inherited UUID PK), `tenant` (inherited FK), `workspace` (FK to `Workspace`), `artifact_type` (`CharField`), `status` (`CharField`, one of `"in_progress" | "completed" | "abandoned"`), `target_artifact` (nullable FK to `Artifact`), `collected_fields` (`JSONField`, default `dict`), `grounding_snapshot` (`JSONField`, default `dict`), `resulting_artifact_ids` (`JSONField`, default `list`), `transcript` (`JSONField`, default `list`), `created_by`/`modified_at`/`version` (inherited from `AuditableModel`, do not redeclare).

- [ ] **Step 1: Write the failing model test**

```python
# backend/persistence/tests/test_interview_session_model.py
"""InterviewSession model — REQ (Interview-Management-Engine spec §3.2)."""
from __future__ import annotations

import pytest

from persistence.models import Artifact, InterviewSession, Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Interview Tenant", slug="interview-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


class TestInterviewSessionDefaults:
    def test_creates_with_defaults(self, tenant, workspace):
        TenantContext.set_tenant(tenant.id)
        try:
            session = InterviewSession.objects.create(
                workspace=workspace, artifact_type="Requirement"
            )
        finally:
            TenantContext.clear_tenant()

        assert session.status == "in_progress"
        assert session.collected_fields == {}
        assert session.grounding_snapshot == {}
        assert session.resulting_artifact_ids == []
        assert session.transcript == []
        assert session.target_artifact is None

    def test_target_artifact_survives_artifact_deletion_as_null(self, tenant, workspace):
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = Artifact.objects.create(
                workspace=workspace, artifact_type="Requirement"
            )
            session = InterviewSession.objects.create(
                workspace=workspace,
                artifact_type="Requirement",
                target_artifact=artifact,
            )
            artifact.delete()
            session.refresh_from_db()
        finally:
            TenantContext.clear_tenant()

        assert session.target_artifact_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest persistence/tests/test_interview_session_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'InterviewSession'`

- [ ] **Step 3: Add the model**

Add to `backend/persistence/models.py`, placed after `TokenUsageRecord` (same file, same style — `TenantScopedModel` base, `pl_` table prefix):

```python
class InterviewSession(TenantScopedModel):
    """Cross-host interview progress state (Interview-Management-Engine spec §3.2).

    The server-side turn state that lets a session started on one host
    (e.g. Claude Code) resume on another (e.g. Hermes) — every host reads
    this row via interview.get_state instead of relying on its own
    conversation history.
    """

    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_ABANDONED = "abandoned"
    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_ABANDONED, "Abandoned"),
    ]

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="interview_sessions"
    )
    artifact_type = models.CharField(
        max_length=64,
        help_text="Which interview protocol applies (PascalCase, matches Artifact.artifact_type).",
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS
    )
    target_artifact = models.ForeignKey(
        Artifact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interview_sessions",
        help_text="Set once grounding identifies an existing artifact to adjust instead of creating a new one.",
    )
    collected_fields = models.JSONField(default=dict, blank=True)
    grounding_snapshot = models.JSONField(default=dict, blank=True)
    resulting_artifact_ids = models.JSONField(default=list, blank=True)
    transcript = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {role, text, timestamp}. Only chat-driving clients (Spec 3) write to this; form clients (Spec 2) leave it empty.",
    )

    class Meta:
        db_table = "pl_interview_session"
        indexes = [
            models.Index(fields=["workspace", "status"]),
        ]
```

- [ ] **Step 4: Generate the migration**

Run: `docker exec reqogniloom-backend-1 python manage.py makemigrations persistence`
Expected: a new file `backend/persistence/migrations/0XXX_interviewsession.py` (Django names it from the model). Open it and confirm it only adds `InterviewSession` — no unrelated changes.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest persistence/tests/test_interview_session_model.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Add RLS coverage**

`InterviewSession` is `TenantScopedModel`, so it needs a policy row in the RLS migration the same way every other tenant table does. Check `backend/persistence/migrations/0003_rls_policies.py` for the pattern (it likely lists table names to apply `CREATE POLICY` to generically, or needs an explicit addition — read it first) and add `pl_interview_session` if the list is explicit rather than automatic.

- [ ] **Step 7: Write the RLS regression test**

```python
# Add to backend/persistence/tests/test_interview_session_model.py
from django.db import connection
import pytest as _pytest

from persistence.db_roles import APP_DB_ROLE

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = _pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


@_pg_only
class TestInterviewSessionRls:
    def test_direct_sql_without_tenant_context_sees_no_rows(self, tenant, workspace):
        TenantContext.set_tenant(tenant.id)
        try:
            InterviewSession.objects.create(workspace=workspace, artifact_type="Requirement")
        finally:
            TenantContext.clear_tenant()

        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pl_interview_session")
                count = cursor.fetchone()[0]
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

        assert count == 0, "RLS failed to block direct SQL access without app.current_tenant"
```

- [ ] **Step 8: Run RLS test**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest persistence/tests/test_interview_session_model.py -v`
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/ backend/persistence/tests/test_interview_session_model.py
git commit -m "feat: add InterviewSession model with RLS"
```

---

## Task 2: Interview protocol configuration (PromptTemplate reuse + YAML validation)

**Files:**
- Create: `backend/application/interview_protocol.py`
- Modify: `backend/mcp_server/tools/prompt_template.py` (add YAML validation for `interview.protocol.*` names on write)
- Test: `backend/application/tests/test_interview_protocol.py`

**Interfaces:**
- Consumes: `persistence.models.PromptTemplate` (existing), `application.ai_derivation_service._get_template_content` pattern for resolution.
- Produces: `application.interview_protocol.INTERVIEW_PROTOCOL_DEFAULTS: dict[str, str]` (factory-default YAML per artifact type, keyed `"interview.protocol.<ArtifactType>"`), `application.interview_protocol.get_protocol(ctx, artifact_type, workspace_id) -> ProtocolConfig`, `application.interview_protocol.ProtocolConfig` (parsed dataclass with `.phases: list[ProtocolPhase]`), `application.interview_protocol.ProtocolPhase` (dataclass: `name: str`, `required_fields: list[ProtocolField]`, `prompt_fragment: str`), `application.interview_protocol.ProtocolField` (dataclass: `name: str`, `type: str = "text"`, `choices: list[str] | None = None`), `application.interview_protocol.ProtocolValidationError(Exception)`.

- [ ] **Step 1: Write the failing test for YAML parsing**

```python
# backend/application/tests/test_interview_protocol.py
"""Interview protocol configuration — spec §3.1."""
from __future__ import annotations

import pytest

from application.interview_protocol import (
    INTERVIEW_PROTOCOL_DEFAULTS,
    ProtocolValidationError,
    parse_protocol_yaml,
)

VALID_YAML = """\
phases:
  - name: elicitation
    required_fields:
      - name: title
        type: text
      - name: rationale
        type: textarea
    prompt_fragment: "Ask for the requirement's title and rationale."
  - name: approval
    prompt_fragment: "Present the drafted requirement for approval."
  - name: formalization
    prompt_fragment: "Confirm and formalize."
"""


class TestParseProtocolYaml:
    def test_parses_phases_and_fields(self):
        protocol = parse_protocol_yaml(VALID_YAML)

        assert [p.name for p in protocol.phases] == ["elicitation", "approval", "formalization"]
        elicitation = protocol.phases[0]
        assert [f.name for f in elicitation.required_fields] == ["title", "rationale"]
        assert elicitation.required_fields[1].type == "textarea"

    def test_field_type_defaults_to_text(self):
        protocol = parse_protocol_yaml(
            "phases:\n"
            "  - name: elicitation\n"
            "    required_fields:\n"
            "      - name: title\n"
            "    prompt_fragment: 'x'\n"
        )
        assert protocol.phases[0].required_fields[0].type == "text"

    def test_rejects_malformed_yaml(self):
        with pytest.raises(ProtocolValidationError):
            parse_protocol_yaml("not: [valid, yaml: structure")

    def test_rejects_missing_phases_key(self):
        with pytest.raises(ProtocolValidationError):
            parse_protocol_yaml("phase_list: []\n")

    def test_rejects_enum_field_without_choices(self):
        with pytest.raises(ProtocolValidationError):
            parse_protocol_yaml(
                "phases:\n"
                "  - name: elicitation\n"
                "    required_fields:\n"
                "      - name: element_type\n"
                "        type: enum\n"
                "    prompt_fragment: 'x'\n"
            )


class TestInterviewProtocolDefaults:
    @pytest.mark.parametrize(
        "artifact_type",
        [
            "Requirement", "ArchitectureElement", "StakeholderNeed", "Risk",
            "TestCase", "Adr", "Issue", "Goal",
        ],
    )
    def test_every_in_scope_artifact_type_has_a_default(self, artifact_type):
        name = f"interview.protocol.{artifact_type}"
        assert name in INTERVIEW_PROTOCOL_DEFAULTS
        # Must itself be valid YAML per the parser above -- a broken factory
        # default would silently break interview.start for every workspace
        # that never overrides it.
        parse_protocol_yaml(INTERVIEW_PROTOCOL_DEFAULTS[name])

    def test_main_goal_has_no_default(self):
        assert "interview.protocol.MainGoal" not in INTERVIEW_PROTOCOL_DEFAULTS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test reqogniloom-backend-1 python -m pytest application/tests/test_interview_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.interview_protocol'`

- [ ] **Step 3: Implement the module**

```python
# backend/application/interview_protocol.py
"""Interview protocol configuration (Interview-Management-Engine spec §3.1).

Protocols are stored as PromptTemplate rows under the
"interview.protocol.<ArtifactType>" namespace, reusing that model's
existing 3-level override chain (workspace -> tenant-global ->
factory-default) instead of a new model. This module owns the YAML
structure inside a protocol's content and the factory-default registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

# All artifact types Spec 1 puts in scope (spec §1) -- everything except
# MainGoal, which stays read-only (matches the MCP surface: only
# main_goal.read/list_versions exist, no write tools).
IN_SCOPE_ARTIFACT_TYPES = (
    "Requirement",
    "ArchitectureElement",
    "StakeholderNeed",
    "Risk",
    "TestCase",
    "Adr",
    "Issue",
    "Goal",
)


class ProtocolValidationError(Exception):
    """Raised when protocol YAML is malformed or violates the schema."""


@dataclass
class ProtocolField:
    name: str
    type: str = "text"
    choices: "list[str] | None" = None


@dataclass
class ProtocolPhase:
    name: str
    required_fields: "list[ProtocolField]" = field(default_factory=list)
    prompt_fragment: str = ""


@dataclass
class ProtocolConfig:
    phases: "list[ProtocolPhase]"


_VALID_FIELD_TYPES = {"text", "textarea", "enum", "number"}


def parse_protocol_yaml(content: str) -> ProtocolConfig:
    """Parse and validate a protocol's YAML content.

    Raises:
        ProtocolValidationError: malformed YAML, missing required keys, or
            an ``enum`` field without ``choices``.
    """
    try:
        raw: Any = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ProtocolValidationError(f"Invalid YAML: {exc}") from exc

    if not isinstance(raw, dict) or "phases" not in raw:
        raise ProtocolValidationError("Protocol YAML must have a top-level 'phases' list.")

    phases = []
    for raw_phase in raw["phases"]:
        if "name" not in raw_phase:
            raise ProtocolValidationError("Each phase needs a 'name'.")
        raw_fields = raw_phase.get("required_fields") or []
        fields = []
        for raw_field in raw_fields:
            if "name" not in raw_field:
                raise ProtocolValidationError("Each required_field needs a 'name'.")
            field_type = raw_field.get("type", "text")
            if field_type not in _VALID_FIELD_TYPES:
                raise ProtocolValidationError(
                    f"Unknown field type {field_type!r} for field {raw_field['name']!r}."
                )
            choices = raw_field.get("choices")
            if field_type == "enum" and not choices:
                raise ProtocolValidationError(
                    f"Field {raw_field['name']!r} has type 'enum' but no 'choices'."
                )
            fields.append(ProtocolField(name=raw_field["name"], type=field_type, choices=choices))
        phases.append(
            ProtocolPhase(
                name=raw_phase["name"],
                required_fields=fields,
                prompt_fragment=raw_phase.get("prompt_fragment", ""),
            )
        )
    return ProtocolConfig(phases=phases)


def _default_protocol_yaml(artifact_type: str) -> str:
    """A minimal, valid factory default: one elicitation phase asking for
    title + rationale, then approval and formalization with no extra
    fields. Workspaces that need more override this via prompt_template.*
    (same mechanism as the other 7 derivation prompt types)."""
    return (
        "phases:\n"
        "  - name: elicitation\n"
        "    required_fields:\n"
        "      - name: title\n"
        "        type: text\n"
        "      - name: rationale\n"
        "        type: textarea\n"
        f"    prompt_fragment: \"Elicit the {artifact_type}'s title and rationale.\"\n"
        "  - name: approval\n"
        f"    prompt_fragment: \"Present the drafted {artifact_type} for approval.\"\n"
        "  - name: formalization\n"
        "    prompt_fragment: \"Confirm and formalize.\"\n"
    )


# Single canonical registry, same pattern as ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS
# (mcp_server.tools.prompt_template reads factory defaults from exactly one
# place per family so every read path agrees).
INTERVIEW_PROTOCOL_DEFAULTS: "dict[str, str]" = {
    f"interview.protocol.{artifact_type}": _default_protocol_yaml(artifact_type)
    for artifact_type in IN_SCOPE_ARTIFACT_TYPES
}


def get_protocol(ctx, artifact_type: str, workspace_id) -> ProtocolConfig:
    """Resolve the effective protocol for *artifact_type* in *workspace_id*.

    Follows PromptTemplate's existing workspace -> tenant-global ->
    factory-default chain via AiDerivationService._get_template_content,
    then parses+validates the resolved YAML.
    """
    from application.ai_derivation_service import AiDerivationService

    name = f"interview.protocol.{artifact_type}"
    content = AiDerivationService._get_template_content(ctx, name, workspace_id)
    if content is None:
        content = INTERVIEW_PROTOCOL_DEFAULTS.get(name)
    if content is None:
        raise ProtocolValidationError(
            f"No interview protocol configured or defaulted for artifact_type={artifact_type!r}."
        )
    return parse_protocol_yaml(content)
```

Note: check `AiDerivationService._get_template_content`'s exact signature and None-vs-default behavior before wiring the last function — the fallback logic above assumes it returns `None` when nothing is configured rather than already falling back internally; read the method first and adjust to match its real contract instead of guessing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test reqogniloom-backend-1 python -m pytest application/tests/test_interview_protocol.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Wire `INTERVIEW_PROTOCOL_DEFAULTS` into the factory-default lookup used by `prompt_template.get`/`.list`**

Read `backend/mcp_server/tools/prompt_template.py`'s `_handle_get` and whatever it imports for factory defaults (it currently reads `application.ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS`, per that module's own docstring cited in Task 2's context). Merge `INTERVIEW_PROTOCOL_DEFAULTS` into the same lookup path so `prompt_template.get(slot="interview.protocol.Requirement")` returns the factory default when no row exists — write a test for this in `backend/mcp_server/tests/test_tool_groups.py`'s existing `prompt_template` test class before changing the handler (TDD): assert `prompt_template.get` on a fresh tenant returns the interview factory default text, then implement.

- [ ] **Step 6: Add YAML validation to the write path**

In `backend/mcp_server/tools/prompt_template.py`'s create/update handler (`_handle_create_or_update`), add: if `name.startswith("interview.protocol.")`, call `interview_protocol.parse_protocol_yaml(content)` before writing and return `VALIDATION_ERROR` (matching the tool's existing error-code convention) if it raises `ProtocolValidationError`. Write the failing test first:

```python
# Add to backend/mcp_server/tests/test_tool_groups.py, in the PromptTemplate test class
def test_create_rejects_malformed_interview_protocol_yaml(self, registry, tenant, workspace):
    result = registry.dispatch(
        "prompt_template.create",
        {
            "name": "interview.protocol.Requirement",
            "content": "not: [valid, yaml: structure",
            "workspace_id": str(workspace.id),
        },
        ctx=make_ctx(tenant),
    )
    assert result.is_error
    assert result.error_code == "VALIDATION_ERROR"
```

(Adapt `registry.dispatch`/`make_ctx` calls to match this test file's actual existing helper names — read a neighboring test in the same class first rather than guessing the harness API.)

- [ ] **Step 7: Run full prompt_template + interview_protocol test suites**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_protocol.py mcp_server/tests/test_tool_groups.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/application/interview_protocol.py backend/application/tests/test_interview_protocol.py backend/mcp_server/tools/prompt_template.py backend/mcp_server/tests/test_tool_groups.py
git commit -m "feat: add interview protocol config (PromptTemplate reuse + YAML validation)"
```

---

## Task 3: `InterviewService` — start / get_state / answer

**Files:**
- Create: `backend/application/interview_service.py`
- Test: `backend/application/tests/test_interview_service.py`

**Interfaces:**
- Consumes: `persistence.models.InterviewSession` (Task 1), `application.interview_protocol.get_protocol` (Task 2), `application.base.ServiceBase._set_tenant_context`, `application.base.NotFoundError`/`ValidationError`.
- Produces: `application.interview_service.InterviewService` with methods `start(self, ctx, artifact_type: str, workspace_id: UUID, seed_context: dict | None = None) -> InterviewSession`, `get_state(self, ctx, session_id: UUID) -> dict` (returns `{phase, collected_fields, missing_fields, grounding_snapshot, status}`, where `missing_fields` is `list[{"name": str, "type": str, "choices": list[str] | None}]` — not bare strings; Spec 2's Hermes form view needs the type to pick an input control), `answer(self, ctx, session_id: UUID, field: str, value: Any) -> InterviewSession`, `list_sessions(self, ctx, workspace_id: UUID, status: str | None = None) -> QuerySet[InterviewSession]`, `get(self, ctx, session_id: UUID) -> InterviewSession`. Also `application.interview_service.ABANDONED_TTL` (a `datetime.timedelta` constant).

This task also implements spec §9's "verwaiste Sessions" behavior: a
session untouched past `ABANDONED_TTL` lazily flips to `abandoned` the
next time anything reads it (`get_state`/`get`/`list_sessions`) — no
scheduled job, matching the spec's explicit YAGNI call.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_interview_service.py
"""InterviewService core state machine — spec §4 (start/get_state/answer/list/get)."""
from __future__ import annotations

import pytest

from application.base import NotFoundError, ValidationError
from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="IS Tenant", slug="is-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant):
    return AuthContext(tenant_id=tenant.id, user_id=None, roles=("admin",))


class TestStart:
    def test_start_creates_session_with_first_phase_missing_fields(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        assert session.status == "in_progress"
        assert session.artifact_type == "Requirement"
        assert session.workspace_id == workspace.id

    def test_start_rejects_out_of_scope_artifact_type(self, ctx, workspace):
        with pytest.raises(ValidationError):
            InterviewService().start(ctx, "MainGoal", workspace.id)


class TestGetState:
    def test_reports_missing_fields_for_fresh_session(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        state = InterviewService().get_state(ctx, session.id)

        assert state["phase"] == "elicitation"
        missing_names = [f["name"] for f in state["missing_fields"]]
        assert "title" in missing_names
        title_field = next(f for f in state["missing_fields"] if f["name"] == "title")
        assert title_field["type"] == "text"
        assert state["collected_fields"] == {}

    def test_unknown_session_raises_not_found(self, ctx):
        import uuid

        with pytest.raises(NotFoundError):
            InterviewService().get_state(ctx, uuid.uuid4())


class TestAnswer:
    def test_answer_moves_field_from_missing_to_collected(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        InterviewService().answer(ctx, session.id, "title", "Login must support SSO")
        state = InterviewService().get_state(ctx, session.id)

        assert state["collected_fields"]["title"] == "Login must support SSO"
        assert "title" not in [f["name"] for f in state["missing_fields"]]

    def test_answer_on_completed_session_raises_validation_error(self, ctx, workspace):
        from persistence.models import InterviewSession

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                status=InterviewSession.STATUS_COMPLETED
            )
        finally:
            TenantContext.clear_tenant()

        with pytest.raises(ValidationError):
            InterviewService().answer(ctx, session.id, "title", "x")


class TestListAndGet:
    def test_list_filters_by_status(self, ctx, workspace):
        svc = InterviewService()
        s1 = svc.start(ctx, "Requirement", workspace.id)
        s2 = svc.start(ctx, "Risk", workspace.id)

        results = list(svc.list_sessions(ctx, workspace.id, status="in_progress"))

        assert {r.id for r in results} == {s1.id, s2.id}

    def test_get_returns_the_session(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        fetched = InterviewService().get(ctx, session.id)
        assert fetched.id == session.id


class TestAbandonedTtl:
    """spec §9: a session untouched past ABANDONED_TTL lazily flips to
    abandoned on the next read -- no scheduled job."""

    def test_get_state_flips_stale_session_to_abandoned(self, ctx, workspace):
        from persistence.models import InterviewSession

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            # Simulate a session nobody touched in a long time by
            # backdating modified_at past ABANDONED_TTL directly in the DB
            # (auto_now would otherwise overwrite any value set via .save()).
            InterviewSession.objects.filter(id=session.id).update(
                modified_at=timezone.now() - ABANDONED_TTL - timedelta(days=1)
            )
        finally:
            TenantContext.clear_tenant()

        state = InterviewService().get_state(ctx, session.id)

        assert state["status"] == "abandoned"

    def test_recent_session_is_not_flipped(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        state = InterviewService().get_state(ctx, session.id)

        assert state["status"] == "in_progress"

    def test_list_bulk_flips_stale_sessions(self, ctx, workspace):
        from persistence.models import InterviewSession

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                modified_at=timezone.now() - ABANDONED_TTL - timedelta(days=1)
            )
        finally:
            TenantContext.clear_tenant()

        in_progress = list(
            InterviewService().list_sessions(ctx, workspace.id, status="in_progress")
        )

        assert session.id not in {s.id for s in in_progress}
```

Add `from datetime import timedelta` and `from django.utils import timezone` to this test file's imports, and `from application.interview_service import ABANDONED_TTL, InterviewService` (extending the existing `InterviewService`-only import).

Check `AuthContext`'s real constructor signature in `backend/auth_tenancy/context.py` before running this — the fixture above assumes `tenant_id`/`user_id`/`roles` kwargs; adjust to match if the real dataclass differs.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.interview_service'`

- [ ] **Step 3: Implement `InterviewService`**

```python
# backend/application/interview_service.py
"""InterviewService — core session state machine (Interview-Management-Engine spec §4-5).

start/get_state/answer/list/get here; grounding is Task 5-6,
formalize is Task 7. Kept in this one file per the spec's "one MCP
toolgroup, one engine" framing -- split further only if it grows past
a single clear responsibility.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional
from uuid import UUID

from django.utils import timezone

from application.base import NotFoundError, ServiceBase, ValidationError
from application.interview_protocol import IN_SCOPE_ARTIFACT_TYPES, get_protocol
from persistence.models import InterviewSession

# spec §9 "verwaiste Sessions": a session untouched this long lazily flips
# to abandoned the next time anything reads it. No scheduled job (YAGNI).
ABANDONED_TTL = timedelta(days=30)


class InterviewService(ServiceBase):
    def start(
        self,
        ctx,
        artifact_type: str,
        workspace_id: UUID,
        seed_context: "Optional[dict]" = None,
    ) -> InterviewSession:
        if artifact_type not in IN_SCOPE_ARTIFACT_TYPES:
            raise ValidationError(
                f"Interviews are not available for artifact_type={artifact_type!r} "
                f"(MainGoal stays read-only; other unknown types are unsupported)."
            )
        self._set_tenant_context(ctx)
        # Fail fast if the protocol config is missing/broken rather than
        # creating a session that can never progress past get_state.
        get_protocol(ctx, artifact_type, workspace_id)
        return InterviewSession.objects.create(
            workspace_id=workspace_id,
            artifact_type=artifact_type,
            collected_fields=(seed_context or {}),
        )

    def _get_session(self, ctx, session_id: UUID) -> InterviewSession:
        self._set_tenant_context(ctx)
        session = InterviewSession.objects.filter(id=session_id).first()
        if session is None:
            raise NotFoundError(f"InterviewSession {session_id} not found")
        self._lazily_abandon_if_stale(session)
        return session

    @staticmethod
    def _lazily_abandon_if_stale(session: InterviewSession) -> None:
        """spec §9: flip a stale in_progress session to abandoned on read.

        Mutates and saves *session* in place when it fires, so callers that
        already hold the returned object see the up-to-date status without
        re-fetching.
        """
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            return
        if timezone.now() - session.modified_at < ABANDONED_TTL:
            return
        session.status = InterviewSession.STATUS_ABANDONED
        session.save(update_fields=["status", "modified_at", "version"])

    def _current_phase_and_missing(self, session: InterviewSession):
        protocol = get_protocol(ctx=None, artifact_type=session.artifact_type, workspace_id=session.workspace_id)  # noqa: E501 -- see note below
        for phase in protocol.phases:
            missing = [
                f for f in phase.required_fields
                if f.name not in session.collected_fields
            ]
            if missing:
                return phase, missing
        # Every field of every phase is answered.
        return protocol.phases[-1], []

    @staticmethod
    def _serialise_field(f) -> "dict[str, Any]":
        # Spec 2 (Hermes plugin, §3-4): InterviewFormView renders one input
        # per missing field and needs its type/choices to pick the right
        # control (text/textarea/enum/number) -- a bare field-name string
        # would lose exactly the information the protocol config's `type`
        # amendment was added for. Every host consumes this same shape;
        # skill-driven hosts (Claude Code/Opencode/Antigravity) just read
        # `.name` and ignore `.type`/`.choices`.
        return {"name": f.name, "type": f.type, "choices": f.choices}

    def get_state(self, ctx, session_id: UUID) -> "dict[str, Any]":
        session = self._get_session(ctx, session_id)
        phase, missing = self._current_phase_and_missing(session)
        return {
            "session_id": str(session.id),
            "status": session.status,
            "phase": phase.name,
            "collected_fields": session.collected_fields,
            "missing_fields": [self._serialise_field(f) for f in missing],
            "grounding_snapshot": session.grounding_snapshot,
        }

    def answer(self, ctx, session_id: UUID, field: str, value: Any) -> InterviewSession:
        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session_id} is {session.status}, cannot answer."
            )
        session.collected_fields = {**session.collected_fields, field: value}
        session.save(update_fields=["collected_fields", "modified_at", "version"])
        return session

    def list_sessions(self, ctx, workspace_id: UUID, status: "Optional[str]" = None):
        self._set_tenant_context(ctx)
        # Bulk-flip stale rows before filtering, so a "status=in_progress"
        # list doesn't include sessions that are stale-but-not-yet-read
        # individually (list_sessions has no single row to lazily patch the
        # way _get_session does).
        InterviewSession.objects.filter(
            workspace_id=workspace_id,
            status=InterviewSession.STATUS_IN_PROGRESS,
            modified_at__lt=timezone.now() - ABANDONED_TTL,
        ).update(status=InterviewSession.STATUS_ABANDONED)

        qs = InterviewSession.objects.filter(workspace_id=workspace_id)
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-modified_at")

    def get(self, ctx, session_id: UUID) -> InterviewSession:
        return self._get_session(ctx, session_id)
```

**Fix before running:** `_current_phase_and_missing` calls `get_protocol(ctx=None, ...)` — this is wrong, `get_protocol` needs a real `ctx` to resolve the PromptTemplate override chain. Thread the real `ctx` through instead (pass it into `_current_phase_and_missing(self, ctx, session)` from both callers). Fixing this placeholder is part of this step, not a follow-up — get it right before Step 4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_service.py
git commit -m "feat: add InterviewService start/get_state/answer/list/get"
```

---

## Task 4: `interview.*` MCP tool group (start / get_state / answer / list / get)

**Files:**
- Create: `backend/mcp_server/tools/interview.py`
- Modify: `backend/mcp_server/tool_registry.py` (register tool group, extend `_WRITE_TOOL_PREFIXES`)
- Test: `backend/mcp_server/tests/test_interview_tool_group.py`

**Interfaces:**
- Consumes: `application.interview_service.InterviewService` (Task 3), `mcp_server.tools.base.BaseToolGroup`/`ToolResult`/`require_uuid`/`require_param` (existing, see `mcp_server/tools/needs.py` for the pattern).
- Produces: `mcp_server.tools.interview.InterviewToolGroup` registered under tool names `interview.start`, `interview.get_state`, `interview.answer`, `interview.list`, `interview.get` (grounding/formalize tools land in Tasks 6-7).

- [ ] **Step 1: Write the failing MCP tool test**

Read `backend/mcp_server/tests/test_tool_groups.py` first for the exact test harness helpers this codebase uses (registry construction, `AuthContext` building, how a tool call result is asserted) — do not invent new ones; match the existing style exactly. Then write, in a new file:

```python
# backend/mcp_server/tests/test_interview_tool_group.py
"""interview.* MCP tool group — spec §4."""
from __future__ import annotations

import pytest

# Match imports/fixtures to whatever test_tool_groups.py actually uses for
# registry/ctx construction -- placeholder names below, replace with the
# real helpers before running.
from mcp_server.tool_registry import ToolRegistry
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="MCP Interview Tenant", slug="mcp-interview")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


class TestInterviewStart:
    def test_start_returns_session_id_and_missing_fields(self, tenant, workspace):
        registry = ToolRegistry()
        result = registry.dispatch(
            "interview.start",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            tenant_id=tenant.id,
        )
        assert not result.is_error
        assert "session_id" in result.data
        assert "title" in [f["name"] for f in result.data["missing_fields"]]


class TestInterviewAnswerAndGetState:
    def test_answer_then_get_state_reflects_it(self, tenant, workspace):
        registry = ToolRegistry()
        start = registry.dispatch(
            "interview.start",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            tenant_id=tenant.id,
        )
        session_id = start.data["session_id"]

        registry.dispatch(
            "interview.answer",
            {"session_id": session_id, "field": "title", "value": "SSO login"},
            tenant_id=tenant.id,
        )
        state = registry.dispatch(
            "interview.get_state", {"session_id": session_id}, tenant_id=tenant.id
        )

        assert state.data["collected_fields"]["title"] == "SSO login"


class TestInterviewListAndGet:
    def test_list_returns_started_session(self, tenant, workspace):
        registry = ToolRegistry()
        start = registry.dispatch(
            "interview.start",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            tenant_id=tenant.id,
        )
        listed = registry.dispatch(
            "interview.list", {"workspace_id": str(workspace.id)}, tenant_id=tenant.id
        )
        assert start.data["session_id"] in [s["id"] for s in listed.data["sessions"]]
```

Before running, open `backend/mcp_server/tests/test_tool_groups.py` and rewrite this test's `registry.dispatch(...)`/fixture calls to match that file's ACTUAL API (constructor args, how `AuthContext`/RBAC roles are supplied, the exact shape of a dispatch result) — the sketch above documents intent, not the verified real signature.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest mcp_server/tests/test_interview_tool_group.py -v`
Expected: FAIL (tool `interview.start` not registered / module not found)

- [ ] **Step 3: Implement the tool group**

Follow `backend/mcp_server/tools/needs.py`'s structure exactly (`_TOOL_MAP`, `_TOOL_SCHEMAS`, `BaseToolGroup` subclass, handler methods, `require_uuid`/`require_param` for input validation, `write_mcp_audit` for the three write tools):

```python
# backend/mcp_server/tools/interview.py
"""MCP Tool Group for cross-host structured interviews (spec §4)."""
from __future__ import annotations

from typing import Any, Dict

from application.base import NotFoundError, ValidationError
from application.interview_service import InterviewService
from mcp_server.tools.base import (
    BaseToolGroup,
    ToolResult,
    optional_uuid,
    require_param,
    require_uuid,
    write_mcp_audit,
)


def _session_to_dict(session: Any) -> dict:
    return {
        "id": str(session.id),
        "workspace_id": str(session.workspace_id),
        "artifact_type": session.artifact_type,
        "status": session.status,
    }


class InterviewToolGroup(BaseToolGroup):
    """interview.* tool group."""

    _TOOL_MAP = {
        "interview.start": "_handle_start",
        "interview.get_state": "_handle_get_state",
        "interview.answer": "_handle_answer",
        "interview.list": "_handle_list",
        "interview.get": "_handle_get",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "interview.start",
            "description": "Start a new structured interview for one artifact type.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_type": {"type": "string"},
                    "workspace_id": {"type": "string"},
                },
                "required": ["artifact_type", "workspace_id"],
            },
        },
        {
            "name": "interview.get_state",
            "description": "Fetch the current progress of an interview session.",
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        },
        {
            "name": "interview.answer",
            "description": "Record an answer for one field of the current phase.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "field": {"type": "string"},
                    "value": {},
                },
                "required": ["session_id", "field", "value"],
            },
        },
        {
            "name": "interview.list",
            "description": "List interview sessions in a workspace, optionally filtered by status.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "interview.get",
            "description": "Fetch one interview session by id.",
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        },
    ]

    def _handle_start(self, params: Dict[str, Any], ctx) -> ToolResult:
        artifact_type = require_param(params, "artifact_type")
        workspace_id = require_uuid(params, "workspace_id")
        try:
            session = InterviewService().start(ctx, artifact_type, workspace_id)
        except ValidationError as exc:
            return ToolResult.validation_error(str(exc))
        write_mcp_audit(ctx, "interview.start", str(session.id))
        state = InterviewService().get_state(ctx, session.id)
        return ToolResult.ok({**_session_to_dict(session), **state})

    def _handle_get_state(self, params: Dict[str, Any], ctx) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        try:
            state = InterviewService().get_state(ctx, session_id)
        except NotFoundError as exc:
            return ToolResult.not_found(str(exc))
        return ToolResult.ok(state)

    def _handle_answer(self, params: Dict[str, Any], ctx) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        field = require_param(params, "field")
        value = params.get("value")
        try:
            session = InterviewService().answer(ctx, session_id, field, value)
        except NotFoundError as exc:
            return ToolResult.not_found(str(exc))
        except ValidationError as exc:
            return ToolResult.validation_error(str(exc))
        write_mcp_audit(ctx, "interview.answer", str(session.id))
        return ToolResult.ok(InterviewService().get_state(ctx, session.id))

    def _handle_list(self, params: Dict[str, Any], ctx) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        status = params.get("status")
        sessions = InterviewService().list_sessions(ctx, workspace_id, status=status)
        return ToolResult.ok({"sessions": [_session_to_dict(s) for s in sessions]})

    def _handle_get(self, params: Dict[str, Any], ctx) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        try:
            session = InterviewService().get(ctx, session_id)
        except NotFoundError as exc:
            return ToolResult.not_found(str(exc))
        return ToolResult.ok(_session_to_dict(session))
```

Cross-check every `ToolResult.*`/`require_param`/`require_uuid`/`write_mcp_audit` call above against their real signatures in `backend/mcp_server/tools/base.py` before running — the sketch follows `needs.py`'s usage pattern but must match the actual helper contracts exactly (e.g. `ToolResult.ok` might take positional vs. keyword data, `validation_error` might expect an error code too).

- [ ] **Step 4: Register the tool group and RBAC prefixes**

In `backend/mcp_server/tool_registry.py`: import `InterviewToolGroup` and register it in the same dict/list the other tool groups live in (find where `"needs": StakeholderNeedsToolGroup()` or equivalent is registered and add `"interview": InterviewToolGroup()` alongside it). Add to `_WRITE_TOOL_PREFIXES`:

```python
    "interview.start",
    "interview.answer",
```

(`interview.formalize` is added here too, in Task 7, when it exists.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest mcp_server/tests/test_interview_tool_group.py -v`
Expected: PASS

- [ ] **Step 6: Run the full MCP RBAC matrix test to confirm the new write tools are gated**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest mcp_server/tests/test_mcp_rbac_role_matrix.py -v`
Expected: PASS — if it fails, the matrix likely needs an explicit entry for the two new write tools; check how an existing write tool (e.g. `requirement.create`) is declared there and mirror it.

- [ ] **Step 7: Commit**

```bash
git add backend/mcp_server/tools/interview.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_interview_tool_group.py
git commit -m "feat: add interview.* MCP tool group (start/get_state/answer/list/get)"
```

---

## Task 5: Structural grounding (no AI)

**Files:**
- Modify: `backend/application/interview_service.py` (add `grounding_context`)
- Modify: `backend/mcp_server/tools/interview.py` (add `interview.grounding_context` tool)
- Test: `backend/application/tests/test_interview_service.py`, `backend/mcp_server/tests/test_interview_tool_group.py`

**Interfaces:**
- Consumes: existing read services (`RequirementService.list_requirements`/equivalent per artifact type — check the actual method names in each service file, `needs.py`/`requirement_service.py`/etc., before wiring; do not assume a uniform method name across all 8 services).
- Produces: `InterviewService.grounding_context(self, ctx, session_id: UUID) -> dict` (returns `{"candidates": [{"artifact_id": str, "title": str, "score": float | None}]}`), updates `session.grounding_snapshot`.

- [ ] **Step 1: Write the failing test**

```python
# Add to backend/application/tests/test_interview_service.py
class TestGroundingStructural:
    def test_grounding_finds_existing_requirement_by_title_overlap(self, ctx, workspace):
        from application.requirement_service import RequirementService

        RequirementService().create_requirement(
            ctx, workspace_id=workspace.id, title="SSO login support", description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")

        result = InterviewService().grounding_context(ctx, session.id)

        assert len(result["candidates"]) >= 1
        titles = [c["title"] for c in result["candidates"]]
        assert "SSO login support" in titles

    def test_grounding_with_no_answers_yet_returns_empty_candidates(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        result = InterviewService().grounding_context(ctx, session.id)
        assert result["candidates"] == []
```

Check `RequirementService.create_requirement`'s real signature (`backend/application/requirement_service.py`) before running — adjust kwargs to match.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py -k Grounding -v`
Expected: FAIL with `AttributeError: 'InterviewService' object has no attribute 'grounding_context'`

- [ ] **Step 3: Implement structural grounding**

Add to `backend/application/interview_service.py`. A minimal, honest v1: for `Requirement`, query `RequirementService`'s list/query method filtered by workspace and a simple substring match against any collected text field; for the other 7 artifact types, follow the same shape once their equivalent read services are confirmed (do this for `Requirement` first and get it fully working/tested before generalizing — YAGNI, don't build all 8 branches speculatively in one step):

```python
    def grounding_context(self, ctx, session_id: UUID) -> "dict[str, Any]":
        session = self._get_session(ctx, session_id)
        candidates: "list[dict[str, Any]]" = []

        title = session.collected_fields.get("title")
        if title and session.artifact_type == "Requirement":
            from application.requirement_service import RequirementService

            # Structural pre-filter: substring match on title within the
            # workspace. Cheap, always available, no AI required (spec §6
            # step 1). AI-assisted ranking is layered on top in Task 6.
            matches = RequirementService().list_requirements(  # verify real method name first
                ctx, workspace_id=session.workspace_id
            )
            candidates = [
                {"artifact_id": str(r.artifact_id), "title": r.title, "score": None}
                for r in matches
                if title.lower() in r.title.lower()
            ]

        session.grounding_snapshot = {"candidates": candidates}
        session.save(update_fields=["grounding_snapshot", "modified_at", "version"])
        return session.grounding_snapshot
```

Before finalizing, open `backend/application/requirement_service.py` and confirm the actual list/query method name and its return shape (does it return ORM objects with `.artifact_id`/`.title`, or dicts?) — adjust the comprehension to match reality rather than the guess above.

- [ ] **Step 4: Add the MCP tool**

In `backend/mcp_server/tools/interview.py`, add `"interview.grounding_context": "_handle_grounding_context"` to `_TOOL_MAP`, a matching schema entry (`session_id` required), and:

```python
    def _handle_grounding_context(self, params: Dict[str, Any], ctx) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        try:
            result = InterviewService().grounding_context(ctx, session_id)
        except NotFoundError as exc:
            return ToolResult.not_found(str(exc))
        return ToolResult.ok(result)
```

(Not added to `_WRITE_TOOL_PREFIXES` — it's a read-shaped side effect on the session's own cache, not a create/update of a real artifact; matches the spec's framing of grounding as advisory.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py mcp_server/tests/test_interview_tool_group.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/application/interview_service.py backend/mcp_server/tools/interview.py backend/application/tests/test_interview_service.py
git commit -m "feat: add structural grounding for Requirement interviews"
```

---

## Task 6: AI-assisted grounding (`suggest_related_artifacts`)

**Files:**
- Modify: `backend/application/interview_service.py` (call the AI layer, fail-open)
- Test: `backend/application/tests/test_interview_service.py`

**Interfaces:**
- Consumes: same free-form-completion pattern as `BundleCompressionService._resolve_provider`/`_call_provider` (`backend/application/bundle_compression_service.py:489-580`ish — read it in full before writing this task's code, it is the template).
- Produces: `InterviewService._resolve_provider()` / `InterviewService._call_grounding_provider(...)` (private, mirrors `BundleCompressionService`'s naming), extends `grounding_context`'s `candidates` with an LLM-ranked `score` when a real provider is configured.

- [ ] **Step 1: Write the failing test**

```python
# Add to backend/application/tests/test_interview_service.py
from unittest.mock import MagicMock, patch


class TestGroundingAiAssisted:
    def test_mock_provider_still_returns_structural_candidates(self, ctx, workspace):
        """Fail-open: no real provider configured -> structural results only,
        never blocks (spec §6)."""
        from application.requirement_service import RequirementService

        RequirementService().create_requirement(
            ctx, workspace_id=workspace.id, title="SSO login support", description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")

        result = InterviewService().grounding_context(ctx, session.id)

        assert len(result["candidates"]) >= 1

    def test_provider_failure_does_not_raise(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "anything")

        with patch(
            "application.interview_service.InterviewService._resolve_provider",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise -- fail-open per spec §6.
            result = InterviewService().grounding_context(ctx, session.id)

        assert "candidates" in result
```

- [ ] **Step 2: Run test to verify it fails on the new assertion**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py -k GroundingAiAssisted -v`
Expected: `test_provider_failure_does_not_raise` FAILs (raises, since nothing catches the patched exception yet); `test_mock_provider_still_returns_structural_candidates` may already pass (structural grounding from Task 5 doesn't touch the provider at all yet) — that's fine, the point of this task is adding the AI layer on top without breaking the fail-open guarantee.

- [ ] **Step 3: Add the AI-assisted layer, wrapped so any failure degrades to structural-only**

Read `backend/application/bundle_compression_service.py`'s `_resolve_provider`/`_call_provider` (lines ~489-580) in full first — this step ports that exact pattern (token-budget check, audit logging, mock-fallback marker convention), not a new one. Then:

```python
    def _resolve_provider(self):
        """Mirrors BundleCompressionService._resolve_provider -- see that
        method's docstring for why resolution is split from the call."""
        from llm_adapter.providers import get_provider, resolve_provider_config

        try:
            config = resolve_provider_config()
            provider = get_provider(config)
            return provider, getattr(provider, "PROVIDER_NAME", config.provider_name or "unknown"), None
        except Exception as exc:  # noqa: BLE001 -- fail-open, see grounding_context
            return None, "unknown", exc

    def grounding_context(self, ctx, session_id: UUID) -> "dict[str, Any]":
        session = self._get_session(ctx, session_id)
        candidates = self._structural_candidates(session)  # extracted from Task 5's inline code

        try:
            provider, provider_name, resolve_error = self._resolve_provider()
            if provider is not None and candidates:
                candidates = self._rank_candidates_with_ai(
                    ctx, session, candidates, provider, provider_name
                )
        except Exception:  # noqa: BLE001 -- grounding must never block the interview (spec §6)
            logger.warning(
                "InterviewService: AI-assisted grounding failed for session=%s, "
                "falling back to structural-only candidates", session_id, exc_info=True
            )

        session.grounding_snapshot = {"candidates": candidates}
        session.save(update_fields=["grounding_snapshot", "modified_at", "version"])
        return session.grounding_snapshot
```

Refactor Task 5's inline structural-matching code into a `_structural_candidates(self, session) -> list[dict]` helper (same logic, just extracted so this step can call it before the AI layer). Implement `_rank_candidates_with_ai` following `BundleCompressionService._call_provider`'s exact audit/token-tracking/mock-marker steps, adapted to a ranking prompt instead of a compression prompt — write this prompt as a new `PROMPT_TEMPLATE_DEFAULTS` entry (name `"interview.grounding_rank"`) in `ai_derivation_service.py`, following the same registration pattern as `BUNDLE_COMPRESSION_PROMPT_TEMPLATE`.

Add `import logging; logger = logging.getLogger(__name__)` at the top of `interview_service.py` if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py -v`
Expected: PASS (all tests in this file)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/ai_derivation_service.py backend/application/tests/test_interview_service.py
git commit -m "feat: add AI-assisted grounding ranking, fail-open"
```

---

## Task 7: Formalization logic + `interview.formalize`

**Files:**
- Modify: `backend/application/interview_service.py` (add `formalize`)
- Modify: `backend/mcp_server/tools/interview.py` (add `interview.formalize` tool, add to `_WRITE_TOOL_PREFIXES`)
- Test: `backend/application/tests/test_interview_service.py`, `backend/mcp_server/tests/test_interview_tool_group.py`

**Interfaces:**
- Consumes: `RequirementService.create_requirement`/update method (confirm exact names before wiring — Requirement is the only artifact type this task implements end-to-end; the other 7 follow the identical pattern in a later, separate pass once this one is proven, per YAGNI — do not speculatively stub all 8 in this task).
- Produces: `InterviewService.formalize(self, ctx, session_id: UUID) -> dict` (returns `{"resulting_artifact_ids": [...], "status": "completed"}`).

- [ ] **Step 1: Write the failing test**

```python
# Add to backend/application/tests/test_interview_service.py
class TestFormalize:
    def test_formalize_with_no_target_creates_new_requirement(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")
        InterviewService().answer(ctx, session.id, "rationale", "Reduce password fatigue")

        result = InterviewService().formalize(ctx, session.id)

        assert len(result["resulting_artifact_ids"]) == 1
        assert result["status"] == "completed"

        from persistence.models import InterviewSession

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            refreshed = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert refreshed.status == InterviewSession.STATUS_COMPLETED

    def test_formalize_with_target_updates_existing_requirement(self, ctx, workspace):
        from application.requirement_service import RequirementService

        existing = RequirementService().create_requirement(
            ctx, workspace_id=workspace.id, title="Old title", description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "New title")

        from persistence.models import InterviewSession

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                target_artifact_id=existing.artifact_id
            )
        finally:
            TenantContext.clear_tenant()

        result = InterviewService().formalize(ctx, session.id)

        updated = RequirementService().get_requirement(ctx, existing.id)  # verify real method name
        assert updated.title == "New title"
        assert str(existing.artifact_id) in result["resulting_artifact_ids"] or len(result["resulting_artifact_ids"]) == 1

    def test_formalize_reraises_if_target_artifact_deleted_mid_session(self, ctx, workspace):
        """spec §5 point 4 / §9: re-check existence at write time."""
        from application.requirement_service import RequirementService
        from persistence.models import Artifact, InterviewSession

        existing = RequirementService().create_requirement(
            ctx, workspace_id=workspace.id, title="Will be deleted", description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "New title")

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                target_artifact_id=existing.artifact_id
            )
            Artifact.objects.filter(id=existing.artifact_id).delete()
        finally:
            TenantContext.clear_tenant()

        with pytest.raises(NotFoundError):
            InterviewService().formalize(ctx, session.id)
```

Confirm `RequirementService.create_requirement`'s return value (does it expose `.artifact_id`?), `get_requirement`'s real name, and the update method's real name/signature in `backend/application/requirement_service.py` before running — adjust all three tests to match reality.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py -k Formalize -v`
Expected: FAIL with `AttributeError: 'InterviewService' object has no attribute 'formalize'`

- [ ] **Step 3: Implement `formalize`**

```python
    def formalize(self, ctx, session_id: UUID) -> "dict[str, Any]":
        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(f"InterviewSession {session_id} is {session.status}, cannot formalize.")

        resulting_ids: "list[str]" = []

        if session.artifact_type == "Requirement":
            from application.requirement_service import RequirementService

            svc = RequirementService()
            if session.target_artifact_id is not None:
                # Re-check existence at write time (spec §9) -- grounding may
                # be stale, the target may have been deleted since.
                target = svc.get_requirement(ctx, session.target_artifact_id)  # verify real method name
                if target is None:
                    raise NotFoundError(
                        f"Target artifact {session.target_artifact_id} no longer exists; "
                        "cannot formalize an update against it."
                    )
                svc.update_requirement(  # verify real method name/signature
                    ctx,
                    requirement_id=target.id,
                    title=session.collected_fields.get("title", target.title),
                    description=session.collected_fields.get("rationale", target.description),
                )
                resulting_ids.append(str(session.target_artifact_id))
            else:
                created = svc.create_requirement(
                    ctx,
                    workspace_id=session.workspace_id,
                    title=session.collected_fields.get("title", ""),
                    description=session.collected_fields.get("rationale", ""),
                )
                resulting_ids.append(str(created.artifact_id))
        else:
            raise ValidationError(
                f"formalize() for artifact_type={session.artifact_type!r} is not implemented yet "
                "-- only Requirement is wired in this plan; the other 7 types follow the "
                "identical pattern in a later pass."
            )

        session.resulting_artifact_ids = resulting_ids
        session.status = InterviewSession.STATUS_COMPLETED
        session.save(update_fields=["resulting_artifact_ids", "status", "modified_at", "version"])
        return {"resulting_artifact_ids": resulting_ids, "status": session.status}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest application/tests/test_interview_service.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Add the MCP tool**

In `backend/mcp_server/tools/interview.py`: add `"interview.formalize": "_handle_formalize"` to `_TOOL_MAP`, a schema entry (`session_id` required), and:

```python
    def _handle_formalize(self, params: Dict[str, Any], ctx) -> ToolResult:
        session_id = require_uuid(params, "session_id")
        try:
            result = InterviewService().formalize(ctx, session_id)
        except NotFoundError as exc:
            return ToolResult.not_found(str(exc))
        except ValidationError as exc:
            return ToolResult.validation_error(str(exc))
        write_mcp_audit(ctx, "interview.formalize", session_id)
        return ToolResult.ok(result)
```

Add `"interview.formalize"` to `_WRITE_TOOL_PREFIXES` in `backend/mcp_server/tool_registry.py` (Task 4's Step 4 left a comment marking this spot).

- [ ] **Step 6: Write + run the MCP-level formalize test**

```python
# Add to backend/mcp_server/tests/test_interview_tool_group.py
class TestInterviewFormalize:
    def test_formalize_creates_requirement_and_completes_session(self, tenant, workspace):
        registry = ToolRegistry()
        start = registry.dispatch(
            "interview.start",
            {"artifact_type": "Requirement", "workspace_id": str(workspace.id)},
            tenant_id=tenant.id,
        )
        session_id = start.data["session_id"]
        registry.dispatch(
            "interview.answer",
            {"session_id": session_id, "field": "title", "value": "SSO login"},
            tenant_id=tenant.id,
        )

        result = registry.dispatch("interview.formalize", {"session_id": session_id}, tenant_id=tenant.id)

        assert not result.is_error
        assert result.data["status"] == "completed"
        assert len(result.data["resulting_artifact_ids"]) == 1
```

Run: `docker exec -e DJANGO_SETTINGS_MODULE=reqogniloom.settings_test -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 python -m pytest mcp_server/tests/test_interview_tool_group.py mcp_server/tests/test_mcp_rbac_role_matrix.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/application/interview_service.py backend/mcp_server/tools/interview.py backend/mcp_server/tool_registry.py backend/application/tests/test_interview_service.py backend/mcp_server/tests/test_interview_tool_group.py
git commit -m "feat: add interview.formalize (Requirement create/update)"
```

---

## Task 8: Host packaging — new interview-management skill

**Files:**
- Create: `dist/agent-skills/interview-management/SKILL.md`
- Modify: `dist/opencode/build_opencode_package.py` (add to `SKILL_NAMES`)
- Modify: `dist/plugins/antigravity/build_antigravity_plugin.py` (add to `SKILL_NAMES`)
- Test: `dist/opencode/test_build_opencode_package.py`, `dist/plugins/antigravity/test_build_antigravity_plugin.py` (extend existing assertions)

**Interfaces:**
- Consumes: `interview.*` MCP tool group (Tasks 4-7), already reachable by any host once deployed — this task only adds the skill *content* that instructs a host agent to use those tools.
- Produces: `dist/agent-skills/interview-management/SKILL.md`, present in `SKILL_NAMES` in both build scripts (spec §7).

- [ ] **Step 1: Write the failing build-script test assertion**

Add to `dist/opencode/test_build_opencode_package.py`'s existing `test_build_opencode_package` test (inside the `for skill_name in [...]` loop's list):

```python
    for skill_name in [
        "vmodell-decomposition", "test-lifecycle", "risk-derivation",
        "ccb-approval-and-baseline", "traceability-audit",
        "interview-management",
    ]:
        assert (tmp_path / "skills" / skill_name / "SKILL.md").exists()
```

Do the equivalent in `dist/plugins/antigravity/test_build_antigravity_plugin.py` — read that file first to match its actual assertion style (it may check a different path shape than the Opencode test).

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec reqogniloom-backend-1 sh -c 'cd /app/.. && pytest dist -v'` (adjust working directory to wherever `dist/` actually resolves inside the container — confirm with `docker exec reqogniloom-backend-1 find / -maxdepth 2 -name dist -type d` if unsure, since `dist/` lives at the repo root, not under `backend/`)
Expected: FAIL — `interview-management` SKILL.md not found

- [ ] **Step 3: Write the skill content**

```markdown
<!-- dist/agent-skills/interview-management/SKILL.md -->
---
name: interview-management
description: Conduct a structured interview to create, improve, or adjust a ReqogniLoom artifact (Requirement, ArchitectureElement, StakeholderNeed, Risk, TestCase, Adr, Issue, or Goal), backed by the interview.* MCP tools.
---

# Interview Management

Use this skill when the user wants to create, refine, or adjust a
ReqogniLoom artifact through a guided conversation, rather than
specifying every field up front.

## How it works

The actual question wording and progress live on the ReqogniLoom server,
not in this file — that's what makes the same interview consistent
across Claude Code, Opencode, and Antigravity. Your job is to run the
conversation naturally, but treat the server as the single source of
truth for state:

1. Call `interview.start(artifact_type, workspace_id)` to begin. It
   returns a `session_id` and the first phase's missing fields.
2. Call `interview.get_state(session_id)` whenever you need to know
   what's still open — including if you're resuming a session someone
   started on a different host. Never assume your own chat history is
   the source of truth for what's been answered.
3. As the user answers, call `interview.answer(session_id, field, value)`
   for each field you can confidently extract. If an answer is
   ambiguous, ask a clarifying question instead of guessing — do not
   record a value you are not confident about.
4. Optionally call `interview.grounding_context(session_id)` to check
   for existing artifacts that might already cover what the user is
   describing, and mention any close matches to the user before
   proceeding — this may avoid creating a duplicate.
5. Once every required field for every phase is answered (`get_state`
   returns an empty `missing_fields` for the final phase), call
   `interview.formalize(session_id)` to create or update the real
   artifact(s). Report the resulting artifact id(s) to the user.

## Scope

Available for: Requirement, ArchitectureElement, StakeholderNeed, Risk,
TestCase, Adr, Issue, Goal. NOT available for MainGoal (read-only,
intentionally out of scope).
```

- [ ] **Step 4: Register the skill in both build scripts**

In `dist/opencode/build_opencode_package.py`, change:

```python
SKILL_NAMES = [
    "vmodell-decomposition", "test-lifecycle", "risk-derivation",
    "ccb-approval-and-baseline", "traceability-audit",
]
```

to:

```python
SKILL_NAMES = [
    "vmodell-decomposition", "test-lifecycle", "risk-derivation",
    "ccb-approval-and-baseline", "traceability-audit",
    "interview-management",
]
```

Make the equivalent change in `dist/plugins/antigravity/build_antigravity_plugin.py` — read its current `SKILL_NAMES` (or equivalent list) first, it may be structured slightly differently.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec reqogniloom-backend-1 sh -c 'cd /app/.. && pytest dist -v'`
Expected: PASS

- [ ] **Step 6: Regenerate the committed `dist/` output**

The build scripts produce output that a separate CI job (Task 9) will now check for freshness — run them for real and commit the result, don't leave `dist/plugins/*`/`dist/opencode/*` stale (this is exactly the class of bug that caused commit `c49a503`):

```bash
docker exec reqogniloom-backend-1 sh -c 'cd /app/.. && python dist/opencode/build_opencode_package.py --out dist/opencode'
docker exec reqogniloom-backend-1 sh -c 'cd /app/.. && python dist/plugins/antigravity/build_antigravity_plugin.py --out dist/plugins/antigravity'
```

(Check both scripts' actual `--out`/default-output-path convention first — `build_opencode_package.py`'s `build(out_dir, skills_src)` signature seen earlier suggests it may write in-place by default rather than needing `--out` pointed back at the committed path; confirm before running so this step doesn't silently write to a throwaway temp dir instead of updating the committed tree.)

Check `git status` afterward and stage whatever the build actually changed (e.g. `dist/opencode/skills/interview-management/`, `dist/plugins/antigravity/reqogniloom/skills/interview-management/`).

- [ ] **Step 7: Commit**

```bash
git add dist/
git commit -m "feat: package interview-management skill for Opencode and Antigravity"
```

---

## Task 9: CI freshness check (closes the c49a503 gap)

**Files:**
- Create: `dist/test_dist_freshness.py`
- Test: (this task's file IS the test)

**Interfaces:**
- Consumes: `dist/opencode/build_opencode_package.py`'s `build()` function, `dist/plugins/antigravity/build_antigravity_plugin.py`'s equivalent, both confirmed present from Task 8.
- Produces: a new pytest test that CI already collects (the existing `agent-templates-test` job in `.github/workflows/ci.yml` runs `pytest docs/agent-templates dist` — this file lands under `dist/` and needs no new CI job).

- [ ] **Step 1: Write the freshness test**

```python
# dist/test_dist_freshness.py
"""CI freshness check for dist/ build output (Interview-Management-Engine spec §8).

Closes the gap that let commit c49a503 happen: nothing previously ran
the build scripts in CI or checked their output against the committed
dist/ tree, so a version bump silently left dist/plugins/*/plugin.json
stamped with the old version until someone noticed by hand. This test
regenerates both packages into a temp dir and diffs them against what's
actually committed -- any drift fails CI.
"""
from __future__ import annotations

import filecmp
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _diff_dirs(committed: Path, regenerated: Path) -> list[str]:
    """Return a list of human-readable diffs; empty means identical."""
    problems: list[str] = []
    comparison = filecmp.dircmp(committed, regenerated)
    if comparison.left_only:
        problems.append(f"Committed but not regenerated (stale/removed source?): {comparison.left_only}")
    if comparison.right_only:
        problems.append(f"Regenerated but not committed (forgot to commit?): {comparison.right_only}")
    if comparison.diff_files:
        problems.append(f"Content differs, re-run the build script and commit: {comparison.diff_files}")
    for sub in comparison.common_dirs:
        problems.extend(_diff_dirs(committed / sub, regenerated / sub))
    return problems


def test_opencode_package_is_fresh(tmp_path):
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "dist" / "opencode" / "build_opencode_package.py"),
         "--out", str(tmp_path)],
        check=True, cwd=REPO_ROOT,
    )
    problems = _diff_dirs(REPO_ROOT / "dist" / "opencode", tmp_path)
    assert not problems, (
        "dist/opencode/ is stale relative to dist/agent-skills/. "
        "Re-run dist/opencode/build_opencode_package.py and commit the output.\n"
        + "\n".join(problems)
    )


def test_antigravity_package_is_fresh(tmp_path):
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "dist" / "plugins" / "antigravity" / "build_antigravity_plugin.py"),
         "--out", str(tmp_path)],
        check=True, cwd=REPO_ROOT,
    )
    problems = _diff_dirs(REPO_ROOT / "dist" / "plugins" / "antigravity", tmp_path)
    assert not problems, (
        "dist/plugins/antigravity/ is stale relative to dist/agent-skills/. "
        "Re-run dist/plugins/antigravity/build_antigravity_plugin.py and commit the output.\n"
        + "\n".join(problems)
    )
```

Confirm `build_antigravity_plugin.py` accepts the same `--out` flag shape as the Opencode one (read its `argparse` setup) — adjust the subprocess call if its CLI differs.

- [ ] **Step 2: Run the test to verify it passes on the freshly-regenerated Task 8 output**

Run: `docker exec reqogniloom-backend-1 sh -c 'cd /app/.. && pytest dist/test_dist_freshness.py -v'`
Expected: PASS (Task 8 Step 6 already regenerated and committed the output, so there should be no drift right now)

- [ ] **Step 3: Prove the test actually catches drift**

Manually edit one committed file (e.g. append a stray character to `dist/plugins/antigravity/reqogniloom/plugin.json`), re-run the test, confirm it FAILS with a clear message naming that file, then revert the manual edit (`git checkout -- dist/plugins/antigravity/reqogniloom/plugin.json`) before continuing. This is a manual verification step, not a permanent test — do not leave the corrupted file committed.

- [ ] **Step 4: Confirm CI already collects this file**

Read `.github/workflows/ci.yml`'s `agent-templates-test` job (`pytest docs/agent-templates dist`) — `dist/test_dist_freshness.py` is picked up automatically by that existing `pytest dist` invocation. No workflow file changes needed for this task.

- [ ] **Step 5: Commit**

```bash
git add dist/test_dist_freshness.py
git commit -m "test: add CI freshness check for dist/ build output"
```

---

## Self-Review Notes (for whoever executes this plan)

- **Task 7 formalize only implements `Requirement`.** The other 7 artifact types (`ArchitectureElement`, `StakeholderNeed`, `Risk`, `TestCase`, `Adr`, `Issue`, `Goal`) raise `ValidationError` until extended — this is a deliberate, stated scope cut (YAGNI: prove the pattern once, end-to-end, tested, before repeating it seven times), not an oversight. A follow-up plan should extend Task 7's `if session.artifact_type == "Requirement": ... else: ...` into one branch per type, each following the identical create-or-update-via-existing-service shape.
- **The spec's "Offene Frage für den Implementierungsplan" (YAML validation timing, spec §3.1) is answered by Task 2 Step 6** — validated on the `prompt_template.create`/`.update` write path, not deferred to `interview.start`.
- Every task that touches an existing service (`RequirementService`, `AiDerivationService._get_template_content`, `mcp_server/tools/base.py` helpers) includes an explicit instruction to verify the real method signature before writing code against it — this codebase's actual method names were not fully confirmed for every call site while writing this plan (only `RequirementService` and `AiDerivationService._get_template_content`'s existence were checked directly); do not skip those verification sub-steps.
