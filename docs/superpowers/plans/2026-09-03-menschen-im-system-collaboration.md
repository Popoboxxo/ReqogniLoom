# Menschen im System — Collaboration Half (Re-Scope)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** RE-SCOPE (2026-09-15). This document supersedes the **collaboration half** of
[2026-09-03-menschen-im-system.md](2026-09-03-menschen-im-system.md). The owner/assignment half of
that plan is **cancelled** — it was overtaken by the merged Attribut-System v3
(epic #934, WS2 #936, WS7 #940) and by the AWMS migration plans. User decision (Option A,
2026-09-15): only Comments + Notifications are re-scoped and will be implemented later.

**Amendment (2026-09-15, second pass):** all four Open Decisions (OD-1…OD-4) are **resolved** — see
§9. OD-1 was resolved *with a scope extension*: notification delivery becomes configurable in the
user's own profile (four opt-out switches, user-global). That extension adds five re-scope-owned
tasks (**26–30**) and is the only change to §1's scope since the re-scope. One new decision was found
while resolving them (OD-5, Task-ID reuse) and is recorded in §9 rather than silently resolved.

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
- **User-profile notification preferences** (amendment 2026-09-15, resolves OD-1): one **user-global**
  opt-out preference with **four switches** — `assigned`, `comment_added`, `transition_pending`,
  `suspect_flagged`, all **on** by default — a self-service REST endpoint, and a
  `NotificationsSection` in the user profile. Tasks 26–30.

### Out of scope — the preference amendment

The deliberate boundary of OD-1's scope extension. Do not widen it without a new decision:

- **No e-mail, no WebSocket/SSE push, no webhooks, no Celery delivery task.** The preference only
  gates *which in-app `Notification` rows get created* for a user. The "no real-time push" constraint
  in §6 is unchanged.
- **No per-workspace preference.** One row per user, applied across every tenant and workspace the
  user belongs to — that is what "user-global" means here. A per-workspace variant would need its own
  decision; it is not a free extension of Task 26.
- **No notification history, archive, digest, or per-artifact mute.** If a trigger is off, the row is
  simply never written.
- **No preference entry for the acting user.** Self-notification suppression stays the producer's
  `exclude_user_id` concern and is applied *before* the preference filter (Task 27).

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

Facts added by the OD-1 amendment (also read at the working tree, 2026-09-15):

| Fact | Evidence |
|---|---|
| Per-user preference precedent: `JSONField` + `TenantScopedModel` + `UniqueConstraint(tenant, user, workspace)` | `backend/auth_tenancy/models.py:423-463` (`UserWorkspacePreference`) |
| Next free `auth_tenancy` migration prefix is **0014** | `backend/auth_tenancy/migrations/` — last file is `0013_apikey_agent_identity.py` |
| A new `TenantScopedModel` **must** ship a `CREATE POLICY` migration or the build fails | `backend/persistence/tests/test_rls_coverage.py:147-163` (static diff of the migration graph against every concrete `TenantScopedModel`), `:189-223` (same expectation against live `pg_policies` / `pg_class.relforcerowsecurity`) |
| Layer-2 preference-service precedent: `ServiceBase`, `_set_tenant_context(ctx)`, explicit `tenant_id` on `get_or_create` | `backend/auth_tenancy/services/preference_service.py:30-110` |
| `application/` may import `auth_tenancy.models` directly | `backend/application/memory_admin_service.py:37` (`from auth_tenancy.models import UserRole`) |
| Self-service REST precedent for `/users/me/*`: `get_auth_context` + `HasOperationPermission`, no workspace in the URL, no admin gate | `backend/admin_ops/theme_rest.py:225-272` (`UserThemePreferenceView`); route `backend/rest_api/urls.py:399-405` |
| Self-service view that delegates to a Layer-2 service instead of touching the ORM | `backend/memory/memory_rest.py:559-604` (`MemorySelfServiceView`); route `backend/rest_api/urls.py:516-522` |
| The ORM ratchet picks up a new `rest_api/*_views.py` by **glob** — ceiling 0, and no direct `persistence.models` import | `backend/rest_api/tests/test_architecture.py:154-164`, `:205-215`, `:218-225` |
| A workspace-free endpoint must **not** be added to the `?workspace_id=`-family list (it asserts a bare GET returns 400) | `backend/rest_api/tests/test_api_consistency_460.py:144-162` |
| Frontend profile-section precedent: own CSS module, `data-testid` on every control, API imported directly from its module | `frontend/src/components/UserProfileSettings/MemorySection.tsx:18-20`, `:81-88`, `:124-132`; mounted at `UserProfileSettings.tsx:94-98` |
| Not every API wrapper is re-exported from the barrel | `frontend/src/api/memory-self-service.ts` exists; `frontend/src/api/index.ts` has no entry for it |
| i18n blocks are top-level keys, placed next to `memorySelfService` | `frontend/src/i18n/locales/de.json:1380`, `frontend/src/i18n/locales/en.json:1380` |

---

## 3. Adopted tasks (Plan #6 → here)

