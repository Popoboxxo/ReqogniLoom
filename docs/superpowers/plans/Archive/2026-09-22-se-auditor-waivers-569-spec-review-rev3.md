---
type: REVIEW
scope: "#569 / docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec.md"
status: open
date: 2026-09-22
author_agent: concept-reviewer
reviewer: concept-reviewer
reviewed_artifact: docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec.md
revision_reviewed: 3
supersedes_review: docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review-rev2.md
issue: "#569"
branch: feat/se-validation-completeness
verdict: CHANGES_REQUESTED
findings:
  critical: 0
  major: 1
  minor: 9
  info: 5
resolution:
  M-A: resolved
  M-B: resolved
  N1: resolved
  N2: resolved
  N3: resolved
  N4: resolved
  N5: resolved
  N6: resolved
---

# Re-Review — #569 Spec, Revision 3 (SE-Auditor Waivers)

Read-only re-review of `2026-09-22-se-auditor-waivers-569-spec.md` (revision 3) against the
actual tree on `feat/se-validation-completeness`. **No spec or source file was modified**;
this document is the only artifact written. Method: every rev3 claim of the `## Changelog`
and of `§11.1` was re-verified against `file:line`, and each new/revised AC
(AC-569-28 … AC-569-33, AC-569-COMPAT, AC-569-02/11/13/15/17/24/29) was checked for internal
consistency and against the existing tests it pins.

**Result in one line:** both rev2 majors are genuinely closed — M-A is **resolved** (disjoint
E1–E18, `not-blocking` moved 422 → 400, consistent with the existing `_apply_waivers` 400
path, sound RFC 9110 split) and M-B is **resolved** (L1 `GovernanceReasonError`/
`GovernanceAuthorityError` → L2 `ValidationError` subclasses with `error_code`, registered in
the shared maps, L1 deliberately unregistered; MCP codes `-32008/-32009/-32010` are free) —
and N3–N6 are fixed. One **new major** remains: the §3.3/AC-569-13 `m7` invariant is
arithmetically unreachable and contradicts the M5 resolution, so AC-569-13 cannot be
implemented as written. Plus nine minor / five info items, none of which changes the design.

---

## 1. M-A — 400-vs-422 status-code contract → **RESOLVED**

Claim: the new Waiver/Report endpoints never emit 422; 422 is reserved for
`POST …/audit/remediate/`; the mapping is total and disjoint.

Verified:

- **Existing 422 host is correctly identified.** `WorkspaceAuditRemediateView.post` maps
  `ValidationError` → 422 (`backend/rest_api/audit_views.py:207-213`) and parse/serializer
  errors → 400 (`:141-144`, `:178-184`). The frontend flip on 422 is real
  (`frontend/src/api/client.ts:303-324` → `UnprocessableEntityError`,
  `frontend/src/components/Audit/audit-dashboard.tsx:309`), with a regression test at
  `frontend/src/components/Audit/audit-dashboard.test.tsx:485-489`.
- **"Finding not blocking" is genuinely a 400 elsewhere.** `_apply_waivers` raises
  `ValidationError` for exactly this condition (`backend/application/baseline_facade.py:620-627`)
  and `_service_error_response` maps `ValidationError` → **400** via
  `_EXC_TO_HTTP[ValidationError]` (`backend/rest_api/views.py:170`, `:192-193`, `:222`). So the
  new endpoint's **400 `WAIVER_FINDING_NOT_BLOCKING`** is status-consistent with the legacy
  surface — rev2's N1 objection (same condition, two different statuses) is gone.
- **E1–E9 / E10–E13 / E14–E16 are disjoint for the classes the spec enumerates**: 201/200,
  400 `VALIDATION_ERROR`, 400 `WAIVER_REASON_REJECTED`, 400 `WAIVER_FINDING_NOT_BLOCKING`,
  403, 404, 409, 500. No error class maps to two statuses. The reserved-host row E17 keeps
  422 exactly where it is today.
