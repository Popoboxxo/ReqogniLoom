"""ArtifactVectorSettingsService — admin read/write of the artifact vector store.

Backs the Admin-UI surface for the artifact vector backend (the counterpart of
:class:`application.memory_settings_service.MemorySettingsService`). It owns
validation and persistence; the REST adapter only gates and transports.

Deliberately **not** part of the memory settings: the artifact store is
decoupled from ``MEMORY_BACKEND`` by ADR-020 §4, so a write here never changes
which memory backend serves. The singleton row lives in
:class:`persistence.models.SystemArtifactVectorSettings`.

Permission checks belong to the view (mirroring the memory-settings precedent);
``user_id`` is attribution-only.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from application.vector_backends import (
    VECTOR_BACKEND_REGISTRY,
    VectorBackendPlugin,
    VectorBackendSettingField,
    resolve_artifact_vector_backend_name,
)
from persistence.models import (
    SYSTEM_ARTIFACT_VECTOR_SETTINGS_ID,
    SystemArtifactVectorSettings,
)
from persistence.transactions import atomic_transaction

logger = logging.getLogger(__name__)

__all__ = [
    "ArtifactVectorSettingsService",
    "ArtifactVectorSettingsValidationError",
]


class ArtifactVectorSettingsValidationError(Exception):
    """Carries the REST ``details`` list for a rejected write."""

    def __init__(self, details: list[dict[str, Any]]) -> None:
        super().__init__("artifact vector settings validation failed")
        self.details = details


def _row() -> SystemArtifactVectorSettings | None:
    return SystemArtifactVectorSettings.objects.first()


def _read_maps(
    row: SystemArtifactVectorSettings | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(backend_options, backend_secrets)``; a GET must never 500."""
    if row is None:
        return {}, {}
    options = row.backend_options or {}
    try:
        secrets = row.backend_secrets or {}
    except Exception:  # noqa: BLE001 - rotated key must not break a read
        logger.warning(
            "ArtifactVectorSettingsService: secrets are unreadable (rotated key?)",
            exc_info=True,
        )
        secrets = {}
    return options, secrets


def _schema_payload(plugin: type[VectorBackendPlugin]) -> list[dict[str, Any]]:
    return [
        {
            "name": field.name,
            "type": field.type,
            "env_var": field.env_var,
            "label_key": field.label_key,
            "choices": list(field.choices),
            "min_value": field.min_value,
            "max_length": field.max_length,
            "default": field.default,
        }
        for field in plugin.settings_schema
    ]


def _validate_options(
    plugin: type[VectorBackendPlugin], options: Any
) -> list[dict[str, Any]]:
    """Validate one backend's option map against its declared schema."""
    details: list[dict[str, Any]] = []
    if not isinstance(options, dict):
        return [{"field": "backend_options", "errors": ["must be an object"]}]
    by_name: dict[str, VectorBackendSettingField] = {
        field.name: field for field in plugin.settings_schema
    }
    for name, value in options.items():
        field = by_name.get(name)
        if field is None:
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": ["unknown field"]}
            )
            continue
        if field.type == "secret":
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": ["secrets must be sent in backend_secrets"]}
            )
            continue
        if value is None:
            continue
        if field.type == "int" and not isinstance(value, int):
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": ["must be an integer"]}
            )
            continue
        if field.type == "int" and field.min_value is not None and value < field.min_value:
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": [f"must be >= {field.min_value}"]}
            )
            continue
        if field.type == "float" and not isinstance(value, (int, float)):
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": ["must be a number"]}
            )
            continue
        if (
            field.type == "float"
            and field.min_value is not None
            and float(value) < field.min_value
        ):
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": [f"must be >= {field.min_value}"]}
            )
            continue
        if field.type == "bool" and not isinstance(value, bool):
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": ["must be a boolean"]}
            )
            continue
        if field.type == "choice" and value not in field.choices:
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": [f"must be one of: {', '.join(field.choices)}"]}
            )
            continue
        if field.type == "str" and not isinstance(value, str):
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": ["must be a string"]}
            )
            continue
        if (
            field.type == "str"
            and field.max_length is not None
            and len(value) > field.max_length
        ):
            details.append(
                {"field": f"backend_options.{plugin.settings_key}.{name}",
                 "errors": [f"must be at most {field.max_length} characters"]}
            )
    return details


