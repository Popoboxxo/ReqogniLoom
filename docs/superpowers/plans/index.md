# Plan Index

This index lists every plan/scoping document in this directory tree and its implementation status,
proven against the source code (not against the plan's own claims).

- **`Archive/`** — plans whose full scope has been implemented and verified. Kept for historical reference
  (design rationale, rejected alternatives, task-by-task execution record); no more action expected.
- **This directory (top level)** — plans with real open work, or explicitly deferred/superseded. Statuses re-checked against `origin/main` on 2026-11-04.


## Top level — open work

## [2026-09-24-motivated-improvement-plan.md](2026-09-24-motivated-improvement-plan.md)
**Open — audit-based improvement plan; partially implemented and not a release approval.** Derived from the 2026-09 system audit, it prioritizes P1 validation, QS-first evidence, a central Django core with a versioned contract/tool registry, and Bluepencil as QS-only/default-off. The plan records open measurements and implementation waves; it contains no application-code changes.

Implementation status as of 2026-09-26 (recorded in the plan's own §14 "Umsetzungsstand"; provenance in [`09-evidence-register.md`](../../se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md) §7.4/§7.5/§9.17, verified via `git log`/`git rev-parse`/`gh pr view`):
- **W0** — evidence baseline and the W0/W1 slice **partially implemented**; W0 exit criteria **not fully met**.
- **W1** — security slice and close-out **merged** (PR #1070 / `82f13395`; PR #1071 / `acde772e`, incl. `7012a7c2`). W1 exit criteria **not fully met**; the W1 residual items stay open.
- **W2** — implemented in **three commits**, **PR #1073 open** against `main`: `6f145c87`, `14fc05e5`, `d4d912bf` (base `acde772e`; diff 30 files, +4858 / −153). Status is **`TEILWEISE VERIFIZIERT`** — the revision binding now exists, but the W2 exit criteria are **not fully met** and no track is marked `VERIFIZIERT` on green tests alone.
- **W3, W4, W5** — **not started**.

Do not read the waves as closed: green tests alone never establish `VERIFIZIERT` (the evidence register's §6 also requires a commit/revision binding), and the open items — the deferred D1 `UniqueConstraint(session, artifact)`, the missing correlation field, W2 negative test 6 (chat/provider outage), `CR-13`, `CR-17`/`CR-22`/`CR-26`, `pl_user`, the service-wrapper `expected_version` gap, and the orphan-gate residual window — all remain **open**.

Update 2026-11-04: PR #1073 (the W2 slice) was merged on 2026-09-26, so the "PR #1073 open" wording above is stale; the plan's §14 itself was not refreshed. No evidence that the W3-W5 exit criteria were met. Backlog plans A-G in `docs/plans/` carry some of the follow-up work, but the waves are not closed.

## [2026-11-01-opencode-v2-support.md](2026-11-01-opencode-v2-support.md)
**Open — rewritten 2026-11-03, tasks not started.** Implementation plan for native OpenCode 2 support next to OpenCode 1 with one shared Streamable HTTP config (URL `…/mcp/`, V1 form). Based on a 2026-11-03 spike against a mock MCP server; what the spike did not prove is tracked in #1702–#1706. All 25 task checkboxes are unchecked. Spec: [`specs/2026-11-01-opencode-v2-support-design.md`](../specs/2026-11-01-opencode-v2-support-design.md).

## [2026-08-07-artifact-quality-assessment-scoping.md](2026-08-07-artifact-quality-assessment-scoping.md)
**Open — v1, v1.1 and v3 delivered; v2 and v2.1 missing.** Scoping doc for the LLM-based content quality score (#378). The v1 vertical (append-only `QualityAssessment`, `quality.assess`/`quality.query`, REST, UI badge/panel), the extra prompt slots (ADR/TestCase/Risk) and the SE-Auditor `QUAL-P1/P2/P3` rules are implemented. The automatic trigger on workflow transitions (v2, tracked as #1578) and the periodic sweep (v2.1) are not built, so the document stays open.

## [2026-09-21-open-issues-bundle.md](2026-09-21-open-issues-bundle.md)
**Open — mostly executed, four items remain (the earlier "not yet implemented" text was stale).** Cluster plan for 40 open issues as of 2026-09-21. Clusters C1-C6 have been executed (embedding alignment, SE-audit cycle/waivers, frontend integrity, E2E hardening, SE completeness, ReqIF identity; MOE/MOP/TPM was decided against in ADR-008). Still open: #801 (inspector for other entity types), #587 (Promptfoo), #879 (milestones, partly present: `milestone_service.py` exists but the issue is unreconciled) and #946 (debug annotations).

## [2026-09-04-open-decisions.md](2026-09-04-open-decisions.md)
**Open — decision log; items 2, 5, 6, 7 still undecided or moot.** Decision log from the 2026-09 plan series. Decision 1 is settled; the traceability decisions (3, 4) were effectively executed with the plan defaults, but decision 2 (provenance deletion on TraceLink confirm, `trace_link_service.py` still sets `proposed_by = None`) is still unapplied and decisions 5-7 belong to plans that are not implemented. Stays open until those plans are built or dropped.

## [2026-09-03-dokumentensicht.md](2026-09-03-dokumentensicht.md)
**Superseded by [`specs/2026-11-04-dokumentensicht-neu-design.md`](../specs/2026-11-04-dokumentensicht-neu-design.md) — do not implement.** The 2026-11 `Document` artifact (ADR-026, #1374) took the name; the section-tree/read-mode design in this plan was replaced by the editable `DocumentView` spec of 2026-11-04. No implementation plan exists yet; it waits for #1670 P1/P4 and slice 1 of the Tabellenansicht plan.

## [2026-09-03-github-jira-integration.md](2026-09-03-github-jira-integration.md)
**Open — not implemented.** There is no `integrations` app, no `ExternalRef`/`IntegrationConfig`/credential model, no webhook receivers and no GitHub/Jira adapters on main. The plan's dependency specs (audit series) are mostly landed, so it could be picked up after a freshness check.

## [2026-09-03-mcp-modernisierung.md](2026-09-03-mcp-modernisierung.md)
**Open — not implemented.** The server still advertises protocol 2024-11-05; there is no `resources/*`, `prompts/*`, session-id or `ApiKey.tool_groups` support. Only the ICD read tools (`icd.get`/`icd.query`) exist. The markdown-renderer conflict with the dokumentensicht plan is moot until either is built.

## [2026-09-03-rollenbasierte-sichten.md](2026-09-03-rollenbasierte-sichten.md)
**Open — not implemented.** No navigation-visibility system object, no `expert_mode_enabled` user preference and no role-resolved sidebar exist on main. Issues #810/#848 are closed, but the planned deliverables are absent, so the plan needs a freshness review before use.

## [2026-11-04-tabellenansicht-neu.md](2026-11-04-tabellenansicht-neu.md)
**Open — not implemented (plan written 2026-11-04, replaces the 2026-09-03 plan).** Five slices: (1) backend core — the Layer-2 update seam `update_artifact_fields`, the Python filter DSL, the table query service, `PATCH artifacts/bulk-update/` (atomic/partial, max 100, `expected_version`) with REST and `artifact.bulk_update`; (2) bulk-transition; (3) saved views and per-user table state (models, RLS, REST, MCP); (4) frontend `ArtifactTable`; (5) E2E guardrail. Slice 1 ships alone and is what the Dokumentensicht needs. Freeze (409) tests are documented xfail until #1670 P4. Spec: [`specs/2026-09-03-tabellenansicht-design.md`](../specs/2026-09-03-tabellenansicht-design.md) (updated 2026-11-04).

## [2026-09-03-tabellenansicht.md](2026-09-03-tabellenansicht.md)
**Superseded by [2026-11-04-tabellenansicht-neu.md](2026-11-04-tabellenansicht-neu.md) — do not implement.** The old 24-task plan has a stale bulk-update contract (partial success, `ids[]`, limit 200 against the Dokumentensicht's all-or-nothing, `items[]`, 100), no update seam, a wrong migration number and React 18. Nothing of it exists on main.

## [2026-08-08-reqmd-interop-and-inspiration-concept.md](2026-08-08-reqmd-interop-and-inspiration-concept.md)
**Deferred — concept document, no task list.** The proposed reqmd import/export bridge and the CTRF test-result adapter do not exist in the backend, and version-pinned trace links are not implemented (only the `suspect` flag). Only the audited-waiver idea was realised, independently, through #569. Stays deferred until the bridge is explicitly wanted.

## [2026-09-03-menschen-im-system.md](2026-09-03-menschen-im-system.md)
**Superseded — kept at top level as historical record of the original scope.** The owner/assignment half was replaced by the central `Artifact.owner`/`reporter` model (Attribut-System v3, AWMS migration plans); the collaboration half (comments, notifications, preferences) was re-scoped, implemented and merged in PR #956, see [Archive/2026-09-03-menschen-im-system-collaboration.md](Archive/2026-09-03-menschen-im-system-collaboration.md). Original header notes: tasks 1–6, 12, 13, 14, 21, 26 cancelled; the physical column drop is left as an AWMS-owned contract step.

## [2026-08-13-hermes-ide-plugin-requirements-mvp.md](2026-08-13-hermes-ide-plugin-requirements-mvp.md)
**Superseded — nothing left to action.** Plan for a REST-backed requirements CRUD panel in the Hermes IDE plugin. The plugin on main implements the MCP-backed interview approach instead (see the archived interview-management plugin plan), and the planned CI workflow was never added.

## Archive/ — fully implemented

## [Archive/2026-07-23-phase0-status-unification.md](Archive/2026-07-23-phase0-status-unification.md)
All planned features are implemented. Checked `backend/workflow/definition_store.py` for `get_state_meta`, `backend/workflow/services.py` for `outdate`/`reactivate`, and `backend/application/requirement_service.py` to confirm rewired deletes routing through `outdate()`.

## [Archive/2026-07-24-phase1-mcp-crud-completion.md](Archive/2026-07-24-phase1-mcp-crud-completion.md)
All planned features are implemented. Verified `StakeholderNeedService`, `RiskService`, `IssueService` list filters excluding outdated statuses. Checked `diagram/services.py` uses `outdate`. Verified `_WRITE_TOOL_PREFIXES` in `backend/mcp_server/tool_registry.py` includes tools like `adr.outdate`, `change_request.outdate`, etc. Checked `workspace.get_preferences` in `admin.py`.

## [Archive/2026-07-24-phase2-context-generators.md](Archive/2026-07-24-phase2-context-generators.md)
All planned features are implemented. Checked `cross_cutting.py` for `DEFAULT_CONTEXT_TOKEN_BUDGETS` and new context handlers including `_handle_test_coverage` and `_handle_change_impact`. Verified `_handle_workspace_get_context` accepts the new `depth` parameter.

## [Archive/2026-07-24-phase3-derive-write-mode.md](Archive/2026-07-24-phase3-derive-write-mode.md)
All planned features are implemented. Checked `ai_derivation_service.py` for `_write_derived_entity`, `_auto_approve`, and the new derive methods. Verified `tool_registry.py` includes new write mode tools (`ai_derivation.derive_requirements_from_need`, `test.derive_from_requirement`, etc.) in `_WRITE_TOOL_PREFIXES`. As documented in the plan, `derive_risks_from_architecture` and others were implemented under the `ai_derivation` prefix to avoid tool prefix collisions.

## [Archive/2026-07-24-phase4-prompt-templates.md](Archive/2026-07-24-phase4-prompt-templates.md)
All planned features are implemented. Verified that the `PromptTemplate` model exists in `backend/persistence/models.py`, the `_get_template_content` lookup logic is present in `backend/application/ai_derivation_service.py`, and the new MCP tools (`prompt_template.list()`, `.create()`, and `.update()`) are correctly defined in `backend/mcp_server/tools/prompt_template.py`.

## [Archive/2026-07-25-phase5-review-endpoints.md](Archive/2026-07-25-phase5-review-endpoints.md)
All planned features are implemented. Verified that the `ReviewPolicy` model is present in `backend/persistence/models.py` along with its migration `0046_add_review_policy.py`. `is_approval_gate` was properly extracted into `backend/workflow/services.py` and the `review.*` MCP tool group exists in `backend/mcp_server/tools/review.py`.

## [Archive/2026-07-30-dogfood-readiness.md](Archive/2026-07-30-dogfood-readiness.md)
All planned features are implemented. The plan mentioned creating `test_mass_assignment_regression.py` only if an equivalent test did not exist; verified an equivalent test already exists inside `backend/rest_api/tests/test_auth_login.py` (covering mass assignment), so no new file was needed. Also confirmed `backend/llm_adapter/providers.py` reads `self.model_name = config.model_name or self.MODEL_NAME`, and `backend/llm_adapter/tests/test_provider_contracts.py` includes the new `test_http_provider_honours_configured_model_name` regression test.

## [Archive/2026-07-30-ziele-und-hauptziel.md](Archive/2026-07-30-ziele-und-hauptziel.md)
All planned features are implemented.
- The `Goal` and `MainGoal` models are present in `backend/application/models.py`.
- The `goals_enabled` and `goals_ai_enabled` fields exist in `backend/persistence/models.py`.
- Both `goal_service.py` and `main_goal_service.py` (and their respective test files) exist in `backend/application/`.

## [Archive/2026-08-01-ui-konzept-vollrollout.md](Archive/2026-08-01-ui-konzept-vollrollout.md)
All planned features are implemented. The one apparent gap is resolved, not open:
- **Resolved (was flagged "not implemented")**: Task 4.3 investigated deleting `RequirementTreeNode.tsx` per the plan's "1 tree implementation after Phase 4" goal, found it is NOT dead code and NOT an accidental duplicate of the artifact-tree pattern — it is a lazy, per-node-fetching explorer over the `derives-from`/`derived-by` trace-link graph that `WorkspaceTree`'s synchronous flat-`nodes[]` contract cannot express. It was deliberately kept as a documented, permanent exception (2026-08-03). Proof: `docs/UI_KONZEPT.md` §16.3 "Dokumentierte Ausnahmen vom Standard" (`RequirementTreeNode.tsx` entry) and `frontend/src/test/ui-ratchet.test.ts:305-327` (`KNOWN_TREE_IMPLEMENTATIONS` baseline lowered 3→2 in the same PR, ratchet-gated against re-adding it). Deleting it now would be a regression, not a cleanup — do not re-flag this item.

(Other tasks — `EmptyState`, `Dialog`, `ArtifactRow`, missing `de.json` keys, ESLint rules, UI updates on routes like ADR/Diagram/etc. — checked and are implemented.)

## [Archive/2026-08-05-mcp-plugin-distribution.md](Archive/2026-08-05-mcp-plugin-distribution.md)
All planned features are implemented.
- `export_tool_manifest.py` is present in `backend/mcp_server/management/commands/`.
- `test_tool_manifest_drift.py` is present in `backend/mcp_server/tests/`.
- `DOMAIN_MODEL.md` and the packaging scripts (`package_skills.py`, `build_claude_plugin.py`, `build_antigravity_plugin.py`, `build_opencode_package.py`) exist in their respective directories.

## [Archive/2026-08-07-diagram-node-graph-implementation.md](Archive/2026-08-07-diagram-node-graph-implementation.md)
All planned features are implemented. Found the migration files (`0006_add_node_graph_payload_format.py`, `0007_diagram_artifact.py`), backend logic (`backend/diagram/node_graph.py`, `convert_canvas_to_node_graph.py`), and frontend components (e.g. `DiagramGraphEditorPage.tsx`, modifications in `DiagramDetailView.tsx`). `sync_node_links` and `_resolve_artifact_id` were added to `traceability_connector.py`.

## [Archive/2026-08-07-diagram-node-graph-refactor-scoping.md](Archive/2026-08-07-diagram-node-graph-refactor-scoping.md)
All planned features are implemented. The corresponding architectural decisions (e.g. `ADR-DS-02` for diagram position persistence) and the backend/frontend components are fully implemented as defined in the codebase.

## [Archive/2026-08-07-workspace-context-graph-implementation.md](Archive/2026-08-07-workspace-context-graph-implementation.md)
All 9 tasks implemented (2026-08-20, PR #630). `backend/context_graph/` app (models, RLS migration, projector, glossary generator, admin_ops, Celery task, management command), `application/context_service.py` facade, `context.query`/`context.related` MCP tools, per-workspace settings REST endpoints + frontend `ContextGraphSettingsSection`. 374 backend tests + 1071/1073 frontend tests green (2 unrelated pre-existing failures).
Three deliberate deviations from this plan's literal text, documented in the code itself:
1. The glossary generator uses title-text matching against `GlossaryTerm.term`/`.synonyms`, not `uses-term` TraceLinks — verified no service in this codebase ever creates one (`GlossaryTerm` isn't even resolvable to an Artifact id), so there was no data to query. See `context_graph/generators/glossary.py`'s module docstring.
2. `context.query`/`context.related` were added to the existing `CrossCuttingToolGroup` (`mcp_server/tools/cross_cutting.py`), not a new `ContextToolGroup`/`context.py` — the `context` prefix was already owned by `context.test_coverage`/`context.change_impact` (Phase 2), so a second registration would have silently overwritten it in `tool_registry.py`'s prefix dict.
3. Tenant-context propagation around the projector's `handle_event` (`persistence.middleware.set_request_tenant`/`clear_request_tenant`, resolving tenant via `Workspace.unscoped`) was not addressed by the plan at all and was added from scratch — no existing subscriber on `application/event_bus.py` (including the never-wired `webhook_dispatcher.py`) had ever solved this.

## [Archive/2026-08-07-workspace-context-graph-scoping.md](Archive/2026-08-07-workspace-context-graph-scoping.md)
The v1 slice this scoping doc's §9 phasing describes is implemented — see the implementation-plan entry above for the full status and documented deviations.

## [Archive/2026-08-08-requirement-bundle-export-query-plan.md](Archive/2026-08-08-requirement-bundle-export-query-plan.md)
All planned features are implemented.
- `RequirementBundleQueryService` is implemented in `backend/application/requirement_bundle_service.py`.
- The JSON/CSV formatters are implemented in `backend/application/requirement_bundle_formatters.py` and wired into `backend/rest_api/views.py` / `backend/rest_api/urls.py`.
- The `requirement_bundle.export` and `requirement_bundle.attribute_schema` MCP tools exist in `backend/mcp_server/tools/requirement_bundle.py` with tests in `backend/mcp_server/tests/test_requirement_bundle_tool_group.py`.

## [Archive/2026-08-09-requirement-bundle-export-compression-plan.md](Archive/2026-08-09-requirement-bundle-export-compression-plan.md)
All planned features are implemented.
- `backend/application/bundle_compression_service.py` implements `BundleCompressionService`.
- `bundle-compression-status` polling endpoint is registered in `backend/rest_api/urls.py` and `backend/rest_api/views.py`.
- MCP `compression_status` integration is present in `backend/mcp_server/tools/requirement_bundle.py`.

## [Archive/2026-08-11-requirement-bundle-export-ui-panel-plan.md](Archive/2026-08-11-requirement-bundle-export-ui-panel-plan.md)
All planned features are implemented.
- `RequirementBundleExportPanel.tsx` is implemented in `frontend/src/components/RequirementBundleExport/`.
- `useBundleCompressionStatus.ts` polling hook exists in `frontend/src/hooks/`.
- The panel is wired into `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx`.

## [Archive/2026-08-14-interview-management-engine.md](Archive/2026-08-14-interview-management-engine.md)
All planned features are implemented.
- `InterviewSession` model exists in `backend/persistence/models.py`.
- `InterviewService` with its methods (`start`, `get_state`, `answer`, `formalize`, `grounding_context`) is fully implemented in `backend/application/interview_service.py`.
- Interview protocol configuration (`parse_protocol_yaml`) exists in `backend/application/interview_protocol.py`.
- The MCP tools and packaging (`dist/agent-skills/interview-management`) are present.

## [Archive/2026-08-14-interview-management-hermes-plugin.md](Archive/2026-08-14-interview-management-hermes-plugin.md)
All planned features are implemented.
- `integrations/hermes-plugin/reqogniloom/src/` contains `mcpClient.ts` with all the typed `interview.*` wrappers.
- The React components `InterviewListView.tsx` and `InterviewFormView.tsx` are fully implemented.
- Integration into the main panel is confirmed in `ReqogniLoomPanel.tsx`.

## [Archive/2026-08-14-interview-management-web-widget.md](Archive/2026-08-14-interview-management-web-widget.md)
All planned features are implemented.
- The REST facade `/api/v1/interviews/` with the chat endpoint is implemented in `backend/rest_api/interview_views.py`.
- `interview.chat_turn` LLM capability exists in `generate_chat_turn` within `interview_service.py`.
- The frontend `interviews.ts` API client exists.
- The widget UI shell and panes (`InterviewWidget.tsx`, `InterviewChatPane.tsx`, `InterviewArtifactPane.tsx`) are present in `frontend/src/components/InterviewWidget/`.

## [Archive/2026-08-16-prompt-variable-catalog.md](Archive/2026-08-16-prompt-variable-catalog.md)
All planned features are implemented.
- `PromptVariable` model exists in `backend/persistence/models.py`.
- The shared resolver `resolve_and_render` is implemented in `backend/application/prompt_resolver.py`.
- The prompt variable services and MCP tool groups (`backend/mcp_server/tools/prompt_variable.py`) are present.
- The API breaking change rename from `breadth`/`depth` to `max_breadth`/`max_depth` was verified in `backend/mcp_server/tools/architecture.py`.
- Frontend `PromptVariablesSection.tsx` and `prompt-variables.ts` API client are fully implemented.

## [Archive/2026-08-18-systemaudit-bugfix-clusters.md](Archive/2026-08-18-systemaudit-bugfix-clusters.md)
All in-scope clusters are implemented, verified cluster-by-cluster (2026-08-23). Cluster 0+1 (INFRA-01..04): `docker-compose.yml`/`docker-compose.override.yml` document all four findings with the exact audit code as a named comment anchor (INFRA-01 `ports: !override`, INFRA-02 dev-only image tag + `pull_policy: build`, INFRA-03 Celery `--concurrency` pinning, INFRA-04 memory limit `128M`→`2G`). Cluster 2 (BUG-01/02): `backend/rest_api/tests/test_requirement_title_required_bug02.py` and `frontend/src/test/workspace-language-persistence.test.tsx` exist. Cluster 3 (BUG-03/04/05): `frontend/src/components/Reviews/useReviewsData.ts:141-152` calls `queryClient.invalidateQueries(...)` for review status transitions. Cluster 5 (i18n BUG-06/07/10): closed per `CHANGELOG.md` [1.7.0-beta.3]. Cluster 6 (BUG-09/#53) and Cluster 8 (BUG-15): both closed per `CHANGELOG.md` [1.7.0-beta.3]. Cluster 9 (BUG-17/21): `backend/icd/icd_manager.py:365` auto-increments `IcdVersion.version_number`; `seed_toothbrush.py` exists as a documented management command. Cluster 10 (bulk-endpoint spike) was a verification-only task with no fix commitment. **Cluster 7 (sidebar) was explicitly declared "OUT OF SCOPE for this batch" in the plan itself** — not part of this plan's full scope; the sidebar issue chain (#720/#449/#592/#608) is tracked separately in `docs/UMSETZUNGSPLAN_POST-1.7.0-BACKLOG.md`.

## [Archive/2026-08-21-multi-user-management.md](Archive/2026-08-21-multi-user-management.md)
All planned features are implemented (2026-08-23, part of the [1.7.0-beta.5] release, #686). `backend/auth_tenancy/models.py:153` — `TenantRole(TenantScopedModel)`; migrations `0009_add_tenant_role.py`/`0010_backfill_tenant_admins.py`. `backend/auth_tenancy/services/authorization.py:53` — `LastAdminError`, `is_tenant_admin`, `assign_tenant_admin`, `revoke_tenant_admin` (660-822) with `select_for_update()`. `UserAccountService` in `user_account.py`. Tests: `test_tenant_role_model.py`, `test_last_admin_invariant.py`, `test_provisioning.py`, `test_user_account_service.py`. MCP: `user.assign_tenant_admin`/`user.revoke_tenant_admin` in `backend/mcp_server/tools/users.py`. REST: `backend/rest_api/user_management_views.py`, with a shared RBAC-matrix test on both surfaces (`test_user_management_rbac_matrix.py` in both `rest_api/tests/` and `mcp_server/tests/`). Frontend: `frontend/src/components/Settings/UserManagement/UserManagement.tsx`.

## [Archive/2026-08-22-review-findings-remediation.md](Archive/2026-08-22-review-findings-remediation.md)
All planned remediation clusters are implemented (2026-08-22, PR #698): the critical data-reachability bug, WCAG contrast/label/keyboard fixes, backend security and code-hygiene batches (timing-safe compares, error-envelope hardening, MCP `params.api_key` stdio restriction, dead-code removal), and the design-consistency sweep (Dialog migration, button unification, DE translations). The source reviews were marked resolved in the same PR (`chore: mark review docs as resolved`). The plan file itself was never committed during execution — archived here after the fact for historical reference.

## [Archive/2026-08-23-system-workspace-banners.md](Archive/2026-08-23-system-workspace-banners.md)
All planned features are implemented (2026-08-23, PR #713, merged). `backend/admin_ops/models.py:146,153,162` — `BannerScope`, `BannerLevel`, `Banner(TenantScopedModel)`. `backend/admin_ops/banner_rest.py` — `GlobalBannerView`, `WorkspaceBannerView`, `PublicLoginBannerView`; all three routes wired in `backend/rest_api/urls.py:192,334-341`. Frontend: `BannerStack.tsx`, `SystemSettings/BannerSection.tsx`, `WorkspaceSettings/WorkspaceBannerSection.tsx`, `NavigationShell/LoginPage.tsx`, each with tests and CSS modules. The plan's own final-review fix wave (DEFAULT_TENANT_ID bug, RLS policy, `Operation.READ` gating) is recorded in the plan text itself as already resolved — no open remainder.

## [Archive/2026-08-24-theme-presets.md](Archive/2026-08-24-theme-presets.md)
All planned features are implemented (PR #745, merged 2026-08-25) and closed issue **#707**. `backend/admin_ops/models.py:286` — `ThemePalette(TenantScopedModel)`; `backend/admin_ops/theme_rest.py` — `ThemePaletteListView`, `ThemePaletteDetailView`, `ThemePaletteExportView`. Frontend `ThemeContext.tsx` rewritten for two independent axes (`paletteKey` + `mode`, `STORAGE_KEY_PALETTE`/`STORAGE_KEY_MODE`), confirmed by its own header comment ("dropped when this file was rewritten for two-axis palettes"). `gh issue view 707` confirms `state: CLOSED`. This also resolves the shared structural gap that had kept the three multi-palette-theming phase plans and their design spec out of Archive/ — see below.

## [Archive/2026-08-20-multi-palette-theming-phase1.md](Archive/2026-08-20-multi-palette-theming-phase1.md)
All planned features are implemented, and the structural gap (#707) that previously kept this out of Archive/ is now resolved by [Archive/2026-08-24-theme-presets.md](Archive/2026-08-24-theme-presets.md) (PR #745) — palette and light/dark mode are now two independent, freely combinable axes. `gh issue view 707` confirms `state: CLOSED`.

## [Archive/2026-08-21-multi-palette-theming-phase2.md](Archive/2026-08-21-multi-palette-theming-phase2.md)
All planned features are implemented; same #707 resolution as Phase 1 above applies — see [Archive/2026-08-24-theme-presets.md](Archive/2026-08-24-theme-presets.md).

## [Archive/2026-08-21-multi-palette-theming-phase3.md](Archive/2026-08-21-multi-palette-theming-phase3.md)
All planned features are implemented; same #707 resolution as Phase 1 above applies — see [Archive/2026-08-24-theme-presets.md](Archive/2026-08-24-theme-presets.md).

## [Archive/2026-08-24-multi-artifact-interview.md](Archive/2026-08-24-multi-artifact-interview.md)
All planned features are implemented (PR #742, merged). `backend/persistence/models.py:2470` — `InterviewSessionArtifact(TenantScopedModel)`. `backend/application/interview_service.py:967` — `_formalize_multi(self, ctx, session, confirmed_proposal)` implements the atomic multi-artifact formalize path; `interview.protocol.multi` prompt template and proposal-preview parsing exist per `git log --grep`. Test coverage confirmed via `test_interview_formalize_multi.py::test_single_mode_formalize_unchanged` reference in the service module.

## [Archive/2026-08-24-ai-memory-and-search.md](Archive/2026-08-24-ai-memory-and-search.md)
All planned features are implemented (PR #746). `backend/memory/` app: `backends.py` (`PgvectorMemoryBackend`), `honcho_backend.py` (`HonchoMemoryBackend`), `context_builder.py`, `tasks.py` (consolidation pipeline, `tests/test_consolidation.py` + `test_consolidation_e2e.py`), `projector.py`. MCP tools in `backend/mcp_server/tools/memory.py`.

## [Archive/2026-08-24-bugfix-session.md](Archive/2026-08-24-bugfix-session.md)
Session-log/implementation plan against 30 referenced GitHub issues (17 in scope). PR #740 ("Bugfix session 2026-08-24 … 20 commits") merged, title/date match the plan. Sample of referenced issues (#662, #663, #664, #667, #682, #708, #710) all `CLOSED`. Archived here in the same style as `Archive/2026-08-18-systemaudit-bugfix-clusters.md`.

## [Archive/2026-08-26-memory-admin-phase1-workspace-overview.md](Archive/2026-08-26-memory-admin-phase1-workspace-overview.md)
Implemented (PR #746). `backend/application/memory_admin_service.py` (`MemoryAdminService`), REST endpoints, `frontend/src/components/SystemSettings/MemoryManagementSection.tsx`.

## [Archive/2026-08-26-memory-admin-phase2-health-check.md](Archive/2026-08-26-memory-admin-phase2-health-check.md)
Implemented (PR #748). `MemoryBackend.health_check()` in `backend/memory/backends.py:125,289`; two new checks in `backend/admin_ops/health_rest.py:240-341` (`_check_memory_embedding`, memory-backend check via `backend.health_check()`).

## [Archive/2026-08-26-memory-admin-phase3-system-settings-override.md](Archive/2026-08-26-memory-admin-phase3-system-settings-override.md)
Implemented (PR #749). `SystemMemorySettings` model; `SystemMemorySettingsView`/`SystemMemorySettingsResetView`/`WorkspaceMemorySettingsView` in `backend/rest_api/urls.py:60-478`; `frontend/src/components/SystemSettings/MemorySystemSettingsSection.tsx`.

## [Archive/2026-08-26-memory-admin-phase4-user-self-service.md](Archive/2026-08-26-memory-admin-phase4-user-self-service.md)
Implemented (PR #750). `MemorySelfServiceView` (GET+DELETE `/api/v1/memory/me/`) in `backend/memory/memory_rest.py:559`; `frontend/src/components/UserProfileSettings/MemorySection.tsx`.

## [Archive/2026-08-27-memory-admin-phase5-visualization.md](Archive/2026-08-27-memory-admin-phase5-visualization.md)
Implemented (PR #751). `frontend/src/components/SystemSettings/MemoryVisualizationSection.tsx` (List/Cluster/Scatter views); backend projection endpoints in `MemoryAdminService`.

## [Archive/2026-09-03-datenmodell-konsolidierung.md](Archive/2026-09-03-datenmodell-konsolidierung.md)
Implemented (PR #880, merged). 29 tasks (plus the 15b/28a/28b/28c-1/28c-2 Expand/Migrate/Contract split discovered mid-execution once `DiagramVersion`/`IcdVersion` turned out not to be pure history tables) across 6 phases; all 6 milestone gates (M0–M5) reached, including the `persistence.ArtifactVersion` substitution for Decision D-4. Full ledger: `.superpowers/sdd/2026-09-03-datenmodell-konsolidierung/progress.md`.

## [Archive/2026-09-03-attribute-definition.md](Archive/2026-09-03-attribute-definition.md)
Implemented (PR #888, merged). All 27 tasks, 7-form frontend rollout complete, code-reviewer verdict APPROVED_WITH_RECOMMENDATIONS (0 blockers). Full ledger: `.superpowers/sdd/2026-09-03-attribute-definition/progress.md`.

## [Archive/2026-09-03-traceability-semantik.md](Archive/2026-09-03-traceability-semantik.md)
Implemented (PR #891, open — CI green, mergeable, awaiting human merge). All 24 tasks plus a final whole-branch review (2 Critical + 5 Important cross-task findings that no single task review could have caught, all fixed) and its own scoped re-review, both clean. Full ledger: `.superpowers/sdd/2026-09-09-traceability-semantik/progress.md`.

## [Archive/2026-09-03-ki-vorschlag-als-zustand.md](Archive/2026-09-03-ki-vorschlag-als-zustand.md)
Implemented (PR #904, merged 2026-09-11, CHANGELOG [1.8.0-beta.10]). All 20 tasks across 5 phases. Agent-authored workflow items (MainGoals, Requirements, TraceLinks, …) enter a `proposed` state (Rule 0) enforced across direct transitions, `outdate()`, bulk-confirm and both hard-delete paths; `ApiKey` gains agent identity, scope and expiry. The plan's one open question (confirming a link nulls `TraceLink.proposed_by`/`proposed_at`) remained a non-blocking spec inconsistency, not a scope gap.

## [Archive/2026-09-03-interview-engine-fix.md](Archive/2026-09-03-interview-engine-fix.md)
Implemented (PR #903, merged 2026-09-11, CHANGELOG [1.8.0-beta.10]). 18 tasks; `formalize()` generalized to all 8 in-scope artifact types via the `ARTIFACT_CREATION_ADAPTERS` registry, transcript compression above a sliding window, and a single `/interviews` surface (`?start=multi`). The prior blocker (GlossaryTerm Artifact-backing on the datenmodell-konsolidierung plan) was resolved by PR #880.

## [Archive/2026-09-11-attribute-definition-v2.md](Archive/2026-09-11-attribute-definition-v2.md)
Implemented (spec/plan PRs #901/#902, implementation PR #905, merged 2026-09-11, CHANGELOG [1.8.0-beta.10]). 12 tasks / 7 phases. Create/delete are thin wrappers over the existing `update_global`/`update_workspace` service methods (reusing `validate_meta_only_change`), `sections[]` was added to `definition_json` (one additive migration), export/import of the whole definition uses `export_definition`/`import_definition`, plus REST + MCP surface and a table-view UI. The catalog concept stayed out of scope by design.

## [Archive/2026-09-03-menschen-im-system-collaboration.md](Archive/2026-09-03-menschen-im-system-collaboration.md)
Implemented (2026-09-15, PR #956 — CI running, awaiting human merge). The collaboration half of the Menschen-im-System plan, re-scoped after the owner/assignment half was superseded by Attribut-System v3 (#934/#936/#940) and AWMS. 19 tasks (7, 8, 9, 26, 27, 10, 15, 16, 17, 18, 19, 20, 28, 22, 23, 24, 25, 29, 30; Task 21 superseded): `Comment`/`Notification` models + RLS, `resolve_artifact_id_or_none`, user-global `UserNotificationPreference` (opt-out, four switches, `auth_tenancy/0014`, no RLS by design), `NotificationPreferenceService`/`NotificationService`/`CommentService`, four triggers (`assigned` bound to `ArtifactAttributeGateway.write()`, `transition_pending`, `suspect_flagged`, `comment_added`), REST (artifact comments, notification feed, self-service preferences) + MCP `comment.*`, frontend `CommentPanel`/`NotificationBell`/profile switches, de/en i18n. Commit range `7c935827`–`d5b52dc3`. DoD PASS, no blockers; the local test-gate reds are not branch-attributable — see [`docs/se/reports/KNOWN_TEST_GATE_REDS.md`](../../se/reports/KNOWN_TEST_GATE_REDS.md).
## [Archive/2026-07-25-phase6-agent-templates.md](Archive/2026-07-25-phase6-agent-templates.md)
All planned features are implemented, with one deliberate deviation decided against. All five role templates, the review-policy hook (`review-policy-gate.sh`/`.md`), `README.md` and `BOOTSTRAP.md` exist under `docs/agent-templates/`, with manifest-membership tests. The first role ships as `requirements-architecture-manager.md` instead of the planned `requirements-architect.md`; the user explicitly decided against renaming it (2026-08-20).

## [Archive/2026-09-22-se-auditor-waivers-569-spec.md](Archive/2026-09-22-se-auditor-waivers-569-spec.md)
Spec fully realised (#569 closed); sampled by surface and tests, not every one of the 33 ACs was checked individually. `BaselineGateWaiver` with RLS and expiry, REST `audit/waivers/`, MCP `audit.waive_finding`/`audit.waivers`, gate semantics with waiver metadata, and the dashboard action/filter. Revoking a waiver was left as an explicit non-goal.

Review files (APPROVED on the last iteration):
- [Archive/2026-09-22-se-auditor-waivers-569-spec-review.md](Archive/2026-09-22-se-auditor-waivers-569-spec-review.md)
- [Archive/2026-09-22-se-auditor-waivers-569-spec-review-rev2.md](Archive/2026-09-22-se-auditor-waivers-569-spec-review-rev2.md)
- [Archive/2026-09-22-se-auditor-waivers-569-spec-review-rev3.md](Archive/2026-09-22-se-auditor-waivers-569-spec-review-rev3.md)
- [Archive/2026-09-22-se-auditor-waivers-569-spec-review-rev3-iter2.md](Archive/2026-09-22-se-auditor-waivers-569-spec-review-rev3-iter2.md)

## [Archive/2026-09-22-se-validation-completeness-spec.md](Archive/2026-09-22-se-validation-completeness-spec.md)
Cluster 5 spec, realised; sampled per section, individual AC test rows not re-run. All four parts are on main: TestCase origin/review status with AI-review-aware coverage (#424), default-on goals with the `VAL-P1` rule (#402), baseline membership and drift (#399), and the #272 remainder (verification_method gate, live-endpoint link check, coverage report, creation-baseline marker, demo fixture). Issues #424/#402/#399/#272 are closed.

Review files (APPROVED on the last iteration):
- [Archive/2026-09-22-se-validation-completeness-review.md](Archive/2026-09-22-se-validation-completeness-review.md)
- [Archive/2026-09-22-se-validation-completeness-review-rev2.md](Archive/2026-09-22-se-validation-completeness-review-rev2.md)
- [Archive/2026-09-22-se-validation-completeness-review-rev3.md](Archive/2026-09-22-se-validation-completeness-review-rev3.md)
