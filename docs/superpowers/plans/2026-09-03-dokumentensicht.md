# Dokumentensicht Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the product's "lebendes Spezifikationsdokument" leitgedanke a real data model — a `Document` with a nested `DocumentSection` tree, a numbered read mode, a Markdown export, and `Baseline.scope="document"` bound to a real `Document` instead of an arbitrary artifact id.

**Architecture:** Two new tenant-scoped models in `persistence/models.py` (no new Django app), three new Layer-2 services (`DocumentService` for CRUD, `DocumentScopeService` for section→artifact-id resolution, `DocumentReadService` for numbering + Markdown assembly) and one new pure module `application/artifact_markdown.py` — the generic per-artifact Markdown renderer extracted out of `ExportService.export_markdown`, which the MCP-Modernisierung spec's `resources/read` consumes later. Layer 3 adds one zero-ORM REST module and one MCP tool group. Baseline binding is a *widening*, not a replacement: Layer 1 (`baseline/`) keeps its artifact-subtree resolver byte-for-byte and gains one explicit `item_ids` bypass, while the Document→ids resolution stays in Layer 2 where `TableQueryService` lives.

**Tech Stack:** Django 6.1 / DRF (`APIView`, no ViewSet), PostgreSQL 16 with row-level security and a GUC-gated immutability trigger, pytest, React 18 + TypeScript 5.5 strict, `react-markdown` 9 (already installed), CSS Modules with `styles/tokens.css` custom properties, vitest, react-i18next, Playwright.

**Spec:** docs/superpowers/specs/2026-09-03-dokumentensicht-design.md

## Global Constraints

- **The filter DSL is consumed, never re-invented.** `DocumentSection.query` is byte-identical to the Tabellenansicht wire format: `{"item_type": str, "filters": {...}, "sort": [...]}`. Evaluation goes exclusively through `application.table_query_service.TableQueryService().query(ctx=…, workspace_id=…, item_type=…, filters=…, sort=…) -> QuerySet`. No second filter format, no second validator.
- **The Markdown renderer is produced here and consumed by spec 7.** `application/artifact_markdown.render_artifact_markdown()` is created in Task 4 by extracting the body of `ExportService.export_markdown`. `diagram/mcp_artifact_provider.McpArtifactProvider` is **diagram-specific** (verified: it lives in `backend/diagram/`, is constructed as `McpArtifactProvider(diagram_manager=_manager)` in `diagram/services.py:54`) and is **not** touched by this plan.
- ADR-01: no ORM access in `rest_api/` or `mcp_server/`. `rest_api/tests/test_architecture.py` caps every new `*_views.py` at 0 direct-ORM lines and forbids importing `persistence.models`; `mcp_server/` root and `mcp_server/tools/` have their own ceilings. All ORM lives in `application/` (and, for scope resolution, in `baseline/`).
- Every DRF view calls `get_auth_context(request)` first; every service calls `self._set_tenant_context(ctx)` before its first query (RLS depends on it).
- Raise **plain `application.base.ValidationError` / `NotFoundError` / `PermissionDeniedError`**, never a subclass: `rest_api/views.py:_EXC_TO_HTTP` is keyed by *exact* exception type, so a subclass silently degrades to a 500.
- New audit entries reuse the declared ops `create` / `update` / `delete` from `audit/models.py`. **Never pass an `operation=` string that is not declared there** — `AuditLogWriter.write` validates via `full_clean` and `ServiceBase._audit` re-raises, so an undeclared op 500s the request *after* the mutation committed (`audit/tests/test_op_vocabulary.py` guards this).
- Both new tables get `ENABLE`/`FORCE ROW LEVEL SECURITY` plus a `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid` policy, exactly as `persistence/migrations/0067_rls_remaining_pl_tables.py` writes them.
- `bl_baseline_snapshot` carries a `BEFORE UPDATE OR DELETE` trigger (`bl_raise_immutable`, `baseline/migrations/0001_initial.py:163-193`). **Never use `ALTER TABLE … DISABLE TRIGGER`** to work around it: that is owner-only DDL and the runtime role `reqogniloom_app` cannot execute it. The repo's pattern is a transaction-local GUC read from inside the trigger function (Task 9).
- MCP tool payloads are serialised with **stdlib `json.dumps`** — every value must already be a JSON primitive. `str()` UUIDs and `.isoformat()` datetimes before they leave the service. And **never use `content` as a top-level payload key** in a tool result: it collides with the JSON-RPC envelope. `document.read` returns `{"markdown": …}`.
- **`format` is a reserved DRF query parameter** (content negotiation). The export endpoint therefore takes no format parameter at all — see Scope decision 2.
- Frontend: **no new inline `style={{`** anywhere under `frontend/src/components/`. `frontend/src/test/ui-ratchet.test.ts` asserts `expect(total).toBe(STYLE_BRACE_BASELINE)` (currently `1015`) — an *exact* equality, so a single new inline style block fails the build. Use CSS Modules with `var(--…)` tokens only. No hex literals in `.tsx`.
- Frontend: `data-testid` on every interactive element (Playwright E2E requirement). Reuse `components/shared/ConfirmDialog` for every destructive confirmation — never hand-roll one (`STATUS_BADGE_IMPLEMENTATION_BASELINE`-style ratchets exist for the shared components).
- i18n keys are **nested objects** in `frontend/src/i18n/locales/{de,en}.json`, never dotted flat keys (`keySeparator` is `"."`, so a literal `"documents.read"` key never resolves). `src/test/i18n-parity.test.ts` requires DE and EN to be structurally identical.
- **Vite has no working HMR on Windows.** After every frontend edit, restart the frontend container before running any Playwright check, or E2E silently tests stale code.
- Test commands in this plan use these two shells (run from the repo root):
  ```bash
  BT() { docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
      --project-directory . run --rm -e DB_NAME=reqlo_doc backend-test pytest "$@"; }
  FT() { docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
      --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run $*"; }
  ```
  The unique `DB_NAME` avoids the shared-`test_reqogniloom` collision when another session runs the suite in parallel.
- Never run the full backend suite or the full Playwright suite in the fix loop — only the modules touched. CI covers the matrix.
- **Migration file numbers are not load-bearing; the `dependencies` entry is.** This plan writes `persistence/migrations/0090_documents.py` and `0091_baseline_document_backfill_trigger.py`. Specs 1–9 each add persistence migrations, so those numbers will already be taken. Run `python manage.py makemigrations --dry-run` first, take the next free number, and point `dependencies` at the *actual* current persistence leaf.
- Branch: `feat/dokumentensicht`. Conventional Commits, English messages.

---

## Dependencies on other specs

This is spec 10 of 11; specs 1–9 are implemented first. Two hard consumptions and one production:

**Consumes — `2026-09-03-tabellenansicht-design.md` (spec 9), plan `docs/superpowers/plans/2026-09-03-tabellenansicht.md`.** The frozen filter-DSL contract, verified against that plan's Task 2/3:

```python
# backend/application/table_query_service.py
TABLE_ITEM_TYPES: dict[str, str]   # "Requirement" | "StakeholderNeed" | "ArchitectureElement"
                                   # | "TestCase" | "Adr" | "Risk" | "Issue" | "GlossaryTerm"
class TableQueryService(ServiceBase):
    def query(self, *, ctx: AuthContext, workspace_id: UUID, item_type: str,
              filters: Mapping[str, Any] | None = None,
              sort: Sequence[Mapping[str, Any]] | None = None) -> QuerySet: ...
def jsonable(value: Any) -> Any: ...
```

`compile_filters`/`compile_sort` in `application/table_filter_dsl.py` raise plain `ValidationError` for an unknown field or a disallowed operator. This plan never calls them directly — it goes through `TableQueryService.query`, so a stored `DocumentSection.query` that names a since-deleted field surfaces as the same 400 the table view produces.

**Consumes — `2026-09-03-datenmodell-konsolidierung-design.md` (spec 1).** That plan already touches `_resolve_document()` in `baseline/delta_index_builder.py`. This plan **extends** the function it leaves behind (one new early-return branch), it does not replace it. If spec 1's plan renamed the method, adjust Task 8's anchor accordingly — the extension point (the top of the document branch, before the recursive CTE runs) is unchanged.

**Produces — for `2026-09-03-mcp-modernisierung-design.md` (spec 7).** Spec 7's §4 says `resources/read` reuses "denselben Markdown-Renderer, den `McpArtifactProvider` heute für `artifact.get` nutzt". That premise is wrong: `McpArtifactProvider` is diagram-specific. The generic renderer is therefore built **here**, in Task 4, as `application/artifact_markdown.render_artifact_markdown()`. Spec 7's implementation imports it. Because spec 7 runs *before* spec 10 in the numbered order, whoever implements spec 7 first must either pull Task 4 forward or accept that `resources/read` lands one step later — flag it in that plan's dependency section.

**Produced for `2026-09-03-rollenbasierte-sichten-design.md` (spec 11).** The read-mode route `/documents/:id/read` is the reader role's default entry point. It is a plain route with no role gate in this plan; spec 11 adds the gate.

---

## Critical findings — verified against the code, and how this plan handles them

**F1 — `BaselineSnapshot.artifact` is a declared-but-dead column. The spec's §6 migration has no data to read.**
`BaselineSnapshot.artifact` exists (`baseline/models.py:83-89`, FK to `persistence.Artifact`, nullable). But `BaselineMetadata` (`baseline/types.py`) carries no artifact field, and `BaselineStore.persist_delta_index` (`baseline/store.py:101-113`) never sets it. `document_id` flows `BaselineFacade.create_baseline → baseline.services.build → DeltaIndexBuilder.build → ScopeResolver.resolve` and is used **only** to resolve the subtree — it is never persisted. Consequence: **every existing `scope="document"` `BaselineSnapshot` row has `artifact_id = NULL`.** The spec's §6 sentence "für jede vorhandene `scope='document'`-`BaselineSnapshot`-Historie mit einer Root-`artifact_id`" describes data that does not exist. Handled by Scope decision 3.

**F2 — `bl_baseline_snapshot` cannot be UPDATEd at all.**
`baseline/migrations/0001_initial.py:163-193` installs `trg_baseline_snapshot_immutable BEFORE UPDATE OR DELETE … EXECUTE FUNCTION bl_raise_immutable()`, which unconditionally `RAISE EXCEPTION 'Baselines are immutable'`. A naive `RunPython` backfill of `document_id` dies there. Handled by Task 9 (GUC-gated, column-scoped trigger exception) — never by `ALTER TABLE … DISABLE TRIGGER`, which the runtime role may not execute.

**F3 — changing what `document_id` *means* is a breaking API change the spec does not mention.**
Today `document_id` is a root **Artifact** UUID on three live surfaces: MCP `baseline.create` (`mcp_server/tools/baseline.py:103-107, 176, 190`), REST `POST /baselines/` under the view-facing name `artifact_id` (`rest_api/views.py:3202-3229`), and `AuditScope.artifact_id` (`application/baseline_facade.py:300-303`). Handled by Scope decision 4 (both accepted, artifact form deprecated but never broken).

**F4 — the SE-Auditor gate reads the same resolver.**
`BaselineFacade._enforce_audit_gate` builds `AuditScope(scope=scope, artifact_id=str(document_id))`; `AuditContext.scope_item_ids` (`traceability/audit/types.py:113-151`) resolves it through `baseline.services.resolve_scope_item_ids`. If a `Document` UUID reached that path unhandled, the gate would resolve an empty scope and wave every baseline through — a silent governance hole. Handled by Task 7 (`AuditScope.item_ids`, pre-seeded by the facade).

**F5 — two resolvers, not one.** `ScopeResolver._resolve_document` (`baseline/delta_index_builder.py:249-351`, returns `DeltaIndexTuple`s with versions *and* the in-scope TraceLinks) and `resolve_scope_item_ids` (`baseline/services.py:307-455`, returns id strings, used by `preview_scope_items` **and** the SE-Auditor). Both need the Document path; Tasks 7+8 cover them separately.

---

## Scope decisions (deviations from the spec, each deliberate)

1. **`Document`/`DocumentSection` live in `persistence/models.py`, not a new Django app.** They are `TenantScopedModel` subclasses with `pl_*` table names, exactly like `SavedView`/`UserTableViewState` from spec 9. A new app would need `INSTALLED_APPS`, an `apps.py`, its own migration chain and its own RLS bootstrapping for zero benefit.

2. **`GET documents/<id>/export/` takes no format parameter**, contrary to the spec's `?format=markdown`. `format` is reserved by DRF content negotiation — a stub renderer registered under that name corrupts the response body at HTTP 200 rather than erroring. The endpoint always returns `text/markdown` with a `Content-Disposition: attachment` header. When DOCX is added later it gets `?fmt=docx`, not `?format=`.

3. **Legacy document-scope baselines are migrated by an opt-in management command, not automatically.** Because of F1 there is no stored root artifact to migrate *from*. The only authoritative record of a legacy baseline's scope is its own frozen `BaselineDeltaIndexEntry` rows. `manage.py backfill_baseline_documents` therefore materialises, per legacy `scope="document"` snapshot, one `Document` plus **one `fixed` section holding exactly that snapshot's `entity_type='item'` ids** — lossless and heuristic-free, where guessing a subtree root from the id set would not be. A `fixed` section rather than the spec's `subtree` section is the direct consequence of F1. Running it is an operator decision (it creates one Document per legacy baseline, which is noise in a workspace that never used document scope); a schema migration must not make that decision. Read paths (`diff`, `get`, `VersionReconstructor`) read only `delta_entries` and are unaffected by a `NULL` `document_id`. **OFFENE FRAGE — see the end of this document.**

4. **`document_id` accepts a `Document` id *or* a root `Artifact` id.** `BaselineFacade.create_baseline` probes `Document` first; a miss falls back to today's artifact-subtree behaviour and logs at INFO. UUID primary keys make a cross-table collision impossible, and this is the same probe-in-order pattern `mcp_server/workspace_scope._TOOL_TARGETS` already relies on. Both REST and MCP schema descriptions are updated to name the Document form as primary and the artifact form as deprecated. No existing caller breaks.

5. **A `query` section is capped at `MAX_SECTION_ITEMS = 500` artifacts**, with a truncation marker in the rendered output and a `truncated: true` flag in the JSON. The spec's §9 "lebendes Dokument" risk has no ceiling; an unbounded live query behind a synchronous read endpoint is a self-inflicted timeout.

6. **Numbering rule, made concrete.** The spec says "1, 1.1, 1.2, 2, …" without saying whether artifacts and subsections share a counter. They do: within a section numbered `N`, the child counter starts at 1, the section's own artifacts consume it first (`N.1`, `N.2`, …) and its child sections continue it (`N.3`, …). That is how a classical Lastenheft reads and it makes every number unique within the document.

7. **The renderer keeps today's falsy-field behaviour.** `ExportService.export_markdown` skips a field when `not value`, so `0` and `False` are invisible. The extracted renderer preserves that exactly, so the refactor in Task 4 is behaviour-preserving. It is a real content gap for a Lastenheft (a `suspect: False` should arguably be printed) and is marked with a `ponytail:` ceiling comment rather than silently changed under an unrelated task.

8. **The read mode renders inside `AppShell`, not as a second router shell.** Print-cleanliness comes from a `@media print` block in `frontend/src/styles/global.css` that hides everything marked `data-print-hide` (sidebar, banner stack, page toolbars) and un-pads `main`. A parallel shell would duplicate the auth gate, the error boundary and the suspense fallback.

9. **No DOCX** (spec §5 already excludes it), **no baseline-pinned read mode** (spec §9 explicitly wants the read mode live), **no section-level permissions**.

---

## File Structure

```
backend/
  persistence/
    models.py                                   MOD  + Document, + DocumentSection
    migrations/0090_documents.py                NEW  CreateModel x2 + RLS enable/force/policy
    tests/test_document_models.py               NEW
  application/
    artifact_markdown.py                        NEW  generic per-artifact Markdown renderer
    document_service.py                         NEW  Document + DocumentSection CRUD, cycle guard
    document_scope_service.py                   NEW  section -> ordered, deduped artifact ids
    document_read_service.py                    NEW  numbering + Markdown assembly
    export_service.py                           MOD  export_markdown delegates to the renderer
    baseline_facade.py                          MOD  Document-aware document_id + AuditScope seeding
    workspace_lookup.py                         MOD  + "document" ENTITY_SPECS entry
    management/commands/backfill_baseline_documents.py  NEW
    tests/test_artifact_markdown.py             NEW
    tests/test_document_service.py              NEW
    tests/test_document_service_sections.py     NEW
    tests/test_document_scope_service.py        NEW
    tests/test_document_read_service.py         NEW
    tests/test_baseline_facade_document_scope.py NEW
    tests/test_backfill_baseline_documents.py   NEW
  baseline/
    services.py                                 MOD  + resolve_artifact_subtree_ids, + item_ids bypass
    delta_index_builder.py                      MOD  _resolve_document + explicit item_ids branch
    types.py                                    MOD  BaselineMetadata + document_id
    store.py                                    MOD  persist document FK
    models.py                                   MOD  + BaselineSnapshot.document FK
    migrations/0007_baseline_document_fk.py     NEW  AddField + trigger replacement
    tests/test_document_scope_binding.py        NEW
  traceability/audit/
    types.py                                    MOD  + AuditScope.item_ids
    rule_engine.py                              MOD  seed AuditContext._scope_item_ids
    tests/test_audit_scope_item_ids.py          NEW
  rest_api/
    document_views.py                           NEW  6 endpoints, zero ORM
    urls.py                                     MOD  6 paths before include(router.urls)
    views.py                                    MOD  BaselineViewSet.create accepts document_id
    serializers.py                              MOD  + document_id on the baseline create serializer
    tests/test_document_views.py                NEW
    tests/test_document_read_export_views.py    NEW
  mcp_server/
    tools/document.py                           NEW  document.list / document.get / document.read
    tool_registry.py                            MOD  + "document" group
    workspace_scope.py                          MOD  + document.get / document.read targets
    tools/baseline.py                           MOD  document_id schema description
    tests/test_document_tool_group.py           NEW
frontend/src/
  api/documents.ts                              NEW  types + wrappers
  components/Documents/
    DocumentsView.tsx / .module.css             NEW  list + create + delete
    DocumentSectionEditor.tsx / .module.css     NEW  section tree CRUD + reorder
    DocumentReadView.tsx / .module.css          NEW  numbered read mode + print
    index.ts                                    NEW  named re-exports
  components/NavigationShell/
    NavigationShell.tsx                         MOD  + 3 routes
    SidebarNavigation.tsx                       MOD  + nav entry, + data-print-hide
  styles/global.css                             MOD  + @media print block
  i18n/locales/{de,en}.json                     MOD  + "documents" namespace
  test/
    documentsApi.test.ts                        NEW
    DocumentsView.test.tsx                      NEW
    DocumentSectionEditor.test.tsx              NEW
    DocumentReadView.test.tsx                   NEW
e2e/
  document-read-mode.spec.ts                    NEW
```

---

## Task 1: Document and DocumentSection models

**Files:**
- Modify: `backend/persistence/models.py` (append after the last `TenantScopedModel` subclass)
- Create: `backend/persistence/migrations/0090_documents.py`
- Test: `backend/persistence/tests/test_document_models.py`

**Interfaces:**
- Produces: `persistence.models.Document`, `persistence.models.DocumentSection`, `DocumentSection.CONTENT_TYPE_QUERY|CONTENT_TYPE_FIXED|CONTENT_TYPE_SUBTREE`

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_document_models.py`:

```python
"""Document / DocumentSection model contract (Dokumentensicht spec §3)."""
from __future__ import annotations

import pytest

from persistence.models import Document, DocumentSection


@pytest.mark.django_db
def test_document_is_tenant_scoped(tenant, workspace):
    doc = Document.objects.create(
        tenant=tenant, workspace=workspace, title="Lastenheft V1"
    )
    assert doc.tenant_id == tenant.id
    assert doc.workspace_id == workspace.id
    assert Document._meta.db_table == "pl_document"


@pytest.mark.django_db
def test_section_defaults_and_ordering(tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="D")
    second = DocumentSection.objects.create(
        tenant=tenant, document=doc, title="Second", order=2,
        content_type=DocumentSection.CONTENT_TYPE_FIXED,
    )
    first = DocumentSection.objects.create(
        tenant=tenant, document=doc, title="First", order=1,
        content_type=DocumentSection.CONTENT_TYPE_FIXED,
    )
    assert list(doc.sections.all()) == [first, second]
    assert first.parent_section_id is None
    assert first.fixed_artifact_ids == []
    assert first.query is None
    assert first.subtree_root_artifact_id is None


@pytest.mark.django_db
def test_deleting_document_cascades_to_sections(tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="D")
    DocumentSection.objects.create(
        tenant=tenant, document=doc, title="S",
        content_type=DocumentSection.CONTENT_TYPE_FIXED,
    )
    doc.delete()
    assert DocumentSection.objects.count() == 0


@pytest.mark.django_db
def test_child_sections_use_self_referential_parent(tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="D")
    parent = DocumentSection.objects.create(
        tenant=tenant, document=doc, title="P", order=1,
        content_type=DocumentSection.CONTENT_TYPE_FIXED,
    )
    child = DocumentSection.objects.create(
        tenant=tenant, document=doc, title="C", order=1,
        parent_section=parent, content_type=DocumentSection.CONTENT_TYPE_FIXED,
    )
    assert list(parent.children.all()) == [child]
```

Reuse the `tenant` / `workspace` fixtures already declared in `backend/persistence/tests/conftest.py`; if they are not there, copy the two-fixture block from `backend/application/tests/conftest.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `BT persistence/tests/test_document_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Document' from 'persistence.models'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/persistence/models.py`:

```python
class Document(TenantScopedModel):
    """A living specification document (Dokumentensicht spec §3).

    The container the product's "lebendes Spezifikationsdokument" leitgedanke
    always implied but never had. Content is not stored here — it is resolved
    at read time from the ordered :class:`DocumentSection` tree, so a document
    reflects the current state of the artifacts it points at.
    """

    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "pl_document"
        indexes = [
            models.Index(
                fields=["workspace", "title"], name="idx_document_ws_title"
            ),
        ]
        ordering = ["title"]

    def __str__(self) -> str:
        return f"Document({self.title!r}, id={self.id})"


class DocumentSection(TenantScopedModel):
    """One chapter of a :class:`Document` (Dokumentensicht spec §3).

    Three content types, each reusing a mechanism that already exists rather
    than inventing a fourth:

      ``query``   — the Tabellenansicht filter DSL verbatim
                    (``{"item_type": ..., "filters": {...}, "sort": [...]}``),
                    evaluated at read time, so the section "lives".
      ``fixed``   — an explicitly curated, ordered artifact id list.
      ``subtree`` — an ``Artifact`` subtree, i.e. exactly what
                    ``Baseline.scope="document"`` resolved before this model
                    existed. Kept so the legacy behaviour has a home.

    ``parent_section`` is the same self-referential pattern as
    ``Artifact.parent``. Cycles are rejected by
    ``application.document_service.DocumentService`` on write, not here —
    a model-level check would fire on every ``save()`` including migrations.
    """

    CONTENT_TYPE_QUERY = "query"
    CONTENT_TYPE_FIXED = "fixed"
    CONTENT_TYPE_SUBTREE = "subtree"
    CONTENT_TYPE_CHOICES = (
        (CONTENT_TYPE_QUERY, "Query"),
        (CONTENT_TYPE_FIXED, "Fixed List"),
        (CONTENT_TYPE_SUBTREE, "Artifact Subtree"),
    )

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="sections"
    )
    parent_section = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    title = models.CharField(max_length=255)
    order = models.IntegerField(default=0)
    content_type = models.CharField(
        max_length=16, choices=CONTENT_TYPE_CHOICES, default=CONTENT_TYPE_FIXED
    )
    #: ``content_type="query"``: the frozen Tabellenansicht filter DSL payload.
    query = models.JSONField(null=True, blank=True)
    #: ``content_type="fixed"``: ordered list of artifact id strings.
    fixed_artifact_ids = models.JSONField(default=list, blank=True)
    #: ``content_type="subtree"``: root of an ``Artifact.parent`` subtree.
    subtree_root_artifact = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_sections",
    )

    class Meta:
        db_table = "pl_document_section"
        ordering = ["order", "title"]
        indexes = [
            models.Index(
                fields=["document", "parent_section", "order"],
                name="idx_docsection_doc_parent",
            ),
        ]

    def __str__(self) -> str:
        return f"DocumentSection({self.title!r}, {self.content_type})"
```

Then generate and hand-edit the migration:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
  --project-directory . run --rm backend-test python manage.py makemigrations persistence \
  --name documents
```

Append the RLS block to the generated `operations` list, byte-identical in shape to `persistence/migrations/0067_rls_remaining_pl_tables.py`:

```python
_TENANT_TABLES = ["pl_document", "pl_document_section"]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)
```

and add `migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql())` as the last operation.

- [ ] **Step 4: Run test to verify it passes**

Run: `BT persistence/tests/test_document_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/0090_documents.py \
        backend/persistence/tests/test_document_models.py
