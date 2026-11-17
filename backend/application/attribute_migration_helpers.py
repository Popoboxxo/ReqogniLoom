"""Internal helper primitives for :mod:`application.attribute_migration_service`.

S4.1 WP-4 (R2C-004 / R2C-005).  This is a *helper* extraction behind the ADR-01
facade: :class:`~application.attribute_migration_service.AttributeMigrationService`
stays the single public entry point and re-exports every name defined here, so
existing ``from application.attribute_migration_service import ...`` callers
are unaffected.  The four-way *service* split is explicitly S4.2 scope and is
deliberately NOT performed here.

Everything in this module is either a pure value helper or an immutable context
object.  No ORM access, no tenant context, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

#: Static per-row failure message (#697, CWE-209). The migration report is
#: returned verbatim in the HTTP 200 body, so the raw exception text — which on
#: this path is a driver/ORM error — must not travel in it; the cause is logged.
_INTERNAL_FAILURE_MESSAGE = "An internal error occurred while applying this change."

#: ``item_type`` -> ordered ``(app_label, model_name)`` candidates. Mirrors the
#: bootstrap command's mapping; ``Icd`` lives in its own app.
_ITEM_MODEL_CANDIDATES: dict[str, tuple[tuple[str, str], ...]] = {
    "Requirement": (("persistence", "Requirement"),),
    "StakeholderNeed": (("persistence", "StakeholderNeed"),),
    "ArchitectureElement": (("persistence", "ArchitectureElement"),),
    "TestCase": (("persistence", "TestCase"),),
    "GlossaryTerm": (("persistence", "GlossaryTerm"),),
    "Icd": (("icd", "Icd"),),
    "Adr": (("persistence", "Adr"), ("application", "Adr")),
    "Risk": (("persistence", "Risk"), ("application", "Risk")),
    "Issue": (("persistence", "Issue"), ("application", "Issue")),
    "Goal": (("persistence", "Goal"), ("application", "Goal")),
    "ChangeRequest": (("persistence", "ChangeRequest"),),
}

_STATUS_CHANGED = "changed"
_STATUS_UNCHANGED = "unchanged"
_STATUS_SKIPPED = "skipped"
_STATUS_FAILED = "failed"

#: Artifact-level FK fields whose value is an ``Actor`` rather than a scalar.
_ARTIFACT_ACTOR_FIELDS: frozenset[str] = frozenset({"owner", "reporter"})

_RUN_APPLY = "apply"
_RUN_DRY_RUN = "dry_run"

#: Rollback statuses (#1082). ``_PARTIALLY_ROLLED_BACK`` is what a rollback
#: answers when a changed target had no before-image to restore from.
_ROLLED_BACK = "rolled_back"
_PARTIALLY_ROLLED_BACK = "partially_rolled_back"

#: ``field`` prefix of a definition change sample, which is what tells the
#: rollback's coverage check whether a reported change is an artifact write or a
#: definition write (and therefore which snapshot table must cover it).
_SAMPLE_FIELD_PREFIX_DEFINITION = "definition:"


class _StepAbort(RuntimeError):
    """Internal: a row/step failed; carries a human-readable message."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class _Sentinel:
    """Sentinel for 'no value' / 'remove key' (never a valid field value)."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<{self._name}>"


_EMPTY = _Sentinel("EMPTY")
_REMOVE = _Sentinel("REMOVE")
_UNSET = _Sentinel("UNSET")


class _ArtifactBatch:
    """Field changes staged for one artifact within one step.

    Every handler accumulates a row's changes here and flushes them in a single
    :meth:`AttributeMigrationService._persist` call: one atomic update and
    exactly one ``AuditEntry`` per changed artifact (spec §6), no matter how
    many fields the step touches on that row.
    """

    __slots__ = ("changes", "staged")

    def __init__(self) -> None:
        #: ``field name -> (is_custom, persisted value)``.
        self.changes: dict[str, tuple[bool, Any]] = {}
        #: ``(ref, report_before, report_after)`` per changed field, in order.
        self.staged: list[tuple[dict[str, str], Any, Any]] = []

    def __bool__(self) -> bool:
        return bool(self.staged)


def _json_safe(value: Any) -> Any:
    """Best-effort JSON projection for a report sample (never raises)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _is_blank(value: Any) -> bool:
    """True for ``None``, empty strings and empty containers."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return not value
    return False


def _facts(source_value: Any, target_value: Any) -> dict[str, bool]:
    """Condition facts for ``only_if`` evaluation of one row."""
    source_has = not _is_blank(source_value)
    target_has = not _is_blank(target_value)
    return {
        "always": True,
        "source_is_empty": not source_has,
        "source_has_text": source_has,
        "target_is_empty": not target_has,
        "target_has_text": target_has,
        "to_is_empty": not target_has,
        "to_has_text": target_has,
    }


class _SafeFormat(dict):
    """``str.format_map`` mapping that leaves unknown placeholders untouched.

    ``{unknown}`` renders back as ``{unknown}`` instead of raising, so one
    missing optional field does not fail the whole row; a genuinely malformed
    expression still surfaces through ``ValueError``.
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass(frozen=True)
class RunContext:
    """Per-run execution state shared by every step of one AWMS run.

    Introduced in S4.1 WP-4 (R2C-004) to replace per-instance mutable flags.
    The dataclass is frozen so a handler cannot rebind the flags; the
    ``snapshot_ids`` list is intentionally shared by reference and grows as
    snapshots are written.  ``audit_artifacts`` comes from
    ``plan["options"]["audit"]`` and controls only the per-artifact
    ``AuditEntry`` (the run's own entries are always written).
    """

    write: bool
    audit_artifacts: bool
    snapshot_ids: list[str]


