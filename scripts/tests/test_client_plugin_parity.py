"""Client-plugin parity: every provider ships the same skills and the listen command.

The binding rule is `.meta-config/project.yaml -> rules.client-feature-parity`:
a feature added to one client plugin must be added to the others in the same
work package, or documented as `partial`/`unsupported` with evidence. This test
covers the artifact half of that rule for the two surfaces the parity request
named explicitly — **skills** and **commands** — so a future package can no
longer silently ship a smaller set.

Live host wiring stays a capability-matrix concern (Hermes/Antigravity runtimes
are not installed in CI); this test proves the shipped inventory.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SKILLS_DIR = REPO_ROOT / "dist" / "agent-skills"
INSTALLER = REPO_ROOT / "scripts" / "clients" / "install.sh"


def _skill_names(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    return {
        entry.name
        for entry in directory.iterdir()
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    }


def canonical_skills() -> set[str]:
    names = _skill_names(CANONICAL_SKILLS_DIR)
    assert len(names) >= 8, f"canonical skill set is unexpectedly small: {sorted(names)}"
    return names


def test_every_client_package_ships_the_canonical_skills() -> None:
    expected = canonical_skills()
    packages = {
        "claude-code": REPO_ROOT / "dist/plugins/claude-code/reqogniloom/skills",
        "antigravity": REPO_ROOT / "dist/plugins/antigravity/reqogniloom/skills",
        "opencode (dist)": REPO_ROOT / "dist/opencode/skills",
        "opencode (npm)": REPO_ROOT / "dist/npm/reqogniloom-opencode/skills",
    }
    for client, directory in packages.items():
        assert _skill_names(directory) == expected, (
            f"{client} ships {sorted(_skill_names(directory))}, "
            f"expected {sorted(expected)}"
        )


def test_hermes_installer_copies_the_canonical_skills() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    hermes = text.split("install_hermes()", 1)[1].split("\n}", 1)[0]
    assert "copy_skills" in hermes
    assert "dist/agent-skills" in hermes, (
        "Hermes must install the same eight skills as the other clients, "
        "not only the single wrapper skill"
    )
    assert "hermes-skill/reqogniloom" in hermes


def test_listen_command_exists_for_every_client() -> None:
    assert (REPO_ROOT / "dist/plugins/claude-code/reqogniloom/commands/listen.md").is_file()
    assert (
        REPO_ROOT / "dist/npm/reqogniloom-opencode/command/reqogniloom-listen.md"
    ).is_file()
    assert (REPO_ROOT / "dist/plugins/antigravity/reqogniloom/LISTEN.md").is_file()
    hermes = (REPO_ROOT / "integrations/hermes-agent-plugin/__init__.py").read_text(
        encoding="utf-8"
    )
    for switch in ("listen on", "listen off", "listen status"):
        assert switch in hermes, (
            "Hermes must expose the shared listen switch in its slash command"
        )


def test_opencode_installer_installs_the_listen_command() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    for section in ("install_opencode_v1()", "install_opencode_v2()"):
        body = text.split(section, 1)[1].split("\n}", 1)[0]
        assert "reqogniloom-listen.md" in body, (
            f"{section} must install the listen command, like the skills"
        )
