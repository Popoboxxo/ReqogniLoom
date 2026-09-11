# SDD ledger — plan: docs/superpowers/plans/2026-09-03-interview-engine-fix.md

**Execution mode note:** run directly by a fork (no Agent-tool access, per
fork hard rules) rather than via the full subagent-driven-development
implementer/reviewer-subagent loop. Every task below was implemented,
tested, and committed by the same execution — no per-task subagent review
happened. Treat this ledger as "implemented and self-verified", not as
"independently reviewed" — a real task/final review pass is still owed
before merge, same bar as any other branch.

## Phase A — L2.1: Single-Kind-Formalize through the adapter registry

**Task 1 (CreatedArtifactRef.entity_id): complete.** Commit `28440fa8`.
18/18 tests pass.

**Task 2 (ArchitectureElement adapter kwarg fix): complete, but the bug
itself was already absent.** Ruling: the plan assumed `_architecture_element`
still passed `name=` instead of `title=` (finding V4). In this tree
(forked from `main` post traceability-semantik/attribute-definition merges)
the adapter body already forwarded `**fields` correctly — only the TEST was
still asserting the wrong (`name=`) kwarg via a bare `MagicMock` that
accepts anything. Applied the plan's `autospec=True` test upgrade anyway
(real value: catches a *future* regression) but did not need to touch the
adapter body itself. Included in commit `28440fa8`.

**Task 3 (build_adapter_fields): complete.** Included in commit `28440fa8`.

**Task 4 (Risk protocol probability/impact): complete.** Commit `38420a0`.
27/27 tests pass. Confirmed this is tier-3 only (`get_protocol()`'s
hardcoded factory fallback) — tiers 1-2 (admin override,
attribute-definition `ai_elicit`) already take precedence when configured;
this closes the gap for a fresh workspace/tenant with neither.

**Task 5 (L2.1 core fix — `_formalize_single` dispatches through the
registry): complete.** Commit `cb9b4632`. 35/35 tests pass (adapters +
TestFormalize + multi-mode regression guard
`test_single_mode_formalize_unchanged`).

