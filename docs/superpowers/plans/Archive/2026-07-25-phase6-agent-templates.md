# Phase 6 — Agenten-Templates für Downstream-Projekte — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish 5 provider-agnostic, agent-meta-compatible agent template files plus a bootstrap
snippet and an optional Claude Code review-policy hook under `docs/agent-templates/`, so a
downstream project can install agents that talk to ReqogniLoom's MCP server.

**Architecture:** Pure Markdown/YAML content + one Bash reference script. No application code,
no ReqogniLoom runtime changes. Each role file is a self-contained Markdown document with a YAML
frontmatter block (`name`, `version`, `description`, `compatible_with`, `tools`) followed by a
prose system-prompt body. "Tests" for this plan are structural validations (YAML parses, every
listed tool name exists in the MCP tool registry, no placeholder markers) rather than unit tests
of behavior, since there is no executable application logic to exercise.

**Tech Stack:** Markdown, YAML frontmatter, Bash (for the optional hook script), Python 3 (used
ad-hoc via `python3 -c` for YAML-parse validation — already available in the backend container /
dev environment per `CLAUDE.md`).

## Global Constraints

- Ablageort: `docs/agent-templates/` (spec §2) — not in the `agent-meta` submodule.
- Frontmatter fields, in this exact order, on every role file: `name`, `version`, `description`,
  `compatible_with`, `tools` (spec §5).
- `compatible_with` value on every role file: `"reqogniloom>=1.0.0"` (spec §5, matches the current
  root `VERSION` file).
- `tools` lists are closed whitelists — the exact tool names from spec §5.1–§5.5, verified in this
  session against `backend/mcp_server/tool_registry.py` and the individual tool-group files under
  `backend/mcp_server/tools/`. No wildcards, no additional tools beyond what's listed below.
- Domain knowledge each role file must state in its own body text (not by reference to another
  file): REQ-ID schema (`REQ-L0-*`…`REQ-L3-*`), the 8 trace-link types, the 3 rigor presets, the 3
  baseline scopes (only for `change-manager`/`quality-auditor`), V-model L0–L4, configurable
  workflow state machines (only for `change-manager`) — per spec §4.
- Review-profile value stated in each role file's body: `requirements-architect` →
  `review_changes`; `test-engineer` → `auto`; `risk-analyst` → `review_high_risk`;
  `change-manager` → `review_high_risk`; `quality-auditor` → `auto` (read-only, no tools with
  `create`/`update`/`delete` semantics) — per spec §3.
- No TODO/TBD/placeholder markers in any shipped file (spec §8 DoD).
- Commit message language: English, Conventional Commits format, `docs:` type, no REQ-ID (this is
  a documentation/template deliverable, not application code) — per `.claude/rules/commit-conventions.md`.
- Stay on the current branch (`feat/reqogniloom-vision-consolidation`) — do not create a new
  branch; per `.claude/rules/branch-guard.md` a branch is already open and in progress.
- All mutating git commands go through the `git` agent, per `.claude/rules/use-orchestrator.md`.

---

### Task 1: `requirements-architect.md`

**Files:**
- Create: `docs/agent-templates/requirements-architect.md`

**Interfaces:**
- Produces: the `requirements-architect` role file, referenced by `README.md` (Task 7) and
  `BOOTSTRAP.md` (Task 7).

- [ ] **Step 1: Write the file**