@dataclass(frozen=True)
class StepContext:
    """Context object passed as the single second argument to step handlers.

    Replaces the former eight-argument handler signature
    ``(ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids)``
    (R2C-005).  ``step`` stays a positional argument because it is the only
    per-invocation value; everything that is constant for the run lives in the
    immutable :class:`RunContext`.  The convenience properties keep handler
    bodies readable without reintroducing the dead parameters.
    """

    ctx: Any
    run: Any
    plan: dict[str, Any]
    item_type: str
    workspaces: list[dict[str, Any]]
    run_context: RunContext

    @property
    def write(self) -> bool:
        """Whether this run performs real writes (``False`` for a dry run)."""
        return self.run_context.write

    @property
    def snapshot_ids(self) -> list[str]:
        """Snapshot ids recorded so far (shared mutable list, by reference)."""
        return self.run_context.snapshot_ids

    @property
    def audit_artifacts(self) -> bool:
        """Whether a per-artifact ``AuditEntry`` is written on this run."""
        return self.run_context.audit_artifacts


class ExpressionRenderer:
    """Render ``{field}`` templates against a row using a closed evaluator.

    Extracted verbatim from ``AttributeMigrationService._render_expression``
    in S4.1 WP-4.  It never calls ``eval``; unknown placeholders are left
    intact by :class:`_SafeFormat` and a malformed template raises
    :class:`_StepAbort` with a static message.  ``artifact_model`` is injected
    by the facade so this helper stays free of Django imports.
    """

    __slots__ = ("_artifact_model",)

    def __init__(self, artifact_model: Any) -> None:
        self._artifact_model = artifact_model

    def render(self, row: Any, expression: str) -> Any:
        """Render *expression* against the values of *row*."""
        values: dict[str, Any] = dict(row.artifact.custom_fields or {})
        for field in type(row)._meta.get_fields():
            name = getattr(field, "name", None)
            if name and not field.is_relation:
                try:
                    values.setdefault(name, getattr(row, name))
                except Exception:  # noqa: BLE001, S112 - field probe (defensive)
                    continue
        for field in self._artifact_model._meta.get_fields():
            name = getattr(field, "name", None)
            if name and not field.is_relation:
                try:
                    values.setdefault(name, getattr(row.artifact, name))
                except Exception:  # noqa: BLE001, S112 - field probe (defensive)
                    continue
        try:
            return expression.format_map(_SafeFormat(values))
        except (KeyError, IndexError, ValueError) as exc:
            raise _StepAbort(
                f"expression {expression!r} could not be rendered: {exc}"
            ) from exc


__all__ = [
    "ExpressionRenderer",
    "RunContext",
    "StepContext",
]
