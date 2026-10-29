"""Request/task-scoped ledger of what memory actually reached a prompt (T-A1-5).

ADR-024 AC-6 asks AI responses to report ``memory_injected``: which prompt
slots received retrieved memory, from which scopes, how many hits, and which
slots were *suppressed* and why. The decision itself is already made in exactly
one place (:func:`memory.injection_policy.resolve_injection`, called from
:func:`memory.context_builder.build_memory_context`); this module only records
that answer, so no second policy evaluation can drift from the first.

Why a ``ContextVar`` and not an explicit parameter: the consumers are wrappers
around an AI call (DRF middleware, the MCP dispatch, the Celery task), while the
producer sits several layers below them (``resolve_and_render`` ->
``build_memory_context``). Threading a ledger object through every intermediate
service would change a large number of signatures for a purely observational
concern. A ``ContextVar`` is per-request/​per-task scoped (including across
``await`` boundaries) and is invisible to callers that never open a ledger.

Semantics:

* :func:`open_ledger` is a context manager; **nesting reuses the outer ledger**
  and only the outermost block closes it. A wrapper (e.g. the MCP registry
  dispatching a tool while a request-scoped ledger is already open) must not
  reset the outer entries.
* :func:`record` is a no-op when no ledger is open — production code paths that
  run outside any request (management commands, projector work) keep working
  unchanged.
* Recording must never break an AI call: :func:`record` swallows (and
  debug-logs) any failure, mirroring the fail-open contract of
  ``build_memory_context`` itself.

``as_contract()`` returns the wire shape documented in Plan A T-A1-5::

    {"slots": ["need_to_sysreq"], "scopes": ["workspace", "user"],
     "count": 4, "suppressed": [{"slot": "bundle_compression", "reason": "hard_off"}]}

and ``None`` when no entry exists at all — the signal the wrappers use to
leave a response byte-identical.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from memory.injection_policy import InjectionDecision

logger = logging.getLogger(__name__)


@dataclass
class Ledger:
    """Accumulated memory-injection entries of one request/task.

    Attributes:
        slots: Slots that actually injected content — i.e. at least one hit was
            rendered for them by their ``record`` call. A consulted slot that
            found nothing is deliberately absent (there is nothing to report);
            a blocked slot appears in ``suppressed`` instead.
        scopes: Scopes that contributed at least one hit, first-seen order,
            unique (render order, artifact-first).
        count: Total number of memory hits rendered in this request — the sum
            over every slot, not a per-slot figure.
        suppressed: ``{"slot": ..., "reason": ...}`` per blocked slot, unique
            on ``(slot, reason)`` in first-seen order (a slot rendered twice in
            one call is still one suppression).
    """

    slots: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    count: int = 0
    suppressed: list[dict[str, str]] = field(default_factory=list)

    def record(
        self,
        slot: str,
        decision: InjectionDecision,
        counts_by_scope: Mapping[str, int],
    ) -> None:
        """Add one ``build_memory_context`` call's outcome."""
        if not decision.inject:
            self._suppress(slot, decision.reason)
            return
        contributing = [
            (scope, hits) for scope, hits in counts_by_scope.items() if hits > 0
        ]
        if not contributing:
            # The policy allowed memory but nothing was found/rendered, so this
            # call put no content into the prompt: not a slot that "injected".
            return
        if slot not in self.slots:
            self.slots.append(slot)
        for scope, hits in contributing:
            if scope not in self.scopes:
                self.scopes.append(scope)
            self.count += hits

    def _suppress(self, slot: str, reason: str) -> None:
        """Record one suppression, de-duplicated on ``(slot, reason)``."""
        if any(
            entry["slot"] == slot and entry["reason"] == reason
            for entry in self.suppressed
        ):
            return
        self.suppressed.append({"slot": slot, "reason": reason})

    def as_contract(self) -> dict[str, Any] | None:
        """Return the wire contract, or ``None`` when nothing was recorded."""
        if not self.slots and not self.suppressed:
            return None
        return {
            "slots": list(self.slots),
            "scopes": list(self.scopes),
            "count": self.count,
            "suppressed": [dict(entry) for entry in self.suppressed],
        }


#: The active ledger, if any. Reset by :func:`open_ledger` on the outermost exit.
_LEDGER: ContextVar[Ledger | None] = ContextVar("memory_injection_ledger", default=None)


def current_ledger() -> Ledger | None:
    """Return the ledger active in this context, or ``None``."""
    return _LEDGER.get()


@contextmanager
def open_ledger() -> Iterator[Ledger]:
    """Activate a ledger for the duration of the block.

    A nested ``open_ledger`` yields the *same* ledger as the enclosing block
    and does not reset it when it exits — otherwise a wrapper that opens a
    ledger around an inner wrapper would silently drop the outer entries.
    """
    existing = _LEDGER.get()
    if existing is not None:
        yield existing
        return
    ledger = Ledger()
    token = _LEDGER.set(ledger)
    try:
        yield ledger
    finally:
        _LEDGER.reset(token)


def record(
    slot: str,
    decision: InjectionDecision,
    counts_by_scope: Mapping[str, int],
) -> None:
    """Record one slot's outcome on the active ledger (no-op when none is open).

    Never raises: transparency must not be able to break an AI call.
    """
    ledger = _LEDGER.get()
    if ledger is None:
        return
    try:
        ledger.record(slot, decision, counts_by_scope)
    except Exception:  # noqa: BLE001 -- observation only, never fatal
        logger.debug("memory injection ledger record failed", exc_info=True)


__all__ = ["Ledger", "current_ledger", "open_ledger", "record"]
