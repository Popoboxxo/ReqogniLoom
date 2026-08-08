# Diagram node/edge graph refactor — scoping and design

> **Status: SCOPING ONLY — not an implementation plan.** No code was written, no branch
> was created, no tests were run.
>
> **Revision 3 — 2026-08-07.** All eight decisions in §9 are now resolved (§9.1-§9.4 from
> revision 2; §9.8 — the reconciler-provenance question raised by the investigation behind
> decision 1 — resolved as **(c) a dedicated `LinkType.DIAGRAM_REF`**, exclusively
> reconciler-owned, never touching hand-authored links). §9.5, §9.6, §9.7 remain open but are
> explicitly non-blocking (see each entry). §5.1.1's `skip_link_sync` question is resolved as
> "not needed" — a consequence of §9.8's answer.
>
> **No decision still blocks implementation start.** §9.5-§9.7 can be answered during
> implementation without changing what has already been designed. This document should now be
> turned into a task-by-task plan in the style of
> `docs/superpowers/plans/2026-08-05-mcp-plugin-distribution.md`.

**Issue:** Popoboxxo/ReqogniLoom#353 — *refactor: replace freehand `canvas_stroke` diagram model with a structured node/edge graph*
**Date:** 2026-08-07 (rev 2)
**Related:** PR #350 (Diagrams D4 preview), PR #351 (stored-XSS hotfix), GH-352 (canvas_stroke type-validation gap — **already closed**, see F0)

**Goal:** Give the general-purpose Diagrams feature a data model that is a *graph* rather than
a *picture* — typed nodes and edges with stable ids, queryable structure, meaningful
versioning, **real trace links from nodes to artifacts**, and client-side rendering on the
read path.

**Architecture:** A new `payload_format=node_graph` alongside the existing four. The schema
lives in a new pure module `backend/diagram/node_graph.py` (Ext layer, no DB, no `rest_api`
import) and is consumed by `DiagramValidator`, by a documentation-only DRF serializer, and by
the MCP tool schemas. The frontend gets a `DiagramGraphEditor/` component tree modelled on
`frontend/src/components/WorkflowEditor/` — same `@xyflow/react` + `@dagrejs/dagre` stack,
same file split, same handle/edge-label conventions — with one deliberate structural
divergence (§4.3), plus a visual/code view toggle (§4.6).

Two things changed in rev 2 relative to rev 1:

1. Every node with a populated `artifact_ref` now produces a **real `documents` TraceLink**
   between the Diagram and the referenced artifact. This requires the Diagram to become
   something the traceability system can point a foreign key at (§3.7) — and, as it turns out,
   also *fixes a latent runtime bug* (F5).
2. There **is** a server-side SVG renderer for `node_graph`, but only on the *export* path
   (MCP), never on the read path. It is a new, small, enum-driven module — not a revival of
   the `canvas_editor.py` string builder (§3.4).

**Tech stack:** No new runtime dependency on either side. `@xyflow/react ^12.11.2` and
`@dagrejs/dagre ^3.0.0` are already in `frontend/package.json` (added for the Workflow
Editor). Backend is stdlib `json` + existing DRF/Django. **PNG export is explicitly out of
scope for v1** and the reason is a dependency argument, not an oversight — see §3.4.4.

---

## 1. What is actually there today

### 1.1 Inventory

| Layer | File | Role |
|---|---|---|
| Model | `backend/diagram/models.py` | `Diagram` (mutable header) + `DiagramVersion` (append-only). `DiagramType` = 5 values, `PayloadFormat` = 4 values. `payload` is a `TextField`; `canvas_json` is a `JSONField` added in migration 0004. |
| Validation | `backend/diagram/validator.py` (612 LOC) | `validate_payload()` routes on `payload_format` → `_validate_mermaid` / `_validate_plantuml` / `_validate_json` / `_validate_canvas_strokes`. |
| Rendering | `backend/diagram/canvas_editor.py` (510 LOC) | `_element_to_svg()` / `_generate_svg()` — the server-side SVG string builder hardened by PR #351. |
| Render hints | `backend/diagram/renderer.py` | `_RENDER_HINTS[(diagram_type, payload_format)] → "mermaid.js" \| "plantuml-js" \| "custom-json"`. `export_svg` / `export_png` are `NotImplementedError` stubs (`renderer.py:165-192`). |
| Service facade | `backend/diagram/services.py` | Module-level functions (not a service class) — `create_diagram`, `update_diagram`, `canvas_auto_save`, `get_canvas_diagram`, `delete_diagram` (soft, via `workflow.services.outdate`)… |
| Traceability | `backend/diagram/traceability_connector.py` | `TraceabilityConnector.create_document_link(diagram_id, target_id)` → `traceability.services.create_trace_link` with `link_type="documents"`. **Broken at runtime — see F5.** |
| REST | `backend/rest_api/diagram_views.py` | `DiagramViewSet` (CRUD + `versions/` + `diff/` + workflow mixin). |
| REST sub-resources | `backend/rest_api/diagram_canvas_views.py`, `backend/rest_api/serializers_diagram.py` | `canvas-strokes/`, `mermaid-source/`, `mermaid-preview/`. |
| MCP | `backend/mcp_server/tools/diagram.py` | 6 tools: `diagram.create/get/update/query/outdate/reactivate`. `create`/`update` accept an optional `target_id` (`:128`, `:160`). |
| MCP artifact | `backend/diagram/mcp_artifact_provider.py` | Renders a diagram as a Markdown artifact for `artifact.get`. |
| Frontend list/detail | `frontend/src/components/DiagramView/` | `DiagramView`, `DiagramList`, `DiagramCreateForm`, `DiagramDetailView`, `useDiagramData`, `diagram-view-shared`. **Already has a `"code" \| "visual"` view toggle** (`DiagramDetailView.tsx:76`) — see §4.6. |
| Frontend canvas | `frontend/src/components/canvas/CanvasEditor.tsx` (1350+ LOC) + `canvas-geometry.ts` | Fabric.js v6 fullscreen editor at `/diagrams/:id/canvas`. |
| Reference pattern | `frontend/src/components/WorkflowEditor/` (23 files) | React Flow + dagre editor for workflow state machines. |

### 1.2 Findings that shape the recommendation

**F0 — the companion "type-validation gap" issue is already closed.**
`validator.py:446-473` (`_validate_element_field_types`) delegates per-element type checking to
`CanvasStrokeElementSerializer` (`rest_api/serializers_diagram.py:35`), so the generic
`/api/v1/diagrams/` intake path now enforces the same field types as the dedicated
`canvas-strokes/` endpoint. The issue body lists this as still open; it is not. It does not
change the case for the refactor, but it removes urgency: **nothing about `canvas_stroke` is
currently exploitable.** This is a quality/capability refactor, not a security fix.

**F1 — a node/edge format already exists in the enum, with essentially no schema.**
`PayloadFormat.JSON` is already the "structured" option, and the frontend's own default
content for it (`diagram-view-shared.ts:34-44`) is literally
`{"nodes":[{"id","label"}],"edges":[{"from","to"}]}`. Validation is
`_JSON_REQUIRED_KEYS` (`validator.py:121-125`): `block` and `context` require a top-level
`nodes` key, `flow` requires `nodes` + `edges`, and `canvas`/`mermaid` require *nothing*.
There is no per-node or per-edge validation of any kind, and no renderer: `_RENDER_HINTS`
maps it to `"custom-json"` and **nothing in the frontend consumes that hint** — the detail
pane falls through to the raw-source `<textarea>` (`DiagramDetailView.tsx:113-127`).

> The refactor is therefore less "add a new format" than "give the format that already
> exists a real schema and a real renderer."

**F2 — the freehand `strokes` array is already lossy to the point of being decorative, and the PR #350 preview is shipped-broken because of it.**
`canvas-geometry.ts:89-122` (`extractStrokeData`) maps **every** Fabric object to
`{type: "pen", …}` and only populates `points` when `o.type === "path"`. Rects, ellipses,
textboxes and connector lines all serialize as `{type: "pen", points: []}`. The real fidelity
lives entirely in `canvas_json` — `canvas.toJSON(["data"])` at `CanvasEditor.tsx:389`.

Meanwhile `CanvasEditor.get_canvas()` (`canvas_editor.py:479-504`) builds the SVG from
`json.loads(version.payload)` — the `strokes` array — **not** from `canvas_json`. Every shape,
text box and connector therefore renders as `<path d="" stroke=… />`: nothing. The read-only
preview added in PR #350 shows only genuine free-hand pen strokes.

> Two consequences. (a) This is a live defect independent of this refactor and should be
> filed and fixed on its own (§7 Phase 0). (b) The `canvas_stroke` payload has close to zero
> migration value — **the data worth migrating is `canvas_json`, not `strokes`.**

**F3 — `canvas_json` already contains a latent node/edge graph, which makes automated conversion feasible.**
The Fabric editor tags every object it creates, and `toJSON(["data"])` preserves that
allowlist:

| Fabric object | `data` payload | Source |
|---|---|---|
| Rect / Ellipse | `{id, type: "rect" \| "circle"}` | `CanvasEditor.tsx:581` |
| Textbox | `{id, type: "text"}` | `CanvasEditor.tsx:602` |
| Connector line | `{type: "connector", id, fromId, toId}` | `CanvasEditor.tsx:523` |
| Node label | `{type: "label", labelFor}` | `CanvasEditor.tsx:773` |
| Arrowhead | `{type: "arrowHead", connectorId}` | `CanvasEditor.tsx:538` |

`fromId`/`toId` on connectors are exactly the edge endpoints a node/edge model needs. An
automated `canvas_json → node_graph` conversion is genuinely high-fidelity for everything
drawn with the shape/connector/text/label tools. It is impossible **only** for free-hand
`path` objects — which have no graph semantics by definition.

**F4 — the blast radius is small and there is no seed dependency.**
- No management command creates diagrams. `backend/auth_tenancy/management/commands/seed_demo.py`
  contains no diagram code at all; `provision_workflow_definitions.py` mentions `Diagram` only
  as a workflow item type.
- `canvas_stroke` appears in 11 backend files (5 of them tests or migrations) and 5 frontend
  files.
- The E2E suite does **not** exercise `canvas_stroke` through the generic API:
  `e2e/tests/canvas-diagram.spec.ts` creates its fixture with
  `diagram_type: 'canvas', payload_format: 'json'` and a `{objects, background}` body;
  `e2e/tests/diagram-api.spec.ts` uses `payload_format: 'json'` with `{nodes, edges}`.
- The only `canvas_stroke` producer in the wild is the Fabric editor's 5-second auto-save.

> Expected production `canvas_stroke` row count on the dogfooding install: low double digits
> at most, all created by hand. There is no fleet to migrate.

**F5 (new in rev 2) — the existing whole-diagram `documents` TraceLink path does not work at runtime, and no test covers it.**
This is the single most important finding behind decision §9.1, and it changes the framing of
that decision from "new feature" to "new feature *plus* latent bugfix".

`TraceabilityConnector.create_document_link` (`traceability_connector.py:54-84`) passes
`diagram.id` as `source_id` into `traceability.services.create_trace_link`. That delegates to
`TraceLinkManager.create`, which does:

```python
# backend/traceability/trace_link_manager.py:235-238
try:
    source = Artifact.unscoped.get(pk=source_id)
except Artifact.DoesNotExist as exc:
    raise SourceNotFoundError(source_id) from exc
```

