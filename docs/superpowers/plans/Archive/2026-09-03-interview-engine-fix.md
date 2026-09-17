# Interview-Engine-Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four interview-engine gaps L2.1/L2.3/L2.4/L2.5 — make `formalize()` work for all 8 in-scope artifact types by routing the single-kind path through the already-productive `ARTIFACT_CREATION_ADAPTERS` registry, make interview provenance visible on every artifact, cap the unbounded chat transcript, and reduce the floating widget to a quick entry point so `/interviews` is the single full interview surface.

**Architecture:** No new subsystem. L2.1 deletes a hardcoded `if session.artifact_type != "Requirement": raise` and dispatches through the existing 9-entry adapter registry — the registry gains one field (`entity_id`) so the single path can keep its issue-#736 "return the subtype id, not the Artifact PK" contract while the multi path keeps using `artifact_id` for provenance rows and TraceLinks. L2.3 mounts the existing `InterviewProvenanceBadge` in the one shared `RightSidebar` shell every artifact detail view already renders (one mount site, not eight), and makes the single path write the `InterviewSessionArtifact` provenance row the badge reads. L2.4 adds `InterviewSession.transcript_summary` plus a sliding-window compressor with a best-effort LLM call. L2.5 turns the widget into a picker that navigates to the already-existing `/interviews?start=<Type>` auto-start route and deletes its session-hosting code.

**Tech Stack:** Python 3.x / Django 5.2 (1 schema migration, no data migration), DRF (docstring/description updates only, no endpoint changes), MCP (2 tool-description updates), React 18 + TS strict (1 shared-shell mount, 1 widget reduction), i18n de/en. No new runtime dependency.

**Spec:** docs/superpowers/specs/2026-09-03-interview-engine-fix-design.md

## Global Constraints

