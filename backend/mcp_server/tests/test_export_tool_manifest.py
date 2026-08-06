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
