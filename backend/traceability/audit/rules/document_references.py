"""DOC-P7 — Dead inline reference (Plan F F3-T7, #1374).

An ``InlineAnchor`` is the text side of an inline reference: the stored
markdown keeps a ``[[glossary:<uuid>@<rev>]]`` token and the anchor register
records where it sits and which trace edge it implies. The target of that edge
can be soft-deleted or retired (``Artifact.lifecycle_status`` and/or a
``state_meta.is_outdated_equivalent`` workflow state). I-5 requires the anchor
to *stay* in that case — the prose must keep its token — and this rule is what
makes the dead reference visible instead of silently rendering a link to
nothing.

Tier: Standard + Extended (``_STANDARD_RULES``); Minimal maps to the empty rule
set, so a Minimal workspace never reports it (concept §6.6).

Severity: WARNING at Standard, BLOCKER at Extended. The rule is advisory while
a workspace is still light-weight; at Extended it joins the release/baseline
gate. Severity comes exclusively from :meth:`severity_for_tier` — the
RuleEngine re-stamps every finding with it.

The rule is scope-agnostic: an anchor belongs to exactly one source artifact,
so there is no baseline subtree to resolve. It reads the register through the
``unscoped`` manager with an explicit tenant filter (the audit infrastructure
convention, mirrors :meth:`AuditContext.iter_trace_links`).
"""
from __future__ import annotations

from traceability.audit.registry import DOC_P7, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity


def _dead_target_ids(
    context: AuditContext, target_ids: set[str]
) -> set[str]:
    """Return the target artifacts that are deleted or archived.

    A target is dead when

    * its ``Artifact.lifecycle_status`` is not ``active`` (soft delete, Plan G
      G1.5 V1), or
    * its entity workflow state is flagged ``is_outdated_equivalent`` (e.g. the
      glossary term's ``deprecated`` retire state).

    The supported inline grammar only targets ``GlossaryTerm`` artifacts
    (ENT-F3 = a), so the entity lookup is scoped to that type; an unknown
    target type is treated as alive rather than guessed dead.
    """
    if not target_ids:
        return set()

    from persistence.models import Artifact, GlossaryTerm
    from workflow import state_reader
    from workflow.definition_store import get_state_meta
    from workflow.services import get_workflow_json

    rows = Artifact.unscoped.filter(
        tenant_id=context.tenant_id, id__in=target_ids
    ).values("id", "lifecycle_status")
    dead: set[str] = {
        str(row["id"])
        for row in rows
        if row["lifecycle_status"] != "active"
    }

    live_ids = target_ids - dead
    if not live_ids:
        return dead

    terms = list(
        GlossaryTerm.unscoped.filter(
            tenant_id=context.tenant_id, artifact_id__in=live_ids
        ).values("id", "artifact_id", "workspace_id")
    )
    if not terms:
        return dead

    states = state_reader.current_states(
        "GlossaryTerm",
        [term["id"] for term in terms],
        tenant_id=context.tenant_id,
    )
    workflow_json = get_workflow_json(context.workspace_id, "GlossaryTerm") or {}
    for term in terms:
        state = states.get(str(term["id"]))
        if state is None:
            continue
        if state == "outdated" or get_state_meta(workflow_json, state).get(
            "is_outdated_equivalent"
        ):
            dead.add(str(term["artifact_id"]))
    return dead


@register_rule
class DeadInlineReferenceRule(Rule):
    """DOC-P7: an inline anchor whose target was deleted or archived."""

    rule_id = DOC_P7
    is_scope_aware = False

    title = "Dead inline reference"
    description = (
        "An inline reference anchors a markdown token to a target artifact "
        "that was deleted or archived. The token stays in the text (I-5), so "
        "the projection renders plain text plus a warning and the trace edge "
        "points nowhere."
    )
    standard_ref = "Plan F F3-T7 / concept §6.6 (I-5)"
    remediation_hint = (
        "Either restore the target artifact or remove the dead token from the "
        "document/work-item text (which removes the anchor and the edge)."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """WARNING at Standard, BLOCKER at Extended (concept §6.6)."""
        return Severity.BLOCKER if tier == "extended" else Severity.WARNING

    def check(self, context: AuditContext) -> list[Finding]:
        from persistence.models import InlineAnchor

        anchors = list(
            InlineAnchor.unscoped.filter(
                tenant_id=context.tenant_id,
                source_artifact__workspace_id=context.workspace_id,
            ).values(
                "source_artifact_id",
                "target_artifact_id",
                "field",
                "token",
            )
        )
        if not anchors:
            return []

        target_ids = {str(anchor["target_artifact_id"]) for anchor in anchors}
        dead = _dead_target_ids(context, target_ids)
        if not dead:
            return []

        findings: list[Finding] = []
        for anchor in anchors:
            target_id = str(anchor["target_artifact_id"])
            if target_id not in dead:
                continue
            source_id = str(anchor["source_artifact_id"])
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    # Re-stamped by RuleEngine._run_rule with
                    # severity_for_tier(); the value here is a placeholder.
                    severity=Severity.WARNING,
                    message=(
                        f"[DOC-P7] Dead inline reference in "
                        f"'{anchor['field']}': {anchor['token']} targets "
                        f"artifact {target_id}, which is deleted or archived."
                    ),
                    artifact_ids=(source_id, target_id),
                )
            )
        return findings


__all__ = ["DeadInlineReferenceRule"]