Task IDs are kept from the original plan so traceability is one lookup. Dropped numbers are
listed in §4. Tasks **26–30** are the only re-scope-owned numbers: they are new scope introduced by
the OD-1 amendment (2026-09-15) and have no counterpart in the original plan — see the numbering note
under §4.

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
  never receive a notification (see §5). **OD-2 resolved the same way (2026-09-15): this is the
  decision now, not a recommendation.**
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
plus `docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . run --rm migrate python manage.py migrate` returning cleanly.

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
- **The preference filter is inside `create_notifications` from the start** (OD-1, Task 27).
  `create_notifications` calls
  `NotificationPreferenceService.apply_preferences(ctx, user_ids, kind)` as its **last step before**
  the `MAX_FANOUT` clamp and the `Notification.unscoped.bulk_create` — so the clamp counts the users
  who will actually be notified, not the raw candidate list. No producer filters its own recipients;
  all four go through this one function, which is what makes the preference impossible to forget on
  one path and honour on another. This is why Task 10 depends on Task 27 and therefore runs *after*
  it despite the higher number (§8).
- **Do not add a `reporter` branch to `notify_assigned`.** OD-1 is resolved: the producer fires only
  when `owner` changes (see §5).

**Verification:** `application/tests/test_notification_service.py` (8 cases) from Plan #6 Task 10
Step 1, plus `application/tests/test_notify_assigned.py` for the new producer (§5), plus
`application/tests/test_notification_preference_service.py` (Task 27) which owns the filter's own
contract.

**Depends on:** Task 7, Task 27.

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
  **OD-3 (resolved 2026-09-15): the fan-out is owner + reporter, with the author excluded** — exactly
  what the probe above returns plus that `exclude_user_id`. The list handed to `create_notifications`
  is the *candidate* set; the preference filter (Task 27) removes users who switched this trigger off.
  **Do not add a producer-local preference check here.**
- One asymmetry worth stating, because it is deliberate and not an oversight: `reporter` receives a
  `comment_added` notification even though it does **not** receive an `assigned` notification (OD-1).
  A comment is follow-up traffic on something the reporter raised; an assignment is not.
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
- **Recipients are filtered inside `create_notifications` (Task 27) — do not re-filter here.** A role
  broadcast is muted per user exactly like a person-scoped notification: a user who switched
  `transition_pending` off receives nothing, even when they hold an `allowed_roles` role.

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
- **OD-4 (resolved 2026-09-15): an external owner is never notified.**
  `notify_user_ids_for_artifact` (Task 15) already drops `Actor.kind == "external"`, so for an
  externally-owned artifact a suspect flag produces zero notifications and the flag stays visible only
  in the artifact's own state. Accepted for v1; revisit if it turns out to hide real work. The
  preference filter (Task 27) applies on top as usual — no producer-local check here either.

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

### Task 26 — `UserNotificationPreference` model + both migrations

**Original goal:** none — **new scope** from the OD-1 amendment (2026-09-15). One user-global opt-out
preference recording which of the four notification triggers the user has switched **off**.

**Model — append to `backend/auth_tenancy/models.py`, directly after `UserWorkspacePreference`
(`:423-463`). Extend the existing import at `:31` to `from persistence.models import AuditableModel,
TenantScopedModel`:**

```python
class UserNotificationPreference(AuditableModel):
    """Per-user opt-out from in-app notification triggers (OD-1, 2026-09-15).

    One row per user, across every tenant and workspace — ``User`` is itself an
    ``AuditableModel`` without tenant scoping (`persistence/models.py:463`), so
    the preference follows the same global identity. A missing row, or a kind
    absent from ``disabled_triggers``, means the trigger is ENABLED: opting out
    is the deviation, not opting in.
    """

    user = models.OneToOneField(
        "persistence.User",
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    disabled_triggers = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "at_user_notification_preference"
```

- **JSON list of disabled trigger keys, not four boolean columns** (assumption A2, §9): it mirrors the
  `optional_artifact_visibility` JSONField one class above, stores only the deviations, and stays
  stable if a fifth trigger kind is ever introduced. `Notification.KIND_CHOICES` (Task 7) remains the
  **only** definition of the trigger vocabulary — this model must not restate it, and the value
  validation lives in Task 28's serializer.
- **The `OneToOneField` is the uniqueness *and* the access path.** No separate unique constraint or
  index is needed; every lookup is "the preference row of this user". Do not add a `tenant` field — a
  user-global preference is intentionally not tenant-scoped.
- Do not redeclare `id` / `created_at` / `modified_at` — inherited from `AuditableModel`
  (`persistence/models.py:341-407`).
- **Do not put this model in `application/models.py`.** It is a user preference, not a collaboration
  entity; `auth_tenancy` already owns `UserWorkspacePreference`, and a new app-level table there does
  not drag `application` into a new migration chain.

**One migration, in this task:**

`backend/auth_tenancy/migrations/0014_user_notification_preference.py` — generated:
```
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py makemigrations auth_tenancy --name user_notification_preference
```
Re-check the prefix first: `ls backend/auth_tenancy/migrations/ | tail -2` — `0013_apikey_agent_identity.py`
is the current last file, but §6 says re-verify before every `makemigrations`.

