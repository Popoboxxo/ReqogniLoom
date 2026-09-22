"""Per-blocker SE-Auditor gate waivers and findings suppressions (GH-821, #569).

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

#569 adds the standalone suppression surface: the same ``BaselineGateWaiver``
entity (no second table, no second truth about "what is a finding") is now also
reachable through the Auditor UI / MCP, carries an optional ``expires_at`` and is
matched through :func:`suppression_applies` — the single matcher used by both the
report (#569 report marking) and the gate (#490). Expiry is evaluated *at
decision time* (``now`` is injectable), never persisted as a state column and
never driven by a background job.

This module is Layer 1 and deliberately does **not** import any facade. The two
governance choke points it owns — :func:`validate_waiver_reason` and
:func:`assert_gate_waiver_authority` — raise the domain errors from
``baseline.exceptions``; the Layer-2 facades remap them to their own exception
types (D4/M2, #569).

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
import re
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

from django.utils import timezone

from baseline.exceptions import GovernanceAuthorityError, GovernanceReasonError
from baseline.models import BaselineGateWaiver

logger = logging.getLogger(__name__)

#: Field separator between the rule id and the artifact ids inside a finding
#: key. A unit separator cannot appear in a rule id or an artifact id, so the
#: rendering stays injective — no pair of distinct findings can collide into
#: the same key and silently waive the wrong one.
_KEY_SEPARATOR = "\x1f"

#: Separator between the artifact ids of one finding.
_ARTIFACT_SEPARATOR = ","

#: Minimum length of an SE-Auditor justification (GH-513, hardened by GH-821).
#: A waiver is a governance record that outlives the person who granted it —
#: "ok" or "later" is not one. Length alone is a weak bar though
#: ("aaaaaaaaaaaaaaa" cleared the old 10-character rule), so
#: :func:`validate_waiver_reason` layers content checks on top of it: a minimum
#: word count, a minimum number of *distinct* words (blocks padding with one
#: repeated token) and at least one readable word. A sentence written for a
#: reviewer passes; a placeholder does not.
#:
#: Moved here from ``application.baseline_facade`` (#569/D4) so the policy has
#: exactly one home at Layer 1; the facade re-exports the three public constants
#: so the established import surface stays valid.
MIN_OVERRIDE_REASON_LENGTH = 15

#: Minimum words in a justification (GH-821).
MIN_REASON_WORDS = 4

#: Minimum *distinct* words in a justification (GH-821). Blocks "test test
#: test test" and one-token padding, which a raw word count would accept.
MIN_REASON_DISTINCT_WORDS = 3

#: Words shorter than this do not count towards the word minimum — they are
#: almost always punctuation fragments ("a", "z") rather than content.
_MIN_REASON_WORD_LENGTH = 2

#: A readable word: three or more consecutive letters (Unicode-aware). Rejects
#: justifications made of digits, ids or punctuation only.
_READABLE_WORD_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)

#: An audit rule id token ("TRACE-P1", "VERIF-P8"). Tokens matching this carry
#: no reasoning — they only repeat the verdict the gate just printed, which is
#: why they do not count towards the word minimum (GH-821: "copied the finding
#: list into the justification" must not pass as a justification).
_RULE_ID_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")


def _resolve_now(now: datetime | None) -> datetime:
    """Return an aware UTC instant for expiry comparisons (#569/D3).

    ``now`` is injectable so expiry is deterministic in tests; a naive value is
    interpreted as UTC (the storage convention) instead of raising a TypeError
    deep inside a comparison.
    """
    if now is None:
        return timezone.now()
    if timezone.is_naive(now):
        return now.replace(tzinfo=dt_timezone.utc)
    return now


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    """True when *expires_at* is set and not in the future relative to *now*.

    A ``NULL`` expiry means unbounded (GH-821 behaviour, no regression).
    """
    if expires_at is None:
        return False
    expires = (
        expires_at if not timezone.is_naive(expires_at) else expires_at.replace(
            tzinfo=dt_timezone.utc
        )
    )
    return expires <= now


def canonical_artifact_ids(artifact_ids: Iterable[Any] | None) -> tuple[str, ...]:
    """Return the finding's artifact ids as a sorted, de-duplicated tuple.

    Sorting is what makes the key order-independent: a rule that reports
    ``("a", "b")`` and one that reports ``("b", "a")`` describe the same
    blocker and must match the same waiver.
    """
    return tuple(sorted({str(artifact_id) for artifact_id in (artifact_ids or ())}))


def finding_key(
    rule_id: str, artifact_ids: Iterable[Any] | None, scope: Any | None = None
) -> str:
    """Return the canonical identity of an audit finding.

    A ``Finding`` (``traceability.audit.types``) has no stable id — it is
    re-derived on every run. Its identity is therefore the rule that reported
    it plus the artifacts it concerns, rendered canonically (see
    :func:`canonical_artifact_ids`), optionally plus the baseline scope it was
    reported in. This one function is the single source of truth: the gate's
    waiver matching, the audit API's ``finding_key`` field and (from #569) the
    suppression lookup all render a finding's identity through it.

    ``scope`` is optional and, when omitted/empty, the rendering is
    **byte-identical to the pre-#1021 format** (``rule_id<US>a,b``). That is a
    compatibility guarantee, not an accident: ``BaselineGateWaiver`` rows
    (GH-821) are append-only governance records that were persisted with that
    exact rendering, so changing it would silently orphan every waiver on file
    and re-block workspaces whose deviations were already accepted. The gate
    (``authoring:application.baseline_facade``) therefore keeps calling this
    function without ``scope`` — it audits exactly one scope per call, so the
    same rule/artifact pair cannot be blocking twice for different reasons.
    Callers that *do* audit several scopes at once, or that need the
    identity a future per-scope suppression entity keys on, pass the finding's
    ``scope`` and get the extended ``rule_id<US>a,b<US>scope`` form.

    Args:
        rule_id: The reporting rule (e.g. ``"TRACE-P1"``).
        artifact_ids: Artifacts the finding concerns. Order-insensitive,
            de-duplicated; empty for graph-level findings.
        scope: The baseline scope the finding was reported in
            (``"document"`` | ``"project"`` | ``"global"``), or ``None`` for a
            scope-agnostic finding. Embedded as-is; a unit separator inside it
            is stripped so the rendering stays injective.
    """
    base = (
        f"{str(rule_id).strip()}{_KEY_SEPARATOR}"
        f"{_ARTIFACT_SEPARATOR.join(canonical_artifact_ids(artifact_ids))}"
    )
    # mutation-probe: removing the two lines below makes
    # test_audit_finding_identity_1021.py::TestCanonicalFindingKey::
    # test_the_scope_less_rendering_is_byte_identical_to_the_legacy_format and
    # test_waivers_569.py::test_unscoped_finding_key_is_byte_identical_to_persisted_gh821_rows
    # fail ("TRACE-P1\x1fa\x1f" != "TRACE-P1\x1fa") — the GH-821 compatibility
    # branch is load-bearing, not cosmetic.
    scope_part = str(scope or "").strip().replace(_KEY_SEPARATOR, "")
    if not scope_part:
        return base
    return f"{base}{_KEY_SEPARATOR}{scope_part}"


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
        expires_at: Optional expiry of the waiver (#569). ``None`` means
            unbounded. Additive; the gate path leaves it ``None``.
    """

    rule_id: str
    artifact_ids: tuple[str, ...]
    reason: str
    expires_at: datetime | None = None

    @property
    def key(self) -> str:
        """Canonical :func:`finding_key` of this request."""
        return finding_key(self.rule_id, self.artifact_ids)


@dataclass(frozen=True)
class SuppressionRecord:
    """One persisted suppression, already normalised for matching (#569).

    A read-model of a ``BaselineGateWaiver`` row: :func:`load_suppressions`
    normalises the nullable/blank column values (``scope``/``scope_artifact_id``
    -> ``""``) so :func:`suppression_applies` never has to guard against a
    hypothetical ``NULL`` if the columns are ever made nullable.

    Attributes:
        id: Waiver row id (UUID).
        finding_key: Persisted, scope-less key (``row.finding_key``).
        rule_id: Canonical rule id of the suppressed finding.
        artifact_ids: Artifacts the waived finding concerns.
        scope: ``""`` means scope-agnostic/unbound.
        scope_artifact_id: ``""`` means not bound to a document.
        reason: The justification on file.
        granted_by: Author id recorded when the waiver was granted.
        created_at: Row creation timestamp.
        expires_at: ``None`` = unbounded; ``<= now`` = expired (#569 R3).
    """

    id: UUID
    finding_key: str
    rule_id: str
    artifact_ids: tuple[str, ...]
    scope: str
    scope_artifact_id: str
    reason: str
    granted_by: str
    created_at: datetime
    expires_at: datetime | None


def suppression_applies(
    record: SuppressionRecord,
    rule_id: str,
    artifact_ids: Iterable[Any] | None,
    scope: str | None = None,
    scope_artifact_id: str | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether *record* suppresses the described finding (#569).

    The single matcher for both the audit report marking and the baseline gate
    (#490). Rule set (R1–R3, spec §3.1):

    * **R1 (key)** — the record's persisted scope-less key equals
      ``finding_key(rule_id, artifact_ids)``. Always mandatory; exactly the
      legacy GH-821 matching.
    * **R2 (scope binding)** — OR over R2a–R2c, at least one must hold:
      * **R2a** ``record.scope == ""`` — unbound, matches any finding with the
        same key (GH-821 behaviour, and the form #569 itself writes for
        scope-agnostic findings).
      * **R2b** the finding is scope-agnostic (``scope`` falsy) — matches only
        when ``record.scope_artifact_id == ""``. Keeps the production-real
        GH-821 rows (``scope="project"``, ``scope_artifact_id=""``) alive while
        preventing a document-bound waiver from silently suppressing the
        scope-agnostic finding of the same rule/artifacts.
      * **R2c** ``record.scope == finding.scope`` — and for ``document``
        additionally only in the exact same document.
    * **R3 (expiry)** — the record is not expired relative to ``now``.

    ``now`` is keyword-only and additive (defaults to the current instant) so
    expiry is deterministically testable at decision time (#569/D3).

    # mutation-probe: removing the R2a/R2b clauses makes
    # test_baseline_gate_waivers_569.py::
    # test_pre_569_persisted_project_stamped_waiver_still_suppresses_after_matcher_switch
    # fail (a GH-821 row stamped ``scope="project"``/``scope_artifact_id=""``
    # no longer suppresses a scope-agnostic finding).
    """
    if record.finding_key != finding_key(rule_id, artifact_ids):
        return False

    finding_scope = str(scope).strip() if scope is not None else ""
    record_scope = record.scope or ""
    record_document = record.scope_artifact_id or ""
    finding_document = (
        str(scope_artifact_id).strip() if scope_artifact_id is not None else ""
    )

    if record_scope == "":
        scope_matches = True
    elif not finding_scope:
        scope_matches = record_document == ""
    elif record_scope == finding_scope:
        scope_matches = (
            finding_scope != "document" or record_document == finding_document
        )
    else:
        scope_matches = False

    if not scope_matches:
        return False

    return not _is_expired(record.expires_at, _resolve_now(now))


def load_suppressions(
    workspace_id: UUID | str,
    tenant_id: UUID | str,
    *,
    include_expired: bool = False,
    now: datetime | None = None,
) -> tuple[SuppressionRecord, ...]:
    """Load the workspace's waivers as :class:`SuppressionRecord` read-models.

    Read-only; a workspace without waivers yields an empty tuple. Errors
    propagate to the caller (the gate decides how to fail — it fails closed).

    Args:
        workspace_id: Workspace whose waivers are loaded.
        tenant_id: Active tenant (explicit row-level isolation, mirroring the
            rest of this module).
        include_expired: When ``False`` (the default) rows whose ``expires_at``
            is ``<= now`` are omitted — the "still suppress?" answer at decision
            time. ``list_suppressions``/the report pass ``True`` to show them as
            ``state="expired"``.
        now: Injectable evaluation instant (#569/D3); defaults to the current
            time. Naive values are interpreted as UTC.
    """
    cutoff = _resolve_now(now)
    rows = (
        BaselineGateWaiver.unscoped.filter(
            workspace_id=workspace_id, tenant_id=tenant_id
        )
        .order_by("created_at", "id")
    )
    records: list[SuppressionRecord] = []
    for row in rows:
        expires_at = row.expires_at
        if not include_expired and _is_expired(expires_at, cutoff):
            continue
        records.append(
            SuppressionRecord(
                id=row.id,
                finding_key=row.finding_key,
                rule_id=row.rule_id,
                artifact_ids=tuple(str(a) for a in (row.artifact_ids or ())),
                scope=row.scope or "",
                scope_artifact_id=row.scope_artifact_id or "",
                reason=row.reason,
                granted_by=row.granted_by or "",
                created_at=row.created_at,
                expires_at=expires_at,
            )
        )
    return tuple(records)


def load_waived_finding_keys(
    workspace_id: UUID | str, tenant_id: UUID | str, *, now: datetime | None = None
) -> frozenset[str]:
    """Return the finding keys **actively** waived in *workspace_id*.

    Compatibility wrapper (GH-821) kept as a public contract for external
    callers and tests: the two-argument call remains positionally valid and
    returns only non-expired keys (#569/AC-569-24). Consumers that need the
    scope-aware answer use :func:`load_suppressions` +
    :func:`suppression_applies`; a scope-blind key set is exactly what #569
    stopped doing in the gate.

    Read-only; a workspace without waivers yields an empty set. Errors
    propagate to the caller (the gate decides how to fail — it fails closed).
    """
    return frozenset(
        record.finding_key
        for record in load_suppressions(
            workspace_id, tenant_id, include_expired=False, now=now
        )
    )


def validate_waiver_reason(reason: str, *, label: str) -> str:
    """Return the cleaned justification, or raise ``GovernanceReasonError``.

    The single source of truth for the waiver/suppression reason policy
    (GH-821, moved from ``application.baseline_facade`` in #569/D4). It lives
    at Layer 1 and raises the domain error, because a Layer-1 module must not
    import ``application.base.ValidationError``. Facades remap:

      * ``application.baseline_facade._validate_gate_reason`` -> plain
        ``ValidationError`` (legacy ``waived_findings`` path, unchanged);
      * ``application.audit_service.AuditService.suppress_finding`` ->
        ``WaiverReasonPolicyViolation`` (400 ``WAIVER_REASON_REJECTED``).

    The GH-513 rule was ``len(reason) >= 10``, which accepts "aaaaaaaaaa" — a
    length check answers "did the caller type something?", not "did the caller
    state something?". A waiver is read by an auditor who was not in the room,
    so the bar is a *statement*:

      * at least :data:`MIN_OVERRIDE_REASON_LENGTH` characters;
      * at least :data:`MIN_REASON_WORDS` words of two or more characters
        (single letters and stray punctuation are not content);
      * at least :data:`MIN_REASON_DISTINCT_WORDS` distinct words, which is what
        rejects one token repeated to satisfy the length (``"test test test"``,
        ``"waiver waiver waiver"``);
      * at least one readable word of three or more letters (rejects digit/id
        padding);
      * at least :data:`MIN_REASON_WORDS` words that are *not* audit rule ids:
        echoing the blocked rule ids ("TRACE-P1 TRACE-P2 …") restates the
        verdict instead of justifying its acceptance.

    Deliberately still mechanical: judging whether a justification is *good* is
    a reviewer's job, and any attempt to do it here would be both unfalsifiable
    and easy to defeat. The point is only that the stored record cannot be a
    placeholder.

    Args:
        reason: Raw caller input.
        label: Field name for the error message (surfaced verbatim to the
            caller; contains no internals).

    Returns:
        The cleaned (stripped) justification.

    Raises:
        GovernanceReasonError: The justification does not meet the policy.
    """
    cleaned = str(reason or "").strip()
    words = [w for w in cleaned.split() if len(w) >= _MIN_REASON_WORD_LENGTH]
    content_words = [w for w in words if not _RULE_ID_TOKEN_RE.match(w)]
    distinct = {w.casefold() for w in words}

    if len(cleaned) < MIN_OVERRIDE_REASON_LENGTH:
        required = f"at least {MIN_OVERRIDE_REASON_LENGTH} characters"
    elif len(words) < MIN_REASON_WORDS:
        required = f"at least {MIN_REASON_WORDS} words"
    elif len(distinct) < MIN_REASON_DISTINCT_WORDS:
        required = (
            f"at least {MIN_REASON_DISTINCT_WORDS} different words (repeating "
            "one word is not a justification)"
        )
    elif not _READABLE_WORD_RE.search(cleaned):
        required = "at least one readable word of three or more letters"
    elif len(content_words) < MIN_REASON_WORDS:
        required = (
            f"at least {MIN_REASON_WORDS} words that are not audit rule ids "
            "(listing the findings is not a justification)"
        )
    else:
        return cleaned

    raise GovernanceReasonError(
        f"Baseline cannot be created: the SE-Auditor {label} must contain "
        f"{required}, stating which deviation is being accepted and why."
    )


def assert_gate_waiver_authority(ctx: Any) -> None:
    """Require approval authority to waive/suppress the gate, or raise.

    The single authority choke point (#569/M2): accepting a known compliance
    deviation is an approval act (``Operation.WORKFLOW_APPROVAL``: Admin or
    Approver), not a write act. For an API key (#865) it additionally has to
    carry the ADMIN capability tier — an AUTHOR-tier (content-writing) key,
    typically handed to an agent that reads untrusted input, must not be able
    to talk its way past the gate.

    Used by both ``BaselineFacade`` (global override + per-finding waivers) and
    ``AuditService.suppress_finding``, so the rule exists once. Callers remap
    :class:`GovernanceAuthorityError` to ``PermissionDeniedError``.

    Raises:
        GovernanceAuthorityError: The caller lacks approval authority or the
            required API-key tier.
    """
    # Deferred import: ``auth_tenancy.services.__init__`` pulls in
    # ``auth_tenancy.services.item_permission``, which imports
    # ``application.base`` — a module-level import here would couple this
    # Layer-1 module to Layer 2 at import time.
    from auth_tenancy.services.authorization import (
        AuthorizationService,
        Operation,
        scope_denial_reason,
    )

    roles = tuple(getattr(ctx, "active_roles", ()) or ())
    decision = AuthorizationService().decide_access(roles, Operation.WORKFLOW_APPROVAL)
    if not decision.allow:
        raise GovernanceAuthorityError(
            "Permission denied: overriding or waiving the SE-Auditor "
            "baseline gate requires approval authority ('admin' or "
            f"'approver'), user has {roles}."
        )

    scope_error = scope_denial_reason(
        getattr(ctx, "scope", None), Operation.WORKFLOW_APPROVAL
    )
    if scope_error:
        raise GovernanceAuthorityError(
            "Permission denied: overriding or waiving the SE-Auditor "
            f"baseline gate is a governance operation. {scope_error}"
        )


def record_waiver(
    *,
    workspace_id: UUID | str,
    tenant_id: UUID | str,
    request: BlockerWaiverRequest,
    rule_id: str,
    scope: str | None,
    scope_artifact_id: str | None,
    granted_by: str,
    expires_at: datetime | None = None,
) -> tuple[BaselineGateWaiver, bool]:
    """Persist *request* as a waiver row; idempotent per (workspace, finding).

    The stored ``rule_id``/``scope`` come from the *matched finding*, never from
    the request: the client identifies a finding, but only the auditor can say
    which scope it was reported in. A repeated waiver for the same finding is
    not an error and does not overwrite the original record — the first
    justification (and its author) is the one on file. That also holds for a
    later ``expires_at`` (#569): the first decision stands.

    Args:
        workspace_id: Workspace the waiver belongs to.
        tenant_id: Active tenant (row-level isolation).
        request: The shape-validated waiver.
        rule_id: Canonical rule id of the matched finding.
        scope: Baseline scope of the matched finding (``None`` -> empty).
        scope_artifact_id: Document-scope root of the matched finding.
        granted_by: User/agent id that granted the waiver.
        expires_at: Optional expiry (#569, additive); ``None`` = unbounded. The
            explicit argument wins; falling back to ``request.expires_at`` so a
            caller that shaped the request without passing it separately still
            persists what it validated.

    Returns:
        ``(row, created)`` — ``created`` is False when the waiver already
        existed, in which case no new audit entry is warranted.
    """
    effective_expiry = expires_at if expires_at is not None else request.expires_at
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
            "expires_at": effective_expiry,
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
    "MIN_OVERRIDE_REASON_LENGTH",
    "MIN_REASON_DISTINCT_WORDS",
    "MIN_REASON_WORDS",
    "SuppressionRecord",
    "assert_gate_waiver_authority",
    "canonical_artifact_ids",
    "finding_key",
    "load_suppressions",
    "load_waived_finding_keys",
    "record_waiver",
    "suppression_applies",
    "validate_waiver_reason",
]