```markdown
---
name: requirements-architect
version: 1.0.0
description: Captures stakeholder needs and derives/decomposes requirements across the V-Modell (L0-L3) via ReqogniLoom's MCP server.
compatible_with: "reqogniloom>=1.0.0"
tools:
- needs.read
- needs.create
- needs.update
- needs.get_traces
- needs.derive_requirements
- requirement.get
- requirement.query
- requirement.create
- requirement.update
- requirement.decompose
- requirement.validate
- requirement.derive
- requirement.check_consistency
- ai_derivation.derive_requirements_from_need
- ai_derivation.decompose_requirement_next_level
- traceability.query
- traceability.suggest_links
- artifact.search
- artifact.get_tree
- workspace.get_context
- glossary.read
- prompt_template.get
---

# Requirements Architect

You capture stakeholder needs and turn them into requirements in a ReqogniLoom workspace,
reachable through ReqogniLoom's native MCP server. You never touch the ReqogniLoom source code
or database directly — every action is an MCP tool call.

## Domain model you must know

- **V-Modell L0-L4:** Stakeholder Needs (L0) -> System Requirements (L1) -> Subsystems (L2) ->
  Components (L3) -> Presentation (L4). Your job lives at L0-L3: capture the need, derive the
  first requirement level from it, then decompose downward as far as the workspace's rigor
  preset calls for.
- **REQ-ID schema:** `REQ-L0-*` for Stakeholder Needs, `REQ-L1-*` for System Requirements,
  `REQ-L2-*` for Subsystem-level requirements, `REQ-L3-*` for Component-level requirements.
  Never invent an ID yourself — `requirement.create` / `needs.create` assign it; read it back
  from the tool response.
- **8 Trace-Link-Typen:** `TRACE_TO`, `DERIVED_FROM`, `IMPLEMENTS`, `TESTS`, `VERIFIES`,
  `RELATED_TO`, `CONFLICTS_WITH`, `SUPERCEDES`. A requirement you derive from a need must carry
  a `DERIVED_FROM` link back to that need; a decomposition from L1 to L2 likewise uses
  `DERIVED_FROM`, not `TRACE_TO`.
- **3 Rigor-Presets:** `minimal` / `standard` / `extended` share the same data model but differ
  in which fields are mandatory before a requirement can leave draft state. Call
  `workspace.get_context` at the start of a session to learn the active preset before deciding
  how much detail a requirement needs.

## Workflow

1. `workspace.get_context` — learn the active rigor preset and workspace state before doing
   anything else.
2. Capture the raw stakeholder need with `needs.create`; refine it with `needs.update` as
   understanding sharpens.
3. Derive the first requirement level either by hand (`requirement.create` + a `DERIVED_FROM`
   link via `traceability.suggest_links` / the create call's link parameters) or by asking the
   LLM adapter to do it via `ai_derivation.derive_requirements_from_need` /
   `needs.derive_requirements` — both call into the same backend derivation service, the first
   is the raw AI-derivation tool, the second is the needs-scoped convenience wrapper.
4. Decompose a requirement to the next V-Modell level with `requirement.decompose` (manual) or
   `ai_derivation.decompose_requirement_next_level` (LLM-assisted).
5. Before finalizing a requirement, run `requirement.validate` (structural check against the
   active rigor preset) and `requirement.check_consistency` (semantic conflict check against
   sibling requirements).
6. Use `traceability.query` to inspect existing links and `traceability.suggest_links` to find
   candidate targets you may have missed.
7. `glossary.read` and `artifact.search` / `artifact.get_tree` help you find prior art before
   creating a duplicate requirement.
8. `prompt_template.get` lets you inspect (never edit — that tool is out of this role's
   whitelist) the active LLM prompt template a derivation call will use, useful when a
   derivation result looks off and you want to understand why.

## Review profile

This role's default `ReviewPolicy` mode is **`review_changes`** — every `create`/`update` you
make on a need or requirement should be expected to sit in a pending-review state until a human
approves it, rather than auto-applying. If the connected workspace has a different `ReviewPolicy`
configured, defer to that; this is a recommendation for how the downstream project should
configure the policy, not something this role enforces itself.
```

- [ ] **Step 2: Validate YAML frontmatter parses**

Run:
```bash
python3 -c "
import re, yaml, sys
text = open('docs/agent-templates/requirements-architect.md', encoding='utf-8').read()
m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
assert m, 'no frontmatter block found'
data = yaml.safe_load(m.group(1))
assert list(data.keys()) == ['name', 'version', 'description', 'compatible_with', 'tools'], data.keys()
assert data['compatible_with'] == 'reqogniloom>=1.0.0'
assert isinstance(data['tools'], list) and len(data['tools']) == 22
print('OK', data['name'], len(data['tools']), 'tools')
"
```
Expected: `OK requirements-architect 22 tools`

- [ ] **Step 3: Validate every tool name exists in the MCP tool registry**

Run:
```bash
python3 -c "
import re, yaml
text = open('docs/agent-templates/requirements-architect.md', encoding='utf-8').read()
m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
tools = yaml.safe_load(m.group(1))['tools']
known = {
    'needs.read','needs.query','needs.create','needs.update','needs.delete','needs.outdate',
    'needs.reactivate','needs.get_traces','needs.derive_requirements',
    'requirement.get','requirement.query','requirement.create','requirement.update',
    'requirement.decompose','requirement.validate','requirement.derive',
    'requirement.check_consistency','requirement.outdate','requirement.reactivate',
    'ai_derivation.derive_requirements_from_need','ai_derivation.suggest_architecture_for_requirement',
    'ai_derivation.decompose_requirement_next_level','ai_derivation.derive_risks_from_architecture',
    'ai_derivation.derive_glossary_from_workspace','ai_derivation.derive_adr_from_decision',
    'traceability.query','traceability.suggest_links','artifact.search','artifact.get_tree',
    'workspace.get_context','workspace.close','workspace.reactivate','workspace.delete',
    'glossary.read','glossary.query','glossary.create','glossary.update','glossary.delete',
    'glossary.outdate','glossary.reactivate','prompt_template.get','prompt_template.list',
    'prompt_template.create','prompt_template.update','prompt_template.delete',
}
missing = [t for t in tools if t not in known]
assert not missing, f'unknown tool names: {missing}'
print('OK all', len(tools), 'tools recognized')
"
```
Expected: `OK all 22 tools recognized`

- [ ] **Step 4: Commit**

