import subprocess
import sys
from pathlib import Path

import yaml

TEMPLATES_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMPLATES_DIR.parent.parent

SKILL_NAMES = [
    "vmodell-decomposition", "test-lifecycle", "risk-derivation",
    "ccb-approval-and-baseline", "traceability-audit",
]


def test_package_skills_copies_all_five(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, str(TEMPLATES_DIR / "package_skills.py"), "--out", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    for name in SKILL_NAMES:
        dst = tmp_path / name / "SKILL.md"
        src = TEMPLATES_DIR / "skills" / name / "SKILL.md"
        assert dst.exists(), f"missing {dst}"
        assert dst.read_text() == src.read_text(), f"{name} was not copied byte-identical"


def test_package_skills_fails_on_missing_description(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    bad_skills_dir = tmp_path / "skills"
    (bad_skills_dir / "broken-skill").mkdir(parents=True)
    (bad_skills_dir / "broken-skill" / "SKILL.md").write_text(
        "---\nname: broken-skill\n---\n\nBody.\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, str(TEMPLATES_DIR / "package_skills.py"),
         "--skills-dir", str(bad_skills_dir), "--out", str(tmp_path / "out")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "broken-skill" in result.stderr
    assert "description" in result.stderr
