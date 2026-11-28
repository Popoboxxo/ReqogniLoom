"""Deterministic change-impact summary generator (D1, AC-28, plan S5.4).

Spec: ``docs/superpowers/specs/2026-11-28-change-artefakt-wirkketten-design.md``
§4.4 (Freitext-Strategie), §4.5 gate check 6 and AC-28. Plan slice: ``S5.4``.

Why this module exists
----------------------
In ``extended`` rigor the free-text ``impact_assessment`` is demoted to an
addendum; the *evidence* for the gate is the generated Markdown in
``ChangeRequest.impact_summary`` (decision D1). That text is a **gate
artefact**, so it must not share the injection surface of the advisory LLM
annotation: it is pure template interpolation over persisted, already-computed
aggregates.

Deliberate properties (each one is tested in
``application/tests/test_change_impact_summary.py``):

* **No LLM, ever.** No provider is resolved or called — not even lazily. The
  summary therefore stays reproducible after a provider outage or a prompt
  change.
* **Aggregates only, no identities.** No titles, UIDs, artifact ids, rationale
  or note text (AC-28 / spec §4.7): the persisted summary must not become an
  existence oracle for items the caller may not read. Only types and counts.
* **Byte-identical for the same run.** Nothing time-dependent is interpolated
  (no "generated at" line); ``impact_generated_at`` carries the timestamp on
  the row. Two calls for the same run therefore produce identical text, which
  is what makes the gate check ``summary_run_id == latest_completed_run.id``
  stable.
* **Latest *completed* run, not latest run.** A later ``failed`` run must not
  invalidate an otherwise valid summary (§4.5 check 6).
* **One ``QuerySet.update()``.** The summary columns are written in a single
  ``UPDATE``: no ``save()``, no ``version`` bump, no ``modified_at``/workflow
  side effects — the summary is derived data, not a user edit.

The read-side ``impact_stats``/``findings_count``/``coverage.uncovered_ids``
remain a request-scoped projection of the *visible* artifact set (AC-28); this
module never fetches per-artifact data and never renders a per-artifact view.

leaf_id : COMP-AS-021
req_id  : REQ-216, REQ-L2-PL-010
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Final
from uuid import UUID

from django.db.models import Count
from django.utils import timezone

from application.base import NotFoundError, ValidationError
from application.models import (
    ChangeImpactFinding,
    ChangeImpactRun,
    ChangeRequest,
    ChangeRequestAffectedItem,
)
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

#: Hard cap on the persisted Markdown (spec §4.4: "Länge im Service gekappt").
MAX_SUMMARY_CHARS: Final[int] = 2000

#: Appended when the body had to be cut. Deterministic — never time-based.
TRUNCATION_MARKER: Final[str] = "\n… [summary truncated]"

#: Number of distinct finding types rendered in the "by type" line.
TOP_FINDING_TYPES: Final[int] = 5

#: Stable order for the severity line (blocking first: it is the gate-relevant one).
_SEVERITY_ORDER: Final[tuple[str, str, str]] = ("blocking", "warning", "info")

#: Stable order for the change-action line (mirrors ``change_action`` choices).
_CHANGE_ACTIONS: Final[tuple[str, str, str]] = ("add", "modify", "remove")

#: Rendered for an empty/absent aggregate so the text is never ambiguous.
_NONE_MARKER: Final[str] = "none"


def latest_completed_run(cr_id: UUID) -> ChangeImpactRun | None:
    """Return the newest ``completed`` run of *cr_id*, or ``None``.

    Ordering is ``(created_at DESC, id DESC)`` — the id tie-breaker keeps the
    result deterministic when two runs share a timestamp. ``failed``/
    ``pending``/``running`` runs are ignored on purpose: spec §4.5 check 6
    requires ``summary_run_id`` to point at the latest *completed* run, so a
    later failure cannot invalidate a valid summary.

    Tenant fencing comes from :class:`persistence.tenancy.TenantManager` (the
    active :class:`TenantContext`) plus the explicit ``change_request_id``
    filter; the caller is expected to have armed the tenant.
    """
    return (
        ChangeImpactRun.objects.filter(
            change_request_id=cr_id,
            status=ChangeImpactRun.Status.COMPLETED,
        )
        .order_by("-created_at", "-id")
        .first()
    )


def generate_summary(
    cr_id: UUID,
    *,
    ctx: AuthContext,
    run_id: UUID | None = None,
) -> str:
    """Generate and persist the deterministic impact summary for *cr_id*.

    Args:
        cr_id: Change request to summarise; must be inside ``ctx``'s tenant.
        ctx: Authenticated caller. Its tenant arms the ORM filter and fences the
            ``UPDATE``. Authorization (write role / item permission) is the
            caller's concern — the engine already asserted it before a run is
            persisted, and this function is a derived-data writer, not a
            user-facing mutation.
        run_id: Run to summarise. Defaults to
            :func:`latest_completed_run` (newest completed run).

    Returns:
        The generated Markdown. ``""`` when the change request has no
        ``completed`` run yet — nothing is written in that case, and no
        exception is raised (an in-flight or failed analysis is a normal state,
        not an error).

    Raises:
        NotFoundError: ``cr_id`` (or an explicit ``run_id``) is not visible in
            the caller's tenant / does not belong to this change request.
        ValidationError: An explicit ``run_id`` names a run that is not
            ``completed``; a summary must always cite a completed run.
    """
    TenantContext.set_tenant(ctx.tenant_id)

    cr = ChangeRequest.objects.filter(id=cr_id, tenant_id=ctx.tenant_id).first()
    if cr is None:
        raise NotFoundError(f"ChangeRequest {cr_id} not found")

    run = _resolve_run(cr_id=cr_id, run_id=run_id)
    if run is None:
        return ""

    text = build_summary(cr_id=cr_id, run=run, tenant_id=ctx.tenant_id)

    ChangeRequest.objects.filter(id=cr_id, tenant_id=ctx.tenant_id).update(
        impact_summary=text,
        summary_run_id=run.id,
        impact_source="analysis",
        impact_generated_at=timezone.now(),
    )
    return text


def build_summary(
    *,
    cr_id: UUID,
    run: ChangeImpactRun,
    tenant_id: UUID,
) -> str:
    """Render the Markdown for *run* without writing anything (pure read).

    Kept public so the gate/read path can preview the exact text that
    :func:`generate_summary` would persist, and so tests can assert on the
    bytes without a second write.
    """
    affected = ChangeRequestAffectedItem.objects.filter(
        change_request_id=cr_id, tenant_id=tenant_id
    )
    change_set_total = affected.count()
    action_counts = {
        row["change_action"]: row["total"]
        for row in affected.values("change_action").annotate(total=Count("id"))
    }
    change_set_types = _count_map(
        affected.values("entity_type").annotate(total=Count("id")), "entity_type"
    )

    finding_rows = list(
        ChangeImpactFinding.objects.filter(run_id=run.id, tenant_id=tenant_id)
        .order_by("artifact_id")
        .values_list(
            "entity_type", "severity", "hop_distance", "weight", "chain_count"
        )
    )

    # Order matters: the gate-relevant lines (run provenance, truncation) come
    # first so a length cut can only ever drop distributions, never the flags
    # the gate reasons about.
    lines = [
        "## Change impact summary",
        "",
        (
            f"- Run: {run.status} · roots_source={run.roots_source} · "
            f"gate_eligible={_bool(run.gate_eligible)} · "
            f"algorithm={run.algorithm_version or _NONE_MARKER}"
        ),
        "- Truncated: "
        + _bool(run.truncated)
        + (
            f" · reason={run.truncated_reason}"
            if run.truncated and run.truncated_reason
            else ""
        ),
        (
            f"- Graph: nodes={run.node_count} · edges={run.edge_count} · "
            f"paths={run.path_count} · visited={len(run.visited_node_ids or [])}"
        ),
        (
            f"- Change set: total={change_set_total} · "
            + " · ".join(
                f"{action}={action_counts.get(action, 0)}"
                for action in _CHANGE_ACTIONS
            )
        ),
        "- Change-set types: " + _format_counts(change_set_types, None),
        f"- Findings: total={len(finding_rows)}",
    ]

    severity_counts = Counter(row[1] for row in finding_rows)
    max_weight = max((row[3] for row in finding_rows), default=None)
    lines.append(
        "- Severity: "
        + " · ".join(
            f"{severity}={severity_counts.get(severity, 0)}"
            for severity in _SEVERITY_ORDER
        )
        + " · max_weight="
        + (_decimal(max_weight) if max_weight is not None else _NONE_MARKER)
    )

    type_counts = Counter(row[0] for row in finding_rows)
    lines.append(
        "- Findings by type (top "
        f"{TOP_FINDING_TYPES}): " + _format_counts(type_counts, TOP_FINDING_TYPES)
    )

    hops = [row[2] for row in finding_rows]
    if hops:
        average = (Decimal(sum(hops)) / Decimal(len(hops))).quantize(Decimal("0.01"))
        lines.append(
            f"- Hop distance: min={min(hops)} · max={max(hops)} · avg={average}"
        )
        chained = sum(1 for row in finding_rows if row[4] > 0)
        # Coverage of the effect-chain evidence, derived from the run alone —
        # no per-artifact lookup (see module docstring / AC-28).
        lines.append(f"- Coverage: findings_with_chains={chained}/{len(finding_rows)}")
    else:
        lines.append("- Hop distance: none")

    return _cap_length("\n".join(lines))


def _resolve_run(
    *, cr_id: UUID, run_id: UUID | None
) -> ChangeImpactRun | None:
    """Resolve the run to summarise; ``None`` only when nothing completed yet."""
    if run_id is None:
        return latest_completed_run(cr_id)

    run = ChangeImpactRun.objects.filter(
        id=run_id, change_request_id=cr_id
    ).first()
    if run is None:
        raise NotFoundError(f"ChangeImpactRun {run_id} not found")
    if run.status != ChangeImpactRun.Status.COMPLETED:
        raise ValidationError(
            f"ChangeImpactRun {run_id} is '{run.status}', not 'completed': "
            "a summary must cite a completed run"
        )
    return run


def _count_map(rows, key: str) -> dict[str, int]:
    """Turn a ``values(key).annotate(total=Count('id'))`` result into a dict."""
    return {row[key]: row["total"] for row in rows}


def _format_counts(counts: Counter, limit: int | None) -> str:
    """Render ``Type=n`` pairs deterministically (count desc, then name asc)."""
    if not counts:
        return _NONE_MARKER
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        ordered = ordered[:limit]
    return " · ".join(f"{name}={count}" for name, count in ordered)


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _decimal(value: Decimal) -> str:
    """Render a weight with a fixed 4-decimal scale (no locale, no float)."""
    return str(Decimal(value).quantize(Decimal("0.0001")))


def _cap_length(text: str) -> str:
    """Cut *text* to :data:`MAX_SUMMARY_CHARS` at a line boundary, deterministically.

    The marker is always appended to a cut body, so a truncated summary is
    visibly distinguishable from a complete one. A body that already fits is
    returned unchanged.
    """
    if len(text) <= MAX_SUMMARY_CHARS:
        return text

    budget = MAX_SUMMARY_CHARS - len(TRUNCATION_MARKER)
    head = text[:budget]
    last_break = head.rfind("\n")
    if last_break > 0:
        head = head[:last_break]
    return head.rstrip() + TRUNCATION_MARKER


__all__ = [
    "MAX_SUMMARY_CHARS",
    "TOP_FINDING_TYPES",
    "TRUNCATION_MARKER",
    "build_summary",
    "generate_summary",
    "latest_completed_run",
]
