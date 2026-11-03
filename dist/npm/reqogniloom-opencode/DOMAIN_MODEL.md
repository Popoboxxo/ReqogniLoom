# ReqogniLoom Domain Model (shared reference)

Every role and process skill in this directory links here instead of restating these concepts —
if you're updating one of them, update it here once, not in five places.

## REQ-ID schema
`REQ-L0-*` (Stakeholder Needs) through `REQ-L3-*` (Component-level requirements); `REQ-L4` is
reserved for Presentation. V-Modell chain: L0 Stakeholder Needs -> L1 System Requirements ->
L2 Subsystems -> L3 Components -> L4 Presentation. Never invent an ID yourself — the relevant
`create` tool assigns it; read it back from the tool response.

## 15 Trace-Link-Typen
The real `LinkType` enum (`backend/traceability/types.py`) has 15 members — not the 8 an earlier
taxonomy draft assumed (GitHub #404). Use the exact lower-case, kebab-case string values
below with `traceability.create_link`/`traceability.query` — anything else is rejected with a 400:

`parent-child` (generic same-type hierarchy edge), `derives-from` (this Requirement/Need was
derived from a higher-level Requirement/Need — V-Modell level transitions use this), `satisfies`
(an architecture element or requirement fulfills a stakeholder need), `verifies` (a TestCase's
passing result is evidence a Requirement/ArchitectureElement is satisfied), `implements` (an
architecture element realizes a requirement), `refines` (same-type elaboration:
Requirement->Requirement or ArchitectureElement->ArchitectureElement), `documents` (a Diagram
documents another artifact), `realizes` and `traces` (deliberately generic/unrestricted
associations — reach for `traces` for a non-committal cross-reference no other type fits),
`copy-of` (same-type duplicate marker), `allocated-to` (a Requirement is allocated to an
ArchitectureElement), `uses-term` (links an artifact to a Glossary term), `decides` (an ADR
decision link — ADR -> ArchitectureElement; also the link ReqogniLoom auto-creates from a new ADR
to the ADR it supersedes, see below), `decomposes` (the hierarchy edge
`RequirementService.decompose()`/`derive_requirement()` creates), `diagram-ref`
(reconciler-owned only — never create/update this one through manual TraceLink CRUD).

**No `conflicts-with`/`supersedes` link type exists.** An earlier taxonomy draft assumed both;
the `LinkType` enum was deliberately never extended with them (explicit product decision, see
`backend/traceability/audit/rules/coverage_consistency.py` — the two SE-Auditor rules that would
check them, `CONS-P9`/`CONS-P10`, are registered but marked `deferred` and never fire). Model a
"conflicts with" relationship via a Risk/Issue artifact describing the conflict instead of a
dedicated link type. Model "supersedes" via the artifact's own workflow status (`Superseded`)
plus a `decides` TraceLink from the new artifact to the old one — this is exactly what
`AdrService.transition_status` does automatically for ADRs; the old artifact stays on record, it
is not deleted. Create links explicitly with `traceability.create_link` when a `create`/`update`
call's own parameters don't already cover the link you need.

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
