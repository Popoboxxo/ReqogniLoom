"""
admin_ops — ThemeService (Theme Presets).

Stateless service owning the stock system-palette lifecycle:

* :meth:`ThemeService.ensure_system_palettes` — idempotently backfills the
  four shipped palettes for a tenant.

Why the lazy backfill exists: migration ``0004_theme_palette`` seeds only
tenants that exist *at migrate time*. Any tenant created afterwards (admin
UI, seeding scripts, tests) would otherwise see an empty palette list until
someone re-ran a data migration. The REST list/export views therefore call
this method before reading, making "every tenant always has the four stock
palettes" an invariant maintained on read instead of a one-shot migration
side effect. ``get_or_create`` keeps it O(1) after the first call and
never touches rows that already exist (system palettes are read-only at
the REST layer, so there is nothing to clobber).
"""
from __future__ import annotations

from uuid import UUID

from admin_ops.models import ThemePalette
from admin_ops.theme_seed_data import (
    BAUHAUS_DARK,
    BAUHAUS_LIGHT,
    DEFAULT_DARK,
    DEFAULT_LIGHT,
    NORDIC_DARK,
    NORDIC_LIGHT,
    SEPIA_DARK,
    SEPIA_LIGHT,
)


class ThemeService:
    """Stock-palette lifecycle for the Theme Presets feature."""

    _SEED_TOKENS = {
        "default": ("Default", DEFAULT_DARK, DEFAULT_LIGHT),
        "bauhaus": ("Bauhaus", BAUHAUS_DARK, BAUHAUS_LIGHT),
        "nordic": ("Nordic", NORDIC_DARK, NORDIC_LIGHT),
        "sepia": ("Sepia", SEPIA_DARK, SEPIA_LIGHT),
    }

    def ensure_system_palettes(self, tenant_id: UUID) -> None:
        """Create any missing stock palette rows for *tenant_id*. Idempotent."""
        for key, (label, dark, light) in self._SEED_TOKENS.items():
            ThemePalette.unscoped.get_or_create(
                tenant_id=tenant_id,
                key=key,
                defaults={
                    "label": label,
                    "is_system": True,
                    "dark_tokens": dark,
                    "light_tokens": light,
                    "token_keys_version": "v1",
                },
            )
