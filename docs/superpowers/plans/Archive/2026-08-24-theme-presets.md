# Theme Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat 5-entry `THEMES` list with two independent axes (palette × mode), move color tokens from static CSS into a DB-backed, importable/exportable `ThemePalette` model, add a server-persisted per-user preset and a tenant-wide System-Admin-configurable default, and make the left navigation fully theme-aware.

**Architecture:** New `ThemePalette`/`UserThemePreference`/`TenantThemeDefault` models in `admin_ops` (mirrors the `Banner` feature's app placement and permission pattern). `tokens.css` keeps only structural (non-color) tokens; all `--color-*` semantic tokens move to the DB and are applied at runtime via `element.style.setProperty()`. `ThemeContext.tsx` is rebuilt around `(paletteKey, mode)` state instead of one `theme` string.

**Tech Stack:** Django 4.2+ / DRF (backend), React 18 + TypeScript (frontend), existing `AuthorizationService.is_tenant_admin` pattern (same as `GlobalBannerView`).

**Spec:** `docs/superpowers/specs/2026-08-24-theme-presets-design.md`

## Global Constraints

- `dark_tokens`/`light_tokens` on every `ThemePalette` row MUST contain exactly the canonical 71-key `--color-*` set (Task 1's `CANONICAL_COLOR_TOKEN_KEYS`) — no more, no fewer. No partial palettes.
- `is_system=True` rows are read-only at the REST layer: PATCH/DELETE always `403`, regardless of role.
- Only System-Admin (`ctx.has_role("admin") or AuthorizationService().is_tenant_admin(...)`, same check as `GlobalBannerView`/`WorkspaceBannerView` in `backend/admin_ops/banner_rest.py`) may import, delete, or set the tenant default. Any authenticated user may export (read) and set their own `UserThemePreference`.
- The 4 existing single-block palettes (`default`, `bauhaus`, `nordic`, `sepia`) must not visually change in the mode they already had — this migration moves values, it does not redesign the existing dark-mode/light-mode looks that already ship today.
- `data-testid` on every new interactive element; every new UI string needs a DE/EN pair (`i18n-parity` ratchet).
- No regression to `frontend/src/test/theme-contrast.test.ts` for any existing combination; new combinations (bauhaus/nordic/sepia's newly authored counterpart mode) must pass the same WCAG AA contrast checks that test already enforces for `default`/`light`.

---

## Task 1: `ThemePalette` model, migration, seed-data extraction

**Files:**
- Create: `backend/admin_ops/models.py` additions (`ThemePalette`)
- Create: `scripts/extract_theme_tokens.py` (one-off helper, not part of the app — generates the seed dict from today's `tokens.css`)
- Create: `backend/admin_ops/migrations/0004_theme_palette.py`
- Test: `backend/admin_ops/tests/test_theme_palette_model.py`

**Interfaces:**
- Produces: `ThemePalette(TenantScopedModel)` with `key`, `label`, `is_system`, `dark_tokens: dict`, `light_tokens: dict`, `token_keys_version`, `created_by`, `created_at`, `updated_at`; `CANONICAL_COLOR_TOKEN_KEYS: frozenset[str]` (the 71 keys below), `TOKEN_KEYS_VERSION = "v1"`.

- [ ] **Step 1: Write the failing test**

```python
# backend/admin_ops/tests/test_theme_palette_model.py
import pytest
from django.db import IntegrityError

from admin_ops.models import ThemePalette, CANONICAL_COLOR_TOKEN_KEYS
from persistence.tests.factories import active_tenant


@pytest.mark.django_db
class TestThemePaletteModel:
    def _valid_tokens(self):
        return {key: "#000000" for key in CANONICAL_COLOR_TOKEN_KEYS}

    def test_can_create_a_complete_custom_palette(self):
        with active_tenant() as tenant:
            palette = ThemePalette.objects.create(
                tenant=tenant, key="acme-brand", label="Acme Brand",
                dark_tokens=self._valid_tokens(), light_tokens=self._valid_tokens(),
                token_keys_version="v1",
            )
            assert palette.is_system is False

    def test_key_unique_per_tenant(self):
        with active_tenant() as tenant, pytest.raises(IntegrityError):
            ThemePalette.objects.create(
                tenant=tenant, key="dup", label="A",
                dark_tokens=self._valid_tokens(), light_tokens=self._valid_tokens(), token_keys_version="v1",
            )
            ThemePalette.objects.create(
                tenant=tenant, key="dup", label="B",
                dark_tokens=self._valid_tokens(), light_tokens=self._valid_tokens(), token_keys_version="v1",
            )

    def test_canonical_key_count(self):
        assert len(CANONICAL_COLOR_TOKEN_KEYS) == 71
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/admin_ops/tests/test_theme_palette_model.py -v`
Expected: FAIL — `ThemePalette` doesn't exist.

- [ ] **Step 3: Add the model**

In `backend/admin_ops/models.py`, add alongside the existing `Banner`/`BannerScope`/`BannerLevel`:

```python
CANONICAL_COLOR_TOKEN_KEYS = frozenset({
    "--color-badge-approved", "--color-badge-approved-text", "--color-badge-danger-bg",
    "--color-badge-danger-text", "--color-badge-draft", "--color-badge-draft-text",
    "--color-badge-info-bg", "--color-badge-info-text", "--color-badge-neutral-bg",
    "--color-badge-neutral-text", "--color-badge-success-bg", "--color-badge-success-text",
    "--color-badge-warning-bg", "--color-badge-warning-text", "--color-border",
    "--color-border-hover", "--color-border-subtle", "--color-card-active-bg", "--color-danger",
    "--color-danger-banner-bg", "--color-danger-dark", "--color-diagram-edge-default",
    "--color-diagram-edge-dependency", "--color-diagram-edge-primary", "--color-diff-added-bg",
    "--color-diff-added-text", "--color-diff-modified-bg", "--color-diff-modified-text",
    "--color-diff-note-bg", "--color-diff-note-text", "--color-diff-removed-bg",
    "--color-diff-removed-text", "--color-diff-unchanged-bg", "--color-diff-unchanged-text",
    "--color-errorboundary-text", "--color-focus", "--color-gradient-ai-end",
    "--color-gradient-ai-start", "--color-level-l0", "--color-level-l1", "--color-level-l3",
    "--color-level-l4", "--color-link-hover", "--color-linktype-badge-bg",
    "--color-linktype-badge-text", "--color-metric-critical", "--color-metric-healthy",
    "--color-metric-neutral", "--color-metric-warning", "--color-nav-active-bg",
    "--color-nav-badge-bg", "--color-nav-badge-text", "--color-nav-bg", "--color-nav-border",
    "--color-nav-hover-bg", "--color-nav-text", "--color-nav-text-muted", "--color-on-primary",
    "--color-primary", "--color-primary-dark", "--color-primary-rgb", "--color-reqtype-default",
    "--color-reqtype-featurereq", "--color-reqtype-syreq", "--color-reqtype-usecase",
    "--color-success", "--color-summary-failed", "--color-summary-notrun", "--color-summary-passed",
    "--color-surface", "--color-surface-raised", "--color-text", "--color-text-muted", "--color-warning",
})

TOKEN_KEYS_VERSION = "v1"


class ThemePalette(TenantScopedModel):
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=128)
    is_system = models.BooleanField(default=False)
    dark_tokens = models.JSONField()
    light_tokens = models.JSONField()
    token_keys_version = models.CharField(max_length=16, default=TOKEN_KEYS_VERSION)
    created_by = models.ForeignKey(
        "auth_tenancy.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_ops_theme_palette"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="uq_theme_palette_tenant_key"),
        ]
```

- [ ] **Step 4: Generate the seed data with the extraction script**

```python
# scripts/extract_theme_tokens.py
"""One-off helper: parses frontend/src/styles/tokens.css and prints the
dark_tokens/light_tokens dicts for the migration in Task 1, Step 5.
Not part of the shipped app -- run once, paste the output, delete or keep
for future re-extraction if tokens.css changes before the next migration.

Usage: python scripts/extract_theme_tokens.py
"""
import re
from pathlib import Path

TOKENS_CSS = Path(__file__).resolve().parent.parent / "frontend/src/styles/tokens.css"
_DECL_RE = re.compile(r"^\s*(--color-[\w-]+):\s*([^;]+);", re.MULTILINE)


def extract_block(text: str, start_marker: str, end_marker: str) -> dict:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    block = text[start:end]
    return {m.group(1): m.group(2).strip() for m in _DECL_RE.finditer(block)}


def main():
    text = TOKENS_CSS.read_text(encoding="utf-8")
    # Default dark block: the SECOND top-level `:root {` (line ~325), ends at
    # the matching `}` before `:root[data-theme="light"]`.
    default_dark = extract_block(text, "/* Colors - Premium Deep Dark/Slate Theme */", ':root[data-theme="light"]')
    default_light = extract_block(text, ':root[data-theme="light"]', ':root[data-theme="bauhaus"]')
    bauhaus = extract_block(text, ':root[data-theme="bauhaus"]', ':root[data-theme="nordic"]')
    nordic = extract_block(text, ':root[data-theme="nordic"]', ':root[data-theme="sepia"]')
    sepia_start = text.index(':root[data-theme="sepia"]')
    sepia = extract_block(text, ':root[data-theme="sepia"]', "\n}", )

    for name, tokens in [
        ("DEFAULT_DARK", default_dark), ("DEFAULT_LIGHT", default_light),
        ("BAUHAUS_EXISTING", bauhaus), ("NORDIC_EXISTING", nordic), ("SEPIA_EXISTING", sepia),
    ]:
        print(f"{name} = {tokens!r}\n")
        missing = {k.replace("_", "-") for k in []}  # placeholder for manual cross-check


if __name__ == "__main__":
    main()
```

Run: `python scripts/extract_theme_tokens.py > /tmp/theme_seed_data.txt`

Manually verify each of `DEFAULT_DARK`/`DEFAULT_LIGHT` has all 71 `CANONICAL_COLOR_TOKEN_KEYS` (the script extracts whatever is literally in the CSS block — if the two `:root { }` blocks' boundary detection above needs adjusting because the actual current file structure differs slightly, fix the markers, re-run, and re-verify against `CANONICAL_COLOR_TOKEN_KEYS` until the key sets match exactly).

`BAUHAUS_EXISTING`/`NORDIC_EXISTING`/`SEPIA_EXISTING` each only have ONE mode's values today (confirmed in the design spec's Ausgangslage) — Task 7 authors the missing counterpart for each; this task seeds only the mode that already exists for those three, leaving the other mode to be filled in by Task 7 before the migration can be finalized (see Task 7's own migration-data-update step).

- [ ] **Step 5: Write the migration**

```python
# backend/admin_ops/migrations/0004_theme_palette.py
from django.db import migrations, models
import django.db.models.deletion


def seed_system_palettes(apps, schema_editor):
    ThemePalette = apps.get_model("admin_ops", "ThemePalette")
    Tenant = apps.get_model("auth_tenancy", "Tenant")

    # DEFAULT_DARK / DEFAULT_LIGHT dicts pasted verbatim from Step 4's script
    # output -- both already complete (71/71 keys each), no placeholder values.
    DEFAULT_DARK = {}   # <- paste extract_theme_tokens.py's DEFAULT_DARK output here
    DEFAULT_LIGHT = {}  # <- paste DEFAULT_LIGHT output here
    # BAUHAUS/NORDIC/SEPIA: both modes, populated after Task 7 authors the
    # missing counterpart for each -- this migration is only finalized once
    # Task 7 has supplied all three pairs (see Task 7, Step 4).
    BAUHAUS_DARK = {}
    BAUHAUS_LIGHT = {}
    NORDIC_DARK = {}
    NORDIC_LIGHT = {}
    SEPIA_DARK = {}
    SEPIA_LIGHT = {}

    for tenant in Tenant.objects.all():
        for key, label, dark, light in [
            ("default", "Default", DEFAULT_DARK, DEFAULT_LIGHT),
            ("bauhaus", "Bauhaus", BAUHAUS_DARK, BAUHAUS_LIGHT),
            ("nordic", "Nordic", NORDIC_DARK, NORDIC_LIGHT),
            ("sepia", "Sepia", SEPIA_DARK, SEPIA_LIGHT),
        ]:
            ThemePalette.objects.create(
                tenant=tenant, key=key, label=label, is_system=True,
                dark_tokens=dark, light_tokens=light, token_keys_version="v1",
            )


def unseed_system_palettes(apps, schema_editor):
    ThemePalette = apps.get_model("admin_ops", "ThemePalette")
    ThemePalette.objects.filter(is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("admin_ops", "0003_banner_rls"),
        ("auth_tenancy", "0010_backfill_tenant_admins"),
    ]

    operations = [
        migrations.CreateModel(
            name="ThemePalette",
            fields=[
                ("id", models.UUIDField(primary_key=True, editable=False, serialize=False)),
                ("key", models.CharField(max_length=64)),
                ("label", models.CharField(max_length=128)),
                ("is_system", models.BooleanField(default=False)),
                ("dark_tokens", models.JSONField()),
                ("light_tokens", models.JSONField()),
                ("token_keys_version", models.CharField(default="v1", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="auth_tenancy.user",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, to="auth_tenancy.tenant",
                )),
            ],
            options={"db_table": "admin_ops_theme_palette"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddConstraint(
            model_name="themepalette",
            constraint=models.UniqueConstraint(fields=["tenant", "key"], name="uq_theme_palette_tenant_key"),
        ),
        migrations.RunPython(seed_system_palettes, unseed_system_palettes),
    ]
```

Note for the implementer: run `python backend/manage.py makemigrations admin_ops --name theme_palette --dry-run` first to compare against this hand-written file and reconcile any field-option drift (matches this project's established pattern from the Banner migration, which needed the same hand-verification step).

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest backend/admin_ops/tests/test_theme_palette_model.py -v`
Expected: PASS (3 tests) — once `DEFAULT_DARK`/`DEFAULT_LIGHT` are pasted in; the model-level tests don't depend on the seed migration's data being non-empty, only on the model/constraint existing.

- [ ] **Step 7: Commit**

```bash
git add backend/admin_ops/models.py backend/admin_ops/migrations/0004_theme_palette.py backend/admin_ops/tests/test_theme_palette_model.py scripts/extract_theme_tokens.py
git commit -m "feat: add ThemePalette model with 4 seeded system palettes"
```

---

## Task 2: `UserThemePreference` + `TenantThemeDefault` models

**Files:**
- Modify: `backend/admin_ops/models.py`
- Create: `backend/admin_ops/migrations/0005_theme_preference_and_default.py`
- Test: `backend/admin_ops/tests/test_theme_preference_models.py`

**Interfaces:**
- Produces: `UserThemePreference(TenantScopedModel)` (`user` OneToOne, `palette_key`, `mode`); `TenantThemeDefault(TenantScopedModel)` (`palette_key`, `mode`, one row per tenant via partial-unique constraint — same pattern as `Banner`'s global-scope uniqueness).

- [ ] **Step 1: Write the failing test**

```python
# backend/admin_ops/tests/test_theme_preference_models.py
import pytest
from django.db import IntegrityError

from admin_ops.models import UserThemePreference, TenantThemeDefault
from persistence.tests.factories import active_tenant, make_user


@pytest.mark.django_db
class TestThemePreferenceModels:
    def test_one_preference_per_user(self):
        with active_tenant() as tenant, pytest.raises(IntegrityError):
            user = make_user(tenant)
            UserThemePreference.objects.create(tenant=tenant, user=user, palette_key="default", mode="dark")
            UserThemePreference.objects.create(tenant=tenant, user=user, palette_key="bauhaus", mode="light")

    def test_one_default_per_tenant(self):
        with active_tenant() as tenant, pytest.raises(IntegrityError):
            TenantThemeDefault.objects.create(tenant=tenant, palette_key="default", mode="dark")
            TenantThemeDefault.objects.create(tenant=tenant, palette_key="nordic", mode="light")

    def test_mode_choices_restricted(self):
        with active_tenant() as tenant:
            user = make_user(tenant)
            pref = UserThemePreference(tenant=tenant, user=user, palette_key="default", mode="dark")
            pref.full_clean()  # should not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/admin_ops/tests/test_theme_preference_models.py -v`
Expected: FAIL — models don't exist.

- [ ] **Step 3: Add the models**

```python
# backend/admin_ops/models.py additions
MODE_DARK = "dark"
MODE_LIGHT = "light"
MODE_CHOICES = ((MODE_DARK, "Dark"), (MODE_LIGHT, "Light"))


class UserThemePreference(TenantScopedModel):
    user = models.OneToOneField("auth_tenancy.User", on_delete=models.CASCADE, related_name="theme_preference")
    palette_key = models.CharField(max_length=64)
    mode = models.CharField(max_length=8, choices=MODE_CHOICES)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_ops_user_theme_preference"


class TenantThemeDefault(TenantScopedModel):
    palette_key = models.CharField(max_length=64)
    mode = models.CharField(max_length=8, choices=MODE_CHOICES)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_ops_tenant_theme_default"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="uq_tenant_theme_default_one_per_tenant"),
        ]
```

- [ ] **Step 4: Write the migration**

```python
# backend/admin_ops/migrations/0005_theme_preference_and_default.py
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("admin_ops", "0004_theme_palette")]

    operations = [
        migrations.CreateModel(
            name="UserThemePreference",
            fields=[
                ("id", models.UUIDField(primary_key=True, editable=False, serialize=False)),
                ("palette_key", models.CharField(max_length=64)),
                ("mode", models.CharField(choices=[("dark", "Dark"), ("light", "Light")], max_length=8)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth_tenancy.tenant")),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE, related_name="theme_preference", to="auth_tenancy.user"
                )),
            ],
            options={"db_table": "admin_ops_user_theme_preference"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name="TenantThemeDefault",
            fields=[
                ("id", models.UUIDField(primary_key=True, editable=False, serialize=False)),
                ("palette_key", models.CharField(max_length=64)),
                ("mode", models.CharField(choices=[("dark", "Dark"), ("light", "Light")], max_length=8)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth_tenancy.tenant")),
            ],
            options={"db_table": "admin_ops_tenant_theme_default"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddConstraint(
            model_name="tenantthemedefault",
            constraint=models.UniqueConstraint(fields=["tenant"], name="uq_tenant_theme_default_one_per_tenant"),
        ),
    ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/admin_ops/tests/test_theme_preference_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/admin_ops/models.py backend/admin_ops/migrations/0005_theme_preference_and_default.py backend/admin_ops/tests/test_theme_preference_models.py
git commit -m "feat: add UserThemePreference and TenantThemeDefault models"
```

---

## Task 3: REST — `theme-palettes` CRUD + export

**Files:**
- Create: `backend/admin_ops/theme_rest.py`
- Modify: `backend/rest_api/urls.py`
- Test: `backend/admin_ops/tests/test_theme_palette_rest.py`

**Interfaces:**
- Consumes: `ThemePalette`, `CANONICAL_COLOR_TOKEN_KEYS` (Task 1); the exact permission pattern from `backend/admin_ops/banner_rest.py`'s `GlobalBannerView` (`is_tenant_admin` check).
- Produces: `GET/POST /api/v1/admin/theme-palettes/`, `GET /api/v1/admin/theme-palettes/{key}/export/`, `DELETE /api/v1/admin/theme-palettes/{key}/`.

- [ ] **Step 1: Write the failing test**

```python
# backend/admin_ops/tests/test_theme_palette_rest.py
import pytest
from rest_framework.test import APIClient

from admin_ops.models import CANONICAL_COLOR_TOKEN_KEYS, ThemePalette
from persistence.tests.factories import active_tenant, admin_user_and_token, editor_user_and_token


@pytest.mark.django_db
class TestThemePaletteRest:
    def _valid_tokens(self):
        return {key: "#000000" for key in CANONICAL_COLOR_TOKEN_KEYS}

    def test_list_includes_seeded_system_palettes(self):
        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/admin/theme-palettes/")
            assert response.status_code == 200
            keys = {p["key"] for p in response.data["results"]}
            assert {"default", "bauhaus", "nordic", "sepia"}.issubset(keys)

    def test_editor_cannot_import(self):
        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.post(
                "/api/v1/admin/theme-palettes/",
                {"label": "Custom", "dark_tokens": self._valid_tokens(), "light_tokens": self._valid_tokens()},
                format="json",
            )
            assert response.status_code == 403

    def test_admin_can_import_a_complete_palette(self):
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.post(
                "/api/v1/admin/theme-palettes/",
                {"label": "Custom", "dark_tokens": self._valid_tokens(), "light_tokens": self._valid_tokens()},
                format="json",
            )
            assert response.status_code == 201
            assert response.data["is_system"] is False

    def test_import_rejects_incomplete_token_set(self):
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            incomplete = self._valid_tokens()
            del incomplete["--color-primary"]
            response = client.post(
                "/api/v1/admin/theme-palettes/",
                {"label": "Custom", "dark_tokens": incomplete, "light_tokens": self._valid_tokens()},
                format="json",
            )
            assert response.status_code == 400
            assert "--color-primary" in str(response.data)

    def test_export_returns_full_tokens(self):
        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/admin/theme-palettes/default/export/")
            assert response.status_code == 200
            assert set(response.data["dark_tokens"].keys()) == CANONICAL_COLOR_TOKEN_KEYS

    def test_delete_system_palette_forbidden(self):
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.delete("/api/v1/admin/theme-palettes/default/")
            assert response.status_code == 403

    def test_delete_custom_palette_by_admin(self):
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            ThemePalette.objects.create(
                tenant=tenant, key="custom-x", label="X", is_system=False,
                dark_tokens=self._valid_tokens(), light_tokens=self._valid_tokens(), token_keys_version="v1",
            )
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.delete("/api/v1/admin/theme-palettes/custom-x/")
            assert response.status_code == 204
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/admin_ops/tests/test_theme_palette_rest.py -v`
Expected: FAIL — view/route don't exist.

- [ ] **Step 3: Implement**

```python
# backend/admin_ops/theme_rest.py
"""REST facade for ThemePalette. Permission pattern mirrors
backend/admin_ops/banner_rest.py's GlobalBannerView exactly (same
is_tenant_admin-or-admin-role check, same rest_api.auth_enforcer usage).
"""
from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_ops.models import CANONICAL_COLOR_TOKEN_KEYS, ThemePalette
from auth_tenancy.services.authorization import AuthorizationService
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _is_system_admin(ctx) -> bool:
    return ctx.has_role("admin") or AuthorizationService().is_tenant_admin(ctx.user_id, ctx.tenant_id)


def _validate_tokens(dark_tokens: dict, light_tokens: dict, lang: str):
    for name, tokens in [("dark_tokens", dark_tokens), ("light_tokens", light_tokens)]:
        given = set(tokens.keys())
        missing = CANONICAL_COLOR_TOKEN_KEYS - given
        extra = given - CANONICAL_COLOR_TOKEN_KEYS
        if missing or extra:
            return build_error_response(
                "VALIDATION_ERROR", lang,
                message=f"{name}: missing={sorted(missing)} extra={sorted(extra)}",
            )
    return None


class ThemePaletteListView(APIView):
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        palettes = ThemePalette.objects.all().order_by("key")
        return Response({"results": [_palette_to_dict(p) for p in palettes]})

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        if not _is_system_admin(ctx):
            return Response(build_error_response("PERMISSION_DENIED", lang), status=status.HTTP_403_FORBIDDEN)

        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)

        dark_tokens = request.data.get("dark_tokens", {})
        light_tokens = request.data.get("light_tokens", {})
        error = _validate_tokens(dark_tokens, light_tokens, lang)
        if error is not None:
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

        label = request.data.get("label", "").strip()
        if not label:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="label is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        key = request.data.get("key") or label.lower().replace(" ", "-")

        palette = ThemePalette.objects.create(
            tenant_id=ctx.tenant_id, key=key, label=label, is_system=False,
            dark_tokens=dark_tokens, light_tokens=light_tokens,
            token_keys_version="v1", created_by_id=ctx.user_id,
        )
        return Response(_palette_to_dict(palette), status=status.HTTP_201_CREATED)


class ThemePaletteDetailView(APIView):
    def delete(self, request: Request, key: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        if not _is_system_admin(ctx):
            return Response(build_error_response("PERMISSION_DENIED", lang), status=status.HTTP_403_FORBIDDEN)

        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        palette = ThemePalette.objects.filter(key=key).first()
        if palette is None:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        if palette.is_system:
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message="System themes are read-only"),
                status=status.HTTP_403_FORBIDDEN,
            )
        palette.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ThemePaletteExportView(APIView):
    def get(self, request: Request, key: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        palette = ThemePalette.objects.filter(key=key).first()
        if palette is None:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        return Response(_palette_to_dict(palette))


def _palette_to_dict(p: ThemePalette) -> dict:
    return {
        "key": p.key, "label": p.label, "is_system": p.is_system,
        "dark_tokens": p.dark_tokens, "light_tokens": p.light_tokens,
        "token_keys_version": p.token_keys_version,
    }


__all__ = ["ThemePaletteListView", "ThemePaletteDetailView", "ThemePaletteExportView"]
```

Wire in `backend/rest_api/urls.py` (alongside the existing `admin/banners/global/` entries):

```python
from admin_ops.theme_rest import ThemePaletteDetailView, ThemePaletteExportView, ThemePaletteListView

urlpatterns += [
    path("admin/theme-palettes/", ThemePaletteListView.as_view(), name="theme-palette-list"),
    path("admin/theme-palettes/<str:key>/", ThemePaletteDetailView.as_view(), name="theme-palette-detail"),
    path("admin/theme-palettes/<str:key>/export/", ThemePaletteExportView.as_view(), name="theme-palette-export"),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/admin_ops/tests/test_theme_palette_rest.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/admin_ops/theme_rest.py backend/rest_api/urls.py backend/admin_ops/tests/test_theme_palette_rest.py
git commit -m "feat: add theme-palettes REST endpoints (list, import, export, delete)"
```

---

## Task 4: REST — user preference + tenant default

**Files:**
- Modify: `backend/admin_ops/theme_rest.py`
- Modify: `backend/rest_api/urls.py`
- Test: `backend/admin_ops/tests/test_theme_preference_rest.py`

**Interfaces:**
- Consumes: `UserThemePreference`, `TenantThemeDefault` (Task 2).
- Produces: `GET/PUT /api/v1/users/me/theme-preference/`, `GET/PUT /api/v1/system/theme-default/`.

- [ ] **Step 1: Write the failing test**

```python
# backend/admin_ops/tests/test_theme_preference_rest.py
import pytest
from rest_framework.test import APIClient

from persistence.tests.factories import active_tenant, admin_user_and_token, editor_user_and_token


@pytest.mark.django_db
class TestThemePreferenceRest:
    def test_get_own_preference_defaults_to_null(self):
        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.get("/api/v1/users/me/theme-preference/")
            assert response.status_code == 200
            assert response.data["palette_key"] is None

    def test_put_own_preference(self):
        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/users/me/theme-preference/", {"palette_key": "nordic", "mode": "light"}, format="json"
            )
            assert response.status_code == 200
            assert response.data == {"palette_key": "nordic", "mode": "light"}

    def test_editor_cannot_set_tenant_default(self):
        with active_tenant() as tenant:
            user, token = editor_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/theme-default/", {"palette_key": "default", "mode": "dark"}, format="json"
            )
            assert response.status_code == 403

    def test_admin_can_set_tenant_default(self):
        with active_tenant() as tenant:
            user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.put(
                "/api/v1/system/theme-default/", {"palette_key": "bauhaus", "mode": "dark"}, format="json"
            )
            assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/admin_ops/tests/test_theme_preference_rest.py -v`
Expected: FAIL — views/routes don't exist.

- [ ] **Step 3: Implement**

```python
# backend/admin_ops/theme_rest.py additions
from admin_ops.models import TenantThemeDefault, UserThemePreference


class UserThemePreferenceView(APIView):
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        pref = UserThemePreference.objects.filter(user_id=ctx.user_id).first()
        return Response({
            "palette_key": pref.palette_key if pref else None,
            "mode": pref.mode if pref else None,
        })

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        palette_key = request.data.get("palette_key")
        mode = request.data.get("mode")
        if mode not in ("dark", "light"):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="mode must be 'dark' or 'light'"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        UserThemePreference.objects.update_or_create(
            tenant_id=ctx.tenant_id, user_id=ctx.user_id,
            defaults={"palette_key": palette_key, "mode": mode},
        )
        return Response({"palette_key": palette_key, "mode": mode})


class TenantThemeDefaultView(APIView):
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        default = TenantThemeDefault.objects.first()
        return Response({
            "palette_key": default.palette_key if default else "default",
            "mode": default.mode if default else "dark",
        })

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(build_error_response("AUTHENTICATION_REQUIRED", lang), status=status.HTTP_401_UNAUTHORIZED)
        if not _is_system_admin(ctx):
            return Response(build_error_response("PERMISSION_DENIED", lang), status=status.HTTP_403_FORBIDDEN)
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        palette_key = request.data.get("palette_key")
        mode = request.data.get("mode")
        TenantThemeDefault.objects.update_or_create(
            tenant_id=ctx.tenant_id, defaults={"palette_key": palette_key, "mode": mode}
        )
        return Response({"palette_key": palette_key, "mode": mode})
```

Wire in `backend/rest_api/urls.py`:

```python
from admin_ops.theme_rest import TenantThemeDefaultView, UserThemePreferenceView

urlpatterns += [
    path("users/me/theme-preference/", UserThemePreferenceView.as_view(), name="user-theme-preference"),
    path("system/theme-default/", TenantThemeDefaultView.as_view(), name="tenant-theme-default"),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/admin_ops/tests/test_theme_preference_rest.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/admin_ops/theme_rest.py backend/rest_api/urls.py backend/admin_ops/tests/test_theme_preference_rest.py
git commit -m "feat: add user theme-preference and tenant theme-default REST endpoints"
```

---

## Task 5: Frontend `ThemeContext.tsx` rewrite (two-axis)

**Files:**
- Modify: `frontend/src/context/ThemeContext.tsx`
- Create: `frontend/src/api/themePalettes.ts`
- Test: `frontend/src/context/ThemeContext.test.tsx` (extend existing file)

**Interfaces:**
- Consumes: `GET /api/v1/admin/theme-palettes/`, `GET/PUT /api/v1/users/me/theme-preference/`, `GET /api/v1/system/theme-default/` (Tasks 3, 4).
- Produces: `useTheme()` now returns `{ paletteKey, mode, palettes, setPreference(paletteKey, mode) }` instead of `{ theme, nextTheme, setTheme, toggleTheme }`. **Breaking change** to every consumer of `useTheme()` — Task 6 updates `WorkspaceSettings.tsx`'s existing usage, Task 8 adds the new pickers.

- [ ] **Step 1: Write the failing test**

```tsx
// Append to frontend/src/context/ThemeContext.test.tsx
import { themePalettesApi } from "../api/themePalettes";
vi.mock("../api/themePalettes");

describe("ThemeContext two-axis", () => {
  beforeEach(() => {
    (themePalettesApi.list as any).mockResolvedValue({
      results: [
        { key: "default", label: "Default", is_system: true, dark_tokens: { "--color-primary": "#111" }, light_tokens: { "--color-primary": "#eee" } },
        { key: "bauhaus", label: "Bauhaus", is_system: true, dark_tokens: { "--color-primary": "#222" }, light_tokens: { "--color-primary": "#ddd" } },
      ],
    });
    (themePalettesApi.getPreference as any).mockResolvedValue({ palette_key: "bauhaus", mode: "light" });
    (themePalettesApi.getTenantDefault as any).mockResolvedValue({ palette_key: "default", mode: "dark" });
  });

  it("resolves to the user's own preference when set", async () => {
    render(<ThemeProvider><Consumer /></ThemeProvider>);
    await waitFor(() => expect(screen.getByTestId("palette-key")).toHaveTextContent("bauhaus"));
    expect(screen.getByTestId("mode")).toHaveTextContent("light");
  });

  it("applies the resolved palette's tokens onto documentElement", async () => {
    render(<ThemeProvider><Consumer /></ThemeProvider>);
    await waitFor(() =>
      expect(document.documentElement.style.getPropertyValue("--color-primary")).toBe("#ddd")
    );
  });

  it("falls back to tenant default when no user preference is set", async () => {
    (themePalettesApi.getPreference as any).mockResolvedValue({ palette_key: null, mode: null });
    render(<ThemeProvider><Consumer /></ThemeProvider>);
    await waitFor(() => expect(screen.getByTestId("palette-key")).toHaveTextContent("default"));
    expect(screen.getByTestId("mode")).toHaveTextContent("dark");
  });

  it("setPreference updates local state immediately and calls the API", async () => {
    render(<ThemeProvider><Consumer /></ThemeProvider>);
    await waitFor(() => expect(screen.getByTestId("palette-key")).toHaveTextContent("bauhaus"));
    fireEvent.click(screen.getByTestId("set-default-dark"));
    expect(screen.getByTestId("palette-key")).toHaveTextContent("default");
    expect(themePalettesApi.setPreference).toHaveBeenCalledWith("default", "dark");
  });
});

function Consumer() {
  const { paletteKey, mode, setPreference } = useTheme();
  return (
    <div>
      <span data-testid="palette-key">{paletteKey}</span>
      <span data-testid="mode">{mode}</span>
      <button data-testid="set-default-dark" onClick={() => setPreference("default", "dark")} />
    </div>
  );
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/context/ThemeContext.test.tsx`
Expected: FAIL — `themePalettesApi` doesn't exist, `useTheme()` still returns the old shape.

- [ ] **Step 3: Implement the API client**

```typescript
// frontend/src/api/themePalettes.ts
import apiClient from "./client";

export interface ThemePalette {
  key: string;
  label: string;
  is_system: boolean;
  dark_tokens: Record<string, string>;
  light_tokens: Record<string, string>;
}

export const themePalettesApi = {
  list: (): Promise<{ results: ThemePalette[] }> => apiClient.get("/admin/theme-palettes/").then((r) => r.data),
  importPalette: (label: string, darkTokens: Record<string, string>, lightTokens: Record<string, string>) =>
    apiClient
      .post("/admin/theme-palettes/", { label, dark_tokens: darkTokens, light_tokens: lightTokens })
      .then((r) => r.data),
  exportPalette: (key: string): Promise<ThemePalette> =>
    apiClient.get(`/admin/theme-palettes/${key}/export/`).then((r) => r.data),
  deletePalette: (key: string) => apiClient.delete(`/admin/theme-palettes/${key}/`),
  getPreference: (): Promise<{ palette_key: string | null; mode: "dark" | "light" | null }> =>
    apiClient.get("/users/me/theme-preference/").then((r) => r.data),
  setPreference: (paletteKey: string, mode: "dark" | "light") =>
    apiClient.put("/users/me/theme-preference/", { palette_key: paletteKey, mode }).then((r) => r.data),
  getTenantDefault: (): Promise<{ palette_key: string; mode: "dark" | "light" }> =>
    apiClient.get("/system/theme-default/").then((r) => r.data),
  setTenantDefault: (paletteKey: string, mode: "dark" | "light") =>
    apiClient.put("/system/theme-default/", { palette_key: paletteKey, mode }).then((r) => r.data),
};
```

- [ ] **Step 4: Rewrite `ThemeContext.tsx`**

```tsx
// frontend/src/context/ThemeContext.tsx
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { themePalettesApi, type ThemePalette } from "../api/themePalettes";

const STORAGE_KEY_PALETTE = "reqflow-theme-palette";
const STORAGE_KEY_MODE = "reqflow-theme-mode";
const FALLBACK_PALETTE = "default";
const FALLBACK_MODE: "dark" | "light" = "dark";

interface ThemeContextValue {
  paletteKey: string;
  mode: "dark" | "light";
  palettes: ThemePalette[];
  setPreference: (paletteKey: string, mode: "dark" | "light") => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function applyPalette(palette: ThemePalette | undefined, mode: "dark" | "light"): void {
  if (!palette) return;
  const tokens = mode === "dark" ? palette.dark_tokens : palette.light_tokens;
  Object.entries(tokens).forEach(([key, value]) => {
    document.documentElement.style.setProperty(key, value);
  });
  document.documentElement.dataset.themeMode = mode;
}

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [palettes, setPalettes] = useState<ThemePalette[]>([]);
  const [paletteKey, setPaletteKey] = useState<string>(
    window.localStorage.getItem(STORAGE_KEY_PALETTE) || FALLBACK_PALETTE
  );
  const [mode, setMode] = useState<"dark" | "light">(
    (window.localStorage.getItem(STORAGE_KEY_MODE) as "dark" | "light" | null) || FALLBACK_MODE
  );

  useEffect(() => {
    let cancelled = false;
    Promise.all([themePalettesApi.list(), themePalettesApi.getPreference(), themePalettesApi.getTenantDefault()])
      .then(([paletteList, userPref, tenantDefault]) => {
        if (cancelled) return;
        setPalettes(paletteList.results);
        const resolvedKey = userPref.palette_key || tenantDefault.palette_key || FALLBACK_PALETTE;
        const resolvedMode = userPref.mode || tenantDefault.mode || FALLBACK_MODE;
        setPaletteKey(resolvedKey);
        setMode(resolvedMode);
      })
      .catch(() => {
        // Network failure: keep the localStorage-cached values already in state.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const palette = palettes.find((p) => p.key === paletteKey);
    applyPalette(palette, mode);
    window.localStorage.setItem(STORAGE_KEY_PALETTE, paletteKey);
    window.localStorage.setItem(STORAGE_KEY_MODE, mode);
  }, [palettes, paletteKey, mode]);

  const setPreference = useCallback((newPaletteKey: string, newMode: "dark" | "light"): void => {
    setPaletteKey(newPaletteKey);
    setMode(newMode);
    void themePalettesApi.setPreference(newPaletteKey, newMode);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ paletteKey, mode, palettes, setPreference }),
    [paletteKey, mode, palettes, setPreference]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/context/ThemeContext.test.tsx`
Expected: PASS (all existing + 4 new tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/context/ThemeContext.tsx frontend/src/api/themePalettes.ts frontend/src/context/ThemeContext.test.tsx
git commit -m "feat: rebuild ThemeContext around independent palette/mode axes"
```

---

## Task 6: Update existing `useTheme()` consumers

**Note on scope:** three files consume the old `useTheme()`/`toggleTheme`/`setTheme` API today (verified via `grep -rl "toggleTheme\|useTheme()" frontend/src`), not just `WorkspaceSettings.tsx` — all three break at TypeScript compile time the moment Task 5 ships, so all three must land together with Task 5 or the build is red in between.

**Files:**
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:29,457,465` (existing `THEMES`/`useTheme` import and picker)
- Modify: `frontend/src/components/NavigationShell/SidebarNavigation.tsx:21,142,689,691,694` (quick-access theme toggle button)
- Modify: `frontend/src/context/WorkspaceContext.tsx:47,134,206,210,362-369` (workspace-theme-seeding effect — removed, superseded by Task 5's own resolution chain)
- Test: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`, `frontend/src/components/NavigationShell/SidebarNavigation.test.tsx`, `frontend/src/context/WorkspaceContext.test.tsx` (all three extend existing files)

**Interfaces:**
- Consumes: `useTheme()`'s new shape (Task 5).

**Part A — `WorkspaceContext.tsx` (do this first, it's the riskiest one):**

Today (lines 206, 210, 362-369): `WorkspaceContext` seeds a workspace's `theme` string field into `ThemeContext` via `setTheme(nextTheme)` on first visit (`hasStoredThemePreference()` gate), a mechanism this feature supersedes (see spec's "Bewusst außerhalb dieses Scopes": `Workspace.theme` is functionally replaced, not formally removed). `setTheme` no longer exists on the new `useTheme()` return shape, so this effect must be deleted, not adapted:

- Remove the `import { useTheme, hasStoredThemePreference } from "./ThemeContext";` (line 47) — replace with nothing, this file no longer touches theme at all.
- Remove the `useState<boolean>(hasStoredThemePreference)` line (206) and its associated state variable.
- Remove the `const { setTheme } = useTheme();` line (210).
- Remove the effect block at lines 362-369 (`const nextTheme = activeWorkspace?.theme; if (!nextTheme) return; setTheme(nextTheme);`) in full.
- Leave the `theme: "dark"` default at line 134 alone if it's part of an unrelated `Workspace` shape default (verify at implementation time whether removing it breaks a type — if `Workspace.theme` is still a real backend field per the spec's "not formally removed" note, the TS type can keep it, just nothing in this file reads it anymore).

- [ ] Write a regression test in `WorkspaceContext.test.tsx` asserting that mounting `WorkspaceProvider` with an `activeWorkspace.theme` set does NOT call any theme-context setter (there is none to call — assert no console errors/warnings instead, since the old test likely asserted the seeding behavior directly and must be removed/replaced).
- [ ] Run: `cd frontend && npx vitest run src/context/WorkspaceContext.test.tsx` — Expected: PASS, no reference to `setTheme`/`hasStoredThemePreference` remains anywhere in this file or its test.

**Part B — `SidebarNavigation.tsx` quick-access toggle:**

Today (line 142): `const { nextTheme, toggleTheme } = useTheme();`, rendered as one cycling button (lines 689-694). Neither `nextTheme` nor `toggleTheme` exist on the new context value. Per the design spec ("die Kombinierbarkeit muss auch im Schnellzugriff sichtbar sein"), replace the single cycling button with a **mode-only** quick toggle (keeps the current palette, flips `dark`↔`light` — the highest-frequency action) — full palette switching stays in Settings (Task 9/Task 6 Part C), which is a rarer action and doesn't need sidebar real estate:

```tsx
// SidebarNavigation.tsx — replace the old toggleTheme button block
const { mode, paletteKey, setPreference } = useTheme();

// ... in the render, replacing the old toggleTheme button ...
<button
  data-testid="sidebar-theme-mode-toggle"
  onClick={() => setPreference(paletteKey, mode === "dark" ? "light" : "dark")}
  title={t("nav.toggleTheme")}
>
  {mode === "dark" ? t("nav.lightMode") : t("nav.darkMode")}
</button>
```

- [ ] Write a regression test in `SidebarNavigation.test.tsx` asserting `sidebar-theme-mode-toggle` flips `mode` without changing `paletteKey` (mock `useTheme` returning `{ mode: "dark", paletteKey: "bauhaus", setPreference: vi.fn() }`, click the button, assert `setPreference` was called with `("bauhaus", "light")`).
- [ ] Run: `cd frontend && npx vitest run src/components/NavigationShell/SidebarNavigation.test.tsx` — Expected: PASS.

**Part C — `WorkspaceSettings.tsx` palette+mode picker:**

- [ ] **Step 1: Write the failing test**

```tsx
// Append to frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx
it("renders a palette picker and a mode picker instead of the old single theme list", () => {
  render(<WorkspaceSettings />);
  expect(screen.getByTestId("theme-palette-picker")).toBeInTheDocument();
  expect(screen.getByTestId("theme-mode-picker")).toBeInTheDocument();
  expect(screen.queryByTestId("theme-option-dark")).not.toBeInTheDocument(); // old flat-list testid gone
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`
Expected: FAIL — old flat picker still present, new testids missing.

- [ ] **Step 3: Replace the picker**

Replace `WorkspaceSettings.tsx`'s existing `import { useTheme, THEMES } from "../../context/ThemeContext";` (line 29) and its render block (lines ~457-465, the `THEMES.map((themeDef) => ...)` list) with:

```tsx
import { useTheme } from "../../context/ThemeContext";

// ... inside the component ...
const { paletteKey, mode, palettes, setPreference } = useTheme();

// ... in the render, replacing the old THEMES.map(...) block ...
<div data-testid="theme-palette-picker">
  {palettes.map((p) => (
    <button
      key={p.key}
      data-testid={`theme-palette-option-${p.key}`}
      aria-pressed={p.key === paletteKey}
      onClick={() => setPreference(p.key, mode)}
    >
      {p.label}
    </button>
  ))}
</div>
<div data-testid="theme-mode-picker">
  <button data-testid="theme-mode-dark" aria-pressed={mode === "dark"} onClick={() => setPreference(paletteKey, "dark")}>
    {t("nav.darkMode")}
  </button>
  <button data-testid="theme-mode-light" aria-pressed={mode === "light"} onClick={() => setPreference(paletteKey, "light")}>
    {t("nav.lightMode")}
  </button>
</div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx`
Expected: PASS (all existing + 1 new test)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx frontend/src/components/WorkspaceSettings/WorkspaceSettings.test.tsx
git commit -m "feat: replace flat theme picker with independent palette/mode pickers"
```

---

## Task 7: Sidebar hardcoded-overlay fix

**Files:**
- Modify: `frontend/src/components/NavigationShell/SidebarNavigation.module.css` (lines 66, 148, 166-167, 187, 328, 463, 532)
- Test: `frontend/src/test/ui-ratchet.test.ts` (extend `HEX_LITERAL_OCCURRENCE_BASELINE`/`HEX_LITERAL_FILE_BASELINE` if this file was counted in the baseline — verify first)

**Interfaces:** none new — pure cleanup.

**Context:** `SidebarNavigation.module.css` already correctly uses `var(--color-nav-*)` for its structural colors (bg/border/text) — verified: `--color-nav-bg`, `--color-nav-border`, `--color-nav-text`, `--color-nav-text-muted`, `--color-nav-hover-bg`, `--color-nav-active-bg`, `--color-nav-badge-bg`, `--color-nav-badge-text` are all real tokens (part of `CANONICAL_COLOR_TOKEN_KEYS`, Task 1) and already consumed. The remaining gap is a handful of literal `rgba(255, 255, 255, 0.1)`/`rgba(0, 0, 0, 0.4)`-style overlay values (hover tints, shadows) at lines 66, 148, 166-167, 187, 328, 463, 532 — these assume a dark background and will look wrong (near-invisible or inverted) once the sidebar can render in a light-mode palette.

- [ ] **Step 1: Write the failing test**

```typescript
// Add to an existing or new test in frontend/src/test/
import { readFileSync } from "fs";
import { describe, it, expect } from "vitest";

describe("SidebarNavigation.module.css theme-agnostic overlays", () => {
  it("has no hardcoded white/black rgba overlay literals", () => {
    const css = readFileSync("src/components/NavigationShell/SidebarNavigation.module.css", "utf-8");
    const rgbaWhiteOrBlack = /rgba\(\s*(255,\s*255,\s*255|0,\s*0,\s*0)\s*,/g;
    const matches = css.match(rgbaWhiteOrBlack) || [];
    expect(matches).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/test/sidebar-theme-agnostic-overlays.test.ts`
Expected: FAIL — 7+ matches found.

- [ ] **Step 3: Add overlay tokens and replace the literals**

Add two new tokens to `CANONICAL_COLOR_TOKEN_KEYS` (Task 1 — if this task runs after Task 1's migration already shipped, add a follow-up migration; if run in the same plan pass before Task 1 is finalized, add these 2 keys to Task 1's list directly instead of appending here):

```
--color-nav-overlay-hover   (was: rgba(255, 255, 255, 0.1) / rgba(255, 255, 255, 0.15))
--color-nav-overlay-shadow  (was: rgba(0, 0, 0, 0.35) / rgba(0, 0, 0, 0.4))
```

In `SidebarNavigation.module.css`, replace each literal:
- Line 66 `rgba(0, 0, 0, 0.4)` → `var(--color-nav-overlay-shadow)`
- Line 166-167 `rgba(255, 255, 255, 0.1)` / `rgba(255, 255, 255, 0.2)` → `var(--color-nav-overlay-hover)` / a second new `--color-nav-overlay-hover-border` token
- Line 187, 463, 532 `rgba(0, 0, 0, 0.35)` → `var(--color-nav-overlay-shadow)`
- Line 328 `rgba(255, 255, 255, 0.15)` → `var(--color-nav-overlay-hover)`
- Line 148 `rgba(79, 110, 247, 0.2)` (focus ring, blue-tinted, not white/black) → leave as-is, this one is not a light/dark-inversion problem, it's already palette-colored; the test's regex only targets white/black overlays and correctly leaves this line alone.

Set values in the seed data (Task 1 / migration update): dark mode gets the current literal values (white-on-dark overlays), light mode gets inverted equivalents (`rgba(0, 0, 0, 0.1)`/`rgba(0, 0, 0, 0.2)` — dark-tinted overlays on a light nav background), matching the same opacity levels.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/test/sidebar-theme-agnostic-overlays.test.ts`
Expected: PASS

- [ ] **Step 5: Run the full ui-ratchet test to confirm no baseline regression**

Run: `cd frontend && npx vitest run src/test/ui-ratchet.test.ts`
Expected: PASS (hex-literal counts should DECREASE, ratchet only fails on increase)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/NavigationShell/SidebarNavigation.module.css frontend/src/test/sidebar-theme-agnostic-overlays.test.ts backend/admin_ops/models.py
git commit -m "fix: replace hardcoded sidebar overlay colors with theme-aware tokens"
```

---

## Task 8: Author bauhaus/nordic/sepia's missing counterpart mode

**Files:**
- Modify: the seed data pasted into `backend/admin_ops/migrations/0004_theme_palette.py` (Task 1, Step 5) — `BAUHAUS_LIGHT`, `NORDIC_LIGHT`, `SEPIA_LIGHT` (or the `_DARK` counterpart, whichever mode each currently lacks — confirm exact gap via `scripts/extract_theme_tokens.py`'s output before starting; the design spec's Ausgangslage states all three exist as dark-oriented blocks today, so this task authors the LIGHT counterpart for all three).
- Modify: `frontend/src/test/theme-contrast.test.ts` (add assertions for the 3 new combinations)

**Interfaces:** none new — content/data authoring, no new code interfaces.

- [ ] **Step 1: Write the failing test**

```typescript
// Add to frontend/src/test/theme-contrast.test.ts, alongside the existing default/light assertions
describe.each(["bauhaus", "nordic", "sepia"])("%s light mode contrast", (paletteKey) => {
  it("meets WCAG AA for text-on-surface", () => {
    const tokens = LIGHT_TOKENS[paletteKey]; // loaded from the same fixture the existing default/light test uses
    expect(contrastRatio(tokens["--color-text"], tokens["--color-surface"])).toBeGreaterThanOrEqual(4.5);
  });

  it("meets WCAG AA for primary-on-surface", () => {
    const tokens = LIGHT_TOKENS[paletteKey];
    expect(contrastRatio(tokens["--color-on-primary"], tokens["--color-primary"])).toBeGreaterThanOrEqual(4.5);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/test/theme-contrast.test.ts`
Expected: FAIL — `LIGHT_TOKENS["bauhaus"]` etc. don't exist yet (empty dicts from Task 1's placeholder `BAUHAUS_LIGHT = {}` etc.).

- [ ] **Step 3: Author the 3 missing token sets**

For each of `bauhaus`, `nordic`, `sepia`: design a light-mode counterpart using the SAME 71 `CANONICAL_COLOR_TOKEN_KEYS`, following that palette's existing dark-mode hue identity (e.g. bauhaus's primary-color hue, but lightened surface/background values and darkened text values for AA contrast on a light background) — the same design exercise `default`'s existing dark→light pair already demonstrates as a precedent (`tokens.css` lines 325-812, both already in the repo as a worked example of the same palette in both modes). This is genuine visual-design work, not mechanical — assign it to whichever implementer/session is equipped to make color decisions (a design-capable session, or the project's `ui-ux-designer` agent role, rather than a purely mechanical implementer).

Once authored, paste the 3 new dicts into `backend/admin_ops/migrations/0004_theme_palette.py`'s `BAUHAUS_LIGHT`/`NORDIC_LIGHT`/`SEPIA_LIGHT` placeholders (replacing the empty `{}`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/test/theme-contrast.test.ts`
Expected: PASS (all existing + 6 new tests: 3 palettes × 2 assertions)

- [ ] **Step 5: Run the backend migration test to confirm the seed data is complete**

Run: `pytest backend/admin_ops/tests/test_theme_palette_model.py -v` and re-verify manually that `BAUHAUS_LIGHT`/`NORDIC_LIGHT`/`SEPIA_LIGHT` each have all 71 keys (same check as Task 1 Step 4 for `DEFAULT_LIGHT`).

- [ ] **Step 6: Commit**

```bash
git add backend/admin_ops/migrations/0004_theme_palette.py frontend/src/test/theme-contrast.test.ts
git commit -m "feat: author light-mode counterparts for bauhaus, nordic, and sepia palettes"
```

---

## Task 9: Admin "Theme Management" settings section

**Files:**
- Create: `frontend/src/components/SystemSettings/ThemeManagementSection.tsx`
- Create: `frontend/src/components/SystemSettings/ThemeManagementSection.module.css`
- Test: `frontend/src/components/SystemSettings/ThemeManagementSection.test.tsx`

**Interfaces:**
- Consumes: `themePalettesApi` (Task 5).
- Produces: `<ThemeManagementSection />` — list, import (file upload), export (file download), set-tenant-default controls; mounted into `SystemSettings.tsx` alongside the existing `BannerSection`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/SystemSettings/ThemeManagementSection.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ThemeManagementSection } from "./ThemeManagementSection";
import { themePalettesApi } from "../../api/themePalettes";

vi.mock("../../api/themePalettes");

describe("ThemeManagementSection", () => {
  beforeEach(() => {
    (themePalettesApi.list as any).mockResolvedValue({
      results: [
        { key: "default", label: "Default", is_system: true, dark_tokens: {}, light_tokens: {} },
        { key: "custom-x", label: "Custom X", is_system: false, dark_tokens: {}, light_tokens: {} },
      ],
    });
  });

  it("shows a read-only badge for system palettes and no delete button", async () => {
    render(<ThemeManagementSection />);
    expect(await screen.findByTestId("theme-row-default")).toBeInTheDocument();
    expect(screen.getByTestId("theme-readonly-badge-default")).toBeInTheDocument();
    expect(screen.queryByTestId("theme-delete-default")).not.toBeInTheDocument();
  });

  it("shows a delete button for custom palettes", async () => {
    render(<ThemeManagementSection />);
    expect(await screen.findByTestId("theme-delete-custom-x")).toBeInTheDocument();
  });

  it("export button downloads the palette", async () => {
    (themePalettesApi.exportPalette as any).mockResolvedValue({
      key: "default", label: "Default", is_system: true, dark_tokens: {}, light_tokens: {},
    });
    render(<ThemeManagementSection />);
    fireEvent.click(await screen.findByTestId("theme-export-default"));
    await waitFor(() => expect(themePalettesApi.exportPalette).toHaveBeenCalledWith("default"));
  });

  it("import uploads a valid JSON file", async () => {
    (themePalettesApi.importPalette as any).mockResolvedValue({ key: "new-one", is_system: false });
    render(<ThemeManagementSection />);
    const file = new File(
      [JSON.stringify({ label: "New One", dark_tokens: {}, light_tokens: {} })],
      "theme.json",
      { type: "application/json" }
    );
    const input = screen.getByTestId("theme-import-input");
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(themePalettesApi.importPalette).toHaveBeenCalled());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/SystemSettings/ThemeManagementSection.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/SystemSettings/ThemeManagementSection.tsx
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { themePalettesApi, type ThemePalette } from "../../api/themePalettes";
import styles from "./ThemeManagementSection.module.css";

export function ThemeManagementSection(): JSX.Element {
  const { t } = useTranslation();
  const [palettes, setPalettes] = useState<ThemePalette[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function reload() {
    themePalettesApi.list().then((r) => setPalettes(r.results));
  }

  useEffect(reload, []);

  function handleExport(key: string) {
    themePalettesApi.exportPalette(key).then((palette) => {
      const blob = new Blob([JSON.stringify(palette, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${key}.theme.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  function handleDelete(key: string) {
    themePalettesApi.deletePalette(key).then(reload);
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const parsed = JSON.parse(text);
    await themePalettesApi.importPalette(parsed.label, parsed.dark_tokens, parsed.light_tokens);
    reload();
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <section className={styles.section}>
      <h2>{t("systemSettings.themes.heading")}</h2>
      <input
        ref={fileInputRef}
        type="file"
        accept="application/json"
        data-testid="theme-import-input"
        onChange={handleImportFile}
      />
      <ul className={styles.list}>
        {palettes.map((p) => (
          <li key={p.key} data-testid={`theme-row-${p.key}`} className={styles.row}>
            <span>{p.label}</span>
            {p.is_system && (
              <span data-testid={`theme-readonly-badge-${p.key}`} className={styles.badge}>
                {t("systemSettings.themes.readOnly")}
              </span>
            )}
            <button data-testid={`theme-export-${p.key}`} onClick={() => handleExport(p.key)}>
              {t("systemSettings.themes.export")}
            </button>
            {!p.is_system && (
              <button data-testid={`theme-delete-${p.key}`} onClick={() => handleDelete(p.key)}>
                {t("systemSettings.themes.delete")}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
```

Add i18n keys (`systemSettings.themes.heading`/`.readOnly`/`.export`/`.delete`, DE+EN) and mount `<ThemeManagementSection />` inside `SystemSettings.tsx` alongside the existing `<BannerSection />`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/SystemSettings/ThemeManagementSection.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SystemSettings/ThemeManagementSection.tsx frontend/src/components/SystemSettings/ThemeManagementSection.module.css frontend/src/components/SystemSettings/ThemeManagementSection.test.tsx frontend/src/components/SystemSettings/SystemSettings.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/de.json
git commit -m "feat: add Theme Management section to System Settings"
```

---

## Task 10: Full-suite regression check

**Files:** none (verification-only task)

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest backend/ -x -q`
Expected: PASS

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 3: `makemigrations --check`**

Run: `python backend/manage.py makemigrations --check --dry-run`
Expected: "No changes detected"

- [ ] **Step 4: Manual smoke check (per project convention — for UI changes, use the feature in a browser before reporting complete)**

Start the dev stack, log in, switch palette and mode independently in both System Settings (as admin) and the user profile picker, confirm the sidebar recolors, confirm a re-login (or hard refresh) restores the same combination from the server (not just `localStorage`) by testing from a different browser/incognito session with the same account.

- [ ] **Step 5: Commit (only if Steps 1-3 needed fixes)**

```bash
git add -A
git commit -m "fix: resolve regressions found in full-suite verification pass"
```

---

## Deliberately out of scope (v1, per spec)

- Cross-tenant theme marketplace/sharing.
- Workspace-level theme override layer (only User-Preset and Tenant-Default, per the approved design).
- In-app visual palette editor/color picker — import is JSON-file-only for v1.
- Backfilling pre-feature `localStorage` preferences into `UserThemePreference` — no server-side access to old client-only data for other devices/users.
