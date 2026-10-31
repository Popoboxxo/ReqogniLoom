"""
QUAL-P1/P2/P3 — advisory quality-assessment rules (#378, WP B5-T4).

The three rules turn the append-only ``QualityAssessment`` table into
SE-Auditor findings. They are the *read* side of the quality-assessment feature
(WP B5): the service writes one verdict row per run, these rules say what the
resulting coverage of the workspace looks like.

* ``QUAL-P1`` — an assessable artifact without any assessment row.
* ``QUAL-P2`` — the latest *successful* assessment scored below the configured
  floor (``quality_min_score``).
* ``QUAL-P3`` — the latest assessment is stale: the entity's content (or the
  rubric that judged it) changed after the verdict was written.

Tier: Extended only (``_EXTENDED_ONLY_RULES``). Minimal maps to the empty rule
set and Standard does not list any QUAL id, so a light workspace never
collects a warning per unassessed artifact.

Severity: always WARNING. ``Rule.severity_for_tier`` defaults to BLOCKER and the
RuleEngine re-stamps *every* finding with it
(``traceability.audit.rule_engine.RuleEngine._run_rule``), so the override is
the only switch that matters: ``AuditService.blocking_findings`` filters on
BLOCKER and ``BaselineFacade`` consumes only that method. An unassessed
artifact is not an SE-conformance defect — it is an advisory hint — so shipping
any of these as a BLOCKER would block every Extended baseline build the moment
the rules land (the #581 calibration lesson).

No LLM, ever
------------
``check()`` reads the table only. It never renders a prompt and never calls a
provider: a *verdict* is requested explicitly by the user (REST/MCP
``quality assess``), an *audit run* only inspects verdicts that already exist.
Running the auditor must therefore stay free of provider cost and latency — the
regression test pins a provider counter at zero across a full engine run.

Data access
-----------
The latest row per entity is one indexed query (``DISTINCT ON`` over
``(tenant, entity_type, entity_id, -created_at)``, the
``idx_qa_entity_created`` index), not one query per entity. The snapshot is
memoised on the :class:`~traceability.audit.types.AuditContext` (#1385), so the
three rules share one read per audit run instead of issuing three.

Gates (the "Gate 2" pattern from ``validation_goals.py``)
--------------------------------------------------------
``QUAL-P1`` is silent unless the workspace already has at least one assessment.
Without that gate every legacy Extended workspace would get one warning per
requirement the first time this rule ships — noise about a feature the
workspace never used, which is exactly the false-positive flood the #581
calibration warns about. A failed (``status="failed"``) row still counts as
"assessed" here: an attempt was recorded, so P1 is about coverage of the
feature, not about verdict quality.

``QUAL-P2`` reads only ``status="ok"`` rows. A failed row stores ``score=0.0``
as a sentinel — reading it as a real zero would report the worst possible score
for a run that produced no score at all.

``QUAL-P3`` also considers only ``status="ok"`` rows (a failed run has no
verdict that could be stale). It recomputes the digest the service stores, i.e.
the canonical content **plus** the prompt provenance, because that composite is
what ``QualityService.assess`` hashes: comparing the stored value with a
content-only hash would report every row in the table as stale. A row is
therefore "stale" exactly when a re-assessment would not be served from the
cache — which is the user-visible meaning of the UI hint "assessment refers to
an older revision".
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from persistence.models import QualityAssessment
from traceability.audit.registry import (
    QUAL_P1,
    QUAL_P2,
    QUAL_P3,
    Rule,
    register_rule,
)
from traceability.audit.types import AuditContext, Finding, Severity
from workflow.services import outdated_item_ids

logger = logging.getLogger(__name__)

#: Config variable holding the advisory score floor (see
#: ``application.prompt_variables.PROMPT_VARIABLE_DEFAULTS``).
MIN_SCORE_VARIABLE = "quality_min_score"

#: Last-resort fallback, used when the config variable cannot be resolved at all
#: or carries a value that is not a number in ``0.0..1.0``. Kept in sync with
#: the factory catalog by ``test_quality_rules_378``; a drifted copy fails that
#: test instead of silently changing the threshold.
DEFAULT_MIN_SCORE: float = 0.6

_SNAPSHOT_KEY = "quality_score.snapshot"


@dataclass(frozen=True)
class _Snapshot:
    """One audit run's view of the workspace's assessments.

    Built once per :class:`AuditContext` (see :func:`_snapshot`) and read by all
    three rules.
    """

    #: Effective ``quality_min_score`` (already validated, ``0.0..1.0``).
    threshold: float
    #: Latest assessment row per ``(entity_type, entity_id)``.
    rows: tuple[QualityAssessment, ...]
    #: Live entity per ``(entity_type, entity_id)`` — only for rows that carry a
    #: verdict and whose entity still exists inside the workspace.
    entities: Mapping[tuple[str, str], Any]
    #: Recomputed cache-key digest per ``(entity_type, entity_id)``.
    digests: Mapping[tuple[str, str], str]

    @property
    def has_any(self) -> bool:
        """Whether the workspace has at least one assessment row at all."""
        return bool(self.rows)

    @property
    def assessed_keys(self) -> frozenset[tuple[str, str]]:
        """``(entity_type, entity_id)`` pairs that carry any assessment row."""
        return frozenset(
            (row.entity_type, str(row.entity_id)) for row in self.rows
        )


def _entity_key(entity_type: str, entity_id: Any) -> tuple[str, str]:
    """Return the ``(entity_type, entity_id)`` snapshot key."""
    return entity_type, str(entity_id)


def _auth_context(context: AuditContext) -> Any:
    """Return a minimal :class:`AuthContext` for tenant-scoped reads.

    ``resolve_config_values`` and the prompt-template lookup are tenant-scoped;
    the audit infrastructure supplies ``tenant_id`` as a string on the context
    (it never relies on the thread-local), so the system context is built from
    it explicitly.
    """
    from auth_tenancy.context import AuthContext

    return AuthContext.system(tenant_id=UUID(context.tenant_id))


def _resolve_threshold(context: AuditContext) -> float:
    """Return the effective ``quality_min_score``, never raising.

    Resolution goes through the ordinary config-variable path
    (``application.prompt_resolver.resolve_config_values``: workspace → tenant →
    factory), so an admin override needs no deploy. Three failure modes are
    handled here rather than propagated:

    * the resolver raises (e.g. an unarmed tenant context) → default,
    * the value is not numeric (a ``"str"``-typed row holding ``"high"``) →
      default,
    * the value is outside ``0.0..1.0`` → default.

    A bool is not a threshold: ``float(True)`` is ``1.0``, which would silently
    make QUAL-P2 fire for every verdict below a perfect score — the opposite of
    what the admin meant — so booleans fall back explicitly. Every fallback is
    logged, so an admin can see why their value was ignored.
    """
    try:
        from application.prompt_resolver import resolve_config_values

        values = resolve_config_values(_auth_context(context), context.workspace_id)
        raw = values.get(MIN_SCORE_VARIABLE)
    except Exception:  # noqa: BLE001 — the threshold is advisory, never fatal
        logger.warning(
            "QUAL: could not resolve %r for workspace %s; using the default %s.",
            MIN_SCORE_VARIABLE,
            context.workspace_id,
            DEFAULT_MIN_SCORE,
            exc_info=True,
        )
        return DEFAULT_MIN_SCORE

    if isinstance(raw, bool) or raw is None:
        logger.warning(
            "QUAL: %r resolved to %r for workspace %s; using the default %s.",
            MIN_SCORE_VARIABLE,
            raw,
            context.workspace_id,
            DEFAULT_MIN_SCORE,
        )
        return DEFAULT_MIN_SCORE
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "QUAL: %r resolved to the non-numeric value %r for workspace %s; "
            "using the default %s.",
            MIN_SCORE_VARIABLE,
            raw,
            context.workspace_id,
            DEFAULT_MIN_SCORE,
        )
        return DEFAULT_MIN_SCORE
    if not 0.0 <= value <= 1.0:
        logger.warning(
            "QUAL: %r resolved to %s, outside 0.0..1.0, for workspace %s; "
            "using the default %s.",
            MIN_SCORE_VARIABLE,
            value,
            context.workspace_id,
            DEFAULT_MIN_SCORE,
        )
        return DEFAULT_MIN_SCORE
    return value


def _latest_rows(context: AuditContext) -> tuple[QualityAssessment, ...]:
    """Return the latest assessment per entity — one ``DISTINCT ON`` query.

    ``unscoped`` with an explicit tenant filter is the audit infrastructure
    convention (the engine supplies tenant/workspace, it never relies on the
    thread-local); RLS still bounds the read to one tenant. The ``ORDER BY``
    prefix must match the ``DISTINCT ON`` expressions, which is why the newest
    row is selected by ``-created_at, -id`` after them — the ``id`` tie-break
    makes "latest" deterministic for two rows written in the same instant.
    """
    return tuple(
        QualityAssessment.unscoped.filter(
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
        )
        .order_by("entity_type", "entity_id", "-created_at", "-id")
        .distinct("entity_type", "entity_id")
    )


def _assessable_models() -> Mapping[str, tuple[Any, str]]:
    """Return ``{entity_type: (model, workspace_filter)}`` for assessable types.

    Taken from the quality service instead of being re-declared here: that
    mapping is the definition of "assessable", and a second copy would drift the
    moment a type is added to the feature (the rule would then quietly stop
    covering it).
    """
    # ``_ENTITY_TYPES`` is the single source of truth for "which model backs
    # which assessable type"; a local copy would drift.
    from application.quality_service import _ENTITY_TYPES

    return _ENTITY_TYPES


def _entities_for(
    context: AuditContext, rows: tuple[QualityAssessment, ...]
) -> dict[tuple[str, str], Any]:
    """Load the live entities behind *rows* (one query per entity type).

    Outdated entities are excluded: a soft-deleted artifact is not "stale", it
    is gone from the model, and flagging it would resurrect a row every list in
    the product already hides.
    """
    by_type: dict[str, list[Any]] = {}
    for row in rows:
        by_type.setdefault(row.entity_type, []).append(row.entity_id)

    models = _assessable_models()
    entities: dict[tuple[str, str], Any] = {}
    for entity_type, entity_ids in by_type.items():
        entry = models.get(entity_type)
        if entry is None:
            # The column is deliberately loose (a new type needs no migration);
            # an unknown type simply carries no P3 check.
            logger.debug(
                "QUAL: no entity model registered for type %r; skipping its "
                "staleness check.",
                entity_type,
            )
            continue
        model, workspace_filter = entry
        queryset = model.unscoped.filter(
            tenant_id=context.tenant_id,
            id__in=entity_ids,
            **{workspace_filter: context.workspace_id},
        ).exclude(
            id__in=outdated_item_ids(entity_type, tenant_id=context.tenant_id)
        )
        for entity in queryset:
            entities[_entity_key(entity_type, entity.id)] = entity
    return entities


def _digests_for(
    context: AuditContext,
    rows: tuple[QualityAssessment, ...],
    entities: Mapping[tuple[str, str], Any],
) -> dict[tuple[str, str], str]:
    """Recompute the cache-key digest each row was written with.

    Mirrors ``QualityService.assess``: the digest covers the canonical content
    *and* the prompt provenance (slot, resolved scope/version, template body
    hash), because that composite is what the service stores and compares. A
    content-only hash would differ from every stored value by construction and
    report the whole table as stale.

    The provenance lookup is one local template read per prompt slot (there are
    at most one per entity type), never a provider call.
    """
    from application.quality_service import (
        QualityService,
        canonical_content,
        content_hash,
    )

    auth = _auth_context(context)
    workspace_id = UUID(context.workspace_id)
    #: slot -> (scope, version, template hash); ``None`` marks an unresolvable
    #: slot so a broken template lookup is attempted once, not per row.
    provenance: dict[str, tuple[str, int | None, str] | None] = {}
    digests: dict[tuple[str, str], str] = {}

    for row in rows:
        key = _entity_key(row.entity_type, row.entity_id)
        entity = entities.get(key)
        if entity is None:
            continue
        slot = row.prompt_slot
        if slot not in provenance:
            try:
                # ``_prompt_provenance`` is the one implementation of "which
                # template would this run use" — the same helper that produced
                # the stored digest. Duplicating it here would let the rule and
                # the service drift apart.
                provenance[slot] = QualityService._prompt_provenance(  # noqa: SLF001
                    auth, slot, workspace_id
                )
            except Exception:  # noqa: BLE001 — a rubric lookup must not fail the audit
                logger.warning(
                    "QUAL: could not resolve the prompt provenance of slot %r "
                    "for workspace %s; skipping its staleness check.",
                    slot,
                    context.workspace_id,
                    exc_info=True,
                )
                provenance[slot] = None
        resolved = provenance[slot]
        if resolved is None:
            continue
        prompt_scope, prompt_version, template_hash = resolved
        try:
            digests[key] = content_hash(
                {
                    "content": canonical_content(row.entity_type, entity),
                    "prompt_slot": slot,
                    "prompt_scope": prompt_scope,
                    "prompt_version": prompt_version,
                    "prompt_template_hash": template_hash,
                }
            )
        except Exception:  # noqa: BLE001 — one odd row must not abort the rule
            logger.warning(
                "QUAL: could not fingerprint %s %s; skipping its staleness "
                "check.",
                row.entity_type,
                row.entity_id,
                exc_info=True,
            )
    return digests


def _build_snapshot(context: AuditContext) -> _Snapshot:
    """Read the workspace's assessment state once (see :func:`_snapshot`)."""
    rows = _latest_rows(context)
    verdicts = tuple(
        row for row in rows if row.status == QualityAssessment.Status.OK
    )
    entities = _entities_for(context, verdicts)
    return _Snapshot(
        threshold=_resolve_threshold(context),
        rows=rows,
        entities=entities,
        digests=_digests_for(context, verdicts, entities),
    )