`Diagram` extends `TenantScopedModel` directly (`diagram/models.py:63`) and lives in its own
table `diagram_diagram`. A Diagram id is **never** an `Artifact` primary key, and nothing in
the codebase creates an `Artifact` row with `artifact_type="Diagram"` (verified: the only
occurrences of the literal are the diff-service field map, the workflow item type, the audit
`entity_type`, and the SE matrix constant). So:

- `create_document_link` always raises `SourceNotFoundError`;
- `DiagramManager.create_diagram` / `.update_diagram` call it at `manager.py:165` and `:253`
  from inside `@atomic_transaction`, so an MCP `diagram.create` with `target_id` set
  **rolls the whole diagram creation back**;
- the batch path has the identical check at `trace_link_manager.py:340-342`;
- every test mocks it away — `diagram/tests/test_traceability_connector.py` patches
  `diagram.traceability_connector.create_trace_link` in all four of its cases, including the
  one named `TestCreateDocumentLinkWithManagerIntegration`.

The docstring at `traceability_connector.py:18-27` describes a deliberate trade-off — "the
PersistenceLayer's RLS/foreign-key constraints do not enforce referential integrity across
application-layer entities" — that the runtime **does not implement**. `TraceLinkManager` is
stricter than the docstring claims: it performs an explicit existence probe before the FK is
ever exercised. The documented artifact-proxy pattern is therefore not a weaker-integrity
variant of a working thing; it is a thing that has never worked.

Two supporting facts point the same way:

- `traceability/types.py:88,106` already declares `_DIAG = "Diagram"` inside
  `SE_CORE_ARTIFACT_TYPES` and `SE_LINK_SEMANTICS[LinkType.DOCUMENTS] = {(_DIAG, "*")}`.
  The SE endpoint matrix was written expecting an `Artifact` whose `artifact_type` is
  `"Diagram"`. That artifact does not exist yet.
- The four artifact-backed domain entities (`StakeholderNeed`, `Requirement`,
  `ArchitectureElement`, `TestCase` — `persistence/models.py:773, 829, 981, 1303`) all use the
  same `artifact = models.OneToOneField(Artifact, …)` shape. There is an established pattern
  and Diagram simply is not on it.

> Consequence for this refactor: decision §9.1 does not "add traceability to diagrams". It
> **implements** traceability for diagrams for the first time, and per-node references are the
> feature that finally justifies the work. §3.7 is the design.

### 1.3 One more constraint worth naming up front

`ArtifactDiffService._ENTITY_FIELDS["Diagram"] = ["payload_format", "payload", "canvas_json"]`
and `_TEXT_FIELDS` contains `"payload"` (`backend/application/artifact_diff_service.py:73, :91`)
— a JSON payload is **line-diffed**. Whatever the new format is, its persisted serialization
must be canonical (stable key order, stable indentation), or every save produces a
full-payload diff and the `versions/`/`diff/` endpoints become noise. `canvas_stroke` never
had this normalization (`canvas_editor.py:357` does a bare `json.dumps`).

---

## 2. Proposed data model: `payload_format = "node_graph"`

### 2.1 Why a new enum value rather than tightening `json`

Tightening `_validate_json` would retroactively invalidate existing `json` rows — including
the E2E fixture at `canvas-diagram.spec.ts:29`, which passes today only because
`_JSON_REQUIRED_KEYS` has no entry for `diagram_type: 'canvas'`. A new value is additive,
costs one `AlterField` migration with no data step, and lets `json` remain what it has always
been in practice: an untyped escape hatch.

`PayloadFormat.payload_format` is `max_length=16` (`models.py:134`). `"node_graph"` is 10
characters — it fits with headroom. (`"canvas_stroke"` is 13.)

### 2.2 Envelope

```json
{
  "schema_version": 1,
  "nodes": [ /* … */ ],
  "edges": [ /* … */ ],
  "viewport": { "x": 0, "y": 0, "zoom": 1 }
}
```

`schema_version` is required and must be `1`. It exists so a future shape change is a
version bump with a converter, not a guess-the-shape heuristic — the mistake `canvas_stroke`
made by having no version marker at all.

### 2.3 Node

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

| Field | Required | Type / domain |
|---|---|---|
| `id` | yes | string, `^[A-Za-z0-9_-]{1,64}$`, unique within the diagram |
| `type` | yes | enum: `box` \| `rounded` \| `ellipse` \| `diamond` \| `note` \| `group` |
| `label` | yes | string, ≤ 500 chars (may be empty) |
| `position` | yes | `{x, y}` finite numbers |
| `size` | no | `{width, height}` finite numbers > 0; omitted = auto-size |
| `style` | no | object with only `accent` ∈ enum (`default`\|`primary`\|`success`\|`warning`\|`danger`\|`muted`) |
| `artifact_ref` | no | `{entity_type, id}`; `entity_type` ∈ the known artifact types, `id` a UUID |
| `parent_id` | no | id of a `group` node, or `null` |

> **`artifact_ref` is not a UI hint (decision §9.1).** A populated `artifact_ref` has real
> backend consequences: on every write, the set of distinct `artifact_ref` targets in the
> payload is reconciled into `documents` TraceLinks between the Diagram and those artifacts
> (§3.7). Three things follow for the schema itself:
>
> 1. `artifact_ref.id` is validated **structurally** by `node_graph.py` (is it a UUID?) but
>    **existence** is only resolvable with DB access, which the pure schema module must not
>    have. Existence/tenant errors therefore surface from the reconciler in
>    `diagram/traceability_connector.py`, not from `validate_node_graph` — see §3.7.3 for
>    exactly which error the caller gets.
> 2. `entity_type` is advisory metadata for the UI. The authority is the id, resolved through
>    `TraceLinkService._resolve_artifact_id` (`application/trace_link_service.py:77-166`),
>    which probes the eight entity tables in order. A mismatched `entity_type` does not change
>    which link gets created.
> 3. **Edges do not become trace links.** An edge between two artifact-bound nodes stays
>    purely visual. This is a deliberate narrowing of scope: it keeps the mapping
>    payload→links one-directional and total (`node.artifact_ref` → `documents` link, nothing
>    else), which is what makes the reconciler in §3.7.2 provably terminating and idempotent.
>    Deriving typed artifact-to-artifact links from a drawing would additionally require
>    deciding which of the 15 `LinkType`s an `edge.type` maps to, and would let a sketch
>    silently mutate the SE trace graph. Out of scope, deliberately.

### 2.4 Edge

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

| Field | Required | Type / domain |
|---|---|---|
| `id` | yes | same id charset as nodes, unique within the diagram |
| `source`, `target` | yes | must reference an existing node `id` in the same payload |
| `type` | yes | enum: `flow` \| `association` \| `dependency` \| `containment` |
| `label` | no | string, ≤ 500 chars |
| `source_handle`, `target_handle` | no | enum: `top` \| `right` \| `bottom` \| `left` \| `null` |
| `style` | no | object with only `line` ∈ (`solid` \| `dashed`) |

### 2.5 Invariants

1. **No free-form numeric or colour field ever reaches a rendered attribute.**
   `style.accent` and `style.line` are *enums*. On the client they map to CSS custom
   properties from `styles/tokens.css`; on the server (§3.4, export path only) they are used
   **exclusively as dictionary keys into module-level literal tables** — the user-supplied
   string itself is never interpolated into markup. The only numbers in the schema are
   `position`, `size` and `viewport.zoom`, all validated finite and capped before any renderer
   sees them. The `#351` bug class is *structurally absent*: see §8.11 for the exact invariant
   and why enum-keyed lookup is strictly stronger than the `_escape_xml_attr` approach
   `canvas_editor.py:158` still uses for colours.
2. **Referential integrity within the payload.** Every `edge.source`/`edge.target` must name
   a node in the same payload; every `node.parent_id` must name a `group` node. This is an
   invariant `canvas_stroke` connectors never had — `source_id`/`target_id` in
   `CanvasStrokeElementSerializer` are unconstrained `CharField`s.
3. **Caps.** ≤ 500 nodes, ≤ 1000 edges, labels ≤ 500 chars, ids ≤ 64 chars, total payload
   ≤ 1 MB. (Mirrors the existing `CANVAS_MAX_ELEMENTS = 1000` / `_MAX_MERMAID_SOURCE_SIZE = 1 MB`
   conventions in `validator.py`.) **New in rev 2:** additionally cap **distinct
   `artifact_ref` targets per diagram at 100**. Rationale in §8.12 — link creation is O(n)
   full-graph adjacency builds, so an uncapped 500-node graph of distinct refs is a
   self-inflicted transaction stall, not a theoretical concern.
4. **Canonical serialization on write.** `json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)`
   before persisting — see §1.3.

### 2.6 How this differs from the WorkflowEditor schema

`WorkflowEditor`'s model (`frontend/src/components/WorkflowEditor/layout.ts:14-27`) is
`StateNodeData { state: WorkflowState }` / `TransitionEdgeData { transition: WorkflowTransition }` —
a *projection* of a backend-owned state machine, not a stored artifact.

| Concern | WorkflowEditor | node_graph |
|---|---|---|
| Node identity | derived from the state name | client-generated stable id, stored |
| Node types | 4 semantic state types (`initial`/`active`/`terminal`/`error`) | 6 shape types, semantically neutral |
| Edge types | one (`transition`), carrying gate metadata | 4 relationship kinds |
| **Positions** | **not stored** — dagre auto-layout, hand-arrangement persisted to `localStorage` (`layout-store.ts`) | **stored in the payload** — see below |
| Layout on open | always dagre | stored positions; dagre only on explicit "Auto-layout" |
| Artifact linkage | none | `artifact_ref` per node → real `documents` TraceLinks (§3.7) |
| Scope | one graph per (workspace, entity type) | one graph per Diagram, many per workspace |

The positions divergence is the important one and is deliberate.
`layout-store.ts:1-12` explains why the workflow editor keeps positions client-side: the
backend workflow model stores no coordinates because states are plain status strings, and
layout there is a presentation concern over derivable content. **For a general-purpose
diagram the layout *is* the artifact** — two people opening the same architecture sketch must
see the same arrangement, and it must survive a browser change and appear in the version
diff. `localStorage` is the wrong home for it.

---

## 3. Backend changes

> **Read §3.7 first.** It is the largest and riskiest part of the backend work and the only
> part that touches a shared, heavily-used subsystem (`backend/traceability/`,
> `backend/persistence/models.py`). §3.1–§3.6 are local to `backend/diagram/`.

### 3.1 Model + migration

- `backend/diagram/models.py` — add `NODE_GRAPH = "node_graph", "Node Graph (JSON)"` to
  `PayloadFormat`.
- `backend/diagram/migrations/0006_add_node_graph_payload_format.py` — a single `AlterField`
  on `DiagramVersion.payload_format`, mirroring migration `0003` exactly. No data migration,
  no new column. (Latest existing migration is `0005_diagram_workspace_id_…`, so `0006` is
  free.)
- A **second** migration `0007_diagram_artifact.py` adds the shadow-artifact FK — see §3.7.1.
  Keep it separate from `0006`: `0006` is a pure enum widening that can ship and be reverted
  independently, `0007` introduces a cross-app FK to `persistence.Artifact`.

