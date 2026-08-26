"""MemorySettingsService — System-Admin read/write of the process-wide
SystemMemorySettings override (Memory Admin UI Phase 3, spec 2026-08-26).

No ctx-based permission check in this service (Phase 3 plan Ruling 3):
the caller (SystemMemorySettingsView / SystemMemorySettingsResetView) already
gates the write paths on ``_is_superuser`` (final whole-branch review C-1) and
the read path on ``_is_system_admin``, matching the existing LlmSettingsView/
ReviewPolicyView/PromptTemplateView precedent of gating in the view rather
than duplicating the check in the service.

``user_id`` is passed in for ATTRIBUTION only (created_by/modified_by +
audit entry, final whole-branch review I-6) — never for authorization.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from django.db import transaction

from memory.models import SYSTEM_MEMORY_SETTINGS_ID, SystemMemorySettings
from persistence.transactions import atomic_transaction

logger = logging.getLogger(__name__)

_OVERRIDABLE_FIELDS = (
    "embedding_provider",
    "embedding_model_name",
    "ollama_base_url",
    "embedding_timeout",
    "memory_backend",
    "honcho_base_url",
)

# Free-text override fields: an empty string here means "no override", not
# "override with an empty value" (final whole-branch review I-3). The read
# overlay in llm_adapter.embedding_service._apply_db_settings / memory.backends
# tests these fields for truthiness, so a stored "" would be silently ignored
# at runtime while _serialize() still reported `<field>_is_override: true` —
# i.e. the dashboard would lie about the effective configuration. Normalising
# "" -> None on write keeps report and runtime in agreement, and makes
# "clear the field in the UI" actually clear the override.
# NOT applicable to embedding_provider/memory_backend (ChoiceFields, cannot be
# blank) nor to embedding_timeout (IntegerField).
_BLANKABLE_TEXT_FIELDS = (
    "embedding_model_name",
    "ollama_base_url",
    "honcho_base_url",
)


class MemorySettingsService:
    """Read/write the singleton SystemMemorySettings row."""

    @staticmethod
    def _serialize(row: Optional[SystemMemorySettings]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field in _OVERRIDABLE_FIELDS:
            value = getattr(row, field, None) if row is not None else None
            data[field] = value
            data[f"{field}_is_override"] = value is not None
        data["honcho_api_key_is_set"] = bool(row.honcho_api_key) if row is not None else False
        return data

    @staticmethod
    def _audit_config_write(user_id: Optional[UUID], operation: str, changed_fields: list[str]) -> None:
        """Best-effort audit entry for a write to the global settings row.

        Not a :class:`ServiceBase` subclass (this service takes no ``ctx``),
        so ``audit.services.log_write`` is called directly with the same
        arguments ``ServiceBase._audit`` would pass. Deliberately non-fatal:
        ``AuditEntry`` is tenant-scoped while this row is deployment-global,
        so an audit write can fail for reasons (missing tenant context on a
        non-request caller) that must not roll back a legitimate config
        change. Field NAMES only — never values, the row holds a secret.

        Runs inside its own nested ``transaction.atomic()`` (a SAVEPOINT,
        since this always runs inside the caller's outer
        ``@atomic_transaction``): a DB-level failure in ``log_write`` (e.g.
        a missing monthly ``AuditEntry`` partition, ADR-L3-AL001-04) issues
        real SQL that poisons the current transaction. Without the nested
        savepoint, catching that exception here would not un-poison the
        OUTER transaction, so the caller's actual config write would still
        silently roll back on commit despite this ``except`` — i.e. the
        surrounding ``try/except`` alone does not protect the config write,
        only a savepoint does.
        """
        if user_id is None:
            return
        try:
            with transaction.atomic():
                from audit.services import log_write

                log_write(
                    actor=str(user_id),
                    actor_type="user",
                    operation=operation,
                    entity_type="SystemMemorySettings",
                    entity_id=SYSTEM_MEMORY_SETTINGS_ID,
                    change_reason=f"fields={sorted(changed_fields)}" if changed_fields else "reset",
                )
        except Exception:  # noqa: BLE001 - see docstring: attribution is best-effort
            logger.warning(
                "MemorySettingsService: audit entry for %s could not be written", operation,
                exc_info=True,
            )

    def get_effective_settings(self) -> dict[str, Any]:
        """Read-only: never creates a row (issue #276 precedent)."""
        row = SystemMemorySettings.objects.first()
        result = self._serialize(row)
        result["warning"] = None
        return result

    @atomic_transaction
    def update_settings(
        self, data: dict[str, Any], user_id: Optional[UUID] = None
    ) -> dict[str, Any]:
        """Apply a partial override. ``user_id`` is attribution-only.

        Omitted fields stay unchanged; a field sent as ``None`` — or, for the
        free-text fields in :data:`_BLANKABLE_TEXT_FIELDS`, as ``""`` — clears
        that field's override so the environment value wins again.
        """
        row, created = SystemMemorySettings.objects.get_or_create(pk=SYSTEM_MEMORY_SETTINGS_ID)

        old_provider = row.embedding_provider
        old_backend = row.memory_backend

        for field in _OVERRIDABLE_FIELDS:
            if field in data:
                value = data[field]
                if field in _BLANKABLE_TEXT_FIELDS and value == "":
                    value = None
                setattr(row, field, value)
        if "honcho_api_key" in data and data["honcho_api_key"]:
            row.honcho_api_key = data["honcho_api_key"]
        if user_id is not None:
            if created or row.created_by_id is None:
                row.created_by_id = user_id
            row.modified_by_id = user_id
        row.save()

        result = self._serialize(row)
        warnings = []
        if "embedding_provider" in data and data["embedding_provider"] != old_provider:
            warnings.append(
                "Embedding provider changed. Existing embeddings were NOT re-indexed "
                "and remain in the previous provider's vector space; re-indexing is manual."
            )
        if "memory_backend" in data and data["memory_backend"] != old_backend:
            warnings.append(
                "Memory backend changed. Existing entries in the previous backend are "
                "NOT migrated automatically."
            )
        result["warning"] = " ".join(warnings) if warnings else None
        self._audit_config_write(user_id, "update", list(data.keys()))
        return result

    @atomic_transaction
    def reset_settings(self, user_id: Optional[UUID] = None) -> dict[str, Any]:
        """Clear every override (including the secret). ``user_id`` is attribution-only."""
        row, created = SystemMemorySettings.objects.get_or_create(pk=SYSTEM_MEMORY_SETTINGS_ID)
        for field in _OVERRIDABLE_FIELDS:
            setattr(row, field, None)
        row.honcho_api_key_encrypted = ""
        if user_id is not None:
            if created or row.created_by_id is None:
                row.created_by_id = user_id
            row.modified_by_id = user_id
        row.save()
        result = self._serialize(row)
        result["warning"] = None
        self._audit_config_write(user_id, "update", [])
        return result


__all__ = ["MemorySettingsService"]
