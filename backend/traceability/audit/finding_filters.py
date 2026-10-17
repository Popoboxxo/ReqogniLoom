"""
SE-Auditor finding filters (#1262) — server-side ``rule_id`` / ``severity`` /
``artifact_type`` selection shared by the REST and MCP audit surfaces.

Scope boundary: the ``AuditService`` (Layer 2) owns tier resolution, running the
RuleEngine and the report shape; this module owns *selection* only. It is pure
with respect to business rules — it never re-implements a rule, it merely
narrows a report's finding list by the caller's query parameters. It lives in
``traceability/audit`` (Layer 1) so both transports import the same predicate
and cannot drift.

Why filtering happens at the transport edge
-------------------------------------------
The REST/MCP audit surfaces call ``AuditService.run_audit`` and then narrow the
returned report with :func:`apply_report_filters`. When a filter is active the
caller requests the *unwindowed* run (``limit=None``), so the filter is applied
to the complete finding set before the window is taken — a filter combined with
``limit``/``offset`` therefore pages over the *filtered* result, not over an
unfiltered window that may contain no matches.
"""
from __future__ import annotations

from collections.abc import Iterable

from traceability.audit.types import Severity

#: Severities a caller may filter on (the two :class:`Severity` members).
VALID_SEVERITIES = frozenset({Severity.BLOCKER.value, Severity.WARNING.value})

#: Default page cap, mirrors ``AuditService.MAX_REPORT_FINDINGS``. Passed in by
#: the transport so this Layer-1 module never imports the Layer-2 service.
DEFAULT_MAX_FINDINGS = 500


def normalize_rule_ids(raw: Iterable[str] | str | None) -> frozenset[str]:
    """Return the requested rule ids as a frozenset (``[]``-tolerant).

    Accepts a repeated query parameter (list) or a single comma-separated
    string; blank entries are dropped so ``rule_id=`` is a no-op.
    """
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        parts: Iterable[str] = raw.split(",")
    else:
        parts = raw
    return frozenset(
        str(part).strip() for part in parts if str(part).strip()
    )


def normalize_severities(raw: Iterable[str] | str | None) -> frozenset[str]:
    """Return the requested severities, validating against :data:`VALID_SEVERITIES`.

    Raises:
        ValueError: an unknown severity was requested. The transport maps this
            to a 400 (REST) / ``VALIDATION_ERROR`` (MCP).
    """
    severities = normalize_rule_ids(raw)
    unknown = severities - VALID_SEVERITIES
    if unknown:
        raise ValueError(
            f"Unknown severity {sorted(unknown)}; expected one of "
            f"{sorted(VALID_SEVERITIES)}."
        )
    return severities


def resolve_artifact_ids_for_type(
    *, artifact_type: str, tenant_id, workspace_id
) -> frozenset[str]:
    """Return the ``Artifact`` ids of *artifact_type* in the workspace.

    ``artifact_type`` is the ``Artifact.artifact_type`` discriminator
    ("Requirement", "ArchitectureElement", "Icd", ...). Tenant/workspace are
    supplied explicitly by the caller (audit infrastructure convention — see
    ``AuditContext.iter_trace_links``); the query uses ``unscoped`` with an
    explicit tenant filter.
    """
    from persistence.models import Artifact

    rows = Artifact.unscoped.filter(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        artifact_type=artifact_type,
    ).values_list("id", flat=True)
    return frozenset(str(row) for row in rows)


def finding_matches(
    finding,
    *,
    rule_ids: frozenset[str] = frozenset(),
    severities: frozenset[str] = frozenset(),
    artifact_type_ids: frozenset[str] | None = None,
) -> bool:
    """Return whether *finding* (a :class:`traceability.audit.types.Finding`)
    satisfies every active filter. An empty/``None`` filter is inert.
    """
    if rule_ids and finding.rule_id not in rule_ids:
        return False
    if severities and finding.severity.value not in severities:
        return False
    if artifact_type_ids is not None and not (
        set(finding.artifact_ids) & artifact_type_ids
    ):
        return False
    return True


def apply_report_filters(
    report,
    *,
    rule_ids: frozenset[str] = frozenset(),
    severities: frozenset[str] = frozenset(),
    artifact_type_ids: frozenset[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    max_findings: int = DEFAULT_MAX_FINDINGS,
) -> None:
    """Narrow *report* in place to the selected findings and recompute counters.

    Mutates an ``AuditService.AuditReport`` (duck-typed: it exposes
    ``findings``, ``truncated``, ``offset`` and the ``total_*`` counters). Only
    called when at least one filter is active, so the unfiltered path keeps its
    exact previous semantics.

    Window semantics: ``limit``/``offset`` are applied to the *filtered* list —
    `limit` is clamped to *max_findings* and ``report.offset`` reports the
    window start, matching the #622 contract the dashboard already uses.
    Counters describe the full filtered set (pre-window), so ``truncated`` means
    "more filtered findings exist past this window".
    """
    selected = [
        view
        for view in report.findings
        if finding_matches(
            view.finding,
            rule_ids=rule_ids,
            severities=severities,
            artifact_type_ids=artifact_type_ids,
        )
    ]
    total = len(selected)

    if limit is not None:
        start = max(offset, 0)
        window_limit = min(max(int(limit), 0), max_findings)
        window = selected[start : start + window_limit]
        report.offset = start
        report.truncated = (start + len(window)) < total
    else:
        window = selected[:max_findings]
        report.offset = 0
        report.truncated = bool(report.truncated) or total > max_findings

    report.findings = window
    report.total_findings_available = total
    # Issue #1150: ``total_blockers_available`` is the *effective* count — a
    # suppressed blocker no longer blocks, so it is excluded here too.
    report.total_blockers_available = sum(
        1
        for view in selected
        if view.finding.severity is Severity.BLOCKER and not view.suppressed
    )
    report.total_warnings_available = sum(
        1 for view in selected if view.finding.severity is Severity.WARNING
    )
    report.total_suppressed_available = sum(1 for view in selected if view.suppressed)
    report.total_suppressed_blockers_available = sum(
        1
        for view in selected
        if view.suppressed and view.finding.severity is Severity.BLOCKER
    )
    # ``include_suppressed`` filtering already ran inside the service; this
    # window did not remove any suppressed finding itself.
    report.suppressed_filtered = 0


__all__ = [
    "DEFAULT_MAX_FINDINGS",
    "VALID_SEVERITIES",
    "apply_report_filters",
    "finding_matches",
    "normalize_rule_ids",
    "normalize_severities",
    "resolve_artifact_ids_for_type",
]
