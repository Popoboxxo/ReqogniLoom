"""Tests for scripts/check_plan_refs.py."""
from pathlib import Path

from check_plan_refs import main, missing_paths, referenced_paths


def test_existing_path_is_ok(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "a.py").write_text("x")
    assert missing_paths("See `backend/a.py:10` here", tmp_path) == []


def test_removed_path_is_reported(tmp_path: Path) -> None:
    assert missing_paths("Layer in `frontend/src/bluepencil/index.tsx`", tmp_path) == [
        "frontend/src/bluepencil/index.tsx"
    ]


def test_create_and_test_lines_are_skipped() -> None:
    text = "- Create: `backend/new.py`\n- Test: `backend/tests/test_new.py`\n- Modify: `backend/old.py`\n"
    assert referenced_paths(text) == ["backend/old.py"]


def test_scratch_and_placeholders_are_ignored() -> None:
    text = "`.tmp/x.md` `backend/<name>/y.py` `docs/*.md` `backend/dir/`"
    assert referenced_paths(text) == []


def test_main_exit_codes(tmp_path: Path, capsys) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("`backend/gone.py`")
    assert main([str(plan), "--root", str(tmp_path)]) == 1
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "gone.py").write_text("x")
    assert main([str(plan), "--root", str(tmp_path)]) == 0
