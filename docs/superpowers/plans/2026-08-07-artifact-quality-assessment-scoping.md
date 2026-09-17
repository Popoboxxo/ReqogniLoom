# Artifact Quality Assessment — Scoping & Design (Issue #378)

> **Scoping document only.** No implementation, no branch, no migration. Every claim below was verified
> against the tree at commit `7752f717` (branch `feat/mcp-plugin-distribution`); file:line references are
> the evidence. The follow-up implementation plan (superpowers-style, task-by-task) is a separate document.

**Goal:** Add an *inhaltliche* (content-level) quality score per artifact — "is this Requirement atomic,
testable, unambiguous?" — on top of the SE-Auditor, which today checks only structural trace/verification
rules. Scores are produced by an LLM call against a **per-workspace overridable prompt slot**, persisted as
append-only history, and readable via MCP, REST and the UI.

**Architecture:** A new Layer-2 `QualityAssessmentService` (ADR-01 single entry point) resolves a prompt
slot through the *existing* factory → tenant-global → workspace-override chain
(`AiDerivationService._get_template_content`), calls `provider.complete()` through the same cached,
timeout-guarded, circuit-broken path the eight derive flows already use, and writes one append-only
`QualityAssessment` row per run. Layer-3 gets a `quality.*` MCP tool group and a `quality_views.py`
REST module, both thin translations over the facade. Trigger modes 2 and 3 (auto / periodic) attach to the
**existing domain-event outbox** and the **existing Celery Beat service** — no new infrastructure. SE-Auditor
integration is a new `QUAL-*` rule that reads *persisted rows only* and never calls an LLM inside
`Rule.check()`.

**Tech Stack:** Python 3.x / Django 4.2 (new model + migration in the `application` app, RLS policy per the
`application/0013` precedent), Celery 5.3 (`llm` queue, `celery-beat` service already deployed),
React 18 + TS strict (badge + panel), i18n de/en. No new runtime dependency.

---

## Global Constraints

- **Never call an LLM inside `Rule.check()`.** `RuleEngine._run_rule`
  (`backend/traceability/audit/rule_engine.py`) has no error isolation and `AuditService.blocking_findings`
  runs on the **baseline-creation path** (`backend/application/baseline_facade.py:101`). A rule that calls a
  provider makes every `GET /audit/` and every `POST /baselines/` LLM-latency-bound and provider-failure-fatal.
  QUAL rules read persisted `QualityAssessment` rows only.
- **Never call an LLM inside a request thread that a user is waiting on for an unrelated write.** Auto-assess
  on transition/update must enqueue a Celery task; a `WorkflowFacade.transition()` that blocks on a 25s
  provider call turns a status change into a timeout.
- **Never call an LLM inside an outbox subscriber.** `poll_and_dispatch` is the beat task that drains the
  outbox every 5 s and dispatches subscribers with a 30 s cap
  (`backend/application/event_bus.py`, `DomainEventBus.dispatch_to_subscribers`). A subscriber that assesses
  inline stalls the entire event pipeline for every tenant. Subscribers enqueue; workers execute.
- **No direct ORM access in `rest_api/`.** REQ-066 has a ratchet test capping direct ORM calls in
  `rest_api/views.py` at zero. Every quality endpoint goes through the Layer-2 facade.
- **`ServiceBase._audit(operation=...)` is fail-loud.** `AuditEntry.OP_CHOICES`
  (`backend/audit/models.py:130-141`) is validated by `full_clean`; an undeclared operation string 500s the
  whole transaction *after* the mutation already succeeded (issue #265, guarded by
  `audit/tests/test_op_vocabulary.py`). Any new operation verb must be added there in the same change.
- **Every new tenant-scoped table needs an RLS policy migration.** Precedent + copyable SQL:
  `backend/application/migrations/0013_goal_adr_change_request_rls_policies.py`. Note the DDL runs as the DB
  owner, not the app role.
- **No hardcoded provider/model/prompt strings outside the slot registry.** The whole point of the feature is
  that a workspace can change the criteria without a deploy.
- **Auto-mode defaults to OFF, per workspace and per artifact type.** A feature that silently spends tokens on
  every keystroke is a cost incident, not a feature.

---

## What already exists (verified)

This section is the load-bearing part of the scoping: most of the issue's "technische Andockpunkte" are real
and usable, but three of them are not what the issue assumes.

### Prompt-template system — real, and a drop-in extension

| Piece | Location | Notes |
|---|---|---|
| Model | `backend/persistence/models.py:1896` (`PromptTemplate`, table `pl_prompt_template`) | Open-ended `name`; `workspace_id=None` = tenant-global; one `is_active` row per `(tenant, workspace_id, name)`; a new version is a **new row**, never an in-place update. Uniqueness enforced in `save()` via a `select_for_update()` mutex on the parent `Tenant` row. |
| Canonical factory registry | `backend/application/ai_derivation_service.py:165` (`PROMPT_TEMPLATE_DEFAULTS`, 8 entries) | Merges `persistence.models.PROMPT_TEMPLATE_DEFAULTS` (4 entries, line 1881) with 4 module constants. Explicitly documented as *the* single registry; both the MCP tool and `SettingsService` read it. |
| Resolution chain | `AiDerivationService._get_template_content` (~line 1316) | workspace override → tenant-global → factory. |
| Slot wire format | `SettingsService._build_slot_state` (`backend/application/settings_service.py:349`) | Produces exactly the `has_workspace_override` / `effective_scope` (`workspace` > `global` > `factory`) shape the issue names. |
| Slot CRUD | `SettingsService.list_prompt_slots` / `set_prompt_slot` / `clear_prompt_slot` | REST: `/api/v1/prompt-templates/slots/[?workspace_id=]` (GET/PUT/DELETE). MCP: `prompt_template.get/list/create/update`. |
| Frontend | `frontend/src/api/prompt-templates.ts:61` (`KNOWN_PROMPT_SLOTS`), `frontend/src/components/WorkspaceSettings/AiPromptsSection.tsx:128` (`SLOT_LABELS`) | The UI enumerates whatever the backend returns and orders known names first — an unknown slot still renders, just unlabelled and last. |

