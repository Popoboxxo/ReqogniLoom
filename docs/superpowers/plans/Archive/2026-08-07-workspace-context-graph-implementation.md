# Workspace Context Graph — v1 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Full rationale, rejected alternatives, and the answered
> product decisions live in `docs/superpowers/plans/Archive/2026-08-07-workspace-context-graph-scoping.md`
> — this plan is the executable v1 slice of that document (its own §9 "Empfohlene Phasierung").
> Where a task brief says "see scoping §X", that section is background/rationale — every value
> an implementer needs to write code is inlined in the task itself.

**Issue:** Popoboxxo/ReqogniLoom#377 — v1 slice only (embedded-only, event-sourced, one
workspace-scoped read, one edge generator). Follow-up issues A–E (embedding-based edges, cron
scheduling, UI graph view, cross-workspace visibility, external Graphify/Honcho connectors) are
explicitly out of scope for this plan — file them separately once v1 ships.

**Goal:** Prove the full chain — artifact/trace-link mutation → outbox event → projector →
derived `ContextEdge` → MCP read — on exactly one generator (`glossary`/`shares-term`) whose
correctness a human can verify by inspection. Everything else is additive on top of a working
spine.

**Architecture:** No new graph store. `pl_artifact` + `pl_tracelink` stay the graph; hard-edge
traversal reuses `traceability/service.py` and `traceability/query_engine.py` unchanged. Two new
tables in a new Layer-1 app `backend/context_graph/` (parallel to `traceability/`, `baseline/`,
`workflow/`, per ADR-01's single-entry-point discipline — REST/MCP talk only to a new Layer-2
facade `application/context_service.py`, never to `context_graph/` directly): `ContextEdge`
(derived, machine-suggested edges) and `WorkspaceContextSettings` (config + operational
watermark state). Exactly one new subscriber (`ContextGraphProjector`) on the **existing**
`application/event_bus.py` Transactional Outbox — not a second event system, and not to be
confused with the separate, identically-named `audit/events.py::DomainEventBus` (audit-only, no
outbox, do not import it here).

**Tech Stack:** No new runtime dependency. PostgreSQL 16 (existing RLS pattern), Redis 7 (existing
cache), Celery 5.3 (existing outbox-poll beat task). pgvector exists but is **not used in v1** —
the v1 generator is deterministic (glossary term matching), no embeddings involved.

## Global Constraints

- **Do not build a second graph store or a nodes/edges table pair that duplicates `pl_artifact`/
  `pl_tracelink`.** `ContextEdge` stores only *derived* edges Origin-tagged as machine-suggested
  — it is additive to the hard-edge graph, never a replacement or a cache of it.
- **`ContextEdge` rows are never written to `pl_tracelink` and never given a `LinkType` value.**
  `LinkType` feeds `SE_LINK_SEMANTICS`, `traceability/coverage_calculator.py`, VCRM reports,
  baseline snapshots, and the SE-Auditor — a machine-guessed edge silently entering any of those
  is a correctness/integrity failure, not a style choice. This is the single most important
  constraint in this plan; violating it in any task is a blocking finding, not a minor one.
- **Coverage, VCRM, and every SE-Auditor/baseline calculation continue reading exclusively from
  `pl_tracelink`.** No task in this plan may add `ContextEdge` as an input to any of those
  calculations, even indirectly.
- **The event subscriber goes on `application/event_bus.py`'s `DomainEventBus`
  (`get_event_bus().register_subscriber(...)`), never on `audit/events.py`'s `DomainEventBus`.**
  Same class name, completely different mechanism (no outbox, audit-only) — importing the wrong
  one is a silent no-op bug, not an import error.
