"""Generic MCP Tool Group for standard CRUD entities."""
import inspect
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from application.base import NotFoundError
from auth_tenancy.context import AuthContext
from mcp_server.tools.base import BaseToolGroup, ToolResult, require_uuid


# ---------------------------------------------------------------------------
# inputSchema introspection (#345 Finding 1)
#
# The create/update schemas used to advertise only ``workspace_id`` / ``id``
# with ``additionalProperties: true``, while the wrapped service required up
# to three more fields — a client that trusted the schema got a 400. Deriving
# the schema from the service signature keeps it honest by construction: it
# cannot drift when a service adds, renames or defaults a parameter.
# ---------------------------------------------------------------------------

_JSON_TYPE_BY_NAME: Dict[str, str] = {
    "str": "string",
    "uuid": "string",
    "datetime": "string",
    "date": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "sequence": "array",
    "dict": "object",
    "mapping": "object",
}

_OPTIONAL_RE = re.compile(r"^(?:typing\.)?Optional\[(.+)\]$")

# Enumerated free-form fields whose accepted values live in the model's
# TextChoices — resolved from the model so the schema cannot drift. ``status``
# is deliberately absent from the *update* schema (it is workflow-managed,
# see ``_fields_from_signature``'s update-name guard and ``_handle_update``),
# but it IS advertised for entities below on `{prefix}.create` (#374): the
# service accepts an initial ``status`` there, so the enum values are useful
# to document up front instead of leaving clients to guess.
_ENUM_FIELDS_BY_PREFIX: Dict[str, Dict[str, str]] = {
    "adr": {"status": "Status"},
    "risk": {
        "probability": "Probability",
        "impact": "Impact",
        "category": "Category",
    },
    "issue": {"severity": "Severity", "category": "Category"},
}


def _annotation_text(annotation: Any) -> str:
    """Return an annotation as source-like text.

    All wrapped services use ``from __future__ import annotations``, so
    ``inspect.signature`` hands back strings; real objects are still handled
    for services that do not.
    """
    if annotation is inspect.Parameter.empty:
        return ""
    if isinstance(annotation, str):
        return annotation
    return getattr(annotation, "__name__", None) or str(annotation)


def _json_type_from_annotation(annotation: Any) -> Optional[str]:
    """Map a parameter annotation to a JSON Schema type, or None if unknown."""
    text = _annotation_text(annotation).strip()
    if not text:
        return None
    match = _OPTIONAL_RE.match(text)
    if match:
        text = match.group(1).strip()
    # "str | None" / "UUID | str"
    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip() not in ("None", "NoneType")]
        if len(parts) != 1:
            return None
        text = parts[0]
    base = text.split("[", 1)[0].strip().rsplit(".", 1)[-1]
    return _JSON_TYPE_BY_NAME.get(base.lower())


def _enum_values(prefix: str, field: str) -> Optional[List[str]]:
    """Return the model's TextChoices values for a known enum field."""
    choices_attr = _ENUM_FIELDS_BY_PREFIX.get(prefix, {}).get(field)
    if choices_attr is None:
        return None
    try:
        # #374: "Deleted" is a soft-delete marker (REQ-006) that
        # AdrValidator.VALID_STATUSES deliberately excludes from what a
        # client may set via create/transition — the advertised enum must
        # match what the service actually accepts, not the full model
        # TextChoices.
        if prefix == "adr" and field == "status":
            from application.adr_service import AdrValidator

            return sorted(AdrValidator.VALID_STATUSES)

        from application import models as application_models

        model = getattr(application_models, prefix.capitalize())
        return list(getattr(model, choices_attr).values)
    except Exception:  # pragma: no cover - defensive: never break tools/list
        return None


