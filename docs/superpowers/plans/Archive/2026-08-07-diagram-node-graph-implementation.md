# Diagram node/edge graph refactor — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Full rationale, alternatives considered, and the answered
> product decisions live in `docs/superpowers/plans/Archive/2026-08-07-diagram-node-graph-refactor-scoping.md`
> (revision 3) — this plan is the executable distillation of that document. Where a task brief
> says "see scoping §X", that section is background/rationale, not a missing spec — every value
> an implementer needs to write code is inlined in the task itself.

**Issue:** Popoboxxo/ReqogniLoom#353 — replace freehand `canvas_stroke` diagram model with a
structured node/edge graph. **Also closes #392** (pre-existing bug: Diagram `documents`
TraceLink creation always raises `SourceNotFoundError`, silently rolled back, masked by mocked
tests) as a side effect of Task 3.

**Goal:** Add `payload_format=node_graph` — a strictly-typed, client-rendered node/edge diagram
format — alongside the existing `canvas_stroke` (kept, narrowed to freehand sketching). Nodes
may reference real artifacts; each reference becomes a dedicated, reconciler-owned TraceLink
type (`DIAGRAM_REF`) that never collides with hand-authored links. Server-side SVG export exists
for `node_graph` only, via a small enum-driven renderer — never for the read path.

**Architecture:** Pure schema module (`backend/diagram/node_graph.py`) wired as a fifth
validator branch; a shadow `Artifact` giving `Diagram` a real traceability anchor; a
desired-state reconciler creating/deleting only `DIAGRAM_REF`-typed links; a small dedicated
SVG renderer for export only; a new `DiagramGraphEditor/` React component tree modelled on
`WorkflowEditor/` (React Flow + dagre, already a dependency) but with positions stored in the
payload, not `localStorage`; a visual/code view toggle; a dry-run-first conversion command from
`canvas_json` (never `strokes`).

**Tech Stack:** No new runtime dependency. Backend: stdlib `json`, existing Django/DRF.
Frontend: `@xyflow/react ^12.11.2`, `@dagrejs/dagre ^3.0.0` (already in `frontend/package.json`).

## Global Constraints

- Every write path (REST, MCP) must canonicalize a `node_graph` payload before persisting:
  `json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)`. Without this,
  `ArtifactDiffService` line-diffs every save as a full rewrite (`artifact_diff_service.py:73,
  :91` treats `payload` as a text field).
- Never tighten `_validate_json` (`backend/diagram/validator.py`) as "cleanup" — `_JSON_REQUIRED_KEYS`
  having no entry for `diagram_type: 'canvas'` is load-bearing: `e2e/tests/canvas-diagram.spec.ts:29`
  passes only because of it.
- Never make `backend/diagram/node_graph.py` import from `rest_api` (or any Ext-layer module).
  It is a pure schema module; `rest_api` imports *it*, never the reverse (the existing
  `_validate_element_field_types` local import of a `rest_api` serializer is an accepted
  exception for the *old* `canvas_stroke` format only — do not repeat that inversion here).
- `DIAGRAM_REF` TraceLinks are reconciler-owned only. The reconciler must filter both `current`
  and `desired` link sets to `link_type=DIAGRAM_REF` before diffing — it must never read, create,
  or delete a `documents` link or any other type on the same Diagram/artifact pair.
- No server-side SVG for `node_graph` on any read path (detail-pane preview, list view). SVG
  exists only behind an explicit `export_format` request. `dangerouslySetInnerHTML` must not
  appear anywhere in `node_graph` frontend code.
- `canvas_stroke` is not deprecated, not removed from the `PayloadFormat` enum, and its validator
  branch is not touched except where a task explicitly says so (Task 1 only).
- Any MCP tool `inputSchema` change requires regenerating `docs/agent-templates/tool-manifest.json`
  (`docker-compose exec backend python manage.py export_tool_manifest`) in the **same task's
  commit** — `backend/mcp_server/tests/test_tool_manifest_drift.py` fails CI otherwise.
- Playwright/E2E specs may be written but must never be executed by an agent in this project —
  hand them to the human to run. Not a task Definition of Done gate.
- `frontend/src/test/ui-ratchet.test.ts` fails if the inline `style={{` count under
  `components/` increases. New components put styling in a CSS module; only genuinely dynamic
  values (e.g. an edge-label transform) become named `CSSProperties` consts — never raise the
  ratchet baseline to pass.
- `frontend/src/test/i18n-parity.test.ts` enforces `de`/`en` key parity. New locale keys must be
  nested objects, not dotted-flat strings (a key literally named `"type.box"` never resolves —
  `keySeparator` is `"."`).
- Backend tests run via
  `docker-compose exec -e DB_USER=reqflow -e DB_PASSWORD=110d00b8a6d252019093c264e4ef4571 backend python -m pytest <path> -v --create-db`.
  Verify `pip show pytest-django` inside the container shows `4.12.0` before trusting a red
  result — rebuild the image (`docker-compose build backend`) if not.
- Git mutations only via commit at the end of each task, on the branch already checked out by
  the controller — implementers commit their own task's work, never touch branches.

---

## File Structure

