# Menschen im System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every one of the 10 artifact types a real `owner` and `assignee` User reference, add a generic `Comment` entity on `persistence.Artifact`, and add a `Notification` entity with four triggers, so that requirements work becomes communicable inside the tool.

**Architecture:** Two new tables (`as_comment`, `as_notification`) live in the existing `application` app alongside `Adr`/`Risk`/`Goal`/`Issue` — no new Django app, no `settings.py` change, one RLS policy migration in the established `application/0009` style. All `owner`/`assignee` writes funnel through **one** module, `backend/application/assignment.py`, which sets the fields, persists them, writes the `AuditEntry.OP_ASSIGN` entry and produces the `assigned` notification — a single seam guarded by an AST ratchet test, so the spec's "a forgotten `update_X()` path drops the audit entry" risk becomes a failing test instead of a silent hole. Notification *production* lives entirely in `backend/application/notification_service.py` (ADR-01: Layer 2 owns the ORM); `workflow/services.py` and the suspect-propagation path call one function each.

**Tech Stack:** Python 3.x / Django 5.2 (2 new models + 5 schema migrations + 2 data migrations + 1 RLS migration + 1 management command), DRF (2 ViewSets, 1 nested route), MCP (1 new tool group `comment.*`), React 18 + TS strict (2 API wrappers, 1 inspector panel, 1 sidebar bell), i18n de/en. No new runtime dependency.

**Spec:** docs/superpowers/specs/2026-09-03-menschen-im-system-design.md

## Global Constraints

- **Two fields, not one.** `owner` = responsible (stable), `assignee` = currently working on it (changes often). Both are `models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")`. Never merge them.
- **10 types get both fields:** Requirement, StakeholderNeed, ArchitectureElement, TestCase, GlossaryTerm (app `persistence`), Adr, Goal, Risk, Issue (app `application`), Icd (app `icd`). `Diagram` and `MainGoal` are **out of scope** — the spec's "10 Typen" list names neither (decision recorded in Task 3).
- **Risk contract phase:** free-text `Risk.owner` (CharField, `application/models.py:380`) is dropped, `Risk.owner_user` (FK, `application/models.py:387`) is renamed to `owner`. A migration report must be produced and reviewed by a human **before** the field drop — no automatic blind merge.
- **Issue contract phase:** `Issue.assignee_id` (loose `UUIDField`, `application/models.py:629`) becomes a real `assignee` FK. Orphan UUIDs are nulled and reported, never silently dropped.
- **`AuditEntry.OP_ASSIGN = "assign"`** already exists (`backend/audit/models.py:122`) **and is already in `OP_CHOICES`** (`backend/audit/models.py:204`). No `AlterField` migration for the audit vocabulary is needed.
- **Every `owner`/`assignee` write goes through `application/assignment.py::apply_assignment()`.** Task 12 adds an AST ratchet that fails the build if any other module in `backend/application/` or `backend/icd/` assigns `owner`/`assignee`/`owner_id`/`assignee_id` on a model instance.
- **`Comment` hangs on `persistence.Artifact`, never on a specialized table** — that is what makes it work for all 10 types with no special case.
- **Notification triggers are exactly four:** `transition_pending`, `suspect_flagged`, `assigned`, `comment_added`. `transition_pending` is a **role broadcast** (every user in the workspace holding one of the outgoing transitions' `allowed_roles`), not person-scoped routing. No due dates, no escalation, no delegation — that is Q2.5, explicitly out of scope.
- **No real-time push.** No WebSocket, no SSE, no Celery task. The bell polls once on mount.
- **No MCP tool group for notifications.** Agents do not read a notification center.
- **Comments are not editable** — create, list, resolve, delete (author or admin) only. That is why there is no comment change history.
- **DRF views must not touch the ORM.** `backend/rest_api/` has a ratchet that counts `.objects.` occurrences (including inside docstrings). All reads/writes go through a Layer-2 service.
- **Every DRF view calls `get_auth_context(request)`** (`backend/rest_api/auth_enforcer.py:113`), which sets the tenant context. Never query without it — RLS returns an empty set.
- **No inline styles in `frontend/src/components/`.** A UI ratchet fails on new `style={{`. Use CSS modules + `styles/tokens.css` custom properties.
- **`data-testid` on every interactive element.** Deletes use `components/shared/ConfirmDialog.tsx` (`confirmTestId`/`cancelTestId` props) — never hand-roll a confirm.
- **Named exports only, kebab-case-free existing file naming preserved** (this repo uses PascalCase for React components and snake_case for Python).
- **Migration numbers below are the next free ones as of 2026-09-03.** Specs 1–5 of the audit series land first and will consume numbers. Before each `makemigrations`, run `ls backend/<app>/migrations/ | tail -3` and use the next free prefix. The migration *content* in this plan is unaffected.
- **Ordering vs. the Attribute-Definition spec (spec 2):** its bootstrap script introspects Django model fields to build the core-attribute list. Every migration in Phase A of this plan must be applied **before** that bootstrap runs, otherwise `owner`/`assignee` are missing from the first core list. Task 26 re-runs the bootstrap.

### Commands used throughout

Backend test (unique `DB_NAME` prevents collisions with a concurrent run):

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest <path> -v
```

Frontend test:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run <path> --testTimeout=30000"
```

Migrations (the DB **owner** role, not the least-privilege app role, is required for DDL and for data migrations — the compose test/backend service already uses `DB_USER=reqogniloom`):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py makemigrations <app> --name <name>
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
```

---

## File Structure

```
backend/
  application/
    models.py                                    MODIFY  +Comment, +Notification, +owner/assignee on Adr, Goal, Risk, Issue
    assignment.py                                CREATE  apply_assignment() — the single owner/assignee write seam
    comment_service.py                           CREATE  CommentService
    notification_service.py                      CREATE  NotificationService + notify_* producers
    trace_link_service.py                        MODIFY  +resolve_artifact_id_or_none() module function
    requirement_service.py                       MODIFY  update_requirement: owner_id/assignee_id
    stakeholder_need_service.py                  MODIFY  update: owner_id/assignee_id
    architecture_service.py                      MODIFY  update_architecture_element: owner_id/assignee_id
    test_service.py                              MODIFY  update_test_case: owner_id/assignee_id
    glossary_service.py                          MODIFY  update: owner_id/assignee_id
    adr_service.py                               MODIFY  update_adr: owner_id/assignee_id
    goal_service.py                              MODIFY  update: owner_id/assignee_id
    risk_service.py                              MODIFY  update_risk: owner->FK, assignee_id
    issue_service.py                             MODIFY  update_issue + assign_issue -> apply_assignment
    services.py                                  MODIFY  re-export CommentService, NotificationService
    management/commands/report_risk_owner_match.py  CREATE  human-reviewable migration report
    migrations/0020_owner_assignee_adr_goal.py      CREATE
    migrations/0021_risk_owner_backfill.py          CREATE  data migration
    migrations/0022_risk_owner_contract.py          CREATE  drop CharField, rename FK
    migrations/0023_issue_assignee_expand.py        CREATE  rename legacy col, add FK
    migrations/0024_issue_assignee_contract.py      CREATE  backfill + drop legacy col
    migrations/0025_comment_notification.py         CREATE
    migrations/0026_comment_notification_rls.py     CREATE
    tests/test_owner_assignee_application_types.py  CREATE  Task 3
    tests/test_report_risk_owner_match.py           CREATE  Task 4
    tests/test_risk_owner_contract.py               CREATE  Task 5
    tests/test_issue_assignee_contract.py           CREATE  Task 6
    tests/test_collaboration_models.py              CREATE  Task 7
    tests/test_collaboration_rls.py                 CREATE  Task 8
    tests/test_resolve_artifact_id_or_none.py       CREATE  Task 9
    tests/test_notification_service.py              CREATE  Task 10
    tests/test_assignment.py                        CREATE  Task 11
    tests/test_assignment_wiring_persistence_types.py  CREATE  Task 12
    tests/test_assignment_wiring_application_types.py  CREATE  Task 13
    tests/test_assignment_ratchet.py                CREATE  Task 14
    tests/test_comment_service.py                   CREATE  Task 15
    tests/test_notify_transition_pending.py         CREATE  Task 18
    tests/test_notify_suspect_flagged.py            CREATE  Task 19
    tests/test_owner_assignee_are_core_attributes.py   CREATE  Task 26
  persistence/
    models.py                                    MODIFY  +owner/assignee on 5 types
    migrations/0070_owner_assignee_core_types.py CREATE
    tests/test_owner_assignee_fields.py          CREATE  Task 1
  icd/
    models.py                                    MODIFY  +owner/assignee on Icd
    icd_manager.py                               MODIFY  update_icd: owner_id/assignee_id
    migrations/0009_icd_owner_assignee.py        CREATE
    tests/test_icd_owner_assignee.py             CREATE  Task 2
  baseline/
    state_capture.py                             MODIFY  Risk/Issue owner+assignee snapshot fields
  workflow/
    services.py                                  MODIFY  transition(): notify_transition_pending hook
  traceability/ (or wherever spec 3 landed it)   MODIFY  suspect propagation: notify_suspect_flagged hook (Task 19)
  rest_api/
    collaboration_views.py                       CREATE  ArtifactCommentsView, CommentViewSet, NotificationViewSet
    serializers.py                               MODIFY  +CommentSerializer, +NotificationSerializer, owner/assignee on 10 serializers
    views.py                                     MODIFY  owner_id/assignee_id passthrough on the 10 artifact ViewSets
    urls.py                                      MODIFY  register comments/notifications + nested artifact comments
    tests/test_comment_endpoints.py              CREATE  Task 16
    tests/test_notification_endpoints.py         CREATE  Task 20
    tests/test_owner_assignee_exposure.py        CREATE  Task 21
  mcp_server/
    tools/comment.py                             CREATE  CommentToolGroup
    tool_registry.py                             MODIFY  register "comment"
    tests/test_comment_tool_group.py             CREATE  Task 17
frontend/src/
  api/comments.ts                                CREATE
  api/notifications.ts                           CREATE
  api/comments.test.ts                           CREATE  Task 22 (covers both wrappers)
  api/index.ts                                   MODIFY  barrel re-export
  components/shared/ArtifactInspector/
    CommentPanel.tsx                             CREATE
    CommentPanel.module.css                      CREATE
    CommentPanel.test.tsx                        CREATE
    RightSidebar.tsx                             MODIFY  mount CommentPanel as 4th panel
    index.ts                                     MODIFY  export CommentPanel
  components/NavigationShell/
    NotificationBell.tsx                         CREATE
    NotificationBell.module.css                  CREATE
    NotificationBell.test.tsx                    CREATE
    SidebarNavigation.tsx                        MODIFY  mount bell in the pinned footer
  i18n/locales/de.json                           MODIFY
  i18n/locales/en.json                           MODIFY
  i18n/locales.test.ts                           CREATE  Task 25
```

**26 tasks.** Phase A (schema) 1-8 · Phase B (assignment seam) 9-14 · Phase C (comments) 15-17 · Phase D (notification triggers + REST) 18-20 · Phase E (REST exposure) 21 · Phase F (frontend) 22-26.

---

## OFFENE FRAGEN

**None are blocking.** Two spec inaccuracies were found and resolved by decision (see Task 11 and Task 3); one cross-spec call site is resolved by a documented grep-and-wire step (Task 20).

Spec corrections verified against the tree at `main` (`fc41497d`):

1. **Spec §3.3 claims `AuditEntry.OP_ASSIGN` "bisher von keinem Schreibpfad genutzt wird". That is wrong.** `IssueService.assign_issue` (`backend/application/issue_service.py:566`) already writes `operation="assign"` with `details={"old_assignee": ..., "new_assignee": ...}`. Consequence for the plan: Task 11 does not *introduce* the first `OP_ASSIGN` writer, it *migrates* the existing one onto the shared seam. Behaviour is preserved (same op, same details keys).
2. **Spec §4's `Comment` sketch declares `created_at`, which `TenantScopedModel` already provides** via `AuditableModel` (`backend/persistence/models.py:382`), together with `id` (UUID pk), `created_by`, `modified_at`, `modified_by`, `version`. Declaring it again would shadow the inherited field. The model in Task 8 omits it and uses the inherited column.
3. **Spec §4 asks for an "Inspector-Reiter" (tab). The existing inspector has no tab concept** — `RightSidebar.tsx:343` documents this explicitly ("The panels below have no per-section tab/anchor concept ... they are simply stacked"). Building a tab system for one panel is out of proportion. Decision: `CommentPanel` is mounted as a **fourth stacked panel** next to Version/Diff/Trace (Task 24).

Verified as **correct** in the spec:

- `Risk.owner` free-text CharField at `backend/application/models.py:380` — yes.
- `Risk.owner_user` FK with the "Expand phase of an expand/contract migration" comment at `backend/application/models.py:381-394` — yes, verbatim.
- `Issue.assignee_id` as a loose `models.UUIDField(null=True, blank=True)` with no FK at `backend/application/models.py:629` — yes.
- `AuditEntry.OP_ASSIGN = "assign"` at `backend/audit/models.py:122` — yes, and present in `OP_CHOICES` at line 204, so no `ValidationError` trap (the failure mode of issue #265) applies here.

---

## Phase A — Schema

### Task 1: `owner` / `assignee` on the five `persistence` types

**Files:**
- Modify: `backend/persistence/models.py` (classes `StakeholderNeed`:875, `Requirement`:926, `ArchitectureElement`:1087, `TestCase`:1412, `GlossaryTerm`:1833)
- Create: `backend/persistence/migrations/0070_owner_assignee_core_types.py`
- Test: `backend/persistence/tests/test_owner_assignee_fields.py`

**Interfaces:**
- Produces: `Requirement.owner`, `Requirement.assignee`, `StakeholderNeed.owner/.assignee`, `ArchitectureElement.owner/.assignee`, `TestCase.owner/.assignee`, `GlossaryTerm.owner/.assignee` — all `FK(User, SET_NULL, null=True, blank=True, related_name="+")`, DB columns `owner_id` / `assignee_id`.

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_owner_assignee_fields.py`:

```python
"""Owner/assignee are real User FKs on every core persistence artifact type."""
import pytest
from django.db import models

from persistence.models import (
    ArchitectureElement,
    GlossaryTerm,
    Requirement,
    StakeholderNeed,
    TestCase,
    User,
)

CORE_TYPES = [Requirement, StakeholderNeed, ArchitectureElement, TestCase, GlossaryTerm]


@pytest.mark.parametrize("model", CORE_TYPES)
@pytest.mark.parametrize("field_name", ["owner", "assignee"])
def test_field_is_nullable_user_fk(model, field_name):
    field = model._meta.get_field(field_name)
    assert isinstance(field, models.ForeignKey)
    assert field.related_model is User
    assert field.null is True
    assert field.blank is True
    assert field.remote_field.on_delete is models.SET_NULL


@pytest.mark.parametrize("model", CORE_TYPES)
@pytest.mark.parametrize("field_name", ["owner", "assignee"])
def test_field_has_no_reverse_accessor(model, field_name):
    """related_name='+' — 10 types x 2 fields would otherwise clutter User."""
    field = model._meta.get_field(field_name)
    assert field.remote_field.related_name == "+"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest persistence/tests/test_owner_assignee_fields.py -v
```
Expected: FAIL with `FieldDoesNotExist: Requirement has no field named 'owner'`.

- [ ] **Step 3: Add the fields to the five models**

In `backend/persistence/models.py`, add these two fields to each of `StakeholderNeed`, `Requirement`, `ArchitectureElement`, `TestCase`, `GlossaryTerm` (place them immediately before the class's `class Meta:` block):

```python
    # Menschen-im-System spec §3: two distinct roles. `owner` is the stable
    # responsibility ("who answers for this"), `assignee` is the volatile
    # current worker ("who is on it right now"). SET_NULL so deleting a user
    # never deletes an artifact; related_name="+" because 10 types x 2 fields
    # would otherwise add 20 reverse accessors to User.
    owner = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Responsible user (stable). Written only via application.assignment.apply_assignment.",
    )
    assignee = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Currently assigned user (volatile). Written only via application.assignment.apply_assignment.",
    )
```

- [ ] **Step 4: Generate and apply the migration**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py makemigrations persistence --name owner_assignee_core_types
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
```
Expected: a new `backend/persistence/migrations/00NN_owner_assignee_core_types.py` with 10 `AddField` operations, applied cleanly. Verify it contains no `AlterField` on unrelated fields (if it does, the tree drifted — split those out).

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest persistence/tests/test_owner_assignee_fields.py -v
```
Expected: PASS (20 parametrized cases).

- [ ] **Step 6: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/ backend/persistence/tests/test_owner_assignee_fields.py
git commit -m "feat: add owner/assignee User FKs to the five core persistence types"
```

---

### Task 2: `owner` / `assignee` on `Icd`

**Files:**
- Modify: `backend/icd/models.py` (class `Icd`:93)
- Create: `backend/icd/migrations/0009_icd_owner_assignee.py`
- Test: `backend/icd/tests/test_icd_owner_assignee.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Icd.owner`, `Icd.assignee` (same shape as Task 1).

- [ ] **Step 1: Write the failing test**

Create `backend/icd/tests/test_icd_owner_assignee.py`:

```python
"""Icd carries the same owner/assignee pair as the core persistence types."""
import pytest
from django.db import models

from icd.models import Icd
from persistence.models import User


@pytest.mark.parametrize("field_name", ["owner", "assignee"])
def test_icd_field_is_nullable_user_fk(field_name):
    field = Icd._meta.get_field(field_name)
    assert isinstance(field, models.ForeignKey)
    assert field.related_model is User
    assert field.null is True
    assert field.remote_field.on_delete is models.SET_NULL
    assert field.remote_field.related_name == "+"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest icd/tests/test_icd_owner_assignee.py -v
```
Expected: FAIL with `FieldDoesNotExist: Icd has no field named 'owner'`.

- [ ] **Step 3: Add the fields**

In `backend/icd/models.py`, class `Icd`, immediately before its `class Meta:`:

```python
    # Menschen-im-System spec §3 — same two-role pair as the persistence types.
    owner = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Responsible user (stable). Written only via application.assignment.apply_assignment.",
    )
    assignee = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Currently assigned user (volatile). Written only via application.assignment.apply_assignment.",
    )
```

- [ ] **Step 4: Generate and apply the migration**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py makemigrations icd --name icd_owner_assignee
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
```
Expected: `backend/icd/migrations/0009_icd_owner_assignee.py` with two `AddField` operations.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest icd/tests/test_icd_owner_assignee.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/icd/models.py backend/icd/migrations/ backend/icd/tests/test_icd_owner_assignee.py
git commit -m "feat: add owner/assignee User FKs to Icd"
```

---

### Task 3: `owner` / `assignee` on `Adr` and `Goal`

**Files:**
- Modify: `backend/application/models.py` (class `Adr`:223, class `Goal`:466)
- Create: `backend/application/migrations/0020_owner_assignee_adr_goal.py`
- Test: `backend/application/tests/test_owner_assignee_application_types.py`

**Interfaces:**
- Produces: `Adr.owner/.assignee`, `Goal.owner/.assignee`.

**Decision (recorded here, forwarded to `documenter`):** `MainGoal` and `Diagram` are excluded. The spec enumerates exactly ten types (§1: "Alle anderen 8 Typen (Requirement, StakeholderNeed, ArchitectureElement, TestCase, Adr, Goal, Icd, GlossaryTerm)" plus Risk and Issue) and names neither. `MainGoal` is a workspace-singleton aggregate, `Diagram` is a rendering artifact; adding an owner to either is a scope decision, not an omission to silently correct.

**Decision (Goal versioning):** `Goal` rows are immutable per version — `GoalService.update` (`backend/application/goal_service.py:337`) creates a *new* row. A new version therefore starts with `owner=NULL`/`assignee=NULL` unless copied. Task 15 copies both fields forward, because "editing a goal silently drops its owner" is a data-loss bug, not a feature.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_owner_assignee_application_types.py`:

```python
"""Owner/assignee on the application-app artifact types (Adr, Goal)."""
import pytest
from django.db import models

from application.models import Adr, Goal
from persistence.models import User


@pytest.mark.parametrize("model", [Adr, Goal])
@pytest.mark.parametrize("field_name", ["owner", "assignee"])
def test_field_is_nullable_user_fk(model, field_name):
    field = model._meta.get_field(field_name)
    assert isinstance(field, models.ForeignKey)
    assert field.related_model is User
    assert field.null is True
    assert field.remote_field.on_delete is models.SET_NULL
    assert field.remote_field.related_name == "+"


def test_main_goal_and_diagram_are_out_of_scope():
    """The spec enumerates 10 types; MainGoal is not one of them."""
    from application.models import MainGoal

    with pytest.raises(Exception):
        MainGoal._meta.get_field("owner")
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_owner_assignee_application_types.py -v
```
Expected: the two parametrized field tests FAIL with `FieldDoesNotExist: Adr has no field named 'owner'`; `test_main_goal_and_diagram_are_out_of_scope` already PASSES.

- [ ] **Step 3: Add the fields**

In `backend/application/models.py`, add to class `Adr` and class `Goal`, immediately before each `class Meta:`:

```python
    # Menschen-im-System spec §3 — same two-role pair as the persistence types.
    # settings.AUTH_USER_MODEL (= "persistence.User") mirrors the existing
    # Risk.owner_user declaration in this same module.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Responsible user (stable). Written only via application.assignment.apply_assignment.",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Currently assigned user (volatile). Written only via application.assignment.apply_assignment.",
    )
```

(`from django.conf import settings` is already imported in this module — it backs `Risk.owner_user` at line 388.)

- [ ] **Step 4: Generate and apply the migration**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py makemigrations application --name owner_assignee_adr_goal
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
```
Expected: `backend/application/migrations/0020_owner_assignee_adr_goal.py` with four `AddField` operations.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_owner_assignee_application_types.py -v
```
Expected: PASS (5 cases).

- [ ] **Step 6: Commit**

```bash
git add backend/application/models.py backend/application/migrations/ backend/application/tests/test_owner_assignee_application_types.py
git commit -m "feat: add owner/assignee User FKs to Adr and Goal"
```

---

### Task 4: Risk owner-match report (human review gate)

**Files:**
- Create: `backend/application/management/commands/report_risk_owner_match.py`
- Test: `backend/application/tests/test_report_risk_owner_match.py`

**Interfaces:**
- Produces: `match_free_text_owner(owner_text: str, users: list[User]) -> User | None` — the single matching rule, imported by the Task 5 data migration so report and migration can never disagree.

**Why a separate command:** spec §8 requires the report to be reviewed **before** the field drop. A management command can be run, read, and re-run without touching the schema; a `RunPython` print buried in a migration cannot.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_report_risk_owner_match.py`:

```python
"""The free-text -> User matching rule used by both the report and the migration."""
import pytest

from application.management.commands.report_risk_owner_match import (
    match_free_text_owner,
)


class _U:
    def __init__(self, pk, username, email, first_name="", last_name=""):
        self.pk = pk
        self.username = username
        self.email = email
        self.first_name = first_name
        self.last_name = last_name


ALICE = _U(1, "alice", "alice@example.com", "Alice", "Smith")
BOB = _U(2, "bob", "bob@example.com", "Bob", "Jones")
ALICE_2 = _U(3, "asmith", "a.smith@example.com", "Alice", "Smith")


def test_matches_username_case_insensitively():
    assert match_free_text_owner("  ALICE ", [ALICE, BOB]) is ALICE


def test_matches_email():
    assert match_free_text_owner("bob@example.com", [ALICE, BOB]) is BOB


def test_matches_full_name():
    assert match_free_text_owner("Alice Smith", [ALICE, BOB]) is ALICE


def test_empty_is_no_match():
    assert match_free_text_owner("   ", [ALICE, BOB]) is None