def _snapshot(context: AuditContext) -> _Snapshot:
    """Return the run-scoped snapshot, building it on first use (#1385)."""
    return context.memoize(_SNAPSHOT_KEY, lambda: _build_snapshot(context))


def _artifact_ids(row: QualityAssessment, entity: Any | None) -> tuple[str, ...]:
    """Return the artifact ids a finding about *row* should point at."""
    artifact_id = getattr(row, "artifact_id", None) or getattr(
        entity, "artifact_id", None
    )
    return (str(artifact_id),) if artifact_id is not None else ()


def _label(row: QualityAssessment, entity: Any | None) -> str:
    """Return ``Type 'title' (id)`` for a finding message."""
    title = getattr(entity, "title", None) or ""
    if title:
        return f"{row.entity_type} '{title}' ({row.entity_id})"
    return f"{row.entity_type} ({row.entity_id})"


def _unassessed_findings(context: AuditContext, snapshot: _Snapshot) -> list[Finding]:
    """Build the QUAL-P1 findings: assessable artifacts with no assessment."""
    assessed = snapshot.assessed_keys
    findings: list[Finding] = []
    for entity_type, (model, workspace_filter) in sorted(
        _assessable_models().items()
    ):
        queryset = (
            model.unscoped.filter(
                tenant_id=context.tenant_id,
                **{workspace_filter: context.workspace_id},
            )
            .exclude(
                id__in=outdated_item_ids(entity_type, tenant_id=context.tenant_id)
            )
            .order_by("id")
            .values("id", "artifact_id", "title")
        )
        for row in queryset:
            if _entity_key(entity_type, row["id"]) in assessed:
                continue
            artifact_ids = (
                (str(row["artifact_id"]),) if row["artifact_id"] else ()
            )
            findings.append(
                Finding(
                    rule_id=QUAL_P1,
                    # Re-stamped by RuleEngine._run_rule; the value here is a
                    # placeholder that documents the rule's intent.
                    severity=Severity.WARNING,
                    message=(
                        f"[QUAL-P1] {entity_type} '{row['title']}' "
                        f"({row['id']}) wurde noch nie bewertet — "
                        "Qualitätsbewertung fehlt."
                    ),
                    artifact_ids=artifact_ids,
                )
            )
    return findings


