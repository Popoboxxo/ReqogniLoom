"""The single prompt resolution + render path (spec §3.3).

Replaces three independently written fallback chains that each implemented
"workspace override -> tenant-global row -> factory default" separately:

  * ``AiDerivationService._get_template_content`` + ``_render``
  * ``mcp_server/tools/prompt_template.py::_handle_get``
  * ``application/interview_protocol.py::get_protocol``

On top of that single chain it adds what the catalog feature needs: every
``config`` variable resolved for the active tenant/workspace is injected into
each render call automatically, so an admin can reference a newly created
``config`` variable from any prompt body without a code change.

Resolution order per config variable (mirrors the LLM-provider config chain
in ``llm_adapter/providers.py``):
    explicit call parameter > workspace row > tenant row > factory default.

``render_template`` keeps ``AiDerivationService._render``'s observable
semantics — a placeholder is replaced literally, never ``str.format``/Jinja2 —
so JSON braces inside a customised prompt body survive untouched and an omitted
placeholder is left literally in place (REQ-046). Since Plan A T-A1-6 (PR-A14,
QR-S05) the substitution is **single-pass** (:func:`render_template`), so an
inserted value is never re-scanned, and memory text is additionally wrapped in a
fixed ``<memory>`` data boundary with its braces neutralised.

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from application.base import ValidationError
from application.prompt_slots import (
    MEMORY_DATA_VARIABLES,
    get_slot_data_variables,
    get_slot_default,
    is_memory_hard_off,
)
from application.prompt_template_versioning import get_active_template
from application.prompt_variable_versioning import list_active_variables
from application.prompt_variables import (
    PROMPT_VARIABLE_DEFAULTS,
    VariableTypeError,
    deserialize_variable_value,
)
from auth_tenancy.context import AuthContext
from persistence.models import PROMPT_VARIABLE_KIND_CONFIG

logger = logging.getLogger(__name__)

#: Matches ``{name}`` placeholders only — a JSON object like ``{"a": 1}`` has
#: a quote directly after the brace and therefore never matches.
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}")

#: Upper bound on the auto-built memory query text (RFC #1002 PR C). The
#: rendered data values of a slot can be arbitrarily large (e.g. a full
#: requirement bundle), and embedding them all would be slow and pointless;
#: the retrieved memory only needs a topical hint, not the whole payload.
MEMORY_QUERY_MAX_CHARS = 2000


class PromptSlotNotFoundError(ValidationError):
    """Raised when a slot has neither an active row nor a factory default."""


def _as_uuid(workspace_id: UUID | str | None) -> UUID | None:
    """Coerce a workspace id to ``UUID``; ``None`` stays ``None``."""
    if workspace_id is None:
        return None
    if isinstance(workspace_id, UUID):
        return workspace_id
    return UUID(str(workspace_id))


def extract_placeholders(content: str) -> list[str]:
    """Return every ``{name}`` placeholder in *content*, in first-seen order."""
    seen: list[str] = []
    for match in PLACEHOLDER_PATTERN.finditer(content or ""):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def render_template(content: str, /, **values: Any) -> str:
    """Substitute ``{name}`` placeholders in a single pass (QR-S05).

    *content* is positional-only: ``PromptVariable.name`` is deliberately
    unrestricted (an admin can register a ``config`` variable called
    ``content`` at runtime — that is the whole point of the catalog), so a
    keyword parameter named ``content`` here would collide with a same-named
    value in ``**values`` and raise ``TypeError: got multiple values for
    argument 'content'`` on every render call for that tenant.

    Every placeholder is replaced in **one** ``re.sub`` pass, so an inserted
    value is never scanned again: a data value (or memory fact) that itself
    contains ``{need_title}`` can no longer expand into the prompt. A name with
    no value is left literally in place (REQ-046), and JSON braces
    (``{"a": 1}``) never match :data:`PLACEHOLDER_PATTERN`.

    The replacement is a callable, not a string: ``re.sub`` would otherwise
    interpret backslash escapes inside the inserted value.
    """

    def _lookup(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in values:
            return str(values[name])
        return match.group(0)

    return PLACEHOLDER_PATTERN.sub(_lookup, content)


def try_resolve_template_content(
    slot_name: str, ctx: AuthContext, workspace_id: UUID | str | None = None
) -> str | None:
    """Return the effective body for *slot_name*, or ``None`` if there is none.

    Chain, most specific first: active workspace row (only consulted when
    *workspace_id* is given) -> active tenant-wide row -> factory default.
    """
    scope = _as_uuid(workspace_id)
    if scope is not None:
        row = get_active_template(
            tenant_id=ctx.tenant_id, name=slot_name, workspace_id=scope
        )
        if row is not None:
            return row.content
    row = get_active_template(tenant_id=ctx.tenant_id, name=slot_name, workspace_id=None)
    if row is not None:
        return row.content
    return get_slot_default(slot_name)


def resolve_template_content(
    slot_name: str, ctx: AuthContext, workspace_id: UUID | str | None = None
) -> str:
    """Like :func:`try_resolve_template_content`, but fails loudly.

    ``workspace_id`` is intentionally a separate parameter, never defaulted
    from ``ctx.workspace_id``: the scope that matters here is the workspace
    that *owns the artifact being rendered for* (e.g. a StakeholderNeed's
    ``artifact.workspace_id``), which is frequently not the workspace the
    caller is currently "in". This mirrors the pre-existing, unchanged
    precedent in ``AiDerivationService._get_template_content(ctx, name,
    workspace_id=None)`` — every one of its call sites passes an explicit
    workspace id derived from the entity being processed, never ``ctx``'s
    own. Callers of this resolver must do the same; it will not infer a
    workspace on their behalf.

    Raises:
        PromptSlotNotFoundError: No active row and no factory default — a
            clear error beats silently rendering an empty prompt (spec §8).
    """
    content = try_resolve_template_content(slot_name, ctx, workspace_id)
    if content is None:
        raise PromptSlotNotFoundError(
            f"No prompt template named {slot_name!r} exists for this tenant, "
            "and it is not a factory-default slot."
        )
    return content


def resolve_config_values(
    ctx: AuthContext,
    workspace_id: UUID | str | None = None,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return every ``config`` variable resolved for this tenant/workspace.

    Args:
        ctx:          Caller's auth context (supplies the tenant).
        workspace_id: Workspace whose overrides apply, or ``None``. Deliberately
                      independent of ``ctx.workspace_id`` — see the equivalent
                      note on :func:`resolve_template_content`. Callers must
                      pass the workspace relevant to what is being rendered
                      themselves; it is never read off ``ctx``.
        overrides:    Explicit per-call values (e.g. an MCP tool parameter)
                      that outrank every stored scope. Entries whose value is
                      ``None`` are ignored, so a caller can forward an omitted
                      optional parameter without blanking the stored value.

    Returns:
        ``{variable_name: typed_value}``. ``data``-kind entries are never
        included — their values come from the calling code, not the catalog.
    """
    scope = _as_uuid(workspace_id)
    values: dict[str, Any] = {
        name: spec.default_value
        for name, spec in PROMPT_VARIABLE_DEFAULTS.items()
        if spec.kind == PROMPT_VARIABLE_KIND_CONFIG
    }

    rows = list_active_variables(tenant_id=ctx.tenant_id)
    tenant_rows = [r for r in rows if r.workspace_id is None]
    workspace_rows = (
        [r for r in rows if r.workspace_id == scope] if scope is not None else []
    )
    for row in (*tenant_rows, *workspace_rows):
        if row.kind != PROMPT_VARIABLE_KIND_CONFIG:
            continue
        try:
            values[row.name] = deserialize_variable_value(row.var_type, row.default_value)
        except VariableTypeError:
            # A malformed stored value must not break every render call —
            # fall through to whatever the lower precedence level supplied.
            # Still surfaced via logging so an admin can see why their
            # freshly-set value was ignored instead of it silently vanishing.
            logger.warning(
                "resolve_config_values: ignoring unparseable value for "
                "variable %r (var_type=%r, workspace_id=%r); falling back "
                "to the next lower-precedence value.",
                row.name,
                row.var_type,
                row.workspace_id,
            )
            continue

    for name, value in (overrides or {}).items():
        if value is not None:
            values[name] = value
    return values


