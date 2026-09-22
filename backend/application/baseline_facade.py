"""
COMP-AS-006 BaselineFacade — Orchestrates baseline lifecycle.

leaf_id : COMP-AS-006
req_id  : REQ-L1-018, REQ-L2-AS-006, REQ-L2-AS-007

Delegates to baseline.services (build/diff/get/list_baselines/get_item_at_baseline)
and orchestrates preset-scope validation + audit via ServiceBase helpers.

Interface contracts implemented:
  IF-AS-EXT-IN-001  — inbound: create_baseline, diff_baselines, get_baseline,
                       list_baselines, get_item_at_baseline
  IF-AS-INT-006     — outbound: PresetPolicyService.is_scope_allowed()

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-006_BaselineFacade/
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Mapping, Optional, Sequence, Tuple
from uuid import UUID

if TYPE_CHECKING:  # pragma: no cover - typing only
    # Import-time only: ``traceability`` (Layer 1) is loaded lazily inside the
    # gate methods so this Layer-2 facade keeps its light import graph.
    from traceability.audit import Finding

    # GH-821: only the string annotations of `_apply_waivers` /
    # `_coerce_waiver_requests` name this type; the runtime import stays local to
    # `_coerce_waiver_requests` so the facade keeps its light import graph. Without
    # this type-check-only alias the annotations reference an undefined name
    # (ruff F821 in the CI gate `ruff check . --select=F821,F822`).
    from baseline.waivers import BlockerWaiverRequest

from auth_tenancy.context import AuthContext

# Backward-compat alias used by tests that patch 'application.baseline_facade.TenantContext'
TenantContext = AuthContext

from application.base import (
    BaselineGateBlockedError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.event_bus import DomainEvent
from application.preset_policy_service import get_preset_policy_service
from persistence.transactions import atomic_transaction

# D4 (#569): the reason-policy constants now live at Layer 1
# (``baseline.waivers``, the SSOT for finding identity and matching). They are
# re-exported here so the established import surface
# (``from application.baseline_facade import MIN_OVERRIDE_REASON_LENGTH``, used
# by ``test_baseline_gate_waivers_821.py``) stays valid. The private patterns
# stay private to ``baseline.waivers`` and are deliberately NOT re-exported.
from baseline.waivers import (  # noqa: F401  (re-exported public constants)
    MIN_OVERRIDE_REASON_LENGTH,
    MIN_REASON_DISTINCT_WORDS,
    MIN_REASON_WORDS,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateWaiverOutcome:
    """What the SE-Auditor gate accepted on the way through.

    Returned by :meth:`BaselineFacade._enforce_audit_gate` so the caller can
    record the decision without re-deriving it. Both collections are empty for
    a clean audit and for a plain (unwaived) block.

    Attributes:
        overridden: Findings waived by the *global* ``override_reason``
            (all-or-nothing verdict override, GH-513).
        suppressed: Findings matched by a per-finding waiver — either one the
            caller supplied in this request or one already on file (GH-821).
        waiver_ids: Ids of the waiver rows *created* by this request. Empty for
            waivers that were already on file, which are not re-audited. Kept
            as-is for backward compatibility (#569/M4).
        matched_waiver_ids: Ids of **all** waiver rows that matched a suppressed
            finding — created *and* reused (#569/M4). :attr:`waiver_ids` alone
            cannot name the row that suppressed a finding on a later build
            (``suppressed > 0`` with ``waiver_ids == ()``), so the baseline
            metadata would otherwise be unable to say *which* decision applied.
    """

    overridden: Tuple["Finding", ...] = ()
    suppressed: Tuple["Finding", ...] = ()
    waiver_ids: Tuple[UUID, ...] = ()
    matched_waiver_ids: Tuple[UUID, ...] = ()

    @property
    def any_waived(self) -> bool:
        """True when at least one finding was waived on the way through."""
        return bool(self.overridden or self.suppressed)


class BaselineFacade(ServiceBase):
    """Orchestrating facade for Baseline operations.

    COMP-AS-006 (IF-AS-EXT-IN-001, IF-AS-INT-006).

    Usage::

        facade = BaselineFacade()
        baseline_id = facade.create_baseline(
            scope="project",
            workspace_id=ws_id,
            name="v1.0-baseline",
            ctx=auth_ctx,
        )
    """

    # ---------- Public API ----------

    @atomic_transaction
    def create_baseline(
        self,
        scope: str,
        workspace_id: UUID | str,
        name: str,
        ctx: AuthContext,
        description: Optional[str] = None,
        document_id: Optional[UUID | str] = None,
        override_reason: Optional[str] = None,
        waived_findings: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> UUID:
        """Create an immutable baseline after preset-scope validation.

        REQ-L3-AS006-001 (scope gate), REQ-L3-AS006-002 (event + audit).

        Args:
            scope: "document" | "project" | "global"
            workspace_id: Target workspace UUID.
            name: Human-readable baseline name (unique per workspace).
            ctx: Fully resolved AuthContext.
            description: Optional description.
            document_id: Required when scope="document".
            override_reason: Written justification for waiving the SE-Auditor
                gate (GH-513). Only consulted when the gate actually reports
                BLOCKER findings; requires approval authority (Admin or
                Approver) and is recorded in the audit log and on the baseline.
            waived_findings: Per-finding waivers, each a mapping with
                ``rule_id``, ``artifact_ids`` and a mandatory ``reason``
                (GH-821), requiring the same approval authority as
                ``override_reason``. A waiver names one blocking finding; the
                matching findings do not count as blockers any more and the
                waiver is persisted, so a later baseline build does not have to
                re-state it. Unlike the global override this is *not*
                all-or-nothing: the request still fails, naming the findings
                that remain unwaived.

        Returns:
            UUID of the newly created baseline.

        Raises:
            PermissionDeniedError: Caller lacks write permission, or lacks
                approval authority for an override/waiver.
            BaselineGateBlockedError: SE-Auditor BLOCKERs remain and no
                accepted override covers them (subclass of ValidationError).
            ValidationError: Scope not allowed by preset, duplicate name, a
                missing ``document_id`` for scope="document", an unusable
                override justification, a malformed or unmatched waiver, or an
                unevaluable gate.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        ws_id = UUID(str(workspace_id))

        # IF-AS-INT-006: scope gate via PresetPolicyService
        self._check_scope_allowed(str(ws_id), scope)

        try:
            doc_id: Optional[UUID] = (
                UUID(str(document_id)) if document_id is not None else None
            )
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValidationError(
                "Baseline cannot be created: document_id is not a valid UUID."
            ) from exc

        # GH-715: scope="document" requires a root artifact to resolve the
        # subtree against (see baseline.services.resolve_scope_item_ids). This
        # MUST be validated here, before the SE-Auditor gate is evaluated —
        # AuditContext.scope_item_ids resolves lazily via the same helper and
        # raises a bare ValueError when document_id/artifact_id is missing,
        # which _enforce_audit_gate's fail-closed handler (GH-400) would
        # otherwise catch and re-wrap as an opaque "internal error", hiding a
        # simple, callable-side validation problem behind a governance-gate
        # failure message.
        if scope == "document" and doc_id is None:
            raise ValidationError(
                "Baseline cannot be created: document_id is required when "
                "scope='document' (the root artifact whose subtree is being "
                "baselined)."
            )

        # SE-conformance gate: no baseline over known-broken traceability —
        # unless the blockers are explicitly and traceably waived (GH-513) or
        # individually waived with their own justification (GH-821).
        outcome = self._enforce_audit_gate(
            workspace_id=ws_id,
            scope=scope,
            document_id=doc_id,
            ctx=ctx,
            override_reason=override_reason,
            waived_findings=waived_findings,
        )
        effective_description = (
            _annotate_waiver(description, outcome, override_reason or "")
            if outcome.any_waived
            else description
        )

        # Delegate to baseline.services (IF-BL-EXT-IN-001)
        from baseline.services import build as baseline_build

        try:
            baseline_id = baseline_build(
                scope=scope,
                workspace_id=ws_id,
                name=name,
                tenant_id=ctx.tenant_id,
                description=effective_description,
                created_by=str(ctx.user_id),
                document_id=doc_id,
            )
        except Exception as exc:
            # Remap baseline-domain exceptions to application layer
            _remap_baseline_exc(exc)

        # Audit
        details: dict = {"scope": scope, "name": name, "workspace_id": str(ws_id)}
        audit_change_reason: Optional[str] = None
        if outcome.overridden:
            # The append-only audit log is the authoritative waiver record:
            # who waived what, when, and why (REQ-L2-AL-001).
            audit_change_reason = (override_reason or "").strip()
            details.update(
                {
                    "audit_gate_override": True,
                    "waived_blocker_count": len(outcome.overridden),
                    "waived_rule_ids": sorted({f.rule_id for f in outcome.overridden}),
                    "override_reason": audit_change_reason,
                }
            )
        if outcome.suppressed:
            # GH-821: per-finding waivers. The durable record is the
            # BaselineGateWaiver row (reason + author + timestamp) plus the
            # per-waiver ``baseline.waiver_create`` audit entry; the summary
            # below rides along with the existing ``baseline.create`` details
            # (``details`` is v1-reserved and currently dropped by the writer,
            # exactly like the GH-513 keys above — the change_reason set further
            # down is the part that persists).
            #
            # The canonical key is rendered WITHOUT the scope, deliberately
            # (see baseline.waivers.finding_key): that is the exact rendering
            # every persisted BaselineGateWaiver row was stored with, and this
            # summary has to name the same identities the rows match.
            from baseline.waivers import finding_key

            suppressed_keys = [
                finding_key(f.rule_id, f.artifact_ids) for f in outcome.suppressed
            ]
            details.update(
                {
                    "suppressed_blocker_count": len(outcome.suppressed),
                    "suppressed_rule_ids": sorted(
                        {f.rule_id for f in outcome.suppressed}
                    ),
                    "suppressed_finding_keys": suppressed_keys,
                    "waiver_ids": [str(waiver_id) for waiver_id in outcome.waiver_ids],
                    # #569/M4: all matched rows (created + reused), not only
                    # the ones created in this build. ``waiver_ids`` keeps the
                    # legacy "created here" meaning.
                    "matched_waiver_ids": [
                        str(waiver_id) for waiver_id in outcome.matched_waiver_ids
                    ],
                }
            )
            if audit_change_reason is None:
                audit_change_reason = (
                    f"{len(outcome.suppressed)} blocking finding(s) suppressed by "
                    "per-finding waivers (GH-821)."
                )
        self._audit(
            ctx=ctx,
            operation="baseline.create",
            entity_type="Baseline",
            entity_id=baseline_id,
            change_reason=audit_change_reason,
            details=details,
        )

        # Domain event (IF-AS-INT-009: BaselineCreated)
        self._emit_event(
            self._make_event(
                event_type="BaselineCreated",
                entity_id=baseline_id,
                workspace_id=ws_id,
                payload={
                    "scope": scope,
                    "name": name,
                    "audit_gate_override": bool(outcome.overridden),
                    "suppressed_blocker_count": len(outcome.suppressed),
                },
            )
        )

        return baseline_id

    # ---------- SE-conformance gate (lever 2) ----------

    def _enforce_audit_gate(
        self,
        *,
        workspace_id: UUID,
        scope: str,
        document_id: Optional[UUID],
        ctx: AuthContext,
        override_reason: Optional[str] = None,
        waived_findings: Optional[Sequence[Mapping[str, Any]]] = None,
        now: Optional[datetime] = None,
    ) -> GateWaiverOutcome:
        """Reject the baseline build when the SE-Auditor reports BLOCKERs.

        A baseline is a governance artefact: freezing a trace graph that the
        workspace's own rigor preset already declares broken makes every
        downstream diff and audit trail authoritative over known-bad data.
        The SE-Auditor (``traceability.audit``) has had BLOCKER-severity rules
        since SysEng 2.0 Phase 2 but was only ever exposed as a *report*; this
        is its first enforcement point.

        Tier awareness comes entirely from the existing
        ``RULE_PRESET_MAP``: Minimal maps to an empty rule set (structurally
        enforced in ``traceability.audit.registry``), so this method issues no
        query and never blocks there. Standard runs the baseline rule set with
        TRACE-P2 downgraded to WARNING; Extended adds the SE-only rules —
        both severity mappings are the RuleEngine's, not re-derived here.

        Latency: run synchronously, matching the surrounding code path —
        ``baseline.services.build`` (delta index + snapshot write) is itself
        synchronous, and the audit is a bounded set of aggregate queries over
        the same scope the build is about to walk. Making the gate async would
        mean the build could not consume its verdict.

        Fail-closed on auditor malfunction (GH-400): this is a governance
        gate, not a best-effort convenience check. An internal error while
        *evaluating* the gate (a bug in a rule, a DB hiccup, an unexpected
        AuditService exception) means the gate's verdict is unknown — and an
        unknown verdict must not be treated as "no BLOCKERs". The previous
        behaviour caught every non-``ValidationError`` exception, logged it,
        and returned as if the audit had come back clean, i.e. an internal
        fault in the gate *itself* silently opened the gate it was supposed
        to guard. Fail-closed here means: surface a clear, catchable
        ``ValidationError`` to the caller (blocking the baseline build) and
        log the original exception via ``logger.exception`` for operators —
        never a silent pass-through.

        Override (GH-513): fail-closed with no exit is a deadlock, not a gate.
        Most findings have no automatic remediation ("Adopt"), and the Auditor
        UI has no manual edit flow, so a workspace with a single stubborn
        BLOCKER could produce no baseline at all — no release, no review, no
        way forward. The gate therefore keeps its default (block), and adds
        one narrow, expensive exit: an explicit written justification from a
        caller with approval authority. Why those three constraints:

          * *explicit* — the override is never implied by a retry; the caller
            has to send ``override_reason`` on purpose;
          * *justified* — the reason is stored in the append-only audit log
            and on the baseline itself, so a later reader sees a waiver rather
            than a clean baseline;
          * *authorised* — waiving a compliance verdict is an approval act
            (``Operation.WORKFLOW_APPROVAL``: Admin or Approver), not a write
            act; every Editor being able to wave the gate through would make
            it decorative.

        The GH-400 fail-closed branch above is deliberately *not* overridable:
        it fires when the verdict is unknown, and an unknown verdict cannot be
        justified — nobody can state what is being accepted.

        Per-finding waivers (GH-821): the global override is the coarse lever —
        it answers "I accept every remaining deviation" with one sentence, which
        is exactly the wrong tool for a workspace whose 47 findings contain 3
        real ones and 44 known-accepted ones. A caller may therefore waive
        *individual* findings instead, each with its own mandatory
        justification, granted by the same authority (Admin/Approver) and
        persisted as a ``BaselineGateWaiver`` row. Waivers already on file are
        applied automatically on later builds — that is what makes them a
        suppression rather than a per-request incantation — and only the
        findings that remain unwaived are reported as blockers.

        Waivers are matched against the findings the auditor *actually*
        returned. Naming a finding that is not blocking is refused
        (``ValidationError``) rather than stored: a waiver is an acceptance of a
        known deviation, and accepting something that does not exist would
        silently suppress it if it ever appeared.

        Args:
            override_reason: Justification for waiving the remaining BLOCKER
                findings, or ``None``/blank for the default (blocking)
                behaviour.
            waived_findings: Per-finding waivers (``GH-821``), each a mapping
                with ``rule_id``, ``artifact_ids`` and a mandatory ``reason``.
            now: Injectable decision instant (#569/D3) for expiry evaluation of
                persisted suppressions; ``None`` uses the current time. Additive
                and keyword-only so every existing caller is unaffected.

        Returns:
            A :class:`GateWaiverOutcome`. Empty for a clean audit and for a
            plain (unwaived) block; the caller records what it contains.

        Raises:
            BaselineGateBlockedError: Unwaived BLOCKER findings remain and no
                global override covers them.
            PermissionDeniedError: Override or waiver attempted without
                approval authority.
            ValidationError: Override justification or waiver unusable/unknown,
                OR the SE-Auditor gate itself failed to evaluate (fail-closed,
                not overridable).
        """
        from application.audit_service import AuditService
        from traceability.audit import AuditScope

        audit_scope = AuditScope(
            scope=scope,
            artifact_id=str(document_id) if document_id is not None else None,
        )
        try:
            findings = AuditService().blocking_findings(
                workspace_id, ctx, scopes=[audit_scope]
            )
        except ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Fail CLOSED on an auditor malfunction (GH-400): a governance
            # gate that cannot be evaluated must block, not silently pass.
            logger.exception(
                "BaselineFacade: SE-Auditor gate failed for ws=%s scope=%s; "
                "blocking the baseline build (fail-closed)",
                workspace_id,
                scope,
            )
            raise ValidationError(
                "Baseline cannot be created: the SE-Auditor gate could not be "
                "evaluated due to an internal error. Baseline creation is "
                "blocked until the SE-Auditor is operational again — this is a "
                "fail-closed governance gate, not a best-effort check."
            ) from exc

        if not findings:
            # A clean audit makes both waiver forms inert (nothing is stored and
            # nothing is recorded) — mirroring the GH-513 behaviour pinned by
            # ``test_override_reason_on_a_clean_workspace_is_inert``: a retry
            # after the findings were fixed must not fail on its now-stale
            # waivers.
            return GateWaiverOutcome()

        requests = self._coerce_waiver_requests(waived_findings)
        suppressed, remaining, waiver_ids, matched_waiver_ids = self._apply_waivers(
            workspace_id=workspace_id,
            scope=scope,
            ctx=ctx,
            findings=findings,
            requests=requests,
            now=now,
        )

        if not remaining:
            return GateWaiverOutcome(
                suppressed=suppressed,
                waiver_ids=waiver_ids,
                matched_waiver_ids=matched_waiver_ids,
            )

        if override_reason is not None and str(override_reason).strip():
            self._assert_override_permission(ctx)
            self._validate_override_reason(override_reason)
            logger.warning(
                "BaselineFacade: SE-Auditor gate OVERRIDDEN for ws=%s scope=%s by "
                "user=%s — %s blocking finding(s) waived (%s); reason: %s",
                workspace_id,
                scope,
                getattr(ctx, "user_id", "?"),
                len(remaining),
                ", ".join(sorted({f.rule_id for f in remaining})),
                str(override_reason).strip(),
            )
            return GateWaiverOutcome(
                overridden=remaining,
                suppressed=suppressed,
                waiver_ids=waiver_ids,
                matched_waiver_ids=matched_waiver_ids,
            )

        raise BaselineGateBlockedError(
            f"Baseline cannot be created: the SE-Auditor reported "
            f"{len(remaining)} blocking finding(s) for this workspace. "
            f"Resolve them first — {_summarise_findings(remaining)}. "
            "If a single finding is an accepted deviation, an Admin or Approver "
            "can waive it individually with a written justification "
            "(waived_findings: [{rule_id, artifact_ids, reason}]); to accept "
            "everything that is still reported, they can supply one "
            "override_reason instead. Either way the decision is recorded in "
            "the audit log and on the baseline."
        )

    def _apply_waivers(
        self,
        *,
        workspace_id: UUID,
        scope: str,
        ctx: AuthContext,
        findings: Sequence["Finding"],
        requests: Sequence["BlockerWaiverRequest"],
        now: Optional[datetime] = None,
    ) -> Tuple[Tuple["Finding", ...], Tuple["Finding", ...], Tuple[UUID, ...], Tuple[UUID, ...]]:
        """Suppress findings covered by per-finding waivers (GH-821, #569).

        Two sources count as "covered": the waivers on file for this workspace
        (persisted by an earlier build — a suppression is durable, otherwise
        every release would have to re-state all 47 justifications) and the ones
        supplied with this request.

        Newly supplied waivers are validated against the *actual* findings and
        persisted; each newly created row also gets its own audit entry, so the
        grant is traceable independently of the baseline it was first used for.
        (On the MCP path an enclosing ``mcp_audit_handoff`` suppresses inner
        audit writes by convention — Codeberg #313 — so there the waiver row and
        the tool call's own entry are the record.) Waivers already on file are
        neither re-validated nor re-audited.

        #569/M7: coverage is decided by :func:`baseline.waivers.suppression_applies`
        (R1–R3: scope-less key + scope binding + expiry), *not* by a scope-blind
        key-set membership. That is what keeps a document-bound waiver from
        silently suppressing the scope-agnostic finding of the same rule, while
        the production-real GH-821 rows (``scope="project"``,
        ``scope_artifact_id=""``) keep matching. Expiry is evaluated here at
        decision time; ``now`` is injectable (#569/D3).

        Returns:
            ``(suppressed_findings, remaining_findings, created_waiver_ids,
            matched_waiver_ids)``. ``created_waiver_ids`` is the legacy
            ``waiver_ids`` contract (rows created by this request only);
            ``matched_waiver_ids`` names **every** matched row — created *and*
            reused (#569/M4).

        Raises:
            PermissionDeniedError: Waivers supplied without approval authority.
            ValidationError: A supplied waiver is malformed or names a finding
                that is not blocking.
        """
        from baseline.waivers import (
            finding_key,
            load_suppressions,
            record_waiver,
            suppression_applies,
        )

        created_ids: List[UUID] = []
        if requests:
            # Same authority as the global override: accepting a known
            # deviation is an approval act, not a write act.
            self._assert_override_permission(ctx)
            by_key = {
                finding_key(f.rule_id, f.artifact_ids): f for f in findings
            }
            unknown = [r for r in requests if r.key not in by_key]
            if unknown:
                raise ValidationError(
                    "Baseline cannot be created: "
                    f"{len(unknown)} supplied waiver(s) name finding(s) that the "
                    "SE-Auditor is not currently reporting as blocking "
                    f"({', '.join(sorted({r.rule_id for r in unknown}))}). "
                    "Waivers may only accept deviations that actually exist — "
                    "re-run the SE-Auditor and waive the findings it reports."
                )
            for request in requests:
                finding = by_key[request.key]
                row, created = record_waiver(
                    workspace_id=workspace_id,
                    tenant_id=ctx.tenant_id,
                    request=request,
                    rule_id=finding.rule_id,
                    scope=finding.scope or scope,
                    scope_artifact_id=finding.scope_artifact_id,
                    granted_by=str(getattr(ctx, "user_id", "") or ""),
                )
                if not created:
                    continue
                created_ids.append(row.id)
                # Per-blocker audit entry (GH-821): the waiver's own reason and
                # author, next to — not inside — the baseline.create summary.
                self._audit(
                    ctx=ctx,
                    operation="baseline.waiver_create",
                    entity_type="BaselineGateWaiver",
                    entity_id=row.id,
                    change_reason=request.reason,
                    details={
                        "workspace_id": str(workspace_id),
                        "rule_id": finding.rule_id,
                        "artifact_ids": list(request.artifact_ids),
                        "scope": finding.scope or scope,
                    },
                )
                logger.warning(
                    "BaselineFacade: blocking finding %s waived for ws=%s by "
                    "user=%s; reason: %s",
                    finding.rule_id,
                    workspace_id,
                    getattr(ctx, "user_id", "?"),
                    request.reason,
                )

        # Reloaded after any grants so newly persisted rows suppress too; only
        # active rows are candidates (expiry is part of the decision).
        records = load_suppressions(
            workspace_id, ctx.tenant_id, include_expired=False, now=now
        )

        suppressed: List["Finding"] = []
        remaining: List["Finding"] = []
        matched_ids: List[UUID] = []
        for finding in findings:
            matching = [
                record
                for record in records
                if suppression_applies(
                    record,
                    finding.rule_id,
                    finding.artifact_ids,
                    finding.scope,
                    finding.scope_artifact_id,
                    now=now,
                )
            ]
            if matching:
                suppressed.append(finding)
                for record in matching:
                    if record.id not in matched_ids:
                        matched_ids.append(record.id)
            else:
                remaining.append(finding)

        return (
            tuple(suppressed),
            tuple(remaining),
            tuple(created_ids),
            tuple(matched_ids),
        )

    @staticmethod
    def _coerce_waiver_requests(
        raw: Optional[Sequence[Mapping[str, Any]]],
    ) -> Tuple["BlockerWaiverRequest", ...]:
        """Normalize caller-supplied waivers, or raise ``ValidationError``.

        One normalisation point for both surfaces (REST serializer and MCP
        params): the caller identifies a finding and justifies accepting it, and
        everything else — canonical artifact ordering, de-duplication, the
        reason policy — is decided here. Messages are deliberately static: no
        payload echo, no internals.
        """
        if raw is None:
            return ()
        if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
            raise ValidationError(
                "Baseline cannot be created: waived_findings must be a list of "
                "{rule_id, artifact_ids, reason} objects."
            )

        from baseline.waivers import BlockerWaiverRequest, canonical_artifact_ids

        coerced: dict[str, BlockerWaiverRequest] = {}
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, Mapping):
                raise ValidationError(
                    f"Baseline cannot be created: waived_findings[{index}] must "
                    "be an object with rule_id, artifact_ids and reason."
                )
            rule_id = str(item.get("rule_id") or "").strip()
            if not rule_id:
                raise ValidationError(
                    f"Baseline cannot be created: waived_findings[{index}] is "
                    "missing rule_id (the SE-Auditor rule being waived)."
                )
            artifact_ids = item.get("artifact_ids") or ()
            if isinstance(artifact_ids, (str, bytes)) or not isinstance(
                artifact_ids, (list, tuple)
            ):
                raise ValidationError(
                    f"Baseline cannot be created: waived_findings[{index}]."
                    "artifact_ids must be a list of artifact UUIDs."
                )
            cleaned_ids = tuple(str(a).strip() for a in artifact_ids)
            if not all(cleaned_ids):
                raise ValidationError(
                    f"Baseline cannot be created: waived_findings[{index}]."
                    "artifact_ids must not contain empty entries."
                )
            reason = _validate_gate_reason(
                str(item.get("reason") or ""),
                label=f"waived_findings[{index}] justification",
            )
            request = BlockerWaiverRequest(
                rule_id=rule_id,
                artifact_ids=canonical_artifact_ids(cleaned_ids),
                reason=reason,
            )
            # A repeat of the same finding is not an error, but it must not
            # produce two rows (the DB unique constraint would reject the
            # second) or two conflicting justifications.
            coerced.setdefault(request.key, request)
        return tuple(coerced.values())

    @staticmethod
    def _assert_override_permission(ctx: AuthContext) -> None:
        """Require approval authority (Admin/Approver) to waive the gate.

        #569/M2: this is now a thin delegator to
        :func:`baseline.waivers.assert_gate_waiver_authority` — the single
        authority choke point shared with ``AuditService.suppress_finding``, so
        there is exactly one copy of the rule and no drift between the gate
        waiver and the Auditor suppression paths. Kept as a
        ``@staticmethod`` so direct callers
        (``test_granular_api_key_scope_865.py``) stay compatible.

        The Layer-1 helper raises the domain error
        ``GovernanceAuthorityError``; it is remapped here to the Layer-2
        ``PermissionDeniedError`` (403) exactly as before. #865: an API key
        additionally has to carry the ADMIN capability tier — an AUTHOR-tier
        (content-writing) key must not be able to talk its way past the gate.
        Keys without a scope at all (JWT bearer sessions) are unaffected, and
        the legacy ``write`` alias is the ADMIN tier.
        """
        from baseline.exceptions import GovernanceAuthorityError
        from baseline.waivers import assert_gate_waiver_authority

        try:
            assert_gate_waiver_authority(ctx)
        except GovernanceAuthorityError as exc:
            raise PermissionDeniedError(str(exc)) from exc

    @staticmethod
    def _validate_override_reason(override_reason: str) -> None:
        """Reject a justification that would not survive an audit (GH-821)."""
        _validate_gate_reason(override_reason, label="override justification")

    def diff_baselines(
        self,
        baseline_a_id: UUID | str,
        baseline_b_id: UUID | str,
        ctx: AuthContext,
    ):
        """Compute structural diff between two baselines.

        REQ-L3-AS006-003.

        Args:
            baseline_a_id: Reference (older) baseline UUID.
            baseline_b_id: Target (newer) baseline UUID.
            ctx: AuthContext for tenant propagation.

        Returns:
            DiffResult (baseline.types.DiffResult).
        """
        self._set_tenant_context(ctx)

        from baseline.services import diff as baseline_diff

        try:
            return baseline_diff(
                baseline_a_id=UUID(str(baseline_a_id)),
                baseline_b_id=UUID(str(baseline_b_id)),
                tenant_id=ctx.tenant_id,
            )
        except Exception as exc:
            _remap_baseline_exc(exc)

    def get_baseline(self, baseline_id: UUID | str, ctx: AuthContext):
        """Return full baseline detail including delta entries.

        Args:
            baseline_id: UUID of the target baseline.
            ctx: AuthContext for tenant propagation.

        Returns:
            BaselineDetail (baseline.types.BaselineDetail).
        """
        self._set_tenant_context(ctx)

        from baseline.services import get as baseline_get

        try:
            return baseline_get(baseline_id=UUID(str(baseline_id)), tenant_id=ctx.tenant_id)
        except Exception as exc:
            _remap_baseline_exc(exc)

    def list_baselines(
        self,
        workspace_id: UUID | str,
        ctx: AuthContext,
        scope: Optional[str] = None,
    ) -> List:
        """Return baseline summaries for a workspace.

        Args:
            workspace_id: Target workspace UUID.
            ctx: AuthContext for tenant propagation.
            scope: Optional scope filter.

        Returns:
            List of BaselineSummary.
        """
        self._set_tenant_context(ctx)

        from baseline.services import list_baselines as baseline_list

        return baseline_list(
            workspace_id=UUID(str(workspace_id)),
            scope=scope,
            tenant_id=ctx.tenant_id,
        )

    def get_item_at_baseline(
        self,
        baseline_id: UUID | str,
        item_id: str,
        ctx: AuthContext,
    ):
        """Reconstruct historical payload of an item at baseline time.

        Args:
            baseline_id: UUID of the target baseline.
            item_id: String UUID of the item.
            ctx: AuthContext for tenant propagation.

        Returns:
            ItemPayload (baseline.types.ItemPayload).
        """
        self._set_tenant_context(ctx)

        from baseline.services import get_item_at_baseline as baseline_item

        try:
            return baseline_item(
                baseline_id=UUID(str(baseline_id)),
                item_id=item_id,
                tenant_id=ctx.tenant_id,
            )
        except Exception as exc:
            _remap_baseline_exc(exc)

    # ---------- Private helpers ----------

    @staticmethod
    def _check_scope_allowed(workspace_id: str, scope: str) -> None:
        """Raise ValidationError if preset forbids this scope.

        IF-AS-INT-006 → PresetPolicyService.is_scope_allowed().
        """
        # get_preset_policy_service is imported at module level to allow test mocking.
        policy = get_preset_policy_service()
        if not policy.is_scope_allowed(workspace_id, scope):
            allowed = policy.get_policy(workspace_id, "baseline_scopes")
            raise ValidationError(
                f"Baseline scope '{scope}' is not allowed by the workspace preset. "
                f"Allowed values: {sorted(allowed)}"
            )


# ---------- SE-Auditor gate helpers (GH-513) ----------

#: How many individual findings the block message enumerates. The QS instance
#: hit 77 BLOCKERs; inlining all of them produced a multi-kilobyte error string
#: that no UI could render usefully. The full list belongs in the Auditor
#: dashboard, which is what the truncation hint points at.
_MAX_LISTED_FINDINGS = 10


def _summarise_findings(findings: Sequence["Finding"]) -> str:
    """Render up to :data:`_MAX_LISTED_FINDINGS` findings, then a count hint."""
    listed = "; ".join(
        f"{f.rule_id} [{', '.join(f.artifact_ids) or 'graph'}]: {f.message}"
        for f in findings[:_MAX_LISTED_FINDINGS]
    )
    remaining = len(findings) - _MAX_LISTED_FINDINGS
    if remaining > 0:
        listed += (
            f"; … and {remaining} more (see the SE-Auditor dashboard for the "
            "full list)"
        )
    return listed


def _validate_gate_reason(reason: str, *, label: str) -> str:
    """Return the cleaned justification, or raise ``ValidationError`` (GH-821).

    #569/M2/D4: a thin delegator to
    :func:`baseline.waivers.validate_waiver_reason` — the single source of truth
    for the reason policy, now owned at Layer 1. It stays a **module-level
    function** (not a method) because callers
    (``_coerce_waiver_requests``, ``_validate_override_reason``) and tests
    (``from application.baseline_facade import _validate_gate_reason``) use it
    that way.

    The Layer-1 helper raises the domain error ``GovernanceReasonError``; it is
    re-raised here as a plain ``application.base.ValidationError`` so the legacy
    ``waived_findings`` path keeps its exact type, message and 400
    ``VALIDATION_ERROR`` code (never ``WAIVER_REASON_REJECTED`` — that dedicated
    code belongs to the new Auditor suppression surface only, #569 §7 Non-Goal).
    The policy rules (length, word count, distinct words, readable word, no
    rule-id echo) are documented on the Layer-1 helper.

    Args:
        reason: Raw caller input.
        label: Field name for the error message (surfaced verbatim to the
            caller; contains no internals).

    Returns:
        The cleaned (stripped) justification.
    """
    from baseline.exceptions import GovernanceReasonError
    from baseline.waivers import validate_waiver_reason

    try:
        return validate_waiver_reason(reason, label=label)
    except GovernanceReasonError as exc:
        raise ValidationError(str(exc)) from exc


def _annotate_waiver(
    description: Optional[str],
    outcome: GateWaiverOutcome,
    override_reason: str,
) -> str:
    """Append the waiver note to the baseline description (GH-513, GH-821, #569).

    A baseline created over known BLOCKERs must not be indistinguishable from
    a clean one. The audit log is the authoritative record, but it is not what
    a reviewer opening the baseline sees — the description is, and it is
    written once at creation time, so this does not touch the snapshot's
    immutability guarantee (``bl_baseline_snapshot`` rejects UPDATEs).

    The two notes are kept distinct on purpose: ``override`` means "every
    remaining finding was accepted at once", ``waiver`` means "these specific
    findings were accepted, each with its own reason". Flattening them into one
    sentence would hide which of the two governance acts actually happened.

    #569/M4: the waiver note also names the **matched** waiver ids (created and
    reused), so a reused waiver is visible on the immutable baseline. The list
    is capped like :func:`_summarise_findings` (plus a count hint) to keep the
    description bounded when a workspace has many waivers.
    """
    notes: list[str] = []
    if outcome.overridden:
        rule_ids = ", ".join(sorted({f.rule_id for f in outcome.overridden}))
        notes.append(
            f"[SE-Auditor override] {len(outcome.overridden)} blocking finding(s) "
            f"waived ({rule_ids}). Justification: {override_reason.strip()}"
        )
    if outcome.suppressed:
        rule_ids = ", ".join(sorted({f.rule_id for f in outcome.suppressed}))
        waiver_part = _summarise_waiver_ids(outcome.matched_waiver_ids)
        notes.append(
            f"[SE-Auditor waiver] {len(outcome.suppressed)} blocking finding(s) "
            f"suppressed by per-finding waiver ({rule_ids}, GH-821). "
            f"Waiver ids: {waiver_part}. "
            "Justifications: see the audit log (baseline.waiver_create)."
        )
    existing = (description or "").strip()
    joined = "\n\n".join(notes)
    return f"{existing}\n\n{joined}" if existing else joined


def _summarise_waiver_ids(waiver_ids: Sequence[UUID]) -> str:
    """Render up to :data:`_MAX_LISTED_FINDINGS` waiver ids, then a count hint."""
    if not waiver_ids:
        return "none"
    listed = ", ".join(str(waiver_id) for waiver_id in waiver_ids[:_MAX_LISTED_FINDINGS])
    remaining = len(waiver_ids) - _MAX_LISTED_FINDINGS
    if remaining > 0:
        listed += f"; … and {remaining} more"
    return listed


# ---------- Exception remapping ----------

def _remap_baseline_exc(exc: Exception) -> None:
    """Re-raise baseline-domain exceptions as application-layer exceptions."""
    from baseline.exceptions import (
        BaselineNotFoundError,
        DuplicateBaselineNameError,
        EmptyBaselineNameError,
        ScopeNotAllowedError,
    )
    from application.base import NotFoundError, ValidationError

    if isinstance(exc, (ScopeNotAllowedError, EmptyBaselineNameError, DuplicateBaselineNameError)):
        raise ValidationError(str(exc)) from exc
    if isinstance(exc, BaselineNotFoundError):
        raise NotFoundError(str(exc)) from exc
    raise exc


__all__ = ["BaselineFacade", "GateWaiverOutcome"]
