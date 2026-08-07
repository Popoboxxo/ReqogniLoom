# Task 3 Report: Split roles (RBAC) from process skills (methodology)

## Pre-check findings (per brief's "Important pre-check before Step 1")

All 5 role files already existed on disk, matching the brief's assumed "existing role" shape
closely:

- `requirements-architect.md`, `test-engineer.md`, `risk-analyst.md`, `change-manager.md`,
  `quality-auditor.md` — all `version: 1.0.0`, `compatible_with: "reqogniloom>=1.0.0"`, with a
  smaller `tools:` whitelist than the brief's target (missing the newly-available tool groups:
  `goal.*`, `diagram.*`, `baseline.*`, `review.*`, `change_request.*`, `custom_field.*`,
  `traceability.create_link`, `ai_derivation.suggest_architecture_for_requirement`,
  `ai_derivation.derive_risks_from_architecture`), each with a "Domain model you must know" +
  "Workflow" body — exactly the conflation the brief describes. Safe to fully replace with the
  Step 10-14 thinned content.

Cross-checked every tool name in the brief (both `EXPECTED_TOOLS_BY_ROLE` and the Step 10-14 role
frontmatter) against the current, already-committed `docs/agent-templates/tool-manifest.json`
(143 tools, Task 1's real output): **no drift found** — every tool the brief lists exists in the
manifest with the exact same name (including `traceability.create_link`, all `review.*`,
`baseline.*`, `change_request.*`, `diagram.*`, `goal.*`/`main_goal.*`, `custom_field.*`, and the
two new `ai_derivation.*` tools). `quality-auditor`'s whitelist is confirmed all-read (`.get`/
`.query`/`.list`/`.compare`/`.read`) against the manifest's `is_write` field. `change-manager`'s
whitelist correctly omits `change_request.delete` even though that tool exists in the manifest —
matches the brief's stated intent (reject/outdate instead of hard-delete).

## What was implemented

Followed the brief's Steps 1-14 essentially verbatim:

1. Wrote both test files (`test_role_tools_exist_in_manifest.py`,
   `test_process_skills_reference_real_tools.py`) exactly as specified — confirmed they FAIL
   before any content files exist (5 of 6 collected tests failed, 1 trivially passed since it
   only needs the manifest which was already present).
2. Created `docs/agent-templates/DOMAIN_MODEL.md` verbatim from the brief.
3. Created the 5 `docs/agent-templates/skills/<name>/SKILL.md` files, with three small additions
   beyond the brief's literal text (see "Discrepancies found" below).
4. Created `docs/agent-templates/skills-tool-refs.json`, with the same three additions applied to
   keep it in sync with the skill text and the roles' tool whitelists.
5. Replaced the 5 role files with the brief's Step 10-14 content verbatim (tool whitelists,
   `process_skill:` pointer, review-policy sections all unchanged from the brief).
6. Ran both new test files — all 6 tests pass.

## Discrepancies found between the brief and a self-consistent result

The brief's own `EXPECTED_TOOLS_BY_ROLE`/Step 10-14 role whitelists were internally consistent
against the manifest, but **not** internally consistent against the brief's own
`skills-tool-refs.json` (Step 9) and `SKILL.md` prose (Steps 4-8) — i.e.
`test_no_tool_appears_in_a_role_without_appearing_in_its_skill_refs` failed three times in a row
against the brief's literal Step 9 JSON, listing tools present in a role's whitelist but never
mentioned in that role's own `skills-tool-refs.json` entry (and, for two of them, never mentioned
in the `SKILL.md` prose either):

1. `requirements-architect` whitelists `requirement.derive`, absent from
   `vmodell-decomposition`'s refs list and never mentioned in its `SKILL.md`. Fixed by adding a
   sentence to `SKILL.md` step 3 distinguishing it from the needs-scoped derivation tools
   (generic requirement-from-requirement derivation) and adding it to the refs list.
