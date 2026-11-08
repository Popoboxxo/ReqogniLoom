"""Repair non-string ICD contract list entries (#1709, beta.29).

The ICD wire contract declares ``preconditions``/``postconditions``/
``invariants`` as ``string[]`` and the detail page renders every entry as a
React child. A historical write path stored structured parameter objects
(``{name, unit, ordering, data_type}``) in those fields, which crashed
``/icds/:id`` with "Objects are not valid as a React child" (React #31).

beta.29 closes the door on the write side (``ContractValidator.validate_syntax``
rejects a non-string element, on create *and* update). This command repairs the
rows that were written before that guard.

For every offending element of an ``Icd`` row:

* a mapping that carries a parameter ``name`` is **moved** to the ICD's
  structured ``parameters`` (an ``IcdParameter`` row is created unless a
  parameter with that name already exists — then only the contract entry is
  dropped, so nothing is duplicated);
* everything else is **stringified** (``json.dumps`` for containers,
  ``str()`` for scalars) so the clause survives in readable form.

Dry-run by default; ``--apply`` writes and emits one audit entry per changed
ICD. Historical ``ArtifactVersion`` snapshots are deliberately **not**
rewritten: that store is append-only by contract, and the frontend skips
non-string entries defensively, so no read path can crash on an old revision.

The command is idempotent: a second run reports zero findings.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand
from django.db import transaction

from icd.models import Icd, IcdParameter
from persistence.tenancy import TenantContext

CONTRACT_FIELDS: tuple[str, ...] = ("preconditions", "postconditions", "invariants")

#: Keys that mark a mapping as a structured parameter rather than a clause.
_PARAMETER_KEYS = frozenset({"name", "unit", "data_type", "ordering", "direction"})


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):  # pragma: no cover - exotic JSON values
        return str(value)


def _as_parameter(value: Any) -> dict[str, Any] | None:
    """Return the parameter fields of *value*, or ``None`` if it is not one."""
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    if not _PARAMETER_KEYS.intersection(value):
        return None
    return value


class Command(BaseCommand):
    help = (
        "Repair non-string ICD contract list entries: parameter objects move "
        "to structured parameters, everything else is stringified (#1709). "
        "Dry-run by default; pass --apply to write."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the repairs (default: report only).",
        )
        parser.add_argument(
            "--workspace",
            type=UUID,
            default=None,
            help="Restrict the scan to one workspace UUID.",
        )

    def handle(self, *args, **options) -> None:
        apply = bool(options["apply"])
        qs = Icd.unscoped.all()
        if options["workspace"] is not None:
            qs = qs.filter(workspace_id=options["workspace"])

        findings = [
            finding
            for icd in qs.order_by("id")
            if (finding := self._scan_icd(icd)) is not None
        ]

        for finding in findings:
            self.stdout.write(
                f"ICD {finding['icd_id']} (workspace {finding['workspace_id']}): "
                + "; ".join(
                    f"{field}: {len(entries)} non-string entr"
                    f"{'y' if len(entries) == 1 else 'ies'}"
                    for field, entries in finding["offenders"].items()
                )
            )

        if not findings:
            self.stdout.write(self.style.SUCCESS("No ICD contract lists to repair."))
            return

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    f"Found {len(findings)} ICD(s); re-run with --apply to repair."
                )
            )
            return

        moved = 0
        stringified = 0
        for finding in findings:
            moved_here, stringified_here = self._repair(finding)
            moved += moved_here
            stringified += stringified_here

        self.stdout.write(
            self.style.SUCCESS(
                f"Repaired {len(findings)} ICD(s): moved {moved} parameter "
                f"object(s), stringified {stringified} value(s)."
            )
        )

    # ---- scan ------------------------------------------------------------

    @staticmethod
    def _scan_icd(icd: Icd) -> dict[str, Any] | None:
        offenders: dict[str, list[Any]] = {}
        for field in CONTRACT_FIELDS:
            value = getattr(icd, field) or []
            bad = [entry for entry in value if not isinstance(entry, str)]
            if bad:
                offenders[field] = bad
        if not offenders:
            return None
        return {
            "icd_id": str(icd.id),
            "tenant_id": icd.tenant_id,
            "workspace_id": str(icd.workspace_id),
            "offenders": offenders,
        }

    # ---- apply -----------------------------------------------------------

    def _repair(self, finding: dict[str, Any]) -> tuple[int, int]:
        moved = 0
        stringified = 0
        TenantContext.set_tenant(finding["tenant_id"])
        try:
            with transaction.atomic():
                icd = (
                    Icd.unscoped.select_for_update()
                    .filter(pk=finding["icd_id"])
                    .first()
                )
                if icd is None:
                    return 0, 0
                for field in CONTRACT_FIELDS:
                    value = getattr(icd, field) or []
                    if all(isinstance(entry, str) for entry in value):
                        continue
                    cleaned: list[str] = []
                    for entry in value:
                        if isinstance(entry, str):
                            cleaned.append(entry)
                            continue
                        parameter = _as_parameter(entry)
                        if parameter is not None:
                            self._ensure_parameter(icd, parameter)
                            moved += 1
                            continue
                        cleaned.append(_stringify(entry))
                        stringified += 1
                    setattr(icd, field, cleaned)
                    icd.save(update_fields=[field, "modified_at"])
                self._audit(icd, finding["offenders"], moved, stringified)
        finally:
            TenantContext.clear_tenant()
        return moved, stringified

    @staticmethod
    def _ensure_parameter(icd: Icd, parameter: dict[str, Any]) -> None:
        """Create the parameter unless one with the same name already exists."""
        name = str(parameter["name"]).strip()[:200]
        if IcdParameter.unscoped.filter(icd_id=icd.id, name=name).exists():
            return
        unit = str(parameter.get("unit") or "")[:50]
        data_type = str(parameter.get("data_type") or "")[:20]
        ordering = parameter.get("ordering")
        IcdParameter.unscoped.create(
            tenant_id=icd.tenant_id,
            icd=icd,
            name=name,
            unit=unit,
            data_type=data_type or "other",
            ordering=ordering if isinstance(ordering, int) and ordering >= 0 else 0,
        )

    @staticmethod
    def _audit(
        icd: Icd, offenders: dict[str, list[Any]], moved: int, stringified: int
    ) -> None:
        from audit.services import log_write

        log_write(
            actor="system:repair_icd_contract_lists",
            actor_type="agent",
            operation="update",
            entity_type="Icd",
            entity_id=icd.id,
            change_reason="repair non-string contract list entries (#1709)",
            ctx={"source": "management_command"},
            details={
                "fields": sorted(offenders),
                "moved_to_parameters": moved,
                "stringified": stringified,
            },
        )