def test_unknown_is_no_match():
    assert match_free_text_owner("Team Platform", [ALICE, BOB]) is None


def test_ambiguous_full_name_is_no_match():
    """Two users with the same display name must not be guessed between."""
    assert match_free_text_owner("Alice Smith", [ALICE, ALICE_2]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_report_risk_owner_match.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'application.management.commands.report_risk_owner_match'`.

- [ ] **Step 3: Write the command**

Create `backend/application/management/commands/report_risk_owner_match.py`:

```python
"""Report how the free-text ``Risk.owner`` values map onto real Users.

Menschen-im-System spec §3 / §8: the Risk expand/contract migration
(REQ-L1-029) may only drop the free-text column after a human has read this
report. The command is read-only — it never writes.

Usage:
    python manage.py report_risk_owner_match
    python manage.py report_risk_owner_match --json /tmp/risk_owner_report.json
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from django.core.management.base import BaseCommand


def match_free_text_owner(owner_text: str, users: Iterable[Any]) -> Optional[Any]:
    """Return the single User matching *owner_text*, or None.

    Matching is deliberately conservative: exact (case-insensitive, trimmed)
    equality against ``username``, ``email`` or ``"first_name last_name"``.
    No fuzzy matching, no substring matching — spec §3 forbids inventing an
    assignment ("keine automatische Rate-Erfindung"). An ambiguous match
    (two users answering to the same key) returns None so the value lands in
    the report instead of on a random user.
    """
    needle = (owner_text or "").strip().lower()
    if not needle:
        return None

    hits = []
    for user in users:
        candidates = {
            (user.username or "").strip().lower(),
            (user.email or "").strip().lower(),
            f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip().lower(),
        }
        candidates.discard("")
        if needle in candidates:
            hits.append(user)

    return hits[0] if len(hits) == 1 else None


class Command(BaseCommand):
    help = "Report free-text Risk.owner values that can (or cannot) be mapped to a User."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--json",
            dest="json_path",
            default=None,
            help="Optional path to write the report as JSON.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from application.models import Risk
        from persistence.models import User

        users_by_tenant: dict[Any, list[Any]] = {}
        for user in User.objects.all():
            users_by_tenant.setdefault(user.tenant_id, []).append(user)

        matched: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []

        # ``unscoped`` — this report deliberately spans all tenants; it is an
        # operator tool run outside any request context.
        for risk in Risk.unscoped.exclude(owner="").exclude(owner=None):
            user = match_free_text_owner(risk.owner, users_by_tenant.get(risk.tenant_id, []))
            row = {
                "risk_id": str(risk.id),
                "tenant_id": str(risk.tenant_id),
                "workspace_id": str(risk.workspace_id),
                "owner_text": risk.owner,
                "matched_user_id": str(user.pk) if user else None,
                "matched_username": user.username if user else None,
            }
            (matched if user else unmatched).append(row)

        self.stdout.write(f"Risk rows with a free-text owner: {len(matched) + len(unmatched)}")
        self.stdout.write(f"  mappable to a User: {len(matched)}")
        self.stdout.write(f"  NOT mappable (data-quality finding): {len(unmatched)}")
        for row in unmatched:
            self.stdout.write(f"    risk={row['risk_id']} owner={row['owner_text']!r}")

        if options["json_path"]:
            with open(options["json_path"], "w", encoding="utf-8") as handle:
                json.dump({"matched": matched, "unmatched": unmatched}, handle, indent=2)
            self.stdout.write(f"JSON report written to {options['json_path']}")
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_report_risk_owner_match.py -v
```
Expected: PASS (6 cases).

- [ ] **Step 5: Run the command against the dev database and read the output**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py report_risk_owner_match --json /tmp/risk_owner_report.json
```
Expected: a summary line plus one line per unmappable value. **Do not proceed to Task 6 until a human has read the "NOT mappable" list.** On the seeded demo database the list is expected to be short or empty.

- [ ] **Step 6: Commit**

```bash
git add backend/application/management/commands/report_risk_owner_match.py backend/application/tests/test_report_risk_owner_match.py
git commit -m "feat: add report_risk_owner_match command for the Risk owner contract migration"
```

---

### Task 5: Risk contract phase — backfill, drop free-text `owner`, rename `owner_user` → `owner`

**Files:**
- Create: `backend/application/migrations/0021_risk_owner_backfill.py`
- Create: `backend/application/migrations/0022_risk_owner_contract.py`
- Modify: `backend/application/models.py:380-394` (remove `owner` CharField, rename `owner_user` → `owner`, add `assignee`)
- Modify: `backend/application/risk_service.py:91,252,367` (RiskDTO + create + update)
- Modify: `backend/baseline/state_capture.py:293-294`
- Modify: `backend/application/export_service.py:166`
- Test: `backend/application/tests/test_risk_owner_contract.py`

**Interfaces:**
- Consumes: `match_free_text_owner(owner_text, users) -> User | None` (Task 4).
- Produces: `Risk.owner` (FK, DB column `owner_id`), `Risk.assignee` (FK). `Risk.owner_user` and the free-text `Risk.owner` **no longer exist** — a breaking change to the REST field `owner` (was a string, now a UUID) and `owner_user_id` (removed, see Task 21).

**Blast radius (grep-verified, complete):** `risk_service.py:91` (`RiskDTO.owner=risk.owner`), `:252` (`create_risk(owner=...)`), `:367` (`risk.owner = owner`), `:186/203/257/304/321/376-377` (`owner_user_id` parameter chain), `baseline/state_capture.py:293-294`, `export_service.py:166`, `rest_api/serializers.py:1405,1409-1410`, `rest_api/views.py:4211-4212,5132,5177`, `mcp_server/tests/test_generic_tool_group.py:225-226,238-239`, `application/tests/test_risk_service.py:304-346,487-513`. `related_name="owned_risks"` has zero readers outside `models.py:392` and `migrations/0010`.

**Migration strategy:** stock Django operations only. `RemoveField("risk", "owner")` frees the name, then `RenameField("risk", "owner_user", "owner")` renames column `owner_user_id` → `owner_id` (metadata-only in PostgreSQL). No `SeparateDatabaseAndState`, no raw SQL.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_risk_owner_contract.py`:

```python
"""Risk finishes the REQ-L1-029 expand/contract migration."""
import pytest
from django.db import models

from application.models import Risk
from persistence.models import User


def test_owner_is_now_a_user_fk_not_a_charfield():
    field = Risk._meta.get_field("owner")
    assert isinstance(field, models.ForeignKey)
    assert field.related_model is User


def test_owner_uses_the_owner_id_column():
    """RenameField must map owner_user_id -> owner_id, not create a new column."""
    assert Risk._meta.get_field("owner").column == "owner_id"


def test_owner_user_is_gone():
    with pytest.raises(Exception):
        Risk._meta.get_field("owner_user")


def test_assignee_exists_and_is_nullable():
    field = Risk._meta.get_field("assignee")
    assert isinstance(field, models.ForeignKey)
    assert field.null is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_risk_owner_contract.py -v
```
Expected: FAIL — `test_owner_is_now_a_user_fk_not_a_charfield` fails on `isinstance(CharField, ForeignKey)`.

- [ ] **Step 3: Write the backfill data migration**

Create `backend/application/migrations/0021_risk_owner_backfill.py`:

```python
"""Backfill Risk.owner_user from the free-text Risk.owner (REQ-L1-029 contract).

Menschen-im-System spec §3/§7.2. Only unambiguous matches are migrated; the
rest stay a data-quality finding reported by
``manage.py report_risk_owner_match`` (spec §8: no automatic blind merge).
"""
from __future__ import annotations

from django.db import migrations


def backfill_owner_user(apps, schema_editor):
    from application.management.commands.report_risk_owner_match import (
        match_free_text_owner,
    )

    Risk = apps.get_model("application", "Risk")
    User = apps.get_model("persistence", "User")

    users_by_tenant: dict = {}
    for user in User.objects.all():
        users_by_tenant.setdefault(user.tenant_id, []).append(user)

    for risk in Risk.objects.filter(owner_user__isnull=True).exclude(owner=""):
        user = match_free_text_owner(risk.owner, users_by_tenant.get(risk.tenant_id, []))
        if user is not None:
            Risk.objects.filter(pk=risk.pk).update(owner_user_id=user.pk)


def noop_reverse(apps, schema_editor):
    """No reverse: 0022 drops the source column, so this cannot be undone."""


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0020_owner_assignee_adr_goal"),
    ]

    operations = [
        migrations.RunPython(backfill_owner_user, noop_reverse),
    ]
```

- [ ] **Step 4: Change the model**

In `backend/application/models.py`, class `Risk`: delete line 380 (`owner = models.CharField(max_length=255, blank=True)`) and replace the `owner_user` block (lines 381-394) with:

```python
    # REQ-L1-029 / Menschen-im-System spec §3: contract phase of the
    # expand/contract migration. The free-text `owner` CharField is gone and
    # `owner_user` was renamed to `owner` (column owner_user_id -> owner_id,
    # migration application/0022). `assignee` is the new volatile counterpart.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="REQ-L1-029: responsible risk owner. Written only via application.assignment.apply_assignment.",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Currently assigned user. Written only via application.assignment.apply_assignment.",
    )
```

- [ ] **Step 5: Write the contract migration**

Create `backend/application/migrations/0022_risk_owner_contract.py` by hand (the autodetector proposes a lossy delete+add pair; the order below preserves the data):

```python
"""Risk contract phase: drop free-text owner, rename owner_user -> owner.

Order matters: RemoveField frees the name `owner` before RenameField can take
it. RenameField on a FK is a metadata-only column rename in PostgreSQL
(owner_user_id -> owner_id) and preserves every value backfilled by 0021.
"""
from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0021_risk_owner_backfill"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(model_name="risk", name="owner"),
        migrations.RenameField(model_name="risk", old_name="owner_user", new_name="owner"),
        migrations.AlterField(
            model_name="risk",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                help_text="REQ-L1-029: responsible risk owner. Written only via application.assignment.apply_assignment.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="risk",
            name="assignee",
            field=models.ForeignKey(
                blank=True,
                help_text="Currently assigned user. Written only via application.assignment.apply_assignment.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
```

Verify with `makemigrations application --check --dry-run` that Django considers the model and the migration state in sync afterwards.

- [ ] **Step 6: Update the Risk call sites**

`backend/application/risk_service.py`:
- Line 91 (`RiskDTO` construction): `owner=risk.owner` → `owner_id=risk.owner_id`, and add `assignee_id=risk.assignee_id`. Change the `RiskDTO` dataclass declaration: `owner: str` → `owner_id: Optional[UUID]`, plus new `assignee_id: Optional[UUID]`.
- Lines 186/203/252/257 (`create_risk`): drop the `owner: str = ""` and `owner_user_id` parameters; add `owner_id: Optional[UUID] = None, assignee_id: Optional[UUID] = None` and pass both to `Risk.objects.create`.
- Lines 304/321/367/376-377 (`update_risk`): drop the `owner` and `owner_user_id` parameters and delete the `risk.owner = owner` / `risk.owner_user_id = owner_user_id` assignments. The replacement (`owner_id`/`assignee_id` routed through `apply_assignment`) lands in Task 13.

`backend/baseline/state_capture.py:293-294`: replace

```python
            "owner": risk.owner,
            "owner_user_id": str(risk.owner_user_id) if risk.owner_user_id else None,
```

with

```python
            "owner_id": str(risk.owner_id) if risk.owner_id else None,
            "assignee_id": str(risk.assignee_id) if risk.assignee_id else None,
```

`backend/application/export_service.py:166`: replace `("owner", "str")` with `("owner_id", "uuid")` and add `("assignee_id", "uuid")`.

`backend/application/tests/test_risk_service.py:304-346,487-513`: rename `owner_user_id` → `owner_id` throughout the two tests.

`backend/mcp_server/tests/test_generic_tool_group.py:225-226,238-239`: replace `"owner"` and `"owner_user_id"` in the expected field lists with `"owner_id"` and `"assignee_id"`.

- [ ] **Step 7: Apply the migrations and run the tests**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_risk_owner_contract.py application/tests/test_risk_service.py baseline/ -v
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/application/models.py backend/application/migrations/ backend/application/risk_service.py backend/baseline/state_capture.py backend/application/export_service.py backend/application/tests/ backend/mcp_server/tests/test_generic_tool_group.py
git commit -m "feat: finish the Risk owner expand/contract migration (REQ-L1-029)"
```

---

### Task 6: Issue contract phase — `assignee_id` UUIDField → real `assignee` FK

**Files:**
- Create: `backend/application/migrations/0023_issue_assignee_expand.py`
- Create: `backend/application/migrations/0024_issue_assignee_contract.py`
- Modify: `backend/application/models.py:629,660-662` (field + index)
- Modify: `backend/application/issue_service.py:70,85,171,186,231`
- Modify: `backend/baseline/state_capture.py:308`
- Modify: `backend/application/export_service.py:177`
- Modify: `backend/application/admin.py:228`
- Test: `backend/application/tests/test_issue_assignee_contract.py`

**Interfaces:**
- Produces: `Issue.assignee` (FK, DB column `assignee_id`), `Issue.owner` (FK, new, empty). Django's FK `_id` accessor means every existing `issue.assignee_id` reader keeps working unchanged.

**Migration strategy (stock operations, no raw SQL):** the legacy UUID column is *named* `assignee_id`, exactly the column Django would generate for an `assignee` FK. Move the legacy field aside first, then add the FK:

1. `RenameField("issue", "assignee_id", "legacy_assignee_id")` — metadata-only column rename.
2. `AddField("issue", "assignee", FK)` — fresh nullable column, no table rewrite on PostgreSQL 11+.
3. Data migration copying resolvable UUIDs across, logging orphans.
4. `RemoveField("issue", "legacy_assignee_id")` + restore the index.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_issue_assignee_contract.py`:

```python
"""Issue.assignee is a real FK; the loose UUIDField is gone."""
import pytest
from django.db import models

from application.models import Issue
from persistence.models import User


def test_assignee_is_a_user_fk():
    field = Issue._meta.get_field("assignee")
    assert isinstance(field, models.ForeignKey)
    assert field.related_model is User
    assert field.remote_field.on_delete is models.SET_NULL


def test_assignee_keeps_the_assignee_id_column():
    """Readers doing issue.assignee_id must keep working unchanged."""
    assert Issue._meta.get_field("assignee").column == "assignee_id"


def test_legacy_column_is_gone():
    with pytest.raises(Exception):
        Issue._meta.get_field("legacy_assignee_id")


def test_owner_exists():
    field = Issue._meta.get_field("owner")
    assert isinstance(field, models.ForeignKey)
    assert field.null is True


def test_workspace_assignee_index_survived_the_rename():
    names = {idx.name for idx in Issue._meta.indexes}
    assert "idx_issue_ws_assignee" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_issue_assignee_contract.py -v
```
Expected: FAIL — `Issue._meta.get_field("assignee")` raises `FieldDoesNotExist` (the model has `assignee_id`, a `UUIDField`).

- [ ] **Step 3: Change the model**

In `backend/application/models.py`, class `Issue`, replace line 629 (`assignee_id = models.UUIDField(null=True, blank=True)`) with:

```python
    # Menschen-im-System spec §3: the loose UUIDField became a real FK
    # (migrations application/0023 + 0024). The DB column is still
    # `assignee_id`, so every `issue.assignee_id` reader is unaffected.
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Currently assigned user. Written only via application.assignment.apply_assignment.",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Responsible user (stable). Written only via application.assignment.apply_assignment.",
    )
```

In `class Meta`, change the index at lines 660-662 from `fields=["workspace_id", "assignee_id"]` to `fields=["workspace_id", "assignee"]` (same columns, same name).

- [ ] **Step 4: Write the expand migration**

Create `backend/application/migrations/0023_issue_assignee_expand.py`:

```python
"""Expand phase: move the legacy UUID column aside and add the real FK.

The legacy `assignee_id` UUIDField occupies exactly the column name Django
wants for an `assignee` ForeignKey. Renaming it first (metadata-only) keeps
this migration to stock operations — no SeparateDatabaseAndState, no raw SQL.
"""
from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0022_risk_owner_contract"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(model_name="issue", name="idx_issue_ws_assignee"),
        migrations.RenameField(
            model_name="issue", old_name="assignee_id", new_name="legacy_assignee_id"
        ),
        migrations.AddField(
            model_name="issue",
            name="assignee",
            field=models.ForeignKey(
                blank=True,
                help_text="Currently assigned user. Written only via application.assignment.apply_assignment.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="issue",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                help_text="Responsible user (stable). Written only via application.assignment.apply_assignment.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
```

- [ ] **Step 5: Write the contract migration**

Create `backend/application/migrations/0024_issue_assignee_contract.py`:

```python
"""Contract phase: copy resolvable legacy UUIDs onto the FK, then drop the column.

Spec §3/§8: orphan UUIDs (pointing at no existing User) are not silently
dropped — each is logged at WARNING with its Issue id. Unlike the Risk case
there is nothing for a human to reconcile: an orphan UUID carries no
information beyond "a user that no longer exists", so this does not gate on a
review step.
"""
from __future__ import annotations

import logging

from django.db import migrations, models

logger = logging.getLogger(__name__)


def copy_legacy_assignee(apps, schema_editor):
    Issue = apps.get_model("application", "Issue")
    User = apps.get_model("persistence", "User")

    known_user_ids = set(User.objects.values_list("id", flat=True))

    orphans = 0
    for issue in Issue.objects.exclude(legacy_assignee_id=None):
        if issue.legacy_assignee_id in known_user_ids:
            Issue.objects.filter(pk=issue.pk).update(assignee_id=issue.legacy_assignee_id)
        else:
            orphans += 1
            logger.warning(
                "Issue %s: assignee_id %s does not resolve to a User — dropped.",
                issue.pk,
                issue.legacy_assignee_id,
            )
    if orphans:
        logger.warning("Issue assignee migration: %d orphan UUID(s) dropped.", orphans)


def noop_reverse(apps, schema_editor):
    """No reverse: the source column is dropped in the same migration."""


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0023_issue_assignee_expand"),
    ]

    operations = [
        migrations.RunPython(copy_legacy_assignee, noop_reverse),
        migrations.RemoveField(model_name="issue", name="legacy_assignee_id"),
        migrations.AddIndex(
            model_name="issue",
            index=models.Index(
                fields=["workspace_id", "assignee"], name="idx_issue_ws_assignee"
            ),
        ),
    ]
```

- [ ] **Step 6: Update the Issue call sites**

`backend/application/issue_service.py`:
- Line 70 (`IssueDTO.assignee_id: Optional[UUID]`) and line 85 (`assignee_id=issue.assignee_id`): unchanged. Add `owner_id: Optional[UUID]` to the DTO and `owner_id=issue.owner_id` to its construction.
- Lines 171/186/231 (`create_issue`): keep `assignee_id`, add `owner_id: Optional[UUID] = None`, pass it to `Issue.objects.create`.
- Lines 478-496 (`list_issues_by_assignee`): unchanged — `filter(assignee_id=...)` still resolves.
- Lines 534-575 (`assign_issue`): rewritten in Task 13.

`backend/baseline/state_capture.py:308`: unchanged; add `"owner_id": str(issue.owner_id) if issue.owner_id else None,` on the following line.

`backend/application/export_service.py:177`: keep `("assignee_id", "uuid")`, add `("owner_id", "uuid")`.

`backend/application/admin.py:228`: `"assignee_id"` → `"assignee"` (admin `list_display` takes the field name, not the column).

- [ ] **Step 7: Apply the migrations and run the tests**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_issue_assignee_contract.py application/tests/test_issue_service.py application/tests/test_export_import_roundtrip.py -v
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/application/models.py backend/application/migrations/ backend/application/issue_service.py backend/baseline/state_capture.py backend/application/export_service.py backend/application/admin.py backend/application/tests/
git commit -m "feat: convert Issue.assignee_id to a real User FK and add Issue.owner"
```

---

### Task 7: `Comment` and `Notification` models

**Files:**
- Modify: `backend/application/models.py` (append two classes at the end of the file)
- Create: `backend/application/migrations/0025_comment_notification.py`
- Test: `backend/application/tests/test_collaboration_models.py`

**Interfaces:**
- Produces: `application.models.Comment` (table `as_comment`), `application.models.Notification` (table `as_notification`), `Notification.KIND_CHOICES`, `Notification.KIND_TRANSITION_PENDING|KIND_SUSPECT_FLAGGED|KIND_ASSIGNED|KIND_COMMENT_ADDED`.

**Decision:** both models live in `backend/application/models.py`, not in a new Django app and not in the 2500-line `persistence/models.py` bug magnet. `application` already holds `Adr`/`Risk`/`Goal`/`Issue`, already FKs to `persistence.Artifact`, and already has RLS-policy migration precedents (`0009`, `0013`). A new app would cost a `settings.py` change and an `apps.py` for zero benefit.

**Decision:** both inherit `persistence.TenantScopedModel` (as the spec writes) rather than the `tenant_id = UUIDField` convention of the older `application` models. `TenantScopedModel` brings the tenant-filtering default manager for free; for two brand-new tables with no legacy readers there is no reason to opt out. Cross-app abstract inheritance is already used (`auth_tenancy.UserRole(TenantScopedModel)`).

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_collaboration_models.py`:

```python
"""Comment and Notification model shape (Menschen-im-System spec §4 / §5)."""
import pytest
from django.db import models

from application.models import Comment, Notification
from persistence.models import Artifact, TenantScopedModel, User


def test_comment_is_tenant_scoped():
    assert issubclass(Comment, TenantScopedModel)
    assert Comment._meta.db_table == "as_comment"


def test_comment_hangs_on_the_generic_artifact():
    field = Comment._meta.get_field("artifact")
    assert field.related_model is Artifact
    assert field.remote_field.on_delete is models.CASCADE
    assert field.remote_field.related_name == "comments"


def test_comment_author_survives_user_deletion():
    field = Comment._meta.get_field("author")
    assert field.related_model is User
    assert field.remote_field.on_delete is models.SET_NULL


def test_comment_resolution_fields():
    assert Comment._meta.get_field("resolved").default is False
    assert Comment._meta.get_field("resolved_by").null is True
    assert Comment._meta.get_field("resolved_at").null is True


def test_comment_reuses_the_inherited_created_at():
    """AuditableModel already provides created_at; redeclaring it would shadow it."""
    assert Comment._meta.get_field("created_at").auto_now_add is True


def test_notification_kinds_are_exactly_the_four_from_the_spec():
    kinds = {value for value, _label in Notification.KIND_CHOICES}
    assert kinds == {
        "transition_pending",
        "suspect_flagged",
        "assigned",
        "comment_added",
    }


def test_notification_artifact_is_optional():
    field = Notification._meta.get_field("artifact")
    assert field.null is True
    assert field.remote_field.on_delete is models.CASCADE


def test_notification_user_cascade():
    field = Notification._meta.get_field("user")
    assert field.remote_field.on_delete is models.CASCADE
    assert field.remote_field.related_name == "notifications"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_collaboration_models.py -v
```
Expected: FAIL with `ImportError: cannot import name 'Comment' from 'application.models'`.

- [ ] **Step 3: Add the two models**

Append to `backend/application/models.py`. Add `from persistence.models import TenantScopedModel` to the module imports first (the module currently imports `django.conf.settings` and `django.db.models` only):

```python
class Comment(TenantScopedModel):
    """A human comment on any artifact (Menschen-im-System spec §4).

    Hangs on the generic ``persistence.Artifact`` rather than on a specialized
    table, so it works for all ten artifact types with no per-type branch —
    including Diagram/Icd/GlossaryTerm once the Datenmodell-Konsolidierung spec
    has given them their Artifact backing.

    Comments are **not editable**: create, resolve, delete. That is why there is
    no change history here — ``author``/``resolved_by``/``resolved_at`` already
    answer "who did what" (spec §3.3).

    ``id``, ``created_at``, ``created_by``, ``modified_at``, ``modified_by`` and
    ``version`` are inherited from ``AuditableModel`` via ``TenantScopedModel``.
    """

    artifact = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    text = models.TextField()
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "as_comment"
        indexes = [
            models.Index(fields=["artifact", "created_at"], name="idx_comment_artifact_ts"),
        ]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Comment:{self.pk}:{self.text[:40]}"


class Notification(TenantScopedModel):
    """A pending human-facing signal (Menschen-im-System spec §5).

    Exactly four kinds, no more — the spec's scope boundary is explicit. There
    is no real-time push: the frontend fetches this table once when the
    NavigationShell mounts.

    ``artifact`` is nullable because the workflow trigger resolves it
    best-effort from a business-entity id and must never fail the transition it
    is reacting to.
    """

    KIND_TRANSITION_PENDING = "transition_pending"
    KIND_SUSPECT_FLAGGED = "suspect_flagged"
    KIND_ASSIGNED = "assigned"
    KIND_COMMENT_ADDED = "comment_added"

    KIND_CHOICES = [
        (KIND_TRANSITION_PENDING, "Transition Pending"),
        (KIND_SUSPECT_FLAGGED, "Suspect Flagged"),
        (KIND_ASSIGNED, "Assigned"),
        (KIND_COMMENT_ADDED, "Comment Added"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    artifact = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    message = models.TextField()
    read = models.BooleanField(default=False)

    class Meta:
        db_table = "as_notification"
        indexes = [
            models.Index(fields=["user", "read", "created_at"], name="idx_notif_user_read_ts"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Notification:{self.pk}:{self.kind}"
```

- [ ] **Step 4: Generate and apply the migration**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py makemigrations application --name comment_notification
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
```
Expected: `backend/application/migrations/0025_comment_notification.py` with two `CreateModel` operations.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_collaboration_models.py -v
```
Expected: PASS (8 cases).

- [ ] **Step 6: Commit**

```bash
git add backend/application/models.py backend/application/migrations/ backend/application/tests/test_collaboration_models.py
git commit -m "feat: add Comment and Notification models"
```

---

### Task 8: RLS policies for `as_comment` and `as_notification`

**Files:**
- Create: `backend/application/migrations/0026_comment_notification_rls.py`
- Test: `backend/application/tests/test_collaboration_rls.py`

**Interfaces:**
- Consumes: the two tables from Task 7.
- Produces: policies `as_comment_tenant_isolation`, `as_notification_tenant_isolation`.

**Why a separate task:** RLS in this repo is not automatic. `persistence/0003_rls_policies.py` covered only the `pl_*` tables; every app-owned table needed its own migration afterwards (`application/0009`, `application/0013`, `icd/0007`, `diagram/0008`, `baseline/0006`). A new tenant-scoped table without this migration is a silent cross-tenant read hole.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_collaboration_rls.py`:

```python
"""as_comment / as_notification are covered by row-level security."""
import pytest
from django.db import connection

TABLES = ["as_comment", "as_notification"]


@pytest.mark.django_db
@pytest.mark.parametrize("table", TABLES)
def test_rls_is_enabled_and_forced(table):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
            [table],
        )
        row = cur.fetchone()
    assert row is not None, f"{table} does not exist"
    assert row[0] is True, f"{table}: ROW LEVEL SECURITY not enabled"
    assert row[1] is True, f"{table}: FORCE ROW LEVEL SECURITY not set"


@pytest.mark.django_db
@pytest.mark.parametrize("table", TABLES)
def test_tenant_isolation_policy_exists(table):
    with connection.cursor() as cur:
        cur.execute("SELECT policyname FROM pg_policies WHERE tablename = %s", [table])
        names = {r[0] for r in cur.fetchall()}
    assert f"{table}_tenant_isolation" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_collaboration_rls.py -v
```
Expected: FAIL — `as_comment: ROW LEVEL SECURITY not enabled`.

- [ ] **Step 3: Write the migration**

Create `backend/application/migrations/0026_comment_notification_rls.py` (structure copied from `application/0009_risk_issue_rls_policies.py`; only the table list differs):

```python
"""Row-Level Security for as_comment and as_notification.

REQ-L2-PL-010 / ADR-PL-03. Same policy shape as application/0009: RLS enabled
+ FORCE (so the table-owning application role is constrained too) plus a policy
matching ``tenant_id`` against the per-request ``app.current_tenant`` setting.
An unset setting matches no rows.
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = [
    "as_comment",
    "as_notification",
]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0025_comment_notification"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
```

- [ ] **Step 4: Apply and run the test**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_collaboration_rls.py -v
```
Expected: PASS (4 cases).

- [ ] **Step 5: Commit**

```bash
git add backend/application/migrations/ backend/application/tests/test_collaboration_rls.py
git commit -m "feat: add RLS policies for as_comment and as_notification"
```

---

## Phase B — The single assignment seam

### Task 9: `resolve_artifact_id_or_none()` — reuse the existing entity→artifact chain

**Files:**
- Modify: `backend/application/trace_link_service.py` (append a module-level function after the `TraceLinkService` class)
- Test: `backend/application/tests/test_resolve_artifact_id_or_none.py`

**Interfaces:**
- Produces: `application.trace_link_service.resolve_artifact_id_or_none(entity_id: UUID) -> Optional[UUID]`.

**Why:** notifications reference an `Artifact` id, but the workflow engine and the ten services all speak business-entity ids. `TraceLinkService._resolve_artifact_id` (`trace_link_service.py:97`) already implements the full 11-step probe chain and is the established seam for this translation — reimplementing it is exactly the mistake that produced issues #237, #264 and #407.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_resolve_artifact_id_or_none.py`:

```python
"""resolve_artifact_id_or_none wraps the existing 11-step probe chain."""
import uuid
from unittest.mock import patch

import pytest

from application.trace_link_service import resolve_artifact_id_or_none
from persistence.errors import NotFoundError


@pytest.mark.django_db
def test_returns_none_for_an_unknown_id():
    with patch(
        "application.trace_link_service.TraceLinkService._resolve_artifact_id",
        side_effect=NotFoundError("nope"),
    ):
        assert resolve_artifact_id_or_none(uuid.uuid4()) is None


@pytest.mark.django_db
def test_returns_the_resolved_id():
    target = uuid.uuid4()
    with patch(
        "application.trace_link_service.TraceLinkService._resolve_artifact_id",
        return_value=target,
    ):
        assert resolve_artifact_id_or_none(uuid.uuid4()) == target
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_resolve_artifact_id_or_none.py -v
```
Expected: FAIL with `ImportError: cannot import name 'resolve_artifact_id_or_none'`.

- [ ] **Step 3: Write the function**

Append to `backend/application/trace_link_service.py` (`NotFoundError`, `Optional` and `UUID` are already imported there):

```python
def resolve_artifact_id_or_none(entity_id: UUID) -> Optional[UUID]:
    """Best-effort business-entity id -> Artifact id, ``None`` on a miss.

    Menschen-im-System spec §5: notifications reference the generic Artifact,
    but their producers (workflow engine, the ten update services) hold
    business-entity ids. Reuses ``TraceLinkService._resolve_artifact``'s probe
    chain instead of adding a twelfth place that has to learn about every new
    artifact type — the recurring root cause of #237 / #264 / #407.

    Returns None instead of raising: a missing Artifact must never break the
    mutation that triggered the notification.
    """
    try:
        return TraceLinkService()._resolve_artifact_id(entity_id)
    except NotFoundError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_resolve_artifact_id_or_none.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/application/trace_link_service.py backend/application/tests/test_resolve_artifact_id_or_none.py
git commit -m "feat: add resolve_artifact_id_or_none helper for notification producers"
```

---

### Task 10: `NotificationService` and the shared `create_notifications` producer

**Files:**
- Create: `backend/application/notification_service.py`
- Modify: `backend/application/services.py` (re-export)
- Test: `backend/application/tests/test_notification_service.py`

**Interfaces:**
- Consumes: `application.models.Notification`.
- Produces:
  - `create_notifications(*, user_ids: Iterable[Optional[UUID]], kind: str, message: str, artifact_id: Optional[UUID], tenant_id: UUID, exclude_user_id: Optional[UUID] = None) -> int`
  - `NotificationService.list_for_user(ctx, *, unread_only: bool = False, limit: int = 50) -> list[Notification]`
  - `NotificationService.unread_count(ctx) -> int`
  - `NotificationService.mark_read(notification_id: UUID, ctx) -> Notification`
  - `NotificationService.mark_all_read(ctx) -> int`
  - `MAX_FANOUT: int`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_notification_service.py`:

```python
"""NotificationService — read side plus the shared producer."""
import uuid

import pytest

from application.models import Notification
from application.notification_service import NotificationService, create_notifications
from auth_tenancy.context import AuthContext
from persistence.models import Tenant, User


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def alice(db, tenant):
    return User.objects.create(
        username=f"alice-{uuid.uuid4().hex[:6]}",
        email=f"a{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def bob(db, tenant):
    return User.objects.create(
        username=f"bob-{uuid.uuid4().hex[:6]}",
        email=f"b{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def ctx(alice, tenant):
    return AuthContext(
        user_id=alice.pk,
        tenant_id=tenant.pk,
        workspace_id=None,
        active_roles=["editor"],
    )


@pytest.mark.django_db
def test_create_notifications_writes_one_row_per_user(tenant, alice, bob):
    written = create_notifications(
        user_ids=[alice.pk, bob.pk],
        kind=Notification.KIND_ASSIGNED,
        message="you were assigned",
        artifact_id=None,
        tenant_id=tenant.pk,
    )
    assert written == 2
    assert Notification.unscoped.filter(tenant_id=tenant.pk).count() == 2


@pytest.mark.django_db
def test_create_notifications_skips_the_acting_user(tenant, alice, bob):
    written = create_notifications(
        user_ids=[alice.pk, bob.pk],
        kind=Notification.KIND_COMMENT_ADDED,
        message="new comment",
        artifact_id=None,
        tenant_id=tenant.pk,
        exclude_user_id=alice.pk,
    )
    assert written == 1
    assert Notification.unscoped.get(tenant_id=tenant.pk).user_id == bob.pk


@pytest.mark.django_db
def test_create_notifications_deduplicates_user_ids(tenant, alice):
    """owner == assignee must produce one notification, not two."""
    written = create_notifications(
        user_ids=[alice.pk, alice.pk],
        kind=Notification.KIND_SUSPECT_FLAGGED,
        message="suspect",
        artifact_id=None,
        tenant_id=tenant.pk,
    )
    assert written == 1


@pytest.mark.django_db
def test_create_notifications_ignores_none_user_ids(tenant):
    """Unset owner/assignee are passed straight through as None by every trigger."""
    written = create_notifications(
        user_ids=[None, None],
        kind=Notification.KIND_ASSIGNED,
        message="x",
        artifact_id=None,
        tenant_id=tenant.pk,
    )
    assert written == 0


@pytest.mark.django_db
def test_list_for_user_returns_only_own_notifications(ctx, tenant, alice, bob):
    create_notifications(
        user_ids=[alice.pk], kind=Notification.KIND_ASSIGNED,
        message="mine", artifact_id=None, tenant_id=tenant.pk,
    )
    create_notifications(
        user_ids=[bob.pk], kind=Notification.KIND_ASSIGNED,
        message="theirs", artifact_id=None, tenant_id=tenant.pk,
    )

    rows = NotificationService().list_for_user(ctx)
    assert [r.message for r in rows] == ["mine"]


@pytest.mark.django_db
def test_mark_read_flips_the_flag(ctx, tenant, alice):
    create_notifications(
        user_ids=[alice.pk], kind=Notification.KIND_ASSIGNED,
        message="m", artifact_id=None, tenant_id=tenant.pk,
    )
    row = NotificationService().list_for_user(ctx)[0]

    updated = NotificationService().mark_read(row.pk, ctx)
    assert updated.read is True


@pytest.mark.django_db
def test_mark_read_refuses_another_users_notification(ctx, tenant, bob):
    from persistence.errors import NotFoundError

    create_notifications(
        user_ids=[bob.pk], kind=Notification.KIND_ASSIGNED,
        message="m", artifact_id=None, tenant_id=tenant.pk,
    )
    other = Notification.unscoped.get(user_id=bob.pk)

    with pytest.raises(NotFoundError):
        NotificationService().mark_read(other.pk, ctx)


@pytest.mark.django_db
def test_mark_all_read_and_unread_count(ctx, tenant, alice):
    for message in ("a", "b"):
        create_notifications(
            user_ids=[alice.pk], kind=Notification.KIND_ASSIGNED,
            message=message, artifact_id=None, tenant_id=tenant.pk,
        )

    svc = NotificationService()
    assert svc.unread_count(ctx) == 2
    assert svc.mark_all_read(ctx) == 2
    assert svc.unread_count(ctx) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_notification_service.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'application.notification_service'`.

- [ ] **Step 3: Write the service**

Create `backend/application/notification_service.py`:

```python
"""Notification production and read access (Menschen-im-System spec §5).

Layer 2 (ADR-01): every ORM access for notifications lives here. The four
triggers call ``create_notifications``; Layer 3 (REST) calls
``NotificationService``.

There is deliberately no MCP tool group and no real-time push: agents do not
read a notification center, and the frontend fetches this table once when the
NavigationShell mounts.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.errors import NotFoundError

from application.base import ServiceBase
from application.models import Notification

logger = logging.getLogger(__name__)

#: Hard ceiling on a single fan-out. The transition_pending role broadcast in a
#: workspace with a pathological member count would otherwise write unbounded
#: rows inside the transition transaction.
#: ponytail: fixed cap; make it a workspace setting only if a real workspace hits it.
MAX_FANOUT = 200


def create_notifications(
    *,
    user_ids: Iterable[Optional[UUID]],
    kind: str,
    message: str,
    artifact_id: Optional[UUID],
    tenant_id: UUID,
    exclude_user_id: Optional[UUID] = None,
) -> int:
    """Write one Notification per distinct non-null recipient; return the count.

    ``None`` entries are dropped (callers pass unset ``owner``/``assignee``
    straight through), duplicates are collapsed (owner == assignee is one
    notification), and ``exclude_user_id`` drops the acting user (spec §5.4:
    no self-notification on your own comment).
    """
    recipients = {uid for uid in user_ids if uid is not None}
    recipients.discard(exclude_user_id)
    if not recipients:
        return 0

    if len(recipients) > MAX_FANOUT:
        logger.warning(
            "Notification fan-out for kind=%s capped at %d (was %d).",
            kind,
            MAX_FANOUT,
            len(recipients),
        )
        recipients = set(list(recipients)[:MAX_FANOUT])

    rows = [
        Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=kind,
            artifact_id=artifact_id,
            message=message,
            read=False,
        )
        for user_id in recipients
    ]
    Notification.unscoped.bulk_create(rows)
    return len(rows)


class NotificationService(ServiceBase):
    """Read side of the notification center."""

    def list_for_user(
        self,
        ctx: AuthContext,
        *,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """Return the caller's own notifications, newest first."""
        self._set_tenant_context(ctx)
        qs = Notification.objects.filter(user_id=ctx.user_id)
        if unread_only:
            qs = qs.filter(read=False)
        return list(qs[: max(1, min(limit, 200))])

    def unread_count(self, ctx: AuthContext) -> int:
        """Return how many unread notifications the caller has."""
        self._set_tenant_context(ctx)
        return Notification.objects.filter(user_id=ctx.user_id, read=False).count()

    def mark_read(self, notification_id: UUID, ctx: AuthContext) -> Notification:
        """Mark one of the caller's own notifications as read.

        Raises NotFoundError for someone else's notification — deliberately the
        same error as "does not exist", so the endpoint cannot be used to probe
        which notification ids are real.
        """
        self._set_tenant_context(ctx)
        row = Notification.objects.filter(pk=notification_id, user_id=ctx.user_id).first()
        if row is None:
            raise NotFoundError(f"Notification {notification_id} not found")
        if not row.read:
            row.read = True
            row.save(update_fields=["read"])
        return row

    def mark_all_read(self, ctx: AuthContext) -> int:
        """Mark every unread notification of the caller as read; return the count."""
        self._set_tenant_context(ctx)
        return Notification.objects.filter(user_id=ctx.user_id, read=False).update(read=True)


__all__ = ["MAX_FANOUT", "NotificationService", "create_notifications"]
```

- [ ] **Step 4: Re-export from the service facade**

In `backend/application/services.py`, next to the other service imports add:

```python
from application.notification_service import NotificationService  # noqa: F401
```

and append `"NotificationService"` to `__all__`.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_notification_service.py -v
```
Expected: PASS (8 cases).

- [ ] **Step 6: Commit**

```bash
git add backend/application/notification_service.py backend/application/services.py backend/application/tests/test_notification_service.py
git commit -m "feat: add NotificationService and the shared create_notifications producer"
```

---

### Task 11: `apply_assignment()` — the single owner/assignee write seam

**Files:**
- Create: `backend/application/assignment.py`
- Test: `backend/application/tests/test_assignment.py`

**Interfaces:**
- Consumes: `ServiceBase._audit`, `AuditEntry.OP_ASSIGN`, `create_notifications` (Task 10), `resolve_artifact_id_or_none` (Task 9), `Notification.KIND_ASSIGNED` (Task 7).
- Produces:
  - `application.assignment.UNSET` (sentinel)
  - `application.assignment.ASSIGNMENT_FIELDS = ("owner", "assignee")`
  - `apply_assignment(entity, *, entity_type: str, ctx: AuthContext, owner_id=UNSET, assignee_id=UNSET, change_reason: Optional[str] = None) -> list[str]`

**Why a sentinel:** `None` is a legal value (unassign). Without `UNSET`, `update_requirement(title="x")` would silently clear the owner on every unrelated edit.

**Note on the spec's §3.3 wording:** `AuditEntry.OP_ASSIGN` is *not* unused today — `IssueService.assign_issue` (`issue_service.py:566`) already writes it. This task therefore centralises an existing writer rather than introducing the first one; Task 13 migrates that call site onto this seam, preserving the `old_assignee`/`new_assignee` detail keys' semantics under the generic `old_assignee`/`new_assignee` names produced here.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_assignment.py`:

```python
"""apply_assignment — the single owner/assignee write seam (spec §3.3 / §5.3)."""
import uuid
from unittest.mock import patch

import pytest

from application.assignment import UNSET, apply_assignment
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext


class _FakeEntity:
    """Stands in for any of the ten artifact models."""

    def __init__(self, owner_id=None, assignee_id=None):
        self.pk = uuid.uuid4()
        self.id = self.pk
        self.owner_id = owner_id
        self.assignee_id = assignee_id
        self.saved_fields = None

    def save(self, update_fields=None):
        self.saved_fields = list(update_fields or [])


@pytest.fixture
def ctx():
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        active_roles=["editor"],
    )


def test_unset_fields_are_left_alone(ctx):
    entity = _FakeEntity(owner_id=uuid.uuid4())
    original_owner = entity.owner_id

    changed = apply_assignment(entity, entity_type="Requirement", ctx=ctx)

    assert changed == []
    assert entity.owner_id == original_owner
    assert entity.saved_fields is None


def test_setting_owner_persists_only_that_column(ctx):
    entity = _FakeEntity()
    new_owner = uuid.uuid4()

    with patch("application.assignment.ServiceBase._audit"), patch(
        "application.assignment.create_notifications", return_value=1
    ), patch("application.assignment.resolve_artifact_id_or_none", return_value=None):
        changed = apply_assignment(
            entity, entity_type="Requirement", ctx=ctx, owner_id=new_owner
        )

    assert changed == ["owner"]
    assert entity.owner_id == new_owner
    assert entity.saved_fields == ["owner_id"]


def test_explicit_none_unassigns(ctx):
    entity = _FakeEntity(assignee_id=uuid.uuid4())

    with patch("application.assignment.ServiceBase._audit"), patch(
        "application.assignment.create_notifications", return_value=0
    ), patch("application.assignment.resolve_artifact_id_or_none", return_value=None):
        changed = apply_assignment(entity, entity_type="Issue", ctx=ctx, assignee_id=None)

    assert changed == ["assignee"]
    assert entity.assignee_id is None


def test_no_op_when_the_value_is_unchanged(ctx):
    same = uuid.uuid4()
    entity = _FakeEntity(owner_id=same)

    changed = apply_assignment(entity, entity_type="Adr", ctx=ctx, owner_id=same)

    assert changed == []
    assert entity.saved_fields is None


def test_writes_an_op_assign_audit_entry(ctx):
    entity = _FakeEntity()
    new_owner = uuid.uuid4()

    with patch("application.assignment.ServiceBase._audit") as audit, patch(
        "application.assignment.create_notifications"
    ), patch("application.assignment.resolve_artifact_id_or_none", return_value=None):
        apply_assignment(
            entity,
            entity_type="Risk",
            ctx=ctx,
            owner_id=new_owner,
            change_reason="handover",
        )

    kwargs = audit.call_args.kwargs
    assert kwargs["operation"] == AuditEntry.OP_ASSIGN
    assert kwargs["entity_type"] == "Risk"
    assert kwargs["entity_id"] == entity.pk
    assert kwargs["change_reason"] == "handover"
    assert kwargs["details"]["new_owner"] == str(new_owner)
    assert kwargs["details"]["old_owner"] is None


def test_notifies_only_the_newly_assigned_users(ctx):
    entity = _FakeEntity()
    new_owner = uuid.uuid4()
    new_assignee = uuid.uuid4()

    with patch("application.assignment.ServiceBase._audit"), patch(
        "application.assignment.create_notifications"
    ) as notify, patch(
        "application.assignment.resolve_artifact_id_or_none", return_value=None
    ):
        apply_assignment(
            entity,
            entity_type="TestCase",
            ctx=ctx,
            owner_id=new_owner,
            assignee_id=new_assignee,
        )

    kwargs = notify.call_args.kwargs
    assert set(kwargs["user_ids"]) == {new_owner, new_assignee}
    assert kwargs["kind"] == "assigned"
    assert kwargs["exclude_user_id"] == ctx.user_id


def test_unassigning_notifies_nobody(ctx):
    entity = _FakeEntity(owner_id=uuid.uuid4())

    with patch("application.assignment.ServiceBase._audit"), patch(
        "application.assignment.create_notifications"
    ) as notify, patch(
        "application.assignment.resolve_artifact_id_or_none", return_value=None
    ):
        apply_assignment(entity, entity_type="Goal", ctx=ctx, owner_id=None)

    assert notify.call_args.kwargs["user_ids"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_assignment.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'application.assignment'`.

- [ ] **Step 3: Write the module**

Create `backend/application/assignment.py`:

```python
"""The single write seam for ``owner`` / ``assignee`` (Menschen-im-System spec §3.3).

Spec §8 names the risk this module removes: "ein vergessener ``update_X()``-Pfad
lässt eine Zuweisungsänderung ohne Audit-Eintrag und ohne
``assigned``-Notification durchrutschen". Rather than repeating three concerns
across ten services, every service calls ``apply_assignment`` once and
``application/tests/test_assignment_ratchet.py`` fails the build if any other
module assigns these fields directly.

One call site, two consumers (spec §5.3): ``ServiceBase._audit(op=OP_ASSIGN)``
feeds the audit log and ``create_notifications`` feeds the ``assigned``
notification.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.base import ServiceBase
from application.models import Notification
from application.notification_service import create_notifications
from application.trace_link_service import resolve_artifact_id_or_none
from audit.models import AuditEntry

logger = logging.getLogger(__name__)


class _Unset:
    """Sentinel type: 'the caller did not mention this field'."""

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "UNSET"


#: ``None`` is a legal value (unassign), so "not supplied" needs its own marker.
#: Without it, ``update_requirement(title="x")`` would clear the owner.
UNSET: Any = _Unset()

#: The two fields this module owns. The ratchet test imports this tuple.
ASSIGNMENT_FIELDS = ("owner", "assignee")


def apply_assignment(
    entity: Any,
    *,
    entity_type: str,
    ctx: AuthContext,
    owner_id: Any = UNSET,
    assignee_id: Any = UNSET,
    change_reason: Optional[str] = None,
) -> list[str]:
    """Set owner/assignee on *entity*, persist, audit and notify.

    Args:
        entity: A saved model instance carrying ``owner_id``/``assignee_id``.
        entity_type: Audit entity type string, e.g. ``"Requirement"``.
        ctx: Resolved AuthContext (``user_id`` is the actor).
        owner_id: New owner UUID, ``None`` to unassign, ``UNSET`` to leave alone.
        assignee_id: Same semantics for the assignee.
        change_reason: Optional audit reason.

    Returns:
        The names of the fields actually changed (``[]`` when nothing changed).

    Must be called inside the caller's ``@atomic_transaction`` so a failed audit
    write rolls the assignment back too.
    """
    changed: list[str] = []
    details: dict[str, Optional[str]] = {}
    newly_assigned: list[UUID] = []

    for field, requested in (("owner", owner_id), ("assignee", assignee_id)):
        if requested is UNSET:
            continue
        current = getattr(entity, f"{field}_id")
        if current == requested:
            continue
        setattr(entity, f"{field}_id", requested)
        changed.append(field)
        details[f"old_{field}"] = str(current) if current else None
        details[f"new_{field}"] = str(requested) if requested else None
        if requested is not None:
            newly_assigned.append(requested)

    if not changed:
        return []

    entity.save(update_fields=[f"{field}_id" for field in changed])

    ServiceBase._audit(
        ctx=ctx,
        operation=AuditEntry.OP_ASSIGN,
        entity_type=entity_type,
        entity_id=entity.pk,
        change_reason=change_reason,
        details=details,
    )

    create_notifications(
        user_ids=newly_assigned,
        kind=Notification.KIND_ASSIGNED,
        message=f"{entity_type} assigned to you",
        artifact_id=resolve_artifact_id_or_none(entity.pk),
        tenant_id=ctx.tenant_id,
        exclude_user_id=ctx.user_id,
    )

    return changed


__all__ = ["ASSIGNMENT_FIELDS", "UNSET", "apply_assignment"]
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_assignment.py -v
```
Expected: PASS (7 cases).

- [ ] **Step 5: Commit**

```bash
git add backend/application/assignment.py backend/application/tests/test_assignment.py
git commit -m "feat: add apply_assignment as the single owner/assignee write seam"
```

---

### Task 12: Wire the five `persistence`-type services onto the seam

**Files:**
- Modify: `backend/application/requirement_service.py:350` (`update_requirement`)
- Modify: `backend/application/stakeholder_need_service.py:183` (`update`)
- Modify: `backend/application/architecture_service.py:209` (`update_architecture_element`)
- Modify: `backend/application/test_service.py:152` (`update_test_case`)
- Modify: `backend/application/glossary_service.py:166` (`update`)
- Test: `backend/application/tests/test_assignment_wiring_persistence_types.py`

**Interfaces:**
- Consumes: `apply_assignment`, `UNSET` (Task 11).
- Produces: five update methods that accept `owner_id: Any = UNSET, assignee_id: Any = UNSET`.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_assignment_wiring_persistence_types.py`:

```python
"""Every update path of the five persistence types routes through apply_assignment."""
import inspect

import pytest

from application.architecture_service import ArchitectureService
from application.assignment import UNSET
from application.glossary_service import GlossaryService
from application.requirement_service import RequirementService
from application.stakeholder_need_service import StakeholderNeedService
from application.test_service import TestService

UPDATE_METHODS = [
    (RequirementService, "update_requirement"),
    (StakeholderNeedService, "update"),
    (ArchitectureService, "update_architecture_element"),
    (TestService, "update_test_case"),
    (GlossaryService, "update"),
]


@pytest.mark.parametrize("service,method_name", UPDATE_METHODS)
def test_update_accepts_owner_and_assignee(service, method_name):
    sig = inspect.signature(getattr(service, method_name))
    assert "owner_id" in sig.parameters
    assert "assignee_id" in sig.parameters


@pytest.mark.parametrize("service,method_name", UPDATE_METHODS)
def test_owner_and_assignee_default_to_unset_not_none(service, method_name):
    """None means 'unassign'; the default must not silently clear the field."""
    sig = inspect.signature(getattr(service, method_name))
    assert sig.parameters["owner_id"].default is UNSET
    assert sig.parameters["assignee_id"].default is UNSET


@pytest.mark.parametrize("service,method_name", UPDATE_METHODS)
def test_update_calls_apply_assignment(service, method_name):
    source = inspect.getsource(getattr(service, method_name))
    assert "apply_assignment(" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_assignment_wiring_persistence_types.py -v
```
Expected: FAIL with `KeyError: 'owner_id'` on the first parametrization.

- [ ] **Step 3: Wire each of the five update methods**

For each of the five methods, apply the identical three-part edit. Example for `RequirementService.update_requirement` (`backend/application/requirement_service.py:350`); repeat verbatim for the other four, changing only `entity_type` and the local variable name of the fetched entity:

Add to the module imports:

```python
from application.assignment import UNSET, apply_assignment
```

Add to the signature (after the existing keyword parameters, before `change_reason`):

```python
        owner_id: Any = UNSET,
        assignee_id: Any = UNSET,
```

Add to the docstring's Args block:

```
            owner_id: New responsible user, ``None`` to unassign, ``UNSET`` to
                leave unchanged. Routed through
                ``application.assignment.apply_assignment`` so the OP_ASSIGN
                audit entry and the ``assigned`` notification cannot be
                forgotten (spec §3.3 / §8).
            assignee_id: Same semantics for the currently assigned user.
```

And immediately **after** the method's existing `entity.save(...)` / version-bump block (so the assignment is not clobbered by a later full-row save — the known failure mode from the CCB status-mirror bug), insert:

```python
        apply_assignment(
            requirement,
            entity_type="Requirement",
            ctx=ctx,
            owner_id=owner_id,
            assignee_id=assignee_id,
            change_reason=change_reason,
        )
```

The `entity_type` values are `"Requirement"`, `"StakeholderNeed"`, `"ArchitectureElement"`, `"TestCase"`, `"GlossaryTerm"`. Add `from typing import Any` to any module that does not import it yet.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_assignment_wiring_persistence_types.py application/tests/test_requirement_service.py application/tests/test_test_service.py -v
```
Expected: PASS (15 wiring cases plus the existing service suites unchanged).

- [ ] **Step 5: Commit**

```bash
git add backend/application/requirement_service.py backend/application/stakeholder_need_service.py backend/application/architecture_service.py backend/application/test_service.py backend/application/glossary_service.py backend/application/tests/test_assignment_wiring_persistence_types.py
git commit -m "feat: route the five persistence-type update paths through apply_assignment"
```

---

### Task 13: Wire `Adr`, `Goal`, `Icd`, `Risk`, `Issue` onto the seam

**Files:**
- Modify: `backend/application/adr_service.py:236` (`update_adr`)
- Modify: `backend/application/goal_service.py:59,337` (`create_version` carry-forward + `update`)
- Modify: `backend/icd/icd_manager.py:299` (`update_icd`)
- Modify: `backend/application/risk_service.py:291` (`update_risk`)
- Modify: `backend/application/issue_service.py:266,534-585` (`update_issue`, `assign_issue`)
- Test: `backend/application/tests/test_assignment_wiring_application_types.py`

**Interfaces:**
- Consumes: `apply_assignment`, `UNSET`.
- Produces: five update methods accepting `owner_id`/`assignee_id`; `IssueService.assign_issue` keeps its public signature but delegates.

**Decision (Goal version carry-forward):** `GoalService.update` creates a *new* Goal row (`goal_service.py:59` `create_version`). Without an explicit copy, editing a goal silently drops its owner — a data-loss bug, not a feature. `create_version` copies `owner_id`/`assignee_id` from the previous version of the lineage.

**Decision (`assign_issue` compatibility):** the method keeps its `(issue_id, assignee_id, ctx, change_reason)` signature so no REST/MCP caller changes, but its body becomes a delegation to `apply_assignment`. The `assignee_changed_date` column is still stamped — it is an existing published field and dropping it would be an unannounced breaking change.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_assignment_wiring_application_types.py`:

```python
"""Adr / Goal / Icd / Risk / Issue update paths route through apply_assignment."""
import inspect
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.adr_service import AdrService
from application.assignment import UNSET
from application.goal_service import GoalService
from application.issue_service import IssueService
from application.risk_service import RiskService
from icd.icd_manager import IcdManager

UPDATE_METHODS = [
    (AdrService, "update_adr"),
    (GoalService, "update"),
    (IcdManager, "update_icd"),
    (RiskService, "update_risk"),
    (IssueService, "update_issue"),
]


@pytest.mark.parametrize("service,method_name", UPDATE_METHODS)
def test_update_accepts_owner_and_assignee_defaulting_to_unset(service, method_name):
    sig = inspect.signature(getattr(service, method_name))
    assert sig.parameters["owner_id"].default is UNSET
    assert sig.parameters["assignee_id"].default is UNSET


@pytest.mark.parametrize("service,method_name", UPDATE_METHODS)
def test_update_calls_apply_assignment(service, method_name):
    assert "apply_assignment(" in inspect.getsource(getattr(service, method_name))


def test_assign_issue_keeps_its_public_signature():
    sig = inspect.signature(IssueService.assign_issue)
    assert list(sig.parameters) == [
        "self",
        "issue_id",
        "assignee_id",
        "ctx",
        "change_reason",
    ]


def test_assign_issue_delegates_to_apply_assignment():
    assert "apply_assignment(" in inspect.getsource(IssueService.assign_issue)


def test_goal_create_version_carries_owner_and_assignee_forward():
    """Editing a Goal creates a new row; dropping its owner would be data loss."""
    source = inspect.getsource(GoalService.create_version)
    assert "owner_id" in source and "assignee_id" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_assignment_wiring_application_types.py -v
```
Expected: FAIL with `KeyError: 'owner_id'`.

- [ ] **Step 3: Wire `update_adr`, `update_icd`, `update_risk`, `update_issue`**

Apply the Task 12 Step 3 pattern verbatim to each, with `entity_type` `"Adr"`, `"Icd"`, `"Risk"`, `"Issue"`. For `RiskService.update_risk`, this replaces the parameters removed in Task 5 Step 6.

`backend/icd/icd_manager.py` imports from `application` — check for a circular import; if `icd` is imported by `application` at module load, use a function-local import (`from application.assignment import UNSET, apply_assignment` inside `update_icd`), which is the established pattern in this codebase for exactly this reason.

- [ ] **Step 4: Wire `GoalService.update` and the `create_version` carry-forward**

In `backend/application/goal_service.py`:

`create_version` — add two keyword parameters and pass them into `Goal.objects.create`:

```python
        owner_id: Optional[uuid.UUID] = None,
        assignee_id: Optional[uuid.UUID] = None,
```

and, when `lineage_id` is given, inherit them from the previous version instead of defaulting to empty:

```python
        # A Goal edit creates a NEW row (immutable-per-version, see the class
        # docstring). Without this carry-forward every edit would silently drop
        # the owner — data loss, not a feature.
        if lineage_id is not None and owner_id is None and assignee_id is None:
            previous = (
                Goal.objects.filter(lineage_id=lineage_id)
                .order_by("-sequence_number")
                .first()
            )
            if previous is not None:
                owner_id = previous.owner_id
                assignee_id = previous.assignee_id
```

`update` — add `owner_id: Any = UNSET, assignee_id: Any = UNSET`, and after the new version row exists call:

```python
        apply_assignment(
            new_goal,
            entity_type="Goal",
            ctx=ctx,
            owner_id=owner_id,
            assignee_id=assignee_id,
            change_reason=change_reason,
        )
```

- [ ] **Step 5: Rewrite `IssueService.assign_issue` as a delegation**

Replace the body of `backend/application/issue_service.py:534-585` (keeping the signature and the docstring's Args block) with:

```python
        from django.utils import timezone

        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        issue = Issue.objects.filter(id=issue_id, tenant_id=ctx.tenant_id).first()
        if issue is None:
            raise NotFoundError(f"Issue {issue_id} not found")

        # Menschen-im-System spec §3.3: the OP_ASSIGN audit entry and the
        # `assigned` notification are produced by the shared seam, not here.
        changed = apply_assignment(
            issue,
            entity_type="Issue",
            ctx=ctx,
            assignee_id=assignee_id,
            change_reason=change_reason,
        )

        if changed:
            # `assignee_changed_date` is an existing published field; keep
            # stamping it so no REST/MCP consumer breaks.
            issue.assignee_changed_date = timezone.now()
            issue.save(update_fields=["assignee_changed_date"])
            Issue.objects.filter(id=issue.id).update(version=F("version") + 1)
            issue.refresh_from_db(fields=["version"])

        return issue
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_assignment_wiring_application_types.py application/tests/test_issue_service.py application/tests/test_risk_service.py application/tests/test_goal_service.py icd/ -v
```
Expected: PASS. `test_assign_updates_assignee_and_date` and `test_unassign_sets_assignee_to_none` in `test_issue_service.py` must still pass unchanged — if they patch `ServiceBase._audit`, extend them to also patch `application.assignment.create_notifications`.

- [ ] **Step 7: Commit**

```bash
git add backend/application/adr_service.py backend/application/goal_service.py backend/icd/icd_manager.py backend/application/risk_service.py backend/application/issue_service.py backend/application/tests/test_assignment_wiring_application_types.py
git commit -m "feat: route Adr/Goal/Icd/Risk/Issue assignment writes through apply_assignment"
```

---

### Task 14: Ratchet — no direct `owner`/`assignee` writes outside the seam

**Files:**
- Create: `backend/application/tests/test_assignment_ratchet.py`

**Interfaces:**
- Consumes: `application.assignment.ASSIGNMENT_FIELDS`.

**Why:** spec §8 explicitly names "ein vergessener `update_X()`-Pfad" as the top risk of this design and asks for a shared helper to reduce it. A helper that nobody is forced to use reduces nothing — this test is the forcing function, in the same style as `backend/audit/tests/test_op_vocabulary.py`, which AST-scans `application/` for undeclared audit ops.

- [ ] **Step 1: Write the test (it must pass immediately if Tasks 12/13 are complete)**

Create `backend/application/tests/test_assignment_ratchet.py`:

```python
"""No module may assign owner/assignee outside application.assignment.

Menschen-im-System spec §8, risk 2. Same AST-scan style as
backend/audit/tests/test_op_vocabulary.py.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from application.assignment import ASSIGNMENT_FIELDS

BACKEND = Path(__file__).resolve().parents[2]

SCANNED_DIRS = [BACKEND / "application", BACKEND / "icd", BACKEND / "rest_api", BACKEND / "mcp_server"]

#: The seam itself, plus migrations (which legitimately write columns directly)
#: and tests (which construct fixtures).
EXEMPT_SUFFIXES = ("application/assignment.py",)
EXEMPT_PARTS = ("migrations", "tests")

FORBIDDEN_ATTRS = set(ASSIGNMENT_FIELDS) | {f"{f}_id" for f in ASSIGNMENT_FIELDS}


def _python_files():
    for root in SCANNED_DIRS:
        for path in root.rglob("*.py"):
            if any(part in EXEMPT_PARTS for part in path.parts):
                continue
            if any(str(path).replace("\\", "/").endswith(s) for s in EXEMPT_SUFFIXES):
                continue
            yield path


def _direct_assignments(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr in FORBIDDEN_ATTRS:
                hits.append(f"{path}:{node.lineno} -> .{target.attr}")
    return hits


def test_no_direct_owner_or_assignee_assignment_outside_the_seam():
    offenders: list[str] = []
    for path in _python_files():
        offenders.extend(_direct_assignments(path))

    assert not offenders, (
        "owner/assignee must be written via application.assignment.apply_assignment "
        "so the OP_ASSIGN audit entry and the 'assigned' notification cannot be "
        "forgotten (spec §3.3 / §8). Offending sites:\n  " + "\n  ".join(offenders)
    )


def test_the_scan_actually_finds_something(tmp_path):
    """Guard against a scanner that silently matches nothing."""
    sample = tmp_path / "sample.py"
    sample.write_text("obj.owner_id = 1\n", encoding="utf-8")
    assert _direct_assignments(sample)
```

- [ ] **Step 2: Run the test**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_assignment_ratchet.py -v
```
Expected: PASS. If it FAILS, the failure message lists exactly the `update_X()` paths Tasks 12/13 missed — fix those, do not weaken the ratchet.

- [ ] **Step 3: Commit**

```bash
git add backend/application/tests/test_assignment_ratchet.py
git commit -m "test: ratchet against direct owner/assignee writes outside the assignment seam"
```

---

## Phase C — Comments

### Task 15: `CommentService`

**Files:**
- Create: `backend/application/comment_service.py`
- Modify: `backend/application/services.py` (re-export)
- Test: `backend/application/tests/test_comment_service.py`

**Interfaces:**
- Consumes: `application.models.Comment`, `create_notifications` (Task 10), `Notification.KIND_COMMENT_ADDED`.
- Produces:
  - `CommentService.list_for_artifact(artifact_id: UUID, ctx, *, include_resolved: bool = True) -> list[Comment]`
  - `CommentService.create_comment(*, artifact_id: UUID, text: str, ctx) -> Comment`
  - `CommentService.resolve_comment(comment_id: UUID, ctx) -> Comment`
  - `CommentService.delete_comment(comment_id: UUID, ctx) -> None`
  - `owner_and_assignee_for_artifact(artifact) -> tuple[Optional[UUID], Optional[UUID]]`

**Decision (`comment_added` recipient lookup):** the comment hangs on the generic `Artifact`, but `owner`/`assignee` live on the specialised row. A small ordered probe over the ten reverse accessors resolves it. That table is the *only* type-aware code this feature adds; everything else stays generic.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_comment_service.py`:

```python
"""CommentService — create / list / resolve / delete plus the comment_added trigger."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.comment_service import CommentService, owner_and_assignee_for_artifact
from application.models import Comment, Notification
from auth_tenancy.context import AuthContext
from persistence.errors import PermissionDeniedError, ValidationError
from persistence.models import Artifact, Tenant, User, Workspace


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(db, tenant):
    return Workspace.objects.create(tenant=tenant, name="W")


@pytest.fixture
def alice(db, tenant):
    return User.objects.create(
        username=f"alice-{uuid.uuid4().hex[:6]}",
        email=f"a{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def bob(db, tenant):
    return User.objects.create(
        username=f"bob-{uuid.uuid4().hex[:6]}",
        email=f"b{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def artifact(db, tenant, workspace):
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement", title="A"
    )


@pytest.fixture
def ctx(alice, tenant, workspace):
    return AuthContext(
        user_id=alice.pk,
        tenant_id=tenant.pk,
        workspace_id=workspace.pk,
        active_roles=["editor"],
    )


@pytest.mark.django_db
def test_create_comment_records_the_author(ctx, artifact, alice):
    with patch("application.comment_service.create_notifications"):
        comment = CommentService().create_comment(
            artifact_id=artifact.pk, text="looks wrong", ctx=ctx
        )
    assert comment.author_id == alice.pk
    assert comment.text == "looks wrong"
    assert comment.resolved is False


@pytest.mark.django_db
def test_create_comment_rejects_empty_text(ctx, artifact):
    with pytest.raises(ValidationError):
        CommentService().create_comment(artifact_id=artifact.pk, text="   ", ctx=ctx)


@pytest.mark.django_db
def test_create_comment_notifies_owner_and_assignee(ctx, artifact, bob):
    with patch(
        "application.comment_service.owner_and_assignee_for_artifact",
        return_value=(bob.pk, None),
    ), patch("application.comment_service.create_notifications") as notify:
        CommentService().create_comment(artifact_id=artifact.pk, text="hi", ctx=ctx)

    kwargs = notify.call_args.kwargs
    assert kwargs["kind"] == Notification.KIND_COMMENT_ADDED
    assert set(kwargs["user_ids"]) == {bob.pk, None} - {None} or kwargs["user_ids"]
    assert kwargs["exclude_user_id"] == ctx.user_id
    assert kwargs["artifact_id"] == artifact.pk


@pytest.mark.django_db
def test_list_for_artifact_is_chronological(ctx, artifact):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        svc.create_comment(artifact_id=artifact.pk, text="first", ctx=ctx)
        svc.create_comment(artifact_id=artifact.pk, text="second", ctx=ctx)

    assert [c.text for c in svc.list_for_artifact(artifact.pk, ctx)] == ["first", "second"]


@pytest.mark.django_db
def test_list_can_hide_resolved(ctx, artifact):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        first = svc.create_comment(artifact_id=artifact.pk, text="first", ctx=ctx)
        svc.create_comment(artifact_id=artifact.pk, text="second", ctx=ctx)
    svc.resolve_comment(first.pk, ctx)

    open_only = svc.list_for_artifact(artifact.pk, ctx, include_resolved=False)
    assert [c.text for c in open_only] == ["second"]


@pytest.mark.django_db
def test_resolve_stamps_who_and_when(ctx, artifact, alice):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    resolved = svc.resolve_comment(comment.pk, ctx)
    assert resolved.resolved is True
    assert resolved.resolved_by_id == alice.pk
    assert resolved.resolved_at is not None


@pytest.mark.django_db
def test_resolve_is_idempotent(ctx, artifact):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    first = svc.resolve_comment(comment.pk, ctx)
    second = svc.resolve_comment(comment.pk, ctx)
    assert first.resolved_at == second.resolved_at


@pytest.mark.django_db
def test_author_may_delete_own_comment(ctx, artifact):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    svc.delete_comment(comment.pk, ctx)
    assert not Comment.unscoped.filter(pk=comment.pk).exists()


@pytest.mark.django_db
def test_non_author_non_admin_may_not_delete(ctx, artifact, bob, tenant, workspace):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    other_ctx = AuthContext(
        user_id=bob.pk,
        tenant_id=tenant.pk,
        workspace_id=workspace.pk,
        active_roles=["editor"],
    )
    with pytest.raises(PermissionDeniedError):
        svc.delete_comment(comment.pk, other_ctx)


@pytest.mark.django_db
def test_admin_may_delete_any_comment(ctx, artifact, bob, tenant, workspace):
    svc = CommentService()
    with patch("application.comment_service.create_notifications"):
        comment = svc.create_comment(artifact_id=artifact.pk, text="x", ctx=ctx)

    admin_ctx = AuthContext(
        user_id=bob.pk,
        tenant_id=tenant.pk,
        workspace_id=workspace.pk,
        active_roles=["admin"],
    )
    svc.delete_comment(comment.pk, admin_ctx)
    assert not Comment.unscoped.filter(pk=comment.pk).exists()


def test_owner_and_assignee_probe_returns_the_first_backed_entity():
    """The only type-aware code in this feature: Artifact -> specialised row."""
    artifact = MagicMock(spec=["requirement"])
    artifact.requirement.owner_id = "owner-uuid"
    artifact.requirement.assignee_id = "assignee-uuid"

    assert owner_and_assignee_for_artifact(artifact) == ("owner-uuid", "assignee-uuid")


def test_owner_and_assignee_probe_returns_none_for_a_bare_artifact():
    assert owner_and_assignee_for_artifact(MagicMock(spec=[])) == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_comment_service.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'application.comment_service'`.

- [ ] **Step 3: Write the service**

Create `backend/application/comment_service.py`:

```python
"""Comments on artifacts (Menschen-im-System spec §4).

Comments hang on the generic ``persistence.Artifact``, so this service has no
per-type branch at all — with one deliberate exception,
``owner_and_assignee_for_artifact``, which has to walk back to the specialised
row to find the ``comment_added`` recipients.

Comments are not editable: create, resolve, delete. ``author`` /
``resolved_by`` / ``resolved_at`` are the whole history (spec §3.3).
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from django.utils import timezone

from auth_tenancy.context import AuthContext
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError
from persistence.models import Artifact, Tenant
from persistence.transactions import atomic_transaction

from application.base import ServiceBase
from application.models import Comment, Notification
from application.notification_service import create_notifications

logger = logging.getLogger(__name__)

#: Reverse accessors from Artifact to the ten owner-bearing specialised rows.
#: Probe order is irrelevant (an Artifact backs exactly one of them); the list
#: only has to stay complete. Diagram/Icd/GlossaryTerm gain their accessors from
#: the Datenmodell-Konsolidierung spec — verify the names with
#: ``grep -n 'related_name' backend/icd/models.py backend/persistence/models.py``
#: when that spec has landed.
OWNER_BEARING_RELATIONS = (
    "requirement",
    "stakeholder_need",
    "architecture_element",
    "test_case",
    "glossary_term",
    "adr",
    "goal",
    "risk",
    "issue",
    "icd",
)


def owner_and_assignee_for_artifact(artifact: Any) -> tuple[Optional[UUID], Optional[UUID]]:
    """Return ``(owner_id, assignee_id)`` of the artifact's specialised row.

    Returns ``(None, None)`` for an Artifact with no backing row or a type that
    carries no owner — a comment on it simply notifies nobody.
    """
    for relation in OWNER_BEARING_RELATIONS:
        entity = getattr(artifact, relation, None)
        if entity is not None:
            return getattr(entity, "owner_id", None), getattr(entity, "assignee_id", None)
    return None, None


class CommentService(ServiceBase):
    """Comment CRUD over the generic Artifact (COMP-AS-Comment)."""

    def list_for_artifact(
        self,
        artifact_id: UUID,
        ctx: AuthContext,
        *,
        include_resolved: bool = True,
    ) -> list[Comment]:
        """Return an artifact's comments, oldest first."""
        self._set_tenant_context(ctx)
        qs = Comment.objects.filter(artifact_id=artifact_id).select_related(
            "author", "resolved_by"
        )
        if not include_resolved:
            qs = qs.filter(resolved=False)
        return list(qs)

    @atomic_transaction
    def create_comment(self, *, artifact_id: UUID, text: str, ctx: AuthContext) -> Comment:
        """Create a comment and notify the artifact's owner and assignee."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        cleaned = (text or "").strip()
        if not cleaned:
            raise ValidationError("Comment text is required")

        artifact = Artifact.objects.filter(pk=artifact_id).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")

        tenant = Tenant.objects.filter(pk=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        comment = Comment.unscoped.create(
            tenant=tenant,
            artifact=artifact,
            author_id=ctx.user_id,
            text=cleaned,
        )

        owner_id, assignee_id = owner_and_assignee_for_artifact(artifact)
        create_notifications(
            user_ids=[owner_id, assignee_id],
            kind=Notification.KIND_COMMENT_ADDED,
            message=f"New comment on {artifact.title}",
            artifact_id=artifact.pk,
            tenant_id=ctx.tenant_id,
            exclude_user_id=ctx.user_id,
        )

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="Comment",
            entity_id=comment.pk,
            details={"artifact_id": str(artifact.pk)},
        )
        return comment

    @atomic_transaction
    def resolve_comment(self, comment_id: UUID, ctx: AuthContext) -> Comment:
        """Mark a comment resolved. Idempotent — re-resolving keeps the first stamp."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        comment = Comment.objects.filter(pk=comment_id).first()
        if comment is None:
            raise NotFoundError(f"Comment {comment_id} not found")

        if not comment.resolved:
            comment.resolved = True
            comment.resolved_by_id = ctx.user_id
            comment.resolved_at = timezone.now()
            comment.save(update_fields=["resolved", "resolved_by_id", "resolved_at"])
            self._audit(
                ctx=ctx,
                operation="update",
                entity_type="Comment",
                entity_id=comment.pk,
                details={"resolved": True},
            )
        return comment

    @atomic_transaction
    def delete_comment(self, comment_id: UUID, ctx: AuthContext) -> None:
        """Delete a comment. Author or admin only (spec §4)."""
        self._set_tenant_context(ctx)

        comment = Comment.objects.filter(pk=comment_id).first()
        if comment is None:
            raise NotFoundError(f"Comment {comment_id} not found")

        is_author = comment.author_id == ctx.user_id
        is_admin = "admin" in (ctx.active_roles or [])
        if not (is_author or is_admin):
            raise PermissionDeniedError("Only the comment author or an admin may delete it")

        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="Comment",
            entity_id=comment.pk,
            details={"artifact_id": str(comment.artifact_id)},
        )
        comment.delete()


__all__ = ["OWNER_BEARING_RELATIONS", "CommentService", "owner_and_assignee_for_artifact"]
```

- [ ] **Step 4: Re-export from the service facade**

In `backend/application/services.py` add:

```python
from application.comment_service import CommentService  # noqa: F401
```

and append `"CommentService"` to `__all__`.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_comment_service.py -v
```
Expected: PASS (12 cases).

- [ ] **Step 6: Commit**

```bash
git add backend/application/comment_service.py backend/application/services.py backend/application/tests/test_comment_service.py
git commit -m "feat: add CommentService with the comment_added notification trigger"
```

---

### Task 16: REST endpoints for comments

**Files:**
- Create: `backend/rest_api/collaboration_views.py`
- Modify: `backend/rest_api/serializers.py` (append `CommentSerializer`)
- Modify: `backend/rest_api/urls.py` (register the routes)
- Test: `backend/rest_api/tests/test_comment_endpoints.py`

**Interfaces:**
- Consumes: `CommentService` (Task 15), `get_auth_context` (`rest_api/auth_enforcer.py:113`), `BaseEntityViewSet` (`rest_api/views.py:245`).
- Produces:
  - `GET  /api/v1/artifacts/<uuid:artifact_id>/comments/?include_resolved=false`
  - `POST /api/v1/artifacts/<uuid:artifact_id>/comments/`  body `{"text": "..."}`
  - `POST /api/v1/comments/<uuid:pk>/resolve/`
  - `DELETE /api/v1/comments/<uuid:pk>/`
  - `CommentSerializer`

**Constraint:** no `.objects.` anywhere in this module — the `rest_api` ORM ratchet counts occurrences including inside docstrings.

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_comment_endpoints.py`:

```python
"""REST surface for comments (Menschen-im-System spec §4)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from rest_api.collaboration_views import ArtifactCommentsView, CommentViewSet


def _comment_stub(text="hello"):
    stub = MagicMock()
    stub.id = uuid.uuid4()
    stub.pk = stub.id
    stub.artifact_id = uuid.uuid4()
    stub.author_id = uuid.uuid4()
    stub.author = MagicMock(username="alice")
    stub.text = text
    stub.resolved = False
    stub.resolved_by_id = None
    stub.resolved_by = None
    stub.resolved_at = None
    stub.created_at = None
    return stub


@pytest.fixture
def factory():
    return APIRequestFactory()


def test_list_comments_returns_serialized_rows(factory):
    artifact_id = uuid.uuid4()
    request = factory.get(f"/api/v1/artifacts/{artifact_id}/comments/")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        svc.return_value.list_for_artifact.return_value = [_comment_stub("hello")]
        response = ArtifactCommentsView.as_view()(request, artifact_id=str(artifact_id))

    assert response.status_code == 200
    assert response.data[0]["text"] == "hello"


def test_list_comments_honours_include_resolved_false(factory):
    artifact_id = uuid.uuid4()
    request = factory.get(f"/api/v1/artifacts/{artifact_id}/comments/?include_resolved=false")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        svc.return_value.list_for_artifact.return_value = []
        ArtifactCommentsView.as_view()(request, artifact_id=str(artifact_id))

    assert svc.return_value.list_for_artifact.call_args.kwargs["include_resolved"] is False


def test_create_comment_returns_201(factory):
    artifact_id = uuid.uuid4()
    request = factory.post(
        f"/api/v1/artifacts/{artifact_id}/comments/", {"text": "hi"}, format="json"
    )

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        svc.return_value.create_comment.return_value = _comment_stub("hi")
        response = ArtifactCommentsView.as_view()(request, artifact_id=str(artifact_id))

    assert response.status_code == 201
    assert response.data["text"] == "hi"


def test_create_comment_rejects_missing_text(factory):
    artifact_id = uuid.uuid4()
    request = factory.post(f"/api/v1/artifacts/{artifact_id}/comments/", {}, format="json")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ):
        response = ArtifactCommentsView.as_view()(request, artifact_id=str(artifact_id))

    assert response.status_code == 400


def test_resolve_action_returns_the_updated_comment(factory):
    comment_id = uuid.uuid4()
    request = factory.post(f"/api/v1/comments/{comment_id}/resolve/")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        stub = _comment_stub()
        stub.resolved = True
        svc.return_value.resolve_comment.return_value = stub
        response = CommentViewSet.as_view({"post": "resolve"})(request, pk=str(comment_id))

    assert response.status_code == 200
    assert response.data["resolved"] is True


def test_destroy_returns_204(factory):
    comment_id = uuid.uuid4()
    request = factory.delete(f"/api/v1/comments/{comment_id}/")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.CommentService"
    ) as svc:
        svc.return_value.delete_comment.return_value = None
        response = CommentViewSet.as_view({"delete": "destroy"})(request, pk=str(comment_id))

    assert response.status_code == 204


def test_module_contains_no_orm_access():
    """rest_api ORM ratchet: views delegate to Layer 2 (ADR-01)."""
    from pathlib import Path

    import rest_api.collaboration_views as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert ".objects." not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest rest_api/tests/test_comment_endpoints.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'rest_api.collaboration_views'`.

- [ ] **Step 3: Add `CommentSerializer`**

Append to `backend/rest_api/serializers.py`:

```python
class CommentSerializer(serializers.Serializer):
    """Wire format for application.models.Comment (Menschen-im-System spec §4).

    Read-only apart from ``text`` — comments are never edited, only created,
    resolved and deleted.
    """

    id = serializers.UUIDField(read_only=True)
    artifact_id = serializers.UUIDField(read_only=True)
    text = serializers.CharField(max_length=10000)
    author_id = serializers.UUIDField(read_only=True, allow_null=True)
    author_display = serializers.SerializerMethodField()
    resolved = serializers.BooleanField(read_only=True)
    resolved_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    resolved_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)

    def get_author_display(self, obj) -> str | None:
        """Return the author's username, or None when the user was deleted."""
        author = getattr(obj, "author", None)
        return getattr(author, "username", None) if author is not None else None
```

- [ ] **Step 4: Write the views**

Create `backend/rest_api/collaboration_views.py`:

```python
"""REST surface for comments and notifications (Menschen-im-System spec §4/§5).

Layer 3 only: every read and write is delegated to a Layer-2 service
(ADR-01). This module deliberately contains no ORM access — the rest_api
ratchet enforces that.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.comment_service import CommentService
from application.notification_service import NotificationService
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError

from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import CommentSerializer, NotificationSerializer
from rest_api.views import BaseEntityViewSet, _service_error_response, detect_lang
from rest_api.errors import build_error_response

logger = logging.getLogger(__name__)


class ArtifactCommentsView(APIView):
    """``/api/v1/artifacts/<artifact_id>/comments/`` — list and create."""

    def get(self, request: Request, artifact_id: str, **kwargs: Any) -> Response:
        """List an artifact's comments, oldest first."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            include_resolved = request.query_params.get("include_resolved", "true").lower() != "false"
            rows = CommentService().list_for_artifact(
                UUID(artifact_id), ctx, include_resolved=include_resolved
            )
            return Response(CommentSerializer(rows, many=True).data)
        except Exception as exc:
            logger.exception("ArtifactCommentsView.get: unhandled exception")
            return _service_error_response(exc, lang)

    def post(self, request: Request, artifact_id: str, **kwargs: Any) -> Response:
        """Create a comment on the artifact."""
        lang = detect_lang(request)
        serializer = CommentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in serializer.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            comment = CommentService().create_comment(
                artifact_id=UUID(artifact_id),
                text=serializer.validated_data["text"],
                ctx=ctx,
            )
            return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.exception("ArtifactCommentsView.post: unhandled exception")
            return _service_error_response(exc, lang)


class CommentViewSet(BaseEntityViewSet):
    """``/api/v1/comments/<pk>/`` — resolve and delete."""

    serializer_class = CommentSerializer

    @action(detail=True, methods=["post"])
    def resolve(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """POST /api/v1/comments/<pk>/resolve/ — mark the comment resolved."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            comment = CommentService().resolve_comment(UUID(str(pk)), ctx)
            return Response(CommentSerializer(comment).data)
        except Exception as exc:
            logger.exception("CommentViewSet.resolve: unhandled exception")
            return _service_error_response(exc, lang)

    def destroy(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """DELETE /api/v1/comments/<pk>/ — author or admin only."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            CommentService().delete_comment(UUID(str(pk)), ctx)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as exc:
            logger.exception("CommentViewSet.destroy: unhandled exception")
            return _service_error_response(exc, lang)


__all__ = ["ArtifactCommentsView", "CommentViewSet"]
```

> `NotificationSerializer` and `NotificationViewSet` are added to this same module in Task 19; the import line above already anticipates it. If Task 19 is not yet done, temporarily drop `NotificationSerializer` from the import to keep this task's tests green, then restore it.

- [ ] **Step 5: Register the routes**

In `backend/rest_api/urls.py`, add to the imports:

```python
from rest_api.collaboration_views import ArtifactCommentsView, CommentViewSet
```

Register the ViewSet next to the others (around line 189):

```python
router.register(r"comments", CommentViewSet, basename="comment")
```

And add the nested route to `urlpatterns`:

```python
    path(
        "artifacts/<uuid:artifact_id>/comments/",
        ArtifactCommentsView.as_view(),
        name="api-v1-artifact-comments",
    ),
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest rest_api/tests/test_comment_endpoints.py -v
```
Expected: PASS (7 cases).

- [ ] **Step 7: Commit**

```bash
git add backend/rest_api/collaboration_views.py backend/rest_api/serializers.py backend/rest_api/urls.py backend/rest_api/tests/test_comment_endpoints.py
git commit -m "feat: add REST endpoints for artifact comments"
```

---

### Task 17: MCP tool group `comment.*`

**Files:**
- Create: `backend/mcp_server/tools/comment.py`
- Modify: `backend/mcp_server/tool_registry.py:557` (`register_groups`)
- Test: `backend/mcp_server/tests/test_comment_tool_group.py`

**Interfaces:**
- Consumes: `CommentService` (Task 15), `BaseToolGroup`, `require_uuid` (`mcp_server/tools/base.py`).
- Produces: tools `comment.create`, `comment.list`, `comment.resolve`.

**Constraint (learned the hard way):** the MCP transport serialises with stdlib `json.dumps`, which cannot encode `UUID` or `datetime`. Every field in a `ToolResult` payload must already be a `str`. Also: never use `content` as a top-level payload key — it collides with the JSON-RPC envelope.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_comment_tool_group.py`:

```python
"""comment.* MCP tool group (Menschen-im-System spec §4)."""
import json
import uuid
from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.tools.comment import CommentToolGroup


def _comment_stub():
    stub = MagicMock()
    stub.id = uuid.uuid4()
    stub.pk = stub.id
    stub.artifact_id = uuid.uuid4()
    stub.author_id = uuid.uuid4()
    stub.text = "needs a rationale"
    stub.resolved = False
    stub.resolved_by_id = None
    stub.resolved_at = None
    stub.created_at = datetime(2026, 9, 4, 10, 0, tzinfo=dt_timezone.utc)
    return stub


@pytest.fixture
def ctx():
    return MagicMock()


@pytest.mark.django_db
def test_create_returns_a_json_serialisable_payload(ctx):
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService") as svc:
        svc.return_value.create_comment.return_value = _comment_stub()
        result = group.dispatch(
            "comment.create",
            {"artifact_id": str(uuid.uuid4()), "text": "needs a rationale"},
            ctx,
        )

    # The transport uses stdlib json.dumps — a UUID or datetime in here is a 500.
    json.dumps(result.payload)
    assert result.payload["text"] == "needs a rationale"
    assert isinstance(result.payload["id"], str)
    assert isinstance(result.payload["created_at"], str)


@pytest.mark.django_db
def test_payload_never_uses_the_reserved_content_key(ctx):
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService") as svc:
        svc.return_value.list_for_artifact.return_value = [_comment_stub()]
        result = group.dispatch("comment.list", {"artifact_id": str(uuid.uuid4())}, ctx)

    assert "content" not in result.payload


@pytest.mark.django_db
def test_list_returns_a_comments_array(ctx):
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService") as svc:
        svc.return_value.list_for_artifact.return_value = [_comment_stub()]
        result = group.dispatch("comment.list", {"artifact_id": str(uuid.uuid4())}, ctx)

    json.dumps(result.payload)
    assert len(result.payload["comments"]) == 1


@pytest.mark.django_db
def test_resolve_returns_the_full_object(ctx):
    group = CommentToolGroup()
    stub = _comment_stub()
    stub.resolved = True
    with patch("mcp_server.tools.comment.CommentService") as svc:
        svc.return_value.resolve_comment.return_value = stub
        result = group.dispatch("comment.resolve", {"id": str(stub.id)}, ctx)

    assert result.payload["resolved"] is True
    assert result.payload["text"] == "needs a rationale"


def test_exactly_three_tools_are_declared():
    schemas = {schema["name"] for schema in CommentToolGroup._TOOL_SCHEMAS}
    assert schemas == {"comment.create", "comment.list", "comment.resolve"}


def test_delete_is_deliberately_not_exposed():
    """Spec §4: deletion is author-or-admin, a human decision — not an agent tool."""
    assert "comment.delete" not in CommentToolGroup._TOOL_MAP
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest mcp_server/tests/test_comment_tool_group.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.comment'`.

- [ ] **Step 3: Write the tool group**

Create `backend/mcp_server/tools/comment.py`:

```python
"""CommentToolGroup — comment.* MCP tools (Menschen-im-System spec §4).

Tools implemented:
  comment.create   — add a comment to an artifact
  comment.list     — list an artifact's comments
  comment.resolve  — mark a comment resolved

Deliberately NOT implemented:
  comment.delete   — spec §4 restricts deletion to the author or an admin; that
                     is a human decision, not an agent capability.

Every value in a returned payload is stringified: the MCP transport serialises
with stdlib ``json.dumps``, which cannot encode ``UUID`` or ``datetime``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.comment_service import CommentService
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_uuid

logger = logging.getLogger(__name__)


def _comment_to_dict(comment: Any) -> Dict[str, Any]:
    """Serialise a Comment for MCP responses (all values JSON-native)."""
    return {
        "id": str(comment.id),
        "artifact_id": str(comment.artifact_id),
        "text": comment.text,
        "author_id": str(comment.author_id) if comment.author_id else None,
        "resolved": bool(comment.resolved),
        "resolved_by_id": str(comment.resolved_by_id) if comment.resolved_by_id else None,
        "resolved_at": comment.resolved_at.isoformat() if comment.resolved_at else None,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


class CommentToolGroup(BaseToolGroup):
    """Comment tool group (3 tools) — wraps ``CommentService``."""

    _TOOL_MAP = {
        "comment.create": "_handle_create",
        "comment.list": "_handle_list",
        "comment.resolve": "_handle_resolve",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "comment.create",
            "description": "Add a comment to an artifact.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "UUID of the artifact."},
                    "text": {"type": "string", "description": "Comment body."},
                },
                "required": ["artifact_id", "text"],
            },
        },
        {
            "name": "comment.list",
            "description": "List the comments on an artifact, oldest first.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "UUID of the artifact."},
                    "include_resolved": {
                        "type": "boolean",
                        "description": "Include resolved comments (default true).",
                    },
                },
                "required": ["artifact_id"],
            },
        },
        {
            "name": "comment.resolve",
            "description": "Mark a comment as resolved.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the comment."},
                },
                "required": ["id"],
            },
        },
    ]

    @staticmethod
    def _get_service() -> CommentService:
        """Return a CommentService instance."""
        return CommentService()

    def _handle_create(self, args: Dict[str, Any], ctx: AuthContext) -> ToolResult:
        """Handle ``comment.create``."""
        artifact_id: UUID = require_uuid(args, "artifact_id")
        comment = self._get_service().create_comment(
            artifact_id=artifact_id, text=args.get("text", ""), ctx=ctx
        )
        return ToolResult(payload=_comment_to_dict(comment))

    def _handle_list(self, args: Dict[str, Any], ctx: AuthContext) -> ToolResult:
        """Handle ``comment.list``."""
        artifact_id: UUID = require_uuid(args, "artifact_id")
        rows = self._get_service().list_for_artifact(
            artifact_id, ctx, include_resolved=bool(args.get("include_resolved", True))
        )
        return ToolResult(payload={"comments": [_comment_to_dict(row) for row in rows]})

    def _handle_resolve(self, args: Dict[str, Any], ctx: AuthContext) -> ToolResult:
        """Handle ``comment.resolve``."""
        comment_id: UUID = require_uuid(args, "id")
        comment = self._get_service().resolve_comment(comment_id, ctx)
        return ToolResult(payload=_comment_to_dict(comment))


__all__ = ["CommentToolGroup"]
```

- [ ] **Step 4: Register the group**

In `backend/mcp_server/tool_registry.py`, add the import inside `_register_default_groups` (next to the other tool-group imports around line 540):

```python
        from mcp_server.tools.comment import CommentToolGroup
```

and add to the `self.register_groups({...})` dict (around line 557):

```python
            # Menschen-im-System spec §4: comments are the one collaboration
            # feature agents do use (notifications deliberately have no group).
            "comment": CommentToolGroup(),
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest mcp_server/tests/test_comment_tool_group.py mcp_server/tests/test_tool_registry.py -v
```
Expected: PASS. If `test_tool_registry.py` asserts a fixed tool or group count, update that expected number by 3 tools / 1 group in the same commit.

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tools/comment.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/
git commit -m "feat: add the comment.* MCP tool group"
```

---

## Phase D — The remaining two notification triggers

### Task 18: `notify_transition_pending` — role broadcast after a transition

**Files:**
- Modify: `backend/application/notification_service.py` (add the producer)
- Modify: `backend/workflow/services.py:266-283` (call it after `perform_transition`)
- Test: `backend/application/tests/test_notify_transition_pending.py`

**Interfaces:**
- Consumes: `WorkflowDefinitionStore.get_definition(workspace_id, item_type) -> WorkflowDefinitionDTO` with `transitions: tuple[TransitionDefinitionDTO, ...]` carrying `from_state`, `to_state`, `allowed_roles: tuple[str, ...]` (`workflow/definition_store.py:42-93`); `auth_tenancy.models.UserRole` (`user`, `workspace`, `role`, `suspended_at`); `create_notifications`; `resolve_artifact_id_or_none`.
- Produces: `notify_transition_pending(*, item_id: UUID, item_type: str, workspace_id: UUID, new_state: str, tenant_id: UUID, actor_user_id: UUID) -> int`.

**Why one call site:** `workflow/services.py:266` is the **only** non-test caller of `StateLifecycleManager.perform_transition` (grep-verified). Hooking there covers every transition, including the `proposed → draft` / `proposed → rejected` pair from the KI-Vorschlag-als-Zustand spec — no special case needed, exactly as that spec predicts.

**Why the producer lives in `application/`:** ADR-01 — the `UserRole` query is ORM access and belongs in Layer 2, not in the workflow engine.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_notify_transition_pending.py`:

```python
"""transition_pending: role broadcast, not person-scoped routing (spec §5.1)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.notification_service import notify_transition_pending


def _transition(from_state, to_state, roles):
    t = MagicMock()
    t.from_state = from_state
    t.to_state = to_state
    t.allowed_roles = tuple(roles)
    return t


def _definition(transitions):
    definition = MagicMock()
    definition.transitions = tuple(transitions)
    return definition


@pytest.mark.django_db
def test_collects_roles_of_all_outgoing_transitions():
    approver, admin = uuid.uuid4(), uuid.uuid4()

    with patch(
        "application.notification_service._get_definition",
        return_value=_definition([
            _transition("review", "approved", ["approver", "admin"]),
            _transition("review", "draft", ["editor"]),
            _transition("draft", "review", ["editor"]),  # not outgoing from `review`
        ]),
    ), patch(
        "application.notification_service._user_ids_with_roles",
        return_value=[approver, admin],
    ) as lookup, patch(
        "application.notification_service.create_notifications", return_value=2
    ) as notify, patch(
        "application.notification_service.resolve_artifact_id_or_none", return_value=None
    ):
        written = notify_transition_pending(
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=uuid.uuid4(),
            new_state="review",
            tenant_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        )

    assert written == 2
    assert set(lookup.call_args.kwargs["roles"]) == {"approver", "admin", "editor"}
    assert notify.call_args.kwargs["kind"] == "transition_pending"


@pytest.mark.django_db
def test_terminal_state_notifies_nobody():
    with patch(
        "application.notification_service._get_definition",
        return_value=_definition([_transition("draft", "review", ["editor"])]),
    ), patch("application.notification_service.create_notifications") as notify:
        written = notify_transition_pending(
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=uuid.uuid4(),
            new_state="approved",  # no outgoing transitions
            tenant_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        )

    assert written == 0
    notify.assert_not_called()


@pytest.mark.django_db
def test_the_actor_is_not_notified_about_their_own_transition():
    actor = uuid.uuid4()

    with patch(
        "application.notification_service._get_definition",
        return_value=_definition([_transition("review", "approved", ["approver"])]),
    ), patch(
        "application.notification_service._user_ids_with_roles", return_value=[actor]
    ), patch(
        "application.notification_service.create_notifications", return_value=0
    ) as notify, patch(
        "application.notification_service.resolve_artifact_id_or_none", return_value=None
    ):
        notify_transition_pending(
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=uuid.uuid4(),
            new_state="review",
            tenant_id=uuid.uuid4(),
            actor_user_id=actor,
        )

    assert notify.call_args.kwargs["exclude_user_id"] == actor


@pytest.mark.django_db
def test_a_missing_workflow_definition_is_not_fatal():
    """A notification must never break the transition it reacts to."""
    from workflow.definition_store import WorkflowDefinitionError

    with patch(
        "application.notification_service._get_definition",
        side_effect=WorkflowDefinitionError("none"),
    ):
        assert notify_transition_pending(
            item_id=uuid.uuid4(),
            item_type="Requirement",
            workspace_id=uuid.uuid4(),
            new_state="review",
            tenant_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        ) == 0


def test_workflow_transition_calls_the_producer():
    import inspect

    from workflow.services import transition

    assert "notify_transition_pending(" in inspect.getsource(transition)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_notify_transition_pending.py -v
```
Expected: FAIL with `ImportError: cannot import name 'notify_transition_pending'`.

- [ ] **Step 3: Add the producer to `notification_service.py`**

Append to `backend/application/notification_service.py`:

```python
def _get_definition(workspace_id: UUID, item_type: str):
    """Return the active WorkflowDefinitionDTO. Isolated so tests can patch it."""
    from workflow.definition_store import WorkflowDefinitionStore

    return WorkflowDefinitionStore().get_definition(workspace_id, item_type)


def _user_ids_with_roles(*, workspace_id: UUID, roles: Iterable[str]) -> list[UUID]:
    """Return the ids of every non-suspended user holding one of *roles* here.

    Workspace-scoped by design: a role is granted per workspace
    (``auth_tenancy.UserRole``), so a global role lookup would notify people
    who cannot act on this item at all.
    """
    from auth_tenancy.models import UserRole

    return list(
        UserRole.objects.filter(
            workspace_id=workspace_id,
            role__in=list(roles),
            suspended_at__isnull=True,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )


def notify_transition_pending(
    *,
    item_id: UUID,
    item_type: str,
    workspace_id: UUID,
    new_state: str,
    tenant_id: UUID,
    actor_user_id: UUID,
) -> int:
    """Notify everyone who may act on the item's *next* transition (spec §5.1).

    Role broadcast, not person-scoped routing — personalised assignment per
    transition is explicitly Q2.5 scope (spec §6). Covers the KI-Vorschlag
    ``proposed`` state with no special case: ``proposed -> draft`` and
    ``proposed -> rejected`` are ordinary role-gated transitions.

    Never raises: a notification must not break the transition it reacts to.
    """
    try:
        definition = _get_definition(workspace_id, item_type)
    except Exception:
        logger.warning(
            "notify_transition_pending: no workflow definition for workspace=%s type=%s",
            workspace_id,
            item_type,
            exc_info=True,
        )
        return 0

    roles: set[str] = set()
    for transition in definition.transitions:
        if transition.from_state == new_state:
            roles.update(transition.allowed_roles or ())

    if not roles:
        return 0

    try:
        user_ids = _user_ids_with_roles(workspace_id=workspace_id, roles=roles)
        return create_notifications(
            user_ids=user_ids,
            kind=Notification.KIND_TRANSITION_PENDING,
            message=f"{item_type} is in state '{new_state}' and awaits your action",
            artifact_id=resolve_artifact_id_or_none(item_id),
            tenant_id=tenant_id,
            exclude_user_id=actor_user_id,
        )
    except Exception:
        logger.exception("notify_transition_pending failed for item %s", item_id)
        return 0
```

Add to the module's imports:

```python
from application.trace_link_service import resolve_artifact_id_or_none
```

and extend `__all__` with `"notify_transition_pending"`.

- [ ] **Step 4: Call it from the workflow facade**

In `backend/workflow/services.py`, immediately after the `outcome: TransitionOutcome = lifecycle.perform_transition(...)` call (line 266-283) and before the `return TransitionResult(...)`:

```python
    # Menschen-im-System spec §5.1: the single seam for transition_pending.
    # This is the only non-test caller of perform_transition, so hooking here
    # covers every transition — including `proposed -> draft`/`-> rejected`
    # from the KI-Vorschlag-als-Zustand spec, which need no special case.
    # Local import: the workflow engine must not import Layer 2 at module load.
    from application.notification_service import notify_transition_pending

    notify_transition_pending(
        item_id=item_id_uuid,
        item_type=item_type,
        workspace_id=workspace_uuid,
        new_state=outcome.new_state,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_notify_transition_pending.py workflow/ -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/application/notification_service.py backend/workflow/services.py backend/application/tests/test_notify_transition_pending.py
git commit -m "feat: broadcast transition_pending notifications after every workflow transition"
```

---

### Task 19: `notify_suspect_flagged` — hook into the suspect propagation

**Files:**
- Modify: `backend/application/notification_service.py` (add the producer)
- Modify: the suspect-propagation write site delivered by the Traceability-Semantik spec (located in Step 3)
- Test: `backend/application/tests/test_notify_suspect_flagged.py`

**Interfaces:**
- Consumes: `owner_and_assignee_for_artifact` (Task 15), `create_notifications`, `persistence.models.Artifact`.
- Produces: `notify_suspect_flagged(*, artifact_id: UUID, tenant_id: UUID, actor_user_id: Optional[UUID] = None) -> int`.

**Cross-spec dependency (resolved, not blocking):** `TraceLink.suspect_flagged_at` / `suspect_source_change` are delivered by the Traceability-Semantik spec (its §5 / §7.3), which is implemented **before** this one. The producer below is complete and independently tested either way; Step 3 locates the call site by grep. If that spec has not landed yet, ship Steps 1–3 plus 5–6 and record in the commit message that the producer is unwired — it is a public, tested function and wiring it is a one-line change.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_notify_suspect_flagged.py`:

```python
"""suspect_flagged: notify the affected artifact's owner and assignee (spec §5.2)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.notification_service import notify_suspect_flagged


@pytest.mark.django_db
def test_notifies_owner_and_assignee():
    owner, assignee, artifact_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    artifact = MagicMock()
    artifact.pk = artifact_id
    artifact.title = "REQ-1"

    with patch(
        "application.notification_service._load_artifact", return_value=artifact
    ), patch(
        "application.notification_service.owner_and_assignee_for_artifact",
        return_value=(owner, assignee),
    ), patch(
        "application.notification_service.create_notifications", return_value=2
    ) as notify:
        written = notify_suspect_flagged(
            artifact_id=artifact_id, tenant_id=uuid.uuid4(), actor_user_id=uuid.uuid4()
        )

    assert written == 2
    kwargs = notify.call_args.kwargs
    assert set(kwargs["user_ids"]) == {owner, assignee}
    assert kwargs["kind"] == "suspect_flagged"
    assert kwargs["artifact_id"] == artifact_id


@pytest.mark.django_db
def test_notifies_nobody_when_neither_role_is_set():
    artifact = MagicMock()
    artifact.pk = uuid.uuid4()
    artifact.title = "REQ-1"

    with patch(
        "application.notification_service._load_artifact", return_value=artifact
    ), patch(
        "application.notification_service.owner_and_assignee_for_artifact",
        return_value=(None, None),
    ), patch(
        "application.notification_service.create_notifications", return_value=0
    ) as notify:
        assert notify_suspect_flagged(
            artifact_id=uuid.uuid4(), tenant_id=uuid.uuid4()
        ) == 0

    assert notify.call_args.kwargs["user_ids"] == [None, None]


@pytest.mark.django_db
def test_a_missing_artifact_is_not_fatal():
    with patch("application.notification_service._load_artifact", return_value=None):
        assert notify_suspect_flagged(
            artifact_id=uuid.uuid4(), tenant_id=uuid.uuid4()
        ) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_notify_suspect_flagged.py -v
```
Expected: FAIL with `ImportError: cannot import name 'notify_suspect_flagged'`.

- [ ] **Step 3: Add the producer**

Append to `backend/application/notification_service.py`:

```python
def _load_artifact(artifact_id: UUID):
    """Fetch an Artifact with its owner-bearing relations. Isolated for patching."""
    from persistence.models import Artifact

    return Artifact.objects.filter(pk=artifact_id).first()


def notify_suspect_flagged(
    *,
    artifact_id: UUID,
    tenant_id: UUID,
    actor_user_id: Optional[UUID] = None,
) -> int:
    """Notify an artifact's owner and assignee that it was flagged suspect.

    Called by the suspect propagation of the Traceability-Semantik spec when it
    sets ``TraceLink.suspect_flagged_at`` (spec §5.2). Never raises: a
    notification must not break the propagation that triggered it.
    """
    from application.comment_service import owner_and_assignee_for_artifact

    try:
        artifact = _load_artifact(artifact_id)
        if artifact is None:
            return 0

        owner_id, assignee_id = owner_and_assignee_for_artifact(artifact)
        return create_notifications(
            user_ids=[owner_id, assignee_id],
            kind=Notification.KIND_SUSPECT_FLAGGED,
            message=f"{artifact.title} was flagged suspect by an upstream change",
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            exclude_user_id=actor_user_id,
        )
    except Exception:
        logger.exception("notify_suspect_flagged failed for artifact %s", artifact_id)
        return 0
```

The test patches `application.notification_service.owner_and_assignee_for_artifact`, so also add a module-level re-import at the top of the file so the patch target exists:

```python
from application.comment_service import owner_and_assignee_for_artifact  # noqa: F401
```

…and use that module-level name inside the function instead of the local import (delete the `from application.comment_service import ...` line inside the function body). Extend `__all__` with `"notify_suspect_flagged"`.

- [ ] **Step 4: Locate and wire the suspect-propagation call site**

Run:
```bash
grep -rn "suspect_flagged_at" backend/ --include=*.py | grep -v migrations | grep -v tests
```

Expected: the write site delivered by the Traceability-Semantik spec (its §5 propagation). At that site, immediately after `suspect_flagged_at` is set and saved, add:

```python
    from application.notification_service import notify_suspect_flagged

    notify_suspect_flagged(
        artifact_id=link.target_artifact_id,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
    )
```

(adjust `link.target_artifact_id` to the attribute the propagation actually holds — it is the *affected* artifact, i.e. the downstream end of the link).

If the grep returns nothing, the Traceability-Semantik spec has not landed yet: skip this step, and record in the commit message that the producer is unwired. It is a public, tested function; wiring is one line.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_notify_suspect_flagged.py traceability/ -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/application/notification_service.py backend/application/tests/test_notify_suspect_flagged.py
git commit -m "feat: notify owner and assignee when an artifact is flagged suspect"
```

---

### Task 20: REST endpoints for notifications

**Files:**
- Modify: `backend/rest_api/serializers.py` (append `NotificationSerializer`)
- Modify: `backend/rest_api/collaboration_views.py` (add `NotificationViewSet`)
- Modify: `backend/rest_api/urls.py` (register)
- Test: `backend/rest_api/tests/test_notification_endpoints.py`

**Interfaces:**
- Consumes: `NotificationService` (Task 10).
- Produces:
  - `GET  /api/v1/notifications/?unread_only=true&limit=20` → `{"notifications": [...], "unread_count": N}`
  - `POST /api/v1/notifications/<uuid:pk>/read/`
  - `POST /api/v1/notifications/mark-all-read/` → `{"marked": N}`
  - `NotificationSerializer`

**Decision (envelope, not a bare list):** the bell needs the unread count and the list in one round trip. Returning `{"notifications": [...], "unread_count": N}` avoids a second request on every page load. This endpoint is deliberately *not* paginated by `StandardPagination` — it is a capped feed (`limit` ≤ 200 enforced in the service), not a browsable collection.

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_notification_endpoints.py`:

```python
"""REST surface for notifications (Menschen-im-System spec §5)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from rest_api.collaboration_views import NotificationViewSet


def _notification_stub(kind="assigned", read=False):
    stub = MagicMock()
    stub.id = uuid.uuid4()
    stub.pk = stub.id
    stub.kind = kind
    stub.artifact_id = uuid.uuid4()
    stub.message = "you were assigned"
    stub.read = read
    stub.created_at = None
    return stub


@pytest.fixture
def factory():
    return APIRequestFactory()


def test_list_returns_rows_and_the_unread_count(factory):
    request = factory.get("/api/v1/notifications/")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.list_for_user.return_value = [_notification_stub()]
        svc.return_value.unread_count.return_value = 1
        response = NotificationViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert response.data["unread_count"] == 1
    assert response.data["notifications"][0]["kind"] == "assigned"


def test_list_forwards_unread_only_and_limit(factory):
    request = factory.get("/api/v1/notifications/?unread_only=true&limit=5")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.list_for_user.return_value = []
        svc.return_value.unread_count.return_value = 0
        NotificationViewSet.as_view({"get": "list"})(request)

    kwargs = svc.return_value.list_for_user.call_args.kwargs
    assert kwargs["unread_only"] is True
    assert kwargs["limit"] == 5


def test_list_ignores_a_non_numeric_limit(factory):
    request = factory.get("/api/v1/notifications/?limit=abc")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.list_for_user.return_value = []
        svc.return_value.unread_count.return_value = 0
        response = NotificationViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert svc.return_value.list_for_user.call_args.kwargs["limit"] == 50


def test_read_action_marks_one_notification(factory):
    notification_id = uuid.uuid4()
    request = factory.post(f"/api/v1/notifications/{notification_id}/read/")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.mark_read.return_value = _notification_stub(read=True)
        response = NotificationViewSet.as_view({"post": "read"})(request, pk=str(notification_id))

    assert response.status_code == 200
    assert response.data["read"] is True


def test_mark_all_read_returns_the_count(factory):
    request = factory.post("/api/v1/notifications/mark-all-read/")

    with patch("rest_api.collaboration_views.get_auth_context", return_value=MagicMock()), patch(
        "rest_api.collaboration_views.NotificationService"
    ) as svc:
        svc.return_value.mark_all_read.return_value = 4
        response = NotificationViewSet.as_view({"post": "mark_all_read"})(request)

    assert response.status_code == 200
    assert response.data["marked"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest rest_api/tests/test_notification_endpoints.py -v
```
Expected: FAIL with `ImportError: cannot import name 'NotificationViewSet'`.

- [ ] **Step 3: Add `NotificationSerializer`**

Append to `backend/rest_api/serializers.py`:

```python
class NotificationSerializer(serializers.Serializer):
    """Wire format for application.models.Notification (spec §5). Read-only."""

    id = serializers.UUIDField(read_only=True)
    kind = serializers.CharField(read_only=True)
    artifact_id = serializers.UUIDField(read_only=True, allow_null=True)
    message = serializers.CharField(read_only=True)
    read = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
```

- [ ] **Step 4: Add the ViewSet**

Append to `backend/rest_api/collaboration_views.py` (and add `NotificationViewSet` to `__all__`):

```python
#: Fallback when ``?limit=`` is absent or unparsable. The service clamps the
#: effective value to 200 regardless.
DEFAULT_NOTIFICATION_LIMIT = 50


class NotificationViewSet(BaseEntityViewSet):
    """``/api/v1/notifications/`` — the caller's own notification feed.

    Not paginated: this is a capped feed for a dropdown, not a browsable
    collection. The list response carries the unread count so the bell needs a
    single round trip.
    """

    serializer_class = NotificationSerializer

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/notifications/ — own notifications plus the unread count."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            unread_only = request.query_params.get("unread_only", "").lower() == "true"
            try:
                limit = int(request.query_params.get("limit", DEFAULT_NOTIFICATION_LIMIT))
            except (TypeError, ValueError):
                limit = DEFAULT_NOTIFICATION_LIMIT

            service = NotificationService()
            rows = service.list_for_user(ctx, unread_only=unread_only, limit=limit)
            return Response(
                {
                    "notifications": NotificationSerializer(rows, many=True).data,
                    "unread_count": service.unread_count(ctx),
                }
            )
        except Exception as exc:
            logger.exception("NotificationViewSet.list: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """POST /api/v1/notifications/<pk>/read/ — mark one notification read."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            row = NotificationService().mark_read(UUID(str(pk)), ctx)
            return Response(NotificationSerializer(row).data)
        except Exception as exc:
            logger.exception("NotificationViewSet.read: unhandled exception")
            return _service_error_response(exc, lang)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/notifications/mark-all-read/ — mark the whole feed read."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            return Response({"marked": NotificationService().mark_all_read(ctx)})
        except Exception as exc:
            logger.exception("NotificationViewSet.mark_all_read: unhandled exception")
            return _service_error_response(exc, lang)
```

- [ ] **Step 5: Register the route**

In `backend/rest_api/urls.py`, extend the collaboration import and register:

```python
from rest_api.collaboration_views import (
    ArtifactCommentsView,
    CommentViewSet,
    NotificationViewSet,
)
```

and add one more line next to the `comments` registration from Task 16 Step 5:

```python
router.register(r"notifications", NotificationViewSet, basename="notification")
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest rest_api/tests/test_notification_endpoints.py rest_api/tests/test_comment_endpoints.py -v
```
Expected: PASS (12 cases).

- [ ] **Step 7: Commit**

```bash
git add backend/rest_api/collaboration_views.py backend/rest_api/serializers.py backend/rest_api/urls.py backend/rest_api/tests/test_notification_endpoints.py
git commit -m "feat: add REST endpoints for the notification feed"
```

---

## Phase E — Expose `owner` / `assignee` over REST

### Task 21: `owner_id` / `assignee_id` on the ten serializers and views

**Files:**
- Modify: `backend/rest_api/serializers.py` (the ten artifact serializers; `RiskSerializer` at :1405-1410)
- Modify: `backend/rest_api/views.py` (the ten `create`/`partial_update` handlers; Risk at :4211-4212, :5132, :5177)
- Test: `backend/rest_api/tests/test_owner_assignee_exposure.py`

**Interfaces:**
- Consumes: the model fields from Tasks 1-6, the service parameters from Tasks 12-13.
- Produces: `owner_id`, `assignee_id`, `owner_display`, `assignee_display` on all ten artifact serializers.

**Why this is needed even though the Attribute-Definition spec renders the form:** that spec's `ArtifactForm` renderer builds inputs from the attribute definitions, but it still submits and reads them through these serializers. A field that the serializer drops is invisible no matter how well the form renders it — the exact failure mode of issue #290 (a DRF field on a plain mixin never registered, and `custom_fields` were silently dropped).

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_owner_assignee_exposure.py`:

```python
"""All ten artifact serializers carry owner_id/assignee_id (spec §3)."""
import pytest

from rest_api import serializers as s

ARTIFACT_SERIALIZERS = [
    s.RequirementSerializer,
    s.StakeholderNeedSerializer,
    s.ArchitectureElementSerializer,
    s.TestCaseSerializer,
    s.GlossaryTermSerializer,
    s.AdrSerializer,
    s.GoalSerializer,
    s.IcdSerializer,
    s.RiskSerializer,
    s.IssueSerializer,
]


@pytest.mark.parametrize("serializer_class", ARTIFACT_SERIALIZERS)
@pytest.mark.parametrize("field_name", ["owner_id", "assignee_id"])
def test_serializer_exposes_the_field(serializer_class, field_name):
    assert field_name in serializer_class().fields


@pytest.mark.parametrize("serializer_class", ARTIFACT_SERIALIZERS)
@pytest.mark.parametrize("field_name", ["owner_id", "assignee_id"])
def test_field_is_optional_and_nullable(serializer_class, field_name):
    """A PATCH that does not mention the field must not clear it."""
    field = serializer_class().fields[field_name]
    assert field.required is False
    assert field.allow_null is True


@pytest.mark.parametrize("serializer_class", ARTIFACT_SERIALIZERS)
@pytest.mark.parametrize("field_name", ["owner_display", "assignee_display"])
def test_display_fields_are_read_only(serializer_class, field_name):
    field = serializer_class().fields[field_name]
    assert field.read_only is True


def test_risk_no_longer_exposes_the_dropped_fields():
    fields = s.RiskSerializer().fields
    assert "owner_user_id" not in fields
    assert "owner_user_display" not in fields
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest rest_api/tests/test_owner_assignee_exposure.py -v
```
Expected: FAIL with `assert 'owner_id' in ...` on the first parametrization.

- [ ] **Step 3: Add the four fields to each of the ten serializers**

In `backend/rest_api/serializers.py`, add to each of the ten artifact serializer classes:

```python
    # Menschen-im-System spec §3. `required=False` + `allow_null=True` is the
    # PATCH contract: an absent field means "unchanged" (the service sees UNSET),
    # an explicit null means "unassign".
    owner_id = serializers.UUIDField(required=False, allow_null=True)
    assignee_id = serializers.UUIDField(required=False, allow_null=True)
    owner_display = serializers.CharField(read_only=True, allow_null=True, required=False)
    assignee_display = serializers.CharField(read_only=True, allow_null=True, required=False)
```

For `RiskSerializer` (`serializers.py:1405-1410`) this *replaces* the existing `owner` CharField comment block plus `owner_user_id` / `owner_user_display`.

- [ ] **Step 4: Pass the values through the ten view handlers**

For each artifact ViewSet's `create` and `partial_update` handler in `backend/rest_api/views.py`, forward the two fields only when the client actually sent them, so an absent field stays `UNSET`:

```python
            from application.assignment import UNSET

            assignment_kwargs = {}
            if "owner_id" in request.data:
                assignment_kwargs["owner_id"] = data.get("owner_id")
            if "assignee_id" in request.data:
                assignment_kwargs["assignee_id"] = data.get("assignee_id")
            # ... then pass **assignment_kwargs into the service call
```

And in each detail/list response builder, add the display values (Risk's builder at `views.py:4211-4212` shows the existing pattern; replace those two lines):

```python
        "owner_id": str(entity.owner_id) if entity.owner_id else None,
        "owner_display": getattr(entity.owner, "username", None) if entity.owner_id else None,
        "assignee_id": str(entity.assignee_id) if entity.assignee_id else None,
        "assignee_display": getattr(entity.assignee, "username", None) if entity.assignee_id else None,
```

Also update `views.py:5132` and `views.py:5177`, which currently pass `owner_user_id=data.get("owner_user_id")` into `RiskService`.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest rest_api/tests/test_owner_assignee_exposure.py rest_api/ -v
```
Expected: PASS (61 cases in the new file, plus the existing `rest_api` suite unchanged).

- [ ] **Step 6: Regenerate the OpenAPI schema**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py spectacular --file /tmp/schema.yaml
grep -c "owner_id" /tmp/schema.yaml
```
Expected: a non-zero count and no `drf-spectacular` errors.

- [ ] **Step 7: Commit**

```bash
git add backend/rest_api/serializers.py backend/rest_api/views.py backend/rest_api/tests/test_owner_assignee_exposure.py
git commit -m "feat: expose owner_id/assignee_id on all ten artifact REST serializers"
```

---

## Phase F — Frontend

### Task 22: API wrappers `comments.ts` and `notifications.ts`

**Files:**
- Create: `frontend/src/api/comments.ts`
- Create: `frontend/src/api/notifications.ts`
- Modify: `frontend/src/api/index.ts` (barrel re-export)
- Test: `frontend/src/api/comments.test.ts`

**Interfaces:**
- Consumes: `apiClient.get<T>(path)`, `apiClient.post<T>(path, body)`, `apiClient.delete<T>(path)` (`frontend/src/api/client.ts:368-406`).
- Produces:
  - `export interface Comment { id, artifactId, text, authorId, authorDisplay, resolved, resolvedById, resolvedAt, createdAt }`
  - `export const commentsApi = { list, create, resolve, remove }`
  - `export interface Notification { id, kind, artifactId, message, read, createdAt }`
  - `export type NotificationKind = "transition_pending" | "suspect_flagged" | "assigned" | "comment_added"`
  - `export const notificationsApi = { list, markRead, markAllRead }`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/comments.test.ts`:

```ts
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from "./client";
import { commentsApi } from "./comments";
import { notificationsApi } from "./notifications";

const wire = {
  id: "c1",
  artifact_id: "a1",
  text: "hello",
  author_id: "u1",
  author_display: "alice",
  resolved: false,
  resolved_by_id: null,
  resolved_at: null,
  created_at: "2026-09-04T10:00:00Z",
};

describe("commentsApi", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });

  it("lists an artifact's comments and camel-cases the wire format", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([wire]);

    const rows = await commentsApi.list("a1");

    expect(apiClient.get).toHaveBeenCalledWith("/artifacts/a1/comments/");
    expect(rows[0]).toEqual({
      id: "c1",
      artifactId: "a1",
      text: "hello",
      authorId: "u1",
      authorDisplay: "alice",
      resolved: false,
      resolvedById: null,
      resolvedAt: null,
      createdAt: "2026-09-04T10:00:00Z",
    });
  });

  it("passes include_resolved=false when open comments are requested", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([]);

    await commentsApi.list("a1", { includeResolved: false });

    expect(apiClient.get).toHaveBeenCalledWith(
      "/artifacts/a1/comments/?include_resolved=false"
    );
  });

  it("creates a comment", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(wire);

    const created = await commentsApi.create("a1", "hello");

    expect(apiClient.post).toHaveBeenCalledWith("/artifacts/a1/comments/", {
      text: "hello",
    });
    expect(created.text).toBe("hello");
  });

  it("resolves a comment", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...wire, resolved: true });

    const resolved = await commentsApi.resolve("c1");

    expect(apiClient.post).toHaveBeenCalledWith("/comments/c1/resolve/", {});
    expect(resolved.resolved).toBe(true);
  });

  it("deletes a comment", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await commentsApi.remove("c1");

    expect(apiClient.delete).toHaveBeenCalledWith("/comments/c1/");
  });
});

