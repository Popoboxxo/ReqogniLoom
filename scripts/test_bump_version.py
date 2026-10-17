"""Tests for the release version bump (issues #1349 / #1353).

The bump must reach *every* carrier, including the four hand-maintained Hermes
desktop-plugin files, and must repair a carrier that is already stale. It also
re-renders the client docs (checked separately by ``render.py --check``).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = REPO_ROOT / "scripts" / "bump_version.py"


def _load_bump():
    spec = importlib.util.spec_from_file_location("reqlo_bump_version", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bump = _load_bump()


def _set_pointer(data: object, pointer: tuple[object, ...], value: str) -> None:
    current = data
    for index, key in enumerate(pointer[:-1]):
        following = pointer[index + 1]
        if isinstance(key, int):
            while len(current) <= key:  # type: ignore[arg-type]
                current.append({} if not isinstance(following, int) else [])  # type: ignore[attr-defined]
            current = current[key]  # type: ignore[index]
        else:
            if key not in current:  # type: ignore[operator]
                current[key] = [] if isinstance(following, int) else {}  # type: ignore[index]
            current = current[key]  # type: ignore[index]
    current[pointer[-1]] = value  # type: ignore[index]


def _write_fixture_tree(root: Path, version: str = "1.0.0") -> None:
    (root / "VERSION").write_text(f"{version}\n", encoding="utf-8")

    per_file: dict[str, dict] = {}
    for loc in bump.VERSION_COUPLED:
        data = per_file.setdefault(loc.path, {})
        _set_pointer(data, loc.pointer, version)
    for rel_path, data in per_file.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    (root / ".env.example").write_text(
        f"# {version}; keep REQOGNILOOM_VERSION in step with the release you deploy.\n"
        f"REQOGNILOOM_VERSION={version}\n",
        encoding="utf-8",
    )
    for rel_path in ("deploy/docker-compose.yml", "deploy/docker-compose.minimal.yml"):
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"image: x:${{REQOGNILOOM_VERSION:-{version}}}\n", encoding="utf-8"
        )
    (root / "site").mkdir(parents=True, exist_ok=True)
    (root / "site/index.html").write_text(
        f'<span class="badge badge--info">v{version}</span>\n'
        f'<span class="mono">{version}</span>\n',
        encoding="utf-8",
    )
    for rel_path, text in (
        ("docs/CODEBASE_OVERVIEW.md", f"Stand `v{version}`\n"),
        ("docs/api/MCP-SURFACE.md", f"| Version | `v{version}` (`VERSION`, `{version}`) |\n"),
        ("systemagents/reqogniloom-operator.md", f"as of `v{version}`\n"),
    ):
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def test_bump_reaches_every_carrier(tmp_path: Path) -> None:
    _write_fixture_tree(tmp_path)
    changes = bump.apply_bumps(tmp_path, "2.0.0")
    changed_paths = {rel_path for rel_path, _ in changes}

    assert (tmp_path / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0"
    for loc in bump.VERSION_COUPLED:
        assert loc.path in changed_paths, f"carrier never bumped: {loc.path}"
        data = json.loads((tmp_path / loc.path).read_text(encoding="utf-8"))
        value = data
        for key in loc.pointer:
            value = value[key]
        assert value == "2.0.0", f"{loc.path} {loc.pointer} still {value!r}"

    env = (tmp_path / ".env.example").read_text(encoding="utf-8")
    assert "1.0.0" not in env
    assert "REQOGNILOOM_VERSION=2.0.0" in env
    compose = (tmp_path / "deploy/docker-compose.yml").read_text(encoding="utf-8")
    assert "${REQOGNILOOM_VERSION:-2.0.0}" in compose


def test_bump_repairs_a_stale_hermes_carrier(tmp_path: Path) -> None:
    _write_fixture_tree(tmp_path)
    stale = tmp_path / "integrations/hermes-plugin/reqogniloom/hermes-plugin.json"
    data = json.loads(stale.read_text(encoding="utf-8"))
    data["version"] = "0.9.0"
    stale.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    bump.apply_bumps(tmp_path, "2.0.0")

    assert json.loads(stale.read_text(encoding="utf-8"))["version"] == "2.0.0"


def test_second_bump_is_a_no_op(tmp_path: Path) -> None:
    _write_fixture_tree(tmp_path)
    bump.apply_bumps(tmp_path, "2.0.0")
    assert bump.apply_bumps(tmp_path, "2.0.0") == []


def test_invalid_version_is_refused(tmp_path: Path) -> None:
    _write_fixture_tree(tmp_path)
    for invalid in ("2.0", "v2.0.0", "latest"):
        try:
            bump.apply_bumps(tmp_path, invalid)
        except bump.BumpError:
            continue
        raise AssertionError(f"accepted invalid version {invalid!r}")


def test_refuses_to_bump_on_main(tmp_path: Path) -> None:
    """The release bump must never run on main/master (branch guard)."""
    import subprocess

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=release@example.test",
            "-c",
            "user.name=Release",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "init",
        ],
        cwd=tmp_path,
        check=True,
    )
    try:
        bump.assert_release_branch(tmp_path)
    except bump.BumpError as exc:
        assert "refusing" in str(exc)
    else:
        raise AssertionError("bump was allowed on main")
