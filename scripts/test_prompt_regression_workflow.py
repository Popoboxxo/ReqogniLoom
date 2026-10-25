"""Workflow contract for the ``prompt-regression`` CI job (plan D / D2.4, QR-S12).

``scripts/test_*.py`` runs in no CI job by default (RB-D18), so this file is
wired into ``agent-templates-test`` in the same PR. It pins the supply-chain and
trigger properties that make the job safe to run on every PR:

* no path filter — a path-filtered Required Check would stay "pending" on PRs
  that do not touch the prompt files (index §f.2),
* least privilege: ``contents: read``, no ``secrets.*`` anywhere in the job and
  ``persist-credentials: false`` on checkout,
* an exact, lockfile-installed toolchain: ``npm ci --ignore-scripts`` and no
  ``npx`` (which would fetch an unpinned package at run time).

Stdlib + PyYAML only; runs from the repo root.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

JOB_NAME = "prompt-regression"
CONTRACT_TEST = "scripts/test_prompt_regression_workflow.py"


def _load_ci() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def _job() -> dict[str, Any]:
    jobs = _load_ci().get("jobs") or {}
    assert JOB_NAME in jobs, f"job {JOB_NAME!r} is missing from ci.yml"
    return jobs[JOB_NAME]


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return job.get("steps") or []


def _walk(node: Any) -> Iterator[Any]:
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _runs(job: dict[str, Any]) -> list[str]:
    return [
        step["run"]
        for step in _steps(job)
        if isinstance(step.get("run"), str)
    ]


def test_job_exists_and_has_no_path_filter():
    """Every push/PR must produce a verdict, not a pending Required Check."""
    job = _job()

    assert "if" not in job or "paths" not in json.dumps(job["if"])
    assert all(
        "paths" not in node for node in _walk(job) if isinstance(node, dict)
    ), "prompt-regression must not be path-filtered (index §f.2)"


def test_job_has_least_privilege_and_no_secrets():
    job = _job()

    assert job.get("permissions") == {"contents": "read"}
    assert "secrets." not in json.dumps(job)


def test_checkout_does_not_persist_credentials():
    job = _job()

    checkouts = [
        step
        for step in _steps(job)
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert checkouts, "prompt-regression must check out the repository"
    assert checkouts[0].get("with", {}).get("persist-credentials") is False


def test_promptfoo_comes_from_the_lockfile_without_npx():
    job = _job()
    runs = "\n".join(_runs(job))

    assert "npm ci" in runs
    assert "--ignore-scripts" in runs
    assert "npx" not in runs, "npx would resolve an unpinned package at run time"


def test_exports_the_case_set_and_evaluates_the_generated_configs():
    job = _job()
    runs = "\n".join(_runs(job))

    assert "export_promptfoo_configs --check" in runs
    assert "export_promptfoo_configs --out" in runs
    assert "promptfoo eval" in runs
    assert "promptfoo/generated" in runs


def test_eval_disables_templating_telemetry_and_update_checks():
    job = _job()

    eval_step = next(
        step
        for step in _steps(job)
        if "promptfoo eval" in str(step.get("run", ""))
    )
    env = eval_step.get("env") or {}

    assert env.get("PROMPTFOO_DISABLE_TEMPLATING") == "true"
    assert env.get("PROMPTFOO_DISABLE_TELEMETRY") == "1"
    assert env.get("PROMPTFOO_DISABLE_UPDATE") == "1"


def test_artifacts_are_uploaded_even_when_the_eval_fails():
    job = _job()

    uploads = [
        step
        for step in _steps(job)
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert uploads, "the generated configs and results must be uploaded"
    assert uploads[0].get("if") == "always()"


def test_contract_test_is_wired_into_agent_templates_test():
    """RB-D18: a bare ``scripts/test_*.py`` file would never run in CI."""
    jobs = _load_ci().get("jobs") or {}
    run_lines = "\n".join(
        str(step.get("run", ""))
        for step in jobs.get("agent-templates-test", {}).get("steps", [])
    )

    assert CONTRACT_TEST in run_lines