**There is deliberately no RLS migration.** `UserNotificationPreference` is not a `TenantScopedModel`,
so it is outside `persistence/tests/test_rls_coverage.py`'s coverage by construction
(`_tenant_scoped_tables()` filters `issubclass(model, TenantScopedModel)`, `:133-139`, `:147-163`) and
because it holds no tenant-owned data. Do **not** add it to `RLS_EXEMPT_TABLES` (`:51-87`): that
allowlist is asserted to contain tenant-scoped tables only
(`test_rls_exemptions_are_still_tenant_scoped_tables`, `:166-183`), so a non-tenant-scoped entry would
fail the build. The table is accessed exclusively as "the current user's own row" (Task 28), never by
tenant.

**Verification:** `auth_tenancy/tests/test_notification_preference_model.py` (4 cases):
(a) `disabled_triggers` defaults to `[]` and survives a save/refresh round-trip;
(b) a second row for the same `user` is rejected (the `OneToOneField` uniqueness; assert
`IntegrityError` inside `transaction.atomic()`);
(c) two users each get their own row;
(d) the same user reading the row in a different tenant/workspace context still sees the **same**
single row — this is what "user-global" means (§9, A1).
Plus `persistence/tests/test_rls_coverage.py` green and
`docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . run --rm migrate python manage.py migrate`
returning cleanly.

**Depends on:** —

---

### Task 27 — `NotificationPreferenceService` + the recipient filter

**Original goal:** none — **new scope** (OD-1). The single place that turns "candidate recipients +
trigger kind" into "recipients who actually want this trigger", plus the read/write methods the
self-service endpoint (Task 28) needs.

**New module — `backend/application/notification_preference_service.py`:**

- `class NotificationPreferenceService(ServiceBase)`.
- **`ALL_KINDS` derives from `Notification.KIND_CHOICES`** (Task 7) — never a second literal list. The
  four kinds are `KIND_ASSIGNED`, `KIND_COMMENT_ADDED`, `KIND_TRANSITION_PENDING`,
  `KIND_SUSPECT_FLAGGED`.
- **`apply_preferences(self, ctx, user_ids: list[UUID], kind: str) -> list[UUID]` — the filter.**
  - One query only: `self._set_tenant_context(ctx)`, then
    `UserNotificationPreference.objects.filter(user_id__in=user_ids)`, then subtract every user whose
    `disabled_triggers` contains `kind`. No N+1 — the candidate list is capped at `MAX_FANOUT = 200`
    by its caller.
  - Input order preserved, duplicates removed, blank/unknown entries in `disabled_triggers` ignored
    (not an error). An unknown `kind` argument filters nothing.
  - **Fail-open, never raise.** A lookup failure (`TenantContextNotSetError`, `DatabaseError`,
    anything) must `logger.exception(...)` and return `user_ids` **unchanged**. Rationale in §9 (A3):
    the four producers all carry a "never raise" contract because a notification must not break the
    mutation it reacts to — failing *closed* here would additionally stop delivery for every user the
    moment the preference table is unreachable, which is a worse failure than an un-muted notification.
- `get_effective_preferences(self, ctx) -> dict[str, bool]` — `{kind: bool}` for all four kinds,
  `True` when no row exists. Built from the same `ALL_KINDS`; this is the GET projection.
- `update_preferences(self, ctx, changes: dict[str, bool]) -> dict[str, bool]` — partial update:
  `False` adds the kind to `disabled_triggers`, `True` removes it, kinds not present in `changes` are
  untouched. Returns the fresh effective map, de-duplicating the stored list.
  - Use `UserNotificationPreference.objects.update_or_create(user_id=..., tenant_id=ctx.tenant_id,
    defaults={...})` with an **explicit** `tenant_id` in the lookup:
    `update_or_create`'s create fallback goes through `QuerySet.create()` and bypasses
    `TenantManager.create()`'s auto-inject — the exact trap
    `PreferenceService.get_or_create_preference` documents (`auth_tenancy/services/preference_service.py:77-86`).
  - Raise `ValidationError` for an unknown kind or a non-bool value; the view (Task 28) maps it to 400.
- **Layer direction:** `application/` → `auth_tenancy.models` is already an established import
  (`application/memory_admin_service.py:37` imports `UserRole`), so no layer guard is tripped. The
  service deliberately does **not** live in `auth_tenancy/services/` next to `PreferenceService`: that
  package already imports `application.base.ServiceBase`, so placing the filter there would create an
  `application → auth_tenancy.services → application` import cycle the moment Task 10 imports it.

Wiring the filter into `create_notifications` is **Task 10's** job — it owns that function. This task
only ships the filter and proves its contract in isolation.

**Verification:** `application/tests/test_notification_preference_service.py` (7 cases):
(a) no row → all four kinds `True`, and `apply_preferences` returns the candidate list unchanged;
(b) `disabled_triggers=["comment_added"]` → that user is removed for `comment_added`, the other three
kinds pass through;
(c) a user disabled for `assigned` still receives `transition_pending`;
(d) blank / unknown entries in `disabled_triggers` are ignored, not an error;
(e) `apply_preferences` preserves input order and de-duplicates the input;
(f) a forced query failure is swallowed and returns the input list unchanged (fail-open) — patch
`UserNotificationPreference.objects` to raise;
(g) `update_preferences({"comment_added": False})` then `({"comment_added": True})` round-trips back to
all-enabled without leaving a duplicate entry in the stored list.
Plus `persistence/tests/test_rls_coverage.py` green (a test that forgets `ctx` will fail closed on
`TenantContextNotSetError` inside `_set_tenant_context` — which is the point).