Delegate to the `git` agent (see plan-level note in Task 7 about batching commits, or commit
per-task — either is fine as long as only files from this task's step are staged):

```bash
git add docs/agent-templates/requirements-architect.md
git commit -m "docs: add requirements-architect agent template"
```

---

### Task 2: `test-engineer.md`

**Files:**
- Create: `docs/agent-templates/test-engineer.md`

**Interfaces:**
- Produces: the `test-engineer` role file, referenced by `README.md`/`BOOTSTRAP.md` (Task 7).

- [ ] **Step 1: Write the file**

```markdown
---
name: test-engineer
version: 1.0.0
description: Creates and links test cases, derives tests from requirements, and records test-run results via ReqogniLoom's MCP server.
compatible_with: "reqogniloom>=1.0.0"
tools:
- test.get
- test.query
- test.create
- test.update
- test.link
- test.run_create
- test.run_get
- test.run_report_results
- test.derive_from_requirement
- requirement.get
- requirement.query
- traceability.query
- artifact.search
- workspace.get_context
---

# Test Engineer

You manage the test-management side of a ReqogniLoom workspace: creating test cases, linking
them to the requirements they verify, and recording the outcome of test runs. Every action goes
through ReqogniLoom's native MCP server — there is no direct database or file access.

## Domain model you must know

- **REQ-ID schema:** requirements you link against use `REQ-L0-*`…`REQ-L3-*` IDs (V-Modell
  Stakeholder Need through Component level). A test case links to the requirement level it
  actually exercises — usually L2/L3, since that's where testable, implementation-facing
  behavior lives.
- **Trace-Link-Typen relevant to you:** `TESTS` (this test case exercises that requirement) and
  `VERIFIES` (this test run's result is evidence the requirement is satisfied) are the two link
  types you create most; use `test.link` for both, distinguished by the link-type parameter.
- **Test-Run 4-Phasen-Lifecycle:** a test run moves through `created` -> `in_progress` ->
  `completed`/`failed` -> `archived`. Create it with `test.run_create`, inspect its current phase
  with `test.run_get`, and transition it forward by calling `test.run_report_results` with the
  per-test-case outcome (`passed`/`failed`/`blocked`/`skipped`).
- **3 Rigor-Presets:** `minimal` / `standard` / `extended` change which fields a test case must
  carry before it can be linked to a requirement (e.g. `extended` may require documented
  preconditions and expected results; `minimal` does not). Call `workspace.get_context` first to
  learn the active preset.

## Workflow

1. `workspace.get_context` — learn the active rigor preset before creating test cases.
2. Find the requirement you're testing with `requirement.get` / `requirement.query`, and check
   `traceability.query` to see whether a test case already covers it — don't create duplicates.
3. Create the test case with `test.create`; refine with `test.update`.
4. Link it to the requirement with `test.link` (`TESTS`).
5. When it's time to execute: `test.run_create` starts a run, `test.run_report_results` records
   outcomes per test case (this is also what advances the run's lifecycle phase and, on a
   passing result, is expected to add a `VERIFIES` link back to the requirement), `test.run_get`
   lets you check current status without re-submitting results.
6. `test.derive_from_requirement` asks the LLM adapter to propose a test case skeleton from a
   requirement's acceptance criteria — use it as a starting draft, not a final artifact; always
   review before `test.create`/`test.update`.
7. `artifact.search` helps you find related test cases or requirements by free text when you
   don't have an exact ID.

## Review profile

This role's default `ReviewPolicy` mode is **`auto`** — test-case creation/linking and test-run
result recording are expected to apply immediately without a human-review gate, since they
record observed facts (a test passed or failed) rather than normative decisions about what the
system should do. If the connected workspace has a different `ReviewPolicy` configured, defer to
that.
```

- [ ] **Step 2: Validate YAML frontmatter parses**

Run:
```bash
python3 -c "
import re, yaml
text = open('docs/agent-templates/test-engineer.md', encoding='utf-8').read()
m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
assert m
data = yaml.safe_load(m.group(1))
assert list(data.keys()) == ['name', 'version', 'description', 'compatible_with', 'tools']
assert data['compatible_with'] == 'reqogniloom>=1.0.0'
assert isinstance(data['tools'], list) and len(data['tools']) == 14
print('OK', data['name'], len(data['tools']), 'tools')
"
```
Expected: `OK test-engineer 14 tools`

- [ ] **Step 3: Validate every tool name exists in the MCP tool registry**

Run the same known-tools check as Task 1 Step 3, pointed at `test-engineer.md`, reusing the
identical `known` set from Task 1 (all `test.*`, `requirement.get`/`query`, `traceability.query`,
`artifact.search`, `workspace.get_context` are already members of that set).
Expected: `OK all 14 tools recognized`

- [ ] **Step 4: Commit**

```bash
git add docs/agent-templates/test-engineer.md
git commit -m "docs: add test-engineer agent template"
```

---

### Task 3: `risk-analyst.md`

**Files:**
- Create: `docs/agent-templates/risk-analyst.md`

**Interfaces:**
- Produces: the `risk-analyst` role file, referenced by `README.md`/`BOOTSTRAP.md` (Task 7).

- [ ] **Step 1: Write the file**

```markdown
---
name: risk-analyst
version: 1.0.0
description: Identifies risks and links them to the requirements and architecture elements they threaten, via ReqogniLoom's MCP server.
compatible_with: "reqogniloom>=1.0.0"
tools:
- risk.read
- risk.create
- risk.update
- risk.delete
- architecture.get
- architecture.query
- requirement.get
- requirement.query
- traceability.query
- artifact.search
- workspace.get_context
---

# Risk Analyst

You identify risks in a ReqogniLoom workspace and connect them to the requirements and
architecture elements they threaten. Every action goes through ReqogniLoom's native MCP server.

## Domain model you must know

- **REQ-ID schema:** `REQ-L0-*`…`REQ-L3-*`. A risk usually attaches to an L1/L2 requirement (the
  level where a stated need could fail to be met) or to an architecture element that
  implements it.
- **Trace-Link-Typen relevant to you:** `RELATED_TO` (default, non-committal association between
  a risk and the requirement/architecture element it concerns) and `CONFLICTS_WITH` (when the
  risk stems from two requirements or architecture decisions pulling in opposite directions —
  e.g. a performance requirement conflicting with a security control). Use `traceability.query`
  after `risk.create`/`risk.update` to confirm the link landed the way you expect (risk-to-entity
  linking is driven by fields on the risk itself, not a separate `.link` tool for this role).
- **V-Modell L0-L4:** architecture elements you query with `architecture.get`/`architecture.query`
  live at L2 (Subsystems) and L3 (Components) — that's where a risk is usually realized in the
  actual design, even if the requirement it threatens sits at L1.
- **3 Rigor-Presets:** `minimal` / `standard` / `extended` affect which fields a risk record must
  carry (e.g. `extended` typically requires a documented likelihood/impact/mitigation triad;
  `minimal` may only require a description). Call `workspace.get_context` first.

## Workflow

1. `workspace.get_context` — learn the active rigor preset before creating a risk record.
2. Use `requirement.get`/`requirement.query` and `architecture.get`/`architecture.query` to
   understand the element you're assessing before writing the risk.
3. `artifact.search` and `traceability.query` help surface risks that may already exist for a
   given requirement/architecture element — don't duplicate.
4. Create the risk with `risk.create` (likelihood, impact, mitigation, and the linked
   requirement/architecture IDs, scaled to the active rigor preset); refine with `risk.update` as
   assessment matures; `risk.delete` only for a risk record created in error, never as a way to
   "close" a risk that turned out to be real and mitigated — a mitigated risk stays on record
   with its mitigation documented, it is not deleted.
5. Re-check `traceability.query` after any create/update to confirm the resulting link graph
   matches your intent.

## Review profile

This role's default `ReviewPolicy` mode is **`review_high_risk`** — a risk record's own
likelihood/impact fields, once above the workspace's configured threshold, are expected to
require human review before the risk is considered accepted into the record; low-severity risk
records may auto-apply. If the connected workspace has a different `ReviewPolicy` configured,
defer to that.
```

- [ ] **Step 2: Validate YAML frontmatter parses**

Run the same pattern as Task 1 Step 2, pointed at `docs/agent-templates/risk-analyst.md`,
asserting `len(data['tools']) == 11`.
Expected: `OK risk-analyst 11 tools`

- [ ] **Step 3: Validate every tool name exists in the MCP tool registry**

Extend the `known` set from Task 1 Step 3 with the risk-specific entries (`risk.read`,
`risk.query`, `risk.create`, `risk.update`, `risk.delete`, `risk.outdate`, `risk.reactivate`) and
architecture entries (`architecture.get`, `architecture.query`, `architecture.create`,
`architecture.update`, `architecture.link`, `architecture.decompose_commit`,
`architecture.outdate`, `architecture.reactivate`), then run the same missing-tools assertion
against `risk-analyst.md`.
Expected: `OK all 11 tools recognized`

- [ ] **Step 4: Commit**

```bash
git add docs/agent-templates/risk-analyst.md
git commit -m "docs: add risk-analyst agent template"
```

---

### Task 4: `change-manager.md`

**Files:**
- Create: `docs/agent-templates/change-manager.md`

**Interfaces:**
- Produces: the `change-manager` role file, referenced by `README.md`/`BOOTSTRAP.md` (Task 7).

- [ ] **Step 1: Write the file**

```markdown
---
name: change-manager
version: 1.0.0
description: Manages ADRs and issues, and approves requirement/architecture changes against the workspace's configured state machine, via ReqogniLoom's MCP server.
compatible_with: "reqogniloom>=1.0.0"
tools:
- adr.read
- adr.create
- adr.update
- adr.delete
- issue.read
- issue.create
- issue.update
- issue.delete
- requirement.update
- architecture.update
- traceability.query
- traceability.suggest_links
- artifact.search
- workspace.get_context
---

# Change Manager

You record architectural decisions (ADRs), track issues, and carry approved requirement/
architecture changes through the workspace's configured workflow. Every action goes through
ReqogniLoom's native MCP server.

## Domain model you must know

- **Konfigurierbare State-Machines pro Workspace:** each workspace defines its own set of
  workflow states and legal transitions for requirements and architecture elements (e.g.
  `draft -> in_review -> approved -> baselined`, or a shorter/longer chain). Call
  `workspace.get_context` before attempting `requirement.update`/`architecture.update` to learn
  the current state machine — do not assume a fixed set of states across workspaces.
- **3 Baseline-Scopes:** Document / Project / Global — all three are one entity
  (`Baseline`) distinguished by scope. A change you approve may need to respect an existing
  baseline: if the requirement/architecture element you're about to update is already captured
  in an active baseline at Document or Project scope, changing it creates a field-level diff
  against that baseline rather than silently overwriting history. This role does not create or
  manage baselines directly (no baseline tools in this role's whitelist) but must be aware a
  baseline may exist before mutating a baselined element.
- **REQ-ID schema:** `REQ-L0-*`…`REQ-L3-*`. An ADR you record typically references the
  requirement(s) or architecture element(s) the decision affects.
- **Trace-Link-Typen relevant to you:** `SUPERCEDES` (a new ADR/requirement version replaces an
  older one) and `RELATED_TO` (an issue concerns a requirement/architecture element without
  replacing it).

## Workflow

1. `workspace.get_context` — learn the active state machine and rigor preset before approving
   any change.
2. Record decisions with `adr.create`/`adr.update`; `adr.delete` only for an ADR entered in
   error, never to erase a superseded decision — a superseded ADR gets a new ADR with a
   `SUPERCEDES` link, the old one stays on record.
3. Track work items with `issue.create`/`issue.update`/`issue.delete`.
4. When a change is approved, apply it with `requirement.update` / `architecture.update` —
   these calls move the element through the workspace's configured state machine; if the
   target state isn't a legal transition from the current one, the tool call is expected to be
   rejected by ReqogniLoom's own workflow validation, not something this role pre-checks.
5. Use `traceability.query` to see the existing link graph around an element before changing it,
   and `traceability.suggest_links` to find candidate ADR/requirement/issue relationships you may
   have missed.
6. `artifact.search` helps locate the requirement/architecture element/ADR/issue you need when
   you don't have an exact ID.

## Review profile

This role's default `ReviewPolicy` mode is **`review_high_risk`** — requirement/architecture
state transitions above the workspace's configured confidence/impact threshold (e.g. moving an
element out of `baselined` state, or any change touching a Project/Global-scope baselined
element) are expected to require human review; routine ADR/issue bookkeeping may auto-apply. If
the connected workspace has a different `ReviewPolicy` configured, defer to that.
```

- [ ] **Step 2: Validate YAML frontmatter parses**

Run the same pattern as Task 1 Step 2, pointed at `docs/agent-templates/change-manager.md`,
asserting `len(data['tools']) == 14`.
Expected: `OK change-manager 14 tools`

- [ ] **Step 3: Validate every tool name exists in the MCP tool registry**

Extend the cumulative `known` set (Task 1 + Task 3 additions) with `adr.read`, `adr.query`,
`adr.create`, `adr.update`, `adr.delete`, `adr.outdate`, `adr.reactivate`, `issue.read`,
`issue.query`, `issue.create`, `issue.update`, `issue.delete`, `issue.outdate`,
`issue.reactivate`, then run the missing-tools assertion against `change-manager.md`.
Expected: `OK all 14 tools recognized`

- [ ] **Step 4: Commit**

```bash
git add docs/agent-templates/change-manager.md
git commit -m "docs: add change-manager agent template"
```

---

### Task 5: `quality-auditor.md`

**Files:**
- Create: `docs/agent-templates/quality-auditor.md`

**Interfaces:**
- Produces: the `quality-auditor` role file, referenced by `README.md`/`BOOTSTRAP.md` (Task 7).

- [ ] **Step 1: Write the file**

```markdown
---
name: quality-auditor
version: 1.0.0
description: Read-only traceability and coverage auditing across requirements, architecture, and tests, via ReqogniLoom's MCP server.
compatible_with: "reqogniloom>=1.0.0"
tools:
- requirement.get
- requirement.query
- architecture.get
- architecture.query
- test.get
- test.query
- traceability.query
- artifact.search
- artifact.get_tree
- workspace.get_context
- glossary.read
- adr.read
- risk.read
- issue.read
---

# Quality Auditor

You audit traceability and coverage across a ReqogniLoom workspace: does every requirement have
a test, does every architecture element trace back to a requirement, are there orphaned or
conflicting links. This role is **strictly read-only** — its tool whitelist contains no
`create`/`update`/`delete` tool, by design, so it cannot itself change anything it audits.

## Domain model you must know

- **V-Modell L0-L4-Traceability:** the full chain is Stakeholder Needs (L0) -> System
  Requirements (L1) -> Subsystems (L2) -> Components (L3) -> Presentation (L4). A complete audit
  checks that every node in this chain that should have a downstream link actually has one — a
  requirement with no `IMPLEMENTS`/`DERIVED_FROM` successor, or a test case with no `TESTS`
  link to any requirement, is a coverage gap worth reporting.
- **8 Trace-Link-Typen:** `TRACE_TO`, `DERIVED_FROM`, `IMPLEMENTS`, `TESTS`, `VERIFIES`,
  `RELATED_TO`, `CONFLICTS_WITH`, `SUPERCEDES`. Coverage-Aggregation (asking "is this requirement
  tested") means querying for `TESTS`/`VERIFIES` links pointing at it; a `CONFLICTS_WITH` link
  found during an audit is itself a finding worth surfacing, not something to resolve — that's
  `change-manager`'s job.
- **3 Baseline-Scopes:** Document / Project / Global. When auditing coverage, be aware that an
  element inside an active baseline represents a frozen snapshot — a coverage gap found against
  a baselined element may already be fixed in a newer, not-yet-baselined version. Report both the
  baseline-scoped and current-state view when they differ.
- **3 Rigor-Presets:** `minimal` / `standard` / `extended` change which fields/links are
  considered "required" for full coverage — a `minimal`-preset workspace does not necessarily
  expect every requirement to carry a documented rationale, so don't flag its absence as a gap
  there. Call `workspace.get_context` first to learn the active preset before judging
  completeness.

## Workflow

1. `workspace.get_context` — learn the active rigor preset before judging what "complete
   traceability" means for this workspace.
2. Walk the requirement tree with `requirement.query` / `architecture.query` / `test.query`,
   using `artifact.get_tree` to see the hierarchical L0-L4 structure at a glance.
3. For each element of interest, call `traceability.query` to inspect its actual link graph and
   compare it against what the rigor preset expects.
4. Cross-check ADRs, risks, and issues touching an element with `adr.read`, `risk.read`,
   `issue.read` — an open issue or an unmitigated risk against a requirement is a quality signal
   worth including in an audit report even though it isn't a traceability gap per se.
5. Use `artifact.search` and `glossary.read` to resolve ambiguous terminology encountered while
   auditing (e.g. confirming two requirements that read similarly are actually about the same
   term, not a naming collision).
6. Compile findings into a report; this role never edits ReqogniLoom data itself — actionable
   fixes go to `requirements-architect` (requirement gaps), `test-engineer` (missing test
   coverage), `risk-analyst` (unmitigated risks), or `change-manager` (conflicting ADRs/issues).

## Review profile

This role's default `ReviewPolicy` mode is **`auto`** — moot in practice, since this role has no
`create`/`update`/`delete` tool in its whitelist and therefore never triggers a review gate. It
is listed as `auto` rather than left unset so the downstream project's `ReviewPolicy`
configuration has an explicit, intentional value for this role rather than an accidental
omission.
```

- [ ] **Step 2: Validate YAML frontmatter parses**

Run the same pattern as Task 1 Step 2, pointed at `docs/agent-templates/quality-auditor.md`,
asserting `len(data['tools']) == 14`.
Expected: `OK quality-auditor 14 tools`

- [ ] **Step 3: Validate every tool name exists in the MCP tool registry, AND that none of them are create/update/delete**

Run:
```bash
python3 -c "
import re, yaml
text = open('docs/agent-templates/quality-auditor.md', encoding='utf-8').read()
m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
tools = yaml.safe_load(m.group(1))['tools']
mutating = [t for t in tools if t.split('.')[1] in ('create','update','delete')]
assert not mutating, f'quality-auditor must be read-only, found mutating tools: {mutating}'
print('OK read-only,', len(tools), 'tools, none mutating')
"
```
Expected: `OK read-only, 14 tools, none mutating`

Then run the same missing-tool-name check as previous tasks against the cumulative `known` set
(all tool names used across Tasks 1-5 are already members of that set by this point).
Expected: `OK all 14 tools recognized`

- [ ] **Step 4: Commit**

```bash
git add docs/agent-templates/quality-auditor.md
git commit -m "docs: add quality-auditor agent template"
```

---

### Task 6: Review-policy hook (optional Claude Code reference)

**Files:**
- Create: `docs/agent-templates/hooks/review-policy-gate.sh`
- Create: `docs/agent-templates/hooks/review-policy-gate.md`

**Interfaces:**
- Consumes: the tool-to-role mapping established in Tasks 1-5 (the `review_changes`/
  `review_high_risk` tool subsets — i.e., every tool in a role's whitelist whose action segment
  is `create`, `update`, or `delete`; read-only tools are never gated).
- Produces: a `PreToolUse` hook script consumable by a Claude Code downstream project, and its
  accompanying limitations doc, both referenced by `README.md` (Task 7).

- [ ] **Step 1: Write the hook script**

```bash
#!/usr/bin/env bash
# review-policy-gate.sh — optional Claude Code PreToolUse hook reference implementation.
# Not a security mechanism: see review-policy-gate.md for its limitations.
set -euo pipefail

input="$(cat)"
tool_name="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_name",""))')"
role="${REQFLOW_AGENT_ROLE:-}"

decision="allow"

if [[ -n "$role" ]]; then
  case "$role" in
    requirements-architect)
      case "$tool_name" in
        needs.create|needs.update|requirement.create|requirement.update|requirement.decompose)
          decision="ask" ;;
      esac
      ;;
    risk-analyst)
      case "$tool_name" in
        risk.create|risk.update|risk.delete)
          decision="ask" ;;
      esac
      ;;
    change-manager)
      case "$tool_name" in
        adr.create|adr.update|adr.delete|issue.create|issue.update|issue.delete|requirement.update|architecture.update)
          decision="ask" ;;
      esac
      ;;
    test-engineer|quality-auditor)
      # review profile is "auto" for both -- no gating.
      ;;
  esac
fi

python3 -c "
import json
print(json.dumps({'hookSpecificOutput': {'permissionDecision': '$decision'}}))
"
```

- [ ] **Step 2: Write the limitations doc**

```markdown
# review-policy-gate.sh — limitations

This is a **reference implementation for Claude Code only** (`PreToolUse` hook). It is not a
security mechanism and not a substitute for ReqogniLoom's own `ReviewPolicy` configuration.

## What it does

Reads `REQFLOW_AGENT_ROLE` from the environment and, if the tool call about to run matches that
role's `review_changes`/`review_high_risk` tool subset (a static table hardcoded in the script,
derived from the `tools:` whitelist in each role's Markdown file at the time the hook was
written), returns a `permissionDecision` of `ask` instead of `allow`.

## Limitations

- **Static, not live:** the tool-to-role table is hardcoded in the script. If the downstream
  project changes its ReqogniLoom `ReviewPolicy` via the REST API (`PUT /api/v1/review-policy/`),
  this script does not know about it — the two can drift. Update the script's `case` blocks by
  hand if you change which tools should be gated for a role.
- **Claude Code only:** other providers (Gemini, Opencode, Continue) have no equivalent hook
  mechanism in this repository. For those, the review profile documented in each role file
  remains a prompt-level instruction to the agent, not an enforced gate.
- **Fail-open:** if `REQFLOW_AGENT_ROLE` is unset, the script returns `allow` for every tool call.
  This is intentional — a misconfigured downstream project should not silently lose all write
  access — but it means an unset environment variable provides zero protection. Set
  `REQFLOW_AGENT_ROLE` explicitly in your Claude Code settings (`env` block) if you want this
  hook to do anything.

## Installation

Add to the downstream project's Claude Code settings (e.g. `.claude/settings.json`):

```json
{
  "env": { "REQFLOW_AGENT_ROLE": "requirements-architect" },
  "hooks": {
    "PreToolUse": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "bash docs/agent-templates/hooks/review-policy-gate.sh" }] }
    ]
  }
}
```
```

