---
type: REVIEW
scope: cluster-5-se-validation-completeness
status: closed
date: 2026-09-22
author_agent: concept-reviewer
reviewer: concept-reviewer
reviewed_artifact: docs/superpowers/plans/2026-09-22-se-validation-completeness-spec.md
revision_reviewed: 3
supersedes_review: docs/superpowers/plans/2026-09-22-se-validation-completeness-review-rev2.md
issues: [424, 402, 399, 272]
branch: feat/se-validation-completeness
verdict: APPROVED
findings:
  critical: 0
  major: 0
  minor: 2
  info: 2
---

# Final Re-Review — Cluster 5 Spec, Revision 3 (SE-Validation Completeness)

## Scope

Read-only final re-review of
`docs/superpowers/plans/2026-09-22-se-validation-completeness-spec.md` (revision 3,
§14 = v2→v3 resolution register) against the actual code on
`feat/se-validation-completeness`. No spec or code file was modified; this review
file is the only artifact written.

Verified: the four rev2 majors/minors **N1, N2, N3, N6** against the real hooks they
name, plus regression of **M1–M3** and a spot-check of **m1–m11 / i1–i3**.
Every `file:line` citation of the revision was opened and confirmed.

## N1 — VAL-P1 severity override → **RESOLVED**

- The hook is real and exactly as documented: `RuleEngine._run_rule`
  (`backend/traceability/audit/rule_engine.py:137-154`) reads
  `severity = rule.severity_for_tier(tier)` **before** `rule.check(...)`, then
  re-stamps every finding whose severity differs (`:140-154`). The base
  implementation returns `Severity.BLOCKER`
  (`backend/traceability/audit/registry.py:233-240`).
- **`severity_for_tier` → WARNING is genuinely the only gate-effective severity.**
  The single gate consumer is `AuditService.blocking_findings`
  (`backend/application/audit_service.py:296`), which filters
  `result.findings` on `Severity.BLOCKER` — i.e. on the **post-`_run_rule`**
  objects. `BaselineFacade._enforce_audit_gate` consumes only that method
  (`backend/application/baseline_facade.py:440-442`). The `Finding(severity=...)`
  value never reaches the gate. The spec's contract table (§5.4) states this
  correctly.
- Precedent confirmed as cited: `LevelProgressionRule.severity_for_tier`
  (`backend/traceability/audit/rules/level_progression.py:138-140`, with the
  "shipping a brand-new rule as a BLOCKER would retroactively…" rationale at
  `:60-63`) and `RequirementAllocatedToArchitectureRule.severity_for_tier`
  (`backend/traceability/audit/rules/trace_derivation_allocation.py:403-428`).
- Preset placement is feasible: `_EXTENDED_ONLY_RULES` is at
  `registry.py:89-98` and feeds `RULE_PRESET_MAP["extended"]` (`:113-117`) and
  `FULL_SE_RULE_IDS` (`:108`); Minimal stays structurally empty (`:114`, `:128`).
- **AC-402-9 is now correct.** It checks (a) the severity **after** the engine
  re-stamp and (b) absence from `blocking_findings`, with the mutation probe keyed
  on the override rather than the `Finding` value. Probe semantics verified: the
  override is the only switch that changes gate behaviour.

## N2 — `memberships_for_artifact` tenant-context save/restore → **RESOLVED**

- The defect was real and the fix targets the right mechanism:
  `clear_request_tenant()` unconditionally clears the thread-local **and**
  `RESET`s the RLS GUC (`backend/persistence/middleware.py:69-73`), while
  `ServiceBase._audit` writes a tenant-scoped `pl_audit_log_entry` row
  (`backend/application/base.py:159-218`; `pl_audit_log_entry` is in the FORCE-RLS
  set, `backend/persistence/migrations/0003_rls_policies.py:57`). A blind clear
  would therefore break the audit write that follows the membership lookup.
- `armed_here` is specified against the **public** primitives only —
  `TenantContext.is_set()` / `.get_tenant()`
  (`backend/persistence/tenancy.py:63-98`, both present and non-raising) — and
  `set_request_tenant` / `clear_request_tenant` are the documented public pair
  (`middleware.py:34`, `:69`).