- **The projector must never make an LLM or embedding call inline.** It runs in the
  `dispatch_outbox_events` Celery-beat callback on the `events` queue, which is explicitly
  latency-sensitive (5-second tick, per `reqogniloom/celery.py`'s own comment). v1's generator
  (glossary term matching) is deterministic and cheap, so this constraint is naturally satisfied
  in v1 — but do not add a network-calling generator to this queue in a later task without
  first adding the `default`-queue delegation this constraint requires.
- **`WorkspaceContextSettings` follows the "missing row = feature off, defaults apply" rule —
  the opposite of `LlmSettings`' "row existence overrides config" rule (Issue #276).** A read
  path must never create a settings row as a side effect. Only an explicit settings-write path
  (the toggle UI, Task 9) creates the row.
- **New tenant-scoped tables require RLS in the same migration that creates them** — follow
  `0026_add_llm_settings.py`'s exact pattern (`ENABLE ROW LEVEL SECURITY` + `CREATE POLICY …
  USING (current_setting('app.current_tenant', true))`) for both `ContextEdge` and
  `WorkspaceContextSettings`. DDL runs under the DB-owner role, not the least-privilege runtime
  role — note this in migration test setup if it trips.
- **`contradicts` as an edge kind is not built in v1 at all.** It is explicitly deferred pending
  a decision on whether it may ever be materialized (resolved: never — only as a
  human-adopted suggestion, out of scope for this plan entirely). Do not add `"contradicts"` to
  `ContextEdge.edge_kind`'s choices in this plan.
- **Backend tests** run via
  `docker-compose exec -e DB_USER=reqflow -e DB_PASSWORD=110d00b8a6d252019093c264e4ef4571 backend python -m pytest <path> -v --create-db`.
  Verify `pip show pytest-django` inside the container shows `4.12.0` before trusting a red
  result.
- **Any MCP tool addition requires regenerating** `docs/agent-templates/tool-manifest.json`
  (`docker-compose exec backend python manage.py export_tool_manifest`) in the same task's
  commit — `backend/mcp_server/tests/test_tool_manifest_drift.py` fails CI otherwise.
- Git mutations only via commit at the end of each task, on the branch already checked out by
  the controller.

---

## File Structure

```
backend/context_graph/                          # new Layer-1 app
  __init__.py
  apps.py                                        # Task 1 — registers ContextGraphProjector
  models.py                                      # Task 3 — ContextEdge, WorkspaceContextSettings
  migrations/0001_initial.py                     # Task 3 — models + RLS
  projector.py                                   # Task 1 (skeleton+registration), Task 4 (logic)
  generators/
    __init__.py
    glossary.py                                  # Task 5 — shares-term generator
  admin_ops.py                                   # Task 8 — rebuild logic
backend/application/
  context_service.py                             # Task 6 — Layer-2 facade
  event_bus.py                                   # unchanged, read-only reference
  trace_link_service.py                           # Task 2 — emit TraceLink* events
  models.py                                       # Task 2 — new EventType values
backend/mcp_server/tools/
  context.py                                      # Task 7 — new ContextToolGroup
backend/reqogniloom/
  settings.py                                     # Task 9 (no beat entry in v1 — cron is Folge-Issue B)
frontend/src/components/WorkspaceSettings/
  ContextGraphSettingsSection.tsx (or similar)     # Task 9
```

---

### Task 1: Prove the subscriber-registration path in production

**Model:** `sonnet` (standard — this task exists specifically because the mechanism is
unproven; needs a real integration test through the actual Celery/outbox machinery, not a mock).

**Why this is Task 1, before any real logic exists:** `application/webhook_dispatcher.py` is the
only subscriber ever written against `application/event_bus.py`'s `DomainEventBus`, and its
`subscribe_to_events()` method is called **only from its own test file** — never from any
`apps.py::ready()`, never from any startup path. The outbox poller has been dispatching into a
production void since the bus was built. This task proves the registration mechanism works at
all, on a trivial no-op subscriber, before Task 4 puts real logic behind it.

**1.** Create `backend/context_graph/` as a new Django app (`__init__.py`, `apps.py`,
`models.py` empty for now — Task 3 fills it in), registered in `INSTALLED_APPS`
(`backend/reqogniloom/settings.py`).

**2. `backend/context_graph/apps.py`**:
```python
class ContextGraphConfig(AppConfig):
    name = "context_graph"

    def ready(self) -> None:
        from context_graph.projector import register_projector_on_event_bus
        register_projector_on_event_bus()
```
Formally identical in shape to `backend/audit/apps.py::AuditConfig.ready()` — but this one calls
`application.event_bus.get_event_bus().register_subscriber(...)`, **not** `audit.events`.

**3. `backend/context_graph/projector.py`** (skeleton for this task — Task 4 fills in real
logic):
```python
class ContextGraphProjector:
    def handle_event(self, event) -> None:
        logger.info("ContextGraphProjector received event: %s", event.event_type)
        # Task 4 fills in the real body

def register_projector_on_event_bus() -> None:
    get_event_bus().register_subscriber("<placeholder-event-type>", ContextGraphProjector().handle_event)
```
The exact event-type string used to register is a placeholder for this task — Task 2 defines
the real `TraceLinkCreated`/etc. types this eventually subscribes to; this task's registration
call may target any existing, already-emitted event type (e.g. `RequirementCreated`) purely to
prove the wiring, and Task 4 will change it to the real set.

**4. Integration test (the actual point of this task):** a test that performs a real mutation
(e.g. creates a `Requirement` through the real service layer, inside a real transaction that
commits), lets the real `poll_and_dispatch()` run (not mocked), and asserts
`ContextGraphProjector.handle_event` was actually invoked (e.g. via a call-counter or a captured
log line) — proving the full chain: mutation → `transaction.on_commit` → outbox INSERT →
`poll_and_dispatch` → `dispatch_to_subscribers` → this projector. This is the single test in
this entire plan that has never existed for this event bus and must not be skipped or mocked
away, per the pattern that let `webhook_dispatcher.py`'s dead registration go unnoticed.

**Done when:** the integration test passes against the real (test) database and the real outbox
poller, proving end-to-end delivery for the first time in this codebase's history.

---

### Task 2: TraceLink domain events + event-catalog consistency

**Model:** `sonnet` (standard — touches a shared service used by many callers; must not change
existing behavior for any caller that doesn't care about events).

Independent of Task 1; both can be reviewed before either depends on the other, but Task 4 needs
this task's event types to exist.

**1. `backend/application/models.py`** — add to `DomainEventOutbox.EventType`:
```python
TRACE_LINK_CREATED = "TraceLinkCreated"
TRACE_LINK_UPDATED = "TraceLinkUpdated"
TRACE_LINK_DELETED = "TraceLinkDeleted"
```
Also add the three currently-undeclared-but-already-emitted types found during scoping (purely
additive, no behavior change — they're already being written to the outbox as bare strings that
don't match any `choices` entry):
```python
STAKEHOLDER_NEED_CREATED = "StakeholderNeedCreated"
STAKEHOLDER_NEED_UPDATED = "StakeholderNeedUpdated"
STAKEHOLDER_NEED_DELETED = "StakeholderNeedDeleted"
GOAL_CREATED = "GoalCreated"
MAIN_GOAL_CREATED = "MainGoalCreated"
```
(Adjust exact naming to match this codebase's existing `EventType` enum-value string convention
— read the existing entries first and mirror their exact casing/format, don't guess.)

**2. `backend/application/trace_link_service.py`** — emit the new events from `create`, `update`,
`delete`, `batch_create_trace_links`, and `batch_delete_trace_links`, using this service's
existing `_emit_event`/`_make_event` seam (`application/base.py`) — the same mechanism every
other `*_service.py` already uses, not a new one. Batch paths emit one event per affected link,
not one batched event (keep the projector's per-artifact re-derivation simple, see Task 4).

**3. Every event producer that emits `RequirementCreated`/`ArchitectureElementCreated`/etc.
(and the new events from step 2)** — ensure `payload["artifact_id"]` is set to the resolved
`Artifact.id`, additively, alongside whatever `entity_id` semantics that producer already uses.
Do not change `entity_id`'s existing meaning for any producer (some use the domain entity's own
id, some use the artifact id — that inconsistency is out of scope to fix everywhere; only
`artifact_id` needs to be reliably present going forward). For `TraceLink` events specifically,
`artifact_id` is not meaningful the same way (a link has a source AND a target artifact) — use
`payload["source_artifact_id"]` and `payload["target_artifact_id"]` instead for these three new
event types specifically.

**Tests:** a test per new event type proving it's now in `EventType.choices` (was previously
emitted as a bare string not matching any choice); a test that
`create`/`update`/`delete`/`batch_create_trace_links`/`batch_delete_trace_links` on
`trace_link_service.py` each emit the corresponding new event with `source_artifact_id`/
`target_artifact_id` populated; a test confirming no existing caller/test of
`trace_link_service.py` broke (run the full existing test file, not just the new tests).

**Done when:** `TraceLinkCreated`/`Updated`/`Deleted` exist in `EventType.choices` and are
emitted from all five `trace_link_service.py` write paths with `source_artifact_id`/
`target_artifact_id`; the three previously-undeclared Need/Goal event strings are now declared.

**Must not break:** any existing test asserting `trace_link_service.py`'s return values or DB
side effects — this task only adds event emission, changes nothing else about these methods'
behavior.

---

### Task 3: `context_graph` app — `ContextEdge` + `WorkspaceContextSettings` models

**Model:** `haiku` (mechanical — model definitions with exact fields given below, migration
following an established RLS pattern).

Independent of Tasks 1-2 (pure schema); Task 4 needs these models to exist.

**1. `backend/context_graph/models.py`**:

```python
class ContextEdge(TenantScopedModel):  # or this repo's exact tenant-scoping base class — check persistence/models.py for the actual base other tenant-scoped models use
    source = models.ForeignKey("persistence.Artifact", on_delete=models.CASCADE, related_name="context_edges_from")
    target = models.ForeignKey("persistence.Artifact", on_delete=models.CASCADE, related_name="context_edges_to")
    edge_kind = models.CharField(max_length=32, choices=[
        ("related", "Related"),
        ("influences", "Influences"),
        ("refines", "Refines"),
        ("shares-term", "Shares Term"),
        # NOTE: "contradicts" is intentionally NOT here — see Global Constraints.
    ])
    origin = models.CharField(max_length=32, choices=[
        ("derived-glossary", "Derived: Glossary"),
        ("derived-embedding", "Derived: Embedding"),
        ("derived-cochange", "Derived: Co-change"),
        ("llm-suggested", "LLM Suggested"),
    ])
    confidence = models.FloatField()  # 0..1
    evidence = models.JSONField(default=dict)  # e.g. {"term_id": "...", "cosine": 0.83}
    generator = models.CharField(max_length=64)  # generator name + version, for targeted invalidation
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cg_context_edge"
        constraints = [
            models.UniqueConstraint(fields=["source", "target", "edge_kind", "origin"], name="uq_context_edge"),
        ]
        indexes = [
            models.Index(fields=["tenant", "source"]),
            models.Index(fields=["tenant", "target"]),
            models.Index(fields=["tenant", "edge_kind"]),
        ]


class WorkspaceContextSettings(TenantScopedModel):
    workspace = models.OneToOneField("persistence.Workspace", on_delete=models.CASCADE, unique=True)
    enabled = models.BooleanField(default=False)              # event-sourced maintenance on/off
    schedule_enabled = models.BooleanField(default=False)      # NOT used until Folge-Issue B (cron) — field exists for forward-compat, no scheduler reads it in v1
    refresh_interval_minutes = models.IntegerField(null=True, blank=True)  # unused in v1, see above
    provider = models.CharField(max_length=32, default="embedded")  # ONLY "embedded" is a valid/accepted value in v1 — reject anything else at the settings-write path (Task 9), do not build a provider registry
    enabled_generators = models.JSONField(default=list)        # e.g. ["glossary"]
    last_projected_at = models.DateTimeField(null=True, blank=True)
    last_refresh_at = models.DateTimeField(null=True, blank=True)
    last_event_id = models.UUIDField(null=True, blank=True)     # watermark
    last_error = models.TextField(blank=True)
    node_count = models.IntegerField(default=0)
    edge_count = models.IntegerField(default=0)

    class Meta:
        db_table = "cg_workspace_context_settings"
```

Check `persistence/models.py` for this repo's actual tenant-scoping base class name/pattern (the
brief above uses a placeholder `TenantScopedModel` — use whatever `LlmSettings` and other
tenant-scoped models actually inherit from) and mirror it exactly, including its RLS migration
convention.

**2. Migration** `backend/context_graph/migrations/0001_initial.py` — creates both tables, and in
the **same migration** (not a follow-up one): `ALTER TABLE cg_context_edge ENABLE ROW LEVEL
SECURITY` + `CREATE POLICY ... USING (current_setting('app.current_tenant', true))`, and the same
for `cg_workspace_context_settings` — copy `0026_add_llm_settings.py`'s exact RLS migration
pattern.

**Tests:** RLS test proving a query under `reqogniloom_app` role with `app.current_tenant` set to
tenant A cannot see tenant B's `ContextEdge`/`WorkspaceContextSettings` rows (mirror whatever
existing RLS test pattern this repo uses, e.g. for `LlmSettings`); a test proving `Diagram.artifact`-style — no wait, not relevant here — a test proving `WorkspaceContextSettings` for a workspace with no row returns "feature off" defaults from the service layer (Task 6), not an error and not an auto-created row; a uniqueness test on `ContextEdge`'s `(source, target, edge_kind, origin)` constraint.

**Done when:** both tables exist with RLS enabled; a migration test confirms tenant isolation.

---

### Task 4: `ContextGraphProjector` — real logic

**Model:** `sonnet` (standard — idempotency and error-isolation logic needs careful test
coverage, this is the correctness-critical task in the plan).

Depends on Task 1 (registration skeleton), Task 2 (the events to subscribe to), Task 3 (the
models to write).

**1. `backend/context_graph/projector.py`** — replace Task 1's placeholder registration with the
real subscription: register for `TRACE_LINK_CREATED`, `TRACE_LINK_UPDATED`, `TRACE_LINK_DELETED`,
and every `*Created`/`*Updated`/`*Deleted` event type already in `EventType.choices` that carries
an `artifact_id` (i.e., every artifact-producing service's events — enumerate `EventType.choices`
programmatically rather than hardcoding a list that will drift).

`handle_event(event) -> None` body:
```
1. workspace_id = resolve from event payload (via the artifact's workspace — artifacts carry
   a workspace FK; resolve artifact_id -> Artifact.objects.get(pk=...).workspace_id, or use
   event.payload["workspace_id"] if the producer already includes it)
2. settings = WorkspaceContextSettings.objects.filter(workspace_id=workspace_id).first()
   (cache this lookup in Redis, short TTL, per scoping §3.1 — a Redis miss just re-queries)
   -> if settings is None or not settings.enabled: return immediately (not an error — an event
      for a disabled workspace is considered "handled")
3. artifact_id = resolve the affected artifact's id from the event (source_artifact_id AND
   target_artifact_id for TraceLink* events -> re-derive for BOTH ends; artifact_id for all
   other event types -> re-derive for that one artifact)