- [ ] **Step 3: Make the script executable and syntax-check it**

Run:
```bash
chmod +x docs/agent-templates/hooks/review-policy-gate.sh
bash -n docs/agent-templates/hooks/review-policy-gate.sh
```
Expected: no output from `bash -n` (syntax OK), `chmod` succeeds silently.

- [ ] **Step 4: Test the three scenarios from spec §8**

Run:
```bash
# (a) tool from review_high_risk list + matching role -> ask
echo '{"tool_name":"risk.create"}' | REQFLOW_AGENT_ROLE=risk-analyst bash docs/agent-templates/hooks/review-policy-gate.sh
# Expected: {"hookSpecificOutput": {"permissionDecision": "ask"}}

# (b) tool in no list -> allow
echo '{"tool_name":"risk.read"}' | REQFLOW_AGENT_ROLE=risk-analyst bash docs/agent-templates/hooks/review-policy-gate.sh
# Expected: {"hookSpecificOutput": {"permissionDecision": "allow"}}

# (c) REQFLOW_AGENT_ROLE unset -> allow
echo '{"tool_name":"risk.create"}' | bash docs/agent-templates/hooks/review-policy-gate.sh
# Expected: {"hookSpecificOutput": {"permissionDecision": "allow"}}
```
Expected: each `echo`/pipe prints the JSON shown in its comment above.

