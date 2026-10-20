"""
SE-Auditor finding filters (#1262) — server-side ``rule_id`` / ``severity`` /
``artifact_type`` selection shared by the REST and MCP audit surfaces.

Scope boundary: the ``AuditService`` (Layer 2) owns tier resolution, running the
RuleEngine and the report shape; this module owns *selection* only. It is pure
with respect to business rules — it never re-implements a rule, it merely
narrows a report's finding list by the caller's query parameters. It lives in
``traceability/audit`` (Layer 1) so both transports import the same predicate
and cannot drift.

Why filtering happens where it does
-----------------------------------
Preferred (#1382): the transport builds one predicate with
:func:`finding_matches` and passes it to
``AuditService.run_audit(..., finding_filter=...)``. The service applies it
*before* computing any total, the ``MAX_REPORT_FINDINGS`` cap, the window or
the remediation proposals, so ``counts`` is the filtered ground truth and a
match beyond the cap is still reachable by paging.

:func:`apply_report_filters` is the older, **deprecated** post-hoc path (kept
for backward compatibility with existing callers/tests; it has no production
caller any more). It narrows an already-capped report, so matches outside the
cap are unreachable and every count it recomputes is only as complete as the
report it was handed — prefer ``finding_filter`` for new code.
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

    Deprecated: prefer ``AuditService.run_audit(finding_filter=...)`` for new
    code (#1382) — it filters *before* the cap/totals, so ``counts`` is the
    filtered ground truth. This helper filters an already-built report and
    therefore cannot reach findings the cap removed. It is kept for
    compatibility (existing callers/tests); it has no production caller on the
    REST or MCP audit path any more. No ``DeprecationWarning`` is emitted —
    that would spam every test run for a helper that is still exported.

    Mutates an ``AuditReport`` (duck-typed: it exposes ``findings``,
    ``truncated``, ``offset`` and the ``total_*`` counters). Only
    called when at least one filter is active, so the unfiltered path keeps its
    exact previous semantics.

    Window semantics: ``limit``/``offset`` are applied to the *filtered* list —
    `limit` is clamped to *max_findings* and ``report.offset`` reports the
    window start, matching the #622 contract the dashboard already uses.
    Counters describe the full filtered set (pre-window), so ``truncated`` means
    "more filtered findings exist past this window".

    Fields mutated: ``findings``, ``truncated``, ``offset``, ``next_offset``,
    ``total_findings_available``, ``total_blockers_available``,
    ``total_warnings_available``, ``total_suppressed_available``,
    ``total_suppressed_blockers_available``. ``suppressed_filtered`` is
    deliberately **not** touched: it is computed by the service from
    ``include_suppressed=False`` and explains the ``page_counts.total`` vs
    ``counts.total`` gap of the *unpaged* run (with a page size that gap is the
    window truncation plus ``suppressed_filtered``); resetting it here would
    erase that explanation (#1382).

    #1382: ``report.next_offset`` is the next window's offset when ``limit`` is
    given, ``truncated`` is set and the window is non-empty; ``None``
    otherwise — including the un-windowed branch, whose ``max_findings`` cap is
    not a sequential walk, and an empty window (which would otherwise return a
    non-advancing cursor).
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
        report.next_offset = (
            start + len(window) if report.truncated and window else None
        )
    else:
        window = selected[:max_findings]
        report.offset = 0
        report.truncated = bool(report.truncated) or total > max_findings
        report.next_offset = None

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
    # ``suppressed_filtered`` is intentionally left as the service computed it:
    # this window removed no suppressed finding itself, and the counter explains
    # the include_suppressed=False gap (#1382).


__all__ = [
    "DEFAULT_MAX_FINDINGS",
    "VALID_SEVERITIES",
    "apply_report_filters",
    "finding_matches",
    "normalize_rule_ids",
    "normalize_severities",
    "resolve_artifact_ids_for_type",
]