2. `change-manager` whitelists `baseline.list`, `change_request.update`, `diagram.outdate`,
   `diagram.reactivate`, `issue.update` — none in `ccb-approval-and-baseline`'s refs list, and
   only `diagram.outdate`/`.reactivate` were implicitly covered by prose (via "same
   outdate-vs-delete distinction" language that didn't actually name them). Fixed by extending
   the `SKILL.md` prose (steps 2, 3, 5) to explicitly name all five tools and adding them to the
   refs list.
3. `quality-auditor` whitelists `custom_field.get`/`custom_field.query`, absent from
   `traceability-audit`'s refs list and not mentioned in its `SKILL.md`. Fixed by adding a
   sentence to step 1 and adding both to the refs list.

I judged these as the brief's own drift (a genuine gap between its Step 9/frontmatter content and
its own Step 15 "PASS (6 tests)" expectation) rather than a reason to weaken the test — the fix
in all three cases was to make the skill documentation actually match its role's tool whitelist,
which is exactly what the test is designed to catch. No role's `tools:` whitelist and no test
assertion was altered; only the three `SKILL.md` files and the sidecar JSON were extended.

## Test output

```
docs/agent-templates/test_role_tools_exist_in_manifest.py::test_every_role_tool_exists_in_manifest PASSED
docs/agent-templates/test_role_tools_exist_in_manifest.py::test_quality_auditor_stays_strictly_read_only PASSED
docs/agent-templates/test_role_tools_exist_in_manifest.py::test_every_role_points_at_its_process_skill PASSED
docs/agent-templates/test_role_tools_exist_in_manifest.py::test_no_tool_appears_in_a_role_without_appearing_in_its_skill_refs PASSED
docs/agent-templates/test_process_skills_reference_real_tools.py::test_skills_tool_refs_only_lists_real_tools PASSED
docs/agent-templates/test_process_skills_reference_real_tools.py::test_every_skill_file_exists_with_valid_frontmatter PASSED
6 passed in 0.16s
```

Run via the repo's `.venv` (`./.venv/Scripts/python.exe -m pytest ...`), per the brief's Docker/DB
note — no Docker/DB needed, these tests only read JSON/YAML/Markdown files.

## Environment note

`python`/`python3` were not on PATH in the Git Bash shell used for this session (Windows Store
alias shadowing); `C:\Repositories\ai-native-reqflow-POC\.venv\Scripts\python.exe` (with `pyyaml`
and `pytest` already installed) was used instead. No Docker was needed for this task.

## Repo-state note (unrelated to this task)

`AGENTS.md` and `CLAUDE.md` at the repo root were already modified (untouched by this task) before
this session started — left as-is, not staged, not committed by the git-agent delegation for this
task's commit.

## Files changed

New:
- `docs/agent-templates/DOMAIN_MODEL.md`
- `docs/agent-templates/skills/vmodell-decomposition/SKILL.md`
- `docs/agent-templates/skills/test-lifecycle/SKILL.md`
- `docs/agent-templates/skills/risk-derivation/SKILL.md`
- `docs/agent-templates/skills/ccb-approval-and-baseline/SKILL.md`
- `docs/agent-templates/skills/traceability-audit/SKILL.md`
- `docs/agent-templates/skills-tool-refs.json`
- `docs/agent-templates/test_role_tools_exist_in_manifest.py`
- `docs/agent-templates/test_process_skills_reference_real_tools.py`

Modified (thinned to RBAC identity only):
- `docs/agent-templates/requirements-architect.md`
- `docs/agent-templates/test-engineer.md`
- `docs/agent-templates/risk-analyst.md`
- `docs/agent-templates/change-manager.md`
- `docs/agent-templates/quality-auditor.md`

Commit was delegated to the `git` agent per this project's rule that git mutations (add/commit)
route through the `git` agent, not the developer role directly (the repo's `orchestrator-guard.sh`
hook also structurally blocks direct `git add`/`commit` in Bash calls from non-`git`/
non-`orchestrator` roles). See the `git` agent's completion for the actual commit hash.

Original commit: `531e4ab4` — "feat: split agent roles (RBAC) from process skills (methodology)".

---

## Review fix round 1 (2026-08-07)

Coordinator review flagged two Important findings against the `531e4ab4` commit. Both fixed below.

### Finding 1 — bare, unexplained tools in prose

Confirmed: `skills-tool-refs.json` (the hand-authored sidecar) already listed every tool each
role whitelists, but several of those tools were never actually named in the corresponding
`SKILL.md`'s prose — a bare presence in the sidecar, no real sentence anywhere in the markdown
body. Fixed by extending existing workflow-step sentences (no new steps added, per the review's
guidance) in all 5 skill files:

