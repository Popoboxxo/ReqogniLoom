"""Neutral application-service registry (ARCH-L1-004).

The public facade :mod:`application.services` and the Step-2/3/4 shim modules
share one registry object.  Historically the registry lived *inside* the
facade, which forced each shim to back-import ``application.services`` and
created the module-level cycle ``services -> stepN -> services`` (R2S-002).

Keeping the registry in this dependency-free module breaks that cycle: the
facade and every shim import the same object from here, and the shims only
append their own entries.  The dict's insertion order is an implicit public
contract (service-discovery order), so the six Step-1 entries below are
populated first and the shims append in Step-2/3/4 order.

Do **not** import :mod:`application.services` from this module — that would
recreate the very cycle this module exists to prevent.
"""
from __future__ import annotations

from application.architecture_service import ArchitectureService
from application.artifact_service import ArtifactService
from application.preset_policy_service import PresetPolicyService
from application.requirement_service import RequirementService
from application.test_service import TestService
from application.trace_link_service import TraceLinkService

# Step-1 entries first — insertion order is the service-discovery contract.
_registry: dict[str, type] = {
    "ArtifactService": ArtifactService,
    "RequirementService": RequirementService,
    "ArchitectureService": ArchitectureService,
    "TestService": TestService,
    "TraceLinkService": TraceLinkService,
    "PresetPolicyService": PresetPolicyService,
}

__all__ = ["_registry"]
