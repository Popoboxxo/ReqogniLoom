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
from typing import Any
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
    "qdrant_base_url",
    "qdrant_collection_prefix",
    "qdrant_distance",
    "qdrant_timeout",
    "qdrant_hnsw_m",
    "qdrant_hnsw_ef_construct",
    "qdrant_prefer_grpc",
    "memory_write_rate_limit_per_hour",
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
# blank) nor to the numeric fields (embedding_timeout/qdrant_timeout/...).
_BLANKABLE_TEXT_FIELDS = (
    "embedding_model_name",
    "ollama_base_url",
    "honcho_base_url",
    "qdrant_base_url",
    "qdrant_collection_prefix",
    "qdrant_distance",
)


#: Legacy flat column <-> (backend, option field) for the dual-write.
_BACKEND_OPTION_LEGACY: dict[tuple[str, str], str] = {
    ("honcho", "base_url"): "honcho_base_url",
    ("qdrant", "base_url"): "qdrant_base_url",
    ("qdrant", "collection_prefix"): "qdrant_collection_prefix",
    ("qdrant", "distance"): "qdrant_distance",
    ("qdrant", "timeout"): "qdrant_timeout",
    ("qdrant", "hnsw_m"): "qdrant_hnsw_m",
    ("qdrant", "hnsw_ef_construct"): "qdrant_hnsw_ef_construct",
    ("qdrant", "prefer_grpc"): "qdrant_prefer_grpc",
}
#: Legacy secret property <-> (backend, secret field).
_BACKEND_SECRET_LEGACY: dict[tuple[str, str], str] = {
    ("honcho", "api_key"): "honcho_api_key",
    ("qdrant", "api_key"): "qdrant_api_key",
}


class BackendSettingsValidationError(Exception):
    """Carries the REST ``details`` list for a rejected backend map.

    Raised after the whole map was validated, so the caller gets every offending
    path at once (``backend_options.honcho.<field>``) instead of one per round
    trip — and never a partially applied write.
    """

    def __init__(self, details: list[dict[str, Any]]) -> None:
        super().__init__("backend settings validation failed")
        self.details = details


def _backend_class(key: str):
    """Resolve a backend by registry name or declared settings key."""
    from memory.backends import MEMORY_BACKEND_REGISTRY

    for name, cls in MEMORY_BACKEND_REGISTRY.items():
        if name == key or (cls.settings_key or name) == key:
            return cls
    return None


def _settings_key(key: str) -> str:
    cls = _backend_class(key)
    if cls is None:
        return key
    return cls.settings_key or key


