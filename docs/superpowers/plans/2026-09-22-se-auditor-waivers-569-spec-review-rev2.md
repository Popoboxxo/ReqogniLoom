---
type: REVIEW
scope: "#569 / docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec.md"
status: open
date: 2026-09-22
author_agent: concept-reviewer
reviewer: concept-reviewer
reviewed_artifact: docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec.md
revision_reviewed: 2
supersedes_review: docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review.md
issue: "#569"
branch: feat/se-validation-completeness
verdict: CHANGES_REQUESTED
findings:
  critical: 0
  major: 2
  minor: 4
  info: 1
resolution:
  C1: resolved
  M1: resolved
  M2: partial
  M3: resolved
  M4: resolved
  M5: resolved
  M6: resolved
  M7: resolved
  m1: resolved
  m2: resolved
  m3: resolved
  m4: resolved
  m5: resolved
  m6: resolved
  m7: resolved
---

# Re-Review — #569 Spec, Revision 2 (SE-Auditor Waivers)

Read-only re-review of `2026-09-22-se-auditor-waivers-569-spec.md` (revision 2, §11 =
„Revision 1 → 2 Auflösungs-Matrix") against the actual tree on
`feat/se-validation-completeness`. **No spec or code file was modified**; this document is the
only artifact.

Method: every resolution claim of §11 was re-verified against `file:line`, and each new/revised
AC (AC-569-17 … AC-569-27, AC-569-COMPAT) was checked for internal consistency with the existing
signatures it pins. Findings of the prior review are reported per item; new findings are N1–N6.

**Result in one line:** C1 and M1/M3–M7 are genuinely resolved (with verifiable evidence); M2 is
**partial** (the authority half is fully specified, the reason-policy half is not), and the
revision introduces one new major contract conflict (400 vs. 422 on the same exception type).

---

## 1. Per-finding status (prior review)

### C1 — Document-scoped findings not suppressible → **RESOLVED**

- REST body carries `scope`/`scope_artifact_id` additively (spec §3.4, `:415-416`, plus the
  explicit statement `:422-424` that they are used *only* for the engine scope and that the
  persisted values still come from the matched finding).
- MCP schema carries the same two fields (spec §3.5, `:509-510`), with the required-pair rule
  for `document`.
- Existence check runs scope-aware: `_run_engine_uncapped(scopes=…)` exists and takes
  `scopes: Optional[Sequence[AuditScope]]` (`backend/application/audit_service.py:233-259`,
  verified) and `AuditScope` accepts `artifact_id`
  (`backend/traceability/audit/types.py:76-85`, verified). The default path is unchanged
  (`rule_engine.py:102-104` → `[AuditScope("project")]`, verified).
- UI path is feasible: the report's findings already carry `scope`/`scope_artifact_id`
  (`traceability/audit/types.py:69-71`) and the TS type already declares both
  (`frontend/src/api/audit.ts:45-46`) — the spec's `WaiveRequest` (§3.6, `:545-552`) can be
  populated from the clicked row.
- AC-569-17 (`:898-908`) covers exactly the gap: document-scoped finding is waivable, missing
  `scope_artifact_id` → 400/422, and a scope-agnostic call creates **no** document-scoped row.
- Note (not a defect): scope-agnostic rules still run when only `document` is requested
  (`rule_engine.py:95-98`), so the narrowed engine run does not hide them.

### M1 — silent tier drift of `audit.se_audit` → **RESOLVED**

- The tool-level set replaces the namespace entry (spec §3.5, `:483-499`): new
  `_GOVERNANCE_TOOL_NAMES` checked **before** `_GOVERNANCE_TOOL_NAMESPACES`, which matches the
  existing evaluation order (`tool_registry.py:1409-1430`, verified) and requires no change to
  the namespace set (`:556-573`, verified: `"audit"` is absent).
- The corrected ist-state is accurate: `audit.se_audit` is not in `_READ_ONLY_TOOL_NAMES`
  (only `audit.query`/`audit.ai_review` at `tool_registry.py:420-421`, verified) and does not
  match `_READ_ONLY_TOOL_SUFFIXES` (`:512`) → `_is_write_tool` `True` (`:1392-1407`) →
  namespace not governance → `Operation.WRITE` (`:1427-1430`). AUTHOR tier confirmed.
- `audit.waivers` is correctly placed in `_READ_ONLY_TOOL_NAMES` (`:499`) — it would otherwise
  fail closed as a write tool.
- Tier is pinned by test (AC-569-18, `:910-918`), including the negative
  `"audit" not in _GOVERNANCE_TOOL_NAMESPACES`.

### M2 — authority choke point not relocated → **PARTIAL**

Resolved part (verified):

- `assert_gate_waiver_authority` is placed in `baseline/waivers.py` (Layer 1), the new
  `GovernanceAuthorityError` is announced in `baseline/exceptions.py` — the module exists and is
  the right home (`backend/baseline/exceptions.py:1-125`, verified) — and both facades remap to
  `PermissionDeniedError`. `baseline/waivers.py` currently imports only `baseline.models`
  (`:32`, verified), so the relocation keeps the downward-only layer direction intact
  (`auth_tenancy` is Layer 0, `application` is Layer 2).
- `BaselineFacade._assert_override_permission` stays as a `@staticmethod` delegator
  (`baseline_facade.py:738-780`, verified) — the direct calls in
  `test_granular_api_key_scope_865.py:207-226` (verified) stay green. AC-569-20 pins both paths.

Residual (why only partial): the **same** layer argument applies to the second helper, and the
spec does not follow it through.

1. `_validate_gate_reason` raises `application.base.ValidationError`
   (`baseline_facade.py:1174-1177`) and the existing test asserts exactly that type
   (`test_baseline_gate_waivers_821.py:388-390`). The spec demands `validate_waiver_reason` be
   moved to Layer 1 „1:1" (§3.1, `:142`, `:179-181`) — but a Layer-1 module may not import
   `application.base` any more than it may import `PermissionDeniedError`, which the spec itself
   states (`:184-188`). **No domain exception is named for the reason policy**, so the mechanism
   (Layer-1 domain error + remap in both facades) is unspecified while its sibling
   (`GovernanceAuthorityError`) is fully specified.
2. `MIN_OVERRIDE_REASON_LENGTH` is imported **from `application.baseline_facade`** by an existing
   test (`test_baseline_gate_waivers_821.py:33`, used at `:382`); the other policy constants live
   next to it (`baseline_facade.py:67-88`). The spec's „thin delegator" keeps the function
   importable but says nothing about the constants' location/re-export.

### M3 — stale „details are dropped" premise → **RESOLVED**

- The premise is corrected in §1 (`:60-67`), §2/DoD 4 (`:84`), §5/E2 (`:646-651`), §7
  (`:1014-1016`) and O5 (`:1081-1083`), and the stale comment is explicitly not used as a
  premise.
- Verified: `ServiceBase._audit` persists `details` („#399: `details` is now persisted") at
  `backend/application/base.py:197-205`, and the `baseline.create` entry already carries
  `suppressed_blocker_count` / `suppressed_rule_ids` / `suppressed_finding_keys` / `waiver_ids`
  (`baseline_facade.py:336-344`, verified). AC-569-09 now asserts on those `details` (`:815-817`).

### M4 — `waiver_ids` contains only newly created rows → **RESOLVED**

- `GateWaiverOutcome.matched_waiver_ids` is additive (`:245-251`); the docstring/field contract it
  preserves is accurate (`baseline_facade.py:104-110`: „Ids of the waiver rows *created* by this
  request", verified).
- `waiver_ids` stays the created-only contract, `details["waiver_ids"]` is unchanged and
  `matched_waiver_ids` is added (§3.2 `:253-258`, E2 `:641-643`) — this respects the existing
  `_apply_waivers` return (`:610-642`, `:667-672`, verified: only `created_ids`).
- AC-569-09 now uses the **reuse** case explicitly (`:808-820`) and AC-569-19 pins the contract
  (`:920-926`). The description extension is safe for existing assertions, which are substring
  based (`test_baseline_gate_waivers_821.py:297`, `:566`; `…_821_rest.py:149`, verified).

### M5 — non-additive re-interpretation of `counts.blockers` → **RESOLVED**

- §3.3/M5 (`:334-353`) keeps `counts.*` / `total_*_available` descriptive and adds only
  `counts.suppressed`, `counts.suppressed_blockers`, `total_suppressed_available`,
  `total_suppressed_blockers_available`; §7 makes the non-reinterpretation a Non-Goal (`:1017-1018`)
  and Risiko 4 is downgraded with the same reasoning (`:1038-1041`).
- Consistent with the real contract (`audit_service.py:99-119` and `AuditReport.to_dict`
  computing counts from `self.findings`, `:136-158`, verified). AC-569-13 asserts it (`:849-861`).

### M6 — missing MCP manifest regeneration → **RESOLVED**

- §9 now names the step and the ratchets (`:1115-1120`); AC-569-25 pins it (`:975-982`).
- Verified: `backend/mcp_server/management/commands/export_tool_manifest.py`,
  `docs/agent-templates/tool-manifest.json` and
  `docs/agent-templates/test_role_tools_exist_in_manifest.py` all exist.

### M7 — GH-821 guarantee incomplete in the matching path → **RESOLVED**

- §1 (`:46-58`) and AC-569-COMPAT (`:686-728`) now pin **four** parts; (c) is exactly the
  missing test of rev1: a row persisted by a real gate build in the production-real form
  `scope="project"`, `scope_artifact_id=""` must keep suppressing after the matcher switch
  (`:709-720`). The row form is correct — `record_waiver(scope=finding.scope or scope)` at
  `baseline_facade.py:635` (verified) stamps the build scope for scope-agnostic findings.
- AC-569-16 is re-anchored on a persisted row instead of a literal (`:881-894`), and (d) carries
  two valid mutation probes: removing `waivers.py:96-97` reddens the byte-identity test (verified
  logic: `scope_part` empty → `base`), removing R2a/R2b reddens the gate-level test (verified
  logic: `finding.scope is None` + `record.scope="project"` matches neither R2a nor R2c).
- Residual (cosmetic, no GH-821 risk): part (b) still describes rows with `scope=""`/`NULL` as
  „Bestandszeilen", but the gate path can never produce them — `record_waiver` writes
  `scope or ""` from a non-empty build scope (`waivers.py:178`, verified). (b) is defensive only;
  the production-real form is covered by (c). Worth a wording fix, not a re-review trigger.

### Minor findings m1–m7 → **all RESOLVED**

| # | Resolution | Evidence |
|---|---|---|
| m1 | `409 SUPPRESSION_EXPIRED` instead of a silent 200 no-op; active row keeps 200/`created=false` | §3.2 `:260-267`, §3.4 `:467`, AC-569-21 `:939-945` |
| m2 | parse helper with `true`/`false` only, absent → `true`, else 400; `state` restricted | §3.4 `:426-430`, AC-569-22 `:947-953`; pattern matches the real `_parse_scopes`/`_parse_pagination` (`audit_views.py:90-128`, verified) |
| m3 | no new inline styles, CSS modules/hoisted `CSSProperties`, explicit `STYLE_BRACE_BASELINE` rule | §3.6 `:579-584`, AC-569-23 `:955-962`; verified `STYLE_BRACE_BASELINE = 705` at `ui-ratchet.test.ts:551`, exact equality at `:1047` (and `<=` at `:1035`) |
| m4 | R2b binds the scope-agnostic case to `record.scope_artifact_id == ""`; no bleed from document-bound waivers | §3.1 R2 `:155-172`, E6 `:662-666`, AC-569-16/26 |
| m5 | `now` keyword-only, positional 2-arg call preserved, equality regression test | §3.1 `:192-200`, AC-569-24 `:964-973` |
| m6 | 4 threat-model questions answered | §8 `:1051-1068`, AC-569-27 `:993-1001` |
| m7 | invariant documented + `suppressed_filtered` + test | §3.3 `:361-365`, AC-569-13/27 |

### Info i1–i4 / O-questions

- i1–i4 needed no change; the AC count that rev1 confirmed („COMPAT + 01…16" = 17) is preserved,
  and rev2 appends 17–27 without renumbering any existing AC (checked ID by ID). O2–O6 are
  entered as **decisions** (§8 `:1070-1086`), O1 is correctly left open as a product decision
  (§7 `:1022-1023`, §8 `:1088-1095`, Risiko 7 `:1048-1049`). O6's premise is accurate: the
  terminology profile maps exactly eight keys (`presets/terminology.py:49-74`, verified) and
  contains no audit/suppression vocabulary.

---

## 2. AC-569-COMPAT — final assessment

**The GH-821 guarantee is now complete** for the four declared parts:

- (a) rendering byte-exact — literal test (existing) + comparison against a persisted row
  (`:691-699`); the literal chain `finding_key(x, ids, None) == finding_key(x, ids) ==
  finding_key(x, ids, "")` holds against `waivers.py:91-98` (verified).
- (b) legacy rows `scope=""`/`NULL` — defensive, see residual above (not production-real).
- (c) matcher switch on the production-real row form `"project"` — the exact gap of rev1's M7,
  now a gate-level test (`:709-720`).
- (d) mutation probes on the rendering branch **and** on the R2a/R2b clauses (`:722-728`).

Remaining wording gap only: part (b) presents a row shape the gate path cannot produce, and the
spec does not state that the new `AuditService` path deliberately stamps `scope=""` for
scope-agnostic findings (§3.3 step 5, `:387-389`) while the gate path stamps `"project"` for the
same finding class (`baseline_facade.py:635`). Both are intended and both are covered by
R2a/R2b — but „two row forms for the same finding" should be an explicit contract sentence, not
an emergent property.

---

## 3. New findings

### N1 — [Logic/Consistency, major] 400 vs. 422 on the same exception type is not resolvable as specified

- §3.4's error table (`:462-469`) demands **400** for placeholder reason, invalid `scope` and
  missing `scope_artifact_id`, but **422** for „finding not reported as BLOCKER" — while §3.3
  routes all four cases through `ValidationError` (step 2 `:371`, step 3 `:375-376`, step 4
  `:383`).
- The type alone cannot express the split: in this module `ValidationError` maps to **422**
  (`audit_views.py:207-213`, verified) and the parse/field layer uses `ValueError`/serializer
  errors for **400** (`:141-144`, `:178-184`). The same condition („names a finding that is not
  blocking", `baseline_facade.py:615-627`) is a **400** on the existing baseline path
  (`views.py:170` + `:3862-3863`).
- Consequence: AC-569-02 (`400`, `:747`), AC-569-15 (`422`, `:877-879`) and AC-569-17
  (`400/422`, `:905-906`) cannot all pass under the module's existing mapping.
- **Fix:** name the mechanism — either a second additive exception (sibling of
  `SuppressionExpiredError`) for the 400-class input errors, or enforcement of the
  scope/reason checks in the serializer/parse layer before the service call — and state which
  type produces which status in §3.4.

### N2 — [Feasibility/SSOT, major] Layer-1 relocation of the reason policy has no error-type contract

(Same substance as the M2 residual; listed separately because it is the newly introduced gap.)

- `validate_waiver_reason` must live in `baseline/waivers.py` (Layer 1) but the logic it copies
  raises `application.base.ValidationError` (`baseline_facade.py:1174-1177`), which Layer 1 must
  not import — the very rule the spec applies to the authority helper (`:184-188`).
- The delegator claim („Verhalten unverändert, bestehende Patches/Tests bleiben gültig", `:180`)
  requires an explicit remap, and `MIN_OVERRIDE_REASON_LENGTH` (`baseline_facade.py:67`) is part
  of the imported surface (`test_baseline_gate_waivers_821.py:33`).
- **Fix:** add `baseline.exceptions.GovernanceReasonError` (or reuse an existing baseline
  domain error), remap it to `ValidationError` in `BaselineFacade._validate_gate_reason` **and**
  in `AuditService.suppress_finding`, and state where the policy constants live/re-export.

### N3 — [Completeness, minor] AC count is off by one

- „**Gesamt: 27 ACs** (AC-569-COMPAT + AC-569-01 … AC-569-16 + AC-569-17 … AC-569-27)"
  (`:896`) = 1 + 16 + 11 = **28**. The AC IDs themselves are complete and unique (verified
  individually); only the total is wrong.

### N4 — [Consistency, minor] AC-569-24 justifies `now` keyword-only with a call site the same revision removes

- AC-569-24 argues the keyword-only `now` is safe because of the positional call at
  `baseline_facade.py:608` (`:970-972`), but §3.2/M7 replaces that very call with
  `load_suppressions` + `suppression_applies` (`:253-255`). The premise becomes stale the moment
  the spec is implemented. Additionally the AC's „When" repeats the identical positional call
  twice (`:967-968`).

### N5 — [Risks, minor] New scope-blind facade helper `suppressed_finding_keys`

- §3.3 adds `AuditService.suppressed_finding_keys(...)` returning „aktive, scope-lose Keys"
  (`:307-309`). Scope-blind key matching is precisely what this revision replaced in the gate
  because it is too broad (R2/R2b, m4) — a consumer that uses this helper to mark or filter
  findings silently bypasses the scope binding. Specify the intended consumer (or drop the
  helper in favour of `list_suppressions` + `suppression_applies`).

### N6 — [Consistency, info] New domain exceptions are not registered in the shared error maps

- `rest_api/views.py:169-206` is keyed by **exact** exception type (its own comment warns about
  silent 500 degradation, `:166-168`). `GovernanceAuthorityError` is remapped before it reaches
  the adapter (fine), and `SuppressionExpiredError` is raised only in the new `audit_views`
  paths (fine) — but the spec should say explicitly that neither type may be surfaced through
  `_service_error_response`, otherwise a future reuse yields 500.

---

## 4. Verdict

**CHANGES_REQUESTED.**

The revision does its job on the substance: the critical C1 is genuinely closed on all three
surfaces (REST, MCP, UI) and with a matching AC; M1, M3, M4, M5, M6 and M7 are resolved with
verifiable `file:line` evidence, all seven minor findings are addressed, O2–O6 are entered as
decisions and O1 correctly stays open. AC-569-COMPAT now covers the full GH-821 guarantee
including the matching path, which was rev1's sharpest objection.

Two majors remain, both narrow and both fixable by specification text alone (no design change):

- **N1** — the 400/422 split for the new endpoints cannot be expressed with one
  `ValidationError` type under this module's mapping; AC-569-02 / AC-569-15 / AC-569-17 depend on
  it.
- **N2 / M2 partial** — the reason policy moves to Layer 1 without a named domain exception and
  without a statement about the policy constants, although the identical constraint was solved
  for the authority helper.

Plus three minor wording/consistency items (N3–N5) and one info note (N6). After those, the
concept is ready to hand off to `requirements`/`se-requirements`.