Real bug found and fixed beyond the plan's own scope: the `_glossary_term`
adapter required `fields["term"]`, but every in-scope type's interview
protocol (and `_formalize_single`'s own title guard) collects `title` —
GlossaryTerm's factory-default protocol never asks for `term` at all. Fixed
by accepting `fields.get("term") or fields["title"]` in the adapter, since
`build_adapter_fields` is deliberately type-agnostic (only
`rationale`→`description`) and should stay that way.

**Ruling on GlossaryTerm's actual status:** the plan's Global Constraints /
finding V11 assume GlossaryTerm is still blocked (no Artifact-backing row).
**This is stale** — Datenmodell-Konsolidierung Phase 3 (PR #880, merged
this session) gave `GlossaryTerm` a backing `Artifact` row, and the
registry's `_glossary_term` entry already creates real terms, not a
`ValidationError`. HOWEVER: `IN_SCOPE_ARTIFACT_TYPES`
(`interview_protocol.py:31-40`) still deliberately excludes `GlossaryTerm`
— so `InterviewService.start(ctx, "GlossaryTerm", ...)` still rejects with
"Interviews are not available for artifact_type='GlossaryTerm'".
GlossaryTerm formalization is reachable **only via the multi-kind path**
(`_formalize_multi`), which doesn't gate on `IN_SCOPE_ARTIFACT_TYPES` since
individual proposals just need a valid adapter entry. This matches the
plan's own "9th registry entry" framing — GlossaryTerm was never meant to
be a single-mode interview target, only a multi-mode one. Do not add it to
`IN_SCOPE_ARTIFACT_TYPES` without a deliberate product decision; that would
be new scope, not a bugfix.

**Task 6 (per-type regression test suite): complete.** Commit `68a53bf`.
16/16 tests pass, all 8 in-scope types × 2 assertions (artifact exists +
workflow state initialized).

Two real fixture gaps found (plan's assumed "before" fixture state didn't
anticipate them):
1. `StakeholderNeedService.create()` sets `created_by=ctx.user_id` with a
   real FK to `pl_user` — unlike several sibling `create_X()` methods,
   a bare `uuid4()` 404s on the constraint. Fixed by creating a real `User`
   row in the `ctx` fixture.
2. `initialize_workflow_states()` silently no-ops when no
   `WorkflowEngineDefinition` exists for `(workspace, item_type)` —
   graceful degradation for an unconfigured type, not a bug. Fixed by
   calling `create_default_workflow(preset="standard", item_type=...)` per
   in-scope type in the `workspace` fixture, so the workflow-state
   assertion is a real integration check, not a false negative.

Also found (not a bug, a real pre-existing design choice, worth knowing for
whoever touches this next): `TestService.create_test_case()` stores
`Artifact.artifact_type` as a **compound** value `"TestCase:<test_type>"`
(default `test_type="Unit"` → `"TestCase:Unit"`), not the bare `"TestCase"`
every other in-scope type uses (`REQ-L2-AS-005`, "tags the artifact_type
with test_type for differentiation" per its own code comment). The
all-types regression test's artifact-existence query uses
`artifact_type__startswith=artifact_type` to handle this without a
type-specific branch — a future consumer of `Artifact.artifact_type` for
TestCase should be aware bare `"TestCase"` never matches.

**Task 7 (MCP tool descriptions + set_target message): complete.** Commit
`709bf08`. 102/102 tests pass (`mcp_server/tests/ -k interview` +
`test_interview_service.py`).

Adjusted the plan's proposed `interview.formalize` description text: it
assumed "GlossaryTerm is rejected: it has no backing Artifact row yet" —
now false per the Task 5 ruling above. Reworded to "Multi-kind sessions ...
create every item atomically (GlossaryTerm included)" instead. Also fixed
one more stale docstring the plan's grep step would have caught
(`formalize()`'s own outer docstring at `interview_service.py:868-872`,
not explicitly named as a file to touch in Task 7's step list but matched
by its own Step 5 grep check).

**Phase A verdict: fully complete and internally consistent.** The L2.1
gap (formalize() only worked for Requirement) is closed for all 8 in-scope
types, verified via a real, non-mocked round trip per type plus the
existing multi-mode regression guard.

## Phase B — L2.3: Make interview provenance visible

**Task 8 (provenance row write) + Task 9 (id-space bridge): complete,
combined into one commit.** Commit `9430183`. 17/17 new tests pass, plus
the multi-mode regression guard reverified (13/13,
`test_interview_formalize_multi.py`). Both `TraceLinkService.
resolve_entity_to_artifact_id` and its `NotFoundError` contract matched
the plan's assumption exactly — no deviation needed.

**Task 10 (mount `InterviewProvenanceBadge` in `RightSidebar`): complete.**
Commit `d6fbb1e4`. 9/9 new tests pass; 248/248 in
`components/shared/`; 478/479 in `src/test` (the one failure,
`theme-contrast.test.ts`, is a pre-existing environment gap — it reads a
`backend/admin_ops/fixtures/...` path the `frontend-test` container
doesn't mount, unrelated to this change).

Two plan-assumed CSS custom property names don't exist in `tokens.css`
(`--color-surface-subtle`, `--color-text-primary`/`-secondary`) —
substituted the real ones (`--color-surface-muted`, `--color-text`/
`-muted`) per the plan's own explicit fallback instruction ("never a
hardcoded value, and never a new token").

**Not verified: Step 7's live-browser walkthrough** ("log in, open
/interviews, start a Requirement interview... confirm the badge is visible
in the right inspector"). This execution has no browser/visual-verification
tool access. All automated coverage (vitest) is green; the actual rendered
UI has not been eyeballed. Flag this explicitly before calling Phase B
done in a human sense — do the manual check before merge.

**Phase B verdict: complete per automated verification; live-UI check
outstanding.**

## Phase C — L2.4: Cap the transcript (Tasks 11-14) — NOT STARTED

## Phase D — L2.5: Reduce the widget to a picker (Tasks 15-17) — NOT STARTED

## Task 18 — GlossaryTerm registry entry — ALREADY RESOLVED, no task needed

Per Task 5's ruling above: `GlossaryTerm`'s Artifact-backing already exists
(PR #880) and the registry entry already creates real terms. The plan
marks this task BLOCKED pending that exact migration — it is no longer
blocked, and no further code change is needed for the registry entry
itself. The only remaining open question (not a blocker, a scope decision)
is whether `GlossaryTerm` should be added to `IN_SCOPE_ARTIFACT_TYPES` so
it becomes reachable via single-mode `start()`/`formalize()` too — that is
new scope, not part of this plan's fix, and should go back to the user/a
follow-up plan rather than being decided unilaterally here.

## Fix round 1 — review of Tasks 1-10 (CHANGES_REQUESTED), 2026-09-11

Independent code review of Tasks 1-10 returned 2 blockers, 2 important, 6
minor. Commits `d5b3f7f1` (blockers) and `0014359d` (the rest).

**C-1 (blocker) — Risk formalize was still broken on every real tenant.
FIXED at the source.** `get_protocol()` prefers tier 2 (the
attribute-definition-derived protocol) over tier 3 (the hardcoded factory
default) whenever a definition exists, and `application.self_init` runs
`bootstrap_attribute_definitions` for every new tenant — so tier 2 is what
every deployment actually resolves and Task 4's tier-3 `_EXTRA_REQUIRED_FIELDS`
fix was unreachable in production. The bootstrap marked only
`title`/`description` as `ai_elicit`, so a Risk interview never asked for
`probability`/`impact` and `formalize()` could only reject the finished
session with `cannot formalize 'Risk' from the collected answers:
'probability'`.
- Source fix: `PER_ITEM_TYPE_AI_ELICIT_FIELDS` in
  `bootstrap_attribute_definitions.py`, shaped exactly like the file's
  existing `PER_ITEM_TYPE_EXCLUDED_FIELDS` / `WIDGET_ATTRIBUTES` per-type
  dicts, plus `SHARED_AI_ELICIT_FIELDS` for the title/description pair.
- Already-bootstrapped tenants: new data migration
  `attribute_definitions/0007_risk_interview_elicits_probability_impact.py`,
  modelled on `0006_relax_adr_description_required` (same `_elicitable`
  /`_mark_elicited`/cache-invalidation shape, repairs BOTH the global and
  the materialized workspace rows). Neither existing command mode fits:
  `--sync-new-fields` only appends missing attributes and never edits one,
  `--reset` discards every admin customization. Documented trade-off in the
  migration docstring: an admin who deliberately cleared `ai_elicit` on one
  of the two gets it back, because the alternative is an unformalizable Risk
  interview.
- The two tiers now cross-reference each other in comments, so the next
  person editing one is told to update the other.

**C-2 (blocker) — the regression suite never exercised the production tier.
FIXED.** `test_interview_formalize_all_types.py` is now split into
`TestFormalizeFactoryDefaultProtocol` (tier 3, kept verbatim) and
`TestFormalizeBootstrappedProtocol` (tier 2, `call_command(
"bootstrap_attribute_definitions", tenant=...)` in a fixture — the same
call `self_init` makes). The bootstrapped class round-trips **all 8**
in-scope types, not only Risk, plus two Risk-specific assertions (the
resolved protocol elicits probability/impact; the answers reach
`create_risk`). Verified non-vacuous: with the C-1 source fix temporarily
reverted, the bootstrapped Risk tests fail with the exact production error;
restored, all 26 pass.
- `_answer_all_required_fields` now loops over phases — a definition-derived
  protocol has one elicitation phase per definition *section*, and
  `get_state` reports only the first incomplete phase's missing fields
  (Risk's probability/impact live in `classification`, not `general`).

**Pre-existing test regression found and fixed en route:**
`test_interview_protocol_from_definition.py::test_get_protocol_falls_back_to_the_factory_default_without_a_definition`
asserted Risk's tier-3 default is exactly `["title", "rationale"]` — false
since Task 4 (commit `38420a04`). Task 4's own verification scope never ran
that module, so the branch has carried a red test since then.

**I-1 (important) — tool description vs. multi-mode prompt. FIXED, both
halves.** Investigated first: multi-mode's only type gate is
`ARTIFACT_CREATION_ADAPTERS.get(item["type"])`, so a hand-built
`confirmed_proposal` containing a GlossaryTerm *is* created — only the prompt
refuses to propose one. (a) `interview.formalize`'s description no longer
claims "(GlossaryTerm included)"; (b) `interview_multi_protocol`'s module
docstring no longer justifies the exclusion with the obsolete "GlossaryTerm
has no Artifact FK" (PR #880) — it now states the real reason (scope: not in
`IN_SCOPE_ARTIFACT_TYPES`, glossary terms are managed on the glossary
surface) and names the hand-built-proposal hole explicitly.

**I-2 (important) — speculative `fields.get("term") or fields["title"]`.
DELETED**, per the reviewer's preferred option. No reachable caller exists
(GlossaryTerm is not in `IN_SCOPE_ARTIFACT_TYPES`, so `start()` rejects it;
the multi prompt never proposes it; the only remaining caller is a
hand-built proposal that names `term` directly). Replaced by a test pinning
the `KeyError`, which `_formalize_multi` converts to a `ValidationError`.
The previous round's ledger justification for this "bug fix" was wrong.

**M-1 FIXED:** `autospec=True` on all 8 adapter tests, not just
ArchitectureElement's. Shared `_assert_called_once_with_kwargs` helper —
autospec records the bound instance as arg 0, so `assert_called_once_with`
no longer works directly.
**M-2 FIXED:** `_structural_candidates`' "in a later pass" comment reworded
(out of scope for this spec; grounding only feeds the Requirement-only
update branch).
**M-3 FIXED:** `artifact_type__in=(T, f"{T}:Unit")` instead of
`__startswith`; the `WorkflowItemState` probe is scoped to the created
`item_id` and the workspace.
**M-4 FIXED:** both `select_related("session")` calls dropped from
`provenance_session_id` — only the local `session_id` FK column is read.

**M-5 NOT FIXED — deliberate, reported as an open product question.** The
badge renders only in the expanded inspector. `renderCollapsedStrip` is a
40px rail of "open the sidebar" buttons with no content of its own; adding a
provenance indicator there means a new icon, a new aria-label, and a
provenance fetch while collapsed. `RightSidebar.tsx:342-351` already records
the precedent for exactly this call ("a real deep-link-to-section affordance
is a UX decision for ui-ux-designer, not an a11y-only pass"). Not a bug,
not fixed here; route it to `ui-ux-designer` if the product wants it.

**M-6 NOT DONE — no browser tooling in this dispatch either.** Same gap as
the Task 10 execution: no Playwright/browser tool is available to this
agent, and `WebFetch` cannot log into a JWT-protected React SPA. The
live-UI walkthrough (Task 10 Step 7) is still owed before merge. All
automated coverage is green.

### Verification (fix round 1, real output)

| Scope | Result |
|---|---|
| `application/tests/test_interview_{artifact_adapters,protocol,protocol_from_definition,provenance,formalize_all_types,service,formalize_multi,multi_review_fixes,multi_chat,multi_protocol}.py` | **175 passed** in 47.72s |
| `rest_api/tests/ mcp_server/tests/ -k interview` | **73 passed**, 2508 deselected |
| `rest_api/tests/test_architecture.py` + `test_bootstrapped_definition_allows_creates.py` | **102 passed** |
| `attribute_definitions/` (incl. new migration-0007 unit test) | **150 passed** |
| other `bootstrap_attribute_definitions` consumers (bundle export/definition service/goal views/bundle tool group) | **100 passed** |
| vitest: `InterviewProvenanceBadge`, `RightSidebar`, the 9 editor suites, `ui-ratchet`, `design-tokens` | **28 files / 148 tests passed** |

Not run (unchanged from the Global Constraints): the full backend suite and
any unfiltered Playwright run — CI's job.

## What's left for whoever resumes this

1. **Phase C (Tasks 11-14, transcript cap)** — model field + migration,
   sliding-window compressor, best-effort LLM call, wiring into the chat
   turn path. Fully specified in the plan (read Tasks 11-14 starting at
   plan line ~1841). No blocking questions expected based on the pattern
   established in Phases A-B (plan text is usually close but not always
   exact against the current tree — verify each "before" assumption
   against real files before applying a diff verbatim, as done throughout
   this ledger).
2. **Phase D (Tasks 15-17, widget reduction)** — frontend-only, needs the
   same `docker compose restart frontend` + manual browser check this
   execution could not do for Task 10 either.
3. **A real task/final review pass** — this execution self-tested every
   task but had no independent reviewer subagent (see execution-mode note
   at the top). Before merge, run at minimum the plan's own final
   whole-branch review step, and ideally the live-browser checks this
   execution skipped (Task 10 Step 7, and whatever Phase D's manual UI
   verification calls for).
4. **Full backend + frontend suite**, not just the targeted modules this
   execution ran (Global Constraints scope local runs to touched
   modules+dependents — CI's job to run the full suite, per the plan's own
   Global Constraints).

Commits on `feat/interview-engine-fix`, in order: `28440fa8` → `38420a0` →
`cb9b4632` → `68a53bf` → `709bf08` → `9430183` → `d6fbb1e4` → (fix round 1)
`d5b3f7f1` → `0014359d`. Not pushed, no PR opened — per directive, that
decision belongs to the parent/user.
