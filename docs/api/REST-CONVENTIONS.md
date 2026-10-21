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
| **HTTP precondition** | `If-Match` request header | `*` or one or more **strong** entity-tags, e.g. `If-Match: "7"` / `"7", "8"` | `412 PRECONDITION_FAILED` |
| **Body field** | `expected_version` in the JSON body | integer ≥ 1 | `409 CONFLICT` |

### Precedence

`If-Match` wins. If both are present and disagree, the header is authoritative —
the standard HTTP mechanism is the only one an intermediary (cache, proxy,
gateway) can reason about, and it is the one the version is checked against
inside the service's row-locked transaction. Supplying a body
`expected_version` that contradicts the header is a client bug that the server
resolves in the header's favour rather than failing on.

### `If-Match` decision matrix (GH-1396)

The header is parsed into an explicit result; there is no "unparseable, so
pretend it was absent" fallback. **400** means the field-value is not a valid
`If-Match`, so the precondition could not be evaluated at all. **412** means it
was evaluated and does not hold.

| Header value | Answer |
|---|---|
| absent | no assertion — the body `expected_version` fallback applies |
| present but blank / whitespace | `400 INVALID_IF_MATCH` |
| `*` | `200` — existence check; no revision comparison, body field ignored |
| single strong tag equal to the current `ETag` | `200` |
| single strong tag not equal | `412 PRECONDITION_FAILED` |
| `W/"7"` (weak validator) | `412` — `If-Match` uses *strong* comparison (RFC 9110 § 13.1.1), so a weak tag can never match |
| unquoted / unbalanced / garbage (`7`, `"7`, `garbage`) | `400 INVALID_IF_MATCH` |
| list (`"7", "8"`) | `200` when **any** strong tag equals the current `ETag`, else `412`; weak entries never match |
| list with a malformed entry | `400 INVALID_IF_MATCH` |

Two further rules the table implies:

* The comparison is against the resource's own current `ETag`, not against a
  re-parsed integer — so the `Baseline` route's ISO-timestamp tag compares
  correctly. When a list matches, the matching revision is still forwarded so
  the authoritative compare stays inside the service's row lock.
* Tags compare as opaque strings: `"07"` is not `"7"` and does not match it.

### Omitting both

A `PATCH` with neither header nor body field is **last-writer-wins**. That is
not an oversight: it is the behaviour for callers that do not track versions.

### Which resources — conditional requests are opt-in

Four resources support them:

| Resource | `ETag` on GET/PATCH | `If-Match` on PATCH | `412` declared |
|----------|--------------------|---------------------|----------------|
| `/api/v1/requirements/{id}/` | yes | yes | yes |
| `/api/v1/test-cases/{id}/` (legacy alias `testcases`) | yes | yes | yes (`testcases` too) |
| `/api/v1/workspaces/{id}/` | yes | yes | yes |
| `/api/v1/baselines/{id}/` | yes — a `created_at` timestamp, not a counter | yes — evaluated *before* the `405` | yes |

Everything below does **not** support conditional requests: it emits no `ETag`
and ignores `If-Match`. Its `PATCH` still accepts the `expected_version` **body**
field (stale → `409 CONFLICT`), which is the older, non-HTTP half of the same
guarantee.

| Resource | `ETag` | `If-Match` | `expected_version` |
|----------|--------|------------|--------------------|
| `/api/v1/architecture/{id}/` | — | ignored | yes |
| `/api/v1/needs/{id}/` | — | ignored | yes |
| `/api/v1/adrs/{id}/` | — | ignored | yes |
| `/api/v1/risks/{id}/` | — | ignored | yes |
| `/api/v1/issues/{id}/` | — | ignored | yes |
| `/api/v1/change-requests/{id}/` | — | ignored | yes |
| `/api/v1/glossary/{id}/` | — | ignored | yes |
| `POST .../transitions/` | workflow revision in the response | yes, but means the **workflow** revision | yes, but means the **entity** version |
| `goal`, `main-goal` | — | — | not enforced (lineage-versioned; updates append a version) |
| `test-runs` | — | — | not declared — sending it is an unknown field (`400`) |

The `ETag` value is the entity's `version` counter, quoted (`"7"`) — the very
counter `expected_version` compares against, so the two can never disagree
about which revision is current. Entities without a `version` counter fall back
to a timestamp tag; that is the `Baseline` case.

A `PATCH` on a workspace that changes nothing the user recognises still advances
the counter: `version` is a concurrency token, not a content revision number
(see the note on `AuditableModel.version`).

### No `412` without `If-Match` (`#1397`)

