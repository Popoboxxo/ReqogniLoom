"""
COMP-RO-003 CircuitBreaker — per-target failure state machine.

Monitors the failure rate per target subsystem and trips a Closed/Open/Half-Open
state machine to fast-fail traffic to an unhealthy target, giving it time to
recover and preventing cascading failures.

Requirements:
- REQ-L3-RO-003-01 (state machine; initial Closed)
- REQ-L3-RO-003-02 (failure accumulation -> Open; emits state change)
- REQ-L3-RO-003-03 (fast-fail can_execute == False while Open)
- REQ-L3-RO-003-04 (recovery via Half-Open probe)

Interfaces:
- IF-RO-INT-001 (input)  : can_execute(target_id) -> bool          (from AsyncDispatcher)
- IF-RO-INT-004 (input)  : report_success / report_failure(target) (from PolicyEngine)
- IF-RO-INT-005 (output) : log_state_change(target, old, new)      (to ResilienceAuditLogger)

State is persisted in CircuitBreakerState (per tenant + target) so the breaker is
consistent across worker processes and survives restarts.

Traceability: REQ-L2-RO-004 -> REQ-L1-032
"""
from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from persistence.tenancy import TenantContext

from resilience import audit_logger
from resilience.models import CircuitBreakerState
from resilience.policies import Policy, resolve_policy


