"""REL-P1 — a released Requirement's live tier diverges from its pinned tier (#1805).

ADR-028 D11 pins ``Requirement.released_tier_key`` when the requirement is
released ("Stufe 4") and the baseline capture reads that value in preference to
the live ``tier_key``. The pin is written **once** and never overwritten
(``application/release_service.py:_stamp_release``), while ``tier_key`` keeps
being recomputed from the allocation/hierarchy graph
(``application/tier_compute.py``). A re-allocation after the release therefore
moves the live tier away from the released one:

* the released baseline still says the old tier (that is the point of the pin),
* every live report, coverage count and tier filter says the new one.

Neither value is *wrong* on its own — the divergence is the finding. Without it
a reviewer has no way to see that a released requirement no longer sits where
it was signed off, and the two views of the same workspace silently disagree.

What is reported
----------------
A Requirement whose pin is set (``released_tier_key IS NOT NULL``) and whose
live ``tier_key`` differs from it. A NULL live tier counts as a divergence: the
tier is no longer determinable (e.g. the leading allocation was revoked after
release) while a pinned value still claims a position in the ladder. A never
released requirement (pin ``NULL``) is never reported — that is the whole
population of a workspace that has not adopted the release flow.

Soft-deleted/archived requirements are excluded through the shared
:func:`workflow.services.outdated_item_ids` convention: the product hides them
everywhere else, and flagging them would resurrect rows the lists already drop.

Data access
-----------
Two queries per audit run, never one per finding:

1. the divergent requirements (workspace via the authoritative
   ``artifact__workspace_id`` join — the denormalized ``Requirement.workspace_id``
   copy is NULL for rows written before #133),
2. the active allocations of exactly those requirements, so the finding can name
   the allocation that drives the live tier (``is_primary`` first, ADR-028 D9).

Severity
--------
``extended`` -> :attr:`Severity.BLOCKER` (blocks baseline creation, waivable per
finding), ``standard`` -> :attr:`Severity.WARNING`. Both match the issue's
mapping; the third level it names (``minimal`` -> info) is inexpressible here
for two independent reasons, and both are deliberate:

* the audit vocabulary has only two severities (:class:`Severity`), and adding
  an ``INFO`` would change every count consumer (badges, baseline gate, release
  reports) for a purely cosmetic level — the same call ``ALLOC-P1`` documents;
* ``minimal`` maps to an empty rule set *by construction*
  (``RULE_PRESET_MAP["minimal"]``), so no rule runs there at all.

The rule is therefore registered for standard + extended, never for minimal.
"""
from __future__ import annotations

from typing import Any

from django.db.models import F, Q

from persistence.models import Allocation, AllocationStatus, Requirement
from traceability.audit.registry import REL_P1, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity
from workflow.services import outdated_item_ids

#: Allocation states that still take part in the tier computation (ADR-028:
#: ``revoked`` is an archive state without a live edge).
_ACTIVE_ALLOCATION_STATUSES = (
    AllocationStatus.DRAFT,
    AllocationStatus.RELEASED,
)


def _divergent_requirements(context: AuditContext) -> list[dict[str, Any]]:
    """Return the workspace's released requirements whose live tier differs.

    One query. The comparison is done in SQL because the population is the
    whole workspace, but the NULL live tier is spelled out separately: in SQL
    ``NOT (tier_key = released_tier_key)`` is ``NULL`` (not true) for a NULL
    live tier, so ``.exclude(tier_key=F(...))`` would silently drop exactly the
    "tier no longer resolvable anymore" case. ``Q(tier_key__isnull=True)``
    makes it explicit instead of accidental.
    """
    return list(
        Requirement.unscoped.filter(
            tenant_id=context.tenant_id,
            artifact__workspace_id=context.workspace_id,
            released_tier_key__isnull=False,
        )
        .filter(Q(tier_key__isnull=True) | ~Q(tier_key=F("released_tier_key")))
        .exclude(id__in=outdated_item_ids("Requirement", tenant_id=context.tenant_id))
        .values("artifact_id", "uid", "title", "tier_key", "released_tier_key")
        .order_by("artifact_id")
    )


