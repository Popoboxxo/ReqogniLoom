# Plan Index

This index lists every plan/scoping document in this directory tree and its implementation status,
proven against the source code (not against the plan's own claims).

- **`Archive/`** — plans whose full scope has been implemented and verified. Kept for historical reference
  (design rationale, rejected alternatives, task-by-task execution record); no more action expected.
- **This directory (top level)** — plans with real open work, or explicitly deferred/decided-against.

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

---

## Open / deferred (not archived)

## [2026-07-25-phase6-agent-templates.md](2026-07-25-phase6-agent-templates.md)
**Decided against (2026-08-20), not a gap to fix.** The `requirements-architect.md` agent template file was never created under that exact name — `requirements-architecture-manager.md` exists instead. Reviewed and the user explicitly chose not to rename/create the file to match the plan's literal naming. The rest of the templates (`test-engineer.md`, `risk-analyst.md`, `change-manager.md`, `quality-auditor.md`) and the hook scripts (`review-policy-gate.sh`/`.md`) are implemented and present. Do not re-flag the naming deviation as an action item.

## [2026-08-07-artifact-quality-assessment-scoping.md](2026-08-07-artifact-quality-assessment-scoping.md)
**Not implemented — deferred (2026-08-20).** Scoping document only (explicitly labelled "no implementation, no branch, no migration" at the top). None of the outlined components exist: no `QualityAssessment` class in `backend/application/models.py`, no `quality_views.py` in `backend/rest_api/`, no `quality.py` in `backend/mcp_server/tools/`, no SE-Auditor `QUAL-*` rules. The doc's own effort estimate is ~8–11 dev-days for the recommended v1 cut alone (~19–26 d for the full issue) and there is no task-by-task implementation plan yet — reviewed and explicitly deferred rather than started; re-scope before picking this up.

## [2026-08-08-reqmd-interop-and-inspiration-concept.md](2026-08-08-reqmd-interop-and-inspiration-concept.md)
**Not implemented — deferred (2026-08-20).** Concept document; three recommended components are absent: `ReqmdExportService`/`ReqmdImportService`, a CTRF-Adapter (`application/ctrf_adapter.py`), and SE-Auditor rule `VERIF-P8b`. Reviewed alongside the workspace-context-graph work and explicitly deferred (not started).

## [2026-08-13-hermes-ide-plugin-requirements-mvp.md](2026-08-13-hermes-ide-plugin-requirements-mvp.md)
**Superseded, not implemented as written — kept out of Archive/ deliberately.** The direct REST-backed CRUD architecture (connect → list → detail → form) this plan describes was never built; the plan's own text states it was superseded by an interview-management approach, which was built instead (see the three `2026-08-14-interview-management-*.md` entries in `Archive/`). Nothing left to action here, but the plan's *own* scope was not implemented — kept at top level rather than archived so that distinction stays visible.

## [2026-09-03-datenmodell-konsolidierung.md](2026-09-03-datenmodell-konsolidierung.md)
**Not implemented — plan written (2026-09-04).** First of 11 implementation plans from the 2026-09-02 systemaudit's 11 specs (see `docs/superpowers/specs/index.md`). 29 tasks, 6 phases, 6 milestone gates (M0–M5); M1 (Task 13) is the gate the attribute-definition plan below depends on. Open decision needing user confirmation: the spec's literal "migrate to the existing audit-log versioning" instruction is not achievable as written (`VersionReconstructor` lives in `baseline/`, `AuditEntry` has no payload column, 8/10 types have no retrievable history) — the plan substitutes a new generic `persistence.ArtifactVersion` table with a row-count guard against history loss (Decision D-4), affecting only Phase 5 (Tasks 25–29).

## [2026-09-03-attribute-definition.md](2026-09-03-attribute-definition.md)
**Not implemented — plan written (2026-09-04).** Second of 11. 27 tasks across Backend Foundation / REST+MCP / Interview+Export consumers / Frontend (7-form rollout in spec order). No blocking questions. Two spec contradictions resolved with documented decisions: `CustomFieldValue.definition` FK cannot survive `CustomFieldDefinition`'s removal as the spec demands both — resolved by switching the FK to an `attribute_name` CharField (values fully preserved); bootstrap order handles the not-yet-implemented datenmodell-konsolidierung dependency gracefully (synthetic `status` attribute + exclusion list) instead of hard-blocking on it.

## [2026-09-03-traceability-semantik.md](2026-09-03-traceability-semantik.md)
**Not implemented — plan written (2026-09-04).** Third of 11. 24 tasks, 6 phases (A Catalog Foundation → B Validation Flip → C TraceLink/Suspect → D Hard Migration → E REST/MCP → F Frontend). **Two blocking questions need a user decision** (both have a plan default, both documented under `## OFFENE FRAGEN`): (1) always-on validation would make today's working Goal/MainGoal/Issue/Interview links uncreatable, since the spec's 8-type matrix never names them — default is grandfathering via an inventory command that measures before deciding; (2) merging `refines` into `derives-from` changes SE-Auditor semantics (`refines` is deliberately non-hierarchical/symmetric in `hierarchy.py`, `derives-from` is not) — default is migrating as specified while measuring the audit-rule delta.

## [2026-09-03-ki-vorschlag-als-zustand.md](2026-09-03-ki-vorschlag-als-zustand.md)
**Not implemented — plan written (2026-09-03, regenerated 2026-09-04).** Fourth of 11. Original version lost to a cross-agent race condition on 2026-09-04 (never git-added, unrecoverable — see `2026-09-04-open-decisions.md`) and rewritten from the same brief; now **20 tasks**, 5 phases. Independently re-confirmed the same critical spec bug both times: `WorkflowDefinitionDTO.initial_state` is `states[0]`, and the spec's JSON put `"proposed"` at position 0 — every artifact, including human-authored ones, would have started as a proposal. Also found the spec's own "shared helper is missing" risk is moot — `workflow.services.initialize_workflow_states(..., ctx)` already accepts `ctx` and is the sole call site for all 13 `create_X()` services, so zero service files need touching. **One open question, not blocking:** confirming a link nulls `TraceLink.proposed_by`/`proposed_at` entirely (§5), destroying provenance — unlike artifacts, where the workflow history entry preserves who proposed it (still present in the regenerated version, verified). Intentional or a spec inconsistency? Not yet confirmed by the user.

## [2026-09-03-interview-engine-fix.md](2026-09-03-interview-engine-fix.md)
**Not implemented — plan written (2026-09-03, regenerated 2026-09-04).** Fifth of 11. Original version lost to the same race condition (see above); now **18 tasks**, 108 steps. No blocking questions. Found a real bug in the existing codebase: the `_architecture_element` interview adapter is only tested against a `MagicMock` that swallows any kwarg — the real `ArchitectureService` expects `title`, the test asserts `name`, so multi-kind ArchitectureElement formalization would crash for real. Also closed: Risk still couldn't be formalized after the spec's own fix (missing required fields in the default protocol), `resulting_artifact_ids` would have regressed issue #736 (fixed via a new `entity_id` field on `CreatedArtifactRef` instead of ID-guessing at the call site), and the provenance badge would have stayed invisible for ~90% of interviews for two independent reasons (single-kind sessions never write `InterviewSessionArtifact`, and the lookup filters on the wrong PK). Blocked: the GlossaryTerm task, on the datenmodell-konsolidierung plan's Artifact-backing (verified not yet implemented).

## [2026-09-03-menschen-im-system.md](2026-09-03-menschen-im-system.md)
**Not implemented — plan written (2026-09-04).** Sixth of 11. 26 tasks, 6 phases (Schema → Assignment seam → Comments → Notification triggers+REST → REST exposure → Frontend). No blocking questions. `AuditEntry.OP_ASSIGN` is already used by one write path today (`IssueService.assign_issue`) contrary to the spec's "never used" claim — the plan migrates that path onto the new seam instead of duplicating it. Two deferred wiring points (grep-gated, with fallback) depend on the traceability-semantik plan's `suspect_flagged_at` and the attribute-definition plan's bootstrap command.

## [2026-09-03-mcp-modernisierung.md](2026-09-03-mcp-modernisierung.md)
**Not implemented — plan written (2026-09-03, regenerated 2026-09-04).** Seventh of 11. Original version lost to the race condition (see above); now **15 tasks**, 111 steps. No blocking questions. `TenantToolRegistry` doesn't exist (the class is `ToolRegistry`), confirmed again independently. `resources/*`/`prompts/*` dispatch as internal pseudo-tools through the existing `ToolRegistry.dispatch_request()` with empty `get_tool_schemas()`, inheriting the full auth/RBAC/preset chain for free while staying invisible in `tools/list`. Protocol version bump is turned into version negotiation (not a hard swap) since `initialize` today ignores `params.protocolVersion` entirely. Depends on `ApiKey.scope` from the ki-vorschlag-als-zustand plan (checked and blocked-not-duplicated). **⚠️ Unresolved cross-plan conflict with dokumentensicht's Task 4** — both plans independently built `application/artifact_markdown.render_artifact_markdown()` with different, incompatible signatures (this plan's is ID+ctx-resolving; dokumentensicht's is dict+numbering-based) because both were regenerated in parallel without seeing each other. Both plans now carry a `⚠️ KNOWN CROSS-PLAN CONFLICT` note with the same reconciliation recommendation — see `2026-09-04-open-decisions.md` item 6.

## [2026-09-03-github-jira-integration.md](2026-09-03-github-jira-integration.md)
**Not implemented — plan written (2026-09-04).** Eighth of 11. 30 tasks across Stage 1 Link-Only / Stage 2 Inbound-Sync / Stage 3 Outbound+Agent / surface verification. No blocking questions. One cross-spec ownership gap found: `WorkflowHistoryEntry.actor_type`/`client_name` are required by both this spec and ki-vorschlag-als-zustand, but neither spec's migration list actually creates them — this plan's Task 17 creates them (needs cross-checking against the ki-vorschlag-als-zustand plan before implementation to avoid a collision). Confirms `WebhookDispatcher.subscribe_to_events()` is already wired from `ApplicationConfig.ready()` (2026-08-27 P0-3c), so Stage 3 is not the first consumer of that dispatch path.

## [2026-09-03-tabellenansicht.md](2026-09-03-tabellenansicht.md)
**Not implemented — plan written (2026-09-04).** Ninth of 11. 24 tasks, 120 steps. No blocking questions. The user's explicit "never bypass workflow rules via bulk edit" requirement is enforced in one function (`assert_no_workflow_owned_fields`) and proven at five levels (unit, service-against-real-rows, REST 400, MCP, E2E via a hand-built PATCH that goes around the UI). Found the spec's C8 finding is itself outdated — `django-filter` isn't installed at all, filtering is in-memory, not `filterset_fields`-based.

## [2026-09-03-dokumentensicht.md](2026-09-03-dokumentensicht.md)
**Not implemented — plan written (2026-09-03, regenerated 2026-09-04).** Tenth of 11. Original version lost to the race condition (see above); now **20 tasks** (11 backend, 8 frontend, 1 E2E). Found `BaselineSnapshot.artifact` is dead — the column exists but is never written anywhere in the current code, so every existing `scope="document"` row has `artifact_id = NULL` and a naive migration would read data that doesn't exist. Also found `bl_baseline_snapshot` has an unconditional UPDATE-blocking DB trigger with no GUC escape hatch — a naive backfill migration would die there; fixed with a GUC-gated trigger exception. **One open question, not blocking:** how to reconstruct legacy document-scope baselines into real `Document` objects when the source data (Baseline.artifact) never existed — see `2026-09-04-open-decisions.md` item 7. **⚠️ Unresolved cross-plan conflict with mcp-modernisierung's Task 5** — both plans independently built `application/artifact_markdown.render_artifact_markdown()` with incompatible signatures; see `2026-09-04-open-decisions.md` item 6.

## [2026-09-03-rollenbasierte-sichten.md](2026-09-03-rollenbasierte-sichten.md)
**Not implemented — plan written (2026-09-03, regenerated 2026-09-04).** Eleventh and last of 11. Original version lost to the race condition (see above); now **15 tasks**, 110 steps, 6 phases. Re-confirmed independently: `NAV_ITEMS.requires` and `useHasRole` already exist in `main` as of commit `54b09760` (predates this whole spec series) — GitHub issue #848 is likely already resolved by that commit and should be checked/closed rather than re-implemented; this plan extends the existing system rather than rebuilding it. Roles confirmed as exactly `admin`/`editor`/`viewer`/`approver`. Section §4 (`audience`) needs zero new work — the attribute-definition plan already delivers the field, validation, editor toggle and section-collapse behavior; this plan only consumes it.