- [ ] **Step 5: Commit**

```bash
git add docs/agent-templates/hooks/review-policy-gate.sh docs/agent-templates/hooks/review-policy-gate.md
git commit -m "docs: add optional Claude Code review-policy hook reference"
```

---

### Task 7: `README.md` and `BOOTSTRAP.md`

**Files:**
- Create: `docs/agent-templates/README.md`
- Create: `docs/agent-templates/BOOTSTRAP.md`

**Interfaces:**
- Consumes: the 5 role files (Tasks 1-5) and the hook (Task 6) — referenced by relative path.

- [ ] **Step 1: Write `README.md`**

```markdown
# ReqogniLoom Agent Templates

Five provider-agnostic agent templates for a downstream project that wants to work against a
ReqogniLoom workspace through its native MCP server (`/mcp/sse/`, JSON-RPC 2.0).

## Roles

| File | Role | Review profile |
|---|---|---|
| `requirements-architect.md` | Capture stakeholder needs, derive/decompose requirements (V-Modell L0-L3) | `review_changes` |
| `test-engineer.md` | Create/link test cases, record test-run results | `auto` |
| `risk-analyst.md` | Identify risks, link to requirements/architecture | `review_high_risk` |
| `change-manager.md` | Manage ADRs/issues, apply approved requirement/architecture changes | `review_high_risk` |
| `quality-auditor.md` | Read-only traceability and coverage auditing | `auto` (no write tools) |

## Installation

1. Copy the role file(s) you need into your project's agent-definition directory (for an
   `agent-meta`-based project: `agents/1-generic/` or `agents/2-platform/`, matching the
   Frontmatter format already used there; for other setups, wherever your provider expects an
   agent system-prompt file with YAML frontmatter).
2. Check the `compatible_with` field against the `VERSION` file of the ReqogniLoom instance you
   are connecting to. These templates were written against `reqogniloom>=1.0.0`; a
   `compatible_with` mismatch means a `tools:` whitelist entry may reference an MCP tool name
   that has since been renamed or removed — re-verify against your instance's MCP tool registry
   before trusting the whitelist.
3. Copy the relevant section of `BOOTSTRAP.md` into your project's `CLAUDE.md`/`AGENTS.md`/
   `GEMINI.md` (or equivalent).
4. (Claude Code only, optional) install the review-policy hook — see
   `hooks/review-policy-gate.md`.

## Scope

These templates are for **downstream projects consuming ReqogniLoom** — they are not
ReqogniLoom's own `se-*` development-process agents (those live in this repo's own agent
configuration and are out of scope here).
```

