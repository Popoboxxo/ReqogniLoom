---
type: REVIEW
scope: "#569 / docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec.md"
status: done
date: 2026-09-22
author_agent: concept-reviewer
reviewer: concept-reviewer
reviewed_artifact: docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec.md
revision_reviewed: 3
review_iteration: 2
supersedes_review: docs/superpowers/plans/2026-09-22-se-auditor-waivers-569-spec-review-rev3.md
issue: "#569"
branch: feat/se-validation-completeness
verdict: APPROVED
findings:
  critical: 0
  major: 0
  minor: 0
  info: 1
resolution:
  R3-01: resolved
  R3-02: resolved
  R3-03: resolved
  R3-04: resolved
  R3-05: resolved
  R3-06: resolved
  R3-07: resolved
  R3-08: resolved
  R3-09: resolved
  R3-10: resolved
  R3-11: resolved
  R3-12: resolved
  R3-13: resolved
  R3-14: resolved
  R3-15: not-applicable-accepted
---

# Iteration-2 Re-Review — #569 Spec, Revision 3 (SE-Auditor Waivers)

Read-only verification of the **iteration-2 response** to `…-spec-review-rev3.md`
(`CHANGES_REQUESTED`; 0 critical, 1 major = R3-01, 9 minor = R3-02…R3-10, 5 info =
R3-11…R3-15). Method: every `resolved` claim of the new `## Changelog — Iteration 2`
table (`:40-65`) was re-checked against the current spec text **and** against the actual
`file:line` source — the author's citations were re-derived independently, not accepted on
faith. **No spec or source file was modified**; this review is the only artifact written.

**Result in one line:** the single blocking item **R3-01 is genuinely closed** (the
unreachable `counts` inequality is replaced by the correct pair, and it is now testable), all
nine minors and the five infos are addressed, `not-applicable` for R3-15 is acceptable, and no
AC was weakened, deleted or made trivially passing. **The spec is implementation-ready.**

---

## 1. R3-01 (major) — `m7` invariant / AC-569-13 → **RESOLVED**

