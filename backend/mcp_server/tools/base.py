"""
MCP Tool Groups — shared base class and utilities.

leaf_id : COMP-MC-003..006
req_id  : REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail),
          REQ-L2-MC-011 (structured error response)

Provides:
- BaseToolGroup: common execute_tool dispatcher and audit helper.
- Parameter validation helpers.
"""
from __future__ import annotations

import logging
from abc import ABC
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from audit.services import mcp_audit_handoff
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from persistence.tenancy import TenantContextNotSetError
from workflow import state_reader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared parameter validation
# ---------------------------------------------------------------------------


class ParameterError(ValueError):
    """Raised when required parameters are missing or invalid."""


def require_param(params: dict[str, Any], name: str) -> Any:
    """Return params[name] or raise ParameterError."""
    val = params.get(name)
    if val is None or (isinstance(val, str) and not val.strip()):
        raise ParameterError(f"Required parameter '{name}' is missing or empty.")
    return val


def optional_uuid(params: dict[str, Any], name: str) -> UUID | None:
    """Return UUID from params[name] or None."""
    val = params.get(name)
    if val is None:
        return None
    try:
        return UUID(str(val))
    except (ValueError, AttributeError):
        raise ParameterError(f"Parameter '{name}' is not a valid UUID: '{val}'")


def require_uuid(params: dict[str, Any], name: str) -> UUID:
    """Return UUID from params[name] or raise ParameterError."""
    val = params.get(name)
    if val is None:
        raise ParameterError(f"Required parameter '{name}' is missing.")
    try:
        return UUID(str(val))
    except (ValueError, AttributeError):
        raise ParameterError(f"Parameter '{name}' is not a valid UUID: '{val}'")


def parse_pagination(
    params: dict[str, Any],
    *,
    default_limit: int = 50,
    max_limit: int = 500,
) -> tuple[int, int]:
    """Return ``(limit, offset)`` for a ``*.query`` tool (C3 / #1668).

    A ``*.query`` used to load the whole workspace; ``limit``/``offset`` bound
    it. An over-large ``limit`` is capped (not rejected), matching the REST
    paginator's documented behaviour; a non-integer or a negative offset is a
    caller error.
    """
    raw_limit = params.get("limit", default_limit)
    raw_offset = params.get("offset", 0)
    try:
        limit = int(raw_limit)
        offset = int(raw_offset)
    except (TypeError, ValueError):
        raise ParameterError("'limit' and 'offset' must be integers.") from None
    if limit < 1:
        raise ParameterError("'limit' must be >= 1.")
    if limit > max_limit:
        limit = max_limit
    if offset < 0:
        raise ParameterError("'offset' must be >= 0.")
    return limit, offset


# ---------------------------------------------------------------------------
# Transport-boundary value conversion
# ---------------------------------------------------------------------------


