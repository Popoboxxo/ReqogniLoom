# Menschen im System — Collaboration Half (Re-Scope)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** RE-SCOPE (2026-09-15). This document supersedes the **collaboration half** of
[2026-09-03-menschen-im-system.md](2026-09-03-menschen-im-system.md). The owner/assignment half of
that plan is **cancelled** — it was overtaken by the merged Attribut-System v3
(epic #934, WS2 #936, WS7 #940) and by the AWMS migration plans. User decision (Option A,
2026-09-15): only Comments + Notifications are re-scoped and will be implemented later.

**Goal:** Give every artifact type a human comment thread and a pending-work notification feed,
so requirement work becomes communicable inside the tool.

**Verification basis:** every `file:line` in §2 and §5 was read at the current working tree on
branch `feat/menschen-im-system` (2026-09-15), not recalled from the original plan.

---

## 1. Scope

### In scope

- `Comment` entity on the generic `persistence.Artifact` + `CommentService`.
- `Notification` entity + `NotificationService` + exactly four producers.
- REST surface for comments and the notification feed.
- MCP tool group `comment.*` (3 tools) — notifications deliberately get **no** MCP group.
- Frontend: `CommentPanel` in the artifact inspector, `NotificationBell` in the sidebar footer,
  API wrappers, de/en i18n.

### Out of scope — superseded

