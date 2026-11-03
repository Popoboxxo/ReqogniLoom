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

#: Real columns on ``SystemMemorySettings``. Per-backend values are NOT
#: columns since Plan A T-A0b-6; they live in the maps below and are exposed
#: through the flat compatibility fields in ``_DERIVED_OPTION_FIELDS``.
_OVERRIDABLE_FIELDS = (
    "embedding_provider",
    "embedding_model_name",
    "ollama_base_url",
    "embedding_timeout",
    "memory_backend",
    "memory_write_rate_limit_per_hour",
)

#: Flat REST compatibility field -> (backend, ``backend_options`` field).
#: Derived on read, mapped on write; the maps are the only store (T-A0b-6).
_DERIVED_OPTION_FIELDS: dict[str, tuple[str, str]] = {
    "honcho_base_url": ("honcho", "base_url"),
    "qdrant_base_url": ("qdrant", "base_url"),
    "qdrant_collection_prefix": ("qdrant", "collection_prefix"),
    "qdrant_distance": ("qdrant", "distance"),
    "qdrant_timeout": ("qdrant", "timeout"),
    "qdrant_hnsw_m": ("qdrant", "hnsw_m"),
    "qdrant_hnsw_ef_construct": ("qdrant", "hnsw_ef_construct"),
    "qdrant_prefer_grpc": ("qdrant", "prefer_grpc"),
}

#: Flat write-only secret field -> (backend, ``backend_secrets`` field).
_DERIVED_SECRET_FIELDS: dict[str, tuple[str, str]] = {
    "honcho_api_key": ("honcho", "api_key"),
    "qdrant_api_key": ("qdrant", "api_key"),
}

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
    def _row_maps(row: SystemMemorySettings | None) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(backend_options, backend_secrets)`` for a read surface.

        ``backend_secrets`` decrypts the blob and raises ``InvalidToken`` once
        ``FIELD_ENCRYPTION_KEY`` was rotated without re-encrypting stored data.
        A read surface must never 500 over that (F8), so the secret map degrades
        to ``{}`` here -- it reports "no key set", which is all an unreadable
        ciphertext can honestly say. Write paths keep using the strict property.
        """
        if row is None:
            return {}, {}
        options = row.backend_options or {}
        try:
            secrets = row.backend_secrets or {}
        except Exception:  # noqa: BLE001 - see docstring; a GET must never 500.
            logger.warning(
                "MemorySettingsService: backend secrets are unreadable (rotated key?)",
                exc_info=True,
            )
            secrets = {}
        return options, secrets

    @staticmethod
    def _serialize(row: SystemMemorySettings | None) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field in _OVERRIDABLE_FIELDS:
            value = getattr(row, field, None) if row is not None else None
            data[field] = value
            data[f"{field}_is_override"] = value is not None

        options, secrets = MemorySettingsService._row_maps(row)

        # Plan A T-A0b-6: the flat per-backend fields stay in the REST contract
        # as derived compatibility fields. Their value comes from
        # ``backend_options``; ``_with_env_fallback`` fills the env value when
        # the map holds no override.
        for field, (backend, option) in _DERIVED_OPTION_FIELDS.items():
            backend_options = options.get(backend) or {}
            data[field] = backend_options.get(option)
            data[f"{field}_is_override"] = option in backend_options

        for field, (backend, secret) in _DERIVED_SECRET_FIELDS.items():
            data[f"{field}_is_set"] = bool((secrets.get(backend) or {}).get(secret))
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
        options, secrets = self._row_maps(row)
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
        """Merge the maps into the row (the sole store since T-A0b-6)."""
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

    @staticmethod
    def _mirror_flat_fields(row: SystemMemorySettings, data: dict[str, Any]) -> None:
        """Map the flat compatibility fields onto the backend maps.

        The flat fields are derived on read (``_serialize``); on write they
        still have to land in ``backend_options``/``backend_secrets`` because
        those maps are the only store since Plan A T-A0b-6.
        """
        options = dict(row.backend_options or {})
        changed = False
        for field, (backend, option) in _DERIVED_OPTION_FIELDS.items():
            if field not in data:
                continue
            value = data[field]
            if field in _BLANKABLE_TEXT_FIELDS and value == "":
                value = None
            key = _settings_key(backend)
            merged = dict(options.get(key) or {})
            if value is None:
                merged.pop(option, None)
            else:
                merged[option] = value
            if merged:
                options[key] = merged
            else:
                options.pop(key, None)
            changed = True
        if changed:
            row.backend_options = options

        # Only touch (and therefore decrypt) the secret blob when the caller
        # actually sent a secret; an unrelated PUT must work even with a
        # rotated FIELD_ENCRYPTION_KEY.
        secret_updates = {
            field: data[field]
            for field in _DERIVED_SECRET_FIELDS
            if data.get(field)
        }
        if secret_updates:
            secrets = dict(row.backend_secrets)
            for field, value in secret_updates.items():
                backend, secret = _DERIVED_SECRET_FIELDS[field]
                key = _settings_key(backend)
                merged = dict(secrets.get(key) or {})
                merged[secret] = value
                secrets[key] = merged
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