def _fields_from_signature(
    method: Callable[..., Any], *, prefix: str, skip: frozenset[str]
) -> Tuple[Dict[str, Any], List[str], bool]:
    """Derive (properties, required, accepts_extra) from a service method.

    ``ctx``/``self`` are injected by the tool group, never sent by the client.
    A parameter without a default is required; a scalar default is published
    as the JSON Schema ``default`` so callers can see e.g. that
    ``issue.create``'s ``severity`` falls back to "medium".
    """
    properties: Dict[str, Any] = {}
    required: List[str] = []
    accepts_extra = False

    for name, param in inspect.signature(method).parameters.items():
        if name in ("self", "ctx") or name in skip:
            continue
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            accepts_extra = True
            continue
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        # `status` is workflow-managed and rejected by `_handle_update`;
        # never advertise it as an updatable field.
        if name == "status" and "update" in getattr(method, "__name__", ""):
            continue

        field: Dict[str, Any] = {}
        json_type = _json_type_from_annotation(param.annotation)
        if json_type is not None:
            field["type"] = json_type

        enum_values = _enum_values(prefix, name)
        if enum_values:
            field["enum"] = enum_values

        is_required = param.default is inspect.Parameter.empty
        if is_required:
            required.append(name)
            field["description"] = f"Required. '{name}' as validated by the {prefix} service."
        else:
            field["description"] = f"Optional. '{name}' as accepted by the {prefix} service."
            if isinstance(param.default, (str, int, float, bool)):
                field["default"] = param.default

        properties[name] = field

    return properties, required, accepts_extra


def _resolve_method(service: Any, prefix: str, action: str) -> Callable[..., Any]:
    """Resolve a service's create/update/delete method.

    Services expose either an entity-specific method (AdrService.create_adr,
    IssueService.delete_issue, ...) or a generic one (GlossaryService.create).
    """
    method = getattr(service, f"{action}_{prefix}", None) or getattr(service, action, None)
    if method is None:
        raise AttributeError(
            f"{service.__class__.__name__} exposes neither '{action}_{prefix}' nor '{action}'"
        )
    return method


def _resolve_id_param(method: Callable[..., Any]) -> str:
    """Find the required, non-``ctx`` parameter an update/delete method
    expects for the entity ID (e.g. ``adr_id``, ``term_id``)."""
    for name, param in inspect.signature(method).parameters.items():
        if name in ("self", "ctx") or param.default is not inspect.Parameter.empty:
            continue
        return name
    raise TypeError(f"Could not resolve ID parameter for {method!r}")


def _resolve_list_method(service: Any, prefix: str) -> Callable[..., Any]:
    """Resolve a service's list method for ``{prefix}.query``.

    Services expose the entity list under differing names: plural
    entity-specific (``list_adrs``, ``list_risks``, ``list_issues``),
    workspace-scoped generic (``GlossaryService.list_by_workspace``), or a
    bare generic ``list``. Tried in that order.
    """
    for candidate in (f"list_{prefix}s", f"list_{prefix}", "list_by_workspace", "list"):
        method = getattr(service, candidate, None)
        if method is not None:
            return method
    raise AttributeError(
        f"{service.__class__.__name__} exposes no recognizable list method for prefix '{prefix}'"
    )


