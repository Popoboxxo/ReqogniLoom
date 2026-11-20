"""Backport of upstream plastic-labs/honcho#1441 onto v3.6.1.

Honcho resolves the operator's ``provider_params.extra_headers.x-opencode-session``
correctly but still drops it on the wire in the Dialectic/DREAM Complete path
(issue #1247). PR #1441 injects the header from the Honcho conversation context
immediately before the provider call instead.

Executed from the entrypoint shim at container start. Idempotent: a
``docker restart`` keeps the container layer, so an already-applied patch is
detected and skipped.

The replacements are intentionally exact and asserted: if the base image
changes, the patch must fail loudly instead of silently targeting a wrong
version. Source: https://github.com/plastic-labs/honcho/pull/1441 (head
7670b6ab559f2389f984a68579e0383d0b62e9f4).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("HONCHO_PATCH_ROOT", "/app/src/llm"))

EXECUTOR = ROOT / "executor.py"
RUNTIME = ROOT / "runtime.py"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(
            f"{path}: expected exactly one occurrence of patch anchor, "
            f"found {text.count(old)} (base image changed?)"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"[honcho-patch] patched {path.name}", flush=True)


def main() -> None:
    if not RUNTIME.is_file() or not EXECUTOR.is_file():
        raise SystemExit(f"[honcho-patch] source files not found under {ROOT}")

    if "def with_opencode_session_header(" in RUNTIME.read_text(encoding="utf-8"):
        print("[honcho-patch] upstream fix #1441 already applied", flush=True)
        return

    # --- runtime.py: imports + function + __all__ --------------------------
    replace_once(
        RUNTIME,
        "from typing import Any, Literal\n",
        "from typing import Any, Literal, cast\nfrom urllib.parse import urlsplit\n",
    )

    replace_once(
        RUNTIME,
        "    return selected_config.model_copy(update=updates)\n\n\ndef effective_temperature(",
        '''    return selected_config.model_copy(update=updates)


def with_opencode_session_header(
    config: ModelConfig,
    telemetry: LLMTelemetryContext | None,
) -> ModelConfig:
    """Use the Honcho conversation ID for OpenCode Go's routing header.

    OpenCode Go requires a stable ``x-opencode-session`` value per conversation.
    Prefer Honcho's canonical session ID; for sessionless calls, use the LLM run
    ID so retries and tool-loop steps in that invocation share one value.
    Operator-configured headers remain the fallback when no ID is available.
    """
    if config.transport != "openai" or config.base_url is None or telemetry is None:
        return config

    parsed_url = urlsplit(config.base_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "opencode.ai"
        or not (parsed_url.path == "/zen/go" or parsed_url.path.startswith("/zen/go/"))
    ):
        return config

    session_id = telemetry.session_id or telemetry.run_id
    if not session_id:
        return config

    provider_params = dict(config.provider_params)
    configured_headers = provider_params.get("extra_headers")
    if configured_headers is not None and not isinstance(configured_headers, dict):
        # Leave malformed operator configuration untouched so the existing
        # request validation reports it rather than silently changing it.
        return config

    headers: dict[str, Any] = cast(dict[str, Any], configured_headers or {})
    headers = {
        key: value
        for key, value in headers.items()
        if key.casefold() != "x-opencode-session"
    }
    headers["x-opencode-session"] = session_id
    provider_params["extra_headers"] = headers
    return config.model_copy(update={"provider_params": provider_params})


def effective_temperature(''',
    )

    replace_once(
        RUNTIME,
        '    "start_captured_span",\n]',
        '    "start_captured_span",\n    "with_opencode_session_header",\n]',
    )

    # --- executor.py: import + call site -----------------------------------
    replace_once(
        EXECUTOR,
        "from .runtime import AttemptPlan, effective_config_for_call\n",
        "from .runtime import (\n"
        "    AttemptPlan,\n"
        "    effective_config_for_call,\n"
        "    with_opencode_session_header,\n"
        ")\n",
    )

    replace_once(
        EXECUTOR,
        """        reasoning_effort=reasoning_effort,
    )

    # The history is rendered for this attempt's model""",
        """        reasoning_effort=reasoning_effort,
    )
    effective_config = with_opencode_session_header(effective_config, telemetry)

    # The history is rendered for this attempt's model""",
    )

    print("[honcho-patch] upstream fix #1441 applied", flush=True)


main()
