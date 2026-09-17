"""Regenerate Hermes IDE plugin manifest with VERSION embedding.

The Hermes plugin (integrations/hermes-plugin/reqogniloom/) declares its own
version in package.json and hermes-plugin.json, but these should be synced to
the repo's VERSION file at release time, following the same pattern as
dist/plugins/claude-code and dist/plugins/antigravity.

This builder:
1. Reads the repo's VERSION
2. Updates package.json and hermes-plugin.json with that version

Build/test verification is handled separately via CI (npm run build && npm test).
"""
import argparse
import json
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent.parent
PLUGIN_ROOT = REPO_ROOT / "integrations" / "hermes-plugin" / "reqogniloom"


def build(plugin_root: Path = PLUGIN_ROOT) -> None:
    """Update Hermes plugin version to match repo VERSION."""
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    # Update package.json
    package_json_path = plugin_root / "package.json"
    package_data = json.loads(package_json_path.read_text(encoding="utf-8"))
    package_data["version"] = version
    package_json_path.write_text(
        json.dumps(package_data, indent=2) + "\n",
        encoding="utf-8",
    )

    # Update hermes-plugin.json
    hermes_manifest_path = plugin_root / "hermes-plugin.json"
    manifest_data = json.loads(hermes_manifest_path.read_text(encoding="utf-8"))
    manifest_data["version"] = version
    hermes_manifest_path.write_text(
        json.dumps(manifest_data, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[OK] Updated Hermes plugin version to {version}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-root", type=Path, default=PLUGIN_ROOT)
    args = parser.parse_args()
    build(plugin_root=args.plugin_root)
