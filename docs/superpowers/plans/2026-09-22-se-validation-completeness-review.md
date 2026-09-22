---
type: REVIEW
scope: cluster-5-se-validation-completeness
status: closed
date: 2026-09-22
author_agent: concept-reviewer
reviewer: concept-reviewer
reviewed_artifact: docs/superpowers/plans/2026-09-22-se-validation-completeness-spec.md
issues: [424, 402, 399, 272]
branch: feat/se-validation-completeness
verdict: CHANGES_REQUESTED
findings:
  critical: 0
  major: 4
  minor: 10
  info: 3
---

# Review — Cluster 5 Spec (SE-Validation Completeness)

## Scope

Read-only review of `docs/superpowers/plans/2026-09-22-se-validation-completeness-spec.md`
(#424, #402, #399, #272). All spec self-claims were verified against the actual code on
`feat/se-validation-completeness`; the four source issues were read from GitHub
(`Popoboxxo/ReqogniLoom`). No file of the spec or of the codebase was modified.

Verified-and-correct (no finding) baseline of facts:

- `CoverageCalculator.coverage()` / `get_coverage_data()` both funnel TestCase-sourced
  `verifies` links through `_filter_to_testcase_ids`; `check_verification_evidence`
  (`workflow/precondition_rules.py:377`) funnels through
  `_exclude_outdated_testcase_ids` → `_filter_to_testcase_ids`. A new
  `include_unreviewed_ai: bool = False` parameter therefore closes **both** paths by
  default.
- `BaselineDeltaIndexEntry` (plain model, no tenant column) carries a nullable `state`;
  `BaselineStore.load_states` / `load_delta_index` do a tenant-filtered
  `BaselineSnapshot.unscoped` pre-check. `item_id` **is** the Artifact UUID
  (`delta_index_builder._resolve_project` reads `pl_artifact.id`), and the stored state
  comes from the same `baseline.state_capture.capture_states` field set — so the spec's
  drift comparison is comparable in principle.
- `satisfies` is `allowed_pairs=[Requirement→Goal]`, `coverage_relevant=True`
  (`link_types/builtin.py:165`); `validate_link_pair(workspace_id, link_type,
  source_type, target_type, *, manual)` matches the AC-402-6 call.
- `_EXTENDED_ONLY_RULES` feeds `FULL_SE_RULE_IDS` and `RULE_PRESET_MAP["extended"]`
  (`traceability/audit/registry.py:89-117`).
- `_EXTENDED.mandatory_fields` really lacks `verification_method`
  (`presets/registry.py:188`), and `scoped_mandatory_fields` folds the legacy preset
  list into the definition-scoped result **for Requirement** — so §7.2 does reach
  `check_mandatory_fields`.
- `TestRunResult.status ∈ {passed, failed, blocked, not_run}` (`models.py:2100`);
  `ChangeRequest.baseline` FK (`:3408`); `ChangeRequestAffectedItem` (`:3444`);
  `set_affected_items` (`change_request_service.py:769`); `allocation-coverage` only at
  `rest_api/views.py:1889`; `_check_link_pair` (`trace_link_service.py:273`) checks
  existence + pair but not soft-delete; `creation_baseline_entry()` returns
  `content_available: False` (`artifact_diff_service.py:221`).
- Migration numbering: latest `persistence` = `0098`, latest `link_types` = `0008`, so
  `0099` / `0100` / `0009` are correct. No new tables, no new RLS policy needed.
- `#399` genuinely accepts the chosen option: *"…nur über einen genehmigten
  ChangeRequest, mindestens aber mit deutlicher Drift-Kennzeichnung am Artefakt"*.
- `#402` asks for exactly what the spec builds ("jedes L0-Need trägt zu mindestens einem
  Goal bei", off-nominal "für TestCases").
- `#569` is explicitly out of scope (§1.2, §10) and no `finding_key` work is introduced.

---

## Findings — major

### M1 — The false-green path is only ⅔ closed: VERIF-P8 still counts unreviewed AI TestCases
- **Severity:** major
- **Category:** Completeness / logic gap (#424)
- **Description:** The spec closes `CoverageCalculator` and
  `check_verification_evidence`, but a third consumer of "TestCase = verification
  evidence" is untouched:
  `traceability/audit/rules/coverage_consistency.py::LeafRequirementHasTestCaseRule`
  (VERIF-P8). It computes `verified_requirement_ids` from **every** active TestCase with
  a `verifies` link (`_active_test_cases` filters only `outdated`, lines 282-289) and
  emits no finding. VERIF-P8 is a **BLOCKER at Extended** and feeds
  `BaselineFacade._enforce_audit_gate` → an unreviewed AI TestCase still makes a leaf
  Requirement look verified for the SE-Auditor and the baseline gate. That is the same
  false-green class #424 exists to remove.
- **Suggested fix:** apply the same `origin == "ai_generated" and not reviewed`
  exclusion in the audit path (e.g. a shared
  `CoverageCalculator._filter_to_testcase_ids(..., include_unreviewed_ai=False)` reuse or
  an `_active_reviewed_test_cases` helper), add an AC
  ("unreviewed AI TC as only verifies evidence → VERIF-P8 finding at Extended") and a
  mutation probe. Alternatively state explicitly, with rationale, why the audit layer is
  deliberately excluded — but do not leave it implicit.

### M2 — `#424` backfill premise is contradicted by the issue and grandfathers the false-green
- **Severity:** major
- **Category:** Unchecked assumption / risk (#424 backfill)
- **Description:** §4.2 justifies `reviewed=True` for **all** existing `pl_testcase` rows
  with *"Diese Zeilen stammen ausnahmslos aus dem manuellen oder (ab jetzt) unmarkierten
  Pfad"*. That premise is false: the issue's own reproduction shows AI/mock test cases
  were persisted through the derive path **unflagged**, precisely because no origin/review
  status existed. Because the same migration also defaults `origin="manual"`, every
  historical AI TestCase becomes `origin=manual, reviewed=True` — indistinguishable and
  counting as full coverage. The false-green that #424 reports is thereby preserved for
  the entire existing dataset, and the change is irreversible (the spec itself notes there
  is no marker of prior state).
- **Suggested fix:** either (a) keep the backfill but present it as an **explicitly
  accepted grandfathering decision** (KPI stability) with a follow-up issue to detect
  historical AI rows from the existing audit trail (`test.derive_from_requirement` /
  MCP derive entries) and re-mark them, or (b) mark existing rows from that audit trail
  where detectable. At minimum delete the "ausnahmslos manuell" claim, which is
  unverifiable and wrong as written.

### M3 — M1/M2 data migrations are not RLS-safe; they can silently update zero rows
- **Severity:** major
- **Category:** Feasibility / reversibility (migrations)
- **Description:** `pl_testcase` and `pl_workspace` are both in the
  `ENABLE + FORCE ROW LEVEL SECURITY` set keyed on `app.current_tenant`
  (`persistence/migrations/0003_rls_policies.py:46-58`). The spec's M1 backfill
  (`TestCase.objects.filter(...).update(reviewed=True)`) and M2 backfill
  (`Workspace.objects.filter(is_active=True, goals_enabled=False).update(...)`) neither
  arm the tenant GUC nor use `SET LOCAL row_security = off`. Under any non-BYPASSRLS
  migration role they update **zero** rows and report success — the exact trap
  `0073_backfill_artifact_backing.py:35-52` documents ("cost a previous backfill (#103) a
  debugging session") and that `link_types/0005`/`0008` solve by arming the tenant per
  tenant. Note the spec's **own** M3 prescribes that safe pattern, so M1/M2 are internally
  inconsistent with it. The default compose `migrate` service connects as the cluster
  superuser (`deploy/docker-compose.yml:342` vs. the app role at `:259`), so this is
  environment-dependent — but relying on it is exactly what the repo's guard rails exist
  to prevent (e.g. `docker compose exec backend python manage.py migrate` with
  `DB_USER` defaulting to `reqogniloom_app`, `settings.py:336`).
- **Suggested fix:** for each backfill, arm `app.current_tenant` per tenant (the
  `link_types/0005` pattern) or `SET LOCAL row_security = off` plus a
  `rows_updated == expected` assertion that fails the migration loudly. Spell the chosen
  mechanism out in §8 rather than leaving "über den … Manager der Migration".

### M4 — VAL-P1 fires retroactively as a baseline blocker for existing goal-using workspaces
- **Severity:** major
- **Category:** Risks / consistency (#402 rollout)
- **Description:** §5.4 correctly notes VAL-P1 is a BLOCKER at Extended and flows into
  `_enforce_audit_gate`. The double gate only protects the *0-goal* case. Per #402's own
  estate figures (4 Goals / 2 MainGoals exist), there **are** Extended workspaces with
  `goals_enabled=True` and ≥1 goal; for those, every active StakeholderNeed without a
  `satisfies`→Goal link becomes an immediate BLOCKER on the next baseline build, with no
  grace period, no opt-in and no data path except per-finding waivers that require
  Admin/Approver authority. The spec's claim "Damit wird ein Extended-Workspace mit 2735
  Requirements und 0 Goals nicht rückwirkend zum Baseline-Blocker" is true but narrow, and
  it is presented as if it settled the retroactive question.
- **Suggested fix:** pick one and document it: ship VAL-P1 as `WARNING` for one release
  (severity escalation later), gate it behind an explicit per-workspace opt-in / feature
  key, or ship a bulk `satisfies`-link remediation (or seed) so the first post-upgrade
  baseline is not blocked by dozens of findings. Add a release note.

---

## Findings — minor

### m1 — `reviewed` PATCH is silently ignored, not rejected
- **Category:** Logic gap (#424)
- **Description:** §4.4 claims a PATCH of the read-only `reviewed` field is rejected by
  `UnknownFieldRejectionMixin`. That mixin's own docstring
  (`rest_api/serializers.py:679-680`) states every **declared** field — "required,
  optional, write-only and read-only alike" — is accepted; DRF then drops it. So
  `PATCH {"reviewed": true}` returns 200 with no change: the #851 silent-no-op class.
- **Suggested fix:** add an explicit `validate()` rejection for `reviewed` on update
  (mirroring the `origin` immutability guard) or document the silent ignore deliberately
  and add an AC pinning the actual behaviour.

### m2 — Test-breakage list for the `goals_enabled` flip is incomplete and partly wrong
- **Category:** Consistency (#402)
- **Description:** `rest_api/tests/test_workspace_create_schema_conformance.py:121`
  asserts `body["goals_enabled"] is False` on a default create — it **will** break and is
  **not** listed. Conversely `rest_api/tests/test_goal_views.py:90` **is** listed but
  passes `goals_enabled=False` explicitly, so it will not break. (Verified breakers:
  `persistence/tests/test_workspace_goals_fields.py:17`,
  `application/tests/test_goal_service.py:102-114`,
  `application/tests/test_main_goal_service.py:113-123`,
  `rest_api/tests/test_workspace_goals_rest.py`.)
- **Suggested fix:** correct the list so the implementer does not chase a phantom break
  and does not get surprised by an unlisted one.

### m3 — `link_types/0009`: filter, dependency and reverse deviate from the cited pattern
- **Category:** Completeness / reversibility (migration)
- **Description:** The spec says M3 follows `0005`/`0006` exactly, but (a) the operational
  bullet omits the `is_customized=False` filter for `lt_workspace_definition` rows, which
  `0005` applies; (b) no `dependencies` entry is given — it must at minimum depend on
  `("link_types", "0008_seed_satisfaction_link_types")`, which is what created the
  `satisfies` rows being mutated; (c) the reverse is specified as "remove the pair again"
  whereas `0005` uses `migrations.RunPython.noop`. Removing the pair on reverse can delete
  a tenant's own deliberately added customization and leaves any existing
  StakeholderNeed→Goal links attached to a pair the catalog no longer allows.
- **Suggested fix:** mirror `0005` literally — `is_customized=False` on workspace rows,
  explicit dependency on `0008`, `RunPython.noop` reverse (or a reverse that removes only
  rows the forward actually changed and never customized ones).

### m4 — `#399` membership search misses global-scope baselines
- **Category:** Logic gap (#399)
- **Description:** §6.2 step 1 restricts candidate baselines to
  `BaselineSnapshot.workspace_id = <artifact's workspace>`. A `scope="global"` baseline
  created from workspace A contains artifacts of workspace B but stores
  `workspace_id=A` (`BaselineMetadata.workspace_id` is the caller's workspace,
  `_resolve_global` walks the whole tenant). For an artifact in B the membership query
  therefore never sees that baseline, so the drift marking silently omits a real
  membership.
- **Suggested fix:** for `scope="global"` candidates filter by tenant only (and/or
  resolve membership through the delta index across the tenant); add an AC with a
  cross-workspace global baseline.

### m5 — `_assert_endpoints_live` relies on an unspecified entity-id resolution
- **Category:** Completeness (#272, §7.3)
- **Description:** The helper is described as using
  `outdated_item_ids(item_type, tenant_id=...)` "gegen die zum Artifact gehörende
  Entity-ID (`_resolve_entity_id_for_artifact`-artige Auflösung)". No such helper exists
  in the codebase, and `outdated_item_ids` returns **entity** ids while the delta index /
  CR tables key on **Artifact** ids. `_check_link_pair` has already loaded both `Artifact`
  rows, whose `lifecycle_status` is the single soft-delete flag ("outdated", per
  `workflow.services.outdated_item_ids` and the service tests) — a direct, universal check
  with no mapping needed.
- **Suggested fix:** specify the direct `Artifact.lifecycle_status == "outdated"` check
  (fail-open only for genuinely unsupported types), or name and define the helper.

### m6 — Flipping v0 `content_available` to `True` contradicts the field's meaning
- **Category:** Logic gap (#272, §7.4.2)
- **Description:** `creation_baseline_entry()` documents v0 as "the empty 'before
  creation' state: diffing *against* it is supported, but there is no stored content to
  display", and `ArtifactVersionService.get_payload` returns `None` for v0. Setting
  `content_available: True` tells consumers "there is retrievable content behind this
  number" while there is none — a consumer that gates an "open content" action on the flag
  regresses. The spec's argument ("his content is known (`{}`)") conflates "defined empty
  state" with "stored content".
- **Suggested fix:** keep `False`, or split the semantics explicitly (e.g. an additional
  `is_creation_baseline: true` flag) and state the consumer contract the issue actually
  needs ("Ersteinrichtung nicht rekonstruierbar").

### m7 — `_ENTITY_FIELDS` rationale is inverted; one-time diff side effect undocumented
- **Category:** Logic gap (#424, §4.3)
- **Description:** The spec says that *without* extending `_ENTITY_FIELDS["TestCase"]`
  "jeder Diff diese Felder als 'changed to empty'" renders. The opposite is true: fields
  absent from `_ENTITY_FIELDS` are not snapshotted by `snapshot_fields` and therefore not
  diffed at all. The "changed/added to empty" risk arises *after* adding them — for a
  writer that never fills them, or when comparing against a pre-upgrade revision. The spec
  does not mention that the first diff of every pre-existing TestCase will show
  `origin`/`reviewed`/`scenario_kind` as added/changed, although the sibling Icd entry
  documents exactly this one-time consequence
  (`artifact_diff_service.py:170-175`).
- **Suggested fix:** correct the rationale and add the one-time-diff note.

### m8 — Wrong path for the shared row component; per-row membership lookup unaddressed
- **Category:** Completeness / feasibility (frontend)
- **Description:** `frontend/src/components/shared/ArtifactRow.tsx` does not exist; the
  component is `frontend/src/components/shared/ArtifactRow/ArtifactRow.tsx` (own
  `.module.css` + test). It is shared by all artifact lists, so putting the
  baseline-drift badge there (§6.4) implies a `baselineMembership(id)` call per rendered
  row — an N+1 API pattern the spec does not address.
- **Suggested fix:** correct the path and either specify a batched membership endpoint /
  row-level payload or restrict the drift badge to the editor header (the spec's own
  alternative).

### m9 — Wrong module for `policy_fields_without_consumer`
- **Category:** Consistency (§7.2)
- **Description:** §7.2 places `policy_fields_without_consumer (:615)` in
  `backend/presets/registry.py`. It lives in
  `backend/workflow/precondition_rules.py:615` (`presets/registry.py` is 427 lines).
  The substantive claim (column branch consumes `verification_method`) is correct.
- **Suggested fix:** fix the citation.

### m10 — VAL-P1 activation gate as written is not fail-open as intended
- **Category:** Logic gap (#402, §5.3)
- **Description:** §5.3 gate 1 is
  `Workspace.objects.filter(id=context.workspace_id, goals_enabled=False).exists()` with
  the stated intent "Kein Workspace-Kontext auflösbar → `return []`, fail-open wie die
  Schwestern-Regeln". With the tenant-scoped manager and an unresolvable context,
  `exists()` is `False`, so the rule does **not** return early and proceeds — the opposite
  of the stated intent. The audit convention elsewhere is explicit
  `unscoped.filter(tenant_id=context.tenant_id, ...)`.
- **Suggested fix:** `Workspace.unscoped.filter(id=context.workspace_id,
  tenant_id=context.tenant_id, goals_enabled=True).exists()` → else `return []`.

### m11 — Acceptance criteria gaps and one AC that does not test its contract
- **Category:** Testability (#424/#402/#399/#272)
- **Description:** ACs are largely concrete and behavioural (good), and the frontend
  obligations (`data-testid` per new element, i18n keys, tokens-only rule, ratchet
  baselines) are explicitly present. Missing/weak: no AC for the MCP `test.mark_reviewed`
  tool; no AC for `pending_ai_review` on the coverage-report endpoint (AC-402-8 covers only
  `scenario_kind`); no AC for the drift badge or the `raise-cr-from-drift` shortcut, whose
  CR-prefill contract (which endpoint/fields for `affected_item`) is unspecified; the
  TestCase-detail review button has no target file named; and **AC-424-1** posts
  `reviewed: false`, which the serializer declares read-only and therefore ignores — the
  AC passes via the service-side derivation, not via the contract it claims to test.
- **Suggested fix:** add the missing ACs, name the CR-prefill endpoint/fields, and rewrite
  AC-424-1 so it actually exercises the client-visible contract (or drop the ignored
  `reviewed` from the payload).

---

## Findings — info

### i1 — `executed_by` is a REST proxy, not a column (#272 point 4)
`TestRunResult` has `executed_at` but no `executed_by`; the REST response derives it from
the run's creator (`rest_api/views.py:4199-4222`). The spec's "ERFÜLLT" is therefore true
at the published API-contract level only, which is what #272 asked for — worth stating.

### i2 — Two unreconciled "review" concepts on TestCase
The new `reviewed` boolean is independent of the existing TestCase workflow state
(`draft→ready→approved→deprecated`) and of Rule 7 (`check_verifies_link`, which gates
`approved`). A TestCase can be workflow-approved while `reviewed=False`, or `reviewed=True`
without ever being workflow-approved. The spec should state the intended relationship so
UI and audit do not present two competing review gates.

### i3 — #569 scope isolation is clean
`#569` (`findings` / `finding_key` waiver) is excluded in §1.2 and §10; VAL-P1 findings
ride the already-shipped `BaselineGateWaiver` / `baseline.waivers.finding_key` without new
identity work. No scope leak found.

---

## Verdict

**CHANGES_REQUESTED** — no critical/unsolvable defect, but four major findings must be
resolved before implementation: the third false-green consumer (VERIF-P8), the
indefensible `reviewed=True` backfill premise, the RLS-unsafe M1/M2 data migrations, and
the retroactive VAL-P1 baseline blocker for existing goal-using workspaces.

## Explicit answers to the eight review questions

1. **#424 false-green — are both call sites closed?** Yes in substance, no in precision.
   `CoverageCalculator` is covered on both entry points (`coverage()` via
   `_get_covered_artifact_ids`, `get_coverage_data`). `check_verification_evidence` is
   covered by the fail-safe default of the new parameter — but the spec names
   `_filter_to_testcase_ids` as the implementation point while the actual call site is the
   wrapper `_exclude_outdated_testcase_ids`, which must be made explicit. A **third**
   consumer (VERIF-P8) is not closed at all → **M1**.
2. **#424 backfill defensible?** No, as written. The "ausnahmslos manuell" premise is
   contradicted by the issue's own reproduction; the backfill preserves the false-green
   for all existing data and is irreversible → **M2**.
3. **#402 default flip.** The data migration is specified but its RLS mechanism is
   under-specified (silent no-op risk) → **M3**, and the reverse is a substantive no-op,
   i.e. the change is a one-way door (documented, but not reversible). VAL-P1 is
   double-gated, but only the 0-goal retroactive case is prevented; existing goal-using
   Extended workspaces **will** get retroactive blockers → **M4**. Off-nominal is
   represented concretely (model field + choices + default, serializer, MCP schema, UI
   select/badge, coverage-report field, ACs) and TestCase-only, which matches #402's
   "Erwartung".
4. **#399.** Yes — the issue text explicitly accepts "mindestens aber mit deutlicher
   Drift-Kennzeichnung am Artefakt", so D1 is defensible. The drift comparison against
   `BaselineDeltaIndexEntry.state` is correctly defined (`item_id` = Artifact UUID; same
   `capture_states` field set; tenant-checked `load_states`). Gaps: the workspace filter
   misses global-scope baselines (**m4**), and `capture_states` depends on an active
   `TenantContext` for statuses, which the retrieve path must set (not stated). Tenant
   isolation of `memberships_for_artifact()` **is** specified (unscoped + explicit tenant
   + store re-verification).
5. **#272 table.** The "already satisfied" rows are correct as far as checked (AC gate via
   `check_mandatory_fields` — tier-aware, approval-gated, legacy list folded in for
   Requirement; link compat via `catalog.validate_link_pair`; `TestRunResult` enum;
   `ChangeRequest.baseline` + `ChangeRequestAffectedItem` + `set_affected_items`), and the
   claimed remaining gaps are real. Two caveats: "point 4 ERFÜLLT" holds only because
   `executed_by` is a REST proxy (**i1**), and the `content_available` v0 "fix" is
   semantically wrong (**m6**). `Closes #272` gating in §7.6 (all four issues in the PR)
   is correct.
6. **Migrations.** Exactly three, numbering verified correct. Dependencies are not spelled
   out (`0009` must depend on `0008`; `0099`/`0100` on `0098`) → **m3**. Reversibility:
   M1/M2 reverses are documented no-ops (one-way in substance); M3's reverse deviates from
   the cited `0005` pattern and can destroy tenant customizations → **m3**. M3's forward is
   idempotent and tenant-scoped **only if** the `is_customized=False` filter from `0005`
   is applied (the operational bullet omits it) → **m3**. M1/M2 are not RLS-safe → **M3**.
7. **AC testability / frontend obligations.** ACs are concrete and behavioural overall;
   the frontend obligations (data-testid, i18n keys, tokens.css-only, ratchet baselines)
   are present and explicit. Gaps and one self-defeating AC → **m11**; wrong component path
   and unaddressed per-row lookup → **m8**.
8. **#569.** Explicitly out of scope in §1.2 and §10; no `finding_key` scope pulled in
   (**i3**).
