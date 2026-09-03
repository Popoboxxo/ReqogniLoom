# Interview-Engine-Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four Interview-Engine gaps from the 2026-09-02 audit (L2.1 single-kind formalize is Requirement-only, L2.3 provenance invisible, L2.4 unbounded transcript, L2.5 two parallel chat UIs) by re-using mechanisms that already exist in the codebase.

**Architecture:** `InterviewService._formalize_single()` stops hardcoding `Requirement` and dispatches through the same `ARTIFACT_CREATION_ADAPTERS` registry the multi-kind path has used in production since the multi-artifact plan; the artifact id it returns is mapped back to the user-facing domain-entity id via the existing `traceability.service.resolve_artifacts()` bridge so the response contract of issue #736 is preserved for all eight types. The transcript gets a `transcript_summary` column plus a best-effort LLM compression step that folds overflow turns into it, injected into the *existing* `{transcript_json}` prompt variable (no new placeholder, so tenant prompt overrides keep working). The floating widget is demoted to a launcher that redirects to `/interviews/{id}`; the chat/artifact panes it renders today stay where they are because `/interviews` already imports them.

**Tech Stack:** Python 3.x / Django 5.2 / DRF / pytest · React 18 / TypeScript 5.5 strict / vitest / react-i18next / react-router-dom

**Spec:** docs/superpowers/specs/2026-09-03-interview-engine-fix-design.md

## Global Constraints

