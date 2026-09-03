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

## [Archive/2026-08-21-multi-user-management-design.md](Archive/2026-08-21-multi-user-management-design.md)
All planned features are implemented (2026-08-23). Matches 1:1 the already-verified implementation plan (`docs/superpowers/plans/Archive/2026-08-21-multi-user-management.md`): `TenantRole` model, last-admin invariant at both workspace and tenant scope, `UserAccountService`, shared REST/MCP RBAC-matrix test. No scope in the spec beyond what the plan covers.

## [Archive/2026-08-23-system-workspace-banners-design.md](Archive/2026-08-23-system-workspace-banners-design.md)
All planned features are implemented (2026-08-23, PR #713). Matches the already-verified implementation plan (`docs/superpowers/plans/Archive/2026-08-23-system-workspace-banners.md`). One deliberate deviation: the spec's Data Model section describes a new standalone `banners` Django app, but the model was actually placed in the existing `admin_ops` app (`backend/admin_ops/models.py`) — a documented, architecturally-justified filing decision in the plan itself ("Layer 0, alongside `admin_ops`/`audit`"), not a scope gap.

## [Archive/2026-08-24-theme-presets-design.md](Archive/2026-08-24-theme-presets-design.md)
All planned features are implemented (PR #745, merged 2026-08-25). Matches the already-verified implementation plan (`docs/superpowers/plans/Archive/2026-08-24-theme-presets.md`). Resolves issue **#707** — `gh issue view 707` confirms `state: CLOSED`.

## [Archive/2026-08-20-multi-palette-theming-design.md](Archive/2026-08-20-multi-palette-theming-design.md)
All 3 phases this spec describes are fully implemented, and the structural gap (#707) that previously kept this out of Archive/ is now resolved by [Archive/2026-08-24-theme-presets-design.md](Archive/2026-08-24-theme-presets-design.md) — palette and light/dark mode are now two independent axes.

## [Archive/2026-08-22-multi-artifact-interview-design.md](Archive/2026-08-22-multi-artifact-interview-design.md)
All planned features are implemented. Adapter registry `backend/application/interview_artifact_adapters.py` (+ `tests/test_interview_artifact_adapters.py`) exists exactly as sketched in the spec; `InterviewService` implements the multi-formalize path — see the matching implementation plan `Archive/2026-08-24-multi-artifact-interview.md` above.

## [Archive/2026-08-24-ai-memory-and-search-design.md](Archive/2026-08-24-ai-memory-and-search-design.md)
All planned features are implemented. `backend/memory/` app: `backends.py` (`PgvectorMemoryBackend`), `honcho_backend.py` (`HonchoMemoryBackend`), `context_builder.py` (prompt integration), `tasks.py` (consolidation pipeline), `projector.py`. MCP tools in `backend/mcp_server/tools/memory.py`. Matches implementation plan `docs/superpowers/plans/Archive/2026-08-24-ai-memory-and-search.md`.

## [Archive/2026-08-26-memory-admin-ui-design.md](Archive/2026-08-26-memory-admin-ui-design.md)
All 5 phases implemented (PRs #746, #748, #749, #750, #751) — see the five matching `docs/superpowers/plans/Archive/2026-08-2[67]-memory-admin-phase*.md` entries for per-phase evidence.

---

## Open / deferred (not archived)

## [2026-07-25-phase6-agent-templates-design.md](2026-07-25-phase6-agent-templates-design.md)
**Decided against (2026-08-20), not a gap to fix.** Mirrors the corresponding implementation plan's status (`docs/superpowers/plans/2026-07-25-phase6-agent-templates.md`): `requirements-architect.md` was never created under that exact name — `requirements-architecture-manager.md` exists instead. Reviewed and the user explicitly chose not to rename/create the file to match. The rest of the spec (`change-manager.md`, `quality-auditor.md`, `risk-analyst.md`, `test-engineer.md`, hook scripts) is implemented. Do not re-flag the naming deviation.

## [2026-08-13-hermes-ide-plugin-design.md](2026-08-13-hermes-ide-plugin-design.md)
**Partially resolved (2026-08-20), one item remains genuinely open:**
- **Item 1 (Requirements Views and APIs) — still not implemented, superseded.** The core `connect → list → detail → form` Requirements management flow this spec describes was never built; `integrations/hermes-plugin/reqogniloom/src/` has no Requirement-specific API endpoints or components. Superseded by the interview-management approach instead (see the two `interview-management-*-design.md` entries in `Archive/`) — mirrors `docs/superpowers/plans/2026-08-13-hermes-ide-plugin-requirements-mvp.md`'s status. Nothing left to action for this item specifically.
- **Item 2 (Status bar item) — resolved by PR #633 (merged 2026-08-20).** The Issue #599 SDK port (`fix/hermes-plugin-sdk-port`) added an explicit `ctx.register({ id: "reqogniloom.status", area: "statusBar.right", ... })` call in the new `activate.ts`, which this item was asking for.

## [2026-08-14-interview-management-engine-design.md](2026-08-14-interview-management-engine-design.md)
**Not implemented — newly found gap (2026-08-20), not previously tracked.** The spec requires a CI job that runs the plugin-package build scripts (`build_opencode_package.py`, etc.) in a temp directory and diffs against the committed `dist/` state, to close a drift gap from commit `c49a503`. No such job exists in `.github/workflows/` — `version-drift-check.yml` only checks deployed API versions against git history, not the plugin packages. No GitHub issue filed yet for this specific gap.

## [2026-08-16-prompt-variable-catalog-design.md](2026-08-16-prompt-variable-catalog-design.md)
**Not implemented — tracked separately.** Phase 3 (Promptfoo test infrastructure) is entirely missing: no `export_promptfoo_configs` management command, no `backend/application/prompt_testing/cases/` directory, no CI job. Already tracked as GitHub Issue #587 ("feat: Promptfoo test infrastructure for prompt templates (Phase 3, Prompt Variable Catalog)") — do not file a duplicate.

## [2026-09-03-attribute-definition-design.md](2026-09-03-attribute-definition-design.md)
**Not implemented — new spec (2026-09-03).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. N/Q1.2. First of several independent follow-up specs from that audit (see the audit's own decomposition into ~11 architectural themes); implementation plan not yet written.