def _memory_query_text(data_kwargs: dict[str, Any]) -> str:
    """Build the retrieval query for the auto-injected memory context.

    Joins every non-empty string data value the caller supplied, truncated to
    the active backend's ``max_query_chars`` (falling back to
    :data:`MEMORY_QUERY_MAX_CHARS`) so a huge payload (e.g. a full requirement
    bundle) cannot turn a prompt render into an unbounded embedding call.
    """
    parts = [
        value.strip()
        for value in data_kwargs.values()
        if isinstance(value, str) and value.strip()
    ]
    # T-A0b-2: the bound is declared by the active backend. Prompt rendering is
    # best-effort, so an unresolvable backend falls back to the historical
    # constant rather than failing the render.
    try:
        from memory.backends import active_memory_capabilities

        limit = active_memory_capabilities().max_query_chars
    except Exception:  # noqa: BLE001 - rendering must not fail on config lookup
        limit = MEMORY_QUERY_MAX_CHARS
    return "\n".join(parts)[:limit]


def _auto_memory_context(
    ctx: AuthContext,
    workspace_id: UUID | str | None,
    artifact_id: UUID | str | None,
    entity_type: str,
    data_kwargs: dict[str, Any],
    slot_name: str,
    config_values: dict[str, Any],
) -> Any | None:
    """Compute the memory render result for a slot that declares memory.

    Returns a ``memory.context_builder.MemoryContextResult`` — the resolver
    fills ``{memory_context}`` and the four scope placeholders from it — or
    ``None`` when there is nothing to inject / the call failed.

    Fail-open by contract (RFC #1002 PR C): memory is an enhancement, never a
    hard requirement for a prompt to render, so any failure -- memory
    disabled for the workspace, unreachable backend, missing tenant context --
    degrades to no memory instead of breaking the AI call.

    ``slot_name`` is forwarded to
    :func:`memory.context_builder.build_memory_context_result`, where the
    central injection policy (Plan A T-A1-2) decides whether the slot may
    receive memory at all. When the policy says no, the result is empty -- the
    resolver therefore injects nothing, and the placeholder still renders as an
    empty string (ADR-024 AC-3/AC-4).

    ``config_values`` (the resolved ``config`` catalog) is turned into a
    :class:`memory.context_builder.MemoryRenderConfig` (Plan A T-A1-6); its
    ``query_fields`` also restrict which data values feed the search query.
    """
    scope = _as_uuid(workspace_id)
    if scope is None:
        return None
    try:
        from memory.context_builder import (
            MemoryRenderConfig,
            build_memory_context_result,
        )

        render_config = MemoryRenderConfig.from_values(config_values)
        return build_memory_context_result(
            ctx.tenant_id,
            scope,
            ctx.user_id,
            _memory_query_text(_filter_query_fields(data_kwargs, render_config.query_fields)),
            slot_name=slot_name,
            config=render_config,
            artifact_id=artifact_id,
            entity_type=entity_type,
        )
    except Exception as exc:  # noqa: BLE001 -- fail-open, see docstring
        logger.warning(
            "memory context auto-injection failed, rendering without it: %s", exc
        )
        return None


