# ReqogniLoom Domain Model (shared reference)

Every role and process skill in this directory links here instead of restating these concepts —
if you're updating one of them, update it here once, not in five places.

## REQ-ID schema
`REQ-L0-*` (Stakeholder Needs) through `REQ-L3-*` (Component-level requirements); `REQ-L4` is
reserved for Presentation. V-Modell chain: L0 Stakeholder Needs -> L1 System Requirements ->
L2 Subsystems -> L3 Components -> L4 Presentation. Never invent an ID yourself — the relevant
`create` tool assigns it; read it back from the tool response.

## 8 Trace-Link-Typen
`TRACE_TO` (generic association), `DERIVED_FROM` (this artifact was derived from that one —
V-Modell level transitions use this), `IMPLEMENTS` (an architecture/component realizes a
requirement), `TESTS` (a test case exercises a requirement), `VERIFIES` (a passing test-run result
is evidence a requirement is satisfied), `RELATED_TO` (non-committal association), `CONFLICTS_WITH`
(two elements pull in opposite directions), `SUPERCEDES` (a new version replaces an older one —
used for ADRs and requirement revisions; the superseded element stays on record, it is not
deleted). Create links explicitly with `traceability.create_link` when a `create`/`update` call's
own parameters don't already cover the link you need.

## 3 Rigor-Presets
`minimal` / `standard` / `extended` share the same data model but differ in which fields are
mandatory (`mandatory_fields`), which workflow states/transitions exist, and which optional
governance features (e.g. CCB approval, baseline-linkage enforcement) are active. Call
`workspace.get_context` at the start of any session to learn the active preset before deciding how
much detail an artifact needs — never assume a fixed set of states or required fields across
workspaces.

## 3 Baseline-Scopes
Document / Project / Global — all three are one entity (`Baseline`) distinguished by scope. An
element already captured in an active baseline represents a frozen snapshot; changing it produces
a field-level diff against that baseline rather than silently overwriting history. Use
`baseline.compare` to see the diff before mutating a baselined element.

## Custom fields
A workspace may add fields beyond the core schema for a given artifact type. `custom_field.get`/
`custom_field.query` discover which apply, in addition to whatever the active rigor preset's
`mandatory_fields` already requires.
