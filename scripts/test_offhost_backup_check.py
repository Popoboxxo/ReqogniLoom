"""Contract tests for ``deploy/check-offhost-backup.sh`` (plan D3.3, #792 point 13).

``make wipe`` deletes `postgres_backup_data` together with the database volume,
so the off-host copy is the only thing left. The gate therefore has to reject
every shape of "backup that is not a backup", not just a missing file:

* no file at all / empty directory,
* a file that is too old to describe the database about to be deleted,
* a truncated or corrupt gzip stream,
* a valid gzip that is not a pg_dump (no ``PostgreSQL database dump`` header),
* a zero-byte file.

The positive case must pass, otherwise the first failing test would hide the
real gate. Docker is not involved: the script only inspects a directory, and the
tests build the artifacts themselves.

Wired into ``agent-templates-test`` in the same PR (RB-D18: a bare
``scripts/test_*.py`` runs in no job by default). Stdlib only.
"""
from __future__ import annotations

import gzip
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "deploy" / "check-offhost-backup.sh"

DUMP_HEADER = b"--\n-- PostgreSQL database dump\n--\n\n"
DUMP_BODY = DUMP_HEADER + b"COPY public.requirement (id) FROM stdin;\n\\N\n\\.\n"


def run_check(directory: Path, max_age: int | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if max_age is not None:
        env["MAX_AGE_SECONDS"] = str(max_age)
    return subprocess.run(
        ["bash", str(SCRIPT), str(directory)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=False,
    )


def write_dump(directory: Path, name: str = "reqogniloom_20261103T010000Z.sql.gz", body: bytes = DUMP_BODY) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    with gzip.open(path, "wb") as handle:
        handle.write(body)
    return path


def test_valid_backup_passes(tmp_path: Path) -> None:
    write_dump(tmp_path)
    result = run_check(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "OK:" in result.stdout


def test_empty_directory_fails(tmp_path: Path) -> None:
    result = run_check(tmp_path)
    assert result.returncode != 0
    assert "no reqogniloom_*.sql.gz" in result.stderr


def test_zero_byte_file_fails(tmp_path: Path) -> None:
    (tmp_path / "reqogniloom_20261103T010000Z.sql.gz").write_bytes(b"")
    result = run_check(tmp_path)
    assert result.returncode != 0
    assert "empty" in result.stderr


def test_stale_backup_fails(tmp_path: Path) -> None:
    path = write_dump(tmp_path)
    old = time.time() - 3600
    os.utime(path, (old, old))
    result = run_check(tmp_path)
    assert result.returncode != 0
    assert "old" in result.stderr


def test_corrupt_gzip_fails(tmp_path: Path) -> None:
    (tmp_path / "reqogniloom_20261103T010000Z.sql.gz").write_bytes(b"this is not a gzip stream")
    result = run_check(tmp_path)
    assert result.returncode != 0
    assert "gzip" in result.stderr


def test_valid_gzip_without_pg_dump_header_fails(tmp_path: Path) -> None:
    write_dump(tmp_path, body=b"some other artifact\n")
    result = run_check(tmp_path)
    assert result.returncode != 0
    assert "pg_dump" in result.stderr


def test_newest_file_wins(tmp_path: Path) -> None:
    """An old broken dump next to a fresh good one must not fail the gate."""
    stale = write_dump(tmp_path, name="reqogniloom_20260101T000000Z.sql.gz")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    write_dump(tmp_path, name="reqogniloom_20261103T010000Z.sql.gz")
    result = run_check(tmp_path)
    assert result.returncode == 0, result.stderr


def test_missing_directory_fails(tmp_path: Path) -> None:
    result = run_check(tmp_path / "does-not-exist")
    assert result.returncode != 0
    assert "not a directory" in result.stderr


if __name__ == "__main__":  # pragma: no cover - convenience only
    sys.exit(pytest.main([__file__, "-q"]))