**Precedent for adding a slot:** commit `51eb906f` (`feat: Goals and MainGoal artifact type with AI aggregation
(#223)`) added `goal_aggregate`. It touched the defaults dict, `settings_service._PROMPT_SLOT_FIELDS`, the test
that counts slots, and the frontend list. Adding a slot is therefore genuinely **drop-in: ~4 files + 1 test +
2 i18n labels. No new plumbing.**

Two traps in that precedent:

1. `_PROMPT_SLOT_FIELDS` (`settings_service.py:68`) is the **legacy flat facade** (`/api/v1/prompt-templates/`),
   deliberately frozen at its historical shape. `#223` added `goal_aggregate` to it, which also stales the
   comment in `ai_derivation_service.py:153` claiming the persistence dict "is intentionally kept at its
   original 3 entries" (it has 4). **New quality slots must NOT be added to `_PROMPT_SLOT_FIELDS`** — the flat
   facade is not the extension point; the slot API is.
2. There are **three** implementations of the same resolution chain
   (`AiDerivationService._get_template_content`, `SettingsService._build_slot_state`,
   `mcp_server/tools/prompt_template.py::_handle_get`). They agree today only because all three read the same
   factory dict. A quality service must read the same dict, not build its own.

**Recommendation.** For v1 (one slot, `quality_requirement`), add the key directly to
`ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS` and reuse `_get_template_content` — zero refactor, exactly the
`#223` precedent. When the 2nd–4th quality slots land (v1.1), extract a neutral
`backend/application/prompt_slots.py` that merges per-domain contributions and re-export the old name for
backward compatibility. Doing that extraction up front for a single key is churn; doing it never leaves the
derivation service owning prompts for a service it does not know about.

### LLM adapter — reuse the free-form `complete()` path, not `validate_artifact`

- `LlmCapabilityInterface.validate_artifact` (`backend/llm_adapter/interface.py:103`) already returns an
  `LlmResult` with `score: float` (validated to `[0.0, 1.0]` in `__post_init__`) and `suggestions: List[str]`,
  and is already wired into `RequirementService.validate_requirement`
  (`backend/application/requirement_service.py:826`) and the `requirement.validate` MCP tool. **This is a real,
  pre-existing overlap with the issue** — see open question O8.
  It is not directly reusable, because its prompt lives inside each provider implementation, not in a
  `PromptTemplate` slot. Making it slot-driven would change the provider interface contract for all four
  providers.
