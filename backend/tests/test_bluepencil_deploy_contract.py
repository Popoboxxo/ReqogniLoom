"""Deploy-contract guard for the bluepencil hub (plan D / D1.1).

The in-app annotation layer is served by a small "hub" process. It used to be a
VENDORED copy of the upstream server (``deploy/bluepencil/server.js``) started
from a bare ``node:22-slim`` image, which meant:

* the deployed code was a file nobody could verify against a release, and
* the hub answered every caller — it had no credential at all, so any client
  that could reach the frontend port could read and write the notes of every
  workspace.

This module locks the replacement wiring in place. It is a *contract* test in
the sense of ``memory/tests/test_honcho_deploy_contract.py``: it reads the
deployment files as text/YAML and asserts the properties that make the switch
safe, without starting a container (``yaml.safe_load`` is enough — notably NOT
``docker compose config``, which would fail whenever the operator has no
``BLUEPENCIL_AUTH_SECRET``, i.e. exactly on the machine that runs this suite).

The seven invariants:

1. the hub image is DIGEST-pinned (a moving tag would silently swap the notes
   protocol under a running store);
2. the image's own entrypoint stays in charge (no ``entrypoint:`` override) and
   ``BLUEPENCIL_AUTH_SECRET`` is a REQUIRED interpolation — ``:?``, never a
   default — so the profile cannot start unauthenticated;
3. the store path and base path are unchanged from the vendored sidecar
   (``/data/notes.json``, ``/bluepencil/api``), so an existing volume keeps its
   notes and the frontend's URLs keep working;
4. the hub publishes no host port (it is reachable over the compose network
   only; its single shared secret is not a substitute for a network boundary);
5. a one-shot ``bluepencil-volume-init`` service chowns the store volume BEFORE
   the hub starts (the old sidecar ran as root, the image runs as ``node``);
6. no vendored ``server.js`` remains and nothing mounts one;
7. the frontend nginx proxy requires a Django-authenticated session
   (``auth_request``) and injects the hub secret server-side instead of
   forwarding whatever the client sent.

The layer delivery from plan D / D1.2 adds one more: the browser layer is not
image content any more, it is a read-only bind mount of a directory that
``deploy/bluepencil/fetch-layer.sh`` materialised from a pinned release. That
mount must not be auto-created by Compose (a missing directory has to be an
error, not an empty, healthy-looking docroot) — see
``test_layer_overlay_mount_is_readonly_and_not_autocreated``.

``deploy/`` and ``frontend/`` are NOT mounted into the backend test container
(only ``./backend`` and ``./docs`` are), so the guards that read them SKIP there
rather than error. They do run in CI, where pytest executes on the checkout with
``working-directory: backend`` and the repository root is therefore readable.
The skip is per-test (not module-level) so a future guard that only needs
``backend/`` is not silently disabled on the container path.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# backend/tests/test_bluepencil_deploy_contract.py ->
#   parents[0] = tests/  parents[1] = backend/  parents[2] = repo root
# On the host that is <repo>; inside the test container the mounted tests live at
# /app/tests, so it resolves to / and the deploy files are simply absent.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEPLOY_COMPOSE = _REPO_ROOT / "deploy" / "docker-compose.yml"
_NGINX_CONF = _REPO_ROOT / "frontend" / "nginx.conf"
_VENDORED_SERVER = _REPO_ROOT / "deploy" / "bluepencil" / "server.js"
_LAYER_OVERLAY = _REPO_ROOT / "deploy" / "docker-compose.bluepencil.yml"

#: Where the overlay mounts the verified layer inside the frontend image; must
#: match the `location ^~ /bluepencil/latest/` in frontend/nginx.conf.
_LAYER_MOUNT_TARGET = "/usr/share/nginx/html/bluepencil/latest"

_HUB_SERVICE = "bluepencil"
_VOLUME_INIT_SERVICE = "bluepencil-volume-init"

#: The env var the frontend nginx injects and the hub verifies.
_AUTH_ENV = "BLUEPENCIL_AUTH_SECRET"

#: ``:?`` is Compose's "required, no default" interpolation. Anything after the
#: colon is the error text, so match the operator hint as well and fail if the
#: expression is a plain default (``:-``) instead.
_REQUIRED_INTERPOLATION_RE = re.compile(
    rf"^\$\{{{_AUTH_ENV}:\?[^}}]+\}}$"
)

#: A manifest-list digest pin. The tag in front of it is documentation; the
#: digest is what actually freezes the image.
_DIGEST_PIN_RE = re.compile(r"@sha256:[0-9a-f]{64}\b")

#: The hub answers ``GET {base}/health`` — the healthcheck must hit the same base
#: the proxy forwards to.
_HEALTH_PATH = "/bluepencil/api/health"


def _load_compose() -> dict:
    """Parse ``deploy/docker-compose.yml`` with the safe loader.

    Skips when the file is absent: the test container only bind-mounts
    ``./backend`` and ``./docs``, so ``deploy/`` is a host/CI-checkout artifact.
    An alias-resolving loader is fine here — the bluepencil block declares its
    own env mapping rather than an ``x-`` anchor.
    """
    if not _DEPLOY_COMPOSE.is_file():
        pytest.skip(
            f"deploy/docker-compose.yml not found at {_DEPLOY_COMPOSE} — "
            "host/CI-checkout-only deploy-contract guard"
        )
    with _DEPLOY_COMPOSE.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _hub_service() -> dict:
    services = _load_compose().get("services") or {}
    assert _HUB_SERVICE in services, f"service {_HUB_SERVICE!r} is missing"
    return services[_HUB_SERVICE]


def _layer_overlay_frontend() -> dict:
    """The overlay's ``frontend`` service, skips when deploy/ is not mounted."""
    if not _LAYER_OVERLAY.is_file():
        pytest.skip(
            f"{_LAYER_OVERLAY} not found — host/CI-checkout-only deploy-contract guard"
        )
    with _LAYER_OVERLAY.open(encoding="utf-8") as handle:
        overlay = yaml.safe_load(handle) or {}
    services = overlay.get("services") or {}
    assert "frontend" in services, (
        f"{_LAYER_OVERLAY.name} must override the frontend service — it is an "
        "overlay for the service that serves the layer"
    )
    return services["frontend"]


