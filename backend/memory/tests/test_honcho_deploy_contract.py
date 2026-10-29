"""Deploy-contract guard for the optional Honcho memory profile (issue #1153).

This module locks the *deployment wiring* of the optional ``honcho`` Compose
profile against the failure mode that caused #1153. The root cause was NOT a
repo-code bug: the compose wiring already reaches the SDK parameters correctly.
The defect was that ``ghcr.io/plastic-labs/honcho:latest`` is a MOVING tag, so a
host could silently pull a different (stale/updated) image than the one the
stack was verified against — the engine then failed to send the required
``x-opencode-session`` header even though every compose line was correct.

The guard therefore pins four invariants of ``deploy/docker-compose.yml``:

1. the shared ``x-honcho-env`` anchor still defines ``LLM_OPENCODE_SESSION``
   (the single deployment-wide session value);
2. BOTH engine processes that read it — ``honcho`` and ``honcho-deriver`` —
   still run the entrypoint shim that materialises the nine dashed
   ``…__EXTRA_HEADERS__x-opencode-session`` variables the engine resolves into
   the ``extra_headers`` SDK kwarg. The shim is retained deliberately: Docker
   29.8.1 preserves dashed env names (#1187), so it is not required on that
   version, but it is harmless and keeps the config portable to older Docker
   versions and other runtimes;
3. all THREE services that run the Honcho image (``honcho``, ``honcho-deriver``,
   ``honcho-migrate``) reference the SAME ``vX.Y.Z@sha256:…`` immutable image,
   so they cannot drift apart and the "verified against this image" claim in the
   compose comments stays reproducible; a stable release tag (never ``latest``)
   names the running version (#1315);
4. every long-running service declares a keep-alive ``restart`` policy, while
   the one-shot services (``bluepencil-volume-init``, ``migrate``,
   ``llm-preflight``, ``honcho-migrate``) stay at Compose's default ``no``
   (#1249, #1418). Before this guard the three Honcho
   runtime services — ``honcho``, ``honcho-postgres``, ``honcho-redis`` — had
   NO policy at all, so a crash or host reboot left the optional memory backend
   silently down while ``up`` still reported the stack as started.

It additionally pins one invariant that needs no compose file at all:

5. ``honcho-ai`` carries the SAME exact pin in ``requirements.txt`` (what the
   image installs) and ``requirements.lock`` (the documented resolved closure).
   The two drifted apart silently — ``requirements.txt`` pinned 2.5.1 while the
   lock still said 2.3.0 — which makes a CVE check against the lock able to
   clear a client version that is not the one deployed (ADR-023 AC-SDK).

6. every Honcho service resolves its embedding model and width from ONE source:
   an explicit ``HONCHO_EMBEDDING_*`` override, else the deployment-wide
   ``EMBEDDING_MODEL_NAME`` / ``EMBEDDING_VECTOR_DIMENSIONS`` the app itself
   embeds with. Two independent default sets let a provider switch leave Honcho
   embedding at a different width than the app stores, which surfaces as
   rejected or useless memory vectors rather than as a config error.

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

#: The Django project root (``backend/``): ``parents[0]`` is ``tests/``,
#: ``parents[1]`` ``memory/``, ``parents[2]`` ``backend/``. It resolves to
#: ``/app`` inside the test container (only ``./backend`` is bind-mounted) and to
#: ``<repo>/backend`` on the host, so the requirements pins below are readable in
#: BOTH environments — unlike ``deploy/``, which exists only on a host checkout.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REQUIREMENTS_TXT = _BACKEND_DIR / "requirements.txt"
_REQUIREMENTS_LOCK = _BACKEND_DIR / "requirements.lock"

#: The optional external-memory SDK whose pin must agree across both files.
_SDK_NAME = "honcho-ai"
_SDK_PIN_RE = re.compile(
    rf"^\s*{re.escape(_SDK_NAME)}\s*==\s*([^\s;#]+)", re.MULTILINE
)

# ``deploy/`` is NOT mounted into the test container, so every compose-based
# guard below SKIPS there rather than erroring (it asserts on the host checkout,
# not on the deployed image). The skip is deliberately per-test via
# ``_load_compose`` instead of ``allow_module_level``: a module-level skip would
# also suppress the requirements-pin guard, which is readable in the container
# and must therefore fail there — a skipped test is not a green test.

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

#: Services that run to completion and MUST stay at Compose's default
#: ``restart: "no"``. Auto-restarting one of these would re-run schema
#: migrations / the preflight probe in a loop, so they are excluded from the
#: keep-alive contract below (#1249). ``bluepencil-volume-init`` is the same
#: shape: a one-shot ``chown`` of the shared review-notes volume that exits after
#: it has fixed ownership (#1418).
_ONE_SHOT_SERVICES = frozenset(
    {"bluepencil-volume-init", "migrate", "llm-preflight", "honcho-migrate"}
)

#: Every service that runs the Honcho image and therefore resolves an embedding
#: configuration. ``honcho`` and ``honcho-deriver`` share one definition through
#: the ``x-honcho-env`` anchor, ``honcho-migrate`` declares its own block; all
#: three must still resolve the SAME model and width, so the guard below checks
#: each service mapping after YAML alias resolution rather than the source text.
_HONCHO_EMBEDDING_SERVICES = ("honcho", "honcho-deriver", "honcho-migrate")

#: Services that only read the *raw* Honcho embedding vars for the
#: ``memory_backend`` health probe (#911). The width has to be visible on this
#: side too: a probe that can see the model but not the dimension cannot tell a
#: working setup from a width mismatch.
_HONCHO_EMBEDDING_PROBE_SERVICES = ("backend", "celery")

#: The one-source expressions. ``${HONCHO_EMBEDDING_X:-${EMBEDDING_X:-default}}``
#: means: an explicit Honcho override wins, otherwise the deployment-wide
#: embedding setting is inherited, otherwise Honcho's own default applies. Before
#: this the two configurations were independent, so a provider switch silently
#: left Honcho embedding into different vectors than the app stores.
_HONCHO_MODEL_EXPR = (
    "${HONCHO_EMBEDDING_MODEL:-${EMBEDDING_MODEL_NAME:-nomic-embed-text}}"
)
_HONCHO_DIMENSIONS_EXPR = (
    "${HONCHO_EMBEDDING_VECTOR_DIMENSIONS:-${EMBEDDING_VECTOR_DIMENSIONS:-768}}"
)
#: The base URL is deliberately NOT nested: Honcho always needs the ``/v1``
#: suffix, so inheriting the app's bare Ollama URL would break every write.
_HONCHO_BASE_URL_EXPR = (
    "${HONCHO_EMBEDDING_BASE_URL:-http://host.docker.internal:11434/v1}"
)

#: Policies that keep a long-running service alive across a crash / host reboot.
#: ``unless-stopped`` is the project-wide default; the others are accepted so a
#: deliberate, stronger choice is not blocked.
_RUNTIME_RESTART_POLICIES = frozenset({"unless-stopped", "always", "on-failure"})

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

#: The released tag the stack is verified against (#1315): a stable anchor,
#: unlike the moving ``latest``/``staging`` tags.
_EXPECTED_TAG = "v3.3.0"
#: The manifest-list digest of that release (#1153).
_EXPECTED_DIGEST = (
    "sha256:5bb8cf7a60845e08f83fed66f01907afa0969dd1d02e414ed576102f3b12dfe8"
)
_EXPECTED_IMAGE = (
    f"ghcr.io/plastic-labs/honcho:{_EXPECTED_TAG}@{_EXPECTED_DIGEST}"
)


def _load_compose() -> dict:
    """Parse ``deploy/docker-compose.yml`` with the safe loader.

    Uses ``yaml.safe_load`` so the top-level ``x-honcho-env`` anchor is resolved
    into the ``honcho`` / ``honcho-deriver`` service mappings exactly as Compose
    reads it, and ``dashed`` keys survive (Compose ignores ``x-`` fields as
    configuration but they are still plain YAML here).

    Skips when the file is absent: the test container bind-mounts only
    ``./backend`` and ``./docs``, so ``deploy/`` is a host-only artifact.
    """
    if not _DEPLOY_COMPOSE.is_file():
        pytest.skip(
            f"deploy/docker-compose.yml not found at {_DEPLOY_COMPOSE} — "
            "host-only deploy-contract guard"
        )
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
    """Every Honcho service must pin the exact release-tag@sha256 reference."""
    image = _load_compose()["services"][service_name]["image"]
    assert "@sha256:" in image, (
        f"{service_name}: image {image!r} is not digest-pinned; a moving tag "
        "is exactly the #1153 failure mode"
    )
    assert image == _EXPECTED_IMAGE, (
        f"{service_name}: image drift — expected {_EXPECTED_IMAGE!r}, got {image!r}"
    )


def test_honcho_image_uses_a_release_tag_not_latest() -> None:
    """A digest alone is not a version anchor (#1315).

    ``latest``/``staging`` are moving tags; a bare ``sha256:…`` is unreadable.
    The reference must carry a released ``vX.Y.Z`` tag so "which version runs?"
    is answerable without ``docker inspect``.
    """
    image = _load_compose()["services"]["honcho"]["image"]
    tag = image.split(":", 2)[1].split("@", 1)[0]
    assert tag not in {"latest", "staging"}, (
        f"honcho: image {image!r} uses the moving tag {tag!r}; pin a released "
        "vX.Y.Z tag (#1315)"
    )
    assert re.fullmatch(r"v\d+\.\d+\.\d+", tag), (
        f"honcho: image tag {tag!r} is not a stable vX.Y.Z release tag (#1315)"
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


def test_all_runtime_services_have_a_keep_alive_restart_policy() -> None:
    """Every long-running service must declare a keep-alive restart policy (#1249).

    A runtime service with no ``restart`` policy stays down after a crash or a
    host reboot, yet ``docker compose up`` still reports the stack as started —
    the user sees a green deploy with a dead service. Before #1249 the optional
    Honcho memory backend had exactly this gap (``honcho``, ``honcho-postgres``
    and ``honcho-redis`` carried no policy while only ``honcho-deriver`` did).
    One-shot services are deliberately excluded: restarting them would re-run
    migrations or the preflight probe in a loop.
    """
    compose = _load_compose()
    offenders = [
        f"{name}={service.get('restart')!r}"
        for name, service in compose["services"].items()
        if name not in _ONE_SHOT_SERVICES
        and service.get("restart") not in _RUNTIME_RESTART_POLICIES
    ]
    assert offenders == [], (
        "runtime service(s) without a keep-alive restart policy: "
        f"{offenders!r} — a crash or host reboot leaves them silently down "
        "while `up` still reports the stack as started (#1249)"
    )


@pytest.mark.parametrize("service_name", sorted(_ONE_SHOT_SERVICES))
def test_one_shot_services_are_not_auto_restarted(service_name: str) -> None:
    """One-shot services must NOT be auto-restarted (#1249).

    ``bluepencil-volume-init``, ``migrate``, ``llm-preflight`` and
    ``honcho-migrate`` run to completion and exit; any policy other than ``no``
    would re-run the chown / the migration / the preflight probe in a loop.
    Absent is equivalent to Compose's ``no`` default.
    """
    service = _load_compose()["services"].get(service_name)
    if service is None:
        pytest.skip(f"{service_name} not present in this compose file")
    policy = service.get("restart", "no")
    assert policy == "no", (
        f"{service_name}: one-shot service has restart={policy!r}; it must stay "
        "'no' so it never re-runs migrations/preflight on exit (#1249)"
    )


def _service_env(compose: dict, service_name: str) -> dict:
    """Return a service's ``environment`` mapping (``{}`` when it declares none).

    PyYAML has already resolved the ``x-honcho-env`` alias here, so
    ``honcho``/``honcho-deriver`` report the same keys as a service that spells
    them out — which is what Compose ultimately renders, and what the guard is
    about.
    """
    service = compose["services"][service_name]
    env = service.get("environment")
    if env is None:
        return {}
    if isinstance(env, list):
        pairs = (item.split("=", 1) for item in env)
        return {key: value for key, value in pairs}
    return dict(env)


def test_honcho_embedding_defaults_derive_from_embedding_vars() -> None:
    """Honcho must inherit the app's embedding settings, not carry its own (#1471).

    There is one embedding configuration per deployment. Before this guard the
    Compose file had two: the backend read ``EMBEDDING_PROVIDER`` /
    ``EMBEDDING_MODEL_NAME`` / ``EMBEDDING_VECTOR_DIMENSIONS`` while the Honcho
    services read ``HONCHO_EMBEDDING_*``, with independent defaults. Switching to
    a provider that embeds at a different width therefore left Honcho reading
    one width and the app another — the failure shows up as rejected or useless
    memory vectors, not as a config error.

    The fix is a nested default: an explicit ``HONCHO_EMBEDDING_*`` override
    still wins, otherwise the deployment-wide ``EMBEDDING_*`` value is
    inherited. Checked per service, so forgetting one of the three Honcho
    services (or one of the two probe consumers) fails here.
    """
    compose = _load_compose()
    expected = {
        "EMBEDDING_MODEL_CONFIG__MODEL": _HONCHO_MODEL_EXPR,
        "EMBEDDING_VECTOR_DIMENSIONS": _HONCHO_DIMENSIONS_EXPR,
        # Not nested on purpose: Honcho needs the /v1 suffix, the app does not
        # use this URL at all. Pinned so a well-meant "unify everything" edit
        # cannot quietly point every memory write at a URL without /v1.
        "EMBEDDING_MODEL_CONFIG__OVERRIDES__BASE_URL": _HONCHO_BASE_URL_EXPR,
    }
    problems = []
    for service_name in _HONCHO_EMBEDDING_SERVICES:
        env = _service_env(compose, service_name)
        for key, value in expected.items():
            if env.get(key) != value:
                problems.append(
                    f"{service_name}.{key}={env.get(key)!r} (expected {value!r})"
                )
    assert problems == [], (
        "Honcho embedding config does not derive from EMBEDDING_*: "
        f"{problems!r} — an explicit HONCHO_EMBEDDING_* override must still win, "
        "but the default has to fall through to EMBEDDING_MODEL_NAME / "
        "EMBEDDING_VECTOR_DIMENSIONS so the app and Honcho cannot disagree"
    )

    probe_problems = [
        f"{service_name}.HONCHO_EMBEDDING_VECTOR_DIMENSIONS="
        f"{_service_env(compose, service_name).get('HONCHO_EMBEDDING_VECTOR_DIMENSIONS')!r}"
        for service_name in _HONCHO_EMBEDDING_PROBE_SERVICES
        if "HONCHO_EMBEDDING_VECTOR_DIMENSIONS"
        not in _service_env(compose, service_name)
    ]
    assert probe_problems == [], (
        "health-probe env is incomplete: "
        f"{probe_problems!r} — the memory_backend probe already sees "
        "HONCHO_EMBEDDING_MODEL, so it needs the width as well, or a dimension "
        "mismatch between app and Honcho stays invisible (#911)"
    )


def _pinned_sdk_version(path: Path) -> str:
    """Return the exact ``honcho-ai`` pin from ``path`` (no range allowed).

    An exact pin is the point: the SDK is imported lazily through
    ``memory/honcho_backend.py`` and every bump must be deliberate
    (``SYSTEMAUDIT-2026-08-27 AP-6 L-2``), so a range or a missing line is a
    contract violation, not a value to compare.
    """
    assert path.is_file(), f"{path} is missing — cannot verify the {_SDK_NAME} pin"
    match = _SDK_PIN_RE.search(path.read_text(encoding="utf-8"))
    assert match is not None, (
        f"{path.name} pins no exact '{_SDK_NAME}==' version; found: "
        f"{[ln for ln in path.read_text(encoding='utf-8').splitlines() if _SDK_NAME in ln]!r}"
    )
    return match.group(1)


def test_honcho_sdk_lock_matches_requirements() -> None:
    """``requirements.lock`` must document the SDK version that is installed.

    ``requirements.txt`` is what ``backend/Dockerfile`` installs; the lock is the
    documented resolved closure used to check a CVE advisory against transitive
    packages *without* a build. When the two disagree, the lock answers for a
    client that is not running: before this guard ``requirements.txt`` pinned
    ``honcho-ai==2.5.1`` (``honcho_backend.py`` is written against 2.5.1's
    ``honcho.conclusions.ConclusionsView``) while the lock still said 2.3.0.
    That drift is exactly what ADR-023 AC-SDK closes (plan A, T-A0-1).
    """
    installed = _pinned_sdk_version(_REQUIREMENTS_TXT)
    locked = _pinned_sdk_version(_REQUIREMENTS_LOCK)
    assert locked == installed, (
        f"{_SDK_NAME} pin drift: requirements.txt installs {installed} but "
        f"requirements.lock documents {locked} — a CVE check against the lock "
        "answers for a client that is not deployed. Re-align the single lock "
        f"line to '{_SDK_NAME}=={installed}' (ADR-023 AC-SDK)"
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

    The import above resolves against the tag+digest-pinned image, so once the
    pin is fixed the spike is reproducible across hosts.

    ESCALATION (#1247): this spike proves the *config resolution* only — one seam
    short of the wire. If it passes but ``memory.ask`` still returns HTTP 500 /
    ``400 MissingSessionID``, the remaining gap is inside the vendor image and
    cannot be observed in-repo; follow the escalation in
    ``docs/DEPLOY_RUNBOOK.md`` §3.1 and **reopen #1153**.
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
