"""Guard for DEP-010 frontend lock metadata and reproducible dev installs.

npm recorded only 880 ``license`` fields for 883 ``resolved`` packages in the
frontend lock - khroma, undici and zod were missing metadata. This guard keeps
resolution/license coverage at 100% (an explicit NOASSERTION allowlist is the
only sanctioned escape hatch) and keeps both Docker build stages on ``npm ci``
so the lock is actually enforced. The dev hot-reload path installs into the
mounted volume via docker-compose.override.yml, so pinning the image stage to
``npm ci`` does not change local development.
"""
from __future__ import annotations

import json
from pathlib import Path

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK = REPO_ROOT / "frontend" / "package-lock.json"
DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
OVERRIDE = REPO_ROOT / "deploy" / "docker-compose.override.yml"

# Packages that upstream genuinely publishes without an SPDX identifier must
# be listed here with a reason AND documented in THIRD-PARTY-NOTICES.md.
# Currently empty: khroma, undici and zod were patched with their real MIT
# license (verified from the published tarballs / registry metadata).
NOASSERTION_ALLOWLIST: dict[str, str] = {}

EXPECTED_VERSIONS = {"khroma": "2.1.0", "undici": "8.12.3", "zod": "4.6.7"}


def _lock() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))


def _stage(text: str, name: str) -> str:
    """Return the body of a named FROM stage, up to the next FROM."""
    marker = f"FROM base AS {name}"
    assert marker in text, f"Docker stage {name!r} not found"
    body = text.split(marker, 1)[1]
    return body.split("\nFROM ", 1)[0]


def test_frontend_lock_is_valid_json() -> None:
    assert _lock().get("lockfileVersion"), "frontend lockfile is not a valid npm lock"


def test_resolved_packages_have_license_metadata() -> None:
    missing: list[str] = []
    for key, package in _lock().get("packages", {}).items():
        if not isinstance(package, dict) or "resolved" not in package:
            continue
        if "license" in package:
            continue
        name = key.split("node_modules/")[-1]
        if name in NOASSERTION_ALLOWLIST:
            continue
        missing.append(name)
    assert not missing, f"resolved packages without license metadata: {missing}"


def test_noassertion_allowlist_is_justified() -> None:
    notices = REPO_ROOT / "docs" / "legal" / "THIRD-PARTY-NOTICES.md"
    text = notices.read_text(encoding="utf-8") if notices.is_file() else ""
    for name, reason in NOASSERTION_ALLOWLIST.items():
        assert reason.strip(), f"{name}: allowlist entry needs a reason"
        assert name in text, f"{name}: NOASSERTION must be documented in THIRD-PARTY-NOTICES.md"


def test_patched_versions_are_unchanged() -> None:
    packages = _lock()["packages"]
    for name, version in EXPECTED_VERSIONS.items():
        entry = next(
            (value for key, value in packages.items() if key.endswith(f"node_modules/{name}")),
            None,
        )
        assert entry is not None, f"{name} missing from lockfile"
        assert entry.get("version") == version, f"{name} version drifted from {version}"


def test_development_stage_uses_npm_ci() -> None:
    stage = _stage(DOCKERFILE.read_text(encoding="utf-8"), "development")
    assert "npm ci" in stage, "development stage must use npm ci (reproducible install)"
    assert "RUN npm install" not in stage, "development stage still uses npm install"


def test_builder_stage_uses_npm_ci() -> None:
    stage = _stage(DOCKERFILE.read_text(encoding="utf-8"), "builder")
    assert "npm ci" in stage, "builder stage must keep using npm ci"


def test_dev_hot_reload_installs_into_mounted_volume() -> None:
    text = OVERRIDE.read_text(encoding="utf-8")
    assert "npm install" in text and "npm run dev" in text, (
        "dev override must keep installing into the mounted node_modules volume; "
        "otherwise switching the image stage to npm ci would break hot reload"
    )