git commit -m "feat(documents): add Document and DocumentSection models"
```

---

## Task 2: DocumentService — document CRUD with the cycle guard

**Files:**
- Create: `backend/application/document_service.py`
- Test: `backend/application/tests/test_document_service.py`

**Interfaces:**
- Consumes: `persistence.models.Document`, `application.base.ServiceBase`
- Produces:
  ```python
  MAX_SECTION_DEPTH: int  # 10
  class DocumentService(ServiceBase):
      def list_documents(self, *, ctx, workspace_id: UUID) -> list[dict]
      def get_document(self, *, ctx, document_id: UUID) -> dict
      def create_document(self, *, ctx, workspace_id: UUID, title: str, description: str = "") -> dict
      def update_document(self, *, ctx, document_id: UUID, title=None, description=None) -> dict
      def delete_document(self, *, ctx, document_id: UUID) -> None
  ```
  Every returned dict is JSON-primitive only: `{"id", "workspace_id", "title", "description", "created_at", "section_count"}`.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_document_service.py`:

```python
"""DocumentService CRUD (Dokumentensicht spec §7)."""
from __future__ import annotations

import json
import uuid

import pytest

from application.base import NotFoundError, ValidationError
from application.document_service import DocumentService
from persistence.models import Document


@pytest.mark.django_db
def test_create_returns_json_primitive_dict(ctx, workspace):
    doc = DocumentService().create_document(
        ctx=ctx, workspace_id=workspace.id, title="Lastenheft"
    )
    assert doc["title"] == "Lastenheft"
    assert doc["section_count"] == 0
    assert isinstance(doc["id"], str)
    assert isinstance(doc["workspace_id"], str)
    json.dumps(doc)  # the MCP transport uses stdlib json


@pytest.mark.django_db
def test_create_rejects_blank_title(ctx, workspace):
    with pytest.raises(ValidationError):
        DocumentService().create_document(
            ctx=ctx, workspace_id=workspace.id, title="   "
        )


@pytest.mark.django_db
def test_list_is_workspace_scoped(ctx, tenant, workspace, other_workspace):
    Document.objects.create(tenant=tenant, workspace=workspace, title="Mine")
    Document.objects.create(tenant=tenant, workspace=other_workspace, title="Theirs")
    titles = [d["title"] for d in DocumentService().list_documents(
        ctx=ctx, workspace_id=workspace.id
    )]
    assert titles == ["Mine"]


@pytest.mark.django_db
def test_get_unknown_id_raises_not_found(ctx):
    with pytest.raises(NotFoundError):
        DocumentService().get_document(ctx=ctx, document_id=uuid.uuid4())


@pytest.mark.django_db
def test_update_changes_title_and_leaves_description(ctx, tenant, workspace):
    doc = Document.objects.create(
        tenant=tenant, workspace=workspace, title="Old", description="keep me"
    )
    updated = DocumentService().update_document(
        ctx=ctx, document_id=doc.id, title="New"
    )
    assert updated["title"] == "New"
    assert updated["description"] == "keep me"


@pytest.mark.django_db
def test_delete_removes_the_row(ctx, tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="Gone")
    DocumentService().delete_document(ctx=ctx, document_id=doc.id)
    assert not Document.objects.filter(id=doc.id).exists()
```

`ctx`, `tenant`, `workspace` come from `backend/application/tests/conftest.py`. Add an `other_workspace` fixture there if it is missing:

```python
@pytest.fixture
def other_workspace(tenant):
    from persistence.models import Workspace

    return Workspace.objects.create(tenant=tenant, name="Other workspace")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_document_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.document_service'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/document_service.py`:

```python
"""Document / DocumentSection CRUD (Dokumentensicht spec §3, §7).

Layer 2 owns every ORM access for the document tree; ``rest_api`` and
``mcp_server`` call this service and never the models (ADR-01).

Audit ops are the declared ``create``/``update``/``delete`` from
``audit/models.py`` — a document is a plain business entity, so it reuses the
generic vocabulary rather than adding a ``document.*`` family that
``AuditLogWriter.write``'s ``full_clean`` would reject.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from application.base import NotFoundError, ServiceBase, ValidationError
from auth_tenancy.context import AuthContext

logger = logging.getLogger(__name__)

#: Ceiling for the ``parent_section`` chain. Ten levels is far past any real
#: Lastenheft gliederung and bounds the recursive walks in
#: ``DocumentReadService`` without needing a cycle-detection set at read time.
MAX_SECTION_DEPTH = 10


def _document_to_dict(document: Any, section_count: int) -> dict[str, Any]:
    """Serialise a ``Document`` to JSON primitives only (stdlib-json safe)."""
    return {
        "id": str(document.id),
        "workspace_id": str(document.workspace_id),
        "title": document.title,
        "description": document.description or "",
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "section_count": section_count,
    }


class DocumentService(ServiceBase):
    """CRUD for :class:`persistence.models.Document`."""

    # ---------- reads ----------

    def list_documents(
        self, *, ctx: AuthContext, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        """Return every document of *workspace_id*, ordered by title."""
        self._set_tenant_context(ctx)
        from django.db.models import Count

        from persistence.models import Document

        rows = (
            Document.objects.filter(workspace_id=workspace_id)
            .annotate(_section_count=Count("sections"))
            .order_by("title")
        )
        return [_document_to_dict(row, row._section_count) for row in rows]

    def get_document(self, *, ctx: AuthContext, document_id: UUID) -> dict[str, Any]:
        """Return one document, or raise ``NotFoundError``."""
        self._set_tenant_context(ctx)
        document = self._load(document_id)
        return _document_to_dict(document, document.sections.count())

    # ---------- writes ----------

    def create_document(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        title: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Create an empty document."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValidationError("Document title must not be empty.")

        from persistence.models import Document

        document = Document.objects.create(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace_id,
            title=clean_title,
            description=(description or "").strip(),
        )
        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="Document",
            entity_id=document.id,
            details={"title": clean_title, "workspace_id": str(workspace_id)},
        )
        return _document_to_dict(document, 0)

    def update_document(
        self,
        *,
        ctx: AuthContext,
        document_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict[str, Any]:
        """Patch title and/or description. Omitted fields are left untouched."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        document = self._load(document_id)

        if title is not None:
            clean_title = title.strip()
            if not clean_title:
                raise ValidationError("Document title must not be empty.")
            document.title = clean_title
        if description is not None:
            document.description = description.strip()
        document.save()

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Document",
            entity_id=document.id,
            details={"title": document.title},
        )
        return _document_to_dict(document, document.sections.count())

    def delete_document(self, *, ctx: AuthContext, document_id: UUID) -> None:
        """Hard-delete a document and, by CASCADE, all of its sections.

        A hard delete is correct here: a Document holds no content of its own,
        only pointers. The artifacts it referenced are untouched, and a
        ``scope="document"`` BaselineSnapshot that named it keeps its frozen
        delta entries (``BaselineSnapshot.document`` is ``SET_NULL``).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        document = self._load(document_id)
        title = document.title
        document.delete()
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="Document",
            entity_id=document_id,
            details={"title": title},
        )

    # ---------- internals ----------

    @staticmethod
    def _load(document_id: UUID) -> Any:
        from persistence.models import Document

        try:
            return Document.objects.get(id=document_id)
        except Document.DoesNotExist as exc:
            raise NotFoundError(f"Document {document_id} not found.") from exc


__all__ = ["DocumentService", "MAX_SECTION_DEPTH"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_document_service.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/document_service.py backend/application/tests/test_document_service.py \
        backend/application/tests/conftest.py
git commit -m "feat(documents): add DocumentService CRUD"
```

---

## Task 3: DocumentSection CRUD, reorder and the cycle guard

**Files:**
- Modify: `backend/application/document_service.py` (append methods to `DocumentService`)
- Test: `backend/application/tests/test_document_service_sections.py`

**Interfaces:**
- Consumes: `DocumentService._load`, `MAX_SECTION_DEPTH`
- Produces:
  ```python
  def list_sections(self, *, ctx, document_id: UUID) -> list[dict]
  def create_section(self, *, ctx, document_id: UUID, title: str, content_type: str,
                     parent_section_id: UUID | None = None, order: int = 0,
                     query: dict | None = None, fixed_artifact_ids: list[str] | None = None,
                     subtree_root_artifact_id: UUID | None = None) -> dict
  def update_section(self, *, ctx, section_id: UUID, **fields) -> dict
  def delete_section(self, *, ctx, section_id: UUID) -> None
  def reorder_sections(self, *, ctx, document_id: UUID, ordered_section_ids: list[UUID]) -> list[dict]
  ```
  Section dict: `{"id", "document_id", "parent_section_id", "title", "order", "content_type", "query", "fixed_artifact_ids", "subtree_root_artifact_id"}`.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_document_service_sections.py`:

```python
"""DocumentSection CRUD, reorder and cycle rejection (spec §3, §9)."""
from __future__ import annotations

import uuid

import pytest

from application.base import ValidationError
from application.document_service import DocumentService
from persistence.models import Document, DocumentSection


@pytest.fixture
def document(tenant, workspace):
    return Document.objects.create(tenant=tenant, workspace=workspace, title="D")


@pytest.mark.django_db
def test_create_query_section_stores_the_dsl_payload(ctx, document):
    payload = {"item_type": "Requirement", "filters": {"category": {"op": "in", "value": ["functional"]}}}
    section = DocumentService().create_section(
        ctx=ctx, document_id=document.id, title="Functional",
        content_type="query", query=payload,
    )
    assert section["content_type"] == "query"
    assert section["query"] == payload
    assert isinstance(section["id"], str)


@pytest.mark.django_db
def test_query_section_without_query_is_rejected(ctx, document):
    with pytest.raises(ValidationError) as exc:
        DocumentService().create_section(
            ctx=ctx, document_id=document.id, title="Broken", content_type="query"
        )
    assert "query" in str(exc.value)


@pytest.mark.django_db
def test_subtree_section_without_root_is_rejected(ctx, document):
    with pytest.raises(ValidationError) as exc:
        DocumentService().create_section(
            ctx=ctx, document_id=document.id, title="Broken", content_type="subtree"
        )
    assert "subtree_root_artifact_id" in str(exc.value)


@pytest.mark.django_db
def test_unknown_content_type_is_rejected(ctx, document):
    with pytest.raises(ValidationError):
        DocumentService().create_section(
            ctx=ctx, document_id=document.id, title="X", content_type="magic"
        )


@pytest.mark.django_db
def test_parent_from_another_document_is_rejected(ctx, tenant, workspace, document):
    other = Document.objects.create(tenant=tenant, workspace=workspace, title="Other")
    foreign = DocumentSection.objects.create(
        tenant=tenant, document=other, title="F", content_type="fixed"
    )
    with pytest.raises(ValidationError) as exc:
        DocumentService().create_section(
            ctx=ctx, document_id=document.id, title="Child",
            content_type="fixed", parent_section_id=foreign.id,
        )
    assert "same document" in str(exc.value)


@pytest.mark.django_db
def test_reparenting_a_section_under_its_own_child_is_rejected(ctx, tenant, document):
    svc = DocumentService()
    a = DocumentSection.objects.create(tenant=tenant, document=document, title="A", content_type="fixed")
    b = DocumentSection.objects.create(tenant=tenant, document=document, title="B", content_type="fixed", parent_section=a)
    with pytest.raises(ValidationError) as exc:
        svc.update_section(ctx=ctx, section_id=a.id, parent_section_id=b.id)
    assert "cycle" in str(exc.value).lower()


@pytest.mark.django_db
def test_section_cannot_be_its_own_parent(ctx, tenant, document):
    a = DocumentSection.objects.create(tenant=tenant, document=document, title="A", content_type="fixed")
    with pytest.raises(ValidationError):
        DocumentService().update_section(ctx=ctx, section_id=a.id, parent_section_id=a.id)


@pytest.mark.django_db
def test_nesting_deeper_than_max_depth_is_rejected(ctx, tenant, document):
    from application.document_service import MAX_SECTION_DEPTH

    parent = None
    for index in range(MAX_SECTION_DEPTH):
        parent = DocumentSection.objects.create(
            tenant=tenant, document=document, title=f"S{index}",
            content_type="fixed", parent_section=parent,
        )
    with pytest.raises(ValidationError) as exc:
        DocumentService().create_section(
            ctx=ctx, document_id=document.id, title="TooDeep",
            content_type="fixed", parent_section_id=parent.id,
        )
    assert "depth" in str(exc.value).lower()


@pytest.mark.django_db
def test_reorder_rewrites_order_in_the_given_sequence(ctx, tenant, document):
    a = DocumentSection.objects.create(tenant=tenant, document=document, title="A", order=0, content_type="fixed")
    b = DocumentSection.objects.create(tenant=tenant, document=document, title="B", order=1, content_type="fixed")
    rows = DocumentService().reorder_sections(
        ctx=ctx, document_id=document.id, ordered_section_ids=[b.id, a.id]
    )
    assert [r["title"] for r in rows] == ["B", "A"]
    assert [r["order"] for r in rows] == [0, 1]


@pytest.mark.django_db
def test_reorder_rejects_a_foreign_section_id(ctx, tenant, workspace, document):
    other = Document.objects.create(tenant=tenant, workspace=workspace, title="Other")
    foreign = DocumentSection.objects.create(tenant=tenant, document=other, title="F", content_type="fixed")
    with pytest.raises(ValidationError):
        DocumentService().reorder_sections(
            ctx=ctx, document_id=document.id, ordered_section_ids=[foreign.id]
        )


@pytest.mark.django_db
def test_delete_section_cascades_to_children(ctx, tenant, document):
    a = DocumentSection.objects.create(tenant=tenant, document=document, title="A", content_type="fixed")
    DocumentSection.objects.create(tenant=tenant, document=document, title="B", content_type="fixed", parent_section=a)
    DocumentService().delete_section(ctx=ctx, section_id=a.id)
    assert DocumentSection.objects.filter(document=document).count() == 0


@pytest.mark.django_db
def test_fixed_artifact_ids_must_be_a_list_of_uuid_strings(ctx, document):
    with pytest.raises(ValidationError):
        DocumentService().create_section(
            ctx=ctx, document_id=document.id, title="X",
            content_type="fixed", fixed_artifact_ids=["not-a-uuid"],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_document_service_sections.py -v`
Expected: FAIL with `AttributeError: 'DocumentService' object has no attribute 'create_section'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/application/document_service.py` (module level, above the class):

```python
_CONTENT_TYPES = ("query", "fixed", "subtree")


def _section_to_dict(section: Any) -> dict[str, Any]:
    """Serialise a ``DocumentSection`` to JSON primitives only."""
    return {
        "id": str(section.id),
        "document_id": str(section.document_id),
        "parent_section_id": (
            str(section.parent_section_id) if section.parent_section_id else None
        ),
        "title": section.title,
        "order": int(section.order),
        "content_type": section.content_type,
        "query": section.query,
        "fixed_artifact_ids": [str(v) for v in (section.fixed_artifact_ids or [])],
        "subtree_root_artifact_id": (
            str(section.subtree_root_artifact_id)
            if section.subtree_root_artifact_id
            else None
        ),
    }


def _validated_artifact_ids(raw: Any) -> list[str]:
    """Coerce ``fixed_artifact_ids`` to a list of UUID strings, or raise."""
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValidationError("'fixed_artifact_ids' must be a list of artifact UUIDs.")
    out: list[str] = []
    for value in raw:
        try:
            out.append(str(UUID(str(value))))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValidationError(
                f"'fixed_artifact_ids' contains a non-UUID value: {value!r}"
            ) from exc
    return out
```

and these methods to `DocumentService`:

```python
    # ---------- sections ----------

    def list_sections(
        self, *, ctx: AuthContext, document_id: UUID
    ) -> list[dict[str, Any]]:
        """Return every section of a document in ``(order, title)`` order."""
        self._set_tenant_context(ctx)
        document = self._load(document_id)
        return [_section_to_dict(s) for s in document.sections.all()]

    def create_section(
        self,
        *,
        ctx: AuthContext,
        document_id: UUID,
        title: str,
        content_type: str,
        parent_section_id: Optional[UUID] = None,
        order: int = 0,
        query: Optional[dict] = None,
        fixed_artifact_ids: Optional[list] = None,
        subtree_root_artifact_id: Optional[UUID] = None,
    ) -> dict[str, Any]:
        """Create one section under *document_id*."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        document = self._load(document_id)

        clean_title = (title or "").strip()
        if not clean_title:
            raise ValidationError("Section title must not be empty.")
        self._validate_content(content_type, query, subtree_root_artifact_id)
        parent = self._validated_parent(document, parent_section_id)

        from persistence.models import DocumentSection

        section = DocumentSection.objects.create(
            tenant_id=ctx.tenant_id,
            document=document,
            parent_section=parent,
            title=clean_title,
            order=int(order),
            content_type=content_type,
            query=query if content_type == "query" else None,
            fixed_artifact_ids=(
                _validated_artifact_ids(fixed_artifact_ids)
                if content_type == "fixed"
                else []
            ),
            subtree_root_artifact_id=(
                subtree_root_artifact_id if content_type == "subtree" else None
            ),
        )
        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="DocumentSection",
            entity_id=section.id,
            details={"document_id": str(document_id), "title": clean_title},
        )
        return _section_to_dict(section)

    def update_section(
        self,
        *,
        ctx: AuthContext,
        section_id: UUID,
        title: Optional[str] = None,
        order: Optional[int] = None,
        parent_section_id: Optional[UUID] = _UNSET,
        content_type: Optional[str] = None,
        query: Optional[dict] = _UNSET,
        fixed_artifact_ids: Optional[list] = _UNSET,
        subtree_root_artifact_id: Optional[UUID] = _UNSET,
    ) -> dict[str, Any]:
        """Patch one section. ``_UNSET`` distinguishes "omitted" from "set to None"."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        section = self._load_section(section_id)

        if title is not None:
            clean_title = title.strip()
            if not clean_title:
                raise ValidationError("Section title must not be empty.")
            section.title = clean_title
        if order is not None:
            section.order = int(order)
        if parent_section_id is not _UNSET:
            section.parent_section = self._validated_parent(
                section.document, parent_section_id, moving=section
            )

        effective_type = content_type or section.content_type
        effective_query = section.query if query is _UNSET else query
        effective_root = (
            section.subtree_root_artifact_id
            if subtree_root_artifact_id is _UNSET
            else subtree_root_artifact_id
        )
        self._validate_content(effective_type, effective_query, effective_root)

        section.content_type = effective_type
        section.query = effective_query if effective_type == "query" else None
        if fixed_artifact_ids is not _UNSET:
            section.fixed_artifact_ids = _validated_artifact_ids(fixed_artifact_ids)
        if effective_type != "fixed":
            section.fixed_artifact_ids = []
        section.subtree_root_artifact_id = (
            effective_root if effective_type == "subtree" else None
        )
        section.save()

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="DocumentSection",
            entity_id=section.id,
            details={"title": section.title},
        )
        return _section_to_dict(section)

    def delete_section(self, *, ctx: AuthContext, section_id: UUID) -> None:
        """Delete a section and, by CASCADE, its children."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        section = self._load_section(section_id)
        title = section.title
        section.delete()
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="DocumentSection",
            entity_id=section_id,
            details={"title": title},
        )

    def reorder_sections(
        self, *, ctx: AuthContext, document_id: UUID, ordered_section_ids: list
    ) -> list[dict[str, Any]]:
        """Rewrite ``order`` to the index of each id in *ordered_section_ids*.

        Sections not named in the list keep their current ``order`` — a reorder
        is per sibling level, and the caller only ever sends one level's ids.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        document = self._load(document_id)

        from django.db import transaction
        from persistence.models import DocumentSection

        wanted = [UUID(str(value)) for value in ordered_section_ids]
        by_id = {
            s.id: s for s in DocumentSection.objects.filter(document=document, id__in=wanted)
        }
        missing = [str(v) for v in wanted if v not in by_id]
        if missing:
            raise ValidationError(
                f"Section(s) not in this document: {', '.join(sorted(missing))}"
            )

        with transaction.atomic():
            for index, section_id in enumerate(wanted):
                section = by_id[section_id]
                section.order = index
                section.save(update_fields=["order"])

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Document",
            entity_id=document.id,
            details={"reordered": [str(v) for v in wanted]},
        )
        return [_section_to_dict(by_id[section_id]) for section_id in wanted]

    # ---------- section internals ----------

    @staticmethod
    def _load_section(section_id: UUID) -> Any:
        from persistence.models import DocumentSection

        try:
            return DocumentSection.objects.select_related("document").get(id=section_id)
        except DocumentSection.DoesNotExist as exc:
            raise NotFoundError(f"DocumentSection {section_id} not found.") from exc

    @staticmethod
    def _validate_content(
        content_type: str, query: Optional[dict], subtree_root_artifact_id: Optional[UUID]
    ) -> None:
        """Reject a content_type whose required payload is missing."""
        if content_type not in _CONTENT_TYPES:
            raise ValidationError(
                f"Unknown content_type '{content_type}'. "
                f"Allowed: {', '.join(_CONTENT_TYPES)}"
            )
        if content_type == "query" and not isinstance(query, dict):
            raise ValidationError(
                "A section with content_type='query' needs a 'query' object "
                "({'item_type': ..., 'filters': {...}, 'sort': [...]})."
            )
        if content_type == "query" and not query.get("item_type"):
            raise ValidationError("'query' must name an 'item_type'.")
        if content_type == "subtree" and subtree_root_artifact_id is None:
            raise ValidationError(
                "A section with content_type='subtree' needs a "
                "'subtree_root_artifact_id'."
            )

    def _validated_parent(
        self, document: Any, parent_section_id: Optional[UUID], moving: Any = None
    ) -> Any:
        """Resolve and validate a parent section: same document, no cycle, depth ok.

        The cycle check walks up from the candidate parent (spec §9). Bounded by
        ``MAX_SECTION_DEPTH + 1`` iterations so a pre-existing cycle in the data
        cannot spin forever — that walk is the guard, not a symptom of one.
        """
        if parent_section_id is None:
            return None
        parent = self._load_section(parent_section_id)
        if parent.document_id != document.id:
            raise ValidationError(
                "parent_section must belong to the same document as the section."
            )
        if moving is not None and parent.id == moving.id:
            raise ValidationError("A section cannot be its own parent (cycle).")

        depth = 1
        node = parent
        while node.parent_section_id is not None:
            if moving is not None and node.parent_section_id == moving.id:
                raise ValidationError(
                    "Moving this section under that parent would create a cycle."
                )
            depth += 1
            if depth > MAX_SECTION_DEPTH:
                raise ValidationError(
                    f"Section nesting depth exceeds the maximum of {MAX_SECTION_DEPTH}."
                )
            node = self._load_section(node.parent_section_id)
        if depth >= MAX_SECTION_DEPTH:
            raise ValidationError(
                f"Section nesting depth exceeds the maximum of {MAX_SECTION_DEPTH}."
            )
        return parent
```

Add the sentinel next to `MAX_SECTION_DEPTH`:

```python
class _Unset:
    """Sentinel: 'this keyword was not supplied' (distinct from ``None``)."""

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<UNSET>"


_UNSET = _Unset()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_document_service_sections.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/document_service.py \
        backend/application/tests/test_document_service_sections.py
git commit -m "feat(documents): add DocumentSection CRUD, reorder and cycle guard"
```

---

## Task 4: Generic artifact Markdown renderer

**Files:**
- Create: `backend/application/artifact_markdown.py`
- Modify: `backend/application/export_service.py:428-459` (`export_markdown` body)
- Test: `backend/application/tests/test_artifact_markdown.py`

**Interfaces:**
- Produces:
  ```python
  def render_artifact_markdown(
      row: Mapping[str, Any], *, heading_level: int = 2,
      number: str | None = None,
      skip_fields: Sequence[str] = ("title", "description"),
  ) -> str
  ```
  Returns a Markdown block ending in a single blank line. Consumed by `DocumentReadService` (Task 6), by `ExportService.export_markdown`, and — later — by the MCP-Modernisierung spec's `resources/read`.

**⚠️ KNOWN CROSS-PLAN CONFLICT (found 2026-09-04, not yet reconciled — see
`docs/superpowers/plans/2026-09-04-open-decisions.md`):** the MCP-Modernisierung plan
(`2026-09-03-mcp-modernisierung.md`, its own Task 5) independently defines a function of
the same name at the same module path, but with a **different signature**:
`render_artifact_markdown(artifact_id: UUID | str, ctx: AuthContext) -> str` —
ID-resolving, field-class-reflection-driven, no numbering concept. **Do not implement
both verbatim.** Recommended reconciliation at implementation time: this plan's
dict-based, numbering-aware signature becomes the shared low-level primitive (it is the
more general shape — an ID-resolving wrapper is trivial to build on top of a dict-based
renderer, the reverse is not); MCP-Modernisierung's Task 5 should be renamed to something
distinct (e.g. `render_artifact_resource(artifact_id, ctx) -> str`) and delegate to this
function for the actual formatting after resolving its own `row` dict. Whoever implements
either task first should leave the module open for the other shape rather than closing it
off.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_artifact_markdown.py`:

```python
"""Generic per-artifact Markdown renderer (Dokumentensicht spec §4)."""
from __future__ import annotations

from application.artifact_markdown import render_artifact_markdown


def test_renders_title_as_a_heading_at_the_requested_level():
    out = render_artifact_markdown({"title": "Brake force"}, heading_level=3)
    assert out.splitlines()[0] == "### Brake force"


def test_number_is_prefixed_to_the_heading():
    out = render_artifact_markdown({"title": "Brake force"}, number="2.1")
    assert out.splitlines()[0] == "## 2.1 Brake force"


def test_description_becomes_the_body_paragraph():
    out = render_artifact_markdown({"title": "T", "description": "Some prose."})
    assert "Some prose." in out
    assert "**description:**" not in out


def test_remaining_fields_render_as_a_definition_list():
    out = render_artifact_markdown({"title": "T", "status": "draft", "uid": "REQ-1"})
    assert "**status:** draft  " in out
    assert "**uid:** REQ-1  " in out


def test_falsy_values_are_skipped_matching_export_service_behaviour():
    # ponytail: parity with the pre-extraction ExportService behaviour --
    # a `False` or `0` field stays invisible. Widen only with a test that
    # pins the new output, since export_markdown shares this renderer.
    out = render_artifact_markdown({"title": "T", "suspect": False, "count": 0})
    assert "suspect" not in out
    assert "count" not in out


def test_missing_title_falls_back_to_id_then_to_unknown():
    assert "abc" in render_artifact_markdown({"id": "abc"})
    assert "Unknown" in render_artifact_markdown({})


def test_list_values_are_comma_joined_and_dicts_are_json():
    out = render_artifact_markdown({"title": "T", "tags": ["a", "b"], "meta": {"k": 1}})
    assert "**tags:** a, b  " in out
    assert '**meta:** {"k": 1}  ' in out


def test_heading_level_is_clamped_to_the_markdown_maximum():
    out = render_artifact_markdown({"title": "T"}, heading_level=99)
    assert out.splitlines()[0] == "###### T"


def test_output_ends_with_exactly_one_blank_line():
    out = render_artifact_markdown({"title": "T", "status": "draft"})
    assert out.endswith("\n")
    assert not out.endswith("\n\n\n")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_artifact_markdown.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.artifact_markdown'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/artifact_markdown.py`:

```python
"""Generic per-artifact Markdown renderer.

Extracted verbatim from ``ExportService.export_markdown``'s per-row loop so
that exactly one implementation serves three callers:

  * ``ExportService.export_markdown``   — the workspace-wide Markdown export,
  * ``DocumentReadService``             — the Dokumentensicht read mode and
                                          its Markdown download (spec §4, §5),
  * the MCP-Modernisierung spec's ``resources/read`` handler (spec 7 §4).

Spec 7's text says this renderer already exists inside ``McpArtifactProvider``.
It does not: ``diagram/mcp_artifact_provider.py`` is diagram-specific (it is
constructed as ``McpArtifactProvider(diagram_manager=...)``). This module is
the shared implementation both specs actually meant.

The input is a plain ``{field: value}`` mapping — the same shape produced by
``ExportService._fetch_entities``, ``TableQueryService.serialize_rows`` and
``baseline.state_capture.capture_states``. Deliberately no ORM, no service and
no Django import: this is a pure function and is unit-testable without a DB.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

#: Markdown supports at most six heading levels.
MAX_HEADING_LEVEL = 6

#: Rendered as the body paragraph and as the heading; never as list entries.
DEFAULT_SKIP_FIELDS: tuple[str, ...] = ("title", "description")


def _scalar(value: Any) -> str:
    """Flatten one field value to a single-line Markdown-safe string."""
    if isinstance(value, (list, tuple)):
        return ", ".join(_scalar(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def render_artifact_markdown(
    row: Mapping[str, Any],
    *,
    heading_level: int = 2,
    number: str | None = None,
    skip_fields: Sequence[str] = DEFAULT_SKIP_FIELDS,
) -> str:
    """Render one artifact row as a Markdown block.

    Args:
        row: ``{field_name: value}`` for a single artifact.
        heading_level: Number of ``#`` characters, clamped to ``[1, 6]``.
        number: Optional hierarchical section number ("2.1") placed before the
            title, for the Lastenheft-style numbering of the read mode.
        skip_fields: Field names excluded from the trailing definition list;
            ``title`` and ``description`` are consumed by the heading and the
            body paragraph respectively.

    Returns:
        A Markdown block terminated by a single newline.
    """
    title = str(row.get("title") or row.get("id") or "Unknown")
    hashes = "#" * max(1, min(MAX_HEADING_LEVEL, int(heading_level)))
    heading = f"{hashes} {number} {title}" if number else f"{hashes} {title}"

    lines: list[str] = [heading, ""]

    description = row.get("description")
    if description:
        lines.append(str(description))
        lines.append("")

    skip = set(skip_fields)
    for key, value in row.items():
        # ponytail: `not value` keeps byte-parity with the pre-extraction
        # ExportService behaviour, so 0/False/[] stay invisible. Widening this
        # to `value is not None` is a content improvement for a Lastenheft but
        # changes existing export output -- do it in its own change, with a
        # test that pins the new bytes.
        if key in skip or not value:
            continue
        lines.append(f"**{key}:** {_scalar(value)}  ")

    return "\n".join(lines).rstrip("\n") + "\n"


__all__ = ["render_artifact_markdown", "MAX_HEADING_LEVEL", "DEFAULT_SKIP_FIELDS"]
```

Replace the per-row loop in `backend/application/export_service.py:439-451` with:

```python
        from application.artifact_markdown import render_artifact_markdown

        for row in rows:
            lines.append(render_artifact_markdown(row, heading_level=2))
            lines.append("---")
            lines.append("")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_artifact_markdown.py application/tests/test_export_service.py -v`
Expected: PASS — 9 new tests pass and the existing `TestExportMarkdown` cases stay green (the refactor is behaviour-preserving).

- [ ] **Step 5: Commit**

```bash
git add backend/application/artifact_markdown.py backend/application/export_service.py \
        backend/application/tests/test_artifact_markdown.py
git commit -m "feat(documents): extract generic artifact markdown renderer from ExportService"
```

---

## Task 5: DocumentScopeService — sections to artifact ids

**Files:**
- Create: `backend/application/document_scope_service.py`
- Test: `backend/application/tests/test_document_scope_service.py`

