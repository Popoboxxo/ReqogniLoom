---
name: ccb-approval-and-baseline
description: Use when recording architectural decisions (ADRs), tracking issues, running a Change Control Board approval, or creating a baseline in a ReqogniLoom workspace.
---

# CCB Approval and Baseline Management

See [DOMAIN_MODEL.md](../../DOMAIN_MODEL.md) for the REQ-ID schema, trace-link types, and baseline
scopes referenced below.

## Workflow

1. `workspace.get_context` — learn the active state machine and rigor preset; a workspace defines
   its own set of legal transitions for requirements/architecture (e.g.
   `draft -> in_review -> approved -> baselined`) — never assume a fixed chain.
2. Record decisions with `adr.create`/`adr.update`. Prefer `adr.outdate` (reversible via
   `adr.reactivate`) over `adr.delete` for a decision that's no longer active but wasn't wrong when
   made — `adr.delete` is for genuine entry errors only; a superseded decision gets a new ADR with
   a `SUPERCEDES` link, the old one stays on record. Apply the same outdate-vs-delete distinction
   to `issue.outdate`/`issue.reactivate` vs `issue.delete` for issue tracking — `issue.update`
   refines an existing issue record (e.g. status, severity) without touching its lifecycle state.
3. For a change that needs Change Control Board sign-off: `change_request.create` records what's
   changing and against which baseline, `change_request.update` refines the description/scope
   while it's still pending — check `baseline.get`/`baseline.compare` first to confirm you're
   evaluating against the right one; `baseline.list` finds the baseline to compare against when you
   don't already have its ID. ReqogniLoom enforces separation of duties server-side: you cannot
   approve a Change Request you created yourself, and `review.approve` against your own
   `change_request.create` is expected to be rejected, not something this skill pre-checks.
4. `review.list_pending` shows the approval queue; act on each with `review.approve`,
   `review.reject`, or `review.request_changes` (sends it back for rework without a final verdict).
5. Once a Change Request is approved, apply it with `requirement.update`/`architecture.update`/
   `diagram.update` (or `diagram.create` if the approved change introduces a new diagram) —
   `diagram.*` is the visual layer of the same architecture domain, update both when an approved
   change affects a diagram representation. Use `diagram.outdate`/`diagram.reactivate` the same
   way as ADRs/issues above when a diagram is superseded rather than wrong. `change_request.delete`
   is deliberately not part of this workflow — a rejected or erroneous Change Request is tracked
   via `review.reject` or `change_request.outdate`/`.reactivate`, never hard-deleted, mirroring the
   ADR philosophy above.
6. Once a batch of approved changes is stable, `baseline.create` snapshots the affected elements —
   deciding when a batch is baseline-worthy is a judgment call here, not something that happens
   automatically on approval.
7. Use `traceability.query` to see the existing link graph before changing an element,
   `traceability.suggest_links` to find candidate ADR/requirement/issue relationships you may have
   missed, and `traceability.create_link` to record one explicitly (e.g. a `SUPERCEDES` link
   between ADR versions).
8. `artifact.search` locates the requirement/architecture/ADR/issue/Change Request you need when
   you don't have an exact ID.
