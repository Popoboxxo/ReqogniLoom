---
name: risk-derivation
description: Use when identifying risks and linking them to the requirements or architecture elements they threaten in a ReqogniLoom workspace, manually or LLM-assisted from architecture.
---

# Risk Derivation

See [DOMAIN_MODEL.md](../../DOMAIN_MODEL.md) for the REQ-ID schema and trace-link types referenced
below.

## Workflow

1. `workspace.get_context` — learn the active rigor preset (it affects which fields a risk record
   must carry, e.g. `extended` typically requires a documented likelihood/impact/mitigation
   triad); `custom_field.get`/`custom_field.query` for anything beyond that.
2. Use `requirement.get`/`requirement.query` and `architecture.get`/`architecture.query` to
   understand the element you're assessing; `diagram.get`/`diagram.query` show its visual layout
   for additional context.
3. `artifact.search` and `traceability.query` surface risks that may already exist for a given
   element — don't duplicate.
4. `ai_derivation.derive_risks_from_architecture` asks the LLM adapter to propose candidate risks
   for a given architecture element — use it to seed a review pass, not as a final risk record;
   always assess likelihood/impact/mitigation yourself before recording anything.
5. Create the risk with `risk.create` (likelihood, impact, mitigation, and the linked
   requirement/architecture IDs); refine with `risk.update` as assessment matures, and `risk.read`
   fetches a single risk by ID when you already know which one you're revisiting. Risk-to-entity
   linking for the primary threatened element is driven by fields on the risk itself; use
   `traceability.create_link` directly (link_type `traces` — the generic, unrestricted association;
   ReqogniLoom has no dedicated `related-to`/`conflicts-with` link type) when a risk needs an
   additional relationship beyond that primary one, and record the nature of the relationship in
   the risk's own description. `risk.delete` is for a risk record created in
   error only, never as a way to "close" a risk that turned out real and mitigated — a mitigated
   risk stays on record with its mitigation documented.
6. Re-check `traceability.query` after any create/update to confirm the resulting link graph
   matches your intent.
