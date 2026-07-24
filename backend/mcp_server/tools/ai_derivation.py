"""
MCP Tool Group for AI-backed derivation flows (REQ-L2-AI-001, REQ-L2-AI-002,
REQ-L2-AI-003).

Exposes the three Draft/Accept derivation flows as MCP tools. Every tool
supports two modes (Phase 3, REQ-L2-AI-003):

  mode="preview" (default) — returns *drafts only*, nothing is persisted.
      This is the original, unchanged behaviour of all three tools.
  mode="write"   — persists the draft(s) via the existing application
      services, creates the corresponding TraceLink(s) back to the source
      entity, and (with ``policy="auto"``) best-effort auto-advances the
      new entity through its workflow.

Tools:
  ai_derivation.derive_requirements_from_need(need_id, n=3, mode, policy)
      StakeholderNeed -> proposed system requirement drafts (write: creates
      one Requirement + "derives-from" TraceLink per draft).
  ai_derivation.suggest_architecture_for_requirement(requirement_id, mode, policy)
      Requirement -> suggested *existing* architecture element ids
      (unassigned reqs only; write: allocates the requirement to the
      top-ranked suggested element via an "allocated-to" TraceLink — only
      one allocation per requirement is possible, see TraceLinkService.allocate;
      no new ArchitectureElement is ever created by this tool, preview or
      write).
  ai_derivation.decompose_requirement_next_level(requirement_id, mode, policy)
      Requirement -> next-level requirement drafts (allocated reqs only;
      write: creates one child Requirement + "derives-from" TraceLink per
      draft).
  ai_derivation.derive_risks_from_architecture(architecture_element_id, mode, policy)
      ArchitectureElement -> proposed risk drafts (write: creates one Risk +
      "traces" TraceLink per draft). See the naming-decision note below.
  ai_derivation.derive_glossary_from_workspace(workspace_id, mode, policy)
      Workspace -> proposed glossary term drafts (write: creates one
      GlossaryTerm per draft; creates NO TraceLink — a bare Workspace id is
      not a resolvable TraceLinkService source and GlossaryTerm has no
      backing Artifact either, see
      ``AiDerivationService._write_glossary_term_draft``'s docstring).

The default LLM provider is ``mock`` (credential-free, deterministic), so the
tools work without external configuration (REQ-L2-AI-002).

REQ-L2-MC-007: because ``mode="write"`` makes all four tools capable of
mutation, all four are registered in ``mcp_server.tool_registry``'s
``_WRITE_TOOL_PREFIXES``. That RBAC gate is name-based (not mode-aware), so
this is a deliberate, new restriction: as of Phase 3, a Viewer can no longer
call any of these four tools at all — including ``mode="preview"``. Before
Phase 3 a Viewer could preview drafts; that capability is now Editor+ only.

Naming decision (Phase 3, Task 3) — ``derive_risks_from_architecture`` lives
under the ``ai_derivation`` prefix, NOT ``risk`` (the design spec's suggested
name is ``risk.derive_from_architecture``): ``ToolGroupRouter`` routes a
prefix to exactly ONE registered tool-group instance, and the ``"risk"``
prefix is already owned by a single ``GenericCrudToolGroup("risk",
RiskService)`` instance (generic CRUD shared verbatim by 5 entities: Risk,
Issue, Adr, ChangeRequest, StakeholderNeed). Adding a "derive" concept to
that shared class would be invasive (touches all 5 entities' tool surface
for a capability only Risk needs), whereas ``test.derive_from_requirement``
could live on the ``test`` prefix precisely because ``McpTestToolGroup`` is
already a bespoke, non-generic class. Keeping the tool on ``ai_derivation``
(deviating from the spec's suggested name) is the lower-risk choice; the
CRUD-group-injection alternative can be revisited later if a second generic
entity needs a derive tool.
"""
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.ai_derivation_service import AiDerivationService, LlmResponseError
from application.base import NotFoundError, ValidationError
from application.requirement_service import RequirementService
from application.risk_service import RiskService
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    ToolResult,
    require_uuid,
    write_mcp_audit,
)
from traceability.types import LinkType