def _validate_secrets(
    plugin: type[VectorBackendPlugin], secrets: Any
) -> list[dict[str, Any]]:
    if not isinstance(secrets, dict):
        return [{"field": "backend_secrets", "errors": ["must be an object"]}]
    allowed = set(plugin.secret_names())
    details: list[dict[str, Any]] = []
    for name, value in secrets.items():
        if name not in allowed:
            details.append(
                {"field": f"backend_secrets.{plugin.settings_key}.{name}",
                 "errors": ["unknown secret field"]}
            )
            continue
        if value is not None and not isinstance(value, str):
            details.append(
                {"field": f"backend_secrets.{plugin.settings_key}.{name}",
                 "errors": ["must be a string"]}
            )
            continue
    return details


class ArtifactVectorSettingsService:
    """Read/write the singleton artifact-vector settings row."""

    # -- read ---------------------------------------------------------------
    def backends_payload(self) -> dict[str, Any]:
        row = _row()
        options, secrets = _read_maps(row)
        payload: dict[str, Any] = {}
        for name, plugin in VECTOR_BACKEND_REGISTRY.items():
            key = plugin.settings_key or name
            override = options.get(key, {}) or {}
            backend_secrets = secrets.get(key, {}) or {}
            payload[name] = {
                "schema": _schema_payload(plugin),
                "values": plugin.effective_settings(),
                "is_override": {
                    field.name: (
                        bool(backend_secrets.get(field.name))
                        if field.type == "secret"
                        else field.name in override
                    )
                    for field in plugin.settings_schema
                },
                "secrets_set": {
                    secret: bool(backend_secrets.get(secret))
                    for secret in plugin.secret_names()
                },
                "capabilities": plugin.capabilities.__dict__,
            }
        return payload

    def get_effective_settings(self) -> dict[str, Any]:
        """Read-only: never creates a row."""
        from application.vector_port import vector_backend_diagnostic

        row = _row()
        return {
            "vector_backend": row.vector_backend if row is not None else None,
            "vector_backend_is_override": bool(
                row is not None and row.vector_backend
            ),
            "effective_vector_backend": resolve_artifact_vector_backend_name(),
            "available_backends": sorted(VECTOR_BACKEND_REGISTRY),
            "backends": self.backends_payload(),
            "diagnostic": vector_backend_diagnostic(),
        }

    # -- write --------------------------------------------------------------
    @atomic_transaction
    def update_settings(
        self, data: dict[str, Any], user_id: UUID | None = None
    ) -> dict[str, Any]:
        """Apply a partial override. Omitted fields stay unchanged.

        ``vector_backend=None`` (or ``""``) clears the selector override so the
        ``ARTIFACT_VECTOR_BACKEND`` environment value wins again.
        """
        row, created = SystemArtifactVectorSettings.objects.get_or_create(
            pk=SYSTEM_ARTIFACT_VECTOR_SETTINGS_ID
        )

        details: list[dict[str, Any]] = []
        backend_value = data.get("vector_backend")
        if "vector_backend" in data and backend_value not in (None, ""):
            if backend_value not in VECTOR_BACKEND_REGISTRY:
                details.append(
                    {"field": "vector_backend",
                     "errors": [
                         "unknown backend; available: "
                         + ", ".join(sorted(VECTOR_BACKEND_REGISTRY))
                     ]}
                )

        options = data.get("backend_options")
        secrets = data.get("backend_secrets")
        if isinstance(options, dict):
            for key, value in options.items():
                plugin = self._plugin_for_key(key)
                if plugin is None:
                    details.append(
                        {"field": f"backend_options.{key}",
                         "errors": ["unknown backend"]}
                    )
                    continue
                details.extend(_validate_options(plugin, value))
        if isinstance(secrets, dict):
            for key, value in secrets.items():
                plugin = self._plugin_for_key(key)
                if plugin is None:
                    details.append(
                        {"field": f"backend_secrets.{key}",
                         "errors": ["unknown backend"]}
                    )
                    continue
                details.extend(_validate_secrets(plugin, value))

        if details:
            raise ArtifactVectorSettingsValidationError(details)

        if "vector_backend" in data:
            row.vector_backend = backend_value or None
        if isinstance(options, dict):
            merged = dict(row.backend_options or {})
            for key, value in options.items():
                plugin = self._plugin_for_key(key)
                assert plugin is not None
                settings_key = plugin.settings_key or key
                current = dict(merged.get(settings_key) or {})
                for field_name, field_value in (value or {}).items():
                    if field_value is None:
                        current.pop(field_name, None)
                    else:
                        current[field_name] = field_value
                if current:
                    merged[settings_key] = current
                else:
                    merged.pop(settings_key, None)
            row.backend_options = merged
        if isinstance(secrets, dict) and secrets:
            merged_secrets = dict(row.backend_secrets)
            for key, value in secrets.items():
                plugin = self._plugin_for_key(key)
                assert plugin is not None
                settings_key = plugin.settings_key or key
                current = dict(merged_secrets.get(settings_key) or {})
                for field_name, field_value in (value or {}).items():
                    if not field_value:
                        # An empty secret means "keep the stored one": the UI
                        # only reports presence, so an untouched empty input
                        # must never erase a configured key.
                        continue
                    current[field_name] = field_value
                if current:
                    merged_secrets[settings_key] = current
                else:
                    merged_secrets.pop(settings_key, None)
            row.backend_secrets = merged_secrets

        if user_id is not None:
            if created or row.created_by_id is None:
                row.created_by_id = user_id
            row.modified_by_id = user_id
        row.save()

        result = self.get_effective_settings()
        self._audit_config_write(user_id, "update", list(data.keys()))
        return result

    @atomic_transaction
    def reset_settings(self, user_id: UUID | None = None) -> dict[str, Any]:
        """Clear the selector and every backend override (env wins again)."""
        row, created = SystemArtifactVectorSettings.objects.get_or_create(
            pk=SYSTEM_ARTIFACT_VECTOR_SETTINGS_ID
        )
        row.vector_backend = None
        row.backend_options = {}
        row.backend_secrets_encrypted = ""
        if user_id is not None:
            if created or row.created_by_id is None:
                row.created_by_id = user_id
            row.modified_by_id = user_id
        row.save()
        result = self.get_effective_settings()
        self._audit_config_write(user_id, "reset", [])
        return result

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _plugin_for_key(
        key: str,
    ) -> type[VectorBackendPlugin] | None:
        plugin = VECTOR_BACKEND_REGISTRY.get(key)
        if plugin is not None:
            return plugin
        for candidate in VECTOR_BACKEND_REGISTRY.values():
            if candidate.settings_key and candidate.settings_key == key:
                return candidate
        return None

    @staticmethod
    def _audit_config_write(
        user_id: UUID | None, operation: str, changed_fields: list[str]
    ) -> None:
        """Best-effort audit entry (field names only, never values)."""
        if user_id is None:
            return
        try:
            from django.db import transaction

            with transaction.atomic():
                from audit.services import log_write

                log_write(
                    actor=str(user_id),
                    actor_type="user",
                    operation=operation,
                    entity_type="SystemArtifactVectorSettings",
                    entity_id=SYSTEM_ARTIFACT_VECTOR_SETTINGS_ID,
                    change_reason=(
                        f"fields={sorted(changed_fields)}" if changed_fields else "reset"
                    ),
                )
        except Exception:  # noqa: BLE001 - attribution is best-effort
            logger.warning(
                "ArtifactVectorSettingsService: audit entry for %s could not be written",
                operation,
                exc_info=True,
            )