- The spec file lives on `main`; the branch this plan was written on had archived it. Read it via `git show main:docs/superpowers/specs/2026-09-03-interview-engine-fix-design.md` if it is absent from the working tree.
- Branch policy: work on `fix/interview-engine-l2` — never commit directly to `main`.
- Conventional Commits, English commit messages, max 72 chars in the subject line.
- Every DRF view keeps its `TenantContext` discipline; no new ORM access in `rest_api/` (the `test_architecture.py` ratchet forbids model imports in `interview_views.py` — use the literal `"multi"`, as that file already does).
- No new prompt placeholder in `interview.chat_turn`: workspace/tenant overrides of that slot predate this change and would silently drop an unknown variable.
- Transcript window is a fixed constant, not a config value: `TRANSCRIPT_WINDOW_ENTRIES = 20` (= 10 user/assistant turn pairs, the spec's "gleitendes Fenster von 10 Turns").
- Transcript compression is a best-effort LLM call: on provider failure nothing is truncated and nothing is summarized — the next turn retries (spec §7: "kein Datenverlust, nur verzögerte Kompression").
- `GlossaryTerm` stays rejected (Task 15 is blocked): it still has no `artifact` FK (`backend/persistence/models.py:1833`), confirmed 2026-09-03.
- Do not touch `docs/superpowers/plans/index.md`.
- Backend targeted test command (memory: concurrent runs collide on the shared `test_reqogniloom` DB):
  `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest <path> -v`
- Frontend targeted test command:
  `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run <path>"`
- After any frontend source edit, restart the frontend container before any browser/E2E check — Vite has no working HMR on Windows in this stack.
- Do NOT run the full Playwright suite. It is not a DoD gate here.

---

## Spec deviations decided while planning (all verified against current code)

1. **`_formalize_single` keeps its update branch Requirement-only.** `set_target()` (`interview_service.py:756`) already rejects non-Requirement targets, so `target_artifact_id` can only ever hold a Requirement. Generalizing the update branch would need per-type `update_X()` mapping that the spec does not ask for. Task 5 adds an explicit guard + honest error instead of leaving it implicit.
2. **`resulting_artifact_ids` keeps carrying the domain-entity id, not the Artifact id.** Issue #736 deliberately made it the entity id; `CreatedArtifactRef` only carries `artifact_id`. Rather than changing the adapter contract in 9 places, Task 2 resolves it back through `traceability.service.resolve_artifacts()`, which already covers all nine Artifact-backed types.
3. **The default protocol must be extended for `Risk` (Task 3).** `_default_protocol_yaml()` elicits only `title` + `rationale` for every type, but `RiskService.create_risk()` requires `probability` and `impact` with no defaults. Without Task 3, L2.1 "works" in a unit test that seeds `collected_fields` directly and still fails in the real interview. `Adr.description` (also required, no default) is covered by the `rationale → description` mapping in Task 1.
4. **The badge goes into the artifact detail panel, not the `PageHeader`.** The spec says "in jeden Artefakt-Editor-`PageHeader`", but `PageHeader` in these routes is page-level (title = "Risks", one `<h1>`, the list's summary), while provenance is a property of the *selected* artifact. It is mounted next to the existing `<TraceSpine>` block, which is already per-artifact and structurally identical across all eight editors.
5. **`InterviewChatPane` / `InterviewArtifactPane` are NOT deleted.** The spec says the widget's 206-line chat pane "entfällt ersatzlos" — but `components/InterviewEditors/InterviewDetail.tsx:20-21` imports both from `InterviewWidget/`. Deleting them would break exactly the surface the spec wants to keep. Task 14 only stops the *widget* from rendering them.
6. **"Per Interview erstellen" needs no change.** The spec asks for a header CTA that pre-selects the current page's type; `components/shared/useInterviewStartCta.ts` already navigates to `/interviews?start=<Type>`, and `InterviewEditors` auto-starts and redirects to `/interviews/{id}`. That is the spec's intent, already shipped, and better than routing through the widget. No task.
7. **`session_kind` is added to `get_state()` (Task 12).** Redirecting *multi* sessions to `/interviews/{id}` (Task 14) crashes `InterviewDetail` today: `get_state()` omits `missing_fields` for multi sessions and the component reads `current.missing_fields.length` unguarded. The frontend currently *guesses* the kind from local start-time state. One backend field removes the guess.

## OFFENE FRAGE (blocking nothing in this plan, needs a product answer before Task 15)

None blocking. Task 15 (GlossaryTerm adapter) is blocked on an external precondition, not on an open question: `docs/superpowers/specs/2026-09-03-datenmodell-konsolidierung-design.md` §4 must first give `GlossaryTerm` an `artifact` OneToOne FK. Verified 2026-09-03: not implemented (`persistence/models.py:1833` has no `artifact` field).

---

## File Structure

```
backend/
  application/
    interview_service.py                      # MODIFY — Tasks 1,2,4,5,7,9,12
    interview_protocol.py                     # MODIFY — Task 3
    ai_derivation_service.py                  # MODIFY — Task 8
    prompt_slots.py                           # MODIFY — Task 8
    tests/
      test_interview_formalize_single_types.py  # CREATE — Tasks 1,2,4,5
      test_interview_protocol.py              # MODIFY — Task 3
      test_interview_transcript_cap.py        # CREATE — Tasks 7,9
  persistence/
    models.py                                 # MODIFY — Task 6
    migrations/0070_interviewsession_transcript_summary.py  # CREATE — Task 6
  rest_api/
    interview_views.py                        # MODIFY — Task 12
  mcp_server/tools/interview.py               # MODIFY — Task 5 (descriptions only)

frontend/src/
  api/interviews.ts                           # MODIFY — Task 12
  components/
    shared/InterviewProvenanceBadge.tsx       # MODIFY — Task 10
    shared/InterviewProvenanceBadge.test.tsx  # MODIFY — Task 10
    RiskEditors/RiskEditors.tsx               # MODIFY — Task 11
    AdrEditors/AdrEditors.tsx                 # MODIFY — Task 11
    IssueEditors/IssueEditors.tsx             # MODIFY — Task 11
    NeedsEditors/NeedsEditors.tsx             # MODIFY — Task 11
    RequirementEditors/RequirementEditors.tsx # MODIFY — Task 11
    ArchitectureEditors/ArchitectureEditors.tsx # MODIFY — Task 11
    TestCaseEditors/TestCaseEditors.tsx       # MODIFY — Task 11
    Goals/GoalDetail.tsx                      # MODIFY — Task 11
    InterviewEditors/InterviewDetail.tsx      # MODIFY — Task 13
    InterviewEditors/InterviewEditors.test.tsx # MODIFY — Task 13
    InterviewWidget/InterviewWidget.tsx       # MODIFY — Task 14
    InterviewWidget/InterviewWidget.test.tsx  # MODIFY — Task 14
  test/RiskEditors.test.tsx                   # MODIFY — Task 11
```

---

## Task 1: `collected_fields` → `create_X()` kwargs mapping

**Files:**
- Modify: `backend/application/interview_service.py` (module level, after `_DIAGRAM_REF_LINK_TYPE` at line 46)
- Test: `backend/application/tests/test_interview_formalize_single_types.py`

**Interfaces:**
- Produces: `_adapter_fields_from_collected(collected_fields: dict[str, Any]) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_interview_formalize_single_types.py`:

```python
"""InterviewService._formalize_single() for all 8 in-scope artifact types.

Audit finding L2.1: the single-kind formalize path used to hardcode
``if session.artifact_type != "Requirement": raise ValidationError`` --
an interview for Risk/Adr/TestCase/... was startable and answerable but
never completable. It now dispatches through the same
ARTIFACT_CREATION_ADAPTERS registry the multi-kind path already uses.

Fixture style mirrors test_interview_formalize_multi.py (local fixtures,
no factories.py): TenantContext.set_tenant/clear_tenant in try/finally
plus an inline AuthContext.
"""
from __future__ import annotations

from application.interview_service import _adapter_fields_from_collected


class TestAdapterFieldsFromCollected:
    def test_rationale_becomes_description(self):
        fields = _adapter_fields_from_collected({"title": "T", "rationale": "Because"})
        assert fields == {"title": "T", "description": "Because"}

    def test_explicit_description_wins_over_rationale(self):
        fields = _adapter_fields_from_collected(
            {"title": "T", "rationale": "R", "description": "D"}
        )
        assert fields == {"title": "T", "description": "D"}

    def test_other_fields_pass_through_unchanged(self):
        fields = _adapter_fields_from_collected(
            {"title": "T", "probability": "low", "impact": "high"}
        )
        assert fields == {"title": "T", "probability": "low", "impact": "high"}

    def test_empty_collected_fields_stay_empty(self):
        assert _adapter_fields_from_collected({}) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_formalize_single_types.py -v`
Expected: FAIL — `ImportError: cannot import name '_adapter_fields_from_collected' from 'application.interview_service'`

- [ ] **Step 3: Write minimal implementation**

In `backend/application/interview_service.py`, directly below the `_DIAGRAM_REF_LINK_TYPE` constant (line 46):

```python
# Protocol field name the factory-default protocol elicits for every type
# (interview_protocol._default_protocol_yaml). No create_X() service
# signature accepts a "rationale" kwarg -- they all take "description" --
# so the single-kind formalize path translates it. Kept as one named
# constant because both the mapper below and its tests refer to it.
_RATIONALE_FIELD = "rationale"


def _adapter_fields_from_collected(collected_fields: "dict[str, Any]") -> "dict[str, Any]":
    """Map a single-kind session's collected answers onto create_X() kwargs.

    Every field the protocol collected is passed through unchanged (so a
    workspace that extended its protocol with e.g. ``category`` or
    ``severity`` reaches the service kwarg of the same name), with exactly
    one rename: ``rationale`` -> ``description``, matching what
    ``_formalize_single`` did by hand for Requirement before L2.1. An
    explicitly collected ``description`` wins -- a protocol that declares
    both means both, and the rename must not clobber the more specific one.
    """
    fields = {k: v for k, v in collected_fields.items() if k != _RATIONALE_FIELD}
    rationale = collected_fields.get(_RATIONALE_FIELD)
    if rationale is not None and "description" not in fields:
        fields["description"] = rationale
    return fields
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_formalize_single_types.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_formalize_single_types.py
git commit -m "feat(interview): map collected protocol fields to create_X kwargs"
```

---

## Task 2: Generic adapter dispatch in `_formalize_single`

**Files:**
- Modify: `backend/application/interview_service.py:839-844` (delete the hardcoded guard), `:909-918` (replace the create branch)
- Test: `backend/application/tests/test_interview_formalize_single_types.py`

**Interfaces:**
- Consumes: `_adapter_fields_from_collected(collected_fields: dict) -> dict` (Task 1); `ARTIFACT_CREATION_ADAPTERS: Dict[str, Callable[[dict, AuthContext, Any], CreatedArtifactRef]]` (`application/interview_artifact_adapters.py:119`); `CreatedArtifactRef(artifact_id: UUID, artifact_type: str)`; `traceability.service.resolve_artifacts(artifact_ids: list[uuid.UUID | str], tenant_id: uuid.UUID) -> list[ResolvedArtifact]` with `ResolvedArtifact(artifact_id: str, resolved: bool, entity_type: str | None, entity_id: str | None)`
- Produces: `InterviewService._entity_id_for(ctx, ref: CreatedArtifactRef) -> str`

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_formalize_single_types.py` (imports go at the top of the file, next to the existing one):

```python
import contextlib
from typing import Iterator

import pytest

from application.base import ValidationError
from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    Adr,
    InterviewSession,
    Issue,
    Risk,
    Tenant,
    TestCase,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


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
    return Tenant.objects.create(name="IV-Single Tenant", slug="iv-single-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="IV-Single-WS")


@pytest.fixture
def editor_ctx(tenant: Tenant) -> AuthContext:
    user = User.objects.create(
        username="iv-single-editor", email="single@example.com", tenant=tenant
    )
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _single_session(
    tenant: Tenant, ws: Workspace, artifact_type: str, collected: dict
) -> InterviewSession:
    with _active(tenant):
        return InterviewSession.objects.create(
            tenant=tenant,
            workspace=ws,
            artifact_type=artifact_type,
            session_kind=InterviewSession.SESSION_KIND_SINGLE,
            status=InterviewSession.STATUS_IN_PROGRESS,
            collected_fields=collected,
        )


class TestFormalizeSingleAllTypes:
    def test_risk_session_creates_a_real_risk(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        session = _single_session(
            tenant,
            workspace,
            "Risk",
            {
                "title": "Vendor outage",
                "rationale": "Single supplier",
                "probability": "high",
                "impact": "high",
            },
        )

        result = InterviewService().formalize(editor_ctx, session.id)

        assert result["status"] == "completed"
        assert len(result["resulting_artifact_ids"]) == 1
        with _active(tenant):
            risk = Risk.objects.get(id=result["resulting_artifact_ids"][0])
            assert risk.title == "Vendor outage"
            assert risk.description == "Single supplier"
            assert risk.probability == "high"

    def test_adr_session_maps_rationale_to_required_description(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        # AdrService.create_adr takes `description` as a required kwarg with
        # no default -- without the rationale->description rename this call
        # raises KeyError inside the adapter.
        session = _single_session(
            tenant, workspace, "Adr", {"title": "Use Postgres", "rationale": "RLS support"}
        )

        result = InterviewService().formalize(editor_ctx, session.id)

        with _active(tenant):
            adr = Adr.objects.get(id=result["resulting_artifact_ids"][0])
            assert adr.description == "RLS support"

    def test_testcase_session_creates_a_real_test_case(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        session = _single_session(
            tenant, workspace, "TestCase", {"title": "Login smoke", "rationale": "Happy path"}
        )

        result = InterviewService().formalize(editor_ctx, session.id)

        with _active(tenant):
            assert TestCase.objects.filter(id=result["resulting_artifact_ids"][0]).exists()

    def test_issue_session_creates_a_real_issue(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        session = _single_session(
            tenant, workspace, "Issue", {"title": "Flaky import", "rationale": "CSV encoding"}
        )

        result = InterviewService().formalize(editor_ctx, session.id)

        with _active(tenant):
            assert Issue.objects.filter(id=result["resulting_artifact_ids"][0]).exists()

    def test_requirement_session_still_returns_the_requirement_id(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        # Issue #736 regression guard: resulting_artifact_ids carries the
        # Requirement's own id (resolvable by RequirementService.get_requirement),
        # NOT the backing Artifact's id -- the adapter returns the latter, so
        # the entity-id resolution step must be in place.
        from persistence.models import Requirement

        session = _single_session(
            tenant, workspace, "Requirement", {"title": "Solo req", "rationale": "Because"}
        )

        result = InterviewService().formalize(editor_ctx, session.id)

        with _active(tenant):
            req = Requirement.objects.get(id=result["resulting_artifact_ids"][0])
            assert req.title == "Solo req"

    def test_missing_required_service_field_is_a_validation_error(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        # Risk without probability/impact: the adapter raises KeyError, which
        # must never escape as an unhandled 500 at the MCP/REST facade.
        session = _single_session(
            tenant, workspace, "Risk", {"title": "Bare risk", "rationale": "No numbers"}
        )

        with pytest.raises(ValidationError) as excinfo:
            InterviewService().formalize(editor_ctx, session.id)
        assert "Risk" in str(excinfo.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_formalize_single_types.py::TestFormalizeSingleAllTypes -v --create-db`
Expected: FAIL — 5 of 6 fail with `ValidationError: formalize() for artifact_type='Risk' is not implemented yet -- only Requirement is wired in this plan`

- [ ] **Step 3: Write minimal implementation**

3a. Delete the hardcoded guard at `interview_service.py:839-844`:

```python
        if session.artifact_type != "Requirement":
            raise ValidationError(
                f"formalize() for artifact_type={session.artifact_type!r} is not "
                "implemented yet -- only Requirement is wired in this plan; the "
                "other 7 types follow the identical pattern in a later pass."
            )
```

3b. Replace the `else:` create branch (currently `interview_service.py:909-918`) with the adapter dispatch. The `if session.target_artifact_id is not None:` update branch above it stays byte-for-byte unchanged:

```python
        else:
            # L2.1: the same adapter registry the multi-kind path
            # (_formalize_multi) has used in production since the
            # multi-artifact plan -- each entry calls the real create_X()
            # service, so workflow-state initialization stays correct for
            # free. No per-type branching here by design.
            from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS

            adapter = ARTIFACT_CREATION_ADAPTERS.get(session.artifact_type)
            if adapter is None:
                raise ValidationError(
                    f"formalize() has no artifact adapter for "
                    f"artifact_type={session.artifact_type!r}."
                )
            fields = _adapter_fields_from_collected(session.collected_fields)
            # The validated/coerced title above wins over the raw collected
            # value (it is stripped and proven non-empty).
            fields["title"] = title
            try:
                ref = adapter(fields, ctx, session.workspace_id)
            except (KeyError, TypeError) as exc:
                # Same conversion _formalize_multi does for proposal items: a
                # protocol that never elicited a service-required field
                # (KeyError) or elicited a field the create_X() signature does
                # not accept (TypeError) is a configuration problem, not a 500.
                raise ValidationError(
                    f"InterviewSession {session.id} cannot be formalized as "
                    f"{session.artifact_type}: {exc}"
                ) from exc
            # Issue #736: resulting_artifact_ids carries the domain-entity id,
            # but CreatedArtifactRef carries the Artifact PK -- bridge it back
            # through the one function that already maps every Artifact-backed
            # type, instead of a second per-type table here.
            resulting_ids.append(self._entity_id_for(ctx, ref))
```

3c. Add the helper as a method of `InterviewService`, directly above `_formalize_multi` (after the `return {"resulting_artifact_ids": ...}` line of `_formalize_single`):

```python
    @staticmethod
    def _entity_id_for(ctx, ref) -> str:
        """Artifact PK -> the domain-entity id detail routes and get_X() take.

        ``traceability.service.resolve_artifacts`` is the single existing
        bridge between the two id spaces (REQ-L2-TE-019) and already covers
        all nine Artifact-backed types. Falls back to the Artifact id when a
        row cannot be resolved (never raises): a formalize() that just
        created the row and then cannot resolve it must still report
        *something* addressable rather than fail after the write.
        """
        from traceability.service import resolve_artifacts

        resolved = resolve_artifacts([ref.artifact_id], ctx.tenant_id)
        if resolved and resolved[0].resolved and resolved[0].entity_id:
            return resolved[0].entity_id
        return str(ref.artifact_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_formalize_single_types.py application/tests/test_interview_formalize_multi.py application/tests/test_interview_service.py -v`
Expected: PASS — including the pre-existing `test_single_mode_formalize_unchanged` regression guard

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_formalize_single_types.py
git commit -m "fix(interview): formalize all 8 artifact types via adapter registry"
```

---

## Task 3: Elicit the fields `Risk` creation actually requires

**Files:**
- Modify: `backend/application/interview_protocol.py:117-135`
- Test: `backend/application/tests/test_interview_protocol.py`

**Interfaces:**
- Produces: `_EXTRA_REQUIRED_FIELDS: dict[str, str]` in `application/interview_protocol.py`
- Consumes: `parse_protocol_yaml(content: str) -> ProtocolConfig` (unchanged)

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_protocol.py`:

```python
class TestFactoryDefaultCoversRequiredCreateFields:
    """L2.1 follow-up: a type whose create_X() service has a required kwarg
    with no default must have that kwarg in its factory-default protocol --
    otherwise the interview never asks and formalize() fails at the adapter.
    Risk is the only such type (RiskService.create_risk: probability, impact);
    Adr.description is covered by the rationale->description mapping in
    interview_service._adapter_fields_from_collected."""

    def test_risk_default_protocol_elicits_probability_and_impact(self):
        from application.interview_protocol import (
            INTERVIEW_PROTOCOL_DEFAULTS,
            parse_protocol_yaml,
        )

        config = parse_protocol_yaml(INTERVIEW_PROTOCOL_DEFAULTS["interview.protocol.Risk"])
        names = {f.name for phase in config.phases for f in phase.required_fields}
        assert {"title", "rationale", "probability", "impact"} <= names

    def test_risk_probability_is_an_enum_with_the_service_choices(self):
        from application.interview_protocol import (
            INTERVIEW_PROTOCOL_DEFAULTS,
            parse_protocol_yaml,
        )

        config = parse_protocol_yaml(INTERVIEW_PROTOCOL_DEFAULTS["interview.protocol.Risk"])
        field = next(
            f
            for phase in config.phases
            for f in phase.required_fields
            if f.name == "probability"
        )
        assert field.type == "enum"
        assert field.choices == ["low", "medium", "high"]

    def test_requirement_default_protocol_is_unchanged(self):
        from application.interview_protocol import (
            INTERVIEW_PROTOCOL_DEFAULTS,
            parse_protocol_yaml,
        )

        config = parse_protocol_yaml(
            INTERVIEW_PROTOCOL_DEFAULTS["interview.protocol.Requirement"]
        )
        names = [f.name for phase in config.phases for f in phase.required_fields]
        assert names == ["title", "rationale"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_protocol.py::TestFactoryDefaultCoversRequiredCreateFields -v`
Expected: FAIL — `AssertionError` on the first test (`{'probability', 'impact'}` missing from `{'title', 'rationale'}`)

- [ ] **Step 3: Write minimal implementation**

In `backend/application/interview_protocol.py`, insert above `_default_protocol_yaml` (line 117) and use it inside:

```python
#: Extra required_fields appended to a type's elicitation phase, keyed by
#: artifact type. Only types whose create_X() service has a required kwarg
#: with NO default need an entry -- without one the interview never asks for
#: the value and formalize() fails inside the adapter (L2.1). Adr's required
#: ``description`` is deliberately absent: interview_service.
#: _adapter_fields_from_collected renames the generic ``rationale`` answer
#: onto it. YAML fragment, not a dataclass, because the whole factory default
#: is assembled as YAML text.
_EXTRA_REQUIRED_FIELDS: "dict[str, str]" = {
    # RiskService.create_risk(probability=..., impact=...): required, no
    # default, validated against Risk.Probability / Risk.Impact.
    "Risk": (
        "      - name: probability\n"
        "        type: enum\n"
        "        choices: [low, medium, high]\n"
        "      - name: impact\n"
        "        type: enum\n"
        "        choices: [low, medium, high]\n"
    ),
}


def _default_protocol_yaml(artifact_type: str) -> str:
    """A minimal, valid factory default: one elicitation phase asking for
    title + rationale (plus any field the type's create_X() service requires
    without a default, see _EXTRA_REQUIRED_FIELDS), then approval and
    formalization with no extra fields. Workspaces that need more override
    this via prompt_template.* (same mechanism as the other 7 derivation
    prompt types)."""
    return (
        "phases:\n"
        "  - name: elicitation\n"
        "    required_fields:\n"
        "      - name: title\n"
        "        type: text\n"
        "      - name: rationale\n"
        "        type: textarea\n"
        + _EXTRA_REQUIRED_FIELDS.get(artifact_type, "")
        + f"    prompt_fragment: \"Elicit the {artifact_type}'s title and rationale.\"\n"
        "  - name: approval\n"
        f"    prompt_fragment: \"Present the drafted {artifact_type} for approval.\"\n"
        "  - name: formalization\n"
        "    prompt_fragment: \"Confirm and formalize.\"\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_protocol.py application/tests/test_interview_formalize_single_types.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_protocol.py backend/application/tests/test_interview_protocol.py
git commit -m "fix(interview): elicit probability and impact in the Risk protocol"
```

---

## Task 4: Write a provenance row for single-kind formalize

**Files:**
- Modify: `backend/application/interview_service.py` (inside the `else:` create branch added in Task 2)
- Test: `backend/application/tests/test_interview_formalize_single_types.py`

**Interfaces:**
- Consumes: `InterviewSessionArtifact` (already imported at `interview_service.py:23-27`); `CreatedArtifactRef.artifact_id` / `.artifact_type`
- Produces: nothing new — makes `InterviewService.provenance_session_id(ctx, artifact_id) -> str | None` answer for single-kind sessions too

- [ ] **Step 1: Write the failing test**

Append to `class TestFormalizeSingleAllTypes` in `backend/application/tests/test_interview_formalize_single_types.py`:

```python
    def test_single_formalize_writes_a_provenance_row(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        # L2.3: provenance_session_id() reads InterviewSessionArtifact, which
        # only _formalize_multi used to write -- so an artifact created by a
        # normal single-type interview showed no "created via interview"
        # badge at all. The badge is only meaningful once this row exists.
        from persistence.models import InterviewSessionArtifact

        session = _single_session(
            tenant, workspace, "Issue", {"title": "Traced issue", "rationale": "Why"}
        )

        InterviewService().formalize(editor_ctx, session.id)

        with _active(tenant):
            row = InterviewSessionArtifact.objects.get(session=session)
            assert row.artifact_type == "Issue"
            assert (
                InterviewService().provenance_session_id(editor_ctx, row.artifact_id)
                == str(session.id)
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest "application/tests/test_interview_formalize_single_types.py::TestFormalizeSingleAllTypes::test_single_formalize_writes_a_provenance_row" -v`
Expected: FAIL — `InterviewSessionArtifact.DoesNotExist: InterviewSessionArtifact matching query does not exist.`

- [ ] **Step 3: Write minimal implementation**

In the `else:` branch from Task 2, directly after `resulting_ids.append(self._entity_id_for(ctx, ref))`:

```python
            # L2.3: the same provenance join row _formalize_multi writes. Only
            # on the create path -- an update against target_artifact_id did
            # not create the artifact, and "created via interview" would be a
            # false claim for it. formalize() wraps this method in
            # @atomic_transaction, so the row and the artifact commit together.
            InterviewSessionArtifact.objects.create(
                session=session,
                artifact_id=ref.artifact_id,
                artifact_type=ref.artifact_type,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_formalize_single_types.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_formalize_single_types.py
git commit -m "feat(interview): record provenance for single-kind formalize"
```

---

## Task 5: Explicit update-branch guard + truthful tool descriptions

**Files:**
- Modify: `backend/application/interview_service.py` (`_formalize_single` docstring at `:833-837`, new guard before the target branch; `formalize()` docstring at `:788-792`; `set_target()` docstring at `:738-742`)
- Modify: `backend/mcp_server/tools/interview.py:7-9`, `:175-200`
- Test: `backend/application/tests/test_interview_formalize_single_types.py`

**Interfaces:**
- Consumes: `InterviewSession.target_artifact_id`, `InterviewSession.artifact_type`
- Produces: no new symbols

- [ ] **Step 1: Write the failing test**

Append to `class TestFormalizeSingleAllTypes`:

```python
    def test_non_requirement_session_with_a_target_is_rejected_clearly(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        # set_target() is Requirement-only, so this shape is only reachable
        # for legacy rows -- but silently *creating* a second artifact when
        # the session says "update that one" would be the worst outcome.
        from persistence.models import Artifact

        session = _single_session(
            tenant, workspace, "Issue", {"title": "Targeted", "rationale": "Why"}
        )
        with _active(tenant):
            artifact = Artifact.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type="Issue",
                custom_fields={},
            )
            session.target_artifact_id = artifact.id
            session.save(update_fields=["target_artifact_id"])

        with pytest.raises(ValidationError) as excinfo:
            InterviewService().formalize(editor_ctx, session.id)
        assert "Requirement" in str(excinfo.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest "application/tests/test_interview_formalize_single_types.py::TestFormalizeSingleAllTypes::test_non_requirement_session_with_a_target_is_rejected_clearly" -v`
Expected: FAIL — `Failed: DID NOT RAISE <class 'application.base.ValidationError'>` (the Requirement-only update branch runs `Requirement.objects.filter(artifact_id=...)`, finds nothing, and raises `NotFoundError`, which is not a `ValidationError`)

- [ ] **Step 3: Write minimal implementation**

3a. In `_formalize_single`, directly above `if session.target_artifact_id is not None:` (currently line 886):

```python
        # The update branch below is Requirement-only: set_target() rejects
        # every other type (see its docstring), so this can only be reached
        # by a legacy row. Fail loudly instead of falling through to the
        # create branch, which would produce a SECOND artifact for a session
        # that explicitly asked to update an existing one.
        if session.target_artifact_id is not None and session.artifact_type != "Requirement":
            raise ValidationError(
                f"InterviewSession {session.id} has a target artifact but "
                f"artifact_type={session.artifact_type!r}; formalize() can only "
                "update an existing artifact for 'Requirement'."
            )
```

3b. Replace the `_formalize_single` docstring (`:833-837`):

```python
        """Single-kind path: one typed artifact from collected_fields.

        Creation dispatches through ARTIFACT_CREATION_ADAPTERS and covers
        all 8 in-scope artifact types (L2.1). The *update* branch
        (target_artifact_id set) stays Requirement-only, matching
        set_target()'s own gate -- generalizing it needs a per-type
        update_X() mapping no caller has asked for.
        Single-mode regression guard:
        test_interview_formalize_multi.py::test_single_mode_formalize_unchanged.
        """
```

3c. In the `formalize()` docstring, replace the paragraph at `:788-792` with:

```python
        Single-kind sessions drive one typed artifact through the classic
        protocol; every in-scope artifact_type is created through its
        production ``create_X()`` service via ARTIFACT_CREATION_ADAPTERS
        (L2.1), the same registry the multi-kind path uses.
```

3d. In `set_target()`'s docstring, replace the paragraph at `:738-742` with:

```python
        Requirement-only, matching ``formalize()``'s *update* branch: since
        L2.1, formalize() can CREATE every in-scope type, but it can only
        UPDATE an existing Requirement. Setting a target on any other
        artifact_type would be a target formalize() can never use, so reject
        it here instead of silently accepting a value that goes nowhere.
```

3e. In `backend/mcp_server/tools/interview.py`, module docstring lines 7-9, replace:

```
interview.grounding_context (Task 5, structural + Task 6 AI-assisted
ranking) / interview.formalize (Task 7, Requirement only) /
interview.set_target (issue #540, confirms a grounding_context()
candidate as formalize()'s update target, Requirement only) /
```

with:

```
interview.grounding_context (Task 5, structural + Task 6 AI-assisted
ranking) / interview.formalize (L2.1, all 8 in-scope artifact types) /
interview.set_target (issue #540, confirms a grounding_context()
candidate as formalize()'s update target; UPDATE is Requirement-only) /
```

3f. In the same file, replace the `interview.formalize` description (lines 176-183):

```python
            "description": (
                "Turn the session's collected answers into a real artifact (write). "
                "Creates a new Requirement, or -- if grounding set a target -- "
                "updates the existing one instead, re-checking at write time that "
                "the target still exists. Marks the session completed and returns "
                "resulting_artifact_ids. Only artifact_type='Requirement' sessions "
                "are supported so far."
            ),
```

with:

```python
            "description": (
                "Turn the session's collected answers into a real artifact (write). "
                "Creates the session's artifact_type through its production "
                "create_X() service -- all 8 in-scope types (Requirement, "
                "StakeholderNeed, ArchitectureElement, Risk, TestCase, Adr, Issue, "
                "Goal) -- or, if grounding set a target, updates that existing "
                "Requirement instead, re-checking at write time that it still "
                "exists. Marks the session completed and returns "
                "resulting_artifact_ids. Every protocol-required field must be "
                "answered first."
            ),
```

3g. Replace the `interview.set_target` description (lines 194-203):

```python
            "description": (
                "Confirm a grounding_context() candidate (or any already-known "
                "artifact_id) as this session's formalize() target (write). "
                "Once set, formalize() updates that existing Requirement "
                "instead of creating a new one. Requirement sessions only -- "
                "formalize()'s update branch does not support the other 7 "
                "in-scope artifact types yet. Re-validates that artifact_id "
                "resolves to a real Requirement right now. Returns the "
                "session's refreshed state."
            ),
```

with:

```python
            "description": (
                "Confirm a grounding_context() candidate (or any already-known "
                "artifact_id) as this session's formalize() target (write). "
                "Once set, formalize() updates that existing Requirement "
                "instead of creating a new one. Requirement sessions only -- "
                "formalize() CREATES every in-scope artifact type, but its "
                "UPDATE branch is Requirement-only, so a target on any other "
                "type could never be used. Re-validates that artifact_id "
                "resolves to a real Requirement right now. Returns the "
                "session's refreshed state."
            ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_formalize_single_types.py mcp_server/tests -k "interview or formalize" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/mcp_server/tools/interview.py backend/application/tests/test_interview_formalize_single_types.py
git commit -m "fix(interview): guard update branch and correct tool descriptions"
```

---

## Task 6: `InterviewSession.transcript_summary` column

**Files:**
- Modify: `backend/persistence/models.py:2457-2461` (after the `transcript` field)
- Create: `backend/persistence/migrations/0070_interviewsession_transcript_summary.py`
- Test: `backend/application/tests/test_interview_transcript_cap.py`

**Interfaces:**
- Produces: `InterviewSession.transcript_summary: str` (TextField, `blank=True`, default `""`)

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_interview_transcript_cap.py`:

```python
"""Transcript capping (audit finding L2.4).

interview_service.generate_chat_turn() used to append every turn to
InterviewSession.transcript forever AND send the whole thing as prompt
context. Turns older than a sliding window are now folded into
InterviewSession.transcript_summary by one best-effort LLM call.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from persistence.models import InterviewSession, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


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
    return Tenant.objects.create(name="IV-Cap Tenant", slug="iv-cap-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="IV-Cap-WS")


class TestTranscriptSummaryColumn:
    def test_new_session_has_an_empty_summary(self, tenant: Tenant, workspace: Workspace):
        with _active(tenant):
            session = InterviewSession.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type="Requirement",
                session_kind=InterviewSession.SESSION_KIND_SINGLE,
            )
            session.refresh_from_db()
        assert session.transcript_summary == ""

    def test_summary_round_trips_through_the_database(
        self, tenant: Tenant, workspace: Workspace
    ):
        with _active(tenant):
            session = InterviewSession.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type="Requirement",
                session_kind=InterviewSession.SESSION_KIND_SINGLE,
            )
            session.transcript_summary = "User wants CSV import."
            session.save(update_fields=["transcript_summary"])
            session.refresh_from_db()
        assert session.transcript_summary == "User wants CSV import."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_transcript_cap.py -v`
Expected: FAIL — `AttributeError: 'InterviewSession' object has no attribute 'transcript_summary'`

- [ ] **Step 3: Write minimal implementation**

3a. In `backend/persistence/models.py`, directly after the `transcript` field of `InterviewSession` (line 2457-2461):

```python
    transcript_summary = models.TextField(
        blank=True,
        default="",
        help_text=(
            "L2.4: compressed prose for every turn that has fallen out of the "
            "live transcript window. Written only by a successful summarization "
            "call; empty means 'nothing compressed yet'."
        ),
    )
```

3b. Create `backend/persistence/migrations/0070_interviewsession_transcript_summary.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    """L2.4: hold compressed older turns instead of growing transcript forever."""

    dependencies = [
        ("persistence", "0069_align_embedding_dimensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="interviewsession",
            name="transcript_summary",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "L2.4: compressed prose for every turn that has fallen out of the "
                    "live transcript window. Written only by a successful summarization "
                    "call; empty means 'nothing compressed yet'."
                ),
            ),
        ),
    ]
```

3c. Verify Django agrees no further migration is outstanding:

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test python manage.py makemigrations persistence --check --dry-run`
Expected: `No changes detected in app 'persistence'`

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_transcript_cap.py -v --create-db`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/0070_interviewsession_transcript_summary.py backend/application/tests/test_interview_transcript_cap.py
git commit -m "feat(interview): add transcript_summary column to InterviewSession"
```

---

## Task 7: Prompt-visible transcript window

**Files:**
- Modify: `backend/application/interview_service.py` (module constant near `ABANDONED_TTL` at line 34; new static method on `InterviewService` above `generate_chat_turn`)
- Test: `backend/application/tests/test_interview_transcript_cap.py`

**Interfaces:**
- Produces: `TRANSCRIPT_WINDOW_ENTRIES: int`; `InterviewService._transcript_for_prompt(session: InterviewSession) -> list[dict[str, Any]]`

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_transcript_cap.py`:

```python
class TestTranscriptForPrompt:
    """Pure shaping, no DB and no LLM: what the next prompt gets to see."""

    def _session(self, transcript, summary=""):
        from persistence.models import InterviewSession

        return InterviewSession(
            artifact_type="Requirement",
            transcript=transcript,
            transcript_summary=summary,
        )

    def test_without_a_summary_the_transcript_is_passed_through(self):
        from application.interview_service import InterviewService

        turns = [{"role": "user", "text": "hi", "timestamp": "t"}]
        assert InterviewService._transcript_for_prompt(self._session(turns)) == turns

    def test_a_summary_is_prepended_as_one_system_entry(self):
        from application.interview_service import InterviewService

        turns = [{"role": "user", "text": "hi", "timestamp": "t"}]
        result = InterviewService._transcript_for_prompt(
            self._session(turns, summary="Earlier: user wants CSV import.")
        )
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert "CSV import" in result[0]["text"]
        assert result[1:] == turns

    def test_window_constant_is_ten_turn_pairs(self):
        from application.interview_service import TRANSCRIPT_WINDOW_ENTRIES

        assert TRANSCRIPT_WINDOW_ENTRIES == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_transcript_cap.py::TestTranscriptForPrompt -v`
Expected: FAIL — `AttributeError: type object 'InterviewService' has no attribute '_transcript_for_prompt'`

- [ ] **Step 3: Write minimal implementation**

3a. Module constant in `interview_service.py`, below `ABANDONED_TTL` (line 34):

```python
# L2.4: how many transcript entries stay verbatim. Two entries per exchange
# (one user, one assistant), so 20 == the spec's "gleitendes Fenster von 10
# Turns". A constant, not a setting -- one threshold is enough (YAGNI).
TRANSCRIPT_WINDOW_ENTRIES = 20

# PromptTemplate slot for the transcript-compression call (L2.4). Registered
# in AiDerivationService.PROMPT_TEMPLATE_DEFAULTS, the single canonical
# factory-default registry -- same arrangement as
# GROUNDING_RANK_PROMPT_TEMPLATE_NAME above.
TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE_NAME = "interview.transcript_summary"
```

3b. Static method on `InterviewService`, directly above `generate_chat_turn`:

```python
    @staticmethod
    def _transcript_for_prompt(session: InterviewSession) -> "list[dict[str, Any]]":
        """Conversation as the next prompt should see it: the compressed
        summary as one leading system entry, then the live window.

        Deliberately re-uses the existing ``{transcript_json}`` prompt
        variable instead of introducing a new placeholder: prompt_resolver.
        render_template only substitutes placeholders a template actually
        contains, so a workspace/tenant override of ``interview.chat_turn``
        written before this change would silently drop a new variable --
        losing the summary for exactly the tenants who customised most.
        """
        if not session.transcript_summary:
            return list(session.transcript)
        return [
            {
                "role": "system",
                "text": f"Summary of earlier turns: {session.transcript_summary}",
                "timestamp": "",
            },
            *session.transcript,
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_transcript_cap.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_transcript_cap.py
git commit -m "feat(interview): shape prompt transcript as summary plus window"
```

---

## Task 8: Register the `interview.transcript_summary` prompt slot

**Files:**
- Modify: `backend/application/ai_derivation_service.py` (new template constant after `INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE` at `:227-261`, new `PROMPT_TEMPLATE_DEFAULTS` entry at `:285`, new `__all__` entry near `:2260`)
- Modify: `backend/application/prompt_slots.py` (`_DATA_VARIABLES_BY_SLOT`)
- Test: `backend/application/tests/test_interview_transcript_cap.py`

**Interfaces:**
- Produces: `INTERVIEW_TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE: str`; slot name `"interview.transcript_summary"` with data variables `("artifact_type", "previous_summary", "turns_json")`

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_transcript_cap.py`:

```python
class TestTranscriptSummarySlot:
    def test_slot_has_a_factory_default(self):
        from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS

        assert "interview.transcript_summary" in PROMPT_TEMPLATE_DEFAULTS

    def test_factory_default_carries_all_three_placeholders(self):
        from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS

        body = PROMPT_TEMPLATE_DEFAULTS["interview.transcript_summary"]
        for placeholder in ("{artifact_type}", "{previous_summary}", "{turns_json}"):
            assert placeholder in body

    def test_slot_declares_its_data_variables(self):
        from application.prompt_slots import get_prompt_slots

        spec = get_prompt_slots()["interview.transcript_summary"]
        assert spec.data_variables == ("artifact_type", "previous_summary", "turns_json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_transcript_cap.py::TestTranscriptSummarySlot -v`
Expected: FAIL — `KeyError: 'interview.transcript_summary'`

- [ ] **Step 3: Write minimal implementation**

3a. In `backend/application/ai_derivation_service.py`, after `INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE` (ends line 261):

```python
# L2.4: folds the turns that fell out of InterviewService's live transcript
# window into one running summary. Fail-open by construction -- the caller
# (InterviewService._compress_transcript) treats any failure as "compress
# later", so a provider outage delays compression instead of blocking chat.
INTERVIEW_TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE = """\
You are compressing the older part of an interview whose goal is to create a \
{artifact_type} in a requirements management system.

Summary of everything before these turns (may be empty):
{previous_summary}

Turns to fold into that summary (JSON list of {"role": ..., "text": ..., \
"timestamp": ...}):
{turns_json}

Write ONE updated summary that replaces both inputs. Preserve every concrete \
fact, decision, constraint, name, number and open question the user stated -- \
those are the raw material the artifact is built from at the end. Drop only \
pleasantries and repetition. Answer with the summary text only: no prose \
framing, no markdown fences, no JSON.
"""
```

3b. Add to `PROMPT_TEMPLATE_DEFAULTS` (line 285, after the `"interview.chat_turn"` entry):

```python
    "interview.transcript_summary": INTERVIEW_TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE,
```

3c. Add `"INTERVIEW_TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE",` to `__all__` next to `"INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE",` (line 2260).

3d. In `backend/application/prompt_slots.py`, add to `_DATA_VARIABLES_BY_SLOT` after the `"interview.chat_turn"` entry:

```python
    # L2.4 transcript compression -- see InterviewService._compress_transcript.
    "interview.transcript_summary": (
        "artifact_type",
        "previous_summary",
        "turns_json",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_transcript_cap.py application/tests/test_prompt_slots.py -v`
Expected: PASS (if `application/tests/test_prompt_slots.py` does not exist, drop it from the command and run only the first path)

- [ ] **Step 5: Commit**

```bash
git add backend/application/ai_derivation_service.py backend/application/prompt_slots.py backend/application/tests/test_interview_transcript_cap.py
git commit -m "feat(interview): register interview.transcript_summary prompt slot"
```

---

## Task 9: Compress overflow turns on every chat turn

**Files:**
- Modify: `backend/application/interview_service.py` (new method above `generate_chat_turn`; call site + `transcript_json` in `generate_chat_turn` at `:1193-1204`; call site + transcript argument in `_generate_multi_chat_turn` at `:1369`)
- Test: `backend/application/tests/test_interview_transcript_cap.py`

**Interfaces:**
- Consumes: `TRANSCRIPT_WINDOW_ENTRIES`, `TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE_NAME`, `InterviewService._transcript_for_prompt` (Task 7); `InterviewService._resolve_provider() -> tuple[Any | None, str, Exception | None]`; `AiDerivationService._get_template_content(ctx, name, workspace_id) -> str`; `AiDerivationService._render(template, **values) -> str`; `llm_adapter.timeouts.resolve_timeout_seconds(purpose) -> float`
- Produces: `InterviewService._compress_transcript(ctx, session: InterviewSession) -> None`

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_transcript_cap.py`:

```python
class TestCompressTranscript:
    """The compression step itself: DB-backed, provider mocked."""

    def _session_with_turns(self, tenant, workspace, count: int):
        from persistence.models import InterviewSession

        turns = [
            {"role": "user" if i % 2 == 0 else "assistant", "text": f"turn {i}", "timestamp": "t"}
            for i in range(count)
        ]
        with _active(tenant):
            return InterviewSession.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type="Requirement",
                session_kind=InterviewSession.SESSION_KIND_SINGLE,
                status=InterviewSession.STATUS_IN_PROGRESS,
                transcript=turns,
            )

    def _ctx(self, tenant):
        from auth_tenancy.context import AuthContext, AuthMethod
        from persistence.models import User

        user = User.objects.create(
            username=f"iv-cap-{tenant.slug}", email="cap@example.com", tenant=tenant
        )
        return AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.API_KEY,
        )

    def test_below_the_window_nothing_is_compressed(self, tenant, workspace):
        from unittest.mock import MagicMock, patch

        from application.interview_service import InterviewService

        session = self._session_with_turns(tenant, workspace, 20)
        provider = MagicMock()
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript(self._ctx(tenant), session)

        provider.complete.assert_not_called()
        assert len(session.transcript) == 20
        assert session.transcript_summary == ""

    def test_overflow_turns_move_into_the_summary(self, tenant, workspace):
        from unittest.mock import MagicMock, patch

        from application.interview_service import InterviewService

        session = self._session_with_turns(tenant, workspace, 24)
        provider = MagicMock()
        provider.complete.return_value = "User needs CSV import with a dry-run mode."
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            with _active(tenant):
                InterviewService()._compress_transcript(self._ctx(tenant), session)
                session.refresh_from_db()

        assert session.transcript_summary == "User needs CSV import with a dry-run mode."
        assert len(session.transcript) == 20
        # The window keeps the NEWEST turns.
        assert session.transcript[0]["text"] == "turn 4"
        assert session.transcript[-1]["text"] == "turn 23"

    def test_a_failing_provider_leaves_everything_untouched(self, tenant, workspace):
        from unittest.mock import MagicMock, patch

        from application.interview_service import InterviewService

        session = self._session_with_turns(tenant, workspace, 24)
        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("provider down")
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            with _active(tenant):
                InterviewService()._compress_transcript(self._ctx(tenant), session)
                session.refresh_from_db()

        # Spec §7: no data loss, only delayed compression.
        assert session.transcript_summary == ""
        assert len(session.transcript) == 24

    def test_no_provider_at_all_is_not_an_error(self, tenant, workspace):
        from unittest.mock import patch

        from application.interview_service import InterviewService

        session = self._session_with_turns(tenant, workspace, 24)
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(None, "none", None)
        ):
            with _active(tenant):
                InterviewService()._compress_transcript(self._ctx(tenant), session)
                session.refresh_from_db()

        assert len(session.transcript) == 24

    def test_an_empty_answer_is_not_written(self, tenant, workspace):
        from unittest.mock import MagicMock, patch

        from application.interview_service import InterviewService

        session = self._session_with_turns(tenant, workspace, 24)
        provider = MagicMock()
        provider.complete.return_value = "   "
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            with _active(tenant):
                InterviewService()._compress_transcript(self._ctx(tenant), session)
                session.refresh_from_db()

        assert session.transcript_summary == ""
        assert len(session.transcript) == 24
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_transcript_cap.py::TestCompressTranscript -v`
Expected: FAIL — `AttributeError: 'InterviewService' object has no attribute '_compress_transcript'`

- [ ] **Step 3: Write minimal implementation**

3a. Method on `InterviewService`, directly above `_transcript_for_prompt`:

```python
    def _compress_transcript(self, ctx, session: InterviewSession) -> None:
        """Fold everything older than the live window into transcript_summary.

        Best effort by design (spec §7 / issue #846): no provider, a failing
        call, or an empty answer all leave BOTH ``transcript`` and
        ``transcript_summary`` untouched, so the next turn simply retries
        with one more entry. Delayed compression, never data loss.

        The daily token budget is deliberately NOT enforced here: this is
        housekeeping the user did not ask for, so an exhausted budget must
        degrade to "don't compress", not to "can't chat" (generate_chat_turn
        keeps its own is_over_daily_limit() gate for the turn itself).
        """
        overflow = session.transcript[:-TRANSCRIPT_WINDOW_ENTRIES]
        if not overflow:
            return

        provider, _provider_name, _resolve_error = self._resolve_provider()
        if provider is None:
            return

        from application.ai_derivation_service import AiDerivationService
        from llm_adapter.timeouts import resolve_timeout_seconds

        template = AiDerivationService._get_template_content(
            ctx, TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE_NAME, session.workspace_id
        )
        prompt = AiDerivationService._render(
            template,
            # Multi-kind sessions carry artifact_type=None by definition.
            artifact_type=session.artifact_type or "artifact",
            previous_summary=session.transcript_summary,
            turns_json=json.dumps(overflow),
        )
        try:
            raw_summary = provider.complete(
                prompt,
                purpose=TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE_NAME,
                timeout=resolve_timeout_seconds(TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE_NAME),
            )
        except Exception:  # noqa: BLE001 -- fail-open, see docstring
            logger.debug(
                "InterviewService: transcript compression failed for session=%s, "
                "retrying on the next turn", session.id
            )
            return

        summary = str(raw_summary or "").strip()
        if not summary:
            # An empty answer would trade real turns for nothing.
            return

        session.transcript_summary = summary
        session.transcript = session.transcript[-TRANSCRIPT_WINDOW_ENTRIES:]
        session.version = F("version") + 1
        session.save(
            update_fields=["transcript", "transcript_summary", "modified_at", "version"]
        )
        session.refresh_from_db(fields=["version"])
```

3b. In `generate_chat_turn`, directly after the `is_over_daily_limit()` block and before `phase, missing = self._current_phase_and_missing(ctx, session)` (line 1187):

```python
        # L2.4: compress BEFORE building the prompt, so this turn already
        # profits from the smaller context.
        self._compress_transcript(ctx, session)
```

3c. In the same method, change the `_render` call (line 1198):

```python
            transcript_json=json.dumps(self._transcript_for_prompt(session)),
```

3d. In `_generate_multi_chat_turn`, before the `get_multi_protocol_prompt(...)` call (line 1369), add the same compression call, and pass the shaped transcript:

```python
        self._compress_transcript(ctx, session)
        prompt = get_multi_protocol_prompt(
            ctx, session.workspace_id, user_message, self._transcript_for_prompt(session)
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_transcript_cap.py application/tests/test_interview_service.py application/tests/test_interview_multi_chat.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_transcript_cap.py
git commit -m "feat(interview): cap chat transcript with a rolling summary"
```

---

## Task 10: Provenance badge links to its session

**Files:**
- Modify: `frontend/src/components/shared/InterviewProvenanceBadge.tsx:44-50`
- Test: `frontend/src/components/shared/InterviewProvenanceBadge.test.tsx`

**Interfaces:**
- Consumes: `interviewsApi.getProvenance(artifactId: UUID) => Promise<{ session_id: string | null }>`
- Produces: unchanged component signature `InterviewProvenanceBadge({ artifactId }: { artifactId: string }): JSX.Element | null`

- [ ] **Step 1: Write the failing test**

Append inside the existing `describe("InterviewProvenanceBadge", ...)` block in `frontend/src/components/shared/InterviewProvenanceBadge.test.tsx`:

```tsx
  it("links to the session that created the artifact", async () => {
    vi.mocked(interviewsApi.getProvenance).mockResolvedValue({ session_id: "sess-9" });

    renderBadge("art-1");

    const link = await screen.findByTestId("interview-provenance-badge");
    expect(link).toHaveAttribute("href", "/interviews/sess-9");
  });
```

If the file's existing helper is not named `renderBadge`, reuse whatever render helper the file already defines (read lines 1-40 first) and keep the assertion body identical.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/shared/InterviewProvenanceBadge.test.tsx"`
Expected: FAIL — received `href="/interviews"`, expected `"/interviews/sess-9"`

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/components/shared/InterviewProvenanceBadge.tsx`, replace the `Link` (line 47):

```tsx
    <Link to={`/interviews/${sessionId}`} data-testid="interview-provenance-badge">
```

and update the module docstring line 8-10 to:

```
 * `interview.multi.createdBadge` i18n key, pointing at that session's own
 * detail route (`/interviews/{session_id}`) — the single interview surface.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/shared/InterviewProvenanceBadge.test.tsx"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/InterviewProvenanceBadge.tsx frontend/src/components/shared/InterviewProvenanceBadge.test.tsx
git commit -m "fix(interview): link provenance badge to its own session"
```

---

## Task 11: Mount the badge in all eight artifact editors

**Files:**
- Modify: `frontend/src/components/RiskEditors/RiskEditors.tsx:161-167`
- Modify: `frontend/src/components/AdrEditors/AdrEditors.tsx:178-184`
- Modify: `frontend/src/components/IssueEditors/IssueEditors.tsx:161-167`
- Modify: `frontend/src/components/NeedsEditors/NeedsEditors.tsx` (its `<TraceSpine .../>` block)
- Modify: `frontend/src/components/RequirementEditors/RequirementEditors.tsx` (its `<TraceSpine .../>` block)
- Modify: `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx` (its `<TraceSpine .../>` block)
- Modify: `frontend/src/components/TestCaseEditors/TestCaseEditors.tsx` (its `<TraceSpine .../>` block)
- Modify: `frontend/src/components/Goals/GoalDetail.tsx:128` (its `<TraceSpine .../>` block)
- Test: `frontend/src/test/RiskEditors.test.tsx`

**Interfaces:**
- Consumes: `InterviewProvenanceBadge({ artifactId }: { artifactId: string })` (Task 10)

- [ ] **Step 1: Write the failing test**

Append to the main `describe` block in `frontend/src/test/RiskEditors.test.tsx`:

```tsx
  it("shows the interview provenance badge for an interview-created risk", async () => {
    const { apiClient } = await import("../api/client");
    vi.mocked(apiClient.get).mockImplementation((path?: string) => {
      if (path === `/interviews/by-artifact/${RISK.id}/`) {
        return Promise.resolve({ session_id: "sess-7" });
      }
      return Promise.resolve({});
    });

    renderPage(`/risks/${RISK.id}`);

    const badge = await screen.findByTestId("interview-provenance-badge");
    expect(badge).toHaveAttribute("href", "/interviews/sess-7");
  });
```

Read the file's existing render helper name and its route path first (it defines one near the bottom of the mock block); use that helper instead of `renderPage` if it is named differently, and keep the assertion body identical. If `RISK` has an `artifact_id`, use that in the path instead of `RISK.id` — the badge is mounted with `item?.artifact_id ?? item?.id`.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/RiskEditors.test.tsx"`
Expected: FAIL — `Unable to find an element by: [data-testid="interview-provenance-badge"]`

- [ ] **Step 3: Write minimal implementation**

In each of the eight files, add the import next to the other `components/shared` imports:

```tsx
import { InterviewProvenanceBadge } from '../shared/InterviewProvenanceBadge';
```

(in `Goals/GoalDetail.tsx` the relative path is also `"../shared/InterviewProvenanceBadge"`; match each file's existing quote style — single quotes in RiskEditors/AdrEditors/IssueEditors/RequirementEditors/ArchitectureEditors/TestCaseEditors, double quotes in GoalDetail).

Then insert the badge on the line directly after the closing `/>` of each `<TraceSpine ... />` element, using the same id expression the file already passes as `useDerivationChain`'s first argument:

- `RiskEditors.tsx` (after line 167): `<InterviewProvenanceBadge artifactId={item.artifact_id ?? item.id} />`
- `AdrEditors.tsx` (after line 184): `<InterviewProvenanceBadge artifactId={item.artifact_id ?? item.id} />`
- `IssueEditors.tsx` (after line 167): `<InterviewProvenanceBadge artifactId={item.artifact_id ?? item.id} />`
- `NeedsEditors.tsx`: `<InterviewProvenanceBadge artifactId={need.artifact_id ?? need.id} />`
- `RequirementEditors.tsx`: `<InterviewProvenanceBadge artifactId={requirement.artifact_id ?? requirement.id} />`
- `ArchitectureEditors.tsx`: `<InterviewProvenanceBadge artifactId={element.artifact_id ?? element.id} />`
- `TestCaseEditors.tsx`: `<InterviewProvenanceBadge artifactId={item.id} />` (this type has no separate `artifact_id`; see the comment at `TestCaseEditors.tsx:135-137`)
- `Goals/GoalDetail.tsx` (after line ~133): `<InterviewProvenanceBadge artifactId={goal.artifact_id ?? goal.id} />`

Each insertion sits inside the existing `{item && ( ... )}` / `{element && ( ... )}` guard. Where that guard currently wraps a single element, wrap both in a fragment:

```tsx
                {item && (
                  <>
                    <TraceSpine
                      stations={derivationChain.stations}
                      isLoading={derivationChain.isLoading}
                      error={derivationChain.error}
                      onOpenArtifact={handleOpenChainArtifact}
                      isOpenable={derivationChain.isOpenable}
                    />
                    <InterviewProvenanceBadge artifactId={item.artifact_id ?? item.id} />
                  </>
                )}
```

The badge renders `null` until the provenance lookup returns a session id, so this adds no visual noise to plain artifacts.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/test/RiskEditors.test.tsx src/test/AdrEditors.test.tsx src/test/IssueEditors.test.tsx src/test/RequirementEditors.test.tsx src/test/ArchitectureEditors.test.tsx"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RiskEditors/RiskEditors.tsx frontend/src/components/AdrEditors/AdrEditors.tsx frontend/src/components/IssueEditors/IssueEditors.tsx frontend/src/components/NeedsEditors/NeedsEditors.tsx frontend/src/components/RequirementEditors/RequirementEditors.tsx frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx frontend/src/components/TestCaseEditors/TestCaseEditors.tsx frontend/src/components/Goals/GoalDetail.tsx frontend/src/test/RiskEditors.test.tsx
git commit -m "feat(interview): show provenance badge in all artifact editors"
```

---

## Task 12: Expose `session_kind` in the session state

**Files:**
- Modify: `backend/application/interview_service.py:312-339` (`get_state`, both branches)
- Modify: `backend/rest_api/interview_views.py:88-94` (`_started_session_state`'s multi branch)
- Modify: `frontend/src/api/interviews.ts:45-57` (`InterviewState`)
- Test: `backend/application/tests/test_interview_service.py`

**Interfaces:**
- Produces: `get_state()["session_kind"]: str` (`"single"` | `"multi"`); TS `InterviewState.session_kind: "single" | "multi"`

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_service.py` (reuse the fixtures already defined in that file; read its fixture names first and substitute them for `tenant` / `workspace` / `editor_ctx` if they differ):

```python
class TestGetStateExposesSessionKind:
    """The frontend used to guess the kind from local start-time state
    (see InterviewChatPane's MultiModeInterview docstring). A multi session
    has no phase/missing_fields, so a consumer that cannot tell the kind
    apart crashes on the detail route."""

    def test_single_session_state_says_single(self, tenant, workspace, editor_ctx):
        session = InterviewService().start(
            editor_ctx, "Requirement", workspace.id
        )
        state = InterviewService().get_state(editor_ctx, session.id)
        assert state["session_kind"] == "single"

    def test_multi_session_state_says_multi(self, tenant, workspace, editor_ctx):
        session = InterviewService().start(
            editor_ctx, None, workspace.id, session_kind="multi"
        )
        state = InterviewService().get_state(editor_ctx, session.id)
        assert state["session_kind"] == "multi"
        assert "missing_fields" not in state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_service.py::TestGetStateExposesSessionKind -v`
Expected: FAIL — `KeyError: 'session_kind'`

- [ ] **Step 3: Write minimal implementation**

3a. In `get_state()`, add the key to BOTH returned dicts (after `"status": session.status,` in each):

```python
            "session_kind": session.session_kind,
```

3b. In `rest_api/interview_views.py`, add the same key to the multi branch of `_started_session_state`:

```python
            "session_kind": session.session_kind,
```

3c. In `frontend/src/api/interviews.ts`, add to `InterviewState` (after `status`) and relax the two fields multi sessions omit:

```ts
  /** Which interview axis this session is on. Backend `get_state()` sends it
   *  for both kinds; multi sessions omit `phase`/`missing_fields` entirely. */
  session_kind: "single" | "multi";
  phase?: string;
  collected_fields: Record<string, unknown>;
  missing_fields?: InterviewField[];
```

Then run `npx tsc --noEmit` (see Step 4) and fix every newly reported call site by using `?? []` / optional access — do not widen the type back.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_service.py rest_api/tests -k "interview" -v`
Expected: PASS

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx tsc --noEmit"`
Expected: no errors (frontend CI does not run `tsc`, so this check must be run by hand here)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/rest_api/interview_views.py backend/application/tests/test_interview_service.py frontend/src/api/interviews.ts
git commit -m "feat(interview): expose session_kind in interview state"
```

---

## Task 13: `/interviews/{id}` survives a multi-mode session

**Files:**
- Modify: `frontend/src/components/InterviewEditors/InterviewDetail.tsx:126-140`
- Test: `frontend/src/components/InterviewEditors/InterviewEditors.test.tsx`

**Interfaces:**
- Consumes: `InterviewState.session_kind` (Task 12); `InterviewChatPane` prop `interview: InterviewState | MultiModeInterview`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/components/InterviewEditors/InterviewEditors.test.tsx`:

```tsx
describe("InterviewEditors with a multi-mode session", () => {
  const MULTI = { id: "s-multi", workspace_id: "ws-001", artifact_type: null, status: "in_progress" };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(interviewsApi.listAll).mockResolvedValue([MULTI] as any);
    // A multi session's get_state() carries no phase and no missing_fields.
    vi.mocked(interviewsApi.getState).mockResolvedValue({
      id: MULTI.id,
      status: "in_progress",
      session_kind: "multi",
      collected_fields: {},
      grounding_snapshot: {},
      transcript: [],
    } as any);
  });

  it("renders the detail panel without crashing on missing_fields", async () => {
    renderPage(`/interviews/${MULTI.id}`);
    expect(await screen.findByTestId("interview-detail")).toBeInTheDocument();
    expect(screen.queryByTestId("interview-missing-fields")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/InterviewEditors/InterviewEditors.test.tsx"`
Expected: FAIL — `TypeError: Cannot read properties of undefined (reading 'length')` from `InterviewDetail`

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/components/InterviewEditors/InterviewDetail.tsx`, below `const canAbandon = ...` (line 51):

```tsx
  // Multi-mode sessions have no per-type protocol, so the backend's
  // get_state() carries neither `phase` nor `missing_fields` (see
  // InterviewService.get_state). Read them defensively rather than
  // assuming the single-mode shape.
  const missingFields = current.missing_fields ?? [];
  const isMulti = current.session_kind === "multi";
```

Replace the missing-fields guard (line 126):

```tsx
      {missingFields.length > 0 && (
```

and its `.map` source (line 130):

```tsx
            {missingFields.map((f) => (
```

Replace the chat pane render (line 139) so the pane gets the discriminator it needs for the multi proposal UI:

```tsx
        <InterviewChatPane
          interview={isMulti ? { ...current, session_kind: "multi" } : current}
          onStateChange={setSession}
        />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/InterviewEditors/"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/InterviewEditors/InterviewDetail.tsx frontend/src/components/InterviewEditors/InterviewEditors.test.tsx
git commit -m "fix(interview): render multi-mode sessions on the detail route"
```

---

## Task 14: Reduce the widget to a launcher

**Files:**
- Modify: `frontend/src/components/InterviewWidget/InterviewWidget.tsx:1-188`
- Test: `frontend/src/components/InterviewWidget/InterviewWidget.test.tsx`

**Interfaces:**
- Consumes: `interviewsApi.start(workspaceId, artifactType, sessionKind?) => Promise<InterviewState>`; `useNavigate()`, `useLocation()` from `react-router-dom`
- Produces: unchanged export `InterviewWidget(): JSX.Element`; `safeLocalStorage` stays exported (it is asserted on in the existing tests)

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/components/InterviewWidget/InterviewWidget.test.tsx` (reuse the file's existing render helper and `interviewsApi` mock; read lines 1-50 for the exact names):

```tsx
describe("InterviewWidget as a launcher", () => {
  it("navigates to the session detail route after starting", async () => {
    vi.mocked(interviewsApi.start).mockResolvedValue({ id: "s-new" } as any);

    renderWidget();
    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-Requirement"));

    await waitFor(() =>
      expect(screen.getByTestId("current-path")).toHaveTextContent("/interviews/s-new")
    );
  });

  it("closes the panel after starting a session", async () => {
    vi.mocked(interviewsApi.start).mockResolvedValue({ id: "s-new" } as any);

    renderWidget();
    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-Requirement"));

    await waitFor(() =>
      expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument()
    );
  });

  it("labels the panel for assistive technology", () => {
    renderWidget();
    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    expect(screen.getByTestId("interview-widget-panel")).toHaveAttribute("aria-label");
  });
});
```

The widget currently renders outside a router in this test file. Extend its render helper to wrap in `<MemoryRouter>` plus a location probe:

```tsx
function LocationProbe(): JSX.Element {
  const location = useLocation();
  return <span data-testid="current-path">{location.pathname}</span>;
}

function renderWidget(): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={["/requirements"]}>
      <InterviewWidget />
      <LocationProbe />
    </MemoryRouter>
  );
}
```

Add `import { MemoryRouter, useLocation } from "react-router-dom";` and route the file's existing render calls through `renderWidget()`.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/InterviewWidget/InterviewWidget.test.tsx"`
Expected: FAIL — path stays `/requirements` and the panel stays open

- [ ] **Step 3: Write minimal implementation**

Replace the body of `frontend/src/components/InterviewWidget/InterviewWidget.tsx` from the imports down, keeping `STORAGE_KEY` and `safeLocalStorage` exactly as they are:

```tsx
/**
 * Interview-management launcher — floating toggle shell.
 *
 * A `position: fixed` overlay, always mounted (via NavigationShell) on every
 * authenticated route. Toggle state persists in localStorage, same pattern as
 * ThemeContext's preference storage.
 *
 * Scope (audit finding L2.5): this is a QUICK ENTRY POINT ONLY. Picking a type
 * (or "not sure yet") starts a session and redirects to `/interviews/{id}`,
 * which is the single full interview surface — list, transcript, formalize,
 * abandon. The widget deliberately no longer renders a chat pane of its own:
 * two independently maintained implementations of the same chat flow was the
 * finding. `InterviewChatPane`/`InterviewArtifactPane` stay in this folder
 * because `InterviewEditors/InterviewDetail.tsx` imports them.
 *
 * WRITE-gate note: WorkspaceContext exposes no currentUserRole-like field yet,
 * so all nine start buttons stay visible for every authenticated user — a
 * deliberate scope-out until a role field exists on the workspace payload.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { interviewsApi } from "../../api/interviews";
import { INTERVIEW_ARTIFACT_TYPES } from "../../constants/interviewArtifactTypes";
import { Spinner } from "../shared/Spinner/Spinner";
import styles from "./InterviewWidget.module.css";
```

State and handlers:

```tsx
export function InterviewWidget(): JSX.Element {
  const { activeWorkspace } = useWorkspace();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    setOpen(safeLocalStorage.getItem(STORAGE_KEY) === "true");
  }, []);

  // Spec §6: the popover closes on navigation. An overlay that stays open
  // across page changes and covers forms was the S19 finding.
  useEffect(() => {
    setOpen(false);
    safeLocalStorage.setItem(STORAGE_KEY, "false");
  }, [location.pathname]);

  const toggle = (): void => {
    const next = !open;
    setOpen(next);
    safeLocalStorage.setItem(STORAGE_KEY, String(next));
  };

  /** Start a session and hand off to the full interview surface. */
  const startAndOpen = async (artifactType: string | null): Promise<void> => {
    if (!activeWorkspace) return;
    setStarting(true);
    try {
      const state = await interviewsApi.start(
        activeWorkspace.id,
        artifactType,
        artifactType === null ? "multi" : "single"
      );
      navigate(`/interviews/${state.id}`);
    } finally {
      setStarting(false);
    }
  };

  if (!activeWorkspace) return <></>;
```

Render — the toggle button stays byte-for-byte as it is today; the panel loses the `session ? ... : ...` branch and gains a label:

```tsx
      {open && (
        <div
          id="interview-widget-panel"
          data-testid="interview-widget-panel"
          className={styles.panel}
          aria-label={t("interviews.newInterviewDescription")}
        >
          <div className={styles.startRow}>
            {INTERVIEW_ARTIFACT_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                data-testid={`interview-widget-start-${type}`}
                className={styles.startButton}
                disabled={starting}
                onClick={() => void startAndOpen(type)}
              >
                {starting ? <Spinner /> : t(`interview.start.${type}`)}
              </button>
            ))}
            {/* Discovery entry point for users who don't know yet which
                artifact type they need. */}
            <button
              type="button"
              data-testid="interview-widget-start-multi"
              className={styles.startButton}
              disabled={starting}
              onClick={() => void startAndOpen(null)}
            >
              {starting ? <Spinner /> : t("interview.multiEntry")}
            </button>
          </div>
        </div>
      )}
```

Delete the now-unused `InterviewChatPane` / `InterviewArtifactPane` / `InterviewState` imports and the `session` / `sessionKind` state. Do NOT delete the pane files.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/InterviewWidget/ && npx tsc --noEmit && npx eslint src/components/InterviewWidget"`
Expected: PASS, no type errors, no lint findings

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/InterviewWidget/InterviewWidget.tsx frontend/src/components/InterviewWidget/InterviewWidget.test.tsx
git commit -m "refactor(interview): reduce widget to a launcher for /interviews"
```

---

## Task 15 (BLOCKED): GlossaryTerm interviews

**Blocked by:** `docs/superpowers/specs/2026-09-03-datenmodell-konsolidierung-design.md` §4 — `GlossaryTerm` must get an `artifact` OneToOne FK to `persistence.Artifact` first. Verified 2026-09-03: `backend/persistence/models.py:1833` has no such field, and `_glossary_term` in `interview_artifact_adapters.py:108-116` rejects every creation for exactly that reason. Do not start this task until `GlossaryTerm.artifact` exists and is populated.

**Files:**
- Modify: `backend/application/interview_artifact_adapters.py:108-116`
- Modify: `backend/application/interview_protocol.py:24-33` (`IN_SCOPE_ARTIFACT_TYPES`)
- Test: `backend/application/tests/test_interview_artifact_adapters.py:122-131`

**Interfaces:**
- Consumes: `GlossaryService().create(...)` returning an object with an `artifact_id` attribute (this is the part the blocking spec must deliver)
- Produces: `ARTIFACT_CREATION_ADAPTERS["GlossaryTerm"]` returning a real `CreatedArtifactRef`

- [ ] **Step 1: Write the failing test**

Replace `test_glossary_term_adapter_rejects_even_for_editor` in `backend/application/tests/test_interview_artifact_adapters.py` with:

```python
    def test_glossary_term_adapter_normalizes_orm_object(self):
        fake_ctx = MagicMock()
        fake_term = MagicMock(artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.GlossaryService.create",
            return_value=fake_term,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["GlossaryTerm"](
                {"term": "Baseline", "definition": "A frozen snapshot."}, fake_ctx, "ws-1"
            )
        mocked.assert_called_once_with(
            workspace_id="ws-1", ctx=fake_ctx, term="Baseline", definition="A frozen snapshot."
        )
        assert ref == CreatedArtifactRef(
            artifact_id=fake_term.artifact_id, artifact_type="GlossaryTerm"
        )
```

and add to `application/tests/test_interview_protocol.py`:

```python
    def test_glossary_term_is_in_scope(self):
        from application.interview_protocol import IN_SCOPE_ARTIFACT_TYPES

        assert "GlossaryTerm" in IN_SCOPE_ARTIFACT_TYPES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_artifact_adapters.py application/tests/test_interview_protocol.py -v`
Expected: FAIL — `ValidationError: GlossaryTerm is not Artifact-backed yet ...` and `AssertionError` on the scope test

- [ ] **Step 3: Write minimal implementation**

Replace `_glossary_term` in `backend/application/interview_artifact_adapters.py`:

```python
def _glossary_term(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = GlossaryService().create(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(artifact_id=obj.artifact_id, artifact_type="GlossaryTerm")
```

Verify `GlossaryService.create`'s real signature before writing this (the blocking spec may rename or reorder kwargs) and adjust the test's `assert_called_once_with` to match. Add `"GlossaryTerm",` to `IN_SCOPE_ARTIFACT_TYPES` in `interview_protocol.py` and update the module docstring at `interview_artifact_adapters.py:13-16`, which still says "plus explicit GlossaryTerm rejection".

Add a `_EXTRA_REQUIRED_FIELDS["GlossaryTerm"]` entry if `GlossaryService.create` requires `definition` without a default — check the signature; if it does, the entry is:

```python
    "GlossaryTerm": (
        "      - name: definition\n"
        "        type: textarea\n"
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests/test_interview_artifact_adapters.py application/tests/test_interview_protocol.py application/tests/test_interview_formalize_multi.py -v`
Expected: PASS (note: `test_interview_formalize_multi.py` has a scenario named `test_viewer_cannot_smuggle_glossary_term_through_multi_formalize` — its WRITE-permission assertion must still hold, only the type-based rejection goes away)

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_artifact_adapters.py backend/application/interview_protocol.py backend/application/tests/test_interview_artifact_adapters.py backend/application/tests/test_interview_protocol.py
git commit -m "feat(interview): create GlossaryTerm through the adapter registry"
```

---

## Final verification (after Task 14; Task 15 stays open)

- [ ] **Backend, all interview modules:**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=reqlo_iv backend-test pytest application/tests -k "interview" persistence/tests -k "interview" rest_api/tests -k "interview" mcp_server/tests -k "interview" -v --create-db`
Expected: PASS

- [ ] **Frontend, all touched suites:**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run src/components/InterviewWidget src/components/InterviewEditors src/components/shared/InterviewProvenanceBadge.test.tsx src/test --testTimeout=30000"`
Expected: PASS (roughly 14 pre-existing local vitest failures unrelated to interviews are a known local-only baseline — compare against a clean checkout before treating any as a regression)

- [ ] **Manual browser check (the spec's core claim):**

```bash
make up
docker-compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . restart frontend
```

Then, logged in: open the widget → "Risk" → land on `/interviews/{id}` → answer title, rationale, probability, impact → Formalize → a real Risk exists on `/risks` and shows the "Angelegt via Interview" badge that links back to the session. This is the exact flow audit finding R6 proved impossible.
