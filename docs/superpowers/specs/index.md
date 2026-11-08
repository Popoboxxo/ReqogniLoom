# Spec Index

This index lists every design/spec document in this directory tree and its implementation status,
proven against the source code (not against the spec's own claims). Mirrors the structure of
`docs/superpowers/plans/index.md` — a spec and its corresponding implementation plan(s) are tracked
independently since a spec can be superseded/decided-against without its later plan doc changing, and
vice versa.

- **`Archive/`** — specs whose full scope has been implemented and verified. Kept for historical
- **This directory (top level)** — specs with real open work, or explicitly deferred/partly superseded. Statuses re-checked against `origin/main` on 2026-11-04.

## Top level — open work

## [2026-11-08-navigationsbaum-und-verbindungsansicht-design.md](2026-11-08-navigationsbaum-und-verbindungsansicht-design.md)
**Open — design draft, no plan yet, not implemented; all open questions answered 2026-11-08, awaiting sign-off.** Two UI restructurings: (a) the Requirements route's left column goes back to being a pure navigation tree — the group admin panel becomes a modal dialog (O1) plus a per-row "add to group" action and a drag-to-group drop; (b) the connection view gains a `trees` mode as the new default: the requirement tree and the architecture tree side by side in one scroll container with allocation edges drawn in the gutter. `two-column` stays as its own mode (O2); the edge overlay and the "more filters" expansion are user preferences (O3/O4). Amends §6.2 of the ordnung-allokation spec (default view) only after sign-off (O5), and removes the duplicate requirement list from the allocation assistant. Prerequisites found in the code and specified here: `allocation-view` element rows carry no `sort_key` (`application/allocation_view_service.py:154`), the element catalogue is capped at 500 combined rows (`frontend/src/components/ConnectionView/useAllocationView.ts:51`), and `element_subtree` never filters the element column. Plan: [`../../plans/2026-11-08-navigationsbaum-und-verbindungsansicht.md`](../../plans/2026-11-08-navigationsbaum-und-verbindungsansicht.md) (tasks G, V2, V — not started).

## [2026-11-01-opencode-v2-support-design.md](2026-11-01-opencode-v2-support-design.md)
**Open — design draft, superseded in parts by the 2026-11-03 spike.** Design for supporting OpenCode V1 and V2 in parallel. Its "Stand 2026-11-03" section replaces §3 and §4: one shared Streamable HTTP config (V1 form, URL `…/mcp/`) carries both versions, so the second registry entry, V2 snippet, merge tool and version autodetect fall away. Unproven points are tracked in #1702–#1706. The valid implementation plan is [`../plans/2026-11-01-opencode-v2-support.md`](../plans/2026-11-01-opencode-v2-support.md) (tasks not started).

## [2026-10-21-backlog-umsetzungsplaene-design.md](2026-10-21-backlog-umsetzungsplaene-design.md)
**Open — umbrella strategy, status "proposed", mixed progress.** Strategy for the 67-issue backlog. Several work packages have landed (promptfoo, 2FA, quality assessment, documents and work items, client docs, key-principal fixes), but A4 Honcho expansion, the BluePencil image (#1418), ErrorBoundary (#598), inspector trace-links (#801), F4/F5 baselines and projection (#1374) and the manual publication steps remain. Not every work package was checked individually, so it is not archived. Track progress through `docs/plans/2026-10-21-backlog-umsetzung-index.md`, not this spec.

## [2026-09-03-menschen-im-system-design.md](2026-09-03-menschen-im-system-design.md)
**Partly implemented, partly superseded — kept at top level because a residual is pending.** Comments and notifications (models, REST, `comment.*` MCP tools, inspector panel, notification feed, user preferences) are done (PR #956; archived plan: [`../plans/Archive/2026-09-03-menschen-im-system-collaboration.md`](../plans/Archive/2026-09-03-menschen-im-system-collaboration.md)); the owner/assignee half was overtaken by the central `Artifact.owner`/`reporter` Actor attribution of Attribut v3 / AWMS. What remains is the AWMS contract step that drops `Risk.owner_name`/`owner_user` and `Issue.assignee_id`, plus the unverified `assign` audit entry on owner changes.

## [2026-09-03-github-jira-integration-design.md](2026-09-03-github-jira-integration-design.md)
**Open — not implemented.** There is no `ExternalRef` entity, no webhook receiver, no `integration.*` tool group and no `external_trigger` on workflow transitions; the only trace is a code comment in `link_types/builtin.py`. The three stages (link-only, inbound sync, outbound and agent) are all still open; a plan exists (`plans/2026-09-03-github-jira-integration.md`) but is unstarted.

## [2026-09-03-mcp-modernisierung-design.md](2026-09-03-mcp-modernisierung-design.md)
**Open — not implemented beyond the ICD read tools (`icd.read`, `icd.query`).** The server still negotiates MCP 2024-11-05, has no `resources/*` or `prompts/*`, no `Mcp-Session-Id` streamable transport and no `ApiKey.tool_groups` curation or `tool.list_groups` tool. The spec remains valid but is unstarted.

## [2026-09-03-tabellenansicht-design.md](2026-09-03-tabellenansicht-design.md)
**Open — not implemented; updated 2026-11-04.** There is no table view filter DSL, no `SavedView` or `UserTableViewState`, and no `artifacts/bulk-update` or `bulk-transition` endpoint or MCP tool. The spec was corrected against main (no `django_filters`, `@list_schema` and `reject_unknown_query_params` exist, `actor`/`criteria-list` in the operator table, list of constraints per field) and its bulk-update contract replaced (`mode` atomic/partial, `items[]` with `expected_version`, max 100, freeze 409). Plan: [`../plans/2026-11-04-tabellenansicht-neu.md`](../plans/2026-11-04-tabellenansicht-neu.md).

## [2026-09-03-dokumentensicht-design.md](2026-09-03-dokumentensicht-design.md)
**Superseded by [2026-11-04-dokumentensicht-neu-design.md](2026-11-04-dokumentensicht-neu-design.md).** Naming note (2026-11-02, ENT-F2 = b): the view is called **`DocumentView`**; the artifact named `Document` is specified in [2026-11-02-f2-document-design.md](Archive/2026-11-02-f2-document-design.md). This file stays as the design record of the old read-only view; nothing of it is built.

## [2026-11-04-dokumentensicht-neu-design.md](2026-11-04-dokumentensicht-neu-design.md)
**Open — design draft, no plan yet.** Editable `DocumentView` (chapters from subtree, filter or list; read, edit-immediately and collect modes; Markdown export; MCP `document_view.*`). Waits for #1670 P1 (`sort_key`), #1670 P4 (freeze) and slice 1 of the Tabellenansicht plan (filter DSL, `bulk-update`); an implementation plan is written only after those are merged.

## [2026-09-03-rollenbasierte-sichten-design.md](2026-09-03-rollenbasierte-sichten-design.md)
**Open — not implemented apart from the `audience: basic | expert` attribute flag and its editor toggle.** Navigation role gating is still the hardcoded `NAV_ITEMS.requires` array, there are no `NavigationVisibility` tables or editor, and the form does not collapse expert sections or offer an expert mode. The reference to issue #848 is stale (closed, different title).

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

## [Archive/2026-09-03-attribute-definition-design.md](Archive/2026-09-03-attribute-definition-design.md)
All planned features are implemented (PR #888, merged). Matches the already-verified implementation plan (`docs/superpowers/plans/Archive/2026-09-03-attribute-definition.md`).

## [Archive/2026-09-03-datenmodell-konsolidierung-design.md](Archive/2026-09-03-datenmodell-konsolidierung-design.md)
All planned features are implemented (PR #880, merged). Matches the already-verified implementation plan (`docs/superpowers/plans/Archive/2026-09-03-datenmodell-konsolidierung.md`).

## [Archive/2026-09-03-traceability-semantik-design.md](Archive/2026-09-03-traceability-semantik-design.md)
All planned features are implemented (PR #891, open — CI green, mergeable, awaiting human merge). Matches the already-verified implementation plan (`docs/superpowers/plans/Archive/2026-09-03-traceability-semantik.md`).

## [Archive/2026-08-13-hermes-ide-plugin-design.md](Archive/2026-08-13-hermes-ide-plugin-design.md)
All items resolved (2026-09-11). Item 1 (Requirements Views and APIs) was never built and is superseded by the interview-management approach (see the archived `interview-management-*-design.md` entries). Item 2 (Status bar item) was resolved by PR #633 (merged 2026-08-20), which added the explicit `ctx.register({ id: "reqogniloom.status", area: "statusBar.right", ... })` call in `activate.ts`. Note: the corresponding plan (`docs/superpowers/plans/2026-08-13-hermes-ide-plugin-requirements-mvp.md`) stays at top level deliberately — superseded, not implemented as written.

## [Archive/2026-08-20-multi-palette-theming-design.md](Archive/2026-08-20-multi-palette-theming-design.md)
All planned features are implemented, and the structural gap (**#707**) that previously kept this spec (and its three phase plans) out of Archive/ is resolved by [the theme-presets plan](../plans/Archive/2026-08-24-theme-presets.md) (PR #745) — palette and light/dark mode are now two independent, freely combinable axes. `gh issue view 707` confirms `state: CLOSED` (re-verified 2026-09-11).

## [Archive/2026-09-03-ki-vorschlag-als-zustand-design.md](Archive/2026-09-03-ki-vorschlag-als-zustand-design.md)
All planned features are implemented (PR #904, merged 2026-09-11, CHANGELOG [1.8.0-beta.10]). Agent-authored workflow items (MainGoals, Requirements, TraceLinks, …) enter a `proposed` state that the same agent can never confirm; `ApiKey` gains agent identity, scope and expiry; `proposed_by`/`proposed_at` are exposed over REST and the review queue gained an AI-proposals mode with bulk confirm. Matches the archived implementation plan (`Archive/2026-09-03-ki-vorschlag-als-zustand.md`). One non-blocking spec inconsistency remains (confirming a link nulls `TraceLink.proposed_by`/`proposed_at`, destroying link provenance) — recorded, not a scope gap.

## [Archive/2026-09-03-interview-engine-fix-design.md](Archive/2026-09-03-interview-engine-fix-design.md)
All planned features are implemented (PR #903, merged 2026-09-11, CHANGELOG [1.8.0-beta.10]). `formalize()` dispatches through the `ARTIFACT_CREATION_ADAPTERS` registry for all 8 in-scope artifact types; interview provenance shows on every artifact detail view; `InterviewSession.transcript_summary` + a sliding-window compressor cap prompt growth; `/interviews?start=multi` is a real discovery entry point. Matches the archived implementation plan (`Archive/2026-09-03-interview-engine-fix.md`). The earlier GlossaryTerm blocker was resolved by datenmodell-konsolidierung (PR #880).

## [Archive/2026-09-11-attribute-definition-v2-design.md](Archive/2026-09-11-attribute-definition-v2-design.md)
All planned features are implemented (spec/plan PRs #901/#902, implementation PR #905, merged 2026-09-11, CHANGELOG [1.8.0-beta.10]). Adds create/delete of custom attribute definitions at Global and Workspace scope through the shared validation path, a table/list toggle, an options editor with a `count_usages` safety check, origin badges + type icons, `sections[]` with visibility toggling and a half/full CSS-Grid layout, and export/import with skip/overwrite/rename collision handling plus REST + MCP surface. Matches the archived implementation plan (`Archive/2026-09-11-attribute-definition-v2.md`). The catalog concept (v2 spec §5) remains an explicitly out-of-scope future extension.
## [Archive/2026-07-25-phase6-agent-templates-design.md](Archive/2026-07-25-phase6-agent-templates-design.md)
Fully implemented, decided against on one point only (2026-08-20). The five downstream agent templates, BOOTSTRAP.md, README and the optional Claude Code review-policy hook live under `docs/agent-templates/`, guarded by CI tests that check every listed tool against the tool manifest. The single deviation is that the requirements role ships as `requirements-architecture-manager.md` instead of `requirements-architect.md`; the user chose to keep that name.

## [Archive/2026-08-14-interview-management-engine-design.md](Archive/2026-08-14-interview-management-engine-design.md)
All planned features are implemented (the earlier "Not implemented / CI gap" entry was stale). The `InterviewSession` model, the seven `interview.*` MCP tools with REST facade, formalize/grounding/auto-abandon logic and the interview skill exist, and the CI freshness gap is closed by `dist/test_full_regeneration.py`, which the `agent-templates-test` job runs. Semantic grounding uses an LLM ranking prompt rather than the pgvector similarity the spec mentioned; it stays optional and never blocks. Not verified: a role-level (`SET ROLE`) RLS test specifically for `InterviewSession`.

## [Archive/2026-08-16-prompt-variable-catalog-design.md](Archive/2026-08-16-prompt-variable-catalog-design.md)
All three phases are implemented: the `PromptVariable` catalog with one shared resolver, the content-driven architecture decompose (`max_breadth`/`max_depth`), the catalog UI with unknown-placeholder warnings, and the promptfoo pipeline (`export_promptfoo_configs`, per-slot case files, `prompt-regression` CI job using the `echo` provider). Deviations are recorded in spec section 6.1. Issue #587 is still open on GitHub only because nobody closed it; the byte-identical snapshot test exists but was not run during the review.

## [Archive/2026-11-02-f2-document-design.md](Archive/2026-11-02-f2-document-design.md)
All planned features are implemented (PRs #1647-#1653; the earlier "F2-T2..T8 remain open" entry was stale). The `Document` artifact with workflow presets, the three document link types, `DocumentService` with freeze and release gates G-1..G-4, `/api/v1/documents/` with ETag and soft-delete contract, the `document.*` MCP tools, events, indexer, baseline capture and the Documents UI all exist on main. The acceptance-criteria checkboxes in the spec are still unchecked. Umbrella issue #1374 stays open for F4 baselines and F5 projection, which this spec excludes.

## [Archive/2026-11-02-f3-workitem-design.md](Archive/2026-11-02-f3-workitem-design.md)
All planned features are implemented (PRs #1656-#1671; the earlier "F3-T2..T9 remain open" entry was stale). The `WorkItem` artifact, tiered workflow presets, `depends-on` and decomposition link pairs, `WorkItemService` with resume/checkpoint/heartbeat, `/api/v1/work-items/`, the eight `work_item.*` MCP tools, the inline-anchor register with rules I-1..I-5, events, the `DOC-P5`/`DOC-P7` audit rules and the Work Items UI are on main. Not individually verified: that the MCP tool descriptions quote the Honcho/Loom boundary verbatim (spec section 12). Umbrella issue #1374 stays open for F4 and F5.