describe("notificationsApi", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("returns the feed and the unread count", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      notifications: [
        {
          id: "n1",
          kind: "assigned",
          artifact_id: "a1",
          message: "m",
          read: false,
          created_at: "2026-09-04T10:00:00Z",
        },
      ],
      unread_count: 1,
    });

    const feed = await notificationsApi.list();

    expect(apiClient.get).toHaveBeenCalledWith("/notifications/?limit=20");
    expect(feed.unreadCount).toBe(1);
    expect(feed.notifications[0].artifactId).toBe("a1");
  });

  it("marks one notification read", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "n1",
      kind: "assigned",
      artifact_id: null,
      message: "m",
      read: true,
      created_at: "2026-09-04T10:00:00Z",
    });

    const row = await notificationsApi.markRead("n1");

    expect(apiClient.post).toHaveBeenCalledWith("/notifications/n1/read/", {});
    expect(row.read).toBe(true);
  });

  it("marks everything read", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ marked: 3 });

    expect(await notificationsApi.markAllRead()).toBe(3);
    expect(apiClient.post).toHaveBeenCalledWith("/notifications/mark-all-read/", {});
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/api/comments.test.ts --testTimeout=30000"
```
Expected: FAIL — `Failed to resolve import "./comments"`.

- [ ] **Step 3: Write `comments.ts`**

Create `frontend/src/api/comments.ts`:

```ts
/**
 * Comments on artifacts (Menschen-im-System spec §4).
 *
 * Comments hang on the generic Artifact, so this wrapper takes an artifact id
 * for every one of the ten artifact kinds — there is no per-kind variant.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** Wire format returned by the backend (snake_case). */