**Depends on:** Task 7 (the `KIND_*` vocabulary), Task 26 (the model).

---

### Task 28 — Self-service REST for the notification preference

**Original goal:** none — **new scope** (OD-1). Let a user read and change their own preference
without an admin, from the profile page.

**New module — `backend/rest_api/notification_preference_views.py`:**

- `class NotificationPreferenceView(APIView)` — `permission_classes = [HasOperationPermission]`,
  **no** `required_operation`: the same shape as the two sibling `/users/me/*` self-service views
  (`admin_ops/theme_rest.py:225-229` `UserThemePreferenceView`, `memory/memory_rest.py:559-573`
  `MemorySelfServiceView`). Any authenticated user, own data only — the `ctx.user_id` filter inside
  the service **is** the authorization boundary. No admin gate, and no `user_id` parameter to abuse.
  (`HasOperationPermission` rather than the default `RbacPermission` because the URL carries no
  `workspace_id`; `ctx.active_roles` can resolve to `()` for a legitimate caller.)
- **`GET /api/v1/users/me/notification-preferences/`** →
  `{"preferences": {"assigned": true, "comment_added": true, "transition_pending": true,
  "suspect_flagged": true}}` — the **effective** map for all four kinds, `true` when no row exists
  (opt-out default). The client never has to know the vocabulary or invert a disabled-list.
- **`PATCH`** on the same path, body `{"preferences": {"<kind>": <bool>}}` — partial; only the kinds
  present in the body change. Returns the same effective map, so the caller can render the server's
  truth instead of its own optimistic guess.
- `lang = detect_lang(request)`; `get_auth_context(request)` inside a `try/except` → 401
  `build_error_response("AUTHENTICATION_REQUIRED", lang)`. §6's rule applies: never query without it —
  RLS returns an empty set.
- `NotificationPreferenceUpdateSerializer(serializers.Serializer)` with
  `preferences = serializers.DictField(child=serializers.BooleanField())`, plus a validator that
  rejects any key outside `NotificationPreferenceService.ALL_KINDS`. Invalid input → 400
  `build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in
  ser.errors.items()])`. A `ValidationError` from the service → 400 `VALIDATION_ERROR` with
  `message=str(exc)`.
- **No ORM in this module, and no `from persistence.models import`.** The file name matches
  `rest_api/*_views.py`, so `rest_api/tests/test_architecture.py:154-164` picks it up by glob and
  applies the default ceiling of **0** (`:205-215`), plus the model-import allowlist (`:218-225`).
  Every read and write goes through `NotificationPreferenceService` (Task 27). The module name is
  therefore load-bearing, not cosmetic: the glob *is* the guard.
- **No MCP counterpart.** A notification preference is a human preference, and notifications
  deliberately have no agent-facing surface (§6). State this in the module docstring, as Task 20 does.

**Route — `backend/rest_api/urls.py`, directly beneath the `users/me/preferences/` entry
(`:393-398`):**

```python
    # Notification delivery preferences (OD-1, 2026-09-15) — the caller's own
    # opt-out switches over the four notification triggers. Same self-service
    # shape as users/me/preferences/ directly above.
    path(
        "users/me/notification-preferences/",
        NotificationPreferenceView.as_view(),
        name="user-notification-preferences",
    ),
```

- **Do NOT add this path to `WORKSPACE_SCOPED_PATHS`** in
  `rest_api/tests/test_api_consistency_460.py:144-162`. That list asserts a bare GET answers 400
  `"workspace_id is required"`; this endpoint reads no `?workspace_id=`, so adding it would fail the
  suite rather than protect anything.

**Verification:** `rest_api/tests/test_notification_preference_views.py` (6 cases):
(a) GET with no row → 200, all four `true`;
(b) PATCH `{"preferences": {"comment_added": false}}` → 200, only `comment_added` flips, and a row now
exists (assert via `UserNotificationPreference.unscoped`);
(c) PATCH `{"preferences": {"comment_added": true}}` → flips back, no duplicate entry;
(d) PATCH `{"preferences": {"not_a_kind": false}}` → 400 `VALIDATION_ERROR`;
(e) PATCH `{"preferences": {"assigned": "yes"}}` → 400 `VALIDATION_ERROR`;
(f) unauthenticated GET and PATCH → 401.
Plus `rest_api/tests/test_architecture.py` green (0 direct-ORM lines in the new module),
`grep -c ".objects." backend/rest_api/notification_preference_views.py` → `0`, and
`application/tests/test_notification_preference_service.py` still green.

**Depends on:** Task 27.

---

### Task 29 — `NotificationsSection` in the user profile

**Original goal:** none — **new scope** (OD-1). The four switches, visible and changeable on the
profile page.

**New API wrapper — `frontend/src/api/notification-preferences.ts`:**

