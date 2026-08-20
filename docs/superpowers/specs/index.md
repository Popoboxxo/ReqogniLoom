# Spec Index

This index lists every design/spec document in this directory tree and its implementation status,
proven against the source code (not against the spec's own claims). Mirrors the structure of
`docs/superpowers/plans/index.md` — a spec and its corresponding implementation plan(s) are tracked
independently since a spec can be superseded/decided-against without its later plan doc changing, and
vice versa.

- **`Archive/`** — specs whose full scope has been implemented and verified. Kept for historical
  design rationale; no more action expected.
- **This directory (top level)** — specs with real open work, or explicitly decided against.

## Archive/ — fully implemented

## [Archive/2026-07-12-frontend-feedback-strategie-design.md](Archive/2026-07-12-frontend-feedback-strategie-design.md)
All planned features are implemented.
- **Impact-Graph-Visualisierung (C1):** `frontend/src/components/ImpactView.tsx` and `impact-preset.ts`.
- **Traces for Risks and Issues (C2, C3):** `RiskEditors.tsx`/`IssueEditors.tsx` integrate `TraceLinkPanel`/`TraceSpine`.
- **TestRun Assignments (C4, C5):** `TestRunsList.tsx`'s `selectedTestCaseIds`, `TestRunDetailEditor.tsx` loads assigned `TestCase` results.
- **Custom Fields (C6):** `CustomFieldDefinition` across backend models, serializers, views, and frontend forms.
- **Glossary Synonyms (C10):** `synonyms = models.JSONField()` on the glossary models.
- **Editable User Profile (C11):** `first_name`/`last_name` update logic in `frontend/src/components/UserProfileSettings/ProfileSection.tsx`.
- **Tags for Issues (B4):** `tags = serializers.JSONField()` backend + `tags?: string[]` frontend.

## [Archive/2026-07-23-reqogniloom-status-unification-design.md](Archive/2026-07-23-reqogniloom-status-unification-design.md)
All planned features are implemented.
- **Status Model Unification:** `is_outdated_equivalent` populated in `backend/workflow/definition_store.py` and migrations.
- **WorkspaceGoal:** `Goal`/`MainGoal` models in `backend/application/models.py`.
- **Context Generators:** `context.test_coverage`, `context.change_impact`, `workspace.llm_system_prompt` in `backend/mcp_server/tools/cross_cutting.py`.
- **Review Endpoints:** `backend/mcp_server/tools/review.py`.

## [Archive/2026-07-30-ziele-und-hauptziel-design.md](Archive/2026-07-30-ziele-und-hauptziel-design.md)
All planned features are implemented.
- **Goal and MainGoal Models:** implemented with trace properties in `backend/application/models.py`.
- **Prompt Template Integration:** `goal_aggregate` present in `prompt_slots.py`, `models.py`, `settings_views.py`, AI derivation services.
- **MCP and REST Integration:** `goal.read` in `backend/mcp_server/tools/goals.py`; REST endpoints in `main_goal_service.py`.

## [Archive/2026-08-08-requirement-bundle-export-design.md](Archive/2026-08-08-requirement-bundle-export-design.md)
All planned features are implemented.
- **Separated Services:** `RequirementBundleQueryService` (`requirement_bundle_service.py`), `BundleCompressionService` (`bundle_compression_service.py`).
- **MCP Tools:** `requirement_bundle.export` and schema endpoints in `backend/mcp_server/tools/requirement_bundle.py`.
- **Prompt Template:** `bundle_compression` references in `bundle_compression_service.py` and related AI tests.

## [Archive/2026-08-14-interview-management-hermes-plugin-design.md](Archive/2026-08-14-interview-management-hermes-plugin-design.md)
All planned features are implemented. `InterviewListView.tsx`/`InterviewFormView.tsx` present, `mcpClient.ts` handles JSON-RPC, `interview_protocol.py` implements `ProtocolField`'s `type`/`choices`.

## [Archive/2026-08-14-interview-management-web-widget-design.md](Archive/2026-08-14-interview-management-web-widget-design.md)
All planned features are implemented. `InterviewSession.transcript` JSONField exists, `POST /api/v1/interviews/{id}/chat/` in `interview_views.py`, `InterviewWidget` mounted in `NavigationShell.tsx`, `AiPromptsSection.tsx` auto-discovers `interview.protocol.<type>` slots.

---

## Open / deferred (not archived)

## [2026-07-25-phase6-agent-templates-design.md](2026-07-25-phase6-agent-templates-design.md)
**Decided against (2026-08-20), not a gap to fix.** Mirrors the corresponding implementation plan's status (`docs/superpowers/plans/2026-07-25-phase6-agent-templates.md`): `requirements-architect.md` was never created under that exact name — `requirements-architecture-manager.md` exists instead. Reviewed and the user explicitly chose not to rename/create the file to match. The rest of the spec (`change-manager.md`, `quality-auditor.md`, `risk-analyst.md`, `test-engineer.md`, hook scripts) is implemented. Do not re-flag the naming deviation.

## [2026-08-13-hermes-ide-plugin-design.md](2026-08-13-hermes-ide-plugin-design.md)
**Partially resolved (2026-08-20), one item remains genuinely open:**
- **Item 1 (Requirements Views and APIs) — still not implemented, superseded.** The core `connect → list → detail → form` Requirements management flow this spec describes was never built; `integrations/hermes-plugin/reqogniloom/src/` has no Requirement-specific API endpoints or components. Superseded by the interview-management approach instead (see the two `interview-management-*-design.md` entries in `Archive/`) — mirrors `docs/superpowers/plans/2026-08-13-hermes-ide-plugin-requirements-mvp.md`'s status. Nothing left to action for this item specifically.
- **Item 2 (Status bar item) — resolved by PR #633.** The Issue #599 SDK port (`fix/hermes-plugin-sdk-port`) added an explicit `ctx.register({ id: "reqogniloom.status", area: "statusBar.right", ... })` call in the new `activate.ts`, which this item was asking for. Re-verify once #633 merges.

## [2026-08-14-interview-management-engine-design.md](2026-08-14-interview-management-engine-design.md)
**Not implemented — newly found gap (2026-08-20), not previously tracked.** The spec requires a CI job that runs the plugin-package build scripts (`build_opencode_package.py`, etc.) in a temp directory and diffs against the committed `dist/` state, to close a drift gap from commit `c49a503`. No such job exists in `.github/workflows/` — `version-drift-check.yml` only checks deployed API versions against git history, not the plugin packages. No GitHub issue filed yet for this specific gap.

## [2026-08-16-prompt-variable-catalog-design.md](2026-08-16-prompt-variable-catalog-design.md)
**Not implemented — tracked separately.** Phase 3 (Promptfoo test infrastructure) is entirely missing: no `export_promptfoo_configs` management command, no `backend/application/prompt_testing/cases/` directory, no CI job. Already tracked as GitHub Issue #587 ("feat: Promptfoo test infrastructure for prompt templates (Phase 3, Prompt Variable Catalog)") — do not file a duplicate.
