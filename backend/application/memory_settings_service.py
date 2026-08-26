"""MemorySettingsService — System-Admin read/write of the process-wide
SystemMemorySettings override (Memory Admin UI Phase 3, spec 2026-08-26).

No ctx-based permission check in this service (Phase 3 plan Ruling 3):
the caller (SystemMemorySettingsView / SystemMemorySettingsResetView) already
gates via its own module-level _is_system_admin(ctx), matching the existing
LlmSettingsView/ReviewPolicyView/PromptTemplateView precedent of gating in
the view rather than duplicating the check in the service.
"""
from __future__ import annotations

from typing import Any, Optional

from memory.models import SYSTEM_MEMORY_SETTINGS_ID, SystemMemorySettings
from persistence.transactions import atomic_transaction

_OVERRIDABLE_FIELDS = (
    "embedding_provider",
    "embedding_model_name",
    "ollama_base_url",
    "embedding_timeout",
    "memory_backend",
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

    def get_effective_settings(self) -> dict[str, Any]:
        """Read-only: never creates a row (issue #276 precedent)."""
        row = SystemMemorySettings.objects.first()
        result = self._serialize(row)
        result["warning"] = None
        return result

    @atomic_transaction
    def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        row, _ = SystemMemorySettings.objects.get_or_create(pk=SYSTEM_MEMORY_SETTINGS_ID)

        old_provider = row.embedding_provider
        old_backend = row.memory_backend

        for field in _OVERRIDABLE_FIELDS:
            if field in data:
                setattr(row, field, data[field])
        if "honcho_api_key" in data and data["honcho_api_key"]:
            row.honcho_api_key = data["honcho_api_key"]
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
        return result

    @atomic_transaction
    def reset_settings(self) -> dict[str, Any]:
        row, _ = SystemMemorySettings.objects.get_or_create(pk=SYSTEM_MEMORY_SETTINGS_ID)
        for field in _OVERRIDABLE_FIELDS:
            setattr(row, field, None)
        row.honcho_api_key_encrypted = ""
        row.save()
        result = self._serialize(row)
        result["warning"] = None
        return result


__all__ = ["MemorySettingsService"]