- The right path is the one the eight derive flows use: `AiDerivationService._complete(prompt, purpose=...,
  artifact_id=...)`, which independently applies the daily token limit (REQ-106), the per-purpose timeout
  (REQ-084 / issue #342), the audit log entry, and maps transport faults to a catchable `LlmResponseError`.
- Timeouts: `llm_adapter/timeouts.py`. Default `LLM_SYNC_TIMEOUT_SECONDS = 25`
  (`backend/reqogniloom/settings.py:512`). A per-artifact quality prompt **must not** be added to
  `WORKSPACE_WIDE_PURPOSES` (that is the 180 s bucket for workspace-wide prompts).
- Retries + breaker: `llm_adapter/resilient_transport.py` — 3 retries, 1/2/4 s backoff, circuit breaker keyed
  `llm:<provider_name>`. Documented caveat (issue #342): a timeout does **not** abort the worker thread, so
  worst-case wall clock per assessment on a hanging provider is ≈ `(3+1) × 25 s + 7 s ≈ 107 s`.
- Cost ceiling: `TENANT_TOKEN_LIMIT_PER_DAY` (`settings.py:532`) **defaults to `None` = unlimited**
  (`llm_adapter/token_tracking.py:140`).
- Response cache: `ai_derivation_service` already caches genuine provider answers for 1 h keyed by
  `(provider, capability, artifact_id#generation, sha256(prompt))`, with O(1) invalidation via
  `invalidate_derivation_cache(artifact_id)` bumping a per-artifact generation counter. **This is the single
  largest cost lever for this feature and it already exists.**

### SE-Auditor — additive rule category, no refactor needed

- Rule ids are constants + a preset map in `backend/traceability/audit/registry.py`
  (`TRACE_P1..P7`, `ARCH_003`, `VERIF_P8`, `CONS_P9/P10`; `RULE_PRESET_MAP`; `ALL_RULE_IDS`).
  `@register_rule` **rejects any id not in `ALL_RULE_IDS`**, so a typo fails loudly at import.
- The registry docstring already contains a 7-step "Adding a new rule" guide, plus a `deferred_reason`
  mechanism for rules whose prerequisites do not exist yet.
- `Severity` is a 2-value enum (`BLOCKER` / `WARNING`) and per-tier severity is resolved by the *engine*
  (`RuleEngine._run_rule` re-stamps every finding with `rule.severity_for_tier(tier)`), so a WARNING-only
  QUAL rule is one method override.
- `Finding` (`traceability/audit/types.py`) carries `rule_id`, `severity`, `message`, `artifact_ids`, `scope`,
  `scope_artifact_id` — nothing structural-only. A quality finding fits the shape verbatim.
- `AuditContext` exposes only `scope_item_ids` and `iter_trace_links` — i.e. the engine's data access is
  deliberately narrow and cheap. A QUAL rule would query `QualityAssessment` directly (as `trace_p7` and the
  coverage rules already query their own models), which is consistent, not a violation.

**Conclusion: additive, no refactor required** — *provided* the rule reads persisted rows only.
One small independent hardening is worth doing alongside: `RuleEngine._run_rule` does not wrap
`rule.check(context)` in `try/except`, so one raising rule fails the whole audit **and the baseline gate**.
That is a pre-existing sharp edge; adding a rule family that touches a new table makes it worth closing.

### Trigger infrastructure — two of three points already exist, one is an unused seam

| Trigger | Attachment point | State |
|---|---|---|
| Manual | new REST/MCP surface | n/a — this *is* v1 |
| On create/update | `ServiceBase._emit_event` → `DomainEventOutbox` → `poll_and_dispatch` → `SubscriberRegistry` | **Exists and is used.** `RequirementCreated/Updated/Deleted`, `ArchitectureElement*`, `TestCase*`, `Adr*`, `Risk*`, `Issue*`, `ChangeRequest*`, `BaselineCreated` are all emitted today (`application/models.py:39-63`). Events fire post-commit via `transaction.on_commit`. Only one subscriber exists today: `application/webhook_dispatcher.py`. |
| On status transition | `DomainEventOutbox.EventType.WORKFLOW_TRANSITIONED` | **Declared but never emitted.** `workflow/services.py:188 transition()` returns a `TransitionResult` and emits nothing; grep shows zero `_emit_event` call sites for this type. Wiring it up from `WorkflowFacade` is the clean fix and benefits more than this feature. |
| Periodic batch | Celery Beat | **Exists.** `CELERY_BEAT_SCHEDULE` (`settings.py:558`) has exactly one entry (`dispatch-outbox-events`, every 5 s → `application.dispatch_outbox_events`), `CELERY_BEAT_SCHEDULER = django_celery_beat.schedulers:DatabaseScheduler` (settings.py:567), and a dedicated **`celery-beat` service** runs in `docker-compose.yml:317-363`. `backend/tests/test_wiring.py` asserts the outbox entry is present; a new entry does not break it. |

**Queue routing detail that matters:** `backend/reqogniloom/celery.py:36` routes `llm_adapter.*` → queue `llm`
and `application.dispatch_outbox_events` → `events`; everything else falls through to `default`. A task named
`application.quality_*` therefore lands on `default` alongside resilience/audit maintenance work. **Add an
explicit route to the `llm` queue** so slow provider calls cannot starve the maintenance queue.

**DatabaseScheduler is a real advantage here:** per-workspace sweep schedules can be created as
`django_celery_beat` DB rows at runtime, instead of being frozen in the static settings dict.

### Preset gating — the existing tool-level gate is dead code

`ToolRegistry._TOOL_FEATURE_MAP` (`tool_registry.py:255`) maps tools to keys `llm_decompose`, `llm_validate`,
`architecture_links`, `test_links`, `traceability`, `artifact_tree`. **None of those are in
`presets.registry.FEATURE_KEYS`**, which has exactly five: `baselines`, `global_baselines`,
`approval_workflows`, `custom_workflows`, `change_reason_mandatory`. `_is_feature_disabled` ends in
`return not features.get(feature_key, True)` → always `False`. **Those gates never disable anything.**

Consequence for this design: do **not** add `quality.assess` to `_TOOL_FEATURE_MAP` expecting it to be
preset-gated. Either add a genuine key to `FEATURE_KEYS` (which forces updating all three `PresetConfig`
literals — `PresetConfig._validate()` rejects a preset missing any key) or gate in the service. For v1, gate in
the service on a `Workspace` flag; a preset key is a follow-up.

---

## 1. Data model

### `QualityAssessment` — append-only, one row per run

Placement: `backend/application/models.py` (app `application`, table prefix `as_`), matching where the newer
domain models went (`ChangeRequest` 0011, `Goal`/`MainGoal` 0012) and where the copyable RLS migration lives.
Base class: plain `models.Model` with explicit `workspace_id` / `tenant_id` UUID columns — that is what the
neighbouring `application` models do (`Risk`, `Adr`, `Goal`, …), *not* `persistence.TenantScopedModel`.

| Field | Type | Rationale |
|---|---|---|
| `id` | UUID pk | |
| `tenant_id` | UUID, indexed | RLS policy column (`app.current_tenant`) |
| `workspace_id` | UUID, indexed | prompt scope + auto-mode config scope |
| `entity_type` | CharField(64) | **Authoritative half of the identity.** Mirrors `AuditEntry.entity_type`. |
| `entity_id` | UUID | **Authoritative other half.** See "why not artifact_id" below. |
| `artifact` | FK → `persistence.Artifact`, **nullable** | Optional denormalised join handle for tree/scope queries. Nullable because `GlossaryTerm` (`persistence/models.py:1699`) has **no** backing `Artifact` (unlike Requirement/ArchitectureElement/TestCase/StakeholderNeed/Adr/Risk/Issue/Goal/MainGoal/ChangeRequest, all of which have a `OneToOneField`). |
| `score` | FloatField, validators `[0.0, 1.0]` | Matches `LlmResult.score`, which the adapter already validates to that range. Presentation scale is a UI concern (see O2). |
| `reasoning` | TextField | |
| `suggestions` | JSONField (list[str], default `list`) | Matches `LlmResult.suggestions`. |
| `criteria` | JSONField (dict, default `dict`, nullable) | Per-criterion sub-scores (atomic / testable / unambiguous / …). Empty in v1; the column avoids a second migration when the prompt starts returning them. |
| `entity_version` | Integer, nullable | The artifact's `version` at assessment time — **staleness marker only**, see below. |
| `content_hash` | CharField(64), indexed | `sha256` of the exact text sent to the provider. **This, not `version`, is the identity of "what was scored."** Enables dedupe + honest history. |
| `prompt_slot` | CharField(100) | Which slot produced this score. |
| `prompt_scope` | CharField(16) — `workspace`\|`global`\|`factory` | Reproducibility: once a workspace customises the prompt, scores from before/after are not comparable. |
| `prompt_version` | Integer, nullable | `PromptTemplate.version` of the row that was used (`NULL` for `factory`). |
| `provider` / `model` / `token_usage` | CharField / CharField / Integer nullable | Mirrors `LlmResult`; needed for cost attribution and for "this score came from `mock`". |
| `trigger` | CharField(16) choices: `manual`, `mcp`, `transition`, `create`, `update`, `batch` | |
| `triggered_by` | CharField(255) | Actor id string, **not a FK** — same rationale as `AuditEntry.actor` (preserves history after user deletion). |
| `status` | CharField(16): `ok` \| `failed` | An auto-triggered assessment that fails must be visible, not silently absent. |
| `error_code` | CharField(64), blank | |
| `created_at` | DateTimeField(auto_now_add) | The history axis. |

**Indexes**
- `(tenant_id, entity_type, entity_id, -created_at)` — latest score + history for one artifact.
- `(tenant_id, workspace_id, -created_at)` — dashboard / batch views.
- `(tenant_id, content_hash)` — dedupe lookup on the auto path.

**Append-only.** Never `UPDATE`; a re-assessment is a new row. This matches `PromptTemplate` (new version = new
row) and `AuditEntry` (append-only enforced by manager + DB trigger). No `is_latest` mutable flag — read the
latest with Postgres `DISTINCT ON (entity_type, entity_id) … ORDER BY entity_type, entity_id, created_at DESC`,
which serves a 200-row list view in one query rather than N.

### Why key on `(entity_type, entity_id)` and not `artifact_id`

Two independent reasons, both grounded in existing bugs:

1. `GlossaryTerm` has no `Artifact` at all. Keying on `artifact_id` would exclude an artifact type the issue
   explicitly lists ("Needs/Goals/Glossary analog").
2. `_resolve_artifact_id` in the TraceLink entity-resolver chain is a documented, recurring source of 404s for
   every newly added artifact type (issues #237, #264). Building a second feature on the same resolution chain
   inherits that failure mode. `(entity_type, entity_id)` is the shape `AuditEntry` already uses and needs no
   resolver.

The nullable `artifact` FK is kept purely so document-scope / tree queries can join without a resolver hop.

### History and versioning — the issue's premise needs correcting

The issue asks for "Score über Versionen hinweg vergleichbar". `AuditableModel.version`
(`persistence/models.py:305-322`) carries an explicit warning (issue #213):

> `version` is a **pure optimistic-concurrency counter**. It is *not* a content revision number and carries no
> history … Never present it as "this artifact has N revisions."

So a score-per-artifact-version series is **not implementable against `version`**. The corrected design:

- The history axis is `created_at` (one row per assessment run).
- `content_hash` answers "did the thing that was scored actually change?" — a re-assess of unchanged content is
  a cache hit, not a new data point.
- `entity_version` answers only "has the row been written since?" (staleness badge: *"score computed for an
  older revision"*).
- If a true score-per-revision series is wanted, the revision source in this codebase is **Baselines**
  (`baseline/`), which snapshot artifact content. Attaching scores to `BaselineItem` is a deliberate follow-up,
  not v1 — see O6.

### Relation to existing models

- **`AuditEntry`** (`backend/audit/models.py:89`): no overlap. It is a write-operation trail with a closed `op`
  vocabulary. A `QualityAssessment` insert *should* produce an `AuditEntry` (it is a write), which means either
  reusing `OP_CREATE` with `entity_type="QualityAssessment"` (recommended, zero risk) or adding a new
  `OP_QUALITY_ASSESS` to `OP_CHOICES`. Skipping this step is the #265 trap: an undeclared operation string 500s
  the transaction *after* the row is written.
- **`Baseline` / `BaselineItem`**: no overlap in v1. Quality scores are derived, re-computable and
  provider-dependent; freezing them into a governance snapshot is a product decision (O6).
- **SE-Auditor `Finding`**: no persistence overlap — findings are computed per run and never stored. A QUAL
  finding is *derived from* `QualityAssessment` rows at audit time.

---

## 2. Prompt-template integration

**Drop-in, no new plumbing.** Concretely, for v1 (`quality_requirement`):

1. `backend/application/ai_derivation_service.py` — add a `QUALITY_REQUIREMENT_PROMPT_TEMPLATE` module constant
   and one key in `PROMPT_TEMPLATE_DEFAULTS` (line 165). This is *the* canonical registry: `SettingsService.
   _all_prompt_defaults()` and `mcp_server/tools/prompt_template.py` both import it, so the slot becomes
   visible in the REST slot API, the MCP tool and the Settings UI **without touching any of them**.
2. `frontend/src/api/prompt-templates.ts` — add the name to `KNOWN_PROMPT_SLOTS` (ordering only; an absent name
   still renders, just last and unlabelled).
3. `frontend/src/components/WorkspaceSettings/AiPromptsSection.tsx` — add a `SLOT_LABELS` entry.
4. `frontend/src/i18n/locales/{de,en}.json` — the label strings. **Watch the flat dotted-key trap:**
   `keySeparator` is `"."`, so a key written as `"quality.requirement"` *inside* an object never resolves.
5. Tests: the slot-count assertions
   (`backend/application/tests/test_ai_derivation_service.py`,
   `backend/rest_api/tests/test_prompt_template_slots.py`) hard-code the number of slots and must be updated —
   exactly as `#223` did (`test_get_template_content_covers_all_eight_names`).

Consumption in the service is one call:

```
content = AiDerivationService._get_template_content(ctx, "quality_requirement", workspace_id=ws_id)
```

which already implements workspace → tenant-global → factory. To persist `prompt_scope` / `prompt_version`
honestly, the service needs the *resolved scope*, not just the text — either call
`SettingsService._slot_state(...)` (which already returns `effective_scope` + versions) or add a
`_get_template_content_with_scope()` sibling. Recommendation: reuse `SettingsService`, since it is the module
that already owns that wire shape.

**Do not** add quality slots to `settings_service._PROMPT_SLOT_FIELDS` (the frozen flat facade).

**v1.1 refactor (deferred):** when slots 2–4 land, extract `backend/application/prompt_slots.py` as a neutral
merge point (`_CORE` + derivation + quality) and alias `ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS` to it,
so a quality service does not require the derivation service to know about quality prompts. Two import sites to
update (`settings_service._all_prompt_defaults`, `mcp_server/tools/prompt_template.py`).

---

## 3. `quality.assess` — MCP tool + REST endpoint

### MCP

New group `backend/mcp_server/tools/quality.py`, prefix `quality`, registered in `ToolRegistry`'s group map
(`tool_registry.py:456` neighbourhood).

```
quality.assess(entity_type, entity_id, workspace_id, force?=false)
  -> { assessment_id, entity_type, entity_id, score, reasoning,
       suggestions: [...], criteria: {...}, prompt_scope, prompt_slot,
       provider, model, trigger, cached: bool, assessed_at }

quality.query(entity_type, entity_id, workspace_id, limit?=20)
  -> { assessments: [ ...same shape... ], count }
```

**Payload shape rule:** never a top-level `content` key in an MCP tool payload — it collides with the MCP
envelope. Same shape on hit and miss (`assessments: []`, `count: 0`), not a different error object.

**RBAC.** `_is_write_tool` is **fail-closed** (`tool_registry.py:155-168`): any name not in
`_READ_ONLY_TOOL_NAMES` and not ending in `.read`/`.query` is treated as WRITE and requires Editor or Admin
(`_check_rbac`, line 817). That default is *correct* for `quality.assess` — it persists a row, so it is a write
even though it feels like a read. **Do not add it to `_READ_ONLY_TOOL_NAMES`.** This mirrors `ai_derivation.*`,
which is write-gated even in `mode="preview"` — a deliberate, documented restriction (a Viewer cannot preview).

`quality.query` inherits the read exemption from its `.query` suffix with **zero registry edits** — this is why
it should be named `quality.query`, not `quality.get_history`.

Write tools must also emit the MCP-enriched audit entry via `write_mcp_audit` / `mcp_audit_handoff`
(REQ-L2-MC-012), exactly as `prompt_template.create/update` do.

### REST

New module `backend/rest_api/quality_views.py` — per the module-per-view-group convention that
`rest_api/audit_views.py` states explicitly ("the codebase splits large view groups into dedicated modules …
rather than growing the 5k-line views.py").

```
POST /api/v1/workspaces/<uuid:workspace_id>/quality/assess/
     body: { entity_type, entity_id, force?: bool }
     201 -> assessment object (as above)
     400 VALIDATION_ERROR | 404 NOT_FOUND | 429 throttled | 500 INTERNAL_SERVER_ERROR

GET  /api/v1/workspaces/<uuid:workspace_id>/quality/<entity_type>/<uuid:entity_id>/
     200 -> { assessments: [...], count, latest }
```

Shape it after `WorkspaceTraceabilitySuggestLinksView` / `WorkspaceAuditAiReviewView`: plain `APIView`,
`get_auth_context(request)`, `detect_lang(request)`, `build_error_response(...)`, service facade only.
Register in `rest_api/urls.py` in the workspace-scoped block next to the `audit/` routes. Note the detail-route
pk seam (#271): `<uuid:…>` converters are used only on aux routes here, which is exactly what these are.

`POST` is the right verb despite feeling read-ish: it creates a resource and is not idempotent. `force=false`
(default) returns the cached/deduped latest assessment when `content_hash` is unchanged, which gives callers a
cheap idempotent path without pretending the endpoint is safe.

**Throttling is mandatory on the POST.** Use `rest_api/throttling.py` — DRF's stock `ScopedRateThrottle`
misbehaves in this project (throttle rates are pinned at import time; the stock classes 500), which is why the
bespoke module exists.

**Permissions.** Read = any authenticated role incl. Viewer; assess = Editor+, matching the MCP gate. Keeping
the two surfaces symmetric matters because agents use MCP and humans use REST against the same data.

---

## 4. Trigger integration points

### (a) Manual — v1

The REST + MCP surface above. Nothing else.

### (b) On status transition

`workflow/services.py:188 transition()` has no post-transition hook and emits no event, but
`DomainEventOutbox.EventType.WORKFLOW_TRANSITIONED` **already exists as an unused enum member**.

Recommended wiring:

1. `WorkflowFacade.transition()` (Layer 2, already a `ServiceBase`) calls
   `self._emit_event(self._make_event(WORKFLOW_TRANSITIONED, entity_id=item_id, workspace_id=…,
   payload={"item_type", "previous_state", "new_state"}))` after a successful `workflow.services.transition()`.
   This closes a pre-existing gap that benefits webhooks too.
2. A quality subscriber registers for `WorkflowTransitioned`, checks the workspace's quality config
   (target state in the configured trigger states? artifact type opted in?), and **enqueues** a Celery task.

Rejected alternative: calling the assessment directly inside `WorkflowFacade.transition`. It would put a 25 s
(worst case ~107 s) provider call inside the request that a user is waiting on for a status change, and an LLM
outage would turn into a transition outage.

### (c) On create/update

Zero new plumbing: `RequirementCreated/Updated`, `ArchitectureElement*`, `TestCase*`, `Adr*`, `Risk*`, `Issue*`,
`ChangeRequest*` are already emitted by `ServiceBase._emit_event`, post-commit. Register one subscriber for the
opted-in event types; it enqueues, subject to the debounce rules in §6.

Caveats: (1) not every assessable type emits an event today — `StakeholderNeed`, `Goal`, `MainGoal`,
`GlossaryTerm` need checking per type and possibly new enum members + emissions; (2) the subscriber runs inside
`poll_and_dispatch`, the 5-second beat drain, under a 30 s dispatch cap — enqueue only.

### (d) Periodic batch

- Beat entry in `CELERY_BEAT_SCHEDULE` (`settings.py:558`) *or*, better, a `django_celery_beat` DB row created
  at runtime — `CELERY_BEAT_SCHEDULER` is the `DatabaseScheduler`, so per-workspace cadences do not have to be
  baked into settings.
- Task home: `backend/application/tasks.py` (documented as the home for beat tasks; currently one task).
  A `quality_sweep()` **fan-out** task: it selects candidate artifacts (opted-in types, no assessment, or stale
  by `content_hash` / age) and enqueues one subtask per artifact. It must never hold a long LLM loop itself —
  that is what makes a sweep unkillable and un-throttleable.
- **Queue routing:** add `'application.quality_*': {'queue': 'llm'}` to `app.conf.task_routes`
  (`backend/reqogniloom/celery.py:36`), otherwise slow assessments land on `default` next to
  resilience/audit maintenance work.
- **Tenant context:** a Celery task has no request, so it must set the tenant explicitly. Note that RLS
  `SET app.current_tenant` is a real DB round trip; the audit-infrastructure precedent for read-only
  cross-tenant machinery is `unscoped.filter(tenant_id=…)` (`AuditContext.iter_trace_links`). Writes must go
  through the tenant-scoped path.
- **Per-tenant fairness:** a sweep must iterate tenants round-robin, not tenant-by-tenant, or one large tenant
  starves the rest and burns the shared daily token budget.

---

## 5. SE-Auditor integration (`QUAL-*`)

**Verdict: feasible as a purely additive rule category. No refactor of the rule engine is required.** The
engine is generic over `Finding`; nothing in `Rule`, `RuleEngine` or `AuditContext` assumes structural graph
checks — the existing rules just happen to be structural.

Mechanics (the registry docstring's own 7-step guide):

1. `traceability/audit/registry.py`: add `QUAL_P1 = "QUAL-P1"` (and siblings) to the constants, to
   `RULE_PRESET_MAP` (Standard and/or Extended), and to `__all__`. `register_rule` rejects ids absent from
   `ALL_RULE_IDS`, so this step cannot be silently skipped.
2. `traceability/audit/rules/quality_score.py`: `@register_rule class QualityScoreRule(Rule)` with
   `is_scope_aware = True` (so it audits only artifacts in the requested baseline scope, using
   `context.scope_item_ids`) and `severity_for_tier(tier) -> Severity.WARNING`.
3. `rules/__init__.py`: `from . import quality_score`.

Proposed initial family (all WARNING in v1):

| Rule | Check (persisted rows only) |
|---|---|
| `QUAL-P1` | Artifact in scope has **no** `QualityAssessment` at all. |
| `QUAL-P2` | Latest score below the workspace threshold. |
| `QUAL-P3` | Latest assessment is **stale**: `content_hash` differs from the artifact's current content. |

The hard constraint, restated because it is the whole risk: **`check()` must not call an LLM.** It runs on every
`GET /api/v1/workspaces/<id>/audit/` and inside `BaselineFacade._assert_no_blocking_findings` on every baseline
creation. Reading `QualityAssessment` rows keeps it a single indexed query.

**Minimal tier is structurally exempt** — `RULE_PRESET_MAP["minimal"]` is a literal empty frozenset with an
import-time `assert` and an unconditional re-empty in `_get_rule_preset_map()`. Nothing to do.

**Recommended companion hardening** (small, independent of this feature): wrap `rule.check(context)` in
`try/except` in `RuleEngine._run_rule`, logging and degrading to `[]`. Today a raising rule takes out the audit
dashboard *and* the baseline-creation path for the whole workspace.

**Baseline gating: do not enable by default.** `BaselineFacade._assert_no_blocking_findings` means the instant a
QUAL rule is `BLOCKER`, a non-deterministic LLM score becomes a hard governance gate on baseline creation. That
is open question O1.

---

## 6. Cost, latency and reliability

### The runaway-cost math

Auto-assess-on-every-update, worst case, with the shipped defaults:

- `TENANT_TOKEN_LIMIT_PER_DAY` defaults to **`None` = unlimited** → **no cost ceiling exists today.**
- 1 provider call per assessment; 3 retries with 1/2/4 s backoff; a timed-out attempt does **not** free the
  worker thread (issue #342), so worst case ≈ `4 × 25 s + 7 s ≈ 107 s` of worker time per artifact against a
  hanging provider.
- An editor saving a 500-word requirement 20× in an afternoon produces 20 `RequirementUpdated` events → 20
  assessments of near-identical text.
- A 2,000-artifact workspace sweep at 1 call each is 2,000 calls per cadence, per workspace, per tenant.

### Recommended controls, in order of leverage

1. **Content-hash dedupe (highest leverage, cheapest).** Skip when the latest `ok` assessment's `content_hash`
   equals the current one. Turns the "editor saves 20×" case into 1 call + 19 DB lookups.
2. **Reuse the existing derivation cache.** `ai_derivation_service` already caches genuine provider answers for
   1 h keyed by `(provider, capability, artifact_id#generation, sha256(prompt))`, with O(1) invalidation via
   `invalidate_derivation_cache`. Free.
3. **Per-artifact cooldown.** `cache.add(f"quality:cooldown:{entity_type}:{entity_id}", 1, 600)` returning
   `False` → skip. Redis is already the shared cache backend (db 1), and `cache.add` is atomic, so this also
   deduplicates concurrent workers.
4. **Opt-in matrix, default OFF.** Per workspace × per artifact type × per trigger mode. Store as a
   `Workspace.quality_config` JSONField — precedent: `Workspace.ai_prompts` (JSONField) and
   `goals_enabled`/`goals_ai_enabled` (booleans) at `persistence/models.py:602-628`. A JSONField avoids a
   config table for a v1 whose shape is not yet settled; promote to a table if it grows.
5. **A real budget.** Introduce `QUALITY_ASSESS_DAILY_BUDGET` (per tenant) checked *before enqueueing*, and
   route quality spend through the existing `record_token_usage` so it lands in the same aggregate as
   derivation. Auto-mode should refuse to enable while no budget is configured — an explicit operator decision
   beats an implicit unlimited one.
6. **Never batch-assess synchronously.** `quality.assess_batch` (if it ever exists) returns a task id, like
   `check_consistency` already does.
7. **Circuit-breaker awareness.** The breaker is keyed `llm:<provider_name>` and shared with derivation. A
   quality sweep hammering a failing provider will trip the breaker and degrade `requirement.decompose`,
   `traceability.suggest_links` and `audit.ai_review` for everyone. The sweep must back off on
   `LlmResponseError`, not just retry the next artifact.
8. **`mock` is the default provider.** With `LLM_PROVIDER=mock` every score is deterministic and meaningless —
   good for tests and E2E, actively misleading in a demo. The UI must surface `provider` on the score panel.

### Latency budget

| Path | Budget |
|---|---|
| `POST .../quality/assess/` (sync) | `LLM_SYNC_TIMEOUT_SECONDS` = 25 s. Do **not** add the purpose to `WORKSPACE_WIDE_PURPOSES` (180 s) — that bucket is for workspace-wide prompts, and nginx defaults to a 60 s proxy timeout. |
| Any auto trigger | Async only. Zero added latency on the user's write path. |

---

## 7. Effort estimate

Dev-days, including tests (this repo's test burden is real: every new REST surface needs `rest_api/tests/`,
every MCP tool needs registry + dispatch tests, and MCP dispatch tests need `django_db` because the RLS
`SET app.current_tenant` is a real DB hit even with fully mocked collaborators).

| Sub-capability | Effort | Notes |
|---|---|---|
| Data model + migration + RLS policy migration | 1.0 – 1.5 d | Copy `application/0013` for the policy SQL; DDL runs as the DB owner. |
| Prompt-template slot — 1 slot (v1) | 0.5 d | Drop-in; ~4 files + slot-count tests + 2 i18n labels. |
| Prompt-template slots — 4 slots + neutral registry module | +1.0 d | v1.1. |
| `QualityAssessmentService` (Layer 2): prompt resolve, `_complete`, JSON parse + validation, hash/dedupe, persist, audit | 2.0 – 3.0 d | The response-parsing hardening (LLM returns prose/fences/out-of-range scores) is most of this. |
| MCP tool group + schemas + RBAC + `write_mcp_audit` + tests | 1.0 – 1.5 d | |
| REST endpoints + serializers + throttling + OpenAPI + tests | 1.0 – 1.5 d | |
| Trigger: on transition (emit the unused `WorkflowTransitioned` + subscriber + task) | 2.0 – 3.0 d | Includes closing a pre-existing gap; needs its own regression tests for the workflow path. |
| Trigger: on create/update (subscriber + dedupe + cooldown + per-type opt-in) | 1.5 – 2.0 d | |
| Trigger: periodic sweep (beat entry, fan-out, queue route, tenant ctx, budget, fairness) | 2.0 – 3.0 d | |
| SE-Auditor `QUAL-*` (3 rules + preset map + engine error isolation) | 1.5 – 2.0 d | |
| UI: score badge + score panel (reasoning/suggestions) + history + i18n de/en | 3.0 – 4.0 d | Badge next to `StatusBadge`/`LevelBadge`/`VersionBadge` in `frontend/src/components/shared/`; panel as a 4th tab in `shared/ArtifactInspector/RightSidebar` alongside Trace/Version/Diff. **Watch the ui-ratchet gate: any new `style={{` literal under `components/` fails `ui-ratchet.test.ts`** — hoist to named `CSSProperties` consts, use `tokens.css` custom properties. |
| Config surface (Workspace toggles + Settings UI section) | 1.0 – 1.5 d | |
| Docs / ADR / REQ-register entries | 0.5 – 1.0 d | |

- **v1 as recommended below: ~8 – 11 d.**
- **Full issue as written: ~19 – 26 d.**

---

## 8. Recommended phasing

### v1 — "one artifact type, one button, real history" (~8–11 d)

- `QualityAssessment` model + migration + RLS.
- One slot: `quality_requirement` (IEEE 29148-oriented criteria).
- `QualityAssessmentService` with content-hash dedupe + derivation-cache reuse.
- `quality.assess` + `quality.query` (MCP), `POST .../quality/assess/` + `GET .../quality/<type>/<id>/` (REST).
- UI: score badge on the Requirement detail + a panel with reasoning, suggestions and the history list.
- Gated behind `Workspace.quality_config.enabled`, default **off**.
- **No** auto-mode, **no** SE-Auditor rules, **no** baseline gating, **no** batch.

Why this cut: it delivers the issue's first two acceptance criteria in full, exercises the whole vertical
(model → service → MCP+REST → UI) once, and produces the real-world score data needed to answer the open
questions — you cannot pick a sensible `QUAL-P2` threshold or judge score stability before you have run a
few hundred real assessments.

### v1.1 — breadth (~2–3 d)

`quality_adr`, `quality_testcase`, `quality_risk` slots + per-type opt-in matrix + the neutral prompt-slot
registry extraction.

### v2 — auto-mode (~4–6 d)

Emit `WorkflowTransitioned`; subscriber + Celery task + cooldown + budget + queue route. Opt-in per workspace
and per type, on transition first (low frequency, high value) and only then on create/update.

### v2.1 — periodic sweep (~2–3 d)

Beat/DatabaseScheduler entry, fan-out, per-tenant fairness, backoff on breaker trip.

### v3 — SE-Auditor (~2 d)

`QUAL-P1/P2/P3` as WARNING, plus the `RuleEngine` error isolation. Baseline blocking stays opt-in and is a
separate decision (O1).

### Follow-up issues to file now

1. Score presentation scale + i18n (product/UX).
2. Baseline-blocking policy for `QUAL-*` (product/governance).
3. Per-tenant LLM budget model — `TENANT_TOKEN_LIMIT_PER_DAY` is a single global setting, not a per-tenant row.
4. Neutral prompt-slot registry extraction (`application/prompt_slots.py`).
5. `RuleEngine._run_rule` error isolation (independent hardening).
6. `requirement.validate` vs `quality.assess` overlap (O8).
7. Emit `WorkflowTransitioned` (independently useful for webhooks).

---

## 9. Risks and open questions

**O1 — Should `QUAL-*` findings ever be baseline-blocking? (biggest open question, needs a human decision.)**
`BaselineFacade._assert_no_blocking_findings` means a single `BLOCKER`-severity QUAL rule turns a
non-deterministic LLM score into a hard gate on baseline creation for the whole workspace — including for
artifacts nobody has assessed yet (`QUAL-P1` would block on *absence*). Recommendation: **WARNING only, never
BLOCKER by default**, with an explicit per-workspace opt-in and a documented threshold, added no earlier than
v3. Requires product sign-off before any QUAL rule is written.

**O2 — Score scale.** Storage is settled by the adapter contract (`LlmResult.score` is validated to `[0.0,
1.0]`), so store a float and do not bikeshed the column. What *is* open is presentation: percentage, A–F,
German school grade 1–6, or a 3-state traffic light. Recommendation: traffic light + numeric on hover — a
precise-looking 0.73 implies a precision an LLM judgement does not have.

**O3 — Determinism and comparability.** The same artifact scored twice by a real provider can differ by more
than the threshold you would want to gate on. With `mock` (the default) scores are perfectly stable and
perfectly meaningless. Needs an explicit product stance: is the score a *trend indicator* (recommended) or a
*measurement*? Only the former survives contact with a real provider.

**O4 — Prompt drift silently breaks history.** The moment a workspace edits `quality_requirement`, all earlier
scores become incomparable. Mitigated by storing `prompt_scope`/`prompt_version`, but the UI must visibly mark
the break in the series rather than drawing one continuous line.

**O5 — The issue's "Score über Versionen" premise is not implementable as written.** `version` is an
optimistic-concurrency counter, not a revision number (#213). The corrected model is `created_at` +
`content_hash`; confirm this substitution is acceptable to the requester before implementation.

**O6 — Should scores be part of a baseline snapshot?** Currently no. Arguments for: a baseline claiming "this
release met the quality bar" is auditable. Against: scores are derived, provider-dependent and re-computable,
and freezing them implies a rigour they do not have. Deliberately deferred.

**O7 — Who may see a score?** A low score is a judgement on a named author's work. Proposed: read = any
authenticated role incl. Viewer; assess = Editor+. Confirm this is acceptable, or scores need their own
visibility rule.

**O8 — Overlap with the existing `requirement.validate`.** `RequirementService.validate_requirement` →
`llm_adapter.validate_artifact` **already returns a `score` + `suggestions` for a Requirement today** and is
exposed as an MCP tool. It differs in three ways: nothing is persisted, the prompt lives inside each provider
implementation (not a slot), and it is Requirement-only. Shipping `quality.assess` alongside it gives agents
two overlapping tools with no stated difference — a known source of wrong tool selection. Recommendation:
ship `quality.assess` on the slot-driven `complete()` path, and in the same release either deprecate
`requirement.validate` or document it explicitly as "legacy, non-persisting, non-configurable". Needs a
decision, not a default.

**O9 — Not every assessable type emits domain events or has a backing `Artifact`.** `GlossaryTerm` has no
`Artifact`; `StakeholderNeed`/`Goal`/`MainGoal`/`GlossaryTerm` event emission needs per-type verification. The
`(entity_type, entity_id)` key handles the first; the second is v2 scope, not v1.

**O10 — The preset feature gate is currently dead code.** `_TOOL_FEATURE_MAP` keys are not in `FEATURE_KEYS`,
so `_is_feature_disabled` always returns `False`. Adding a genuine `quality_assessment` feature key means
updating all three `PresetConfig` literals (`_validate()` rejects any preset missing a key). Worth doing, but as
its own change — not smuggled into this feature.

---

## Appendix — file map (proposed, none created)

```
backend/application/
  models.py                          # + QualityAssessment
  migrations/0016_quality_assessment.py          # model + indexes
  migrations/0017_quality_assessment_rls.py      # RLS policy (copy 0013)
  quality_assessment_service.py      # Layer-2 facade (ADR-01)
  ai_derivation_service.py           # + QUALITY_REQUIREMENT_PROMPT_TEMPLATE, + 1 key in PROMPT_TEMPLATE_DEFAULTS
  tasks.py                           # v2.1: quality_sweep fan-out beat task
  services.py                        # + re-export (the only permitted edit to this file)
  tests/test_quality_assessment_service.py

backend/mcp_server/tools/
  quality.py                         # quality.assess (write-gated) + quality.query (read-exempt via suffix)
backend/mcp_server/tool_registry.py  # + group registration for the "quality" prefix
backend/mcp_server/tests/test_quality_tool_group.py

backend/rest_api/
  quality_views.py                   # POST assess/ + GET history
  urls.py                            # + 2 workspace-scoped routes
  tests/test_quality_views.py

backend/traceability/audit/          # v3 only
  registry.py                        # + QUAL_P1/P2/P3 constants + RULE_PRESET_MAP entries
  rules/quality_score.py
  rules/__init__.py                  # + from . import quality_score
  rule_engine.py                     # + try/except around rule.check (independent hardening)

backend/reqogniloom/
  celery.py                          # + task_route 'application.quality_*' -> queue 'llm'
  settings.py                        # + QUALITY_ASSESS_DAILY_BUDGET, v2.1 beat entry

backend/persistence/models.py        # + Workspace.quality_config JSONField (v1 gate)

frontend/src/
  api/quality.ts                     # typed wrapper
  api/prompt-templates.ts            # + KNOWN_PROMPT_SLOTS entry
  components/shared/QualityBadge.tsx
  components/shared/ArtifactInspector/QualityPanel.tsx   # 4th tab next to Trace/Version/Diff
  components/WorkspaceSettings/AiPromptsSection.tsx      # + SLOT_LABELS entry
  i18n/locales/{de,en}.json          # flat dotted keys — keySeparator is "."
```