```
backend/diagram/
  node_graph.py                    # Task 1 — pure schema module (dataclasses, validate_node_graph)
  node_graph_renderer.py           # Task 5 — export-only SVG renderer
  migrations/0006_add_node_graph_payload_format.py   # Task 1
  migrations/0007_diagram_artifact.py                # Task 3
  models.py                        # Task 1 (enum value), Task 3 (Diagram.artifact FK)
  validator.py                     # Task 1 (5th branch), Task 1 (canonical serialization hook)
  services.py                      # Task 1 (canonical serialize on write), Task 3/4 (shadow artifact + reconciler wiring), Task 7 (conversion command wiring)
  traceability_connector.py        # Task 3 (_resolve_artifact_id), Task 4 (sync_node_links reconciler)
  renderer.py                      # Task 1 (_RENDER_HINTS entry), Task 5 (export_svg dispatch)
  management/commands/convert_canvas_to_node_graph.py   # Task 7
backend/traceability/
  types.py                         # Task 3 (LinkType.DIAGRAM_REF)
backend/rest_api/
  serializers_diagram.py           # Task 1 (doc-only NodeGraphPayloadSerializer)
backend/mcp_server/tools/
  diagram.py                       # Task 2 (enum inputSchema, export_format param), Task 4 (artifact_ref error mapping)
  mcp_artifact_provider.py         # Task 2 (node/edge summary rendering)
frontend/src/components/DiagramGraphEditor/
  DiagramGraphEditorPage.tsx       # Task 6
  GraphCanvas.tsx                  # Task 6
  GraphNode.tsx                    # Task 6
  GraphEdge.tsx                    # Task 6
  graph-layout.ts                  # Task 6
  GraphInspectorPanel.tsx          # Task 6
  GraphToolbar.tsx                 # Task 6
  useGraphPayload.ts               # Task 6
  DiagramGraphEditor.module.css    # Task 6
  index.ts                         # Task 6
frontend/src/components/DiagramView/
  DiagramDetailView.tsx            # Task 6 (code/visual toggle), Task 8 (read-only preview, create-form default)
  diagram-view-shared.ts           # Task 8 (PAYLOAD_FORMATS, DEFAULT_CONTENT)
frontend/src/types/index.ts        # Task 6 (PayloadFormat union, NodeGraphPayload types)
frontend/src/components/NavigationShell/NavigationShell.tsx   # Task 6 (route)
docs/                              # Task 9 — SE documentation, ADR
```

---

### Task 1: Backend schema, validation, and canonical serialization

**Model:** `sonnet` (standard — multi-file integration, existing patterns to follow exactly).

Add `payload_format=node_graph` as a new, fully independent format. Do not touch `json` or
`canvas_stroke` validator branches.

**1. `backend/diagram/models.py`** — add to `PayloadFormat`:
```python
NODE_GRAPH = "node_graph", "Node Graph (JSON)"
```
(`payload_format` is `max_length=16`; `"node_graph"` is 10 chars, fits.)

**2. Migration** `backend/diagram/migrations/0006_add_node_graph_payload_format.py` — a single
`AlterField` on `DiagramVersion.payload_format`, mirroring migration `0003` exactly (same
`choices` list shape, no data migration, no new column).

**3. `backend/diagram/node_graph.py`** (new, pure module — no DB import, no `rest_api` import):

Envelope:
```json
{
  "schema_version": 1,
  "nodes": [ /* Node */ ],
  "edges": [ /* Edge */ ],
  "viewport": { "x": 0, "y": 0, "zoom": 1 }
}
```
`schema_version` is required and must equal `1`.

Node:
```json
{
  "id": "n-7f3a2c",
  "type": "box",
  "label": "Auth Service",
  "position": { "x": 120, "y": 40 },
  "size": { "width": 180, "height": 64 },
  "style": { "accent": "primary" },
  "artifact_ref": { "entity_type": "ArchitectureElement", "id": "…uuid…" },
  "parent_id": null
}
```
| Field | Required | Domain |
|---|---|---|
| `id` | yes | `^[A-Za-z0-9_-]{1,64}$`, unique within the diagram |
| `type` | yes | enum: `box` \| `rounded` \| `ellipse` \| `diamond` \| `note` \| `group` |
| `label` | yes | string, ≤ 500 chars, may be empty |
| `position` | yes | `{x, y}` finite numbers |
| `size` | no | `{width, height}` finite numbers > 0 |
| `style` | no | object with only `accent` ∈ `default`\|`primary`\|`success`\|`warning`\|`danger`\|`muted` |
| `artifact_ref` | no | `{entity_type, id}` — `entity_type` one of the known artifact type names used elsewhere in this codebase (`Requirement`, `StakeholderNeed`, `ArchitectureElement`, `TestCase`, `Adr`, `Risk`, `Issue`, `GlossaryTerm`, `Goal`, `MainGoal`), `id` a UUID string |
| `parent_id` | no | id of a `group`-type node in the same payload, or `null` |