- `owner` / `assignee` as per-type User FKs. **Superseded** by Attribut v3 (#936/#940):
  attribution now lives centrally on `Artifact.owner` / `Artifact.reporter` as **`Actor`** FKs
  (`backend/persistence/models.py:1096-1111`). There is no `assignee` field anywhere today.
- Any `application/assignment.py` / `apply_assignment()` seam. **It was never built**
  (`grep -r "apply_assignment" backend/` → no files) and **must not be built** — §5 names the
  seam that actually exists.
- Risk / Issue expand-contract migrations. Owned by AWMS
  (`backend/attribute_definitions/migration_plans/{risk_owner_to_actor,issue_assignee_to_actor}.yaml`);
  the physical column drop is a later, AWMS-owned contract step.

---

## 2. Verified Ist-Zustand (2026-09-15)

| Fact | Evidence |
|---|---|
| `Actor` entity: `kind ∈ {user, external}`, `user` FK SET_NULL | `backend/persistence/models.py:784-834` |
| `Artifact.owner` / `.reporter` are `Actor` FKs, SET_NULL, `related_name="+"` | `backend/persistence/models.py:1096-1111` |
| `Artifact.priority` is a plain `CharField` (no model choices) | `backend/persistence/models.py:1112-1122` |
| `Risk.owner` → `Risk.owner_name` (same DB column), `Risk.owner_user` still present | `persistence/models.py:2930`, `:2937`; `persistence/migrations/0092_rename_risk_owner_to_owner_name.py` |
| `Issue.assignee_id` is still a loose `UUIDField` | `persistence/models.py:3186` |
| Layer-2 models are re-exported from `application.models` | `backend/application/models.py:24-39` |
| `owner` / `reporter` / `priority` are already core attributes | `backend/application/artifact_attribute_gateway.py:144-146` (`_ARTIFACT_LEVEL_CORE_FIELDS`) |
| AWMS bootstrap command exists | `backend/attribute_definitions/management/commands/bootstrap_attribute_definitions.py` |
| `AuditEntry.OP_ASSIGN = "assign"`, present in `OP_CHOICES` | `backend/audit/models.py:122`, `:211` |
| `ServiceBase._audit(ctx, operation, entity_type, entity_id, change_reason=None, details=None)` | `backend/application/base.py:160-218` |
| `TraceLinkService.resolve_entity_to_artifact_id()` — **public** wrapper (fix #264) | `backend/application/trace_link_service.py:249-271` |
| Suspect propagation + `suspect_flagged_at` stamp | `backend/application/trace_link_service.py:1293` (`propagate_suspect_status`), stamp at `:1442-1445` |
| Workflow transition facade | `backend/workflow/services.py:210` (`transition`), `:283` (`perform_transition`), `:293` (`return TransitionResult`) |
| `TransitionDefinitionDTO.allowed_roles` / `WorkflowDefinitionStore.get_definition` | `backend/workflow/definition_store.py:57`, `:63`, `:1109` |
| **No** `Comment` / `Notification` model, **no** `as_comment` / `as_notification` table | `grep -r "^class \(Comment\|Notification\)" backend/` → none |
| **No** `notification_service.py`, `comment_service.py`, `rest_api/collaboration_views.py` | glob → none |
| RLS precedent unchanged, SQL shape identical to the plan's Task 8 code | `backend/application/migrations/0009_risk_issue_rls_policies.py:43-66` |
| Next free migration prefixes | `persistence/0093`, `application/0025`, `icd/0014` (icd not needed here) |
| `build_error_response` lives in `rest_api.serializers`, **not** `rest_api.errors` | `backend/rest_api/serializers.py` (imported that way by ~12 view modules); `rest_api/errors.py` does not exist |
| `_service_error_response` / `detect_lang` / `_SYSTEM_FIELD_NAMES` | `rest_api/views.py:183`, `rest_api/serializers.py:154`, `rest_api/views.py:4152` |
| MCP tool-manifest drift test exists → adding a group requires manifest regeneration | `backend/mcp_server/tests/test_tool_manifest_drift.py` |
| Inspector has no tab concept; 3 stacked panels | `frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx:344-345`, panels block `:458-473` |
| `ArtifactKind` has **12** members (incl. `diagram`, `mainGoal`) | `frontend/src/components/shared/ArtifactInspector/types.ts:21-33` |
| Sidebar pinned footer unchanged | `frontend/src/components/NavigationShell/SidebarNavigation.tsx:718`, `nav-profile` at `:754` |
| No `frontend/src/i18n/locales.test.ts` → Task 25 creates it | glob → none |
| `keySeparator` unset → i18next default `"."` applies | `frontend/src/i18n/index.ts` (no `keySeparator` / `nsSeparator`) |
| `UUID` type alias | `frontend/src/types/index.ts:15` |

---

## 3. Adopted tasks (Plan #6 → here)

Task IDs are kept from the original plan so traceability is one lookup. Dropped numbers are
listed in §4.

### Task 7 — `Comment` and `Notification` models

**Original goal:** two new tables (`as_comment`, `as_notification`) appended to
`backend/application/models.py`, one migration, no new Django app.

**Adaptation to today:**

- Migration filename `backend/application/migrations/0025_comment_notification.py` — still the next
  free prefix (`0024_release_layer2_models.py` is the current last).
- `application/models.py` is today a **~243-line** module; §24-39 re-export the seven Layer-0 models.
  Appending two classes remains correct — do not move them into `persistence/models.py`.
- `from django.conf import settings` must be added to the module imports (it currently imports only
  `uuid` and `django.db.models`).
- **`Comment.author` / `Notification.user` stay `settings.AUTH_USER_MODEL` (`persistence.User`).**
  Deliberate: a comment requires a login, and the notification recipient must be login-capable.
  `Actor.kind="external"` rows are placeholders with no user — they can own an artifact but can
  never receive a notification (see §5).
- No `assignee` column exists, so nothing in this task has to model one.
- `Comment` must not redeclare `created_at` — inherited from `AuditableModel`
  (`persistence/models.py:341-392`); `TenantScopedModel` at `:408`.
- Keep the exact two model definitions from the original Task 7 Step 3; they need no change.

**Verification:** `application/tests/test_collaboration_models.py` (8 cases), as written in
Plan #6 Task 7 Step 1 — still valid verbatim.

**Depends on:** —

---

### Task 8 — RLS policies for `as_comment` and `as_notification`

**Original goal:** enable + FORCE RLS and add a `<table>_tenant_isolation` policy for both tables.

**Adaptation to today:**

- Migration filename `backend/application/migrations/0026_comment_notification_rls.py`.
- The SQL body from Plan #6 Task 8 Step 3 is **still byte-compatible** with the current precedent:
  compare `backend/application/migrations/0009_risk_issue_rls_policies.py:43-66`. Keep `_TENANT_TABLES`,
  `_enable_sql()`, `_disable_sql()` unchanged.
- Add the `("persistence", "0003_rls_policies")` dependency alongside
  `("application", "0025_comment_notification")`, exactly as `application/0009` does
  (`:71-74`) — the ordering guarantee is what makes the policy land after the base RLS extension.

**Verification:** `application/tests/test_collaboration_rls.py` (4 cases) from Plan #6 Task 8 Step 1,
plus `docker compose ... exec backend python manage.py migrate` returning cleanly.

**Depends on:** Task 7.

---

### Task 9 — `resolve_artifact_id_or_none()` helper

**Original goal:** a best-effort business-entity id → `Artifact` id helper, so notification producers
never fail the mutation they react to.

**Adaptation to today:**

- **Reuse the public wrapper, not the private method.** Since fix #264 the class exposes
  `TraceLinkService.resolve_entity_to_artifact_id(entity_id, ctx=None)` at
  `backend/application/trace_link_service.py:249-271`. The original plan wrapped the private
  `_resolve_artifact_id` (`:112`); reaching into a private method from Layer 2 is exactly what #264
  fixed. The new module-level function must call `resolve_entity_to_artifact_id`.
- Keep the name `resolve_artifact_id_or_none` and the `except NotFoundError: return None` contract
  (do **not** let `NotFoundError` escape — a missing Artifact must never break the mutation).
- The probe chain has grown since the plan was written: `Risk` (`:240`), `Issue` (`:243`) and
  `MainGoal` are now covered. No action needed — just don't duplicate the chain.
- Keep the tests from Plan #6 Task 9 Step 1 but retarget the patch to
  `TraceLinkService.resolve_entity_to_artifact_id`.

**Verification:** `application/tests/test_resolve_artifact_id_or_none.py` — returns `None` on
`NotFoundError`, returns the resolved id otherwise.

**Depends on:** —

---

### Task 10 — `NotificationService` + shared `create_notifications` producer

**Original goal:** one producer function (`create_notifications`) plus a read-side service
(list / unread_count / mark_read / mark_all_read) in `backend/application/notification_service.py`,
re-exported from `application/services.py`.

**Adaptation to today:**

- The module does not exist — create it as written in Plan #6 Task 10 Step 3.
- `ServiceBase._set_tenant_context` (`application/base.py:150`) and `_audit`
  (`:160-218`) signatures are unchanged, so the model-code in the original plan still compiles.
- Keep `MAX_FANOUT = 200` and the `Notification.unscoped.bulk_create` path.
- **Add one producer** the original plan carried in its superseded Task 11: `notify_assigned`. Its
  binding point is defined in §5 — it does **not** live in an `assignment.py`.
- Keep the `KIND_CHOICES` four-tuple; `assigned` remains one of the four.

**Verification:** `application/tests/test_notification_service.py` (8 cases) from Plan #6 Task 10
Step 1, plus `application/tests/test_notify_assigned.py` for the new producer (§5).

**Depends on:** Task 7.

---

### Task 15 — `CommentService`

**Original goal:** comment CRUD over the generic Artifact plus the `comment_added` trigger.

**Adaptation to today — the type-aware probe is gone:**

- The original plan's `owner_and_assignee_for_artifact()` walked a 10-entry
  `OWNER_BEARING_RELATIONS` tuple because `owner`/`assignee` lived on the *specialised* rows.
  **That is no longer true.** `owner`/`reporter` are columns on `Artifact` itself
  (`persistence/models.py:1096-1111`). Replace the probe with:

  ```python
  def notify_user_ids_for_artifact(artifact) -> list[UUID]:
      """User ids to notify for an artifact: owner + reporter, internal actors only."""
      ids = []
      for actor in (artifact.owner, artifact.reporter):
          if actor is not None and actor.kind == "user" and actor.user_id is not None:
              ids.append(actor.user_id)
      return ids
  ```

  `Actor.kind == "external"` is dropped — an external placeholder has no login and therefore no
  notification feed. This is the one behaviour change the re-scope introduces, and it removes the
  last type-aware code in the feature.
- `CommentService.list_for_artifact` / `create_comment` / `resolve_comment` / `delete_comment` and
  the `ValidationError` on blank text / `PermissionDeniedError` for non-author-non-admin delete are
  unchanged.
- `create_comment` passes `notify_user_ids_for_artifact(artifact)` into `create_notifications` with
  `kind=KIND_COMMENT_ADDED`, `artifact_id=artifact.pk`, `exclude_user_id=ctx.user_id`.
- `Comment` hangs on `artifact_id` — the **generic** Artifact id, not the business-entity id. The
  REST/MCP callers must therefore resolve entity → Artifact via
  `TraceLinkService.resolve_entity_to_artifact_id` (Task 9) — same helper, same seam.

**Verification:** `application/tests/test_comment_service.py` from Plan #6 Task 15 Step 1 with the
two probe tests replaced by: (a) internal owner + external reporter → one recipient; (b) owner ==
reporter == comment author → zero recipients.

**Depends on:** Task 7, Task 10.

---

### Task 16 — REST endpoints for comments

**Original goal:** `rest_api/collaboration_views.py` with `ArtifactCommentsView` (list/create) and
`CommentViewSet` (resolve/delete), a `CommentSerializer`, and route registration.

**Adaptation to today:**

- **Import correction (must-fix):** the original code block imported
  `from rest_api.errors import build_error_response`. That module does not exist. Use
  `from rest_api.serializers import build_error_response, detect_lang` (matching every other view
  module, e.g. `backend/rest_api/comment` peers in `audit_views.py`, `metrics_views.py`).
- `_service_error_response` is `backend/rest_api/views.py:183`; import it from `rest_api.views`
  together with `BaseEntityViewSet` — exactly as `rest_api/interview_views.py` does.
- Route registration: the router block is `backend/rest_api/urls.py:189-219`. Add
  `router.register(r"comments", CommentViewSet, basename="comment")` there, and the nested
  `artifacts/<uuid:artifact_id>/comments/` path next to the other `urlpatterns` entries.
- **Drop the `NotificationSerializer` import from this task's file.** The original code block
  imported it "in anticipation" of Task 20 and told the reader to remove it if Task 20 was not yet
  done. In the re-scope, tasks are executed in order, so Task 16 must not reference it at all —
  Task 20 adds the import.
- Keep the ORM-ratchet test (`assert ".objects." not in source`); it is the guard that keeps this
  module on the right side of ADR-01.

**Verification:** `rest_api/tests/test_comment_endpoints.py` (7 cases) from Plan #6 Task 16 Step 1,
plus `grep -c ".objects." backend/rest_api/collaboration_views.py` → `0`.

**Depends on:** Task 15.

---

### Task 17 — MCP tool group `comment.*`

**Original goal:** `backend/mcp_server/tools/comment.py` with `comment.create` / `comment.list` /
`comment.resolve`, registered in the tool registry. `comment.delete` deliberately not exposed.

**Adaptation to today:**

- Registration point: `backend/mcp_server/tool_registry.py` → `_register_default_groups` /
  `register_groups({...})`. Re-locate with
  `grep -n "register_groups" backend/mcp_server/tool_registry.py` before editing — the original
  plan's "around line 540/557" is from an older tree.
- **New mandatory step (did not exist when the plan was written):** the repo now has a
  tool-manifest drift gate (`backend/mcp_server/tests/test_tool_manifest_drift.py`). After
  registering the group, regenerate the manifest with
  `python manage.py export_tool_manifest` and commit it in the same commit — otherwise the drift
  test fails the build. This is the one place where the re-scoped plan adds work the original
  plan did not have.
- The `json.dumps`-safety constraint (stdlib cannot encode `UUID`/`datetime`) and the reserved
  `content` key constraint are unchanged — keep both tests.
- `require_uuid` / `BaseToolGroup` / `ToolResult` import paths from the original code block are
  unchanged.

**Verification:** `mcp_server/tests/test_comment_tool_group.py` (6 cases) plus
`mcp_server/tests/test_tool_manifest_drift.py` green after manifest regeneration.

**Depends on:** Task 15.

---

### Task 18 — `notify_transition_pending` (role broadcast)

**Original goal:** after a workflow transition, notify every workspace user holding a role that may
perform one of the outgoing transitions. Hooked at the single non-test caller of
`StateLifecycleManager.perform_transition`.

**Adaptation to today:**

- Hook site is unchanged in kind but the line numbers moved:
  `backend/workflow/services.py` — `def transition` at `:210`, `perform_transition(...)` at `:283`,
  `return TransitionResult(...)` at `:293`. Insert the local-import + call **between `:283` and
  `:293`**.
- `WorkflowDefinitionStore.get_definition` still exists at `backend/workflow/definition_store.py:1109`;
  `TransitionDefinitionDTO.allowed_roles` at `:57`; `WorkflowDefinitionDTO` at `:63`. The producer
  body from Plan #6 Task 18 Step 3 needs no change.
- **Re-verify the "only non-test caller" claim before relying on it** — the tree has grown since:
  `grep -rn "perform_transition" backend/ --include=*.py | grep -v tests | grep -v lifecycle_manager.py`.
  If a second non-test caller now exists, hook the producer inside `perform_transition` itself
  instead, and record the deviation in the commit message.
- Keep the "never raises" contract (`try/except` → `return 0`): a notification must not break the
  transition it reacts to.
- KI-Vorschlag `proposed` states are ordinary role-gated transitions — no special case, as before.

**Verification:** `application/tests/test_notify_transition_pending.py` (5 cases) from Plan #6
Task 18 Step 1, plus `workflow/` suite green.

**Depends on:** Task 9, Task 10.

---

### Task 19 — `notify_suspect_flagged`

**Original goal:** notify the affected artifact's owner and assignee when the suspect propagation
flags it.

**Adaptation to today — call site now exists and is named:**

- The producer's call site is **no longer a grep-and-hope step**. It is
  `TraceLinkService.propagate_suspect_status` (`backend/application/trace_link_service.py:1293`),
  and the affected artifacts are collected in `newly_flagged_ids` (`:1416`, `:1430`). The
  `suspect_flagged_at` stamp sits directly after it at `:1442-1445`.
- Wire the producer **after line 1445**, iterating `newly_flagged_ids` (an `Artifact` id set) — that
  set, not `fired`, is the ground truth for "was actually flagged". Notifying off `fired` would
  produce false notifications for far ends that are non-flaggable or already suspect — the same
  false-audit-trail bug the stamp already avoids (`:1432-1440`).
- The recipient lookup is `notify_user_ids_for_artifact` (Task 15) — **not**
  `owner_and_assignee_for_artifact`. It takes an `Artifact` row, so bulk-fetch the flagged artifacts
  before the loop.
- Keep the "never raises" contract and the `_load_artifact` patch seam.

**Verification:** `application/tests/test_notify_suspect_flagged.py` (3 cases) from Plan #6 Task 19
Step 1, retargeted to the new recipient helper, plus `application/tests/test_suspect_propagation.py`
green (it already asserts the stamp behaviour at `:206`, `:280`).

**Depends on:** Task 10, Task 15.

---

### Task 20 — REST endpoints for notifications

**Original goal:** `NotificationSerializer`, `NotificationViewSet`
(list / `<pk>/read/` / `mark-all-read/`), envelope response `{notifications, unread_count}`,
registered as `r"notifications"`.

**Adaptation to today:**

- Add the `NotificationSerializer` import to `rest_api/collaboration_views.py` in this task (Task 16
  deliberately leaves it out — see Task 16).
- Register `router.register(r"notifications", NotificationViewSet, basename="notification")` in the
  router block at `backend/rest_api/urls.py:189-219`.
- Keep the deliberate non-pagination and the `DEFAULT_NOTIFICATION_LIMIT = 50` fallback; the service
  clamps at 200 regardless.
- No MCP counterpart — notifications intentionally have no agent-facing surface. State this in the
  module docstring, as the original did.

**Verification:** `rest_api/tests/test_notification_endpoints.py` (5 cases) plus the comment
endpoint suite still green (12 cases combined).

**Depends on:** Task 10, Task 16 (same module).

---

### Task 22 — Frontend API wrappers `comments.ts` / `notifications.ts`

**Original goal:** two typed API wrappers with snake_case→camelCase mapping in one place per type,
barrel re-export.

**Adaptation to today:**

- `frontend/src/api/client.ts`, `frontend/src/api/index.ts` and the `UUID` alias
  (`frontend/src/types/index.ts:15`) all exist — the original wiring is unchanged.
- **Path correction for the backend import of `UUID`:** the original code block imports
  `type { UUID } from "../types"`, which resolves to `frontend/src/types/index.ts` — correct as
  written. No change.
- The `NotificationKind` union is still exactly the four kinds.
- Keep `NOTIFICATION_FEED_LIMIT = 20`.

**Verification:** `frontend/src/api/comments.test.ts` (8 cases) from Plan #6 Task 22 Step 1.

**Depends on:** Task 16, Task 20 (wire shapes must match before the wrappers are written).

---

### Task 23 — `CommentPanel` in the artifact inspector

**Original goal:** a fourth stacked inspector panel with list/create/resolve/delete, `ConfirmDialog`
for the delete, tokens-only CSS, `data-testid` on every interactive element.

**Adaptation to today:**

- `RightSidebar.tsx` structure is unchanged: the no-tab comment is at `:344-345`, the panels block at
  `:458`, `TracePanel` at `:473`. Mount `CommentPanel` after `TracePanel`, inside `styles.panels`.
- `ArtifactKind` (`types.ts:21-33`) has **12** members, not 10 — includes `diagram` and `mainGoal`.
  The panel uses `kind` for the heading only, so nothing breaks; do not add a kind→count assumption.
- `ConfirmDialog` at `frontend/src/components/shared/ConfirmDialog.tsx` and `tokens.css`
  (`frontend/src/styles/tokens.css`) both exist. The CSS-module token names in the original plan must
  be checked against the file —
  `grep -o -- "--[a-z-]*" frontend/src/styles/tokens.css | sort -u` — and substituted with the nearest
  existing token if any are missing. Never introduce a literal.
- Vite HMR does not work on Windows in this stack: restart the frontend container before browser
  verification, as the original plan's Step 7 says.

**Verification:** `CommentPanel.test.tsx` (8 cases) from Plan #6 Task 23 Step 1, plus the existing
`RightSidebar.test.tsx` suite (it stubs the three sibling panels — add a stub for `CommentPanel` so
the shell test stays isolated).

**Depends on:** Task 22.

---

### Task 24 — `NotificationBell` in the sidebar footer

**Original goal:** a bell with an unread badge and a dropdown, mounted in the pinned sidebar footer,
fetched once on mount and after each mark-read. No polling, no push.

**Adaptation to today:**

- Mount point unchanged: `SidebarNavigation.tsx:718` (`<div className={styles.footer}>`), insert
  immediately before the `nav-profile` button at `:754`. `NavigationShell.tsx` is still a pure
  router, so the original placement decision still holds.
- Keep the silent-on-fetch-failure behaviour — a notification centre must never block the chrome it
  lives in.

**Verification:** `NotificationBell.test.tsx` (9 cases) from Plan #6 Task 24 Step 1, plus the
`NavigationShell` suite green.

**Depends on:** Task 22.

---

### Task 25 — i18n keys for comments and notifications

**Original goal:** nested `comments.*` / `notifications.*` namespaces in `de.json` and `en.json`,
with a test asserting both locales and the absence of flat dotted keys.

**Adaptation to today:**

- `frontend/src/i18n/locales.test.ts` **does not exist** — take the original plan's "otherwise
  create" branch. Create the file as written.
- `frontend/src/i18n/index.ts` sets no `keySeparator`, so i18next's default `"."` applies. The flat
  dotted key ban is still correct and still worth the regression test.
- `de.json` / `en.json` exist at `frontend/src/i18n/locales/`.
- Note: this task depends on the key list actually used by Tasks 23 and 24 — run it **last** so the
  test's key constants reflect reality rather than the plan's draft.

**Verification:** `frontend/src/i18n/locales.test.ts` green (~40 cases with `describe.each`).

**Depends on:** Task 23, Task 24.

---

## 4. Dropped tasks

| # | Task | Reason |
|---|---|---|
| 1 | `owner`/`assignee` FKs on the five `persistence` types | **Superseded by Attribut v3 (#936/#940)** — `owner` lives centrally on `Artifact` as an `Actor` FK (`persistence/models.py:1096`). |
| 2 | `owner`/`assignee` FKs on `Icd` | **Superseded by Attribut v3 (#936)** — same central `Artifact.owner`, no per-type column. |
| 3 | `owner`/`assignee` FKs on `Adr` and `Goal` | **Superseded by Attribut v3 (#936)** — same. |
| 4 | Risk owner-match report (human gate) | **Superseded by AWMS** — `Risk.owner` → `owner_name` already landed (`persistence/0092`); matching is now the AWMS `transform: to_actor` step, not a bespoke command. |
| 5 | Risk contract phase (backfill, drop CharField, rename FK) | **AWMS-owned** — `backend/attribute_definitions/migration_plans/risk_owner_to_actor.yaml`; the physical column drop is a later AWMS contract step. |
| 6 | Issue contract phase (`assignee_id` UUIDField → FK) | **AWMS-owned** — `backend/attribute_definitions/migration_plans/issue_assignee_to_actor.yaml`. |
| 12 | Wire the five `persistence` services onto `apply_assignment` | **Superseded** — no per-type `owner`/`assignee` fields to wire; the gateway is the write path (§5). |
| 13 | Wire `Adr`/`Goal`/`Icd`/`Risk`/`Issue` onto the seam | **Superseded** — same reason as Task 12. |
| 14 | AST ratchet: no direct `owner`/`assignee` writes outside the seam | **Superseded** — `apply_assignment` does not exist and must not be built; §5 names the real seam. If a ratchet is wanted later, it should guard `ArtifactAttributeGateway.write` instead. |
| 21 | `owner_id`/`assignee_id` on the ten serializers and views | **Already delivered by Attribut v3** — `owner`/`reporter`/`priority` are on the serializers via `artifact_system_fields` (`rest_api/serializers.py:570-593`, `mcp_server/tools/generic.py:10`). |
| 26 | Re-run the bootstrap so `owner`/`assignee` become core attributes | **Done** — `owner`/`reporter`/`priority` are already `_ARTIFACT_LEVEL_CORE_FIELDS` (`application/artifact_attribute_gateway.py:144-146`), bootstrapped by `bootstrap_attribute_definitions`. |

---

## 5. The `assigned` trigger — exact seam

The original plan routed `assigned` through `application/assignment.py::apply_assignment()` (its
Task 11). **That module was never created and must not be created**
(`grep -r "apply_assignment" backend/` → no files). The `assigned` notification kind still exists —
it just has a different seam today.

### Today's write path for `Artifact.owner` / `.reporter`

```text
REST   backend/rest_api/views.py:428   BaseEntityViewSet._apply_artifact_system_fields()
REST   backend/rest_api/views.py:458     -> ArtifactAttributeGateway().write(...)
MCP    backend/mcp_server/tools/system_fields.py:77   apply_system_fields()
MCP    backend/mcp_server/tools/system_fields.py:106    -> ArtifactAttributeGateway().write(...)
                                                                    |
                                                        both converge on
                                                                    v
       backend/application/artifact_attribute_gateway.py:625   ArtifactAttributeGateway.write()
       backend/application/artifact_attribute_gateway.py:690-698   owner/reporter/priority resolved
       backend/application/artifact_attribute_gateway.py:697       setattr(target, name, value)   <-- single assignment site
       backend/application/artifact_attribute_gateway.py:710-711   for target in targets: self._persist(target)
```

### Binding point

> **`backend/application/artifact_attribute_gateway.py:710`** —
> the `for target in targets: self._persist(target)` loop inside
> `ArtifactAttributeGateway.write()`.

`notify_assigned(...)` is called **after** that loop, so it fires only once the new actor FK is
actually persisted, and it fires for REST and MCP identically (ADR-004: one gateway, both
transports). Do **not** put the call at the `setattr` on `:697` — that is pre-save, so a failing
`_persist` would already have produced a notification for an assignment that never landed.
(Validation itself runs earlier still, at `:658`.)

### Semantics required by the re-scope

- Compare the pre-write and post-write `owner` Actor. **`write()` does not read the previous value
  on its own** — it calls `setattr` directly (`:697`); the read path `_read_core_value` (`:497-510`)
  belongs to `read()`. Capture `getattr(target, "owner_id")` explicitly **before** the assignment
  loop (`:674`), so the comparison needs no extra query.
- Notify **only the newly set owner**, and only when that `Actor` has `kind == "user"` — take
  `actor.user_id`. An `Actor` with `kind == "external"` has no login and no feed; skip it
  (`persistence/models.py:784-834`).
- `exclude_user_id=ctx.user_id` — never notify the actor who performed the write.
- `artifact_id` = the backing Artifact id (the gateway already holds it), so no
  `resolve_artifact_id_or_none` call is needed on this path.
- `kind = Notification.KIND_ASSIGNED`.
- Never raises: wrap in `try/except` + `logger.exception` like the other three producers, so a
  notification failure cannot roll back a legitimate attribute write.

### Open Decision (see §9, OD-1)

Whether a change to **`reporter`** also produces an `assigned` notification. Recommendation: **no** —
`reporter` is provenance ("who reported this"), not an assignment. Only `owner` changes notify.
This is a product decision, not an implementation detail.

---

## 6. Global Constraints

Adopted from Plan #6, corrected where the tree has moved.

**Still valid verbatim:**

- `Comment` hangs on `persistence.Artifact`, never on a specialised table — that is what makes it
  work for every artifact type with no special case.
- Notification triggers are exactly four: `transition_pending`, `suspect_flagged`, `assigned`,
  `comment_added`. `transition_pending` is a **role broadcast** over the outgoing transitions'
  `allowed_roles`, never person-scoped routing.
- No real-time push: no WebSocket, no SSE, no Celery task. The bell fetches once on mount.
- No MCP tool group for notifications.
- Comments are not editable — create, list, resolve, delete (author or admin) only, which is why
  there is no comment change history.
- DRF views must not touch the ORM — `backend/rest_api/` has a ratchet counting `.objects.`
  occurrences, including inside docstrings. All reads/writes go through a Layer-2 service.
- Every DRF view calls `get_auth_context(request)` (`backend/rest_api/auth_enforcer.py`) — never
  query without it, RLS returns an empty set.
- No inline styles in `frontend/src/components/`; use CSS modules + `styles/tokens.css` custom
  properties.
- `data-testid` on every interactive element. Deletes use
  `components/shared/ConfirmDialog.tsx` (`confirmTestId`/`cancelTestId` props) — never hand-roll a
  confirm.
- Named exports only; PascalCase for React components, snake_case for Python.

**Corrected / added for today:**

- **Migration prefixes:** `persistence/0093`, `application/0025`, `application/0026`. (`icd/0014` is
  the next free icd prefix but this re-scope touches no icd migration.)
  Before each `makemigrations`, run `ls backend/<app>/migrations/ | tail -3` and use the next free
  prefix — the numbers above are the state at 2026-09-15, not a guarantee.
- **Attribution is `Actor`, not `User`.** `Artifact.owner` / `.reporter` are FKs to
  `persistence.Actor` (`persistence/models.py:1096-1111`). Only `Actor.kind == "user"` rows have a
  `user_id` and can be notified. `Notification.user` stays a `User` FK.
- **There is no `assignee` field.** Do not add one in this re-scope.
- **No `apply_assignment`, no `application/assignment.py`, no AST ratchet for owner writes.** The
  gateway (§5) is the seam.
- **MCP manifest drift gate:** adding `comment.*` requires regenerating the tool manifest
  (`backend/mcp_server/management/commands/export_tool_manifest.py`) in the same commit, or
  `backend/mcp_server/tests/test_tool_manifest_drift.py` fails.
- **`build_error_response` is imported from `rest_api.serializers`**, not `rest_api.errors`
  (which does not exist).
- **`ArtifactKind` has 12 members** (`diagram`, `mainGoal` included) — do not assume 10.
- **Ordering vs. the Attribute-Definition spec:** no longer a constraint. `owner`/`reporter` are
  already core attributes; Task 26 is dropped (§4). The re-scoped tasks do not touch the bootstrap.

---

## 7. Commands used throughout

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

Migrations (the DB **owner** role, not the least-privilege app role, is required for DDL and data
migrations — the compose test/backend service already uses `DB_USER=reqogniloom`):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py makemigrations <app> --name <name>
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
```

MCP manifest regeneration (required after Task 17):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py export_tool_manifest
```

Frontend restart (Vite HMR is broken on Windows in this stack):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . restart frontend
```

> Verify the service names once before the first run:
> `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . config --services`.

---

## 8. Task order, dependencies and verification

Sequence: **7 → 8 → 9 → 10 → 15 → 16 → 17 → 18 → 19 → 20 → 22 → 23 → 24 → 25**

| # | Task | Depends on | Verification |
|---|---|---|---|
| 7 | `Comment` + `Notification` models | — | `application/tests/test_collaboration_models.py` (8) |
| 8 | RLS for `as_comment` / `as_notification` | 7 | `application/tests/test_collaboration_rls.py` (4) |
| 9 | `resolve_artifact_id_or_none()` | — | `application/tests/test_resolve_artifact_id_or_none.py` |
| 10 | `NotificationService` + `create_notifications` + `notify_assigned` | 7 | `application/tests/test_notification_service.py` (8), `test_notify_assigned.py` |
| 15 | `CommentService` + `notify_user_ids_for_artifact` | 7, 10 | `application/tests/test_comment_service.py` |
| 16 | REST comments | 15 | `rest_api/tests/test_comment_endpoints.py` (7), ORM-ratchet grep = 0 |
| 17 | MCP `comment.*` | 15 | `mcp_server/tests/test_comment_tool_group.py` (6) + drift test + manifest regenerated |
| 18 | `notify_transition_pending` | 9, 10 | `application/tests/test_notify_transition_pending.py` (5), `workflow/` green |
| 19 | `notify_suspect_flagged` | 10, 15 | `application/tests/test_notify_suspect_flagged.py` (3), `test_suspect_propagation.py` green |
| 20 | REST notifications | 10, 16 | `rest_api/tests/test_notification_endpoints.py` (5) |
| 22 | API wrappers `comments.ts` / `notifications.ts` | 16, 20 | `frontend/src/api/comments.test.ts` (8) |
| 23 | `CommentPanel` | 22 | `CommentPanel.test.tsx` (8) + `RightSidebar.test.tsx` green |
| 24 | `NotificationBell` | 22 | `NotificationBell.test.tsx` (9) + `NavigationShell` green |
| 25 | i18n keys de/en | 23, 24 | `frontend/src/i18n/locales.test.ts` green |

Parallelisable: 8 ∥ 9; 16 ∥ 17 ∥ 18 ∥ 19 after 15/10; 23 ∥ 24 after 22.

**Per-task gate:** run the task's own test file, then the touched app's suite. Do not batch the
green check to the end of a phase.

---

## 9. Open Decisions

**OD-1 — Does `reporter` trigger the `assigned` notification?**
`owner` and `reporter` both live on `Artifact` and are written through the same gateway call.
Recommendation: notify on `owner` only; `reporter` is provenance, not an assignment. Needs a product
answer before Task 10's `notify_assigned` is written, because it decides whether the producer takes
one id or two.

**OD-2 — Is `Comment.author` a `User` FK or an `Actor` FK?**
Recommendation: keep `User` (a comment requires a login; the notification fan-out needs a
`user_id` directly). Choosing `Actor` would force an actor→user resolution on every read projection.
Flagged rather than assumed because the rest of the attribution model moved to `Actor` in #936 and a
reviewer may want consistency over simplicity.

**OD-3 — Does the `comment_added` fan-out include `reporter`?**
Same shape as OD-1, one level down: `notify_user_ids_for_artifact` returns owner + reporter under
the recommendation. If OD-1 resolves to "owner only", this should follow for consistency.

**OD-4 — Should a suspect-flag notification go to the artifact's owner even when the owner is
external?**
Recommendation: no (external actors have no feed). Consequence: for an externally-owned artifact, a
suspect flag produces zero notifications and the flag is only visible in the artifact's own state.
Accepted for v1; revisit if it turns out to hide real work.

None of OD-1…OD-4 blocks Tasks 7, 8, 9, 16, 17, 20, 22–25. OD-1 blocks Task 10's `notify_assigned`
writer; OD-3 blocks Task 15's `create_comment`. They can be answered in parallel with the early
schema tasks.

---

## 10. Self-review

### Coverage of the original plan's collaboration half

| Original task | Re-scoped as | Status |
|---|---|---|
| 7 Comment/Notification models | Task 7 | adopted, prefix updated |
| 8 RLS policies | Task 8 | adopted, dependency added |
| 9 `resolve_artifact_id_or_none` | Task 9 | adopted, public wrapper |
| 10 `NotificationService` | Task 10 | adopted + `notify_assigned` folded in |
| 15 `CommentService` | Task 15 | adopted, 10-relation probe removed |
| 16 REST comments | Task 16 | adopted, import path corrected |
| 17 MCP `comment.*` | Task 17 | adopted, manifest step added |
| 18 `transition_pending` | Task 18 | adopted, hook line moved |
| 19 `suspect_flagged` | Task 19 | adopted, call site now concrete |
| 20 REST notifications | Task 20 | adopted |
| 22 API wrappers | Task 22 | adopted |
| 23 `CommentPanel` | Task 23 | adopted, RightSidebar re-verified |
| 24 `NotificationBell` | Task 24 | adopted |
| 25 i18n | Task 25 | adopted, test file created |

Dropped owners half: Tasks 1–6, 12, 13, 14, 21, 26 — see §4.

### Not covered, on purpose

- `MainGoal` / `Diagram` attribution — was already out of scope in the original plan (its Task 3
  decision) and is untouched by this re-scope.
- The physical drop of `Risk.owner_name` / `Issue.assignee_id` — AWMS-owned contract step.
- Any owner/assignment edit UI — the attribute-definition renderer already ships `owner`/`reporter`.

### Placeholder scan

No `TBD`, no `TODO`, no "similar to Task N". Three items defer to a grep or a decision, each with an
exact command or an explicit Open Decision ID and a stated fallback:

- Task 17 — registry line number is located by `grep -n "register_groups"`, because the original
  plan's line reference predates the current tree.
- Task 18 — the "only non-test caller" claim must be re-verified by grep, with the fallback named.
- §9 OD-1…OD-4 — recorded as decisions, not guessed.

### Type-consistency check

- `create_notifications` keyword signature is identical in its definition (Task 10) and all four
  producers (Task 10 `notify_assigned`, Task 15, Task 18, Task 19).
- `notify_user_ids_for_artifact` is defined once (Task 15) and consumed by Task 19 only.
- `Notification.KIND_*` constants are referenced by name, never as string literals.
- `resolve_artifact_id_or_none` is defined in Task 9 and used in Task 18; §5 explains why the
  `assigned` producer does **not** need it.
- `NotificationSerializer` is created in Task 20 and imported in Task 20 only (Task 16 no longer
  references it).
- Frontend: `Comment` / `Notification` TS interfaces (Task 22) match the DRF serializer fields
  (Tasks 16, 20) field-for-field.
- `ArtifactKind` is imported from the existing `ArtifactInspector/types.ts`, not redeclared.
