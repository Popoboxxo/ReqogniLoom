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
`cb9b4632` → `68a53bf` → `709bf08` → `9430183` → `d6fbb1e4`. Not pushed, no
PR opened — per directive, that decision belongs to the parent/user.