The `412` a generated client retries on is only meaningful together with the
request header that produces it, so the contract pairs them:

* the OpenAPI document declares `412` on exactly the four `PATCH` operations
  above — five path entries, because `TestCaseViewSet` is routed twice — and
  declares an **optional** `If-Match` header parameter on exactly the same five;
* no operation outside that set declares `412`, and no operation outside it
  declares `If-Match`. Both directions are a contract bug: a `412` on a route
  that ignores the header advertises a failure a client cannot avoid, and an
  `If-Match` parameter on a route that ignores it advertises protection the
  server does not give.

The single source of truth is `backend/rest_api/conditional_requests.py`
(`CONDITIONAL_REQUEST_OPERATIONS`, `UNSUPPORTED_CONDITIONAL_FAMILIES`); it also
produces the conditional-request paragraph of the published schema description.
`backend/rest_api/tests/test_conditional_request_contract_1397.py` regenerates
the schema in-process and fails if the document and that module disagree. Adding
an entry requires the route to actually evaluate the header
(`ETagMixin.check_if_match` / `ETagMixin.resolve_expected_version`) **and** to
emit the `ETag` its clients condition against.

**Why only these four.** They are the only resources whose `ETag` derives from a
monotonic `version` counter (or, for the immutable `Baseline`, a stable
timestamp) that `expected_version` already compares against — an `ETag` and a
body field therefore can never disagree about which revision is current.
Retro-fitting `ETag`/`If-Match` onto the other six artifact families would add a
write precondition to six ViewSets with no client demand: a stale header would
start refusing writes that answered `200` before. That is a behaviour change,
not a contract-honesty fix, so those families remain explicitly *not* conditional.

### `transitions/` is a different lock

`POST /api/v1/<entity>/{id}/transitions/` accepts `expected_version` and
`If-Match` too, and they mean the **workflow** revision
(`WorkflowItemState.version`), not the entity's `ETag`. Both revisions are
included in the GET and POST responses so the value is discoverable. A stale
value answers **`409 CONFLICT`**, deliberately different from the `412` a
stale `If-Match` on `PATCH` answers — same header, two different things, two
different status codes, on two routes of the same resource. An intermediary
that normalises 412 to 409 (or vice versa) will mis-handle one of them.

The header is parsed by the same parser as on `PATCH`, with the same
`400 INVALID_IF_MATCH` for a blank/malformed value; only the *mismatch* answer
differs (409 here, 412 there). A tag list is compared against the workflow
revision on this route. The dedicated special routes (`/adrs/{pk}/supersede/`,
`/change-requests/{pk}/transition/`, …) share that mapping but cannot resolve
the current workflow revision up front, so they treat a tag list as a
mismatch.

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
tag or no header answers `405`. A malformed header is the same
`400 INVALID_IF_MATCH` as everywhere else.

### Preset-gated endpoints — documented, never silently opened

Some routes exist only where the workspace's active **rigor preset** enables
their feature key. The runtime check is `PresetGateMixin` +
`preset_endpoint_key`; baselines (`preset_endpoint_key = "baselines"`) are the
worked example:

| Preset | `baselines` | `GET /api/v1/baselines/?workspace_id=…` |
|--------|-------------|------------------------------------------|
| `minimal` | off | `404` |
| `standard` | on | `200` |
| `extended` | on | `200` |

A preset-disabled route answers **`404`**, not `403` — the endpoint does not
exist for that workspace, so its absence must not be distinguishable from an
unknown route or an unknown id. Baselines, an unknown/foreign workspace and an
unknown baseline id all render the same opaque `NOT_FOUND` body
(`rest_api/not_found.py`), which is deliberate. The flat collection route adds
one more cause: a missing `workspace_id` makes the gate fall back to the
caller's tenant id, resolves no workspace, and therefore answers `404` in
**every** preset (see above).

Two rules follow:

* **The schema states the gate.** Since #1380 the generated OpenAPI description
  of `/api/v1/baselines/` (`GET` and `POST`) and `/api/v1/baselines/{id}/`
  (`GET`) names the preset condition and carries a dedicated `404` response
  describing all three causes; `GET /api/v1/baselines/` declares
  `workspace_id` as a **required** query parameter. A generated client can
  therefore see that the call may legitimately 404 without the resource being
  absent, and can supply the parameter the gate needs.
* **A gate is never silently opened to make the schema true.** The honest fix
  for "the document advertises an endpoint that 404s" is to document the
  condition, not to remove the gate. Changing a preset gate is a product
  decision that goes through the preset registry (`presets/registry.py`), never
  a side effect of an API-contract change.

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

### Reading links: `source_id` is an Artifact id, not an entity `id` (#1270)

