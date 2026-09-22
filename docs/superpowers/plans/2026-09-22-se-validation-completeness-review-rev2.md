---
type: REVIEW
scope: cluster-5-se-validation-completeness
status: open
date: 2026-09-22
author_agent: concept-reviewer
reviewer: concept-reviewer
reviewed_artifact: docs/superpowers/plans/2026-09-22-se-validation-completeness-spec.md
revision_reviewed: 2
supersedes_review: docs/superpowers/plans/2026-09-22-se-validation-completeness-review.md
issues: [424, 402, 399, 272]
branch: feat/se-validation-completeness
verdict: CHANGES_REQUESTED
findings:
  critical: 0
  major: 3
  minor: 4
  info: 1
---

# Re-Review — Cluster 5 Spec, Revision 2 (SE-Validation Completeness)

## Scope

Read-only re-review of `docs/superpowers/plans/2026-09-22-se-validation-completeness-spec.md`
(revision 2, §13 = resolution register) against the actual code on
`feat/se-validation-completeness`. No spec or code file was modified.

Every self-claim of §13 was re-verified against the tree; the four prior majors
(M1–M4) and a spot-check of m1/m4/m6/m8/m11 are reported below with `file:line`
evidence. Three findings from the prior review are genuinely resolved; **M4 is not**,
and the revision introduces two new major issues plus four minor ones.

---

## Per-major-finding status (prior review)

### M1 — VERIF-P8 false-green (third consumer) → **RESOLVED**

- The plan (§4.5(3)) introduces `_active_verifying_test_cases` in
  `traceability/audit/rules/coverage_consistency.py` and switches
  `LeafRequirementHasTestCaseRule.check` to it. The existing third consumer is
  real and correctly identified: `VERIF-P8` computes `verified_requirement_ids`
  from **every** active TestCase (`coverage_consistency.py:282-289`), and the
  helper it replaces filters only on `outdated` (`:156-195`). The shared
  predicate `counts_as_verification_evidence` is a single module-level function
  both the calculator and the rule will call — no duplication of the rule logic.
- **TRACE-P6 exemption is justified.** `TestCaseVerifiesExistingArtifactRule`
  keeps `_active_test_cases` (`:223`) because it asks "does this TestCase point
  at an existing artifact?", independent of review status; the revision states
  this as an explicit rationale and keeps a comment at the helper. A review
  filter there would silently disable TRACE-P6 for unreviewed AI TestCases
  (rule gap, not rule effect). Sound.
- **Mutation probe is valid.** AC-424-10 removes the predicate from
  `_active_verifying_test_cases`; since that helper is the only source of the
  exclusion for VERIF-P8, AC-424-9 (expects a `VERIF-P8` finding) must turn red.
  The probe targets the new consumer exactly as §9 claims.

### M2 — `#424` backfill premise → **RESOLVED**

- No `reviewed=True` backfill remains. `0099` is schema-only: three `AddField`
  + one `AlterField`, no `RunPython` (§4.2, §8 row 1). Existing rows receive
  `origin="unknown"`, `reviewed=False`, `scenario_kind="nominal"` via the DDL
  column default. On PostgreSQL `AddField` with `preserve_default=False` is
  `ALTER TABLE … ADD COLUMN … DEFAULT …` (metadata-only, no DML), and DDL is not
  subject to row-level policies — the claim "no silent zero-row no-op" holds.
- The "ausnahmslos manuell" claim is deleted; D4 documents the grandfathering
  and the residual uncertainty is scoped to F7. AC-424-7 pins the new semantics.
- `origin` is consistently 3-valued: model `TextChoices` includes `unknown`
  (§4.1), the serializer restricts clients to `{manual, ai_generated}` (§4.4),
  and the service default is `MANUAL` (§4.3). No downstream consumer found that
  assumes a 2-valued field. (One tightening gap: see **N7**.)

### M3 — RLS-unsafe migrations → **RESOLVED**

- **`0099` schema-only** — confirmed immune (above).
- **`0100`** arms per tenant (`SET app.current_tenant`), counts `expected`,
  updates, asserts `updated == expected`, and `finally: RESET` (§5.1, §8 row 2).
  This mirrors the proven `link_types/0005` pattern (`0005_backfill_goal_reference_pairs.py:35-44,81-100`)
  and the loud-failure philosophy of `0073_backfill_artifact_backing.py:35-52`.
  `pl_workspace` is in the `FORCE ROW LEVEL SECURITY` set
  (`persistence/migrations/0003_rls_policies.py:46-58`). `Tenant` is deliberately
  outside it, so tenant enumeration is safe.
