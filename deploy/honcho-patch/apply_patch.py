"""Backport of upstream plastic-labs/honcho#1441 onto v3.6.1.

Honcho resolves the operator's ``provider_params.extra_headers.x-opencode-session``
correctly but still drops it on the wire in the Dialectic/DREAM Complete path
(issue #1247). PR #1441 injects the header from the Honcho conversation context
immediately before the provider call instead.

Executed from the entrypoint shim at container start. Idempotent: a
``docker restart`` keeps the container layer, so an already-applied patch is
detected and skipped.

Integrity rules (security audit finding #1 — CWE-664):

* Idempotency is evaluated **per file and per edit**. The patch is applied only
  when *none* of the post-conditions hold; when *all* of them hold the run is a
  no-op. Any other combination is a **partial patch** and aborts with a message
  that says so — a half-applied patch must never be reported as "already
  applied" (that would leave the container running while the header is still
  dropped on the wire).
* Writes are atomic: the new content goes to a temp file in the same directory
  and is moved into place with ``os.replace``, so a SIGTERM mid-write cannot
  leave a truncated source file behind. Both files are staged before the first
  ``os.replace`` to keep the cross-file window as small as possible.

The replacements are intentionally exact and asserted: if the base image
changes, the patch must fail loudly instead of silently targeting a wrong
version. Source: https://github.com/plastic-labs/honcho/pull/1441 (head
7670b6ab559f2389f984a68579e0383d0b62e9f4).
"""
from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

ROOT = Path(os.environ.get("HONCHO_PATCH_ROOT", "/app/src/llm"))

LOG_PREFIX = "[honcho-patch]"

_RECREATE_HINT = (
    "Recreate the container (docker compose up -d --force-recreate <service>) "
    "so the patched image layer is discarded and the backport can run again."
)


class PatchError(RuntimeError):
    """The base image does not match the anchors this backport expects."""


class Edit(NamedTuple):
    """One exact-text replacement inside a single source file."""

    old: str
    new: str


_RUNTIME_EDITS: tuple[Edit, ...] = (
    Edit(
        old="from typing import Any, Literal\n",
        new="from typing import Any, Literal, cast\nfrom urllib.parse import urlsplit\n",
    ),
    Edit(
        old="    return selected_config.model_copy(update=updates)\n\n\ndef effective_temperature(",
        new='''    return selected_config.model_copy(update=updates)


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
    ),
    Edit(
        old='    "start_captured_span",\n]',
        new='    "start_captured_span",\n    "with_opencode_session_header",\n]',
    ),
)

_EXECUTOR_EDITS: tuple[Edit, ...] = (
    Edit(
        old="from .runtime import AttemptPlan, effective_config_for_call\n",
        new="from .runtime import (\n"
        "    AttemptPlan,\n"
        "    effective_config_for_call,\n"
        "    with_opencode_session_header,\n"
        ")\n",
    ),
    Edit(
        old="""        reasoning_effort=reasoning_effort,
    )

    # The history is rendered for this attempt's model""",
        new="""        reasoning_effort=reasoning_effort,
    )
    effective_config = with_opencode_session_header(effective_config, telemetry)

    # The history is rendered for this attempt's model""",
    ),
)


def patch_plan(root: Path = ROOT) -> tuple[tuple[Path, tuple[Edit, ...]], ...]:
    """Return ``(path, edits)`` pairs in application order."""
    return (
        (root / "runtime.py", _RUNTIME_EDITS),
        (root / "executor.py", _EXECUTOR_EDITS),
    )


def is_applied(path: Path, edits: Sequence[Edit]) -> bool:
    """True when *every* post-condition of ``edits`` already holds in ``path``.

    Raises ``PatchError`` for the mixed state: some post-conditions hold while
    others do not. That is a half-applied file, and reporting it as "already
    applied" is exactly the failure mode this function exists to rule out.
    """
    text = path.read_text(encoding="utf-8")
    states = [edit.new in text for edit in edits]
    if all(states):
        return True
    if any(states):
        present = [i for i, done in enumerate(states, start=1) if done]
        missing = [i for i, done in enumerate(states, start=1) if not done]
        raise PatchError(
            f"{path}: partial patch state — edit(s) {present} applied, "
            f"edit(s) {missing} missing. The container layer holds a half-applied "
            f"patch, so the #1441 fix cannot be trusted to be active. "
            f"{_RECREATE_HINT}"
        )
    return False


def _patched_text(path: Path, edits: Sequence[Edit]) -> str:
    """Return ``path``'s content with ``edits`` applied, anchors verified."""
    text = path.read_text(encoding="utf-8")
    for position, edit in enumerate(edits, start=1):
        found = text.count(edit.old)
        if found != 1:
            raise PatchError(
                f"{path}: expected exactly one occurrence of patch anchor "
                f"#{position}, found {found} (base image changed?) {_RECREATE_HINT}"
            )
        text = text.replace(edit.old, edit.new, 1)
    return text


def _stage(path: Path, content: str) -> Path:
    """Write ``content`` to a temp file next to ``path`` and return its path.

    The original file mode is preserved: the patched modules must keep whatever
    read permissions the vendor image gave them (a bare ``mkstemp`` file is
    ``0600``, which would break a non-root application process).
    """
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".patchtmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def atomic_write(path: Path, content: str) -> None:
    """Replace ``path`` with ``content`` atomically (temp file + ``os.replace``)."""
    tmp = _stage(path, content)
    try:
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def apply_patch(root: Path | None = None) -> bool:
    """Apply the backport under ``root`` (default: the module's ``ROOT``).

    Returns ``True`` when the patch was written and ``False`` when it was
    already fully present. Raises ``PatchError`` for a missing source file, a
    changed base image, or *any* partial state (single file or across files).
    """
    root = ROOT if root is None else root
    plan = patch_plan(root)

    for path, _ in plan:
        if not path.is_file():
            raise PatchError(
                f"{path}: source file not found — check HONCHO_PATCH_ROOT "
                f"(expected {root}) and the pinned base image."
            )

    already: list[Path] = []
    pending: dict[Path, str] = {}
    for path, edits in plan:
        if is_applied(path, edits):
            already.append(path)
        else:
            pending[path] = _patched_text(path, edits)

    if not pending:
        print(f"{LOG_PREFIX} upstream fix #1441 already applied", flush=True)
        return False

    if already:
        # One file is fully patched while another is not: the previous run was
        # interrupted between the two files (the exact state that used to be
        # reported as success). Finish nothing; abort loudly instead. The
        # wording avoids the success log line verbatim so an operator or a
        # monitoring grep for it cannot mistake this for a healthy start.
        raise PatchError(
            f"partial patch across files — patched: "
            f"{', '.join(p.name for p in already)}; unpatched: "
            f"{', '.join(p.name for p in pending)}. The #1441 fix is NOT fully "
            f"active. {_RECREATE_HINT}"
        )

    staged: list[tuple[Path, Path]] = []
    try:
        for path, text in pending.items():
            staged.append((path, _stage(path, text)))
        for path, tmp in staged:
            os.replace(tmp, path)
            print(f"{LOG_PREFIX} patched {path.name}", flush=True)
    except BaseException:
        for _, tmp in staged:
            tmp.unlink(missing_ok=True)
        raise

    print(f"{LOG_PREFIX} upstream fix #1441 applied", flush=True)
    return True


def main() -> None:
    try:
        apply_patch()
    except (PatchError, OSError) as exc:
        raise SystemExit(f"{LOG_PREFIX} FATAL: {exc}") from exc


if __name__ == "__main__":
    main()
