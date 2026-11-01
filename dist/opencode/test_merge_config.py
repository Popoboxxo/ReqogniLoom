"""Tests for the OpenCode V2 config merge tool.

The CLI is driven through ``subprocess`` rather than imported: Task 4 calls it
exactly that way from ``install.sh``, so the tests exercise the same contract
(argv, exit codes, stdout/stderr) the installer depends on.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from build_opencode_package import v2_server_entry
from merge_config import merge_v2

BUILD_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUILD_DIR.parent.parent

URL = "http://h:8001"
KEY_ENV = "MY_KEY"


def _run_cli(args):
    return subprocess.run(
        [sys.executable, str(BUILD_DIR / "merge_config.py"), *args],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def test_merge_keeps_other_servers_and_v1_entries():
    """V1 entries (``mcp.<name>``), other V2 servers (``mcp.servers.<name>``)
    and unrelated top-level keys must survive the merge byte-for-byte, and the
    caller's dict must not be mutated."""
    config = {
        "mcp": {
            "legacy": {"type": "remote", "url": "x"},
            "servers": {"other": {"type": "local", "command": ["x"]}},
        },
        "model": "m",
    }
    snapshot = json.loads(json.dumps(config))

    merged = merge_v2(config, URL, KEY_ENV)

    assert config == snapshot, "merge_v2 must not mutate its input"
    assert merged["mcp"]["legacy"] == {"type": "remote", "url": "x"}
    assert merged["mcp"]["servers"]["other"] == {"type": "local", "command": ["x"]}
    assert merged["model"] == "m"
    assert merged["mcp"]["servers"]["reqogniloom"] == v2_server_entry(URL, KEY_ENV)


def test_merge_is_idempotent():
    config = {"mcp": {"servers": {"other": {"type": "local", "command": ["x"]}}}}

    once = merge_v2(config, URL, KEY_ENV)
    twice = merge_v2(once, URL, KEY_ENV)

    assert twice == once


def test_merge_creates_missing_structure():
    merged = merge_v2({}, URL, KEY_ENV)

    assert merged == {"mcp": {"servers": {"reqogniloom": v2_server_entry(URL, KEY_ENV)}}}


def test_merge_rejects_non_dict_mcp():
    """A structurally wrong config would otherwise blow up with an
    AttributeError deep inside the merge; the CLI maps this to exit 2."""
    with pytest.raises(ValueError):
        merge_v2({"mcp": None}, URL, KEY_ENV)


def test_cli_creates_file_and_parent_dir(tmp_path):
    target = tmp_path / "new" / "dir" / "opencode.json"

    result = _run_cli(["--config", str(target), "--url", URL, "--key-env", KEY_ENV])

    assert result.returncode == 0, result.stderr
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    data = json.loads(text)
    assert data["mcp"]["servers"]["reqogniloom"] == v2_server_entry(URL, KEY_ENV)


def test_cli_refuses_jsonc_and_leaves_file_untouched(tmp_path):
    """A commented config cannot be round-tripped by a JSON parser, so the tool
    must refuse instead of silently dropping the comments."""
    target = tmp_path / "opencode.json"
    original = "// comment\n{}\n"
    target.write_text(original, encoding="utf-8")

    result = _run_cli(["--config", str(target), "--url", URL, "--key-env", KEY_ENV])

    assert result.returncode == 2
    assert target.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("opencode.json.bak-*")) == []
    combined = result.stdout + result.stderr
    assert "JSONC" in combined
    assert "Eintrag von Hand einfügen" in combined
    assert "opencode.v2.json.snippet" in combined


@pytest.mark.parametrize("bad_env", ["A B", "A$B", "{x}"])
def test_cli_rejects_bad_key_env(tmp_path, bad_env):
    target = tmp_path / "opencode.json"

    result = _run_cli(["--config", str(target), "--url", URL, "--key-env", bad_env])

    assert result.returncode == 2
    assert not target.exists()


def test_cli_dry_run_writes_nothing(tmp_path):
    target = tmp_path / "nested" / "opencode.json"

    result = _run_cli(
        ["--config", str(target), "--url", URL, "--key-env", KEY_ENV, "--dry-run"]
    )

    assert result.returncode == 0, result.stderr
    assert not target.exists()
    assert not target.parent.exists(), "dry run must not create directories"
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    assert lines, "dry run must report what it would do"
    assert all(line.startswith("[dry-run]") for line in lines)


def test_cli_writes_backup_before_changing_existing_file(tmp_path):
    target = tmp_path / "opencode.json"
    old = (
        json.dumps(
            {"mcp": {"servers": {"other": {"type": "local", "command": ["x"]}}}},
            indent=2,
        )
        + "\n"
    )
    target.write_text(old, encoding="utf-8")

    result = _run_cli(["--config", str(target), "--url", URL, "--key-env", KEY_ENV])

    assert result.returncode == 0, result.stderr
    backups = list(tmp_path.glob("opencode.json.bak-*"))
    assert len(backups) == 1
    assert re.fullmatch(r"opencode\.json\.bak-\d{14}", backups[0].name)
    assert backups[0].read_text(encoding="utf-8") == old
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["mcp"]["servers"]["other"] == {"type": "local", "command": ["x"]}
    assert data["mcp"]["servers"]["reqogniloom"] == v2_server_entry(URL, KEY_ENV)


def test_cli_exit_3_when_target_not_writable(tmp_path):
    """``blocker`` is a regular file, so the target's parent cannot be created
    (ENOTDIR). Used instead of a chmod check so the test also holds when the
    suite runs as root."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    target = blocker / "opencode.json"

    result = _run_cli(["--config", str(target), "--url", URL, "--key-env", KEY_ENV])

    assert result.returncode == 3, result.stderr
    assert result.stderr.strip(), "exit 3 must explain why the write failed"
