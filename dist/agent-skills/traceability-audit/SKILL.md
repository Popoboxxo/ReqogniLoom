---
name: traceability-audit
description: Use for read-only traceability and coverage auditing across requirements, architecture, tests, goals, baselines, and CCB process health in a ReqogniLoom workspace.
---

# Traceability and Coverage Audit

See [DOMAIN_MODEL.md](../../DOMAIN_MODEL.md) for the REQ-ID schema, trace-link types, and baseline
scopes referenced below. This skill is strictly read-only by design — it never mutates anything it
audits; findings route to whichever role/skill owns the fix.

## Workflow

1. `workspace.get_context` — learn the active rigor preset before judging what "complete
   traceability" means for this workspace; a `minimal`-preset workspace does not necessarily
   expect every requirement to carry a documented rationale, don't flag its absence as a gap there.
   `custom_field.get`/`custom_field.query` show which workspace-specific fields exist beyond the
   core schema — a missing custom field the preset doesn't actually require is not a gap either.
2. Walk the tree with `requirement.query` / `architecture.query` / `test.query`, using
   `artifact.get_tree` for the hierarchical L0-L4 structure at a glance; once a query surfaces a
   specific element worth a closer look, `requirement.get`/`architecture.get`/`test.get` fetch it
   directly by ID. `diagram.get`/`diagram.query` check whether architecture elements have current
   diagram documentation.
3. For each element of interest, call `traceability.query` to inspect its link graph and compare
   against what the rigor preset expects — a requirement with no `IMPLEMENTS`/`DERIVED_FROM`
   successor, or a test case with no `TESTS` link, is a coverage gap; a `CONFLICTS_WITH` link found
   during audit is itself a finding, not something to resolve here.
4. Cross-check ADRs, risks, and issues with `adr.read`, `risk.read`, `issue.read` — an open issue
   or unmitigated risk against a requirement is a quality signal worth including even though it
   isn't a traceability gap per se.
5. `goal.query`/`main_goal.read` extend the audit upward: does every captured need still trace to
   an active goal; `goal.read` fetches a single goal by ID once `goal.query` has narrowed it down.
   `baseline.list`/`baseline.compare` extend it against history: does the current state of a
   baselined element still match what was actually baselined — `baseline.get` fetches a specific
   baseline by ID when you already know which one to inspect — report both views when they differ,
   since a gap against a baselined element may already be fixed in a newer, not-yet-baselined
   version. `change_request.query` (search by criteria) and `change_request.read` (fetch one by
   ID) together with `review.list_pending` surface CCB process health (aging pending reviews,
   Change Requests with no linked baseline) as a distinct class of finding.
6. Use `artifact.search` and `glossary.read` to resolve ambiguous terminology (e.g. confirming two
   similarly-worded requirements aren't actually a naming collision).
7. Compile findings into a report — this skill never edits ReqogniLoom data; route requirement gaps
   to the `vmodell-decomposition` skill's role, missing test coverage to `test-lifecycle`'s role,
   unmitigated risks to `risk-derivation`'s role, and conflicting ADRs/issues/CCB backlog to
   `ccb-approval-and-baseline`'s role.