**Interfaces:**
- Consumes: `application.table_query_service.TableQueryService.query` (spec 9), `baseline.services.resolve_artifact_subtree_ids` (created in Task 7 — **implement Task 7 Step 3's extraction first if you hit an ImportError**; it is a pure extraction with no behaviour change and can be pulled forward)
- Produces:
  ```python
  MAX_SECTION_ITEMS: int  # 500
  @dataclass(frozen=True)
  class ResolvedSection:
      section_id: str
      artifact_ids: tuple[str, ...]
      truncated: bool
  class DocumentScopeService(ServiceBase):
      def resolve_section(self, *, ctx, section) -> ResolvedSection
      def resolve_document_artifact_ids(self, *, ctx, document_id: UUID) -> list[str]
  ```

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_document_scope_service.py`:

```python
"""DocumentSection -> ordered artifact ids (Dokumentensicht spec §3, §6)."""
from __future__ import annotations

import uuid

import pytest

from application import document_scope_service as dss
from application.document_scope_service import DocumentScopeService, MAX_SECTION_ITEMS
from persistence.models import Document, DocumentSection


@pytest.fixture
def document(tenant, workspace):
    return Document.objects.create(tenant=tenant, workspace=workspace, title="D")


@pytest.mark.django_db
def test_fixed_section_returns_its_ids_in_the_stored_order(ctx, tenant, document):
    ids = [str(uuid.uuid4()) for _ in range(3)]
    section = DocumentSection.objects.create(
        tenant=tenant, document=document, title="Fixed",
        content_type="fixed", fixed_artifact_ids=ids,
    )
    resolved = DocumentScopeService().resolve_section(ctx=ctx, section=section)
    assert list(resolved.artifact_ids) == ids
    assert resolved.truncated is False


@pytest.mark.django_db
def test_fixed_section_is_capped_at_max_section_items(ctx, tenant, document):
    ids = [str(uuid.uuid4()) for _ in range(MAX_SECTION_ITEMS + 5)]
    section = DocumentSection.objects.create(
        tenant=tenant, document=document, title="Big",
        content_type="fixed", fixed_artifact_ids=ids,
    )
    resolved = DocumentScopeService().resolve_section(ctx=ctx, section=section)
    assert len(resolved.artifact_ids) == MAX_SECTION_ITEMS
    assert resolved.truncated is True


@pytest.mark.django_db
def test_query_section_delegates_to_table_query_service(ctx, tenant, document, monkeypatch):
    artifact_id = uuid.uuid4()

    class _Row:
        def __init__(self, aid):
            self.artifact_id = aid

    captured = {}

    class _FakeTableQueryService:
        def query(self, **kwargs):
            captured.update(kwargs)
            return [_Row(artifact_id)]

    monkeypatch.setattr(dss, "TableQueryService", _FakeTableQueryService)
    section = DocumentSection.objects.create(
        tenant=tenant, document=document, title="Q", content_type="query",
        query={"item_type": "Requirement", "filters": {"status": {"op": "in", "value": ["draft"]}}},
    )
    resolved = DocumentScopeService().resolve_section(ctx=ctx, section=section)
    assert list(resolved.artifact_ids) == [str(artifact_id)]
    assert captured["item_type"] == "Requirement"
    assert captured["filters"] == {"status": {"op": "in", "value": ["draft"]}}
    assert captured["workspace_id"] == document.workspace_id


@pytest.mark.django_db
def test_subtree_section_delegates_to_the_baseline_subtree_resolver(
    ctx, tenant, document, monkeypatch
):
    root = uuid.uuid4()
    child = str(uuid.uuid4())
    monkeypatch.setattr(
        dss, "resolve_artifact_subtree_ids", lambda **kw: [str(root), child]
    )
    section = DocumentSection.objects.create(
        tenant=tenant, document=document, title="Sub",
        content_type="subtree", subtree_root_artifact_id=root,
    )
    resolved = DocumentScopeService().resolve_section(ctx=ctx, section=section)
    assert list(resolved.artifact_ids) == [str(root), child]


@pytest.mark.django_db
def test_document_ids_are_deduplicated_across_sections_in_section_order(
    ctx, tenant, document
):
    shared = str(uuid.uuid4())
    only_second = str(uuid.uuid4())
    DocumentSection.objects.create(
        tenant=tenant, document=document, title="A", order=0,
        content_type="fixed", fixed_artifact_ids=[shared],
    )
    DocumentSection.objects.create(
        tenant=tenant, document=document, title="B", order=1,
        content_type="fixed", fixed_artifact_ids=[shared, only_second],
    )
    ids = DocumentScopeService().resolve_document_artifact_ids(
        ctx=ctx, document_id=document.id
    )
    assert ids == [shared, only_second]


@pytest.mark.django_db
def test_a_broken_query_section_fails_soft_and_yields_no_ids(ctx, tenant, document, monkeypatch):
    from application.base import ValidationError

    class _ExplodingTableQueryService:
        def query(self, **kwargs):
            raise ValidationError("Unknown field 'gone' for this item type")

    monkeypatch.setattr(dss, "TableQueryService", _ExplodingTableQueryService)
    section = DocumentSection.objects.create(
        tenant=tenant, document=document, title="Broken", content_type="query",
        query={"item_type": "Requirement", "filters": {"gone": {"op": "in", "value": []}}},
    )
    resolved = DocumentScopeService().resolve_section(ctx=ctx, section=section)
    assert resolved.artifact_ids == ()
    assert resolved.error is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_document_scope_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.document_scope_service'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/document_scope_service.py`:

```python
"""Resolve a Document's sections to ordered artifact ids (spec §3, §6).

This is the single place that knows how the three ``content_type`` values map
onto artifacts, and it is deliberately Layer 2: a ``query`` section needs
``TableQueryService`` (Layer 2), which Layer 1 ``baseline/`` must not import.
Layer 1 therefore never learns what a Document is — ``BaselineFacade`` resolves
the ids here and hands the finished list down (see Task 8).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from application.base import ServiceBase, ValidationError
from application.table_query_service import TableQueryService
from auth_tenancy.context import AuthContext
from baseline.services import resolve_artifact_subtree_ids

logger = logging.getLogger(__name__)

#: Hard ceiling per section. A ``query`` section is evaluated live on every
#: read (spec §9), and an unbounded live query behind a synchronous endpoint is
#: a self-inflicted timeout.
#: ponytail: fixed cap, not pagination. Add per-section paging only when a real
#: document actually needs more than 500 items in one chapter.
MAX_SECTION_ITEMS = 500


@dataclass(frozen=True)
class ResolvedSection:
    """One section's artifact ids plus the two things a reader must be told."""

    section_id: str
    artifact_ids: tuple[str, ...]
    truncated: bool = False
    #: Human-readable reason the section yielded nothing, or ``None``.
    error: Optional[str] = None


class DocumentScopeService(ServiceBase):
    """Section -> artifact ids, and document -> deduplicated artifact ids."""

    def resolve_section(
        self, *, ctx: AuthContext, section: Any
    ) -> ResolvedSection:
        """Resolve one ``DocumentSection`` to an ordered tuple of artifact ids."""
        self._set_tenant_context(ctx)
        handler = {
            "fixed": self._resolve_fixed,
            "query": self._resolve_query,
            "subtree": self._resolve_subtree,
        }.get(section.content_type)
        if handler is None:
            return ResolvedSection(
                section_id=str(section.id),
                artifact_ids=(),
                error=f"Unknown content_type '{section.content_type}'.",
            )
        return handler(ctx, section)

    def resolve_document_artifact_ids(
        self, *, ctx: AuthContext, document_id: UUID
    ) -> list[str]:
        """Return every artifact id in *document_id*, deduplicated, in section order.

        Used by the baseline binding (spec §6): the union of all sections is
        exactly the set a ``scope="document"`` baseline freezes.
        """
        self._set_tenant_context(ctx)
        from persistence.models import Document

        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return []

        seen: dict[str, None] = {}
        for section in self._ordered_sections(document):
            for artifact_id in self.resolve_section(ctx=ctx, section=section).artifact_ids:
                seen.setdefault(artifact_id, None)
        return list(seen)

    # ---------- helpers ----------

    @staticmethod
    def _ordered_sections(document: Any) -> list[Any]:
        """Depth-first section walk in ``(order, title)`` order.

        Mirrors the read mode's traversal so the baseline scope and the read
        mode can never disagree about membership.
        """
        by_parent: dict[Any, list[Any]] = {}
        for section in document.sections.all():
            by_parent.setdefault(section.parent_section_id, []).append(section)

        ordered: list[Any] = []

        def _walk(parent_id: Any, depth: int) -> None:
            if depth > 32:  # defensive: bounded even if the data holds a cycle
                return
            for section in by_parent.get(parent_id, []):
                ordered.append(section)
                _walk(section.id, depth + 1)

        _walk(None, 0)
        return ordered

    @staticmethod
    def _capped(ids: list[str], section: Any) -> ResolvedSection:
        truncated = len(ids) > MAX_SECTION_ITEMS
        return ResolvedSection(
            section_id=str(section.id),
            artifact_ids=tuple(ids[:MAX_SECTION_ITEMS]),
            truncated=truncated,
        )

    def _resolve_fixed(self, ctx: AuthContext, section: Any) -> ResolvedSection:
        return self._capped([str(v) for v in (section.fixed_artifact_ids or [])], section)

    def _resolve_query(self, ctx: AuthContext, section: Any) -> ResolvedSection:
        """Evaluate the stored Tabellenansicht filter DSL payload live."""
        payload = section.query or {}
        try:
            rows = TableQueryService().query(
                ctx=ctx,
                workspace_id=section.document.workspace_id,
                item_type=str(payload.get("item_type") or ""),
                filters=payload.get("filters"),
                sort=payload.get("sort"),
            )
            ids = [
                str(getattr(row, "artifact_id", None) or getattr(row, "id"))
                for row in rows[: MAX_SECTION_ITEMS + 1]
            ]
        except ValidationError as exc:
            # Fail-soft, matching the SavedView contract in the Tabellenansicht
            # spec §6: a stale stored query yields an empty section with a
            # visible reason, never a 500 that hides the whole document.
            logger.info(
                "Document section %s has an unusable query: %s", section.id, exc
            )
            return ResolvedSection(
                section_id=str(section.id), artifact_ids=(), error=str(exc)
            )
        return self._capped(ids, section)

    def _resolve_subtree(self, ctx: AuthContext, section: Any) -> ResolvedSection:
        """Delegate to the Layer-1 artifact-subtree resolver (Task 7)."""
        if section.subtree_root_artifact_id is None:
            return ResolvedSection(
                section_id=str(section.id),
                artifact_ids=(),
                error="Section has no subtree_root_artifact_id.",
            )
        ids = resolve_artifact_subtree_ids(
            root_artifact_id=section.subtree_root_artifact_id,
            workspace_id=section.document.workspace_id,
            tenant_id=ctx.tenant_id,
        )
        return self._capped(list(ids), section)


__all__ = ["DocumentScopeService", "ResolvedSection", "MAX_SECTION_ITEMS"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_document_scope_service.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/document_scope_service.py \
        backend/application/tests/test_document_scope_service.py
git commit -m "feat(documents): resolve document sections to artifact ids"
```

---

## Task 6: DocumentReadService — numbering and Markdown assembly

**Files:**
- Create: `backend/application/document_read_service.py`
- Test: `backend/application/tests/test_document_read_service.py`

**Interfaces:**
- Consumes: `DocumentScopeService.resolve_section`, `artifact_markdown.render_artifact_markdown`, `baseline.state_capture.capture_states`, `baseline.types.DeltaIndexTuple`
- Produces:
  ```python
  @dataclass(frozen=True)
  class ReadSection:
      number: str; title: str; depth: int
      artifact_ids: tuple[str, ...]; truncated: bool; error: str | None
  @dataclass(frozen=True)
  class ReadDocument:
      document_id: str; title: str; markdown: str; sections: tuple[ReadSection, ...]
      def to_dict(self) -> dict[str, Any]
  class DocumentReadService(ServiceBase):
      def read(self, *, ctx, document_id: UUID) -> ReadDocument
  ```

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_document_read_service.py`:

```python
"""Read mode: numbering + Markdown assembly (Dokumentensicht spec §4)."""
from __future__ import annotations

import json
import uuid

import pytest

from application import document_read_service as drs
from application.document_read_service import DocumentReadService
from application.document_scope_service import ResolvedSection
from persistence.models import Document, DocumentSection


@pytest.fixture
def document(tenant, workspace):
    return Document.objects.create(tenant=tenant, workspace=workspace, title="Lastenheft")


def _stub_rows(monkeypatch, titles_by_id):
    """Replace the batched state loader with a deterministic stub."""
    monkeypatch.setattr(
        drs,
        "capture_states",
        lambda delta_index, tenant_id: {
            t.item_id: {"title": titles_by_id[t.item_id], "status": "draft"}
            for t in delta_index
            if t.item_id in titles_by_id
        },
    )


@pytest.mark.django_db
def test_root_sections_are_numbered_1_and_2(ctx, tenant, document, monkeypatch):
    monkeypatch.setattr(
        DocumentReadService, "_resolve", lambda self, ctx, s: ResolvedSection(str(s.id), ())
    )
    DocumentSection.objects.create(tenant=tenant, document=document, title="Scope", order=0, content_type="fixed")
    DocumentSection.objects.create(tenant=tenant, document=document, title="Requirements", order=1, content_type="fixed")

    result = DocumentReadService().read(ctx=ctx, document_id=document.id)
    assert [(s.number, s.title) for s in result.sections] == [("1", "Scope"), ("2", "Requirements")]
    assert result.markdown.startswith("# Lastenheft\n")
    assert "## 1 Scope" in result.markdown
    assert "## 2 Requirements" in result.markdown


@pytest.mark.django_db
def test_artifacts_consume_the_child_counter_before_subsections(
    ctx, tenant, document, monkeypatch
):
    a1, a2 = str(uuid.uuid4()), str(uuid.uuid4())
    _stub_rows(monkeypatch, {a1: "First req", a2: "Second req"})
    parent = DocumentSection.objects.create(
        tenant=tenant, document=document, title="Chapter", order=0,
        content_type="fixed", fixed_artifact_ids=[a1, a2],
    )
    DocumentSection.objects.create(
        tenant=tenant, document=document, title="Sub", order=0,
        content_type="fixed", parent_section=parent,
    )

    result = DocumentReadService().read(ctx=ctx, document_id=document.id)
    assert "### 1.1 First req" in result.markdown
    assert "### 1.2 Second req" in result.markdown
    # the subsection continues the same counter
    assert [(s.number, s.title) for s in result.sections] == [("1", "Chapter"), ("1.3", "Sub")]


@pytest.mark.django_db
def test_nested_sections_get_dotted_numbers(ctx, tenant, document, monkeypatch):
    monkeypatch.setattr(
        DocumentReadService, "_resolve", lambda self, ctx, s: ResolvedSection(str(s.id), ())
    )
    top = DocumentSection.objects.create(tenant=tenant, document=document, title="A", order=0, content_type="fixed")
    mid = DocumentSection.objects.create(tenant=tenant, document=document, title="B", order=0, parent_section=top, content_type="fixed")
    DocumentSection.objects.create(tenant=tenant, document=document, title="C", order=0, parent_section=mid, content_type="fixed")

    numbers = [s.number for s in DocumentReadService().read(ctx=ctx, document_id=document.id).sections]
    assert numbers == ["1", "1.1", "1.1.1"]


@pytest.mark.django_db
def test_truncated_section_renders_a_visible_marker(ctx, tenant, document, monkeypatch):
    monkeypatch.setattr(
        DocumentReadService,
        "_resolve",
        lambda self, ctx, s: ResolvedSection(str(s.id), (), truncated=True),
    )
    DocumentSection.objects.create(tenant=tenant, document=document, title="Big", content_type="fixed")
    result = DocumentReadService().read(ctx=ctx, document_id=document.id)
    assert "truncated" in result.markdown.lower()
    assert result.sections[0].truncated is True


@pytest.mark.django_db
def test_section_error_is_reported_in_the_markdown_and_the_payload(
    ctx, tenant, document, monkeypatch
):
    monkeypatch.setattr(
        DocumentReadService,
        "_resolve",
        lambda self, ctx, s: ResolvedSection(str(s.id), (), error="Unknown field 'gone'"),
    )
    DocumentSection.objects.create(tenant=tenant, document=document, title="Broken", content_type="query", query={"item_type": "Requirement"})
    result = DocumentReadService().read(ctx=ctx, document_id=document.id)
    assert "Unknown field 'gone'" in result.markdown
    assert result.sections[0].error == "Unknown field 'gone'"


@pytest.mark.django_db
def test_to_dict_is_stdlib_json_serialisable(ctx, tenant, document, monkeypatch):
    monkeypatch.setattr(
        DocumentReadService, "_resolve", lambda self, ctx, s: ResolvedSection(str(s.id), ())
    )
    DocumentSection.objects.create(tenant=tenant, document=document, title="S", content_type="fixed")
    payload = DocumentReadService().read(ctx=ctx, document_id=document.id).to_dict()
    json.dumps(payload)
    assert "markdown" in payload
    assert "content" not in payload  # never collide with the JSON-RPC envelope


@pytest.mark.django_db
def test_artifacts_are_loaded_in_one_batch_for_the_whole_document(
    ctx, tenant, document, monkeypatch
):
    calls = []
    a1, a2 = str(uuid.uuid4()), str(uuid.uuid4())

    def _spy(delta_index, tenant_id):
        calls.append([t.item_id for t in delta_index])
        return {t.item_id: {"title": "X"} for t in delta_index}

    monkeypatch.setattr(drs, "capture_states", _spy)
    DocumentSection.objects.create(tenant=tenant, document=document, title="A", order=0, content_type="fixed", fixed_artifact_ids=[a1])
    DocumentSection.objects.create(tenant=tenant, document=document, title="B", order=1, content_type="fixed", fixed_artifact_ids=[a2])

    DocumentReadService().read(ctx=ctx, document_id=document.id)
    assert len(calls) == 1
    assert sorted(calls[0]) == sorted([a1, a2])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_document_read_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.document_read_service'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/document_read_service.py`:

```python
"""Read mode: numbered Markdown for a whole Document (spec §4, §5).

Numbering (spec §4, made concrete): within a section numbered ``N`` the child
counter starts at 1; the section's own artifacts consume it first
(``N.1``, ``N.2``, ...) and its child sections continue it. Root sections are
``1``, ``2``, ... That is how a classical Lastenheft reads, and it makes every
number unique inside the document.

Artifact rows are loaded once for the whole document via
``baseline.state_capture.capture_states`` — the codebase's existing batched,
cross-type artifact-state loader (one query per candidate table, no N+1),
already used by the baseline snapshot path. Re-implementing a per-type loader
here would be a second source of truth for "what fields does an artifact have".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from application.artifact_markdown import render_artifact_markdown
from application.base import NotFoundError, ServiceBase
from application.document_scope_service import DocumentScopeService, ResolvedSection
from auth_tenancy.context import AuthContext
from baseline.state_capture import capture_states
from baseline.types import DeltaIndexTuple

logger = logging.getLogger(__name__)

#: Markdown heading level of a root section. The document title is ``#``.
ROOT_SECTION_HEADING_LEVEL = 2


@dataclass(frozen=True)
class ReadSection:
    """One rendered section of the read mode."""

    number: str
    title: str
    depth: int
    artifact_ids: tuple[str, ...]
    truncated: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "depth": self.depth,
            "artifact_ids": list(self.artifact_ids),
            "truncated": self.truncated,
            "error": self.error,
        }


@dataclass(frozen=True)
class ReadDocument:
    """The whole read-mode payload: the Markdown plus its section outline."""

    document_id: str
    title: str
    markdown: str
    sections: tuple[ReadSection, ...]

    def to_dict(self) -> dict[str, Any]:
        """JSON primitives only. The Markdown key is ``markdown``, never
        ``content`` — a top-level ``content`` key collides with the MCP
        JSON-RPC envelope."""
        return {
            "document_id": self.document_id,
            "title": self.title,
            "markdown": self.markdown,
            "sections": [s.to_dict() for s in self.sections],
        }


class DocumentReadService(ServiceBase):
    """Assemble a Document into numbered Markdown."""

    def read(self, *, ctx: AuthContext, document_id: UUID) -> ReadDocument:
        """Resolve every section live and render the document."""
        self._set_tenant_context(ctx)
        from persistence.models import Document

        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist as exc:
            raise NotFoundError(f"Document {document_id} not found.") from exc

        by_parent: dict[Any, list[Any]] = {}
        for section in document.sections.all():
            by_parent.setdefault(section.parent_section_id, []).append(section)

        # Pass 1: walk the tree, resolve each section, assign numbers.
        numbered: list[tuple[Any, str, int, ResolvedSection]] = []
        self._walk(ctx, by_parent, parent_id=None, prefix="", depth=0, out=numbered)

        # Pass 2: one batched load for every artifact in the whole document.
        all_ids: list[str] = []
        seen: set[str] = set()
        for _section, _number, _depth, resolved in numbered:
            for artifact_id in resolved.artifact_ids:
                if artifact_id not in seen:
                    seen.add(artifact_id)
                    all_ids.append(artifact_id)
        rows = self._load_rows(all_ids, ctx)

        # Pass 3: render.
        lines: list[str] = [f"# {document.title}", ""]
        if document.description:
            lines.append(document.description)
            lines.append("")
        read_sections: list[ReadSection] = []

        for section, number, depth, resolved in numbered:
            heading_level = min(6, ROOT_SECTION_HEADING_LEVEL + depth)
            lines.append(f"{'#' * heading_level} {number} {section.title}")
            lines.append("")
            if resolved.error:
                lines.append(f"> _{resolved.error}_")
                lines.append("")
            for index, artifact_id in enumerate(resolved.artifact_ids, start=1):
                row = rows.get(artifact_id)
                if row is None:
                    continue
                lines.append(
                    render_artifact_markdown(
                        row,
                        heading_level=min(6, heading_level + 1),
                        number=f"{number}.{index}",
                    )
                )
            if resolved.truncated:
                lines.append(
                    f"> _List truncated after {len(resolved.artifact_ids)} entries._"
                )
                lines.append("")
            read_sections.append(
                ReadSection(
                    number=number,
                    title=section.title,
                    depth=depth,
                    artifact_ids=resolved.artifact_ids,
                    truncated=resolved.truncated,
                    error=resolved.error,
                )
            )

        return ReadDocument(
            document_id=str(document.id),
            title=document.title,
            markdown="\n".join(lines).rstrip("\n") + "\n",
            sections=tuple(read_sections),
        )

    # ---------- internals ----------

    def _resolve(self, ctx: AuthContext, section: Any) -> ResolvedSection:
        """Seam: overridden in tests to avoid a live query per section."""
        return DocumentScopeService().resolve_section(ctx=ctx, section=section)

    def _walk(
        self,
        ctx: AuthContext,
        by_parent: dict,
        *,
        parent_id: Any,
        prefix: str,
        depth: int,
        out: list,
    ) -> None:
        """Depth-first numbering walk.

        The counter is shared: a section's own artifacts take ``prefix.1 ...``
        and its child sections continue from there.
        """
        if depth > 32:  # defensive; DocumentService caps real depth at 10
            return
        counter = 1
        for section in by_parent.get(parent_id, []):
            number = f"{prefix}{counter}" if not prefix else f"{prefix}{counter}"
            resolved = self._resolve(ctx, section)
            out.append((section, number, depth, resolved))
            # Children start after this section's own artifacts.
            child_start = len(resolved.artifact_ids) + 1
            self._walk_children(
                ctx, by_parent, section=section, number=number, depth=depth,
                start=child_start, out=out,
            )
            counter += 1

    def _walk_children(
        self, ctx: AuthContext, by_parent: dict, *, section: Any, number: str,
        depth: int, start: int, out: list,
    ) -> None:
        """Number a section's children continuing its artifact counter."""
        children = by_parent.get(section.id, [])
        if not children:
            return
        counter = start
        for child in children:
            child_number = f"{number}.{counter}"
            resolved = self._resolve(ctx, child)
            out.append((child, child_number, depth + 1, resolved))
            self._walk_children(
                ctx, by_parent, section=child, number=child_number,
                depth=depth + 1, start=len(resolved.artifact_ids) + 1, out=out,
            )
            counter += 1

    @staticmethod
    def _load_rows(artifact_ids: list[str], ctx: AuthContext) -> dict[str, dict]:
        """Batch-load one ``{field: value}`` row per artifact id."""
        if not artifact_ids:
            return {}
        delta_index = [
            DeltaIndexTuple(item_id=artifact_id, version=0, entity_type="item")
            for artifact_id in artifact_ids
        ]
        try:
            return capture_states(delta_index, ctx.tenant_id)
        except Exception:  # pragma: no cover - defensive, mirrors the baseline path
            logger.warning(
                "Document read: artifact state load failed; rendering headings only.",
                exc_info=True,
            )
            return {}


__all__ = ["DocumentReadService", "ReadDocument", "ReadSection"]
```

Note on `_walk`: the root call passes `prefix=""` so root sections are numbered `1`, `2`, … and every nested level goes through `_walk_children`, which is the only place the dotted prefix is built. Simplify `_walk`'s `number` line to `number = str(counter)` — it is only ever called for the root level.

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_document_read_service.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/document_read_service.py \
        backend/application/tests/test_document_read_service.py
git commit -m "feat(documents): add numbered markdown read mode service"
```

---

## Task 7: Extract the artifact-subtree resolver and add the AuditScope item_ids seam

**Files:**
- Modify: `backend/baseline/services.py:307-455` (`resolve_scope_item_ids`)
- Modify: `backend/traceability/audit/types.py:76-85` (`AuditScope`)
- Modify: `backend/traceability/audit/rule_engine.py:106-112`
- Test: `backend/traceability/audit/tests/test_audit_scope_item_ids.py`

**Interfaces:**
- Produces:
  ```python
  # baseline/services.py
  def resolve_artifact_subtree_ids(*, root_artifact_id: UUID, workspace_id: UUID,
                                   tenant_id: UUID) -> list[str]
  # traceability/audit/types.py
  @dataclass(frozen=True)
  class AuditScope:
      scope: str
      artifact_id: Optional[str] = None
      item_ids: Optional[tuple[str, ...]] = None   # NEW: pre-resolved membership
  ```

- [ ] **Step 1: Write the failing test**

Create `backend/traceability/audit/tests/test_audit_scope_item_ids.py`:

```python
"""AuditScope.item_ids lets a caller pre-resolve scope membership (spec §6).

Without this seam a Document-scoped baseline would reach
``resolve_scope_item_ids(artifact_id=<Document UUID>)``, resolve nothing, and
wave every SE-Auditor BLOCKER through -- a silent governance hole.
"""
from __future__ import annotations

import uuid

from traceability.audit.types import AuditContext, AuditScope


def test_audit_scope_accepts_pre_resolved_item_ids():
    ids = (str(uuid.uuid4()), str(uuid.uuid4()))
    scope = AuditScope("document", artifact_id=None, item_ids=ids)
    assert scope.item_ids == ids


def test_audit_scope_item_ids_defaults_to_none():
    assert AuditScope("project").item_ids is None


def test_context_seeded_with_item_ids_never_queries_the_resolver(monkeypatch):
    import baseline.services as bl

    def _boom(**kwargs):  # pragma: no cover - must never be called
        raise AssertionError("resolve_scope_item_ids must not be called")

    monkeypatch.setattr(bl, "resolve_scope_item_ids", _boom)
    ids = frozenset({"a", "b"})
    ctx = AuditContext(
        tier="standard",
        workspace_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        scope="document",
        _scope_item_ids=ids,
    )
    assert ctx.scope_item_ids == ids


def test_rule_engine_seeds_the_context_from_the_scope(monkeypatch):
    from traceability.audit import rule_engine as re_mod

    captured = {}

    class _Probe(AuditContext):
        def __init__(self, **kwargs):
            captured.update(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(re_mod, "AuditContext", _Probe)
    engine = re_mod.RuleEngine()
    ids = ("x", "y")
    engine.run(
        tier="standard",
        workspace_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        scopes=[AuditScope("document", artifact_id=None, item_ids=ids)],
    )
    assert captured.get("_scope_item_ids") == frozenset(ids)
```

Adjust `engine.run(...)`'s keyword names to the real `RuleEngine.run` signature (read `backend/traceability/audit/rule_engine.py:60-116` first); the assertion is what matters.

Add to `backend/baseline/tests/test_baseline.py`:

```python
@pytest.mark.django_db
class TestResolveArtifactSubtreeIds:
    """The extracted subtree resolver is byte-equivalent to the old branch."""

    def test_matches_resolve_scope_item_ids_document_branch(self, ...):
        from baseline.services import (
            resolve_artifact_subtree_ids,
            resolve_scope_item_ids,
        )

        # Build the same three-artifact parent chain the existing
        # test_document_scope_follows_tracelinks case builds, then:
        via_extracted = resolve_artifact_subtree_ids(
            root_artifact_id=root.id, workspace_id=ws.id, tenant_id=tenant.id
        )
        via_public = resolve_scope_item_ids(
            scope="document", workspace_id=ws.id, tenant_id=tenant.id,
            artifact_id=root.id,
        )
        assert via_extracted == via_public
```

Copy the fixture body from the existing `resolve_scope_item_ids(scope='document')` case at `backend/baseline/tests/test_baseline.py:1152-1200` — it already builds exactly this graph.

- [ ] **Step 2: Run test to verify it fails**

Run: `BT traceability/audit/tests/test_audit_scope_item_ids.py -v`
Expected: FAIL with `TypeError: AuditScope.__init__() got an unexpected keyword argument 'item_ids'`

- [ ] **Step 3: Write minimal implementation**

In `backend/baseline/services.py`, extract the `else:  # document` branch of `resolve_scope_item_ids` (lines 407-451) into a new public function, and have the original call it:

```python
def resolve_artifact_subtree_ids(
    *,
    root_artifact_id: uuid.UUID,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> list[str]:
    """Return the root artifact plus every descendant, as ordered id strings.

    Extracted verbatim from :func:`resolve_scope_item_ids`'s ``document``
    branch so the Dokumentensicht ``subtree`` section type
    (``application.document_scope_service``) can reuse the exact same walk
    without going through the scope-string dispatch. Behaviour is unchanged;
    :func:`resolve_scope_item_ids` now delegates here.

    Descendant resolution walks two edge sources (issue #42):
    ``pl_artifact.parent_id`` and ``derives-from``/``refines`` TraceLinks
    (source=child -> target=parent).
    """
    if tenant_id is None:
        return []

    from django.db import connection

    sql_ids = """
        WITH RECURSIVE edges AS (
            SELECT a.id AS child_id, a.parent_id AS parent_id
            FROM pl_artifact a
            WHERE a.parent_id IS NOT NULL
              AND a.tenant_id = %s
            UNION ALL
            SELECT tl.source_id AS child_id, tl.target_id AS parent_id
            FROM pl_tracelink tl
            WHERE tl.tenant_id = %s
              AND tl.link_type IN ('derives-from', 'refines')
        ),
        descendants AS (
            SELECT a.id
            FROM pl_artifact a
            WHERE a.id = %s
              AND a.workspace_id = %s
              AND a.tenant_id = %s
            UNION
            SELECT e.child_id
            FROM edges e
            INNER JOIN descendants d ON e.parent_id = d.id
        )
        SELECT id::text FROM descendants ORDER BY id
    """
    params = [
        str(tenant_id),
        str(tenant_id),
        str(root_artifact_id),
        str(workspace_id),
        str(tenant_id),
    ]
    with connection.cursor() as cur:
        cur.execute(sql_ids, params)
        return [row[0] for row in cur.fetchall()]
```

Replace the `else:  # document` branch with:

```python
    else:  # document
        return resolve_artifact_subtree_ids(
            root_artifact_id=artifact_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
        )
```

(and add `"resolve_artifact_subtree_ids"` to `__all__`).

In `backend/traceability/audit/types.py`, extend `AuditScope`:

```python
    scope: str
    artifact_id: Optional[str] = None
    #: Pre-resolved scope membership. Set by a caller that already knows the
    #: exact artifact id set -- specifically ``BaselineFacade`` for a
    #: ``scope="document"`` baseline bound to a real ``Document``, whose
    #: membership is the union of its sections and is NOT derivable from a
    #: single root ``artifact_id`` (Dokumentensicht spec §6). When present it
    #: bypasses ``baseline.services.resolve_scope_item_ids`` entirely.
    item_ids: Optional[Tuple[str, ...]] = None
```

(import `Tuple` from `typing`.)

In `backend/traceability/audit/rule_engine.py:106-112`:

```python
                scope_ctx = AuditContext(
                    tier=tier,
                    workspace_id=workspace_id,
                    tenant_id=tenant_id,
                    scope=audit_scope.scope,
                    scope_artifact_id=audit_scope.artifact_id,
                    _scope_item_ids=(
                        frozenset(audit_scope.item_ids)
                        if audit_scope.item_ids is not None
                        else None
                    ),
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT traceability/audit/tests/test_audit_scope_item_ids.py baseline/tests/test_baseline.py -v`
Expected: PASS (4 new tests plus the whole existing baseline suite unchanged)

- [ ] **Step 5: Commit**

```bash
git add backend/baseline/services.py backend/traceability/audit/types.py \
        backend/traceability/audit/rule_engine.py \
        backend/traceability/audit/tests/test_audit_scope_item_ids.py \
        backend/baseline/tests/test_baseline.py
git commit -m "feat(baseline): extract subtree resolver and add AuditScope.item_ids seam"
```

---

## Task 8: ScopeResolver accepts a pre-resolved item id set

**Files:**
- Modify: `backend/baseline/delta_index_builder.py:49-79` (`ScopeResolver.resolve`), `:249-351` (`_resolve_document`), `:375-440` (`DeltaIndexBuilder.build`)
- Modify: `backend/baseline/services.py:69-109` (`build`)
- Test: `backend/baseline/tests/test_document_scope_binding.py`

**Interfaces:**
- Produces:
  ```python
  # baseline/services.py
  def build(scope, workspace_id, name, tenant_id, description=None, created_by="",
            document_id=None, item_ids: Optional[list[str]] = None) -> UUID
  # baseline/delta_index_builder.py
  ScopeResolver.resolve(scope, workspace_id, tenant_id, document_id=None,
                        item_ids: Optional[list[str]] = None) -> list[DeltaIndexTuple]
  ```
  When `item_ids` is supplied for `scope="document"`, the recursive CTE is skipped and versions + in-scope TraceLinks are read for exactly those ids. Everything else is unchanged.

- [ ] **Step 1: Write the failing test**

Create `backend/baseline/tests/test_document_scope_binding.py`:

```python
"""scope='document' can be driven by an explicit item id set (spec §6)."""
from __future__ import annotations

import uuid

import pytest

from baseline.delta_index_builder import ScopeResolver


@pytest.mark.django_db
class TestExplicitItemIds:
    def test_explicit_ids_bypass_the_subtree_walk(self, tenant, workspace, artifacts):
        """Two unrelated artifacts (no parent link, no tracelink) both land in
        scope when named explicitly -- which the CTE walk could never produce."""
        a, b = artifacts[0], artifacts[1]
        tuples = ScopeResolver().resolve(
            scope="document",
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            item_ids=[str(a.id), str(b.id)],
        )
        item_ids = {t.item_id for t in tuples if t.entity_type == "item"}
        assert item_ids == {str(a.id), str(b.id)}

    def test_versions_come_from_the_database_not_the_caller(
        self, tenant, workspace, artifacts
    ):
        a = artifacts[0]
        a.version = 7
        a.save(update_fields=["version"])
        tuples = ScopeResolver().resolve(
            scope="document", workspace_id=workspace.id, tenant_id=tenant.id,
            item_ids=[str(a.id)],
        )
        assert [t.version for t in tuples if t.item_id == str(a.id)] == [7]

    def test_tracelinks_in_scope_are_still_captured(
        self, tenant, workspace, artifacts, trace_link
    ):
        tuples = ScopeResolver().resolve(
            scope="document", workspace_id=workspace.id, tenant_id=tenant.id,
            item_ids=[str(trace_link.source_id)],
        )
        assert any(t.entity_type == "trace_link" for t in tuples)

    def test_empty_item_ids_yields_an_empty_scope_not_a_full_walk(
        self, tenant, workspace, artifacts
    ):
        tuples = ScopeResolver().resolve(
            scope="document", workspace_id=workspace.id, tenant_id=tenant.id,
            item_ids=[],
        )
        assert tuples == []

    def test_document_id_without_item_ids_keeps_the_legacy_subtree_behaviour(
        self, tenant, workspace, artifacts
    ):
        root = artifacts[0]
        tuples = ScopeResolver().resolve(
            scope="document", workspace_id=workspace.id, tenant_id=tenant.id,
            document_id=root.id,
        )
        assert str(root.id) in {t.item_id for t in tuples}

    def test_neither_document_id_nor_item_ids_still_raises(self, tenant, workspace):
        with pytest.raises(ValueError, match="document_id"):
            ScopeResolver().resolve(
                scope="document", workspace_id=workspace.id, tenant_id=tenant.id
            )
```

Reuse the `tenant` / `workspace` / `artifacts` / `trace_link` fixtures from `backend/baseline/tests/test_baseline.py`; move them to `backend/baseline/tests/conftest.py` if they are still module-local.

- [ ] **Step 2: Run test to verify it fails**

Run: `BT baseline/tests/test_document_scope_binding.py -v`
Expected: FAIL with `TypeError: ScopeResolver.resolve() got an unexpected keyword argument 'item_ids'`

- [ ] **Step 3: Write minimal implementation**

In `backend/baseline/delta_index_builder.py`, change `ScopeResolver.resolve`'s signature and document branch:

```python
    def resolve(
        self,
        scope: str,
        workspace_id: uuid.UUID,
        tenant_id: uuid.UUID,
        document_id: Optional[uuid.UUID] = None,
        item_ids: Optional[list[str]] = None,
    ) -> list[DeltaIndexTuple]:
        """Return (item_id, version, entity_type) tuples for the given scope.

        Args:
            item_ids: Pre-resolved membership for ``scope="document"``. Layer 2
                supplies it when the baseline is bound to a real ``Document``
                (Dokumentensicht spec §6), whose membership is the union of its
                sections and cannot be derived from a single root artifact.
                When supplied, the recursive subtree walk is skipped; versions
                and in-scope TraceLinks are still read from the database.
        """
        if scope == "project":
            return self._resolve_project(workspace_id, tenant_id)
        elif scope == "global":
            return self._resolve_global(tenant_id)
        elif scope == "document":
            if item_ids is not None:
                return self._resolve_explicit_items(item_ids, tenant_id)
            if document_id is None:
                raise ValueError(
                    "document_id is required for scope='document' "
                    "(or an explicit item_ids list)"
                )
            return self._resolve_document(document_id, workspace_id, tenant_id)
        else:
            raise ValueError(f"Unknown scope: {scope!r}")
```

Add the new resolver next to `_resolve_document` — the TraceLink half is factored out of `_resolve_document` so both branches share it verbatim:

```python
    def _resolve_explicit_items(
        self, item_ids: list[str], tenant_id: uuid.UUID
    ) -> list[DeltaIndexTuple]:
        """Delta tuples for an explicitly named artifact id set.

        Same output shape as :meth:`_resolve_document` (items + the TraceLinks
        whose source is in scope); only the membership question is answered by
        the caller instead of by the recursive CTE.
        """
        from django.db import connection

        wanted = [str(v) for v in item_ids]
        if not wanted:
            return []

        placeholders = ",".join(["%s"] * len(wanted))
        sql = f"""
            SELECT a.id::text, a.version
            FROM pl_artifact a
            WHERE a.id::text IN ({placeholders})
              AND a.tenant_id = %s
            ORDER BY a.id
        """
        with connection.cursor() as cur:
            cur.execute(sql, wanted + [str(tenant_id)])
            rows = cur.fetchall()

        items = [
            DeltaIndexTuple(item_id=str(row[0]), version=int(row[1]), entity_type="item")
            for row in rows
        ]
        items.extend(self._trace_links_for(items, tenant_id))
        return items

    @staticmethod
    def _trace_links_for(
        items: list[DeltaIndexTuple], tenant_id: uuid.UUID
    ) -> list[DeltaIndexTuple]:
        """TraceLinks whose source is one of *items* (REQ-L2-BL-001)."""
        if not items:
            return []
        from django.db import connection

        item_ids = [t.item_id for t in items]
        placeholders = ",".join(["%s"] * len(item_ids))
        tl_sql = f"""
            SELECT tl.id::text, tl.version
            FROM pl_tracelink tl
            WHERE tl.source_id::text IN ({placeholders})
              AND tl.tenant_id = %s
            ORDER BY tl.id
        """
        with connection.cursor() as cur:
            cur.execute(tl_sql, item_ids + [str(tenant_id)])
            rows = cur.fetchall()
        return [
            DeltaIndexTuple(
                item_id=str(row[0]), version=int(row[1]), entity_type="trace_link"
            )
            for row in rows
        ]
```

Replace the tail of `_resolve_document` (lines 325-351, the `if items:` TraceLink block) with `items.extend(self._trace_links_for(items, tenant_id))`.

Thread `item_ids` through `DeltaIndexBuilder.build` (add the keyword, pass it to `self._resolver.resolve(...)`) and through `baseline.services.build` (add the keyword, pass it to `get_builder().build(...)`), documenting it in both docstrings the same way.

- [ ] **Step 4: Run test to verify it passes**

Run: `BT baseline/tests/test_document_scope_binding.py baseline/tests/test_baseline.py -v`
Expected: PASS (6 new tests, existing baseline suite unchanged)

- [ ] **Step 5: Commit**

```bash
git add backend/baseline/delta_index_builder.py backend/baseline/services.py \
        backend/baseline/tests/test_document_scope_binding.py
git commit -m "feat(baseline): accept a pre-resolved item id set for document scope"
```

---

## Task 9: BaselineSnapshot.document FK and the GUC-gated trigger exception

**Files:**
- Modify: `backend/baseline/models.py:81-89` (add the FK next to the existing `artifact` FK)
- Create: `backend/baseline/migrations/0007_baseline_document_fk.py`
- Test: `backend/baseline/tests/test_document_scope_binding.py` (append a class)

**Interfaces:**
- Produces: `BaselineSnapshot.document` (FK to `persistence.Document`, `null=True`, `on_delete=SET_NULL`, `related_name="baseline_snapshots"`), and the transaction-local GUC `app.baseline_document_backfill`.

**Why the trigger must change at all:** `baseline/migrations/0001_initial.py:163-193` installs `trg_baseline_snapshot_immutable BEFORE UPDATE OR DELETE`, which raises unconditionally. Task 11's backfill has to write `document_id` onto existing rows. `ALTER TABLE … DISABLE TRIGGER` is **owner-only DDL** — the runtime role `reqogniloom_app` cannot execute it, so that approach passes in tests (which run as the owner) and fails in production with "must be owner of table". The repo's pattern is a transaction-local GUC read from inside the trigger function: setting a dotted GUC needs no privilege and takes no `ACCESS EXCLUSIVE` lock.

- [ ] **Step 1: Write the failing test**

Append to `backend/baseline/tests/test_document_scope_binding.py`:

```python
@pytest.mark.django_db(transaction=True)
class TestImmutabilityStaysIntact:
    """The GUC exception is opt-in, one-way and one-column."""

    def _snapshot(self, tenant, workspace):
        from baseline.models import BaselineSnapshot

        return BaselineSnapshot.objects.create(
            tenant=tenant, workspace_id=workspace.id, scope="document",
            name=f"bl-{uuid.uuid4()}",
        )

    def test_plain_update_still_raises(self, tenant, workspace):
        from django.db import connection
        from django.db.utils import InternalError, ProgrammingError

        snap = self._snapshot(tenant, workspace)
        with pytest.raises((InternalError, ProgrammingError)) as exc:
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE bl_baseline_snapshot SET name = %s WHERE id = %s",
                    ["renamed", str(snap.id)],
                )
        assert "immutable" in str(exc.value).lower()

    def test_delete_still_raises(self, tenant, workspace):
        from django.db import connection
        from django.db.utils import InternalError, ProgrammingError

        snap = self._snapshot(tenant, workspace)
        with pytest.raises((InternalError, ProgrammingError)):
            with connection.cursor() as cur:
                cur.execute(
                    "DELETE FROM bl_baseline_snapshot WHERE id = %s", [str(snap.id)]
                )

    def test_document_id_backfill_is_allowed_under_the_guc(
        self, tenant, workspace, document
    ):
        from django.db import connection, transaction

        snap = self._snapshot(tenant, workspace)
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.baseline_document_backfill', 'true', true)"
                )
                cur.execute(
                    "UPDATE bl_baseline_snapshot SET document_id = %s WHERE id = %s",
                    [str(document.id), str(snap.id)],
                )
        snap.refresh_from_db()
        assert str(snap.document_id) == str(document.id)

    def test_the_guc_does_not_permit_changing_any_other_column(
        self, tenant, workspace, document
    ):
        from django.db import connection, transaction
        from django.db.utils import InternalError, ProgrammingError

        snap = self._snapshot(tenant, workspace)
        with pytest.raises((InternalError, ProgrammingError)):
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT set_config('app.baseline_document_backfill', 'true', true)"
                    )
                    cur.execute(
                        "UPDATE bl_baseline_snapshot "
                        "SET document_id = %s, name = %s WHERE id = %s",
                        [str(document.id), "renamed", str(snap.id)],
                    )

    def test_the_guc_cannot_overwrite_an_existing_document_id(
        self, tenant, workspace, document, second_document
    ):
        from django.db import connection, transaction
        from django.db.utils import InternalError, ProgrammingError

        snap = self._snapshot(tenant, workspace)
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.baseline_document_backfill', 'true', true)"
                )
                cur.execute(
                    "UPDATE bl_baseline_snapshot SET document_id = %s WHERE id = %s",
                    [str(document.id), str(snap.id)],
                )
        with pytest.raises((InternalError, ProgrammingError)):
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT set_config('app.baseline_document_backfill', 'true', true)"
                    )
                    cur.execute(
                        "UPDATE bl_baseline_snapshot SET document_id = %s WHERE id = %s",
                        [str(second_document.id), str(snap.id)],
                    )
```

Add two fixtures to `backend/baseline/tests/conftest.py`:

```python
@pytest.fixture
def document(tenant, workspace):
    from persistence.models import Document

    return Document.objects.create(tenant=tenant, workspace=workspace, title="Doc A")


@pytest.fixture
def second_document(tenant, workspace):
    from persistence.models import Document

    return Document.objects.create(tenant=tenant, workspace=workspace, title="Doc B")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT baseline/tests/test_document_scope_binding.py::TestImmutabilityStaysIntact -v`
Expected: FAIL with `ProgrammingError: column "document_id" of relation "bl_baseline_snapshot" does not exist`

- [ ] **Step 3: Write minimal implementation**

Add to `BaselineSnapshot` in `backend/baseline/models.py`, directly below the existing `artifact` field:

```python
    # Dokumentensicht spec §6: for scope="document" this is the real
    # ``persistence.Document`` the baseline froze. It supersedes the legacy
    # ``artifact`` column above, which was declared but never written by
    # ``BaselineStore.persist_delta_index`` -- every pre-existing
    # scope="document" row therefore has artifact_id NULL, which is why the
    # migration of old rows is an opt-in management command rather than a data
    # migration (there is nothing stored to migrate from).
    # SET_NULL, not CASCADE: deleting a document must never destroy the
    # immutable baseline history that referenced it.
    document = models.ForeignKey(
        "persistence.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="baseline_snapshots",
    )
```

Create `backend/baseline/migrations/0007_baseline_document_fk.py`:

```python
"""Bind scope="document" baselines to a real Document (Dokumentensicht §6).

Two operations:

1. ``AddField`` for the nullable ``document`` FK.
2. ``CREATE OR REPLACE`` of ``bl_raise_immutable()`` with one narrow, opt-in
   exception so ``manage.py backfill_baseline_documents`` can stamp
   ``document_id`` onto pre-existing rows.

Why a GUC and not ``ALTER TABLE ... DISABLE TRIGGER``: disabling a trigger is
owner-only DDL. Tables are owned by the migration role (``DB_USER``); the app
connects as ``reqogniloom_app`` (``persistence/migrations/0048_app_role.py``)
with CRUD grants only, so a DISABLE would pass in tests (owner) and fail in
production with "must be owner of table". Setting a dotted custom GUC needs no
privilege, is scoped to the transaction, and takes no ACCESS EXCLUSIVE lock.

The exception is as narrow as it can be made:
  * only under an explicit, transaction-local ``set_config(..., true)``,
  * only when ``document_id`` was NULL and becomes non-NULL (one-way, once),
  * only when every other column is byte-identical
    (``to_jsonb(NEW) - 'document_id' = to_jsonb(OLD) - 'document_id'``).
DELETE keeps raising unconditionally.
"""
from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models

_ALLOW_BACKFILL_FN = """
CREATE OR REPLACE FUNCTION bl_raise_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF TG_TABLE_NAME = 'bl_baseline_snapshot'
           AND coalesce(current_setting('app.baseline_document_backfill', true), '') = 'true'
           AND OLD.document_id IS NULL
           AND NEW.document_id IS NOT NULL
           AND (to_jsonb(NEW) - 'document_id') = (to_jsonb(OLD) - 'document_id')
        THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'Baselines are immutable';
    ELSIF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Baselines are immutable';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

_ORIGINAL_FN = """
CREATE OR REPLACE FUNCTION bl_raise_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Baselines are immutable';
    ELSIF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Baselines are immutable';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("baseline", "0006_baseline_snapshot_rls"),
        # Point this at the migration that actually created pl_document.
        ("persistence", "0090_documents"),
    ]

    operations = [
        migrations.AddField(
            model_name="baselinesnapshot",
            name="document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="baseline_snapshots",
                to="persistence.document",
            ),
        ),
        migrations.RunSQL(sql=_ALLOW_BACKFILL_FN, reverse_sql=_ORIGINAL_FN),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT baseline/tests/test_document_scope_binding.py -v`
Expected: PASS (11 passed — 6 from Task 8 plus 5 immutability cases)

- [ ] **Step 5: Commit**

```bash
git add backend/baseline/models.py backend/baseline/migrations/0007_baseline_document_fk.py \
        backend/baseline/tests/test_document_scope_binding.py backend/baseline/tests/conftest.py
git commit -m "feat(baseline): add Document FK with a GUC-gated backfill exception"
```

---

## Task 10: Persist the Document binding and resolve it in BaselineFacade

**Files:**
- Modify: `backend/baseline/types.py` (`BaselineMetadata`)
- Modify: `backend/baseline/store.py:101-113` (`persist_delta_index`)
- Modify: `backend/baseline/delta_index_builder.py:427-440` (metadata assembly)
- Modify: `backend/baseline/services.py:69-109` (`build`)
- Modify: `backend/application/baseline_facade.py:112-213` (`create_baseline`), `:296-307` (`_enforce_audit_gate`)
- Modify: `backend/application/workspace_lookup.py:68-101` (`ENTITY_SPECS`)
- Test: `backend/application/tests/test_baseline_facade_document_scope.py`

**Interfaces:**
- Consumes: `DocumentScopeService.resolve_document_artifact_ids`, `AuditScope.item_ids`, `baseline.services.build(item_ids=…, document_ref=…)`
- Produces: `BaselineMetadata.document_id: Optional[UUID]`; `BaselineSnapshot.document_id` populated on every new document-scope baseline built from a real `Document`.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_baseline_facade_document_scope.py`:

```python
"""scope='document' binds to a real Document; artifact ids keep working (§6)."""
from __future__ import annotations

import uuid

import pytest

from application.base import ValidationError
from application.baseline_facade import BaselineFacade
from baseline.models import BaselineSnapshot
from persistence.models import Document, DocumentSection


@pytest.fixture
def document_with_section(tenant, workspace, artifacts):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="Lastenheft")
    DocumentSection.objects.create(
        tenant=tenant, document=doc, title="Reqs", content_type="fixed",
        fixed_artifact_ids=[str(artifacts[0].id)],
    )
    return doc


@pytest.mark.django_db
def test_document_uuid_binds_the_snapshot_to_the_document(
    ctx, workspace, document_with_section, monkeypatch
):
    monkeypatch.setattr(BaselineFacade, "_enforce_audit_gate", lambda self, **kw: ())
    baseline_id = BaselineFacade().create_baseline(
        scope="document", workspace_id=workspace.id, name="bl-doc", ctx=ctx,
        document_id=document_with_section.id,
    )
    snap = BaselineSnapshot.objects.get(id=baseline_id)
    assert str(snap.document_id) == str(document_with_section.id)


@pytest.mark.django_db
def test_document_scope_captures_exactly_the_sections_artifacts(
    ctx, workspace, artifacts, document_with_section, monkeypatch
):
    monkeypatch.setattr(BaselineFacade, "_enforce_audit_gate", lambda self, **kw: ())
    baseline_id = BaselineFacade().create_baseline(
        scope="document", workspace_id=workspace.id, name="bl-doc-2", ctx=ctx,
        document_id=document_with_section.id,
    )
    snap = BaselineSnapshot.objects.get(id=baseline_id)
    captured = {e.item_id for e in snap.delta_entries.all() if e.entity_type == "item"}
    assert captured == {str(artifacts[0].id)}


@pytest.mark.django_db
def test_a_root_artifact_uuid_still_works_and_leaves_document_null(
    ctx, workspace, artifacts, monkeypatch
):
    """Backwards compatibility: every pre-existing caller sends an Artifact id."""
    monkeypatch.setattr(BaselineFacade, "_enforce_audit_gate", lambda self, **kw: ())
    baseline_id = BaselineFacade().create_baseline(
        scope="document", workspace_id=workspace.id, name="bl-legacy", ctx=ctx,
        document_id=artifacts[0].id,
    )
    snap = BaselineSnapshot.objects.get(id=baseline_id)
    assert snap.document_id is None
    assert str(artifacts[0].id) in {e.item_id for e in snap.delta_entries.all()}


@pytest.mark.django_db
def test_the_audit_gate_receives_the_resolved_item_ids_for_a_document(
    ctx, workspace, artifacts, document_with_section, monkeypatch
):
    captured = {}

    class _SpyAuditService:
        def blocking_findings(self, workspace_id, ctx, scopes):
            captured["scopes"] = scopes
            return ()

    monkeypatch.setattr(
        "application.audit_service.AuditService", _SpyAuditService
    )
    BaselineFacade().create_baseline(
        scope="document", workspace_id=workspace.id, name="bl-gate", ctx=ctx,
        document_id=document_with_section.id,
    )
    scope = captured["scopes"][0]
    assert scope.item_ids == (str(artifacts[0].id),)


@pytest.mark.django_db
def test_unknown_uuid_is_a_clean_validation_error(ctx, workspace, monkeypatch):
    monkeypatch.setattr(BaselineFacade, "_enforce_audit_gate", lambda self, **kw: ())
    with pytest.raises(ValidationError):
        BaselineFacade().create_baseline(
            scope="document", workspace_id=workspace.id, name="bl-missing", ctx=ctx,
            document_id=uuid.uuid4(),
        )
```

`_enforce_audit_gate` imports `AuditService` lazily from `application.audit_service`, so patching the attribute on that module (as above) is what takes effect — do not patch `application.baseline_facade.AuditService`, which does not exist as a module attribute.

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_baseline_facade_document_scope.py -v`
Expected: FAIL — the binding case fails with `AssertionError: None != '<uuid>'`, and the "exactly the sections artifacts" case fails because the subtree walk finds nothing under a Document UUID.

- [ ] **Step 3: Write minimal implementation**

`backend/baseline/types.py` — add to `BaselineMetadata`:

```python
    #: For ``scope="document"``: the ``persistence.Document`` this baseline
    #: froze (Dokumentensicht spec §6). ``None`` for project/global scope and
    #: for the legacy artifact-root form of document scope.
    document_id: Optional[uuid.UUID] = None
```

`backend/baseline/store.py` — in `persist_delta_index`, add one kwarg to the `BaselineSnapshot(...)` construction:

```python
                document_id=metadata.document_id,
```

`backend/baseline/delta_index_builder.py` — `DeltaIndexBuilder.build` gains `document_ref: Optional[uuid.UUID] = None` and sets `document_id=document_ref` on the `BaselineMetadata`. A separate keyword from `document_id` on purpose: `document_id` still means "the thing the scope is resolved from" (which may be an Artifact), `document_ref` means "the Document row to record". Thread the same keyword through `baseline.services.build`.

`backend/application/baseline_facade.py` — in `create_baseline`, after the existing `scope == "document" and doc_id is None` guard:

```python
        # Dokumentensicht spec §6: document scope now names a real Document.
        # A raw root-Artifact UUID stays accepted (every pre-existing REST/MCP
        # caller sends one); Document is probed first, and UUID primary keys
        # make a cross-table collision impossible.
        document_ref: Optional[UUID] = None
        resolved_item_ids: Optional[list[str]] = None
        if scope == "document":
            from persistence.models import Artifact, Document

            if Document.objects.filter(id=doc_id).exists():
                from application.document_scope_service import DocumentScopeService

                document_ref = doc_id
                resolved_item_ids = DocumentScopeService().resolve_document_artifact_ids(
                    ctx=ctx, document_id=doc_id
                )
            elif not Artifact.objects.filter(id=doc_id).exists():
                raise ValidationError(
                    f"Baseline cannot be created: no Document and no Artifact "
                    f"with id {doc_id} exists in this tenant."
                )
            else:
                logger.info(
                    "Baseline document scope resolved %s as a root Artifact "
                    "(deprecated; pass a Document id instead).",
                    doc_id,
                )
```

Pass both onward:

```python
        waived = self._enforce_audit_gate(
            workspace_id=ws_id,
            scope=scope,
            document_id=doc_id,
            ctx=ctx,
            override_reason=override_reason,
            item_ids=resolved_item_ids,
        )
        ...
            baseline_id = baseline_build(
                scope=scope,
                workspace_id=ws_id,
                name=name,
                tenant_id=ctx.tenant_id,
                description=effective_description,
                created_by=str(ctx.user_id),
                document_id=doc_id,
                item_ids=resolved_item_ids,
                document_ref=document_ref,
            )
```

and in `_enforce_audit_gate`, add `item_ids: Optional[list[str]] = None` and seed the scope:

```python
        audit_scope = AuditScope(
            scope=scope,
            artifact_id=str(document_id) if document_id is not None else None,
            item_ids=tuple(item_ids) if item_ids is not None else None,
        )
```

`backend/application/workspace_lookup.py` — add to `ENTITY_SPECS` so the MCP RBAC gate (Task 14) can resolve a document's owning workspace:

```python
    "document": EntityWorkspaceSpec("persistence.models.Document"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_baseline_facade_document_scope.py application/tests/test_baseline_audit_gate.py baseline/tests/ -v`
Expected: PASS (5 new tests; the existing baseline and audit-gate suites unchanged)

- [ ] **Step 5: Commit**

```bash
git add backend/baseline/types.py backend/baseline/store.py \
        backend/baseline/delta_index_builder.py backend/baseline/services.py \
        backend/application/baseline_facade.py backend/application/workspace_lookup.py \
        backend/application/tests/test_baseline_facade_document_scope.py
git commit -m "feat(baseline): bind document-scope baselines to a real Document"
```

---

## Task 11: backfill_baseline_documents management command

**Files:**
- Create: `backend/application/management/commands/backfill_baseline_documents.py`
- Test: `backend/application/tests/test_backfill_baseline_documents.py`

**Interfaces:**
- Consumes: the `app.baseline_document_backfill` GUC from Task 9
- Produces: `manage.py backfill_baseline_documents --tenant <uuid> [--dry-run]`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_backfill_baseline_documents.py`:

```python
"""Opt-in backfill of legacy document-scope baselines (spec §6, §9)."""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command

from baseline.models import BaselineDeltaIndexEntry, BaselineSnapshot
from persistence.models import Document, DocumentSection


def _legacy_document_baseline(tenant, workspace, artifact_ids, name):
    snap = BaselineSnapshot.objects.create(
        tenant=tenant, workspace_id=workspace.id, scope="document", name=name
    )
    for artifact_id in artifact_ids:
        BaselineDeltaIndexEntry.objects.create(
            baseline=snap, item_id=str(artifact_id), version=1, entity_type="item"
        )
    BaselineDeltaIndexEntry.objects.create(
        baseline=snap, item_id=str(uuid.uuid4()), version=1, entity_type="trace_link"
    )
    return snap


@pytest.mark.django_db(transaction=True)
def test_creates_one_document_with_a_fixed_section_per_legacy_baseline(
    tenant, workspace, artifacts
):
    ids = [str(artifacts[0].id), str(artifacts[1].id)]
    snap = _legacy_document_baseline(tenant, workspace, ids, "legacy-1")

    call_command("backfill_baseline_documents", tenant=str(tenant.id))

    snap.refresh_from_db()
    assert snap.document_id is not None
    doc = Document.objects.get(id=snap.document_id)
    assert "legacy-1" in doc.title
    section = DocumentSection.objects.get(document=doc)
    assert section.content_type == "fixed"
    assert sorted(section.fixed_artifact_ids) == sorted(ids)


@pytest.mark.django_db(transaction=True)
def test_trace_link_entries_are_not_treated_as_artifacts(tenant, workspace, artifacts):
    snap = _legacy_document_baseline(
        tenant, workspace, [str(artifacts[0].id)], "legacy-2"
    )
    call_command("backfill_baseline_documents", tenant=str(tenant.id))
    snap.refresh_from_db()
    section = DocumentSection.objects.get(document_id=snap.document_id)
    assert section.fixed_artifact_ids == [str(artifacts[0].id)]


@pytest.mark.django_db(transaction=True)
def test_dry_run_writes_nothing(tenant, workspace, artifacts):
    snap = _legacy_document_baseline(
        tenant, workspace, [str(artifacts[0].id)], "legacy-3"
    )
    call_command("backfill_baseline_documents", tenant=str(tenant.id), dry_run=True)
    snap.refresh_from_db()
    assert snap.document_id is None
    assert Document.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_is_idempotent(tenant, workspace, artifacts):
    _legacy_document_baseline(tenant, workspace, [str(artifacts[0].id)], "legacy-4")
    call_command("backfill_baseline_documents", tenant=str(tenant.id))
    call_command("backfill_baseline_documents", tenant=str(tenant.id))
    assert Document.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_project_scope_baselines_are_ignored(tenant, workspace):
    BaselineSnapshot.objects.create(
        tenant=tenant, workspace_id=workspace.id, scope="project", name="proj"
    )
    call_command("backfill_baseline_documents", tenant=str(tenant.id))
    assert Document.objects.count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_backfill_baseline_documents.py -v`
Expected: FAIL with `CommandError: Unknown command: 'backfill_baseline_documents'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/management/commands/backfill_baseline_documents.py`:

```python
"""Materialise a Document for every legacy scope="document" baseline (§6).

Opt-in on purpose. ``BaselineSnapshot.artifact`` was declared in
``baseline/models.py`` but never written by ``BaselineStore`` -- every
pre-existing document-scope snapshot therefore has ``artifact_id IS NULL`` and
there is no stored root artifact to migrate from. What *is* authoritative is
the snapshot's own frozen delta index, so this command reproduces the
historical scope exactly: one Document per legacy snapshot, holding one
``fixed`` section with that snapshot's ``entity_type='item'`` ids. No
heuristic root-guessing, no data loss.

Run against a copy first (spec §9): ``--dry-run`` reports without writing.

The ``document_id`` write goes through the transaction-local GUC installed by
``baseline/migrations/0007_baseline_document_fk.py``; the snapshot stays
immutable in every other respect.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Create a Document for each legacy scope='document' BaselineSnapshot."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--tenant", required=True, help="Tenant UUID to process.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Report what would be created without writing anything.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from baseline.models import BaselineSnapshot
        from persistence.models import Document, DocumentSection

        try:
            tenant_id = UUID(str(options["tenant"]))
        except (ValueError, TypeError) as exc:
            raise CommandError("--tenant must be a valid UUID") from exc
        dry_run: bool = bool(options.get("dry_run"))

        # RLS: a maintenance command runs outside a request, so the session
        # variable has to be armed explicitly. Without it every query returns
        # zero rows and the command silently no-ops (the #103 backfill trap).
        with connection.cursor() as cur:
            cur.execute(
                "SELECT set_config('app.current_tenant', %s, false)", [str(tenant_id)]
            )

        snapshots = BaselineSnapshot.unscoped.filter(
            tenant_id=tenant_id, scope="document", document__isnull=True
        ).order_by("created_at")

        created = 0
        for snapshot in snapshots:
            artifact_ids = sorted(
                {
                    entry.item_id
                    for entry in snapshot.delta_entries.filter(entity_type="item")
                }
            )
            if not artifact_ids:
                self.stdout.write(f"skip {snapshot.name}: no item entries to reproduce")
                continue
            if dry_run:
                self.stdout.write(
                    f"would create Document for {snapshot.name} "
                    f"({len(artifact_ids)} artifacts)"
                )
                continue

            with transaction.atomic():
                document = Document.objects.create(
                    tenant_id=tenant_id,
                    workspace_id=snapshot.workspace_id,
                    title=f"{snapshot.name} (migriert)",
                    description=(
                        "Automatically created from a legacy document-scope "
                        "baseline. The section below reproduces exactly the "
                        "artifacts that baseline froze."
                    ),
                )
                DocumentSection.objects.create(
                    tenant_id=tenant_id,
                    document=document,
                    title="Inhalt",
                    order=0,
                    content_type=DocumentSection.CONTENT_TYPE_FIXED,
                    fixed_artifact_ids=artifact_ids,
                )
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT set_config('app.baseline_document_backfill', 'true', true)"
                    )
                    cur.execute(
                        "UPDATE bl_baseline_snapshot SET document_id = %s WHERE id = %s",
                        [str(document.id), str(snapshot.id)],
                    )
            created += 1
            self.stdout.write(f"bound {snapshot.name} -> Document {document.id}")

        verb = "would create" if dry_run else "created"
        self.stdout.write(self.style.SUCCESS(f"{verb} {created} document(s)"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_backfill_baseline_documents.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/management/commands/backfill_baseline_documents.py \
        backend/application/tests/test_backfill_baseline_documents.py
git commit -m "feat(baseline): add opt-in backfill for legacy document-scope baselines"
```

---

## Task 12: REST document and section CRUD

**Files:**
- Create: `backend/rest_api/document_views.py`
- Modify: `backend/rest_api/urls.py` (5 paths, before `include(router.urls)`)
- Test: `backend/rest_api/tests/test_document_views.py`

**Interfaces:**
- Consumes: `DocumentService` (all methods)
- Produces:
  ```
  GET|POST         /api/v1/documents/
  GET|PATCH|DELETE /api/v1/documents/<uuid:document_id>/
  GET|POST         /api/v1/documents/<uuid:document_id>/sections/
  POST             /api/v1/documents/<uuid:document_id>/sections/reorder/
  PATCH|DELETE     /api/v1/document-sections/<uuid:section_id>/
  ```

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_document_views.py`:

```python
"""REST surface for documents and sections (spec §7)."""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from persistence.models import Document, DocumentSection


@pytest.fixture
def client(auth_headers):
    api = APIClient()
    api.credentials(**auth_headers)
    return api


@pytest.mark.django_db
def test_list_requires_workspace_id(client):
    assert client.get("/api/v1/documents/").status_code == 400


@pytest.mark.django_db
def test_list_returns_workspace_documents(client, tenant, workspace):
    Document.objects.create(tenant=tenant, workspace=workspace, title="D1")
    response = client.get(f"/api/v1/documents/?workspace_id={workspace.id}")
    assert response.status_code == 200
    assert [d["title"] for d in response.data["documents"]] == ["D1"]


@pytest.mark.django_db
def test_create_returns_201_and_the_document(client, workspace):
    response = client.post(
        "/api/v1/documents/",
        {"workspace_id": str(workspace.id), "title": "Lastenheft"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["title"] == "Lastenheft"


@pytest.mark.django_db
def test_create_with_blank_title_is_400_not_500(client, workspace):
    response = client.post(
        "/api/v1/documents/",
        {"workspace_id": str(workspace.id), "title": "  "},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_get_unknown_document_is_404(client):
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/").status_code == 404


@pytest.mark.django_db
def test_patch_updates_the_title(client, tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="Old")
    response = client.patch(
        f"/api/v1/documents/{doc.id}/", {"title": "New"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["title"] == "New"


@pytest.mark.django_db
def test_delete_returns_204(client, tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="Gone")
    assert client.delete(f"/api/v1/documents/{doc.id}/").status_code == 204


@pytest.mark.django_db
def test_create_section_with_a_query_payload(client, tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="D")
    response = client.post(
        f"/api/v1/documents/{doc.id}/sections/",
        {
            "title": "Functional",
            "content_type": "query",
            "query": {"item_type": "Requirement", "filters": {}},
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["query"]["item_type"] == "Requirement"


@pytest.mark.django_db
def test_create_query_section_without_query_is_400(client, tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="D")
    response = client.post(
        f"/api/v1/documents/{doc.id}/sections/",
        {"title": "Broken", "content_type": "query"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_reorder_returns_the_new_order(client, tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="D")
    a = DocumentSection.objects.create(
        tenant=tenant, document=doc, title="A", order=0, content_type="fixed"
    )
    b = DocumentSection.objects.create(
        tenant=tenant, document=doc, title="B", order=1, content_type="fixed"
    )
    response = client.post(
        f"/api/v1/documents/{doc.id}/sections/reorder/",
        {"section_ids": [str(b.id), str(a.id)]},
        format="json",
    )
    assert response.status_code == 200
    assert [s["title"] for s in response.data["sections"]] == ["B", "A"]


@pytest.mark.django_db
def test_patch_section_rejecting_a_cycle_is_400(client, tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="D")
    a = DocumentSection.objects.create(
        tenant=tenant, document=doc, title="A", content_type="fixed"
    )
    b = DocumentSection.objects.create(
        tenant=tenant, document=doc, title="B", content_type="fixed", parent_section=a
    )
    response = client.patch(
        f"/api/v1/document-sections/{a.id}/",
        {"parent_section_id": str(b.id)},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_delete_section_returns_204(client, tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="D")
    section = DocumentSection.objects.create(
        tenant=tenant, document=doc, title="S", content_type="fixed"
    )
    assert client.delete(f"/api/v1/document-sections/{section.id}/").status_code == 204
```

Reuse `auth_headers` / `tenant` / `workspace` from `backend/rest_api/tests/conftest.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `BT rest_api/tests/test_document_views.py -v`
Expected: FAIL — every case returns 404 (no route registered)

- [ ] **Step 3: Write minimal implementation**

Create `backend/rest_api/document_views.py`:

```python
"""Document / DocumentSection REST endpoints (Dokumentensicht spec §7).

Zero ORM (ADR-01): every query goes through
``application.document_service.DocumentService``. ``_service_error`` keeps the
mapping from the three Layer-2 exceptions to HTTP codes in exactly one place;
``DocumentService`` raises the plain ``application.base`` types on purpose,
since a subclass would degrade to a 500 in ``rest_api/views.py:_EXC_TO_HTTP``.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.document_service import DocumentService
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _service_error(exc: Exception, lang: str) -> Response:
    """Map a Layer-2 exception onto its HTTP response."""
    if isinstance(exc, NotFoundError):
        return Response(
            build_error_response("NOT_FOUND", lang, message=str(exc)),
            status=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, PermissionDeniedError):
        return Response(
            build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
            status=status.HTTP_403_FORBIDDEN,
        )
    return Response(
        build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _serializer_error(ser: serializers.Serializer, lang: str) -> Response:
    return Response(
        build_error_response(
            "VALIDATION_ERROR",
            lang,
            details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
        ),
        status=status.HTTP_400_BAD_REQUEST,
    )


class DocumentCreateSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    title = serializers.CharField(max_length=255, trim_whitespace=False)
    description = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )


class DocumentPatchSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, max_length=255, trim_whitespace=False)
    description = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )


class SectionWriteSerializer(serializers.Serializer):
    """Body of POST/PATCH on a section. Every field is optional on PATCH."""

    title = serializers.CharField(required=False, max_length=255, trim_whitespace=False)
    content_type = serializers.ChoiceField(
        required=False, choices=["query", "fixed", "subtree"]
    )
    parent_section_id = serializers.UUIDField(required=False, allow_null=True)
    order = serializers.IntegerField(required=False)
    query = serializers.JSONField(required=False, allow_null=True)
    fixed_artifact_ids = serializers.ListField(
        required=False, child=serializers.CharField()
    )
    subtree_root_artifact_id = serializers.UUIDField(required=False, allow_null=True)


class ReorderSerializer(serializers.Serializer):
    section_ids = serializers.ListField(child=serializers.UUIDField())


class DocumentListCreateView(APIView):
    """GET (list) and POST (create) on /api/v1/documents/."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        raw = request.query_params.get("workspace_id")
        if not raw:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="'workspace_id' is required."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            workspace_id = UUID(raw)
        except ValueError:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="'workspace_id' must be a UUID."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        documents = DocumentService().list_documents(ctx=ctx, workspace_id=workspace_id)
        return Response({"documents": documents, "count": len(documents)})

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        ser = DocumentCreateSerializer(data=request.data)
        if not ser.is_valid():
            return _serializer_error(ser, lang)
        try:
            document = DocumentService().create_document(
                ctx=ctx,
                workspace_id=ser.validated_data["workspace_id"],
                title=ser.validated_data["title"],
                description=ser.validated_data.get("description", ""),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)
        return Response(document, status=status.HTTP_201_CREATED)


class DocumentDetailView(APIView):
    """GET / PATCH / DELETE on /api/v1/documents/<uuid:document_id>/."""

    def get(self, request: Request, document_id: UUID, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        try:
            return Response(
                DocumentService().get_document(ctx=ctx, document_id=document_id)
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)

    def patch(self, request: Request, document_id: UUID, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        ser = DocumentPatchSerializer(data=request.data)
        if not ser.is_valid():
            return _serializer_error(ser, lang)
        try:
            return Response(
                DocumentService().update_document(
                    ctx=ctx,
                    document_id=document_id,
                    title=ser.validated_data.get("title"),
                    description=ser.validated_data.get("description"),
                )
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)

    def delete(self, request: Request, document_id: UUID, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        try:
            DocumentService().delete_document(ctx=ctx, document_id=document_id)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentSectionListCreateView(APIView):
    """GET / POST on /api/v1/documents/<uuid:document_id>/sections/."""

    def get(self, request: Request, document_id: UUID, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        try:
            sections = DocumentService().list_sections(ctx=ctx, document_id=document_id)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)
        return Response({"sections": sections, "count": len(sections)})

    def post(self, request: Request, document_id: UUID, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        ser = SectionWriteSerializer(data=request.data)
        if not ser.is_valid():
            return _serializer_error(ser, lang)
        data = ser.validated_data
        try:
            section = DocumentService().create_section(
                ctx=ctx,
                document_id=document_id,
                title=data.get("title", ""),
                content_type=data.get("content_type", "fixed"),
                parent_section_id=data.get("parent_section_id"),
                order=data.get("order", 0),
                query=data.get("query"),
                fixed_artifact_ids=data.get("fixed_artifact_ids"),
                subtree_root_artifact_id=data.get("subtree_root_artifact_id"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)
        return Response(section, status=status.HTTP_201_CREATED)


class DocumentSectionReorderView(APIView):
    """POST /api/v1/documents/<uuid:document_id>/sections/reorder/."""

    def post(self, request: Request, document_id: UUID, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        ser = ReorderSerializer(data=request.data)
        if not ser.is_valid():
            return _serializer_error(ser, lang)
        try:
            sections = DocumentService().reorder_sections(
                ctx=ctx,
                document_id=document_id,
                ordered_section_ids=ser.validated_data["section_ids"],
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)
        return Response({"sections": sections})


class DocumentSectionDetailView(APIView):
    """PATCH / DELETE on /api/v1/document-sections/<uuid:section_id>/."""

    #: Forwarded only when actually present in the body, so DocumentService's
    #: ``_UNSET`` sentinel keeps meaning "omitted" rather than "set to None".
    _PATCHABLE = (
        "title",
        "order",
        "content_type",
        "parent_section_id",
        "query",
        "fixed_artifact_ids",
        "subtree_root_artifact_id",
    )

    def patch(self, request: Request, section_id: UUID, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        ser = SectionWriteSerializer(data=request.data)
        if not ser.is_valid():
            return _serializer_error(ser, lang)
        data = ser.validated_data
        forwarded = {key: data[key] for key in self._PATCHABLE if key in data}
        try:
            section = DocumentService().update_section(
                ctx=ctx, section_id=section_id, **forwarded
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)
        return Response(section)

    def delete(self, request: Request, section_id: UUID, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        try:
            DocumentService().delete_section(ctx=ctx, section_id=section_id)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


__all__ = [
    "DocumentDetailView",
    "DocumentListCreateView",
    "DocumentSectionDetailView",
    "DocumentSectionListCreateView",
    "DocumentSectionReorderView",
]
```

In `backend/rest_api/urls.py`, import the five views and add these paths **before** `path("", include(router.urls))`:

```python
    path("documents/", DocumentListCreateView.as_view(), name="api-v1-documents"),
    path(
        "documents/<uuid:document_id>/",
        DocumentDetailView.as_view(),
        name="api-v1-document-detail",
    ),
    path(
        "documents/<uuid:document_id>/sections/reorder/",
        DocumentSectionReorderView.as_view(),
        name="api-v1-document-sections-reorder",
    ),
    path(
        "documents/<uuid:document_id>/sections/",
        DocumentSectionListCreateView.as_view(),
        name="api-v1-document-sections",
    ),
    path(
        "document-sections/<uuid:section_id>/",
        DocumentSectionDetailView.as_view(),
        name="api-v1-document-section-detail",
    ),
```

`sections/reorder/` is declared before `sections/` deliberately: Django resolves in declaration order, and keeping the more specific path first removes any doubt.

- [ ] **Step 4: Run test to verify it passes**

Run: `BT rest_api/tests/test_document_views.py rest_api/tests/test_architecture.py -v`
Expected: PASS (12 new tests; the ADR-01 ratchet stays green — `document_views.py` has zero direct-ORM lines and does not import `persistence.models`)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/document_views.py backend/rest_api/urls.py \
        backend/rest_api/tests/test_document_views.py
git commit -m "feat(documents): add REST CRUD for documents and sections"
```

---

## Task 13: REST read mode and Markdown export

**Files:**
- Modify: `backend/rest_api/document_views.py` (append two views)
- Modify: `backend/rest_api/urls.py` (2 paths)
- Modify: `backend/rest_api/views.py:3202-3229` (baseline create accepts `document_id`)
- Modify: `backend/rest_api/serializers.py` (baseline create serializer + `document_id`)
- Test: `backend/rest_api/tests/test_document_read_export_views.py`

**Interfaces:**
- Consumes: `DocumentReadService.read`
- Produces:
  ```
  GET /api/v1/documents/<uuid:document_id>/read/    -> {"document_id","title","markdown","sections":[…]}
  GET /api/v1/documents/<uuid:document_id>/export/  -> text/markdown attachment
  ```

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_document_read_export_views.py`:

```python
"""Read mode and Markdown export endpoints (spec §4, §5)."""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from persistence.models import Document, DocumentSection


@pytest.fixture
def client(auth_headers):
    api = APIClient()
    api.credentials(**auth_headers)
    return api


@pytest.fixture
def document(tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="Lastenheft")
    DocumentSection.objects.create(
        tenant=tenant, document=doc, title="Scope", order=0, content_type="fixed"
    )
    return doc


@pytest.mark.django_db
def test_read_returns_markdown_and_the_section_outline(client, document):
    response = client.get(f"/api/v1/documents/{document.id}/read/")
    assert response.status_code == 200
    assert response.data["title"] == "Lastenheft"
    assert response.data["markdown"].startswith("# Lastenheft")
    assert response.data["sections"][0]["number"] == "1"
    assert "content" not in response.data


@pytest.mark.django_db
def test_read_unknown_document_is_404(client):
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/read/").status_code == 404


@pytest.mark.django_db
def test_export_returns_a_markdown_attachment(client, document):
    response = client.get(f"/api/v1/documents/{document.id}/export/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/markdown")
    assert "attachment" in response["Content-Disposition"]
    assert ".md" in response["Content-Disposition"]
    assert b"# Lastenheft" in response.content


@pytest.mark.django_db
def test_export_does_not_negotiate_on_a_format_param(client, document):
    """`format` is reserved by DRF content negotiation, so the endpoint must
    not expose a format switch at all (Scope decision 2)."""
    response = client.get(f"/api/v1/documents/{document.id}/export/?fmt=markdown")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/markdown")


@pytest.mark.django_db
def test_baseline_create_accepts_document_id(client, tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="D")
    DocumentSection.objects.create(
        tenant=tenant, document=doc, title="S", content_type="fixed",
        fixed_artifact_ids=[],
    )
    response = client.post(
        "/api/v1/baselines/",
        {
            "workspace_id": str(workspace.id),
            "scope": "document",
            "name": f"bl-{uuid.uuid4()}",
            "document_id": str(doc.id),
        },
        format="json",
    )
    # 400 only if the SE-Auditor gate blocks; never the old "artifact_id is
    # required" validation error.
    assert response.status_code in (201, 400)
    assert "artifact_id is required" not in str(response.data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT rest_api/tests/test_document_read_export_views.py -v`
Expected: FAIL — read/export return 404; the baseline case returns 400 "artifact_id is required for document scope"

- [ ] **Step 3: Write minimal implementation**

Append to `backend/rest_api/document_views.py`:

```python
class DocumentReadView(APIView):
    """GET /api/v1/documents/<uuid:document_id>/read/ (spec §4).

    Deliberately live: ``query`` sections are evaluated on every call, so two
    reads seconds apart may differ. That is the "lebendes Dokument" contract
    (spec §9); a frozen view is what a Baseline is for.
    """

    def get(self, request: Request, document_id: UUID, **kwargs: Any) -> Response:
        from application.document_read_service import DocumentReadService

        lang = detect_lang(request)
        ctx = get_auth_context(request)
        try:
            rendered = DocumentReadService().read(ctx=ctx, document_id=document_id)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)
        return Response(rendered.to_dict())


class DocumentExportView(APIView):
    """GET /api/v1/documents/<uuid:document_id>/export/ (spec §5).

    Markdown only, and **no format query parameter**: ``format`` is reserved by
    DRF content negotiation, and a stub renderer registered under that name
    corrupts the body at HTTP 200 rather than erroring. A future DOCX export
    gets ``?fmt=docx``.
    """

    def get(self, request: Request, document_id: UUID, **kwargs: Any) -> Response:
        from django.http import HttpResponse

        from application.document_read_service import DocumentReadService

        lang = detect_lang(request)
        ctx = get_auth_context(request)
        try:
            rendered = DocumentReadService().read(ctx=ctx, document_id=document_id)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error(exc, lang)

        safe_title = (
            "".join(
                char if char.isalnum() or char in "-_" else "_"
                for char in rendered.title
            )
            or "document"
        )
        response = HttpResponse(
            rendered.markdown, content_type="text/markdown; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="{safe_title}.md"'
        return response
```

Add both names to `__all__` and register in `backend/rest_api/urls.py` next to the other document paths:

```python
    path(
        "documents/<uuid:document_id>/read/",
        DocumentReadView.as_view(),
        name="api-v1-document-read",
    ),
    path(
        "documents/<uuid:document_id>/export/",
        DocumentExportView.as_view(),
        name="api-v1-document-export",
    ),
```

In `backend/rest_api/serializers.py`, add to the baseline create serializer (the one whose `validated_data` feeds `views.py:3189`):

```python
    document_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text=(
            "Document UUID for scope='document' (Dokumentensicht spec §6). "
            "The legacy 'artifact_id' form (a root Artifact UUID) is still "
            "accepted for backwards compatibility."
        ),
    )
```

In `backend/rest_api/views.py`, replace the `artifact_id` block at `:3202-3229` with:

```python
            # Dokumentensicht spec §6: 'document_id' names a real Document.
            # 'artifact_id' is the legacy view-facing name for a root Artifact
            # UUID and stays supported -- the facade probes Document first and
            # falls back to the artifact subtree.
            scope_ref = data.get("document_id") or data.get("artifact_id")
            if scope == "document" and scope_ref is None:
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message=(
                            "document_id (or the legacy artifact_id) is required "
                            "for document scope"
                        ),
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if scope_ref is not None:
                # GH-724: reject a malformed UUID here with a clean 400 instead
                # of letting the facade's UUID(str(...)) escape as a 500.
                try:
                    UUID(str(scope_ref))
                except (ValueError, TypeError):
                    return Response(
                        build_error_response(
                            "VALIDATION_ERROR",
                            lang,
                            message="document_id must be a valid UUID",
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                create_kwargs["document_id"] = str(scope_ref)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT rest_api/tests/test_document_read_export_views.py rest_api/tests/test_baselines.py -v`
Expected: PASS (5 new tests; the existing baseline REST suite stays green because `artifact_id` still works)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/document_views.py backend/rest_api/urls.py \
        backend/rest_api/views.py backend/rest_api/serializers.py \
        backend/rest_api/tests/test_document_read_export_views.py
git commit -m "feat(documents): add read-mode and markdown export endpoints"
```

---

## Task 14: MCP document tool group

**Files:**
- Create: `backend/mcp_server/tools/document.py`
- Modify: `backend/mcp_server/tool_registry.py` (group map, ~line 600)
- Modify: `backend/mcp_server/workspace_scope.py` (`_TOOL_TARGETS`)
- Modify: `backend/mcp_server/tools/baseline.py:103-107` (`document_id` schema description)
- Test: `backend/mcp_server/tests/test_document_tool_group.py`

**Interfaces:**
- Consumes: `DocumentService.list_documents/get_document/list_sections`, `DocumentReadService.read`
- Produces: MCP tools `document.list`, `document.get`, `document.read` (all read-only)

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_document_tool_group.py`:

```python
"""document.* MCP tool group (Dokumentensicht spec §7)."""
from __future__ import annotations

import json
import uuid

import pytest

from mcp_server.tools.document import DocumentToolGroup
from persistence.models import Document, DocumentSection


@pytest.fixture
def group():
    return DocumentToolGroup()


@pytest.fixture
def document(tenant, workspace):
    doc = Document.objects.create(tenant=tenant, workspace=workspace, title="Lastenheft")
    DocumentSection.objects.create(
        tenant=tenant, document=doc, title="Scope", order=0, content_type="fixed"
    )
    return doc


def test_schemas_declare_three_read_tools(group):
    names = {schema["name"] for schema in group.get_tool_schemas()}
    assert names == {"document.list", "document.get", "document.read"}


def test_list_requires_workspace_id_in_its_schema(group):
    schema = next(s for s in group.get_tool_schemas() if s["name"] == "document.list")
    assert schema["inputSchema"]["required"] == ["workspace_id"]


@pytest.mark.django_db
def test_list_returns_documents(group, auth_context, workspace, document):
    result = group.dispatch(
        "document.list", {"workspace_id": str(workspace.id)}, auth_context
    )
    assert result.success
    assert result.data["documents"][0]["title"] == "Lastenheft"


@pytest.mark.django_db
def test_get_includes_the_section_list(group, auth_context, document):
    result = group.dispatch("document.get", {"id": str(document.id)}, auth_context)
    assert result.success
    assert result.data["document"]["title"] == "Lastenheft"
    assert result.data["sections"][0]["title"] == "Scope"


@pytest.mark.django_db
def test_read_returns_markdown_under_a_non_colliding_key(group, auth_context, document):
    result = group.dispatch("document.read", {"id": str(document.id)}, auth_context)
    assert result.success
    assert result.data["markdown"].startswith("# Lastenheft")
    # A top-level "content" key collides with the JSON-RPC envelope.
    assert "content" not in result.data


@pytest.mark.django_db
def test_payloads_are_stdlib_json_serialisable(group, auth_context, document):
    for tool, params in (
        ("document.get", {"id": str(document.id)}),
        ("document.read", {"id": str(document.id)}),
    ):
        result = group.dispatch(tool, params, auth_context)
        json.dumps(result.data)  # the MCP transport uses stdlib json


@pytest.mark.django_db
def test_unknown_document_is_a_clean_not_found(group, auth_context):
    result = group.dispatch("document.get", {"id": str(uuid.uuid4())}, auth_context)
    assert not result.success
    assert "not found" in result.message.lower()


@pytest.mark.django_db
def test_missing_id_is_a_validation_error(group, auth_context):
    result = group.dispatch("document.get", {}, auth_context)
    assert not result.success


def test_workspace_scope_registry_covers_every_id_named_tool():
    from mcp_server.workspace_scope import _TOOL_TARGETS

    assert _TOOL_TARGETS["document.get"] == (("id", "document"),)
    assert _TOOL_TARGETS["document.read"] == (("id", "document"),)
```

Mirror the fixture set (`auth_context`, `tenant`, `workspace`) from `backend/mcp_server/tests/test_baseline_tool_group.py`. Every DB-touching test needs `@pytest.mark.django_db` even with mocked collaborators — arming RLS via `SET app.current_tenant` is a real database hit and pytest-django 4.12 no longer tolerates it without the mark.

- [ ] **Step 2: Run test to verify it fails**

Run: `BT mcp_server/tests/test_document_tool_group.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.document'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/tools/document.py`:

```python
"""DocumentToolGroup -- read-only MCP access to documents (spec §7).