class CircuitBreaker:
    """Stateful breaker for a single (active tenant, target) pair.

    Instances are cheap and stateless themselves — all state lives in
    :class:`CircuitBreakerState`, fetched/locked per operation. The active tenant
    is resolved implicitly through the tenant-scoped ``objects`` manager.
    """

    def __init__(self, target_subsystem: str, policy: Policy | None = None) -> None:
        """Bind the breaker to a target.

        Args:
            target_subsystem: Target identifier (e.g. ``"llm"``).
            policy: Optional explicit policy; defaults resolved per target.
        """
        self.target_subsystem = target_subsystem
        self.policy = resolve_policy(target_subsystem, policy)

    # -- IF-RO-INT-001 -----------------------------------------------------

    def can_execute(self) -> bool:
        """IF-RO-INT-001: return whether traffic to the target is currently allowed.

        REQ-L3-RO-003-03: returns False while Open.
        REQ-L3-RO-003-04: once the recovery timeout has elapsed, transitions
        Open -> Half-Open and returns True for a single probe request.

        Returns:
            True if the call may proceed, False to fast-fail.
        """
        with transaction.atomic():
            row = self._locked_or_create()

            if row.state == CircuitBreakerState.STATE_CLOSED:
                return True

            if row.state == CircuitBreakerState.STATE_HALF_OPEN:
                # A probe is already in flight; reject further calls until it
                # reports back (REQ-L3-RO-003-04 single probe).
                return False

            # Open: allow a probe only after the recovery timeout elapsed.
            if self._recovery_elapsed(row):
                self._transition(row, CircuitBreakerState.STATE_HALF_OPEN)
                return True
            return False

    # -- diagnostics ---------------------------------------------------------

    def peek_state(self) -> tuple[str, int, "object | None"] | None:
        """Read-only snapshot of the persisted row, for logging only (issue #714).

        Unlike :meth:`can_execute` / :meth:`report_failure`, this never locks
        or creates a row — it must be safe to call from a code path (fast-fail
        logging) that runs *after* ``can_execute()`` already made the
        Open/Closed decision, without perturbing a concurrent
        can_execute()/report_failure() transaction on the same row.

        Returns:
            ``(state, failure_count, opened_at)`` when a row exists for this
            target, or ``None`` when the breaker has never recorded a failure
            (still implicitly Closed, nothing interesting to log).
        """
        row = (
            CircuitBreakerState.objects.filter(
                target_subsystem=self.target_subsystem
            )
            .first()
        )
        if row is None:
            return None
        return (row.state, row.failure_count, row.opened_at)

    # -- IF-RO-INT-004 -----------------------------------------------------

    def report_success(self) -> None:
        """IF-RO-INT-004: record a successful call.

        REQ-L3-RO-003-04: a success in Half-Open closes the circuit and resets
        the failure counter.
        """
        with transaction.atomic():
            row = self._locked_or_create()
            if row.state != CircuitBreakerState.STATE_CLOSED:
                self._transition(row, CircuitBreakerState.STATE_CLOSED)
            row.failure_count = 0
            row.save(update_fields=["failure_count"])

    def report_failure(self) -> None:
        """IF-RO-INT-004: record a failed call.

        REQ-L3-RO-003-02: accumulates failures; trips to Open at the threshold.
        REQ-L3-RO-003-04: a failure in Half-Open re-opens the circuit.

        SA-18: accumulation is windowed by ``Policy.failure_window_seconds`` —
        the counter restarts at 1 when the previous failure is older than the
        window, so ``failure_count`` measures the current burst rather than the
        row's lifetime total (which is what ``failure_count``'s own help_text
        always claimed, and what ``failure_threshold`` is calibrated for).
        """
        with transaction.atomic():
            row = self._locked_or_create()
            now = timezone.now()
            # SA-18: sliding window. ``failure_count`` must describe the current
            # failure burst, not the row's lifetime history — otherwise a target
            # that failed four times months ago trips on its next single blip.
            if self._failure_window_expired(row, now):
                row.failure_count = 1
            else:
                row.failure_count += 1
            row.last_failure_at = now

            if row.state == CircuitBreakerState.STATE_HALF_OPEN:
                row.save(update_fields=["failure_count", "last_failure_at"])
                self._transition(row, CircuitBreakerState.STATE_OPEN, opened_at=now)
                return

            if (
                row.state == CircuitBreakerState.STATE_CLOSED
                and row.failure_count >= self.policy.failure_threshold
            ):
                row.save(update_fields=["failure_count", "last_failure_at"])
                self._transition(row, CircuitBreakerState.STATE_OPEN, opened_at=now)
                return

            row.save(update_fields=["failure_count", "last_failure_at"])

    # -- internals ---------------------------------------------------------

    def _locked_or_create(self) -> CircuitBreakerState:
        """Return the row for this target, row-locked, creating it if absent.

        REQ-L3-RO-003-01: new targets start Closed (model default). ``select_for_update``
        serialises concurrent failure/success reports across workers.

        SA-18 (Systemaudit 2026-08-27): the lock cannot serialise the *first*
        report for a (tenant, target) pair — there is no row yet to lock, so two
        workers observing the same first failure both fall through to the INSERT
        and the UniqueConstraint on (tenant, target_subsystem) turns the loser
        into an IntegrityError. That surfaced as a 500 on the very call the
        breaker exists to protect. The loser now simply re-reads the winner's
        row: the create is wrapped in its own savepoint so the IntegrityError
        does not poison the caller's transaction, and the retry is a plain
        locked SELECT that is guaranteed to find the committed row.
        """
        row = self._select_locked()
        if row is not None:
            return row

        try:
            # Nested atomic == savepoint: an IntegrityError here must stay
            # recoverable inside the report_success/report_failure transaction.
            with transaction.atomic():
                # The tenant-scoped manager filters by tenant but does not inject
                # it on insert, so set the active tenant explicitly
                # (REQ-L1-032 isolation).
                created = CircuitBreakerState.objects.create(
                    target_subsystem=self.target_subsystem,
                    tenant_id=TenantContext.get_tenant(),
                )
        except IntegrityError:
            # Lost the create race: the concurrent winner's row is committed.
            row = self._select_locked()
            if row is None:  # pragma: no cover - defensive
                raise
            return row

        # Re-fetch under lock for consistent concurrent semantics.
        return CircuitBreakerState.objects.select_for_update().get(pk=created.pk)

    def _select_locked(self) -> CircuitBreakerState | None:
        """Return this target's row locked ``FOR UPDATE``, or None if absent."""
        return (
            CircuitBreakerState.objects.select_for_update()
            .filter(target_subsystem=self.target_subsystem)
            .first()
        )

    def _failure_window_expired(self, row: CircuitBreakerState, now) -> bool:
        """True if the previous failure is older than the policy's window (SA-18).

        A row that has never recorded a failure (``last_failure_at is None``) is
        not "expired" — it is simply at count 0, and the caller's ``+= 1`` is the
        first failure of a new burst either way.
        """
        if row.last_failure_at is None:
            return False
        window = timedelta(seconds=self.policy.failure_window_seconds)
        return now - row.last_failure_at > window

    def _recovery_elapsed(self, row: CircuitBreakerState) -> bool:
        """True if the recovery timeout has passed since the breaker opened.

        A row that is Open without an ``opened_at`` is treated as just-opened (not
        elapsed): an Open breaker must never become permeable until its recovery
        window has measurably passed, so a missing timestamp fails safe (closed to
        traffic), not open.
        """
        if row.opened_at is None:
            return False
        deadline = row.opened_at + timedelta(
            seconds=self.policy.recovery_timeout_seconds
        )
        return timezone.now() >= deadline

    def _transition(
        self,
        row: CircuitBreakerState,
        new_state: str,
        opened_at=None,
    ) -> None:
        """Persist a state transition and emit IF-RO-INT-005 (audit).

        REQ-L3-RO-003-02/04: every state change is forwarded to the
        ResilienceAuditLogger.
        """
        old_state = row.state
        if old_state == new_state:
            return
        row.state = new_state
        if new_state == CircuitBreakerState.STATE_OPEN:
            row.opened_at = opened_at or timezone.now()
        elif new_state == CircuitBreakerState.STATE_CLOSED:
            row.opened_at = None
        row.save(update_fields=["state", "opened_at"])
        audit_logger.log_state_change(self.target_subsystem, old_state, new_state)