`DiagramType` is **not** extended. A `node_graph` payload is orthogonal to `block`/`flow`/
`context` — see open question §9.5 on whether those types should still mean anything here.

### 3.2 Schema module (new)

`backend/diagram/node_graph.py` — pure, no DB, no `rest_api` import:

- dataclasses / `TypedDict`s for the envelope, node and edge,
- the enum constants (node types, edge types, accents, handles, caps),
- `validate_node_graph(data: dict) -> ValidationResult` returning the same frozen
  `ValidationResult` dataclass `validator.py` already uses (`is_valid`, `error_msg`,
  `line_number`, `diagram_type`), so error surfacing through
  `DiagramValidationError → 400 VALIDATION_ERROR` needs no new plumbing,
- **new in rev 2:** `collect_artifact_refs(data: dict) -> list[UUID]` — the single, pure
  extraction function that both the link reconciler (§3.7) and the conversion command (§5)
  use to derive the desired link set from a payload. Deduplicated, order-stable. Keeping this
  pure and in the schema module is what stops "which nodes count as referencing" from
  becoming a second, divergent definition inside the connector.

Wire `validate_node_graph` as a fifth branch in `DiagramValidator.validate_payload`
(`validator.py:253-275`).

> **DECISION — do not repeat the GH-352 layering shortcut.**
> `_validate_element_field_types` (`validator.py:465`) does a *local* import of a `rest_api`
> serializer from the Ext layer to avoid maintaining two type maps. That inversion was the
> lesser evil for an existing format with an existing serializer. For a new format, put the
> schema in `diagram/node_graph.py` — the layer that owns it — and have `rest_api` import
> *that*. Dependency direction is restored, and there is still exactly one type map.

### 3.3 Render hints

`renderer.py::_RENDER_HINTS` — add `(t, PayloadFormat.NODE_GRAPH) → "react-flow"` for each
`DiagramType` that should accept the format. Unmapped combinations already fall back to
`"unknown"` without raising, so this is additive.

### 3.4 Server-side SVG: export-only, via a dedicated enum-driven renderer

> **Rewritten in rev 2 per decision §9.4c.** Rev 1 said "no server-side SVG at all for this
> format." That stance is **reversed for the export path** and **retained for the read path.**
> The distinction is the whole design, so state it precisely:
>
> - **Read path (browser, detail pane, editor): still zero server SVG.** No
>   `dangerouslySetInnerHTML`, no `sanitizeSvg`, no server round-trip. React Flow renders the
>   same payload the editor writes (§4.4). This is the security win the issue asks for and it
>   is unchanged.
> - **Export path (MCP, and later possibly the PDF report): a new server-side SVG renderer.**
>   An agent calling `diagram.get` cannot run React Flow. Without this it can read the JSON
>   but never *see* the diagram.

#### 3.4.1 What is built

A new module `backend/diagram/node_graph_renderer.py` — small, pure, no DB:

```
render_svg(payload: dict) -> str
```

Explicitly **not** an extension of `canvas_editor.py`. That module's job is freehand strokes
with free-form colours; reusing it would drag its `_escape_xml_attr(element.get("color"))`
model (`canvas_editor.py:158`) into a format that does not need it.

`DiagramRenderer.export_svg` (`renderer.py:181-192`, currently an unconditional
`NotImplementedError`) becomes a dispatcher: `payload_format == "node_graph"` delegates to the
new module; every other format keeps raising `NotImplementedError` with the existing message.
One seam, honest about what it does and does not support.

#### 3.4.2 How the schema's own enums map to SVG, safely

The renderer never interpolates a user-supplied string into an attribute. Every attribute
value is produced one of exactly three ways:

**(a) Enum → module-level literal table.** The user's string is a *lookup key*, never output.

```python
# module-level, server-owned, closed
_ACCENT: dict[str, tuple[str, str]] = {      # accent -> (fill, stroke)
    "default": ("#f4f4f5", "#a1a1aa"),
    "primary": ("#dbeafe", "#3b82f6"),
    "success": ("#dcfce7", "#22c55e"),
    "warning": ("#fef3c7", "#f59e0b"),
    "danger":  ("#fee2e2", "#ef4444"),
    "muted":   ("#fafafa", "#d4d4d8"),
}
_LINE_DASH: dict[str, str | None] = {"solid": None, "dashed": "6 4"}
_SHAPE: dict[str, Callable[..., str]] = {
    "box": _rect, "rounded": _rounded_rect, "ellipse": _ellipse,
    "diamond": _polygon, "note": _note, "group": _group_frame,
}

fill, stroke = _ACCENT.get(style.get("accent", "default"), _ACCENT["default"])
```

An attacker who submits `style.accent = '" onload="alert(1)'` gets `_ACCENT["default"]`,
because the value is a *key miss*, not an escaped string. There is no code path by which that
string appears in the output at all. The same holds for `style.line`, `node.type`, `edge.type`
and the four handle positions.

Note the `.get(…, default)` rather than `[…]`: the validator has already rejected unknown
enum values, so the fallback is unreachable in practice — but a renderer that raises
`KeyError` on a payload persisted before a future enum narrowing is a worse failure mode than
one that draws a grey box.

**(b) Validated number → numeric coercion helper.** `position.x/y`, `size.width/height`,
`viewport.zoom` reach `x=`, `y=`, `width=`, `height=` attributes. By the time the renderer
runs, `validate_node_graph` has already asserted each is a finite number within its cap
(§2.5.3). The renderer nevertheless routes each through the same
`_num_attr(value, default)` helper `canvas_editor.py:117-129` uses — coerce to a finite float,
reject non-numbers to the default, format integrally, XML-escape. **This is deliberate
redundancy**, and the reason is in the helper's own docstring: it exists "so that a future
element type cannot reintroduce the attribute-injection class of bug by forgetting the
coercion step." A node type added in six months by someone who has not read this document
still cannot inject. Import the helper from `canvas_editor` or lift both helpers into a shared
`diagram/_svg_primitives.py`; do not re-implement them.

**(c) Free text → escaped text node, never an attribute.** `node.label` and `edge.label` are
the **only** free-form strings in the schema, and they are the only values that need escaping
at all. Two rules, both load-bearing:

- emit them as the **child text content** of `<text>`, never as an attribute value, and
- XML-escape `& < > " '` on the way out.

No `<foreignObject>`, no embedded HTML, no `<script>`, no `href`, no `style=` attribute
anywhere in the output. This also keeps the output compatible with the frontend's
`sanitizeSvg` DOMPurify configuration, which strips `foreignObject` outright — anything the
renderer emits must survive that filter, or it renders server-side and vanishes client-side.

Labels are already capped at 500 chars, so there is no truncation logic and no size-based
denial-of-service surface beyond the caps in §2.5.3.

#### 3.4.3 Why the validator having run is a real guarantee, not an assumption

The renderer is only reachable from `DiagramRenderer.export_svg`, which is only reachable from
the MCP export handler (§3.6), which loads a persisted `DiagramVersion.payload`. Every path
that writes a `node_graph` payload goes through `DiagramValidator.validate_payload`
(`manager.py` calls it before *both* `create_diagram` and `update_diagram`), which routes to
`validate_node_graph`. There is no unvalidated write path — that is exactly the property
`canvas_stroke` lacked before GH-352 (F0).

**However**, "the validator ran" is a claim about *this* deployment's history, not a type-level
guarantee: rows written before a future schema tightening, or by a data migration, would not
be covered. That is why the renderer re-runs `validate_node_graph` on entry and returns a
minimal "unrenderable payload" placeholder SVG (a bordered rect with an escaped message)
rather than raising or best-efforting. Cost: one pure validation pass over ≤ 1 MB. Benefit:
the safety argument stops depending on a historical claim, and §8.11 becomes checkable in a
single function. **Do not skip this for performance.**

#### 3.4.4 PNG — decision: out of scope for v1, and here is the dependency evidence

**Recommendation: ship SVG only. Do not add a rasterization dependency now.** This is a
decision, not a deferral of the question.

What is actually available today, verified:

| Candidate | Status in this repo | Verdict |
|---|---|---|
| `reportlab>=4.0,<5.0` | **Already in `backend/requirements.txt:43`** (PDF generation, REQ-L2-AS-016) | **Cannot rasterize SVG.** reportlab renders its own `Drawing` object model; it has no SVG parser. Pairing it with SVG requires `svglib` on top. Its `renderPM` rasterizer additionally needs the `_renderPM` C extension. |
| `svglib` | Not present | Pure-Python SVG → reportlab `Drawing`. **No Dockerfile change needed** — this is the cheaper of the two if PNG ever becomes mandatory. Quality is adequate for simple shapes-and-text, which is all `node_graph` emits. |
| `cairosvg` | Not present | Needs `libcairo2` (+ `libpango`) as **system** packages. `backend/Dockerfile` stage 2 is `python:3.12-slim` and installs no graphics libraries at all (only `libpq` for psycopg2). Adding cairo means editing the runtime stage, growing the image, and taking on a native-library CVE surface. |

Against that cost, what does PNG actually buy? The consumers are (a) MCP agents, which handle
SVG text fine and often prefer it — it is smaller and machine-readable; (b) browsers, which
render SVG natively; (c) the traceability PDF report, where `reportlab` would need a
`Drawing`, i.e. `svglib`, i.e. the same decision made later with more information (§9.6).
Nothing in the export need is PNG-specific.

**Concrete recommendation:** implement `render_svg` only. Leave `DiagramRenderer.export_png`
(`renderer.py:165-179`) as the `NotImplementedError` stub it is today, and update its docstring
to name `svglib` as the intended route rather than "headless Chromium + mermaid-cli", which is
wrong for this format. Revisit only if a consumer states a hard PNG requirement.

### 3.5 REST

- `DiagramViewSet.create` / `partial_update` need **no signature change** — both already pass
  `payload_format` + `content` straight through to the service
  (`diagram_views.py:184-193`, `:258-263`), and both already catch `DiagramValidationError`
  and return `400 VALIDATION_ERROR`. They must additionally catch the link-reconciliation
  errors from §3.7.3 and map them to `400`, not `500`.
- **Recommend adding no payload sub-resource endpoint.** `canvas-strokes/` and `mermaid-source/`
  exist because those formats need a side-channel. A `node_graph` payload needs none:
  `retrieve()` already returns `content`, and the client renders it.
- **No REST SVG-export endpoint either.** The export renderer (§3.4) is wired to MCP only.
  The browser has React Flow; giving it a server-rendered SVG would reintroduce exactly the
  `dangerouslySetInnerHTML` + `sanitizeSvg` read path this refactor removes. If a "download as
  SVG" button is ever wanted, the client can serialize its own React Flow viewport — no server
  involvement. **Do not add `GET /diagrams/{id}/svg/`.**
- `serializers_diagram.py` — add a `NodeGraphPayloadSerializer` **for drf-spectacular schema
  documentation only**, importing its enums from `diagram/node_graph.py`. It must not become
  a second source of truth (§3.2).
- The canonical-serialization step (§2.5.4) belongs in `diagram/services.py` on the write
  path, so REST and MCP both get it. This is behaviour `canvas_stroke` does not have — call
  it out in review as an intentional divergence, not an inconsistency.

### 3.6 MCP