A link's `source_id` / `target_id` are **Artifact** UUIDs — the same space as an
entity's `artifact_id`, **not** its `id`. Joining a Requirement's `id` against a
link's `source_id` matches nothing and silently yields wrong coverage (a QA run
read "100 % orphans" instead of ~0.7 %). Link reads therefore also expose the
unambiguous, read-only aliases `source_artifact_id` / `target_artifact_id`; the
original keys keep their values.

| Field | Value |
|-------|-------|
| `source_id` / `target_id` | the stored Artifact UUIDs (backward compatible) |
| `source_artifact_id` / `target_artifact_id` | the same values, unambiguous names |

Join trace links against `artifact_id` (or `source_artifact_id`), never against
an entity's `id`.

### The three identifiers, and when each is stable (#1261)

| Identifier | Scope | Use it for | Survives ReqIF re-import? |
|------------|-------|------------|----------------------------|
| `uid` (e.g. `REQ-001`) | workspace-local, human-readable | display, prose, traceability docs | **no** — reassigned on import into another workspace |
| `id` | the entity row's primary key | the entity's own API paths (`/requirements/{id}/`) | no |
| `artifact_id` | the canonical Artifact UUID | TraceLink endpoints, cross-workspace references, exports | **yes** |
| `global_uuid` | read-only alias of `artifact_id` (#1261) | display the stable UUID as an attribute | **yes** |

`global_uuid` can be displayed but never set. The workspace-local `uid` is the
human-readable label; the global UUID is the durable reference. See
[#1270](https://github.com/Popoboxxo/ReqogniLoom/issues/1270) and
[#1094](https://github.com/Popoboxxo/ReqogniLoom/issues/1094).

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

---

## 10. Hard `DELETE` stays — the detail UI offers an outdated transition instead

`DELETE /api/v1/{resource}/{id}/` remains on every workflow-backed artifact type
(requirements, needs, adrs, risks, issues, testcases, architecture) and on the
MCP surface. It is a **soft** delete: the row survives and moves to the
workflow's outdated-equivalent state (`state_meta: {…: {is_outdated_equivalent:
true}}`, e.g. `deprecated`, `Superseded`, `Wontfix`, `Closed`), and the list
endpoints hide it unless the caller opts in with `?include_deleted=true`.

The endpoints exist for **admin / data-hygiene / automation** callers (scripts,
migrations, MCP agents) that decide server-side to retire an artifact. They are
deliberately **no longer offered from the artifact detail UI** (decision D6):
the detail form's destructive button is gone and has been replaced by a
"Veralten" action that runs the artifact's own workflow transition to the
outdated-equivalent target. Consequences:

* Retiring an artifact from the UI now goes through `POST
  /api/v1/{resource}/{id}/transitions/` (role / `change_reason` / signature
  gates enforced by the WorkflowEngine), not through `DELETE`.
* A `DELETE` is still a valid API/MCP call and behaves exactly as before — the
  visibility change is purely client-side.
* List visibility is uniform across artifact types: `?include_deleted=true`
  reveals outdated rows, and every artifact list offers the same opt-in toggle
  plus an "outdated" row badge.

---

## 11. Suggestion inbox — agent-keyed writes, `409 PRODUCER_CONTEXT_REQUIRED`

The suggestion inbox (`GET /api/v1/suggestions/`, accepted/rejected via
`POST /api/v1/suggestions/{id}/accept/` / `.../reject/`) is the human-readable
side of the ADR-019 loop. In the UI it is the **"Suggestions" mode of
`ReviewsView`** — there is no second page or route. Two facts a client (and a
human reviewer) has to know:

* **Suggestions are produced by an agent, never by the human UI.** Producing a
  proposal requires an **agent-typed API key** (an `reqlo_*` key with an agent
  principal); a human bearer token or session is refused **fail-closed** with
  `409 PRODUCER_CONTEXT_REQUIRED`. That is by design (Zusage 7(f)): an
  unstamped, unreviewed proposal must never be attributed to a person. The MCP
  side raises the same error (`suggestion` tool group), so the guarantee is
  transport-independent.
* **The inbox is already reachable** — it is the mode toggle on the review
  surface (`reviews-suggestions-mode-toggle`), with an accompanying hint that
  names the agent path. An **empty inbox is expected** on a workspace that no
  agent has proposed into; it is not a broken feature.

An agent may not accept or reject **its own** proposal: that answers
`403 PERMISSION_DENIED` (`AgentSelfConfirmError`). Accept/reject require the
`WRITE` operation (editor/approver/admin); reading the inbox is `READ`
(viewer included).