- **Nested-context safety: correct for the dominant case.** All wired call sites
  (`RequirementService.update_requirement` `backend/application/requirement_service.py:387`,
  `TestService.update_test_case` `backend/application/test_service.py:245`,
  `delete_requirement` `requirement_service.py:564`, and the `retrieve` paths) run
  either under the tenant middleware or under the MCP dispatch, which arms **both**
  layers via `set_request_tenant`
  (`backend/mcp_server/tool_registry.py:952-1020`). With a pre-armed context,
  `armed_here=False` → the ambient context is left untouched (spec's invariant),
  and no `RESET`/re-`SET` roundtrip occurs.
- AC coverage is now adequate: AC-D1-10 (`is_set()==False` afterwards),
  AC-D1-12 (nested/dominant case + subsequent `_audit` succeeds), AC-D1-13
  (edit end-to-end), plus the §9 mutation probe.
- Algorithmic signatures verified verbatim: `BaselineStore.load_states(baseline_id,
  tenant_id, item_ids: Optional[list[str]])` (`backend/baseline/store.py:167-201`)
  with the tenant-check preamble `BaselineSnapshot.unscoped.filter(id=…, tenant_id=…)`
  (`:191-194`); `load_delta_index` likewise (`:134-157`); `capture_states(
  delta_index, tenant_id)` accepting `DeltaIndexTuple`
  (`backend/baseline/state_capture.py:62-65`, `backend/baseline/types.py:24`);
  `ScopeResolver._resolve_global` (`backend/baseline/delta_index_builder.py:172`).
  See R3 for a residual (info-level) edge.

## N3 — interview TestCase producer + complete producer enumeration → **RESOLVED**

- P4 is now specified: `_test_case` passes `origin="ai_generated"`,
  `reviewed=False` (§4.8). The call site is real and unpatched today —
  `backend/application/interview_artifact_adapters.py:95-99` calls
  `TestService().create_test_case(workspace_id=…, ctx=…, **fields)` with no
  `origin`, registered at `:208`.
- The path is genuinely LLM-driven (not human-confirmed): the multi-artifact
  prompt emits `"LLM emits a fenced ```json block, we extract and json.loads it"`
  (`backend/application/interview_multi_protocol.py:6-10`) with `TestCase` among
  the proposed types (`:38-41`), and `TestCase` is in `IN_SCOPE_ARTIFACT_TYPES`
  (`backend/application/interview_protocol.py:31-40`). Rejecting the
  "documented exception" is the correct call — an exception would reintroduce the
  exact #424 false-green class.
- **The P1–P5 enumeration is complete.** Two independent greps over `backend/`
  confirm the production producer set is exactly `{P1…P5}`:
  - `create_test_case(` outside `*/tests/` and `*/conftest.py`:
    `rest_api/views.py:2406` (P1), `mcp_server/tools/tests.py:566` (P2),
    `mcp_server/tools/tests.py:1114` (P3),
    `application/interview_artifact_adapters.py:96` (P4),
    `auth_tenancy/management/commands/seed_toothbrush.py:400` (P5).
    `rest_api/serializers.py:1164` is a comment; `application/test_service.py:142`
    is the definition.
  - `TestCase.objects.create(` outside tests/conftest:
    only `application/test_service.py:196` — the asserted single model choke point.
- The REST derive path is **not** a hidden producer: `POST /api/v1/requirements/{pk}/derive-testcase/`
  (`rest_api/views.py:1296-1318`) returns a draft and persists nothing, which is
  why AC-424-1 correctly chains the subsequent `POST /api/v1/testcases/` (P1).
- The overwrite-protection mechanism as written is imprecise — see R1. It cannot
  produce a false-green (worst case a loud `TypeError`), so N3 remains resolved.

## N6 — `0100` historical models → **RESOLVED**

- §5.1 point 2 and §8 row 2 now mandate
  `apps.get_model("persistence", "Tenant")` / `apps.get_model("persistence", "Workspace")`.
  The precedent and rationale are exactly as cited:
  `backend/link_types/migrations/0005_backfill_goal_reference_pairs.py:73-90`
  (historical models) and
  `backend/persistence/migrations/0073_backfill_artifact_backing.py:12-17`
  ("the live ``TenantManager`` … requires an ambient ``TenantContext`` that no
  migration has").
- The failure mode the fix avoids is real: `TenantManager.get_queryset` calls
  `TenantContext.get_tenant()` and raises `TenantContextNotSetError`
  (`backend/persistence/tenancy.py:135-143`); the migration arms only the DB GUC.
- **RLS-safe and asserted:** `pl_workspace` is in the FORCE-RLS set
  (`0003_rls_policies.py:46-58`, `:67`), tenant enumeration uses `pl_tenant`
  (deliberately excluded from that set, `:43-45`), arming is per tenant with
  `SET app.current_tenant` + `finally: RESET` (pattern `0005:35-44`), and
  `expected`/`updated` are both formed on the **same historical model**, so
  `assert updated == expected` is meaningful under a non-BYPASSRLS role
  (AC-402-2).
- Migration numbering is free: highest is `persistence/0098_requirement_rationale_requirement_source.py`
  and `link_types/0008_seed_satisfaction_link_types.py`; `0099`/`0100`/`0009`
  are available.

## No regression of M1–M3 / m1–m11

| Prior item | Status | Evidence re-verified |
|---|---|---|
| M1 VERIF-P8 third consumer | intact | `_active_test_cases` (`traceability/audit/rules/coverage_consistency.py:156-195`) still filters only `outdated`; `LeafRequirementHasTestCaseRule.check` uses it at `:282`; the shared predicate + `_active_verifying_test_cases` plan is unchanged (§4.5(3)) |
| M2 `unknown` grandfathering | intact | `0099` remains schema-only (§4.2/§8 row 1); serializer restricted to `{manual, ai_generated}` (§4.4); service default `MANUAL` (§4.3) |
| M3 RLS migrations | intact | `store.py:154-156` / `:191-194` tenant-check preamble; `0009` tenant-armed + `is_customized=False` + `RunPython.noop` (§5.2/§8 row 3) |
| m1 `reviewed`/`origin` PATCH rejection | intact | §4.4 unchanged, AC-424-6 both rejections |
| m2 test-breakage list | intact | `persistence/tests/test_workspace_goals_fields.py:17` (`assertFalse`), `rest_api/tests/test_workspace_create_schema_conformance.py:121` (`is False`), `rest_api/tests/test_goal_views.py:90-91` (explicit `goals_enabled=False`) all confirmed |
| m3 `link_types/0009` | intact | dependency `0008`, `is_customized=False`, noop reverse (§5.2) |
| m4 global scope + arming | intact | `_resolve_global` at `delta_index_builder.py:172`; §6.2 no workspace filter for global |
| m5 `_assert_endpoints_live` | intact | `lifecycle_status == "outdated"` direct check (§7.3) |
| m6 v0 `content_available` | intact | `creation_baseline_entry()` returns `content_available: False` (`artifact_diff_service.py:213-222`) |
| m7 `_ENTITY_FIELDS` rationale | intact | corrected rationale + one-time diff note (§4.3) |
| m8 ArtifactRow path / N+1 | intact | badge confined to editor header (§6.4/D7) |
| m9 wrong module | intact | `policy_fields_without_consumer` is at `workflow/precondition_rules.py:615` |
| m10 VAL-P1 fail-open gate | intact | `Workspace.unscoped` exists (`persistence/models.py:427`); `.unscoped` semantics documented (`:408-436`) |
| m11 AC gaps / CR prefill | intact | `create_change_request(..., affected_item_ids=…)` already accepts it (`application/change_request_service.py:197`, validated at `:873`); only serializer + view pass-through are new |
| i1–i3 | intact | unchanged (§13) |

**Addendum (not a regression):** `traceability/services.py:157-191` is a facade
over the calculator and is not mentioned in §4.5 — see R4.

## Findings — minor

### R1 — The stated P4 overwrite protection does not work as described
- **Severity:** minor
- **Category:** Logic gap / precision (#424, §4.8)
- **Description:** §4.8 claims "`origin`/`reviewed` werden **nach** `**fields`
  aufgeführt" as the overwrite protection for the interview adapter. Keyword-argument
  ordering provides no such protection: if the proposal dict contains `origin`,
  `create_test_case(..., origin=…, **fields)` raises
  `TypeError: got multiple values for keyword argument 'origin'` regardless of
  whether the explicit keyword precedes or follows `**fields`. The shipped
  pseudo-code block places `origin`/`reviewed` **before** `**fields`, i.e. the
  opposite of the prose. Only the second mechanism named in the same paragraph —
  `fields = {k: v for k, v in fields.items() if k not in ("origin", "reviewed")}` —
  satisfies AC-424-14. This is reachable in practice: `protocol_from_definition`
  derives protocol field names from tenant-defined attribute definitions
  (`interview_protocol.py:214-266`), so a tenant attribute literally named
  `origin` would land in `fields`.
- **Impact:** not a false-green — a duplicate key fails loudly (the AC turns red).
  But an implementer following the primary wording speculatively loses a test
  iteration and may "fix" it by dropping the guard.
- **Suggested fix:** make the dict-filter the **normative** mechanism (promote it
  from "bzw." to the primary form) and delete the ordering rationale; alternatively
  call `create_test_case` with the adapter keys applied last to a filtered dict.

### R2 — AC-424-16's frozen producer set conflicts with the cluster's own new fixture command
- **Severity:** minor
- **Category:** Consistency / logic gap (#424 §4.8+§7.5)
- **Description:** AC-424-16 freezes the set of productive `create_test_case(`
  call sites (everything outside `*/tests/` and `*/conftest.py`) as exactly
  `{P1,P2,P3,P4,P5}`. P5 is itself a management command
  (`auth_tenancy/management/commands/seed_toothbrush.py:400`), so commands are
  in scope. §7.5 then introduces a **new** command `seed_full_chain.py` that seeds
  12 TestCases "nutzt ausschließlich bestehende Services" — i.e. it will call
  `create_test_case` and become a sixth productive call site. Implemented as
  written, AC-424-16 is red by construction on the cluster's own deliverable.
- **Impact:** the intended mechanism (force an explicit `origin` decision per new
  producer) is working as designed; the expected set is simply stale relative to
  §7.5. No behavioural gap — `origin="manual"`, `reviewed=true` is already stated
  for the fixture.
- **Suggested fix:** add the new command as **P6** to §4.8 and to AC-424-16's
  expected set (pin it explicitly to `origin="manual"`, `reviewed=True`), or
  state that AC-424-16 is evaluated after §7.5 lands and includes it.

## Findings — info

### R3 — `armed_here` keys on the thread-local, not on the RLS GUC
- **Severity:** info
- **Description:** `armed_here = TenantContext.is_set()` treats "thread-local set"
  as "RLS armed". The two are coupled only when arming goes through
  `set_request_tenant`; a bare `TenantContext.set_tenant(...)` sets the thread-local
  without `SET app.current_tenant`. The codebase documents that exact pattern as a
  former bug class ("fix #110: use set_request_tenant, not the bare TenantContext",
  `mcp_server/tool_registry.py:952`), and remnants of the bare form still exist
  (e.g. `mcp_server/tools/audit.py:513`, `admin_ops/theme_rest.py:104`). Every
  wired call site of `memberships_for_artifact` runs under middleware or MCP
  dispatch, both of which arm the GUC, so the residual risk is theoretical today.
- **Suggested fix (optional):** note the assumption in §6.2, or re-arm when
  `prior_tenant_id != ctx.tenant_id` even if a context is present.

### R4 — The `traceability.services` coverage facade inherits the new default silently
- **Severity:** info
- **Description:** `traceability/services.py:157-191` wraps
  `CoverageCalculator.coverage` / `get_coverage_data` and is used,
  among others, by `VCRMReportGenerator` (which explicitly passes
  `include_outdated=True`, `:187-191`). Once `include_unreviewed_ai` defaults to
  `False` in the calculator, this facade excludes unreviewed AI TestCases too —
  which is the intended #424 semantics, but the spec's §4.5 consumer list does not
  name it and does not expose the escape hatch through it.
- **Suggested fix:** add a one-line note to §4.5 that the facade inherits the new
  default deliberately (and optionally forwards `include_unreviewed_ai`).

## Verdict

**APPROVED.** 0 critical, 0 major, 2 minor, 2 info.

All four items the revision committed to (N1, N2, N3, N6) are genuinely resolved
against the real code, not just restated: the `severity_for_tier` re-stamp path
was followed end-to-end into `blocking_findings`; the tenant-context fix uses the
public primitives and is safe for the nested/middleware case; the interview
producer is the third LLM path and the enumeration was independently confirmed
complete by grep (5 producers, 1 model choke point); the `0100` `RunPython` now
uses historical models with per-tenant arming and a meaningful assertion. M1–M3
and m1–m11 show no regression, and the revision is implementable without further
design decisions — the migration design is sound and RLS-safe.

The two minors are precision/completeness gaps in the acceptance-criteria
machinery, both loud (a red test, never a false-green) and both resolvable inside
the implementation task: R1 by making the already-named dict-filter normative, R2
by adding `seed_full_chain` as P6. Neither blocks the two downstream workstreams;
they should be folded into the implementation as noted.

### Handoff

**Cleared for `database-engineer` (migrations) and `developer` (implementation).**

- Migrations `persistence/0099` (schema-only), `persistence/0100` (historical
  models + per-tenant arm + `updated == expected` assertion) and
  `link_types/0009` (tenant-armed, `is_customized=False`, noop reverse) are
  free, correctly ordered and RLS-safe as specified.
- Implementation may start on §4–§7 with R1 and R2 folded in as specified above.
- N5 / F10 (`origin`/`reviewed`/`scenario_kind` absent from
  `baseline/state_capture.py:226-243` — confirmed still absent) remains a
  documented, accepted follow-up, not a gate.