**Re-derived identity (independent of the author's citation).**

`backend/application/audit_service.py:136-151` (`AuditReport.to_dict`) computes all three
counters from the **same** `self.findings` list:

```python
blockers = sum(1 for fv in self.findings if fv.finding.severity is Severity.BLOCKER)
warnings = sum(1 for fv in self.findings if fv.finding.severity is Severity.WARNING)
"counts": {"total": len(self.findings), "blockers": blockers, "warnings": warnings},
```

`backend/traceability/audit/types.py:26-36` — `class Severity(str, Enum)` has **exactly two**
members `BLOCKER`/`WARNING`. Therefore every item in `findings` is counted by exactly one of
the two sums, i.e. `counts.blockers + counts.warnings == counts.total` is an **identity in
`self.findings`** and can never be broken *inside* `counts`. The pre-existing absolute counters
`total_findings_available`/`total_blockers_available`/`total_warnings_available`
(`audit_service.py:99-129`) describe the pre-cap run, so the only reachable inequality is
between `counts.*` (returned window) and `total_*_available` (full run).

**Verification of the three required sub-conditions:**

| Requirement | Spec location | Verified |
|---|---|---|
| (i) internally consistent | §3.3 `:519-531`; AC-569-13 `:1217-1221`; V17 `:1704` | New text states the **unconditional** identity `counts.blockers + counts.warnings == counts.total` (severity binary) and, separately, `counts.total != total_findings_available` only *when* filtered/capped. The old unreachable `counts.total != counts.blockers + counts.warnings` survives **only** as the explicitly disowned "would be arithmetically unreachable and is therefore not part of the contract" sentence (`:530-531`, `:1220-1221`). No contradiction. |
| (ii) actually testable | V17 `:1704` | Two concrete assertions: `counts["blockers"] + counts["warnings"] == counts["total"]` **in both modes**, and (filter-active) `counts.total == len(findings)` + `counts.total != total_findings_available` + `total_findings_available == len(findings) + suppressed_filtered`. All four are satisfiable from `to_dict()` plus the specified filter/cap contract. |
| (iii) faithful to M5 / BUG-15 | §3.3 `:492-511`, §3.3 `:516-524` | `counts.*` remains **descriptive** of `findings`; the absolute/available split is unchanged except that "filtered" joins "capped" as a window cause. `suppressed_filtered` (`:523-524`) makes the difference explainable. No counter is re-interpreted. |

**The required pair is present verbatim:** the contract is now
`counts.blockers + counts.warnings == counts.total` (**always**) **AND**
`counts.total != total_findings_available` (when filtered/capped), with `suppressed_filtered`
supplying the explanation. ✔

**Sweep of every remaining AC mentioning `counts` for a reintroduced unreachability:**

| AC / V | `counts` usage | Reachable? |
|---|---|---|
| AC-569-05 / V9 `:1131`, `:1696` | `counts == {"active": 1, "expired": 1}` (waiver-list shape, not the report) | ✔ distinct object, no inequality |
| AC-569-07 / V11 `:1150`, `:1698` | `counts["suppressed"] >= 1` | ✔ trivially satisfiable, no arithmetic claim |
| AC-569-13 / V17 `:1217-1221`, `:1704` | identity + window inequality | ✔ as above |
| AC-569-27 / V31 `:1363-1365`, `:1718` | `counts.total == len(findings)` **and** `total_findings_available == len(findings) + suppressed_filtered` (uncapped) | ✔ both derived from the same specified contract; mutually consistent with V17 |

No AC reintroduces an intra-`counts` inequality. The author's claim that AC-569-27/V31 and
AC-569-07 are clean is **confirmed**.

---

## 2. The minors R3-02 … R3-10 — spot-check against source

| Finding | Author claim | Your verification (exact evidence) | Verdict |
|---|---|---|---|
| **R3-02** MCP wire behaviour | `isError:true` + string code, no numeric code on `tools/call` | `_PROTOCOL_ERROR_CODES` (`protocol_handler.py:96-103`) contains only PARSE/INVALID/UNKNOWN/AUTH/PERMISSION/FEATURE — the three new codes are absent. The `tools/call` branch at `:585-595` returns `format_jsonrpc_result(request_id, {"content":[…], "isError": True})` — a **successful result, no numeric JSON-RPC code**. `ERROR_CODE_MAP` ends at `RATE_LIMITED: -32007` (`:121`), so `-32008/-32009/-32010` are free. Spec §3.5 `:845-858`, AC-569-02 `:1104-1107`, V6 `:1693`. | **resolved** (+ info note, §5) |
| **R3-03** `_validate_gate_reason` scope | module-level function, not a `BaselineFacade` method | `baseline_facade.py:1117` is a **module-level** `def _validate_gate_reason(reason: str, *, label: str) -> str:` (no class/self). Spec now says module-level in §3.1 `:290-297`, §3.4.2 table `:728`, AC-569-29(ii) `:1387`, §7 `:1472`. | **resolved** |
| **R3-04** row-form (b)/(c) reword | (b) = defensive coverage of the **new** `scope=""` form; (c) = production-real `"project"` | `baseline_facade.py:635` `scope=finding.scope or scope`; `waivers.py:178` `"scope": scope or ""`; `models.py:230` `CharField(max_length=32, blank=True, default="")` (so `NULL` is not representable — as stated). Spec §1 `:126-131`, `:137-143`; AC-COMPAT(b) `:1051-1059`; (c) `:1061-1072`. | **resolved** |
| **R3-05** GET status totality | new E19/E20 rows | `WorkspaceAuditView.get` (`audit_views.py:134-164`) has **only** `NotFoundError`→404 and `except Exception`→500 — exactly as the spec's totality paragraph claims. E19/E20 added (`:673-674`), paragraph `:676-683`, referenced by AC-569-28 `:1371` and V32 `:1719`; E14 has deliberately no 403 (a `PermissionDeniedError` from `run_audit` would indeed be a 500 today). | **resolved** |
| **R3-06** "422 only in remediate" | scoped to this audit module | `architecture_decompose_views.py:149-156` returns `HTTP_422_UNPROCESSABLE_ENTITY` for `DecompositionAuditError`. Spec now scopes the claim in D1 `:162-168`, §3.4.1 `:642-651` and §7 `:1466-1468`, naming `architecture_decompose_views.py:156` as outside/untouched. | **resolved** |
| **R3-07** E3 vs E8 precedence | request `expires_at` guard (E3/400) runs before the existing-row check (E8/409) | Spec §3.3 step 8 `:567-569`, E8 row `:662`, 409 RFC bullet `:704-706`. Internally consistent with the ordered steps (step 4 `:543-545` precedes step 8 `:565`). | **resolved** |
| **R3-08** `granted_by` invariant scope | scoped to the two new surfaces; gate path unchanged | Gate path `baseline_facade.py:637` persists `granted_by=str(getattr(ctx, "user_id", "") or "")` with **no** blank check — confirmed. Spec §3.2 `:349-365` and §3.4.2 negative invariant `:766-773` scope the rule and label the pre-existing `granted_by=""` rows as deliberately out of scope. | **resolved** |
| **R3-09** None-safe formula | `str(getattr(ctx, "user_id", "") or "").strip()` | §3.3 step 2 `:538`, AC-569-30 `:1403`, V34 `:1721` all use the None-safe form and explicitly pin `None ⇒ ""` (not `"None"`). | **resolved** |
| **R3-10** `Closes #569` | new §9 bullet | §9 `:1596-1600` "PR-Pflicht … trägt `Closes #569`", plus target branch `feat/se-audit-waivers` off `origin/main 564e62ab`. | **resolved** |
| **R3-11** mutation-probe marker | `# mutation-probe:` marker + PR description | AC-COMPAT(d) `:1080-1083` requires the marker and the PR procedure. | **resolved** |
| **R3-12** V31 doc half | threat model flagged as documentation duty | V31 `:1718` states "**Doku-Pflicht, keine Test-Assertion**". | **resolved** |
| **R3-13** `ERROR_CODES` shape | "Name → message string" + `ERROR_CODE_MAP` "Name → int" | §3.4.2 duty 4 `:759-764` rephrased exactly so, and explicitly distinguished from `_PROTOCOL_ERROR_CODES` (verified against `protocol_handler.py:51-103`). | **resolved** |
| **R3-14** R2 clause wording | "OR over R2a–R2c, at least one" | §3.1 R2 `:260` now reads "OR über R2a–R2c: **mindestens eine** Klausel muss greifen, mehrere dürfen zugleich wahr sein". | **resolved** |

---

## 3. R3-15 — dual error codes for one condition → **`not-applicable` accepted**

Premise re-verified: `rest_api/views.py:169-190` maps `ValidationError` → **400** and
`:192-206` maps it → `VALIDATION_ERROR`, keyed by **exact** type (`:166-168`). The legacy
`waived_findings` path raises plain `ValidationError` (`baseline_facade.py:619-627`), so it
returns `400 VALIDATION_ERROR`. The new surface returns `400 WAIVER_FINDING_NOT_BLOCKING`
(§3.4.1 E5 `:659`; §3.4.2 `:731`).

**Ruling:** the author's `not-applicable` is **acceptable**. Both responses are the same status
(400) for the same condition; the codes differ only to let the new UI show a specific message
(`audit.waiveNotBlocking`, §3.6 `:894-895`) while the unchanged legacy contract keeps its code
(§7 Non-Goal `:1471-1473`). Unifying them would either break the legacy client contract or
weaken the new surface's specificity — both worse than the documented divergence. This matches
my own rev3 ruling (R3-15, "Fix: None"). Not blocking, no change required.

---

## 4. Regression check

- **AC count:** §6 `:1259` says **34** = `AC-569-COMPAT + AC-569-01…16 + AC-569-17…27 +
  AC-569-28…33` = 1 + 16 + 11 + 6. Enumerated IDs in §6 are complete and unique — ✔.
- **Verification plan V1–V37:** all 37 rows present and 1:1 to the ACs (V1–V4 = COMPAT a–d;
  V5–V17 = AC-01…13; V18–V21 = AC-14…17; V22–V31 = AC-18…27; V32–V37 = AC-28…33). No AC lacks a
  V-row and no V-row references a missing AC — ✔.
- **AC-569-COMPAT four-part and verifiable:** (a) byte-exact rendering `:1041-1049`,
  (b) defensive R2a `:1051-1059`, (c) matcher-switch on the production-real form `:1061-1072`,
  (d) two mutation probes `:1074-1083`. Each has an explicit `Datei::Test` and a falsifiable
  assertion — ✔.
- **No AC weakened / deleted / trivially passing:** the iteration-2 changes are precision-only;
  AC-569-13 gained assertions (not lost them); AC-569-02's numeric-code assertion moved to V36
  rather than being dropped; AC-569-27/V31 gained a concrete value equality; no AC was removed.
  No newly-passing assertion is vacuous — ✔.
- **Binding user constraints survived:** `feat/se-audit-waivers` off `origin/main 564e62ab`
  (frontmatter `:16`, §9 `:1598-1600`); `Closes #569` (§9 `:1596`); positional
  `finding_key(rule_id, artifact_ids, scope=None)` unchanged (§3.1 `:203-208`, AC-COMPAT(a),
  AC-569-33) — ✔.

**Method limitation (stated honestly):** the rev3 document is untracked, so no byte-diff against
revision-3-on-disk was possible. The regression check therefore rests on (a) the current
document's internal consistency, (b) the rev3 review's own quoted evidence (`:461-465`,
`:1100-1102`), and (c) line-number deltas consistent with additive text. No counter-evidence of a
weakened AC was found.

---

## 5. Non-blocking note (info, R3-02 residual)

The spec's §3.5 sentence (`:845-850`) and AC-569-02/V6 (`:1104-1107`, `:1693`) describe the
`tools/call` error as carrying a "String-`error_code`". At the **raw JSON-RPC frame** level the
`isError` result carries only `content` + `isError` (verified: `protocol_handler.py:585-595`;
`test_protocol_handler.py:383-407`; `test_llm_timeout_error_mapping.py:195-203`) — the string code
lives on the handler's `ToolResult.error_code` (`ToolResult.__init__`, `:136-149`), which is how
every existing tool-group test asserts it (`test_audit_tool_group.py:185,303,…`). The normative
claim ("no numeric code on `tools/call`") is correct; the phrase is only ambiguous about the
level. **Implementer guidance:** assert `result.error_code == "WAIVER_REASON_REJECTED"` on the
`ToolResult` returned by the handler (existing convention), and `frame["result"]["isError"] is
True` on the frame — no spec change needed. This is the only residual from the entire review; it
does not block.

---

## 6. Verdict

**APPROVED.**

R3-01 — the single blocker — is genuinely resolved: the corrected §3.3 `m7` block and
AC-569-13 now assert the reachable, independently re-derived pair
`counts.blockers + counts.warnings == counts.total` (always) **and**
`counts.total != total_findings_available` (filtered/capped), with `suppressed_filtered` making
the difference explainable and the M5/BUG-15 descriptive-vs-absolute split intact. The
`counts` sweep found no reintroduced unreachability. All nine minors and five infos are
addressed against the cited source, `not-applicable` for R3-15 is accepted, and no AC was
weakened, deleted or made trivially passing; the 34-AC set, the V1–V37 plan, the four-part
AC-569-COMPAT and the binding constraints all hold.

**Implementation may start.**

*Non-blocking note the implementer must respect:* assert the MCP error code on
`ToolResult.error_code` (handler level) plus `frame["result"]["isError"] is True`, per §5 above.
