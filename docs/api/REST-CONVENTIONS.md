# REST Cross-Cutting Conventions

Contracts that hold across the whole `/api/v1/` surface, rather than for one
endpoint. Each of them is something a client has to know and that the generated
OpenAPI schema does not state well enough on its own — either because it is
about *two* requests interacting, or because the honest answer is "this fails,
and that is correct".

**Related:** [MCP surface reference](MCP-SURFACE.md) · generated OpenAPI at
`GET /openapi.json` (JSON), `GET /api/schema/` (YAML, JSON via `Accept`) and
`/api/schema/swagger-ui/` — see §8.

---

## 1. Optimistic locking on `PATCH` — two paths, not one

A `PATCH` can be made conditional in **two** independent ways. The second one
(`expected_version` in the request body) predates the first and is documented
nowhere else; both must be known to use the feature correctly.

| Path | Where | Accepted shape | Stale answer |
|------|-------|----------------|--------------|
| **HTTP precondition** | `If-Match` request header | a single **strong** entity-tag, e.g. `If-Match: "7"` | `412 PRECONDITION_FAILED` |
| **Body field** | `expected_version` in the JSON body | integer ≥ 1 | `409 CONFLICT` |

### Precedence

`If-Match` wins. If both are present and disagree, the header is authoritative —
the standard HTTP mechanism is the only one an intermediary (cache, proxy,
gateway) can reason about, and it is the one the version is checked against
inside the service's row-locked transaction. Supplying a body
`expected_version` that contradicts the header is a client bug that the server
resolves in the header's favour rather than failing on.

`If-Match` is only honoured as a *single strong tag*:

* `W/"7"` — a weak tag never satisfies `If-Match` (RFC 9110 § 13.1.1 strong
  comparison), and is treated as "no precondition given".
* `*` — an existence check, not a revision check. The row was already loaded,
  so it always passes. `tools/call` / no-op.
* `"7", "8"` — a multi-tag list is out of scope. Matching "any of N revisions"
  would need a `version IN (...)` compare in the service, which no `update_*`
  offers, so the header is ignored and the body field applies.
* A non-numeric tag is ignored by the header path and falls through to
  `expected_version`. (The immutable-`Baseline` PATCH route compares the tag
  directly rather than parsing it, which is what lets it accept a timestamp
  tag.)

### Omitting both

A `PATCH` with neither header nor body field is **last-writer-wins**. That is
not an oversight: it is the behaviour for callers that do not track versions.

### Which resources

| Resource | `ETag` on GET/PATCH | `If-Match` | `expected_version` |
|----------|--------------------|------------|--------------------|
| `/api/v1/requirements/{id}/` | yes | yes | yes |
| `/api/v1/test-cases/{id}/` (alias `testcases`) | yes | yes | yes |
| `/api/v1/architecture/{id}/` | — | — | yes |
| `/api/v1/needs/{id}/` | — | — | yes |
| `/api/v1/adrs/{id}/` | — | — | yes |
| `/api/v1/risks/{id}/` | — | — | yes |
| `/api/v1/issues/{id}/` | — | — | yes |
| `/api/v1/change-requests/{id}/` | — | — | yes |
| `/api/v1/glossary/{id}/` | — | — | yes |
| `/api/v1/baselines/{id}/` | yes | yes (`412`) | n/a — baselines are immutable, PATCH answers `405` |
| `POST .../transitions/` | workflow revision in the response | yes, but means the **workflow** revision | yes, but means the **entity** version |
| `goal`, `main-goal` | — | — | not enforced (lineage-versioned; updates append a version) |
| `test-runs` | — | — | not declared — sending it is an unknown field (`400`) |

The `ETag` value is the entity's `version` counter, quoted (`"7"`) — the very
counter `expected_version` compares against, so the two can never disagree
about which revision is current. Entities without a `version` counter fall back
to a timestamp tag; that is the `Baseline` case.

### `transitions/` is a different lock