class MemorySettingsService:
    """Read/write the singleton SystemMemorySettings row."""

    @staticmethod
    def _serialize(row: SystemMemorySettings | None) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field in _OVERRIDABLE_FIELDS:
            value = getattr(row, field, None) if row is not None else None
            data[field] = value
            data[f"{field}_is_override"] = value is not None
        # Derive the "is set" flags from the PRESENCE of the encrypted column,
        # never from the decrypting property (F8): ``row.qdrant_api_key`` calls
        # ``decrypt_secret``, which raises ``InvalidToken`` over stored
        # ciphertext once FIELD_ENCRYPTION_KEY has been rotated. That turned
        # every admin GET into a 500 even though presence -- not decryptability
        # -- is the only thing this flag reports. Presence is what the column
        # already encodes (``encrypt_secret("")`` keeps ""), so the flag stays
        # identical for healthy rows.
        data["honcho_api_key_is_set"] = (
            bool(row.honcho_api_key_encrypted) if row is not None else False
        )
        data["qdrant_api_key_is_set"] = (
            bool(row.qdrant_api_key_encrypted) if row is not None else False
        )
        return data

    @staticmethod
    def _audit_config_write(user_id: UUID | None, operation: str, changed_fields: list[str]) -> None:
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

    def backends_payload(self) -> dict[str, Any]:
        """The additive ``backends`` object of the settings response.

        Values are effective (DB override > env > default) and NEVER contain a
        secret: a secret field is reported through ``secrets_set`` only.
        """
        from dataclasses import asdict

        from memory.backends import MEMORY_BACKEND_REGISTRY

        row = SystemMemorySettings.objects.first()
        options = (row.backend_options if row is not None else {}) or {}
        secrets = (row.backend_secrets if row is not None else {}) or {}
        payload: dict[str, Any] = {}
        for name, cls in MEMORY_BACKEND_REGISTRY.items():
            key = cls.settings_key or name
            override = options.get(key, {}) or {}
            backend_secrets = secrets.get(key, {}) or {}
            schema = [
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
                for field in cls.settings_schema
            ]
            is_override = {
                field.name: (
                    bool(backend_secrets.get(field.name))
                    if field.type == "secret"
                    else field.name in override
                )
                for field in cls.settings_schema
            }
            capabilities = asdict(cls.capabilities)
            capabilities["scopes"] = list(capabilities["scopes"])
            payload[name] = {
                "schema": schema,
                "values": cls.effective_settings(),
                "is_override": is_override,
                "secrets_set": {
                    secret: bool(backend_secrets.get(secret))
                    for secret in cls.secret_names()
                },
                "capabilities": capabilities,
            }
        return payload

    @staticmethod
    def _validate_backend_maps(
        options: Any, secrets: Any
    ) -> list[dict[str, Any]]:
        """Validate both maps against the declared schemas; return all details."""
        details: list[dict[str, Any]] = []

        if options is not None and not isinstance(options, dict):
            details.append({"field": "backend_options", "errors": ["must be an object"]})
            options = {}
        if secrets is not None and not isinstance(secrets, dict):
            details.append({"field": "backend_secrets", "errors": ["must be an object"]})
            secrets = {}

        def _validate(values: dict, base: str, *, secret_map: bool) -> None:
            for backend, fields in values.items():
                cls = _backend_class(backend)
                if cls is None:
                    details.append(
                        {"field": f"{base}.{backend}", "errors": ["unknown backend"]}
                    )
                    continue
                if not isinstance(fields, dict):
                    details.append(
                        {"field": f"{base}.{backend}", "errors": ["must be an object"]}
                    )
                    continue
                specs = {field.name: field for field in cls.settings_schema}
                for field_name, value in fields.items():
                    spec = specs.get(field_name)
                    path = f"{base}.{backend}.{field_name}"
                    if spec is None:
                        details.append({"field": path, "errors": ["unknown field"]})
                        continue
                    if secret_map and spec.type != "secret":
                        details.append(
                            {"field": path, "errors": ["not a secret field"]}
                        )
                        continue
                    if not secret_map and spec.type == "secret":
                        details.append(
                            {
                                "field": path,
                                "errors": ["secret fields must use backend_secrets"],
                            }
                        )
                        continue
                    if value is None:
                        continue
                    if spec.type == "bool":
                        if not isinstance(value, bool):
                            details.append({"field": path, "errors": ["must be a boolean"]})
                    elif spec.type == "int":
                        if not isinstance(value, int) or isinstance(value, bool):
                            details.append({"field": path, "errors": ["must be an integer"]})
                    elif spec.type == "float":
                        if not isinstance(value, (int, float)) or isinstance(value, bool):
                            details.append({"field": path, "errors": ["must be a number"]})
                    else:
                        if not isinstance(value, str):
                            details.append({"field": path, "errors": ["must be a string"]})
                            continue
                        if spec.choices and value not in spec.choices:
                            details.append(
                                {
                                    "field": path,
                                    "errors": [f"must be one of {list(spec.choices)}"],
                                }
                            )
                        if spec.max_length is not None and len(value) > spec.max_length:
                            details.append(
                                {
                                    "field": path,
                                    "errors": [f"must be at most {spec.max_length} characters"],
                                }
                            )
                    if (
                        not secret_map
                        and isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and spec.min_value is not None
                        and value < spec.min_value
                    ):
                        details.append(
                            {
                                "field": path,
                                "errors": [f"must be at least {spec.min_value}"],
                            }
                        )

        _validate(options or {}, "backend_options", secret_map=False)
        _validate(secrets or {}, "backend_secrets", secret_map=True)
        return details

    @classmethod
    def _apply_backend_maps(
        cls, row: SystemMemorySettings, options: Any, secrets: Any
    ) -> None:
        """Merge the maps into the row and dual-write the legacy columns."""
        options = options or {}
        secrets = secrets or {}

        current_options = dict(row.backend_options or {})
        for backend, fields in options.items():
            key = _settings_key(backend)
            merged = dict(current_options.get(key) or {})
            for field_name, value in fields.items():
                if value is None:
                    merged.pop(field_name, None)
                else:
                    merged[field_name] = value
            if merged:
                current_options[key] = merged
            else:
                current_options.pop(key, None)
        row.backend_options = current_options

        current_secrets = dict(row.backend_secrets)
        for backend, fields in secrets.items():
            key = _settings_key(backend)
            merged = dict(current_secrets.get(key) or {})
            for field_name, value in fields.items():
                if value is None:
                    merged.pop(field_name, None)
                else:
                    merged[field_name] = value
            if merged:
                current_secrets[key] = merged
            else:
                current_secrets.pop(key, None)
        row.backend_secrets = current_secrets

        # Dual-write (QR-T15): old code reads the legacy columns until the
        # contract migration (T-A0b-6) drops them.
        for (backend, field_name), legacy in _BACKEND_OPTION_LEGACY.items():
            if backend in options and field_name in (options.get(backend) or {}):
                setattr(row, legacy, (current_options.get(backend) or {}).get(field_name))
        for (backend, field_name), legacy in _BACKEND_SECRET_LEGACY.items():
            if backend in secrets and field_name in (secrets.get(backend) or {}):
                value = (current_secrets.get(backend) or {}).get(field_name) or ""
                setattr(row, legacy, value)

    @staticmethod
    def _mirror_flat_fields(row: SystemMemorySettings, data: dict[str, Any]) -> None:
        """Keep the maps in sync when a caller uses the legacy flat fields."""
        options = dict(row.backend_options or {})
        changed = False
        for (backend, field_name), legacy in _BACKEND_OPTION_LEGACY.items():
            if legacy not in data:
                continue
            value = getattr(row, legacy)
            key = _settings_key(backend)
            merged = dict(options.get(key) or {})
            if value is None:
                merged.pop(field_name, None)
            else:
                merged[field_name] = value
            if merged:
                options[key] = merged
            else:
                options.pop(key, None)
            changed = True
        if changed:
            row.backend_options = options

        secrets = dict(row.backend_secrets)
        secrets_changed = False
        for (backend, field_name), legacy in _BACKEND_SECRET_LEGACY.items():
            if legacy not in data:
                continue
            value = getattr(row, legacy)
            key = _settings_key(backend)
            merged = dict(secrets.get(key) or {})
            if value:
                merged[field_name] = value
            else:
                merged.pop(field_name, None)
            if merged:
                secrets[key] = merged
            else:
                secrets.pop(key, None)
            secrets_changed = True
        if secrets_changed:
            row.backend_secrets = secrets

    def get_effective_settings(self) -> dict[str, Any]:
        """Read-only: never creates a row (issue #276 precedent)."""
        row = SystemMemorySettings.objects.first()
        result = self._serialize(row)
        result["warning"] = None
        result["backends"] = self.backends_payload()
        return result

    @atomic_transaction
    def update_settings(
        self, data: dict[str, Any], user_id: UUID | None = None
    ) -> dict[str, Any]:
        """Apply a partial override. ``user_id`` is attribution-only.

        Omitted fields stay unchanged; a field sent as ``None`` — or, for the
        free-text fields in :data:`_BLANKABLE_TEXT_FIELDS`, as ``""`` — clears
        that field's override so the environment value wins again.
        """
        row, created = SystemMemorySettings.objects.get_or_create(pk=SYSTEM_MEMORY_SETTINGS_ID)

        # ENT-A1 = b with a transition (QR-T24): these three UI fields have no
        # server-side effect. Accept them (no 400) but say so once per request;
        # they are never persisted, so a later decision cannot resurrect stale
        # data.
        for deprecated in (
            "honcho_peer_name",
            "honcho_workspace_id",
            "honcho_app_id",
        ):
            if deprecated in data:
                logger.warning(
                    "SystemMemorySettings: %s is deprecated and was not persisted",
                    deprecated,
                )

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
        if "qdrant_api_key" in data and data["qdrant_api_key"]:
            row.qdrant_api_key = data["qdrant_api_key"]

        # T-A0b-3: validate the whole backend maps before touching the row, so
        # a rejected field cannot leave a half-applied write behind.
        details = self._validate_backend_maps(
            data.get("backend_options"), data.get("backend_secrets")
        )
        if details:
            raise BackendSettingsValidationError(details)
        if "backend_options" in data or "backend_secrets" in data:
            self._apply_backend_maps(
                row, data.get("backend_options"), data.get("backend_secrets")
            )
        self._mirror_flat_fields(row, data)

        if user_id is not None:
            if created or row.created_by_id is None:
                row.created_by_id = user_id
            row.modified_by_id = user_id
        row.save()

        result = self._serialize(row)
        result["backends"] = self.backends_payload()
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
    def reset_settings(self, user_id: UUID | None = None) -> dict[str, Any]:
        """Clear every override (including the secret). ``user_id`` is attribution-only."""
        row, created = SystemMemorySettings.objects.get_or_create(pk=SYSTEM_MEMORY_SETTINGS_ID)
        for field in _OVERRIDABLE_FIELDS:
            setattr(row, field, None)
        row.honcho_api_key_encrypted = ""
        row.qdrant_api_key_encrypted = ""
        row.backend_options = {}
        row.backend_secrets_encrypted = ""
        if user_id is not None:
            if created or row.created_by_id is None:
                row.created_by_id = user_id
            row.modified_by_id = user_id
        row.save()
        result = self._serialize(row)
        result["warning"] = None
        result["backends"] = self.backends_payload()
        self._audit_config_write(user_id, "update", [])
        return result


__all__ = ["MemorySettingsService"]