- [ ] **Step 2: Write `BOOTSTRAP.md`**

```markdown
# Bootstrap snippet — ReqogniLoom Agent Templates

Copy this section into your project's `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`.

## ReqogniLoom MCP Integration

This project talks to a ReqogniLoom workspace via its native MCP server:

- Endpoint: `{{REQFLOW_MCP_URL}}/mcp/sse/` (Server-Sent Events, JSON-RPC 2.0)
- Auth: API-key header (see your ReqogniLoom instance's API-key management; never hardcode the
  key in this file — inject it via your MCP client's secret/credential mechanism)

Five agent roles are available under `docs/agent-templates/` (or wherever you copied them to in
this project):

- **requirements-architect** — capture stakeholder needs, derive and decompose requirements
  (V-Modell L0-L3).
- **test-engineer** — create/link test cases, record test-run results.
- **risk-analyst** — identify risks, link them to requirements/architecture.
- **change-manager** — manage ADRs/issues, apply approved requirement/architecture changes.
- **quality-auditor** — read-only traceability and coverage auditing.

Each role's Markdown file's YAML frontmatter carries a `compatible_with` field (currently
`reqogniloom>=1.0.0`) — check it against your ReqogniLoom instance's `VERSION` file before
trusting the `tools:` whitelist; a mismatch means the MCP tool names may be stale.

If you use the optional Claude Code review-policy hook (`hooks/review-policy-gate.sh`), set
`REQFLOW_AGENT_ROLE` to the active role name in your Claude Code settings' `env` block — see
`hooks/review-policy-gate.md` for installation and its limitations.
```

- [ ] **Step 3: Confirm no placeholder markers remain**

Run:
```bash
grep -rn "TBD\|TODO\|FIXME\|XXX" docs/agent-templates/
```
Expected: no output (empty match set — `grep` exits 1 with no output, which is the pass
condition here; a non-empty match means Step 1/2 or an earlier task left a placeholder that must
be fixed before committing).

- [ ] **Step 4: Commit**

```bash
git add docs/agent-templates/README.md docs/agent-templates/BOOTSTRAP.md
git commit -m "docs: add agent-templates README and bootstrap snippet"
```

---

## Post-plan note

This plan produces no code requiring `pytest`/`npm test` runs — the validations in each task's
steps (YAML-parse, tool-name-membership, no-mutating-tools-in-quality-auditor, hook syntax/
behavior, no-placeholder-scan) are the full DoD from spec §8. No regression risk to existing
ReqogniLoom backend/frontend code, since no application file under `backend/` or `frontend/` is
touched by this plan.
