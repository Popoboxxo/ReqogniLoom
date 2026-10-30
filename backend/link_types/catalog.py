"""Resolved per-workspace link-type catalog + the always-on endpoint check.

This module is the **single seam**: ``application.trace_link_service``, the
REST views, the MCP tools and the SE-Auditor read link-type semantics only
through here. Nothing else queries ``WorkspaceLinkTypeDefinition``.

Replaces ``traceability.types.check_se_link_semantics`` and its two escape
hatches, both removed ersatzlos:

* the ``se_mode`` gate — a dev_mode workspace used to skip validation entirely;
* the ``SE_CORE_ARTIFACT_TYPES`` allow-list — any artifact type outside the
  five "core" ones passed unchecked, which is the exact cause of audit finding
  U2 (``verifies`` from a Risk was accepted, from a StakeholderNeed rejected).

Caching follows ``presets/gate.py``: a process-local dict tagged with the
shared cache generation for the workspace, so a bump performed in any worker
makes every other worker discard its entry on the next read. A bulk
``QuerySet.update()`` bypasses ``save()``/signals, so every writer must call
:func:`invalidate_workspace` explicitly.

Sub-types
---------
A pair side and an endpoint type may carry a sub-type tag as ``Typ:Subtag``
(``ArchitectureElement:function``). That is the **only** sub-type
representation — no second spelling, no separate ``subtype`` key. Which types
may carry one is decided by :data:`SUBTYPE_FIELDS`, a generic register mapping
an artifact type to its sub-type field (not bound to ``ArchitectureElement``).
"""
from __future__ import annotations

import threading
from typing import Any
from uuid import UUID

from persistence.cache_generation import bump_cache_generation, cache_generation
from persistence.errors import ValidationError

from .models import WorkspaceLinkTypeDefinition
from .schema import validate_definition_json

CACHE_NAMESPACE = "link_types"

#: artifact type -> entity field holding its sub-type value. Only a type listed
#: here may carry a ``Typ:Subtag`` tag in a pair or an endpoint.
SUBTYPE_FIELDS: dict[str, str] = {"ArchitectureElement": "element_type"}

_cache_lock = threading.Lock()
#: workspace_id (str) -> (generation, {key: definition_json})
_catalog_cache: dict[str, tuple[int, dict[str, dict[str, Any]]]] = {}


def normalize_artifact_type(artifact_type: str | None) -> str:
    """Strip sub-type tags: ``"TestCase:unit"`` -> ``"TestCase"``.

    ``Typ:Subtag`` is the only sub-type representation the catalog knows; this
    helper reduces either side (pair or endpoint) to the base type. An endpoint
    keeps its full ``Typ:Subtag`` string when it is compared against a tagged
    pair — see :func:`validate_link_pair`.

    Moved here from ``traceability.types`` so the catalog owns the whole
    matching vocabulary.
    """
    if not artifact_type:
        return ""
    return artifact_type.split(":", 1)[0]


def invalidate_workspace(workspace_id: str) -> None:
    """Drop this process's entry and bump the shared generation.

    Both halves are needed: the pop alone leaves other workers stale, the bump
    alone leaves this process waiting out the generation read TTL.
    """
    with _cache_lock:
        _catalog_cache.pop(str(workspace_id), None)
    bump_cache_generation(CACHE_NAMESPACE, str(workspace_id))


def resolve_catalog(workspace_id: UUID | str) -> dict[str, dict[str, Any]]:
    """Return ``{key: definition_json}`` for every **active** type of a workspace.

    Reads the materialized per-workspace rows; there is no merge-on-read
    against the global template (spec section 4: materialized copy).
    """
    ws_key = str(workspace_id)
    generation = cache_generation(CACHE_NAMESPACE, ws_key)

    with _cache_lock:
        entry = _catalog_cache.get(ws_key)
    if entry is not None and entry[0] == generation:
        return entry[1]

    catalog: dict[str, dict[str, Any]] = {}
    rows = WorkspaceLinkTypeDefinition.objects.filter(
        workspace_id=workspace_id
    ).only("key", "definition_json")
    for row in rows:
        definition = row.definition_json or {}
        if not definition.get("active", True):
            continue
        catalog[row.key] = definition

    with _cache_lock:
        _catalog_cache[ws_key] = (generation, catalog)
    return catalog


