"""Deploy-contract guard for the optional Honcho memory profile (issue #1153).

This module locks the *deployment wiring* of the optional ``honcho`` Compose
profile against the failure mode that caused #1153. The root cause was NOT a
repo-code bug: the compose wiring already reaches the SDK parameters correctly.
The defect was that ``ghcr.io/plastic-labs/honcho:latest`` is a MOVING tag, so a
host could silently pull a different (stale/updated) image than the one the
stack was verified against — the engine then failed to send the required
``x-opencode-session`` header even though every compose line was correct.

The guard therefore pins three invariants of ``deploy/docker-compose.yml``:

1. the shared ``x-honcho-env`` anchor still defines ``LLM_OPENCODE_SESSION``
   (the single deployment-wide session value);
2. BOTH engine processes that read it — ``honcho`` and ``honcho-deriver`` —
   still run the entrypoint shim that materialises the nine dashed
   ``…__EXTRA_HEADERS__x-opencode-session`` variables the engine resolves into
   the ``extra_headers`` SDK kwarg (Docker itself drops dashed env names);
3. all THREE services that run the Honcho image (``honcho``, ``honcho-deriver``,
   ``honcho-migrate``) reference the SAME ``:latest@sha256:…`` immutable image,
   so they cannot drift apart and the "verified against this image" claim in the
   compose comments stays reproducible.

It is deliberately Docker-free and Django-free so it runs on the host with::

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \\
        memory/tests/test_honcho_deploy_contract.py -q

PyYAML is required, but only transitively (via drf-spectacular) — it is not a
direct dependency. A live check that the pinned image resolves the dashed value
into ``sdk_params["extra_headers"]`` is provided separately as an opt-in
``integration`` test.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest
import yaml

# backend/memory/tests/test_honcho_deploy_contract.py -> repo root is parents[3].
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEPLOY_COMPOSE = _REPO_ROOT / "deploy" / "docker-compose.yml"

# HOST-ONLY guard: the Django test suite runs inside the ``backend`` container,
# where the repo's ``deploy/`` directory is NOT mounted into the image. There the
# compose file is unreachable, and this module must SKIP rather than error (it
# asserts on the host checkout, not on the deployed image). ``allow_module_level``
# keeps the skip from being reported as a collection error.
if not _DEPLOY_COMPOSE.is_file():
    pytest.skip(
        f"deploy/docker-compose.yml not found at {_DEPLOY_COMPOSE} — "
        "host-only deploy-contract guard",
        allow_module_level=True,
    )

#: The assignment that actually materialises one header env var in the shim.
#: Matched whitespace-tolerantly so a reformat of the embedded Python block does
#: not silently defang the guard; the *write* is what turns the module list into
#: env vars, so pinning it (not just the list) is the point.
_HEADER_WRITE_RE = re.compile(
    r"os\.environ\s*\[\s*module\s*\+\s*SUFFIX\s*\]\s*=\s*session"
)

#: The three services that run the Honcho image and must share one digest.
_HONCHO_IMAGE_SERVICES = ("honcho", "honcho-deriver", "honcho-migrate")

#: The two long-running engine processes that must both run the session shim.
_HONCHO_SHIM_SERVICES = ("honcho", "honcho-deriver")

#: The per-module env-var suffix the shim appends to every engine module prefix.
_SESSION_HEADER_SUFFIX = (
    "MODEL_CONFIG__OVERRIDES__PROVIDER_PARAMS__EXTRA_HEADERS__x-opencode-session"
)

#: Explicit module prefixes the shim writes the session suffix for.
_EXPLICIT_MODULE_PREFIXES = (
    "DERIVER_",
    "SUMMARY_",
    "DREAM_INDUCTION_",
    "DREAM_DEDUCTION_",
)

#: Dialectic module prefixes are composed from a format string + these levels.
_DIALECTIC_LEVELS = ("minimal", "low", "medium", "high", "max")
_DIALECTIC_PREFIX_TEMPLATE = "DIALECTIC_LEVELS__{}__"

#: The verified-good immutable digest for the current ``:latest`` image (#1153).
_EXPECTED_DIGEST = (
    "sha256:350b778af29b8b5b0b9a5b5436a00ea912acc7490908a9cb4fb7d80fa963e5c2"
)
_EXPECTED_IMAGE = f"ghcr.io/plastic-labs/honcho:latest@{_EXPECTED_DIGEST}"


def _load_compose() -> dict:
    """Parse ``deploy/docker-compose.yml`` with the safe loader.

    Uses ``yaml.safe_load`` so the top-level ``x-honcho-env`` anchor is resolved
    into the ``honcho`` / ``honcho-deriver`` service mappings exactly as Compose
    reads it, and ``dashed`` keys survive (Compose ignores ``x-`` fields as
    configuration but they are still plain YAML here).
    """
    with _DEPLOY_COMPOSE.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _command_text(service: dict) -> str:
    """Join a service's ``entrypoint`` + ``command`` into one searchable string.

    The shim is a list containing a single block scalar, but flattening any
    list/str shape keeps the guard robust if a future edit switches to the
    list or shell form.
    """
    parts: list[str] = []
    for key in ("entrypoint", "command"):
        value = service.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            parts.append(value)
        else:
            parts.extend(str(item) for item in value)
    return "\n".join(parts)


def _normalise_whitespace(text: str) -> str:
    """Collapse the block scalar's indentation/newlines into single spaces.

    The shim is an indented YAML block scalar, so a raw read carries the literal
    line breaks and indentation; normalising lets the guard match whole Python
    statements regardless of how the block is formatted.
    """
    return re.sub(r"\s+", " ", text).strip()


def _missing_module_references(text: str) -> list[str]:
    """Return the module prefixes whose reference is absent from ``text``.

    The four explicit prefixes are literal in the shim. The five dialectic
    prefixes are composed at runtime from ``DIALECTIC_LEVELS__{}__`` and the
    level tuple, so their guard checks the format skeleton plus every level
    token — together these pin all nine resolved names (the alternative, faking
    the fully-composed strings, would not match the source).
    """
    missing = [prefix for prefix in _EXPLICIT_MODULE_PREFIXES if prefix not in text]
    if _DIALECTIC_PREFIX_TEMPLATE not in text:
        missing.append(_DIALECTIC_PREFIX_TEMPLATE)
    for level in _DIALECTIC_LEVELS:
        token = f'"{level}"'
        if token not in text:
            missing.append(f"{level} level token")
    return missing


def test_x_honcho_env_defines_the_session_value() -> None:
    """The shared anchor must still carry ``LLM_OPENCODE_SESSION``."""
    compose = _load_compose()
    env = compose.get("x-honcho-env")
    assert isinstance(env, dict), "top-level x-honcho-env anchor is missing"
    assert "LLM_OPENCODE_SESSION" in env, (
        "x-honcho-env no longer defines LLM_OPENCODE_SESSION; the session header "
        "cannot be derived (see #1050/#1051)"
    )


@pytest.mark.parametrize("service_name", _HONCHO_SHIM_SERVICES)
def test_entrypoint_shim_materialises_all_nine_session_headers(service_name: str) -> None:
    """Both engine processes must run the shim for all nine module prefixes."""
    service = _load_compose()["services"][service_name]
    text = _command_text(service)
    assert _SESSION_HEADER_SUFFIX in text, (
        f"{service_name}: entrypoint/command no longer references the session "
        f"suffix {_SESSION_HEADER_SUFFIX!r}"
    )
    missing = _missing_module_references(text)
    assert missing == [], (
        f"{service_name}: shim no longer covers module prefix(es) {missing!r} — "
        "a half-configured engine answers reads while every write dies"
    )
    normalised = _normalise_whitespace(text)
    assert "module + SUFFIX" in normalised, (
        f"{service_name}: shim no longer composes `module + SUFFIX` — the list "
        "above is inert without the per-module env-var name"
    )
    assert _HEADER_WRITE_RE.search(normalised) is not None, (
        f"{service_name}: shim lists the module prefixes but no longer WRITES "
        "them — `os.environ[module + SUFFIX] = session` is gone, so the engine "
        "never sees the session header and every write dies (#1153)"
    )


@pytest.mark.parametrize("service_name", _HONCHO_IMAGE_SERVICES)
def test_honcho_image_is_pinned_to_the_expected_digest(service_name: str) -> None:
    """Every Honcho service must pin the exact ``:latest@sha256:`` reference."""
    image = _load_compose()["services"][service_name]["image"]
    assert "@sha256:" in image, (
        f"{service_name}: image {image!r} is not digest-pinned; a moving :latest "
        "tag is exactly the #1153 failure mode"
    )
    assert image.endswith(_EXPECTED_DIGEST), (
        f"{service_name}: image digest drift — expected {_EXPECTED_IMAGE!r}, got {image!r}"
    )


def test_all_honcho_services_share_one_pinned_image() -> None:
    """All three services must reference one identical image so they cannot drift."""
    compose = _load_compose()
    images = {
        name: compose["services"][name]["image"] for name in _HONCHO_IMAGE_SERVICES
    }
    assert len(set(images.values())) == 1, (
        f"Honcho services reference different images: {images!r} — migrate, API and "
        "deriver must run the same build"
    )


@pytest.mark.integration
def test_pinned_image_resolves_opencode_session_sdk_param() -> None:
    """Live (opt-in) check that the pinned image yields the ``extra_headers`` kwarg.

    SKIPPED by default. A faithful live spike cannot run in-process here: the
    resolution happens inside the pinned SERVER image (its model-config resolver
    turns the nine dashed env names into the SDK's ``extra_headers`` kwarg), which
    cannot be imported on the host without pulling and running the image. Rather
    than fake the assertion, this test gates on Docker + ``honcho-ai`` being
    present and then skips; the real evidence is the manual spike below.

    Exact manual spike command (run from the repo root); a green run prints the
    session value the engine will send::

        LLM_OPENCODE_SESSION=spike \\
        docker compose -f deploy/docker-compose.yml --project-directory . \\
          --profile honcho run --rm --entrypoint /app/.venv/bin/python honcho -c \
          'import os
           SUFFIX="MODEL_CONFIG__OVERRIDES__PROVIDER_PARAMS__EXTRA_HEADERS__x-opencode-session"
           for m in ["DERIVER_","SUMMARY_","DREAM_INDUCTION_","DREAM_DEDUCTION_"] + [
               "DIALECTIC_LEVELS__{}__".format(l)
               for l in ("minimal","low","medium","high","max")]:
               os.environ[m+SUFFIX] = os.environ["LLM_OPENCODE_SESSION"]
           from src.config import settings
           sdk_params = settings.DERIVER_MODEL_CONFIG.overrides.provider_params
           assert sdk_params["extra_headers"]["x-opencode-session"] == "spike"
           print("OK", sdk_params["extra_headers"]["x-opencode-session"])'

    The import above resolves against the DIGEST-pinned image, so once the digest
    is fixed the spike is reproducible across hosts.
    """
    if shutil.which("docker") is None:
        pytest.skip(
            "Docker not available; run the manual spike documented in this "
            "test's docstring."
        )
    if importlib.util.find_spec("honcho") is None:
        pytest.skip(
            "honcho-ai not importable on this host; run the manual spike "
            "documented in this test's docstring."
        )
    pytest.skip(
        "Live spike is not automated in-process (see docstring for the exact "
        "manual command); no assertion is faked here."
    )