- `export type NotificationPreferenceKind = "assigned" | "comment_added" | "transition_pending" |
  "suspect_flagged"` plus
  `export const NOTIFICATION_PREFERENCE_KINDS: readonly NotificationPreferenceKind[]` — the exact shape
  of `OPTIONAL_FEATURES` in `frontend/src/api/preferences.ts:41-48`.
- `notificationPreferencesApi.get(): Promise<Record<NotificationPreferenceKind, boolean>>` →
  `apiClient.get("/users/me/notification-preferences/")`, unwrapping `.preferences`.
- `notificationPreferencesApi.update(changes: Partial<Record<NotificationPreferenceKind, boolean>>):
  Promise<Record<NotificationPreferenceKind, boolean>>` → `apiClient.patch(...)` with
  `{preferences: changes}`, unwrapping `.preferences`.
- Consumed by **direct import**, not re-exported from `frontend/src/api/index.ts` — exactly how
  `memory-self-service.ts` is consumed by `MemorySection.tsx:15-18`, and that file is likewise absent
  from the barrel. Do not add a barrel entry just for symmetry.

**New component — `frontend/src/components/UserProfileSettings/NotificationsSection.tsx`** plus
**`NotificationsSection.module.css`**:

- Named export `NotificationsSection`, structurally a sibling of `MemorySection.tsx`: own CSS module
  (no inline styles — §6), `useTranslation`, one `load` callback in a `useEffect`.
- One checkbox row per kind, mapped from `NOTIFICATION_PREFERENCE_KINDS`. **The checkbox is the
  *enabled* state** (checked = the trigger is on), because the stored model is opt-out and the UI must
  not make the user invert it mentally.
- Toggle handling follows the `visibility-section` pattern in `UserProfileSettings.tsx:45-73` — the
  closest precedent, since it is the same "toggle one per-user preference" shape — rather than
  `MemorySection`'s reload-everything: hold the toggled kind in a `pendingKind` state, disable only
  *that* row's checkbox while the PATCH is in flight, apply the **server's returned map** on success,
  and on failure surface the message in a `role="alert"` element while leaving the previous state
  intact (never flip the box optimistically and then lie).
- `data-testid` on every interactive element (§6): `notification-preferences-section` on the
  `<section>`, `notification-pref-row-<kind>`, `notification-pref-checkbox-<kind>`,
  `notification-preferences-loading`, `notification-preferences-error`.
- Mount it in `UserProfileSettings.tsx` as the next stacked section after `<MemorySection />`
  (`:98`), **before** the workspace-scoped `visibility-section` block: the three preceding sections
  are user-global, the visibility block is workspace-scoped, and this one is user-global again — keep
  the user-global sections contiguous.

**Verification:** `frontend/src/components/UserProfileSettings/NotificationsSection.test.tsx`
(mirrors `MemorySection.test.tsx`, which mocks its API module):
(a) four checkboxes render and are all checked for an all-enabled response;
(b) an all-disabled response renders four unchecked boxes;
(c) clicking `notification-pref-checkbox-comment_added` calls `update({comment_added: false})` exactly
once;
(d) the server's returned map wins over the local guess — return the opposite value and assert the box
follows the response, not the click;
(e) a rejected `update` renders `role="alert"` text and leaves the checkbox in its previous state;
(f) a rejected `get` renders the same alert and no checkboxes;
(g) the section renders inside `UserProfileSettings` after `MemorySection`.
Plus the `frontend/src/components/UserProfileSettings/` suite green.

**Depends on:** Task 28 (the wire shape must match before the wrapper is written).

---

### Task 30 — i18n keys for the notification preferences

**Original goal:** none — **new scope** (OD-1). de/en labels for Task 29's section, extending Task 25's
locale test rather than starting a second one.

- Add a top-level `notificationPreferences` block to **both**
  `frontend/src/i18n/locales/de.json` and `en.json`, next to `memorySelfService` (`de.json:1380`) —
  nested keys only. Task 25's flat-dotted-key ban and its `locales.test.ts` are the enforcement; do not
  create a second test file.
- Keys required by Task 29: `title`, `hint`, `assigned`, `comment_added`, `transition_pending`,
  `suspect_flagged`, `error`, `loading`.
- Extend `frontend/src/i18n/locales.test.ts` (created by Task 25) with the same `describe.each`
  treatment for `notificationPreferences.*`, including the assertion that **both** locales carry every
  key. The four trigger labels are the ones that silently drift if the kind vocabulary in
  `notification-preferences.ts` and the locale files diverge.
- Run it **after** Task 29, so the key constants are read off the component rather than guessed — same
  reasoning as Task 25.

**Verification:** `frontend/src/i18n/locales.test.ts` green.

**Depends on:** Task 25, Task 29.

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

> **Numbering note (OD-5, §9).** The IDs in this table are **original Plan #6** numbers — that is what
> makes "one lookup" work for the dropped tasks. The re-scope's own numbering continues at **26** for
> the OD-1 preference amendment (§3, Tasks 26–30). The original plan's Task 26 (the bootstrap re-run,
> above) and the re-scope's Task 26 (`UserNotificationPreference`) are **different tasks that share a
> number**; a bare "Task 26" is ambiguous unless the section is named. Everywhere else this document
> re-uses only *adopted* IDs — this is the single overlap, and it overlaps a dropped ID, so no adopted
> task is affected. Renumbering the new tasks to 27–31 would remove the overlap but break the numbering
> the OD-1 decision was recorded with; the note is the cheaper fix.

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

