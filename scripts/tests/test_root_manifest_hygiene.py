"""Guard: the root npm manifests must stay free of the unused ``headroom-ai`` dep (DEP-008).

``package.json``/``package-lock.json`` at the repository root are not installed by
any CI job (``npm ci`` runs only in ``frontend/`` and ``promptfoo/``). A repo-wide
search finds no code import of ``headroom-ai`` — only these two manifests and two
historic audit reports. Keeping an unused, far-behind dependency in the root lock
widens the supply-chain attack surface, so this guard keeps both files clean.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "package.json"
LOCK = REPO_ROOT / "package-lock.json"
UNUSED_DEP = "headroom-ai"
DEP_FIELDS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)


def _load(path: Path) -> dict:
    assert path.is_file(), f"missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("field", DEP_FIELDS)
def test_root_manifest_has_no_headroom_ai(field: str) -> None:
    doc = _load(MANIFEST)
    assert UNUSED_DEP not in doc.get(field, {}), (
        f"{MANIFEST.name}: '{UNUSED_DEP}' must not be declared in '{field}'"
    )


def test_root_lock_has_no_headroom_ai_package() -> None:
    packages = _load(LOCK).get("packages", {})
    assert f"node_modules/{UNUSED_DEP}" not in packages, (
        f"{LOCK.name}: resolved package '{UNUSED_DEP}' must be removed"
    )
    assert UNUSED_DEP not in packages.get("", {}).get("dependencies", {}), (
        f"{LOCK.name}: root dependency '{UNUSED_DEP}' must be removed"
    )


@pytest.mark.parametrize("path", (MANIFEST, LOCK))
def test_root_manifests_have_no_headroom_ai_text(path: Path) -> None:
    assert UNUSED_DEP not in path.read_text(encoding="utf-8"), (
        f"{path.name}: stale '{UNUSED_DEP}' reference"
    )
