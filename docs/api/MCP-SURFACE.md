# MCP Surface Reference

The agent-facing catalogue of the native ReqogniLoom MCP server (`POST /mcp/`,
JSON-RPC 2.0). This document exists because the tool surface changed faster
than the prose describing it, and every drift cost a QA run
([#1085](https://github.com/Popoboxxo/ReqogniLoom/issues/1085),
[#1080](https://github.com/Popoboxxo/ReqogniLoom/issues/1080)).

**The machine-readable catalogue is authoritative.**
[`docs/agent-templates/tool-manifest.json`](../agent-templates/tool-manifest.json)
carries the full contract of every tool (name, prefix, read/write
classification, description, `inputSchema`). Regenerate it with
`python backend/manage.py export_tool_manifest`. The table below is the
human-readable summary of the same data, plus the facts the JSON cannot state
(which tools are deliberately absent, and which capabilities exist only here).

**Related:** [REST cross-cutting conventions](REST-CONVENTIONS.md) ·
generated OpenAPI at `GET /api/schema/` and `/api/schema/swagger-ui/`

---

## 1. Catalogue size

| Figure | Value |
|--------|-------|
| Tools | **220** |
| Tool-group prefixes | **35** |
| Version | `v1.8.0-beta.18` (`VERSION`, `1.8.0-beta.18`) — `memory.ask` (REQ-192, [#1154](https://github.com/Popoboxxo/ReqogniLoom/issues/1154)) is the first tool-surface change since the beta.16 measurement below |
| Measured at | `98b1c9a8` on `fix/beta16-qa-sweep` — i.e. the `v1.8.0-beta.16` tag commit `9eb2fc58` plus [#1080](https://github.com/Popoboxxo/ReqogniLoom/issues/1080) (`65c732b4`, adds `test.run_list`) |
| Source of truth | `docs/agent-templates/tool-manifest.json`, `tool_count` field |

History of the number, so a future reader can tell an intentional change from a
stale copy:

| Claim | Where it appeared | Verdict |
|-------|-------------------|---------|
| 172 tools / 30 groups | `docs/SYSTEMAUDIT_2026-09-02_GROB.md` (audit snapshot) | historical, left as an audit record |
| 212 / 35 | beta.13 documentation | wrong, never re-measured |
| 215 | a docs PR that copied the previous figure instead of measuring | wrong |
| 218 / 35 | measured on `v1.8.0-beta.16` @ `9eb2fc58` ([#1080](https://github.com/Popoboxxo/ReqogniLoom/issues/1080)) | correct for that commit |
| 219 / 35 | after `test.run_list` ([#1080](https://github.com/Popoboxxo/ReqogniLoom/issues/1080)) | correct until `memory.ask` |
| **220 / 35** | after `memory.ask` (REQ-192, [#1154](https://github.com/Popoboxxo/ReqogniLoom/issues/1154)) | **current** |

### How to re-derive the number

Do not copy a number from prose. Measure it, and record the version and the
commit alongside the result.

**Live, against a running instance** (needs a `reqlo_*` API key whose user has
write + governance capability — a Viewer key legitimately sees fewer tools,
because `tools/list` hides what the caller may not execute):

```bash
curl -s -X POST "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
| python3 -c '
import sys, json
tools = json.load(sys.stdin)["result"]["tools"]
groups = {}
for t in tools:
    groups.setdefault(t["name"].split(".", 1)[0], []).append(t["name"])
print(len(tools), "tools /", len(groups), "groups")
for g in sorted(groups):
    print(f"{g} {len(groups[g])}")
'
```

**Offline, from the registry** — no key, no server, no database. This is the
form the CI guard uses:

```bash
cd backend && python manage.py export_tool_manifest --out /tmp/tool-manifest.json
python3 -c '
import json
m = json.load(open("/tmp/tool-manifest.json"))
groups = {}
for t in m["tools"]:
    groups.setdefault(t["name"].split(".", 1)[0], []).append(t["name"])
print(m["tool_count"], "tools /", len(groups), "groups")
'
```

Both forms must agree. Three guards keep them that way, so the number in this
document cannot silently rot:

| Guard | What it pins |
|-------|--------------|
| `backend/mcp_server/tests/test_tool_manifest_drift.py` | committed manifest ↔ live registry, field by field (`is_write`, `prefix`, `description`, `inputSchema`, `tool_count`) |
| `backend/mcp_server/tests/test_entity_surface_parity.py` | the 220/35 figure, and that every REST-exposed entity is readable over MCP |
| `backend/mcp_server/tests/test_export_tool_manifest.py` | the manifest's own shape invariants |

If you add or remove a tool, run all three; if the count moves, update the
table in §1 and §2 **in the same change**, with the new version and commit.

---

## 2. Tool groups

35 prefixes, 220 tools. Tools are called as `<prefix>.<tool_name>`.

| Group | Tools | Names |
|-------|------:|-------|
| `admin` | 3 | `admin.backup_create`, `admin.backup_list`, `admin.restore` |
| `adr` | 7 | `adr.create`, `adr.delete`, `adr.outdate`, `adr.query`, `adr.read`, `adr.reactivate`, `adr.update` |
| `ai_derivation` | 6 | `ai_derivation.decompose_requirement_next_level`, `ai_derivation.derive_adr_from_decision`, `ai_derivation.derive_glossary_from_workspace`, `ai_derivation.derive_requirements_from_need`, `ai_derivation.derive_risks_from_architecture`, `ai_derivation.suggest_architecture_for_requirement` |
| `architecture` | 9 | `architecture.create`, `architecture.decompose`, `architecture.decompose_commit`, `architecture.get`, `architecture.link`, `architecture.outdate`, `architecture.query`, `architecture.reactivate`, `architecture.update` |
| `artifact` | 2 | `artifact.get_tree`, `artifact.search` |
| `attribute_catalog` | 8 | `attribute_catalog.add_to_definition`, `attribute_catalog.create`, `attribute_catalog.deprecate`, `attribute_catalog.export`, `attribute_catalog.import`, `attribute_catalog.list`, `attribute_catalog.search`, `attribute_catalog.update` |
| `attribute_definition` | 13 | `attribute_definition.count_usages`, `attribute_definition.create`, `attribute_definition.create_workspace`, `attribute_definition.delete`, `attribute_definition.delete_workspace`, `attribute_definition.export`, `attribute_definition.export_workspace`, `attribute_definition.get`, `attribute_definition.import`, `attribute_definition.import_workspace`, `attribute_definition.list`, `attribute_definition.reset`, `attribute_definition.update` |
| `attribute_migration` | 6 | `attribute_migration.apply`, `attribute_migration.dry_run`, `attribute_migration.get_run`, `attribute_migration.list_runs`, `attribute_migration.plan`, `attribute_migration.rollback` |
| `audit` | 5 | `audit.ai_review`, `audit.query`, `audit.se_audit`, `audit.waive_finding`, `audit.waivers` |
| `baseline` | 4 | `baseline.compare`, `baseline.create`, `baseline.get`, `baseline.list` |
| `change_request` | 7 | `change_request.create`, `change_request.delete`, `change_request.outdate`, `change_request.query`, `change_request.read`, `change_request.reactivate`, `change_request.update` |
| `comment` | 3 | `comment.create`, `comment.list`, `comment.resolve` |
| `context` | 4 | `context.change_impact`, `context.query`, `context.related`, `context.test_coverage` |
| `diagram` | 6 | `diagram.create`, `diagram.get`, `diagram.outdate`, `diagram.query`, `diagram.reactivate`, `diagram.update` |
| `events` | 2 | `events.dlq_list`, `events.dlq_replay` |
| `glossary` | 7 | `glossary.create`, `glossary.delete`, `glossary.outdate`, `glossary.query`, `glossary.read`, `glossary.reactivate`, `glossary.update` |
| `goal` | 10 | `goal.create`, `goal.create_version`, `goal.delete`, `goal.list_versions`, `goal.outdate`, `goal.query`, `goal.read`, `goal.reactivate`, `goal.transition`, `goal.update` |
| `icd` | 4 | `icd.create`, `icd.query`, `icd.read`, `icd.update` |
| `interview` | 10 | `interview.abandon`, `interview.answer`, `interview.formalize`, `interview.get`, `interview.get_state`, `interview.grounding_context`, `interview.list`, `interview.propose`, `interview.set_target`, `interview.start` |
| `issue` | 7 | `issue.create`, `issue.delete`, `issue.outdate`, `issue.query`, `issue.read`, `issue.reactivate`, `issue.update` |
| `link_type` | 5 | `link_type.create`, `link_type.get`, `link_type.list`, `link_type.reset`, `link_type.update` |
| `main_goal` | 5 | `main_goal.approve`, `main_goal.create_manual`, `main_goal.generate`, `main_goal.list_versions`, `main_goal.read` |
| `memory` | 7 | `memory.ask`, `memory.digest`, `memory.forget`, `memory.get`, `memory.list`, `memory.query`, `memory.write` |
| `needs` | 8 | `needs.create`, `needs.derive_requirements`, `needs.get_traces`, `needs.outdate`, `needs.query`, `needs.read`, `needs.reactivate`, `needs.update` |
| `permissions` | 4 | `permissions.check`, `permissions.list`, `permissions.revoke`, `permissions.set_rule` |
| `prompt_template` | 4 | `prompt_template.create`, `prompt_template.get`, `prompt_template.list`, `prompt_template.update` |
| `prompt_variable` | 4 | `prompt_variable.clear`, `prompt_variable.get`, `prompt_variable.list`, `prompt_variable.set` |
| `requirement` | 11 | `requirement.check_consistency`, `requirement.check_consistency_status`, `requirement.create`, `requirement.decompose`, `requirement.derive`, `requirement.get`, `requirement.outdate`, `requirement.query`, `requirement.reactivate`, `requirement.update`, `requirement.validate` |
| `requirement_bundle` | 3 | `requirement_bundle.attribute_schema`, `requirement_bundle.compression_status`, `requirement_bundle.export` |
| `review` | 4 | `review.approve`, `review.list_pending`, `review.reject`, `review.request_changes` |
| `risk` | 7 | `risk.create`, `risk.delete`, `risk.outdate`, `risk.query`, `risk.read`, `risk.reactivate`, `risk.update` |
| `test` | 14 | `test.create`, `test.derive_from_requirement`, `test.get`, `test.link`, `test.mark_reviewed`, `test.outdate`, `test.query`, `test.reactivate`, `test.run_complete`, `test.run_create`, `test.run_get`, `test.run_list`, `test.run_report_results`, `test.update` |
| `traceability` | 5 | `traceability.coverage`, `traceability.create_link`, `traceability.query`, `traceability.suggest_links`, `traceability.vcrm` |
| `user` | 9 | `user.activate`, `user.assign_role`, `user.assign_tenant_admin`, `user.create`, `user.deactivate`, `user.list`, `user.reactivate_role`, `user.revoke_tenant_admin`, `user.suspend_role` |
| `workspace` | 7 | `workspace.close`, `workspace.delete`, `workspace.get_context`, `workspace.get_preferences`, `workspace.list`, `workspace.llm_system_prompt`, `workspace.reactivate` |

### Prefixes that share one tool group

Three prefixes are served by a single group instance, so a tool's prefix is not
always its module: `traceability` + `artifact` + `context` are one
`CrossCuttingToolGroup`, and `audit` + `events` are one `AuditToolGroup`
(REQ-129). The registration table is
`backend/mcp_server/tool_registry.py::ToolRegistry._ensure_groups`.

---

## 3. What is deliberately *not* in the catalogue

Agents hit these limits; they are decisions, not gaps in progress. Adding one
means a new tool, not a new namespace.

| Absent | Why | What exists instead |
|--------|-----|---------------------|
| `comment.query` | The comment tool group has one read shape: list the comments of one artifact. There is no free-text or filter query over comments. | `comment.list` (`artifact_id`) |
| `testcase.*` | There is no `testcase` prefix. The TestCase entity lives in the `test` group. | `test.get`, `test.query`, `test.create`, `test.update`, `test.link`, `test.mark_reviewed`, `test.outdate`, `test.reactivate`, `test.derive_from_requirement` |
| any API-key management tool | Key lifecycle is a REST-only governance path; MCP exposes no `api_key.*` / `permissions.key.*` group, so a compromised MCP client cannot mint itself a key. | REST `POST/GET/DELETE /api/v1/api-keys/` |
| notification tools | The notification feed is human-facing. | REST `GET /api/v1/notifications/` |
| `main_goal.query` | Only `main_goal.read` (by id) and `main_goal.list_versions` (by lineage) exist, so a MainGoal is not enumerable by workspace. | REST `GET /api/v1/main-goals/?workspace_id=` |
| a workspace-wide TraceLink enumeration | `traceability.query` needs an `artifact_id`; there is no "list every link in this workspace" tool. | `traceability.coverage` (counts, does not enumerate) |

The last two were found by the entity-surface parity ratchet
(`backend/mcp_server/tests/entity_surface_matrix.py`) when it was written for
[#1080](https://github.com/Popoboxxo/ReqogniLoom/issues/1080), and are
recorded there as ratcheted gaps rather than left unmentioned.

One more absence worth stating explicitly, because the opposite claim is the one
in circulation: **`memory.write` does exist.** See §4.


---

## 4. The `memory` group in full

`memory.write` **does exist** and has existed since RFC #1002. Writing is not
restricted to the background projector: `memory.write` is the explicit,
caller-driven write path, and `memory.forget` the explicit delete path. An
earlier QA note claiming "`memory.write` does not exist (writing only via
projectors)" was wrong; correcting it here so the next reader does not repeat
it.

| Tool | Class | Purpose |
|------|-------|---------|
| `memory.ask` | write (LLM) | Natural-language question answered from one scope's memory |
| `memory.digest` | read | Consolidated digest of one scope |
| `memory.forget` | write | Delete a memory entry (ownership/admin-gated) |
| `memory.get` | read | One entry by id |
| `memory.list` | read | Recent entries for a workspace / user-tenant scope |
| `memory.query` | read | Semantic search over a workspace or user-tenant memory |
| `memory.write` | write | **Create an entry explicitly**, with `scope` = `workspace` \| `user` \| `artifact` |

`memory.write` parameters: `content` (required), `scope` (required; one of
`workspace` / `user` / `artifact`), `workspace_id`, `artifact_id`,
`confidence` (default `1.0`), `change_reason`. Scope `artifact` without an
`artifact_id` is rejected rather than silently landing in the workspace scope.

`memory.ask` ([#1154](https://github.com/Popoboxxo/ReqogniLoom/issues/1154),
REQ-192) parameters: `query` (required; at most 10000 characters), `workspace_id`
(required; also the scope id when no artifact is named), `artifact_id`
(optional; narrows the question to that artifact's scope), `reasoning_level`
(optional; one of
`minimal` / `low` / `medium` / `high` / `max`). It delegates to the active
backend's dialectic surface (`MemoryBackend.ask`): on Honcho the question is
answered through `peer.chat`, scoped to the scope's session; on `pgvector`,
which has no generative engine, the answer is a defined degradation
(`degraded: true`, empty `answer`) rather than an error or an HTTP 500. The
response mirrors the digest shape plus a degradation hint: `answer`,
`generated_at`, `backend`, `degraded`, `detail`. Like the digest it is
RBAC-gated by the same read matrix and never raises — but unlike the digest it
is **write-gated**: it invokes a generative LLM call, so a read-only/Viewer key
must not be able to drive LLM spend (same rule as `interview.grounding_context`).

Writes are rate-limited per `(tenant, user)` via
`MEMORY_WRITE_RATE_LIMIT_PER_HOUR` (default `60`; `0` = unlimited). The active
backend is selected by `MEMORY_BACKEND` (`pgvector` default, `honcho`
optional).

---

## 5. The `test` group and the TestRun lifecycle

`test` is one group covering two entities: **TestCase** and **TestRun**. The
run tools use a `run_` infix rather than a separate `test_run` prefix, because
the registry already shares one group instance across the prefixes of an entity
family (`traceability`/`artifact`/`context`, `audit`/`events`) and a second
prefix would split one lifecycle across two namespaces while duplicating its
schemas in `tools/list`.

| Tool | Class | Purpose |
|------|-------|---------|
| `test.run_create` | write | Create a run; optional `test_case_ids` seed `not_run` result rows |
| `test.run_list` | read | **List a workspace's runs, newest first** (added in [#1080](https://github.com/Popoboxxo/ReqogniLoom/issues/1080)) |
| `test.run_get` | read | One run plus its per-TestCase result rows |
| `test.run_report_results` | write | Record results (bulk or single object) |
| `test.run_complete` | write | Finalize a run explicitly (`close_test_run`) |

Before #1080 the TestRun entity existed over REST (`GET /api/v1/test-runs/`)
but no tool could *find* one over MCP — only `test.run_get`, which needs an id
the caller already held. A run created by CI, or by another agent, was
therefore invisible. `test.run_list` closes that.

### The four-phase lifecycle

The documented phases are `created → in_progress → completed/failed →
archived`. The model's own vocabulary is narrower, and the tools report what the
model stores rather than the prose:

| Phase | `TestRun.status` | Written by |
|-------|------------------|------------|
| created / started | `in_progress` | `test.run_create` |
| running | `in_progress` | `test.run_report_results`, while any result is still `not_run` |
| completed / failed | `passed` / `failed` / `partial` | derived from the recorded results by `test.run_report_results`; `test.run_complete` re-derives the same aggregate when it closes a run that has results |
| archived | `closed` | `test.run_complete` on a run with **no** results — a deliberate human verdict |

There is deliberately no `created`, `completed` or `archived` value on
`TestRun.status`; `passed`/`failed`/`partial` already say *how* a run ended.
`passed`/`failed`/`partial` are **derived**: re-reporting a result after a run
finalized re-derives them. `closed` is the one status a later result post does
not overwrite — the result rows are still recorded.

`test.run_list` rows carry the observable evidence of that state: `status`,
`result_summary` (`total` / `passed` / `failed` / `blocked` / `not_run`),
`finished_at` (null while `in_progress`), plus `id`, `workspace_id`, `name`,
`uid`, `ci_job_id`, `version`, `created_at`, `updated_at`. A list row is the
same shape a `test.run_get` body returns, and the same shape
`GET /api/v1/test-runs/{id}/` returns.

Parameters: `workspace_id` (required — the dispatcher narrows the caller's
roles to it and answers `PERMISSION_DENIED` for a workspace they hold no role
in), `status` (optional filter, one of the five values above), `limit`
(optional, 1–500, default 100; applied in the query, so a large workspace is
not materialised whole).

---

## 6. VCRM — a capability with no REST route

`traceability.vcrm` exports the **Verification Cross Reference Matrix**
(COMP-TE-004, [#410](https://github.com/Popoboxxo/ReqogniLoom/issues/410)):
requirement × component × test case × result, per workspace.

| | |
|---|---|
| MCP tool | `traceability.vcrm` |
| Parameters | `workspace_id` (required), `format` = `json` (default) \| `csv` |
| JSON result | the matrix rows plus `row_count` |
| CSV result | `csv` (the mandatory CSV export) plus `row_count` |
| REST route | **none** |
| OpenAPI operations mentioning `vcrm` | **0** |

A full-text search of the generated OpenAPI schema for `vcrm` returns no hits
(`backend/rest_api/**` and `backend/rest_api/openapi.py` contain **0**
occurrences), which is exactly the trap [#1085](https://github.com/Popoboxxo/ReqogniLoom/issues/1085)
point 5 reports: a reader who searches the REST documentation never finds the
capability. This section is the canonical answer to "where does VCRM live".

Implementation: `backend/traceability/vcrm_report_generator.py` (Layer 1,
`VCRMReportGenerator`), re-exported through
`backend/traceability/services.py` (`generate_vcrm`, `export_vcrm_csv`,
`export_vcrm_pdf`).

**Unreachable third format.** `export_vcrm_pdf(workspace_id, baseline_id?)` is
implemented and unit-tested, but *no transport exposes it*: the MCP tool accepts
`format` = `json` \| `csv` only, and there is no REST route. So PDF exists in
the code and in the tests, and nowhere else — a reader of either the code or the
API docs will come away with a different picture. Recommendation: add
`format: "pdf"` to `traceability.vcrm`, or note the gap here and in the
component architecture doc (COMP-TE-004), which currently lists
`export_vcrm_pdf()` as part of the interface without saying nothing calls it.

Same shape, same reason: `traceability.coverage` and `audit.se_audit` (from
[#1001](https://github.com/Popoboxxo/ReqogniLoom/issues/1001)) are also
MCP-only. **Recommendation (not implemented here — the REST surface is owned by
another workstream):** either expose `GET /api/v1/vcrm/?workspace_id=` and
`GET /api/v1/vcrm/export.csv/?workspace_id=`, or state the MCP-only status in the
OpenAPI description of the traceability operations, so the asymmetry is visible
from the REST schema instead of only from this file.

---

## 7. Read/write classification

`tools/list` is role- and capability-filtered: a caller sees exactly the tools
it may execute.

| Key tier (`ApiKey.scope`) | Sees |
|---------------------------|-------|
| `read_only` | read tools only |
| `author` | + content writes; the governance namespaces hidden |
| `admin` (also the legacy `write` tier) | everything |

The **governance namespaces** (ADMIN tier) are `admin`, `user`, `permissions`,
`workspace`, `events`, `baseline`, `prompt_template`, `prompt_variable`,
`link_type`, `attribute_definition`, `attribute_catalog`,
`attribute_migration` — plus one tool-level exception, `audit.waive_finding`.
`audit` itself is *not* a governance namespace: `audit.se_audit` is a
read-only SE-Auditor run that any workspace member may call, so only the waiver
(the act that accepts a known deviation) is lifted to ADMIN. The authoritative
set is `mcp_server.tool_registry._GOVERNANCE_TOOL_NAMESPACES` /
`_GOVERNANCE_TOOL_NAMES`.

Note that `baseline.list` / `baseline.get` / `baseline.compare` stay READ-tier;
only `baseline.create` (whose gate override/waiver is an approval-authority act)
is governance. Similarly `review.*` and `interview.*` are ordinary content
writes, not governance.

`tools/list` also narrows, never widens: both `tools/list` and the custom
`tools/filter` accept `toolset` (a named phase preset), `filter`
(`{groups, names, search}`) and `compact`. The named toolsets are `core`,
`authoring`, `verification`, `auditing`, `admin` and `ai`. `tools/filter`
additionally returns `count`, `total` (the caller's full RBAC-gated catalogue
size) and `toolsets`, so a client can see what a filter saved. The catalogue is
always RBAC-gated *before* filtering, so a filter can only ever narrow it.

`tools/call` still works for any tool the key's scope and role permit,
regardless of the filter — `ApiKey.tool_groups` is catalogue curation, not a
security boundary.

Two error shapes worth distinguishing when diagnosing a `tools/call`:

* an **unknown** tool name answers JSON-RPC `-32601` (`UNKNOWN_TOOL`);
* a **known** tool the caller's key or role may not use answers
  `PERMISSION_DENIED` with a message naming the role or the capability tier —
  not `-32601`. A `-32601` therefore always means "no such tool", never "not
  allowed".
