"""Regression tests for the Honcho #1441 runtime backport (audit finding #1).

Security audit finding #1 (MEDIUM, CWE-664): ``apply_patch.py`` reported
"already applied" after checking a single marker in a single file, wrote
non-atomically, and the entrypoint shim silently skipped a missing mount.

What is covered here — all without network or Docker:

* per-file/per-edit idempotency (all post-conditions or none, never a mix),
* the cross-file half state that used to mask a broken patch,
* atomic replacement (temp file in the same directory + ``os.replace``),
* loud failure on a changed base image / missing source file,
* fail-closed entrypoint shims for BOTH Honcho services.

The real v3.6.1 sources are not vendored in this repository, so the anchors are
exercised against faithful minimal fixtures that contain exactly the strings the
backport expects (each anchor exactly once, as in the pinned image).
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PATCH_SCRIPT = REPO_ROOT / "deploy" / "honcho-patch" / "apply_patch.py"
COMPOSE_FILE = REPO_ROOT / "deploy" / "docker-compose.yml"

# --- fixtures: the anchors of the pinned honcho v3.6.1 image -----------------

RUNTIME_PRISTINE = '''"""Fixture: minimal shape of honcho v3.6.1 src/llm/runtime.py."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ModelConfig(BaseModel):
    transport: str = "openai"
    base_url: str | None = None
    provider_params: dict[str, Any] = {}


class LLMTelemetryContext(BaseModel):
    session_id: str | None = None
    run_id: str | None = None


def effective_config_for_call(config: ModelConfig) -> ModelConfig:
    updates: dict[str, Any] = {}
    selected_config = config
    return selected_config.model_copy(update=updates)


def effective_temperature(config: ModelConfig) -> float:
    return 0.0


__all__ = [
    "effective_config_for_call",
    "effective_temperature",
    "start_captured_span",
]
'''

EXECUTOR_PRISTINE = '''"""Fixture: minimal shape of honcho v3.6.1 src/llm/executor.py."""
from .runtime import AttemptPlan, effective_config_for_call


def execute_llm_call(effective_config, telemetry, reasoning_effort):
    effective_config = effective_config_for_call(
        effective_config=effective_config,
        telemetry=telemetry,
        reasoning_effort=reasoning_effort,
    )

    # The history is rendered for this attempt's model
    return effective_config
