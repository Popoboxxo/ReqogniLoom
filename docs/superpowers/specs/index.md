# Index of Not Yet Implemented Features\n\nThis index lists each document in this directory and details exactly what has NOT YET been implemented, proven against the source code.\n\n## [2026-07-12-frontend-feedback-strategie-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-07-12-frontend-feedback-strategie-design.md)
All planned features are implemented. 
Proof of implementation for the "ausstehend" features:
- **Impact-Graph-Visualisierung (C1):** Implemented. Searched for `Impact` in `frontend/src/components` and found `ImpactView.tsx` and `impact-preset.ts`.
- **Traces for Risks and Issues (C2, C3):** Implemented. Checked `RiskEditors.tsx` and `IssueEditors.tsx` and both integrate `TraceLinkPanel` and `TraceSpine`.
- **TestRun Assignments (C4, C5):** Implemented. `TestRunsList.tsx` has logic for `selectedTestCaseIds` and `TestRunDetailEditor.tsx` loads the assigned `TestCase` results.
- **Custom Fields (C6):** Implemented. Searched for `CustomFieldDefinition` and found it across backend models, serializers, views, and frontend forms.
- **Glossary Synonyms (C10):** Implemented. Checked `backend/persistence/models.py` and found `synonyms = models.JSONField()` on the glossary models.
- **Editable User Profile (C11):** Implemented. Found `first_name` and `last_name` update logic inside `frontend/src/components/UserProfileSettings/ProfileSection.tsx`.
- **Tags for Issues (B4):** Implemented. Found `tags = serializers.JSONField()` in the backend serializers and `tags?: string[]` in the frontend API.

## [2026-07-23-reqogniloom-status-unification-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-07-23-reqogniloom-status-unification-design.md)
All planned features are implemented.
Proof:
- **Status Model Unification:** Searched for `is_outdated_equivalent` and found it successfully populated in `backend/workflow/definition_store.py` and migrations.
- **WorkspaceGoal:** Found `Goal` and `MainGoal` as models in `backend/application/models.py`.
- **Context Generators:** Searched the codebase and found `context.test_coverage`, `context.change_impact`, and `workspace.llm_system_prompt` mapped inside `backend/mcp_server/tools/cross_cutting.py`.
- **Review Endpoints:** Found implementations inside `backend/mcp_server/tools/review.py`.

## [2026-07-25-phase6-agent-templates-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-07-25-phase6-agent-templates-design.md)
- **Not implemented item 1:** `requirements-architect.md` file is missing.
  - *Proof:* Listed the contents of `c:/Repositories/ai-native-reqflow-POC/docs/agent-templates` using `list_dir`. The file `requirements-architect.md` does not exist. However, there is a similarly named file `requirements-architecture-manager.md`, which suggests it was implemented under a different name than specified in the design. The rest of the files (`change-manager.md`, `quality-auditor.md`, `risk-analyst.md`, `test-engineer.md`, and the `hooks` scripts) were found.

## [2026-07-30-ziele-und-hauptziel-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-07-30-ziele-und-hauptziel-design.md)
All planned features are implemented.
Proof:
- **Goal and MainGoal Models:** Searched `backend/application/models.py` and found both `Goal` and `MainGoal` implemented with their respective trace properties.
- **Prompt Template Integration:** Searched for `goal_aggregate` and found it present in `prompt_slots.py`, `models.py`, `settings_views.py`, and the AI derivation services.
- **MCP and REST Integration:** Found `goal.read` and corresponding tools in `backend/mcp_server/tools/goals.py` as well as the REST endpoints in `main_goal_service.py`.

## [2026-08-08-requirement-bundle-export-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-08-08-requirement-bundle-export-design.md)
All planned features are implemented.
Proof:
- **Separated Services:** Searched and found `RequirementBundleQueryService` (in `requirement_bundle_service.py`) and `BundleCompressionService` (in `bundle_compression_service.py`).
- **MCP Tools:** Found `requirement_bundle.export` and schema endpoints in `backend/mcp_server/tools/requirement_bundle.py`.
- **Prompt Template:** Found `bundle_compression` references in `bundle_compression_service.py` and related AI tests.
\n\n## [2026-08-13-hermes-ide-plugin-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-08-13-hermes-ide-plugin-design.md)
- **Not implemented item 1 (Requirements Views and APIs)**: The spec plans for a core Requirements management flow (`connect → list → detail → form`) using `/api/v1/requirements/` endpoints. I verified `integrations/hermes-plugin/reqogniloom/src/api.ts` and it completely lacks endpoints for Requirements (only workspace and auth are present). A search for Requirement-specific React components (`list`, `detail`, `form`) in `integrations/hermes-plugin/reqogniloom/src/` returned 0 results. The plugin only implemented the Interview views from Spec 2, skipping the core Requirement views entirely.
- **Not implemented item 2 (Status bar item)**: The `hermes-plugin.json` manifest and `activate.ts` were supposed to register a `reqogniloom.status` status bar item showing an open-requirement count. Reviewed `activate.ts` and found no `statusBarItems` being registered.

## [2026-08-14-interview-management-engine-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-08-14-interview-management-engine-design.md)
- **Not implemented item 1 (CI-Freshness-Check)**: The spec requires a new CI job to close the drift gap (Commit c49a503) by running the build scripts (`build_opencode_package.py`, etc.) in a temporary directory and diffing against the committed `dist/` stand. I checked the workflows in `.github/workflows/` (using `grep_search` for `dist` and `build_opencode_package`) and found no such job. The existing `version-drift-check.yml` only checks deployed API versions against git history, not the plugin packages.

## [2026-08-14-interview-management-hermes-plugin-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-08-14-interview-management-hermes-plugin-design.md)
- **All planned features are implemented**. I verified that `InterviewListView.tsx` and `InterviewFormView.tsx` are present, `mcpClient.ts` handles the JSON-RPC communication, and `interview_protocol.py` on the backend correctly implements the new form field types (`type`, `choices`) in `ProtocolField`.

## [2026-08-14-interview-management-web-widget-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-08-14-interview-management-web-widget-design.md)
- **All planned features are implemented**. I verified that `InterviewSession` includes the `transcript` JSONField in `models.py`. The `POST /api/v1/interviews/{id}/chat/` endpoint is present in `interview_views.py`. `InterviewWidget` is mounted inside `NavigationShell.tsx`, and the `AiPromptsSection.tsx` automatically discovers and generates the labels for `interview.protocol.<type>` slots with the new variable hint block.

## [2026-08-16-prompt-variable-catalog-design.md](file:///c:/Repositories/ai-native-reqflow-POC/docs/superpowers/specs/2026-08-16-prompt-variable-catalog-design.md)
- **Not implemented item 1 (Promptfoo Testinfrastruktur)**: Phase 3 (Promptfoo testing) is entirely missing. I checked the backend for the `export_promptfoo_configs` management command and found no matches. I attempted to list the `backend/application/prompt_testing/cases/` directory, but it does not exist. Additionally, there is no CI job for promptfoo in `.github/workflows/`.
\n\n