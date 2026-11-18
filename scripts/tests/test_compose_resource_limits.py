"""Guard that every shipped Compose service declares an explicit memory limit.

OPS-011: the base ``deploy/docker-compose.yml`` capped only the eight default
services; the backup sidecar and every optional-profile service (honcho/*,
qdrant) could grow until the host OOM-killed the capped Postgres alongside
them. A hard ``deploy.resources.limits.memory`` per service keeps one workload
from taking down its neighbours.

The test parses the YAML rather than grepping text so a misplaced/indented
``memory:`` key cannot satisfy it. A minimum-service assertion prevents a
vacuous pass if the services tree is ever renamed or silently truncated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "deploy" / "docker-compose.yml"

#: 9 default services + 5 honcho-profile + 1 qdrant-profile (base f60697d).
MIN_SERVICES = 15


def _load_services() -> dict[str, Any]:
    """Return the ``services:`` mapping of the shipped base Compose file."""
    assert COMPOSE_FILE.is_file(), f"missing {COMPOSE_FILE.relative_to(REPO_ROOT)}"

    document = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "compose root must be a mapping"

    services = document.get("services")
    assert isinstance(services, dict), "`services:` must be a mapping"
    return services


def test_every_compose_service_has_memory_limit() -> None:
    """Every service must carry deploy.resources.limits.memory."""
    services = _load_services()

    # Vacuous-pass guard: an empty/renamed services tree must not pass.
    assert len(services) >= MIN_SERVICES, (
        f"expected >= {MIN_SERVICES} services, found {len(services)}"
    )

    missing: list[str] = []
    for name in sorted(services):
        spec = services[name] or {}
        assert isinstance(spec, dict), f"service {name!r} must be a mapping"

        deploy = spec.get("deploy") or {}
        resources = deploy.get("resources") or {}
        limits = resources.get("limits") or {}
        memory = limits.get("memory") if isinstance(limits, dict) else None

        if not isinstance(limits, dict) or not memory:
            missing.append(name)

    assert not missing, (
        "Compose services without deploy.resources.limits.memory:\n"
        + "\n".join(f"  - {name}" for name in missing)
    )
