# System & Workspace Banners — Design Spec

> Status: approved by user 2026-08-23. Feeds into an implementation plan via
> `superpowers:writing-plans`.

## Goal

Admins can broadcast a short, dismissible, Markdown-formatted announcement
banner at the top of the app. Two independent scopes:

- **Global banner** — set by System-Admins (`TenantRole(role=admin)`),
  visible to every user across every workspace, optionally also on the
  (unauthenticated) login page.
- **Workspace banner** — set by that workspace's Workspace-Admin
  (`UserRole(role=admin, workspace=X)`) or by any System-Admin, visible only
  to users inside that workspace.

Both scopes can be active simultaneously and stack (global on top,
workspace below). Exactly one banner record exists per scope instance
(one global row per tenant, one row per workspace) — editing overwrites,
there is no list/queue of banners.

## Non-Goals

- No scheduling (start/end dates) — enable/disable is manual only, per the
  user's explicit scope ("aktivieren und deaktivieren können").
- No banner history/audit list UI (the `updated_by`/`updated_at` fields
  exist for accountability, not for a dedicated history view).
- No per-user targeting (roles, cohorts) beyond the two scopes.
- No rich-text editor — plain Markdown textarea, matching the existing
  `MarkdownPreview` component's UX.

## Data Model

New Django app `banners` (Layer 0, alongside `admin_ops`/`audit` as a
small cross-cutting operational-config app — not part of the generic
Artifact model, since a banner is not a requirements-engineering artifact).

```python
class Banner(TenantScopedModel):
    SCOPE_GLOBAL = "global"
    SCOPE_WORKSPACE = "workspace"
    SCOPE_CHOICES = ((SCOPE_GLOBAL, "Global"), (SCOPE_WORKSPACE, "Workspace"))

    LEVEL_NEUTRAL = "neutral"
    LEVEL_INFO = "info"
    LEVEL_WARNING = "warning"
    LEVEL_CRITICAL = "critical"
    LEVEL_CHOICES = (
        (LEVEL_NEUTRAL, "Neutral"),
        (LEVEL_INFO, "Info"),
        (LEVEL_WARNING, "Warning"),
        (LEVEL_CRITICAL, "Critical"),
    )

    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES)
    workspace = models.ForeignKey(
        "persistence.Workspace", on_delete=models.CASCADE,
        null=True, blank=True, related_name="banner",
    )  # null iff scope == SCOPE_GLOBAL
    level = models.CharField(max_length=16, choices=LEVEL_CHOICES, default=LEVEL_NEUTRAL)
    message = models.TextField(blank=True)  # Markdown source
    enabled = models.BooleanField(default=False)
    dismissible = models.BooleanField(default=True)  # form default seeds False when level=critical; still user-editable
    show_on_login_page = models.BooleanField(default=False)  # ignored unless scope == SCOPE_GLOBAL
    updated_by = models.ForeignKey(
        "persistence.User", on_delete=models.SET_NULL, null=True, related_name="+",
    )

    class Meta:
        db_table = "banner"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(scope="global"),
                name="uq_banner_one_global_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["workspace"], condition=models.Q(scope="workspace"),
                name="uq_banner_one_per_workspace",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(scope="global", workspace__isnull=True)
                    | models.Q(scope="workspace", workspace__isnull=False)
                ),
                name="ck_banner_workspace_matches_scope",
            ),
        ]
```

`updated_at` comes from `TenantScopedModel`'s existing audit fields (matches
the pattern used by `AuditEntry` and other Layer-0 models) — no new field
needed.

`dismissible` default: the creation/edit form pre-fills `dismissible=False`
when the admin picks `level=critical` and `True` otherwise, but the admin
can always override either way before saving — this is UI-level
pre-filling, not a model-level conditional default (matches the user's
"modularer" requirement from brainstorming).

## Permissions

Reuses the existing RBAC primitives, no new `Operation` enum member needed:

- **Global banner read/write:** requires an active `TenantRole(role=admin)`
  row for the requesting user's tenant (same check used by the multi-user
  management System-Admin gates).
- **Workspace banner read/write:** requires either
  `UserRole(role=admin, workspace=X, suspended_at=None)` for the target
  workspace, OR an active `TenantRole(role=admin)` for the tenant
  (System-Admin can edit any workspace's banner without joining it).
- **Read (display) for both scopes:** any authenticated user in the
  tenant/workspace — banners are informational, not access-controlled
  content.
- **Login-page global banner:** unauthenticated by design (see below) —
  returns only `message`/`level`/`dismissible` for the tenant resolved from
  the request's existing tenant-resolution mechanism (subdomain/host
  header, whatever the login page already uses to know which tenant it's
  showing). Never leaks whether `enabled=False` differs from "no banner
  configured" (both return `204 No Content`) — avoids information
  disclosure about tenant configuration state to unauthenticated clients.

