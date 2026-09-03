# Memory Admin UI — Phase 5: Visualisierung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This plan is self-contained** — grounded in a live read of `memory/models.py`, `application/memory_admin_service.py`, `memory/memory_rest.py`, `application/context_service.py` (cache idiom), `SystemSettings.tsx`/`MemoryManagementSection.tsx` (frontend tab + table conventions), `MismatchReviewTable.tsx` (pagination convention); no prior conversation context is required to implement it.

**Goal:** Let a System-Admin actually SEE what's in consolidated memory, not just counts. New "Visualisierung" area inside the existing System-Settings "Memory" tab, with a scope switcher ("Dieser Workspace" / "Global") and three views: a paginated, full-text-filterable **List**, a similarity-based **Cluster** grouping, and a **2D-Scatter** PCA projection of the embedding vectors.

**Architecture:** Two new read-only endpoints added to `MemoryAdminService` (extends the Phase 1 System-Admin service, same `_assert_system_admin` gate — NOT the older view-level `_is_system_admin()` helper `SystemMemorySettingsView` uses, see Ruling 3) + two new thin `APIView`s in `memory/memory_rest.py`. Backend does the numeric heavy-lifting (PCA via plain `numpy` SVD, threshold-based cosine-similarity clustering via union-find, deterministic sampling above 5000 entries, Redis-backed caching of the projection) so the frontend only ever renders pre-computed `{x, y, cluster_id}` points — no client-side linear algebra. Frontend: new tab-like sub-navigation inside the Memory system-settings tab (`MemoryVisualizationSection.tsx`), List/Cluster/Scatter as three internal views sharing one scope switcher; the scatter plot is a plain inline SVG (no new charting dependency — this codebase has ZERO chart library today, see Ruling 2).

**Tech Stack:** Django 4.2 (no migration — read-only over existing models), `numpy` (already a transitive dependency via `sentence-transformers`/`torch`, per spec — verify with `python -c "import numpy"` inside the backend container before relying on it, but do not add it to `requirements.txt` unless that import actually fails), Django's `cache` framework (already Redis-backed, `backend/reqogniloom/settings.py` `CACHES["default"]`), React 18 + TS (existing `SystemSettings.tsx` "memory" tab), plain SVG (no D3/Recharts/etc.).

**Spec:** `docs/superpowers/specs/2026-08-26-memory-admin-ui-design.md`, "Phase 5 — Visualisierung" section (lines 198-223) + "Testing (je Phase)" section's Phase-5-specific note (lines 243-246).

## Rulings (plan-vs-spec conflicts resolved before execution — do not re-litigate; if new evidence contradicts one, ledger it and escalate, don't silently reverse it)

