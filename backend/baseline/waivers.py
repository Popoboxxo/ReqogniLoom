"""Per-blocker SE-Auditor gate waivers (GH-821).

leaf_id : COMP-BL-003 (BaselineStore extension)
req_id  : REQ-L2-BL-001, REQ-L2-AL-001

The baseline gate (``application.baseline_facade.BaselineFacade``) can refuse a
build because the SE-Auditor reports BLOCKER findings. Until now the only exit
was a single ``override_reason`` that waived *all* of them at once, which made a
workspace with 47 findings unwirtschaftbar: you could either fix every single
one, or accept the whole set with one sentence (issue #821). This module owns
the per-finding counterpart — identity, matching and persistence — so the
facade stays an orchestrator and the REST/MCP surfaces do not re-derive what a
"finding" is.

Storage is append-only: a waiver is a governance record, and the row (plus the
``AuditLog`` entry written next to it) is what makes "we accepted this
deviation, on this artifact, for this rule, for this reason" durable instead of
a line in one response body.

Why ``unscoped`` + an explicit ``tenant_id`` (mirroring ``baseline.store``):
the gate is reachable from management-adjacent paths that legitimately run
without an armed request context, and RLS is the second isolation layer in
production. The tenant filter is applied explicitly here, so nothing is lost.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

from baseline.models import BaselineGateWaiver

logger = logging.getLogger(__name__)

#: Field separator between the rule id and the artifact ids inside a finding
#: key. A unit separator cannot appear in a rule id or an artifact id, so the
#: rendering stays injective — no pair of distinct findings can collide into
#: the same key and silently waive the wrong one.
_KEY_SEPARATOR = "\x1f"

#: Separator between the artifact ids of one finding.
_ARTIFACT_SEPARATOR = ","


def canonical_artifact_ids(artifact_ids: Iterable[Any] | None) -> tuple[str, ...]:
    """Return the finding's artifact ids as a sorted, de-duplicated tuple.

    Sorting is what makes the key order-independent: a rule that reports
    ``("a", "b")`` and one that reports ``("b", "a")`` describe the same
    blocker and must match the same waiver.
    """
    return tuple(sorted({str(artifact_id) for artifact_id in (artifact_ids or ())}))


def finding_key(rule_id: str, artifact_ids: Iterable[Any] | None) -> str:
    """Return the canonical identity of an audit finding.

    A ``Finding`` (``traceability.audit.types``) has no stable id — it is
    re-derived on every run. Its identity for waiver purposes is therefore the
    rule that reported it plus the artifacts it concerns, rendered canonically
    (see :func:`canonical_artifact_ids`). The scope is deliberately *not* part
    of the key: the gate only ever audits one scope per call, so the same
    rule/artifact pair cannot be blocking twice for different reasons.
    """
    return (
        f"{str(rule_id).strip()}{_KEY_SEPARATOR}"
        f"{_ARTIFACT_SEPARATOR.join(canonical_artifact_ids(artifact_ids))}"
    )


@dataclass(frozen=True)
class BlockerWaiverRequest:
    """One caller-supplied per-blocker waiver, already shape-validated.

    Built by the facade from the request payload (REST serializer or MCP
    params) — the surfaces never construct it directly, so the shape rules live
    in exactly one place.

    Attributes:
        rule_id: The SE-Auditor rule being waived (e.g. ``"TRACE-P1"``).
        artifact_ids: Artifacts the finding concerns (empty for graph-level
            findings). Order-insensitive, de-duplicated.
        reason: Mandatory written justification for this single deviation.
    """

    rule_id: str
    artifact_ids: tuple[str, ...]
    reason: str

    @property
    def key(self) -> str:
        """Canonical :func:`finding_key` of this request."""
        return finding_key(self.rule_id, self.artifact_ids)


def load_waived_finding_keys(
    workspace_id: UUID | str, tenant_id: UUID | str
) -> frozenset[str]:
    """Return the finding keys already waived in *workspace_id*.

    Read-only; a workspace without waivers yields an empty set. Errors
    propagate to the caller (the gate decides how to fail — it fails closed).
    """
    rows = BaselineGateWaiver.unscoped.filter(
        workspace_id=workspace_id, tenant_id=tenant_id
    ).values_list("finding_key", flat=True)
    return frozenset(rows)


def record_waiver(
    *,
    workspace_id: UUID | str,
    tenant_id: UUID | str,
    request: BlockerWaiverRequest,
    rule_id: str,
    scope: str | None,
    scope_artifact_id: str | None,
    granted_by: str,
) -> tuple[BaselineGateWaiver, bool]:
    """Persist *request* as a waiver row; idempotent per (workspace, finding).

    The stored ``rule_id``/``scope`` come from the *matched finding*, never from
    the request: the client identifies a finding, but only the auditor can say
    which scope it was reported in. A repeated waiver for the same finding is
    not an error and does not overwrite the original record — the first
    justification (and its author) is the one on file.

    Args:
        workspace_id: Workspace the waiver belongs to.
        tenant_id: Active tenant (row-level isolation).
        request: The shape-validated waiver.
        rule_id: Canonical rule id of the matched finding.
        scope: Baseline scope of the matched finding (``None`` -> empty).
        scope_artifact_id: Document-scope root of the matched finding.
        granted_by: User/agent id that granted the waiver.

    Returns:
        ``(row, created)`` — ``created`` is False when the waiver already
        existed, in which case no new audit entry is warranted.
    """
    row, created = BaselineGateWaiver.unscoped.get_or_create(
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        finding_key=request.key,
        defaults={
            "rule_id": rule_id,
            "artifact_ids": list(request.artifact_ids),
            "scope": scope or "",
            "scope_artifact_id": scope_artifact_id or "",
            "reason": request.reason,
            "granted_by": granted_by,
        },
    )
    if not created:
        logger.info(
            "baseline gate: waiver for %s/%s already on file (ws=%s); "
            "keeping the original justification",
            rule_id,
            request.key,
            workspace_id,
        )
    return row, created


__all__ = [
    "BlockerWaiverRequest",
    "canonical_artifact_ids",
    "finding_key",
    "load_waived_finding_keys",
    "record_waiver",
]
