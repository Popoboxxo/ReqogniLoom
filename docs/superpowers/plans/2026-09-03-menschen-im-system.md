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
    migrations/0023_issue_assignee_contract.py      CREATE  rename legacy col, add FK
    migrations/0024_issue_assignee_backfill.py      CREATE  data migration
    migrations/0025_comment_notification.py         CREATE
    migrations/0026_comment_notification_rls.py     CREATE
    tests/test_assignment.py                     CREATE
    tests/test_assignment_ratchet.py             CREATE
    tests/test_comment_service.py                CREATE
    tests/test_notification_service.py           CREATE
  persistence/
    models.py                                    MODIFY  +owner/assignee on 5 types
    migrations/0070_owner_assignee_core_types.py CREATE
  icd/
    models.py                                    MODIFY  +owner/assignee on Icd
    icd_manager.py                               MODIFY  update_icd: owner_id/assignee_id
    migrations/0009_icd_owner_assignee.py        CREATE
  workflow/
    services.py                                  MODIFY  transition(): notify_transition_pending hook
  traceability/ or application/                  MODIFY  suspect propagation: notify_suspect_flagged hook (Task 20)
  rest_api/
    collaboration_views.py                       CREATE  CommentViewSet, NotificationViewSet
    serializers.py                               MODIFY  +CommentSerializer, +NotificationSerializer, owner/assignee on 10 serializers
    urls.py                                      MODIFY  register comments/notifications + nested artifact comments
    tests/test_comment_endpoints.py              CREATE
    tests/test_notification_endpoints.py         CREATE
  mcp_server/
    tools/comment.py                             CREATE  CommentToolGroup
    tool_registry.py                             MODIFY  register "comment"
    tests/test_comment_tool_group.py             CREATE
frontend/src/
  api/comments.ts                                CREATE
  api/notifications.ts                           CREATE
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
```

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
