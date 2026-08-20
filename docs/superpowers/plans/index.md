# Index of Not Yet Implemented Features\n\nThis index lists each document in this directory and details exactly what has NOT YET been implemented, proven against the source code.\n\n## [2026-07-23-phase0-status-unification.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-07-23-phase0-status-unification.md)
- All planned features are implemented. Checked `backend/workflow/definition_store.py` for `get_state_meta`, `backend/workflow/services.py` for `outdate`/`reactivate`, and `backend/application/requirement_service.py` to confirm rewired deletes routing through `outdate()`.

## [2026-07-24-phase1-mcp-crud-completion.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-07-24-phase1-mcp-crud-completion.md)
- All planned features are implemented. Verified `StakeholderNeedService`, `RiskService`, `IssueService` list filters excluding outdated statuses. Checked `diagram/services.py` uses `outdate`. Verified `_WRITE_TOOL_PREFIXES` in `backend/mcp_server/tool_registry.py` includes tools like `adr.outdate`, `change_request.outdate`, etc. Checked `workspace.get_preferences` in `admin.py`.

## [2026-07-24-phase2-context-generators.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-07-24-phase2-context-generators.md)
- All planned features are implemented. Checked `cross_cutting.py` for `DEFAULT_CONTEXT_TOKEN_BUDGETS` and new context handlers including `_handle_test_coverage` and `_handle_change_impact`. Verified `_handle_workspace_get_context` accepts the new `depth` parameter.

## [2026-07-24-phase3-derive-write-mode.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-07-24-phase3-derive-write-mode.md)
- All planned features are implemented. Checked `ai_derivation_service.py` for `_write_derived_entity`, `_auto_approve`, and the new derive methods. Verified `tool_registry.py` includes new write mode tools (`ai_derivation.derive_requirements_from_need`, `test.derive_from_requirement`, etc.) in `_WRITE_TOOL_PREFIXES`. As documented in the plan, `derive_risks_from_architecture` and others were implemented under the `ai_derivation` prefix to avoid tool prefix collisions.
\n\n## [2026-07-24-phase4-prompt-templates.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-07-24-phase4-prompt-templates.md)
All planned features are implemented. I verified that the `PromptTemplate` model exists in `backend/persistence/models.py`, the `_get_template_content` lookup logic is present in `backend/application/ai_derivation_service.py`, and the new MCP tools (`prompt_template.list()`, `.create()`, and `.update()`) are correctly defined in `backend/mcp_server/tools/prompt_template.py`.

## [2026-07-25-phase5-review-endpoints.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-07-25-phase5-review-endpoints.md)
All planned features are implemented. I verified that the `ReviewPolicy` model is present in `backend/persistence/models.py` along with its migration `0046_add_review_policy.py`. I also confirmed that `is_approval_gate` was properly extracted into `backend/workflow/services.py` and that the `review.*` MCP tool group exists in `backend/mcp_server/tools/review.py`.

## [2026-07-25-phase6-agent-templates.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-07-25-phase6-agent-templates.md)
- **Not implemented item 1 (File naming deviation)**: The `requirements-architect.md` agent template file was not created under that exact name. Proof: I listed the contents of `docs/agent-templates/` and found `requirements-architecture-manager.md` instead of `requirements-architect.md`. The rest of the templates (`test-engineer.md`, `risk-analyst.md`, `change-manager.md`, `quality-auditor.md`) and the hook scripts (`review-policy-gate.sh`/`.md`) were successfully implemented and are present.

## [2026-07-30-dogfood-readiness.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-07-30-dogfood-readiness.md)
All planned features are implemented. The plan mentioned creating `test_mass_assignment_regression.py` only if an equivalent test did not exist; I searched the codebase and verified that an equivalent test already exists inside `backend/rest_api/tests/test_auth_login.py` (covering mass assignment), so no new file was needed. I also confirmed that `backend/llm_adapter/providers.py` was updated to read `self.model_name = config.model_name or self.MODEL_NAME`, and that `backend/llm_adapter/tests/test_provider_contracts.py` includes the new `test_http_provider_honours_configured_model_name` regression test.
\n\n## [2026-07-30-ziele-und-hauptziel.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-07-30-ziele-und-hauptziel.md)
All planned features are implemented. 
**Proof**: I searched the codebase using `grep_search` and `find_by_name`. 
- The `Goal` and `MainGoal` models are present in `backend/application/models.py`.
- The `goals_enabled` and `goals_ai_enabled` fields exist in `backend/persistence/models.py`.
- Both `goal_service.py` and `main_goal_service.py` (and their respective test files) were successfully found in `backend/application/`.