_VALID_MODES = ("preview", "write")
_VALID_POLICIES = ("manual", "auto")


def _parse_mode_policy(params: Dict[str, Any]) -> tuple[str, str]:
    """Return the validated ``(mode, policy)`` pair from *params*.

    Raises:
        ParameterError: Either value is not one of the accepted enums.
    """
    mode = params.get("mode", "preview")
    policy = params.get("policy", "manual")
    if mode not in _VALID_MODES:
        raise ParameterError(
            f"'mode' must be one of {_VALID_MODES}, got '{mode}'."
        )
    if policy not in _VALID_POLICIES:
        raise ParameterError(
            f"'policy' must be one of {_VALID_POLICIES}, got '{policy}'."
        )
    return mode, policy


_MODE_POLICY_SCHEMA_PROPERTIES: Dict[str, Any] = {
    "mode": {
        "type": "string",
        "enum": list(_VALID_MODES),
        "description": (
            "'preview' (default) returns drafts only; 'write' persists them "
            "and creates the corresponding trace link(s)."
        ),
    },
    "policy": {
        "type": "string",
        "enum": list(_VALID_POLICIES),
        "description": (
            "Only relevant for mode='write'. 'manual' (default) leaves new "
            "entities in their initial draft state; 'auto' best-effort "
            "auto-advances them through their workflow."
        ),
    },
}