Edge:
```json
{
  "id": "e-0b91",
  "source": "n-7f3a2c",
  "target": "n-91bc4d",
  "type": "flow",
  "label": "",
  "source_handle": "bottom",
  "target_handle": "top",
  "style": { "line": "solid" }
}
```
| Field | Required | Domain |
|---|---|---|
| `id` | yes | same charset as node ids, unique within the diagram |
| `source`, `target` | yes | must each equal an existing node `id` in the same payload |
| `type` | yes | enum: `flow` \| `association` \| `dependency` \| `containment` |
| `label` | no | string, ≤ 500 chars |
| `source_handle`, `target_handle` | no | enum: `top`\|`right`\|`bottom`\|`left`, or `null` |
| `style` | no | object with only `line` ∈ `solid`\|`dashed` |

Invariants to enforce in `validate_node_graph(data: dict) -> ValidationResult`:
1. Every `edge.source`/`edge.target` names a node `id` present in `nodes`.
2. Every `node.parent_id` names a node whose `type == "group"`.
3. Caps: ≤ 500 nodes, ≤ 1000 edges, labels ≤ 500 chars, ids ≤ 64 chars, total serialized payload
   ≤ 1 MB (mirror `CANVAS_MAX_ELEMENTS` / `_MAX_MERMAID_SOURCE_SIZE` conventions already in
   `validator.py`).