Three tools, all reads:

  document.list — documents of a workspace
  document.get  — one document plus its section tree
  document.read — the numbered read-mode Markdown for a whole document

``document.read`` is the point of the group: an agent can read a specification
as one coherent document instead of artifact by artifact.

Layering (ADR-01): no ORM here. Everything goes through
``application.document_service`` / ``application.document_read_service``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.document_read_service import DocumentReadService
from application.document_service import DocumentService
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_uuid

logger = logging.getLogger(__name__)


class DocumentToolGroup(BaseToolGroup):
    """Read-only ``document.*`` tools."""

    _TOOL_MAP = {
        "document.list": "_handle_list",
        "document.get": "_handle_get",
        "document.read": "_handle_read",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "document.list",
            "description": "List the specification documents of a workspace (read).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the target workspace.",
                    }
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "document.get",
            "description": "Fetch one document with its ordered section tree (read).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Document UUID."}
                },
                "required": ["id"],
            },
        },
        {
            "name": "document.read",
            "description": (
                "Render a whole document as numbered Markdown (read). Query "
                "sections are evaluated live, so the result reflects the "
                "current state of the workspace."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Document UUID."}
                },
                "required": ["id"],
            },
        },
    ]

    # ---------- handlers ----------

    def _handle_list(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        try:
            workspace_id = require_uuid(params, "workspace_id")
            documents = DocumentService().list_documents(
                ctx=auth_context, workspace_id=workspace_id
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return self._error(exc)
        return ToolResult.ok({"documents": documents, "count": len(documents)})

    def _handle_get(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        try:
            document_id = require_uuid(params, "id")
            service = DocumentService()
            document = service.get_document(ctx=auth_context, document_id=document_id)
            sections = service.list_sections(ctx=auth_context, document_id=document_id)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return self._error(exc)
        return ToolResult.ok({"document": document, "sections": sections})

    def _handle_read(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        try:
            document_id = require_uuid(params, "id")
            rendered = DocumentReadService().read(
                ctx=auth_context, document_id=document_id
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return self._error(exc)
        # ``to_dict`` returns JSON primitives only and uses the key
        # ``markdown`` -- never ``content``, which collides with the JSON-RPC
        # envelope and 500s the transport.
        return ToolResult.ok(rendered.to_dict())

    @staticmethod
    def _error(exc: Exception) -> ToolResult:
        if isinstance(exc, NotFoundError):
            return ToolResult.error("NOT_FOUND", str(exc))
        if isinstance(exc, PermissionDeniedError):
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.error("VALIDATION_ERROR", str(exc))


__all__ = ["DocumentToolGroup"]
```

Match `ToolResult.ok` / `ToolResult.error` and `BaseToolGroup.dispatch` to their real signatures in `backend/mcp_server/protocol_handler.py` and `backend/mcp_server/tools/base.py` before writing — `backend/mcp_server/tools/baseline.py` is the closest working reference.

Register in `backend/mcp_server/tool_registry.py`, inside the group dict:

```python
            # Dokumentensicht spec §7: read a specification as one document,
            # not artifact by artifact. Read-only group.
            "document": DocumentToolGroup(),
```

and in `backend/mcp_server/workspace_scope.py`'s `_TOOL_TARGETS`, in the reads block:

```python
    "document.get": (("id", "document"),),
    "document.read": (("id", "document"),),
```

(`document.list` requires `workspace_id`, so the dispatcher scopes it without help. The `"document"` entity key was added to `ENTITY_SPECS` in Task 10.)

Update the `document_id` description in `backend/mcp_server/tools/baseline.py:103-107`:

```python
                    "document_id": {
                        "type": "string",
                        "description": (
                            "Document UUID -- required when scope='document'. "
                            "A root Artifact UUID is still accepted for "
                            "backwards compatibility (deprecated)."
                        ),
                    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT mcp_server/tests/test_document_tool_group.py mcp_server/tests/test_mcp_workspace_scope.py -v`
Expected: PASS (10 new tests; the workspace-scope ratchet accounts for all three new read tools)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/document.py backend/mcp_server/tool_registry.py \
        backend/mcp_server/workspace_scope.py backend/mcp_server/tools/baseline.py \
        backend/mcp_server/tests/test_document_tool_group.py
git commit -m "feat(documents): add read-only document.* MCP tool group"
```

---

## Task 15: Frontend API wrapper

**Files:**
- Create: `frontend/src/api/documents.ts`
- Test: `frontend/src/test/documentsApi.test.ts`

**Interfaces:**
- Consumes: `apiClient` from `frontend/src/api/client.ts`
- Produces:
  ```ts
  export interface DocumentSummary { id, workspace_id, title, description, created_at, section_count }
  export interface DocumentSectionDto { id, document_id, parent_section_id, title, order,
                                        content_type, query, fixed_artifact_ids, subtree_root_artifact_id }
  export interface ReadSectionDto { number, title, depth, artifact_ids, truncated, error }
  export interface ReadDocumentDto { document_id, title, markdown, sections }
  export const documentsApi: { list, get, create, update, remove,
                               listSections, createSection, updateSection,
                               deleteSection, reorderSections, read }
  ```

**Note on the export endpoint:** `apiClient.get` always calls `response.json()`, and `/documents/<id>/export/` returns `text/markdown` — so the UI download is built from `read().markdown` instead (a `Blob` + object URL). No raw-text client method is added; the `/export/` route stays for API and agent consumers. `ponytail:` skipped a text transport, add it when a second non-JSON endpoint needs one.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/documentsApi.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getAllPages: vi.fn(),
}));

import { apiClient } from '../api/client';
import { documentsApi } from '../api/documents';

describe('documentsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('list passes workspace_id as a query parameter and unwraps documents', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      documents: [{ id: 'd1', title: 'Lastenheft' }],
      count: 1,
    });
    const result = await documentsApi.list('ws-1');
    expect(apiClient.get).toHaveBeenCalledWith('/documents/?workspace_id=ws-1');
    expect(result[0].title).toBe('Lastenheft');
  });

  it('create posts workspace_id and title', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({ id: 'd1' });
    await documentsApi.create({ workspace_id: 'ws-1', title: 'D' });
    expect(apiClient.post).toHaveBeenCalledWith('/documents/', {
      workspace_id: 'ws-1',
      title: 'D',
    });
  });

  it('listSections unwraps the sections envelope', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      sections: [{ id: 's1', title: 'Scope' }],
      count: 1,
    });
    const result = await documentsApi.listSections('d1');
    expect(apiClient.get).toHaveBeenCalledWith('/documents/d1/sections/');
    expect(result[0].title).toBe('Scope');
  });

  it('reorderSections posts the id list to the reorder path', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({ sections: [] });
    await documentsApi.reorderSections('d1', ['s2', 's1']);
    expect(apiClient.post).toHaveBeenCalledWith('/documents/d1/sections/reorder/', {
      section_ids: ['s2', 's1'],
    });
  });

  it('updateSection patches the flat section path', async () => {
    (apiClient.patch as ReturnType<typeof vi.fn>).mockResolvedValue({ id: 's1' });
    await documentsApi.updateSection('s1', { title: 'New' });
    expect(apiClient.patch).toHaveBeenCalledWith('/document-sections/s1/', {
      title: 'New',
    });
  });

  it('read returns the markdown payload unchanged', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      document_id: 'd1',
      title: 'Lastenheft',
      markdown: '# Lastenheft\n',
      sections: [],
    });
    const result = await documentsApi.read('d1');
    expect(apiClient.get).toHaveBeenCalledWith('/documents/d1/read/');
    expect(result.markdown).toBe('# Lastenheft\n');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/documentsApi.test.ts`
Expected: FAIL with `Failed to resolve import "../api/documents"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/api/documents.ts`:

```ts
import { apiClient } from './client';