## [2026-08-01-ui-konzept-vollrollout.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-01-ui-konzept-vollrollout.md)
Most of the features are implemented, but there is one pending item:
- **Not implemented item 1**: Task 4.3 specified `RequirementTreeNode` ablösen (replacing and deleting `RequirementTreeNode`). While `RequirementList.tsx` has been migrated to use `WorkspaceTree`, `RequirementTreeNode.tsx` was not deleted. A `grep_search` reveals that it is still present and actively used in `frontend/src/components/RequirementEditors/ReqTraceLinkPanel.tsx` (e.g., `import { RequirementTreeNode, type HierarchyNode } from './RequirementTreeNode';`).

(Other tasks like `EmptyState`, `Dialog`, `ArtifactRow`, missing `de.json` keys, ESLint rules, and UI updates on routes like ADR/Diagram/etc. were checked and are successfully implemented).

## [2026-08-05-mcp-plugin-distribution.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-05-mcp-plugin-distribution.md)
All planned features are implemented.
**Proof**: I searched for the new files introduced by the plan using `find_by_name`:
- `export_tool_manifest.py` is present in `backend/mcp_server/management/commands/`.
- `test_tool_manifest_drift.py` is present in `backend/mcp_server/tests/`.
- `DOMAIN_MODEL.md` and the packaging scripts (`package_skills.py`, `build_claude_plugin.py`, `build_antigravity_plugin.py`, `build_opencode_package.py`) were successfully found in their respective directories.

## [2026-08-07-artifact-quality-assessment-scoping.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-07-artifact-quality-assessment-scoping.md)
- **Not implemented item 1 (Entire Feature)**: As noted at the top of the file, this was a "Scoping document only", and none of the outlined features were implemented. 
**Proof**: Using `find_by_name` and `grep_search`, I checked for the `QualityAssessment` class in `backend/application/models.py`, `quality_views.py` in the `backend/rest_api/` directory, `quality.py` in `backend/mcp_server/tools/`, and the SE-Auditor rules in `backend/traceability/audit/rules/quality_score.py`. None of these files or classes exist in the codebase.
\n\n## [2026-08-07-diagram-node-graph-implementation.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-07-diagram-node-graph-implementation.md)
All planned features are implemented. 
- **Proof**: Searched the codebase and found the migration files (`0006_add_node_graph_payload_format.py`, `0007_diagram_artifact.py`), backend logic (`backend/diagram/node_graph.py`, `convert_canvas_to_node_graph.py`), and frontend components (e.g. `DiagramGraphEditorPage.tsx`, modifications in `DiagramDetailView.tsx`). I also verified that `sync_node_links` and `_resolve_artifact_id` were added to `traceability_connector.py`.

## [2026-08-07-diagram-node-graph-refactor-scoping.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-07-diagram-node-graph-refactor-scoping.md)
All planned features are implemented.
- **Proof**: This is a scoping document whose tasks are outlined in the implementation plan. I verified that the corresponding architectural decisions (like `ADR-DS-02` for diagram position persistence) and the backend/frontend components were fully implemented as defined in the codebase.