def _driving_allocations(
    context: AuditContext, artifact_ids: list[Any]
) -> dict[str, dict[str, Any]]:
    """Return ``{requirement_artifact_id: allocation}`` for *artifact_ids*.

    One query for all reported requirements (no N+1). "Driving" is the leading
    allocation when the workspace uses ``allocation.cardinality=multiple``
    (ADR-028 D9): ``is_primary`` wins, otherwise the lowest element id keeps the
    choice deterministic for a workspace that is mid-migration.
    """
    if not artifact_ids:
        return {}
    rows = Allocation.unscoped.filter(
        tenant_id=context.tenant_id,
        requirement_artifact_id__in=artifact_ids,
        status__in=list(_ACTIVE_ALLOCATION_STATUSES),
    ).values(
        "requirement_artifact_id", "element_artifact_id", "is_primary", "status"
    )
    # ``-is_primary`` puts the leading allocation first; the id tie-break keeps
    # the message stable across runs (the same reason ``iter_trace_links`` is
    # ordered).
    driving: dict[str, dict[str, Any]] = {}
    for row in sorted(
        rows,
        key=lambda r: (
            not r["is_primary"],
            str(r["requirement_artifact_id"]),
            str(r["element_artifact_id"]),
        ),
    ):
        driving.setdefault(str(row["requirement_artifact_id"]), row)
    return driving


def _allocation_hint(allocation: dict[str, Any] | None) -> str:
    """Return the ``;`` clause naming the allocation behind the live tier."""
    if allocation is None:
        return (
            "; no active allocation drives the live tier — it was revoked or "
            "never linked."
        )
    role = "leading" if allocation["is_primary"] else "non-leading"
    return (
        f"; driven by the {role} allocation ({allocation['status']}) to "
        f"architecture element {allocation['element_artifact_id']}."
    )


@register_rule
class ReleaseTierPinDivergenceRule(Rule):
    """REL-P1: the live tier of a released Requirement differs from its pin."""

    rule_id = REL_P1
    is_scope_aware = False

    title = "Released requirement's tier drifted from the released pin"
    description = (
        "A requirement was released with a pinned tier (released_tier_key, "
        "ADR-028 D11) and its live tier has changed since — typically because "
        "it was re-allocated or its derivation parent moved. The released "
        "baseline keeps the pinned tier while live reports use the new one, so "
        "the same requirement is reported at two different SE levels."
    )
    standard_ref = "ADR-028 D11 / Stufe 4 (release pin vs. live tier ladder)"
    remediation_hint = (
        "Either undo the allocation/parent change that moved the tier, or "
        "re-release the requirement so the pin follows the intended position."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """BLOCKER at extended, WARNING at standard (#1805).

        Minimal is unreachable — the preset is empty by construction — and the
        audit vocabulary has no ``INFO``; see the module docstring.
        """
        if tier == "standard":
            return Severity.WARNING
        return Severity.BLOCKER

    def check(self, context: AuditContext) -> list[Finding]:
        requirements = _divergent_requirements(context)
        if not requirements:
            return []
        driving = _driving_allocations(
            context, [row["artifact_id"] for row in requirements]
        )
        findings: list[Finding] = []
        for row in requirements:
            artifact_id = str(row["artifact_id"])
            label = row["uid"] or row["title"] or artifact_id
            live = row["tier_key"] or "unresolved (NULL)"
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,  # re-stamped by RuleEngine
                    message=(
                        f"[REL-P1] Requirement '{label}' ({artifact_id}) is "
                        f"released with pinned tier '{row['released_tier_key']}' "
                        f"but its live tier is '{live}'"
                        + _allocation_hint(driving.get(artifact_id))
                    ),
                    artifact_ids=(artifact_id,),
                )
            )
        return findings


__all__ = ["ReleaseTierPinDivergenceRule"]