`POST /api/v1/<entity>/{id}/transitions/` accepts `expected_version` and
`If-Match` too, and they mean the **workflow** revision
(`WorkflowItemState.version`), not the entity's `ETag`. Both revisions are
included in the GET and POST responses so the value is discoverable. A stale
value answers **`409 CONFLICT`**, deliberately different from the `412` a
stale `If-Match` on `PATCH` answers — same header, two different things, two
different status codes, on two routes of the same resource. An intermediary
that normalises 412 to 409 (or vice versa) will mis-handle one of them.

Two further traps on that route:

* the workflow revision is **not derivable**. Nothing in the workflow graph,
  the item's fields or the entity ETag reveals it; the only sources are the
  `version` key of the GET and POST responses. A client must be *handed* one.
* the transition response embeds the refreshed entity, which keeps **its own**
  version under its own key (e.g. `body["requirement"]["version"]`). That is
  the number for a subsequent `PATCH`; the top-level `body["version"]` is the
  workflow revision. Two different numbers with two different meanings in one
  response.

Omitting both on `transitions/` stays supported and is last-writer-wins. A
non-numeric revision is a `400`, not a permanent `409`.

---

## 2. Read-only fields on `PATCH` → `400 VALIDATION_ERROR`

Server-owned and privilege-shaped fields cannot be set through `PATCH`. This is
correct, deliberate behaviour — these keys used to be dropped by the serializer
without a word while the request still answered `200`, so a cross-workspace move
or a mass-assignment attempt *looked* like it had succeeded
([#269](https://github.com/Popoboxxo/ReqogniLoom/issues/269) finding 5).

| Field | `PATCH` answer |
|-------|---------------|
| `workspace_id` | **`400 VALIDATION_ERROR`** — `'workspace_id' is read-only and cannot be set via PATCH.` |
| `id`, `uid`, `version` | `400` — same rule |
| `artifact_id`, `tenant_id`, `created_at`, `updated_at`, `created_by_id`, `modified_by_id` | `400` — same rule |
| `is_admin` | `400` — same rule |
| `status` | `400` with a *different* message: `status cannot be changed via PATCH; use POST .../transitions/ with a target_state instead.` A `status` that is a verbatim echo of the current value is accepted and ignored, so a client may round-trip what it read. |
| any key the serializer does not declare | `400` — `Unknown field '<key>'.` |

`workspace_id` is the one worth calling out, because it is the natural thing to
send when a client holds a stale workspace handle: an entity cannot be moved
between workspaces with `PATCH`. `change_reason` and `custom_fields` are
additionally accepted on every entity regardless of whether the serializer
declares them, because the detail panels send them on every save.

This applies to the workflow-backed entity ViewSets — `Requirement`,
`StakeholderNeed`, `ArchitectureElement`, `TestCase`, `Adr`, `Risk`, `Goal`,
`MainGoal`, `Issue`, `ChangeRequest`, `GlossaryTerm`.

---

## 3. Baselines: `workspace_id` is not optional

**Use the nested route.** It cannot be called without the workspace, so it
cannot be called wrong:

```
GET  /api/v1/workspaces/{workspace_id}/baselines/
POST /api/v1/workspaces/{workspace_id}/baselines/
```

The flat route exists for backward compatibility (older frontend and MCP
callers use the query parameter) and requires the parameter explicitly:

```
GET  /api/v1/baselines/?workspace_id={workspace_id}
POST /api/v1/baselines/           # workspace_id in the body
```

Calling the flat list route **without** `workspace_id` answers **`404`**, not
`400`. That is misleading — it reads as "baselines do not exist" rather than
"you forgot a parameter" — and it is a real defect in the response, tracked
alongside the misleading-message theme in
[#460](https://github.com/Popoboxxo/ReqogniLoom/issues/460).

Root cause, for whoever fixes it: `BaselineViewSet.list` runs the **preset gate
first**, and the gate's workspace fallback is
`request.query_params["workspace_id"] or str(auth_ctx.tenant_id)` — with no
query parameter it feeds the **tenant id in where a workspace id belongs**, the
feature lookup finds no such workspace, and the gate raises `Http404`. The
parameter validation (`parse_workspace_id`, which does produce a proper
`400 VALIDATION_ERROR`) only runs afterwards. Reordering the two would change
which of two simultaneous errors a caller sees, so the fix has to be in the
gate's fallback, not in the ordering.

**Do not work around it.** There is no tenant-wide baseline list: baselines are
workspace-scoped, and the preset gate is per workspace. Pass the workspace.

Baselines are additionally **immutable**: `PATCH` answers `405`, and a baseline
is finished by creating a new one. Its `ETag` is a `created_at` timestamp
rather than a version counter, for that reason — and the `If-Match` precondition
is evaluated *before* the immutability answer, so a stale tag on a baseline
`PATCH` answers `412` (the resource changed under the client) while a current
tag or no header answers `405`.

---

## 4. TraceLink endpoints: which UUID `source_id` / `target_id` expects

`POST /api/v1/tracelinks/` takes `source_id`, `target_id` and `link_type`.
**`pl_tracelink` has no `source_type` / `target_type` column** — endpoint types
are resolved through the union table `pl_artifact`, and the row stores
**Artifact UUIDs**.

Every specialized table owns its own primary key *and* a backing `Artifact` row
with a **different** primary key. Both ids are valid inputs; the server
resolves either one and stores the Artifact UUID.

| You pass | What the server resolves | Stored as |
|----------|--------------------------|-----------|
| the **sub-type entity id** — what `GET /api/v1/requirements/` returns as `id` | the entity's `artifact_id` | the Artifact UUID |
| the **backing Artifact id** — what existing TraceLink rows and `GET /api/v1/artifacts/{id}/` return | itself, unchanged | the Artifact UUID |

The two forms are interchangeable, and passing the sub-type id is usually
easier: the id you just read from the entity's own `GET` is the id you send.
A client never has to look up the `artifact_id` separately.

```bash
# Both of these create the same link.
curl -X POST "$API/api/v1/tracelinks/?workspace_id=$WS" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"source_id": "<Requirement.id>",       "target_id": "<ArchitectureElement.id>", "link_type": "decomposes"}'

curl -X POST "$API/api/v1/tracelinks/?workspace_id=$WS" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"source_id": "<Requirement.artifact_id>", "target_id": "<ArchitectureElement.artifact_id>", "link_type": "decomposes"}'
```

The response's `source_id` / `target_id` are always the **Artifact** UUIDs,
whatever you sent. Read them from the response if you need to chain further
calls.

Resolution is registry-driven (`persistence/artifact_backing.py`,
`ARTIFACT_TYPE_MODELS`) and tenant-scoped: each probe reads a subtype table's
own primary key through its tenant-filtering manager, so a foreign-tenant id
matches nothing and answers `404 NOT_FOUND` without leaking existence.

### Cross-reference: #1075

Until [#1075](https://github.com/Popoboxxo/ReqogniLoom/issues/1075) landed, the
resolution was a hand-maintained probe list. It listed `Requirement`,
`ArchitectureElement`, `TestCase`, `StakeholderNeed`, `Adr`, `Goal`, `MainGoal`,
`Risk` and `Issue` — and **not** `Icd`, which is why an ICD that
`GET /api/v1/icds/{id}/` returned as `200` was a `404` link endpoint. The same
divergence affects every artifact-backed type; ICD only exposed it first because
its serializer returns no `artifact_id` field at all.

**The contract documented above is the post-#1075 contract**, and it is the
stable one: the resolution is registry-driven, so a newly added artifact-backed
type resolves without anyone remembering to add it to a list. If you are reading
this on a build older than #1075, treat "Icd resolves" as not yet true and pass
`artifact_id` instead.

---

## 5. VCRM is MCP-only

The **Verification Cross Reference Matrix** (COMP-TE-004,
[#410](https://github.com/Popoboxxo/ReqogniLoom/issues/410)) is available
**only through MCP**, as the tool `traceability.vcrm`. There is deliberately no
REST counterpart:

| | |
|---|---|
| MCP tool | `traceability.vcrm` |
| Parameters | `workspace_id` (required), `format` = `json` (default) \| `csv` |
| REST route | **none** |
| OpenAPI operations mentioning `vcrm` | **0** |

No route, view, serializer or OpenAPI source under `backend/rest_api/**`
mentions `vcrm` (the only case-insensitive hits are two prose comments in
`rest_api/tests/`), so no REST route and no generated OpenAPI operation
mentions it. A client searching only the REST documentation will not find the
capability — that is the trap
[#1085](https://github.com/Popoboxxo/ReqogniLoom/issues/1085) point 5 reports.

VCRM is an agent-facing aggregate (requirement × component × test case ×
result), not a CRUD entity, so it owns no REST collection. The canonical
description of where VCRM lives is
[MCP surface reference § 6](MCP-SURFACE.md#6-vcrm--a-capability-with-no-rest-route),
which also records that the PDF variant `export_vcrm_pdf()` is implemented and
tested but intentionally reachable from no transport (unused-by-design). This
section is the REST-side statement of the same decision, so the asymmetry is
visible from both documents and neither contradicts the other.

---

## 6. List responses: one pagination envelope

Every list/collection endpoint under `/api/v1/` — the workflow-backed entity
ViewSets, `/users/`, `/api-keys/`, `/reviews/`, `/reviews/pending/`,
`/link-type-defaults/` and the workspace-scoped link types — answers with the
same offset envelope:

```json
{
  "count": 42,
  "next": "…?page=3",
  "previous": "…?page=1",
  "page_size": 25,
  "max_page_size": 100,
  "results": [ /* … */ ]
}
```

`page` (1-based) and `page_size` (default 25, hard-capped at 100) are the query
parameters. The effective `page_size` and the ceiling `max_page_size` are echoed
so a client can tell a *capped* page from a *short last* page. An invalid `page`
answers **404** (`rest_api.serializers.StandardPagination`), never a 500.

### `/users/` — a completed breaking transition

`GET /api/v1/users/` used to return a **bare JSON array** and ignored
`page`/`page_size`, unlike every other list endpoint. It now returns the
envelope above (audit finding INT-05, AUD-2026-09-074). This is a **breaking
change** for a client that assumed an array:

* The in-repo consumers were migrated with it — `frontend/src/api/users.ts`
  requests `?page_size=100` and reads `results`, and
  `e2e/tests/user-management.spec.ts` accepts the envelope.
* A consumer that still reads the response body as a top-level array must switch
  to `body.results`. `count`/`next`/`previous` stay additive for clients that
  already read them.

---

## 7. Path spelling: canonical kebab-case, aliases keep working

Multi-word collection paths use **kebab-case** as the canonical spelling. Every
resource whose spelling was historically mixed is registered under **both**
forms — the canonical path and a backward-compatible alias — so no existing
client breaks and new clients have a single rule:

| Canonical (kebab-case) | Backward-compatible alias |
|------------------------|---------------------------|
| `/api/v1/test-cases/` | `/api/v1/testcases/` |
| `/api/v1/trace-links/` | `/api/v1/tracelinks/` |
| `/api/v1/test-runs/` | `/api/v1/testruns/` |
| `/api/v1/main-goals/` | `/api/v1/maingoals/` |
| `/api/v1/change-requests/` | `/api/v1/changerequests/` |

Both spellings resolve to the **same** `ViewSet` and the **same** objects —
neither is a separate implementation, a second serializer or a second service.
New clients should use the canonical column; the alias column is frozen (it
exists for compatibility and is not a place to add new routes). §1 names the
canonical spelling and the tests cover both forms resolving identically.

---

## 8. OpenAPI access points and content types

The generated OpenAPI 3 document is reachable four ways. All are **public** (no
Bearer token / tenant context required):

| URL | Format | `Content-Type` |
|-----|--------|----------------|
| `GET /openapi.json` | JSON | `application/vnd.oai.openapi+json` |
| `GET /api/openapi.json` | JSON | `application/vnd.oai.openapi+json` |
| `GET /api/schema/` | YAML by default; JSON with `Accept: application/json` | `application/vnd.oai.openapi` (YAML) / `application/vnd.oai.openapi+json` (JSON) |
| `GET /api/schema` | same as `/api/schema/` | same |

`/openapi.json` is the canonical machine-readable document for SDK generators
that cannot consume YAML. `/api/openapi.json` is an alias — it matches the path
the auth middleware's exemption list (`auth_tenancy.middleware`) already carries,
and the path the SE requirements name. `/api/schema/` is kept unchanged as the
YAML entry point.

Because `APPEND_SLASH` is disabled project-wide (CR-03), the non-trailing
`/api/schema` had no redirect to fall back on and used to 404; it is therefore
routed explicitly and now answers directly.

The `Content-Type` is set on both renderers, so a strict client (one that refuses
to parse a body whose media type it does not recognise) can consume the document
without a special case.

---

## 9. `memory.ask` on REST — a write-gated read with an explicit degradation state

`POST /api/v1/workspaces/{workspace_id}/memory/ask/` (view
`WorkspaceMemoryAskView`, route name `workspace-memory-ask`) is the REST mirror
of the MCP tool `memory.ask`
([MCP surface reference § 4](MCP-SURFACE.md#4-the-memory-group-in-full)).
Before [#1155](https://github.com/Popoboxxo/ReqogniLoom/issues/1155) Aspekt 1 the
capability existed only over MCP; this route closes that asymmetry. Both
transports delegate to the same `MemoryEntryService.ask`, so they share one
validation, one `MemoryPolicy` and one answer shape — the REST body is not a
second implementation.

### Request

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `query` | string | **yes** | Non-blank; at most 10000 characters (`MAX_ASK_QUERY_CHARS`). |
| `artifact_id` | UUID | no | Aims the question at that artifact's scope; the service resolves the owning workspace itself, so the workspace path segment is still required. |
| `reasoning_level` | string | no | One of `minimal` / `low` / `medium` / `high` / `max` (`VALID_REASONING_LEVELS`). |

A missing or blank `query`, an unknown `reasoning_level` or a malformed
`artifact_id` answers **`400 VALIDATION_ERROR`** before any backend call.

### Response

```json
{
  "answer": "…",
  "generated_at": "2026-10-06T12:34:56.789012+00:00",
  "backend": "honcho",
  "degraded": false,
  "detail": ""
}
```

Field-for-field the MCP payload; `generated_at` is ISO-8601. `derivation_status`
does **not** appear here: it is a `MemoryDigest`-only signal and the MCP tool
does not emit it either, so adding it on REST alone would break the mirror.

### Authorization is the WRITE gate

The route is a `POST`, so the default `RbacPermission` maps it to
`Operation.WRITE` and fails closed: a Viewer-role member is denied **`403`
before the handler runs**, and an API key on the `read_only` capability tier is
denied independently of RBAC. The MCP tool is write-gated the same way
(`_WRITE_TOOL_PREFIXES`) — the call drives a generative LLM, so "it only reads"
is not a reason to let a read-only credential spend tokens. Inside the service
`MemoryPolicy` additionally fences the workspace/artifact scope.

### No `memory.write` rate limit — deliberately

`memory.ask` is **not** charged to the `memory.write` fixed-window limiter
(`memory.ratelimit`, `MEMORY_WRITE_RATE_LIMIT_PER_HOUR`, default `60`): that
counter is a writes-per-hour quota guarding the persistence + embedding budget,
while `ask` stores nothing. Charging it would silently redefine an
admin-configured knob and let question-asking starve legitimate writes. The MCP
path enforces no such limit either, so a REST-only limit would be asymmetric
across transports and trivially bypassed through the other one. Cost is bounded
instead by the WRITE gate, the transport throttles and `MEMORY_ASK_TIMEOUT`. A
dedicated ask quota, if ever wanted, belongs in `MemoryEntryService.ask` so both
transports inherit it.

### F9: `degraded` and an empty `answer` are different states

`degraded` is the field to inspect before trusting `answer`:

* `degraded: true` — the engine could not answer (no dialectic surface on this
  backend, unreachable engine, unknown scope). `detail` names the cause as
  `engine_error:<ClassName>`, `unknown_scope:<ClassName>` or
  `"no dialectic engine"`, and never carries user data.
* `degraded: false` with an empty `answer` — a genuine "nothing known".

`ask` never raises and never answers `500` for a backend-side failure; a failing
backend degrades into the flag, exactly like `digest`. On `pgvector`, which has
no generative engine, this degradation is the normal shape, not an error.