@register_rule
class QualityCoverageRule(Rule):
    """QUAL-P1: every assessable artifact carries at least one assessment."""

    rule_id = QUAL_P1
    is_scope_aware = False

    title = "Assessable artifact has no quality assessment"
    description = (
        "Every assessable artifact (Requirement, ADR, TestCase, Risk) should "
        "have been quality-assessed at least once. Only reported once the "
        "workspace has used the feature at all — advisory at every tier."
    )
    standard_ref = "UMSETZUNGSPLAN_SYSENG_2.0.md (quality coverage, #378/WP B5)"
    remediation_hint = (
        "Run 'assess quality' on the artifact, or stop treating the quality "
        "layer as complete for this workspace."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """Always WARNING — an unassessed artifact must never block a baseline."""
        return Severity.WARNING

    def check(self, context: AuditContext) -> list[Finding]:
        snapshot = _snapshot(context)
        # Gate 2 (#378): a workspace that has never used the feature has no
        # quality layer to be incomplete — flagging every artifact there would
        # be noise on legacy data, not signal.
        if not snapshot.has_any:
            return []
        return _unassessed_findings(context, snapshot)


@register_rule
class QualityScoreFloorRule(Rule):
    """QUAL-P2: the latest successful score is below ``quality_min_score``."""

    rule_id = QUAL_P2
    is_scope_aware = False

    title = "Quality score below the advisory floor"
    description = (
        "The latest *successful* quality assessment of the artifact scored "
        "below the configured floor (config variable 'quality_min_score', "
        "default 0.6). Failed runs carry no verdict and are ignored. Advisory."
    )
    standard_ref = "UMSETZUNGSPLAN_SYSENG_2.0.md (quality score, #378/WP B5)"
    remediation_hint = (
        "Apply the assessment's suggestions, then re-assess the artifact."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """Always WARNING — a low LLM score is a hint, not a conformance defect."""
        return Severity.WARNING

    def check(self, context: AuditContext) -> list[Finding]:
        snapshot = _snapshot(context)
        threshold = snapshot.threshold
        findings: list[Finding] = []
        for row in snapshot.rows:
            # A failed run stores score=0.0 as a sentinel: never read it as a
            # real zero (that would report the worst possible score for a run
            # that produced no score at all).
            if row.status != QualityAssessment.Status.OK:
                continue
            if row.score >= threshold:
                continue
            entity = snapshot.entities.get(_entity_key(row.entity_type, row.entity_id))
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=(
                        f"[QUAL-P2] {_label(row, entity)} hat einen "
                        f"Qualitäts-Score von {row.score:.2f}, unter der "
                        f"Schwelle {threshold:.2f}."
                    ),
                    artifact_ids=_artifact_ids(row, entity),
                )
            )
        return findings