- **RFC 9110 split is defensible.** 400 (§15.5.1) for malformed/unknown/policy-failing
  requests and the not-blocking case; 403 (§15.5.4) for role/tier denials; 404 (§15.5.5) for
  cross-tenant workspace, matching `audit_views.py:155-159`; 409 (§15.5.10) for the m1 state
  conflict. The 409 argument ("well-formed + authorized, but the target resource state forbids
  the idempotent 200") is sound and 409 is already an established status in this layer
  (`OptimisticLockError` → 409, `views.py:189`).

Residuals (minor, do not block M-A): see **R3-05** (GET rows lack 403/500) and **R3-06**
("exclusively remediate" is true only inside the audit module).

## 2. M-B — Reason-policy error type across the layer boundary → **RESOLVED**

Claim: L1 `GovernanceReasonError` (`baseline/exceptions.py`) → L2
`WaiverReasonPolicyViolation` / `WaiverFindingNotBlockingError` / `SuppressionExpiredError`
(`application/base.py`) with stable `error_code` attributes, registered in
`_EXC_TO_HTTP`/`_EXC_TO_CODE`/`ERROR_CODES`/`ERROR_CODE_MAP`/`_ERROR_MESSAGES`; one authority
choke point.

Verified:

- **The layer direction is legal.** `baseline/exceptions.py` exists with `BaselineError(Exception)`
  as root (`:13-14`), so `GovernanceReasonError(BaselineError)` is *not* a `ValidationError` and
  the existing `except ValidationError` paths are untouched. `baseline/waivers.py` today imports
  only `baseline.models` (`:32`), and `auth_tenancy` is Layer 0, so moving
  `assert_gate_waiver_authority` there keeps the downward-only import graph.
- **The precedence pattern is real.** `BaselineGateBlockedError(ValidationError)`
  (`application/base.py:61-77`) is exactly the "distinct subclass + own `error_code`" pattern
  the spec copies, and its docstring itself warns that the REST maps are keyed by *exact* type
  and a subclass without an entry degrades to 500 (`:74-77`) — the spec's registration duty
  answers that warning directly.
- **One authority choke point is specified and testable.** `assert_gate_waiver_authority`
  (`baseline/waivers.py`) plus `BaselineFacade._assert_override_permission` as a `@staticmethod`
  delegator (`baseline_facade.py:738-780`) — the direct calls in
  `backend/rest_api/tests/test_granular_api_key_scope_865.py:207-226` stay valid. AC-569-20
  pins both paths on one helper.
- **No persisted waiver without reason + audit entry.** Both call sites of `record_waiver` are
  covered: the new `AuditService.suppress_finding` (steps 3 + 8) and the existing gate path
  (`_coerce_waiver_requests` → `_validate_gate_reason`, `baseline_facade.py:723`, audit at
  `:645-657`). `record_waiver` itself is unchanged and only reachable through those two.
- **L1 non-registration is safe as specified.** Every L1 raise site
  (`validate_waiver_reason`, `assert_gate_waiver_authority`) is wrapped by both facades, and the
  existing module-level delegator re-raises `ValidationError`, so the two L1 types cannot reach
  `_service_error_response` on any current path. A future unwrapped caller degrades to a loud
  500 + log — the intended fail-loud behaviour, documented in §3.4.2/N6.
- **MCP codes are genuinely free.** `backend/mcp_server/protocol_handler.py:108-122` ends at
  `RATE_LIMITED: -32007`; `-32008/-32009/-32010` are unused (`grep -3200` across
  `backend/mcp_server/` returns only `-32000…-32007` plus test literals). `ERROR_CODES`
  (`:51-87`) and `ERROR_CODE_MAP` (`:108-122`) both exist and are the right registration points.
  `baseline.waiver_create` is already a declared OP (`backend/audit/models.py:165`), so
  `write_mcp_audit(operation="baseline.waiver_create", …)` is vocabulary-legal.

Residuals (minor, do not block M-B): **R3-02** (numeric code never surfaces on `tools/call`),
**R3-03** (`_validate_gate_reason` is not a `BaselineFacade` method), **R3-08** (the blanket
"`granted_by` is mandatory" claim only holds on the new surfaces).

## 3. AC-569-COMPAT — four parts, verifiable → **yes** (one wording caveat)

- **(a) byte-exact rendering** — the existing test exists and is pinned:
  `backend/application/tests/test_audit_finding_identity_1021.py:115-122`
  (`finding_key("TRACE-P1", ["b","a"]) == "TRACE-P1\x1fa,b"`), and the chain
  `finding_key(r, ids, None) == finding_key(r, ids) == finding_key(r, ids, "")` holds against
  `baseline/waivers.py:91-98`. New test V1 adds a comparison against a real persisted row.
- **(b) legacy rows** — defensive R2a (`record.scope == ""`). Caveat: see **R3-04** — the
  `scope=""` row form is now produced by the *new* `AuditService` path (§1 "zwei Zeilenformen"),
  not by the gate, so calling it "Bestandszeile" is misleading (the gate stamps
  `finding.scope or scope` = `"project"`, `baseline_facade.py:635`).
- **(c) matcher-switch protection on the production-real form** — exactly the rev1 gap: a row
  persisted by a real gate build (`scope="project"`, `scope_artifact_id=""`) must keep
  suppressing after the `suppression_applies` switch. The R2b clause
  (`finding.scope is None` **and** `record.scope_artifact_id == ""`) does match this form
  (verified against `baseline_facade.py:529-534`, `:667-671` and `record_waiver`'s
  `scope or ""` at `waivers.py:178`). V3 is a real, non-tautological gate-level test.
- **(d) mutation probes** — the `waivers.py:96-97` probe genuinely reddens the byte-identity
  test (`"TRACE-P1\x1fa\x1f" != "TRACE-P1\x1fa"`); the R2a/R2b probe genuinely reddens V3
  (`finding.scope is None` + `record.scope="project"` matches neither R2a nor R2c). Both are
  documented rather than automated — see **R3-11** (info).

The R1/R2/R3 rule set is internally coherent for every row/finding combination I checked
(scope-agnostic vs `""`/`"project"`/document-bound records; document finding vs `"project"`
record). AC-569-16 (i)/(ii)/(iii) and AC-569-26 match the clause behaviour.

## 4. Entity delta is correctly scoped → **yes**

§1 states explicitly: **"Die Entität existiert bereits."** `BaselineGateWaiver(TenantScopedModel)`
is in `backend/baseline/models.py:190-269` with `reason`, `granted_by`, `scope`,
`scope_artifact_id`, the unique constraint `(workspace_id, finding_key)` (`:249-252`) and the
non-blank check (`:253-256`); the migrations `0007`/`0008` exist and `0009` is free (highest is
`0008_baseline_gate_waiver_rls.py`). The declared delta is exactly *expiry + surfaces + audit
trail* — no second entity, no second table, no re-derivation of `finding_key`. This is not a
green-field build. No finding.

## 5. Gate semantics §490 → **correct**

E1 (suppressed ⇒ not a blocker) matches the existing key-set behaviour it replaces
(`baseline_facade.py:529-537`, `:667-671`); E2 records the decision threefold
(immutable Description via `_annotate_waiver` `:1205-1211`, append-only waiver row, `AuditLog`);
the `baseline.create` `details` already carry `suppressed_blocker_count`,
`suppressed_rule_ids`, `suppressed_finding_keys`, `waiver_ids` (`:336-344`) and `ServiceBase._audit`
persists `details` since #399 (`application/base.py:197-205`) — the stale comment at
`baseline_facade.py:322-325` is correctly *not* used as a premise. E3 (expired ⇒ stops
suppressing, evaluated at decision time, no job/state) is consistent with
`load_suppressions(..., now=…)` + R3. The GH-400 fail-closed path
(`baseline_facade.py:495-511`) remains un-waivable, as claimed.

## 6. Verification plan §12 (V1–V37) — one non-satisfiable assertion

Every AC has exactly one V-row and each assertion is concrete except **R3-01** (V13/V17/AC-569-13):
the `m7` inequality is false by construction. V4 and V31 carry documentation-only halves
(R3-11, R3-12). No AC is otherwise unfalsifiable or trivially passing; V36 (`ERROR_CODE_MAP`
values, DE+EN keys) and V37 (re-export + 15/4/3 constants) are exact.

## 7. Ratchet compliance → **no increase demanded**

- New interactive elements carry `data-testid` (`audit-waive-<index>`, `audit-waive-dialog`,
  `audit-waive-confirm`, `audit-suppressed-badge-<index>`, `audit-show-suppressed`,
  `audit-count-suppressed`) — §3.6.
- No hardcoded hex: §3.6 forbids new inline `style={{…}}` and mandates CSS modules /
  `var(--…)` tokens / hoisted `CSSProperties`.
- `STYLE_BRACE_BASELINE = 705` (`frontend/src/test/ui-ratchet.test.ts:551`), asserted by exact
  equality (`:1047`) and `<=` (`:1035`); AC-569-23 requires it unchanged and explicitly "nie
  erhöht". No ratchet increase is required.

## 8. Findings

| ID | Severity | Section | Evidence | Fix |
|---|---|---|---|---|
| **R3-01** | **major** | §3.3 (`m7`-Invariante, `:461-465`), AC-569-13 (`:1100-1102`) | `counts.total != counts.blockers + counts.warnings` is unreachable: `AuditReport.to_dict()` computes all three from the same `self.findings` list (`application/audit_service.py:136-151`), and `Severity` has exactly two members `BLOCKER`/`WARNING` (`traceability/audit/types.py:35-36`), so `blockers + warnings == total` is an identity. The same AC states `counts.*` describe the **filtered** list, so the inequality can only hold if `counts.blockers`/`counts.warnings` were computed *pre-filter* — which contradicts M5 ("sie beschreiben, was in `findings` steht") and the BUG-15 contract (`audit_service.py:99-119`). Satisfying AC-569-13 as written would re-introduce the exact non-additive counter re-interpretation rev1's M5 flagged and rev2/rev3 claim to have resolved. | Replace the parenthetical with the intended relation — `counts.total != total_findings_available` (returned window vs. full run) — and state explicitly that `counts.blockers + counts.warnings == counts.total` holds **always** because severity is binary. Do the same at `:461-465` and in AC-569-13. Text-only, no design change. |
| **R3-02** | minor | §3.5 error table (`:738-745`), AC-569-02 (`:989-991`) | `WAIVER_REASON_REJECTED`/`WAIVER_FINDING_NOT_BLOCKING`/`SUPPRESSION_EXPIRED` are **not** in `_PROTOCOL_ERROR_CODES` (`mcp_server/protocol_handler.py:96-103`), so on the standard `tools/call` surface `handle()` takes the `isError: true` branch (`:585-595`) and never emits a numeric JSON-RPC code; `ERROR_CODE_MAP` is consulted only for protocol errors or direct-method dispatch. The table lists `-32008/-32009/-32010` (and `-32004` for `NOT_FOUND`) as if they appear on the wire. AC-569-02's "assert … JSON-RPC `-32008`" would fail against `tools/call`. | State the wire behaviour explicitly: on `tools/call` the three codes surface as `result.isError == true` with the **string** `error_code` (matching every other tool-execution error, e.g. `NOT_FOUND`); the numeric code is assertable via `ERROR_CODE_MAP` or on direct-method dispatch. Adjust AC-569-02's MCP assertion accordingly. (Adding them to `_PROTOCOL_ERROR_CODES` would be a deliberate frame-shape change and is *not* recommended.) |
| **R3-03** | minor | §3.1 (`:247-249`), §3.4.2 table (`:639`), AC-569-29 (ii) (`:1268`) | `BaselineFacade._validate_gate_reason` does not exist. It is a **module-level** function `application.baseline_facade._validate_gate_reason` (`baseline_facade.py:1117`), imported as such by the existing test (`test_baseline_gate_waivers_821.py:35`) and called at `:723` (`_coerce_waiver_requests`) and `:785` (`_validate_override_reason`). | Rename the contract to "module-level `_validate_gate_reason` in `application/baseline_facade`"; keep the delegator at module level so the existing import/usage stays intact. (`_assert_override_permission` *is* a `@staticmethod` — that part is correct.) |
| **R3-04** | minor | §1 table (b) (`:92`), AC-569-COMPAT (b) (`:942-948`) | `scope=""` is now the **new** `AuditService` row form (§1 "zwei Zeilenformen"), not a legacy form: the gate always writes `finding.scope or scope` with a non-empty build scope (`baseline_facade.py:635` → `waivers.py:178`), so no pre-#569 row can carry `scope=""`; the model field is `CharField(blank=True, default="")`, i.e. `NULL` is not even representable. | Reword (b) as the **R2a defensive** case against the new `""` row form (and note `NULL` is hypothetical), keeping (c) as the production-real legacy proof. No rule change. |
| **R3-05** | minor | §3.4.1 E10–E16 (`:592-598`) | The mapping is not fully total: `GET …/audit/waivers/` has no 500 row, and `GET …/audit/` has no 403/500 row. Today `WorkspaceAuditView.get` has only `NotFoundError` → 404 and `except Exception` → 500 (`audit_views.py:155-164`), so a `PermissionDeniedError` from `run_audit` would already be a 500. | Add the missing rows (or add one explicit sentence that pre-existing 403/500 behaviour on the report endpoint is unchanged). |
| **R3-06** | minor | D1 (`:125-128`), §3.4.1 (`:573-579`) | "422 bleibt ausschließlich `POST …/audit/remediate/` vorbehalten" is inaccurate codebase-wide: `rest_api/architecture_decompose_views.py:156` also returns 422 (and `errors.ts:22-29` documents that path). | Scope the claim to "in diesem Modul / auf den neuen Endpunkten"; the invariant that matters ("no new endpoint emits 422") is unaffected. |
| **R3-07** | minor | §3.4.1 E3 vs. E8; §3.3 steps 4 vs. 8 (`:477-479`, `:499-501`) | The precedence for the combined case (request `expires_at <= now` **and** only an expired row exists) is unstated; the ordered steps imply D2 wins (400 before `record_waiver`), but the E-table presents E3 and E8 as independent rows. | State the precedence explicitly: the request-`expires_at` guard (D2/E3) runs before the existing-row check (m1/E8). |
| **R3-08** | minor | §3.4.2 Negativ-Invariante (c) (`:674-678`), §3.2 (`:301-307`) | "(c) `granted_by` ist Pflicht" holds only on the new surfaces. The unchanged gate path persists `granted_by = str(getattr(ctx,"user_id","") or "")` without a blank check (`baseline_facade.py:637`), so a waiver with an empty author remains reachable there — deliberately out of scope. | Qualify the invariant as scoped to the two new surfaces (and optionally note the pre-existing gate-path behaviour as a known, unchanged limitation). |
| **R3-09** | minor | AC-569-30 (`:1282`) vs. §3.3 step 2 (`:472`) | The assertion writes `granted_by == str(ctx.user_id).strip()`, while the service contract is `str(getattr(ctx,"user_id","") or "").strip()`; for `ctx.user_id is None` the two expressions differ (`"None"` vs `""`). | Use the same None-safe expression in the AC. |
| **R3-10** | minor | §9 Rollout (`:1437-1472`) | The user's binding delivery constraint "PR must carry `Closes #569`" is not stated anywhere in the spec (only in the bundle plan `2026-09-21-open-issues-bundle.md:49,193`). | Add the `Closes #569` requirement to §9 (and, while there, the branch statement is already correct: `feat/se-audit-waivers` off `origin/main`). |
| **R3-11** | info | AC-569-COMPAT (d) (`:963-969`), §12 V4 | The mutation probes are documented in test docstrings, not automated; a docstring can claim a probe it never performed. This is the same pattern accepted in rev1/rev2. | Optional: note the probe procedure in the PR description, or add a `# mutation-probe:` marker so a reviewer can re-run it manually. |
| **R3-12** | info | §12 V31 (`:1587`) | The second half of V31 ("§8 Threat-Model-Fragen (1)–(4) je beantwortet") is a documentation assertion, not a test. | Keep it in §8; drop it from the test-assertion cell (or mark it "doc, not test"). |
| **R3-13** | info | §3.4.2 registration duty 4 (`:670-672`) | Phrasing "erhält Einträge in `ERROR_CODES` und `ERROR_CODE_MAP`: `WAIVER_REASON_REJECTED: -32008`" mismatches the real shapes: `ERROR_CODES` maps name → message string, `ERROR_CODE_MAP` maps name → int (`protocol_handler.py:51-122`). Intent is clear and AC-569-32/V36 is consistent. | Rephrase to "message entry in `ERROR_CODES` + numeric entry in `ERROR_CODE_MAP`". |
| **R3-14** | info | §3.1 R2 (`:219-222`) | "genau eine der drei Klauseln muss greifen" is imprecise: R2a and R2b can both be true (`record.scope == ""`, `finding.scope is None`, `record.scope_artifact_id == ""`). Boolean-OR semantics are correct, the wording is not. | Say "mindestens eine greift" (or "OR over R2a–R2c"). |
| **R3-15** | info | E5 (`:587`) vs. Non-Goal (`:1348-1350`) | The same condition yields `400 WAIVER_FINDING_NOT_BLOCKING` on the new endpoint and `400 VALIDATION_ERROR` on the legacy `waived_findings` path. Deliberate, status-consistent, documented. | None. |

## 9. Rulings on the five flagged open points

1. **O1 — Revoke / re-grant path.** **Acceptable as specified.** Out of #569 scope, correctly
   flagged as a product decision (§7, §8 O1, Risiko 7). Two consequences are already covered:
   the baseline `override_reason` remains the coarse escape hatch (E4, `baseline_facade.py:539-556`),
   and a wrong waiver is never hidden (row + audit trail remain). One recommendation: because
   409 (`SUPPRESSION_EXPIRED`) is not client-resolvable while O1 is open, state that explicitly
   in §3.4.1 (the 409 rationale currently reads as if the client could "resolve and resubmit",
   which only becomes true once O1 ships).
2. **D2 — strictness on an already-expired `expires_at`.** **Acceptable as specified.** Rejecting
   `expires_at <= now` with 400 is deterministic, state-independent, and prevents a no-op row.
   Required change is only the precedence note **R3-07** (D2/E3 must be stated to win over m1/E8
   when both apply).
3. **`granted_by` blank → 403 vs 400.** **Acceptable as specified (403).** Attribution failure is
   an authorization concern, consistent with E6; a `granted_by` key in the body is a separate,
   correct 400 via `UnknownFieldRejectionMixin` (`serializers.py:663-695`). Required change:
   align the AC expression (**R3-09**) and scope the blanket invariant (**R3-08**).
4. **MCP numeric codes `-32008/-32009/-32010`.** **Acceptable as specified; codes are free**
   (highest registered server code is `RATE_LIMITED: -32007`, `protocol_handler.py:121`).
   Required change: clarify the wire behaviour (**R3-02**) so the AC assertion matches the
   `isError` branch.
5. **DE/EN wording.** **Acceptable as specified.** `_ERROR_MESSAGES` requires both languages
   (`serializers.py:85-86`) and AC-569-32/V36 pins a non-empty DE **and** EN entry per new code;
   authoring the strings is ordinary i18n work, not a contract gap. Optional: pin the exact
   strings in §3.4.2 to remove the last authoring degree of freedom.

## 10. Binding-constraint check

- **Branch:** `target_branch: feat/se-audit-waivers (cut from origin/main 564e62ab)` — matches the
  user constraint and correctly overrides the rev2 `fix/se-audit-trace-p1-cycle` recommendation
  (frontmatter `:12-13`). ✔
- **`finding_key` positional compatibility:** signature unchanged, `scope=None` third positional
  arg preserved, AC-569-COMPAT(a)/AC-569-33 pin rendering + re-export; `load_waived_finding_keys`
  keeps the 2-arg positional form with keyword-only `now` (AC-569-24, matches
  `waivers.py:126-128`). ✔
- **`Closes #569`:** not stated in the spec — **R3-10**. ✖ (minor)

## 11. Verdict

**CHANGES_REQUESTED.**

M-A **resolved**, M-B **resolved**; N1–N6 all resolved (N3: the "34 ACs" count is correct —
1 + 16 + 11 + 6; N4: AC-569-24's premise is corrected and the duplicate "When" is gone; N5:
`suppressed_finding_keys` is removed from §3.3 and §7; N6: registration duties + the deliberate
L1 non-registration are explicit). AC-569-COMPAT's four parts are genuinely verifiable, the
entity delta is correctly framed as "exists already, add expiry + surfaces", the gate semantics
are right, and no ratchet increase is demanded.

The single blocker is **R3-01**: AC-569-13 (and its §3.3 `m7` rationale) asserts a counter
relation that cannot hold without re-introducing the non-additive `counts` re-interpretation
that M5 claims to have fixed. It is a text-only repair, but it is normative and currently
unsatisfiable, so the spec is not yet implementation-ready. With R3-01 fixed (and R3-02/R3-03
worth taking in the same pass), the concept is ready to hand off to `requirements`/`se-requirements`.