**Access is unaffected by the UI decision (decision §9.4a — stated explicitly).** §5.1.1
removes `json` from the *create form*. That is a UI-surface decision only. MCP callers are not
UI: `diagram.create` and `diagram.update` keep **full** access to every value of
`payload_format`, including `json` (unchanged semantics, unchanged `_validate_json`) and the
new `node_graph`. No MCP tool is gated, deprecated or narrowed by this refactor. An agent can
create, read, update and query `node_graph` diagrams without any REST or browser involvement.

Changes:

- **Enum-ify `payload_format`.** `mcp_server/tools/diagram.py:122-124` and `:158` describe it
  as free text (`"One of 'mermaid' | 'plantuml' | 'json' | 'canvas_stroke'."`). Convert both
  to a real JSON-Schema `enum` and add `node_graph`. Agents currently have to guess from prose.
- **Export: extend `diagram.get` with `export_format`, do not add a seventh tool.**

  ```jsonc
  // diagram.get inputSchema, new property
  "export_format": {
      "type": "string",
      "enum": ["source", "svg"],
      "default": "source",
      "description": "'source' returns the raw payload; 'svg' returns a rendered SVG (node_graph only)."
  }
  ```

  Why extend rather than add `diagram.export`: the group's `_TOOL_MAP`
  (`mcp_server/tools/diagram.py:96-103`) is six plain CRUD verbs
  (`create/get/update/query/outdate/reactivate`); a seventh verb that is really "get, but
  rendered" breaks that shape. `diagram.get` already owns version resolution via
  `version_number` — a separate tool would have to duplicate it, and export-of-version-3 is an
  obvious requirement. And practically: one modified `inputSchema` is one manifest
  regeneration, whereas a new tool additionally needs a `_TOOL_MAP` entry, an RBAC
  classification check against `tool_registry._WRITE_TOOL_PREFIXES` (it is a read, so it must
  *not* match), and a new manifest entry.

  Response shape — `_handle_get` (`mcp_server/tools/diagram.py:282-306`) currently returns
  `ToolResult.ok({"diagram": payload})` with `payload["content"]` nested one level down. Add
  a sibling **inside** `diagram`:

  ```json
  { "diagram": { "…": "…", "content": "…", "export": { "format": "svg", "media_type": "image/svg+xml", "data": "<svg …>" } } }
  ```

  **Never introduce a top-level `content` key in a tool result payload** — it collides with
  the MCP envelope's own `content` field. The provider already nests it; keep it nested.

  `export_format: "svg"` on a non-`node_graph` diagram returns
  `ToolResult.error("VALIDATION_ERROR", …)`, mirroring the existing
  "has no workspace assigned" guard style in `_handle_outdate`. It must not 500.

- **"As code" needs no new tool — confirmed.** Raw JSON is already what
  `diagram.get` returns today: `_handle_get` puts `version.payload` into
  `payload["content"]` verbatim (`mcp_server/tools/diagram.py:296-305`), and §2.5.4 guarantees
  that string is canonically formatted JSON. With `export_format` defaulting to `"source"`,
  existing agent behaviour is byte-identical. **Do not add a `diagram.get_source` /
  `diagram.as_code` tool.**
- **CI gate:** `docs/agent-templates/tool-manifest.json` is generated from the live registry
  and guarded by `backend/mcp_server/tests/test_tool_manifest_drift.py`. Any `inputSchema`
  change requires `python manage.py export_tool_manifest` and committing the regenerated
  manifest **in the same PR**, or CI goes red. Rev 2 now changes *three* schemas
  (`create`, `update`, `get`) instead of two.
- `mcp_artifact_provider.py:60-75` renders a diagram to Markdown by dumping
  `diagram_data["content"]` verbatim. For `node_graph`, render a node/edge summary table
  instead of a raw JSON blob — this is where the format finally becomes *useful to an agent*,
  which is half the "nothing to query" complaint in the issue. Include each node's
  `artifact_ref` target in that table, since those are now real links.
- `diagram.create` / `diagram.update` keep their existing `target_id` parameter. Its behaviour
  changes only in that it **starts working** (F5) — it creates a whole-diagram `documents`
  link, now on top of a real shadow Artifact. Node-level refs are additive to it, not a
  replacement (§3.7.2).

### 3.7 Per-node trace links — the mechanism (decision §9.1)

This is the new subsection rev 2 adds. It is the largest single piece of backend work in the
plan and the only one that touches `backend/persistence/models.py`.

#### 3.7.1 Does `Diagram` have to become an `Artifact`? — Investigated answer: it needs a *shadow* Artifact, and there is no cheaper option

The question posed in rev 1 §9.1 was whether per-node links could be modelled *without* making
Diagram an Artifact — e.g. a link type pointing at a `(diagram_id, node_id)` composite.
**Investigated: no, not without modifying `persistence.TraceLink` itself.** The reasons are
concrete:

- `TraceLink.source` and `TraceLink.target` are both
  `models.ForeignKey(Artifact, on_delete=models.CASCADE, …)` (`persistence/models.py:1233-1238`).
  Not UUIDFields. A non-Artifact endpoint is not expressible.
- `TraceLink` carries no metadata/JSON column at all. Its complete field set is
  `source, target, link_type, embedding` plus `tenant` and the audit fields from
  `TenantScopedModel` (`persistence/models.py:361-389`). There is nowhere to put a `node_id`.
- Even before the FK, `TraceLinkManager.create` performs an explicit
  `Artifact.unscoped.get(pk=source_id)` existence probe (`trace_link_manager.py:235-238`) —
  which is precisely why the current code is broken (F5).

So a `(diagram_id, node_id)` composite endpoint would require **either** a new nullable
`source_node_id` column on `pl_tracelink` plus a revision of the
`uq_tracelink_edge` UNIQUE(source, target, link_type) constraint (`persistence/models.py:1275-1278`),
**or** a new side-table. Both change a core table that the query engine, coverage calculator,
VCRM generator, baseline diff and SE auditor all read. That is a much larger blast radius than
the alternative, for a benefit — knowing *which node* a link came from — that the payload
already records losslessly.

**Chosen mechanism: a shadow Artifact per Diagram, and a link set that is the deduplicated
projection of the payload.**

```python
# backend/diagram/models.py — Diagram
artifact = models.OneToOneField(
    "persistence.Artifact",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="diagram",
    help_text=(
        "Shadow Artifact row (artifact_type='Diagram') that gives the "
        "TraceabilityEngine an FK-integrous endpoint for this Diagram. "
        "Created lazily on the first trace-link write; NULL for diagrams "
        "that have never been linked, and for diagrams with no workspace."
    ),
)
```

Four properties of that declaration, each with a reason:

- **`artifact_type="Diagram"` on the shadow row.** Not a new convention —
  `traceability/types.py:88,106` already declares `_DIAG = "Diagram"` in
  `SE_CORE_ARTIFACT_TYPES` and `SE_LINK_SEMANTICS[documents] = {(_DIAG, "*")}`. The SE endpoint
  matrix needs **zero** changes; it was written for this row.
- **`null=True` is forced, twice over.** Existing `Diagram` rows predate the column, and
  `Artifact.workspace` is a **non-null** FK (`persistence/models.py:725-727`) while
  `Diagram.workspace_id` is nullable (`diagram/models.py:82`, per migration 0005's
  Expand/Contract rollout). A workspace-less Diagram therefore *cannot* have a shadow at all —
  see §3.7.3.
- **`on_delete=SET_NULL`, diverging from the four existing proxies.** `StakeholderNeed`,
  `Requirement`, `ArchitectureElement` and `TestCase` all use `CASCADE`
  (`persistence/models.py:773, 829, 981, 1303`), because for them the Artifact *is* the
  identity. For Diagram the relationship is inverted: the Diagram is the identity and the
  Artifact is a projection of it. Deleting the shadow must not delete the drawing. Name this
  divergence in review so it does not read as an inconsistency.
- **Lazy creation, not creation-on-`create_diagram`.** A diagram that never references an
  artifact should not put a row in `pl_artifact`, where it would show up in artifact lists,
  tree walks, coverage denominators and baselines. The shadow is created on the first write
  that produces at least one link, inside the same transaction.

**Second required change — the resolver chain.** `TraceLinkService._resolve_artifact_id`
(`application/trace_link_service.py:77-166`) probes eight entity tables in order and raises
`NotFoundError` otherwise (`:166`). Add a Diagram step. Without it, any caller passing a
user-facing Diagram id to `traceability.create_link` gets a 404 — the exact failure mode of
issues #237 (Goal/MainGoal) and #264 (TestCase/StakeholderNeed). This is a two-line addition
and the single most forgettable part of the whole change.

#### 3.7.2 The reconciler: desired-state, not append

Per-node links are created by **reconciling the payload's reference set against the existing
link set on every write**, not by appending on create.

Location: extend `backend/diagram/traceability_connector.py` (COMP-DS-004) with

```
sync_node_links(diagram, payload, actor_id) -> SyncResult(created, removed, skipped)
```

called from `DiagramManager.create_diagram` and `.update_diagram` at exactly the two places
`create_document_link` is already called (`manager.py:165`, `:253`), inside the existing
`@atomic_transaction`. That keeps the Ext-layer boundary intact: `diagram/` still talks to
`traceability.services` and nothing else.

Algorithm:

1. If `payload_format != "node_graph"` → return immediately. Other formats are untouched.
2. `desired = {resolve(ref) for ref in node_graph.collect_artifact_refs(payload)}` — via
   `TraceLinkService._resolve_artifact_id` (§3.7.1), so a node may carry the user-facing
   Requirement/ArchitectureElement/TestCase/… id rather than an internal Artifact id.
3. Ensure the shadow Artifact exists if `desired` is non-empty (create lazily; error if the
   Diagram has no workspace — §3.7.3).
4. `current = {link.target_id for link in documents-links whose source is the shadow}`.
5. Create `desired - current`; delete `current - desired`.

Why desired-state rather than append-only — this is the direct answer to "what happens when a
node is deleted, or its `artifact_ref` changed":

- A node deleted, or its `artifact_ref` cleared or repointed → the stale link **disappears on
  the next save**. Append-only would leave a link asserting a relationship the diagram no
  longer draws, which is worse than no link at all: coverage metrics and the SE auditor read
  these links.
- The operation is **idempotent**: saving the same payload twice is a no-op on links, which
  matters because the editor will autosave.
- Two nodes referencing the same artifact collapse to **one** link. This is not a choice —
  `uq_tracelink_edge` UNIQUE(source, target, link_type) (`persistence/models.py:1275-1278`)
  makes a second one impossible. The set semantics of step 2 make that explicit rather than
  letting it surface as an `IntegrityError`.
- The whole-diagram `documents` link created from the existing `target_id` parameter is
  **indistinguishable** from a node-derived one — same source, same target, same link_type.
  That collision is the substance of open question §9.8; read it before implementing step 5.

#### 3.7.3 Links attach to the header, not to the version — and what that costs

The shadow Artifact hangs off `Diagram` (the mutable header), not off `DiagramVersion` (the
append-only snapshot). So **the link set always reflects the current version.** Rolling back
to version 3 does not restore version 3's links until version 3's payload is re-saved as
version 8.

This was chosen over the alternative — a shadow Artifact per `DiagramVersion` — because that
alternative would make `traceability.query` return one hit per historical version of the same
diagram (N near-duplicates for a diagram edited N times), inflate coverage denominators, and
grow `pl_artifact` without bound on a table that every tree walk and baseline scan reads. The
cost of the chosen design is that **historical link state lives in the version payload, not in
`pl_tracelink`** — it is recoverable (parse `DiagramVersion.payload`), just not queryable.
Recorded as risk §8.9.

