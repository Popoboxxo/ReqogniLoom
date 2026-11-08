"""Repair the duplicated ``Risk.severity`` carrier (#1707, beta.29).

Before beta.29 the attribute matrix declared ``severity`` for ``Risk`` twice:
once as the persisted ``Risk.severity`` column (excluded from introspection)
and once as an **extended** ``number`` attribute in ``Artifact.custom_fields``.
The two disagreed about the type, so the DRF serializer rejected ``7`` while
the attribute gateway rejected ``"high"`` — no value could satisfy both.

beta.29 keeps exactly one carrier: ``Risk.severity`` as an introspected core
``enum`` (``low|medium|high``). This command migrates the leftovers:

1. every numeric ``custom_fields["severity"]`` on a ``Risk`` is mapped onto the
   enum via :meth:`Risk.score_to_severity` — the codebase's one severity
   mapping (``>= 9`` high, ``>= 4`` medium, else low) — written to the
   ``Risk.severity`` column and **removed** from ``custom_fields`` (a stale
   extended key would otherwise be rejected as "not a defined attribute" on the
   next ``custom_fields`` write);
2. every workspace definition that still declares the ``extended``/``number``
   twin replaces it with the introspected core enum attribute.

Dry-run by default; ``--apply`` writes. Tenant-wide *global* defaults are only
**reported**: they are owned by ``manage.py bootstrap_attribute_definitions``,
which regenerates them from the stage matrix — editing them here would create a
second writer for the same row.

The command is idempotent: a second run reports zero findings.
"""
from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from application.models import Risk
from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    introspect_core_attributes,
)
from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from persistence.models import Artifact

_SEVERITIES = frozenset(Risk.Severity.values)


def _map_to_severity(value: Any) -> str | None:
    """Map one legacy ``custom_fields["severity"]`` value onto the enum.

    Returns ``None`` when the value cannot be mapped. Booleans are refused on
    purpose — ``True`` is not severity 1.
    """
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in _SEVERITIES:
            return candidate
        try:
            value = float(candidate)
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return Risk.score_to_severity(int(value))