def get_definition(
    workspace_id: UUID | str, key: str
) -> dict[str, Any] | None:
    """Return one active definition, or None when the key is absent/inactive."""
    return resolve_catalog(workspace_id).get(key)


def _pair_side_matches(pair_type: str | None, endpoint_type: str | None) -> bool:
    """Does one side of an ``allowed_pairs`` entry accept *endpoint_type*?

    ``*`` accepts anything; a side **with** a tag accepts only that exact
    ``Typ:Subtag`` string; a side **without** a tag accepts the normalised base
    type, so untagged pairs keep matching every sub-type (expand guarantee).
    """
    if pair_type == "*":
        return True
    if not pair_type:
        return False
    if ":" in pair_type:
        return pair_type == (endpoint_type or "")
    return pair_type == normalize_artifact_type(endpoint_type)


def validate_link_pair(
    workspace_id: UUID | str,
    link_type: str,
    source_type: str | None,
    target_type: str | None,
    *,
    manual: bool,
) -> None:
    """Validate a link against the workspace catalog. Always. For every type.

    Args:
        workspace_id: Workspace owning both endpoints.
        link_type: The catalog key under validation.
        source_type: Endpoint type of the source, either the base
            ``Artifact.artifact_type`` or ``Typ:Subtag`` when the artifact type
            is in :data:`SUBTYPE_FIELDS`.
        target_type: Same for the target endpoint.
        manual: True for hand-authored links (REST ``trace-links``, every MCP
            trace-link tool). System paths (the diagram reconciler) pass False
            and may write ``system_owned`` types.

    Raises:
        ValidationError: Unknown/inactive type, a system-owned type on the
            manual path, or an endpoint pair the type does not allow. The
            message always lists the acceptable values (audit finding R3), in
            the same ``Typ:Subtag`` notation the pairs are written in.
    """
    catalog = resolve_catalog(workspace_id)
    definition = catalog.get(link_type)
    if definition is None:
        raise ValidationError(
            f"Unknown link type '{link_type}'. "
            f"Valid types in this workspace: {', '.join(sorted(catalog)) or '(none)'}."
        )

    if manual and not definition.get("manual_creatable", True):
        raise ValidationError(
            f"'{link_type}' is a system-managed link type and cannot be "
            f"created or updated manually."
        )

    src = source_type or ""
    tgt = target_type or ""
    pairs = definition.get("allowed_pairs") or []

    for pair in pairs:
        # A non-mapping entry is a corrupt row: every write path validates the
        # ``allowed_pairs`` shape, so such an entry can only come from a direct
        # DB write. Skip it rather than raising AttributeError, so the caller
        # still gets the regular pair-mismatch ValidationError below.
        if not isinstance(pair, dict):
            continue
        if _pair_side_matches(pair.get("source_type"), src) and _pair_side_matches(
            pair.get("target_type"), tgt
        ):
            return

    allowed = ", ".join(
        sorted(
            f"{p.get('source_type')}->{p.get('target_type')}"
            for p in pairs
            if isinstance(p, dict)
        )
    )
    raise ValidationError(
        f"'{link_type}' is not valid from {src or '(unknown)'} to "
        f"{tgt or '(unknown)'}. Allowed: {allowed or '(none configured)'}."
    )


def validate_definition(payload: Any, *, key: str) -> dict[str, Any]:
    """Re-export of :func:`link_types.schema.validate_definition_json`.

    Keeps every write path importing from one module.
    """
    return validate_definition_json(payload, key=key)


__all__ = [
    "CACHE_NAMESPACE",
    "SUBTYPE_FIELDS",
    "get_definition",
    "invalidate_workspace",
    "normalize_artifact_type",
    "resolve_catalog",
    "validate_definition",
    "validate_link_pair",
]
