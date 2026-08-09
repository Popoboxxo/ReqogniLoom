---
name: vmodell-decomposition
description: Use when capturing a stakeholder need or deriving/decomposing a requirement across V-Modell levels (L0-L3) in a ReqogniLoom workspace, manually or LLM-assisted.
---

# V-Modell Decomposition

See [DOMAIN_MODEL.md](../../DOMAIN_MODEL.md) for the REQ-ID schema, trace-link types, and rigor
presets referenced below.

## Workflow

1. `workspace.get_context` — learn the active rigor preset and, if the workspace has goals
   configured, `goal.read`/`goal.query`/`main_goal.read` to see which strategic goal the need
   should ultimately serve; flag (don't silently proceed) if it doesn't trace toward any active
   goal.
2. Capture the raw stakeholder need with `needs.create`; refine it with `needs.update` as
   understanding sharpens. `needs.read` fetches a single need by ID once captured, and
   `needs.get_traces` shows which requirements have already been derived from it, so you can tell
   an already-decomposed need from one still waiting. `custom_field.get`/`custom_field.query` show
   workspace-specific fields to fill in beyond the core schema.
3. Derive the first requirement level either by hand (`requirement.create` + an explicit
   `DERIVED_FROM` link via `traceability.create_link`) or by asking the LLM adapter via
   `ai_derivation.derive_requirements_from_need` / `needs.derive_requirements` — both call the
   same backend derivation service, the first is the raw AI-derivation tool, the second is the
   needs-scoped convenience wrapper. `requirement.derive` is the generic single-requirement
   derivation call for deriving one requirement from another already-existing requirement
   (rather than from a raw stakeholder need) — use it when the source is itself a requirement.
4. Fetch the requirement you're about to decompose with `requirement.get` (by ID) or
   `requirement.query` (by criteria, when you don't have an exact ID); `requirement.update`
   revises its fields directly when a decomposition pass surfaces a correction on the source
   requirement itself, without going through `decompose`/`derive` again. Decompose it to the next
   V-Modell level with `requirement.decompose` (manual) or
   `ai_derivation.decompose_requirement_next_level` (LLM-assisted). After decomposing,
   `ai_derivation.suggest_architecture_for_requirement` proposes which architecture element(s) the
   new requirement level should map to — review before an architecture-owning identity actually
   creates the `architecture.*` element.
5. Before finalizing, run `requirement.validate` (structural check against the active rigor
   preset) and `requirement.check_consistency` (semantic conflict check against sibling
   requirements).
6. Use `traceability.query` to inspect existing links and `traceability.suggest_links` to find
   candidate targets you may have missed.
7. `glossary.read`, `artifact.search`, and `artifact.get_tree` help find prior art before creating
   a duplicate requirement.
8. `prompt_template.list` shows which named templates exist; `prompt_template.get` inspects one —
   useful when a derivation result looks off and you want to understand why (never edit a
   template from here; that's an administrative action, out of scope for this skill).
9. To hand off a completed decomposition, `requirement_bundle.export` gathers every requirement
   `ALLOCATED_TO` an architecture element into one JSON/Markdown/CSV bundle; check
   `requirement_bundle.attribute_schema` first to see which attribute names are valid for that
   bundle's `fields` filter. Large exports (or an explicit `async` request) run in the background —
   poll `requirement_bundle.compression_status` with the returned `task_id` until it reports
   `done`.