@register_rule
class QualityStaleAssessmentRule(Rule):
    """QUAL-P3: the latest assessment no longer matches the artifact."""

    rule_id = QUAL_P3
    is_scope_aware = False

    title = "Quality assessment is stale"
    description = (
        "The artifact's content (or the rubric that judged it) changed after "
        "the latest successful assessment, so the stored verdict no longer "
        "describes the artifact as it is now. Advisory."
    )
    standard_ref = "UMSETZUNGSPLAN_SYSENG_2.0.md (quality staleness, #378/WP B5)"
    remediation_hint = (
        "Re-assess the artifact so the verdict refers to the current revision."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """Always WARNING — a stale verdict is an advisory hint, never a block."""
        return Severity.WARNING

    def check(self, context: AuditContext) -> list[Finding]:
        snapshot = _snapshot(context)
        findings: list[Finding] = []
        for row in snapshot.rows:
            if row.status != QualityAssessment.Status.OK:
                continue
            key = _entity_key(row.entity_type, row.entity_id)
            digest = snapshot.digests.get(key)
            if digest is None or digest == row.content_hash:
                continue
            entity = snapshot.entities.get(key)
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=(
                        f"[QUAL-P3] {_label(row, entity)} hat sich seit der "
                        "letzten Bewertung geändert (Inhalt oder Bewertungs-"
                        "Rubrik) — die Bewertung bezieht sich auf einen "
                        "älteren Stand."
                    ),
                    artifact_ids=_artifact_ids(row, entity),
                )
            )
        return findings


__all__ = [
    "DEFAULT_MIN_SCORE",
    "MIN_SCORE_VARIABLE",
    "QualityCoverageRule",
    "QualityScoreFloorRule",
    "QualityStaleAssessmentRule",
]