class Command(BaseCommand):
    help = (
        "Repair numeric Risk severity values in custom_fields and remove the "
        "extended attribute twin from workspace definitions (#1707). "
        "Dry-run by default; pass --apply to write."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the repairs (default: report only).",
        )

    def handle(self, *args, **options) -> None:
        apply = bool(options["apply"])

        artifact_findings = self._scan_artifacts()
        definition_findings = self._scan_workspace_definitions()
        global_rows = self._scan_global_definitions()

        for finding in artifact_findings:
            self.stdout.write(
                f"Risk artifact {finding['artifact_id']} (workspace "
                f"{finding['workspace_id']}): custom_fields['severity']="
                f"{json.dumps(finding['raw'])} -> {finding['mapped'] or 'UNMAPPABLE'}"
            )
        for finding in definition_findings:
            self.stdout.write(
                f"Workspace definition {finding['definition_id']} (workspace "
                f"{finding['workspace_id']}, preset {finding['preset']}): "
                f"extended 'severity' twin -> {finding['action']}"
            )
        for row in global_rows:
            self.stdout.write(
                self.style.WARNING(
                    f"Global definition {row['definition_id']} (preset "
                    f"{row['preset']}) still carries the extended 'severity' "
                    "twin — run `manage.py bootstrap_attribute_definitions` to "
                    "regenerate the global defaults."
                )
            )

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    f"Found {len(artifact_findings)} artifact value(s) and "
                    f"{len(definition_findings)} workspace definition(s) to "
                    f"repair ({len(global_rows)} global row(s) need a "
                    "bootstrap); re-run with --apply to repair."
                )
            )
            return

        mapped = 0
        skipped = 0
        for finding in artifact_findings:
            if finding["mapped"] is None:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Risk artifact {finding['artifact_id']}: cannot map "
                        f"{json.dumps(finding['raw'])} onto low|medium|high; "
                        "left untouched."
                    )
                )
                continue
            self._apply_artifact(finding)
            mapped += 1

        for finding in definition_findings:
            self._apply_definition(finding)

        self.stdout.write(
            self.style.SUCCESS(
                f"Repaired {mapped} Risk severity value(s) "
                f"({skipped} unmappable) and {len(definition_findings)} "
                "workspace definition(s)."
            )
        )

    # ---- artifact custom_fields ------------------------------------------

    def _scan_artifacts(self) -> list[dict[str, Any]]:
        """Risks whose backing Artifact still carries an extended severity."""
        findings: list[dict[str, Any]] = []
        rows = Artifact.unscoped.filter(artifact_type="Risk").values(
            "id", "workspace_id", "custom_fields"
        )
        for row in rows:
            custom_fields = row["custom_fields"] or {}
            if "severity" not in custom_fields:
                continue
            raw = custom_fields["severity"]
            findings.append(
                {
                    "artifact_id": str(row["id"]),
                    "workspace_id": str(row["workspace_id"]),
                    "raw": raw,
                    "mapped": _map_to_severity(raw),
                }
            )
        return findings

    def _apply_artifact(self, finding: dict[str, Any]) -> None:
        with transaction.atomic():
            artifact = (
                Artifact.unscoped.select_for_update()
                .filter(pk=finding["artifact_id"])
                .first()
            )
            if artifact is None:
                return
            custom_fields = dict(artifact.custom_fields or {})
            if custom_fields.pop("severity", None) is None:
                return
            artifact.custom_fields = custom_fields
            artifact.save(update_fields=["custom_fields", "modified_at"])
            Risk.unscoped.filter(artifact_id=artifact.id).update(
                severity=finding["mapped"]
            )

    # ---- workspace definitions -------------------------------------------

    def _core_severity(self, preset: str) -> dict[str, Any] | None:
        for attribute in introspect_core_attributes("Risk", preset):
            if attribute["name"] == "severity":
                return attribute
        return None

    def _is_ext_twin(self, attribute: dict[str, Any]) -> bool:
        return (
            attribute.get("name") == "severity"
            and attribute.get("kind") == "extended"
        )

    def _scan_workspace_definitions(self) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        rows = WorkspaceAttributeDefinition.unscoped.filter(item_type="Risk")
        for row in rows:
            attributes = self._attributes(row.definition_json)
            if not any(self._is_ext_twin(attribute) for attribute in attributes):
                continue
            replacement = self._core_severity(row.preset)
            findings.append(
                {
                    "definition_id": str(row.id),
                    "workspace_id": str(row.workspace_id),
                    "preset": row.preset,
                    "attributes": attributes,
                    "replacement": replacement,
                    "action": (
                        "remove twin" if replacement is None else "replace with core enum"
                    ),
                }
            )
        return findings

    def _apply_definition(self, finding: dict[str, Any]) -> None:
        replacement = finding["replacement"]
        attributes = [
            attribute
            for attribute in finding["attributes"]
            if not self._is_ext_twin(attribute)
        ]
        if replacement is not None:
            attributes.append(replacement)
        with transaction.atomic():
            row = (
                WorkspaceAttributeDefinition.unscoped.select_for_update()
                .filter(pk=finding["definition_id"])
                .first()
            )
            if row is None:
                return
            definition = (
                dict(row.definition_json)
                if isinstance(row.definition_json, dict)
                else {"attributes": []}
            )
            definition["attributes"] = attributes
            sections = definition.get("sections")
            if isinstance(sections, list) and replacement is not None:
                names = {section.get("name") for section in sections}
                if replacement["section"] not in names:
                    sections.append(
                        {
                            "name": replacement["section"],
                            "order": len(sections),
                            "visible": True,
                            "layout": "full",
                        }
                    )
            row.definition_json = definition
            row.version = F("version") + 1
            row.save(update_fields=["definition_json", "version", "modified_at"])
        self._invalidate(finding["workspace_id"])

    # ---- global defaults (report only) -----------------------------------

    def _scan_global_definitions(self) -> list[dict[str, Any]]:
        rows = GlobalAttributeDefinition.unscoped.filter(item_type="Risk")
        return [
            {"definition_id": str(row.id), "preset": row.preset}
            for row in rows
            if any(
                self._is_ext_twin(attribute)
                for attribute in self._attributes(row.definition_json)
            )
        ]

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _attributes(definition_json: Any) -> list[dict[str, Any]]:
        if not isinstance(definition_json, dict):
            return []
        raw = definition_json.get("attributes", [])
        return [entry for entry in raw if isinstance(entry, dict)]

    @staticmethod
    def _invalidate(workspace_id: str) -> None:
        from application.cache_invalidation import invalidate_workspace_caches

        invalidate_workspace_caches(workspace_id)
