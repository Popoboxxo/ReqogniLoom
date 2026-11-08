# Plan Index

This index lists every plan document in `docs/plans/` and `docs/plans/Archive/` and its implementation status,
checked against `origin/main` (audit of 2026-11-04). It mirrors `docs/superpowers/plans/index.md`.

Evidence level: the backlog plans A-G were verified at PR/commit level (commit subject on `origin/main` plus
existence of the named deliverable), not line by line. Items that could not be proven from the repository are
marked UNVERIFIED. GitHub issues named below were NOT closed by this archiving step.

- **`Archive/`** — plans whose own scope has been implemented. Kept for historical reference; no more code work expected
  (open housekeeping issues are listed per entry).
- **This directory (top level)** — plans with real open work, plus live coordination and decision documents.

## Top level — open work

## [2026-11-08-navigationsbaum-und-verbindungsansicht.md](2026-11-08-navigationsbaum-und-verbindungsansicht.md)
**Open — plan written, nothing implemented; every task checkbox unchecked.** Implementation plan for the spec of the same date: **(G)** move the requirement group administration out of the navigation column into a modal dialog, plus a per-row "add to group" action and a drag-to-group drop; **(V2)** split the `allocation-view` read object by row kind (`kind=requirement|element`, fixing the shared 500-row cap and the ineffective `element_subtree` filter) and expose the artifact `sort_key` on element rows; **(V)** add the `trees` connection view as the default — requirement tree and architecture tree in one scroll container, allocation edges in the gutter, selection in the rows, collapsed filter bar, two new user preferences. Three PRs (G, V2, V); V ships as one PR because V1's assistant-list removal and V3's row checkboxes only work together. Spec: [`../superpowers/specs/2026-11-08-navigationsbaum-und-verbindungsansicht-design.md`](../superpowers/specs/2026-11-08-navigationsbaum-und-verbindungsansicht-design.md).