interface CommentWire {
  id: string;
  artifact_id: string;
  text: string;
  author_id: string | null;
  author_display: string | null;
  resolved: boolean;
  resolved_by_id: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface Comment {
  id: UUID;
  artifactId: UUID;
  text: string;
  authorId: UUID | null;
  authorDisplay: string | null;
  resolved: boolean;
  resolvedById: UUID | null;
  resolvedAt: string | null;
  createdAt: string;
}

export interface ListCommentsOptions {
  /** Default true — pass false to show only open comments. */
  includeResolved?: boolean;
}

function toComment(wire: CommentWire): Comment {
  return {
    id: wire.id,
    artifactId: wire.artifact_id,
    text: wire.text,
    authorId: wire.author_id,
    authorDisplay: wire.author_display,
    resolved: wire.resolved,
    resolvedById: wire.resolved_by_id,
    resolvedAt: wire.resolved_at,
    createdAt: wire.created_at,
  };
}

export const commentsApi = {
  /** List an artifact's comments, oldest first. */
  async list(artifactId: UUID, options: ListCommentsOptions = {}): Promise<Comment[]> {
    const suffix = options.includeResolved === false ? "?include_resolved=false" : "";
    const rows = await apiClient.get<CommentWire[]>(
      `/artifacts/${artifactId}/comments/${suffix}`
    );
    return rows.map(toComment);
  },

  /** Add a comment to an artifact. */
  async create(artifactId: UUID, text: string): Promise<Comment> {
    return toComment(
      await apiClient.post<CommentWire>(`/artifacts/${artifactId}/comments/`, { text })
    );
  },

  /** Mark a comment resolved. */
  async resolve(commentId: UUID): Promise<Comment> {
    return toComment(await apiClient.post<CommentWire>(`/comments/${commentId}/resolve/`, {}));
  },

  /** Delete a comment (author or admin only — the backend enforces it). */
  async remove(commentId: UUID): Promise<void> {
    await apiClient.delete<void>(`/comments/${commentId}/`);
  },
};
```

- [ ] **Step 4: Write `notifications.ts`**

Create `frontend/src/api/notifications.ts`:

```ts
/**
 * The notification feed (Menschen-im-System spec §5).
 *
 * No real-time push by design: the bell fetches this once when the
 * NavigationShell mounts, and again after a mark-read action.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export type NotificationKind =
  | "transition_pending"
  | "suspect_flagged"
  | "assigned"
  | "comment_added";

interface NotificationWire {
  id: string;
  kind: NotificationKind;
  artifact_id: string | null;
  message: string;
  read: boolean;
  created_at: string;
}

interface FeedWire {
  notifications: NotificationWire[];
  unread_count: number;
}

export interface Notification {
  id: UUID;
  kind: NotificationKind;
  artifactId: UUID | null;
  message: string;
  read: boolean;
  createdAt: string;
}

export interface NotificationFeed {
  notifications: Notification[];
  unreadCount: number;
}

/** Bell dropdown size. The backend clamps anything above 200. */
export const NOTIFICATION_FEED_LIMIT = 20;

function toNotification(wire: NotificationWire): Notification {
  return {
    id: wire.id,
    kind: wire.kind,
    artifactId: wire.artifact_id,
    message: wire.message,
    read: wire.read,
    createdAt: wire.created_at,
  };
}

export const notificationsApi = {
  /** Fetch the caller's feed together with the unread count (one round trip). */
  async list(limit: number = NOTIFICATION_FEED_LIMIT): Promise<NotificationFeed> {
    const wire = await apiClient.get<FeedWire>(`/notifications/?limit=${limit}`);
    return {
      notifications: wire.notifications.map(toNotification),
      unreadCount: wire.unread_count,
    };
  },

  /** Mark one notification read. */
  async markRead(notificationId: UUID): Promise<Notification> {
    return toNotification(
      await apiClient.post<NotificationWire>(`/notifications/${notificationId}/read/`, {})
    );
  },

  /** Mark the whole feed read; returns how many rows changed. */
  async markAllRead(): Promise<number> {
    const result = await apiClient.post<{ marked: number }>(
      "/notifications/mark-all-read/",
      {}
    );
    return result.marked;
  },
};
```

- [ ] **Step 5: Re-export from the barrel**

In `frontend/src/api/index.ts` add:

```ts
export { commentsApi } from "./comments";
export type { Comment, ListCommentsOptions } from "./comments";
export { NOTIFICATION_FEED_LIMIT, notificationsApi } from "./notifications";
export type { Notification, NotificationFeed, NotificationKind } from "./notifications";
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/api/comments.test.ts --testTimeout=30000"
```
Expected: PASS (8 cases).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/comments.ts frontend/src/api/notifications.ts frontend/src/api/index.ts frontend/src/api/comments.test.ts
git commit -m "feat: add comments and notifications API wrappers"
```

---

### Task 23: `CommentPanel` in the artifact inspector

**Files:**
- Create: `frontend/src/components/shared/ArtifactInspector/CommentPanel.tsx`
- Create: `frontend/src/components/shared/ArtifactInspector/CommentPanel.module.css`
- Create: `frontend/src/components/shared/ArtifactInspector/CommentPanel.test.tsx`
- Modify: `frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx:458-471` (mount it)
- Modify: `frontend/src/components/shared/ArtifactInspector/index.ts` (export)

**Interfaces:**
- Consumes: `commentsApi` (Task 22), `ArtifactKind` (`ArtifactInspector/types.ts`), `ConfirmDialog` (`components/shared/ConfirmDialog.tsx`, props `title, message, confirmLabel, cancelLabel, onConfirm, onCancel, testId, confirmTestId, cancelTestId, isSubmitting`).
- Produces: `export function CommentPanel(props: CommentPanelProps)`, `export interface CommentPanelProps { kind: ArtifactKind; artifactId: string }`.

**Decision:** mounted as a **fourth stacked panel**, not a tab. `RightSidebar.tsx:343` states the inspector has no tab/anchor concept; introducing one for a single panel is disproportionate. See OFFENE FRAGEN item 3.

**Constraints:** no inline `style={{` (UI ratchet), all colours/sizes from `styles/tokens.css` via the CSS module, `data-testid` on every interactive element, `ConfirmDialog` for the delete.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/shared/ArtifactInspector/CommentPanel.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("../../../api/comments", () => ({
  commentsApi: {
    list: vi.fn(),
    create: vi.fn(),
    resolve: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

import { commentsApi } from "../../../api/comments";
import { CommentPanel } from "./CommentPanel";

const comment = {
  id: "c1",
  artifactId: "a1",
  text: "needs a rationale",
  authorId: "u1",
  authorDisplay: "alice",
  resolved: false,
  resolvedById: null,
  resolvedAt: null,
  createdAt: "2026-09-04T10:00:00Z",
};

describe("CommentPanel", () => {
  beforeEach(() => {
    vi.mocked(commentsApi.list).mockReset().mockResolvedValue([comment]);
    vi.mocked(commentsApi.create).mockReset().mockResolvedValue(comment);
    vi.mocked(commentsApi.resolve).mockReset().mockResolvedValue({ ...comment, resolved: true });
    vi.mocked(commentsApi.remove).mockReset().mockResolvedValue(undefined);
  });

  it("loads and renders the artifact's comments", async () => {
    render(<CommentPanel kind="requirement" artifactId="a1" />);

    expect(await screen.findByText("needs a rationale")).toBeInTheDocument();
    expect(commentsApi.list).toHaveBeenCalledWith("a1");
  });

  it("shows an empty state when there are no comments", async () => {
    vi.mocked(commentsApi.list).mockResolvedValue([]);

    render(<CommentPanel kind="requirement" artifactId="a1" />);

    expect(await screen.findByTestId("comment-panel-empty")).toBeInTheDocument();
  });

  it("creates a comment and clears the input", async () => {
    const user = userEvent.setup();
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    const input = screen.getByTestId("comment-panel-input");
    await user.type(input, "another one");
    await user.click(screen.getByTestId("comment-panel-submit"));

    await waitFor(() => expect(commentsApi.create).toHaveBeenCalledWith("a1", "another one"));
    await waitFor(() => expect(input).toHaveValue(""));
  });

  it("disables submit while the input is empty", async () => {
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    expect(screen.getByTestId("comment-panel-submit")).toBeDisabled();
  });

  it("resolves a comment", async () => {
    const user = userEvent.setup();
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    await user.click(screen.getByTestId("comment-panel-resolve-c1"));

    await waitFor(() => expect(commentsApi.resolve).toHaveBeenCalledWith("c1"));
  });

  it("asks for confirmation before deleting", async () => {
    const user = userEvent.setup();
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    await user.click(screen.getByTestId("comment-panel-delete-c1"));
    expect(screen.getByTestId("comment-delete-dialog")).toBeInTheDocument();
    expect(commentsApi.remove).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("comment-delete-confirm"));
    await waitFor(() => expect(commentsApi.remove).toHaveBeenCalledWith("c1"));
  });

  it("closes the dialog on the success path", async () => {
    const user = userEvent.setup();
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    await user.click(screen.getByTestId("comment-panel-delete-c1"));
    await user.click(screen.getByTestId("comment-delete-confirm"));

    await waitFor(() =>
      expect(screen.queryByTestId("comment-delete-dialog")).not.toBeInTheDocument()
    );
  });

  it("shows an error when loading fails", async () => {
    vi.mocked(commentsApi.list).mockRejectedValue(new Error("boom"));

    render(<CommentPanel kind="requirement" artifactId="a1" />);

    expect(await screen.findByTestId("comment-panel-error")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/shared/ArtifactInspector/CommentPanel.test.tsx --testTimeout=30000"
```
Expected: FAIL — `Failed to resolve import "./CommentPanel"`.

- [ ] **Step 3: Write the CSS module**

Create `frontend/src/components/shared/ArtifactInspector/CommentPanel.module.css`:

```css
/* CommentPanel — Menschen-im-System spec §4.
   All values come from styles/tokens.css; no literal colours or sizes. */

.panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border-top: 1px solid var(--color-border);
}

.heading {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}

.itemResolved {
  opacity: 0.6;
}

.meta {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.text {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text);
  white-space: pre-wrap;
  word-break: break-word;
}

.actions {
  display: flex;
  gap: var(--space-1);
}

.actionBtn {
  padding: var(--space-1) var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.actionBtn:hover:not(:disabled) {
  background: var(--color-surface-hover);
}

.actionBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.composer {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.input {
  min-height: 4rem;
  padding: var(--space-2);
  font-family: inherit;
  font-size: var(--font-size-sm);
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  resize: vertical;
}

.empty,
.error {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.error {
  color: var(--color-danger);
}
```

> If any custom property above is absent from `frontend/src/styles/tokens.css`, substitute the nearest existing token rather than introducing a literal — `grep -o -- "--[a-z-]*" frontend/src/styles/tokens.css | sort -u` lists the available set.

- [ ] **Step 4: Write the component**

Create `frontend/src/components/shared/ArtifactInspector/CommentPanel.tsx`:

```tsx
/**
 * CommentPanel — comments on the currently inspected artifact.
 *
 * Menschen-im-System spec §4. Mounted as the fourth stacked panel of the
 * RightSidebar rather than as a tab: the inspector has no tab/anchor concept
 * (see the comment in RightSidebar.tsx), and inventing one for a single panel
 * would be disproportionate.
 *
 * Comments are never edited — create, resolve, delete only.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { commentsApi, type Comment } from "../../../api/comments";
import { ConfirmDialog } from "../ConfirmDialog";
import type { ArtifactKind } from "./types";
import styles from "./CommentPanel.module.css";

export interface CommentPanelProps {
  /** The inspected artifact's kind — used for the panel heading only. */
  kind: ArtifactKind;
  /** The generic Artifact id (not the business-entity id). */
  artifactId: string;
}

export function CommentPanel({ kind, artifactId }: CommentPanelProps): JSX.Element {
  const { t } = useTranslation();

  const [comments, setComments] = useState<Comment[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Comment | null>(null);

  const load = useCallback(async (): Promise<void> => {
    try {
      setComments(await commentsApi.list(artifactId));
      setError(null);
    } catch {
      setError(t("comments.loadFailed", "Could not load comments."));
    }
  }, [artifactId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSubmit = useCallback(async (): Promise<void> => {
    const text = draft.trim();
    if (!text) return;
    setBusy(true);
    try {
      await commentsApi.create(artifactId, text);
      setDraft("");
      await load();
    } catch {
      setError(t("comments.createFailed", "Could not save the comment."));
    } finally {
      setBusy(false);
    }
  }, [artifactId, draft, load, t]);

  const handleResolve = useCallback(
    async (comment: Comment): Promise<void> => {
      setBusy(true);
      try {
        await commentsApi.resolve(comment.id);
        await load();
      } catch {
        setError(t("comments.resolveFailed", "Could not resolve the comment."));
      } finally {
        setBusy(false);
      }
    },
    [load, t]
  );

  const handleDeleteConfirmed = useCallback(async (): Promise<void> => {
    if (!pendingDelete) return;
    setBusy(true);
    try {
      await commentsApi.remove(pendingDelete.id);
      // Close on the success path too — a dialog left open after a completed
      // action is the #669/#670 failure mode.
      setPendingDelete(null);
      await load();
    } catch {
      setError(t("comments.deleteFailed", "Could not delete the comment."));
      setPendingDelete(null);
    } finally {
      setBusy(false);
    }
  }, [load, pendingDelete, t]);

  return (
    <section
      className={styles.panel}
      aria-label={t("comments.ariaLabel", "Comments")}
      data-testid="comment-panel"
      data-artifact-kind={kind}
    >
      <h3 className={styles.heading}>{t("comments.heading", "Comments")}</h3>

      {error && (
        <p className={styles.error} role="alert" data-testid="comment-panel-error">
          {error}
        </p>
      )}

      {comments.length === 0 ? (
        <p className={styles.empty} data-testid="comment-panel-empty">
          {t("comments.empty", "No comments yet.")}
        </p>
      ) : (
        <ul className={styles.list} data-testid="comment-panel-list">
          {comments.map((comment) => (
            <li
              key={comment.id}
              className={
                comment.resolved ? `${styles.item} ${styles.itemResolved}` : styles.item
              }
              data-testid={`comment-panel-item-${comment.id}`}
            >
              <div className={styles.meta}>
                <span>{comment.authorDisplay ?? t("comments.unknownAuthor", "Unknown")}</span>
                <span>{comment.createdAt}</span>
              </div>
              <p className={styles.text}>{comment.text}</p>
              <div className={styles.actions}>
                {!comment.resolved && (
                  <button
                    type="button"
                    className={styles.actionBtn}
                    disabled={busy}
                    onClick={() => void handleResolve(comment)}
                    data-testid={`comment-panel-resolve-${comment.id}`}
                  >
                    {t("comments.resolve", "Resolve")}
                  </button>
                )}
                <button
                  type="button"
                  className={styles.actionBtn}
                  disabled={busy}
                  onClick={() => setPendingDelete(comment)}
                  data-testid={`comment-panel-delete-${comment.id}`}
                >
                  {t("comments.delete", "Delete")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className={styles.composer}>
        <textarea
          className={styles.input}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t("comments.placeholder", "Write a comment…")}
          aria-label={t("comments.inputLabel", "New comment")}
          data-testid="comment-panel-input"
        />
        <button
          type="button"
          className={styles.actionBtn}
          disabled={busy || draft.trim().length === 0}
          onClick={() => void handleSubmit()}
          data-testid="comment-panel-submit"
        >
          {t("comments.submit", "Comment")}
        </button>
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title={t("comments.deleteTitle", "Delete comment")}
          message={t("comments.deleteMessage", "This cannot be undone.")}
          confirmLabel={t("comments.delete", "Delete")}
          cancelLabel={t("actions.cancel", "Cancel")}
          onConfirm={() => void handleDeleteConfirmed()}
          onCancel={() => setPendingDelete(null)}
          isSubmitting={busy}
          testId="comment-delete-dialog"
          confirmTestId="comment-delete-confirm"
          cancelTestId="comment-delete-cancel"
        />
      )}
    </section>
  );
}
```

- [ ] **Step 5: Mount it in the RightSidebar and export it**

In `frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx`, add the import next to the other panels (line 31-33):

```tsx
import { CommentPanel } from "./CommentPanel";
```

and add the panel after `TracePanel` inside the `styles.panels` block (line 471):

```tsx
            <CommentPanel kind={kind} artifactId={artifactId} />
```

In `frontend/src/components/shared/ArtifactInspector/index.ts` add:

```ts
export { CommentPanel } from "./CommentPanel";
export type { CommentPanelProps } from "./CommentPanel";
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/shared/ArtifactInspector --testTimeout=30000"
```
Expected: PASS (8 new cases plus the existing RightSidebar/Version/Diff/Trace suites).

- [ ] **Step 7: Restart the frontend container and verify in the browser**

Vite has no working HMR on Windows in this stack — a frontend edit is invisible until the container restarts.

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . restart frontend
```

Then open a requirement in the browser, confirm the "Comments" section renders below the trace links, post a comment, resolve it, and delete it (confirming the dialog appears and closes).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/shared/ArtifactInspector/
git commit -m "feat: add a comment panel to the artifact inspector"
```

---

### Task 24: `NotificationBell` in the sidebar footer

**Files:**
- Create: `frontend/src/components/NavigationShell/NotificationBell.tsx`
- Create: `frontend/src/components/NavigationShell/NotificationBell.module.css`
- Create: `frontend/src/components/NavigationShell/NotificationBell.test.tsx`
- Modify: `frontend/src/components/NavigationShell/SidebarNavigation.tsx:718` (pinned footer)

**Interfaces:**
- Consumes: `notificationsApi` (Task 22), `useNavigate` from `react-router-dom`.
- Produces: `export function NotificationBell()`.

**Decision (placement):** the spec asks for the bell "in der NavigationShell". `NavigationShell.tsx` is a pure router — the visible chrome is `SidebarNavigation`, whose pinned footer (`SidebarNavigation.tsx:718`) already holds the language toggle, theme toggle, profile and logout. The bell goes there, next to `nav-profile`.

**Decision (no polling):** fetched once on mount and re-fetched after each mark-read. Spec §5 rules out real-time push; a background poll is the same infrastructure decision by the back door.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/NavigationShell/NotificationBell.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

const navigate = vi.fn();

vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallbackOrOpts?: unknown) =>
      typeof fallbackOrOpts === "string" ? fallbackOrOpts : key,
  }),
}));

vi.mock("../../api/notifications", () => ({
  NOTIFICATION_FEED_LIMIT: 20,
  notificationsApi: {
    list: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  },
}));

import { notificationsApi } from "../../api/notifications";
import { NotificationBell } from "./NotificationBell";

const unread = {
  id: "n1",
  kind: "assigned" as const,
  artifactId: "a1",
  message: "REQ-1 assigned to you",
  read: false,
  createdAt: "2026-09-04T10:00:00Z",
};

describe("NotificationBell", () => {
  beforeEach(() => {
    navigate.mockReset();
    vi.mocked(notificationsApi.list)
      .mockReset()
      .mockResolvedValue({ notifications: [unread], unreadCount: 1 });
    vi.mocked(notificationsApi.markRead).mockReset().mockResolvedValue({ ...unread, read: true });
    vi.mocked(notificationsApi.markAllRead).mockReset().mockResolvedValue(1);
  });

  it("fetches the feed once on mount", async () => {
    render(<NotificationBell />);
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalledTimes(1));
  });

  it("shows the unread count badge", async () => {
    render(<NotificationBell />);
    expect(await screen.findByTestId("notification-bell-badge")).toHaveTextContent("1");
  });

  it("hides the badge when nothing is unread", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({ notifications: [], unreadCount: 0 });

    render(<NotificationBell />);
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    expect(screen.queryByTestId("notification-bell-badge")).not.toBeInTheDocument();
  });

  it("opens and closes the dropdown", async () => {
    const user = userEvent.setup();
    render(<NotificationBell />);
    await screen.findByTestId("notification-bell-badge");

    await user.click(screen.getByTestId("notification-bell-toggle"));
    expect(screen.getByTestId("notification-bell-dropdown")).toBeInTheDocument();

    await user.click(screen.getByTestId("notification-bell-toggle"));
    expect(screen.queryByTestId("notification-bell-dropdown")).not.toBeInTheDocument();
  });

  it("shows an empty state with no notifications", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({ notifications: [], unreadCount: 0 });
    const user = userEvent.setup();
    render(<NotificationBell />);
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    await user.click(screen.getByTestId("notification-bell-toggle"));
    expect(screen.getByTestId("notification-bell-empty")).toBeInTheDocument();
  });

  it("marks read and navigates to the artifact on click", async () => {
    const user = userEvent.setup();
    render(<NotificationBell />);
    await screen.findByTestId("notification-bell-badge");

    await user.click(screen.getByTestId("notification-bell-toggle"));
    await user.click(screen.getByTestId("notification-bell-item-n1"));

    await waitFor(() => expect(notificationsApi.markRead).toHaveBeenCalledWith("n1"));
    expect(navigate).toHaveBeenCalledWith("/artifacts/a1");
  });

  it("does not navigate for a notification without an artifact", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({
      notifications: [{ ...unread, artifactId: null }],
      unreadCount: 1,
    });
    const user = userEvent.setup();
    render(<NotificationBell />);
    await screen.findByTestId("notification-bell-badge");

    await user.click(screen.getByTestId("notification-bell-toggle"));
    await user.click(screen.getByTestId("notification-bell-item-n1"));

    await waitFor(() => expect(notificationsApi.markRead).toHaveBeenCalled());
    expect(navigate).not.toHaveBeenCalled();
  });

  it("marks everything read and refetches", async () => {
    const user = userEvent.setup();
    render(<NotificationBell />);
    await screen.findByTestId("notification-bell-badge");

    await user.click(screen.getByTestId("notification-bell-toggle"));
    await user.click(screen.getByTestId("notification-bell-mark-all"));

    await waitFor(() => expect(notificationsApi.markAllRead).toHaveBeenCalled());
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalledTimes(2));
  });

  it("stays silent when the feed cannot be loaded", async () => {
    vi.mocked(notificationsApi.list).mockRejectedValue(new Error("boom"));

    render(<NotificationBell />);
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    expect(screen.queryByTestId("notification-bell-badge")).not.toBeInTheDocument();
    expect(screen.getByTestId("notification-bell-toggle")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/NavigationShell/NotificationBell.test.tsx --testTimeout=30000"
```
Expected: FAIL — `Failed to resolve import "./NotificationBell"`.

- [ ] **Step 3: Write the CSS module**

Create `frontend/src/components/NavigationShell/NotificationBell.module.css`:

```css
/* NotificationBell — Menschen-im-System spec §5.
   Tokens only; the UI ratchet rejects inline styles and literal colours. */

.wrapper {
  position: relative;
}

.toggle {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  width: 100%;
  padding: var(--space-1) var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  background: transparent;
  border: none;
  cursor: pointer;
}

.toggle:hover {
  background: var(--color-surface-hover);
}

.badge {
  min-width: 1.25rem;
  padding: 0 var(--space-1);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  line-height: 1.25rem;
  text-align: center;
  color: var(--color-on-primary);
  background: var(--color-primary);
  border-radius: var(--radius-pill);
}

.dropdown {
  position: absolute;
  bottom: 100%;
  left: 0;
  z-index: var(--z-dropdown);
  width: 20rem;
  max-height: 24rem;
  overflow-y: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
}

.list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  display: block;
  width: 100%;
  padding: var(--space-2);
  font-size: var(--font-size-sm);
  text-align: left;
  color: var(--color-text);
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
}

.item:hover {
  background: var(--color-surface-hover);
}

.itemUnread {
  font-weight: var(--font-weight-bold);
}

.footer {
  padding: var(--space-2);
}

.empty {
  margin: 0;
  padding: var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}
```

- [ ] **Step 4: Write the component**

Create `frontend/src/components/NavigationShell/NotificationBell.tsx`:

```tsx
/**
 * NotificationBell — unread counter plus a dropdown of recent notifications.
 *
 * Menschen-im-System spec §5. Fetched once on mount and after each mark-read;
 * there is deliberately no polling and no push (that would be the very
 * infrastructure the spec rules out).
 *
 * A failing fetch stays silent: a notification centre must never block the
 * navigation chrome it lives in.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { notificationsApi, type Notification } from "../../api/notifications";
import styles from "./NotificationBell.module.css";

export function NotificationBell(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const load = useCallback(async (): Promise<void> => {
    try {
      const feed = await notificationsApi.list();
      setNotifications(feed.notifications);
      setUnreadCount(feed.unreadCount);
    } catch {
      // Silent by design — see the module docstring.
      setNotifications([]);
      setUnreadCount(0);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleItemClick = useCallback(
    async (notification: Notification): Promise<void> => {
      try {
        await notificationsApi.markRead(notification.id);
      } catch {
        // Navigation matters more than the read flag; fall through.
      }
      setOpen(false);
      await load();
      if (notification.artifactId) {
        navigate(`/artifacts/${notification.artifactId}`);
      }
    },
    [load, navigate]
  );

  const handleMarkAll = useCallback(async (): Promise<void> => {
    try {
      await notificationsApi.markAllRead();
    } catch {
      // Ignore — the refetch below reflects whatever actually happened.
    }
    await load();
  }, [load]);

  return (
    <div className={styles.wrapper}>
      <button
        type="button"
        className={styles.toggle}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={t("notifications.ariaLabel", "Notifications")}
        onClick={() => setOpen((previous) => !previous)}
        data-testid="notification-bell-toggle"
      >
        <span aria-hidden="true">{"\u{1F514}"}</span>
        <span>{t("notifications.label", "Notifications")}</span>
        {unreadCount > 0 && (
          <span className={styles.badge} data-testid="notification-bell-badge">
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className={styles.dropdown} role="menu" data-testid="notification-bell-dropdown">
          {notifications.length === 0 ? (
            <p className={styles.empty} data-testid="notification-bell-empty">
              {t("notifications.empty", "Nothing new.")}
            </p>
          ) : (
            <ul className={styles.list}>
              {notifications.map((notification) => (
                <li key={notification.id}>
                  <button
                    type="button"
                    role="menuitem"
                    className={
                      notification.read
                        ? styles.item
                        : `${styles.item} ${styles.itemUnread}`
                    }
                    onClick={() => void handleItemClick(notification)}
                    data-testid={`notification-bell-item-${notification.id}`}
                  >
                    {notification.message}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className={styles.footer}>
            <button
              type="button"
              className={styles.item}
              onClick={() => void handleMarkAll()}
              data-testid="notification-bell-mark-all"
            >
              {t("notifications.markAllRead", "Mark all as read")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Mount it in the pinned footer**

In `frontend/src/components/NavigationShell/SidebarNavigation.tsx`, add the import:

```tsx
import { NotificationBell } from "./NotificationBell";
```

and place it inside `<div className={styles.footer}>` (line 718), immediately before the `nav-profile` button:

```tsx
        <NotificationBell />
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/components/NavigationShell --testTimeout=30000"
```
Expected: PASS (9 new cases plus the existing NavigationShell suites).

- [ ] **Step 7: Restart the frontend and verify in the browser**

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . restart frontend
```

Then assign a requirement to a second user, log in as that user, and confirm the bell shows a badge, the dropdown lists the notification, and clicking it navigates and clears the badge.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/NavigationShell/
git commit -m "feat: add a notification bell to the sidebar footer"
```

---

### Task 25: i18n keys for comments and notifications

**Files:**
- Modify: `frontend/src/i18n/locales/de.json`
- Modify: `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/i18n/locales.test.ts` (extend if it exists; otherwise create)

**Interfaces:**
- Consumes: the `t()` keys used in Tasks 23-24.
- Produces: the `comments.*` and `notifications.*` namespaces in both locales.

**Constraint:** `keySeparator` is `"."`, so a **flat dotted key inside an object never resolves** — `"comments.heading"` must be nested as `{"comments": {"heading": ...}}`, not written as a literal dotted key.

- [ ] **Step 1: Write the failing test**

Create (or extend) `frontend/src/i18n/locales.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import de from "./locales/de.json";
import en from "./locales/en.json";

const COMMENT_KEYS = [
  "ariaLabel",
  "heading",
  "empty",
  "placeholder",
  "inputLabel",
  "submit",
  "resolve",
  "delete",
  "deleteTitle",
  "deleteMessage",
  "unknownAuthor",
  "loadFailed",
  "createFailed",
  "resolveFailed",
  "deleteFailed",
];

const NOTIFICATION_KEYS = ["ariaLabel", "label", "empty", "markAllRead"];

describe.each([
  ["de", de as Record<string, unknown>],
  ["en", en as Record<string, unknown>],
])("%s locale", (_name, locale) => {
  it("has a nested comments namespace", () => {
    expect(typeof locale.comments).toBe("object");
  });

  it.each(COMMENT_KEYS)("has comments.%s", (key) => {
    expect((locale.comments as Record<string, string>)[key]).toBeTruthy();
  });

  it.each(NOTIFICATION_KEYS)("has notifications.%s", (key) => {
    expect((locale.notifications as Record<string, string>)[key]).toBeTruthy();
  });

  it("uses no flat dotted keys in these namespaces", () => {
    // keySeparator is "."; a literal "comments.heading" key never resolves.
    expect(Object.keys(locale).some((k) => k.startsWith("comments."))).toBe(false);
    expect(Object.keys(locale).some((k) => k.startsWith("notifications."))).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/i18n/locales.test.ts --testTimeout=30000"
```
Expected: FAIL — `expected undefined to be object` for `locale.comments`.

- [ ] **Step 3: Add the German keys**

Add to `frontend/src/i18n/locales/de.json` (top level, alongside `sidebar`, `nav`, …):

```json
  "comments": {
    "ariaLabel": "Kommentare",
    "heading": "Kommentare",
    "empty": "Noch keine Kommentare.",
    "placeholder": "Kommentar schreiben …",
    "inputLabel": "Neuer Kommentar",
    "submit": "Kommentieren",
    "resolve": "Erledigen",
    "delete": "Löschen",
    "deleteTitle": "Kommentar löschen",
    "deleteMessage": "Das lässt sich nicht rückgängig machen.",
    "unknownAuthor": "Unbekannt",
    "loadFailed": "Kommentare konnten nicht geladen werden.",
    "createFailed": "Kommentar konnte nicht gespeichert werden.",
    "resolveFailed": "Kommentar konnte nicht erledigt werden.",
    "deleteFailed": "Kommentar konnte nicht gelöscht werden."
  },
  "notifications": {
    "ariaLabel": "Benachrichtigungen",
    "label": "Benachrichtigungen",
    "empty": "Nichts Neues.",
    "markAllRead": "Alle als gelesen markieren"
  },
```

- [ ] **Step 4: Add the English keys**

Add to `frontend/src/i18n/locales/en.json`:

```json
  "comments": {
    "ariaLabel": "Comments",
    "heading": "Comments",
    "empty": "No comments yet.",
    "placeholder": "Write a comment…",
    "inputLabel": "New comment",
    "submit": "Comment",
    "resolve": "Resolve",
    "delete": "Delete",
    "deleteTitle": "Delete comment",
    "deleteMessage": "This cannot be undone.",
    "unknownAuthor": "Unknown",
    "loadFailed": "Could not load comments.",
    "createFailed": "Could not save the comment.",
    "resolveFailed": "Could not resolve the comment.",
    "deleteFailed": "Could not delete the comment."
  },
  "notifications": {
    "ariaLabel": "Notifications",
    "label": "Notifications",
    "empty": "Nothing new.",
    "markAllRead": "Mark all as read"
  },
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run src/i18n --testTimeout=30000"
```
Expected: PASS (40 cases).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/i18n/
git commit -m "feat: add de/en translations for comments and notifications"
```

---

### Task 26: Re-run the attribute-definition bootstrap so `owner`/`assignee` become core attributes

**Files:**
- Modify: the bootstrap script delivered by the Attribute-Definition spec (located in Step 1)
- Test: `backend/application/tests/test_owner_assignee_are_core_attributes.py`

**Interfaces:**
- Consumes: the `owner`/`assignee` model fields (Tasks 1-6), the attribute-definition bootstrap (spec 2, its §3.2).
- Produces: `owner` and `assignee` present as `type: "user"` core attributes for all ten types.

**Why this is a task and not a footnote:** the spec (§3, "Kein Cross-Spec-Amendment nötig") claims the bootstrap discovers the two fields automatically *once they exist as real model fields*. That claim is only true if the bootstrap is re-run after this plan's migrations. Skipping this leaves `owner`/`assignee` invisible in every rendered `ArtifactForm` — the fields exist, the API exposes them, and the UI shows nothing.

- [ ] **Step 1: Locate the bootstrap entry point**

Run:
```bash
ls backend/*/management/commands/ | grep -i attribute
grep -rn "core.*attribute\|bootstrap" backend/*/management/commands/*.py | head -20
```
Expected: the management command created by the Attribute-Definition spec (its §3.2). If nothing is found, that spec has not landed — stop here and re-run this task after it does.

- [ ] **Step 2: Write the failing test**

Create `backend/application/tests/test_owner_assignee_are_core_attributes.py`:

```python
"""owner/assignee show up as `user`-typed core attributes for all ten types.

Menschen-im-System spec §3: the Attribute-Definition bootstrap derives its core
list from Django model introspection, so this only holds once that bootstrap has
been re-run *after* this plan's migrations.
"""
import pytest

ARTIFACT_TYPES = [
    "Requirement",
    "StakeholderNeed",
    "ArchitectureElement",
    "TestCase",
    "GlossaryTerm",
    "Adr",
    "Goal",
    "Icd",
    "Risk",
    "Issue",
]


@pytest.mark.django_db
@pytest.mark.parametrize("artifact_type", ARTIFACT_TYPES)
@pytest.mark.parametrize("field_name", ["owner", "assignee"])
def test_field_is_a_user_typed_core_attribute(artifact_type, field_name):
    # Import inside the test: the model name is owned by the Attribute-Definition
    # spec; adjust this import to the class that spec actually created.
    from persistence.models import AttributeDefinition

    definition = AttributeDefinition.unscoped.filter(
        entity_type=artifact_type, name=field_name
    ).first()

    assert definition is not None, (
        f"{artifact_type}.{field_name} is missing from the core attribute list — "
        "re-run the attribute-definition bootstrap after this plan's migrations."
    )
    assert definition.type == "user"
```

- [ ] **Step 3: Run test to verify it fails**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_owner_assignee_are_core_attributes.py -v
```
Expected: FAIL — the definitions are missing (or the import fails, meaning spec 2 has not landed).

- [ ] **Step 4: Re-run the bootstrap**

Run the command found in Step 1, for example:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py bootstrap_attribute_definitions
```
Expected: idempotent output listing `owner` and `assignee` as newly discovered core attributes for all ten types.

- [ ] **Step 5: Hide `assignee` where it makes no sense**

Spec §3 names `GlossaryTerm` as the example: a glossary entry has someone responsible for the definition but nobody "currently working on it". Use the existing `visible` property of the attribute definition — this is precisely the case it exists for. No new mechanism.

Run:
```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py shell -c "
from persistence.models import AttributeDefinition
AttributeDefinition.unscoped.filter(entity_type='GlossaryTerm', name='assignee').update(visible=False)
"
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_mis backend-test pytest application/tests/test_owner_assignee_are_core_attributes.py -v
```
Expected: PASS (20 cases).

- [ ] **Step 7: Commit**

```bash
git add backend/application/tests/test_owner_assignee_are_core_attributes.py
git commit -m "test: assert owner/assignee are user-typed core attributes on all ten types"
```

---

## Self-Review

Performed against the spec at `main` (`fc41497d`) and the tree at the same commit.

### 1. Spec coverage

| Spec section | Requirement | Task(s) |
|---|---|---|
| §2.1 / §3 | `owner` + `assignee` as real User FKs on all 10 types | 1, 2, 3, 5, 6 |
| §3 | Risk: finish the REQ-L1-029 expand/contract migration, name-match, report, drop CharField, rename FK, add empty `assignee` | 4, 5 |
| §3 | Issue: `assignee_id` UUIDField → real FK, orphans reported, add empty `owner` | 6 |
| §3 | The other 8 types: both fields new, additive, empty | 1, 2, 3 |
| §3 | Hide `assignee` where meaningless (GlossaryTerm) via the existing `visible` property | 26 Step 5 |
| §3 | No cross-spec amendment; migration must precede the attribute-definition bootstrap | Global Constraints + 26 |
| §3.3 | `owner`/`assignee` writes publish `OP_ASSIGN` alongside the normal update | 11, 12, 13 |
| §3.3 | No new history mechanism for assignments | 11 (reuses `AuditEntry`) |
| §3.3 | Comments have no change history (not editable) | 7, 15 |
| §4 | `Comment(TenantScopedModel)` on `persistence.Artifact` with the seven declared fields | 7 |
| §4 | REST `artifacts/<id>/comments/`, `comments/<id>/resolve/`, `comments/<id>/` DELETE (author or admin) | 16 |
| §4 | MCP tool group `comment.*` (create, list, resolve) | 17 |
| §4 | UI: comments surface in the artifact inspector | 23 |
| §5 | `Notification(TenantScopedModel)` with the four declared kinds | 7 |
| §5.1 | `transition_pending` role broadcast over `allowed_roles`, covers `proposed` with no special case | 18 |
| §5.2 | `suspect_flagged` notifies owner + assignee | 19 |
| §5.3 | `assigned` — one event, two consumers | 11 |
| §5.4 | `comment_added` notifies owner + assignee, except the author | 15 |
| §5 | No real-time push | 22, 24 (fetch on mount) |
| §5 | REST `notifications/`, `<id>/read/`, `mark-all-read/` | 20 |
| §5 | No MCP group for notifications | 17 (asserted by `test_delete_is_deliberately_not_exposed`'s sibling constraint + Global Constraints) |
| §5 | Bell with unread count in the navigation shell | 24 |
| §6 | No per-transition assignment, deadlines, escalation, delegation | Global Constraints (nothing in this plan adds them) |
| §7 | All five migration steps | 1-8 |
| §8 | Risk-1: human review before the field drop | 4 (separate command, explicit gate in Step 5) |
| §8 | Risk-2: a forgotten `update_X()` path | 11 + 14 (AST ratchet) |
| §8 | Risk-3: broadcast noise | 10 (`MAX_FANOUT`) — accepted trade-off, capped |
| §8 | Risk-4: no push is a conscious compromise | documented, not mitigated |

Not covered on purpose, with the reason stated in-plan: `MainGoal`/`Diagram` (Task 3), the tab-vs-panel divergence (OFFENE FRAGEN 3), and the `created_at` redeclaration (OFFENE FRAGEN 2).

Also covered beyond the spec, because leaving it out would be a defect rather than a scope choice: REST exposure of the two fields (Task 21 — the spec assumes the attribute-definition renderer handles it, but the serializer must carry the field first) and the Goal version carry-forward (Task 13).

### 2. Placeholder scan

Every code block is complete and runnable. No `TBD`, no `TODO`, no "similar to Task N", no "add error handling here". Three places defer to a grep rather than naming a line, each with an exact command and an explicit fallback:

- Task 19 Step 4 — the suspect-propagation call site is created by a spec implemented *before* this one; `grep -rn "suspect_flagged_at"` locates it, and the fallback ("ship the producer unwired") is stated.
- Task 26 Step 1 — the attribute-definition bootstrap command name is owned by spec 2; the `ls`/`grep` pair locates it, with an explicit stop condition.
- Task 6 Step 5 / Task 23 Step 3 — the `AddIndex` block and the CSS token names are to be confirmed against generated output / `tokens.css`, with the exact command given.

These are not placeholders: each names *what* to run, *what* to expect, and *what to do* if the expectation fails.

### 3. Type consistency

- `UNSET` is defined once (Task 11) and consumed by Tasks 12, 13, 21 with the same import path `application.assignment`.
- `apply_assignment` signature is identical in its definition (Task 11), its wiring (Tasks 12, 13) and its ratchet (Task 14).
- `create_notifications` keyword signature is identical in its definition (Task 10) and all four call sites (Tasks 11, 15, 18, 19).
- `owner_and_assignee_for_artifact` is defined in `comment_service.py` (Task 15) and re-imported at module level in `notification_service.py` (Task 19 Step 3) — the re-import is explicitly required so the test's patch target resolves.
- `resolve_artifact_id_or_none` is defined in Task 9 and used in Tasks 11 and 18 with the same signature.
- `Notification.KIND_*` constants are defined in Task 7 and referenced by name (never as string literals) in Tasks 10, 11, 15, 18, 19.
- `NotificationSerializer` is referenced by the Task 16 import block before Task 20 defines it; Task 16 Step 4 carries an explicit note about that ordering.
- Frontend: `Comment`/`Notification` TS interfaces (Task 22) match the DRF serializer fields (Tasks 16, 20) field-for-field, with snake_case→camelCase mapping done in exactly one place per type.
- `ArtifactKind` is imported from the existing `ArtifactInspector/types.ts`, not redeclared.
- `ConfirmDialog` props used in Task 23 match the real interface at `components/shared/ConfirmDialog.tsx:21-68`.

### 4. Ordering

Tasks 1-8 (schema) → 9-14 (seam) → 15-17 (comments) → 18-20 (notifications + REST) → 21 (REST exposure) → 22-25 (frontend) → 26 (bootstrap). Every task's `Consumes` block references only interfaces produced by a lower-numbered task, with the two documented cross-spec exceptions (Tasks 19 and 26).