def _read_nginx_conf() -> str:
    if not _NGINX_CONF.is_file():
        pytest.skip(
            f"frontend/nginx.conf not found at {_NGINX_CONF} — "
            "host/CI-checkout-only deploy-contract guard"
        )
    return _NGINX_CONF.read_text(encoding="utf-8")


def _nginx_block(config: str, header: str) -> str:
    """Return the ``{ ... }`` body of the nginx block opened by ``header``.

    Brace matching is textual from the header's opening brace until the depths
    balance. The bluepencil locations contain no brace inside a comment or a
    quoted string, so no lexer is needed — a full nginx parser would be a much
    larger dependency than this guard is worth.
    """
    start = config.find(header)
    assert start != -1, f"nginx block {header!r} not found"
    opening = config.find("{", start)
    assert opening != -1, f"nginx block {header!r} has no opening brace"
    depth = 0
    for index in range(opening, len(config)):
        char = config[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return config[opening + 1 : index]
    raise AssertionError(f"nginx block {header!r} is not closed")


def test_hub_image_is_digest_pinned() -> None:
    """The default image reference must freeze a digest, not just carry a tag."""
    image = _hub_service().get("image")
    assert isinstance(image, str), "the bluepencil service declares no image"
    assert _DIGEST_PIN_RE.search(image), (
        "the bluepencil hub image is not digest-pinned; a moving tag could swap "
        f"the notes protocol under a running store: {image!r}"
    )
    # The pin lives in the DEFAULT of an override variable, so an operator can
    # still point the service at another build without editing the file.
    assert image.startswith("${BLUEPENCIL_HUB_IMAGE:-"), (
        "the pinned default must stay overridable through BLUEPENCIL_HUB_IMAGE"
    )


def test_hub_runs_with_auth_secret() -> None:
    """Image entrypoint in charge, shared secret mandatory (ENT-D2 = B)."""
    service = _hub_service()
    assert "entrypoint" not in service, (
        "the hub must use the image's own entrypoint — an override bypasses the "
        "BLUEPENCIL_* handling (and the log-safe secret branch) it implements"
    )
    environment = service.get("environment") or {}
    assert isinstance(environment, dict), "environment must be a mapping"
    assert _AUTH_ENV in environment, (
        f"{_AUTH_ENV} is not passed to the hub — it would accept every caller"
    )
    expression = str(environment[_AUTH_ENV])
    assert _REQUIRED_INTERPOLATION_RE.match(expression), (
        f"{_AUTH_ENV} must be a required interpolation "
        f"(${{{_AUTH_ENV}:?<hint>}}) with no default, got {expression!r}"
    )


def test_hub_keeps_store_path_and_base() -> None:
    """Store file name and base path survive the switch from the vendored copy."""
    environment = _hub_service().get("environment") or {}
    assert environment.get("BLUEPENCIL_STORE") == "/data/notes.json", (
        "the store file name is the notes contract — a new name would orphan the "
        "notes already in the bluepencil_data volume"
    )
    assert environment.get("BLUEPENCIL_BASE") == "/bluepencil/api", (
        "BLUEPENCIL_BASE must match the `location /bluepencil/api/` the frontend "
        "proxy forwards"
    )
    assert str(environment.get("BLUEPENCIL_PORT")) == "8787", (
        "the frontend proxy targets bluepencil:8787; the port is not optional"
    )
    healthcheck = str((_hub_service().get("healthcheck") or {}).get("test"))
    assert _HEALTH_PATH in healthcheck, (
        "the health probe must use the same /bluepencil/api base the proxy "
        "forwards, or it measures a path nobody serves"
    )


def test_hub_publishes_no_host_port() -> None:
    """No ``ports:`` on the hub: compose-network only, no LAN exposure."""
    assert not _hub_service().get("ports"), (
        "the hub must not publish a host port — it is internal-only and its one "
        "shared secret is not a per-user access control"
    )


def test_volume_init_runs_before_hub() -> None:
    """A one-shot chown must fix the store volume before the hub starts."""
    compose = _load_compose()
    services = compose.get("services") or {}
    assert _VOLUME_INIT_SERVICE in services, (
        f"{_VOLUME_INIT_SERVICE} is missing — a volume written by the old "
        "root sidecar is not writable by the image's node user"
    )
    init = services[_VOLUME_INIT_SERVICE]
    assert "bluepencil" in (init.get("profiles") or []), (
        "the init service must live in the bluepencil profile, like the hub"
    )
    assert str(init.get("user")) == "0", "chown must run as root"
    assert [str(part) for part in (init.get("entrypoint") or [])][:2] == [
        "chown",
        "-R",
    ], "the init service must replace the entrypoint with a chown"
    assert str(init.get("restart")) == "no", "the init service is one-shot"
    assert "bluepencil_data:/data" in [
        str(volume) for volume in (init.get("volumes") or [])
    ], "the init service must mount the store volume"

    depends_on = _hub_service().get("depends_on") or {}
    assert isinstance(depends_on, dict), (
        "the hub's depends_on must use the long form to express a condition"
    )
    dependency = depends_on.get(_VOLUME_INIT_SERVICE) or {}
    assert dependency.get("condition") == "service_completed_successfully", (
        "the hub must wait for the volume init to COMPLETE — a plain "
        "`depends_on` list only waits for the container to start"
    )


def test_no_vendored_server_js() -> None:
    """The vendored hub binary is gone and nothing mounts it any more."""
    compose = _load_compose()  # host/CI-checkout guard: skip without deploy/
    assert not _VENDORED_SERVER.exists(), (
        f"{_VENDORED_SERVER} still exists — the hub must run from the pinned "
        "image, not from an unverifiable vendored copy"
    )
    # Parse the volumes instead of grepping the file: the comments deliberately
    # mention the deleted path, so a text match would be a false positive.
    mounted = [
        str(volume)
        for service in (compose.get("services") or {}).values()
        for volume in (service.get("volumes") or [])
        if "bluepencil/server.js" in str(volume)
    ]
    assert mounted == [], f"a service still bind-mounts the vendored hub: {mounted}"


def test_nginx_bluepencil_location_requires_auth_request() -> None:
    """The proxy gates the hub behind a Django session and injects the secret."""
    config = _read_nginx_conf()

    proxy_block = _nginx_block(config, "location /bluepencil/api/ {")
    assert "auth_request /_bluepencil_auth;" in proxy_block, (
        "the bluepencil proxy has no auth_request — the hub would be reachable "
        "by anyone who can reach the frontend port"
    )
    assert "proxy_set_header x-bluepencil-auth" in proxy_block, (
        "the hub secret is not injected by nginx — with the hub's auth enabled "
        "every call would be answered 401"
    )
    assert "${" + _AUTH_ENV + "}" in proxy_block, (
        "the injected header must read the envsubst placeholder "
        f"${{{_AUTH_ENV}}} so the secret stays out of the image"
    )
    # A header the CLIENT sent must never reach the hub: the set_header above
    # overwrites it, which only holds while it is the only assignment.
    assert proxy_block.count("proxy_set_header x-bluepencil-auth") == 1, (
        "more than one x-bluepencil-auth assignment in the proxy block — the "
        "client header could survive"
    )

    auth_block = _nginx_block(config, "location = /_bluepencil_auth {")
    assert "internal;" in auth_block, (
        "the auth subrequest target must be `internal` so it is not an open "
        "session probe"
    )
    assert "/api/v1/auth/me/" in auth_block, (
        "the auth subrequest must ask the backend's session endpoint"
    )
    assert "proxy_set_header Cookie $http_cookie;" in auth_block, (
        "the httpOnly access cookie must be forwarded, or every browser call 401s"
    )


def test_layer_overlay_mount_is_readonly_and_not_autocreated() -> None:
    """D1.2: the layer is a read-only mount of a directory that must exist.

    The layer bytes used to be checked into ``frontend/public/bluepencil/latest``
    and baked into the image, so every layer update forced a rebuild and nothing
    could tell an audited release from a hand-copied directory. The overlay
    replaces that with a bind mount of whatever
    ``deploy/bluepencil/fetch-layer.sh`` verified against
    ``deploy/bluepencil/layer.lock.json``.

    Three properties make that safe, and each fails silently if dropped:

    * ``read_only: true`` — the serving container must not be able to rewrite the
      bytes a browser will execute;
    * ``bind.create_host_path: false`` — Compose otherwise CREATES an empty
      directory when the fetch was forgotten, so the stack comes up healthy and
      404s every asset (``try_files $uri =404`` in the nginx location) or, worse,
      removes the directory again on ``down``;
    * the ``source`` stays interpolated so an operator can point it at another
      fetched directory without editing the file.
    """
    frontend = _layer_overlay_frontend()

    volumes = frontend.get("volumes") or []
    assert isinstance(volumes, list), "frontend volumes must be a list"

    mounts = [
        volume
        for volume in volumes
        if isinstance(volume, dict) and volume.get("target") == _LAYER_MOUNT_TARGET
    ]
    assert len(mounts) == 1, (
        "expected exactly one long-form bind mount targeting "
        f"{_LAYER_MOUNT_TARGET!r}, found {len(mounts)} — the short "
        "'host:container' form cannot express read_only/create_host_path at all"
    )
    mount = mounts[0]

    assert mount.get("type") == "bind", (
        f"the layer mount must be type 'bind', got {mount.get('type')!r}"
    )
    assert mount.get("read_only") is True, (
        "a writable layer mount lets the frontend container replace the code a "
        "browser executes — mount it read_only: true"
    )

    bind = mount.get("bind") or {}
    assert isinstance(bind, dict), "the layer mount needs a `bind:` options mapping"
    assert bind.get("create_host_path") is False, (
        "create_host_path must be false: a forgotten fetch-layer.sh otherwise "
        "yields an empty, silently healthy docroot instead of a Compose error"
    )

    source = mount.get("source")
    assert isinstance(source, str), "the layer mount declares no source"
    assert source.startswith("${BLUEPENCIL_LAYER_DIR:-"), (
        "the mount source must stay an interpolated default "
        "(${BLUEPENCIL_LAYER_DIR:-...}) so an operator can point it at another "
        f"verified directory, got {source!r}"
    )
    assert source.endswith("}"), f"unterminated interpolation in mount source: {source!r}"
