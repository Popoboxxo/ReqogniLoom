# Phase 4: Prompt-Template-System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `PromptTemplate` from a tenant-wide singleton with 3 hardcoded slots into a named, versioned, multi-template model with Global-default + per-workspace-override scoping, and add `prompt_template.list()`/`.create()`/`.update()` MCP tools (`.get()` already exists). Retrofit all 7 AI-derive methods (3 already slot-sourced, 4 Phase-3-added ones currently using inline module constants) onto the new unified lookup.

**Architecture:** One model, two composed axes — versioning (new row per edit, old row's `is_active` flips to `False`, never overwritten) and scope (`workspace_id` NULL = tenant-wide global default, non-NULL = workspace-specific override). Lookup is a simple fallback chain: workspace-override → tenant-global → factory-default constant. Deliberately NOT wired into Phase 0's `workflow.services.outdate()`/`WorkflowItemState` machinery (see Global Constraints) — versioning here is a lightweight `is_active` boolean, not a business-process workflow.

**Tech Stack:** Django 4.2, Python 3.x, pytest, `backend/persistence/models.py`, `backend/mcp_server/tools/prompt_template.py`, `backend/application/ai_derivation_service.py`.

## Global Constraints

- No REQ-ID in commit messages.
- **Design decision (documented, not re-litigated): template versioning does NOT go through Phase 0's `workflow.services.outdate()`/`WorkflowItemState`.** `PromptTemplate` is a versioned config/content artifact, not a business-process entity with review states — provisioning a `WorkflowEngineDefinition`+`WorkflowItemState` row per template-name-per-workspace for something that's just "is this version current" would be real, unjustified machinery overhead (confirmed: `PromptTemplate` is not in `WORKFLOW_ENTITY_TYPES` today, and adding it would require a new preset + per-instance state rows). Instead: a plain `is_active: bool` field, flipped in the same transaction that creates a new version — same OUTCOME ("old version is superseded, never overwritten, still queryable for history") via a much simpler mechanism.
- Old singleton was **tenant-scoped** (one row per tenant, 3 fixed slots). New model is **workspace-scoped-with-fallback**: a tenant-wide default (`workspace_id=NULL`) plus optional per-workspace overrides. Migration must map each existing tenant's singleton row onto 3 new tenant-wide-default (`workspace_id=NULL`) rows — preserving any tenant customization exactly, not silently reverting to factory defaults.
- `_WRITE_TOOL_PREFIXES` already reserves `prompt_template.create`/`.update`/`.delete` (pre-registered by an earlier phase, unused until now) — confirm these still make sense for the final tool set; `.list`/`.get` need no write-prefix entry (read-only).
- All 7 derive methods in `ai_derivation_service.py` must end up using the SAME unified lookup helper — the 3 already-slot-sourced ones and the 4 Phase-3 inline-constant ones. The 4 module-level prompt constants (`TESTCASE_DERIVE_PROMPT_TEMPLATE`, `ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE`, `WORKSPACE_TO_GLOSSARY_PROMPT_TEMPLATE`, `DECISION_TO_ADR_PROMPT_TEMPLATE`) become the new templates' FACTORY-DEFAULT fallback values (extending `PROMPT_TEMPLATE_DEFAULTS`), not deleted — `_render()` itself is untouched (simple `{key}` substitution, already provider-agnostic).
- REST API (`settings_service.py`/`settings_views.py`, the existing 3-slot get/put/reset endpoints) must keep working unchanged for the 3 original slot names — implemented as a thin compatibility layer reading/writing the new model's tenant-global (`workspace_id=NULL`) rows, not as a parallel/duplicate storage path. New templates and workspace-level overrides are NOT exposed via REST in this phase (MCP-only) — explicitly out of scope, avoids scope creep into the REST layer's own versioning story.
- Out of scope: exposing new templates or workspace-overrides via REST; a UI for template management; retrofitting `TraceabilitySuggestService`/`architecture_decompose_service.py`/`ai_review_service.py` even if they turn out to reference `PromptTemplate` (Task 1 must confirm whether they're real consumers or false-positive grep matches before deciding — if real, note as a follow-up, don't silently expand this phase's scope to touch them without a fresh sign-off).

---

## Task 1: New `PromptTemplate` model shape + data migration

**Files:**
- Modify: `backend/persistence/models.py` (replace/extend the `PromptTemplate` class)
- Create: `backend/persistence/migrations/00XX_prompt_template_versioning.py` (confirm next migration number by listing `backend/persistence/migrations/`)
- Test: `backend/persistence/tests/test_prompt_template_model.py` (create if it doesn't exist, or extend if it does — check first)

**Interfaces:**
- Produces: `PromptTemplate` fields: `name` (CharField, e.g. `"need_to_sysreq"`, `"testcase_derive"` — NOT an enum/choices field, since templates are now open-ended, not a fixed 3-slot set), `content` (TextField), `version` (PositiveIntegerField, starts at 1, increments per name+workspace_id scope), `is_active` (BooleanField, default True), `workspace_id` (UUIDField, `null=True, blank=True` — NULL means tenant-wide default), plus standard `tenant`/timestamps from `TenantScopedModel`.
- Constraint: at most one `is_active=True` row per `(tenant, workspace_id, name)` — enforce via a partial unique index if the DB supports it, or via application-level enforcement in the create path (check both, prefer DB-level if Postgres partial indexes are already used elsewhere in this codebase — grep for `condition=` in existing migrations first).

- [ ] **Step 1: Verify the two flagged research ambiguities before writing model code**

Read `backend/application/architecture_decompose_service.py` and `backend/application/ai_review_service.py` in full — confirm whether either genuinely calls into `PromptTemplate`/`PROMPT_TEMPLATE_DEFAULTS` at runtime (a real consumer needing retrofit) or only imports the model for an unrelated reason (e.g. type hint, admin registration) — false positive. Document the finding in this task's report; if a real consumer is found, do NOT silently retrofit it in this task — flag it explicitly as a follow-up decision needed before Phase 4 is considered complete.

- [ ] **Step 2: Write failing tests for the new model shape**

```python
# backend/persistence/tests/test_prompt_template_model.py
import pytest
from django.db import IntegrityError


@pytest.mark.django_db
def test_create_tenant_global_template(tenant):
    from persistence.models import PromptTemplate
    tpl = PromptTemplate.objects.create(
        tenant=tenant, name="need_to_sysreq", content="Derive from {need_title}",
        version=1, is_active=True, workspace_id=None,
    )
    assert tpl.workspace_id is None
    assert tpl.is_active is True


@pytest.mark.django_db
def test_only_one_active_version_per_name_and_scope(tenant):
    from persistence.models import PromptTemplate
    PromptTemplate.objects.create(tenant=tenant, name="need_to_sysreq", content="v1", version=1, is_active=True)
    # Creating a second active=True row for the same (tenant, workspace_id=None, name)
    # must be rejected — confirm the exact enforcement mechanism (DB constraint vs.
    # application-level check in a create_or_version() helper, per Step 1's research)
    # before writing this assertion's exact expected exception type.
    ...


@pytest.mark.django_db
def test_workspace_override_and_tenant_global_coexist(tenant, workspace):
    from persistence.models import PromptTemplate
    PromptTemplate.objects.create(tenant=tenant, name="need_to_sysreq", content="global v1", version=1, is_active=True, workspace_id=None)
    PromptTemplate.objects.create(tenant=tenant, name="need_to_sysreq", content="workspace override v1", version=1, is_active=True, workspace_id=workspace.id)
    assert PromptTemplate.objects.filter(tenant=tenant, name="need_to_sysreq", workspace_id=None, is_active=True).count() == 1
    assert PromptTemplate.objects.filter(tenant=tenant, name="need_to_sysreq", workspace_id=workspace.id, is_active=True).count() == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
docker-compose build backend
docker-compose run --rm backend python -m pytest persistence/tests/test_prompt_template_model.py -v
```

- [ ] **Step 3: Replace the `PromptTemplate` model class**

Replace the existing 3-fixed-field class (`persistence/models.py:1560` per this plan's research) with the new shape. Keep `PROMPT_TEMPLATE_DEFAULTS` as a dict (extend it — see Task 2) but remove the old `UniqueConstraint(fields=["tenant"], ...)`, replacing with the new scoped-uniqueness approach decided in Step 1's follow-up read. Keep `get_slot`/`reset_slot`/`reset_all` methods ONLY if `settings_service.py`'s REST compatibility layer (Task 4) still needs them as-is — otherwise remove and let Task 4 build its own thin adapter.

- [ ] **Step 4: Write the migration**

Schema migration for the new fields, PLUS a data migration (in the same or a follow-up migration file, following the `RunPython` pattern from Phase 0's `0010_seed_state_meta_outdated_flags.py`) that:
- For every existing `PromptTemplate` singleton row (one per tenant, 3 slot values on it): create 3 new rows (`name="need_to_sysreq"`/`"sysreq_to_arch_assign"`/`"sysreq_decompose_next_level"`, `content=<old field value>`, `version=1`, `is_active=True`, `workspace_id=None`) preserving the tenant's actual customized content exactly.
- Idempotent: safe to re-run (check for existing rows with the target name+tenant+workspace_id=None before inserting).

- [ ] **Step 5: Run tests, verify pass**

- [ ] **Step 6: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/ backend/persistence/tests/test_prompt_template_model.py
git commit -m "feat: replace PromptTemplate singleton with named, versioned, workspace-overridable model"
```

---

## Task 2: Unified lookup helper + wire all 7 derive methods

**Files:**
- Modify: `backend/application/ai_derivation_service.py`
- Test: `backend/application/tests/test_ai_derivation_service.py`

**Interfaces:**
- Produces: `AiDerivationService._get_template_content(ctx: AuthContext, name: str, workspace_id: UUID | None = None) -> str` — replaces `_get_slot`. Lookup order: (1) active row where `workspace_id=workspace_id, name=name` if `workspace_id` given, (2) active row where `workspace_id=None, name=name` (tenant-global), (3) `PROMPT_TEMPLATE_DEFAULTS[name]` (factory default, extended to include all 7 names in this task).

- [ ] **Step 1: Write failing tests for `_get_template_content`'s fallback chain**

```python
@pytest.mark.django_db
def test_get_template_content_falls_back_workspace_then_global_then_factory(tenant, workspace, auth_ctx):
    from application.ai_derivation_service import AiDerivationService
    svc = AiDerivationService()

    # No rows at all -> factory default
    assert svc._get_template_content(auth_ctx, "testcase_derive") == TESTCASE_DERIVE_PROMPT_TEMPLATE  # import the constant to compare

    # Tenant-global row exists -> used over factory default
    from persistence.models import PromptTemplate
    PromptTemplate.objects.create(tenant=tenant, name="testcase_derive", content="GLOBAL OVERRIDE {requirement_title}", version=1, is_active=True, workspace_id=None)
    assert "GLOBAL OVERRIDE" in svc._get_template_content(auth_ctx, "testcase_derive")

    # Workspace-specific row exists -> used over tenant-global
    PromptTemplate.objects.create(tenant=tenant, name="testcase_derive", content="WORKSPACE OVERRIDE {requirement_title}", version=1, is_active=True, workspace_id=workspace.id)
    assert "WORKSPACE OVERRIDE" in svc._get_template_content(auth_ctx, "testcase_derive", workspace_id=workspace.id)
    # but a DIFFERENT workspace still gets the tenant-global one
    assert "GLOBAL OVERRIDE" in svc._get_template_content(auth_ctx, "testcase_derive", workspace_id=uuid4())
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement `_get_template_content`, extend `PROMPT_TEMPLATE_DEFAULTS`**

```python
PROMPT_TEMPLATE_DEFAULTS = {
    "need_to_sysreq": DEFAULT_NEED_TO_SYSREQ,
    "sysreq_to_arch_assign": DEFAULT_SYSREQ_TO_ARCH_ASSIGN,
    "sysreq_decompose_next_level": DEFAULT_SYSREQ_DECOMPOSE_NEXT_LEVEL,
    "testcase_derive": TESTCASE_DERIVE_PROMPT_TEMPLATE,
    "architecture_to_risk": ARCHITECTURE_TO_RISK_PROMPT_TEMPLATE,
    "workspace_to_glossary": WORKSPACE_TO_GLOSSARY_PROMPT_TEMPLATE,
    "decision_to_adr": DECISION_TO_ADR_PROMPT_TEMPLATE,
}

@staticmethod
def _get_template_content(ctx: AuthContext, name: str, workspace_id: "UUID | None" = None) -> str:
    from persistence.models import PromptTemplate
    if workspace_id is not None:
        row = PromptTemplate.objects.filter(tenant_id=ctx.tenant_id, workspace_id=workspace_id, name=name, is_active=True).first()
        if row is not None:
            return row.content
    row = PromptTemplate.objects.filter(tenant_id=ctx.tenant_id, workspace_id=None, name=name, is_active=True).first()
    if row is not None:
        return row.content
    return PROMPT_TEMPLATE_DEFAULTS[name]
```

- [ ] **Step 4: Rewire all 7 derive methods to call `_get_template_content` instead of `_get_slot`/inline constants**

For the 3 originally-slot-sourced methods: replace `self._get_slot(ctx, "need_to_sysreq")`-style calls with `self._get_template_content(ctx, "need_to_sysreq", workspace_id=<the relevant workspace id already in scope in that method>)`.
For the 4 Phase-3 methods: replace direct references to `TESTCASE_DERIVE_PROMPT_TEMPLATE` etc. with `self._get_template_content(ctx, "testcase_derive", workspace_id=...)`.

**Note for the implementer:** verify each method already has a `workspace_id` in scope at the point it builds its prompt (some derive methods take `requirement_id`/`architecture_element_id` and resolve `workspace_id` from the fetched entity later in the method body — make sure the template lookup happens AFTER that resolution, not before, or thread the id through earlier if needed).

- [ ] **Step 5: Run tests, verify pass, commit**

```bash
docker-compose run --rm backend python -m pytest application/tests/test_ai_derivation_service.py -v
git add backend/application/ai_derivation_service.py backend/application/tests/test_ai_derivation_service.py
git commit -m "feat: wire all 7 derive methods onto the unified workspace/tenant/factory template lookup"
```

---

## Task 3: MCP tools — `prompt_template.list()`, `.create()`, `.update()`

**Files:**
- Modify: `backend/mcp_server/tools/prompt_template.py`
- Test: `backend/mcp_server/tests/test_prompt_template_tool_group.py`

**Interfaces:**
- Produces: `_handle_list`, `_handle_create`, `_handle_update` on `PromptTemplateToolGroup`. Update `_handle_get` since the old `slot` param's fixed enum (`list(PROMPT_TEMPLATE_DEFAULTS.keys())`) is now open-ended (new names can be created at runtime) — decide whether to keep validating against `PROMPT_TEMPLATE_DEFAULTS.keys()` (rejecting truly novel names) or allow any name (since `.create()` can introduce new ones) — the latter is more consistent with "named, versioned, multi-template" being genuinely open-ended, not just the original 7. Document the decision.

- [ ] **Step 1: Write failing tests**

```python
def test_prompt_template_list_returns_all_active_templates(...):
    ...

def test_prompt_template_create_new_version_deactivates_old(...):
    # calling .create() for an existing (name, workspace_id) pair creates version N+1,
    # is_active=True, and flips the PREVIOUS active row for that scope to is_active=False
    ...

def test_prompt_template_update_is_an_alias_for_create_new_version(...):
    # decide: is .update() semantically distinct from .create() (e.g. .create() only
    # allowed for brand-new names, .update() only for existing ones — reject creating
    # a duplicate active version via the wrong verb), or are they the same operation
    # under two names for convenience? Make an explicit decision, test it.
    ...

def test_prompt_template_write_tools_require_editor_role():
    ...
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement the 3 new handlers**

```python
def _handle_list(self, *, params, auth_context, api_key):
    workspace_id = params.get("workspace_id")  # optional filter
    qs = PromptTemplate.objects.filter(tenant_id=auth_context.tenant_id, is_active=True)
    if workspace_id:
        qs = qs.filter(workspace_id=UUID(str(workspace_id)))
    return ToolResult.ok({"templates": [{"name": t.name, "workspace_id": str(t.workspace_id) if t.workspace_id else None, "version": t.version, "content": t.content} for t in qs]})

def _handle_create(self, *, params, auth_context, api_key):
    name = params.get("name")
    content = params.get("content")
    workspace_id = params.get("workspace_id")  # None = tenant-global
    if not name or not content:
        return ToolResult.error("VALIDATION_ERROR", "name and content are required")
    from django.db import transaction
    with transaction.atomic():
        prior = PromptTemplate.objects.select_for_update().filter(
            tenant_id=auth_context.tenant_id, name=name,
            workspace_id=UUID(str(workspace_id)) if workspace_id else None, is_active=True,
        ).first()
        next_version = (prior.version + 1) if prior else 1
        if prior:
            prior.is_active = False
            prior.save(update_fields=["is_active"])
        new_row = PromptTemplate.objects.create(
            tenant_id=auth_context.tenant_id, name=name, content=content,
            version=next_version, is_active=True,
            workspace_id=UUID(str(workspace_id)) if workspace_id else None,
        )
    write_mcp_audit("prompt_template.create", new_row.id, auth_context, api_key)
    return ToolResult.ok({"name": name, "version": next_version, "workspace_id": workspace_id})
```

**Note for the implementer:** verify `select_for_update()` is safe/consistent with this codebase's existing transaction patterns (check how Phase 0/3's `@atomic_transaction` decorator is used elsewhere — consider using it here too instead of a raw `transaction.atomic()` block, for consistency).

Update `_handle_get` per the Step-1-flagged naming-openness decision.

- [ ] **Step 4: Run tests, verify pass, commit**

```bash
git add backend/mcp_server/tools/prompt_template.py backend/mcp_server/tests/test_prompt_template_tool_group.py
git commit -m "feat: add prompt_template.list/.create/.update MCP tools"
```

---

## Task 4: REST-layer backward compatibility

**Files:**
- Modify: `backend/rest_api/settings_service.py` (or wherever the exact service lives — confirm exact file/module name first, this plan's research referenced `settings_service.py`/`settings_views.py` without a full path)
- Test: existing REST test file for prompt-template settings (confirm exact name, e.g. `test_llm_settings.py`/`test_prompt_template.py` — check `rest_api/tests/`)

**Interfaces:**
- Consumes: the new `PromptTemplate` model (Task 1), reading/writing only `workspace_id=None` (tenant-global) rows for the 3 original slot names — REST contract unchanged.

- [ ] **Step 1: Write failing tests proving the existing REST get/put/reset endpoints still work identically**

```python
def test_get_prompt_template_slot_still_works(api_client, tenant):
    response = api_client.get("/api/v1/settings/prompt-templates/need_to_sysreq/")
    assert response.status_code == 200
    # existing response shape assertions, unchanged

def test_put_prompt_template_slot_creates_new_active_version(api_client, tenant):
    # PUT with new content -> old tenant-global row deactivated, new one created,
    # GET afterward returns the new content
    ...
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Update `settings_service.py`'s get/put/reset to read/write the new model's tenant-global rows**

Reuse Task 2/3's create-new-version logic (extract a small shared helper if that avoids duplicating the version-bump transaction logic a third time — judgment call, document it).

- [ ] **Step 4: Run tests, verify pass, commit**

```bash
git add backend/rest_api/ 
git commit -m "fix: adapt REST prompt-template settings endpoints to the new versioned model"
```

---

## Post-Plan Verification

- [ ] Run full regression: `docker-compose run --rm backend python -m pytest application/tests/ mcp_server/tests/ persistence/tests/ rest_api/tests/ -q` — cross-check any new failures against files this plan touched.
- [ ] Confirm the 3 pre-registered `_WRITE_TOOL_PREFIXES` entries (`prompt_template.create`/`.update`/`.delete`) match the FINAL tool set — if `.delete` was never implemented (not requested by this plan), decide whether to remove the unused reservation or leave it for a future phase, and document the choice either way.
- [ ] Grep for any remaining reference to the old 3-fixed-field `PromptTemplate` shape (`get_slot`/`reset_slot`/`PROMPT_TEMPLATE_DEFAULTS[...]` direct dict access outside the new lookup helper) to confirm the retrofit is complete.

---

*Plan complete. Next: choose an execution approach.*
