"""AWMS engine — dry-run/apply/rollback over declarative migration plans.

Attribut v3 WS7 (#940, spec ``docs/se/attribut/attribut-migrationssystematik.md``
§3–§7, §9–§10). This is the Layer-2 facade and engine: REST views, MCP handlers
and the ``attribute_migrate`` management command all call it (ADR-01), and it is
the only place that touches ``Artifact.custom_fields`` / model fields for a
migration.

Execution model
---------------
* **dry_run is the default** (spec §3): every operation is planned against the
  real rows, the report is identical to an ``apply`` report, but no artifact,
  definition or snapshot row is written. Only the *run* row is recorded (mode
  ``dry_run``, status ``planned``), so previews are auditable history.
* **apply** snapshots every touched artifact before writing
  (:class:`~persistence.models.AttributeMigrationSnapshot`) and writes one
  ``AuditEntry`` per changed artifact (spec §6, op
  ``attribute_migration.apply``).
* **rollback** restores artifacts from a run's snapshots and audits each restore
  (op ``attribute_migration.rollback``).

Safety
------
* Each artifact write is guarded by its optimistic-lock ``version``: a
  concurrent modification raises a conflict for that row instead of overwriting
  it (spec §6).
* ``abort_on_error`` stops at the first failed row; otherwise the run finishes
  and reports ``partial``. Partial changes remain and are exactly why the
  snapshot exists.
* ``only_if`` conditions and ``expression`` values use safe, closed evaluators —
  never ``eval`` (spec §4).
* The plan hash is stored on the run; applying a *different* plan under an
  already-applied ``plan_id`` is refused (spec §6).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable, Iterable
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from attribute_definitions.migration_plan import (
    MAX_SAMPLES,
    MOVE,
    MigrationPlanError,
    OP_BACKFILL_VALUE,
    OP_DEFINE_ATTRIBUTE,
    OP_DERIVE_VALUE,
    OP_DROP_ATTRIBUTE,
    OP_MAP_VALUE,
    OP_MERGE_ATTRIBUTE,
    OP_MIGRATE_VALUE,
    OP_REQUEUE_DEFINITION,
    OP_RENAME_ATTRIBUTE,
    OP_RETYPE_ATTRIBUTE,
    OP_SPLIT_ATTRIBUTE,
    OP_VERIFY,
    REF_CUSTOM_FIELD,
    STRATEGY_CONSTANT,
    STRATEGY_DERIVE_FROM_LINK,
    STRATEGY_EXPRESSION,
    evaluate_condition,
    normalize_plan,
    parse_verify_assertion,
    plan_hash,
)
from attribute_definitions.migration_transforms import (
    APPLIED,
    DEFAULT_REGISTRY,
    FAILED,
    SKIPPED,
    TransformContext,
    TransformOutcome,
    TransformRegistry,
)
from attribute_definitions.schema import (
    PRESETS,
    AttributeSchemaError,
    normalize_attribute,
    stored_attributes,
)
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext
from persistence.errors import NotFoundError, PermissionDeniedError
from persistence.models import Artifact

from application.attribute_definition_service import AttributeDefinitionService
from application.base import ServiceBase

logger = logging.getLogger(__name__)

#: `item_type` -> ordered `(app_label, model_name)` candidates. Mirrors the
#: bootstrap command's mapping; `Icd` lives in its own app.
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
#: The engine resolves them through ``ActorService`` (spec §8: legacy
#: owner/created_by values move onto the Actor carrier) instead of writing the
#: raw wire value into the FK column.
_ARTIFACT_ACTOR_FIELDS: frozenset[str] = frozenset({"owner", "reporter"})

_RUN_APPLY = "apply"
_RUN_DRY_RUN = "dry_run"


class AttributeMigrationNotFound(NotFoundError):
    """No migration run with the given id in the active tenant."""


class AttributeMigrationConflict(ValueError):
    """A plan with the same id was already applied with a different hash."""


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
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return not value
    return False


def _facts(source_value: Any, target_value: Any) -> dict[str, bool]:
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


class AttributeMigrationService(ServiceBase):
    """Plan, preview, apply and roll back declarative value migrations."""

    def __init__(
        self,
        *,
        registry: TransformRegistry | None = None,
        definitions: AttributeDefinitionService | None = None,
    ) -> None:
        self._registry = registry or DEFAULT_REGISTRY
        self._definitions = definitions or AttributeDefinitionService()
        #: Per-run toggle from ``plan["options"]["audit"]`` (spec §3): when
        #: false the per-artifact ``AuditEntry`` is suppressed. ``_execute``
        #: sets it for the plan it runs; the default keeps a direct helper call
        #: safe. Every call site constructs a fresh service instance (no
        #: long-lived sharing), so this per-run state cannot leak across plans.
        self._audit_artifacts = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_plan(self, payload: Any) -> dict[str, Any]:
        """Validate *payload* and return ``{plan, plan_hash}`` (no DB access).

        Deliberately permission-free: it is a pure schema check, matching the
        spec's "plan lesend für alle" MCP reading. Every method that touches
        data asserts ``admin``.
        """
        normalized = normalize_plan(payload)
        return {"plan": normalized, "plan_hash": plan_hash(normalized)}

    def dry_run(self, ctx: AuthContext, payload: Any) -> dict[str, Any]:
        """Plan-only execution: full report, no artifact/definition writes."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        normalized = normalize_plan(payload)
        return self._execute(ctx, normalized, write=False)

    def apply(self, ctx: AuthContext, payload: Any) -> dict[str, Any]:
        """Execute a plan for real (snapshots + writes + per-artifact audit)."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        normalized = normalize_plan(payload)
        # `apply` is the explicit destructive entry point; the document's own
        # ``mode`` must not silently downgrade it to a preview. A plan whose
        # mode is dry_run executed through this method still runs for real —
        # callers that want a preview use ``dry_run``.
        if normalized["mode"] != _RUN_APPLY:
            normalized = {**normalized, "mode": _RUN_APPLY}
        return self._execute(ctx, normalized, write=True)

    def rollback(self, ctx: AuthContext, run_id: Any) -> dict[str, Any]:
        """Restore every artifact a run touched, from its snapshots."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        run = self._get_run(run_id)
        if run.mode != _RUN_APPLY:
            raise MigrationPlanError(
                [f"run {run.id} is a dry run and has nothing to roll back"]
            )
        if run.status == "rolled_back":
            return {
                "run_id": str(run.id),
                "status": run.status,
                "restored": 0,
                "message": "run is already rolled back",
            }

        from persistence.models import AttributeMigrationSnapshot

        snapshots = list(
            AttributeMigrationSnapshot.objects.filter(run=run).order_by("artifact_id")
        )
        restored = 0
        samples: list[dict[str, Any]] = []
        with transaction.atomic():
            for snapshot in snapshots:
                if self._restore_snapshot(ctx, snapshot):
                    restored += 1
                if len(samples) < MAX_SAMPLES:
                    samples.append(
                        {
                            "artifact_id": str(snapshot.artifact_id),
                            "fields": sorted(snapshot.model_fields or {}),
                        }
                    )
            run.status = "rolled_back"
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "finished_at", "modified_at", "version"])
            self._audit(
                ctx,
                operation=AuditEntry.OP_ATTRIBUTE_MIGRATION_ROLLBACK,
                entity_type="AttributeMigrationRun",
                entity_id=run.id,
                details={"restored": restored, "plan_id": run.plan_id},
            )
        return {
            "run_id": str(run.id),
            "status": run.status,
            "restored": restored,
            "samples": samples,
        }

    def list_runs(
        self,
        ctx: AuthContext,
        *,
        plan_id: str | None = None,
        mode: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List runs of the active tenant, newest first."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        from persistence.models import AttributeMigrationRun

        qs = AttributeMigrationRun.objects.all()
        if plan_id:
            qs = qs.filter(plan_id=plan_id)
        if mode:
            qs = qs.filter(mode=mode)
        if status:
            qs = qs.filter(status=status)
        capped = max(1, min(int(limit), 200))
        return [self._run_payload(run) for run in qs.order_by("-started_at")[:capped]]

    def get_run(self, ctx: AuthContext, run_id: Any) -> dict[str, Any]:
        """Return one run, including its stored report."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        return self._run_payload(self._get_run(run_id))

    # ------------------------------------------------------------------
    # Run plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _run_payload(run: Any) -> dict[str, Any]:
        return {
            "id": str(run.id),
            "plan_id": run.plan_id,
            "plan_hash": run.plan_hash,
            "mode": run.mode,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "actor_type": run.actor_type,
            "actor_label": run.actor_label,
            "counts": dict(run.counts or {}),
            "snapshot_reference": list(run.snapshot_reference or []),
            "report": dict(run.report_json or {}),
        }

    def _get_run(self, run_id: Any) -> Any:
        from persistence.models import AttributeMigrationRun

        try:
            identifier = UUID(str(run_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AttributeMigrationNotFound(f"run {run_id!r} not found") from exc
        run = AttributeMigrationRun.objects.filter(id=identifier).first()
        if run is None:
            raise AttributeMigrationNotFound(f"run {run_id} not found")
        return run

    def _execute(
        self, ctx: AuthContext, plan: dict[str, Any], *, write: bool
    ) -> dict[str, Any]:
        from persistence.models import AttributeMigrationRun

        scope = plan["scope"]
        self._assert_same_tenant(ctx, scope)
        item_type = scope["item_type"]
        if item_type not in _ITEM_MODEL_CANDIDATES:
            raise MigrationPlanError([f"item_type {item_type!r} has no resolvable model"])
        workspaces = self._resolve_workspaces(scope)
        digest = plan_hash(plan)

        if write:
            self._assert_no_hash_conflict(plan["id"], digest)

        mode = _RUN_APPLY if write else _RUN_DRY_RUN
        run = AttributeMigrationRun.objects.create(
            tenant_id=ctx.tenant_id,
            plan_id=plan["id"],
            plan_hash=digest,
            mode=mode,
            status="planned",
            started_at=timezone.now(),
            actor_type=getattr(ctx, "actor_type", "user") or "user",
            actor_label=getattr(ctx, "agent_label", "") or "",
            snapshot_reference=[],
        )
        self._audit(
            ctx,
            operation=AuditEntry.OP_CREATE,
            entity_type="AttributeMigrationRun",
            entity_id=run.id,
            details={"plan_id": plan["id"], "mode": mode},
        )

        steps: list[dict[str, Any]] = []
        snapshot_ids: list[str] = []
        abort = bool(plan["options"].get("abort_on_error", True))
        # Consume the ``audit`` plan option (WS6/WS7 review #939/#940
        # Medium/Low 4): the run's own create/rollback entries are always
        # written; this only controls the per-changed-artifact ``AuditEntry``.
        self._audit_artifacts = bool(plan["options"].get("audit", True))
        try:
            for index, step in enumerate(plan["steps"]):
                if step["op"] == OP_VERIFY:
                    outcome = self._step_verify(step, steps)
                else:
                    outcome = self._execute_step(
                        ctx,
                        run,
                        step,
                        plan,
                        item_type,
                        workspaces,
                        write=write,
                        snapshot_ids=snapshot_ids,
                    )
                outcome["index"] = index
                outcome["op"] = step["op"]
                steps.append(outcome)
                if outcome["counts"]["failed"] and abort:
                    raise _StepAbort(
                        f"step {index} ({step['op']}) had "
                        f"{outcome['counts']['failed']} failure(s)"
                    )
            status = self._status_for(steps, write=write, abort=abort)
        except _StepAbort as exc:
            status = "failed"
            logger.warning("AWMS run %s aborted: %s", run.id, exc.message)
        except Exception:
            # Mask the real error with the finally-status update would hide it;
            # record a failed run and re-raise so the caller sees the cause.
            status = "failed"
            raise
        finally:
            summary = self._summary(steps)
            report = {
                "plan_id": plan["id"],
                "plan_hash": digest,
                "mode": mode,
                "status": status,
                "scope": scope,
                "steps": steps,
                "summary": summary,
            }
            run.status = status
            run.finished_at = timezone.now()
            run.counts = summary
            run.report_json = report
            run.snapshot_reference = snapshot_ids
            run.save(
                update_fields=[
                    "status",
                    "finished_at",
                    "counts",
                    "report_json",
                    "snapshot_reference",
                    "modified_at",
                    "version",
                ]
            )
            report["run_id"] = str(run.id)
        return report

    @staticmethod
    def _summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "steps": len(steps),
            "matched": sum(step["counts"]["matched"] for step in steps),
            "changed": sum(step["counts"]["changed"] for step in steps),
            "skipped": sum(step["counts"]["skipped"] for step in steps),
            "failed": sum(step["counts"]["failed"] for step in steps),
            "steps_failed": sum(1 for step in steps if step["counts"]["failed"]),
        }

    @staticmethod
    def _status_for(steps: list[dict[str, Any]], *, write: bool, abort: bool) -> str:
        has_failures = any(step["counts"]["failed"] for step in steps)
        if has_failures:
            return "failed" if abort else "partial"
        if not write:
            return "planned"
        return "applied"

    def _assert_same_tenant(self, ctx: AuthContext, scope: dict[str, Any]) -> None:
        tenant = scope.get("tenant", "current")
        if tenant in ("current", None):
            return
        if str(tenant) != str(ctx.tenant_id):
            raise PermissionDeniedError(
                "AWMS Teil A operates on the caller's tenant only; "
                f"scope.tenant={tenant!r} differs from the active tenant"
            )

    def _assert_no_hash_conflict(self, plan_id: str, digest: str) -> None:
        from persistence.models import AttributeMigrationRun

        previous = (
            AttributeMigrationRun.objects.filter(plan_id=plan_id, mode=_RUN_APPLY)
            .order_by("-started_at")
            .first()
        )
        if previous is not None and previous.plan_hash != digest:
            raise AttributeMigrationConflict(
                f"plan '{plan_id}' was already applied with a different content "
                f"(hash {previous.plan_hash}); bump the plan id"
            )

    # ------------------------------------------------------------------
    # Scope / row resolution
    # ------------------------------------------------------------------

    def _resolve_workspaces(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        from persistence.models import Workspace

        raw = scope.get("workspace", "*")
        qs = Workspace.objects.all()
        if raw != "*":
            try:
                ids = [UUID(str(value)) for value in raw]
            except (TypeError, ValueError) as exc:
                raise MigrationPlanError(
                    [f"scope.workspace contains an invalid UUID: {exc}"]
                ) from exc
            qs = qs.filter(id__in=ids)
        presets = set(scope.get("preset") or [])
        resolved = []
        for workspace in qs.order_by("name"):
            preset_name = ""
            if isinstance(workspace.preset, dict):
                preset_name = str(workspace.preset.get("name", ""))
            if presets and preset_name not in presets:
                continue
            resolved.append({"id": workspace.id, "preset": preset_name})
        return resolved

    @staticmethod
    def _model_for(item_type: str) -> Any:
        from django.apps import apps

        for app_label, model_name in _ITEM_MODEL_CANDIDATES[item_type]:
            model = apps.get_model(app_label, model_name)
            if model is not None:
                return model
        raise MigrationPlanError([f"no model found for item_type {item_type!r}"])

    def _rows(self, item_type: str, workspace_ids: Iterable[UUID]) -> list[Any]:
        model = self._model_for(item_type)
        ids = list(workspace_ids)
        if not ids:
            return []
        qs = model.objects.filter(artifact__workspace_id__in=ids)
        qs = qs.exclude(artifact__lifecycle_status="deleted")
        return list(qs.select_related("artifact").order_by("id"))

    # ------------------------------------------------------------------
    # Field carriers
    # ------------------------------------------------------------------

    @staticmethod
    def _field_carrier(model: Any, name: str) -> str | None:
        try:
            model._meta.get_field(name)
        except Exception:  # FieldDoesNotExist and any dynamic oddity
            pass
        else:
            return "type"
        try:
            Artifact._meta.get_field(name)
        except Exception:
            return None
        return "artifact"

    def _read_value(self, row: Any, ref: dict[str, str]) -> Any:
        if ref["kind"] == REF_CUSTOM_FIELD:
            return (row.artifact.custom_fields or {}).get(ref["name"])
        carrier = self._field_carrier(type(row), ref["name"])
        if carrier == "type":
            return getattr(row, ref["name"])
        if carrier == "artifact":
            if ref["name"] in _ARTIFACT_ACTOR_FIELDS:
                # Report/compare in the actor wire form, not as an Actor row:
                # that is what a plan writes and what keeps ``target_is_empty``
                # and the idempotency check meaningful.
                from application.artifact_attribute_gateway import artifact_system_fields

                return artifact_system_fields(row.artifact).get(ref["name"])
            return getattr(row.artifact, ref["name"])
        return None

    def _read_artifact_field(self, artifact: Any, name: str) -> Any:
        custom = artifact.custom_fields or {}
        if name in custom:
            return custom[name]
        carrier = self._field_carrier(type(artifact), name)
        if carrier is not None:
            return getattr(artifact, name)
        return _EMPTY

    def _resolve_actor_id(self, ctx: AuthContext, value: Any) -> Any:
        """Resolve an actor wire value / legacy payload to an ``Actor`` id.

        Spec §8 moves the legacy owner/assignee carriers onto the Artifact Actor
        FKs. Plans therefore may name a raw value (``Risk.owner_name`` text,
        ``Issue.assignee_id`` UUID, a ``User`` FK row) — this maps all of them
        onto the same actor value form the transports use and resolves it via
        :class:`~application.actor_service.ActorService`, so a name becomes a
        reusable external actor and a user id becomes the tenant's actor row.

        ``None``/empty clears the FK. An id that no longer resolves to a
        ``User``/``Actor`` (dangling UUID, UUID-shaped legacy text) degrades to
        a reviewable external actor named after the raw value — never aborting
        the run (spec §8). Entity *creation* is limited to Actor resolution
        here — the actor-only slice of spec §10 step 8 that the first-plan set
        needs; general entity creation stays #393.
        """
        if value is None or value is _EMPTY or value is _REMOVE:
            return None
        from application.actor_service import ActorService

        actors = ActorService()
        if isinstance(value, dict):
            kind = value.get("kind")
            if kind == "external":
                return actors.get_or_create_external(ctx, value.get("name") or "").id
            reference = value.get("id")
            if reference is None:
                raise _StepAbort(f"unrecognized actor value {value!r}")
            text = str(reference).strip()
            if not text:
                raise _StepAbort(f"actor value {value!r} has an empty id")
            # Covers ``kind == "user"`` and any other kind carrying an id.
            # WS6/WS7 review (#939/#940) Medium 3: a dangling UUID (deleted
            # user) or UUID-shaped legacy text degrades to a reviewable
            # external placeholder instead of raising ``NotFoundError`` and
            # aborting the whole run under ``abort_on_error`` — the contract
            # ``migration_transforms.to_actor`` documents. Previously only the
            # non-dict branch below degraded; the dict branch went straight
            # through ``get_or_create_for_user`` and aborted.
            return self._resolve_actor_or_placeholder(actors, ctx, text)
        # A FK read (User/Actor instance) or a raw id/name.
        reference = getattr(value, "pk", value)
        text = str(reference).strip()
        if not text:
            return None
        return self._resolve_actor_or_placeholder(actors, ctx, text)

    def _resolve_actor_or_placeholder(
        self, actors: Any, ctx: AuthContext, text: str
    ) -> Any:
        """Resolve *text* to an actor id, degrading to an external placeholder.

        A dangling id or free text becomes a reviewable external actor named
        after the raw value instead of aborting the migration (spec §8,
        ``to_actor`` docstring).
        """
        from persistence.errors import NotFoundError

        try:
            return actors.resolve_reference(ctx, text).id
        except (NotFoundError, ValueError):
            return actors.get_or_create_external(ctx, text).id

    # ------------------------------------------------------------------
    # Transforms
    # ------------------------------------------------------------------

    def _apply_transform(
        self,
        value: Any,
        transform: dict[str, Any] | None,
        *,
        value_map: dict[str, Any] | None,
        fallback: Any = None,
        link_resolver: Callable[[Any], TransformOutcome] | None = None,
    ) -> TransformOutcome:
        if transform is None and value_map is None:
            return TransformOutcome(APPLIED, value)
        if transform is None:
            transform = {"name": "enum_map", "options": {}}
        context = TransformContext(
            options=dict(transform.get("options") or {}),
            value_map=value_map,
            fallback=fallback,
            link_resolver=link_resolver,
        )
        fn = self._registry.get(transform["name"])
        return fn(value, context)

    # ------------------------------------------------------------------
    # Step dispatch
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        ctx: AuthContext,
        run: Any,
        step: dict[str, Any],
        plan: dict[str, Any],
        item_type: str,
        workspaces: list[dict[str, Any]],
        *,
        write: bool,
        snapshot_ids: list[str],
    ) -> dict[str, Any]:
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            OP_MIGRATE_VALUE: self._step_migrate_value,
            OP_MAP_VALUE: self._step_map_value,
            OP_BACKFILL_VALUE: self._step_backfill_value,
            OP_DERIVE_VALUE: self._step_derive_value,
            OP_SPLIT_ATTRIBUTE: self._step_split_attribute,
            OP_MERGE_ATTRIBUTE: self._step_merge_attribute,
            OP_RENAME_ATTRIBUTE: self._step_rename_attribute,
            OP_RETYPE_ATTRIBUTE: self._step_retype_attribute,
            OP_DEFINE_ATTRIBUTE: self._step_define_attribute,
            OP_DROP_ATTRIBUTE: self._step_drop_attribute,
            OP_REQUEUE_DEFINITION: self._step_requeue_definition,
        }
        return handlers[step["op"]](
            ctx,
            run,
            step,
            plan,
            item_type,
            workspaces,
            write=write,
            snapshot_ids=snapshot_ids,
        )

    @staticmethod
    def _empty_outcome(message: str = "") -> dict[str, Any]:
        return {
            "counts": {"matched": 0, "changed": 0, "skipped": 0, "failed": 0},
            "transform_counts": {"applied": 0, "skipped": 0, "failed": 0},
            "changes": [],
            "errors": [],
            "message": message,
        }

    # ------------------------------------------------------------------
    # Value steps
    # ------------------------------------------------------------------

    def _step_migrate_value(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        outcome = self._empty_outcome()
        source_ref, target_ref = step["from"], step["to"]
        move = step["mode"] == MOVE
        for row in self._rows(item_type, [w["id"] for w in workspaces]):
            outcome["counts"]["matched"] += 1
            current_source = self._read_value(row, source_ref)
            current_target = self._read_value(row, target_ref)
            if step.get("only_if") and not evaluate_condition(
                step["only_if"], _facts(current_source, current_target)
            ):
                self._record_skip(outcome, row, target_ref, "only_if not met")
                continue
            result = self._apply_transform(
                current_source,
                step.get("transform"),
                value_map=step.get("value_map"),
                fallback=step.get("fallback"),
                link_resolver=self._link_resolver(row, step),
            )
            outcome["transform_counts"][result.status] += 1
            if result.status == FAILED:
                self._record_failure(outcome, row, target_ref, result.message)
                continue
            if result.status == SKIPPED:
                self._record_skip(outcome, row, target_ref, result.message)
                continue
            batch = _ArtifactBatch()
            # The report shows the value *being migrated* as the before-image,
            # so a preview reads "old: alpha -> alpha" for a copy.
            self._stage(
                outcome, row, target_ref, result.value, current_target, batch,
                report_before=current_source,
            )
            # `move` clears the source in the *same* atomic write: the source is
            # only dropped when the target write succeeds, and the artifact gets
            # one audit entry, not two.
            if move and not _is_blank(current_source):
                self._stage(
                    outcome, row, source_ref, None, current_source, batch, clear=True
                )
            self._flush(ctx, run, row, batch, write, outcome, snapshot_ids)
        return outcome

    def _step_map_value(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        outcome = self._empty_outcome()
        target_ref = step["target"]
        for row in self._rows(item_type, [w["id"] for w in workspaces]):
            outcome["counts"]["matched"] += 1
            current = self._read_value(row, target_ref)
            if step.get("only_if") and not evaluate_condition(
                step["only_if"], _facts(current, current)
            ):
                self._record_skip(outcome, row, target_ref, "only_if not met")
                continue
            result = self._apply_transform(
                current,
                {"name": "enum_map", "options": {}},
                value_map=step.get("value_map"),
                fallback=step.get("fallback"),
            )
            outcome["transform_counts"][result.status] += 1
            if result.status == FAILED:
                self._record_failure(outcome, row, target_ref, result.message)
                continue
            if result.status == SKIPPED:
                self._record_skip(outcome, row, target_ref, result.message)
                continue
            batch = _ArtifactBatch()
            self._stage(outcome, row, target_ref, result.value, current, batch)
            self._flush(ctx, run, row, batch, write, outcome, snapshot_ids)
        return outcome

    def _step_backfill_value(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        outcome = self._empty_outcome()
        target_ref = step["target"]
        for row in self._rows(item_type, [w["id"] for w in workspaces]):
            outcome["counts"]["matched"] += 1
            current = self._read_value(row, target_ref)
            condition = step.get("only_if") or "target_is_empty"
            if not evaluate_condition(condition, _facts(current, current)):
                self._record_skip(outcome, row, target_ref, "only_if not met")
                continue
            try:
                new_value = self._backfill_value(row, step)
            except _StepAbort as exc:
                self._record_failure(outcome, row, target_ref, exc.message)
                continue
            if new_value is _EMPTY:
                self._record_skip(outcome, row, target_ref, "no value derivable")
                continue
            batch = _ArtifactBatch()
            self._stage(outcome, row, target_ref, new_value, current, batch)
            self._flush(ctx, run, row, batch, write, outcome, snapshot_ids)
        return outcome

    def _step_derive_value(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        outcome = self._empty_outcome()
        target_ref = step["target"]
        for row in self._rows(item_type, [w["id"] for w in workspaces]):
            outcome["counts"]["matched"] += 1
            current = self._read_value(row, target_ref)
            if step.get("only_if") and not evaluate_condition(
                step["only_if"], _facts(current, current)
            ):
                self._record_skip(outcome, row, target_ref, "only_if not met")
                continue
            try:
                new_value = self._render_expression(row, step["expression"])
            except _StepAbort as exc:
                self._record_failure(outcome, row, target_ref, exc.message)
                continue
            if _is_blank(new_value):
                self._record_skip(outcome, row, target_ref, "expression rendered empty")
                continue
            batch = _ArtifactBatch()
            self._stage(outcome, row, target_ref, new_value, current, batch)
            self._flush(ctx, run, row, batch, write, outcome, snapshot_ids)
        return outcome

    def _step_split_attribute(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        outcome = self._empty_outcome()
        source_ref = step["from"]
        targets = step["targets"]
        separator = step.get("separator")
        for row in self._rows(item_type, [w["id"] for w in workspaces]):
            outcome["counts"]["matched"] += 1
            source_value = self._read_value(row, source_ref)
            if _is_blank(source_value):
                self._record_skip(outcome, row, source_ref, "source is empty")
                continue
            parts = (
                [part.strip() for part in str(source_value).split(separator)]
                if separator
                else None
            )
            batch = _ArtifactBatch()
            for position, target in enumerate(targets):
                value = (
                    parts[position]
                    if parts is not None and position < len(parts)
                    else source_value
                )
                current = self._read_value(row, target["to"])
                result = self._apply_transform(
                    value, target.get("transform"), value_map=None, fallback=None
                )
                outcome["transform_counts"][result.status] += 1
                if result.status != APPLIED:
                    self._record_skip(
                        outcome, row, target["to"], result.message or "transform skipped"
                    )
                    continue
                self._stage(outcome, row, target["to"], result.value, current, batch)
            self._flush(ctx, run, row, batch, write, outcome, snapshot_ids)
        return outcome

    def _step_merge_attribute(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        outcome = self._empty_outcome()
        target_ref = step["to"]
        for row in self._rows(item_type, [w["id"] for w in workspaces]):
            outcome["counts"]["matched"] += 1
            merged = None
            for source_ref in step["sources"]:
                candidate = self._read_value(row, source_ref)
                if not _is_blank(candidate):
                    merged = candidate
                    break
            if merged is None:
                self._record_skip(outcome, row, target_ref, "all sources empty")
                continue
            result = self._apply_transform(
                merged,
                step.get("transform"),
                value_map=None,
                fallback=step.get("fallback"),
            )
            outcome["transform_counts"][result.status] += 1
            if result.status != APPLIED:
                self._record_skip(
                    outcome, row, target_ref, result.message or "transform skipped"
                )
                continue
            current = self._read_value(row, target_ref)
            batch = _ArtifactBatch()
            self._stage(outcome, row, target_ref, result.value, current, batch)
            self._flush(ctx, run, row, batch, write, outcome, snapshot_ids)
        return outcome

    # ------------------------------------------------------------------
    # Definition steps
    # ------------------------------------------------------------------

    def _definition_targets(
        self, plan: dict[str, Any], item_type: str
    ) -> list[dict[str, Any]]:
        """Resolve the definition rows a definition-level op applies to."""
        scope = plan["scope"]
        presets = scope.get("preset") or list(PRESETS)
        targets: list[dict[str, Any]] = [
            {"kind": "global", "preset": preset} for preset in presets
        ]
        from attribute_definitions.models import WorkspaceAttributeDefinition

        for workspace in self._resolve_workspaces(scope):
            # Only touch a workspace definition that is actually materialized;
            # a missing one is the job of `requeue_definition`/bootstrap, and
            # `resolve()` would raise instead of reporting a clean skip.
            if not WorkspaceAttributeDefinition.objects.filter(
                workspace_id=workspace["id"], item_type=item_type
            ).exists():
                continue
            targets.append(
                {
                    "kind": "workspace",
                    "id": workspace["id"],
                    "preset": workspace["preset"],
                }
            )
        return targets

    def _step_define_attribute(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        outcome = self._empty_outcome()
        try:
            raw_block = dict(step["attribute"])
            raw_block["name"] = raw_block.get("name") or step.get("name", "")
            block = normalize_attribute(raw_block)
        except AttributeSchemaError as exc:
            self._record_failure(outcome, None, "define_attribute", "; ".join(exc.errors))
            return outcome

        required_on = set(step.get("required_on") or [])
        for target in self._definition_targets(plan, item_type):
            outcome["counts"]["matched"] += 1
            preset = target["preset"]
            payload_block = (
                {**block, "required": preset in required_on} if required_on else block
            )
            field = f"definition:{target['kind']}:{preset}:{payload_block['name']}"
            record = {
                "artifact_id": None,
                "workspace_id": str(target.get("id")) if target.get("id") else None,
                "field": field,
                "before": None,
                "after": "defined",
                "status": _STATUS_CHANGED,
                "reason": "define_attribute",
            }
            if not write:
                outcome["counts"]["changed"] += 1
                self._append_sample(outcome, record)
                continue
            try:
                current = self._read_definition(ctx, item_type, target)
                if payload_block["name"] in {a["name"] for a in current}:
                    self._record_skip(outcome, None, field, "already defined")
                    continue
                self._save_definition(
                    ctx, item_type, target, current + [payload_block]
                )
                outcome["counts"]["changed"] += 1
                self._append_sample(outcome, record)
            except Exception as exc:  # noqa: BLE001 - one bad target must not kill the run
                self._record_failure(outcome, None, field, str(exc))
        return outcome

    def _step_rename_attribute(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        return self._definition_value_transform(
            ctx, run, step, plan, item_type, workspaces,
            write=write, snapshot_ids=snapshot_ids, action="rename",
        )

    def _step_retype_attribute(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        return self._definition_value_transform(
            ctx, run, step, plan, item_type, workspaces,
            write=write, snapshot_ids=snapshot_ids, action="retype",
        )

    def _definition_value_transform(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids, action
    ):
        """Rename/retype an *extended* attribute in every definition + its values.

        Core attributes are refused: their identity is fixed by the Django model
        (``validate_meta_only_change``), so renaming/retyping one is a schema
        migration, not a value migration.
        """
        if action == "rename":
            old_name = step["from"]["name"]
            new_name = step["to"]["name"]
            source_ref, target_ref = step["from"], step["to"]
        else:
            old_name = step["name"]
            new_name = step["name"]
            source_ref = {"kind": REF_CUSTOM_FIELD, "name": old_name}
            target_ref = {"kind": REF_CUSTOM_FIELD, "name": old_name}

        outcome = self._empty_outcome()
        for target in self._definition_targets(plan, item_type):
            outcome["counts"]["matched"] += 1
            field = f"definition:{target['kind']}:{target['preset']}:{old_name}"
            record = {
                "artifact_id": None,
                "workspace_id": str(target.get("id")) if target.get("id") else None,
                "field": field,
                "before": old_name,
                "after": new_name,
                "status": _STATUS_CHANGED,
                "reason": action,
            }
            if not write:
                outcome["counts"]["changed"] += 1
                self._append_sample(outcome, record)
                continue
            try:
                current = self._read_definition(ctx, item_type, target)
                entry = next((a for a in current if a["name"] == old_name), None)
                if entry is None:
                    self._record_skip(outcome, None, field, "attribute not in definition")
                    continue
                if entry["kind"] == "core":
                    self._record_failure(
                        outcome, None, field,
                        f"'{old_name}' is a core attribute; schema changes are out of scope",
                    )
                    continue
                updated = []
                for attribute in current:
                    if attribute["name"] != old_name:
                        updated.append(attribute)
                    elif action == "rename":
                        updated.append({**attribute, "name": new_name})
                    else:
                        updated.append({**attribute, "type": step["new_type"]})
                self._save_definition(ctx, item_type, target, updated)
                outcome["counts"]["changed"] += 1
                self._append_sample(outcome, record)
            except Exception as exc:  # noqa: BLE001
                self._record_failure(outcome, None, field, str(exc))

        # L2: rewrite the value keys on the artifacts themselves.
        if action == "rename" and source_ref["kind"] == REF_CUSTOM_FIELD:
            for row in self._rows(item_type, [w["id"] for w in workspaces]):
                value = self._read_value(row, source_ref)
                if _is_blank(value):
                    continue
                current = self._read_value(row, target_ref)
                batch = _ArtifactBatch()
                self._stage(outcome, row, target_ref, value, current, batch)
                if source_ref["name"] != target_ref["name"]:
                    # Old and new key are written in one update: the source is
                    # never left behind, and the artifact is audited once.
                    self._stage(
                        outcome, row, source_ref, None, value, batch, clear=True
                    )
                self._flush(ctx, run, row, batch, write, outcome, snapshot_ids)
        return outcome

    def _step_drop_attribute(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        outcome = self._empty_outcome()
        name = step["name"]

        for target in self._definition_targets(plan, item_type):
            outcome["counts"]["matched"] += 1
            field = f"definition:{target['kind']}:{target['preset']}:{name}"
            record = {
                "artifact_id": None,
                "workspace_id": str(target.get("id")) if target.get("id") else None,
                "field": field,
                "before": "present",
                "after": None,
                "status": _STATUS_CHANGED,
                "reason": "drop_attribute",
            }
            if not write:
                outcome["counts"]["changed"] += 1
                self._append_sample(outcome, record)
                continue
            try:
                current = self._read_definition(ctx, item_type, target)
                entry = next((a for a in current if a["name"] == name), None)
                if entry is None:
                    self._record_skip(outcome, None, field, "attribute not in definition")
                    continue
                if entry["kind"] == "core":
                    self._record_failure(
                        outcome, None, field,
                        f"'{name}' is a core attribute and cannot be dropped by AWMS",
                    )
                    continue
                self._save_definition(
                    ctx, item_type, target, [a for a in current if a["name"] != name]
                )
                outcome["counts"]["changed"] += 1
                self._append_sample(outcome, record)
            except Exception as exc:  # noqa: BLE001
                self._record_failure(outcome, None, field, str(exc))

        ref = {"kind": REF_CUSTOM_FIELD, "name": name}
        for row in self._rows(item_type, [w["id"] for w in workspaces]):
            current = (row.artifact.custom_fields or {}).get(name)
            if _is_blank(current):
                continue
            outcome["counts"]["matched"] += 1
            batch = _ArtifactBatch()
            self._stage(outcome, row, ref, None, current, batch, clear=True)
            self._flush(ctx, run, row, batch, write, outcome, snapshot_ids)
        return outcome

    def _step_requeue_definition(
        self, ctx, run, step, plan, item_type, workspaces, *, write, snapshot_ids
    ):
        """Re-materialize global definitions into non-customized workspace rows.

        Spec §8.4's hard rule: a customized workspace row is never overwritten
        after this action.
        """
        outcome = self._empty_outcome()
        presets = set(step["preset"])
        from attribute_definitions.models import WorkspaceAttributeDefinition

        for workspace in self._resolve_workspaces(plan["scope"]):
            if workspace["preset"] not in presets:
                continue
            rows = WorkspaceAttributeDefinition.objects.filter(
                workspace_id=workspace["id"], item_type=item_type
            )
            for row in rows:
                outcome["counts"]["matched"] += 1
                field = f"workspace:{workspace['id']}:{item_type}"
                if row.is_customized:
                    self._record_skip(
                        outcome, None, field, "workspace definition is customized"
                    )
                    continue
                if not write:
                    outcome["counts"]["changed"] += 1
                    continue
                try:
                    self._definitions.reset_workspace(ctx, item_type, workspace["id"])
                    outcome["counts"]["changed"] += 1
                except Exception as exc:  # noqa: BLE001
                    self._record_failure(outcome, None, field, str(exc))
        return outcome

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    @staticmethod
    def _step_verify(step: dict[str, Any], prior_steps: list[dict[str, Any]]) -> dict[str, Any]:
        """Evaluate report-based assertions against the steps so far (spec §4)."""
        outcome = AttributeMigrationService._empty_outcome()
        summary = AttributeMigrationService._summary(prior_steps)
        for assertion in step["assertions"]:
            parsed = parse_verify_assertion(assertion)
            if parsed is None:  # pragma: no cover - normalized at plan validation
                outcome["counts"]["failed"] += 1
                outcome["errors"].append({"assertion": assertion, "message": "unparsable"})
                continue
            metric, operator, expected = parsed
            actual = int(summary.get(metric, 0))
            passed = {
                "==": actual == expected,
                "!=": actual != expected,
                "<": actual < expected,
                "<=": actual <= expected,
                ">": actual > expected,
                ">=": actual >= expected,
            }[operator]
            if passed:
                outcome["counts"]["matched"] += 1
            else:
                outcome["counts"]["failed"] += 1
                outcome["errors"].append(
                    {
                        "assertion": assertion,
                        "message": f"{metric}={actual} does not satisfy {operator} {expected}",
                    }
                )
        outcome["message"] = f"{len(step['assertions'])} assertion(s) evaluated"
        return outcome

    # ------------------------------------------------------------------
    # Row write helpers
    # ------------------------------------------------------------------

    def _stage(
        self,
        outcome: dict[str, Any],
        row: Any,
        ref: dict[str, str],
        new_value: Any,
        current_value: Any,
        batch: _ArtifactBatch,
        *,
        clear: bool = False,
        report_before: Any = _UNSET,
    ) -> bool:
        """Stage one field change on *batch*; returns True when it changed.

        ``clear=True`` drops the value (``_REMOVE`` for a custom field, ``_EMPTY``
        for a model field). ``report_before`` overrides the before-image recorded
        in the report — a value migration reports the *source* payload, not the
        target's previous value.
        """
        if not clear and new_value == current_value:
            outcome["counts"]["skipped"] += 1
            self._append_sample(
                outcome,
                self._sample(row, ref, current_value, new_value, _STATUS_UNCHANGED, "no change"),
            )
            return False
        is_custom = ref["kind"] == REF_CUSTOM_FIELD
        batch.changes[ref["name"]] = (
            is_custom,
            (_REMOVE if is_custom else _EMPTY) if clear else new_value,
        )
        before = current_value if report_before is _UNSET else report_before
        batch.staged.append((ref, before, None if clear else new_value))
        return True

    def _flush(
        self,
        ctx: Any,
        run: Any,
        row: Any,
        batch: _ArtifactBatch,
        write: bool,
        outcome: dict[str, Any],
        snapshot_ids: list[str],
    ) -> None:
        """Persist (or report) every change staged for one artifact exactly once."""
        if not batch:
            return
        if write:
            try:
                self._persist(ctx, run, row, batch.changes, snapshot_ids)
            except Exception as exc:  # noqa: BLE001 - one failed row must not kill the run
                # The whole artifact write is atomic (see _persist): nothing of
                # this batch was left behind, so report the row as failed.
                self._record_failure(
                    outcome, row, batch.staged[0][0], str(exc)
                )
                return
            reason = "applied"
        else:
            reason = "dry run"
        for ref, before, after in batch.staged:
            self._append_sample(
                outcome,
                self._sample(row, ref, before, after, _STATUS_CHANGED, reason),
            )
        outcome["counts"]["changed"] += len(batch.staged)

    def _persist(
        self,
        ctx: Any,
        run: Any,
        row: Any,
        changes: dict[str, tuple[bool, Any]],
        snapshot_ids: list[str],
    ) -> None:
        """Snapshot then write one artifact's staged fields with a lock guard.

        **One** atomic block per artifact: snapshot the before-image, write all
        custom/model fields in a single ``UPDATE``, and emit exactly one
        ``AuditEntry``. The optimistic lock filters on the *current in-memory*
        version, then that version is bumped so a later write to the same row in
        the same step cannot trip over the engine's own version bump.
        """
        from persistence.custom_fields import validate_custom_fields
        from persistence.models import AttributeMigrationSnapshot

        custom_before = dict(row.artifact.custom_fields or {})
        custom_after = dict(custom_before)
        model_before: dict[str, Any] = {}
        type_updates: dict[str, Any] = {}
        artifact_updates: dict[str, Any] = {}

        for name, (is_custom, value) in changes.items():
            if is_custom:
                if value is _REMOVE:
                    custom_after.pop(name, None)
                elif value is _EMPTY:
                    custom_after[name] = None
                else:
                    custom_after[name] = value
                continue
            carrier = self._field_carrier(type(row), name)
            if carrier == "type":
                model_before[name] = getattr(row, name)
                type_updates[name] = None if value is _EMPTY else value
            elif carrier == "artifact":
                if name in _ARTIFACT_ACTOR_FIELDS:
                    # Persist the resolved Actor id, never the raw wire value:
                    # the column is a FK (spec section 4).
                    model_before[name] = getattr(row.artifact, f"{name}_id")
                    artifact_updates[f"{name}_id"] = self._resolve_actor_id(ctx, value)
                else:
                    model_before[name] = getattr(row.artifact, name)
                    artifact_updates[name] = None if value is _EMPTY else value
            else:
                raise _StepAbort(f"field '{name}' does not exist on {type(row).__name__}")

        custom_changed = custom_after != custom_before
        if custom_changed:
            validate_custom_fields(custom_after)

        with transaction.atomic():
            if custom_changed or model_before:
                # The snapshot is the run's *first* before-image for this
                # artifact: a later step touching the same row only merges the
                # model fields it encountered, it never overwrites the original
                # custom_fields. Otherwise rollback would restore an
                # intermediate state instead of the state before the run.
                snapshot, created = AttributeMigrationSnapshot.objects.get_or_create(
                    run=run,
                    artifact_id=row.artifact_id,
                    defaults={
                        "tenant_id": ctx.tenant_id,
                        "workspace_id": row.artifact.workspace_id,
                        "custom_fields": custom_before,
                        "model_fields": {},
                    },
                )
                if model_before:
                    merged = dict(snapshot.model_fields or {})
                    for name, before in model_before.items():
                        merged.setdefault(name, _json_safe(before))
                    snapshot.model_fields = merged
                    snapshot.save(
                        update_fields=["model_fields", "modified_at", "version"]
                    )
                if created:
                    snapshot_ids.append(str(snapshot.id))

            now = timezone.now()
            artifact_fields: dict[str, Any] = {}
            if custom_changed:
                artifact_fields["custom_fields"] = custom_after
            artifact_fields.update(artifact_updates)
            # One UPDATE for custom + artifact-level model fields: the previous
            # two-step version made the second UPDATE filter on a version the
            # first had just bumped, so it matched no row.
            if artifact_fields:
                updated = Artifact.objects.filter(
                    id=row.artifact_id, version=row.artifact.version
                ).update(**artifact_fields, version=F("version") + 1, modified_at=now)
                self._assert_locked(updated, row)
                row.artifact.version += 1
            if type_updates:
                updated = type(row).objects.filter(id=row.id, version=row.version).update(
                    **type_updates, version=F("version") + 1, modified_at=now
                )
                self._assert_locked(updated, row)
                row.version += 1

            if self._audit_artifacts:
                self._audit(
                    ctx,
                    operation=AuditEntry.OP_ATTRIBUTE_MIGRATION_APPLY,
                    entity_type="Artifact",
                    entity_id=row.artifact_id,
                    details={
                        "run_id": str(run.id),
                        "plan_id": run.plan_id,
                        "fields": sorted(changes),
                    },
                )

    @staticmethod
    def _assert_locked(updated_rows: int, row: Any) -> None:
        if updated_rows == 0:
            raise _StepAbort(
                f"optimistic-lock conflict on artifact {row.artifact_id}: "
                "row changed since the plan was read"
            )

    def _restore_snapshot(self, ctx, snapshot: Any) -> bool:
        from persistence.custom_fields import validate_custom_fields

        artifact = Artifact.objects.filter(id=snapshot.artifact_id).first()
        if artifact is None:
            return False
        type_updates: dict[str, Any] = {}
        artifact_updates: dict[str, Any] = {}
        try:
            carrier_model = self._model_for(str(artifact.artifact_type))
        except MigrationPlanError:
            carrier_model = None
        for name, before in (snapshot.model_fields or {}).items():
            carrier = self._field_carrier(
                carrier_model if carrier_model is not None else Artifact, name
            )
            if carrier == "type" and carrier_model is not None:
                type_updates[name] = before
            elif name in _ARTIFACT_ACTOR_FIELDS:
                # The snapshot stored the FK id (see ``_persist``); restore it
                # onto the ``<name>_id`` column.
                artifact_updates[f"{name}_id"] = before
            else:
                artifact_updates[name] = before
        custom_fields = snapshot.custom_fields
        if custom_fields is not None:
            validate_custom_fields(custom_fields)
        now = timezone.now()
        with transaction.atomic():
            if custom_fields is not None:
                Artifact.objects.filter(id=snapshot.artifact_id).update(
                    custom_fields=custom_fields, version=F("version") + 1, modified_at=now
                )
            if type_updates and carrier_model is not None:
                carrier_model.objects.filter(artifact_id=snapshot.artifact_id).update(
                    **type_updates, version=F("version") + 1, modified_at=now
                )
            if artifact_updates:
                Artifact.objects.filter(id=snapshot.artifact_id).update(
                    **artifact_updates, version=F("version") + 1, modified_at=now
                )
            self._audit(
                ctx,
                operation=AuditEntry.OP_ATTRIBUTE_MIGRATION_ROLLBACK,
                entity_type="Artifact",
                entity_id=snapshot.artifact_id,
                details={
                    "run_id": str(snapshot.run_id),
                    "fields": sorted(snapshot.model_fields or {}),
                },
            )
        return True

    # ------------------------------------------------------------------
    # Report helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sample(row, ref, before, after, status, reason) -> dict[str, Any]:
        artifact_id = str(row.artifact_id) if row is not None else None
        workspace_id = (
            str(row.artifact.workspace_id)
            if row is not None and row.artifact.workspace_id
            else None
        )
        prefix = "custom_fields" if ref.get("kind") == REF_CUSTOM_FIELD else "model_field"
        return {
            "artifact_id": artifact_id,
            "workspace_id": workspace_id,
            "field": f"{prefix}.{ref['name']}",
            "before": _json_safe(before),
            "after": _json_safe(after),
            "status": status,
            "reason": reason,
        }

    @staticmethod
    def _append_sample(outcome: dict[str, Any], record: dict[str, Any]) -> None:
        if len(outcome["changes"]) < MAX_SAMPLES:
            outcome["changes"].append(record)

    def _record_skip(self, outcome, row, ref, reason: str) -> None:
        outcome["counts"]["skipped"] += 1
        if isinstance(ref, dict):
            self._append_sample(
                outcome, self._sample(row, ref, None, None, _STATUS_SKIPPED, reason)
            )

    def _record_failure(self, outcome, row, ref, message: str) -> None:
        outcome["counts"]["failed"] += 1
        if len(outcome["errors"]) < MAX_SAMPLES:
            outcome["errors"].append({"field": str(ref), "message": message})
        if isinstance(ref, dict) and row is not None:
            self._append_sample(
                outcome, self._sample(row, ref, None, None, _STATUS_FAILED, message)
            )

    # ------------------------------------------------------------------
    # Definition helpers
    # ------------------------------------------------------------------

    def _read_definition(self, ctx, item_type: str, target: dict[str, Any]) -> list[dict[str, Any]]:
        if target["kind"] == "global":
            payload = self._definitions.get_global(ctx, item_type, target["preset"])
        else:
            payload = self._definitions.resolve(ctx, item_type, target["id"])
        return stored_attributes({"attributes": payload.get("attributes", [])})

    def _save_definition(
        self, ctx, item_type: str, target: dict[str, Any], attributes: list[dict[str, Any]]
    ) -> None:
        if target["kind"] == "global":
            self._definitions.update_global(ctx, item_type, target["preset"], attributes)
        else:
            self._definitions.update_workspace(ctx, item_type, target["id"], attributes)

    # ------------------------------------------------------------------
    # Link / expression helpers
    # ------------------------------------------------------------------

    def _link_resolver(
        self, row: Any, step: dict[str, Any]
    ) -> Callable[[Any], TransformOutcome] | None:
        via = step.get("via") or {}
        if not via:
            return None

        def _resolve(_value: Any) -> TransformOutcome:
            resolved = self._resolve_link_value(row, via)
            if resolved is _EMPTY:
                if step.get("fallback") is not None:
                    return TransformOutcome(APPLIED, step["fallback"], "link fallback")
                return TransformOutcome(SKIPPED, None, "no linked source value")
            return TransformOutcome(APPLIED, resolved, "linked value")

        return _resolve

    def _resolve_link_value(self, row: Any, via: dict[str, Any]) -> Any:
        from persistence.models import TraceLink

        link_type = via.get("link_type")
        if not isinstance(link_type, str) or not link_type:
            raise _StepAbort("'via.link_type' is required for link derivation")
        direction = via.get("direction", "outgoing")
        if direction not in ("outgoing", "incoming"):
            raise _StepAbort("'via.direction' must be 'outgoing' or 'incoming'")
        source_attr = via.get("source_attr")
        if not isinstance(source_attr, str) or not source_attr:
            raise _StepAbort("'via.source_attr' is required for link derivation")
        query = (
            TraceLink.objects.filter(source_id=row.artifact_id, link_type=link_type)
            if direction == "outgoing"
            else TraceLink.objects.filter(target_id=row.artifact_id, link_type=link_type)
        )
        link = query.select_related("target", "source").first()
        if link is None:
            return _EMPTY
        other = link.target if direction == "outgoing" else link.source
        return self._read_artifact_attribute(other, source_attr)

    def _read_artifact_attribute(self, artifact: Any, name: str) -> Any:
        """Read *name* off a linked Artifact, its type entity or custom_fields.

        ``artifact_system_fields``/``Artifact`` only cover the cross-cutting
        columns; ``priority``'s documented source (spec §8.2) is
        ``StakeholderNeed.moscow_priority``, a *type-model* column. Resolving the
        type entity here is what makes ``derive_from_link`` reach it.
        """
        custom = artifact.custom_fields or {}
        if name in custom:
            return custom[name]
        carrier = self._field_carrier(type(artifact), name)
        if carrier is not None:
            return getattr(artifact, name)
        try:
            model = self._model_for(str(artifact.artifact_type))
        except MigrationPlanError:
            return _EMPTY
        entity = model.objects.filter(artifact_id=artifact.id).first()
        if entity is None:
            return _EMPTY
        carrier = self._field_carrier(type(entity), name)
        if carrier == "type":
            return getattr(entity, name)
        return _EMPTY

    def _backfill_value(self, row: Any, step: dict[str, Any]) -> Any:
        strategy = step["value_strategy"]
        if strategy == STRATEGY_CONSTANT:
            return step.get("value") if step.get("value") is not None else _EMPTY
        if strategy == STRATEGY_EXPRESSION:
            expression = step.get("expression")
            if not isinstance(expression, str) or not expression.strip():
                raise _StepAbort("'expression' is required for value_strategy=expression")
            return self._render_expression(row, expression)
        if strategy == STRATEGY_DERIVE_FROM_LINK:
            via = step.get("via") or {}
            if not via:
                raise _StepAbort("'via' is required for value_strategy=derive_from_link")
            resolved = self._resolve_link_value(row, via)
            if resolved is _EMPTY:
                return step.get("fallback") if step.get("fallback") is not None else _EMPTY
            return resolved
        raise _StepAbort(f"unknown value_strategy {strategy!r}")

    def _render_expression(self, row: Any, expression: str) -> Any:
        """Render a ``{field}`` template against the row's values (no ``eval``)."""
        values: dict[str, Any] = dict(row.artifact.custom_fields or {})
        for field in type(row)._meta.get_fields():
            name = getattr(field, "name", None)
            if name and not field.is_relation:
                try:
                    values.setdefault(name, getattr(row, name))
                except Exception:  # pragma: no cover - defensive
                    continue
        for field in Artifact._meta.get_fields():
            name = getattr(field, "name", None)
            if name and not field.is_relation:
                try:
                    values.setdefault(name, getattr(row.artifact, name))
                except Exception:  # pragma: no cover - defensive
                    continue
        try:
            return expression.format_map(_SafeFormat(values))
        except (KeyError, IndexError, ValueError) as exc:
            raise _StepAbort(
                f"expression {expression!r} could not be rendered: {exc}"
            ) from exc


__all__ = [
    "AttributeMigrationConflict",
    "AttributeMigrationNotFound",
    "AttributeMigrationService",
]