## Backend API (`admin_ops` app, mirrors `health_rest.py`'s adapter style)

- `GET/PUT /api/v1/admin/banners/global/` — System-Admin only
  (`HasOperationPermission`-equivalent gate checking `TenantRole`).
- `GET/PUT /api/v1/workspaces/<workspace_id>/banner/` — Workspace-Admin or
  System-Admin.
- `GET /api/v1/public/banners/login/` — unauthenticated, tenant resolved
  from request context, returns `204` if no enabled+`show_on_login_page`
  global banner exists, else `200` with `{level, message, dismissible}`.

Serializer validation: `message` runs through the same Markdown-safety path
already applied to requirement descriptions (no new sanitization logic —
reuse whatever `MarkdownPreview`'s consuming fields already validate
server-side, e.g. the same field-level HTML-stripping behavior verified by
`test_html_markup_in_title_is_rejected_not_silently_stripped`).

## Frontend Display

- New component `frontend/src/components/NavigationShell/BannerStack.tsx`,
  mounted in `NavigationShell.tsx` above the routed content, below the top
  navigation bar.
- Fetches both the global banner (already available to any authenticated
  user via a lightweight `GET`) and, when a workspace is active, that
  workspace's banner. Renders 0–2 stacked rows, global first.
- Each row: colored left-border/background per `level` (four CSS tokens —
  `--color-banner-neutral`, `-info`, `-warning`, `-critical` — added to
  `styles/tokens.css`, themed per existing theme blocks so banners stay
  legible across dark/light/bauhaus/nordic/sepia), rendered Markdown body
  via the same `react-markdown` setup as `MarkdownPreview` (no glossary
  `@Term` interpolation — that's requirement-editor-specific), and an
  `X` dismiss button shown only when `dismissible`.
- Dismiss state: `sessionStorage` key `banner-dismissed-<scope>-<id>-<updated_at>`.
  Session-scoped (not `localStorage`) so it resets on next login, per the
  user's explicit requirement; keying on `updated_at` means an admin
  editing the message content invalidates any prior dismissal automatically.
- `LoginPage.tsx` calls the public login-banner endpoint once on mount and
  renders the same row style (dismiss writes to `sessionStorage` too, same
  key shape with `scope=global-login`).

## Settings UI

- **System Settings:** new `frontend/src/components/SystemSettings/BannerSection.tsx`
  — Markdown textarea (reusing `MarkdownPreview`'s edit/preview toggle
  UI), level radio group (4 options), `enabled` / `dismissible` /
  `show_on_login_page` checkboxes, Save button. Mirrors the existing
  `EnforcementModePanel.tsx` section-in-a-tab pattern. Visible only to
  System-Admins (component-level gate matching `WorkspaceAdminSection.tsx`'s
  existing role check).
- **Workspace Settings:** new
  `frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.tsx` —
  same fields minus `show_on_login_page`. Visible to Workspace-Admins of
  that workspace and to System-Admins (mirrors `PermissionsSection.tsx`'s
  existing visibility gate pattern).

## i18n

New keys under `banners.*` in `de.json`/`en.json`: section titles, level
labels (`neutral`/`info`/`warning`/`critical`), field labels
(`enabled`/`dismissible`/`showOnLoginPage`), the dismiss button's
`aria-label`.

## Testing

- **Backend:** permission-matrix tests (System-Admin / Workspace-Admin of
  the right workspace / Workspace-Admin of a different workspace /
  non-admin member — 4×2 scopes) on both PUT endpoints; the public
  login-endpoint's tenant-resolution and `204`-vs-`200` behavior;
  uniqueness-constraint tests (second `POST`-equivalent upsert overwrites,
  never creates a second row).
- **Frontend:** `BannerStack` render tests (0/1/2 banners stacked, level
  colors, dismiss removes the row and persists across a re-render but not
  across a simulated new session), `BannerSection`/`WorkspaceBannerSection`
  visibility-gate tests (admin sees it, non-admin doesn't).
- **E2E:** one flow — System-Admin sets a global banner → visible to a
  workspace member → member dismisses it → gone on reload within the same
  session → reappears after a fresh login (new browser context in the
  Playwright test, simulating "next login").

## Open Items For The Plan (not decided here, implementer's judgment within these bounds)

- Exact REST serializer/view file layout within `admin_ops` (one file vs.
  split public/admin) — follow the existing `health_rest.py` vs. `rest.py`
  split convention in that app.
- Whether `Banner` needs its own Django app or can live inside `admin_ops`
  directly — default to inside `admin_ops` (no new app) unless the
  implementer finds a reason `admin_ops` shouldn't own a model (it
  currently has none, only REST adapters over other apps' models) — in
  that case a new minimal `banners` app is the fallback, not the default.