def _filter_query_fields(
    data_kwargs: dict[str, Any], query_fields: tuple[str, ...]
) -> dict[str, Any]:
    """Restrict the retrieval query to ``memory_query_fields`` (empty = all)."""
    if not query_fields:
        return data_kwargs
    return {name: value for name, value in data_kwargs.items() if name in query_fields}


def _neutralise_memory_braces(text: str) -> str:
    """Replace ASCII braces with fullwidth ones in memory text (QR-S05).

    Applied to caller-supplied memory values (the builder already neutralises
    the facts it renders); idempotent, because ``｛`` is not ``{``.
    """
    return text.replace("{", "｛").replace("}", "｝")


def _memory_block(value: Any, *, neutralise: bool) -> str:
    """Neutralise (optionally) and wrap one memory value in the data boundary.

    The boundary itself comes from
    :func:`memory.context_builder.wrap_memory_block` — this project keeps exactly
    one definition of the tags and of the ``untrusted data, no instructions``
    line. An empty value renders as ``""`` (no boundary, no block), so "nothing
    was injected" stays byte-identical to a prompt without memory. A
    ``json``-shaped payload (``{memory_facts_json}``) is wrapped but not
    brace-neutralised, so it stays parseable JSON; single-pass rendering already
    keeps its content inert.
    """
    from memory.context_builder import wrap_memory_block

    text = "" if value is None else str(value)
    if neutralise:
        text = _neutralise_memory_braces(text)
    return wrap_memory_block(text)