- **`link_types/0009`** is tenant-armed, filters `is_customized=False`, depends
  on `0008_seed_satisfaction_link_types`, and uses `RunPython.noop` reverse —
  exactly the `0005` shape (§5.2, §8 row 3). `0008` is indeed what created the
  `satisfies` rows (`link_types/migrations/0008_seed_satisfaction_link_types.py:26`).
- One precision gap: the spec must use the **historical** models
  (`apps.get_model`) in the `0100` `RunPython`, not the live `Workspace.objects`.
  The live default manager is tenant-scoped via the thread-local
  (`persistence/tenancy.py:135-143`), which no migration sets, so it would raise
  `TenantContextNotSetError` instead of arming. See **N6** (minor).

### M4 — VAL-P1 retroactive blocker → **NOT_RESOLVED** (see major finding N1)

The revision states VAL-P1 emits `Severity.WARNING` and that
`blocking_findings` filters on BLOCKER (§5.3/§5.4, §13-M4). Both premises are
correct in isolation, but the **rule engine re-stamps every finding with
`rule.severity_for_tier(tier)`**, so the finding-level severity is not the
effective one. See N1.

---

## Findings — major

### N1 (was M4) — VAL-P1 will still gate baselines: the severity override is missing
- **Severity:** major
- **Category:** Logic gap / consistency (#402)
- **Description:** `RuleEngine._run_rule` ignores the severity a rule sets on its
  `Finding` and re-stamps it from `rule.severity_for_tier(tier)`
  (`traceability/audit/rule_engine.py:137-154`); the base implementation returns
  `Severity.BLOCKER` (`traceability/audit/registry.py:233-240`). Every WARNING
  rule in the codebase therefore overrides that method
  (`traceability/audit/rules/level_progression.py:138-140` for CONS-P11,
  `traceability/audit/rules/trace_derivation_allocation.py:403-404` for TRACE-P2).
  The spec's VAL-P1 sketch sets `severity=Severity.WARNING` on the `Finding` only
  (§5.3 point 4) and never specifies a `severity_for_tier` override. As written,
  VAL-P1 findings are re-stamped **BLOCKER**, `AuditService.blocking_findings`
  (`application/audit_service.py:296`) returns them, and
  `BaselineFacade._enforce_audit_gate` (`application/baseline_facade.py:440`)
  blocks the baseline build — i.e. the exact retroactive blocker the revision
  claims to have removed. AC-402-9 would fail against the design as specified.
- **Suggested fix:** declare `severity_for_tier(self, tier) -> Severity` returning
  `Severity.WARNING` on `ValidationGoalsRule` (mirroring CONS-P11), and state in
  §5.3/§5.4 that this override — not the `Finding` value — is the effective
  severity. Add the override to the mutation probe in §9 (set it to BLOCKER →
  AC-402-9 must go red).

### N2 — `memberships_for_artifact` clears a TenantContext it may not own
- **Severity:** major
- **Category:** Logic gap / regression (#399)
- **Description:** §6.2 step 1 prescribes `set_request_tenant(ctx.tenant_id)` …
  `finally: clear_request_tenant()`. `clear_request_tenant()` unconditionally
  clears the thread-local context **and** `RESET`s the RLS GUC
  (`persistence/middleware.py:69-73`). But `memberships_for_artifact` is called
  from inside request-scoped service methods (`RequirementService.update_requirement`,
  `TestService.update_test_case`, the `retrieve` paths — §6.2/§6.3), where the
  middleware already owns the context. Clearing it mid-request removes the
  context for everything that follows: the spec's own edit integration calls
  `self._audit(...)` **after** the membership lookup (§6.2), and `_audit`
  (`application/base.py:159-218`) writes tenant-scoped rows that need an active
  context. The result is a `TenantContextNotSetError`/500 on the normal update
  path — and the fail-open wrapper around the drift call does not cover the
  subsequent audit write. AC-D1-10 only tests the "no context present" case and
  misses the (dominant) "context already present" case.
- **Suggested fix:** save/restore instead of blind clear — remember
  `TenantContext.is_set()`/`get_tenant()` before arming and only
  `clear_request_tenant()` when this call armed it; otherwise leave the caller's
  context untouched. Add an AC for the nested case ("context already armed →
  unchanged after the call").

### N3 — Second LLM TestCase producer is not marked; the false-green survives there
- **Severity:** major
- **Category:** Completeness / logic gap (#424)
- **Description:** The revision closes the *consumer* side comprehensively and
  patches one producer — the MCP derive path
  (`mcp_server/tools/tests.py:1114` → `create_test_case(..., origin="ai_generated")`).
  A second LLM-driven TestCase producer exists and is untouched: the interview
  formalize flow is LLM-backed (`application/interview_multi_protocol.py:6`
  "LLM emits a fenced ```json block …", and `:41` lists TestCase among the
  multi-proposal types), and its adapter calls
  `TestService().create_test_case(...)` with no `origin`
  (`application/interview_artifact_adapters.py:95-99`, registered at `:208`;
  TestCase is in `IN_SCOPE_ARTIFACT_TYPES`, `application/interview_protocol.py:31-36`).
  Those rows therefore land as `origin="manual", reviewed=True` and still count
  as full verification evidence — the same false-green #424 reports, just via a
  different producer. §1.1 claims the consumer side is closed, but the producer
  side is only partially closed.
- **Suggested fix:** pass `origin="ai_generated", reviewed=False` from the
  `_test_case` interview adapter (or explicitly document, with rationale, why
  interview-formalized TestCases are treated as human-confirmed and add that
  rationale to F5/F7). Add an AC covering the interview path.

---

## Findings — minor

### N4 — `is_creation_baseline` on "all other rows" needs a third module
- **Severity:** minor
- **Category:** Consistency (#272, §7.4.2)
- **Description:** §7.4.2 says "Betroffen: `list_versions` (:472) und
  `list_versions_for_entity` (:499) — beide nutzen denselben Helper". Only the v0
  row comes from `creation_baseline_entry` (`artifact_diff_service.py:213-222`).
  The non-v0 rows come from `ArtifactVersionService.list_revisions`
  (`artifact_version_service.py:163-185`) for `list_versions`
  (`artifact_diff_service.py:490`) and from `_current_version_entry`
  (`:526-539`) for `list_versions_for_entity`. To emit
  `is_creation_baseline: False` consistently those two producers must also be
  touched (plus `rest_api/icd_views.py:740` / `diagram_views.py:373`, which use
  the helper directly and get the key for free).
- **Suggested fix:** name `ArtifactVersionService.list_revisions` and
  `_current_version_entry` as affected in §7.4.2, or centralize the key in one
  builder.

### N5 — New editable TestCase columns are absent from the baseline state capture
- **Severity:** minor
- **Category:** Consistency (#398 invariant, #424/#399)
- **Description:** `baseline.state_capture._capture_items` snapshots the TestCase
  state from a fixed field dict that does **not** include `origin`, `reviewed`
  or `scenario_kind` (`baseline/state_capture.py:226-243`), even though the
  module's own contract is "every user-editable column of every artifact-backed
  entity belongs in this map … a field that is not captured here is a field
  whose drift is structurally invisible" (`:116-126`). `scenario_kind` (PATCH)
  and `reviewed` (review action) are user-editable and do bump `version`
  (`application/artifact_service.py:121-146` snapshots all concrete fields), so
  a baseline diff will see the version move but no content change — exactly the
  class of bug #398 fixed.
- **Suggested fix:** add the three fields to the TestCase branch of
  `_capture_items` (or document why they are intentionally excluded from
  baseline state).

### N6 — `0100` must use historical models, not the live manager
- **Severity:** minor
- **Category:** Feasibility (migration)
- **Description:** §5.1 writes `Workspace.objects.filter(tenant_id=<t>, …)`. If
  implemented against the live model, `TenantManager.get_queryset` calls
  `TenantContext.get_tenant()` (`persistence/tenancy.py:135-143`) and raises
  `TenantContextNotSetError` because the migration only arms the DB GUC, not the
  thread-local. `link_types/0005` sidesteps this by using
  `apps.get_model(...)` (`0005_backfill_goal_reference_pairs.py:73-90`), and
  `0073` documents exactly why (`0073_backfill_artifact_backing.py:12-17`).
- **Suggested fix:** state explicitly that the `0100` `RunPython` resolves
  `Tenant`/`Workspace` through `apps.get_model("persistence", …)`.

### N7 — `origin` validation is wider than the client contract
- **Severity:** minor
- **Category:** Consistency (#424)
- **Description:** §4.3 validates `origin ∈ TestCaseOrigin.values` — which
  includes `unknown` — while §4.4 restricts the REST serializer to
  `{manual, ai_generated}` and F5 states "`unknown` ist clientseitig gesperrt".
  The MCP `test.create` schema extension is not stated to exclude `unknown`, so
  the "system-only" value is writable through at least one service caller.
- **Suggested fix:** validate service input against the client-writable subset
  and keep `unknown` settable only by the migration, or state the MCP schema's
  choice set explicitly.

---

## Findings — info

### I1 — A crashing VAL-P1 fails the baseline gate closed
Even with N1 fixed (WARNING), the GH-400 fail-closed handler in
`BaselineFacade._enforce_audit_gate` (`application/baseline_facade.py:443-459`)
turns any *exception* raised while evaluating the gate into a `ValidationError`
that blocks the baseline. A bug in the new VAL-P1 rule would therefore still
block Extended baselines even though the rule is advisory. This is existing,
intended gate behaviour (not a defect in the spec), but it is worth a release
note alongside F8.

---

## Spot-check of the minor items (m1–m11)

| Item | Status | Evidence |
|------|--------|----------|
| m1 `reviewed` PATCH | RESOLVED | Explicit `validate()` rejection reading `self.initial_data` for `reviewed` **and** `origin` (§4.4); AC-424-6 tests both. Feasible — `UnknownFieldRejectionMixin` accepts declared read-only fields (`rest_api/serializers.py:663-695`), so an explicit guard is required and is now specified. |
| m2 test-breakage list | RESOLVED | `test_workspace_create_schema_conformance.py:121` now listed (asserts `is False`); `test_goal_views.py:90` correctly re-classified as non-breaking (it passes `goals_enabled=False` explicitly). |
| m3 `link_types/0009` | RESOLVED | `is_customized=False` filter, `dependencies=[("link_types","0008_…")]`, `RunPython.noop` reverse (§5.2/§8); matches `0005`. |
| m4 global scope + arming | RESOLVED (with N2) | Global candidates tenant-wide without workspace filter (§6.2 step 2) — correct: `ScopeResolver._resolve_global` walks the whole tenant (`baseline/delta_index_builder.py:172-191`). Arming direction correct (`capture_states` → `state_reader.current_states` without `tenant_id`, `baseline/state_capture.py:592` + `workflow/state_reader.py:132-138`), but see N2 for the clear. |
| m5 `_assert_endpoints_live` | RESOLVED | Direct `Artifact.lifecycle_status == "outdated"` check on the already-loaded endpoints (§7.3); no invented helper. |
| m6 v0 `content_available` | RESOLVED (with N4) | `content_available` stays `False` (`artifact_diff_service.py:221`); `is_creation_baseline: True` added additively. See N4 for the producer scope. |
| m7 `_ENTITY_FIELDS` rationale | RESOLVED | Corrected rationale (unlisted ⇒ not snapshotted) plus the one-time "added" diff note (§4.3), matching the Icd precedent (`artifact_diff_service.py:170-175`). |
| m8 ArtifactRow path + N+1 | RESOLVED | Path corrected to `frontend/src/components/shared/ArtifactRow/ArtifactRow.tsx` (exists); badge restricted to the editor header, list badge explicitly out of scope (§6.4/D7). |
| m9 wrong module | RESOLVED | Citation now `backend/workflow/precondition_rules.py:615` — verified, the function is there. |
| m10 VAL-P1 gate fail-open | RESOLVED | `Workspace.unscoped.filter(id=…, tenant_id=…, goals_enabled=True).exists()` → else `return []` (§5.3); AC-402-4 extended. |
| m11 AC gaps | RESOLVED | AC-424-1 no longer posts the read-only `reviewed`; new AC-424-11 (MCP `test.mark_reviewed`), AC-424-12 (`pending_ai_review`), AC-D1-11 (badge + CR prefill); CR-prefill contract named (`affected_item_ids`, §4.4/§6.4). `create_change_request` already accepts `affected_item_ids` (`application/change_request_service.py:187-197`), so only serializer + view pass-through are new — feasible. |

Other verified-correct facts: latest migrations are `persistence/0098` and
`link_types/0008` (so `0099`/`0100`/`0009` are free); `satisfies` is
`Requirement→Goal` only (`link_types/builtin.py:182`) and `test_builtin.py:157`
pins that list; `Workspace.goals_enabled` default is `False`
(`persistence/models.py:731`) and the serializer default is `False`
(`rest_api/serializers.py:1633`); no existing `coverage-report`,
`review` or `baseline-membership` action collides with the planned routes.

---

## Verdict

**CHANGES_REQUESTED** — no critical defect, and M1/M2/M3 are genuinely resolved.
M4 is **not** resolved: the audit engine re-stamps VAL-P1 to BLOCKER because the
required `severity_for_tier` override is missing (N1), which re-introduces the
retroactive baseline blocker. Two further majors (N2 TenantContext clobbering on
every edit/retrieve path, N3 second LLM TestCase producer) must be fixed before
implementation. The four minors are precision/completeness gaps.

### Required before approval
1. **N1** — `severity_for_tier → WARNING` on the VAL-P1 rule (+ mutation probe).
2. **N2** — save/restore the tenant context in `memberships_for_artifact`.
3. **N3** — mark the interview-formalized TestCase producer (or document the
   exception explicitly).

### Explicit answer: cleared for `database-engineer`?
**No.** The migration design (M1–M3) itself is sound and RLS-safe, but the
cluster as a whole is not cleared until N1–N3 are resolved and the spec is
re-issued as revision 3.
