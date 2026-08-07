---
name: test-lifecycle
description: Use when creating or linking test cases, deriving tests from requirements, or recording test-run results in a ReqogniLoom workspace.
---

# Test Lifecycle

See [DOMAIN_MODEL.md](../../DOMAIN_MODEL.md) for the REQ-ID schema and trace-link types referenced
below.

## Workflow

1. `workspace.get_context` — learn the active rigor preset (it changes which fields a test case
   must carry before linking to a requirement); `custom_field.get`/`custom_field.query` show
   workspace-specific test-case fields beyond that (e.g. a required environment/browser matrix).
2. Find the requirement you're testing with `requirement.get`/`requirement.query`, and check
   `traceability.query` to see whether a test case already covers it — don't create duplicates.
3. Create the test case with `test.create`; refine with `test.update`.
4. Link it to the requirement with `test.link` using the `TESTS` link type.
5. When it's time to execute: `test.run_create` starts a run, `test.run_report_results` records
   outcomes per test case (`passed`/`failed`/`blocked`/`skipped` — this also advances the run's
   lifecycle phase and, on a passing result, is expected to add a `VERIFIES` link back to the
   requirement), `test.run_get` checks current status without re-submitting results. The 4-phase
   lifecycle is `created` -> `in_progress` -> `completed`/`failed` -> `archived`.
6. `test.derive_from_requirement` asks the LLM adapter to propose a test-case skeleton from a
   requirement's acceptance criteria — use it as a starting draft, always review before
   `test.create`/`test.update`.
7. `artifact.search` finds related test cases or requirements by free text when you don't have an
   exact ID.