'''


def _load_patch_module() -> ModuleType:
    """Import ``apply_patch.py`` without executing its ``main()``."""
    spec = importlib.util.spec_from_file_location("honcho_apply_patch", PATCH_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # A unique name keeps repeated loads from colliding in ``sys.modules``.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def patch_module() -> ModuleType:
    return _load_patch_module()


@pytest.fixture()
def source_tree(tmp_path: Path) -> Path:
    (tmp_path / "runtime.py").write_text(RUNTIME_PRISTINE, encoding="utf-8")
    (tmp_path / "executor.py").write_text(EXECUTOR_PRISTINE, encoding="utf-8")
    return tmp_path


def _leftover_temps(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir() if p.name.endswith(".patchtmp"))


# --- idempotency ------------------------------------------------------------


def test_plan_covers_both_files_and_every_anchor(patch_module: ModuleType) -> None:
    plan = patch_module.patch_plan(Path("/nowhere"))
    assert [path.name for path, _ in plan] == ["runtime.py", "executor.py"]
    assert sum(len(edits) for _, edits in plan) == 5


def test_patch_applies_every_post_condition_and_is_idempotent(
    patch_module: ModuleType, source_tree: Path
) -> None:
    assert patch_module.apply_patch(source_tree) is True

    runtime = (source_tree / "runtime.py").read_text(encoding="utf-8")
    executor = (source_tree / "executor.py").read_text(encoding="utf-8")

    assert "from typing import Any, Literal, cast" in runtime
    assert "from urllib.parse import urlsplit" in runtime
    assert "def with_opencode_session_header(" in runtime
    assert '    "with_opencode_session_header",\n]' in runtime
    assert "    with_opencode_session_header,\n" in executor
    assert "effective_config = with_opencode_session_header(effective_config, telemetry)" in executor

    snapshot = {
        "runtime.py": (source_tree / "runtime.py").read_bytes(),
        "executor.py": (source_tree / "executor.py").read_bytes(),
    }

    # Second container start: docker restart keeps the layer -> no-op.
    assert patch_module.apply_patch(source_tree) is False
    assert {
        "runtime.py": (source_tree / "runtime.py").read_bytes(),
        "executor.py": (source_tree / "executor.py").read_bytes(),
    } == snapshot
    assert _leftover_temps(source_tree) == []


def test_half_patched_first_file_is_not_reported_as_applied(
    patch_module: ModuleType, source_tree: Path
) -> None:
    """The exact finding: runtime patched, executor untouched.

    A previous run interrupted between the two files must abort loudly, never
    print "already applied" and never boot with a half patch.
    """
    runtime = source_tree / "runtime.py"
    runtime.write_text(
        patch_module._patched_text(runtime, patch_module._RUNTIME_EDITS),
        encoding="utf-8",
    )
    executor_before = (source_tree / "executor.py").read_text(encoding="utf-8")

    with pytest.raises(patch_module.PatchError) as excinfo:
        patch_module.apply_patch(source_tree)

    message = str(excinfo.value)
    assert "partial patch across files" in message
    assert "runtime.py" in message
    assert "executor.py" in message
    assert "already applied" not in message
    assert "force-recreate" in message
    # Nothing was written in the failing run.
    assert (source_tree / "executor.py").read_text(encoding="utf-8") == executor_before
    assert _leftover_temps(source_tree) == []


def test_single_file_with_partial_edits_raises(
    patch_module: ModuleType, source_tree: Path
) -> None:
    """One of runtime.py's three edits applied, the other two missing."""
    runtime = source_tree / "runtime.py"
    only_first = RUNTIME_PRISTINE.replace(
        "from typing import Any, Literal\n",
        "from typing import Any, Literal, cast\nfrom urllib.parse import urlsplit\n",
        1,
    )
    runtime.write_text(only_first, encoding="utf-8")

    with pytest.raises(patch_module.PatchError) as excinfo:
        patch_module.is_applied(runtime, patch_module._RUNTIME_EDITS)

    message = str(excinfo.value)
    assert "partial patch state" in message
    assert "edit(s) [1] applied" in message
    assert "edit(s) [2, 3] missing" in message
    assert (source_tree / "executor.py").read_text(encoding="utf-8") == EXECUTOR_PRISTINE


# --- base-image drift -------------------------------------------------------


def test_changed_base_image_fails_loudly_and_writes_nothing(
    patch_module: ModuleType, source_tree: Path
) -> None:
    (source_tree / "executor.py").write_text(
        EXECUTOR_PRISTINE.replace(
            "from .runtime import AttemptPlan, effective_config_for_call\n", ""
        ),
        encoding="utf-8",
    )

    with pytest.raises(patch_module.PatchError) as excinfo:
        patch_module.apply_patch(source_tree)

    message = str(excinfo.value)
    assert "expected exactly one occurrence of patch anchor" in message
    assert "base image changed?" in message
    # runtime.py was already turned into new text in memory, but staging happens
    # only after every file validated -> the on-disk file is untouched.
    assert (source_tree / "runtime.py").read_text(encoding="utf-8") == RUNTIME_PRISTINE
    assert _leftover_temps(source_tree) == []


def test_missing_source_files_abort(patch_module: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(patch_module.PatchError, match="source file not found"):
        patch_module.apply_patch(tmp_path)


def test_main_exits_with_prefixed_fatal_message(
    patch_module: ModuleType, tmp_path: Path
) -> None:
    patch_module.ROOT = tmp_path
    with pytest.raises(SystemExit) as excinfo:
        patch_module.main()
    code = excinfo.value.code
    assert isinstance(code, str)
    assert code.startswith("[honcho-patch] FATAL:")
    assert "source file not found" in code


# --- atomic writes ----------------------------------------------------------


def test_atomic_write_replaces_content_and_preserves_mode(
    patch_module: ModuleType, tmp_path: Path
) -> None:
    target = tmp_path / "module.py"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o640)

    patch_module.atomic_write(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert _leftover_temps(tmp_path) == []


def test_failed_replace_leaves_original_intact(
    patch_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "module.py"
    target.write_text("old\n", encoding="utf-8")

    def _explode(src: object, dst: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(patch_module.os, "replace", _explode)

    with pytest.raises(OSError, match="simulated rename failure"):
        patch_module.atomic_write(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old\n"
    assert _leftover_temps(tmp_path) == []


def test_failed_write_cleans_up_temp_file(
    patch_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "module.py"
    target.write_text("old\n", encoding="utf-8")

    def _explode(fd: int, *args: object, **kwargs: object) -> object:
        os.close(fd)
        raise OSError("simulated write failure")

    monkeypatch.setattr(patch_module.os, "fdopen", _explode)

    with pytest.raises(OSError, match="simulated write failure"):
        patch_module._stage(target, "new\n")

    assert _leftover_temps(tmp_path) == []


# --- entrypoint shims -------------------------------------------------------


def test_entrypoint_shims_fail_closed_when_mount_is_missing() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert compose.count("if not os.path.isfile(_patch):") == 2, (
        "both honcho and honcho-deriver must refuse to start without the patch"
    )
    assert "if os.path.isfile(_patch):" not in compose, (
        "a silent skip of a missing patch mount is the finding this guards"
    )
    assert compose.count("refusing to start without the fix") == 2
    assert "[honcho] FATAL" in compose
    assert "[honcho-deriver] FATAL" in compose
    # The execution itself is still there (test_deploy_image_pins asserts it too).
    assert compose.count('exec(compile(open(_patch).read(), _patch, "exec"))') == 2