- `skills/vmodell-decomposition/SKILL.md` — step 2 now explains `needs.read` (fetch a need by ID)
  and `needs.get_traces` (see which requirements were already derived from it); step 4 now
  explains `requirement.get`/`requirement.query` (fetch-by-ID vs. search-by-criteria, before
  decomposing) and `requirement.update` (revise the source requirement directly without
  re-running decompose/derive).
- `skills/test-lifecycle/SKILL.md` — step 3 now explains `test.get`/`test.query` (check for an
  existing case by ID/criteria before creating a duplicate).
- `skills/risk-derivation/SKILL.md` — step 5 now explains `risk.read` (fetch a known risk by ID
  when revisiting an assessment).
- `skills/ccb-approval-and-baseline/SKILL.md` — step 2 now explains `adr.read`, `issue.create`,
  and `issue.read`; step 3 now explains `change_request.read`/`change_request.query`; step 5 now
  explains `diagram.get`/`diagram.query` (look up the current diagram before updating it).
- `skills/traceability-audit/SKILL.md` — step 2 now explains `requirement.get`/`architecture.get`/
  `test.get` (drill into a specific element a query surfaced); step 5 now explains `goal.read`
  (fetch a goal by ID after `goal.query` narrowed it down), `baseline.get` (fetch a specific
  baseline by ID), and `change_request.read` (fetch a specific Change Request by ID).

`skills-tool-refs.json` itself needed no changes for Finding 1 — it already listed all these
tools; the gap was purely between the sidecar and the actual prose, which is exactly what
Finding 2's stronger test now catches directly.

### Finding 2 — the guard test couldn't catch Finding 1's pattern

Added a new test, `test_every_whitelisted_tool_is_named_in_its_skill_prose`, to
`docs/agent-templates/test_role_tools_exist_in_manifest.py` (extended the existing file, not a
new one — kept the fix minimal per the review's instruction). For each role, it reads the actual
`SKILL.md` body (frontmatter stripped), and asserts every tool in the role's `tools:` whitelist
appears backtick-quoted (`` `tool.name` ``) somewhere in that body text — the exact citation
pattern every skill already uses throughout its prose. This checks the real markdown, not the
hand-maintained `skills-tool-refs.json` sidecar, so it can no longer be fooled by a sidecar that
was kept "in sync" with the whitelist alone while the prose itself stayed silent on a tool.

**This test is not hypothetical — it fired for real during this fix**, independent of the
coordinator's finding list: it caught `change-manager.md`'s whitelisted `change_request.reactivate`
appearing in `ccb-approval-and-baseline/SKILL.md` only as the shorthand
`` `change_request.outdate`/`.reactivate` `` (the second tool name elided after the shared
`change_request.` prefix) rather than fully backtick-quoted on its own. Fixed by spelling out
`` `change_request.reactivate` `` in full. This is direct evidence the new test enforces the
constraint for real, not just against the specific tools named in the review.

### Test output after both fixes

```
docs/agent-templates/test_role_tools_exist_in_manifest.py::test_every_role_tool_exists_in_manifest PASSED
docs/agent-templates/test_role_tools_exist_in_manifest.py::test_quality_auditor_stays_strictly_read_only PASSED
docs/agent-templates/test_role_tools_exist_in_manifest.py::test_every_role_points_at_its_process_skill PASSED
docs/agent-templates/test_role_tools_exist_in_manifest.py::test_no_tool_appears_in_a_role_without_appearing_in_its_skill_refs PASSED
docs/agent-templates/test_role_tools_exist_in_manifest.py::test_every_whitelisted_tool_is_named_in_its_skill_prose PASSED
docs/agent-templates/test_process_skills_reference_real_tools.py::test_skills_tool_refs_only_lists_real_tools PASSED
docs/agent-templates/test_process_skills_reference_real_tools.py::test_every_skill_file_exists_with_valid_frontmatter PASSED
7 passed in 0.15s
```

### Files changed in this round

- `docs/agent-templates/skills/vmodell-decomposition/SKILL.md`
- `docs/agent-templates/skills/test-lifecycle/SKILL.md`
- `docs/agent-templates/skills/risk-derivation/SKILL.md`
- `docs/agent-templates/skills/ccb-approval-and-baseline/SKILL.md`
- `docs/agent-templates/skills/traceability-audit/SKILL.md`
- `docs/agent-templates/test_role_tools_exist_in_manifest.py` (new test added)

Committed as a new commit (not amended), delegated to the `git` agent for the same
`orchestrator-guard.sh` reason as the original commit.