Error surface — all of these are `400`-class, never `500`:

| Condition | Result |
|---|---|
| `artifact_ref.id` resolves to nothing | `NotFoundError` from `_resolve_artifact_id`, mapped to `VALIDATION_ERROR` naming the offending **node id** (not just the uuid — the user needs to find it on the canvas) |
| target is in another tenant | `CrossTenantLinkError` from `TraceLinkManager` (`trace_link_manager.py:_validate_cross_tenant_boundary`) |
| Diagram has no `workspace_id` and the payload has refs | `VALIDATION_ERROR` — mirror the wording of the existing guard in `_handle_outdate`: *"Diagram {id} has no workspace assigned"* |
| cycle | `CycleDetectedError`. In practice unreachable: `documents` edges only ever leave the shadow artifact and nothing points *into* it, so the DFS at `trace_link_manager.py:259-260` cannot find a return path. Handle it anyway rather than letting it escape as a 500. |

Because the whole thing runs inside `@atomic_transaction`, **any of these aborts the save** —
the diagram is not persisted with a half-applied link set. That is the correct behaviour but
it must be stated: a typo'd `artifact_ref` blocks the save of an otherwise valid drawing. The
frontend must surface the node id from the error (§4.4).

One deliberate non-change: the diagram connector calls `traceability.services.create_trace_link`
directly, which **bypasses** `TraceLinkService._enforce_se_semantics`
(`application/trace_link_service.py:195-240`). No behavioural gap results —
`SE_LINK_SEMANTICS[documents]` is `{(Diagram, "*")}`, i.e. permissive on the target side — but
it is worth knowing that se_mode adds no constraint on this path.

### 3.8 Nothing to change

Audit, workflow lifecycle (`outdate`/`reactivate` via `WorkflowTransitionsMixin`), RBAC
(`_assert_write_permission`, `tool_registry._WRITE_TOOL_PREFIXES`), tenancy, and the
`versions/`/`diff/` endpoints all operate on `payload_format`-agnostic fields and need no
edits — provided §2.5.4 canonical serialization is honoured.

Notably `delete_diagram` (`diagram/services.py:195-215`) is a **soft** delete via
`workflow.services.outdate` — "physical deletion intentionally avoided". So no Diagram row is
ever hard-deleted, the shadow Artifact is never cascade-orphaned, and its `documents` links
survive an outdate. Whether an outdated diagram's links *should* survive is a product
question, not a mechanism one; the mechanism does the conservative thing.

---

## 4. Frontend changes

### 4.1 New component tree

`frontend/src/components/DiagramGraphEditor/`, mirroring the WorkflowEditor file split:

| New file | Modelled on | Notes |
|---|---|---|
| `DiagramGraphEditorPage.tsx` | `WorkflowEditorPage.tsx` | route container, load/save, edit-mode toggle, **and the visual/code view-mode toggle (§4.6)** |
| `GraphCanvas.tsx` | `WorkflowCanvas.tsx` | React Flow viewport, `onConnect`, drag, delete |
| `GraphNode.tsx` | `StateNode.tsx` | 4 handles, `memo`, inline rename on double-click, artifact-ref badge |
| `GraphEdge.tsx` | `TransitionEdge.tsx` | bezier + `EdgeLabelRenderer` pill + wide transparent hover path |
| `GraphCodeView.tsx` | `DiagramDetailView.tsx:449-467` (`diagram-source-preview`) | **new in rev 2** — read-only formatted-JSON view (§4.6) |
| `graph-layout.ts` | `layout.ts` | dagre; **keep the centre→top-left correction** (`layout.ts:62-66`) |
| `GraphInspectorPanel.tsx` | `InspectorPanel.tsx` | node/edge properties + the `artifact_ref` picker |
| `GraphToolbar.tsx` | `CanvasToolbar.tsx` | add node, auto-layout, fit view, zoom |
| `useGraphPayload.ts` | `useWorkflowData.ts` + `useWorkflowMutations.ts` | TanStack Query against `diagramsApi` |
| `DiagramGraphEditor.module.css` | `WorkflowEditor.module.css` | see §4.5 on the ratchet |
| `index.ts` | `index.ts` | named exports only |

### 4.2 Shared vs. copied

**Copy the patterns, do not extract a shared library on the first pass.** Concretely worth
copying rather than abstracting:

- module-scope `NODE_TYPES`/`EDGE_TYPES` consts (`WorkflowCanvas.tsx:41-42` — React Flow
  warns on unstable type maps recreated per render);
- the dagre centre→top-left position correction (`layout.ts:62-66`) and the self-loop skip
  (`layout.ts:51-55`) — both are easy to get subtly wrong;
- the handle-id convention (`top`/`left` targets, `bottom`/`right` sources —
  `StateNode.tsx:81-108`), because the layout code emits matching `sourceHandle`/`targetHandle`;
- `EdgeLabelRenderer` + the wide transparent hover path (`TransitionEdge.tsx:63-72`).

A premature `components/shared/flow/` extraction would couple a stable, shipped editor to a
new one whose requirements are still moving. Revisit after the second editor stabilises.

### 4.3 The one structural divergence

Positions round-trip through the payload, not `localStorage`. There is **no**
`layout-store.ts` equivalent, and **auto-layout is an explicit toolbar button, not the
default on load**. Re-flowing a hand-arranged architecture sketch every time someone opens it
is the exact opposite of what the workflow editor should do with derived content — and
getting this backwards is the most likely way to copy the reference pattern too literally.

### 4.4 Everything else

- **Routing** (`NavigationShell.tsx:141-144`): add
  `<Route path="/diagrams/:id/graph" element={<DiagramGraphEditorWrapper />} />` alongside
  the existing `canvas` and `mermaid` fullscreen routes.
- **Detail pane** (`DiagramDetailView.tsx:112-127`): the `isCanvas`/`canRenderVisual` pair
  and the `editorRoute` ternary become a `payload_format → {previewKind, editorRoute}` map
  with a `node_graph` entry. The preview is the same React Flow canvas with
  `nodesDraggable={false}`, `nodesConnectable={false}`, `elementsSelectable={false}` — **no
  SVG, no `sanitizeSvg`, no `dangerouslySetInnerHTML` on this path.** This is the concrete
  win the issue asks for and the reason the format is safer by construction. (§3.4's export
  renderer is MCP-only and never reaches the browser.)
- **View-mode toggle in the editor** — see §4.6.
- **Types** (`types/index.ts:432`): `PayloadFormat` union `+= "node_graph"`; add
  `NodeGraphPayload` / `GraphNode` / `GraphEdge` / `ArtifactRef` interfaces mirroring §2.
- **Create form** (`diagram-view-shared.ts:22-47`): `PAYLOAD_FORMATS += "node_graph"`,
  `DEFAULT_CONTENT.node_graph` = a canonical two-node starter graph.
- **Artifact-ref error surfacing (new in rev 2).** A save can now fail because of a bad
  `artifact_ref` (§3.7.3), and the whole save is rejected. The inspector must map the returned
  node id back to a canvas selection and focus it, rather than showing a bare
  `VALIDATION_ERROR` toast. Without this, a user with a stale reference has a diagram they
  cannot save and no way to find out why.
- **i18n**: roughly 35-45 new keys per locale (rev 1 said 30-40; the code view and the
  artifact-ref error states add some). For scale, `workflow.*` has 111 keys and
  `diagram.*` + `canvas.*` together have 47. `frontend/src/test/i18n-parity.test.ts` enforces
  de/en parity. Watch the dotted-flat-key trap: a key written as `"type.box"` *inside* a
  locale object never resolves, because `keySeparator` is `"."` — nest it.
- **`data-testid` on every interactive element** (project convention, E2E requirement).

### 4.5 Two gates that will bite

1. **`frontend/src/test/ui-ratchet.test.ts`** counts inline `style={{` literals under
   `components/` against a frozen ceiling and fails when the count *increases*. A new
   component tree must put its styling in `DiagramGraphEditor.module.css`; the handful of
   unavoidable dynamic styles (the React Flow edge-label `transform`, per
   `TransitionEdge.tsx:79-81`) must be hoisted to named `CSSProperties` consts. **Never raise
   the baseline to make it pass.** Note the pattern being copied in §4.6 is itself
   inline-styled (`DiagramDetailView.tsx:373-400`, `:449-467`) — copy its *structure and i18n
   keys*, not its inline styles.
2. **Vite HMR is unreliable on Windows** in this stack — after touching the frontend
   container, verify in a real browser rather than trusting the dev server, and do not
   restart the frontend service casually.

### 4.6 View-mode toggle: visual graph (default) ↔ code view (decision §9.4b)

New requirement in rev 2. **The graph/edit view is the default; a code view showing the raw
JSON is one explicit toggle away.**

**Reuse the pattern that already exists — do not invent one.** `DiagramDetailView.tsx` already
implements exactly this toggle for Mermaid:

| Existing piece | Location | Reuse as-is |
|---|---|---|
| `const [viewMode, setViewMode] = useState<"code" \| "visual">("visual")` | `DiagramDetailView.tsx:76` | same state type, same `"visual"` default |
| Two `aria-pressed` toggle buttons in a group labelled `t("diagrams.viewMode")` | `DiagramDetailView.tsx:373-400` | same a11y structure (`aria-label` on the group, `aria-pressed` per button) |
| i18n keys `diagrams.viewMode`, `diagrams.viewModeLabels.code`, `diagrams.viewModeLabels.visual` | `i18n/locales/{de,en}.json` | **already exist in both locales** — zero new keys for the toggle itself |
| `<pre data-testid="diagram-source-preview">` read-only source block | `DiagramDetailView.tsx:449-467` | same element and `data-testid` convention; lift the styling into the CSS module per §4.5 |
| Reset to `"visual"` when the loaded diagram changes | `DiagramDetailView.tsx:84` | same effect — otherwise a code view sticks across navigation |

Behaviour in `DiagramGraphEditorPage.tsx`:

- `"visual"` (default) → `GraphCanvas`, full editing.
- `"code"` → `GraphCodeView`, **read-only**, rendering the canonical
  `JSON.stringify(payload, …, 2)` of the *current in-editor state* (not the last-saved server
  copy — otherwise unsaved edits appear to vanish when toggling).
- Read-only is a deliberate narrowing versus the Mermaid editor, which allows editing its
  textarea. A `node_graph` payload has cross-field invariants (edge endpoints must name
  existing nodes, `parent_id` must name a `group`) that a free-text editor lets a user break
  silently, and the round-trip back into React Flow state is a second parser to maintain.
  Ship read-only; a "copy to clipboard" button covers the realistic use case (paste into an
  agent prompt or a bug report). Revisit if users ask.

---

## 5. Migration strategy — recommendation

**Recommendation: a variant of (a) — keep `canvas_stroke` permanently as a *narrowed*
freehand-sketch format, make `node_graph` the default for structured diagrams, and ship a
one-time opt-in conversion command that converts `canvas_json` (not `strokes`).**