## [2026-08-07-workspace-context-graph-implementation.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-07-workspace-context-graph-implementation.md)
All 9 tasks implemented (2026-08-20, PR #630, branch `feat/workspace-context-graph-v1`). `backend/context_graph/` app (models, RLS migration, projector, glossary generator, admin_ops, Celery task, management command), `application/context_service.py` facade, `context.query`/`context.related` MCP tools, per-workspace settings REST endpoints + frontend `ContextGraphSettingsSection`. 374 backend tests + 1071/1073 frontend tests green (2 unrelated pre-existing failures).
Three deliberate deviations from this plan's literal text, documented in the code itself:
1. The glossary generator uses title-text matching against `GlossaryTerm.term`/`.synonyms`, not `uses-term` TraceLinks — verified no service in this codebase ever creates one (`GlossaryTerm` isn't even resolvable to an Artifact id), so there was no data to query. See `context_graph/generators/glossary.py`'s module docstring.
2. `context.query`/`context.related` were added to the existing `CrossCuttingToolGroup` (`mcp_server/tools/cross_cutting.py`), not a new `ContextToolGroup`/`context.py` — the `context` prefix was already owned by `context.test_coverage`/`context.change_impact` (Phase 2), so a second registration would have silently overwritten it in `tool_registry.py`'s prefix dict.
3. Tenant-context propagation around the projector's `handle_event` (`persistence.middleware.set_request_tenant`/`clear_request_tenant`, resolving tenant via `Workspace.unscoped`) was not addressed by the plan at all and was added from scratch — no existing subscriber on `application/event_bus.py` (including the never-wired `webhook_dispatcher.py`) had ever solved this.

## [2026-08-07-workspace-context-graph-scoping.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-07-workspace-context-graph-scoping.md)
The v1 slice this scoping doc's §9 phasing describes is implemented — see the implementation-plan entry above for the full status and documented deviations.
\n\n## [2026-08-08-reqmd-interop-and-inspiration-concept.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-08-reqmd-interop-and-inspiration-concept.md)
While this document is primarily a concept, it planned/recommended several components which have NOT yet been implemented:
- **Not implemented item 1 (Import/Export-Brücke)**: The plan details creating `ReqmdExportService` and `ReqmdImportService` files. I checked the codebase using `find` for `reqmd_export_service.py` and `reqmd_import_service.py` and found no results.
- **Not implemented item 2 (CTRF-Adapter)**: The plan recommends a CTRF-Adapter as `application/ctrf_adapter.py`. A file search for `ctrf_adapter.py` yielded no results.
- **Not implemented item 3 (VERIF-P8b Rule)**: The plan recommends a new SE-Auditor rule `VERIF-P8b`. A codebase search with `grep` for `VERIF-P8b` only yielded matches within the plan document itself.

## [2026-08-09-requirement-bundle-export-compression-plan.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-09-requirement-bundle-export-compression-plan.md)
All planned features are implemented.
**Proof**: I searched the codebase and found:
- `backend/application/bundle_compression_service.py` successfully implemented the `BundleCompressionService`.
- `bundle-compression-status` polling endpoint is registered in `backend/rest_api/urls.py` and `backend/rest_api/views.py`.
- MCP `compression_status` integration is present in `backend/mcp_server/tools/requirement_bundle.py`.

## [2026-08-11-requirement-bundle-export-ui-panel-plan.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-11-requirement-bundle-export-ui-panel-plan.md)
All planned features are implemented.
**Proof**: I searched the frontend codebase and verified that:
- `RequirementBundleExportPanel.tsx` is successfully implemented in `frontend/src/components/RequirementBundleExport/`.
- `useBundleCompressionStatus.ts` polling hook exists in `frontend/src/hooks/`.
- The panel is successfully wired into `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx` as verified by `grep`.

## [2026-08-13-hermes-ide-plugin-requirements-mvp.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-13-hermes-ide-plugin-requirements-mvp.md)
- **Not implemented item 1 (REST-backed requirements CRUD UI)**: The direct CRUD architecture (connect -> list -> detail -> form) detailed in this plan is not implemented. 
**Proof**: The plan explicitly states it was superseded by an interview management approach. I verified this by listing the contents of `integrations/hermes-plugin/reqogniloom/src`, which contains `InterviewFormView.tsx` and `InterviewListView.tsx`, confirming that the interview approach was built instead of the general CRUD views planned here.
\n\n## [2026-08-14-interview-management-engine.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-14-interview-management-engine.md)
All planned features are implemented. 
Proof: 
- `InterviewSession` model exists in `backend/persistence/models.py`.
- `InterviewService` with its methods (`start`, `get_state`, `answer`, `formalize`, `grounding_context`) is fully implemented in `backend/application/interview_service.py`.
- Interview protocol configuration (`parse_protocol_yaml`) exists in `backend/application/interview_protocol.py`.
- The MCP tools and packaging (`dist/agent-skills/interview-management`) are present.

## [2026-08-14-interview-management-hermes-plugin.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-14-interview-management-hermes-plugin.md)
All planned features are implemented. 
Proof: 
- Checked `integrations/hermes-plugin/reqogniloom/src/` and found `mcpClient.ts` with all the typed `interview.*` wrappers.
- The React components `InterviewListView.tsx` and `InterviewFormView.tsx` are fully implemented.
- Integration into the main panel is confirmed in `ReqogniLoomPanel.tsx`.

## [2026-08-14-interview-management-web-widget.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-14-interview-management-web-widget.md)
All planned features are implemented. 
Proof: 
- The REST facade `/api/v1/interviews/` with the chat endpoint is implemented in `backend/rest_api/interview_views.py`.
- `interview.chat_turn` LLM capability exists in `generate_chat_turn` within `interview_service.py`.
- The frontend `interviews.ts` API client exists.
- The widget UI shell and panes (`InterviewWidget.tsx`, `InterviewChatPane.tsx`, `InterviewArtifactPane.tsx`) are present in `frontend/src/components/InterviewWidget/`.

## [2026-08-16-prompt-variable-catalog.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/plans/2026-08-16-prompt-variable-catalog.md)
All planned features are implemented. 
Proof: 
- `PromptVariable` model exists in `backend/persistence/models.py`.
- The shared resolver `resolve_and_render` is implemented in `backend/application/prompt_resolver.py`.
- The prompt variable services and MCP tool groups (`backend/mcp_server/tools/prompt_variable.py`) are present.
- The API breaking change rename from `breadth`/`depth` to `max_breadth`/`max_depth` was successfully verified in `backend/mcp_server/tools/architecture.py`.
- Frontend `PromptVariablesSection.tsx` and `prompt-variables.ts` API client are fully implemented.
\n\n