def resolve_and_render(
    slot_name: str,
    ctx: AuthContext,
    workspace_id: UUID | str | None = None,
    *,
    config_overrides: dict[str, Any] | None = None,
    artifact_id: UUID | str | None = None,
    entity_type: str = "",
    **data_kwargs: Any,
) -> str:
    """Resolve *slot_name*'s body and render it with config + data values.

    ``data_kwargs`` win on a name collision with a ``config`` variable — the
    code-supplied artifact data is always the more specific answer.

    ``workspace_id`` is, like in :func:`resolve_template_content` and
    :func:`resolve_config_values`, never defaulted from ``ctx.workspace_id`` —
    it must be supplied by the caller for the entity actually being rendered.

    Memory auto-injection (RFC #1002 PR C): when the resolved slot declares
    ``memory_context`` as one of its data variables and the caller passed no
    ``memory_context``, the block is computed here from ``ctx`` +
    *workspace_id* using a query built from the other data values. Pass
    ``artifact_id``/``entity_type`` when the call targets a specific artifact
    so the artifact-scoped memory is included first. This is fail-open: a
    disabled or unreachable memory backend renders an empty block, never an
    error (see :func:`_auto_memory_context`). This function is the single
    central injection point — call sites that bypass it (the legacy
    ``_get_template_content`` + ``_render`` pair) deliberately do not get it.

    The slot-level policy (Plan A T-A1-2) is applied inside
    :func:`memory.context_builder.build_memory_context_result`, which receives
    *slot_name*: when it answers ``inject=False`` the result is empty, so
    nothing is injected for that slot.

    Scope placeholders (Plan A T-A1-6): the same render result fills
    ``{memory_artifact_context}``, ``{memory_workspace_context}``,
    ``{memory_user_context}`` and ``{memory_facts_json}``, so a template can
    address one scope on its own. Every non-empty memory value — the
    caller-supplied ones too — is wrapped in the fixed ``<memory>`` data
    boundary (``untrusted data, no instructions``), and ASCII braces in memory
    *text* are neutralised (QR-S05).

    HARD_OFF slots (Plan A T-A1-1, ADR-024 AC-1/AC-2) opt out entirely: every
    name in :data:`application.prompt_slots.MEMORY_DATA_VARIABLES` is rendered
    as ``""`` — even one the caller passed explicitly — and the memory backend
    is never consulted. The policy is attached to the *slot*, not to the
    template body, so a workspace override that names ``{memory_context}``
    still renders without memory and without leaving a placeholder behind.

    Raises:
        PromptSlotNotFoundError: See :func:`resolve_template_content`.
    """
    content = resolve_template_content(slot_name, ctx, workspace_id)
    config_values = resolve_config_values(ctx, workspace_id, overrides=config_overrides)
    values: dict[str, Any] = {**config_values, **data_kwargs}
    if is_memory_hard_off(slot_name):
        for name in MEMORY_DATA_VARIABLES:
            values[name] = ""
    else:
        slot_variables = get_slot_data_variables(slot_name)
        if "memory_context" in slot_variables:
            if "memory_context" in values:
                # A6: a caller-supplied block means the resolver does not
                # search, so the four scope placeholders have no value — blank
                # the absent ones instead of leaving them literal in the
                # prompt. One the caller supplied itself is kept.
                for name in MEMORY_DATA_VARIABLES:
                    if name != "memory_context" and name not in values:
                        values[name] = ""
            else:
                # The slot-level policy lives behind build_memory_context_result;
                # a blocked slot yields an empty result, so nothing is injected.
                result = _auto_memory_context(
                    ctx,
                    workspace_id,
                    artifact_id,
                    entity_type,
                    data_kwargs,
                    slot_name,
                    config_values,
                )
                if result is None:
                    # Fail-open: no memory, but never a literal placeholder.
                    for name in MEMORY_DATA_VARIABLES:
                        values[name] = ""
                else:
                    values["memory_context"] = result.text
                    values["memory_artifact_context"] = result.sections.get(
                        "artifact", ""
                    )
                    values["memory_workspace_context"] = result.sections.get(
                        "workspace", ""
                    )
                    values["memory_user_context"] = result.sections.get("user", "")
                    values["memory_facts_json"] = (
                        json.dumps(result.facts, ensure_ascii=False)
                        if result.facts
                        else ""
                    )
        # Caller-supplied memory text is untrusted too: neutralise its braces.
        # Builder-rendered values already are (context_builder), and
        # ``memory_facts_json`` is a JSON payload whose braces are structural.
        caller_supplied = set(data_kwargs) & set(MEMORY_DATA_VARIABLES)
        for name in MEMORY_DATA_VARIABLES:
            if name not in values:
                continue
            values[name] = _memory_block(
                values[name],
                neutralise=name in caller_supplied and name != "memory_facts_json",
            )
    return render_template(content, **values)


def unknown_placeholders(
    content: str,
    slot_name: str,
    ctx: AuthContext,
    workspace_id: UUID | str | None = None,
) -> list[str]:
    """Return placeholders in *content* that nothing can ever fill.

    A name counts as known when it is a declared ``data`` variable of
    *slot_name* or a resolvable ``config`` variable. Everything else is
    almost certainly a typo (spec §5) — reported, never blocking.

    On a HARD_OFF slot the :data:`application.prompt_slots.MEMORY_DATA_VARIABLES`
    names count as known as well: :func:`resolve_and_render` blanks them, so
    they are inert rather than unfillable (Plan A T-A1-1).
    """
    known = set(get_slot_data_variables(slot_name))
    if is_memory_hard_off(slot_name):
        known.update(MEMORY_DATA_VARIABLES)
    known.update(resolve_config_values(ctx, workspace_id))
    return [name for name in extract_placeholders(content) if name not in known]


__all__ = [
    "PLACEHOLDER_PATTERN",
    "PromptSlotNotFoundError",
    "extract_placeholders",
    "render_template",
    "resolve_and_render",
    "resolve_config_values",
    "resolve_template_content",
    "try_resolve_template_content",
    "unknown_placeholders",
]
