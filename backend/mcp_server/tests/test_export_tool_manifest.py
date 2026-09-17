"""Tests for the MCP tool manifest export command."""
import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command


def test_export_tool_manifest_writes_valid_json(tmp_path):
    out_path = tmp_path / "tool-manifest.json"
    call_command("export_tool_manifest", "--out", str(out_path), stdout=StringIO())

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))

    assert data["tool_count"] == len(data["tools"])
    assert data["tool_count"] > 100  # registry has 107 tools as of 2026-08-05
    assert data["generated_from"].startswith("reqogniloom==")

    names = {t["name"] for t in data["tools"]}
    assert "requirement.create" in names
    assert "goal.query" in names          # was missing from the hand-written whitelist
    assert "diagram.create" in names       # was missing from the hand-written whitelist
    assert "baseline.create" in names      # was missing from the hand-written whitelist

    by_name = {t["name"]: t for t in data["tools"]}
    assert by_name["requirement.create"]["is_write"] is True
    assert by_name["requirement.query"]["is_write"] is False


def test_export_tool_manifest_no_duplicate_names(tmp_path):
    out_path = tmp_path / "tool-manifest.json"
    call_command("export_tool_manifest", "--out", str(out_path), stdout=StringIO())
    data = json.loads(out_path.read_text(encoding="utf-8"))

    names = [t["name"] for t in data["tools"]]
    assert len(names) == len(set(names)), "duplicate tool name in manifest"


def test_export_tool_manifest_write_tools_correctly_marked(tmp_path):
    """Regression: goal.*/main_goal.* write tools must have is_write: true."""
    out_path = tmp_path / "tool-manifest.json"
    call_command("export_tool_manifest", "--out", str(out_path), stdout=StringIO())
    data = json.loads(out_path.read_text(encoding="utf-8"))

    by_name = {t["name"]: t for t in data["tools"]}

    # At minimum, check that a known mutating goal tool is marked as write
    # goal.create and goal.delete are definitely write operations
    assert "goal.create" in by_name, "goal.create missing from manifest"
    assert "goal.delete" in by_name, "goal.delete missing from manifest"

    assert by_name["goal.create"]["is_write"] is True, (
        "goal.create must have is_write: true (it is a write tool)"
    )
    assert by_name["goal.delete"]["is_write"] is True, (
        "goal.delete must have is_write: true (it is a write tool)"
    )


def test_export_tool_manifest_json_roundtrip_safe(tmp_path):
    """Regression: build_manifest() JSON output must be valid and round-trip-safe."""
    out_path = tmp_path / "tool-manifest.json"
    call_command("export_tool_manifest", "--out", str(out_path), stdout=StringIO())

    # Read the written JSON
    raw_text = out_path.read_text(encoding="utf-8")
    data = json.loads(raw_text)

    # Write it back and re-read to ensure round-trip safety
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    data_after = json.loads(out_path.read_text(encoding="utf-8"))

    # Verify key structure is preserved
    assert data["tool_count"] == data_after["tool_count"]
    assert len(data["tools"]) == len(data_after["tools"])

    # Verify a sample tool's properties survive round-trip
    sample_tool = data["tools"][0]
    sample_tool_after = next(
        (t for t in data_after["tools"] if t["name"] == sample_tool["name"]), None
    )
    assert sample_tool_after is not None
    assert sample_tool["is_write"] == sample_tool_after["is_write"]