class AiDerivationToolGroup(BaseToolGroup):
    """AI derivation tool group (REQ-L2-AI-002, write mode REQ-L2-AI-003)."""

    _TOOL_MAP = {
        "ai_derivation.derive_requirements_from_need": "_handle_derive_requirements",
        "ai_derivation.suggest_architecture_for_requirement": "_handle_suggest_architecture",
        "ai_derivation.decompose_requirement_next_level": "_handle_decompose_next_level",
        "ai_derivation.derive_risks_from_architecture": "_handle_derive_risks_from_architecture",
        "ai_derivation.derive_glossary_from_workspace": "_handle_derive_glossary_from_workspace",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "ai_derivation.derive_requirements_from_need",
            "description": (
                "Propose system requirement drafts for a stakeholder need. "
                "mode='preview' (default) returns drafts only; mode='write' "
                "persists each draft as a Requirement and links it back to "
                "the need via a 'derives-from' trace link."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "need_id": {
                        "type": "string",
                        "description": "UUID of the stakeholder need.",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Number of requirement drafts (default 3).",
                    },
                    **_MODE_POLICY_SCHEMA_PROPERTIES,
                },
                "required": ["need_id"],
            },
        },
        {
            "name": "ai_derivation.suggest_architecture_for_requirement",
            "description": (
                "Suggest existing architecture elements that could satisfy "
                "an unassigned requirement. mode='preview' (default) returns "
                "element ids only; mode='write' allocates the requirement to "
                "the top-ranked suggested element via an 'allocated-to' trace "
                "link (only one allocation per requirement is possible; no "
                "new ArchitectureElement is ever created by this tool)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirement_id": {
                        "type": "string",
                        "description": "UUID of the requirement.",
                    },
                    **_MODE_POLICY_SCHEMA_PROPERTIES,
                },
                "required": ["requirement_id"],
            },
        },
        {
            "name": "ai_derivation.decompose_requirement_next_level",
            "description": (
                "Propose next-level requirement drafts for a requirement that is "
                "allocated to at least one architecture element. mode='preview' "
                "(default) returns drafts only; mode='write' persists each draft "
                "as a child Requirement and links it back to the parent via a "
                "'derives-from' trace link."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirement_id": {
                        "type": "string",
                        "description": "UUID of the requirement to decompose.",
                    },
                    **_MODE_POLICY_SCHEMA_PROPERTIES,
                },
                "required": ["requirement_id"],
            },
        },
        {
            "name": "ai_derivation.derive_risks_from_architecture",
            "description": (
                "Propose risk drafts for an architecture element. "
                "mode='preview' (default) returns drafts only; mode='write' "
                "persists each draft as a Risk and links it back to the "
                "architecture element via a 'traces' trace link."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "architecture_element_id": {
                        "type": "string",
                        "description": "UUID of the architecture element.",
                    },
                    **_MODE_POLICY_SCHEMA_PROPERTIES,
                },
                "required": ["architecture_element_id"],
            },
        },
        {
            "name": "ai_derivation.derive_glossary_from_workspace",
            "description": (
                "Propose glossary term drafts extracted from a workspace's "
                "requirements and architecture elements. mode='preview' "
                "(default) returns drafts only; mode='write' persists each "
                "draft as a GlossaryTerm. No trace link is created (a "
                "Workspace id cannot be a trace-link source and GlossaryTerm "
                "has no backing Artifact)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the workspace to scan.",
                    },
                    **_MODE_POLICY_SCHEMA_PROPERTIES,
                },
                "required": ["workspace_id"],
            },
        },
    ]

    def __init__(
        self,
        service: Optional[AiDerivationService] = None,
        requirement_service: Optional[RequirementService] = None,
        risk_service: Optional[RiskService] = None,
    ) -> None:
        self._service = service or AiDerivationService()
        self._requirement_service = requirement_service or RequirementService()
        self._risk_service = risk_service or RiskService()

    def _handle_derive_requirements(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        need_id = require_uuid(params, "need_id")
        n_raw = params.get("n", 3)
        try:
            n = int(n_raw)
        except (TypeError, ValueError):
            return ToolResult.error("VALIDATION_ERROR", "'n' must be an integer.")
        mode, policy = _parse_mode_policy(params)

        try:
            preview = self._service.derive_requirements_from_need(
                auth_context, need_id, n=n
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        if mode == "preview":
            return ToolResult.ok(preview)

        try:
            need = self._service._get_stakeholder_need(need_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        workspace_id = need.artifact.workspace_id

        # Each draft is written in its own atomic transaction
        # (AiDerivationService._write_derived_entity is wrapped in
        # @atomic_transaction): a failure on one draft (e.g. an invalid
        # trace-link semantics violation) only rolls back that one draft and
        # must not discard the drafts already written in this loop. Failures
        # are collected instead of raised so the caller can see exactly
        # which drafts succeeded and which failed (REQ-L3-PL003-002).
        written: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for draft in preview["drafts"]:
            try:
                result = self._service._write_derived_entity(
                    ctx=auth_context,
                    workspace_id=workspace_id,
                    item_type="Requirement",
                    create_fn=lambda d=draft: self._requirement_service.create_requirement(
                        workspace_id=workspace_id,
                        title=d["title"],
                        ctx=auth_context,
                        description=d["description"],
                    ),
                    # TraceLinkService._resolve_artifact_id only resolves
                    # Artifact/Requirement/ArchitectureElement/Adr ids — not
                    # StakeholderNeed ids — so the link must be sourced from
                    # the need's *artifact* id, not its own PK.
                    source_entity_id=need.artifact_id,
                    source_item_type="StakeholderNeed",
                    link_type=LinkType.DERIVES_FROM.value,
                    policy=policy,
                )
            except (ValidationError, NotFoundError) as exc:
                failed.append({"draft": draft, "error": str(exc)})
                continue
            written.append(result)
            write_mcp_audit(
                ctx=auth_context,
                operation="derive_requirements_from_need",
                entity_type="Requirement",
                entity_id=UUID(result["id"]),
                tool_name="ai_derivation.derive_requirements_from_need",
                api_key=api_key,
                details={"source_need_id": str(need_id), "policy": policy},
            )
        response: Dict[str, Any] = {"written": written}
        if failed:
            response["failed"] = failed
        return ToolResult.ok(response)

    def _handle_suggest_architecture(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        requirement_id = require_uuid(params, "requirement_id")
        mode, policy = _parse_mode_policy(params)

        try:
            preview = self._service.suggest_architecture_for_requirement(
                auth_context, requirement_id
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        if mode == "preview":
            return ToolResult.ok(preview)

        # Write mode here means something different from the other two
        # tools: suggest_architecture_for_requirement only ever suggests
        # *existing* ArchitectureElement ids (it never drafts new elements),
        # so "persisting the draft" cannot mean "create a new entity" — there
        # is nothing for policy="auto" to auto-approve, so `policy` is
        # accepted for schema symmetry with the other two tools but has no
        # effect on this tool's write path.
        #
        # TraceLinkService.allocate() enforces exactly one "allocated-to"
        # link per requirement (it deletes any prior allocation before
        # creating the new one — REQ-L1-042), so — unlike the other two
        # tools, whose preview is a *list* every entry of which gets
        # persisted — only the top-ranked suggestion is allocated here.
        # Looping allocate() over every suggested id would silently discard
        # all but the last one, which is not a "write everything the preview
        # returned" semantic worth pretending to support.
        suggested_ids = preview["suggested_arch_element_ids"]
        if not suggested_ids:
            return ToolResult.ok({"written": []})

        from application.trace_link_service import TraceLinkService

        top_choice = suggested_ids[0]
        link = TraceLinkService().allocate(
            requirement_id=requirement_id,
            architecture_element_id=UUID(top_choice),
            ctx=auth_context,
        )
        write_mcp_audit(
            ctx=auth_context,
            operation="suggest_architecture_for_requirement",
            entity_type="TraceLink",
            entity_id=link.id,
            tool_name="ai_derivation.suggest_architecture_for_requirement",
            api_key=api_key,
            details={
                "requirement_id": str(requirement_id),
                "arch_element_id": top_choice,
            },
        )
        return ToolResult.ok(
            {"written": [{"target_id": top_choice, "trace_link_id": str(link.id)}]}
        )

    def _handle_decompose_next_level(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        requirement_id = require_uuid(params, "requirement_id")
        mode, policy = _parse_mode_policy(params)

        try:
            preview = self._service.decompose_requirement_next_level(
                auth_context, requirement_id
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        if mode == "preview":
            return ToolResult.ok(preview)

        try:
            parent_req = self._service._get_requirement(requirement_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        workspace_id = parent_req.artifact.workspace_id

        # See _handle_derive_requirements above: each draft is written in its
        # own atomic transaction, so a failure on one draft must not discard
        # the drafts already written in this loop.
        written: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for draft in preview["drafts"]:
            try:
                result = self._service._write_derived_entity(
                    ctx=auth_context,
                    workspace_id=workspace_id,
                    item_type="Requirement",
                    create_fn=lambda d=draft: self._requirement_service.create_requirement(
                        workspace_id=workspace_id,
                        title=d["title"],
                        ctx=auth_context,
                        description=d["description"],
                    ),
                    source_entity_id=requirement_id,
                    source_item_type="Requirement",
                    link_type=LinkType.DERIVES_FROM.value,
                    policy=policy,
                )
            except (ValidationError, NotFoundError) as exc:
                failed.append({"draft": draft, "error": str(exc)})
                continue
            written.append(result)
            write_mcp_audit(
                ctx=auth_context,
                operation="decompose_requirement_next_level",
                entity_type="Requirement",
                entity_id=UUID(result["id"]),
                tool_name="ai_derivation.decompose_requirement_next_level",
                api_key=api_key,
                details={"parent_requirement_id": str(requirement_id), "policy": policy},
            )
        response: Dict[str, Any] = {"written": written}
        if failed:
            response["failed"] = failed
        return ToolResult.ok(response)

    def _handle_derive_risks_from_architecture(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        architecture_element_id = require_uuid(params, "architecture_element_id")
        mode, policy = _parse_mode_policy(params)

        try:
            preview = self._service.derive_risks_from_architecture(
                auth_context, architecture_element_id
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        if mode == "preview":
            return ToolResult.ok(preview)

        try:
            ae = self._service._get_architecture_element(architecture_element_id)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        workspace_id = ae.artifact.workspace_id

        # See _handle_derive_requirements above: each draft is written in its
        # own atomic transaction, so a failure on one draft must not discard
        # the drafts already written in this loop.
        written: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for draft in preview["drafts"]:
            try:
                result = self._service._write_derived_entity(
                    ctx=auth_context,
                    workspace_id=workspace_id,
                    item_type="Risk",
                    create_fn=lambda d=draft: self._risk_service.create_risk(
                        workspace_id=workspace_id,
                        title=d["title"],
                        probability=d["probability"],
                        impact=d["impact"],
                        ctx=auth_context,
                        description=d["description"],
                        category=d["category"],
                    ),
                    # _resolve_artifact_id resolves bare ArchitectureElement
                    # ids directly, so the element's own id (not its artifact
                    # id) is used as the link source — mirrors how
                    # decompose_requirement_next_level sources its link from
                    # requirement_id above.
                    source_entity_id=architecture_element_id,
                    source_item_type="ArchitectureElement",
                    link_type=LinkType.TRACES.value,
                    policy=policy,
                )
            except (ValidationError, NotFoundError) as exc:
                failed.append({"draft": draft, "error": str(exc)})
                continue
            written.append(result)
            write_mcp_audit(
                ctx=auth_context,
                operation="derive_risks_from_architecture",
                entity_type="Risk",
                entity_id=UUID(result["id"]),
                tool_name="ai_derivation.derive_risks_from_architecture",
                api_key=api_key,
                details={
                    "source_architecture_element_id": str(architecture_element_id),
                    "policy": policy,
                },
            )
        response: Dict[str, Any] = {"written": written}
        if failed:
            response["failed"] = failed
        return ToolResult.ok(response)

    def _handle_derive_glossary_from_workspace(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = require_uuid(params, "workspace_id")
        mode, policy = _parse_mode_policy(params)

        try:
            preview = self._service.derive_glossary_from_workspace(
                auth_context, workspace_id
            )
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except LlmResponseError as exc:
            return ToolResult.error("INTERNAL_ERROR", str(exc))

        if mode == "preview":
            return ToolResult.ok(preview)

        # Unlike the other three write paths, this one creates NO trace
        # link (see AiDerivationService._write_glossary_term_draft's
        # docstring: a bare Workspace id is not a resolvable
        # TraceLinkService source, and GlossaryTerm has no backing Artifact
        # to link from either).
        #
        # Each draft is written in its own atomic transaction
        # (_write_glossary_term_draft is wrapped in @atomic_transaction), so
        # a failure on one draft must not discard the drafts already written
        # in this loop. GlossaryService.create() raises ValidationError for
        # a colliding (workspace, term) pair (REQ-L1-044's unique_together
        # constraint) — caught here exactly like every other draft-specific
        # ValidationError, never left to crash the batch
        # (REQ-L3-PL003-002).
        written: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for draft in preview["drafts"]:
            try:
                result = self._service._write_glossary_term_draft(
                    ctx=auth_context,
                    workspace_id=workspace_id,
                    term=draft["term"],
                    definition=draft["definition"],
                    synonyms=draft["synonyms"],
                    abbreviation=draft["abbreviation"],
                    policy=policy,
                )
            except (ValidationError, NotFoundError) as exc:
                failed.append({"draft": draft, "error": str(exc)})
                continue
            written.append(result)
            write_mcp_audit(
                ctx=auth_context,
                operation="derive_glossary_from_workspace",
                entity_type="GlossaryTerm",
                entity_id=UUID(result["id"]),
                tool_name="ai_derivation.derive_glossary_from_workspace",
                api_key=api_key,
                details={"source_workspace_id": str(workspace_id), "policy": policy},
            )
        response: Dict[str, Any] = {"written": written}
        if failed:
            response["failed"] = failed
        return ToolResult.ok(response)


__all__ = ["AiDerivationToolGroup"]