/** One document, as returned by the list/detail endpoints. */
export interface DocumentSummary {
  id: string;
  workspace_id: string;
  title: string;
  description: string;
  created_at: string | null;
  section_count: number;
}

/** The three content types of a section (Dokumentensicht spec §3). */
export type SectionContentType = 'query' | 'fixed' | 'subtree';

/**
 * A section's stored filter DSL payload. Byte-identical to the Tabellenansicht
 * wire format — never define a second filter shape here.
 */
export interface SectionQuery {
  item_type: string;
  filters?: Record<string, unknown>;
  sort?: Array<{ field: string; dir: 'asc' | 'desc' }>;
}

export interface DocumentSectionDto {
  id: string;
  document_id: string;
  parent_section_id: string | null;
  title: string;
  order: number;
  content_type: SectionContentType;
  query: SectionQuery | null;
  fixed_artifact_ids: string[];
  subtree_root_artifact_id: string | null;
}

export interface ReadSectionDto {
  number: string;
  title: string;
  depth: number;
  artifact_ids: string[];
  truncated: boolean;
  error: string | null;
}

export interface ReadDocumentDto {
  document_id: string;
  title: string;
  markdown: string;
  sections: ReadSectionDto[];
}

export interface DocumentCreatePayload {
  workspace_id: string;
  title: string;
  description?: string;
}

export interface SectionWritePayload {
  title?: string;
  content_type?: SectionContentType;
  parent_section_id?: string | null;
  order?: number;
  query?: SectionQuery | null;
  fixed_artifact_ids?: string[];
  subtree_root_artifact_id?: string | null;
}