### OD-1 resolved (2026-09-15) — `reporter` does not notify; delivery is user-configurable

**Only an `owner` change produces an `assigned` notification.** The recommendation stands and is now
the decision: `reporter` is provenance ("who reported this"), not an assignment. The producer takes
**one** id, not two. This is a deliberate assumption recorded in §9 (OD-1), not a derivation — it is
changeable later by extending the producer, with no schema change.

**The same decision extended the scope** (§1): notification delivery became configurable in the user's
own profile — one **user-global** opt-out preference, **four switches** (`assigned`, `comment_added`,
`transition_pending`, `suspect_flagged`), all **on** by default. Tasks 26–30.

The filter does **not** live here. It lives in one place — inside `create_notifications` (Task 10),
delegating to `NotificationPreferenceService.apply_preferences` (Task 27), which is why Task 27 runs
before Task 10 in the §8 sequence. `notify_assigned` passes a candidate list and nothing else: adding
a preference check in this producer would create a second, divergence-prone filter and would be wrong
even if it happened to work.

---

## 6. Global Constraints

Adopted from Plan #6, corrected where the tree has moved.

**Still valid verbatim:**

- `Comment` hangs on `persistence.Artifact`, never on a specialised table — that is what makes it
  work for every artifact type with no special case.
- Notification triggers are exactly four: `transition_pending`, `suspect_flagged`, `assigned`,
  `comment_added`. `transition_pending` is a **role broadcast** over the outgoing transitions'
  `allowed_roles`, never person-scoped routing. **Each of the four is switchable off per user**
  (OD-1 amendment, Tasks 26–30); the vocabulary itself stays closed at four.
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

- **Migration prefixes:** `persistence/0093`, `application/0025`, `application/0026`. **Added by the
  OD-1 amendment:** `auth_tenancy/0014` (the preference model, one migration, no RLS — it is not a
  `TenantScopedModel`, see §9 A1). (`icd/0014` is the next free icd prefix but this re-scope touches no
  icd migration.) Before each `makemigrations`, run `ls backend/<app>/migrations/ | tail -3` and use
  the next free prefix — the numbers above are the state at 2026-09-15, not a guarantee.
- **A new `TenantScopedModel` must ship its own `CREATE POLICY` migration.** The coverage guard
  (`persistence/tests/test_rls_coverage.py:147-163`) diffs the migration graph off disk against every
  concrete `TenantScopedModel` and fails the build otherwise; `:189-223` re-checks the live schema.
  `RLS_EXEMPT_TABLES` (`:51-87`) is reserved for tables with a proven tenant-context-free access path,
  and is itself asserted to list tenant-scoped tables only (`:166-183`). The preference table is
  **not** a `TenantScopedModel`, so it needs neither a policy nor an exemption entry.
- **The preference filter lives in exactly one place:** `create_notifications`
  (`application/notification_service.py`, Task 10), delegating to
  `NotificationPreferenceService.apply_preferences` (Task 27). Producers hand over a *candidate* list;
  none of them filters its own recipients.
- **Only the four trigger kinds are configurable, and only per user.** No fifth trigger, no
  per-workspace override, no e-mail/push/webhook channel, no notification history — see §1's amendment
  boundary. `Notification.KIND_CHOICES` stays the single definition of the vocabulary; the model
  (Task 26) and the UI (Task 29) both read it, neither restates it.
