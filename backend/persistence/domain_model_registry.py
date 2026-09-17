"""Dependency-inversion seam for Layer-1 modules that need Layer-2/Ext model classes.

SA-21 (SYSTEMAUDIT_2026-08-27 §4.1 #3): ``traceability/service.py`` and
``baseline/state_capture.py`` (both Layer 1) resolve Artifact <-> domain-entity
across *every* Generic Artifact Model type, including five entity types
(``Adr``, ``Risk``, ``Issue``, ``Goal``, ``MainGoal``) whose Django models live
in ``application.models`` (Layer 2), plus ``Icd`` from the ``icd`` app
for baseline state capture — both lazy imports going the wrong direction in
the layering.

Rather than have Layer 1 import Layer 2 (or a sibling app) directly, this
Layer-0-owned registry is populated by each owning app's ``AppConfig.ready()``
(``application.apps.ApplicationConfig``, ``icd.apps.IcdConfig``) — the same
register-on-``ready()`` pattern ``audit.apps.AuditConfig`` already uses for
``AuditLogWriter``/``DomainEventBus`` and ``persistence.status_provider`` uses
for the workflow soft-delete lookup. Consumers resolve model classes by name
instead of importing across layers; a name that was never registered (e.g. an
optional app not installed) simply comes back ``None``/omitted, preserving the
previous ``try/except ImportError`` "degrade gracefully" behaviour without the
cross-layer import.
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional, Type

_registry: Dict[str, Type] = {}


def register_models(models: Dict[str, Type]) -> None:
    """Register one or more named model classes. Additive — never clears.

    Called from an owning app's ``AppConfig.ready()`` (e.g.
    ``application.apps.ApplicationConfig``, ``icd.apps.IcdConfig``).
    """
    _registry.update(models)


def get_model(name: str) -> Optional[Type]:
    """Return the registered model class for *name*, or ``None`` if absent."""
    return _registry.get(name)


def get_models(*names: str) -> Dict[str, Type]:
    """Return ``{name: model}`` for every *names* entry that is registered.

    Names with no registered model are silently omitted — mirrors the old
    per-call-site ``try/except ImportError: pass`` degrade-gracefully
    behaviour (e.g. an optional app not installed).
    """
    return {name: _registry[name] for name in names if name in _registry}


__all__ = ["register_models", "get_model", "get_models"]