export const documentsApi = {
  list: async (workspaceId: string): Promise<DocumentSummary[]> => {
    const body = await apiClient.get<{ documents: DocumentSummary[]; count: number }>(
      `/documents/?workspace_id=${workspaceId}`
    );
    return body.documents;
  },

  get: async (id: string): Promise<DocumentSummary> =>
    apiClient.get<DocumentSummary>(`/documents/${id}/`),

  create: async (payload: DocumentCreatePayload): Promise<DocumentSummary> =>
    apiClient.post<DocumentSummary>('/documents/', payload),

  update: async (
    id: string,
    payload: Partial<Pick<DocumentSummary, 'title' | 'description'>>
  ): Promise<DocumentSummary> =>
    apiClient.patch<DocumentSummary>(`/documents/${id}/`, payload),

  remove: async (id: string): Promise<void> => apiClient.delete(`/documents/${id}/`),

  listSections: async (documentId: string): Promise<DocumentSectionDto[]> => {
    const body = await apiClient.get<{
      sections: DocumentSectionDto[];
      count: number;
    }>(`/documents/${documentId}/sections/`);
    return body.sections;
  },

  createSection: async (
    documentId: string,
    payload: SectionWritePayload
  ): Promise<DocumentSectionDto> =>
    apiClient.post<DocumentSectionDto>(`/documents/${documentId}/sections/`, payload),

  updateSection: async (
    sectionId: string,
    payload: SectionWritePayload
  ): Promise<DocumentSectionDto> =>
    apiClient.patch<DocumentSectionDto>(`/document-sections/${sectionId}/`, payload),

  deleteSection: async (sectionId: string): Promise<void> =>
    apiClient.delete(`/document-sections/${sectionId}/`),

  reorderSections: async (
    documentId: string,
    sectionIds: string[]
  ): Promise<DocumentSectionDto[]> => {
    const body = await apiClient.post<{ sections: DocumentSectionDto[] }>(
      `/documents/${documentId}/sections/reorder/`,
      { section_ids: sectionIds }
    );
    return body.sections;
  },

  /**
   * Render the whole document. `query` sections are evaluated server-side on
   * every call, so two reads seconds apart may differ — that is the "lebendes
   * Dokument" contract (spec §9), not a caching bug.
   */
  read: async (id: string): Promise<ReadDocumentDto> =>
    apiClient.get<ReadDocumentDto>(`/documents/${id}/read/`),
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/documentsApi.test.ts`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/test/documentsApi.test.ts
git commit -m "feat(documents): add frontend documents api wrapper"
```

---

## Task 16: DocumentsView — list, create, delete

**Files:**
- Create: `frontend/src/components/Documents/DocumentsView.tsx`
- Create: `frontend/src/components/Documents/DocumentsView.module.css`
- Create: `frontend/src/components/Documents/index.ts`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/test/DocumentsView.test.tsx`

**Interfaces:**
- Consumes: `documentsApi`, `useWorkspace()` from `frontend/src/context`, `ConfirmDialog` from `components/shared`
- Produces: named export `DocumentsView`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/DocumentsView.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/documents', () => ({
  documentsApi: {
    list: vi.fn(),
    create: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock('../context/WorkspaceContext', () => ({
  useWorkspace: () => ({ workspaceId: 'ws-1' }),
}));

import { documentsApi } from '../api/documents';
import { DocumentsView } from '../components/Documents/DocumentsView';

const renderView = () =>
  render(
    <MemoryRouter>
      <DocumentsView />
    </MemoryRouter>
  );

describe('DocumentsView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (documentsApi.list as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: 'd1',
        workspace_id: 'ws-1',
        title: 'Lastenheft',
        description: '',
        created_at: null,
        section_count: 3,
      },
    ]);
  });

  it('lists the workspace documents', async () => {
    renderView();
    expect(await screen.findByText('Lastenheft')).toBeInTheDocument();
    expect(documentsApi.list).toHaveBeenCalledWith('ws-1');
  });

  it('shows an empty state when there are no documents', async () => {
    (documentsApi.list as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderView();
    expect(await screen.findByTestId('documents-empty-state')).toBeInTheDocument();
  });

  it('creates a document from the form', async () => {
    (documentsApi.create as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'd2',
      workspace_id: 'ws-1',
      title: 'Pflichtenheft',
      description: '',
      created_at: null,
      section_count: 0,
    });
    renderView();
    await screen.findByText('Lastenheft');
    await userEvent.type(
      screen.getByTestId('document-title-input'),
      'Pflichtenheft'
    );
    await userEvent.click(screen.getByTestId('document-create-btn'));
    await waitFor(() =>
      expect(documentsApi.create).toHaveBeenCalledWith({
        workspace_id: 'ws-1',
        title: 'Pflichtenheft',
      })
    );
  });

  it('does not create a document with a blank title', async () => {
    renderView();
    await screen.findByText('Lastenheft');
    await userEvent.click(screen.getByTestId('document-create-btn'));
    expect(documentsApi.create).not.toHaveBeenCalled();
  });

  it('deletes only after the shared confirm dialog is accepted', async () => {
    (documentsApi.remove as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    renderView();
    await screen.findByText('Lastenheft');
    await userEvent.click(screen.getByTestId('document-delete-d1'));
    expect(documentsApi.remove).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId('document-delete-confirm'));
    await waitFor(() => expect(documentsApi.remove).toHaveBeenCalledWith('d1'));
  });

  it('links to the read mode of each document', async () => {
    renderView();
    const link = await screen.findByTestId('document-read-link-d1');
    expect(link).toHaveAttribute('href', '/documents/d1/read');
  });

  it('renders an error banner when the list request fails', async () => {
    (documentsApi.list as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('boom')
    );
    renderView();
    expect(await screen.findByTestId('documents-error')).toBeInTheDocument();
  });
});
```

Adjust the `useWorkspace` mock path and the returned shape to the real context module (`frontend/src/context/`) before running.

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/DocumentsView.test.tsx`
Expected: FAIL with `Failed to resolve import "../components/Documents/DocumentsView"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/Documents/DocumentsView.module.css`:

```css
.page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.toolbar {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.input {
  flex: 1;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font: inherit;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.title {
  flex: 1;
  font-weight: var(--font-weight-medium);
}

.meta {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.empty,
.error {
  padding: var(--space-4);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
}

.error {
  border-style: solid;
  border-color: var(--color-danger);
  color: var(--color-danger);
}
```

Replace every custom property above with the actual names in `frontend/src/styles/tokens.css` — read that file first; no hex literals, no invented tokens.

Create `frontend/src/components/Documents/DocumentsView.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { documentsApi, type DocumentSummary } from '../../api/documents';
import { useWorkspace } from '../../context/WorkspaceContext';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import styles from './DocumentsView.module.css';

/**
 * Document list for the current workspace (Dokumentensicht spec §7).
 *
 * Deliberately thin: creating a document only needs a title; the section tree
 * is edited in `DocumentSectionEditor`, and reading happens in
 * `DocumentReadView`.
 */
export function DocumentsView(): JSX.Element {
  const { t } = useTranslation();
  const { workspaceId } = useWorkspace();
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<DocumentSummary | null>(null);

  const reload = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setDocuments(await documentsApi.list(workspaceId));
      setError(null);
    } catch {
      setError(t('documents.loadFailed'));
    }
  }, [workspaceId, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleCreate = async (): Promise<void> => {
    const clean = title.trim();
    if (!clean || !workspaceId) return;
    try {
      await documentsApi.create({ workspace_id: workspaceId, title: clean });
      setTitle('');
      await reload();
    } catch {
      setError(t('documents.createFailed'));
    }
  };

  const handleDelete = async (): Promise<void> => {
    if (!pendingDelete) return;
    try {
      await documentsApi.remove(pendingDelete.id);
      await reload();
    } catch {
      setError(t('documents.deleteFailed'));
    } finally {
      // Close on the success path too, not only on cancel.
      setPendingDelete(null);
    }
  };

  return (
    <div className={styles.page} data-testid="documents-view">
      <h1>{t('documents.title')}</h1>

      <div className={styles.toolbar}>
        <input
          className={styles.input}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={t('documents.newPlaceholder')}
          aria-label={t('documents.newPlaceholder')}
          data-testid="document-title-input"
        />
        <button
          type="button"
          onClick={() => void handleCreate()}
          data-testid="document-create-btn"
        >
          {t('documents.create')}
        </button>
      </div>

      {error !== null && (
        <div role="alert" className={styles.error} data-testid="documents-error">
          {error}
        </div>
      )}

      {documents.length === 0 && error === null ? (
        <p className={styles.empty} data-testid="documents-empty-state">
          {t('documents.empty')}
        </p>
      ) : (
        <ul className={styles.list} data-testid="documents-list">
          {documents.map((document) => (
            <li key={document.id} className={styles.row}>
              <span className={styles.title}>{document.title}</span>
              <span className={styles.meta}>
                {t('documents.sectionCount', { count: document.section_count })}
              </span>
              <Link
                to={`/documents/${document.id}`}
                data-testid={`document-edit-link-${document.id}`}
              >
                {t('documents.edit')}
              </Link>
              <Link
                to={`/documents/${document.id}/read`}
                data-testid={`document-read-link-${document.id}`}
              >
                {t('documents.read')}
              </Link>
              <button
                type="button"
                onClick={() => setPendingDelete(document)}
                data-testid={`document-delete-${document.id}`}
              >
                {t('actions.delete')}
              </button>
            </li>
          ))}
        </ul>
      )}

      {pendingDelete !== null && (
        <ConfirmDialog
          title={t('documents.deleteTitle')}
          message={t('documents.deleteMessage', { title: pendingDelete.title })}
          confirmTestId="document-delete-confirm"
          cancelTestId="document-delete-cancel"
          onConfirm={() => void handleDelete()}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
```

Match `ConfirmDialog`'s real prop names by reading `frontend/src/components/shared/ConfirmDialog.tsx` first — never hand-roll a confirm dialog, the shared one is the single delete seam and carries the E2E test ids.

Create `frontend/src/components/Documents/index.ts`:

```ts
export { DocumentsView } from './DocumentsView';
```

Add the `documents` namespace as a **nested object** to both locale files (`keySeparator` is `"."`, so a flat `"documents.title"` key never resolves). DE:

```json
  "documents": {
    "title": "Dokumente",
    "create": "Anlegen",
    "edit": "Bearbeiten",
    "read": "Lesemodus",
    "newPlaceholder": "Titel des neuen Dokuments",
    "empty": "Noch keine Dokumente in diesem Workspace.",
    "sectionCount": "{{count}} Abschnitte",
    "loadFailed": "Dokumente konnten nicht geladen werden.",
    "createFailed": "Dokument konnte nicht angelegt werden.",
    "deleteFailed": "Dokument konnte nicht gelöscht werden.",
    "deleteTitle": "Dokument löschen",
    "deleteMessage": "\"{{title}}\" wirklich löschen? Die referenzierten Artefakte bleiben erhalten."
  }
```

EN uses the same structure with English strings — `src/test/i18n-parity.test.ts` requires DE and EN to be structurally identical.

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/DocumentsView.test.tsx src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS (7 new tests; i18n parity green; the ratchet's `STYLE_BRACE_BASELINE` exact-equality assertion still holds because no inline `style={{` was added)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Documents/ frontend/src/i18n/locales/de.json \
        frontend/src/i18n/locales/en.json frontend/src/test/DocumentsView.test.tsx
git commit -m "feat(documents): add documents list view"
```

---

## Task 17: DocumentSectionEditor — section tree CRUD and reorder

**Files:**
- Create: `frontend/src/components/Documents/DocumentSectionEditor.tsx`
- Create: `frontend/src/components/Documents/DocumentSectionEditor.module.css`
- Modify: `frontend/src/components/Documents/index.ts`
- Modify: `frontend/src/i18n/locales/{de,en}.json` (extend the `documents` namespace)
- Test: `frontend/src/test/DocumentSectionEditor.test.tsx`

**Interfaces:**
- Consumes: `documentsApi.get/listSections/createSection/updateSection/deleteSection/reorderSections`
- Produces: named export `DocumentSectionEditor` (reads `:id` from the route via `useParams`)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/DocumentSectionEditor.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/documents', () => ({
  documentsApi: {
    get: vi.fn(),
    listSections: vi.fn(),
    createSection: vi.fn(),
    updateSection: vi.fn(),
    deleteSection: vi.fn(),
    reorderSections: vi.fn(),
  },
}));

import { documentsApi } from '../api/documents';
import { DocumentSectionEditor } from '../components/Documents/DocumentSectionEditor';

const section = (over: Partial<Record<string, unknown>> = {}) => ({
  id: 's1',
  document_id: 'd1',
  parent_section_id: null,
  title: 'Scope',
  order: 0,
  content_type: 'fixed',
  query: null,
  fixed_artifact_ids: [],
  subtree_root_artifact_id: null,
  ...over,
});

const renderEditor = () =>
  render(
    <MemoryRouter initialEntries={['/documents/d1']}>
      <Routes>
        <Route path="/documents/:id" element={<DocumentSectionEditor />} />
      </Routes>
    </MemoryRouter>
  );

describe('DocumentSectionEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (documentsApi.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'd1',
      workspace_id: 'ws-1',
      title: 'Lastenheft',
      description: '',
      created_at: null,
      section_count: 2,
    });
    (documentsApi.listSections as ReturnType<typeof vi.fn>).mockResolvedValue([
      section(),
      section({ id: 's2', title: 'Requirements', order: 1, content_type: 'query',
                query: { item_type: 'Requirement', filters: {} } }),
    ]);
  });

  it('renders the document title and its sections', async () => {
    renderEditor();
    expect(await screen.findByText('Lastenheft')).toBeInTheDocument();
    expect(screen.getByText('Scope')).toBeInTheDocument();
    expect(screen.getByText('Requirements')).toBeInTheDocument();
  });

  it('creates a fixed section', async () => {
    (documentsApi.createSection as ReturnType<typeof vi.fn>).mockResolvedValue(
      section({ id: 's3', title: 'Glossary' })
    );
    renderEditor();
    await screen.findByText('Scope');
    await userEvent.type(screen.getByTestId('section-title-input'), 'Glossary');
    await userEvent.click(screen.getByTestId('section-create-btn'));
    await waitFor(() =>
      expect(documentsApi.createSection).toHaveBeenCalledWith('d1', {
        title: 'Glossary',
        content_type: 'fixed',
      })
    );
  });

  it('sends the query payload when the content type is query', async () => {
    (documentsApi.createSection as ReturnType<typeof vi.fn>).mockResolvedValue(section());
    renderEditor();
    await screen.findByText('Scope');
    await userEvent.type(screen.getByTestId('section-title-input'), 'Functional');
    await userEvent.selectOptions(screen.getByTestId('section-type-select'), 'query');
    await userEvent.selectOptions(
      screen.getByTestId('section-item-type-select'),
      'Requirement'
    );
    await userEvent.click(screen.getByTestId('section-create-btn'));
    await waitFor(() =>
      expect(documentsApi.createSection).toHaveBeenCalledWith('d1', {
        title: 'Functional',
        content_type: 'query',
        query: { item_type: 'Requirement', filters: {} },
      })
    );
  });

  it('moving a section up reorders through the api', async () => {
    (documentsApi.reorderSections as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderEditor();
    await screen.findByText('Requirements');
    await userEvent.click(screen.getByTestId('section-move-up-s2'));
    await waitFor(() =>
      expect(documentsApi.reorderSections).toHaveBeenCalledWith('d1', ['s2', 's1'])
    );
  });

  it('the first section cannot be moved up', async () => {
    renderEditor();
    await screen.findByText('Scope');
    expect(screen.getByTestId('section-move-up-s1')).toBeDisabled();
  });

  it('deletes a section only after confirmation', async () => {
    (documentsApi.deleteSection as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    renderEditor();
    await screen.findByText('Scope');
    await userEvent.click(screen.getByTestId('section-delete-s1'));
    expect(documentsApi.deleteSection).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId('section-delete-confirm'));
    await waitFor(() => expect(documentsApi.deleteSection).toHaveBeenCalledWith('s1'));
  });

  it('shows a server validation error instead of failing silently', async () => {
    (documentsApi.createSection as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('bad')
    );
    renderEditor();
    await screen.findByText('Scope');
    await userEvent.type(screen.getByTestId('section-title-input'), 'X');
    await userEvent.click(screen.getByTestId('section-create-btn'));
    expect(await screen.findByTestId('sections-error')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/DocumentSectionEditor.test.tsx`
Expected: FAIL with `Failed to resolve import "../components/Documents/DocumentSectionEditor"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/Documents/DocumentSectionEditor.module.css` mirroring `DocumentsView.module.css` (`.page`, `.toolbar`, `.input`, `.list`, `.row`, `.error`), plus one indentation rule driven by a custom property so nesting needs no inline style:

```css
.row {
  margin-left: calc(var(--space-4) * var(--section-depth, 0));
}
```

Create `frontend/src/components/Documents/DocumentSectionEditor.tsx`. Key points, all exercised by the tests above:

* `const { id: documentId } = useParams<{ id: string }>();` — bail to `<Navigate to="/documents" replace />` when absent, mirroring `CanvasEditorWrapper`.
* State: `document`, `sections`, `title`, `contentType` (`'fixed' | 'query' | 'subtree'`), `itemType`, `error`, `pendingDelete`.
* `handleCreate` builds the payload conditionally so an unused key is never sent:
  ```tsx
  const payload: SectionWritePayload = { title: clean, content_type: contentType };
  if (contentType === 'query') {
    payload.query = { item_type: itemType, filters: {} };
  }
  await documentsApi.createSection(documentId, payload);
  ```
  `filters: {}` is an empty but valid Tabellenansicht DSL payload — column filters are added later through the same shape the table view already produces; this editor deliberately does not build a second filter UI.
* `handleMove(sectionId, delta)` swaps the id in the sibling-level list and calls `documentsApi.reorderSections(documentId, nextIds)`. Only siblings of the same `parent_section_id` participate — the backend reorders per level.
* Move-up on the first sibling and move-down on the last are rendered `disabled`.
* Depth indentation: `style` is forbidden, so pass the depth through a CSS custom property on the element's `className` set — use a data attribute plus a small set of CSS rules:
  ```css
  .row[data-depth='1'] { margin-left: var(--space-4); }
  .row[data-depth='2'] { margin-left: calc(var(--space-4) * 2); }
  .row[data-depth='3'] { margin-left: calc(var(--space-4) * 3); }
  ```
  Three levels of visual indentation is enough; deeper sections still render, just not further indented. `ponytail: fixed three-step indent ladder, generate more rules only if real documents nest deeper.`
* Every button carries `data-testid={`section-<action>-${section.id}`}`; deletion goes through the shared `ConfirmDialog` with `confirmTestId="section-delete-confirm"`.
* Errors set `error` and render `<div role="alert" data-testid="sections-error">`.

Extend the `documents` i18n namespace in both locales with `sections`, `sectionTitle`, `sectionType`, `itemType`, `addSection`, `moveUp`, `moveDown`, `deleteSectionTitle`, `deleteSectionMessage`, `sectionsFailed` — nested, DE and EN structurally identical.

Add to `frontend/src/components/Documents/index.ts`:

```ts
export { DocumentSectionEditor } from './DocumentSectionEditor';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/DocumentSectionEditor.test.tsx src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS (7 new tests; i18n parity and the inline-style ratchet stay green)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Documents/ frontend/src/i18n/locales/de.json \
        frontend/src/i18n/locales/en.json frontend/src/test/DocumentSectionEditor.test.tsx
git commit -m "feat(documents): add document section editor"
```

---

## Task 18: DocumentReadView — full-bleed read mode

**Files:**
- Create: `frontend/src/components/Documents/DocumentReadView.tsx`
- Create: `frontend/src/components/Documents/DocumentReadView.module.css`
- Modify: `frontend/src/components/Documents/index.ts`
- Modify: `frontend/src/i18n/locales/{de,en}.json`
- Test: `frontend/src/test/DocumentReadView.test.tsx`

**Interfaces:**
- Consumes: `documentsApi.read`, `react-markdown` v9 (already a dependency — no new package)
- Produces: named export `DocumentReadView`

**Security note:** `react-markdown` 9 does **not** render raw HTML unless `rehype-raw` is added. Do not add it. Artifact descriptions are user free-text, and the repo already had one SVG-attribute XSS through an unsanitised render path; the default no-raw-HTML behaviour is the mitigation here, so no `DOMPurify` pass is needed as long as `rehype-raw` stays out.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/DocumentReadView.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/documents', () => ({
  documentsApi: { read: vi.fn() },
}));

import { documentsApi } from '../api/documents';
import { DocumentReadView } from '../components/Documents/DocumentReadView';

const payload = {
  document_id: 'd1',
  title: 'Lastenheft',
  markdown: '# Lastenheft\n\n## 1 Scope\n\n### 1.1 Brake force\n\nStops the car.\n',
  sections: [
    { number: '1', title: 'Scope', depth: 0, artifact_ids: ['a1'], truncated: false, error: null },
  ],
};

const renderView = () =>
  render(
    <MemoryRouter initialEntries={['/documents/d1/read']}>
      <Routes>
        <Route path="/documents/:id/read" element={<DocumentReadView />} />
      </Routes>
    </MemoryRouter>
  );

describe('DocumentReadView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (documentsApi.read as ReturnType<typeof vi.fn>).mockResolvedValue(payload);
  });

  it('renders the markdown as headings, not as raw text', async () => {
    renderView();
    expect(
      await screen.findByRole('heading', { name: 'Lastenheft', level: 1 })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: '1 Scope', level: 2 })
    ).toBeInTheDocument();
  });

  it('renders a table of contents from the section outline', async () => {
    renderView();
    const toc = await screen.findByTestId('document-toc');
    expect(toc).toHaveTextContent('1');
    expect(toc).toHaveTextContent('Scope');
  });

  it('marks the reading surface as the print region', async () => {
    renderView();
    const surface = await screen.findByTestId('document-read-surface');
    expect(surface).toHaveAttribute('data-print-region', 'document');
  });

  it('marks the toolbar as print-hidden', async () => {
    renderView();
    const toolbar = await screen.findByTestId('document-read-toolbar');
    expect(toolbar).toHaveAttribute('data-print-hide', 'true');
  });

  it('the print button calls window.print', async () => {
    const spy = vi.fn();
    vi.stubGlobal('print', spy);
    renderView();
    await screen.findByTestId('document-read-surface');
    await userEvent.click(screen.getByTestId('document-print-btn'));
    expect(spy).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('the download button builds a markdown object url from the read payload', async () => {
    const createObjectURL = vi.fn(() => 'blob:doc');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL });
    renderView();
    await screen.findByTestId('document-read-surface');
    await userEvent.click(screen.getByTestId('document-download-btn'));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    vi.unstubAllGlobals();
  });

  it('reports a section error inline instead of hiding it', async () => {
    (documentsApi.read as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...payload,
      sections: [
        { number: '1', title: 'Broken', depth: 0, artifact_ids: [], truncated: false,
          error: "Unknown field 'gone'" },
      ],
    });
    renderView();
    expect(await screen.findByTestId('document-section-warning-1')).toHaveTextContent(
      "Unknown field 'gone'"
    );
  });

  it('shows an error banner when the read request fails', async () => {
    (documentsApi.read as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
    renderView();
    expect(await screen.findByTestId('document-read-error')).toBeInTheDocument();
  });
});
```

`jsdom` has no `Blob.text()`, so the download test asserts on `URL.createObjectURL` rather than on the blob's contents.

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/DocumentReadView.test.tsx`
Expected: FAIL with `Failed to resolve import "../components/Documents/DocumentReadView"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/Documents/DocumentReadView.module.css`:

```css
.layout {
  display: grid;
  grid-template-columns: minmax(12rem, 16rem) minmax(0, 1fr);
  gap: var(--space-6);
  align-items: start;
}

.toc {
  position: sticky;
  top: var(--space-4);
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: var(--font-size-sm);
}

.tocItem {
  padding: var(--space-1) 0;
  color: var(--color-text-muted);
}

.surface {
  max-width: 48rem;
  line-height: var(--line-height-relaxed);
  color: var(--color-text);
}

.toolbar {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.warning {
  border-left: 3px solid var(--color-warning);
  padding-left: var(--space-3);
  color: var(--color-text-muted);
}

.error {
  padding: var(--space-4);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-md);
  color: var(--color-danger);
}

@media print {
  .layout {
    display: block;
  }

  .toc {
    display: none;
  }

  .surface {
    max-width: none;
  }
}
```

Replace every custom property with the real names from `frontend/src/styles/tokens.css`.

Create `frontend/src/components/Documents/DocumentReadView.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';

import { documentsApi, type ReadDocumentDto } from '../../api/documents';
import styles from './DocumentReadView.module.css';

/**
 * Full-bleed reading surface for one document (Dokumentensicht spec §4).
 *
 * `react-markdown` renders without raw HTML by default — do NOT add
 * `rehype-raw`. Artifact descriptions are user free-text, and the no-raw-HTML
 * default is what keeps this surface safe without a second sanitiser pass.
 *
 * Print: the toolbar and the table of contents carry `data-print-hide`, and
 * the reading surface carries `data-print-region="document"`; the shell chrome
 * is hidden by the `@media print` block in `styles/global.css`.
 */
export function DocumentReadView(): JSX.Element {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [document, setDocument] = useState<ReadDocumentDto | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (documentId: string) => {
    try {
      setDocument(await documentsApi.read(documentId));
      setError(null);
    } catch {
      setError(t('documents.readFailed'));
    }
  }, [t]);

  useEffect(() => {
    if (id) void load(id);
  }, [id, load]);

  const handleDownload = (): void => {
    if (!document) return;
    const blob = new Blob([document.markdown], {
      type: 'text/markdown;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const anchor = window.document.createElement('a');
    anchor.href = url;
    anchor.download = `${document.title || 'document'}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (!id) return <Navigate to="/documents" replace />;

  if (error !== null) {
    return (
      <div role="alert" className={styles.error} data-testid="document-read-error">
        {error}
      </div>
    );
  }

  if (document === null) {
    return <div role="status">{t('loading')}</div>;
  }

  const warnings = document.sections.filter((section) => section.error !== null);

  return (
    <div className={styles.layout}>
      <nav
        className={styles.toc}
        aria-label={t('documents.tocLabel')}
        data-print-hide="true"
        data-testid="document-toc"
      >
        {document.sections.map((section) => (
          <div key={section.number} className={styles.tocItem}>
            {section.number} {section.title}
          </div>
        ))}
      </nav>

      <div>
        <div
          className={styles.toolbar}
          data-print-hide="true"
          data-testid="document-read-toolbar"
        >
          <button
            type="button"
            onClick={() => window.print()}
            data-testid="document-print-btn"
          >
            {t('documents.print')}
          </button>
          <button
            type="button"
            onClick={handleDownload}
            data-testid="document-download-btn"
          >
            {t('documents.download')}
          </button>
        </div>

        {warnings.map((section) => (
          <p
            key={section.number}
            className={styles.warning}
            data-testid={`document-section-warning-${section.number}`}
          >
            {section.number} {section.title}: {section.error}
          </p>
        ))}

        <article
          className={styles.surface}
          data-print-region="document"
          data-testid="document-read-surface"
        >
          <ReactMarkdown>{document.markdown}</ReactMarkdown>
        </article>
      </div>
    </div>
  );
}
```

Extend the `documents` i18n namespace in both locales with `print`, `download`, `tocLabel`, `readFailed`; add the export to `frontend/src/components/Documents/index.ts`.

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/DocumentReadView.test.tsx src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS (9 new tests; parity and the ratchet stay green)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Documents/ frontend/src/i18n/locales/de.json \
        frontend/src/i18n/locales/en.json frontend/src/test/DocumentReadView.test.tsx
git commit -m "feat(documents): add full-bleed document read mode"
```

---

## Task 19: Routes, sidebar entry and the global print stylesheet

**Files:**
- Modify: `frontend/src/components/NavigationShell/NavigationShell.tsx:95-104` (lazy imports), `:188-197` (routes)
- Modify: `frontend/src/components/NavigationShell/SidebarNavigation.tsx:93` (nav item), and the `<nav>` / banner elements (`data-print-hide`)
- Modify: `frontend/src/styles/global.css` (append an `@media print` block)
- Modify: `frontend/src/i18n/locales/{de,en}.json` (`nav.documents`)
- Test: `frontend/src/test/DocumentsRouting.test.tsx`

**Interfaces:**
- Consumes: `DocumentsView`, `DocumentSectionEditor`, `DocumentReadView`
- Produces: routes `/documents`, `/documents/:id`, `/documents/:id/read`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/DocumentsRouting.test.tsx`:

```tsx
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const read = (relative: string): string =>
  readFileSync(resolve(__dirname, '..', relative), 'utf8');

describe('documents routing and print chrome', () => {
  it('registers all three document routes', () => {
    const shell = read('components/NavigationShell/NavigationShell.tsx');
    expect(shell).toContain('path="/documents"');
    expect(shell).toContain('path="/documents/:id"');
    expect(shell).toContain('path="/documents/:id/read"');
  });

  it('lazy-loads the document components like every other route', () => {
    const shell = read('components/NavigationShell/NavigationShell.tsx');
    expect(shell).toMatch(/lazy\(\s*\(\)\s*=>\s*import\("\.\.\/Documents/);
  });

  it('adds a sidebar entry for documents', () => {
    const sidebar = read('components/NavigationShell/SidebarNavigation.tsx');
    expect(sidebar).toContain('"/documents"');
    expect(sidebar).toContain('nav.documents');
  });

  it('the sidebar nav is marked print-hidden', () => {
    const sidebar = read('components/NavigationShell/SidebarNavigation.tsx');
    expect(sidebar).toContain('data-print-hide');
  });

  it('global.css hides print-hidden chrome and un-pads the page', () => {
    const css = read('styles/global.css');
    expect(css).toContain('@media print');
    expect(css).toContain('[data-print-hide]');
    expect(css).toContain('[data-print-region="document"]');
  });

  it('both locales carry nav.documents', () => {
    const de = JSON.parse(read('i18n/locales/de.json'));
    const en = JSON.parse(read('i18n/locales/en.json'));
    expect(de.nav.documents).toBeTruthy();
    expect(en.nav.documents).toBeTruthy();
  });
});
```

A source-text assertion rather than a render test on purpose: `NavigationShell` mounts the auth gate, the workspace context and every lazy route, so rendering it in vitest costs far more setup than the one fact under test — that the routes are wired.

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/DocumentsRouting.test.tsx`
Expected: FAIL — `expect(shell).toContain('path="/documents"')` fails

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/components/NavigationShell/NavigationShell.tsx`, next to the other lazy imports:

```tsx
const DocumentsView = lazy(() => import("../Documents/DocumentsView"));
const DocumentSectionEditor = lazy(
  () => import("../Documents/DocumentSectionEditor")
);
const DocumentReadView = lazy(() => import("../Documents/DocumentReadView"));
```

The components are named exports, so each module needs a matching `export default` line **or** the lazy import must map it:

```tsx
const DocumentsView = lazy(() =>
  import("../Documents/DocumentsView").then((m) => ({ default: m.DocumentsView }))
);
```

Use the `.then` form — the project forbids default exports, and the other lazy routes that import a named component use the same shape (check `GlossaryView` for the local convention and follow it).

Add the routes next to `/glossary`:

```tsx
              <Route path="/documents" element={<DocumentsView />} />
              <Route path="/documents/:id" element={<DocumentSectionEditor />} />
              <Route path="/documents/:id/read" element={<DocumentReadView />} />
```

In `frontend/src/components/NavigationShell/SidebarNavigation.tsx`, add to the nav item list in the `requirements` group (documents are a requirements deliverable, next to `/glossary`):

```tsx
  { path: "/documents", labelKey: "nav.documents", feature: "dashboard", group: "requirements" },
```

`feature: "dashboard"` is the always-on feature key already used by `/goals`, `/glossary` and `/interviews` — documents are not preset-gated.

Add `data-print-hide="true"` to the `<nav aria-label={t("nav.mainNavigation")}>` element and to `BannerStack`'s outer element in `frontend/src/components/NavigationShell/NavigationShell.tsx`.

Append to `frontend/src/styles/global.css`:

```css
/* ---------------------------------------------------------------------------
 * Print (Dokumentensicht spec §4: "keinen Druck" was an explicit audit gap)
 *
 * The read mode renders inside the normal AppShell, so print-cleanliness is a
 * global concern rather than a second router shell: anything marked
 * data-print-hide disappears, and the document surface takes the full page.
 * ------------------------------------------------------------------------ */
@media print {
  [data-print-hide] {
    display: none !important;
  }

  main {
    padding: 0 !important;
    overflow: visible !important;
    height: auto !important;
  }

  [data-print-region="document"] {
    max-width: none;
    color: #000;
  }

  [data-print-region="document"] h1,
  [data-print-region="document"] h2,
  [data-print-region="document"] h3 {
    break-after: avoid;
  }

  [data-print-region="document"] a::after {
    content: " (" attr(href) ")";
    font-size: 0.85em;
  }
}
```

The `#000` literal is inside a `@media print` block in `global.css`. `HEX_LITERAL_CSS_OCCURRENCE_BASELINE` is a `toBeLessThanOrEqual` ratchet at 203 with `HEX_LITERAL_CSS_FILE_BASELINE = 1`; if `global.css` is not already the one allowed file, use the ink token from `tokens.css` instead of `#000` — check `ui-ratchet.test.ts` before choosing.

Add `"documents"` under the `nav` object in both locale files (DE: `"Dokumente"`, EN: `"Documents"`).

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/DocumentsRouting.test.tsx src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS (6 new tests; parity and all ratchets green)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/NavigationShell/ frontend/src/styles/global.css \
        frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json \
        frontend/src/test/DocumentsRouting.test.tsx
git commit -m "feat(documents): wire document routes, nav entry and print stylesheet"
```

---

## Task 20: E2E — create a document, add a section, read it

**Files:**
- Create: `e2e/document-read-mode.spec.ts`

**Interfaces:**
- Consumes: the running dev stack (`make up`), the `seed_demo` workspace, the `data-testid`s from Tasks 16-19

**Before running:** restart the frontend container. Vite has no working HMR on Windows, so Playwright silently tests stale code otherwise:

```bash
docker compose -f deploy/docker-compose.yml restart frontend
```

- [ ] **Step 1: Write the failing test**

Create `e2e/document-read-mode.spec.ts`:

```ts
import { expect, test } from '@playwright/test';

import { login } from './helpers/auth';

test.describe('Document read mode', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('creates a document, adds a section and reads it', async ({ page }) => {
    const title = `E2E Lastenheft ${Date.now()}`;

    await page.goto('/documents');
    await expect(page.getByTestId('documents-view')).toBeVisible();

    await page.getByTestId('document-title-input').fill(title);
    await page.getByTestId('document-create-btn').click();
    await expect(page.getByText(title)).toBeVisible();

    const row = page.locator('li', { hasText: title });
    await row.getByRole('link', { name: /bearbeiten|edit/i }).click();

    await page.getByTestId('section-title-input').fill('Anforderungen');
    await page.getByTestId('section-type-select').selectOption('query');
    await page.getByTestId('section-item-type-select').selectOption('Requirement');
    await page.getByTestId('section-create-btn').click();
    await expect(page.getByText('Anforderungen')).toBeVisible();

    await page.goBack();
    await row.getByTestId(/^document-read-link-/).click();

    const surface = page.getByTestId('document-read-surface');
    await expect(surface).toBeVisible();
    await expect(surface.getByRole('heading', { level: 1 })).toHaveText(title);
    // The numbering is the point of the read mode.
    await expect(surface.getByRole('heading', { level: 2 })).toContainText('1 Anforderungen');
  });

  test('the print stylesheet hides the shell chrome', async ({ page }) => {
    await page.goto('/documents');
    const first = page.getByTestId('documents-list').locator('li').first();
    await first.locator('[data-testid^="document-read-link-"]').click();
    await expect(page.getByTestId('document-read-surface')).toBeVisible();

    await page.emulateMedia({ media: 'print' });
    await expect(page.getByTestId('document-read-toolbar')).toBeHidden();
    await expect(page.getByTestId('document-toc')).toBeHidden();
    await expect(page.getByTestId('document-read-surface')).toBeVisible();
    await page.emulateMedia({ media: 'screen' });
  });
});
```

Match the `login` helper import path to the existing specs in `e2e/` (read one of them first — the helper location and signature are the local convention).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd e2e && node node_modules/@playwright/test/cli.js test document-read-mode.spec.ts`
Expected: FAIL — `/documents` is unreachable until Tasks 16-19 are deployed to the running stack.

Note: invoke the local `@playwright/test` CLI directly. A root `node_modules/playwright` at a different version makes `npx playwright` pick the wrong binary and every spec dies at `test.describe()`.

- [ ] **Step 3: Write minimal implementation**

No new production code. Restart the frontend container so it serves the Task 16-19 build, then re-run:

```bash
docker compose -f deploy/docker-compose.yml restart frontend
```

If the read-mode heading assertion fails on numbering, the cause is in `DocumentReadService._walk_children` (Task 6), not in the spec.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd e2e && node node_modules/@playwright/test/cli.js test document-read-mode.spec.ts`
Expected: PASS (2 passed)

Do **not** run the full Playwright suite here. It is expensive, CI covers it on every PR, and a full local run needs explicit user approval.

- [ ] **Step 5: Commit**

```bash
git add e2e/document-read-mode.spec.ts
git commit -m "test(documents): add e2e coverage for the document read mode"
```

---

## Final verification

- [ ] Backend, only the touched modules:
  `BT persistence/tests/test_document_models.py application/tests/ baseline/ traceability/audit/tests/ rest_api/tests/test_document_views.py rest_api/tests/test_document_read_export_views.py rest_api/tests/test_architecture.py mcp_server/tests/test_document_tool_group.py mcp_server/tests/test_mcp_workspace_scope.py -q`
- [ ] Frontend: `FT src/test/ --testTimeout=30000` — the ratchet suites walk `src/` and flake at the default 5s timeout; ~14 pre-existing local failures are expected and are green in CI (compare against `main` before blaming the branch).
- [ ] OpenAPI still generates: `docker compose ... run --rm backend-test python manage.py spectacular --file /dev/null`
- [ ] Manual smoke against the running stack, not just pytest: create a document via `POST /api/v1/documents/`, add a `query` section, `GET .../read/`, and confirm the numbering. A green unit suite has hidden guaranteed-500 REST endpoints in this repo before (str-vs-UUID pk, MagicMock fixtures).
- [ ] MCP smoke: `document.list` / `document.read` through a real `X-API-Key` request, confirming the payload survives `json.dumps`.
- [ ] Full backend suite and full Playwright suite: **CI only.** Never in the local fix loop.

---

## Self-review

**1. Spec coverage.**

| Spec section | Covered by |
|---|---|
| §3 `Document` / `DocumentSection`, three content types, `parent_section` | Tasks 1-3 |
| §4 read mode, section resolution, hierarchical numbering, `/documents/<id>/read` | Tasks 5, 6, 13, 18 |
| §4 print-optimised stylesheet | Tasks 18, 19 |
| §5 Markdown export, no new dependency | Tasks 4, 13, 18 |
| §5 DOCX explicitly out of scope | honoured (Scope decision 9) |
| §6 `Baseline.scope="document"` bound to a real `Document` | Tasks 7-10 |
| §6 `_resolve_document` extended, not replaced; snapshot/diff/`VersionReconstructor` untouched | Task 8 (one new branch, the CTE walk is byte-identical) |
| §6 migration of existing document-scope baselines | Task 11 (opt-in command; see the open question) |
| §7 REST `documents/`, `sections/`, `read/`, `export/` | Tasks 12, 13 |
| §7 MCP `document.list` / `.get` / `.read` | Task 14 |
| §8 migration steps 1-4 | Tasks 1, 9-11, 12-13, 18-19 |
| §9 risk "query sections are live" | documented in the service, the API wrapper and the read view; `MAX_SECTION_ITEMS` bounds it |
| §9 risk "recursive `parent_section` cycle" | Task 3 (`_validated_parent`, 4 tests) |
| §9 risk "migration touches production data" | Task 11 `--dry-run` |

The filter DSL is consumed 1:1 from `application/table_query_service.TableQueryService.query` (Task 5), and the generic Markdown renderer is produced in Task 4 for the MCP-Modernisierung spec to consume.

**2. Placeholder scan.** No "TBD", no "similar to Task N", no "add error handling" without code. Three places delegate a detail to the live source rather than guessing it, each naming the exact file to read first: `ConfirmDialog`'s prop names (Task 16), `ToolResult`/`BaseToolGroup`'s signatures (Task 14), and the token names in `tokens.css` (Tasks 16-18). Task 17's implementation is described as a bulleted contract rather than a full listing — every behaviour it names is pinned by one of that task's 7 tests, and the payload-building and reorder logic are given as literal code.

**3. Type consistency.** Verified end to end: `DocumentSection` (Task 1) → `ResolvedSection` (Task 5) → `ReadSection` / `ReadDocument` (Task 6) → `to_dict()` → REST body (Task 13) → `ReadDocumentDto` (Task 15) → `DocumentReadView` (Task 18). `resolve_artifact_subtree_ids` is produced in Task 7 and consumed in Task 5 — Task 5 flags the ordering and says the extraction may be pulled forward. `AuditScope.item_ids` is produced in Task 7 and consumed in Task 10. `BaselineMetadata.document_id` (Task 10) is written by `store.py` in the same task. `document_ref` and `document_id` are deliberately distinct keywords on `build`, documented at every hop.

---

## OFFENE FRAGE

**Should legacy `scope="document"` baselines be migrated automatically, or only on request?**

The spec (§6, §8.2) asks for an automatic migration: "für jede vorhandene `scope='document'`-`BaselineSnapshot`-Historie mit einer Root-`artifact_id` wird ein neues `Document` … erzeugt". Two verified facts make that impossible as written:

1. **There is no stored root `artifact_id`.** `BaselineSnapshot.artifact` (`baseline/models.py:83-89`) is declared but never written — `BaselineMetadata` has no artifact field and `BaselineStore.persist_delta_index` (`baseline/store.py:101-113`) does not set it. Every pre-existing document-scope row has `artifact_id = NULL`. A migration reading that column would find nothing; inferring the root from the frozen id set is guesswork (the subtree walk follows both `parent_id` and `derives-from`/`refines` links, so several ids can qualify).
2. **The table cannot be UPDATEd** without the trigger exception this plan introduces (Task 9).

**Decision taken so the plan is executable:** Task 11 ships `manage.py backfill_baseline_documents --tenant <uuid> [--dry-run]`, which reproduces each legacy baseline's scope *exactly* from its own `entity_type='item'` delta entries as one `fixed` section — lossless, no heuristics — and stamps `document_id` through the GUC. Nothing runs automatically; `document_id` stays `NULL` for untouched rows, and no read path (`diff`, `get`, `VersionReconstructor`) depends on it.

**What needs a decision from the product owner:**

- **(a)** Is one synthetic `Document` per legacy baseline acceptable? A workspace with 40 historical document baselines gets 40 documents named `"<baseline> (migriert)"` in its list. The alternative is to leave `document_id` `NULL` forever and treat legacy baselines as "not document-bound" — no data loss either way, only a difference in list noise.
- **(b)** Should the command instead group baselines by identical id set (one `Document` per distinct scope, several baselines pointing at it)? That is closer to the spec's word "Historie", costs one extra grouping pass, and is a five-line change to Task 11 — but it silently merges two baselines that happened to freeze the same set for unrelated reasons.

Both variants are small deltas to Task 11 only; nothing else in the plan changes. Implement Task 11 as written unless the product owner picks (b).
