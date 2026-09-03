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

## [2026-08-20-multi-palette-theming-design.md](2026-08-20-multi-palette-theming-design.md)
**Literal scope fully implemented, structural gap remains — kept out of Archive/ (2026-08-23).** All 3 phases this spec describes are fully built (verified in `docs/superpowers/plans/index.md`'s three `2026-08-2[01]-multi-palette-theming-phase*.md` entries) — the spec's own §5 already records all three as done with exact test counts. Not archived because open issue **#707** ("Theme palette and light/dark mode cannot be combined — flat list instead of two axes") is a structural gap this spec never addressed: palette and light/dark mode share one flat `THEMES` registry instead of being two independent, combinable axes. Tracked in `docs/UMSETZUNGSPLAN_POST-1.7.0-BACKLOG.md` Group K (P3, needs its own architectural redesign spec).

## [2026-09-03-attribute-definition-design.md](2026-09-03-attribute-definition-design.md)
**Not implemented — new spec (2026-09-03).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. N/Q1.2. First of several independent follow-up specs from that audit (see the audit's own decomposition into ~11 architectural themes); implementation plan not yet written. Has a real ordering dependency on the second spec below — see its Section 7.

## [2026-09-03-datenmodell-konsolidierung-design.md](2026-09-03-datenmodell-konsolidierung-design.md)
**Not implemented — new spec (2026-09-03, amended same day).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. B1/B2/B6/Q2.3. Second of several independent follow-up specs from the same audit. Its Section 7 documents an ordering dependency: this spec's status-consolidation phase must land before the attribute-definition spec's bootstrap migration. Amended while writing the interview-engine-fix spec: the audit's B2 text wrongly listed `GlossaryTerm` as already Artifact-backed — it isn't (verified against `persistence/models.py` and `interview_artifact_adapters.py`'s explicit rejection) — so Section 4 now covers Diagram/Icd/GlossaryTerm together, not just the first two. Implementation plan not yet written.

## [2026-09-03-traceability-semantik-design.md](2026-09-03-traceability-semantik-design.md)
**Not implemented — new spec (2026-09-03, amended same day).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. B4/U1-U3/Q1.6/Q2.4. Third of several independent follow-up specs from the same audit. Reduces 15 trace-link types to 8, makes the link-type catalog a configurable Global/Workspace system object (same inheritance pattern as workflow-defaults and attribute-definition), and implements the suspect-propagation mechanism that already-filed GitHub issue #849 needs. Has a cross-spec note (Section 5) for the datenmodell-konsolidierung spec (`suspect` should eventually move to `Artifact`, not implemented there yet) and (Section 5) for the ki-vorschlag-als-zustand spec (`proposed_by`/`proposed_at` fields on TraceLink, not implemented there yet). Amended while writing the github-jira-integration spec: `references`' allowed targets now include `ExternalRef`. Implementation plan not yet written.

## [2026-09-03-interview-engine-fix-design.md](2026-09-03-interview-engine-fix-design.md)
**Not implemented — new spec (2026-09-03).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. L, R6. Fourth of several independent follow-up specs from the same audit. Smaller than the first three: reuses the already-productive `ARTIFACT_CREATION_ADAPTERS` registry (from the archived multi-artifact-interview spec) to fix the single-kind `formalize()` path instead of building new infrastructure. Depends on the datenmodell-konsolidierung spec's amended Section 4 for GlossaryTerm interview support. Deliberately deviates from the audit's S19 UI recommendation (keeps `/interviews` as the primary surface, reduces the widget instead) per explicit user direction. Implementation plan not yet written.

## [2026-09-03-ki-vorschlag-als-zustand-design.md](2026-09-03-ki-vorschlag-als-zustand-design.md)
**Not implemented — new spec (2026-09-03).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. Q2.1/E2.1. Fifth of several independent follow-up specs from the same audit. Models "AI proposal, pending human confirmation" as a `proposed` state in the existing Workflow Engine (not a new parallel field/mechanism) — Rigor-preset-coupled via each preset's default workflow graph (minimal: no `proposed` state; standard/extended: yes). Subsumes the audit's separately-tracked E2.1 (API-key scopes/expiry) as a prerequisite (`ApiKey.principal_type`/`scope`/`workspace_ids`/`expires_at`). Deliberately excludes workflow transitions from proposal-state (stays with existing signature-gates) per explicit user direction. Depends on the traceability-semantik spec's `TraceLink` schema extension point for the link-level `proposed_by`/`proposed_at` fields. Implementation plan not yet written.

## [2026-09-03-menschen-im-system-design.md](2026-09-03-menschen-im-system-design.md)
**Not implemented — new spec (2026-09-03).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. Q1.1 (audit's own #1 priority by value/effort). Sixth of several independent follow-up specs from the same audit. Adds `owner` (accountable) and `assignee` (currently tasked) as two separate User FKs on all 10 artifact types — finishes two already-started-but-abandoned migrations found in the code (`Risk.owner_user` expand/contract, REQ-L1-029; `Issue.assignee_id`'s loose UUIDField). Adds generic `Comment` (on `persistence.Artifact`) and `Notification` (4 triggers) entities. Wires assignment changes into the existing `AuditEntry`/`OP_ASSIGN` audit mechanism (already defined, never used) rather than inventing new history tracking. Deliberately excludes per-transition assignment/deadlines/escalation/delegation (Q2.5 — a separate, deeper concept per the audit's own framing). Implementation plan not yet written.

## [2026-09-03-github-jira-integration-design.md](2026-09-03-github-jira-integration-design.md)
**Not implemented — new spec (2026-09-03).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. W/E1/Q2.10. Seventh of several independent follow-up specs from the same audit. Follows the audit's own 3-stage plan (Link-Only / Inbound-Sync / Outbound+Agent). `ExternalRef` gets its own Artifact-backing row (same pattern as Diagram/Icd/GlossaryTerm in the datenmodell-konsolidierung spec) so it can participate in `TraceLink` via `references` — required an amendment to the traceability-semantik spec (`references`' allowed targets). Inbound sync rules extend the Workflow Engine with an `external_trigger` field on transitions rather than a parallel mechanism. Outbound credentials: per-workspace Personal Access Token (explicit user choice over full OAuth-App flow). GitLab and webhook self-service (E2.2) explicitly out of scope. Implementation plan not yet written.

## [2026-09-03-mcp-modernisierung-design.md](2026-09-03-mcp-modernisierung-design.md)
**Not implemented — new spec (2026-09-03).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. C5/C6/E3.4/I.7. Eighth of several independent follow-up specs from the same audit. Protocol version bump (2024-11-05 → 2025-06-18), Streamable HTTP with `Mcp-Session-Id` (legacy SSE kept, not removed), `resources/*` for artifact markdown, `prompts/*` for the existing PromptTemplate system, new `icd.*` read tool group for REST/MCP parity. Two manifest-size filters with explicitly different enforcement: `ApiKey.scope` (from the ki-vorschlag-als-zustand spec) is a real security boundary enforced at both `tools/list` and `tools/call`; new `ApiKey.tool_groups` is list-only curation — `tools/call` still works for any permitted tool regardless of `tool_groups`, a distinction the user explicitly asked to have clarified before approving. The pure bugfixes from Kap. H1/H4/R4 are already tracked as GitHub issue #846, not part of this spec. Implementation plan not yet written.

## [2026-09-03-tabellenansicht-design.md](2026-09-03-tabellenansicht-design.md)
**Not implemented — new spec (2026-09-03).** From `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kap. Q1.3/C8. Ninth of several independent follow-up specs from the same audit. Table view with type-aware per-column filtering and multi-sort, driven by the same Attribute-Definition metadata `ArtifactForm` already uses (also structurally fixes C8's "filters not in schema" complaint as a byproduct). Two persistence concepts per explicit design choice: `UserTableViewState` (unnamed, auto-updating "where I left off") and `SavedView` (named, explicitly saved, optionally workspace-shared) — the user asked specifically for saveable filters. Generic `ARTIFACT_UPDATE_ADAPTERS`-based bulk-update/bulk-transition endpoints with partial-success responses; workflow-state fields (`editable: "workflow"`) are hard-rejected from bulk-update regardless of caller, enforced in code per explicit user requirement ("unter Wahrung aller Workflows"), not just documented. Explicitly excludes formulas/pivot-tables/drag-fill. Implementation plan not yet written.
