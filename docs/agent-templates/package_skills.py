"""Stage docs/agent-templates/skills/<name>/SKILL.md into dist/agent-skills/
— a copy-and-validate step, not a render step, since Task 3 already
authored these in final shippable form. Every platform packager (Claude
Code, Antigravity, OpenCode) reads from dist/agent-skills/ so none of them
need to know the docs/agent-templates/ source layout."""
import argparse
import shutil
import sys
from pathlib import Path

import yaml

TEMPLATES_DIR = Path(__file__).resolve().parent
DEFAULT_SKILLS_DIR = TEMPLATES_DIR / "skills"
DEFAULT_OUT = TEMPLATES_DIR.parent.parent / "dist" / "agent-skills"


def _parse_frontmatter(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{path} has no YAML frontmatter")
    end = raw.index("\n---\n", 4)
    return yaml.safe_load(raw[4:end])


def package(skills_dir: Path, out_dir: Path) -> None:
    errors: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            errors.append(f"{skill_dir}: no SKILL.md")
            continue
        frontmatter = _parse_frontmatter(skill_path)
        if frontmatter.get("name") != skill_dir.name:
            errors.append(f"{skill_path}: frontmatter name != directory name")
        if not frontmatter.get("description"):
            errors.append(f"{skill_path}: missing description")
        if "tools" in frontmatter:
            errors.append(f"{skill_path}: process skills must not carry a tools: field")

        dst_dir = out_dir / skill_dir.name
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_path, dst_dir / "SKILL.md")

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-dir", type=Path, default=DEFAULT_SKILLS_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    package(args.skills_dir, args.out)