class GenericCrudToolGroup(BaseToolGroup):
    """Generic tool group for standard CRUD operations."""

    def __init__(self, prefix: str, service_class: Any, item_type: str | None = None):
        self.prefix = prefix
        self._service = service_class()
        # Workflow item_type string (e.g. "Adr", "GlossaryTerm") passed to
        # workflow.services.outdate()/reactivate() — PascalCase, distinct
        # from the lowercase `prefix` used for tool-name routing. Defaults
        # to prefix.capitalize() (works for adr/risk/issue); entities whose
        # workflow item_type doesn't match their prefix 1:1 (e.g. glossary
        # -> "GlossaryTerm") must pass it explicitly at registration.
        self._item_type = item_type or prefix.capitalize()
        # Resolved once so the handlers below don't need per-entity branching.
        self._read_method = _resolve_method(self._service, prefix, "get")
        self._create_method = _resolve_method(self._service, prefix, "create")
        self._update_method = _resolve_method(self._service, prefix, "update")
        self._delete_method = _resolve_method(self._service, prefix, "delete")
        self._list_method = _resolve_list_method(self._service, prefix)
        self._read_id_param = _resolve_id_param(self._read_method)
        self._update_id_param = _resolve_id_param(self._update_method)
        self._delete_id_param = _resolve_id_param(self._delete_method)
        # Dynamically define the TOOL_MAP for this instance
        self._TOOL_MAP = {
            f"{prefix}.read": "_handle_read",
            f"{prefix}.create": "_handle_create",
            f"{prefix}.update": "_handle_update",
            f"{prefix}.delete": "_handle_delete",
            f"{prefix}.outdate": "_handle_outdate",
            f"{prefix}.reactivate": "_handle_reactivate",
            f"{prefix}.query": "_handle_query",
        }
        # #345 Finding 1: create/update schemas are derived from the wrapped
        # service signature so `tools/list` states the real contract.
        create_props, create_required, create_extra = _fields_from_signature(
            self._create_method, prefix=prefix, skip=frozenset({"workspace_id"})
        )
        update_props, update_required, update_extra = _fields_from_signature(
            self._update_method, prefix=prefix, skip=frozenset({self._update_id_param})
        )
        # `workspace_id` / `id` are consumed by the handlers themselves, so
        # they are declared here rather than taken from the signature.
        create_props = {
            "workspace_id": {
                "type": "string",
                "description": "Required. UUID of the target workspace.",
            },
            **create_props,
        }
        create_required = ["workspace_id"] + create_required
        update_props = {
            "id": {
                "type": "string",
                "description": f"Required. UUID of the {prefix} entity.",
            },
            **update_props,
        }
        update_required = ["id"] + update_required

        # Instance-level JSON schemas (prefix is only known at construction).
        self._TOOL_SCHEMAS = [
            {
                "name": f"{prefix}.read",
                "description": f"Fetch a single {prefix} entity by ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": f"UUID of the {prefix} entity."},
                    },
                    "required": ["id"],
                },
            },
            {
                "name": f"{prefix}.create",
                "description": (
                    f"Create a new {prefix} entity (write). Fields are passed "
                    "flat at the top level of `params` — this tool group does "
                    "NOT take a nested `data` object."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": create_props,
                    "required": create_required,
                    "additionalProperties": create_extra,
                },
            },
            {
                "name": f"{prefix}.update",
                "description": (
                    f"Update a {prefix} entity (write). Only the fields you "
                    "send are changed; they are passed flat at the top level "
                    "of `params` — this tool group does NOT take a nested "
                    f"`data` object. `status` is workflow-managed: use "
                    f"{prefix}.outdate / {prefix}.reactivate or the REST "
                    "workflow transitions endpoint."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": update_props,
                    "required": update_required,
                    "additionalProperties": update_extra,
                },
            },
            {
                "name": f"{prefix}.delete",
                "description": f"Delete a {prefix} entity (write).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": f"UUID of the {prefix} entity."},
                    },
                    "required": ["id"],
                },
            },
            {
                "name": f"{prefix}.outdate",
                "description": f"Soft-delete a {prefix} entity via the workflow engine's outdate escape hatch (write).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": f"UUID of the {prefix} entity."},
                        "reason": {"type": "string", "description": "Optional audit reason."},
                    },
                    "required": ["id"],
                },
            },
            {
                "name": f"{prefix}.reactivate",
                "description": f"Restore an outdated {prefix} entity to its previous state (write).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": f"UUID of the {prefix} entity."},
                    },
                    "required": ["id"],
                },
            },
            {
                "name": f"{prefix}.query",
                "description": f"List {prefix} entities in a workspace (read-only).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace_id": {
                            "type": "string",
                            "description": "UUID of the target workspace.",
                        },
                        "include_outdated": {
                            "type": "boolean",
                            "description": "If true, include outdated (soft-deleted) entities. Defaults to false.",
                        },
                    },
                    "required": ["workspace_id"],
                },
            },
        ]
    
    @staticmethod
    def _jsonify(value: Any) -> Any:
        """Coerce a single value into a JSON-serializable form.

        UUID/datetime/date/Decimal are not JSON-serializable by ``json.dumps``
        and would crash the MCP response encoder (e.g. ``Issue.due_date``).
        """
        if isinstance(value, uuid.UUID):
            return str(value)
        # datetime is a subclass of date; check it first for full ISO precision.
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        return value

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        """Convert object to dict dynamically."""
        if hasattr(obj, "__dict__"):
            data = {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
            # Coerce non-JSON-serializable values (UUID/datetime/date/Decimal).
            return {k: self._jsonify(v) for k, v in data.items()}
        return {"id": str(getattr(obj, "id", ""))}

    def _handle_read(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        try:
            obj = self._read_method(ctx=auth_context, **{self._read_id_param: obj_id})
            return ToolResult.ok({"data": self._to_dict(obj)})
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))

    def _handle_create(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        kwargs = {k: v for k, v in params.items() if k != "workspace_id"}
        try:
            obj = self._create_method(ctx=auth_context, workspace_id=workspace_id, **kwargs)
            return ToolResult.ok({"data": self._to_dict(obj)})
        except TypeError as exc:
            # #268: a required field missing from `params` (e.g. `description`
            # for Adr, `probability`/`impact` for Risk) surfaces here as a
            # Python TypeError from the service call's missing positional
            # argument. Left uncaught, that used to fall through to the bare
            # `except Exception` below as an opaque INTERNAL_ERROR (HTTP 500)
            # instead of an actionable client-facing validation error —
            # mirrors the TypeError handling in `_handle_update` (#83 Bug 1).
            return ToolResult.error(
                "VALIDATION_ERROR", f"Missing or invalid field for {self.prefix}.create: {exc}"
            )
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_update(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        kwargs = {k: v for k, v in params.items() if k != "id"}
        # #83 Bug 2: `status` is a workflow-managed field for every entity
        # this generic group serves (Adr, Risk, Issue, GlossaryTerm, ...) —
        # it can only move through `{prefix}.outdate` / `{prefix}.reactivate`
        # (soft-delete/restore) or the REST workflow `transitions/` endpoint
        # (WorkflowEngine-gated), mirroring the REST PATCH rejection in
        # WorkflowTransitionsMixin._validate_patch_payload (QA-123). Unlike the
        # REST guard — which since #263 tolerates an unchanged status echo
        # because the UI resends the whole form — this one rejects `status`
        # outright: MCP callers pass explicit kwargs, so there is no
        # whole-object echo to accommodate here. Forwarding
        # it here used to hit the update method's missing parameter and
        # surface as an opaque "INTERNAL_ERROR: ...got an unexpected keyword
        # argument 'status'" instead of an actionable message.
        if "status" in kwargs:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"'status' cannot be changed via {self.prefix}.update; use "
                f"{self.prefix}.outdate / {self.prefix}.reactivate for "
                "lifecycle changes, or the REST workflow transitions "
                "endpoint (POST /api/v1/<entity>/{id}/transitions/) for a "
                "state-machine-gated status change.",
            )
        try:
            obj = self._update_method(ctx=auth_context, **{self._update_id_param: obj_id}, **kwargs)
            return ToolResult.ok({"data": self._to_dict(obj)})
        except TypeError as exc:
            # Any other unexpected/misnamed field: surface a clear, actionable
            # message instead of letting it fall through to a bare
            # INTERNAL_ERROR (#83 Bug 1 root cause pattern).
            return ToolResult.error(
                "VALIDATION_ERROR", f"Invalid field for {self.prefix}.update: {exc}"
            )
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_delete(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        try:
            self._delete_method(ctx=auth_context, **{self._delete_id_param: obj_id})
            return ToolResult.ok({"status": "deleted"})
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _resolve_workspace_id(self, *, obj_id: uuid.UUID, auth_context: AuthContext) -> uuid.UUID:
        """Fetch the entity and read its ``workspace_id`` — the same
        resolution the entity services use internally before calling
        ``workflow.services.outdate()`` (e.g. ``AdrService.delete_adr``).
        """
        obj = self._read_method(ctx=auth_context, **{self._read_id_param: obj_id})
        return obj.workspace_id

    def _handle_outdate(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        reason = params.get("reason", "")
        from workflow.services import outdate

        try:
            workspace_id = self._resolve_workspace_id(obj_id=obj_id, auth_context=auth_context)
            outdate(
                item_id=obj_id,
                item_type=self._item_type,
                workspace_id=workspace_id,
                ctx=auth_context,
                reason=reason,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        return ToolResult.ok({"id": str(obj_id), "status": "outdated"})

    def _handle_reactivate(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        obj_id = require_uuid(params, "id")
        from workflow.services import reactivate

        try:
            workspace_id = self._resolve_workspace_id(obj_id=obj_id, auth_context=auth_context)
            result = reactivate(
                item_id=obj_id,
                item_type=self._item_type,
                workspace_id=workspace_id,
                ctx=auth_context,
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValueError as exc:
            return ToolResult.error("INVALID_STATE", str(exc))
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
        return ToolResult.ok({"id": str(obj_id), "status": result.new_state})

    def _handle_query(self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        include_outdated = params.get("include_outdated", False)
        try:
            results = self._list_method(
                workspace_id=workspace_id, ctx=auth_context, include_deleted=include_outdated
            )
            return ToolResult.ok({"items": [self._to_dict(r) for r in results]})
        except Exception as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))
