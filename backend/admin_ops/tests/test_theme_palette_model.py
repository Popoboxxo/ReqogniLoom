"""ThemePalette model tests (Theme Presets, Task 1).

Covers:
* a complete custom palette can be created (is_system defaults to False),
* the (tenant, key) uniqueness constraint,
* the canonical 77-key --color-* token set (74 keys enumerated by the plan
  plus the 3 sidebar overlay tokens Task 7 folds into the canonical set —
  see the deviation note in the implementation plan report).
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from admin_ops.models import CANONICAL_COLOR_TOKEN_KEYS, ThemePalette

from .conftest import active_tenant


@pytest.mark.django_db
class TestThemePaletteModel:
    def _valid_tokens(self) -> dict[str, str]:
        return {key: "#000000" for key in CANONICAL_COLOR_TOKEN_KEYS}

    def test_can_create_a_complete_custom_palette(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            palette = ThemePalette.objects.create(
                tenant=tenant_a,
                key="acme-brand",
                label="Acme Brand",
                dark_tokens=self._valid_tokens(),
                light_tokens=self._valid_tokens(),
                token_keys_version="v1",
            )
            assert palette.is_system is False

    def test_key_unique_per_tenant(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            ThemePalette.unscoped.create(
                tenant=tenant_a,
                key="dup",
                label="A",
                dark_tokens=self._valid_tokens(),
                light_tokens=self._valid_tokens(),
                token_keys_version="v1",
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                ThemePalette.unscoped.create(
                    tenant=tenant_a,
                    key="dup",
                    label="B",
                    dark_tokens=self._valid_tokens(),
                    light_tokens=self._valid_tokens(),
                    token_keys_version="v1",
                )

    def test_canonical_key_count(self) -> None:
        assert len(CANONICAL_COLOR_TOKEN_KEYS) == 77