> **Decision §9.2, confirmed:** freehand *is* being kept, and the ask is explicitly for
> "ein System im gleichen Stil wie WorkflowEditor für Diagramme allgemein". That is precisely
> what §5.1 item 2 + §4 describe: `canvas_stroke`/Fabric narrowed to genuine freehand annotation,
> `node_graph` as the structured default, rendered by a React Flow + dagre editor built on the
> WorkflowEditor's file split, node/edge conventions and layout code (§4.1, §4.2). Rev 1
> already recommended this; rev 2 records it as **confirmed by the product owner**, not as a
> standing recommendation. No design change follows from it — the value of the decision is
> that §5.2's "why not full replacement" is now settled rather than pending.

### 5.1 Concretely

1. **`node_graph` becomes the offered "structured" option** in the create form, displacing
   `json`. `json` stays in the enum and `_validate_json` stays exactly as it is — existing
   rows and the E2E fixtures keep working — but it is removed from the create form's list.
   **UI only:** `json` and `node_graph` both remain fully creatable and updatable via REST and
   MCP (§3.6, decision §9.4a).
2. **`canvas_stroke` + the Fabric editor are kept and narrowed** to freehand
   sketching/annotation. The shape, connector and text tools stop being the recommended way
   to draw boxes-and-arrows. Rationale: that tooling duplicates — worse — what React Flow
   does natively, *and* its output is invisible in the preview today (F2).
3. **A one-time, opt-in conversion command**, converting `canvas_json` per F3:

   ```
   python manage.py convert_canvas_to_node_graph  (--diagram <uuid> | --workspace <uuid>)  [--apply]
   ```

   - reads `DiagramVersion.canvas_json` of the **current** version;
   - maps `data.type ∈ {rect, circle}` → nodes (position from `left`/`top`, size from
     `width * scaleX` / `height * scaleY`); `data.type == "label"` folds into the `labelFor`
     node's `label`; a standalone `data.type == "text"` becomes a `note` node;
     `data.type == "connector"` → edge with `source = data.fromId`, `target = data.toId`;
     `arrowHead` and `connectorPreview` are skipped as derived render artifacts;
   - **refuses to convert and reports** any canvas containing genuine free-hand `path`
     objects — those have no graph equivalent, and silently dropping them is data loss;
   - writes the result as a **new `DiagramVersion`**, never mutating history — the model is
     append-only by design, so the pre-conversion version stays intact and revertible;
   - **dry-run by default**; `--apply` required to write.

   *Why a management command and not a UI button:* per F4 this is a one-shot operation over a
   low-double-digit row count on a dogfooding install, not a recurring user workflow. Building
   UI for it costs more than the migration itself.
4. **Fix F2 regardless.** The `canvas-strokes/` SVG export should render from `canvas_json`
   (or stop claiming to preview shapes). File it as its own bug — it is broken today, it is
   not blocked by this design, and leaving it broken while shipping a competing format makes
   the comparison dishonest.

### 5.1.1 Impact of per-node trace links on the conversion command (rev 2)

Checked, and there is a small but real change: **the converter must go through the same
link-reconciliation path as a normal save, not write `DiagramVersion` rows directly.**

Fabric objects carry no `artifact_ref` — there is nothing in `canvas_json` to map to one — so
a *converted* diagram produces an **empty** desired-link set. That is not a no-op:
`sync_node_links` is desired-state (§3.7.2), so a diagram that already has whole-diagram
`documents` links from a `target_id` call would have them **deleted** by a naive conversion.

Two rules for the command:

1. Call `diagram.services.update_diagram` (which routes through `DiagramManager` and the
   reconciler) rather than constructing a `DiagramVersion` by hand. Hand-rolling the write
   would also skip validation and canonical serialization (§2.5.4).
2. Depends on the answer to §9.8. If links get provenance (option c), the converter is safe as
   written. If not, the converter must **not** run the reconciler on an empty ref set — add an
   explicit `skip_link_sync=True` for this one caller and document why. Do not discover this
   during implementation.

This moves the migration estimate from Small to Small–Medium (§6).

### 5.2 Why not (b), full replacement

- Freehand annotation is a real, distinct use case (marking up a rough sketch in a workshop)
  that React Flow structurally cannot serve. **Confirmed as kept — decision §9.2.**
- `REQ-L1-056` / `REQ-L2-DS-006` are live, traced SE requirements with a dedicated E2E spec
  (`e2e/tests/canvas-diagram.spec.ts`). Retiring them would be a **requirements change**;
  decision §9.2 settles that they are not being retired.
- Removing `canvas_stroke` from `PayloadFormat.choices` would invalidate existing
  `DiagramVersion` rows on their next save, forcing a real data migration for no benefit.

### 5.3 Why not plain (a) without a conversion path

"Keep both, new default" alone strands the boxes-and-arrows diagrams people have already
drawn in a format whose preview does not render them. The conversion tool is cheap
*specifically because of* F3 — the graph is already latent in the stored data — and it is
what makes option (a) honest rather than an abandonment.

---

## 6. Effort estimate

Sizes, not calendar time.

**Overall: Very Large** (revised up from *Large* in rev 1).

The rev 1 estimate rested on the sentence *"everything else in this document is stable under
either answer [to §9.1]; only the size estimate and Phase 6 are not."* That was correct, and
the answer came back as the expensive one. The honest reassessment:

- Rev 1's backend work was **additive and local**: one enum value, one pure schema module, one
  validator branch, one render hint. Nothing outside `backend/diagram/` changed.
- Rev 2's backend work **modifies a shared subsystem**. It adds a column to `Diagram` with an
  FK into `persistence.Artifact`, creates rows in `pl_artifact` (a table read by artifact
  lists, tree walks, coverage denominators, baselines and the SE auditor), writes into
  `pl_tracelink`, and extends `TraceLinkService._resolve_artifact_id` — the function whose
  omissions caused issues #237 and #264.
- And it does so on top of a code path that **does not currently work and has no real test
  coverage** (F5). The first honest task is not "add per-node links", it is "make one
  whole-diagram link work end-to-end against a database", which nothing in the repo has ever
  done.

That is a category change — from "new feature inside one Ext module" to "change to the
traceability data model, plus a latent-bug fix, plus a new rendering module in the code area
that produced #351". *Very Large* is the honest label, not a mechanical inflation.

| Area | Rev 1 | Rev 2 | Why it moved |
|---|---|---|---|
| **Backend — schema/validation** | Small–Medium | Small–Medium | Unchanged. `node_graph.py` + validator branch + enum + `AlterField` + canonical serialization. `collect_artifact_refs` is a few lines. |
| **Backend — trace links (§3.7)** | *(did not exist)* | **Large** | New `Diagram.artifact` FK + migration 0007 + lazy shadow creation; the desired-state reconciler inside `@atomic_transaction`; `_resolve_artifact_id` extension; four distinct error paths (§3.7.3) each needing a mapping to 400; and the F5 fix underneath all of it. Touches `persistence/models.py`, `application/trace_link_service.py`, `diagram/traceability_connector.py`, `diagram/manager.py`. |
| **Backend — SVG renderer (§3.4)** | *(explicitly none)* | **Medium** | New `node_graph_renderer.py`: 6 shape emitters, edge paths + arrow markers, text layout, the re-validation guard, the accent/line/handle tables. Not conceptually hard, but it is ~300-400 LOC of output-correctness code and it needs adversarial tests, because it lives in the blast radius of #351. |
| **MCP** | Small | **Small–Medium** | 3 `inputSchema` edits instead of 2 (`create`, `update`, **`get`**) + `export_format` handling + renderer wiring + the artifact-provider summary. Manifest drift guard applies. |
| **Frontend** | **Large** | **Large** | Essentially unchanged. 10-11 new files. The code-view toggle (§4.6) is genuinely cheap — the state shape, the button group, the `<pre>` block and the i18n keys all already exist in `DiagramDetailView`. The artifact-ref error surfacing is the only new non-trivial bit. |
| **Migration** | Small | **Small–Medium** | The converter must route through the reconciler, and its behaviour is gated on §9.8 (§5.1.1). |
| **Testing** | Medium | **Large** | Rev 1's list, plus: DB-backed link tests that do **not** mock `create_trace_link` (the existing suite's blind spot, F5) — create/update/reconcile/remove/idempotency/cross-tenant/no-workspace; a `_resolve_artifact_id` regression test for Diagram; adversarial renderer tests (hostile `accent`, hostile `label`, non-finite numbers, unknown node type) asserting no attribute injection; a golden-SVG test. Note the project convention: **Playwright is never run by an agent** — E2E specs may be written but are handed to the user and are not a DoD gate. Also note (from prior sessions) that backend tests need the DB owner role and `--create-db`, and that there is a known red baseline unrelated to this work. |

Sequencing note: backend and frontend remain cleanly separable — Phases 1-2b can land and be
exercised via `curl`/MCP long before any UI exists. The trace-link phase (1b) is the natural
place to stop and re-evaluate if the estimate proves optimistic; everything after it is
independent of it.

---

## 7. Phased approach

Each phase is independently mergeable and leaves `main` green.

**Phase 0 — fix the shipped preview defect (independent, do first).**
Make the `canvas-strokes/` SVG export render from `canvas_json`, or make the detail pane stop
promising a shape preview it cannot deliver (F2). *Done when:* a canvas containing a rect, a
text box and a connector produces a preview showing all three, or an explicit
"preview unavailable for this canvas" state. *Must not break:* PR #351's XSS hardening — any
new rendering path goes through the same numeric coercion, or better, through the client.

**Phase 1 — backend schema and validation.**
`node_graph.py` (incl. `collect_artifact_refs`), the enum value, migration 0006, the validator
branch, the render hint, the canonical-serialization step on the write path. *Done when:*
`POST /api/v1/diagrams/` with `payload_format=node_graph` accepts a valid graph, rejects a
dangling edge endpoint / unknown node type / over-cap payload with `400 VALIDATION_ERROR`, and
two consecutive identical saves produce an empty `diff/`. *Must not break:* `_validate_json` —
leave it untouched (§8.5).

**Phase 1b — trace links (rev 2; unblocked as of rev 3 — §9.8 resolved).**
Split into two mergeable steps, because the first is shared infrastructure that also happens
to repair a pre-existing bug:

- **1b-i — give `Diagram` a real `Artifact` to link against.** `Diagram.artifact` + migration
  0007 + lazy shadow creation + the `_resolve_artifact_id` step. This is the root fix behind
  both #392 (the pre-existing, separately filed bug where `Artifact.unscoped.get(pk=source_id)`
  always raises `SourceNotFoundError` for a Diagram) and the new `DIAGRAM_REF` link type this
  refactor needs — they share one root cause and one fix. *Done when:* MCP `diagram.create`
  with `target_id` set actually creates a `documents` TraceLink against a real database (this
  incidentally closes #392) **and the test proving it does not mock `create_trace_link`.**
  Ships value even if the rest of the refactor is abandoned.
- **1b-ii — reconcile per node.** `sync_node_links` in `traceability_connector.py`, wired at
  `manager.py:165`/`:253`, creating/deleting `DIAGRAM_REF` links only (§9.8) — never touching
  `documents` or any other type on the same Diagram/artifact pair; the four error paths mapped
  to 400 (§3.7.3). *Done when:* saving a graph creates one `DIAGRAM_REF` link per distinct
  `artifact_ref`; re-saving is a no-op; clearing a ref removes its link; a cross-tenant or
  unresolvable ref aborts the save with a message naming the node id; a pre-existing
  `documents` link on the same Diagram survives a save untouched.

**Phase 2 — MCP surface (source).**
Enum-ify the `payload_format` schemas on `create`/`update`, add `node_graph`, regenerate and
commit `tool-manifest.json`, teach `mcp_artifact_provider` to summarize a graph including
`artifact_ref` targets. *Done when:* `test_tool_manifest_drift` passes and `artifact.get` on a
`node_graph` diagram returns a readable node/edge table.

**Phase 2b — SVG renderer + export (new in rev 2).**
`node_graph_renderer.py`; `DiagramRenderer.export_svg` dispatch; `export_format` on
`diagram.get`; manifest regeneration (again — batch it with Phase 2 if the two land together).
*Done when:* `diagram.get(id, export_format="svg")` on a `node_graph` diagram returns a
well-formed SVG that renders in a browser and survives `sanitizeSvg` unchanged; the same call
on a Mermaid diagram returns `VALIDATION_ERROR`, not a 500; and the adversarial test set
(hostile `accent`, hostile `label`, non-finite `position`) produces output containing **no**
attacker-controlled attribute bytes. *Must not break:* `export_png` stays a documented stub
(§3.4.4).

**Phase 3 — frontend editor (the bulk).**
The `DiagramGraphEditor/` tree, the `/diagrams/:id/graph` route, types, i18n, the visual/code
toggle (§4.6), the artifact-ref picker and its error surfacing. *Done when:* a diagram can be
created, laid out, edited, saved and reloaded with positions intact, verified in a real browser
at more than one viewport; toggling to Code shows the current in-editor JSON and back to Visual
loses nothing. *Must not break:* `ui-ratchet.test.ts`, `i18n-parity.test.ts`.

**Phase 4 — read path and defaults.**
Detail-pane preview via read-only React Flow; create form offers `node_graph` and drops
`json` (UI only — MCP unaffected, §3.6). *Done when:* no `node_graph` code path in the browser
touches `dangerouslySetInnerHTML`.

**Phase 5 — conversion command.**
`convert_canvas_to_node_graph`, dry-run first, with a refusal path for free-hand strokes, and
routed through the reconciler per §5.1.1. *Done when:* a dry run over the dogfooding workspace
prints a per-diagram convertible / not-convertible report; `--apply` produces new versions
without mutating old ones; **and a converted diagram that previously had a whole-diagram
`documents` link still has it afterwards.**

**Phase 6 — SE documentation.**
New REQ ids, interface-registry entries, and ADRs recording: (a) the shadow-Artifact pattern
and the header-scoped link lifetime (§3.7.3) — this supersedes the artifact-proxy note at
`traceability_connector.py:18-27`, which is now factually wrong and must be rewritten, not
just annotated; (b) "client-side rendering on the read path, dedicated enum-driven renderer on
the export path"; (c) the positions-in-payload divergence from `WorkflowEditor`. Delegate to
`documenter`; the decision blocks belong in the ADRs, not only in commit messages.

---

## 8. Risks

1. **Diff noise.** Without §2.5.4's canonical serialization, `ArtifactDiffService` line-diffs
   the payload and every save looks like a full rewrite (`artifact_diff_service.py:73, :91`).
   Cheap to get right up front, expensive to retrofit once versions exist.
2. **Two structured formats is a UX smell.** `json` and `node_graph` will both be in the enum
   and both creatable via API/MCP — deliberately so (§3.6). Mitigation: `json` disappears from
   the create form and from documentation, and the MCP tool description names `node_graph` as
   the structured format. Full removal is §9.4 (resolved: not removed).
3. **MCP manifest drift guard.** Changing a tool `inputSchema` without regenerating
   `tool-manifest.json` in the same PR turns CI red. Rev 2 changes three schemas across two
   phases — the second regeneration is the easy one to forget.
4. **Bundle size.** `@xyflow/react` is already a dependency, so there is no new install — but
   confirm the diagrams route is code-split the same way the workflow route is, or the
   diagrams list page starts paying for React Flow it does not use.
5. **Do not tighten `_validate_json`.** `e2e/tests/canvas-diagram.spec.ts:29` creates its
   fixture as `diagram_type: 'canvas', payload_format: 'json'` with a `{objects, background}`
   body, which passes only because `_JSON_REQUIRED_KEYS` has no `canvas` entry. Tightening it
   as "cleanup" breaks that spec for no gain.
6. **Layer-inversion temptation.** The `validator.py → rest_api` local import is an accepted
   exception for an existing format. Reproducing it for `node_graph` would normalize the
   inversion (§3.2).
7. **`max_length=16`** on `payload_format` leaves 6 characters of headroom after
   `"node_graph"`. Not a blocker; worth knowing before someone proposes
   `"structured_graph"`.
8. **Playwright is never run automatically** in this project. E2E specs may be written; they
   must be handed to the user to execute and are not a DoD gate.

**New in rev 2 — from decision §9.1 (trace links):**

9. **Link state is header-scoped, so version history and link history diverge.** The shadow
   Artifact hangs off `Diagram`, not `DiagramVersion` (§3.7.3). Restoring an old version does
   not restore its links until that payload is re-saved. Historical link state is recoverable
   by parsing `DiagramVersion.payload`, but it is **not queryable** through
   `traceability.query`, the coverage calculator, or a baseline diff. Anyone reasoning about
   "what did this diagram document at baseline X" from `pl_tracelink` alone will get today's
   answer, not X's. Accepted deliberately (the alternative — an Artifact per version — is
   worse), but it must be written into the ADR, not left as folklore.
10. **The reconciler cannot tell a graph-derived link from a hand-authored one.** `TraceLink`
    has no provenance column, and a `documents` link created by `sync_node_links` is
    byte-identical to one created by `traceability.create_link` or by the `target_id`
    parameter. Desired-state reconciliation will therefore **silently delete a link a human
    created by hand**, if the current payload has no node referencing that target. This is the
    single highest-consequence unknown in the plan and is escalated as open question **§9.8**.
    Do not start Phase 1b-ii before it is answered.