- **A new `rest_api/*_views.py` module is automatically ratcheted at zero direct-ORM lines** and may
  not `from persistence.models import` (`rest_api/tests/test_architecture.py:154-164`, `:205-225`).
  Task 28's module is named `*_views.py` on purpose: the glob is the guard, so the name is not
  cosmetic.
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
# makemigrations is local codegen (no DDL); the app container is fine for it.
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py makemigrations <app> --name <name>
# `migrate` applies DDL and data migrations and must NOT run through `exec backend`
# (that is the least-privilege application role). Run the one-shot `migrate`
# service, which runs as the DB owner role, together with the deploy override:
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml --project-directory . run --rm migrate python manage.py migrate
```

> **Corrected 2026-09-15 (Chunk 1 finding).** The previous
> `exec backend python manage.py migrate` line was wrong: `exec` runs the command in the
> long-lived `backend` container under the least-privilege application DB role, which cannot
> apply DDL/data migrations. Use the `run --rm migrate` form above. The same correction was
> applied to Task 8's and Task 26's verification commands.

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

Sequence: **7 → 8 → 9 → 26 → 27 → 10 → 15 → 16 → 17 → 18 → 19 → 20 → 28 → 22 → 23 → 24 → 25 → 29 → 30**

> **One inversion against the table's numeric order, and it is deliberate: 26 and 27 run *before* 10.**
> Task 10 owns `create_notifications`, and Task 27 is the preference filter that lives inside it
> (OD-1). The filter therefore has to exist before the first producer is written, so that no producer
> is ever built against — and no test ever pins — an unfiltered service. The table below stays sorted
> by number for lookup; the **"Depends on" column is authoritative** for ordering.

| # | Task | Depends on | Verification |
|---|---|---|---|
| 7 | `Comment` + `Notification` models | — | `application/tests/test_collaboration_models.py` (8) |
| 8 | RLS for `as_comment` / `as_notification` | 7 | `application/tests/test_collaboration_rls.py` (4) |
| 9 | `resolve_artifact_id_or_none()` | — | `application/tests/test_resolve_artifact_id_or_none.py` |
| 10 | `NotificationService` + `create_notifications` + `notify_assigned` | 7, **27** | `application/tests/test_notification_service.py` (8), `test_notify_assigned.py`, filter test (27) |
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
| 26 | `UserNotificationPreference` + model migration (no RLS) | — | `auth_tenancy/tests/test_notification_preference_model.py` (4), `persistence/tests/test_rls_coverage.py` green |
| 27 | `NotificationPreferenceService` + `apply_preferences` filter | 7, 26 | `application/tests/test_notification_preference_service.py` (7) |
| 28 | Self-service REST `users/me/notification-preferences/` | 27 | `rest_api/tests/test_notification_preference_views.py` (6), `test_architecture.py` green, ORM grep = 0 |
| 29 | `NotificationsSection` in the user profile | 28 | `NotificationsSection.test.tsx` (7) + `UserProfileSettings/` suite green |
| 30 | i18n keys for the preference section | 25, 29 | `frontend/src/i18n/locales.test.ts` green |

Parallelisable: 8 ∥ 9 ∥ 26 after 7; 16 ∥ 17 ∥ 18 ∥ 19 after 15/10; **28 ∥ 22** after 27/20 (28 needs
only 27, and can run alongside the whole frontend block 22–25); 23 ∥ 24 after 22.

**Per-task gate:** run the task's own test file, then the touched app's suite. Do not batch the
green check to the end of a phase.

---

## 9. Decisions

All four original Open Decisions were answered by the user on **2026-09-15**. The section keeps its
original heading and OD numbering so inbound references (`§9 OD-1`, `§5 OD-1`) still resolve.

### Resolved

**OD-1 — Does `reporter` trigger the `assigned` notification? → RESOLVED, with a scope extension.**

- **No.** The `assigned` producer fires **only** on an `owner` change. `reporter` is **provenance**
  ("who reported this"), not an assignment. The producer takes one id, not two. Recorded as a
  **deliberate assumption** rather than a derivation (§5): it follows from the field's semantics under
  Attribut v3, and it is changeable later by extending the producer — no schema change, no migration.
- **Scope extension (the reason this amendment exists):** notification delivery becomes configurable
  **in the user's own profile**.
  - **User-global** preference — one row per user across all tenants, **not** workspace-bound; it
    applies to every workspace the user belongs to.
  - **Four switches**, one per trigger: `assigned`, `comment_added`, `transition_pending`,
    `suspect_flagged`.
  - **Opt-out.** All four default to **on**; the stored value is the set of *disabled* triggers, so a
    missing row or a missing entry means "enabled". **Nothing changes for any existing user.**
  - Implemented by **Task 26** (model migration, no RLS), **27** (filter + preference service),
    **28** (self-service REST), **29** (profile UI), **30** (i18n).
  - **Where the filter sits:** inside `create_notifications`, once, for all four producers — **not**
    in the individual producers. Task 27 therefore lands **before Task 10**, the earliest producer, so
    no producer is ever written against an unfiltered service (§8).

**OD-2 — Is `Comment.author` a `User` FK or an `Actor` FK? → RESOLVED: `User` FK.**
As recommended. A comment requires a login, and the notification fan-out needs a `user_id` directly;
an `Actor` FK would force an actor→user resolution on every read projection. Task 7's code block is
unchanged. Consistency with #936's `Actor` move was weighed and rejected here: attribution answers
"who is responsible", a comment author answers "who may write this", and only the latter needs a login.

**OD-3 — Does the `comment_added` fan-out include `reporter`? → RESOLVED: yes — owner + reporter.**
The fan-out is `notify_user_ids_for_artifact(artifact)` (owner + reporter, internal actors only) with
`exclude_user_id=ctx.user_id`, so **the author never receives their own comment notification**. This is
Task 15 exactly as already written; the decision confirms it rather than changing it.
It is deliberately **not** symmetric with OD-1: `reporter` receives a comment notification even though
it does not receive an assignment notification, because a comment is follow-up traffic on something
the reporter raised.

**OD-4 — Should a suspect-flag notification go to an external owner? → RESOLVED: no.**
`Actor.kind == "external"` rows have no login and no feed, so `notify_user_ids_for_artifact` (Task 15)
drops them and `notify_suspect_flagged` (Task 19) notifies nobody for an externally-owned artifact.
Consequence, accepted for v1: the flag stays visible only in the artifact's own suspect state. Revisit
if it turns out to hide real work. No new work.

### Assumptions (recorded, not open)

**A1 — "User-global" means one row per user, across all tenants (resolved 2026-09-15).** The user
explicitly chose a user-global preference applying to all workspaces. `User` is itself an
`AuditableModel` without tenant scoping (`persistence/models.py:463`), so
`UserNotificationPreference(AuditableModel)` with a `OneToOneField(user)` is the faithful model: no
`tenant` field, **no RLS policy**, and **not** in `RLS_EXEMPT_TABLES` (that allowlist is asserted to
contain tenant-scoped tables only, `:166-183`). Access is always "the current user's own row" (Task 28),
which is what keeps a non-RLS table safe here. An earlier draft made it per-`(tenant, user)`; that was
rejected as contradicting the "all workspaces" requirement.

**A2 — A JSON list of disabled triggers, not four boolean columns.** It mirrors the
`optional_artifact_visibility` JSONField one class above, stores only the deviations, and needs no
migration if a fifth trigger kind is ever added. The cost, stated plainly: the trigger vocabulary is
enforced in the serializer (Task 28) against `Notification.KIND_CHOICES`, **not** by the database.
Four boolean columns would be typed but would restate the trigger list in the schema — the thing §6
forbids.

**A3 — The filter fails open.** If the preference lookup fails, `create_notifications` proceeds
unfiltered rather than dropping recipients (Task 27). The four producers all carry an explicit "never
raise — a notification must not break the mutation it reacts to" contract; failing *closed* here would
additionally stop delivery for every user the moment the preference table is unreachable, which is a
worse failure than an un-muted notification.

### Open (found while resolving the above)

**OD-5 — Task-ID `26` is reused.** The original plan's Task 26 ("re-run the bootstrap so
`owner`/`assignee` become core attributes") is a *dropped* task listed in §4; this amendment numbers
its first new task `26` as well. §4's IDs are original-Plan-#6 numbers, §3's 26–30 are re-scope
numbers, and the overlap is on a **dropped** ID — no adopted task is affected, and there is no
implementation impact either way. A disambiguating note sits under §4. Renumbering the new tasks to
27–31 would remove the overlap; it was not done because the OD-1 decision is recorded with the numbers
26–30. **Confirm the numbering is acceptable, or renumber — this is the only open item from the
amendment.**

None of this blocks a task: A1 needs a yes/no before Task 26 (its fallback is stated inline), OD-5 is
editorial, and the 26–30 chain can start as soon as Task 7 has defined the `KIND_*` vocabulary.

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

Dropped owners half: Tasks 1–6, 12, 13, 14, 21, 26 — see §4 (those are **original-Plan-#6** numbers;
see the numbering note under §4 for the one overlap with the amendment's Task 26).

The OD-1 amendment's **Tasks 26–30 have no counterpart in the original plan** — they are new scope,
not a re-scope of existing tasks, so they are absent from the table above by construction.

### Not covered, on purpose

- `MainGoal` / `Diagram` attribution — was already out of scope in the original plan (its Task 3
  decision) and is untouched by this re-scope.
- The physical drop of `Risk.owner_name` / `Issue.assignee_id` — AWMS-owned contract step.
- Any owner/assignment edit UI — the attribute-definition renderer already ships `owner`/`reporter`.
- E-mail/webhook/digest delivery of notifications, per-workspace preferences, and notification
  history — the stated boundary of the OD-1 extension (§1).

### Placeholder scan

No `TBD`, no `TODO`, no "similar to Task N". Four items defer to a grep or a decision, each with an
exact command or an explicit decision/assumption ID and a stated fallback:

- Task 17 — registry line number is located by `grep -n "register_groups"`, because the original
  plan's line reference predates the current tree.
- Task 18 — the "only non-test caller" claim must be re-verified by grep, with the fallback named.
- Task 26 — the migration prefix is re-checked with `ls backend/auth_tenancy/migrations/ | tail -2`
  even though `0014` was read off the tree on 2026-09-15.
- §9 — OD-1…OD-4 are **resolved**; A1–A3 are recorded assumptions with inline fallbacks; OD-5 is the
  one remaining open (editorial) item, and it names the alternative numbering explicitly.

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

**Added by the OD-1 amendment:**

- `NotificationPreferenceService.apply_preferences(ctx, user_ids, kind)` is defined once (Task 27) and
  called once (inside `create_notifications`, Task 10) — the four producers never call it directly, so
  there is exactly one call site to keep correct.
- `Notification.KIND_CHOICES` (Task 7) is the single source of the trigger vocabulary: `ALL_KINDS`
  (Task 27) derives from it, Task 26's model stores only keys from it, and Task 28's serializer
  validates against it. No second literal four-item list appears anywhere in the chain.
- `NotificationPreferenceService` (Task 27) is the only thing that touches
  `UserNotificationPreference`, and Task 28's view module has zero direct-ORM lines — the ratchet
  (`rest_api/tests/test_architecture.py`) enforces this rather than a convention.
- `NotificationPreferenceKind` (Task 29, TS union) and the four keys of the effective map returned by
  Task 28's GET/PATCH are the same four strings; Task 30's locale test is what catches drift between
  them and `de.json` / `en.json`.
- Task 27's `ctx` parameter type is `AuthContext` (`auth_tenancy.context`), the same type every other
  Layer-2 service takes — not a bespoke context object.
