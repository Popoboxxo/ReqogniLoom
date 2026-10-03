"""Tests for the Hermes plugin builder.

This is the only one of the five dist/ builders without a sibling test, so a
VERSION bump could leave integrations/hermes-plugin/reqogniloom/{package.json,
hermes-plugin.json} on the previous version with nothing noticing. The
builder mutates those two files in place rather than rendering a tree from
templates, so every test here runs against a tmp_path copy: pointing the
builder at the committed tree would rewrite the working tree from inside the
test suite.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent.parent
PLUGIN_ROOT = REPO_ROOT / "integrations" / "hermes-plugin" / "reqogniloom"
MANIFEST_FILES = ["package.json", "hermes-plugin.json"]
STALE_VERSION = "0.0.0-stale"


@pytest.fixture
def plugin_root(tmp_path):
    """Copy the committed manifests into tmp_path for the builder to mutate."""
    dst = tmp_path / "reqogniloom"
    dst.mkdir()
    for name in MANIFEST_FILES:
        shutil.copy2(PLUGIN_ROOT / name, dst / name)
    return dst


def run_builder(plugin_root: Path) -> None:
    """Run the builder as the standalone script the release process invokes."""
    result = subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_hermes_plugin.py"),
         "--plugin-root", str(plugin_root)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr


def repo_version() -> str:
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_build_hermes_plugin_rewrites_a_stale_version(plugin_root):
    """The drift this builder exists to prevent. The stale version is seeded
    explicitly because the committed tree is currently in sync with VERSION and
    would pass even if the builder did nothing at all."""
    for name in MANIFEST_FILES:
        path = plugin_root / name
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = STALE_VERSION
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    run_builder(plugin_root)

    for name in MANIFEST_FILES:
        rewritten = json.loads(
            (plugin_root / name).read_text(encoding="utf-8")
        )
        assert rewritten["version"] == repo_version(), (
            f"{name} was not resynced to repo VERSION"
        )


def test_build_hermes_plugin_sets_version_in_both_manifests(plugin_root):
    run_builder(plugin_root)

    for name in MANIFEST_FILES:
        assert json.loads(
            (plugin_root / name).read_text(encoding="utf-8")
        )["version"] == repo_version(), (
            f"{name} must carry the repo VERSION, not the plugin's own literal"
        )


def test_build_hermes_plugin_preserves_every_other_key(plugin_root):
    """The builder may only touch `version`; every other key in both files must
    round-trip unchanged, whatever those keys happen to be at the time."""
    run_builder(plugin_root)

    for name in MANIFEST_FILES:
        before = json.loads((PLUGIN_ROOT / name).read_text(encoding="utf-8"))
        after = json.loads((plugin_root / name).read_text(encoding="utf-8"))
        assert {k: v for k, v in after.items() if k != "version"} == {
            k: v for k, v in before.items() if k != "version"
        }, f"{name}: builder altered keys other than 'version'"


def test_build_hermes_plugin_preserves_manifest_contract(plugin_root):
    """The fields the two consumers actually read — npm for package.json, the
    Hermes plugin loader for hermes-plugin.json — must survive the rewrite.
    Dropping any of them fails silently: npm still installs, Hermes still lists
    the plugin, and the breakage only surfaces at runtime."""
    run_builder(plugin_root)

    package = json.loads(
        (plugin_root / "package.json").read_text(encoding="utf-8")
    )
    committed_package = json.loads(
        (PLUGIN_ROOT / "package.json").read_text(encoding="utf-8")
    )
    for key in ["main", "scripts", "peerDependencies", "devDependencies",
                "private", "type"]:
        if key in committed_package:
            assert package.get(key) == committed_package[key], (
                f"package.json lost or altered {key}"
            )

    manifest = json.loads(
        (plugin_root / "hermes-plugin.json").read_text(encoding="utf-8")
    )
    committed_manifest = json.loads(
        (PLUGIN_ROOT / "hermes-plugin.json").read_text(encoding="utf-8")
    )
    for key in ["id", "main", "activationEvents", "contributes", "engines",
                "permissions", "author", "description"]:
        if key not in committed_manifest:
            continue
        assert manifest.get(key) == committed_manifest[key], (
            f"hermes-plugin.json lost or altered {key}"
        )


def test_build_hermes_plugin_output_is_two_space_json(plugin_root):
    """Both files must stay canonical json.dumps(indent=2) output with
    exactly one trailing newline — the same serialization the other builders
    use, which is what makes a re-run byte-identical and the drift check
    meaningful."""
    run_builder(plugin_root)

    for name in MANIFEST_FILES:
        raw = (plugin_root / name).read_text(encoding="utf-8")
        data = json.loads(raw)  # raises on invalid JSON
        assert raw.endswith("\n"), f"{name} must end with a trailing newline"
        assert not raw.endswith("\n\n"), f"{name} gained a blank trailing line"
        assert raw == json.dumps(data, indent=2) + "\n", (
            f"{name} is not 2-space-indented JSON in the repo's canonical form"
        )


def test_build_hermes_plugin_is_idempotent(plugin_root):
    """Re-running on already-generated files must be a no-op, otherwise a
    release process that runs the builder twice produces a spurious diff."""
    run_builder(plugin_root)
    first = {
        name: (plugin_root / name).read_bytes() for name in MANIFEST_FILES
    }

    run_builder(plugin_root)
    second = {
        name: (plugin_root / name).read_bytes() for name in MANIFEST_FILES
    }

    assert first == second, "re-running the builder changed its own output"