- **`ARTIFACT_CREATION_ADAPTERS` is the single artifact-creation seam for interviews.** Both `_formalize_single` and `_formalize_multi` dispatch through it after this plan. No second creation path, no per-type `if` in `interview_service.py`.
- **Every adapter MUST call the production `create_X()` service method** — never a shortcut insert. That is what keeps workflow-state initialization correct for free (module docstring, `backend/application/interview_artifact_adapters.py:3-6`).
- **8 in-scope artifact types, exactly:** `Requirement`, `ArchitectureElement`, `StakeholderNeed`, `Risk`, `TestCase`, `Adr`, `Issue`, `Goal` (`IN_SCOPE_ARTIFACT_TYPES`, `backend/application/interview_protocol.py:24-33`). `MainGoal` stays out of scope (no MCP write tools exist for it). `GlossaryTerm` is a 9th registry entry that deliberately **rejects** with a `ValidationError`.
- **`CreatedArtifactRef.artifact_id` is ALWAYS the `persistence.Artifact` PK** — the FK target of `InterviewSessionArtifact.artifact` and both `TraceLink` endpoints. Task 1 adds `entity_id` (the user-facing subtype id) next to it; the two are distinct UUIDs and must never be conflated.
- **`resulting_artifact_ids` carries the subtype id, not the Artifact PK** (issue #736 — the id `RequirementService.get_requirement()` resolves). This contract must survive the L2.1 rewrite for `Requirement` and is extended verbatim to the other 7 types.
- **`formalize()`'s *update* branch (`target_artifact_id` set) stays `Requirement`-only.** The spec's L2.1 fix is about the *create* path. Generalizing updates needs a second (update) adapter registry and is explicitly out of scope; `set_target()`'s existing guard (`interview_service.py:756`) therefore stays, its message only gets corrected.
- **Malformed adapter input must never escape as a 500.** `KeyError` (missing required field, e.g. Risk without `probability`) and `TypeError` (field name the `create_X()` signature does not accept) are converted to `ValidationError` — the same conversion `_formalize_multi` already does at `interview_service.py:1018-1030`.
- **`probability` / `impact` choices are exactly `low` / `medium` / `high`** (`Risk.Probability` / `Risk.Impact`, `backend/application/models.py`). `RiskService.create_risk` has no default for either.
- **The transcript window is `TRANSCRIPT_WINDOW_TURNS = 10` turns = 20 transcript entries** (one turn writes a `user` and an `assistant` entry — see `interview_service.py:1271-1275`). A fixed constant, never a setting (spec §5: YAGNI).
- **Transcript compression must never block a chat turn.** Provider unavailable or `complete()` raising ⇒ log at debug, leave `transcript` uncompressed, retry on the next turn. No data loss, only deferred compression (spec §7).
- **Compression runs AFTER the turn is persisted**, so a compression failure can never lose the turn that triggered it.
- **DRF views must not touch the ORM.** `backend/rest_api/` has a ratchet that counts `.objects.` occurrences *including inside docstrings*. All reads/writes go through a Layer-2 service.
- **Every DRF view calls `get_auth_context(request)`**, which sets the tenant context. Never query without it — RLS returns an empty set.
- **No inline styles in `frontend/src/components/`.** A UI ratchet fails on new `style={{`. Use CSS modules + custom properties from `frontend/src/styles/tokens.css`.
- **`data-testid` on every interactive element.** Never hand-roll a confirm dialog — use `frontend/src/components/shared/ConfirmDialog.tsx`.
- **Named exports only** (React components are PascalCase files, Python is snake_case — preserve the existing naming, do not rename files).
- **Vite has no working HMR on Windows.** After every frontend edit, restart the frontend container before any browser/E2E check, or you are testing stale code.
- **Migration number below is the next free one as of 2026-09-04** (`backend/persistence/migrations/` ends at `0069_align_embedding_dimensions.py`). Specs 1–4 of the audit series land first and will consume numbers. Before `makemigrations`, run `ls backend/persistence/migrations/ | tail -3` and use the next free prefix. The migration *content* is unaffected.
- **Local test runs are scoped.** Run only the modules touched plus their direct dependents. The full backend suite (20–35 min sequential) is CI's job. A full unfiltered Playwright run requires explicit user approval — targeted `--grep` checks do not.

### Commands used throughout

Backend test (a unique `DB_NAME` prevents collisions with a concurrent run sharing `test_reqogniloom`):

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest <path> -v
```

Frontend test:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run <path> --testTimeout=30000"
```

Migrations (the DB **owner** role is required for DDL; the compose backend service already uses `DB_USER=reqogniloom`):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py makemigrations persistence --name interview_transcript_summary
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
```

Frontend container restart (mandatory after every frontend edit before a browser check):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . restart frontend
```

---

## Spec-Verification Findings (read before Task 1)

These were verified against the live tree at `chore/archive-implemented-specs-plans`. The spec is accurate on its two central claims and wrong on two secondary ones. Each finding is resolved inside a task below — nothing here is left open.

| # | Spec claim | Reality | Resolution |
|---|---|---|---|
| V1 | `application/interview_artifact_adapters.py` holds `ARTIFACT_CREATION_ADAPTERS` covering 8 types + `GlossaryTerm` rejection | **CONFIRMED.** `interview_artifact_adapters.py:119-129`, 9 entries, `_glossary_term` raises `ValidationError` at line 113. | — |
| V2 | Hardcoded `if session.artifact_type != "Requirement"` guard at `interview_service.py:839` with the "only Requirement is wired in this plan" message | **CONFIRMED, verbatim.** `interview_service.py:839-844`. Two sibling Requirement-only guards also exist: `:756` (`set_target`) and `:456` (`_structural_candidates`). | Task 5 removes `:839`. `:756` stays by design (Global Constraints), message corrected in Task 7. `:456` is a grounding pre-filter, out of scope for this spec. |
| V3 | Spec §5: "der Single-Kind-Pfad ruft für `session.artifact_type` denselben Adapter auf" | **INCOMPLETE.** The multi path feeds adapters LLM-proposed `fields` already shaped to the `create_X()` signature. The single path holds `collected_fields`, shaped by the *protocol* — factory default is `{title, rationale}` for all 8 types. `rationale` is not a kwarg on **any** `create_X()` ⇒ `TypeError`; `Risk` additionally needs `probability`/`impact` ⇒ `KeyError`. A naive `adapter(session.collected_fields, ...)` fails for every type. | Task 3 (`build_adapter_fields`) + Task 4 (Risk protocol default). |
| V4 | — (not claimed) | **BUG FOUND.** `_architecture_element` is only ever exercised through `patch(...)`-mocked tests (`test_interview_artifact_adapters.py:63-77`), which accept any kwargs. The real `create_architecture_element` signature takes `title`, not `name`. The existing test asserts `name="Sensor Unit"` — a false positive; a real multi-mode `ArchitectureElement` proposal built from `{"name": ...}` raises `TypeError`. | Task 2. |
| V5 | Spec §4: badge visible "wenn `provenance_session_id()` für das Artefakt einen Treffer liefert" | **DEAD FOR SINGLE MODE.** `provenance_session_id` (`interview_service.py:1470-1493`) only reads `InterviewSessionArtifact`, which **only `_formalize_multi` writes**. Single-mode artifacts — the majority path — would never show a badge. | Task 8. |
| V6 | — (not claimed) | **ID-SPACE MISMATCH.** `provenance_session_id` filters on the Artifact PK. Every artifact detail view passes the *subtype* id (`RequirementEditors.tsx:723` `artifactId={requirement.id}`). The badge would never match. | Task 9 (reuse `TraceLinkService.resolve_entity_to_artifact_id`, the existing public 10-type bridge). |
| V7 | Spec §4: mount the badge "in jeden Artefakt-Editor-`PageHeader`" | **WRONG SEAM.** `PageHeader` in those editors is the *list* route header (title + count) — it has no single artifact. The shared artifact-detail shell is `components/shared/ArtifactInspector/RightSidebar.tsx`, already rendered by all 8 editors plus Glossary/Diagram/ICD/Goals, and it already receives `artifactId`. | Task 10 mounts once in `RightSidebar` instead of eight times in `PageHeader`. |
| V8 | Spec §1 L2.5: widget and `/interviews` "teilen keine Komponenten außer der API — zwei vollständige, unabhängig gepflegte Implementierungen desselben Chat-Flows" | **FALSE.** `InterviewDetail.tsx:20-21` imports `InterviewChatPane` **and** `InterviewArtifactPane` from `../InterviewWidget/`. There is exactly **one** chat implementation, reused by two hosts. The real duplication is only the widget's *hosting* of a full session. | L2.5 shrinks to Tasks 15–17 (widget stops hosting sessions). No component extraction needed — it already happened. |
| V9 | Spec §6: "Per Interview erstellen" leads "wie heute auf die Interviews-Liste" | **ALREADY FIXED.** `useInterviewStartCta.ts:48` navigates to `/interviews?start=<Type>`; `InterviewEditors.tsx:74-82` auto-starts and `navigate`s to `/interviews/{id}`. Exactly the behaviour the spec asks for. | No task. Documented here so no one "fixes" it again. |
| V10 | Spec §6: widget has a "Popover-Typauswahl" with an S19 `aria-label` fix | **NO POPOVER EXISTS.** The widget is a `position: fixed` panel (`InterviewWidget.module.css`) toggled by a FAB that already carries a translated, state-aware `aria-label` (`InterviewWidget.tsx:119-126`). | Task 16 keeps the existing panel + FAB and only removes the session-hosting branch. "Closes on navigation" is satisfied for free: after Task 16 the panel's only action navigates away and clears its own state. |
| V11 | Spec §3: `GlossaryTerm` blocked until Datenmodell-Konsolidierung §4 delivers Artifact-backing | **CONFIRMED BLOCKED.** `persistence/models.py:1833-1856` — `GlossaryTerm` has `workspace`, `term`, `definition`, `synonyms`, `abbreviation`, `version`, `lifecycle_status`. No `artifact` FK. Latest migration is `0069`; no Artifact-backing migration exists. | Task 18, marked BLOCKED. |

**OFFENE FRAGE:** none. Every ambiguity above was resolved with a documented decision inside its task.

---

## File Structure

```
backend/
  application/
    interview_artifact_adapters.py               MODIFY  +entity_id on CreatedArtifactRef, fix _architecture_element,
                                                         +build_adapter_fields(), +GlossaryTerm entry (Task 18, blocked)
    interview_protocol.py                        MODIFY  _default_protocol_yaml() becomes per-type (Risk gets probability/impact)
    interview_service.py                         MODIFY  _formalize_single via registry, +provenance row,
                                                         +_compress_transcript_if_needed(), provenance_session_id id-space bridge
    ai_derivation_service.py                     MODIFY  +INTERVIEW_TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE, +transcript_summary slot
    prompt_slots.py                              MODIFY  +interview.transcript_summary, +transcript_summary on interview.chat_turn
    tests/
      test_interview_artifact_adapters.py        MODIFY  signature-binding assertions, entity_id assertions
      test_interview_service.py                  MODIFY  invert test_formalize_for_non_requirement_type_raises_validation_error
      test_interview_formalize_all_types.py      CREATE  7 new per-type regression tests
      test_interview_provenance.py               CREATE  single-mode provenance row + id-space bridge
      test_interview_transcript_cap.py           CREATE  window/compression/fallback
      test_interview_protocol.py                 MODIFY  Risk default protocol assertions
  persistence/
    models.py                                    MODIFY  +InterviewSession.transcript_summary
    migrations/
      00XX_interview_transcript_summary.py       CREATE  AddField (number: next free, see Global Constraints)
  mcp_server/
    tools/interview.py                           MODIFY  formalize/set_target tool descriptions

frontend/
  src/
    components/
      shared/
        InterviewProvenanceBadge.tsx             MODIFY  link to /interviews/{sessionId}, styled span+link
        InterviewProvenanceBadge.module.css      CREATE  badge geometry (no inline styles)
        InterviewProvenanceBadge.test.tsx        MODIFY  asserts the session-scoped href
        ArtifactInspector/
          RightSidebar.tsx                       MODIFY  render <InterviewProvenanceBadge artifactId={artifactId}/>
          RightSidebar.test.tsx                  MODIFY  badge-mount assertion
      InterviewEditors/
        InterviewEditors.tsx                     MODIFY  accept ?start=multi
        InterviewEditors.test.tsx                MODIFY  ?start=multi test
      InterviewWidget/
        InterviewWidget.tsx                      MODIFY  picker-only: navigate to /interviews?start=...
        InterviewWidget.test.tsx                 MODIFY  navigation assertions replace session assertions
    i18n/locales/de.json                         MODIFY  +interview.widget.hint, +interviews.provenance*
    i18n/locales/en.json                         MODIFY  same keys
```

**Deliberately NOT done** (recorded so nobody re-opens it):
- `InterviewChatPane` / `InterviewArtifactPane` / `ProposalPreviewGraph` are **not** moved out of `components/InterviewWidget/`. After Task 16 their only host is `InterviewEditors/InterviewDetail.tsx`, so the folder name is mildly stale — but a move is pure churn across four test files and their import paths, with zero behaviour change. Move them when the folder is otherwise emptied.
- No update-adapter registry (see Global Constraints).
- No `Memory`-system wiring for `transcript_summary` (spec §5 explicitly defers that to a Kap.-M spec).

---

## Phase A — L2.1: Single-Kind-Formalize through the adapter registry

### Task 1: `CreatedArtifactRef.entity_id` — the user-facing id next to the Artifact PK

**Why:** adapters return the Artifact PK. `_formalize_single` must keep returning the *subtype* id in `resulting_artifact_ids` (issue #736, asserted by `test_interview_service.py:532-542`). Every service already returns an object/dict carrying both ids, so one extra field removes the whole conflict — no lookup, no id-space guessing at the call site.

**Files:**
- Modify: `backend/application/interview_artifact_adapters.py:37-41` (dataclass), `:44-105` (all 8 adapters)
- Test: `backend/application/tests/test_interview_artifact_adapters.py`

**Interfaces:**
- Produces: `CreatedArtifactRef(artifact_id: UUID, artifact_type: str, entity_id: UUID)` — `artifact_id` = `persistence.Artifact` PK, `entity_id` = the subtype row id (`Requirement.id`, `Goal` version-row `id`, …).

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_artifact_adapters.py`:

```python
    def test_requirement_adapter_carries_both_id_spaces(self):
        fake_ctx = MagicMock()
        fake_requirement = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.RequirementService.create_requirement",
            return_value=fake_requirement,
        ):
            ref = ARTIFACT_CREATION_ADAPTERS["Requirement"]({"title": "T"}, fake_ctx, "ws-1")
        # The two ids are distinct UUIDs (Requirement.artifact is a
        # OneToOneField with its own pk) -- provenance rows/TraceLinks use
        # artifact_id, resulting_artifact_ids uses entity_id (issue #736).
        assert ref.artifact_id == fake_requirement.artifact_id
        assert ref.entity_id == fake_requirement.id
        assert ref.artifact_id != ref.entity_id

    def test_goal_adapter_entity_id_is_the_version_row_id(self):
        fake_ctx = MagicMock()
        goal_artifact_id = uuid.uuid4()
        goal_version_id = uuid.uuid4()
        with patch(
            "application.interview_artifact_adapters.GoalService.create_version",
            return_value={
                "id": goal_version_id,
                "artifact_id": goal_artifact_id,
                "title": "G",
            },
        ):
            ref = ARTIFACT_CREATION_ADAPTERS["Goal"]({"title": "G"}, fake_ctx, "ws-1")
        assert ref.artifact_id == goal_artifact_id
        assert ref.entity_id == goal_version_id
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_artifact_adapters.py -k both_id_spaces -v
```
Expected: FAIL with `TypeError: CreatedArtifactRef.__init__() got an unexpected keyword argument 'entity_id'` — or `AttributeError: 'CreatedArtifactRef' object has no attribute 'entity_id'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/application/interview_artifact_adapters.py`, replace the dataclass:

```python
@dataclass(frozen=True)
class CreatedArtifactRef:
    # Always the persistence.Artifact PK -- see module docstring contract.
    # Consumed by InterviewSessionArtifact.artifact and both TraceLink endpoints.
    artifact_id: UUID
    artifact_type: str
    # The user-facing subtype row id (Requirement.id, Goal version-row id, ...).
    # Distinct UUID from artifact_id. This is what formalize() reports in
    # resulting_artifact_ids (issue #736): the id requirement.get()/
    # RequirementService.get_requirement() resolve.
    entity_id: UUID
```

Then set `entity_id` in all 8 adapters (`_glossary_term` still only raises):

```python
def _requirement(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = RequirementService().create_requirement(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="Requirement", entity_id=obj.id
    )


def _stakeholder_need(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    dto = StakeholderNeedService().create(ctx=ctx, workspace_id=workspace_id, **fields)
    return CreatedArtifactRef(
        artifact_id=dto.artifact_id, artifact_type="StakeholderNeed", entity_id=dto.id
    )


def _architecture_element(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = ArchitectureService().create_architecture_element(
        workspace_id=workspace_id, ctx=ctx, **fields
    )
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="ArchitectureElement", entity_id=obj.id
    )


def _risk(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = RiskService().create_risk(
        workspace_id=workspace_id,
        title=fields["title"],
        probability=fields["probability"],
        impact=fields["impact"],
        ctx=ctx,
        **{k: v for k, v in fields.items() if k not in ("title", "probability", "impact")},
    )
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="Risk", entity_id=obj.id
    )


def _test_case(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = TestService().create_test_case(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="TestCase", entity_id=obj.id
    )


def _adr(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = AdrService().create_adr(
        workspace_id=workspace_id,
        title=fields["title"],
        description=fields["description"],
        ctx=ctx,
        **{k: v for k, v in fields.items() if k not in ("title", "description")},
    )
    return CreatedArtifactRef(artifact_id=obj.artifact_id, artifact_type="Adr", entity_id=obj.id)


def _issue(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = IssueService().create_issue(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="Issue", entity_id=obj.id
    )


def _goal(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    result = GoalService().create_version(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(
        artifact_id=result["artifact_id"], artifact_type="Goal", entity_id=result["id"]
    )
```

- [ ] **Step 4: Fix the four existing tests that construct `CreatedArtifactRef` positionally**

`test_interview_artifact_adapters.py` lines 34-36, 47-49, 61, 75-77, 88-90, 107, 118-120 compare against a 2-field `CreatedArtifactRef`. Give each fake an explicit `id` and add `entity_id` to the expectation. Example for the Requirement case:

```python
    def test_requirement_adapter_normalizes_orm_object(self):
        fake_ctx = MagicMock()
        fake_requirement = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.RequirementService.create_requirement",
            return_value=fake_requirement,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["Requirement"]({"title": "T"}, fake_ctx, "ws-1")
        mocked.assert_called_once_with(workspace_id="ws-1", ctx=fake_ctx, title="T")
        assert ref == CreatedArtifactRef(
            artifact_id=fake_requirement.artifact_id,
            artifact_type="Requirement",
            entity_id=fake_requirement.id,
        )
```

Apply the same shape to `test_stakeholder_need_adapter_normalizes_dto`, `test_goal_adapter_normalizes_dict_return` (add `entity_id=<the "id" value>`), `test_architecture_element_adapter_normalizes_orm_object`, `test_test_case_adapter_normalizes_orm_object`, `test_adr_adapter_normalizes_orm_object`, `test_issue_adapter_normalizes_orm_object`.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_artifact_adapters.py -v
```
Expected: PASS (all tests, old and new).

- [ ] **Step 6: Verify no other consumer breaks on the new required field**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test sh -c "grep -rn 'CreatedArtifactRef(' --include=*.py . | grep -v interview_artifact_adapters.py"
```
Expected: only `application/tests/test_interview_artifact_adapters.py` matches (the frontend has a same-named but unrelated TS interface in `InterviewChatPane.tsx:42` — it is a wire-format type with `artifact_id`/`artifact_type` only and is **not** affected).

- [ ] **Step 7: Commit**

```bash
git add backend/application/interview_artifact_adapters.py backend/application/tests/test_interview_artifact_adapters.py
git commit -m "refactor: carry both id spaces on CreatedArtifactRef"
```

---

### Task 2: Fix the `ArchitectureElement` adapter's wrong kwarg and make adapter tests signature-binding

**Why (finding V4):** every adapter test patches the service method with a bare `MagicMock`, which accepts any kwargs — so a wrong kwarg name is invisible. `ArchitectureService.create_architecture_element` takes `title`, and the adapter's test asserts `name=`. Fix the contract *and* the blind spot, otherwise Task 5 inherits it.

**Files:**
- Modify: `backend/application/interview_artifact_adapters.py:54-58`
- Modify: `backend/application/tests/test_interview_artifact_adapters.py:63-77`

**Interfaces:**
- Consumes: `CreatedArtifactRef(..., entity_id=...)` from Task 1.
- Produces: `ARTIFACT_CREATION_ADAPTERS["ArchitectureElement"]` that binds against the real `create_architecture_element` signature.

- [ ] **Step 1: Write the failing test**

Replace `test_architecture_element_adapter_normalizes_orm_object` in `backend/application/tests/test_interview_artifact_adapters.py` with:

```python
    def test_architecture_element_adapter_uses_the_real_signature(self):
        """A bare MagicMock accepts any kwargs, so a wrong field name (this
        adapter passed `name=`, the service takes `title=`) stayed invisible.
        `autospec=True` makes the patch bind against the real signature, so a
        kwarg the service does not accept raises TypeError here."""
        fake_ctx = MagicMock()
        fake_element = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters."
            "ArchitectureService.create_architecture_element",
            autospec=True,
            return_value=fake_element,
        ) as mocked:
            ref = ARTIFACT_CREATION_ADAPTERS["ArchitectureElement"](
                {"title": "Sensor Unit"}, fake_ctx, "ws-1"
            )
        _instance, kwargs = mocked.call_args[0], mocked.call_args[1]
        assert kwargs == {"workspace_id": "ws-1", "ctx": fake_ctx, "title": "Sensor Unit"}
        assert ref == CreatedArtifactRef(
            artifact_id=fake_element.artifact_id,
            artifact_type="ArchitectureElement",
            entity_id=fake_element.id,
        )

    def test_architecture_element_adapter_rejects_unknown_field_name(self):
        """`name` is not a create_architecture_element kwarg -- with autospec
        the mismatch surfaces as TypeError, which _formalize_single/_multi
        convert into a clean ValidationError (never a 500)."""
        fake_ctx = MagicMock()
        with patch(
            "application.interview_artifact_adapters."
            "ArchitectureService.create_architecture_element",
            autospec=True,
        ):
            with pytest.raises(TypeError):
                ARTIFACT_CREATION_ADAPTERS["ArchitectureElement"](
                    {"name": "Sensor Unit"}, fake_ctx, "ws-1"
                )
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_artifact_adapters.py -k architecture_element -v
```
Expected: `test_architecture_element_adapter_uses_the_real_signature` FAILS. (The adapter body itself is already correct — it forwards `**fields` — so the failure is in the *old* test's `name=` expectation being replaced; run this step to confirm both new tests execute and the second one passes only once autospec is in place.)

- [ ] **Step 3: Write minimal implementation**

The adapter body needs only a corrected docstring — `**fields` already forwards whatever `build_adapter_fields` (Task 3) produces. Replace `_architecture_element` in `backend/application/interview_artifact_adapters.py`:

```python
def _architecture_element(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # ArchitectureService.create_architecture_element takes `title`, NOT
    # `name` -- the pre-existing test asserted `name=` against a bare
    # MagicMock, which accepts anything, so the mismatch was a false green.
    # Callers (build_adapter_fields / a multi-mode proposal) must supply
    # `title`; anything else raises TypeError, which both formalize paths
    # convert into a ValidationError.
    obj = ArchitectureService().create_architecture_element(
        workspace_id=workspace_id, ctx=ctx, **fields
    )
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="ArchitectureElement", entity_id=obj.id
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_artifact_adapters.py -v
```
Expected: PASS.

- [ ] **Step 5: Check the multi-mode prompt does not instruct the LLM to emit `name`**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test sh -c "grep -n 'name' application/interview_multi_protocol.py"
```
Expected: if the multi-protocol factory-default prompt shows an `ArchitectureElement` example using `"name"`, change that example to `"title"` in the same commit. If it does not mention it, no change.

- [ ] **Step 6: Commit**

```bash
git add backend/application/interview_artifact_adapters.py backend/application/tests/test_interview_artifact_adapters.py backend/application/interview_multi_protocol.py
git commit -m "fix: ArchitectureElement interview adapter used a non-existent kwarg"
```

---

### Task 3: `build_adapter_fields()` — protocol field names to service kwargs

**Why (finding V3):** `collected_fields` is keyed by *protocol* field names; adapters expect `create_X()` kwarg names. The factory-default protocol produces `{"title", "rationale"}` for all 8 types, and `rationale` is a kwarg on none of them. Today's `_formalize_single` hardcodes this mapping inline for Requirement (`interview_service.py:899` / `:914`, `description=session.collected_fields.get("rationale")`). Lift that one rename into the adapters module so all 8 types share it.

**Decision (documented, not a guess):** the mapping is **one rename plus pass-through**. `rationale → description`. Every other collected key is forwarded untouched — a workspace that overrides the protocol chooses its own field names, and a name the service does not accept surfaces as a `TypeError` that both formalize paths already convert into a clean `ValidationError`. Rejected alternative: deriving the accepted kwarg set via `inspect.signature` on a second per-type registry of target callables — more machinery, and it would *silently drop* a mistyped field instead of reporting it.

**Files:**
- Modify: `backend/application/interview_artifact_adapters.py` (append below the registry)
- Test: `backend/application/tests/test_interview_artifact_adapters.py`

**Interfaces:**
- Produces: `build_adapter_fields(collected_fields: dict) -> dict` — the kwargs dict to hand to an entry of `ARTIFACT_CREATION_ADAPTERS`.
- Consumed by: Task 5 (`_formalize_single`).

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_artifact_adapters.py`:

```python
from application.interview_artifact_adapters import build_adapter_fields  # noqa: E402


class TestBuildAdapterFields:
    def test_renames_rationale_to_description(self):
        assert build_adapter_fields({"title": "T", "rationale": "Because"}) == {
            "title": "T",
            "description": "Because",
        }

    def test_passes_unknown_protocol_fields_through_untouched(self):
        # A workspace-custom protocol picks its own field names; forwarding
        # them means a name the service accepts works, and a name it does not
        # accept raises TypeError -> ValidationError, rather than being
        # silently dropped.
        assert build_adapter_fields(
            {"title": "R", "probability": "high", "impact": "low"}
        ) == {"title": "R", "probability": "high", "impact": "low"}

    def test_explicit_description_wins_over_rationale(self):
        # If a protocol declares `description` directly, it is authoritative --
        # the rationale rename must not clobber it.
        assert build_adapter_fields(
            {"title": "A", "description": "Direct", "rationale": "Indirect"}
        ) == {"title": "A", "description": "Direct"}

    def test_empty_rationale_still_maps_to_empty_description(self):
        # create_requirement's own default is "" -- never None, which would
        # violate the NOT NULL on description.
        assert build_adapter_fields({"title": "T", "rationale": None}) == {
            "title": "T",
            "description": "",
        }

    def test_does_not_mutate_the_input(self):
        collected = {"title": "T", "rationale": "R"}
        build_adapter_fields(collected)
        assert collected == {"title": "T", "rationale": "R"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_artifact_adapters.py::TestBuildAdapterFields -v
```
Expected: FAIL with `ImportError: cannot import name 'build_adapter_fields' from 'application.interview_artifact_adapters'`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/application/interview_artifact_adapters.py`:

```python
# Protocol field name -> create_X() kwarg name. The factory-default interview
# protocol (interview_protocol._default_protocol_yaml) elicits `title` and
# `rationale` for every in-scope type, but `rationale` is a kwarg on none of
# the create_X() signatures -- every service calls that field `description`.
# _formalize_single used to do this rename inline for Requirement only; it
# lives here so all 8 types share exactly one mapping.
_PROTOCOL_FIELD_ALIASES = {"rationale": "description"}


def build_adapter_fields(collected_fields: dict) -> dict:
    """Translate an interview session's ``collected_fields`` into adapter kwargs.

    Applies :data:`_PROTOCOL_FIELD_ALIASES` and forwards everything else
    untouched. An explicitly collected target name always wins over an alias
    (a protocol that declares ``description`` directly is authoritative).

    Unknown keys are deliberately **not** filtered: a workspace-custom
    protocol chooses its own field names, so a key the target ``create_X()``
    does not accept must surface as a ``TypeError`` -- which both
    ``_formalize_single`` and ``_formalize_multi`` convert into a clean
    ``ValidationError`` naming the offending field -- rather than being
    silently dropped, which would create an artifact missing the answer the
    user actually gave.

    Args:
        collected_fields: ``InterviewSession.collected_fields``.

    Returns:
        A new dict; the input is never mutated.
    """
    fields = dict(collected_fields)
    for source, target in _PROTOCOL_FIELD_ALIASES.items():
        if source not in fields:
            continue
        value = fields.pop(source)
        if target in fields:
            continue
        # `or ""` mirrors every create_X() default: description is NOT NULL,
        # so an unanswered optional field must become "" and never None.
        fields[target] = value or ""
    return fields
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_artifact_adapters.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_artifact_adapters.py backend/application/tests/test_interview_artifact_adapters.py
git commit -m "feat: map interview protocol fields onto create_X kwargs"
```

---

### Task 4: Risk's factory-default protocol elicits `probability` and `impact`

**Why:** `RiskService.create_risk` requires `probability` and `impact` with no default. The current factory-default protocol is type-agnostic (`title` + `rationale`), so a `Risk` interview can never collect them and `formalize()` would raise `KeyError → ValidationError` on a session the user completed. `Adr` needs `description`, which the `rationale` alias from Task 3 already supplies. The other 6 types need nothing extra.

**Files:**
- Modify: `backend/application/interview_protocol.py:117-135`
- Test: `backend/application/tests/test_interview_protocol.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `INTERVIEW_PROTOCOL_DEFAULTS["interview.protocol.Risk"]` whose elicitation phase declares `probability` and `impact` as `enum` fields with choices `["low", "medium", "high"]`.

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_protocol.py` (inside the class that holds `test_every_in_scope_artifact_type_has_a_default`):

```python
    def test_risk_default_protocol_elicits_probability_and_impact(self):
        """RiskService.create_risk has no default for probability/impact, so
        the protocol must collect them or formalize() can never succeed for a
        Risk interview."""
        config = parse_protocol_yaml(INTERVIEW_PROTOCOL_DEFAULTS["interview.protocol.Risk"])
        elicitation = config.phases[0]
        by_name = {f.name: f for f in elicitation.required_fields}
        assert "title" in by_name
        assert by_name["probability"].type == "enum"
        assert by_name["probability"].choices == ["low", "medium", "high"]
        assert by_name["impact"].type == "enum"
        assert by_name["impact"].choices == ["low", "medium", "high"]

    def test_non_risk_defaults_keep_the_two_field_shape(self):
        """Only Risk needs extra fields; adding them everywhere would make
        every other interview longer for no reason."""
        config = parse_protocol_yaml(
            INTERVIEW_PROTOCOL_DEFAULTS["interview.protocol.Requirement"]
        )
        names = [f.name for f in config.phases[0].required_fields]
        assert names == ["title", "rationale"]
```

Make sure `parse_protocol_yaml` is imported in that test module (it already is, line 10 region — verify and add if missing).

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_protocol.py -k "probability or two_field_shape" -v
```
Expected: `test_risk_default_protocol_elicits_probability_and_impact` FAILS with `KeyError: 'probability'`.

- [ ] **Step 3: Write minimal implementation**

Replace `_default_protocol_yaml` in `backend/application/interview_protocol.py`:

```python
# Extra elicitation fields a type needs beyond title+rationale, because its
# create_X() service method declares them without a default. Keyed by
# artifact type; every type not listed keeps the two-field default.
#
# Risk: RiskService.create_risk(workspace_id, title, probability, impact, ctx)
# -- probability/impact have no default, so a Risk interview that never asks
# for them produces a session formalize() can only reject.
# Adr needs `description`, which the rationale -> description alias in
# interview_artifact_adapters.build_adapter_fields already supplies.
_EXTRA_REQUIRED_FIELDS: "dict[str, str]" = {
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
    title + rationale (+ any type-specific fields whose create_X() service
    method has no default, see _EXTRA_REQUIRED_FIELDS), then approval and
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
        f"{_EXTRA_REQUIRED_FIELDS.get(artifact_type, '')}"
        f"    prompt_fragment: \"Elicit the {artifact_type}'s title and rationale.\"\n"
        "  - name: approval\n"
        f"    prompt_fragment: \"Present the drafted {artifact_type} for approval.\"\n"
        "  - name: formalization\n"
        "    prompt_fragment: \"Confirm and formalize.\"\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_protocol.py -v
```
Expected: PASS — including the pre-existing `test_every_in_scope_artifact_type_has_a_default`, which re-parses every default and would catch a YAML indentation slip.

- [ ] **Step 5: Verify `answer()` accepts the enum values end to end**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_service.py -k "answer" -v
```
Expected: PASS. (`InterviewService._validate_field_value_type`, `interview_service.py:426-431`, rejects any enum value not in `choices` — the values `low`/`medium`/`high` match `Risk.Probability` / `Risk.Impact` exactly.)

- [ ] **Step 6: Commit**

```bash
git add backend/application/interview_protocol.py backend/application/tests/test_interview_protocol.py
git commit -m "feat: Risk interview protocol elicits probability and impact"
```

---

### Task 5: `_formalize_single` dispatches through `ARTIFACT_CREATION_ADAPTERS`

**Why:** this is the L2.1 fix. Delete `interview_service.py:839-844` and route the create branch through the registry.

**Files:**
- Modify: `backend/application/interview_service.py:832-965`
- Test: `backend/application/tests/test_interview_service.py:614-620` (invert the existing test)

**Interfaces:**
- Consumes: `ARTIFACT_CREATION_ADAPTERS`, `build_adapter_fields(collected_fields)`, `CreatedArtifactRef(artifact_id, artifact_type, entity_id)`.
- Produces: unchanged public shape `{"resulting_artifact_ids": list[str], "status": str}`; `resulting_artifact_ids` carries `entity_id` values.

- [ ] **Step 1: Write the failing test**

Replace `test_formalize_for_non_requirement_type_raises_validation_error` in `backend/application/tests/test_interview_service.py:614-620` with:

```python
    def test_formalize_for_risk_creates_a_real_risk(self, ctx, workspace):
        """L2.1: the single-kind path dispatches through
        ARTIFACT_CREATION_ADAPTERS, so every in-scope type formalizes -- not
        only Requirement. Risk is the strictest case: create_risk() has no
        default for probability/impact."""
        from application.risk_service import RiskService

        session = InterviewService().start(ctx, "Risk", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "Sensor drift")
        InterviewService().answer(ctx, session.id, "rationale", "Thermal expansion")
        InterviewService().answer(ctx, session.id, "probability", "high")
        InterviewService().answer(ctx, session.id, "impact", "medium")

        result = InterviewService().formalize(ctx, session.id)

        assert result["status"] == "completed"
        assert len(result["resulting_artifact_ids"]) == 1
        # resulting_artifact_ids carries the subtype id (issue #736), so the
        # type's own read service resolves it directly.
        risk = RiskService().get_risk(uuid.UUID(result["resulting_artifact_ids"][0]), ctx)
        assert risk.title == "Sensor drift"
        assert risk.probability == "high"
        assert risk.impact == "medium"

    def test_formalize_reports_missing_service_field_as_validation_error(
        self, ctx, workspace
    ):
        """A KeyError from an adapter (Risk without probability) must surface
        as a clean ValidationError naming the type, never as an unhandled
        500 -- same contract _formalize_multi already honours."""
        from persistence.models import InterviewSession as _Session

        session = InterviewService().start(ctx, "Risk", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "Incomplete")
        InterviewService().answer(ctx, session.id, "rationale", "why")
        InterviewService().answer(ctx, session.id, "probability", "high")
        InterviewService().answer(ctx, session.id, "impact", "low")
        # Drop `impact` behind the protocol's back, reproducing a stale
        # session whose workspace protocol was edited mid-interview.
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            row = _Session.objects.get(id=session.id)
            collected = dict(row.collected_fields)
            collected.pop("impact")
            _Session.objects.filter(id=session.id).update(collected_fields=collected)
        finally:
            TenantContext.clear_tenant()

        with pytest.raises(ValidationError) as excinfo:
            InterviewService().formalize(ctx, session.id)
        assert "Risk" in str(excinfo.value)

    def test_formalize_rejects_glossary_term_with_a_clear_message(self, ctx, workspace):
        """GlossaryTerm has no Artifact backing row yet (blocked on the
        Datenmodell-Konsolidierung spec); the registry rejects it explicitly
        rather than writing an unresolvable FK."""
        from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS

        assert "GlossaryTerm" in ARTIFACT_CREATION_ADAPTERS
        with pytest.raises(ValidationError) as excinfo:
            ARTIFACT_CREATION_ADAPTERS["GlossaryTerm"]({"title": "X"}, ctx, workspace.id)
        assert "GlossaryTerm" in str(excinfo.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_service.py -k "formalize_for_risk" -v
```
Expected: FAIL with `ValidationError: formalize() for artifact_type='Risk' is not implemented yet -- only Requirement is wired in this plan; ...`.

- [ ] **Step 3: Write minimal implementation**

Replace the body of `_formalize_single` in `backend/application/interview_service.py` (lines 832-918, up to and including the `else:` create branch) with:

```python
    def _formalize_single(self, ctx, session) -> "dict[str, Any]":
        """Single-kind path: one typed artifact from collected_fields.

        Dispatches through ARTIFACT_CREATION_ADAPTERS -- the same registry
        the multi-kind path uses -- so all 8 in-scope artifact types work
        through their production ``create_X()`` service method (workflow
        state initialization included). This replaced a hardcoded
        ``if session.artifact_type != "Requirement": raise`` (spec L2.1).

        The *update* branch (``target_artifact_id`` set) stays
        Requirement-only: generalizing it needs a second, update-flavoured
        adapter registry, which the spec does not ask for -- see
        ``set_target()``'s matching guard.
        """
        # Reuse get_state()'s exact missing-fields computation: a non-empty
        # `missing` here means the interview is not actually complete yet.
        _, missing = self._current_phase_and_missing(ctx, session)
        if missing:
            missing_names = ", ".join(f.name for f in missing)
            raise ValidationError(
                f"InterviewSession {session.id} is not complete yet -- missing "
                f"required field(s): {missing_names}. Cannot formalize."
            )

        # The completeness guard above only trusts the *protocol*: a workspace
        # override that never declares `title` in required_fields makes
        # `missing` trivially empty. No artifact type may be created with an
        # empty title regardless of what the protocol says -- check
        # independently. str(...) coercion is defense-in-depth (issue #542).
        title = str(session.collected_fields.get("title") or "").strip()
        if not title:
            raise ValidationError(
                f"InterviewSession {session.id} has no non-empty 'title' in "
                f"collected_fields; cannot formalize a {session.artifact_type} "
                "without a title."
            )

        from application.interview_artifact_adapters import (
            ARTIFACT_CREATION_ADAPTERS,
            build_adapter_fields,
        )

        resulting_ids: "list[str]" = []
        created_ref = None

        if session.target_artifact_id is not None:
            from application.requirement_service import RequirementService
            from persistence.models import Requirement

            if session.artifact_type != "Requirement":
                raise ValidationError(
                    f"formalize() cannot update an existing "
                    f"{session.artifact_type!r}: the grounded-update branch is "
                    "Requirement-only. Start a session without a target to "
                    "create a new artifact instead."
                )
            target = Requirement.objects.filter(
                artifact_id=session.target_artifact_id
            ).first()
            if target is None:
                raise NotFoundError(
                    f"Target artifact {session.target_artifact_id} no longer "
                    "exists; cannot formalize an update against it."
                )
            updated = RequirementService().update_requirement(
                target.id,
                ctx,
                title=title,
                description=session.collected_fields.get("rationale"),
            )
            # Issue #736: resulting_artifact_ids carries the Requirement's own
            # id, not the backing Artifact's id -- distinct UUIDs.
            resulting_ids.append(str(updated.id))
        else:
            adapter = ARTIFACT_CREATION_ADAPTERS.get(session.artifact_type)
            if adapter is None:
                raise ValidationError(
                    f"No artifact creation adapter for "
                    f"artifact_type={session.artifact_type!r}."
                )
            fields = build_adapter_fields(session.collected_fields)
            fields["title"] = title  # the normalised/stripped value wins
            try:
                created_ref = adapter(fields, ctx, session.workspace_id)
            except (KeyError, TypeError) as exc:
                # Same contract as _formalize_multi (interview_service.py:1018):
                # a missing required service field (KeyError) or a protocol
                # field name the create_X() signature does not accept
                # (TypeError) is caller/config input, not a server fault --
                # it must never escape as an unhandled 500.
                raise ValidationError(
                    f"cannot formalize {session.artifact_type!r} from the "
                    f"collected answers: {exc}"
                ) from exc
            # Issue #736: report the user-facing subtype id, not the
            # Artifact PK the provenance row below uses.
            resulting_ids.append(str(created_ref.entity_id))
```

Everything from `session.resulting_artifact_ids = resulting_ids` (old line 920) onward stays **unchanged**. Task 8 inserts the provenance write into this same method.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_service.py -k "TestFormalize" -v
```
Expected: PASS — including the pre-existing `test_formalize_with_no_target_creates_new_requirement` (issue-#736 assertion), `test_formalize_with_target_updates_existing_requirement`, `test_formalize_reraises_if_target_artifact_deleted_mid_session`, `test_formalize_rejects_empty_title_even_if_protocol_has_no_title_field` and `test_formalize_rejects_non_string_title_without_crashing`.

- [ ] **Step 5: Run the multi-mode regression guard**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_formalize_multi.py application/tests/test_interview_multi_review_fixes.py -v
```
Expected: PASS. `test_single_mode_formalize_unchanged` (`test_interview_formalize_multi.py:269`) is the explicit "the single path still behaves the same" guard.

- [ ] **Step 6: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_service.py
git commit -m "fix: formalize single-kind interviews for all in-scope types"
```

---

### Task 6: One end-to-end regression test per in-scope artifact type

**Why:** spec §3 requires "ein Regressionstest pro Typ (Requirement bereits vorhanden, sieben neu): Interview starten → Pflichtfelder beantworten → `formalize()` → Artefakt existiert mit korrektem `artifact_type` und initialisiertem Workflow-State."

**Files:**
- Create: `backend/application/tests/test_interview_formalize_all_types.py`

**Interfaces:**
- Consumes: `InterviewService().start/answer/formalize`, `IN_SCOPE_ARTIFACT_TYPES`.
- Produces: nothing (test-only).

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_interview_formalize_all_types.py`:

```python
"""L2.1 regression: formalize() works for every in-scope artifact type.

One parametrized round trip per type -- start, answer the protocol's required
fields, formalize, then assert the artifact exists with the right
``artifact_type`` and an initialized workflow state. Requirement is included
(not only the 7 new types) so the parametrization is the single place the
per-type contract is stated.
"""
from __future__ import annotations

import uuid

import pytest

from application.interview_protocol import IN_SCOPE_ARTIFACT_TYPES
from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Artifact, Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="IFA Tenant", slug="ifa-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS", goals_enabled=True)
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant):
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


#: Values to answer per protocol field type. The factory-default protocol asks
#: title+rationale for every type; Risk additionally asks probability+impact
#: (enum low/medium/high, see interview_protocol._EXTRA_REQUIRED_FIELDS).
_ENUM_ANSWER = "high"


def _answer_all_required_fields(svc: InterviewService, ctx, session_id) -> None:
    """Answer whatever the resolved protocol declares as still missing."""
    state = svc.get_state(ctx, session_id)
    for field in state["missing_fields"]:
        if field["type"] == "enum":
            value = (field.get("choices") or [_ENUM_ANSWER])[0]
        elif field["type"] == "number":
            value = 1
        else:
            value = f"Interview answer for {field['name']}"
        svc.answer(ctx, session_id, field["name"], value)


@pytest.mark.parametrize("artifact_type", IN_SCOPE_ARTIFACT_TYPES)
def test_formalize_creates_the_artifact_for_every_in_scope_type(
    ctx, workspace, artifact_type
):
    svc = InterviewService()
    session = svc.start(ctx, artifact_type, workspace.id)
    _answer_all_required_fields(svc, ctx, session.id)

    result = svc.formalize(ctx, session.id)

    assert result["status"] == "completed"
    assert len(result["resulting_artifact_ids"]) == 1


@pytest.mark.parametrize("artifact_type", IN_SCOPE_ARTIFACT_TYPES)
def test_formalized_artifact_has_the_right_type_and_a_workflow_state(
    ctx, workspace, artifact_type
):
    """The adapters call the production create_X(), which initializes the
    workflow state -- that is the whole reason the registry exists (see
    interview_artifact_adapters module docstring)."""
    from workflow.models import WorkflowItemState

    svc = InterviewService()
    session = svc.start(ctx, artifact_type, workspace.id)
    _answer_all_required_fields(svc, ctx, session.id)
    svc.formalize(ctx, session.id)

    TenantContext.set_tenant(ctx.tenant_id)
    try:
        artifacts = list(
            Artifact.objects.filter(
                workspace_id=workspace.id, artifact_type=artifact_type
            )
        )
        assert len(artifacts) == 1, (
            f"expected exactly one {artifact_type} Artifact row, got {len(artifacts)}"
        )
        assert WorkflowItemState.objects.filter(
            item_type=artifact_type
        ).exists(), f"no WorkflowItemState initialized for {artifact_type}"
    finally:
        TenantContext.clear_tenant()
```

- [ ] **Step 2: Run test to verify it fails (before Task 5 is applied) or passes (after)**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_formalize_all_types.py -v
```
Expected after Tasks 1-5: 16 PASS (8 types × 2 tests).

- [ ] **Step 3: Resolve any per-type failure by fixing the adapter or the protocol, never the test**

If a type fails, the cause is one of exactly three things — fix it at the source:
1. `KeyError: '<field>'` — that service requires a field with no default. Add it to `_EXTRA_REQUIRED_FIELDS` in `backend/application/interview_protocol.py` (Task 4's dict), with the right `type`/`choices`.
2. `TypeError: ... unexpected keyword argument '<field>'` — the protocol field name differs from the `create_X()` kwarg. Add the rename to `_PROTOCOL_FIELD_ALIASES` in `backend/application/interview_artifact_adapters.py` (Task 3).
3. `PermissionDeniedError` on `Goal` — the workspace fixture must set `goals_enabled=True` (already done above; `GoalService.create_version` raises otherwise, see `_goal`'s comment).

- [ ] **Step 4: Verify the workflow-state assertion is not vacuous**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_formalize_all_types.py -k "workflow_state and Adr" -v
```
Expected: PASS. Then temporarily change the assertion to `item_type="NoSuchType"` and re-run: it must FAIL. Revert the temporary change.

- [ ] **Step 5: Commit**

```bash
git add backend/application/tests/test_interview_formalize_all_types.py
git commit -m "test: formalize round trip for all 8 in-scope artifact types"
```

---

### Task 7: Correct the MCP tool descriptions and the `set_target` guard message

**Why:** `mcp_server/tools/interview.py:7`, `:9`, `:175-199` still tell agents "Requirement only". A wrong tool description is a functional bug for an MCP client — it will not attempt a `Risk` interview it is told cannot work.

**Files:**
- Modify: `backend/mcp_server/tools/interview.py:5-12` (module docstring), `:175-200` (tool schema descriptions)
- Modify: `backend/application/interview_service.py:756-761` (`set_target` guard message)
- Test: `backend/mcp_server/tests/` (add to the existing interview tool test module)

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change — description text only.

- [ ] **Step 1: Write the failing test**

Find the existing interview MCP test module:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test sh -c "ls mcp_server/tests/ | grep -i interview"
```

Append to that module (create `mcp_server/tests/test_interview_tools_descriptions.py` if none exists):

```python
"""The formalize tool description must not tell agents a working type is unsupported."""
from mcp_server.tools.interview import InterviewTools


def _descriptions() -> dict:
    return {t["name"]: t["description"] for t in InterviewTools().list_tools()}


def test_formalize_description_does_not_claim_requirement_only():
    text = _descriptions()["interview.formalize"]
    assert "Requirement only" not in text
    assert "only Requirement" not in text


def test_formalize_description_names_the_supported_types():
    text = _descriptions()["interview.formalize"]
    for artifact_type in ("Requirement", "Risk", "Adr", "Goal"):
        assert artifact_type in text


def test_set_target_description_still_states_the_requirement_only_update_branch():
    """set_target IS still Requirement-only by design -- the description must
    keep saying so, and must not be swept up by the formalize fix."""
    text = _descriptions()["interview.set_target"]
    assert "Requirement" in text
```

Adjust `InterviewTools().list_tools()` to whatever the registry's actual accessor is (check `mcp_server/tools/interview.py:40-60` — the class exposes a handler map at `:48`; use the same accessor the existing tests in that directory use).

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  mcp_server/tests/test_interview_tools_descriptions.py -v
```
Expected: FAIL — the current description contains "Requirement only".

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/tools/interview.py`, module docstring lines 5-12: replace "interview.formalize (Task 7, Requirement only)" with "interview.formalize (all 8 in-scope artifact types via ARTIFACT_CREATION_ADAPTERS)", and keep the `set_target` line's "Requirement only" note, rewording it to "Requirement only -- formalize()'s grounded-update branch".

Replace the `interview.formalize` tool description (around `:175`):

```python
            "description": (
                "Formalize an interview session into real artifact(s). "
                "Single-kind sessions create one artifact of the session's "
                "artifact_type -- Requirement, ArchitectureElement, "
                "StakeholderNeed, Risk, TestCase, Adr, Issue or Goal -- "
                "through that type's production create service, so workflow "
                "state is initialized. Multi-kind sessions take a "
                "caller-confirmed proposal and create every item atomically. "
                "GlossaryTerm is rejected: it has no backing Artifact row yet."
            ),
```

Replace the `interview.set_target` description (around `:196`):

```python
                "Pin an existing artifact (by artifact_id) as this session's "
                "formalize() target (write). Once set, formalize() updates "
                "that existing Requirement instead of creating a new one. "
                "Requirement only: formalize()'s grounded-UPDATE branch is "
                "Requirement-only (its CREATE branch supports all 8 in-scope "
                "types). Start a session without a target for the others."
```

In `backend/application/interview_service.py:756-761`, replace the `set_target` guard message:

```python
        if session.artifact_type != "Requirement":
            raise ValidationError(
                f"set_target() for artifact_type={session.artifact_type!r} is not "
                "supported -- formalize()'s grounded-UPDATE branch is "
                "Requirement-only (its CREATE branch handles all 8 in-scope "
                "types), so a target on any other artifact_type could never "
                "be used. Start a session without a target instead."
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  mcp_server/tests/ -k interview -v
```
Expected: PASS.

- [ ] **Step 5: Confirm no stale "Requirement only" text remains in the interview surface**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test sh -c \
  "grep -rn 'only Requirement\|Requirement only\|the other 7 types\|other 8 in-scope' application/interview_service.py application/interview_artifact_adapters.py mcp_server/tools/interview.py rest_api/interview_views.py"
```
Expected: only the *deliberate* `set_target` / grounded-update occurrences remain. Anything referring to `formalize()`'s create path is stale — fix it now. (`_structural_candidates` at `interview_service.py:446` is the grounding pre-filter, out of this spec's scope; leave it, but re-word "in a later pass" to "out of scope for the Interview-Engine-Fix spec" so it does not read as this task's leftover.)

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tools/interview.py backend/application/interview_service.py backend/mcp_server/tests/
git commit -m "docs: correct interview formalize tool description for all types"
```

---

## Phase B — L2.3: Make interview provenance visible

### Task 8: `_formalize_single` writes the `InterviewSessionArtifact` provenance row

**Why (finding V5):** `provenance_session_id()` only reads `InterviewSessionArtifact`, and only `_formalize_multi` writes it. Without this, the badge is permanently invisible for single-mode artifacts — the majority path — and L2.3 would ship dead.

**Files:**
- Modify: `backend/application/interview_service.py` (`_formalize_single`, after `resulting_ids.append(...)` in the create branch)
- Create: `backend/application/tests/test_interview_provenance.py`

**Interfaces:**
- Consumes: `CreatedArtifactRef.artifact_id` (Task 1).
- Produces: one `InterviewSessionArtifact` row per single-mode created artifact. The update branch writes none (the artifact pre-existed — it was not created by this interview).

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_interview_provenance.py`:

```python
"""L2.3: interview provenance is recorded and resolvable for BOTH session kinds."""
from __future__ import annotations

import uuid

import pytest

from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import InterviewSessionArtifact, Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="IP Tenant", slug="ip-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant):
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _formalized_requirement(ctx, workspace):
    svc = InterviewService()
    session = svc.start(ctx, "Requirement", workspace.id)
    svc.answer(ctx, session.id, "title", "Provenance probe")
    svc.answer(ctx, session.id, "rationale", "so the badge has something to find")
    result = svc.formalize(ctx, session.id)
    return session, result


class TestSingleModeProvenance:
    def test_single_mode_formalize_writes_a_provenance_row(self, ctx, workspace):
        session, _ = _formalized_requirement(ctx, workspace)

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            rows = list(InterviewSessionArtifact.objects.filter(session_id=session.id))
        finally:
            TenantContext.clear_tenant()

        assert len(rows) == 1
        assert rows[0].artifact_type == "Requirement"

    def test_provenance_row_references_the_artifact_pk_not_the_subtype_id(
        self, ctx, workspace
    ):
        """InterviewSessionArtifact.artifact is an Artifact FK. The subtype id
        returned in resulting_artifact_ids is a DIFFERENT UUID -- storing it
        here would write an unresolvable FK."""
        from application.requirement_service import RequirementService

        session, result = _formalized_requirement(ctx, workspace)
        requirement = RequirementService().get_requirement(
            uuid.UUID(result["resulting_artifact_ids"][0]), ctx
        )

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            row = InterviewSessionArtifact.objects.get(session_id=session.id)
        finally:
            TenantContext.clear_tenant()

        assert row.artifact_id == requirement.artifact_id
        assert row.artifact_id != requirement.id

    def test_update_branch_writes_no_provenance_row(self, ctx, workspace):
        """A grounded update did not CREATE the artifact, so claiming the
        interview produced it would be wrong."""
        from application.requirement_service import RequirementService
        from persistence.models import InterviewSession

        existing = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Pre-existing", ctx=ctx, description=""
        )
        svc = InterviewService()
        session = svc.start(ctx, "Requirement", workspace.id)
        svc.answer(ctx, session.id, "title", "Updated title")
        svc.answer(ctx, session.id, "rationale", "why")

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                target_artifact_id=existing.artifact_id
            )
        finally:
            TenantContext.clear_tenant()

        svc.formalize(ctx, session.id)

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            assert not InterviewSessionArtifact.objects.filter(
                session_id=session.id
            ).exists()
        finally:
            TenantContext.clear_tenant()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_provenance.py::TestSingleModeProvenance -v
```
Expected: the first two FAIL with `assert 0 == 1` / `DoesNotExist`; `test_update_branch_writes_no_provenance_row` already PASSES.

- [ ] **Step 3: Write minimal implementation**

In `backend/application/interview_service.py`, inside `_formalize_single`'s create branch, directly after `resulting_ids.append(str(created_ref.entity_id))`:

```python
            # L2.3: the same provenance join row _formalize_multi writes, so
            # provenance_session_id()/the InterviewProvenanceBadge work for
            # single-kind sessions too -- previously only multi-kind
            # artifacts could ever show "created via interview".
            # artifact_id (the Artifact PK), never entity_id: this is an
            # Artifact FK.
            InterviewSessionArtifact.objects.create(
                session=session,
                artifact_id=created_ref.artifact_id,
                artifact_type=created_ref.artifact_type,
            )
```

`InterviewSessionArtifact` is already imported at `interview_service.py:23-27`. The write sits inside `formalize()`'s `@atomic_transaction`, so a later failure rolls it back with everything else.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_provenance.py application/tests/test_interview_service.py -k "TestFormalize or Provenance" -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_provenance.py
git commit -m "fix: record interview provenance for single-kind sessions"
```

---

### Task 9: `provenance_session_id()` accepts subtype ids as well as Artifact PKs

**Why (finding V6):** every artifact detail view holds the *subtype* id (`RequirementEditors.tsx:723` passes `requirement.id`). `provenance_session_id` filters on the Artifact PK, so the badge would never match. `TraceLinkService.resolve_entity_to_artifact_id` (`trace_link_service.py:234-256`) is the existing, public, ADR-01-compliant bridge covering all 10 types — reuse it instead of adding a second resolver.

**Files:**
- Modify: `backend/application/interview_service.py:1470-1493`
- Test: `backend/application/tests/test_interview_provenance.py`

**Interfaces:**
- Consumes: `TraceLinkService().resolve_entity_to_artifact_id(entity_id, ctx=...) -> UUID`, raising `NotFoundError` on an unknown id.
- Produces: `provenance_session_id(ctx, artifact_id) -> str | None`, unchanged signature, now accepting either id space.

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_provenance.py`:

```python
class TestProvenanceLookupIdSpaces:
    def test_resolves_by_artifact_pk(self, ctx, workspace):
        from application.requirement_service import RequirementService

        session, result = _formalized_requirement(ctx, workspace)
        requirement = RequirementService().get_requirement(
            uuid.UUID(result["resulting_artifact_ids"][0]), ctx
        )

        found = InterviewService().provenance_session_id(ctx, requirement.artifact_id)

        assert found == str(session.id)

    def test_resolves_by_subtype_id(self, ctx, workspace):
        """Every artifact detail view passes the subtype id (e.g.
        RequirementEditors passes `requirement.id`), so the badge lookup must
        accept it -- otherwise it never matches anything."""
        from application.requirement_service import RequirementService

        session, result = _formalized_requirement(ctx, workspace)
        requirement = RequirementService().get_requirement(
            uuid.UUID(result["resulting_artifact_ids"][0]), ctx
        )
        assert requirement.id != requirement.artifact_id  # guard: really two spaces

        found = InterviewService().provenance_session_id(ctx, requirement.id)

        assert found == str(session.id)

    def test_unknown_id_returns_none_not_an_error(self, ctx, workspace):
        """A plain (non-interview) artifact and a wholly unknown UUID are both
        the normal answer 'not created by an interview', never an exception --
        the badge is informational and must not surface an error."""
        assert InterviewService().provenance_session_id(ctx, uuid.uuid4()) is None

    def test_non_interview_artifact_returns_none(self, ctx, workspace):
        from application.requirement_service import RequirementService

        plain = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Hand-written", ctx=ctx, description=""
        )
        assert InterviewService().provenance_session_id(ctx, plain.id) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_provenance.py::TestProvenanceLookupIdSpaces -v
```
Expected: `test_resolves_by_subtype_id` FAILS with `assert None == '<session id>'`.

- [ ] **Step 3: Write minimal implementation**

Replace `provenance_session_id` in `backend/application/interview_service.py`:

```python
    def provenance_session_id(self, ctx, artifact_id: UUID) -> "str | None":
        """Resolve the interview session that created *artifact_id*, if any.

        Reads the ``InterviewSessionArtifact`` provenance join row written by
        both ``_formalize_single`` (L2.3) and ``_formalize_multi`` -- the
        reverse lookup of "which interview produced this artifact".

        *artifact_id* may be **either** a ``persistence.Artifact`` PK (what
        the join row stores) **or** a business-entity/subtype id such as
        ``Requirement.id`` -- every artifact detail view holds the latter
        (see RightSidebar's ``artifactId`` prop), and the two are distinct
        UUIDs. Resolution goes through ``TraceLinkService``'s existing public
        10-type bridge rather than a second, drifting resolver.

        Tenant scoping comes from the thread-local manager via
        ``_set_tenant_context``, so an id from another tenant resolves to
        None rather than leaking the owning session.

        Returns the session's id as a string, or None when no provenance row
        exists -- a missing row is a normal answer ("not created by an
        interview"), not an error. An id that resolves to nothing at all is
        likewise None, not a raised NotFoundError: this backs a purely
        informational badge.
        """
        self._set_tenant_context(ctx)
        row = (
            InterviewSessionArtifact.objects.filter(artifact_id=artifact_id)
            .select_related("session")
            .first()
        )
        if row is None:
            from application.trace_link_service import TraceLinkService

            try:
                resolved = TraceLinkService().resolve_entity_to_artifact_id(
                    artifact_id, ctx=ctx
                )
            except NotFoundError:
                return None
            if resolved == artifact_id:
                # Already an Artifact PK -- the first probe was authoritative.
                return None
            row = (
                InterviewSessionArtifact.objects.filter(artifact_id=resolved)
                .select_related("session")
                .first()
            )
            if row is None:
                return None
        return str(row.session_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_provenance.py -v
```
Expected: PASS.

- [ ] **Step 5: Verify the REST endpoint end to end**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  rest_api/tests/ -k "interview and (artifact or provenance)" -v
```
Expected: PASS. `GET /api/v1/interviews/by-artifact/{id}/` (`rest_api/interview_views.py:165-184`) passes its parsed UUID straight through, so no view change is needed.

- [ ] **Step 6: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_provenance.py
git commit -m "fix: resolve interview provenance from subtype ids too"
```

---

### Task 10: Mount `InterviewProvenanceBadge` in the shared `RightSidebar`

**Why (finding V7):** the spec says "in jeden Artefakt-Editor-`PageHeader`", but that header belongs to the *list* route and has no single artifact. `components/shared/ArtifactInspector/RightSidebar.tsx` is the shared artifact-detail shell already rendered by all 8 interview types plus Glossary/Diagram/ICD/Goals, and it already receives `artifactId`. One mount instead of eight, and no editor is forgotten later.

**Files:**
- Modify: `frontend/src/components/shared/InterviewProvenanceBadge.tsx`
- Create: `frontend/src/components/shared/InterviewProvenanceBadge.module.css`
- Modify: `frontend/src/components/shared/InterviewProvenanceBadge.test.tsx`
- Modify: `frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx`
- Modify: `frontend/src/components/shared/ArtifactInspector/RightSidebar.test.tsx`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`

**Interfaces:**
- Consumes: `interviewsApi.getProvenance(artifactId) -> { session_id: string | null }` (unchanged), `RightSidebarProps.artifactId: string | number`.
- Produces: `<InterviewProvenanceBadge artifactId={string} />` linking to `/interviews/{sessionId}`.

- [ ] **Step 1: Write the failing test**

Replace the body of `frontend/src/components/shared/InterviewProvenanceBadge.test.tsx` assertions with (keep the file's existing imports/mocks and add what is missing):

```tsx
  it("links to the specific session, not the interviews list", async () => {
    vi.mocked(interviewsApi.getProvenance).mockResolvedValue({
      session_id: "11111111-1111-1111-1111-111111111111",
    });

    render(
      <MemoryRouter>
        <InterviewProvenanceBadge artifactId="art-1" />
      </MemoryRouter>,
    );

    const link = await screen.findByTestId("interview-provenance-badge");
    expect(link).toHaveAttribute(
      "href",
      "/interviews/11111111-1111-1111-1111-111111111111",
    );
  });

  it("renders nothing for an artifact with no interview provenance", async () => {
    vi.mocked(interviewsApi.getProvenance).mockResolvedValue({ session_id: null });

    render(
      <MemoryRouter>
        <InterviewProvenanceBadge artifactId="art-2" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(interviewsApi.getProvenance).toHaveBeenCalledWith("art-2");
    });
    expect(screen.queryByTestId("interview-provenance-badge")).not.toBeInTheDocument();
  });
```

And add to `frontend/src/components/shared/ArtifactInspector/RightSidebar.test.tsx`:

```tsx
  it("mounts the interview provenance badge for the inspected artifact", async () => {
    vi.mocked(interviewsApi.getProvenance).mockResolvedValue({
      session_id: "22222222-2222-2222-2222-222222222222",
    });

    render(
      <MemoryRouter>
        <RightSidebar kind="requirement" artifactId="req-1" />
      </MemoryRouter>,
    );

    expect(
      await screen.findByTestId("interview-provenance-badge"),
    ).toBeInTheDocument();
  });
```

Add `vi.mock("../../../api/interviews", ...)` to `RightSidebar.test.tsx` if it does not already mock that module. **Important:** a partial `vi.mock` of `api/interviews` that omits a newly imported export makes every consumer test throw — mock the whole module shape, e.g. `vi.mock("../../../api/interviews", () => ({ interviewsApi: { getProvenance: vi.fn() } }))`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/shared/InterviewProvenanceBadge.test.tsx src/components/shared/ArtifactInspector/RightSidebar.test.tsx --testTimeout=30000"
```
Expected: FAIL — badge href is `/interviews`, and `RightSidebar` renders no badge.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/shared/InterviewProvenanceBadge.module.css`:

```css
/* Geometry only. Colour comes from the shared badge tokens so the badge
   follows every theme without a per-theme override here. */
.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  line-height: var(--leading-tight);
  background: var(--color-surface-subtle);
  color: var(--color-text-secondary);
  text-decoration: none;
}

.badge:hover,
.badge:focus-visible {
  color: var(--color-text-primary);
  text-decoration: underline;
}
```

Verify each custom property exists before using it:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "grep -n 'space-1\|space-2\|radius-sm\|font-size-xs\|leading-tight\|color-surface-subtle\|color-text-secondary\|color-text-primary' src/styles/tokens.css"
```
If a name is absent, substitute the nearest existing token from that file — never a hardcoded value, and never a new token.

Replace `frontend/src/components/shared/InterviewProvenanceBadge.tsx`:

```tsx
/**
 * InterviewProvenanceBadge — "this artifact came out of an interview".
 *
 * Renders nothing until the backend confirms an interview provenance row for
 * `artifactId` (`GET /interviews/by-artifact/{artifact_id}/` answers
 * `{ session_id: null }` for plain artifacts), then links to that session.
 *
 * `artifactId` may be either the Artifact PK or the artifact's own subtype id
 * — the backend resolves both (InterviewService.provenance_session_id) — so
 * callers can pass whichever id they already hold.
 *
 * Mounted once, in the shared ArtifactInspector RightSidebar, rather than in
 * each artifact editor: RightSidebar is the single detail-panel shell every
 * artifact route already renders, so one mount covers all of them and no new
 * artifact type can forget it.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { interviewsApi } from "../../api/interviews";
import styles from "./InterviewProvenanceBadge.module.css";

interface InterviewProvenanceBadgeProps {
  artifactId: string;
}

export function InterviewProvenanceBadge({
  artifactId,
}: InterviewProvenanceBadgeProps): JSX.Element | null {
  const { t } = useTranslation();
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSessionId(null);
    interviewsApi
      .getProvenance(artifactId)
      .then((r) => {
        if (!cancelled) setSessionId(r.session_id);
      })
      .catch(() => {
        // Lookup failure degrades to "no provenance" -- the badge is purely
        // informational and must never surface as an unhandled rejection.
        if (!cancelled) setSessionId(null);
      });
    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  if (!sessionId) return null;

  return (
    <Link
      to={`/interviews/${sessionId}`}
      className={styles.badge}
      data-testid="interview-provenance-badge"
      title={t("interviews.provenanceHint", "Open the interview that created this")}
    >
      {t("interview.multi.createdBadge")}
    </Link>
  );
}
```

In `frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx`, add the import next to the panel imports:

```tsx
import { InterviewProvenanceBadge } from "../InterviewProvenanceBadge";
```

and render it as the first child inside the expanded `<aside>` body, above `<VersionPanel .../>`:

```tsx
        <InterviewProvenanceBadge artifactId={String(artifactId)} />
```

(`artifactId` is `string | number`; `String(...)` keeps the badge's prop a plain string.)

- [ ] **Step 4: Add the i18n keys**

`frontend/src/i18n/locales/de.json` — inside the existing `"interviews"` object:

```json
    "provenanceHint": "Interview öffnen, aus dem dieses Artefakt entstanden ist"
```

`frontend/src/i18n/locales/en.json` — same key:

```json
    "provenanceHint": "Open the interview this artifact came from"
```

`interview.multi.createdBadge` ("Angelegt via Interview" / its English counterpart) already exists — do not duplicate it.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/shared/ --testTimeout=30000"
```
Expected: PASS. Note that ~14 vitest failures elsewhere in this repo are pre-existing locally while green in CI — compare against a pre-change run of the same path before blaming this task.

- [ ] **Step 6: Run the inline-style and token ratchets**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/test --testTimeout=30000"
```
Expected: PASS — no new `style={{` under `components/`, no hardcoded colour.

- [ ] **Step 7: Verify in the browser**

```bash
docker compose -f deploy/docker-compose.yml --project-directory . restart frontend
```
Then: log in, open `/interviews`, start a Requirement interview, answer title + rationale, formalize. Follow the created requirement to `/requirements/{id}` and confirm the badge is visible in the right inspector and navigates to `/interviews/{sessionId}`. Then open a hand-created requirement and confirm **no** badge renders.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/shared/InterviewProvenanceBadge.tsx frontend/src/components/shared/InterviewProvenanceBadge.module.css frontend/src/components/shared/InterviewProvenanceBadge.test.tsx frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx frontend/src/components/shared/ArtifactInspector/RightSidebar.test.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: show interview provenance on every artifact detail view"
```

---

## Phase C — L2.4: Cap the transcript

### Task 11: `InterviewSession.transcript_summary`

**Files:**
- Modify: `backend/persistence/models.py:2457-2461` (after `transcript`)
- Create: `backend/persistence/migrations/00XX_interview_transcript_summary.py`
- Test: `backend/persistence/tests/test_interview_session_model.py`

**Interfaces:**
- Produces: `InterviewSession.transcript_summary: str` (TextField, `blank=True`, default `""`).

- [ ] **Step 1: Write the failing test**

Append to `backend/persistence/tests/test_interview_session_model.py`:

```python
def test_transcript_summary_defaults_to_empty_string(db, interview_session):
    """L2.4: compressed older turns live here. Empty (never NULL) at start, so
    every read path can concatenate it without a None check."""
    assert interview_session.transcript_summary == ""


def test_transcript_summary_accepts_long_text(db, interview_session):
    long_summary = "x" * 20_000
    interview_session.transcript_summary = long_summary
    interview_session.save(update_fields=["transcript_summary"])
    interview_session.refresh_from_db(fields=["transcript_summary"])
    assert interview_session.transcript_summary == long_summary
```

Reuse whatever session fixture that module already defines; if it has none, construct the row inline with the same `TenantContext.set_tenant(...)` try/finally convention used by the other tests in that file.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  persistence/tests/test_interview_session_model.py -k transcript_summary -v
```
Expected: FAIL with `AttributeError: 'InterviewSession' object has no attribute 'transcript_summary'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/persistence/models.py`, directly after the `transcript` field on `InterviewSession`:

```python
    transcript_summary = models.TextField(
        blank=True,
        default="",
        help_text=(
            "L2.4: LLM-compressed digest of the turns that fell out of the "
            "sliding transcript window (InterviewService."
            "TRANSCRIPT_WINDOW_TURNS). Prepended to the chat prompt instead "
            "of the full history, so prompt size stops growing with session "
            "length. Empty, never NULL: every read path concatenates it."
        ),
    )
```

- [ ] **Step 4: Generate and apply the migration**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend sh -c "ls persistence/migrations/ | tail -3"
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py makemigrations persistence --name interview_transcript_summary
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
```
Expected: one `AddField` operation on `interviewsession`, no other operation. If `makemigrations` proposes anything else, an unrelated model drifted — investigate before continuing, do not commit the extra operation.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  persistence/tests/test_interview_session_model.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/ backend/persistence/tests/test_interview_session_model.py
git commit -m "feat: add InterviewSession.transcript_summary"
```

---

### Task 12: The `interview.transcript_summary` prompt template and slot

**Why:** the compressor is "ein LLM-Call mit dem bestehenden Mock-Fallback-Muster, analog zu `generate_chat_turn`" (spec §5), so its prompt belongs in the same single canonical registry every other interview prompt resolves through (`AiDerivationService.PROMPT_TEMPLATE_DEFAULTS`, workspace → tenant → factory chain).

**Files:**
- Modify: `backend/application/ai_derivation_service.py:227-286` (template + defaults dict + `__all__` at `:2260`)
- Modify: `backend/application/prompt_slots.py:66-77`
- Test: `backend/application/tests/test_interview_transcript_cap.py`

**Interfaces:**
- Produces: slot `interview.transcript_summary` with placeholders `previous_summary`, `overflow_json`; and a new `transcript_summary` placeholder added to the existing `interview.chat_turn` slot.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_interview_transcript_cap.py` with:

```python
"""L2.4: sliding transcript window + LLM compression of the overflow."""
from __future__ import annotations

import uuid

import pytest

from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
from application.prompt_slots import get_prompt_slots


class TestTranscriptSummaryPrompt:
    def test_slot_is_registered_with_its_placeholders(self):
        slots = get_prompt_slots()
        assert "interview.transcript_summary" in slots
        names = set(slots["interview.transcript_summary"].placeholders)
        assert names == {"previous_summary", "overflow_json"}

    def test_factory_default_template_exists_and_uses_both_placeholders(self):
        template = PROMPT_TEMPLATE_DEFAULTS["interview.transcript_summary"]
        assert "{previous_summary}" in template
        assert "{overflow_json}" in template

    def test_chat_turn_slot_gained_the_summary_placeholder(self):
        """The chat prompt must carry the compressed history, or capping the
        transcript would silently drop context instead of condensing it."""
        slots = get_prompt_slots()
        assert "transcript_summary" in set(slots["interview.chat_turn"].placeholders)
```

Adjust `.placeholders` to the actual attribute name on `PromptSlotSpec` (`prompt_slots.py`) — read it first and use the real one.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_transcript_cap.py::TestTranscriptSummaryPrompt -v
```
Expected: FAIL with `KeyError: 'interview.transcript_summary'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/application/ai_derivation_service.py`, after `INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE`:

```python
INTERVIEW_TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE = """\
You are condensing the older part of a requirements-elicitation interview so \
the conversation can continue without resending the whole history.

Summary of everything before this batch (may be empty):
{previous_summary}

Turns to fold into that summary (JSON list of \
{"role": ..., "text": ..., "timestamp": ...}):
{overflow_json}

Write ONE replacement summary that supersedes both inputs. Preserve every \
concrete fact the user stated -- names, numbers, thresholds, constraints, \
decisions, and anything they explicitly rejected -- because the rest of the \
interview and the final artifact are built from this text alone. Drop \
pleasantries, restatements and the assistant's own questions. Do not \
speculate and do not add anything the transcript does not contain.

Respond with the summary text only: no preamble, no headings, no markdown \
fences.
"""
```

Add it to the defaults dict (around `:285`):

```python
    "interview.chat_turn": INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE,
    "interview.transcript_summary": INTERVIEW_TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE,
```

Add it to `__all__` (around `:2260`), next to `"INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE"`:

```python
    "INTERVIEW_TRANSCRIPT_SUMMARY_PROMPT_TEMPLATE",
```

In `backend/application/prompt_slots.py`, extend the `interview.chat_turn` entry and add the new one:

```python
    "interview.chat_turn": (
        "artifact_type",
        "transcript_json",
        # L2.4: the compressed digest of turns that fell out of the sliding
        # window. A workspace-custom chat_turn template that omits this
        # placeholder still renders (render_template substitutes placeholders
        # individually and ignores unused values) -- it just loses the older
        # context, which is the pre-L2.4 behaviour, not a crash.
        "transcript_summary",
        "current_phase_fragment",
        "missing_fields_json",
        "grounding_snapshot_json",
        "user_message",
        "memory_context",
    ),
    "interview.transcript_summary": ("previous_summary", "overflow_json"),
```

Then add `{transcript_summary}` to the factory-default `INTERVIEW_CHAT_TURN_PROMPT_TEMPLATE`, right above the existing "Conversation so far" block:

```
Summary of earlier parts of this conversation (may be empty):
{transcript_summary}

Most recent turns (JSON list of {"role": ..., "text": ..., "timestamp": ...}):
{transcript_json}
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_transcript_cap.py application/tests/test_prompt_slots.py -v
```
Expected: PASS. If `test_prompt_slots.py` asserts an exact slot count, update that number — a new slot is the intended change.

- [ ] **Step 5: Verify the REST-exposed prompt-template surface still agrees**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  rest_api/tests/ mcp_server/tests/ -k "prompt_template or prompt_slot" -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/application/ai_derivation_service.py backend/application/prompt_slots.py backend/application/tests/test_interview_transcript_cap.py
git commit -m "feat: add interview transcript summary prompt slot"
```

---

### Task 13: `_compress_transcript_if_needed()` — sliding window with a best-effort LLM call

**Why:** spec §5. The compressor must never block or fail a chat turn (spec §7 risk: LLM provider failure, issue #846).

**Decision (documented):** the window is counted in **turns**, and one turn writes **two** transcript entries (`user` + `assistant`, `interview_service.py:1271-1275`), so `TRANSCRIPT_WINDOW_TURNS = 10` means 20 retained entries. Compression runs **after** the turn is persisted, in its own `save()`, so a compression failure can never lose the turn that triggered it. The purpose string is not added to `WORKSPACE_WIDE_PURPOSES` — a 10-turn chat digest is a per-session prompt, not a workspace-wide one, so the tight 25 s `LLM_SYNC_TIMEOUT_SECONDS` default is correct.

**Files:**
- Modify: `backend/application/interview_service.py` (module constant near `ABANDONED_TTL:34`, new method near `generate_chat_turn`)
- Test: `backend/application/tests/test_interview_transcript_cap.py`

**Interfaces:**
- Consumes: `InterviewSession.transcript_summary` (Task 11), slot `interview.transcript_summary` (Task 12), `self._resolve_provider()`.
- Produces: `InterviewService.TRANSCRIPT_WINDOW_TURNS: int = 10`, `InterviewService._compress_transcript_if_needed(ctx, session) -> None`.

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_transcript_cap.py`:

```python
from unittest.mock import MagicMock, patch  # noqa: E402

from application.interview_service import InterviewService  # noqa: E402
from auth_tenancy.context import AuthContext, AuthMethod  # noqa: E402
from persistence.models import InterviewSession, Tenant, Workspace  # noqa: E402
from persistence.tenancy import TenantContext  # noqa: E402


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="TC Tenant", slug="tc-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant):
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _session_with_entries(ctx, workspace, entry_count: int):
    session = InterviewService().start(ctx, "Requirement", workspace.id)
    entries = [
        {"role": "user" if i % 2 == 0 else "assistant", "text": f"m{i}", "timestamp": "t"}
        for i in range(entry_count)
    ]
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        InterviewSession.objects.filter(id=session.id).update(transcript=entries)
        return InterviewSession.objects.get(id=session.id)
    finally:
        TenantContext.clear_tenant()


class TestTranscriptCompression:
    def test_does_nothing_below_the_window(self, ctx, workspace):
        # 10 turns = 20 entries -- exactly at the window, nothing to fold out.
        session = _session_with_entries(ctx, workspace, 20)
        with patch.object(InterviewService, "_resolve_provider") as resolver:
            InterviewService()._compress_transcript_if_needed(ctx, session)
        resolver.assert_not_called()
        assert len(session.transcript) == 20
        assert session.transcript_summary == ""

    def test_folds_the_overflow_into_the_summary(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        provider.complete.return_value = "  Condensed history.  "
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        assert session.transcript_summary == "Condensed history."
        # Only the newest 20 entries survive; the 6 oldest were folded in.
        assert len(session.transcript) == 20
        assert session.transcript[0]["text"] == "m6"
        assert session.transcript[-1]["text"] == "m25"

    def test_persists_the_compression(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        provider.complete.return_value = "Condensed."
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert reloaded.transcript_summary == "Condensed."
        assert len(reloaded.transcript) == 20

    def test_provider_failure_leaves_the_transcript_intact(self, ctx, workspace):
        """Spec §7: a failed LLM call must not block or truncate the
        interview -- the turn stays, compression retries next turn."""
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("provider down")
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        assert session.transcript_summary == ""
        assert len(session.transcript) == 26

    def test_no_provider_leaves_the_transcript_intact(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        with patch.object(
            InterviewService,
            "_resolve_provider",
            return_value=(None, "mock", RuntimeError("unconfigured")),
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        assert session.transcript_summary == ""
        assert len(session.transcript) == 26

    def test_previous_summary_is_fed_back_in(self, ctx, workspace):
        """The second compression must supersede the first summary, not
        append to it -- otherwise the digest grows unboundedly and defeats
        the whole cap."""
        session = _session_with_entries(ctx, workspace, 26)
        session.transcript_summary = "Earlier digest."
        provider = MagicMock()
        provider.complete.return_value = "Merged digest."
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        prompt = provider.complete.call_args[0][0]
        assert "Earlier digest." in prompt
        assert session.transcript_summary == "Merged digest."
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_transcript_cap.py::TestTranscriptCompression -v
```
Expected: FAIL with `AttributeError: 'InterviewService' object has no attribute '_compress_transcript_if_needed'`.

- [ ] **Step 3: Write minimal implementation**

Add the module constant in `backend/application/interview_service.py`, below `ABANDONED_TTL` (line 34):

```python
# L2.4 spec §5: how many chat turns stay in `transcript` verbatim. Everything
# older is folded into `transcript_summary`. One turn writes TWO transcript
# entries (user + assistant, see generate_chat_turn), so the retained entry
# count is twice this. A fixed constant, deliberately not a setting: one
# threshold is enough (spec §5, YAGNI).
TRANSCRIPT_WINDOW_TURNS = 10
```

Add the method to `InterviewService`, directly above `generate_chat_turn`:

```python
    def _compress_transcript_if_needed(self, ctx, session: InterviewSession) -> None:
        """Fold turns older than the sliding window into ``transcript_summary``.

        L2.4 (spec §5): ``transcript`` used to grow without bound, and every
        chat turn resent the whole history as prompt context. Above
        ``TRANSCRIPT_WINDOW_TURNS`` turns, the overflow is replaced by one
        LLM-written digest that *supersedes* the previous digest (it is fed
        back in), so the summary itself cannot grow without bound either.

        Best-effort by contract (spec §7, issue #846): no provider, or a
        provider that raises, means "no compression this turn" -- the
        transcript is left exactly as it was and the next turn retries. Never
        raises, never blocks the chat. Called AFTER the triggering turn is
        already persisted, so a failure here cannot lose that turn.

        Mutates *session* in place and persists both fields; the caller does
        not need to re-save.
        """
        window_entries = TRANSCRIPT_WINDOW_TURNS * 2
        if len(session.transcript) <= window_entries:
            return

        overflow = session.transcript[:-window_entries]
        window = session.transcript[-window_entries:]

        provider, provider_name, _resolve_error = self._resolve_provider()
        if provider is None:
            logger.debug(
                "InterviewService: no LLM provider for transcript compression, "
                "session=%s -- deferring to the next turn", session.id
            )
            return

        from application.ai_derivation_service import AiDerivationService
        from llm_adapter.timeouts import resolve_timeout_seconds

        template = AiDerivationService._get_template_content(
            ctx, "interview.transcript_summary", session.workspace_id
        )
        prompt = AiDerivationService._render(
            template,
            previous_summary=session.transcript_summary or "",
            overflow_json=json.dumps(overflow),
        )
        try:
            summary = provider.complete(
                prompt,
                purpose="interview.transcript_summary",
                timeout=resolve_timeout_seconds("interview.transcript_summary"),
            )
        except Exception:  # noqa: BLE001 -- best-effort by contract, see docstring
            logger.debug(
                "InterviewService: transcript compression failed for session=%s "
                "(provider=%s) -- transcript left uncompressed, retrying next turn",
                session.id, provider_name, exc_info=True,
            )
            return

        summary = (summary or "").strip()
        if not summary:
            # An empty digest would silently DISCARD the overflow turns.
            # Treat it exactly like a failed call.
            logger.debug(
                "InterviewService: empty transcript summary for session=%s -- "
                "transcript left uncompressed", session.id
            )
            return

        session.transcript_summary = summary
        session.transcript = window
        session.save(update_fields=["transcript_summary", "transcript", "modified_at"])
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_transcript_cap.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_transcript_cap.py
git commit -m "feat: compress interview transcript above a sliding window"
```

---

### Task 14: Wire compression and the summary into `generate_chat_turn`

**Files:**
- Modify: `backend/application/interview_service.py:1196-1206` (prompt render), `:1269-1311` (post-write block)
- Test: `backend/application/tests/test_interview_transcript_cap.py`

**Interfaces:**
- Consumes: `_compress_transcript_if_needed(ctx, session)`, `session.transcript_summary`.
- Produces: unchanged `generate_chat_turn` return shape `{"reply": str, "state": dict}`.

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_interview_transcript_cap.py`:

```python
class TestChatTurnUsesTheSummary:
    def test_prompt_carries_the_summary_and_only_the_window(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 20)
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                transcript_summary="Digest of the early conversation."
            )
        finally:
            TenantContext.clear_tenant()

        provider = MagicMock()
        provider.complete.return_value = '{"extracted_fields": {}, "reply": "ok"}'
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService().generate_chat_turn(ctx, session.id, "next question")

        prompt = provider.complete.call_args_list[0][0][0]
        assert "Digest of the early conversation." in prompt
        # The freshly-appended turn is in the window; the summary is separate.
        assert "next question" in prompt

    def test_chat_turn_triggers_compression_after_persisting(self, ctx, workspace):
        """Compression runs on the persisted transcript, so the turn that
        pushed it over the window can never be lost by a compression failure."""
        session = _session_with_entries(ctx, workspace, 20)
        provider = MagicMock()
        provider.complete.side_effect = [
            '{"extracted_fields": {}, "reply": "ok"}',  # the chat turn
            "Condensed history.",                        # the compression call
        ]
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService().generate_chat_turn(ctx, session.id, "one more")

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        # 20 + 2 new entries = 22, compressed back down to the 20-entry window.
        assert len(reloaded.transcript) == 20
        assert reloaded.transcript_summary == "Condensed history."

    def test_compression_failure_still_returns_the_reply(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 20)
        provider = MagicMock()
        provider.complete.side_effect = [
            '{"extracted_fields": {}, "reply": "ok"}',
            RuntimeError("provider down"),
        ]
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            result = InterviewService().generate_chat_turn(ctx, session.id, "one more")

        assert result["reply"] == "ok"
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert len(reloaded.transcript) == 22  # uncompressed, nothing lost
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_transcript_cap.py::TestChatTurnUsesTheSummary -v
```
Expected: FAIL — `"Digest of the early conversation." in prompt` is False, and the transcript is not compressed.

- [ ] **Step 3: Write minimal implementation**

In `backend/application/interview_service.py`, add the new value to the `AiDerivationService._render` call at `:1197-1206`:

```python
        prompt = AiDerivationService._render(
            template,
            artifact_type=session.artifact_type,
            transcript_json=json.dumps(session.transcript),
            # L2.4: the digest of turns already folded out of `transcript`.
            # `transcript` itself is now the sliding window, not the whole
            # history, so without this the prompt would silently lose context.
            transcript_summary=session.transcript_summary or "",
            current_phase_fragment=phase.prompt_fragment,
            missing_fields_json=json.dumps([self._serialise_field(f) for f in missing]),
            grounding_snapshot_json=json.dumps(session.grounding_snapshot),
            user_message=user_message,
            memory_context=memory_context,
        )
```

Then, immediately **after** the `with transaction.atomic():` block closes (after `self._emit_event(...)`, before `return {"reply": reply, ...}` at `:1311`):

```python
        # L2.4: deliberately OUTSIDE the atomic block above -- the turn is
        # already committed, so a compression failure (or a slow second LLM
        # call) can neither roll back nor lose it. Never raises; see
        # _compress_transcript_if_needed's contract.
        self._compress_transcript_if_needed(ctx, session)

        return {"reply": reply, "state": self.get_state(ctx, session_id)}
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_transcript_cap.py application/tests/test_interview_multi_chat.py -v
```
Expected: PASS. `test_interview_multi_chat.py` guards `_generate_multi_chat_turn`, which this task deliberately leaves untouched (multi sessions build their prompt via `get_multi_protocol_prompt`, `interview_service.py:1369` — capping that path is not in this spec).

- [ ] **Step 5: Run the whole interview backend surface**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/ -k interview -v
```
Expected: PASS across all 10 interview test modules.

- [ ] **Step 6: Commit**

```bash
git add backend/application/interview_service.py backend/application/tests/test_interview_transcript_cap.py
git commit -m "feat: use the transcript summary as chat prompt context"
```

---

## Phase D — L2.5: One full interview surface

### Task 15: `/interviews?start=multi` — the discovery entry point through the existing auto-start route

**Why:** Task 16 makes the widget navigate instead of holding a session. `InterviewEditors`' auto-start effect (`:74-82`) already handles `?start=<Type>` but rejects anything outside `INTERVIEW_ARTIFACT_TYPES`, so `multi` needs one branch. Doing this **first** means Task 16 has a working destination.

**Files:**
- Modify: `frontend/src/components/InterviewEditors/InterviewEditors.tsx:52-82`
- Modify: `frontend/src/components/InterviewEditors/InterviewEditors.test.tsx`

**Interfaces:**
- Consumes: `interviewsApi.start(workspaceId, artifactType, sessionKind?)` (`api/interviews.ts` — already accepts `null` + `"multi"`, see `InterviewWidget.tsx:98`).
- Produces: route contract `/interviews?start=<InterviewArtifactType> | multi`.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/components/InterviewEditors/InterviewEditors.test.tsx`:

```tsx
  it("auto-starts a multi-kind discovery session for ?start=multi", async () => {
    vi.mocked(interviewsApi.start).mockResolvedValue({
      id: "sess-multi",
      status: "in_progress",
      transcript: [],
      missing_fields: [],
      collected_fields: {},
      grounding_snapshot: {},
    } as never);

    render(
      <MemoryRouter initialEntries={["/interviews?start=multi"]}>
        <Routes>
          <Route path="/interviews" element={<InterviewEditors />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(interviewsApi.start).toHaveBeenCalledWith("ws-1", null, "multi");
    });
  });

  it("ignores an unknown ?start= value without starting anything", async () => {
    render(
      <MemoryRouter initialEntries={["/interviews?start=Banana"]}>
        <Routes>
          <Route path="/interviews" element={<InterviewEditors />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("interviews-page")).toBeInTheDocument();
    });
    expect(interviewsApi.start).not.toHaveBeenCalled();
  });
```

Match the existing file's workspace mock so `activeWorkspace.id` really is `"ws-1"`; read the top of `InterviewEditors.test.tsx` and reuse its `useWorkspace` mock verbatim.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/InterviewEditors/InterviewEditors.test.tsx --testTimeout=30000"
```
Expected: the `?start=multi` test FAILS — `interviewsApi.start` was never called (the type guard at `:77` rejects `"multi"`).

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/components/InterviewEditors/InterviewEditors.tsx`, replace `handleStart` and the auto-start effect:

```tsx
  /** Sentinel `?start=` value for a multi-kind discovery session. */
  const MULTI_START_PARAM = "multi";

  const handleStart = async (artifactType: string): Promise<void> => {
    if (!activeWorkspace) return;
    setStartingType(artifactType);
    setStartError(null);
    try {
      // A multi-kind discovery session is bound to no protocol, so it starts
      // with artifact_type=null and session_kind="multi".
      const state =
        artifactType === MULTI_START_PARAM
          ? await interviewsApi.start(activeWorkspace.id, null, "multi")
          : await interviewsApi.start(activeWorkspace.id, artifactType);
      setShowStartDialog(false);
      refresh();
      navigate(`/interviews/${state.id}`);
    } catch (err) {
      setStartError(extractErrorMessage(err));
    } finally {
      setStartingType(null);
    }
  };

  // CTA entry point from other artifact pages and from the interview widget
  // (`/interviews?start=<Type>` / `?start=multi`). Skips the picker dialog
  // since the choice is already made; the param is stripped right away so
  // back/refresh never re-triggers a second session.
  const [searchParams, setSearchParams] = useSearchParams();
  const autoStartRequested = useRef(false);
  useEffect(() => {
    const requestedType = searchParams.get("start");
    if (!requestedType || autoStartRequested.current || !activeWorkspace) return;
    const isKnown =
      requestedType === MULTI_START_PARAM ||
      INTERVIEW_ARTIFACT_TYPES.includes(
        requestedType as (typeof INTERVIEW_ARTIFACT_TYPES)[number],
      );
    if (!isKnown) return;
    autoStartRequested.current = true;
    setSearchParams({}, { replace: true });
    void handleStart(requestedType);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, activeWorkspace]);
```

Move `const MULTI_START_PARAM = "multi";` to module scope (above `export default function InterviewEditors`) and export it, so Task 16 imports the same constant instead of re-typing the literal:

```tsx
/** Sentinel `?start=` value for a multi-kind discovery session. */
export const MULTI_START_PARAM = "multi";
```

Also add the multi option to the picker dialog's grid, so `/interviews` alone offers what the widget offers:

```tsx
            <button
              type="button"
              className={styles.typeButton}
              data-testid={`interview-start-${MULTI_START_PARAM}`}
              disabled={startingType !== null}
              onClick={() => void handleStart(MULTI_START_PARAM)}
            >
              {startingType === MULTI_START_PARAM ? (
                <Spinner label={t("actions.creating", "Starting...")} />
              ) : (
                t("interview.multiEntry")
              )}
            </button>
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/InterviewEditors/ --testTimeout=30000"
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/InterviewEditors/InterviewEditors.tsx frontend/src/components/InterviewEditors/InterviewEditors.test.tsx
git commit -m "feat: start a multi-kind interview from the ?start= route"
```

---

### Task 16: Reduce the widget to a quick entry point

**Why:** spec §6. The widget stops owning a session; it picks a type and navigates to `/interviews?start=<Type>`, which Task 15 / the pre-existing effect turns into `/interviews/{id}`. This deletes the widget's `session`/`sessionKind`/`starting` state and its `InterviewChatPane` + `InterviewArtifactPane` hosting — the panes themselves stay, still used by `InterviewDetail` (finding V8).

**Files:**
- Modify: `frontend/src/components/InterviewWidget/InterviewWidget.tsx`
- Modify: `frontend/src/components/InterviewWidget/InterviewWidget.test.tsx`

**Interfaces:**
- Consumes: `MULTI_START_PARAM` from `../InterviewEditors/InterviewEditors`, `useNavigate()`, `INTERVIEW_ARTIFACT_TYPES`.
- Produces: unchanged test ids `interview-widget-toggle`, `interview-widget-panel`, `interview-widget-start-<Type>`, `interview-widget-start-multi` — **do not rename them**, an id move breaks Playwright specs while vitest stays green.

- [ ] **Step 1: Write the failing test**

Replace the session-hosting assertions in `frontend/src/components/InterviewWidget/InterviewWidget.test.tsx` with:

```tsx
  it("navigates to the interviews route instead of hosting a session", async () => {
    render(
      <MemoryRouter initialEntries={["/requirements"]}>
        <Routes>
          <Route path="/requirements" element={<InterviewWidget />} />
          <Route path="/interviews" element={<div data-testid="interviews-route" />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-Risk"));

    expect(await screen.findByTestId("interviews-route")).toBeInTheDocument();
    // The widget must not start the session itself -- /interviews owns that,
    // so there is exactly one start path and one chat surface.
    expect(interviewsApi.start).not.toHaveBeenCalled();
  });

  it("routes the discovery entry point to ?start=multi", async () => {
    render(
      <MemoryRouter initialEntries={["/requirements"]}>
        <Routes>
          <Route path="/requirements" element={<InterviewWidget />} />
          <Route path="/interviews" element={<div data-testid="interviews-route" />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-multi"));

    expect(await screen.findByTestId("interviews-route")).toBeInTheDocument();
  });

  it("closes the panel after navigating away", async () => {
    render(
      <MemoryRouter initialEntries={["/requirements"]}>
        <Routes>
          <Route path="/requirements" element={<InterviewWidget />} />
          <Route path="/interviews" element={<InterviewWidget />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-Adr"));

    await waitFor(() => {
      expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
    });
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBe("false");
  });

  it("renders no chat pane at all", () => {
    render(
      <MemoryRouter>
        <InterviewWidget />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));

    expect(screen.queryByTestId("interview-chat-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("interview-artifact-formalize")).not.toBeInTheDocument();
  });
```

Keep the existing toggle/localStorage tests (lines 55-78) unchanged — that behaviour is not in scope.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/InterviewWidget/InterviewWidget.test.tsx --testTimeout=30000"
```
Expected: FAIL — the widget calls `interviewsApi.start` and renders `interview-chat-input`.

- [ ] **Step 3: Write minimal implementation**

Replace `frontend/src/components/InterviewWidget/InterviewWidget.tsx` in full:

```tsx
/**
 * Interview-management web widget — quick entry point (spec L2.5).
 *
 * A `position: fixed` overlay, always mounted (via NavigationShell) on every
 * authenticated route. Its ONLY job is picking what to interview about and
 * handing off to `/interviews?start=<Type>`, which starts the session and
 * routes to `/interviews/{id}`.
 *
 * It deliberately hosts no chat: interviews are multi-turn conversations that
 * need more room than an overlay comfortably gives, and an overlay that stays
 * open across navigation while covering forms is a UX problem for long
 * sessions (audit finding S19). `/interviews` is the single full interview
 * surface — `InterviewChatPane`/`InterviewArtifactPane` (still in this folder)
 * are rendered there, by `InterviewEditors/InterviewDetail`.
 *
 * WRITE-gate note: WorkspaceContext exposes no currentUserRole-like field, so
 * all nine buttons stay visible for every authenticated user — pre-existing
 * behaviour, deliberately unchanged here.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { INTERVIEW_ARTIFACT_TYPES } from "../../constants/interviewArtifactTypes";
import { MULTI_START_PARAM } from "../InterviewEditors/InterviewEditors";
import styles from "./InterviewWidget.module.css";

const STORAGE_KEY = "reqflow-interview-widget-open";

/**
 * Defensive localStorage wrapper (issue #679) — direct `window.localStorage`
 * access throws in third-party-cookie-restricted browsers, private-browsing
 * storage lockouts, and JSDOM environments where the property is unavailable.
 * The toggle-open state persisted here is a nice-to-have, never worth
 * freezing the widget over.
 */
export const safeLocalStorage = {
  getItem: (key: string): string | null => {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem: (key: string, value: string): void => {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Storage unavailable (private browsing, disabled cookies, etc.) — no-op.
    }
  },
};

export function InterviewWidget(): JSX.Element {
  const { activeWorkspace } = useWorkspace();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(safeLocalStorage.getItem(STORAGE_KEY) === "true");
  }, []);

  const setOpenPersisted = (next: boolean): void => {
    setOpen(next);
    safeLocalStorage.setItem(STORAGE_KEY, String(next));
  };

  /**
   * Hand off to the interviews route, which owns session creation. Closing
   * the panel first is what satisfies the S19 "must not stay open across
   * navigation, covering the page underneath" finding.
   */
  const goToInterview = (startParam: string): void => {
    setOpenPersisted(false);
    navigate(`/interviews?start=${startParam}`);
  };

  if (!activeWorkspace) return <></>;

  return (
    <>
      <button
        type="button"
        data-testid="interview-widget-toggle"
        className={styles.toggle}
        onClick={() => setOpenPersisted(!open)}
        // #741: the FAB renders nothing but the 💬 glyph, so the label IS the
        // whole accessible name.
        aria-label={
          open
            ? t("interview.widget.close", "Interview-Assistent schließen")
            : t("interview.widget.open", "Interview-Assistent öffnen")
        }
        title={t("interview.widget.title", "Interview-Assistent")}
        aria-expanded={open}
        aria-controls="interview-widget-panel"
      >
        <span aria-hidden="true">{"\u{1F4AC}"}</span>
      </button>
      {open && (
        <div
          id="interview-widget-panel"
          data-testid="interview-widget-panel"
          className={styles.panel}
          role="group"
          aria-label={t("interview.widget.title", "Interview-Assistent")}
        >
          <p className={styles.hint}>{t("interview.widget.hint")}</p>
          <div className={styles.startRow}>
            {INTERVIEW_ARTIFACT_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                data-testid={`interview-widget-start-${type}`}
                className={styles.startButton}
                onClick={() => goToInterview(type)}
              >
                {t(`interview.start.${type}`)}
              </button>
            ))}
            <button
              type="button"
              data-testid={`interview-widget-start-${MULTI_START_PARAM}`}
              className={styles.startButton}
              onClick={() => goToInterview(MULTI_START_PARAM)}
            >
              {t("interview.multiEntry")}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
```

Add the `.hint` rule to `frontend/src/components/InterviewWidget/InterviewWidget.module.css`:

```css
.hint {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-xs);
  line-height: var(--leading-normal);
  color: var(--color-text-secondary);
}
```

Verify those custom properties exist in `frontend/src/styles/tokens.css` (same check as Task 10 Step 3); substitute the nearest existing token if one is missing.

- [ ] **Step 4: Add the i18n key**

`frontend/src/i18n/locales/de.json`, inside `"interview"."widget"`:

```json
      "hint": "Wähle einen Typ — das Interview öffnet sich unter /interviews."
```

`frontend/src/i18n/locales/en.json`, same place:

```json
      "hint": "Pick a type — the interview opens under /interviews."
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/InterviewWidget/ src/components/InterviewEditors/ --testTimeout=30000"
```
Expected: PASS. `InterviewChatPane.test.tsx`, `InterviewArtifactPane.test.tsx` and `ProposalPreviewGraph.test.tsx` must stay green untouched — those components did not change, only their second host went away.

- [ ] **Step 6: Confirm no dangling import and no orphaned component**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx tsc --noEmit -p tsconfig.json 2>&1 | head -30; grep -rn 'InterviewChatPane\|InterviewArtifactPane' src/ --include=*.tsx | grep -v 'InterviewWidget/Interview'"
```
Expected: no TS errors from this change (note: frontend CI does not run `tsc`, so this manual check is the only gate). The grep must show `InterviewEditors/InterviewDetail.tsx` as the remaining consumer of both panes — if it shows none, something over-deleted; restore it.

- [ ] **Step 7: Verify in the browser**

```bash
docker compose -f deploy/docker-compose.yml --project-directory . restart frontend
```
Then: on `/requirements`, open the widget, click "Risiko". Confirm the panel closes, the URL becomes `/interviews/{id}`, and the chat is usable there. Reload `/requirements` and confirm the widget panel is closed (state persisted as `false`). Click the discovery button and confirm a multi session opens. Check the panel's layout at 1366 px and 1920 px viewport widths.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/InterviewWidget/ frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "refactor: reduce the interview widget to a quick entry point"
```

---

### Task 17: Frontend regression sweep and a targeted E2E check

**Files:**
- Test only (no source change unless a failure demands one).

- [ ] **Step 1: Run the full frontend unit suite**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run --testTimeout=30000"
```
Expected: no NEW failures. ~14 failures are pre-existing locally while green in CI — diff this run against a pre-change run of the same command, do not chase inherited red.

- [ ] **Step 2: Check for E2E specs that land on a moved surface**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "grep -rn 'interview' ../e2e/tests/ || echo 'no interview e2e specs'"
```
Expected: only `visual-regression.spec.ts:24` (`['interviews', '/interviews']`), which screenshots the list route — unaffected by Tasks 15/16. If any spec asserts a widget-hosted chat, update it to the `/interviews/{id}` flow in this task.

- [ ] **Step 3: Run the one affected E2E spec, filtered**

Run (from `e2e/`, using the LOCAL Playwright binary — a root `node_modules/playwright` at another version makes every spec die at `test.describe()`):

```bash
node node_modules/@playwright/test/cli.js test tests/visual-regression.spec.ts --grep interviews
```
Expected: PASS, or a snapshot diff caused by the sidebar/route being visually unchanged. Visual baselines are per-platform (`-linux` in CI, `-win32` locally): a missing local baseline is not a failure of this change. A **full** unfiltered Playwright run needs explicit user approval — do not start one here.

- [ ] **Step 4: Run the whole backend interview surface once more**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/ persistence/tests/test_interview_session_model.py rest_api/tests/ mcp_server/tests/ -k interview -v
```
Expected: PASS.

- [ ] **Step 5: Commit any test updates**

```bash
git add e2e/ frontend/src
git commit -m "test: adjust interview specs to the single interview surface"
```

---

## Phase E — Blocked follow-up

### Task 18: `GlossaryTerm` interview adapter — **BLOCKED**

**BLOCKED ON:** `docs/superpowers/specs/2026-09-03-datenmodell-konsolidierung-design.md` §4 — `GlossaryTerm` must gain a `OneToOneField` to `persistence.Artifact`, plus the backfill migration, plus `GlossaryService.create_term` creating the `Artifact` row first.

**Verified precondition status as of 2026-09-04: NOT MET.** `backend/persistence/models.py:1833-1856` — `GlossaryTerm` has `workspace`, `term`, `definition`, `synonyms`, `abbreviation`, `version`, `lifecycle_status` and **no** `artifact` FK. Latest migration is `0069_align_embedding_dimensions.py`. Until that lands, `_glossary_term` must keep raising: writing an `InterviewSessionArtifact` row for an artifact-less `GlossaryTerm` produces an unresolvable FK, and a `TraceLink` to it is impossible.

**Do not start this task before the check in Step 1 passes.**

**Files:**
- Modify: `backend/application/interview_artifact_adapters.py:108-129`
- Modify: `backend/application/interview_protocol.py:24-33` (`IN_SCOPE_ARTIFACT_TYPES`)
- Test: `backend/application/tests/test_interview_artifact_adapters.py`, `backend/application/tests/test_interview_formalize_all_types.py`

**Interfaces:**
- Consumes: `GlossaryService.create_term(...)` returning an object with `.id` and `.artifact_id` (its post-Datenmodell-Konsolidierung shape).
- Produces: `ARTIFACT_CREATION_ADAPTERS["GlossaryTerm"]` that creates instead of rejecting.

- [ ] **Step 1: Verify the precondition is met**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test python -c "
from persistence.models import GlossaryTerm
names = {f.name for f in GlossaryTerm._meta.get_fields()}
print('artifact FK present:', 'artifact' in names)
"
```
Expected to proceed: `artifact FK present: True`. If it prints `False`, **stop** — this task stays blocked and the plan is complete without it.

- [ ] **Step 2: Write the failing test**

Replace `test_glossary_term_adapter_rejects_even_for_editor` in `backend/application/tests/test_interview_artifact_adapters.py` with:

```python
    def test_glossary_term_adapter_creates_an_artifact_backed_term(self):
        """Unblocked by the Datenmodell-Konsolidierung spec §4: GlossaryTerm
        now has an Artifact backing row, so it creates like the other 8."""
        fake_ctx = MagicMock()
        fake_term = MagicMock(id=uuid.uuid4(), artifact_id=uuid.uuid4())
        with patch(
            "application.interview_artifact_adapters.GlossaryService.create_term",
            autospec=True,
            return_value=fake_term,
        ):
            ref = ARTIFACT_CREATION_ADAPTERS["GlossaryTerm"](
                {"term": "Latency", "definition": "Time to first byte"},
                fake_ctx,
                "ws-1",
            )
        assert ref == CreatedArtifactRef(
            artifact_id=fake_term.artifact_id,
            artifact_type="GlossaryTerm",
            entity_id=fake_term.id,
        )
```

- [ ] **Step 3: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_artifact_adapters.py -k glossary -v
```
Expected: FAIL with `ValidationError: GlossaryTerm is not Artifact-backed yet ...`.

- [ ] **Step 4: Write minimal implementation**

Replace `_glossary_term` in `backend/application/interview_artifact_adapters.py`:

```python
def _glossary_term(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # Unblocked by the Datenmodell-Konsolidierung spec §4: GlossaryTerm now
    # has an Artifact backing row, so InterviewSessionArtifact provenance and
    # TraceLink endpoints can reference it like any other type.
    obj = GlossaryService().create_term(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="GlossaryTerm", entity_id=obj.id
    )
```

Add `"GlossaryTerm"` to `IN_SCOPE_ARTIFACT_TYPES` in `backend/application/interview_protocol.py` so the type gets a factory-default interview protocol and can be started at all. Then add its required fields to `_EXTRA_REQUIRED_FIELDS` (Task 4's dict) — `GlossaryService.create_term` has no default for `definition`, and `term` is its title field:

```python
    "GlossaryTerm": (
        "      - name: term\n"
        "        type: text\n"
        "      - name: definition\n"
        "        type: textarea\n"
    ),
```

Confirm the real `create_term` signature first and adjust `_PROTOCOL_FIELD_ALIASES` / `_EXTRA_REQUIRED_FIELDS` to match it exactly:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test python -c "
import inspect
from application.glossary_service import GlossaryService
print(inspect.signature(GlossaryService.create_term))
"
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest \
  application/tests/test_interview_artifact_adapters.py \
  application/tests/test_interview_formalize_all_types.py \
  application/tests/test_interview_protocol.py -v
```
Expected: PASS. `test_interview_formalize_all_types.py` parametrizes over `IN_SCOPE_ARTIFACT_TYPES`, so `GlossaryTerm` gets its full round trip for free.

- [ ] **Step 6: Update the two docstrings that still promise a rejection**

In `backend/application/interview_artifact_adapters.py:8-16` (module docstring) and `backend/mcp_server/tools/interview.py` (the `interview.formalize` description from Task 7), replace the "GlossaryTerm is rejected: it has no backing Artifact row yet" sentence with the 9-type list.

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_ife backend-test pytest mcp_server/tests/ -k interview -v
```
Expected: PASS (Task 7's `test_formalize_description_names_the_supported_types` still holds; add `"GlossaryTerm"` to its type tuple).

- [ ] **Step 7: Commit**

```bash
git add backend/application/interview_artifact_adapters.py backend/application/interview_protocol.py backend/mcp_server/tools/interview.py backend/application/tests/
git commit -m "feat: create GlossaryTerm from interviews"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Requirement | Task(s) |
|---|---|---|
| §3 L2.1 | Single-kind path uses `ARTIFACT_CREATION_ADAPTERS` instead of the hardcoded guard | 5 (prerequisites 1–4) |
| §3 L2.1 | One regression test per type: start → answer → formalize → artifact exists with correct `artifact_type` + initialized workflow state | 6 |
| §3 L2.1 | `GlossaryTerm` stays rejected until Datenmodell-Konsolidierung §4; then a one-entry adapter | 18 (BLOCKED, precondition verified unmet) |
| §4 L2.3 | `InterviewProvenanceBadge` visible when `provenance_session_id()` hits | 8, 9, 10 |
| §4 L2.3 | Badge click leads to `/interviews/{id}` | 10 |
| §5 L2.4 | New `InterviewSession.transcript_summary` TextField, empty at start | 11 |
| §5 L2.4 | Sliding window of 10 turns, older turns compressed via one LLM call | 12, 13 |
| §5 L2.4 | Prompt context = `transcript_summary` + last 10 turns, not the full history | 14 |
| §6 L2.5 | `/interviews` stays the primary, full interaction surface | 15, 16 |
| §6 L2.5 | Widget reduced to type-pick + redirect; chat pane code removed from it | 16 |
| §6 L2.5 | Type picker closes on navigation and has an `aria-label` | 16 (V10: no popover exists; the panel gets both) |
| §6 L2.5 | "Per Interview erstellen" opens with the page's type preselected | none — V9: already the behaviour |
| §7 | LLM failure must not block the interview; retry next turn, no data loss | 13 (three tests), 14 |
| §7 | Cross-spec dependency on Datenmodell-Konsolidierung | 18 |
| Scope-out | `ai_elicit` protocol derivation (L2.2) | not planned — Attribute-Definition spec §7 owns it |
| Scope-out | Pure translation work (L2.6), MainGoal interviews | not planned |

**2. Placeholder scan** — no "TBD", no "TODO", no "similar to Task N", no "add appropriate error handling" without code. Every step names a file, a command and an expected outcome. Three steps intentionally instruct a *lookup* before writing (Task 7 Step 1 tool accessor, Task 12 Step 1 `PromptSlotSpec` attribute name, Task 18 Step 4 `create_term` signature) — each gives the exact command to run and what to do with the answer, so none is a deferred decision.

**3. Type consistency**

- `CreatedArtifactRef(artifact_id: UUID, artifact_type: str, entity_id: UUID)` — defined Task 1, consumed Tasks 2, 5, 8, 18. `artifact_id` → provenance rows + TraceLinks; `entity_id` → `resulting_artifact_ids`. Never swapped.
- `build_adapter_fields(collected_fields: dict) -> dict` — defined Task 3, consumed Task 5 only.
- `InterviewService.TRANSCRIPT_WINDOW_TURNS: int` and `_compress_transcript_if_needed(ctx, session) -> None` — defined Task 13, consumed Task 14.
- `provenance_session_id(ctx, artifact_id: UUID) -> str | None` — signature unchanged (Task 9); the REST view needs no edit.
- `MULTI_START_PARAM: string` — exported Task 15, imported Task 16.
- `InterviewProvenanceBadge({ artifactId: string })` — Task 10; `RightSidebar.artifactId` is `string | number`, coerced with `String(...)` at the call site.
- `interviewsApi.getProvenance(id) -> { session_id: string | null }` — unchanged wire shape.

**4. Blast radius double-checked**

- `CreatedArtifactRef` gains a **required** field. Only `interview_artifact_adapters.py` and its test module construct it (Task 1 Step 6 verifies). The same-named TS interface in `InterviewChatPane.tsx:42` is an unrelated wire-format type and is untouched.
- `IN_SCOPE_ARTIFACT_TYPES` is read by `interview_protocol.INTERVIEW_PROTOCOL_DEFAULTS`, `InterviewService.start`'s scope gate and the frontend `INTERVIEW_ARTIFACT_TYPES` constant. Only Task 18 changes it, and only once unblocked — the frontend constant must be updated in the same commit.
- Removing the widget's session hosting removes a *host*, not a component. `InterviewChatPane`, `InterviewArtifactPane` and `ProposalPreviewGraph` keep `InterviewEditors/InterviewDetail.tsx` as their consumer; Task 16 Step 6 asserts this with a grep.

## OFFENE FRAGEN

None. Every ambiguity found while verifying the spec (findings V3–V10) is resolved by an explicit, documented decision inside the task that needs it.