4. For the affected artifact(s): call each enabled generator (v1: just
   context_graph.generators.glossary.generate_for_artifact(artifact_id)) to get the full set of
   ContextEdge rows that generator currently believes should exist for that artifact — full
   recomputation, not incremental delta (idempotency requirement, see below)
5. Upsert: for each (source, target, edge_kind, origin) the generator returned, get_or_create /
   update_or_create against the UniqueConstraint from Task 3. Delete any existing ContextEdge
   row with origin="derived-glossary" (or whichever generator ran) for that artifact that the
   generator's fresh run did NOT return (stale edge cleanup) -- but ONLY rows with that specific
   origin/generator, never touch rows from a different generator/origin.
6. settings.last_event_id = event.event_id; settings.last_projected_at = now(); settings.save()
```

**2. Idempotency:** `poll_and_dispatch()` is documented *at-least-once* delivery — a worker crash
after dispatch but before the outbox row is marked published re-delivers the event. The
upsert-on-unique-constraint + full-recomputation-per-artifact design (not incremental
delta/counter) in step 5 is what makes re-delivery safe: replaying the same event twice produces
the same final `ContextEdge` set both times.

**3. Error isolation:** the bus already logs and swallows subscriber exceptions
(`dispatch_to_subscribers`) so one failing event doesn't block others. This projector must
additionally write `settings.last_error = str(exc)` (in a `try/except` around the body, saving
`last_error` on failure) so a silently-failing projector is visible in `WorkspaceContextSettings`
— surfaced later in the settings UI (Task 9) and in every `context.*` MCP response's `stale`
field (Task 7).

**4. Queue placement:** confirm (do not need to change, just verify and note in the report) that
this subscriber runs on the outbox poller's existing `events` queue and makes zero network/LLM/
embedding calls — the glossary generator is pure DB queries.

**Tests:** re-delivering the same event twice produces the identical final `ContextEdge` set
(no duplicate rows, no drift) — the core idempotency test; an event for a workspace with
`enabled=False` (or no settings row) produces zero `ContextEdge` writes and no error; a
generator exception is caught, recorded in `settings.last_error`, and does not prevent
`last_event_id`/`last_projected_at` from other successful events being updated; deleting a
`ContextEdge`'s underlying justification (e.g. removing the shared glossary term) and
re-triggering the projector removes the now-stale edge without touching edges from a different
generator/origin on the same artifact.

**Done when:** the full chain (real mutation → outbox → projector → `ContextEdge` upsert) is
proven end-to-end for at least one artifact type, replay-safe, and workspace-toggle-respecting.

---

### Task 5: Generator — `glossary` / `shares-term`

**Model:** `sonnet` (standard — needs correct, human-verifiable term-matching logic; this is the
generator whose output a human must be able to eyeball and immediately judge right or wrong, per
the scoping doc's rationale for choosing it as the v1 proof generator).

Depends on Task 3 (models) and Task 4's interface (`generate_for_artifact(artifact_id) ->
list[ContextEdgeCandidate]`, called by the projector — define the exact candidate shape this
function returns to match what Task 4 step 5 upserts).

**1. `backend/context_graph/generators/glossary.py`** — deterministic, no LLM, no embeddings:
`generate_for_artifact(artifact_id: UUID) -> list[ContextEdgeCandidate]`. Reuses the existing
`uses-term` `LinkType` and `GlossaryTerm.synonyms` field (both already exist in this codebase,
per scoping §9 — confirm their exact current shape by reading `traceability/types.py` and
`persistence/models.py::GlossaryTerm` before writing the generator, do not assume field names).
Logic: find every `GlossaryTerm` this artifact already has a `uses-term` `TraceLink` to (or
whose name/synonym appears in the artifact's title/description — pick the simpler, more
literal approach: reuse existing `uses-term` links rather than re-implementing term detection,
since that's already solved elsewhere in this codebase); for every *other* artifact that also
has a `uses-term` link to the same `GlossaryTerm`, emit a candidate edge
`(source=this_artifact, target=other_artifact, edge_kind="shares-term",
origin="derived-glossary", confidence=1.0, evidence={"term_id": ..., "term_name": ...},
generator="glossary-v1")`. Confidence is always `1.0` for this generator — it is deterministic,
not probabilistic (unlike a future embedding-based generator).

**Tests:** two artifacts sharing a `uses-term` link to the same `GlossaryTerm` produce a
`shares-term` `ContextEdge` between them (both directions, or one directed edge — decide and
document which, consistent with how `ContextEdge.source`/`target` are read elsewhere; if
undirected in meaning, still store one row per unordered pair, not two); an artifact with no
shared terms produces zero candidates; the `evidence` field contains enough information for a
human to verify the claim by inspection (the term name, not just its id).

**Done when:** the generator's output for a hand-constructed fixture (two Requirements sharing
one glossary term) is a `ContextEdge` a human can look at and immediately confirm is correct.

---

### Task 6: `ContextService` facade — read path + cache

**Model:** `sonnet` (standard — composes existing traceability APIs, needs correct
tenant/workspace scoping, cache-key design).

Depends on Task 3 (models exist to read).

**1. `backend/application/context_service.py`** (new Layer-2 facade, per ADR-01 — REST/MCP call
only this, never `context_graph/` directly):

```python
def get_context(artifact_id: UUID, ctx: AuthContext, depth: int = 2, include: list[str] | None = None, max_nodes: int = 50) -> ContextResult:
    """Hard edges via traceability.service.impact_analysis(); soft edges via ContextEdge."""