## [2026-09-18-ui-dialog-und-button-konsolidierung.md](2026-09-18-ui-dialog-und-button-konsolidierung.md)
**Open — mostly superseded in practice.** UI consolidation plan from the 2026-09 audit (dialog footers, one button standard, attribute labels and order). The button block was effectively delivered through the design-system ratchet (violations ceiling 0), but the duplicate ConfirmDialog, the label-resolver/section-order tasks and the final acceptance were never closed out; the issue-driven parts (#985, #986, #929 family) are closed. Checkboxes in the file are not maintained (136 open vs 8 checked). Re-scope against the 2026-10-19 UI audit plan before executing further.

## [UI_AUDIT_UMSETZUNGSPLAN_2026-10-20.md](UI_AUDIT_UMSETZUNGSPLAN_2026-10-20.md)
**Open — not started.** Execution plan for the 2026-10-19 UI audit (reuse, consistency, usability): P0 quick wins (comment ID bug, clipboard fallback, loading gates), tabs primitive, sidebar and inspector rebuild, tree move and hierarchy trees, attribute catalog. Only the audit and plan exist on main (PRs #1445, #1452); spot checks show none of the fixes are implemented yet.

## [2026-10-04-one-click-client-installation.md](2026-10-04-one-click-client-installation.md)
**Open.** Concept for one-command MCP + roles/skills installation per provider harness. Stage 1 (registry, installer/verifier, DE/EN client docs, CI drift gate) is implemented; Stage 2 (store/registry/npm publication, waves W1-W5) is drafted but unpublished and depends on external accounts tracked in #1230. Stage-1 residue (provider data-call proof) is self-reported, not independently verified.

## [2026-10-05-bugfix-hub-integrationen.md](2026-10-05-bugfix-hub-integrationen.md)
**Open (one verification left).** Work plan for the external-boundary bug bundles B0-B5 (REST/MCP parity, provider robustness, plugin runtime, API contract, Honcho memory). All bundle issues except #1153 are closed and the B5 memory/suggestion deliverables exist on main; only the live proof for the Honcho dialectic header (#1153) and the stage-2 publication (tracked in the one-click plan) remain.

## [2026-10-21-plan-a-memory-und-suche.md](2026-10-21-plan-a-memory-und-suche.md)
**Open, essentially code-complete.** All 29 PRs of the memory and search plan (embedding provenance, backend-neutral settings, three-level memory injection with HARD_OFF, Qdrant artifact index with hybrid query and pgvector fallback, Honcho dream/derived search/summaries/webhooks, search mode and recall set) are on main (verified at PR/commit level). What remains is closing the nine linked issues (#1317 #1336 #1337 #1339 #1314 #1334 #1316 #18 #1378) after checking acceptance, the live T1 proof of `memory.ask` (UNVERIFIED, user gate U-3) and the user-run Qdrant probe window (U-4).

## [2026-10-21-plan-d-deployment-dx.md](2026-10-21-plan-d-deployment-dx.md)
**Open for external work only.** All 15 repo PRs are merged (nginx security headers, promptfoo regression net, env-secret scan, setup/wipe tooling, client documentation, mcp-publisher pin, server.json host template, OpenCode npm package, seed_demo guard). The BluePencil hub/layer work package was overtaken by the removal of BluePencil from the repo (commit 1ad7ef17, 2026-11-02). Left: user-run publication gates tracked in #1230, the required-check setting for `prompt-regression` (UNVERIFIED), and issue housekeeping (#587, #1418 now moot).

## [2026-10-21-plan-g-qa-haertung.md](2026-10-21-plan-g-qa-haertung.md)
**Open, mostly delivered.** QA hardening for uid/workspace-FK integrity, deterministic list ordering and index, quiet outbox/compose behaviour, base-image digest pins, required/length/24px form fixes and the katex override are merged (about 17 of 20 PRs, verified at PR/commit level). Still missing are the NotFound page and dialog focus-return (G5.2) and confirmation of the doc clarifications (G5.3, UNVERIFIED); PR 10 (async create embedding) is conditional and unconfirmed. 14 QA issues remain open (e.g. #1381, #1386, #1399-#1403, #1404, #1406-#1412) and need check-and-close or follow-up.

## Top level — live coordination and decision documents (not plans)

These three files are NOT implementation plans. They stay at top level because the plans that reference them are still open.

## [2026-10-21-backlog-umsetzung-index.md](2026-10-21-backlog-umsetzung-index.md)
**Live coordination index, not a plan.** Cross-plan index for the backlog plans A-G (waves, merge queues, migration-number reservations, shared DoD rules). Written against `b175c970`; almost all of its sequencing is now historical because the plans landed. Still referenced by plans A, D and G. Archive together with the last of them.

## [2026-10-21-entscheidungen-offen.md](2026-10-21-entscheidungen-offen.md)
**Live decision register, not a plan.** Register of the 54 user decisions the A-G plans needed, with options, recommendations and blocked work packages. The blocking ones were decided on 2026-10-22 and 2026-10-26 and are reflected in code; what stays open are a handful of user gates (U-1 required CI check, U-4 Qdrant probe window, U-5 publication accounts, U-6, ENT-F5 follow-up) and decisions made moot by the BluePencil removal. Archive with the plans.

## [2026-10-21-korrekturauftraege.md](2026-10-21-korrekturauftraege.md)
**One-shot work order, exhausted; kept next to the plans it corrected.** Stage-2 work order listing the 112 plan-specific and 11 shared correction orders (KA-*) derived from the technical and security cross-reviews of plans A-G. All were applied to the plans before implementation; the document has no remaining function beyond history and no live task.

## Archive/ — implemented

## [Archive/2026-10-06-adr-019-umsetzungsplan-vorschlags-schleife.md](Archive/2026-10-06-adr-019-umsetzungsplan-vorschlags-schleife.md)
All planned features are implemented. ADR-019 is accepted and WP1-WP7 exist on main: Suggestion entity with RLS migrations, service and adapter registry, `suggestion.*` MCP tools and manifest entries, REST endpoints, the `suggest_links` producer, and the Reviews inbox UI. Deferred by design: other producers, retention, TraceLink field deprecation.

## [Archive/2026-10-07-umsetzungsplaene-1155-1201-1202-1204.md](Archive/2026-10-07-umsetzungsplaene-1155-1201-1202-1204.md)
All four lead topics are implemented. The suggestion loop (#1155) shipped via ADR-019, Hermes now talks to the server over MCP only (#1201/#1202), and Qdrant is an optional vector backend behind a vector port with a compose profile (#1204, ADR-020/022). All referenced issues are closed. Not re-checked at WP granularity: the individual WP-H* UI details of the Hermes dashboard tab (UNVERIFIED; covered by closed #1201/#1202).

## [Archive/2026-10-15-frontend-audit-fixes.md](Archive/2026-10-15-frontend-audit-fixes.md)
All phases 0-8 are implemented and merged (PRs #1426-#1431, #1440, #1441): timer-leak and memo fixes, safeStorage consolidation, list/form scaffolding reuse, type-barrel split, god-component decomposition, WCAG fixes with an axe smoke gate, and design-system ratchet burn-down. The ratchet ceilings have since reached zero.

## [Archive/2026-10-21-plan-b-se-modell.md](Archive/2026-10-21-plan-b-se-modell.md)
**Archived on PR/commit-level evidence — verified at PR/commit level, not line by line.** Every PR-B1..PR-B20b has a commit or deliverable on main: SE attributes filled by seed and interview, `validates` link type and validation coverage and VCRM method, the function element with `performs`/`satisfies` in the catalog, ADR-004 accepted, advisory quality assessment (model, prompts, REST/MCP, audit rules, UI badge), and Milestone as the only B6 entity. Issues still open: #879 (Milestone model/API/UI is merged in PRs #1672-#1674, the issue was not closed). The operational QS seed-backfill step is not repo evidence (UNVERIFIED).

## [Archive/2026-10-21-plan-c-ui-ux.md](Archive/2026-10-21-plan-c-ui-ux.md)
**Archived on PR/commit-level evidence — verified at PR/commit level, not line by line.** PR-C1..PR-C16 were all found as commits: ErrorBoundary no longer leaks raw errors, buttons follow the size/radius token standard with a per-route E2E gate, the three-level preference service (REST, MCP, generic settings UI) carries readable-ID visibility with a contract migration, the markdown toolbar, inspector fixes, TestCase trace panel, profile/review i18n and collapsible sidebar groups. Issues still open: #186 and #85 (plan prescribes close with comment), #946 (replaced by BluePencil, which has since been removed from the repo), and #598, #1094, #1287, #801 (deliverables merged, verify and close). No missing code work found.

## [Archive/2026-10-21-plan-e-security-api.md](Archive/2026-10-21-plan-e-security-api.md)
All planned features are implemented except E2.5, which was decided against and is documented in code (`rest_api/conditional_requests.py`: those families support body `expected_version` -> 409 only). The API-key fence, the honest API contract (If-Match, OpenAPI conditional declarations, typed schema with a zero-fallback ratchet, list-parameter declarations) and TOTP two-factor for staff (models, login step, enrollment API, break-glass reset, enforcement cutover command, UI) are on main. Archived on PR/commit-level evidence — verified at PR/commit level, not line by line. Operator step outside the repo: switching MFA to `required` after `mfa_enforce_cutover`.

## [Archive/2026-10-21-plan-f-dokumente-baselines.md](Archive/2026-10-21-plan-f-dokumente-baselines.md)
**Archived on PR/commit-level evidence — verified at PR/commit level, not line by line.** All planned features of F1-F4 are implemented: central link validation and issue/risk link types, linkable diagrams, lossless row import, baseline capture completeness, baseline tags, additive rollback via change request (ADR-025), the Document artifact with lifecycle/freeze/REST/MCP/UI, and WorkItem with inline anchors and resume state. Archived for its own PR scope only. Issue still open: #1374, which stays open for the separate F5 projection/adoption package (ENT-F5=a, not yet specified).