1. **No "Tags" column.** The spec's List view mock mentions "Text-Snippet, Timestamp, Tags, Volltext-Filter" but neither `WorkspaceMemory` nor `UserTenantMemory` has a tags field or any tag-extraction pipeline (verified: `grep -n tags backend/memory/models.py` — zero hits). Building a tagging system is a separate, much larger feature, not part of "visualize what already exists." Ruling: List view shows content snippet + timestamp + confidence + owner (workspace or user) + full-text filter — no tags column, no fake/placeholder tag data.
2. **No new frontend charting dependency.** This codebase has zero existing chart library (`recharts`/`d3`/`chart.js`/`victory`/`visx`/`plotly`/`nivo` — verified via `grep` on `frontend/package.json`, zero hits). The spec is explicit about avoiding new *backend* dependencies (numpy is enough, no scikit-learn/UMAP) for the exact same resource-scarcity reason this Docker environment already runs into elsewhere (see Phase 2's cold-load bug). A 2D scatter of ≤5000 points is a solved problem in plain SVG (map x/y to `<circle cx cy>`, color by `cluster_id`) — adding a charting library for this one view is disproportionate. Ruling: render the scatter as inline SVG in `MemoryVisualizationSection.tsx`, no new `package.json` dependency.
3. **Auth gate: service-level `_assert_system_admin`, mirrors Phase 1, NOT the older view-level `_is_system_admin()` helper.** `memory/memory_rest.py`'s own module docstring already documents two competing conventions in this file: `SystemMemorySettingsView` gates in the view (predates Phase 1), while `SystemMemoryWorkspaceOverviewView`/`SystemMemoryWorkspaceDeleteView` (Phase 1) gate inside `MemoryAdminService` via `_assert_system_admin(ctx)` raising `PermissionDeniedError`, caught by the view and turned into 403. Phase 3's own Ruling 3 explicitly called the view-level helper the OLDER pattern. New work extends `MemoryAdminService`, so it inherits the newer, service-level gate — no new permission helper invented.
4. **Scope semantics.** `scope=workspace&workspace_id=<uuid>` = that workspace's own `WorkspaceMemory` rows + its CURRENT members' `UserTenantMemory` rows (exact same member-scoping already implemented in `MemoryAdminService.delete_workspace_memory`/`_member_ids` — reuse that helper, don't reinvent). `scope=global` = every `WorkspaceMemory` row and every `UserTenantMemory` row in the ACTIVE TENANT (both managers are already `TenantScopedModel`-scoped to the active tenant via RLS — "global" never crosses tenant boundaries, it just drops the workspace filter). No new "cross-tenant super-admin" concept.
5. **Superseded entries are excluded.** `superseded_by` marks a fact replaced by a newer one without deleting the historical row (see `memory/models.py` docstring). A visualization answering "what does the AI currently remember" should show live facts, not consolidation history. Ruling: both the List and Projection endpoints filter `superseded_by__isnull=True`. (If a future admin need for "show history too" emerges, that's a separate toggle, not default behavior — ledger, don't build speculatively.)
6. **Entries with no embedding (`embedding IS NULL`) appear in the List view but are excluded from Cluster/Scatter.** A row can exist before its embedding is computed (async consolidation). The List view is a raw content browser — show it there. PCA/clustering fundamentally cannot place a point with no vector — silently drop it from `projection/`'s `points`, and include `excluded_no_embedding: int` in the response so the UI can show "N entries have no embedding yet" rather than the count silently not adding up.
7. **Owner label.** Every returned entry/point carries `owner_type: "workspace" | "user"`, `owner_id`, and `owner_label` (the workspace's `name` for `WorkspaceMemory`, the user's `email` for `UserTenantMemory` — `persistence.models.User.email`, already the standard identifying field used elsewhere in this codebase's admin surfaces). No separate lookup endpoint — the admin service resolves labels inline (small N, one extra query per distinct workspace/user, not per-row N+1 — batch via `.values_list`/`in_bulk`).
8. **Clustering algorithm: threshold-based union-find on cosine similarity, matching the spec's own words exactly ("Threshold-basiert, Server-seitig vorberechnet, kein Live-Clustering im Client").** Threshold constant `CLUSTER_SIMILARITY_THRESHOLD = 0.85` (module-level constant in the new service code, not a magic number inline) — two entries land in the same cluster if their cosine similarity ≥ threshold, transitively (classic union-find over an O(n²) pairwise comparison, bounded by the ≤5000-entry sampling cap from Ruling 9, so worst case is ~12.5M comparisons of 384-dim vectors — use `numpy` vectorized cosine similarity via the normalized dot-product matrix, NOT a Python double-loop, or this will be unusably slow). `cluster_id` is an arbitrary stable integer per connected component (order of first appearance is fine — nothing downstream depends on specific ids being meaningful across requests).
9. **Sampling above 5000 entries.** Exact spec wording: "Bei sehr großen Workspaces (>5000 Einträge) wird die Projektion auf eine Stichprobe begrenzt (deterministisch, z.B. jeden n-ten Eintrag)". Ruling: order the (embedding-having, non-superseded) entries by `created_at` ascending, then `id` as a stable tiebreaker, and take every `ceil(total / 5000)`-th one until ≤5000 remain. `projection/`'s response includes `sampled: bool`, `sample_size: int`, `total_size: int` so the UI can render the "Stichprobe von N/Gesamt" notice (spec's explicit UI requirement — do not omit it).
10. **Cache key includes a watermark, mirrors `context_service.py`'s `cg:ctx:...:{watermark}` idiom exactly.** `mem:proj:{tenant_id}:{scope}:{workspace_id or 'global'}:{watermark}`, where `watermark` is a cheap aggregate over the scoped queryset (e.g. `f"{count}:{max_created_at.isoformat() if max_created_at else 'none'}"`) computed BEFORE the expensive PCA/clustering work — so a cache hit costs one `aggregate()` call, not zero queries, but avoids ever recomputing PCA for an unchanged dataset. TTL: `_CACHE_TTL_SECONDS = 300` (reuses the exact constant value already established in `context_service.py` for the same "short-lived, expensive-to-recompute" cache class).
11. **List view pagination mirrors `MismatchReviewTable.tsx`'s existing frontend convention**: `page` (1-indexed) + `page_size` query params, response carries `results`/`count`; frontend keeps local `page`/`totalPages` state, Prev/Next buttons, no new pagination component invented.

## Global Constraints

- Every new query MUST stay within the active tenant's RLS boundary — `WorkspaceMemory.objects`/`UserTenantMemory.objects`/`Workspace.objects` are already `TenantScopedModel` managers; do not bypass them with raw SQL or an unscoped manager.
- `_assert_system_admin(ctx)` (existing `MemoryAdminService` staticmethod) gates every new service method — call it first, before any query.
- The PCA/clustering computation MUST be vectorized `numpy` (matrix ops), never a Python-level nested loop over entries — Ruling 8's complexity bound only holds with vectorization.
- Cache invalidation is TTL-only (Ruling 10) — no explicit cache-bust on new memory writes; 300s staleness is an accepted tradeoff already precedented by `context_service.py`.
- Every new frontend-visible string needs a matching key in BOTH `frontend/src/i18n/locales/de.json` and `frontend/src/i18n/locales/en.json` (checked by `frontend/src/test/i18n-parity.test.ts`).
- `data-testid` on every interactive element (project convention, E2E-Pflicht).
- Backend tests run via: `docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python -m pytest <paths> -v"`. Frontend tests via: `docker exec reqogniloom-frontend-1 npx vitest run <path>`. Never run tests on the host.
- Per the spec's own Phase-5 testing note: the PCA test must assert on **cluster membership / relative structure** (e.g. "these two known-similar synthetic vectors land in the same cluster and are closer to each other than to a third, dissimilar vector"), NEVER on exact `x`/`y` coordinates — SVD's sign is not deterministic across numpy/BLAS versions, an exact-coordinate snapshot test WILL be flaky.

---

### Task 1: Backend — `MemoryAdminService` entries/projection + REST endpoints

**Files:**
- Modify: `backend/application/memory_admin_service.py` (add `list_entries`, `get_projection`, `_resolve_owner_labels` helper, `_scoped_queryset_pair` helper reusing `_member_ids`)
- Modify: `backend/memory/memory_rest.py` (add `SystemMemoryEntriesListView`, `SystemMemoryProjectionView`, add to `__all__`)
- Modify: `backend/rest_api/urls.py` (import + register both routes)
- Test: `backend/application/tests/test_memory_admin_service.py` (append — check this file's existing fixture conventions from Phase 1's tests first)
- Test: `backend/memory/tests/test_memory_rest.py` (append REST-layer tests)

**Interfaces:**
- Consumes: `memory.models.{WorkspaceMemory, UserTenantMemory}`, `persistence.models.{Workspace, User}`, `django.core.cache.cache`, `numpy`.
- Produces:
  - `MemoryAdminService.list_entries(ctx, scope, workspace_id=None, page=1, page_size=25, q=None) -> dict` (`{results, count, page, page_size}`)
  - `MemoryAdminService.get_projection(ctx, scope, workspace_id=None) -> dict` (`{points, sampled, sample_size, total_size, excluded_no_embedding}`)
  - Routes `system/memory/entries/` (GET) and `system/memory/projection/` (GET), both `permission_classes = [HasOperationPermission]`, System-Admin gated inside the service (Ruling 3).

- [ ] **Step 1: `list_entries`**

  In `memory_admin_service.py`, add a small internal helper first (used by both new methods AND, optionally, refactor `delete_workspace_memory` to reuse it later — but do NOT touch `delete_workspace_memory` in this task, out of scope):

  ```python
  def _scoped_querysets(self, scope: str, workspace_id: UUID | None) -> tuple[Any, Any]:
      """Return (WorkspaceMemory qs, UserTenantMemory qs) for *scope*, live entries only."""
      if scope == "workspace":
          if workspace_id is None:
              raise ValidationError("workspace_id is required for scope=workspace")
          member_ids = self._member_ids(workspace_id)
          ws_qs = WorkspaceMemory.objects.filter(workspace_id=workspace_id, superseded_by__isnull=True)
          user_qs = (
              UserTenantMemory.objects.filter(user_id__in=member_ids, superseded_by__isnull=True)
              if member_ids else UserTenantMemory.objects.none()
          )
      elif scope == "global":
          ws_qs = WorkspaceMemory.objects.filter(superseded_by__isnull=True)
          user_qs = UserTenantMemory.objects.filter(superseded_by__isnull=True)
      else:
          raise ValidationError(f"Unknown scope: {scope!r}")
      return ws_qs, user_qs
  ```

  Import `ValidationError` from wherever this codebase's service layer already raises validation errors for bad input (check `application/base.py` first — likely already has one alongside `NotFoundError`/`PermissionDeniedError`; use that, don't invent a new exception type).

  `list_entries`: assert admin, resolve the two querysets via `_scoped_querysets`, apply `q` as an `icontains` filter on `content` to BOTH querysets if provided, union the two into one page: since Django can't easily `UNION` across different models with different owner semantics, the simplest correct approach for a single system-admin debugging view (not a hot path) is to pull both querysets ordered by `-created_at`, tag each row with its owner metadata in Python, concatenate, sort by `created_at` descending, then slice `[(page-1)*page_size : page*page_size]` for the page and compute `count = ws_qs.count() + user_qs.count()` — acceptable because this is a System-Admin-only, infrequently-hit debugging surface, not a per-request-critical path; do not over-engineer a cross-model SQL union for it. Owner labels: batch-resolve via `Workspace.objects.filter(id__in=...).values_list("id", "name")` and `User.objects.filter(id__in=...).values_list("id", "email")` once per call (Ruling 7 — no N+1).

- [ ] **Step 2: `get_projection`**

  Assert admin, resolve scoped querysets (same helper), filter to `embedding__isnull=False` (Ruling 6 — track the excluded count separately: `excluded_no_embedding = (ws_qs.filter(embedding__isnull=True).count() + user_qs.filter(embedding__isnull=True).count())` measured on the PRE-filter querysets), compute the cache key (Ruling 10) and return the cached value if present.

  On a cache miss:
  1. Pull the combined (workspace + user) live, embedded rows, ordered by `created_at` then `id` (Ruling 9's stable order).
  2. Apply deterministic sampling if `total > 5000` (Ruling 9).
  3. Build an `(N, 384)` numpy matrix from the `VectorField` values (each row's `.embedding` — confirm at implementation time whether `pgvector.django.VectorField` already yields a numpy-compatible sequence or needs an explicit `np.array(...)` conversion; check `memory/backends.py`'s existing embedding-handling code for the established conversion idiom before writing new conversion code).
  4. PCA: center the matrix (subtract column means), SVD via `numpy.linalg.svd`, project onto the top-2 right singular vectors -> `(N, 2)` coordinates.
  5. Clustering: L2-normalize each row, compute the `(N, N)` cosine-similarity matrix via `normalized @ normalized.T`, union-find over pairs `>= CLUSTER_SIMILARITY_THRESHOLD` (Ruling 8), assign integer `cluster_id`s.
  6. Assemble `points = [{"id": ..., "x": float(x), "y": float(y), "cluster_id": c, "owner_type": ..., "owner_id": ..., "owner_label": ...} for ...]` (Ruling 7 label resolution, same batching as Step 1).
  7. `cache.set(cache_key, result, _CACHE_TTL_SECONDS)`, return `result`.

  For N=0 or N=1 (can't do a 2-point SVD meaningfully), short-circuit: 0 entries -> empty `points`; 1 entry -> single point at `(0.0, 0.0)`, `cluster_id: 0`, no SVD/clustering math needed — guard this explicitly, don't let `numpy.linalg.svd` choke on a degenerate shape.

- [ ] **Step 3: REST views + routes**

  `SystemMemoryEntriesListView`/`SystemMemoryProjectionView` in `memory/memory_rest.py`: parse `scope`/`workspace_id`/`page`/`page_size`/`q` from `request.query_params`, call the service, catch `PermissionDeniedError` -> 403, catch the validation exception from Step 1 -> 400 (`build_error_response("VALIDATION_ERROR", ...)`), return `Response(result)`. Mirror `SystemMemoryWorkspaceOverviewView`'s existing `try/except get_auth_context` 401 pattern exactly.

  Routes in `rest_api/urls.py`, added to the existing memory-routes block right after `system-memory-workspace-delete`:
  ```python
  path("system/memory/entries/", SystemMemoryEntriesListView.as_view(), name="system-memory-entries"),
  path("system/memory/projection/", SystemMemoryProjectionView.as_view(), name="system-memory-projection"),
  ```

- [ ] **Step 4: Tests**

  `test_memory_admin_service.py`: `list_entries` — scope=workspace returns only that workspace's WorkspaceMemory + current members' UserTenantMemory (not other workspaces'/members'); scope=global returns everything in-tenant; `q` filters by content substring; superseded entries excluded; pagination math correct; non-admin caller gets `PermissionDeniedError`.

  `get_projection` — **the spec-mandated deterministic test**: build a small synthetic set of embeddings (e.g. two 384-dim vectors that are near-identical + one that's orthogonal/very different — construct via `numpy`, no real ML model needed), assert the two similar ones land in the SAME `cluster_id` and the dissimilar one lands in a DIFFERENT `cluster_id` — assert nothing about exact `x`/`y` values (Global Constraint above). Also test: entries without embeddings are excluded and counted in `excluded_no_embedding`; >5000-entry sampling triggers `sampled: true` with correct `sample_size`/`total_size` (can use a smaller threshold via dependency injection/monkeypatch if 5000 real rows is impractical to seed in a test — check how existing large-N tests in this codebase handle this, e.g. `grep -rn "5000\|SAMPLE" backend/*/tests/*.py`, otherwise just directly unit-test the sampling helper function in isolation with a small N and a monkeypatched threshold constant).

  `test_memory_rest.py`: both views — 401 unauthenticated, 403 non-admin, 400 bad `scope`/missing `workspace_id`, 200 happy path shape.

---

### Task 2: Frontend — `MemoryVisualizationSection.tsx` (List + Cluster + Scatter)

**Files:**
- Create: `frontend/src/api/memory-visualization.ts`
- Create: `frontend/src/components/SystemSettings/MemoryVisualizationSection.tsx`
- Create: `frontend/src/components/SystemSettings/MemoryVisualizationSection.module.css`
- Create: `frontend/src/components/SystemSettings/MemoryVisualizationSection.test.tsx`
- Modify: `frontend/src/components/SystemSettings/SystemSettings.tsx` (mount `<MemoryVisualizationSection />` in the "memory" tab, after `<MemoryManagementSection />`)
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`

**Interfaces:**
- Consumes: `GET /api/v1/system/memory/entries/` and `GET /api/v1/system/memory/projection/` (Task 1).
- Produces: `memoryVisualizationApi.listEntries()`/`.getProjection()`, `MemoryVisualizationSection` component.

- [ ] **Step 1: `frontend/src/api/memory-visualization.ts`**

  Mirror `memoryAdmin.ts`'s existing style for this feature area. Types:
  ```typescript
  export interface MemoryEntryRow {
    id: string;
    content: string;
    created_at: string;
    confidence: number;
    owner_type: "workspace" | "user";
    owner_id: string;
    owner_label: string;
  }
  export interface MemoryEntriesPage {
    results: MemoryEntryRow[];
    count: number;
    page: number;
    page_size: number;
  }
  export interface MemoryProjectionPoint {
    id: string;
    x: number;
    y: number;
    cluster_id: number;
    owner_type: "workspace" | "user";
    owner_id: string;
    owner_label: string;
  }
  export interface MemoryProjection {
    points: MemoryProjectionPoint[];
    sampled: boolean;
    sample_size: number;
    total_size: number;
    excluded_no_embedding: number;
  }
  ```
  `listEntries(params: {scope, workspaceId?, page?, pageSize?, q?})` / `getProjection(params: {scope, workspaceId?})`, both building the query string manually (check how `MismatchReviewTable.tsx`'s API wrapper builds its query string and match that convention).

- [ ] **Step 2: `MemoryVisualizationSection.tsx` — scope switcher + 3 internal views**

  Structure (all styled via the new CSS module, NOT inline `style={{}}` — the `ui-ratchet.test.ts` baseline is frozen, see the Phase 4 CI incident that already happened once in this exact area; use CSS classes from day one):
  - Scope switcher: two buttons/radio "Dieser Workspace" (uses `activeWorkspace` from `useWorkspace()`, disabled/hidden if no active workspace) / "Global" — `data-testid="memory-viz-scope-workspace"` / `data-testid="memory-viz-scope-global"`.
  - View switcher (List / Cluster / Scatter) — `data-testid="memory-viz-view-list"` / `-cluster` / `-scatter`.
  - **List view**: table (content snippet — truncate long content client-side with an ellipsis + full text in a `title` attribute, timestamp, confidence, owner label), full-text filter input (`data-testid="memory-viz-filter-input"`, debounced or on-submit — check `MismatchReviewTable.tsx`'s filter debounce pattern and match it), Prev/Next pagination (Ruling 11).
  - **Cluster view**: group `projection` points by `cluster_id`, render as a list of collapsible groups (or a simple grouped table) showing member count + owner labels per cluster — no need for a fancy layout, this is a debugging aid, not a marketing dashboard.
  - **Scatter view**: inline `<svg>` (fixed viewBox, e.g. `0 0 600 400`), normalize `x`/`y` into the viewBox (min/max scale, computed client-side from the returned points — simple linear mapping, a few lines), one `<circle>` per point, fill color derived from `cluster_id` (a small fixed palette array, cycle with modulo — do NOT hand-pick 5000 distinct colors, a palette of ~10 cycling colors is enough for visual grouping). Show the "Stichprobe von N/Gesamt" notice (Ruling 9) when `sampled: true`, and an `excluded_no_embedding` notice when > 0 (Ruling 6).
  - Loading/error/empty states, `data-testid`s consistent with this file's own naming (`memory-viz-*`), matching the error/loading conventions already used by `MemoryManagementSection.tsx`/`MemorySection.tsx` in this same codebase (role="alert"/role="status", `t()`-wrapped strings).

- [ ] **Step 3: Wire into `SystemSettings.tsx`**

  Add `<MemoryVisualizationSection />` right after `<MemoryManagementSection />` inside the existing `"memory"` tab block (line ~170).

- [ ] **Step 4: i18n keys**

  New nested block under the EXISTING `systemSettings.memory.*` namespace (this section lives inside the same System-Settings Memory tab as `MemoryManagementSection`, unlike Phase 4's deliberately-separate `memorySelfService` — different context, follow the local convention that's already there) — e.g. `systemSettings.memory.viz.*` for scope switcher, view switcher, table headers, empty/sampled/excluded notices. Match both `de.json`/`en.json`, verified by `i18n-parity.test.ts`.

- [ ] **Step 5: `MemoryVisualizationSection.test.tsx`**

  Cover: scope switch triggers a re-fetch with the new scope; view switch (List/Cluster/Scatter) renders the right sub-view without re-fetching unnecessarily (projection and entries are separate API calls — switching List<->Cluster<->Scatter shouldn't need entries/ if only Cluster/Scatter are shown, but DOES need projection/ once, cached client-side per scope to avoid refetching on every view-tab click); List pagination Prev/Next; filter input triggers a re-fetch with `q`; sampled/excluded-no-embedding notices render when the API says so; error states.

---

### Task 3: Verification

- [ ] Backend: `docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python -m pytest application/tests/test_memory_admin_service.py memory/tests/test_memory_rest.py -v"`, then the full `memory/ application/ rest_api/` suites for regressions.
- [ ] Frontend: `docker exec reqogniloom-frontend-1 npx vitest run src/components/SystemSettings src/api/memory-visualization`, then `npx vitest run src/test/ui-ratchet.test.ts src/test/i18n-parity.test.ts` explicitly (Task 2 Step 2's CSS-module note exists precisely because this ratchet test already broke Phase 4's PR once — do not repeat that mistake here).
- [ ] Manual/browser check: as System-Admin, open System Settings -> Memory tab, confirm List/Cluster/Scatter render for both scopes with real (or seeded) data, confirm the sampled/excluded notices appear when applicable (can force this in a dev shell by seeding >5000 rows or rows with `embedding=None`, or just verify the code path via the unit tests if seeding that much data by hand is impractical).
- [ ] Whole-diff review before PR: re-check Ruling 3 (service-level admin gate, not a duplicated/weaker view-level one), Ruling 4 (scope semantics never leak cross-tenant data), Ruling 8 (clustering is vectorized numpy, not a Python double-loop that'll time out on 5000 entries), and the Global Constraint about PCA test determinism (no exact-coordinate assertions anywhere).
