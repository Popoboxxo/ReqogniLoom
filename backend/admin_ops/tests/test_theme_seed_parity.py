"""Parity between the authored DB light palettes and the frontend fixture
(Theme Presets, Task 8).

``frontend/src/test/fixtures/themePalettes.light.json`` is the single
authored source for bauhaus/nordic/sepia's light-mode token maps; the WCAG
AA contrast checks in ``frontend/src/test/theme-contrast.test.ts`` run
against it, so the DB seed must carry EXACTLY those values — any drift
between what was contrast-checked and what ships would silently void the
contrast guarantee.
"""
from __future__ import annotations

import json
from pathlib import Path

from admin_ops.models import CANONICAL_COLOR_TOKEN_KEYS
from admin_ops.theme_seed_data import BAUHAUS_LIGHT, NORDIC_LIGHT, SEPIA_LIGHT

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures/themePalettes.light.json"
)


def _fixture() -> dict[str, dict[str, str]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestAuthoredLightPalettes:
    def test_fixture_exists(self) -> None:
        assert FIXTURE.exists()

    def test_bauhaus_light_matches_fixture(self) -> None:
        assert BAUHAUS_LIGHT == _fixture()["bauhaus"]

    def test_nordic_light_matches_fixture(self) -> None:
        assert NORDIC_LIGHT == _fixture()["nordic"]

    def test_sepia_light_matches_fixture(self) -> None:
        assert SEPIA_LIGHT == _fixture()["sepia"]

    def test_all_maps_carry_exactly_the_canonical_key_set(self) -> None:
        for palette in (BAUHAUS_LIGHT, NORDIC_LIGHT, SEPIA_LIGHT):
            assert set(palette.keys()) == set(CANONICAL_COLOR_TOKEN_KEYS)
