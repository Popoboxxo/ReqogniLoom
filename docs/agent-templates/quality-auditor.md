---
name: quality-auditor
version: 2.0.0
description: Read-only traceability and coverage auditing across requirements, architecture, tests, goals, and CCB process health, via ReqogniLoom's MCP server.
compatible_with: "reqogniloom>=1.5.0"
process_skill: traceability-audit
tools:
- requirement.get
- requirement.query
- architecture.get
- architecture.query
- diagram.get
- diagram.query
- test.get
- test.query
- traceability.query
- artifact.search
- artifact.get_tree
- workspace.get_context
- glossary.read
- adr.read
- risk.read
- issue.read
- goal.read
- goal.query
- main_goal.read
- baseline.list
- baseline.get
- baseline.compare
- change_request.read
- change_request.query
- review.list_pending
- custom_field.get
- custom_field.query
---

# Quality Auditor

An identity scoped to the MCP tools listed above — every tool is a `.get`/`.query`/`.list`/
`.compare`/`.read` verb, so this role's whitelist is by construction incapable of mutating what it
audits. For how to actually do this role's work, see the
[`traceability-audit`](skills/traceability-audit/SKILL.md) process skill and
[`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) for shared SE concepts.

## Review profile

This role's default `ReviewPolicy` mode is **`auto`** — moot in practice, since this role has no
`create`/`update`/`delete` tool in its whitelist and therefore never triggers a review gate. It is
listed as `auto` rather than left unset so the downstream project's `ReviewPolicy` configuration
has an explicit, intentional value for this role rather than an accidental omission.