4. `artifact_ref.entity_type`, when present, must be one of the known types listed above;
   `artifact_ref.id` must parse as a UUID (do not resolve/verify existence here — that happens
   in Task 3's reconciler, at write time, inside the transaction).
5. Reuse the frozen `ValidationResult` dataclass already defined in `validator.py` (`is_valid`,
   `error_msg`, `line_number`, `diagram_type`) as the return type — no new error-surfacing
   plumbing.

Export a small extraction helper, e.g. `extract_artifact_refs(payload: dict) -> list[tuple[str, dict]]`
returning `(node_id, artifact_ref)` pairs for every node with a populated `artifact_ref` — Task 3's
reconciler and Task 7's conversion command both need this and must not duplicate the walk.

**4. `backend/diagram/validator.py`** — wire `node_graph.validate_node_graph` as a fifth branch
in `DiagramValidator.validate_payload` (alongside the existing `_validate_mermaid` /
`_validate_plantuml` / `_validate_json` / `_validate_canvas_strokes`), routed on
`payload_format == PayloadFormat.NODE_GRAPH`.

**5. `backend/diagram/renderer.py`** — add `(t, PayloadFormat.NODE_GRAPH) → "react-flow"` to
`_RENDER_HINTS` for every `DiagramType`. Unmapped combinations already fall back to `"unknown"`
without raising — additive only.

**6. `backend/diagram/services.py`** — on the write path (wherever `create_diagram`/
`update_diagram`/`canvas_auto_save` currently persist `payload`), when `payload_format ==
NODE_GRAPH`, canonicalize before writing:
`json.dumps(json.loads(payload), ensure_ascii=False, sort_keys=True, indent=2)` (validate first,
canonicalize second — canonicalizing invalid JSON is undefined). This must run for both REST and
MCP write paths — put it in the shared service function both call, not duplicated in each
transport layer.

**7. `backend/rest_api/serializers_diagram.py`** — add `NodeGraphPayloadSerializer` for
drf-spectacular documentation only, importing its enums/shapes from `diagram/node_graph.py` —
must not become a second source of truth for the schema.

**Tests:** validator unit tests — happy path, each invariant violated individually (dangling edge
endpoint, unknown node type, non-group `parent_id` target, over-cap payload, bad
`artifact_ref.entity_type`, non-UUID `artifact_ref.id`), REST create/update round-trip via
`payload_format=node_graph`, canonical-serialization test (two semantically-identical but
differently-key-ordered payloads produce byte-identical stored `payload` and an empty `diff/`
between consecutive saves).

**Done when:** `POST /api/v1/diagrams/` with `payload_format=node_graph` accepts a valid graph;
rejects a dangling edge endpoint / unknown node type / over-cap payload with
`400 VALIDATION_ERROR`; two consecutive identical-content saves produce an empty `diff/`.

**Must not break:** `_validate_json`, `_validate_canvas_strokes` — leave both byte-for-byte
untouched. `e2e/tests/canvas-diagram.spec.ts` and `e2e/tests/diagram-api.spec.ts` fixtures must
keep passing conceptually (do not run E2E — reason about the fixture shapes against the
untouched `json`/`canvas` validator paths).

---

### Task 2: Fix the pre-existing canvas_json-vs-strokes preview defect

**Model:** `sonnet` (standard — root cause already diagnosed, needs careful verification against
real Fabric.js output shapes).

Independent bug, unrelated to `node_graph`, found during scoping (scoping doc finding F2). Fix
it now, separately, so the new format isn't shipped next to a broken old one.

**Root cause:** `frontend/src/components/canvas/canvas-geometry.ts::extractStrokeData` maps
**every** Fabric.js object to `{type: "pen", …}` and only populates `points` when
`o.type === "path"` — rects, ellipses, textboxes and connector lines all serialize into the
`strokes` array as `{type: "pen", points: []}`. But `backend/diagram/canvas_editor.py`'s
`get_canvas()`/`_generate_svg()` builds the read-only preview SVG from `json.loads(version.payload)`
— i.e. from the lossy `strokes` array — **not** from `canvas_json` (the Fabric `toJSON(["data"])`
output at `frontend/src/components/canvas/CanvasEditor.tsx:389`, which has full fidelity: every
rect/ellipse/textbox/connector is tagged with `data: {id, type, fromId, toId, ...}`, see
`CanvasEditor.tsx:523,538,581,602,773`). Result: the PR #350 preview renders only genuine
free-hand pen strokes; every shape, text box, and connector is invisible.

**Fix:** Make `CanvasEditor.get_canvas()`/`_generate_svg()` (or whatever the SVG-building entry
point is named in `backend/diagram/canvas_editor.py`) read from `canvas_json`, not `strokes`,
when `canvas_json` is present and non-empty on the `DiagramVersion` — building the SVG from the
same rect/ellipse/textbox/connector/label/arrowHead tagged objects the Fabric editor already
saves. Fall back to `strokes` only for pre-existing rows that have `canvas_json=null` (freehand-only
drawings created before this fix, or genuinely freehand-only sessions that never touch shape
tools). Preserve every numeric-coercion/escaping hardening from the PR #351 XSS fix — this is a
*source* change (which array to read), not a rendering-safety change; do not weaken any
sanitization already in place.

**Tests:** a fixture `canvas_json` containing a rect, a textbox, and a connector between them
produces an SVG containing all three shapes (not just an empty `<path d=""/>`); a
`canvas_json=null` row still renders from `strokes` as before; PR #351's adversarial XSS test
cases (hostile numeric fields) still pass unchanged against the new code path.

**Done when:** a canvas diagram containing a rect, a text box, and a connector produces a preview
SVG showing all three — or, if full fidelity isn't achievable for some element type, an explicit
"preview unavailable for this element" fallback (never a silently empty shape).

**Must not break:** PR #351's XSS hardening. Any element attribute reaching the SVG string must
go through the same coercion/escaping already in place, regardless of which source array feeds
it.

---

### Task 3: Diagram gets a real shadow Artifact (closes #392) + `LinkType.DIAGRAM_REF`

**Model:** `sonnet` (standard — touches persistence + traceability, needs care, but the mechanism
is fully specified below).

This is the root-cause fix behind **two** things at once: the pre-existing bug where
`TraceLinkManager.create` always raises `SourceNotFoundError` for a Diagram (filed separately as
GitHub #392 — `Diagram` is deliberately not an `Artifact` subclass today, see
`backend/traceability/traceability_connector.py:18-27`), and the new capability this refactor
needs (a node's `artifact_ref` becoming a real trace link).

**1. `backend/persistence/models.py`** — add to `Diagram`:
```python
artifact = models.OneToOneField(
    "persistence.Artifact",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="diagram",
)
```
Nullable, lazily created (not backfilled for existing rows in this task — see Task 3 step 3).

**2. Migration** `backend/diagram/migrations/0007_diagram_artifact.py` (or under
`backend/persistence/migrations/` if that's where `Diagram`'s own migrations live in this repo —
confirm by checking where the `Diagram` model's app_label resolves) — adds the nullable FK
column only. No backfill, no data migration.

**3. `backend/diagram/traceability_connector.py`** — add `_resolve_artifact_id(diagram) -> UUID`:
if `diagram.artifact_id` is set, return it; otherwise, inside the same transaction as the caller
(never open a new one — this must be atomic with whatever write triggered it), lazily create an
`Artifact(artifact_type="Diagram", tenant=diagram.tenant, ...)` row, set `diagram.artifact = <new
artifact>`, save, and return the new id. This single lazy-creation path is what both the old
`documents`-link path (#392) and the new `DIAGRAM_REF` reconciler (Task 4) call — one fix, two
consumers.

**4. `backend/traceability/types.py`** — add to `LinkType`:
```python
DIAGRAM_REF = "diagram-ref"
```
placed after `DECOMPOSES` (the current last entry), following the existing kebab-case string
convention. Add a one-line comment above it: `# Reconciler-owned only (Codeberg #353) — never
hand-authored, never touched by manual trace-link CRUD.`

**5. Fix #392 itself**: wherever the existing whole-diagram `documents`-link creation currently
calls `Artifact.unscoped.get(pk=source_id)` and gets a Diagram's raw UUID (causing the
`SourceNotFoundError`), route it through the new `_resolve_artifact_id` instead, so it resolves
to the shadow Artifact's real id.

**Tests:** a DB-backed test (not mocking `create_trace_link`) proving MCP `diagram.create` with
`target_id` set actually persists a `documents` TraceLink end-to-end (this is the regression test
for #392 — the existing four tests all mock the failure away; write one that does not); a test
proving `_resolve_artifact_id` is idempotent (second call on the same Diagram returns the same
artifact id, does not create a second shadow Artifact); a test proving the lazy creation
participates in the caller's transaction (a rollback of the outer operation also rolls back the
shadow Artifact creation).

**Done when:** MCP `diagram.create` with `target_id` set creates a real, persisted `documents`
TraceLink (closing #392); `LinkType.DIAGRAM_REF` exists and is importable; `_resolve_artifact_id`
is idempotent and transaction-safe.

**Must not break:** any existing test relying on `Diagram` NOT being a full `Artifact` subclass
(it still isn't — this is a nullable side-channel FK, not an inheritance change). RLS on the new
`Diagram.artifact` FK — no new table, no new RLS policy needed since it's a column on the
existing `Diagram` table pointing at the existing `Artifact` table.

---

### Task 4: Per-node trace-link reconciler

**Model:** `sonnet` (standard — desired-state diffing logic, needs correctness care and thorough
idempotency tests).

Depends on Task 1 (schema, `extract_artifact_refs`) and Task 3 (`_resolve_artifact_id`,
`LinkType.DIAGRAM_REF`).

**1. `backend/diagram/traceability_connector.py`** — add `sync_node_links(diagram, node_graph_payload)`:
1. Resolve `diagram_artifact_id = _resolve_artifact_id(diagram)` (Task 3).
2. `desired = extract_artifact_refs(node_graph_payload)` (Task 1) → dedupe to the distinct set
   of `(entity_type, id)` targets referenced (multiple nodes may reference the same artifact —
   that's one link, not N).
3. Resolve each `(entity_type, id)` in `desired` to a real target `Artifact` id. If a reference
   names an artifact that does not exist, belongs to a different tenant, or is soft-deleted —
   **abort the whole save** with a `400 VALIDATION_ERROR` naming the offending node id (do not
   silently drop it, do not partially apply the rest). This is a stricter contract than a normal
   trace-link create because it's implicit, not an explicit user action on one link.
4. `current = TraceLink.objects.filter(source=diagram_artifact_id, link_type=LinkType.DIAGRAM_REF)`
   **only** — this filter is the entire safety mechanism; it must never omit `link_type=DIAGRAM_REF`.
5. Diff: create `desired - current`, delete `current - desired`, leave the intersection alone.
   Wrap in the same `@atomic_transaction` as the diagram save itself (same commit or nothing).

**2. Wire it** into `backend/diagram/manager.py` (or wherever `create_diagram`/`update_diagram`/
`canvas_auto_save` currently call the validator) — after successful validation of a
`node_graph` payload, before the response is returned, call `sync_node_links`.

**3. `backend/rest_api/diagram_views.py`** and **`backend/mcp_server/tools/diagram.py`** — catch
whatever exception `sync_node_links` raises for an unresolvable/cross-tenant `artifact_ref` and
map it to `400 VALIDATION_ERROR` (REST) / the equivalent MCP error envelope, with a message
naming the node id (per step 3 above).

**Tests (must not mock `create_trace_link` / `TraceLink.objects`):** saving a graph with two
nodes referencing the same artifact creates exactly one `DIAGRAM_REF` link; re-saving the
identical graph is a no-op (no new rows, no deleted rows); clearing a node's `artifact_ref` and
re-saving removes its link; a node referencing a nonexistent/cross-tenant artifact aborts the
save with `400` and creates zero links; a **pre-existing `documents` link** on the same Diagram/
artifact pair survives an unrelated `node_graph` save completely untouched (this is the test
that proves the `link_type=DIAGRAM_REF` filter actually protects hand-authored links — it is the
single most important test in this task).

**Done when:** saving a graph creates one `DIAGRAM_REF` link per distinct `artifact_ref`;
re-saving is idempotent; clearing a ref removes its link; unresolvable refs abort the save
naming the node; a `documents` link on the same pair is never touched.

**Must not break:** Task 3's #392 fix — a `documents` link created via the old `target_id` path
must remain fully independent of anything this task's reconciler does.

---

### Task 5: MCP surface — enum payload_format, artifact summary, SVG export

**Model:** `haiku` (mechanical — schema edits, manifest regen, templated summary rendering; low
design judgment required once Tasks 1-4 exist).

**1. `backend/mcp_server/tools/diagram.py`** — convert the `payload_format` parameter description
on both `create` and `update` from free prose (`"One of 'mermaid' | 'plantuml' | 'json' |
'canvas_stroke'."`) to a real JSON-Schema `enum` including `node_graph`. MCP access to
`node_graph`/`json` is unrestricted (create/update both, no UI-only limitation applies to MCP —
that's a frontend-only decision, Task 8).

**2. `backend/mcp_server/mcp_artifact_provider.py`** — when rendering a `node_graph` diagram to
Markdown for `artifact.get`, replace the raw JSON dump with a readable summary table: node id,
type, label, artifact_ref (if any); edge id, source→target, type, label. This is the concrete
answer to the issue's "nothing to query" complaint.

**3. Regenerate the manifest** in this task's own commit:
`docker-compose exec backend python manage.py export_tool_manifest`, then run
`backend/mcp_server/tests/test_tool_manifest_drift.py` to confirm it's green.

**Tests:** an MCP schema test asserting `payload_format` is a JSON-Schema `enum` (not free text)
containing `node_graph`; a test that `artifact.get` on a `node_graph` diagram returns a
node/edge table, not raw JSON.

**Done when:** `test_tool_manifest_drift` passes; `artifact.get` on a `node_graph` diagram
returns a readable summary.

---

### Task 6: Server-side SVG renderer + export

**Model:** `sonnet` (standard — security-relevant: every attribute must be traced to a safe
source; needs adversarial test authorship, not just happy-path).

Depends on Task 1 (schema/enums). Independent of Tasks 3-5.

**1. `backend/diagram/node_graph_renderer.py`** (new) — `render_svg(payload: dict) -> str`.
Assumes `payload` has already passed `node_graph.validate_node_graph` (Task 1) — this renderer
does not re-validate, it trusts the caller ran validation first, and its own tests must include
a case proving it raises rather than silently rendering unvalidated input.

Safety design (must be followed exactly, this is the security-critical part):
- `style.accent` and `style.line` are **enums** — map each to a fixed SVG attribute string via a
  literal Python dict (`{"primary": "#...", "default": "#...", ...}`), never string-interpolate
  the enum value itself into an attribute.
- `position`/`size`/`viewport.zoom` are the only numeric fields; route every one through a single
  `_num_attr(value: float) -> str` coercion helper that rejects non-finite values (`nan`, `inf`)
  and formats with a fixed precision — never `str(value)` directly into markup.
- `label` (the only free-text field reaching the renderer) is emitted **only** as the text content
  of an SVG `<text>` element, XML-escaped, **never** as an attribute value and never
  string-interpolated into a `style=` or `d=` attribute.
- Unknown `node.type` / `edge.type` values (should be unreachable post-validation, but defend
  anyway) raise, they do not fall through to a default shape silently.

**2. `backend/diagram/renderer.py`** — add an `export_svg` dispatch: when called for a
`node_graph` diagram, call `node_graph_renderer.render_svg`. The existing `export_svg`/`export_png`
`NotImplementedError` stubs (per scoping doc §3.4) stay stubs for every other format — this task
only implements the `node_graph` case. **PNG stays out of scope** — `reportlab` (already in
`requirements.txt`) cannot parse SVG, and no PNG rasterization dependency is being added in this
plan; if PNG is wanted later it is a separate, explicitly-scoped follow-up.

**3. `backend/mcp_server/tools/diagram.py`** — add an `export_format` parameter to `diagram.get`
(values: `null` (default, returns canonical JSON as today) | `"svg"`). When `export_format="svg"`
on a `node_graph` diagram, call the renderer and return the SVG string. When `export_format="svg"`
on any *other* format (Mermaid, PlantUML, canvas_stroke, json), return `400 VALIDATION_ERROR` —
do not attempt to render, do not 500. Regenerate `tool-manifest.json` in this task's commit
(same drift-guard requirement as Task 5).

**Tests (adversarial, not just happy-path):** a hostile `accent` value that isn't in the enum is
rejected before reaching the renderer (defense-in-depth — validator should already reject it,
test that the renderer independently refuses too); a hostile `label` containing `</text><script>`
produces XML-escaped output with zero unescaped `<`/`>`/`&` in the emitted `<text>` content; a
non-finite `position.x` (`NaN`, `Infinity` — reachable only if validation is bypassed, test the
renderer's own defense) raises rather than emitting `NaN` into an SVG attribute; a golden-file
test comparing a known-good payload's rendered SVG against a checked-in expected string; the SVG
output is well-formed XML (parseable) for every node type and every edge type at least once.

**Done when:** `diagram.get(id, export_format="svg")` on a `node_graph` diagram returns
well-formed SVG containing no attacker-controlled attribute bytes; the same call on a Mermaid
diagram returns `400 VALIDATION_ERROR`, not a 500.

**Must not break:** `export_png` stays a documented `NotImplementedError` stub for all formats
including `node_graph`.

---

### Task 7: Conversion command (`canvas_json` → `node_graph`)

**Model:** `sonnet` (standard — mapping logic with a refusal path, needs care around silent data
loss).

Depends on Tasks 1 and 4 (writes must route through validation + the reconciler, not hand-rolled
`DiagramVersion` construction).

**1. `backend/diagram/management/commands/convert_canvas_to_node_graph.py`** (new Django
management command):
```
python manage.py convert_canvas_to_node_graph  (--diagram <uuid> | --workspace <uuid>)  [--apply]
```
- Reads `DiagramVersion.canvas_json` of the **current** version of each targeted `canvas_stroke`
  diagram (never the lossy `strokes` array — see Task 2's F2 finding for why).
- Mapping: `data.type in {"rect","circle"}` → a `node_graph` node (position from Fabric's
  `left`/`top`, size from `width * scaleX` / `height * scaleY`); `data.type == "label"` folds its
  text into the node named by `data.labelFor`'s `label` field; a standalone `data.type == "text"`
  (no `labelFor`) becomes a `note`-type node; `data.type == "connector"` → an edge with
  `source = data.fromId`, `target = data.toId`; `arrowHead` and any connector-preview helper
  objects are skipped (derived render artifacts, not semantic content).
- **Refuses to convert** (reports, does not partially convert) any diagram whose `canvas_json`
  contains a genuine free-hand `path`-type object — those have no graph equivalent, and dropping
  them silently would be data loss. Report which diagrams were skipped and why.
- Writes the result as a **new `DiagramVersion`** via the same service-layer write path Task 1/4
  use (i.e. goes through `node_graph.validate_node_graph` and Task 4's `sync_node_links`, not a
  hand-constructed `DiagramVersion.objects.create(...)`), never mutating or deleting the source
  `canvas_stroke` version — the model is append-only, the pre-conversion version stays intact.
- **Dry-run by default.** Without `--apply`, print a per-diagram report (convertible / not
  convertible / reason) and write nothing. `--apply` is required to persist.

**Tests:** a fixture `canvas_json` with rects + a connector converts correctly (assert the
resulting `node_graph` payload's nodes/edges); a fixture containing a free-hand `path` object is
refused (dry run reports it, `--apply` writes nothing for that diagram, other diagrams in the
same `--workspace` run still convert); dry-run mode never writes to the DB (assert row count
unchanged); a converted diagram whose nodes carry `artifact_ref` values correctly triggers Task
4's reconciler (the new version has `DIAGRAM_REF` links, proving the command didn't bypass the
service-layer write path).

**Done when:** a dry run over a workspace prints a per-diagram convertible/not-convertible
report; `--apply` produces new `DiagramVersion` rows without mutating or deleting old ones; a
free-hand-containing diagram is refused, not partially converted.

---

### Task 8: Frontend editor — `DiagramGraphEditor/` component tree

**Model:** `sonnet` (standard — the React Flow/dagre wiring is a well-understood copy of
`WorkflowEditor/`, but the inspector panel, artifact-ref picker, and payload (de)serialization
are genuinely new).

Depends on Task 1 (backend schema shape must match exactly) and, for the artifact-ref picker, on
knowing the known artifact-type list from Task 1.

Build `frontend/src/components/DiagramGraphEditor/`, mirroring `frontend/src/components/WorkflowEditor/`'s
file split and copying (not abstracting into a shared library — see rationale below) these
specific patterns:
- module-scope `NODE_TYPES`/`EDGE_TYPES` consts (not recreated per render — React Flow warns
  otherwise), following `WorkflowCanvas.tsx:41-42`'s pattern.
- the dagre centre→top-left position correction and self-loop skip from `layout.ts:51-66`.
- the handle-id convention (`top`/`left` = targets, `bottom`/`right` = sources) from
  `StateNode.tsx:81-108`, so layout-emitted `sourceHandle`/`targetHandle` values match.
- `EdgeLabelRenderer` + wide transparent hover path from `TransitionEdge.tsx:63-72`.

**Do not extract a shared `components/shared/flow/` library on this pass** — copying the
patterns is deliberate; a premature abstraction would couple the stable `WorkflowEditor` to a
still-moving new editor.

**Files:**
| File | Modelled on | Notes |
|---|---|---|
| `DiagramGraphEditorPage.tsx` | `WorkflowEditorPage.tsx` | route container, load/save, edit-mode toggle, **and the visual/code view toggle (see below)** |
| `GraphCanvas.tsx` | `WorkflowCanvas.tsx` | viewport, `onConnect`, drag, delete |
| `GraphNode.tsx` | `StateNode.tsx` | 4 handles, `memo`, inline rename on double-click |
| `GraphEdge.tsx` | `TransitionEdge.tsx` | bezier + label pill + hover path |
| `graph-layout.ts` | `layout.ts` | dagre; keep the centre→top-left correction |
| `GraphInspectorPanel.tsx` | `InspectorPanel.tsx` | node/edge properties + `artifact_ref` picker (search/select against the known artifact types from Task 1's table) |
| `GraphToolbar.tsx` | `CanvasToolbar.tsx` | add node, auto-layout (explicit button, see divergence below), fit view, zoom |
| `useGraphPayload.ts` | `useWorkflowData.ts` + `useWorkflowMutations.ts` | TanStack Query against `diagramsApi`, canonical (de)serialization matching Task 1's schema exactly |
| `DiagramGraphEditor.module.css` | `WorkflowEditor.module.css` | mind the ui-ratchet gate (Global Constraints) |
| `index.ts` | `index.ts` | named exports only |

**The one deliberate structural divergence from `WorkflowEditor`:** positions round-trip through
the saved payload, **not** `localStorage`. There is no `layout-store.ts` equivalent. Auto-layout
is an explicit toolbar button, never applied automatically on load — re-flowing a hand-arranged
diagram every time someone opens it would destroy the arrangement two collaborators expect to
see identically. Getting this backwards (copying `WorkflowEditor`'s "always dagre on load,
positions in localStorage" behavior) is the most likely way to over-copy the reference pattern —
call this out explicitly in the implementer's self-review.

**Code-view toggle (new frontend requirement, decided during scoping):** the editor defaults to
the visual React Flow canvas, with an explicit toggle to a read-only **Code view** showing the
current in-editor payload as formatted JSON. Reuse whatever code-viewing pattern
`DiagramDetailView.tsx` already has for the Mermaid source view (find and reuse its component/
pattern rather than inventing a new one) — the toggle should feel identical across formats.
Toggling to Code shows the live in-editor state (not a stale server copy); toggling back to
Visual must not lose any in-progress edit.

**Routing:** add `<Route path="/diagrams/:id/graph" element={<DiagramGraphEditorWrapper />} />`
in `frontend/src/components/NavigationShell/NavigationShell.tsx`, alongside the existing
`canvas`/`mermaid` fullscreen routes.

**Types:** `frontend/src/types/index.ts` — `PayloadFormat` union `+= "node_graph"`; add
`NodeGraphPayload` / `GraphNode` / `GraphEdge` interfaces mirroring Task 1's schema exactly
(field names, enum values — any drift here is a silent contract break with the backend).

**i18n:** new keys under a nested `diagramGraph` (or similar) namespace in both `de` and `en`
locale files — never a dotted-flat key (Global Constraints). `data-testid` on every interactive
element (project convention).

**Tests:** `vitest` for `graph-layout.ts` (dagre wiring, centre-correction, self-loop skip),
payload (de)serialization round-trip against Task 1's exact schema, and the inspector panel's
artifact-ref picker. A `diagram-node-graph.spec.ts` E2E spec should be **written** (create, lay
out, edit, save, reload with positions intact; toggle to Code and back) but **not executed** by
the implementer — hand it to the human per Global Constraints.

**Done when:** a diagram can be created, laid out, edited, saved and reloaded with positions
intact, verified in a real browser at more than one viewport by the implementer (manual browser
check, not Playwright); toggling to Code view shows the current payload and toggling back loses
nothing.

**Must not break:** `ui-ratchet.test.ts`, `i18n-parity.test.ts`.

---

### Task 9: Read path, defaults, and detail-pane integration

**Model:** `haiku` (mechanical — wires an already-built editor into already-existing detail/list
views; no new design judgment).

Depends on Task 8 (the editor must exist).

**1. `frontend/src/components/DiagramView/DiagramDetailView.tsx`** — the existing
`isCanvas`/`canRenderVisual` ternary/pair becomes a `payload_format → {previewKind, editorRoute}`
map with a `node_graph` entry pointing at the new `/diagrams/:id/graph` route. The read-only
preview is the same React Flow canvas from Task 8 with `nodesDraggable={false}`,
`nodesConnectable={false}`, `elementsSelectable={false}` — confirm zero `dangerouslySetInnerHTML`
on this path (Global Constraints).

**2. `frontend/src/components/DiagramView/diagram-view-shared.ts`** — `PAYLOAD_FORMATS +=
"node_graph"`; add `DEFAULT_CONTENT.node_graph` = a canonical two-node starter graph matching
Task 1's schema exactly.

**3. Create form** — `node_graph` becomes the offered "structured" option, **displacing `json`
from the create form's list** (not from the enum — `json` stays fully valid via REST/MCP per
Global Constraints and Task 5, this is a UI-only change). `canvas_stroke` stays offered,
re-labeled/re-framed in the UI copy as the freehand-sketch option (not the general-purpose
default).

**Tests:** a component test that selecting `node_graph` in the create form produces the correct
default payload; a component test that `DiagramDetailView` renders the read-only React Flow
preview (not raw JSON, not an SVG `<img>`) for a `node_graph` diagram.

**Done when:** no `node_graph` code path in the browser touches `dangerouslySetInnerHTML`; the
create form offers `node_graph` and no longer offers `json`; MCP/REST access to `json` is
unaffected.

---

### Task 10: SE documentation

**Model:** `haiku` (mechanical — documentation following an established template, delegate to
the `documenter` convention already used in this project rather than a generic implementer if
that fits better; otherwise a cheap model is sufficient since no code judgment is required).

Depends on all prior tasks being complete (documents what was actually built, not what was
planned).

- New REQ ids for the `node_graph` payload format and the `DIAGRAM_REF` link type, following this
  repo's `REQ-Lx-*` numbering convention (check `docs/se/L1/` or wherever the traceability
  register for this ARCH-L1 system lives for the next free id).
- Interface-registry entries for the new `context`-adjacent surfaces this task touches (the
  `DIAGRAM_REF` link type addition to `SE_LINK_SEMANTICS` if that matrix needs updating for the
  new type — check whether `SE_LINK_SEMANTICS`/coverage calculator/link-type filters need
  `DIAGRAM_REF` added to their enumeration, per the scoping doc's noted follow-up).
- An ADR recording two decisions: (a) no server-side SVG rendering for the `node_graph` read
  path, only for explicit export (Task 6); (b) positions stored in the payload rather than
  `localStorage`, diverging deliberately from `WorkflowEditor`'s pattern (Task 8).

**Done when:** the ADR exists and is linked from both `backend/diagram/node_graph.py`'s module
docstring and the `DiagramGraphEditor/` README/index comment; `SE_LINK_SEMANTICS` (or wherever
the 14 (now 15) link types are enumerated for SE-mode endpoint validation) includes
`DIAGRAM_REF` or explicitly documents why it's intentionally excluded from SE endpoint semantics
(it's reconciler-owned, not a human SE-discipline link — this is likely an intentional exclusion,
but it must be a documented decision, not a silent gap).
