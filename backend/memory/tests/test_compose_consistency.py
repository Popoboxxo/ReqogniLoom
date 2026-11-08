"""Compose-hygiene guard for the shipped deployment files (C1-T1/T5/T6/T7/T9).

Docker-free: parses the YAML and asserts the invariants that used to drift
between the base and minimal files, and between services:

* every service rotates its logs (the Honcho four were missing it — #1740);
* every service carries ``TZ`` (display only; the DB stays UTC);
* Postgres has explicit shared memory (#1742);
* backend/celery/migrate take their memory limit from an env var with the
  measured default (#1735);
* the TLS overlay is a proxy-only overlay and is not a version carrier.

Run with::

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \
        backend/memory/tests/test_compose_consistency.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY = REPO_ROOT / "deploy"

BASE = DEPLOY / "docker-compose.yml"
MINIMAL = DEPLOY / "docker-compose.minimal.yml"
TLS = DEPLOY / "docker-compose.tls.example.yml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _services(path: Path) -> dict:
    return _load(path)["services"]


@pytest.mark.parametrize("path", [BASE, MINIMAL], ids=["base", "minimal"])
def test_every_service_rotates_logs(path: Path) -> None:
    services = _services(path)
    missing = [
        name
        for name, service in services.items()
        if "logging" not in service
        or service["logging"].get("options", {}).get("max-size") is None
    ]
    assert not missing, f"services without log rotation: {missing}"


@pytest.mark.parametrize("path", [BASE, MINIMAL], ids=["base", "minimal"])
def test_every_service_carries_tz(path: Path) -> None:
    services = _services(path)
    missing = []
    for name, service in services.items():
        env = service.get("environment") or {}
        if not isinstance(env, dict) or "TZ" not in env:
            missing.append(name)
    assert not missing, f"services without TZ: {missing}"


@pytest.mark.parametrize("path", [BASE, MINIMAL], ids=["base", "minimal"])
def test_postgres_has_explicit_shm(path: Path) -> None:
    postgres = _services(path)["postgres"]
    assert "shm_size" in postgres
    assert "POSTGRES_SHM_SIZE" in str(postgres["shm_size"])


def test_memory_limits_are_env_driven() -> None:
    base = _services(BASE)
    assert "BACKEND_MEM_LIMIT" in str(base["backend"]["deploy"]["resources"]["limits"])
    assert "CELERY_MEM_LIMIT" in str(base["celery"]["deploy"]["resources"]["limits"])
    assert "MIGRATE_MEM_LIMIT" in str(base["migrate"]["deploy"]["resources"]["limits"])

    minimal = _services(MINIMAL)
    assert "BACKEND_MEM_LIMIT" in str(
        minimal["backend"]["deploy"]["resources"]["limits"]
    )
    assert "MIGRATE_MEM_LIMIT" in str(
        minimal["migrate"]["deploy"]["resources"]["limits"]
    )


def test_tls_overlay_is_proxy_only_and_not_a_version_carrier() -> None:
    services = _services(TLS)
    assert set(services) == {"caddy"}
    assert "logging" in services["caddy"]
    assert all("REQOGNILOOM_VERSION" not in str(s.get("image", "")) for s in services.values())


def test_honcho_model_pins_use_the_environment() -> None:
    text = BASE.read_text(encoding="utf-8")
    assert "${HONCHO_LLM_MODEL:-${LLM_MODEL:-mimo-v2.5}}" in text
    # No literal pin may survive next to a transport/base-URL pin.
    assert "MODEL_CONFIG__MODEL: mimo-v2.5" not in text