11. **The SVG renderer must not reintroduce the #351 injection class — the invariant, stated
    exactly.** Not "it is safe because the schema is typed", which is an assertion. The
    checkable invariant is:

    > *Every byte in the renderer's output is one of: (a) a literal from the module's own
    > source; (b) a value selected from a module-level literal table by an enum key, where a
    > key miss falls back to a literal; (c) a finite number that passed both
    > `validate_node_graph`'s cap check and `_num_attr`'s coercion; or (d) XML-escaped text
    > from `label`, emitted as a `<text>` child node and never as an attribute value.*

    Two failure modes break it, and both are review checklist items rather than test cases:
    **adding an attribute sourced from a non-enum string field** (a future `style.color`, a
    `node.href`, a `data-*` passthrough — any of these reopens #351 exactly), and **emitting a
    label into an attribute** (`<title>` is fine as a child element; `aria-label="…"` is not).
    The enum-keyed-lookup property is what makes this *stronger* than `canvas_editor.py`'s
    approach, which still passes an arbitrary user string through
    `_escape_xml_attr(element.get("color", …))` at `canvas_editor.py:158` — escaping is a
    correct-implementation guarantee; a key miss is a structural one. Also: the guarantee
    depends on §3.4.3's re-validation on entry. Removing that as a "redundant" optimization
    silently downgrades (c) from a guarantee to a historical claim.
12. **Link creation is O(n) full-graph adjacency builds inside one transaction.**
    `TraceLinkManager.create` calls `self.get_trace_links(link_type=link_type)` and
    `_build_adjacency(existing)` **per link** (`trace_link_manager.py:259-260`) for its eager
    cycle check. A graph with 60 distinct `artifact_ref`s therefore performs 60 fetches of
    every `documents` link in the tenant plus 60 adjacency rebuilds, in a single transaction,
    on every save — including editor autosaves. Mitigations, in order of preference:
    (a) the ≤ 100 distinct-refs cap (§2.5.3); (b) skip the cycle check for `documents` — it is
    provably unreachable, since nothing links *into* a diagram shadow artifact (§3.7.3);
    (c) use `batch_create_trace_links`, which does one Tarjan pass at transaction end instead
    of a DFS per link. **Measure before optimizing**, but do not ship the naive loop without
    at least the cap.
13. **`Artifact.workspace` is non-null; `Diagram.workspace_id` is not.** A Diagram created
    before migration 0005's backfill, or by any path that leaves `workspace_id` NULL, cannot
    have a shadow Artifact at all. Handled as a 400 (§3.7.3), but it means "add an
    `artifact_ref`" can fail on legacy rows for a reason that has nothing to do with the
    reference. Check the actual NULL count on the dogfooding install before Phase 1b.
14. **`_resolve_artifact_id` is the recurring 404 factory.** Every previous artifact type
    added to the system (#237 Goal/MainGoal, #264 TestCase/StakeholderNeed) shipped without its
    step in `application/trace_link_service.py:77-166` and surfaced as a 404 on link creation.
    Diagram will do the same if the two-line addition in §3.7.1 is skipped. It has no
    compile-time or type-level guard — only a test.
15. **The existing traceability tests mock exactly the thing that is broken.** All four cases
    in `diagram/tests/test_traceability_connector.py` patch
    `diagram.traceability_connector.create_trace_link`, including the one named
    `…WithManagerIntegration`. Adding more tests in that style would keep F5 invisible. Every
    new link test must hit the database.

---

## 9. Decisions and open questions

**Questions 1-4 were answered on 2026-08-07 and are kept below as decision records.
Questions 5-7 remain open. Question 8 is new, raised by the investigation behind decision 1,
and blocks Phase 1b-ii.**

1. ~~**Does `artifact_ref` participate in real traceability, or is it display-only?**~~
   **RESOLVED 2026-08-07 — real trace links, node-scoped only.**
   Each node with a populated `artifact_ref` produces a real `documents` TraceLink between the
   Diagram and the referenced artifact, extending the existing single whole-diagram link
   (`traceability_connector.py:52`) from per-diagram to per-node. **Edges between two
   artifact-bound nodes stay purely visual and do NOT become trace links** — deliberate
   narrowing, rationale in §2.3.
   *Mechanism (investigated, §3.7):* `Diagram` gets a **shadow Artifact** —
   `OneToOneField(Artifact, on_delete=SET_NULL, null=True)` with `artifact_type="Diagram"`,
   created lazily. A `(diagram_id, node_id)` composite endpoint was investigated and rejected:
   `TraceLink.source`/`.target` are hard FKs to `Artifact` and the model has no metadata
   column, so a composite endpoint would require altering `pl_tracelink` and its
   `uq_tracelink_edge` constraint — a far larger blast radius than a shadow row that
   `SE_LINK_SEMANTICS[documents] = {(Diagram, "*")}` already anticipates.
   Node identity is **not** stored on the link; the link set is the deduplicated projection of
   the payload, reconciled to desired state on every write. Links attach to the Diagram
   header, so old versions do not retain their own links (§3.7.3, risk §8.9).
   *Unplanned dividend:* this also fixes F5 — the existing whole-diagram link path has never
   worked at runtime.
2. ~~**Is freehand sketching a capability we are keeping?**~~
   **RESOLVED 2026-08-07 — CONFIRMED: keep freehand, and build "ein System im gleichen Stil
   wie WorkflowEditor für Diagramme allgemein".** This is exactly what rev 1 §5.1 recommended,
   now confirmed rather than merely proposed: `canvas_stroke` + Fabric stay, narrowed to
   genuine freehand annotation; `node_graph` becomes the structured default; the editor is
   built on the WorkflowEditor's React Flow + dagre pattern, file split and conventions (§4).
   `REQ-L1-056` / `REQ-L2-DS-006` are **not** retired, so no requirements change is needed.
   No design change follows — the value is that §5.2 is settled.
3. ~~**Rigor-preset gating.**~~
   **RESOLVED 2026-08-07 — no.** `node_graph` editing is **not** preset-gated. It stays as
   `diagrams` is today: a per-user module visibility toggle
   (`frontend/src/api/preferences.ts:45`), not an Extended-only feature the way workflow
   *editing* is. Confirms the rev 1 recommendation; no design change.
4. ~~**Does `json` stay reachable?**~~
   **RESOLVED 2026-08-07 — yes, with three sub-decisions.**
   **(a) Reachability.** `json` and `node_graph` both stay fully reachable **via MCP**.
   Removing `json` from the create form (§5.1.1) is a **UI-surface decision only** — MCP
   callers are not UI and keep full create/update access to every `payload_format`, `json`
   included and unchanged. No MCP tool is gated or deprecated by this refactor (§3.6).
   **(b) Default view + code view.** The **visual graph/edit view is the default**, with an
   explicit toggle to a **"Code view" showing the raw JSON**. Read-only, reusing the
   `"code" | "visual"` toggle, `aria-pressed` button group, `<pre data-testid=…>` block and
   the already-existing `diagrams.viewMode*` i18n keys from `DiagramDetailView.tsx:76, 373-400,
   449-467` (§4.6). New frontend requirement; not in rev 1.
   **(c) Server-side SVG export via MCP is back in scope**, using a **dedicated
   `node_graph`→SVG renderer**, explicitly **not** headless-browser rendering. Justified by the
   schema being strictly typed — enum-only style fields, capped finite numerics, referential
   integrity — unlike the freeform `canvas_stroke` model behind #351. This **reverses rev 1's
   §3.4 "no SVG at all"** for the *export* path while keeping it absolutely for the *read*
   path (§3.4). Surfaced as `export_format` on the existing `diagram.get` rather than a new
   tool (§3.6). **"As code" needs no new tool** — `diagram.get` already returns the raw
   canonical JSON in `diagram.content`. **PNG: decided out of scope for v1** — `reportlab` is
   already present but cannot parse SVG, `cairosvg` needs native cairo in a `python:3.12-slim`
   image that ships no graphics libraries, and no consumer has a PNG-specific need; `svglib`
   is named as the cheaper route if that changes (§3.4.4).

**Still open:**

5. **Do the five `DiagramType` values still mean anything for `node_graph`?** `block`, `flow`
   and `context` differ today only in which JSON keys `_validate_json` requires. With a real
   schema they would carry no behaviour at all. Options: keep as free-text categorisation,
   collapse to one, or give each a distinct default node-type palette.
   *(Unaffected by decisions 1-4. Does not block Phase 1 — the format is orthogonal to
   `DiagramType` either way.)*
6. **Server-side export for the traceability PDF report.** Is a rendered `node_graph` needed in
   the PDF, and at what fidelity?
   **Partially answered by decision 4c.** The hard part — "does a server-side `node_graph`
   renderer exist, and is building one acceptable?" — is now settled: yes, `node_graph_renderer.render_svg`
   (§3.4) will exist and is reachable from `traceability/pdf_report_generator.py`. What remains
   is a genuinely smaller follow-up rather than a from-scratch question:
   (a) the *product* question — should diagrams appear in the PDF at all, and which ones? — is
   **still open and still a human decision**; and
   (b) if yes, `reportlab` (already in `requirements.txt:43`) cannot consume SVG directly, so
   embedding needs `svglib` — the same dependency call flagged in §3.4.4, now with a concrete
   consumer behind it. Deciding "yes, in the PDF" is the thing that would justify adding
   `svglib`; nothing else currently does.
7. **Who runs the conversion?** §5 assumes an operator-run one-shot. If self-service
   conversion is required, add a UI + async job and move the migration estimate from
   Small–Medium to Medium.

**New — raised by the investigation behind decision 1. Blocks Phase 1b-ii:**

8. **How should the reconciler treat a `documents` link it did not create?**
   `TraceLink` has no provenance column (fields: `source`, `target`, `link_type`, `embedding`,
   plus tenant/audit — `persistence/models.py:1233-1250`). A link created by `sync_node_links`
   is therefore **indistinguishable** from one created by a human via
   `traceability.create_link`, or by the existing `target_id` parameter on
   `diagram.create`/`diagram.update` (`mcp_server/tools/diagram.py:128, 160`).
   Desired-state reconciliation (§3.7.2 step 5) deletes `current - desired`. So: **a link a
   user created by hand between this diagram and an artifact will be silently deleted the next
   time the diagram is saved without a node referencing that artifact.** Including on autosave.
   Three options, none free:

   | Option | Consequence |
   |---|---|
   | **(a) Additive only** — never delete | No data is ever destroyed, but stale links accumulate and outlive the nodes that justified them. Coverage metrics and the SE auditor read these links, so they degrade quietly. Contradicts the "link set reflects the drawing" property that motivates the feature. |
   | **(b) Full desired-state** — delete anything not in the payload | Clean, idempotent, matches the mental model "the diagram *is* the link set". Destroys hand-authored links, silently, with no undo. |
   | **(c) Provenance marker** — distinguish graph-derived links and reconcile only those | Correct, and the only option that lets both mechanisms coexist. Costs a schema change to a core table, or a convention (e.g. a distinct `link_type` such as `"documents-node"`, which keeps `pl_tracelink` untouched but adds a 16th value to `LinkType` and has to be taught to `SE_LINK_SEMANTICS`, the coverage calculator and every link-type filter). |

   *Engineering lean, for what it is worth:* **(c) via a distinct link_type**, because it is
   the only option that does not force a choice between silent data loss and silent rot, and
   because a new `LinkType` value is additive where a new column is not. But this is a product
   call about what a trace link *means*, and it also determines whether the conversion command
   needs a `skip_link_sync` escape hatch (§5.1.1). **It should be answered before Phase 1b-ii
   starts, not during it.**

   **RESOLVED 2026-08-07 — (c), a dedicated link type.** Confirmed: node→artifact references
   get their own `LinkType` value, exclusively used for diagram-node-generated links, never
   for hand-authored links. Concretely: add `DIAGRAM_REF = "diagram-ref"` to
   `backend/traceability/types.py::LinkType` (kebab-case string value, consistent with the
   existing 13 entries — `DOCUMENTS = "documents"` is the closest sibling but stays
   hand-authored-only; `DIAGRAM_REF` is reconciler-owned-only, the two never overlap on the
   same row). The desired-state reconciler (§3.7.2) filters `current`/`desired` to
   `link_type=DIAGRAM_REF` before diffing, so it only ever creates/deletes links of that one
   type — a human-authored `documents` link (once #392 makes that path work) or any other
   type between the same Diagram and artifact is invisible to it and never touched. This also
   resolves §5.1.1's `skip_link_sync` question: the converter needs no escape hatch, since
   reconciling `DIAGRAM_REF` links can never collide with or delete a pre-existing link of a
   different type.

   **Follow-up, not a blocker:** `DIAGRAM_REF` must be taught to whatever `SE_LINK_SEMANTICS`,
   the coverage calculator, and any link-type filter/dropdown (frontend `LinkType` union,
   `TraceLinksForm.tsx`, `traceability.query` filters) currently enumerate the 13 existing
   types by name — an implementation task for Phase 1b-ii, not a further open question.

---

## 10. Summary of the recommendation

Add `payload_format=node_graph` with the schema in §2, validated by a new pure
`backend/diagram/node_graph.py`, and edited/read in the browser exclusively client-side by a
new `DiagramGraphEditor/` modelled on `WorkflowEditor/` — **with positions stored in the
payload rather than `localStorage`**, which is the one place the reference pattern must not be
copied. The editor defaults to the visual graph and offers a read-only **Code view** one
toggle away, reusing the `"code" | "visual"` pattern, button group and i18n keys that
`DiagramDetailView` already ships.

**A node's `artifact_ref` is real traceability, not decoration.** Each populated reference
becomes a `DIAGRAM_REF` TraceLink — a **dedicated, reconciler-owned link type** (§9.8),
never `documents` — between the Diagram and the referenced artifact, reconciled to desired
state on every write. Because it is its own type, reconciliation can never delete a
hand-authored `documents` (or any other) link, so §5.1.1's `skip_link_sync` escape hatch turns
out to be unnecessary. Mechanically this requires giving `Diagram` a **shadow `Artifact`**
(`artifact_type="Diagram"`, lazily created, `SET_NULL`) — the endpoint that `SE_LINK_SEMANTICS`
has been declaring since before this refactor and that `TraceLinkManager`'s
`Artifact.unscoped.get(pk=source_id)` probe has always silently required. Edges stay purely
visual. Links attach to the Diagram header, so they always describe the current version and
never the history — an accepted, documented trade-off. **This part of the work sits next to a
pre-existing, independent bug** (filed separately as #392): today's whole-diagram `documents`
link path raises `SourceNotFoundError` on every real call and rolls the diagram creation back
with it, and every test mocks the failure away — `DIAGRAM_REF` does not depend on #392 being
fixed first, since it is a new type on a now-real `Artifact` FK, not a repair of the old path.

**Server-side SVG is back — but only for export, never for the read path.** A new,
deliberately small `backend/diagram/node_graph_renderer.py` maps the schema's own enums to
literal tables (`accent` → fill/stroke pairs, `line` → dash arrays, `type` → shape emitters),
routes every number through the existing `_num_attr` coercion, and emits the one free-text
field — `label` — as an escaped `<text>` child, never as an attribute. That is what makes it
safe *by construction* rather than by escaping, and §8.11 states the invariant precisely
enough to check in review. It is surfaced as `export_format` on the existing `diagram.get`;
"as code" needs no new tool because `diagram.get` already returns the canonical JSON. **PNG is
decided out of scope for v1** — `reportlab` cannot parse SVG and `cairosvg` needs native
libraries this image does not carry.

Keep `canvas_stroke` permanently, narrowed to genuine freehand sketching (confirmed, not
merely recommended), and ship a dry-run-first management command that converts `canvas_json`
(never `strokes`) into `node_graph` as a new append-only version, refusing rather than silently
dropping free-hand paths — routed through the link reconciler so conversion does not delete
existing links. Fix the `canvas_json`-vs-`strokes` preview defect (F2) first and separately —
it is broken in production today.

**Overall size: Very Large**, revised up from Large, because decision §9.1 moved the backend
from an additive change inside one Ext module to a change in the traceability data model on
top of a code path that has never worked. Phase 1b-i is the natural first slice: it fixes the
pre-existing bug (filed separately as #392) and delivers a working diagram trace link on its
own, independently of everything else.

**No decision blocks implementation start anymore.** §9.8 is resolved: the reconciler owns a
dedicated `DIAGRAM_REF` link type and never touches `documents` or any hand-authored link.
§9.5-§9.7 remain open but are non-blocking (each is scoped to its own phase or explicitly
deferred). The next step is turning this document into a task-by-task implementation plan.
