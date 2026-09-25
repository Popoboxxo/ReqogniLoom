from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

_REPO_ROOT = Path(os.environ.get("REQLO_REPO_ROOT", Path(__file__).resolve().parents[3]))
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "version-drift-check.yml"

if not _WORKFLOW.is_file():
    pytest.skip(
        "workflow file is not mounted in the backend test image",
        allow_module_level=True,
    )


def _determine_step() -> dict:
    document = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["check-drift"]["steps"]
    return next(step for step in steps if step.get("name") == "Determine deployed URL")


_STEP = _determine_step()
_ENV = _STEP["env"]
_RUN = _STEP["run"]
_DISPATCH_ENV = next(
    key for key, value in _ENV.items() if "github.event.inputs.deployed_url" in value
)
_SECRET_ENV = next(
    key for key, value in _ENV.items() if "secrets.DEPLOYED_VERSION_URL" in value
)


def _execute(tmp_path: Path, dispatch: str, secret: str):
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            _DISPATCH_ENV: dispatch,
            _SECRET_ENV: secret,
            "GITHUB_OUTPUT": output.as_posix(),
        }
    )
    if os.name == "nt":
        environment["WSLENV"] = f"{_DISPATCH_ENV}:{_SECRET_ENV}:GITHUB_OUTPUT/p"
    command = (
        ["wsl.exe", "bash", "-euo", "pipefail"]
        if os.name == "nt"
        else ["bash", "-euo", "pipefail"]
    )
    completed = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        input=_RUN.encode("utf-8"),
        capture_output=True,
        timeout=20,
        check=False,
    )
    result = SimpleNamespace(
        returncode=completed.returncode,
        stdout=completed.stdout.decode("utf-8", errors="replace"),
        stderr=completed.stderr.decode("utf-8", errors="replace"),
    )
    return result, output.read_text(encoding="utf-8"), (tmp_path / "sentinel").exists()


def test_deployed_url_expressions_are_bound_only_as_step_environment() -> None:
    assert "${{" not in _RUN
    expressions = {str(value) for value in _ENV.values() if "${{" in str(value)}
    assert expressions == {
        "${{ github.event.inputs.deployed_url }}",
        "${{ secrets.DEPLOYED_VERSION_URL }}",
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/api/v1/version/",
        "https://example.com:8443/api/v1/version/",
    ],
)
def test_valid_https_url_is_forwarded_to_github_output(tmp_path, url):
    result, output, sentinel = _execute(tmp_path, url, "")

    assert result.returncode == 0, result.stderr
    assert output == f"url={url}\nskip=false\n"
    assert sentinel is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a b",
        "https://example.com/a\tb",
        "https://example.com:99999/api/v1/version/",
        "https:///api/v1/version/",
        "https://-bad.example/api/v1/version/",
        "https://example.com/\"; touch sentinel; #",
        "https://example.com/; touch sentinel",
        "https://example.com/\n touch sentinel",
        "https://example.com/\r touch sentinel",
        "https://example.com/>sentinel",
        "https://example.com/$(touch sentinel)",
        "https://example.com/`touch sentinel`",
        "https://example.com/%3Btouch%20sentinel",
        "https://127.0.0.1:9443/api/v1/version/",
        "https://[::1]:9443/api/v1/version/",
        "https://10.0.0.1/api/v1/version/",
        "https://192.168.1.1/api/v1/version/",
        "https://172.16.0.1/api/v1/version/",
        "https://169.254.169.254/api/v1/version/",
        "https://[::ffff:127.0.0.1]/api/v1/version/",
        "https://localhost/api/v1/version/",
        "https://localhost.localdomain/api/v1/version/",
    ],
)
def test_invalid_deployed_url_fails_without_output_or_command_execution(tmp_path, url):
    result, output, sentinel = _execute(tmp_path, url, "")

    assert result.returncode == 1
    assert output == ""
    assert sentinel is False


def test_secret_fallback_is_validated(tmp_path):
    result, output, sentinel = _execute(
        tmp_path,
        "",
        "https://secret.example/api/v1/version/",
    )

    assert result.returncode == 0, result.stderr
    assert output == "url=https://secret.example/api/v1/version/\nskip=false\n"
    assert sentinel is False


def test_secret_crlf_is_rejected_when_used(tmp_path):
    result, output, sentinel = _execute(
        tmp_path,
        "",
        "https://secret.example/api/v1/version/\r\n",
    )

    assert result.returncode == 1
    assert output == ""
    assert sentinel is False


def test_dispatch_input_has_priority_over_secret(tmp_path):
    dispatch = "https://dispatch.example/api/v1/version/"
    result, output, sentinel = _execute(
        tmp_path,
        dispatch,
        "https://secret.example/\r\n",
    )

    assert result.returncode == 0, result.stderr
    assert output == f"url={dispatch}\nskip=false\n"
    assert sentinel is False


def test_empty_configuration_skips_without_output_url(tmp_path):
    result, output, sentinel = _execute(tmp_path, "", "")

    assert result.returncode == 0, result.stderr
    assert output == "skip=true\n"
    assert sentinel is False
