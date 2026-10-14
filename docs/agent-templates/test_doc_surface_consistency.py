"""Doc-surface consistency gate (#1293 — Doku-Audit).

Two classes of defect are pinned here, both of them *silent*: the CI is green
while the documentation lies to the next reader.

1. **The documented MCP tool count.** ``docs/agent-templates/tool-manifest.json``
   is the single source of truth (``tool_count``). Several living documents
   repeat that number as prose; before this gate they drifted independently
   (#1104, #1293): the manifest said 228 while ``README.md`` said 227 and
   ``docs/api/MCP-SURFACE.md`` said 228. ``test_meta_tool_count_drift.py``
   already guards the generated root-context files (``.meta-config/project.yaml``,
   ``AGENTS.md``, ``CLAUDE.md``); this module extends the same ratchet to the
   human-facing docs.
2. **Copy-paste-broken shell commands.** The doc audit found commands that
   simply do not run any more — ``docker-compose`` (the standalone binary is
   gone; it is ``docker compose`` now) and a bare ``python`` interpreter that is
   not on ``PATH`` in every environment (``python3`` is). This gate fails on the
   next reintroduction instead of shipping it a third time.

Why a *marker* rule for the tool count
--------------------------------------
``N tools`` alone is not enough: ``MCP-SURFACE.md`` deliberately lists the
*history* of the number ("172 tools / 30 groups" …) and the group table lists
per-group counts. A candidate is only read as the catalogue size when the same
line also names the catalogue (``MCP``, ``tool-group prefix``, ``prefixes``,
``tool-manifest``, ``tools/list`` or a tool-call result). That rule matches every
current claim and none of the historical or per-group ones.

Dependencies: stdlib + PyYAML only (the CI job ``agent-templates-test`` installs
nothing else).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

MANIFEST_REL = "docs/agent-templates/tool-manifest.json"

#: Living documents whose prose repeats the MCP catalogue size. Historical
#: reports (``docs/archive/**``, ``docs/audit/**``, …) are deliberately excluded:
#: they record a point in time and must not be rewritten.
TOOL_COUNT_DOCS = (
    "README.md",
    "docs/api/MCP-SURFACE.md",
    "docs/clients/antigravity.md",
    "docs/clients/antigravity.de.md",
)

#: Docs whose fenced shell examples must not use the retired commands.
SHELL_COMMAND_DOCS = (
    "README.md",
    "docs/agent-templates/INSTALL.md",
    "docs/api/MCP-SURFACE.md",
)

#: ``clients/registry.yaml`` Client id whose ``verify`` block repeats the count.
REGISTRY_REL = "clients/registry.yaml"
REGISTRY_TOOL_COUNT_CLIENT = "antigravity"

#: A number immediately before "tools" (optionally "individual tools"). The
#: ``(?!-)`` keeps "36 tool-group" / "tool-call" from being read as "36 tool".
_TOOL_COUNT_RE = re.compile(r"(\d+)\s+(?:individual\s+)?[Tt]ools?\b(?!-)")

#: The ``| Tools | **239** | `` row of MCP-SURFACE §1 (digits *after* "Tools").
_TOOL_COUNT_ROW_RE = re.compile(r"\|\s*Tools\s*\|\s*\**(\d+)\**\s*\|")

#: A line only names the catalogue size when it also names the catalogue.
_CATALOGUE_MARKERS = (
    "tool-group prefix",
    "mcp-katalog",
    "prefixes",
    "tool-manifest",
    "tools/list",
    "tool-call result",
    "tool-call-ergebnis",
    "mcp",
)

#: The retired standalone Compose binary. ``deploy/docker-compose.yml`` (a file
#: name) must not match, hence the "not preceded by a path separator" guard.
_LEGACY_COMPOSE_RE = re.compile(r"(?<![\w/.-])docker-compose\s")

#: A bare ``python`` interpreter (not ``python3``, not ``python3.12``).
_BARE_PYTHON_RE = re.compile(r"(?<![\w3.])python\s")


def _find_repo_root() -> Optional[Path]:
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / MANIFEST_REL).is_file():
            return ancestor
    return None


def _manifest_tool_count(root: Path) -> int:
    manifest = json.loads((root / MANIFEST_REL).read_text(encoding="utf-8"))
    count = manifest.get("tool_count")
    assert isinstance(count, int), f"{MANIFEST_REL} has no integer tool_count"
    return count


def _documented_counts(text: str) -> Set[int]:
    """Catalogue-size claims in a markdown document (marker rule, see module doc)."""
    counts: Set[int] = set()
    for line in text.splitlines():
        low = line.lower()
        if any(marker in low for marker in _CATALOGUE_MARKERS):
            counts |= {int(m.group(1)) for m in _TOOL_COUNT_RE.finditer(line)}
        counts |= {int(m.group(1)) for m in _TOOL_COUNT_ROW_RE.finditer(line)}
    return counts


def _shell_fence_lines(text: str) -> List[str]:
    """Return the lines inside ``` fences whose language is a shell."""
    lines: List[str] = []
    in_shell = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_shell:
                in_shell = False
                continue
            lang = stripped[3:].strip().lower()
            in_shell = lang in ("bash", "sh", "shell", "zsh")
            continue
        if in_shell:
            lines.append(line)
    return lines


def find_doc_surface_problems(root: Optional[Path] = None) -> List[str]:
    """Return one problem per doc-surface defect; empty means green."""
    if root is None:
        root = _find_repo_root()
        if root is None:
            return [
                f"repo root not reachable from {Path(__file__).resolve()} — no "
                f"ancestor directory contains {MANIFEST_REL}"
            ]
    problems: List[str] = []
    count = _manifest_tool_count(root)

    for rel in TOOL_COUNT_DOCS:
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel} is missing at {path}")
            continue
        found = _documented_counts(path.read_text(encoding="utf-8"))
        if not found:
            problems.append(
                f"{rel} documents no MCP tool count at all — add a "
                f"\"<int> tools\" claim next to the catalogue name, or drop the "
                f"file from TOOL_COUNT_DOCS (a conscious, reviewed decision). "
                f"The current count is {count}."
            )
        wrong = sorted(found - {count})
        if wrong:
            problems.append(
                f"{rel} documents tool count {wrong}, but {MANIFEST_REL} says "
                f"tool_count = {count} — update {rel} to {count} (or regenerate "
                f"the manifest with `python3 backend/manage.py export_tool_manifest`)."
            )

    registry_path = root / REGISTRY_REL
    if registry_path.is_file():
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        clients = (registry or {}).get("clients") or []
        entry = next(
            (c for c in clients if c.get("id") == REGISTRY_TOOL_COUNT_CLIENT), None
        )
        if entry is None:
            problems.append(
                f"{REGISTRY_REL} has no '{REGISTRY_TOOL_COUNT_CLIENT}' client — "
                "the tool-count guard cannot check it."
            )
        else:
            blob = json.dumps(entry.get("verify") or {})
            found = {int(m.group(1)) for m in _TOOL_COUNT_RE.finditer(blob)}
            wrong = sorted(found - {count})
            if wrong:
                problems.append(
                    f"{REGISTRY_REL} ({REGISTRY_TOOL_COUNT_CLIENT}) documents tool "
                    f"count {wrong}, but {MANIFEST_REL} says {count}."
                )

    for rel in SHELL_COMMAND_DOCS:
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel} is missing at {path}")
            continue
        for line in _shell_fence_lines(path.read_text(encoding="utf-8")):
            if _LEGACY_COMPOSE_RE.search(line):
                problems.append(
                    f"{rel}: legacy `docker-compose` command — use "
                    f"`docker compose`: {line.strip()}"
                )
            if _BARE_PYTHON_RE.search(line):
                problems.append(
                    f"{rel}: bare `python` interpreter — use `python3`: "
                    f"{line.strip()}"
                )
    return problems


def find_installer_problems(root: Optional[Path] = None) -> List[str]:
    """Pin the two installer defects from the 2026-10-05 client smoke test."""
    if root is None:
        root = _find_repo_root()
        if root is None:
            return ["repo root not reachable"]
    script = root / "scripts" / "clients" / "install.sh"
    if not script.is_file():
        return [f"scripts/clients/install.sh is missing at {script}"]
    text = script.read_text(encoding="utf-8")
    problems: List[str] = []

    # (a) The Codex branch must wire the key via bearer_token_env_var — its
    #     transport has no custom-header option, so `codex mcp add --url` alone
    #     registers the server unauthenticated.
    if "--bearer-token-env-var" not in text:
        problems.append(
            "scripts/clients/install.sh: the Codex branch does not pass "
            "--bearer-token-env-var, so `codex mcp add` registers reqogniloom "
            "without a credential."
        )

    # (b) No CWD-relative skills default may write into the checkout.
    for legacy_default in ("SKILLS_DIR:-.opencode/skills", "SKILLS_DIR:-.agents/skills"):
        if legacy_default in text:
            problems.append(
                f"scripts/clients/install.sh still defaults the skills dir to a "
                f"CWD-relative path (`{legacy_default}`) — it writes into the "
                "repo when run from the checkout."
            )
    if "resolve_skills_dir" not in text:
        problems.append(
            "scripts/clients/install.sh lost the `resolve_skills_dir` guard that "
            "refuses a skills dir inside the checkout."
        )
    return problems


def test_doc_surface_is_consistent() -> None:
    """The real repository must be green (the positive gate)."""
    problems = find_doc_surface_problems()
    assert not problems, problems


def test_installer_defects_are_pinned() -> None:
    """The installer must carry the Codex bearer env + the containment guard."""
    problems = find_installer_problems()
    assert not problems, problems


def test_stale_tool_count_goes_red(tmp_path: Path) -> None:
    """NEGATIVE proof: a stale prose count must fail, a historical one must not."""
    (tmp_path / "docs" / "agent-templates").mkdir(parents=True)
    (tmp_path / MANIFEST_REL).write_text(
        json.dumps({"tool_count": 239, "tools": []}), encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "The server exposes 36 tool-group prefixes, 227 individual tools.\n"
        # historical "N tools" without a catalogue marker must be ignored:
        "| 172 tools / 30 groups | audit snapshot | historical |\n",
        encoding="utf-8",
    )
    for rel in TOOL_COUNT_DOCS:
        if rel == "README.md":
            continue
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("36 tool-group prefixes, 239 tools.\n", encoding="utf-8")

    problems = find_doc_surface_problems(tmp_path)
    assert any("README.md" in p and "227" in p for p in problems), problems
    assert not any("172" in p for p in problems), problems


def test_legacy_shell_commands_go_red(tmp_path: Path) -> None:
    """NEGATIVE proof: `docker-compose` / bare `python` in a fence must fail."""
    (tmp_path / "docs" / "agent-templates").mkdir(parents=True)
    (tmp_path / MANIFEST_REL).write_text(
        json.dumps({"tool_count": 1, "tools": []}), encoding="utf-8"
    )
    for rel in TOOL_COUNT_DOCS:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1 tools in the MCP catalogue.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "1 tools in the MCP catalogue.\n"
        "```bash\n"
        "docker-compose exec backend python manage.py migrate\n"
        "python3 -m pytest -q\n"
        "docker compose -f deploy/docker-compose.yml up -d\n"
        "```\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "agent-templates" / "INSTALL.md").write_text(
        "1 tools in the MCP catalogue.\n", encoding="utf-8"
    )

    problems = find_doc_surface_problems(tmp_path)
    joined = "\n".join(problems)
    assert "legacy `docker-compose`" in joined, problems
    assert "bare `python`" in joined, problems
    # `deploy/docker-compose.yml` is a file name, not a retired command.
    assert not any("deploy/docker-compose.yml up" in p for p in problems), problems