def get_related(artifact_id: UUID, ctx: AuthContext, edge_kinds: list[str] | None = None, min_confidence: float = 0.5, limit: int = 10) -> RelatedResult:
    """Soft edges only, from ContextEdge, scope="workspace" only in v1 (scope="tenant" is Folge-Issue D — reject it explicitly with a clear error if requested, do not silently narrow to workspace)."""
```

- `get_context`'s hard-edge portion calls `traceability.service.impact_analysis()` — **the same
  Layer-1 API `traceability.query`/`traceability.suggest_links` already call**. Do not write a
  second traversal implementation.
- `get_context`'s soft-edge portion is an indexed point query against `ContextEdge` (no
  recursive CTE needed — direct edges only in v1, `depth` applies only to the hard-edge side via
  `impact_analysis`'s existing depth parameter).
- Enrichment (titles/UIDs) reuses `traceability.service._enrich()` (or its public equivalent) —
  do not duplicate that lookup.
- Cache: `django.core.cache` (Redis, `settings.CACHES`), key = `(artifact_id, depth, include-set)`,
  invalidated by comparing against `WorkspaceContextSettings.last_event_id` (the watermark) —
  a cache entry older than the current watermark is treated as a miss. Every returned result
  carries `stale: bool` (true if the workspace's projector `last_error` is set, or if
  `enabled=False`/no settings row exists — meaning the soft-edge portion is known-incomplete)
  and `generated_at: datetime`.
- RBAC/tenant scoping: resolve tenant/workspace from `ctx: AuthContext` exactly as every other
  `application/*_service.py` method does — no special-casing.

**Tests:** `get_context` on an artifact with both a hard trace-link and a `ContextEdge` returns
both, correctly separated into their own response fields (never merged into one undifferentiated
list — the reconciler/UI distinction from the resolved §11.1 decision depends on this); a
workspace with no `WorkspaceContextSettings` row returns `stale=true` and an empty soft-edge list
(not an error); cache hit/miss behavior against the watermark; `get_related(scope="tenant")`
raises/rejects cleanly (not silently narrowed) since that's Folge-Issue D, not v1.

**Done when:** both facade functions work end-to-end against Task 3's models and the existing
`traceability.service` APIs, with correct caching and staleness reporting.

---

### Task 7: `context.query` and `context.related` MCP tools

**Model:** `haiku` (mechanical — thin MCP wrapper over Task 6's already-built facade; no new
business logic).

Depends on Task 6.

**1. `backend/mcp_server/tools/context.py`** (new `ContextToolGroup`, prefix `context`, **both
tools read-only** — explicitly **not** added to `_WRITE_TOOL_PREFIXES` in `tool_registry.py`, no
editor role required):

```
context.query
  artifact_id  : uuid (required)
  workspace_id : uuid (optional; resolved from artifact if omitted)
  depth        : int 1..3, default 2
  include      : ["upstream","downstream","semantic","risks","issues"], default all
  max_nodes    : int, default 50, hard-capped
  -> { artifact: {...}, upstream: [...], downstream: [...], semantic: [...],
       open_risks: [...], open_issues: [...], stale: bool, generated_at: iso8601, truncated: bool }

context.related
  artifact_id    : uuid (required)
  edge_kinds     : [str] (optional)
  min_confidence : float, default 0.5
  scope          : "workspace" (only valid value in v1 — "tenant" is rejected with a clear
                    error naming Folge-Issue D as the reason, not silently coerced)
  limit          : int, default 10, max 50
  -> { related: [...], scope: "workspace", truncated: bool }
```

**Note the tool description must state the artifact-orientation explicitly in its first
sentence** (e.g. "Returns context for a single artifact — for workspace-level orientation, use
`workspace.get_context` instead") — per the resolved §11.8 decision, this is the mitigation for
the confirmed naming collision risk with the existing `workspace.get_context` tool.

**2.** No top-level `content` key in the response payload (collides with the MCP envelope).
Empty results are an empty list, never a missing field.

**3.** Regenerate `tool-manifest.json` in this task's commit; confirm
`test_tool_manifest_drift.py` passes.

**Tests:** MCP schema test for both tools; a test that `context.related(scope="tenant")` returns
a clear rejection, not data; a test that an empty result set returns `related: []`, not a missing
key.

**Done when:** `test_tool_manifest_drift` passes; both tools are callable end-to-end against
Task 6's facade with correctly-shaped responses.

---

### Task 8: `context.rebuild` admin path

**Model:** `sonnet` (standard — this is the toggle-without-replay mechanism; needs to correctly
run every enabled generator over every artifact in a workspace without missing any).

Depends on Task 4 (the projector/generator interface) and Task 3 (settings model).

**Why this exists:** the outbox is not a retention log — re-enabling a previously-disabled
workspace cannot "catch up" by replaying old events (published rows aren't guaranteed retained,
and this isn't a documented contract even where they currently are). Enabling `context_graph`
for a workspace must trigger a **full rebuild from current state**, not from the event stream.

**1. `backend/context_graph/admin_ops.py`** — `rebuild_workspace_graph(workspace_id: UUID) ->
RebuildResult`: iterate every `Artifact` in the workspace, call every enabled generator
(`WorkspaceContextSettings.enabled_generators`) for each, upsert via the same Task 4 step 5
mechanism (reuse it, do not duplicate). Update `node_count`/`edge_count`/`last_projected_at` on
completion.

**2.** Expose as an MCP tool or a management command (decide based on what fits — this is an
admin/operator action, likely a Django management command
`python manage.py rebuild_context_graph --workspace <uuid>` is sufficient for v1 rather than a
new MCP write tool; if a management command, no manifest regeneration needed).

**3.** Wire it as the action the settings toggle (Task 9) triggers when a workspace transitions
from `enabled=False` to `enabled=True`.

**Tests:** rebuilding a workspace with N artifacts and M shared-glossary-term pairs produces
exactly M `ContextEdge` rows (no duplicates, no missed pairs); rebuilding twice is idempotent
(second run produces the same row count, no drift); rebuilding a workspace with
`enabled_generators=[]` produces zero edges without error.

**Done when:** a full rebuild over a fixture workspace produces the correct edge set and is
idempotent on repeat.

---

### Task 9: Per-workspace settings toggle (UI)

**Model:** `sonnet` (standard — frontend + a thin backend settings-write endpoint, needs the
"missing row = off" discipline respected exactly).

Depends on Task 3 (settings model), Task 8 (rebuild trigger on enable).

**1. Backend:** a settings-write path (REST endpoint or reuse an existing workspace-settings
pattern in this codebase) that creates/updates a workspace's `WorkspaceContextSettings` row.
Creating the row for the first time with `enabled=True` triggers Task 8's rebuild (async, via
Celery — do not run a potentially-large rebuild synchronously in the request/response cycle).
Setting `enabled=False` does not delete existing `ContextEdge` rows (they simply stop being
refreshed) — confirm this matches the toggle semantics described in scoping §3.4.

**2. Frontend:** `frontend/src/components/WorkspaceSettings/` already exists as the correct
location (not `SystemSettings`, which is tenant-wide) — add a new section with an on/off toggle
for `enabled`, a read-only display of `last_projected_at`/`node_count`/`edge_count`/`last_error`
(operational visibility, not just configuration), and a manual "Rebuild now" button calling
Task 8's path directly (useful for testing and for recovering from a `last_error` state without
waiting for the next mutation). `schedule_enabled`/`refresh_interval_minutes` fields exist on the
model (Task 3) but **this task does not surface them in the UI** — they're unused until
Folge-Issue B (cron), and shipping a UI control for a setting nothing reads yet is misleading.

**Tests:** toggling on for a workspace with no prior settings row creates one and triggers a
rebuild; the UI displays `last_error` when the projector has failed; toggling off does not
delete `ContextEdge` rows (assert row count unchanged); `data-testid` on the toggle and rebuild
button (project convention).

**Done when:** a user can enable/disable the feature per workspace from `WorkspaceSettings/`,
see operational status, and manually trigger a rebuild — completing the v1 acceptance criteria
this issue's product owner confirmed (event-sourced maintenance, per-workspace on/off,
`context.query`/`context.related` returning context including semantic relationships).