def transport_safe(value: Any) -> Any:
    """Coerce an arbitrary service value into a JSON-serialisable primitive.

    The single transport-boundary conversion of the tool layer. A payload can
    carry values ``json.dumps`` cannot encode (a row's ``modified_at``
    datetime) or — in tool-contract tests that patch a service with a
    ``MagicMock`` — anything at all; either would turn a valid tool result into
    an opaque ``INTERNAL_ERROR``/HTTP 500. ``None``/``str``/``int``/``float``/
    ``bool`` pass through, ``dict``/``list``/``tuple``/``set`` recurse (dict
    keys are stringified), a ``UUID`` becomes its string form and a
    date/datetime its ISO string. Anything else — including a ``MagicMock``
    whose ``isoformat()`` is itself a mock — is rendered through ``str``.

    A non-string ``isoformat()`` result is never trusted, so the mock caveat is
    handled once for every group instead of per call site.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): transport_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [transport_safe(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    rendered = getattr(value, "isoformat", None)
    if callable(rendered):
        candidate = rendered()
        if isinstance(candidate, str):
            return candidate
    return str(value)


# ---------------------------------------------------------------------------
# Soft-delete audit reason (P1.10 / finding M-14)
# ---------------------------------------------------------------------------
#
# ``{prefix}.outdate`` / ``{prefix}.delete`` tools are soft-deletes, and the
# workflow engine records a reason on the transition. The parameter was spelled
# ``reason`` on some tools and ``change_reason`` on others (every REST
# ``DELETE`` uses ``change_reason``), so a client had to know which transport it
# was talking to. ``change_reason`` is now canonical everywhere and ``reason``
# stays a deprecated alias: supported through 1.11.0 (inclusive); removal no
# earlier than 1.12.0.


#: Canonical ``inputSchema`` key for a soft-delete audit reason (P1.10).
CANONICAL_SOFT_DELETE_REASON_KEY = "change_reason"

#: Deprecated alias kept through the 1.11.0 line (P1.10).
DEPRECATED_SOFT_DELETE_REASON_KEY = "reason"


def soft_delete_reason(params: Mapping[str, Any]) -> str:
    """Return the audit reason for a soft-delete call.

    Canonical key is ``change_reason``; ``reason`` is a deprecated alias,
    supported through 1.11.0 (inclusive) with removal no earlier than 1.12.0.
    When both are supplied the canonical
    value wins (the alias is ignored) — never merged, never an error, so an old
    client keeps working unchanged. A blank canonical value counts as "not
    supplied" and falls through to the alias, which is what a client that
    serialises an unset field as ``""`` sends.

    The resolved string is trimmed; a missing/None value becomes ``""``.
    """
    canonical = params.get(CANONICAL_SOFT_DELETE_REASON_KEY)
    if canonical is not None and str(canonical).strip():
        return str(canonical).strip()
    alias = params.get(DEPRECATED_SOFT_DELETE_REASON_KEY)
    if alias is None:
        return ""
    return str(alias).strip()


def soft_delete_reason_properties() -> dict[str, dict[str, Any]]:
    """Return the ``inputSchema.properties`` fragment for a soft-delete reason.

    A fresh dict per call so a group that mutates its schema cannot leak into a
    sibling: two tools advertising the same two properties must stay
    independent objects. Both are optional — a preset, not the schema, decides
    whether the reason is mandatory.
    """
    return {
        CANONICAL_SOFT_DELETE_REASON_KEY: {
            "type": "string",
            "description": (
                "Reason for the soft-delete, recorded on the audit trail. May "
                "be mandatory when the workspace preset requires a "
                "change_reason for writes."
            ),
        },
        DEPRECATED_SOFT_DELETE_REASON_KEY: {
            "type": "string",
            "deprecated": True,
            "description": (
                "Deprecated alias of 'change_reason': supported through 1.11.0 "
                "(inclusive); removal no earlier than 1.12.0. Ignored when "
                "'change_reason' is supplied."
            ),
        },
    }


# ---------------------------------------------------------------------------
# CRUD verb vocabulary + hidden aliases (R2A-003)
# ---------------------------------------------------------------------------
#
# Five entity prefixes are served by ``GenericCrudToolGroup`` and publish
# ``.read``/``.query``, while the hand-written groups publish ``.get``/``.list``
# for the same two operations. The catalogue therefore carries two verb
# families for "fetch one" and "list many".
#
# We do NOT rename published tools here: ``workspace_scope._TOOL_TARGETS`` and
# the #1376 shadow ratchet key off the published names, so a rename would be a
# cross-cutting change (and would break the "one prefix, one fetch/list verb"
# invariant only if done partially). Instead every prefix keeps exactly one
# published verb per operation, and the *alternative* verb spellings are
# declared as hidden aliases with ``deprecated`` + ``replacedBy`` metadata.
# Aliases are metadata only: they add no tools, so ``tools/list`` stays at 313
# (``docs/agent-templates/tool-manifest.json``'s ``tool_count``), and they are
# never routed (see :meth:`ToolRegistry.hidden_tool_aliases`).
#
# Canonical verbs document the target vocabulary for new groups. A new group
# must use them; existing prefixes are ratcheted by
# ``test_tool_naming_and_descriptions.py``.
CANONICAL_FETCH_VERB = "get"
CANONICAL_LIST_VERB = "list"

#: The two accepted spellings of each operation, used by the lint ratchet to
#: count "one fetch / one list verb per prefix" independently of which family
#: a legacy group publishes.
FETCH_VERBS: frozenset[str] = frozenset({"get", "read"})
LIST_VERBS: frozenset[str] = frozenset({"list", "query"})


def tool_verb(tool_name: str) -> str:
    """Return the verb segment of *tool_name* (immediately after the prefix).

    Nested tools such as ``requirement.acceptance_criteria.get`` are not CRUD
    verbs of the ``requirement`` prefix — their second segment is the nested
    namespace (``acceptance_criteria``), which is not in :data:`FETCH_VERBS`.
    Counting the final segment instead would falsely report a second fetch
    verb on that prefix.
    """
    parts = tool_name.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def verb_operation(tool_name: str) -> str | None:
    """Classify *tool_name* as ``"fetch"``/``"list"`` or ``None``."""
    verb = tool_verb(tool_name)
    if verb in FETCH_VERBS:
        return "fetch"
    if verb in LIST_VERBS:
        return "list"
    return None


#: Canonical ``required`` head of every workspace-scoped ``*.query`` tool
#: (issue #1615). ``requirement.query`` used to advertise ``workspace_id`` as
#: optional while its siblings required it, so a client could not tell from
#: ``tools/list`` which calls are guaranteed to be workspace-bound. Building
#: the list through :func:`workspace_query_required` makes that requirement a
#: single source of truth instead of one hand-maintained literal per tool.
WORKSPACE_QUERY_REQUIRED: tuple[str, ...] = ("workspace_id",)


def workspace_query_required(*extra: str) -> list[str]:
    """Return the ``required`` list for a workspace-scoped ``*.query`` tool.

    Every ``*.query`` tool whose catalogue is scoped to exactly one workspace
    must require ``workspace_id``; handlers already reject a call without it
    (e.g. ``requirement.query``), so a schema that omits it is the kind of
    contract drift issue #1615 reported. ``extra`` appends additional required
    parameters for tools that need more than the workspace (``quality.query``).

    The runtime twin of this constraint is
    ``mcp_server/tests/test_query_tool_workspace_required.py``, which checks
    the *advertised* catalogue rather than trusting each tool to use this
    helper — a new tool cannot silently opt out.
    """
    return [*WORKSPACE_QUERY_REQUIRED, *extra]


def reject_unknown_params(
    params: dict[str, Any], allowed: list[str], tool_name: str
) -> None:
    """Raise ParameterError if *params* contains a key not in *allowed*.

    Issue #459 (finding 1): opt-in, per-tool guard against unrecognised
    parameters that would otherwise be silently ignored (e.g. a client
    sending ``test_case_id`` instead of the documented ``test_case_ids``
    array — the run is created but the typo'd parameter has no effect).

    Deliberately NOT wired into ``BaseToolGroup.execute_tool`` as a global
    dispatcher-level check: across 40+ tools, a blanket "reject unknown
    params" rule risks breaking existing clients that rely on extra keys
    being tolerated/ignored, without a coordinated audit of every tool's
    ``inputSchema``. Call this explicitly from handlers that want strict
    validation instead.
    """
    unknown = sorted(k for k in params if k not in allowed)
    if unknown:
        raise ParameterError(
            f"Unknown parameter(s) for tool '{tool_name}': {', '.join(unknown)}. "
            f"Allowed parameters: {', '.join(sorted(allowed))}."
        )


# ---------------------------------------------------------------------------
# Per-parameter capability tier (governance acts behind a mixed tool)
# ---------------------------------------------------------------------------


def require_admin_tier(
    auth_context: AuthContext, *, tool_name: str, level: str
) -> None:
    """Raise PermissionDeniedError unless the key carries the ADMIN tier.

    The registry's tier map (:meth:`ToolRegistry._required_scope_operation`) is
    keyed by *tool name*, which is exactly right for a split like
    ``preference.set`` / ``preference.set_default`` — but cannot express a tool
    whose governance-ness depends on a **parameter**. ``tree_display_config.set``
    and ``create_form_definition.set``/``.import`` write three levels behind one
    name, and ``scope="user"`` must stay self-service for an AUTHOR key.

    So the tool stays at ``Operation.WRITE`` in the registry (it must remain
    advertised to AUTHOR keys) and the handler calls this helper for the
    ``workspace``/``global`` levels. The check is the same single implementation
    every transport uses: ``scope_denial_reason`` above the RBAC matrix, so a
    privileged *owner* cannot lend the tier away (the R6 hole).

    A bearer/session context carries no ``scope``; ``scope_denial_reason``
    returns ``None`` for it, leaving the service-level RBAC check as the only
    gate — unchanged human behaviour.

    Args:
        auth_context: The caller's context (``scope`` decides the tier).
        tool_name: Tool being executed, for the error message.
        level: The governance level being written ("workspace"/"global").

    Raises:
        PermissionDeniedError: the key's scope is below the ADMIN tier.
    """
    # Imported lazily: ``auth_tenancy.services`` pulls in item-permission code
    # that imports application services, so a module-level import here would
    # run at MCP package-init time (same note as the registry's own lazy gate).
    from auth_tenancy.services.authorization import (
        Operation,
        scope_denial_reason,
    )
    from persistence.errors import PermissionDeniedError

    reason = scope_denial_reason(auth_context.scope, Operation.WORKSPACE_CONFIG)
    if reason:
        raise PermissionDeniedError(
            f"Permission denied: the {level}-wide default written by "
            f"'{tool_name}' is a governance operation, which requires "
            f"scope='admin'. {reason}"
        )


# ---------------------------------------------------------------------------
# Workflow-engine status seam (Datenmodell-Konsolidierung Phase 1)
# ---------------------------------------------------------------------------


def resolve_engine_status(
    item_type: str,
    item_id: Any,
    fallback: str | None = None,
    *,
    status_map: dict[str, str] | None = None,
) -> str:
    """Resolve an entity's ``status`` wire value from the workflow engine.

    Every MCP payload builder that used to read an entity's own (still
    present, Phase 0 mirror) ``status`` column now goes through this seam
    instead -- ``WorkflowItemState.current_state`` is the single source of
    truth (D-1); the wire key name and value vocabulary are unchanged.

    Pass a pre-batched *status_map* (:func:`resolve_status_map`) for
    list-shaped responses so a page of N items costs one engine query
    instead of N -- mirrors
    ``rest_api.mixins.workflow_state.WorkflowStateSerializerMixin``'s
    batching. Omit it to resolve a single item inline via
    ``workflow.state_reader.current_state``.

    Falls back to *fallback* when given (mainly for tests exercising the
    fallback path with a literal), else to *item_type*'s preset initial state
    (``workflow.state_reader.initial_state``) when the engine has no
    ``WorkflowItemState`` row for the item (e.g. Goal/MainGoal, which have no
    state backfill, or any item created in a definition-less workspace), so
    an untracked item never silently regresses to an empty string. Also
    falls back when no ``TenantContext`` is active: production dispatch
    (``ToolRegistry.dispatch_request``) always activates it before a handler
    runs, so this only matters for tests that call ``execute_tool`` directly
    against a mocked service with no live tenant/DB.

    Datenmodell-Konsolidierung Task 12: the entity's own ``status`` column is
    dropped, so production callers no longer have a column value to pass as
    *fallback* -- they call this with *fallback* omitted and rely on the
    preset-initial-state default (documented, reviewed data-loss tradeoff,
    see Task 12 report Finding 2).

    Datenmodell-Konsolidierung Phase 4 (Decision D-3): soft-delete moved to
    ``Artifact.lifecycle_status``, off the workflow state. The ``state_reader``
    seam re-joins the two axes for the wire, so a soft-deleted item still
    resolves to ``"outdated"`` here -- the only signal an MCP client has that it
    is deleted. See ``workflow.state_reader.current_states``.
    """
    if status_map is not None:
        engine_state = status_map.get(str(item_id))
    else:
        try:
            engine_state = state_reader.current_state(item_type, item_id)
        except TenantContextNotSetError:
            engine_state = None
    if engine_state is not None:
        return engine_state
    return fallback or state_reader.initial_state(item_type)


def resolve_status_map(item_type: str, item_ids: Iterable[Any]) -> dict[str, str]:
    """Batch-resolve wire ``status`` values for many items in one query.

    Thin, defensive wrapper over ``workflow.state_reader.current_states`` for
    list-shaped MCP responses -- pass the result as :func:`resolve_engine_status`'s
    *status_map* so a page of N items costs one engine query, not N. Returns
    an empty mapping (every item then falls back to its own column) when no
    ``TenantContext`` is active, instead of propagating
    ``TenantContextNotSetError`` -- see :func:`resolve_engine_status` for why
    that is safe.
    """
    try:
        return state_reader.current_states(item_type, item_ids)
    except TenantContextNotSetError:
        return {}


# ---------------------------------------------------------------------------
# Attribute-definition enforcement (ledger gap #1 / issue #881)
# ---------------------------------------------------------------------------


def validate_artifact_write(
    auth_context: AuthContext,
    item_type: str | None,
    workspace_id: Any,
    changed_fields: dict[str, Any],
    existing: dict[str, Any] | None,
) -> ToolResult | None:
    """Validate an MCP create/update payload against the resolved AttributeDefinition.

    Same central gate as ``rest_api.mixins.workflow_transitions.
    WorkflowTransitionsMixin._validate_attribute_definition`` (Task 11) — both
    delegate to ``ArtifactAttributeGateway.validate``, which is a thin
    behaviour-preserving forward to the identical
    ``AttributeDefinitionService.validate_artifact_fields``, just translated to
    a ``ToolResult`` error instead of a DRF ``Response``. Routing both seams
    through the gateway gives attribute validation exactly one entry point
    (Epic #934 / WS1 #935, ADR-004). Every MCP artifact-write tool group is
    expected to call this before delegating to its wrapped service, closing the
    gap where MCP writes bypassed the enforcement the REST ViewSets already had.

    Returns a ``ToolResult.error(...)`` on violation, ``None`` when clean —
    callers stay a single ``if``. Degrades to ``None`` (no-op) on the same
    "cannot decide" outcomes as the REST guard: no ``item_type``/workspace id
    (not an artifact write), no bootstrapped definition for this item type/
    preset, or a cross-tenant workspace id (the wrapped service call below
    answers that with its own error).

    Since WS2 review #936 the gate also resolves the Artifact-level
    ``owner``/``reporter`` actor references against the DB (the DB-free
    definition check cannot distinguish an unknown actor UUID from a valid
    one), so an unresolvable actor is rejected before the wrapped service
    creates the artifact.
    """
    if not item_type or workspace_id is None:
        return None
    from application.artifact_attribute_gateway import ArtifactAttributeGateway
    from application.attribute_definition_service import (
        AttributeDefinitionNotFound,
        AttributeSchemaError,
        FieldValidationError,
    )
    from presets.exceptions import CrossTenantWorkspaceError

    try:
        gateway = ArtifactAttributeGateway()
        gateway.validate(
            auth_context, item_type, workspace_id, changed_fields, existing
        )
        # WS2 review #936 (Major 2): the DB-free check above cannot tell an
        # unknown/foreign-tenant actor UUID from a valid one. Resolve the
        # Artifact-level actor references here so an unresolvable owner/reporter
        # is rejected before the wrapped service creates the artifact.
        gateway.validate_actor_system_fields(
            auth_context, item_type, workspace_id, changed_fields
        )
    except (AttributeDefinitionNotFound, CrossTenantWorkspaceError):
        return None
    except FieldValidationError as exc:
        message = "; ".join(
            f"{name}: {', '.join(messages)}"
            for name, messages in sorted(exc.errors.items())
        )
        return ToolResult.error("VALIDATION_ERROR", message)
    except AttributeSchemaError as exc:
        return ToolResult.error(
            "VALIDATION_ERROR",
            "The attribute definition for this workspace is malformed: "
            + "; ".join(exc.errors),
        )
    return None


def artifact_custom_fields(entity: Any) -> dict[str, Any]:
    """Return the ``custom_fields`` map from an entity's backing Artifact.

    Mirrors ``rest_api.views._artifact_custom_fields`` (REQ-L2-AS-037): the
    extended attributes live on ``Artifact.custom_fields`` and every
    artifact-backed entity reaches them through its OneToOne ``artifact``
    relation. Missing/NULL normalizes to ``{}`` so the MCP read shape stays
    stable, and non-dict values (e.g. mocked objects in unit tests) degrade to
    ``{}`` instead of leaking into the JSON response.
    """
    artifact = getattr(entity, "artifact", None)
    source = artifact if artifact is not None else entity
    custom_fields = getattr(source, "custom_fields", None)
    return custom_fields if isinstance(custom_fields, dict) else {}


# ---------------------------------------------------------------------------
# MCP Audit helper (REQ-L2-MC-012)
# ---------------------------------------------------------------------------


class McpAuditWriteError(RuntimeError):
    """Raised by :func:`write_mcp_audit` under ``fail_closed=True`` (#569).

    A distinct type (not a bare ``RuntimeError``) so a governance handler can
    map exactly this failure to an error result without catching unrelated
    runtime faults.
    """


def write_mcp_audit(
    ctx: AuthContext,
    operation: str,
    entity_type: str,
    entity_id: UUID,
    tool_name: str,
    api_key: str,
    details: dict[str, Any] | None = None,
    *,
    fail_closed: bool = False,
) -> None:
    """Write an MCP-specific audit log entry synchronously.

    REQ-L2-MC-012: Audit entry must be written before the response is sent.
    The api_key is passed as the raw secret to ``audit.services.log_write``;
    the SHA-256 hashing (with ``"sha256:"`` prefix) is performed by
    ``audit.writer.ContextEnricher`` — the raw key is never stored.

    Codeberg #313: for handlers whose sole underlying ApplicationService
    call would otherwise write its own, redundant internal entry for this
    same entity, wrap that one call in :func:`mcp_audit_handoff` (re-exported
    here from ``audit.services``) immediately before calling this function —
    this call then becomes the single audit entry for the operation.

    Args:
        fail_closed: #569 review BR-569-02. ``False`` (default) keeps the
            historical best-effort contract — a failed audit write is logged
            and swallowed so an optional courtesy entry can never fail an
            otherwise-valid tool call. ``True`` opts a *governance* write into
            fail-closed semantics: the failure is re-raised as
            :class:`McpAuditWriteError` so the caller can roll back its
            mutation and answer an error instead of ``ok`` (a blocking finding
            must never be silenced without an audit trail).

    Raises:
        McpAuditWriteError: only when ``fail_closed`` is ``True`` and the
            underlying write failed.
    """
    try:
        from audit.services import log_write

        log_write(
            actor=str(ctx.user_id),
            actor_type="agent",
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            ctx={
                "source": "mcp",
                "client_name": tool_name,
                "api_key": api_key,
            },
            details=details,
        )
    except Exception as exc:
        logger.exception(
            "MCP audit write failed for tool=%s entity=%s", tool_name, entity_id
        )
        if fail_closed:
            raise McpAuditWriteError(
                f"The audit entry for {operation!r} on {entity_type} "
                f"({entity_id}) could not be written; the governance write was "
                "rolled back."
            ) from exc


# ---------------------------------------------------------------------------
# Base tool group
# ---------------------------------------------------------------------------


def map_tool_exception(
    exc: Exception,
) -> tuple[str, str] | tuple[str, str, dict[str, Any]] | None:
    """Map a known domain exception to ``(error_code, message[, details])``.

    Central mapping for every tool group (#1663, #1661, N2-N4): a domain
    validation, not-found, permission, optimistic-lock or integrity failure is
    a caller-actionable answer, not ``INTERNAL_ERROR``. Returning ``None``
    keeps the transport's CWE-209 masking for anything genuinely unexpected.

    Design §4.5 (plan S5.3): a :class:`~application.base.ChangeImpactGateError`
    subtype returns a **3-tuple** whose third element is its structured
    ``details`` payload (``reason``, ``run_id``/``status``, ``finding_ids``/
    ``count``, ``key``). The subtype check runs *before*
    ``isinstance(exc, ValidationError)`` — otherwise every gate refusal would
    collapse into ``VALIDATION_ERROR`` and lose both its code and its details.

    The imports are deliberately lazy: this module is loaded at MCP start-up,
    while ``application.base`` pulls in the event bus and Django settings.
    """
    from application.base import (
        AdoptionHashMismatchError,
        AllocationConflictError,
        ChangeImpactGateError,
        OptimisticLockError,
        WorkflowFrozenError,
    )
    from persistence.errors import (
        NotFoundError,
        PermissionDeniedError,
        ValidationError,
    )

    # Design §4.5 / plan S5.3: MUST precede the ValidationError branch below.
    # The subtype carries its own stable ``error_code`` plus a machine-readable
    # ``details`` dict, so the caller gets all three (code, message, details).
    if isinstance(exc, ChangeImpactGateError):
        code = exc.error_code or "VALIDATION_ERROR"
        return code, str(exc), dict(getattr(exc, "details", None) or {})

    # Issue #1823: an unreachable memory engine is a retryable upstream state,
    # not a server defect -- the same SERVICE_UNAVAILABLE code REST answers
    # with (memory.memory_rest._memory_error_response). Imported lazily like
    # everything in this helper: memory.backends pulls in the ORM models, and
    # the import is guarded so an unrelated failure on a deployment without the
    # memory app still degrades to the masked INTERNAL_ERROR.
    try:
        from memory.backends import MemoryBackendUnavailableError
    except Exception:  # pragma: no cover - the memory app is always installed
        MemoryBackendUnavailableError = ()  # type: ignore[assignment,misc]
    if MemoryBackendUnavailableError and isinstance(exc, MemoryBackendUnavailableError):
        return "SERVICE_UNAVAILABLE", str(exc)
    if isinstance(
        exc, AdoptionHashMismatchError | AllocationConflictError | WorkflowFrozenError
    ):
        return "CONFLICT", str(exc)
    if isinstance(exc, ValidationError):
        return "VALIDATION_ERROR", str(exc)
    # #1966: a handler's own ``int()``/``float()`` conversion raises a plain
    # ValueError for a wrongly typed argument. That is a caller-actionable
    # validation failure, not a server defect — map only the exact base type so
    # custom ValueErrors with a domain contract keep their own handling and
    # genuinely unexpected failures stay CWE-209-masked below.
    if type(exc) is ValueError:
        return "VALIDATION_ERROR", str(exc) or "Invalid parameter value."
    if isinstance(exc, NotFoundError):
        return "NOT_FOUND", str(exc)
    if isinstance(exc, PermissionDeniedError):
        return "PERMISSION_DENIED", str(exc)
    if isinstance(exc, OptimisticLockError):
        return "CONFLICT", f"Version conflict: {exc}"

    # #1986: CycleDetectedError is a plain Exception, not the
    # persistence.errors.ValidationError handled above. A cycle raised while
    # anchoring an ICD used to escape every handler's except-list and surface
    # as INTERNAL_ERROR. Map it centrally so every tool group gets a typed,
    # caller-actionable answer.
    try:
        from traceability.exceptions import CycleDetectedError
    except ImportError:  # pragma: no cover - traceability is always installed
        CycleDetectedError = ()  # type: ignore[assignment,misc]
    if CycleDetectedError and isinstance(exc, CycleDetectedError):
        return (
            "VALIDATION_ERROR",
            "The requested link would introduce a cycle; choose a source/target "
            "pair that keeps the traceability hierarchy acyclic.",
        )

    try:
        from django.db import IntegrityError
    except Exception:  # pragma: no cover - Django is always available in-app
        IntegrityError = ()  # type: ignore[assignment,misc]
    if IntegrityError and isinstance(exc, IntegrityError):
        # Never surface the driver message (constraint/table names, SQL).
        return (
            "CONFLICT",
            "The request conflicts with existing data; nothing was changed.",
        )

    try:
        from workflow.lifecycle_manager import (
            WorkflowConflictError,
            WorkflowStateError,
        )
        from workflow.services import WorkflowItemNotFoundError
    except Exception:  # pragma: no cover - workflow is always installed
        return None

    if isinstance(exc, WorkflowConflictError):
        return "CONFLICT", str(exc)
    if isinstance(exc, WorkflowItemNotFoundError):
        return "NOT_FOUND", str(exc)
    if isinstance(exc, WorkflowStateError):
        return "INVALID_STATE", str(exc)
    return None


class BaseToolGroup(ABC):
    """Common base for all MCP tool groups.

    Subclasses implement ``_TOOL_MAP`` mapping tool names → handler methods.
    """

    # Subclasses must define: {"tool.name": "_method_name"}
    _TOOL_MAP: dict[str, str] = {}

    #: Subclasses can define schema mapping: {"tool.name": {...schema dict...}}
    _TOOL_SCHEMAS: list[dict[str, Any]] = []

    #: True only for *capability* groups: they are routable pseudo-tool groups
    #: that deliberately publish no schemas (``get_tool_schemas() == []``), so
    #: they never appear in ``tools/list``. Only the ``resources/*`` and
    #: ``prompts/*`` MCP capabilities use this (MCP-Modernisierung Task 6/7);
    #: the "no shadow tools" ratchet in
    #: ``test_mcp_workspace_fence_1376.py`` skips them by this flag. A normal
    #: tool group must leave it False — otherwise its tools would silently lose
    #: the #1376 undeclared-``workspace_id`` guard.
    capability_only: bool = False

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return the MCP JSON schemas for all tools in this group.

        API-008 ratchet: the old ``{"kwargs": {...}}`` fallback advertised a
        contract that accepted literally anything while the handler silently
        ignored unknown keys. Every production group must now publish explicit
        schemas (``_TOOL_SCHEMAS``, built dynamically in ``__init__`` where the
        prefix is only known then, or through an override such as the
        attribute groups). Capability groups return an empty list — they are
        not tools and never appear in ``tools/list``.

        A group with no explicit schemas fails closed at construction of the
        catalogue instead of shipping a useless contract. This is deliberately
        *not* a central ``inputSchema`` validator: the design decision at
        :func:`reject_unknown_params` (opt-in, per-handler) stays in force.
        """
        if self._TOOL_SCHEMAS:
            return self._TOOL_SCHEMAS
        if self.capability_only:
            return []
        raise RuntimeError(
            f"{type(self).__name__} publishes no explicit _TOOL_SCHEMAS. "
            "Publish a schema per mapped tool (the 'kwargs' fallback is "
            "forbidden by the API-008 ratchet)."
        )

    def schema_param_names(self, tool_name: str) -> list[str]:
        """Return the declared ``inputSchema`` property names of *tool_name*.

        Single source of truth for handlers that call
        :func:`reject_unknown_params`: deriving the allow-list from the
        published schema keeps the two from drifting apart, so adding a
        property to the schema cannot turn a documented call into a
        validation error.

        Returns an empty list for an unknown tool name or a group that has no
        explicit ``_TOOL_SCHEMAS`` — callers should treat that as "no strict
        validation possible" rather than "nothing is allowed". A group built
        without ``__init__`` (unit-test double) therefore stays permissive;
        production groups always have a schema and stay strict.
        """
        try:
            schemas = self.get_tool_schemas()
        except RuntimeError:
            return []
        for schema in schemas:
            if schema.get("name") == tool_name:
                properties = schema.get("inputSchema", {}).get("properties", {})
                return list(properties.keys())
        return []

    def execute_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        auth_context: AuthContext,
        api_key: str,
    ) -> ToolResult:
        """Dispatch *tool_name* to the registered handler method.

        Args:
            tool_name: MCP tool identifier.
            params: Caller parameters (api_key already stripped).
            auth_context: Validated and role-resolved AuthContext.
            api_key: Raw API key (for audit hash — never logged plaintext).

        Returns:
            ToolResult from the handler, or UNKNOWN_TOOL error.
        """
        method_name = self._TOOL_MAP.get(tool_name)
        if not method_name:
            return ToolResult.error(
                "UNKNOWN_TOOL", f"Tool '{tool_name}' not found in {type(self).__name__}."
            )
        handler = getattr(self, method_name, None)
        if handler is None:
            return ToolResult.error("INTERNAL_ERROR", f"Handler '{method_name}' not implemented.")
        try:
            return handler(params=params, auth_context=auth_context, api_key=api_key)
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except Exception as exc:
            mapped = map_tool_exception(exc)
            if mapped is not None:
                # Design §4.5 (plan S5.3): a change-impact refusal comes back
                # as a 3-tuple carrying its structured ``details``; every other
                # mapping stays a 2-tuple and keeps its previous shape.
                if len(mapped) == 3:
                    code, message, details = mapped
                else:
                    code, message = mapped
                    details = None
                logger.debug(
                    "Tool %s returned %s: %s", tool_name, code, message
                )
                return ToolResult.error(code, message, details=details)
            # fix #108: str(exc) on an unmapped exception (IntegrityError,
            # ProgrammingError, KeyError, ...) can contain SQL fragments,
            # table/column names, or constraint names. Log the real detail,
            # return only a static message to the caller.
            logger.exception("Error in %s.%s for tool=%s", type(self).__name__, method_name, tool_name)
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")


__all__ = [
    "BaseToolGroup",
    "CANONICAL_FETCH_VERB",
    "CANONICAL_LIST_VERB",
    "CANONICAL_SOFT_DELETE_REASON_KEY",
    "DEPRECATED_SOFT_DELETE_REASON_KEY",
    "FETCH_VERBS",
    "LIST_VERBS",
    "McpAuditWriteError",
    "ParameterError",
    "artifact_custom_fields",
    "mcp_audit_handoff",
    "map_tool_exception",
    "optional_uuid",
    "parse_pagination",
    "reject_unknown_params",
    "require_admin_tier",
    "require_param",
    "require_uuid",
    "resolve_engine_status",
    "resolve_status_map",
    "soft_delete_reason",
    "soft_delete_reason_properties",
    "tool_verb",
    "transport_safe",
    "validate_artifact_write",
    "verb_operation",
    "workspace_query_required",
    "write_mcp_audit",
]
