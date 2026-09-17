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

``render_template`` keeps ``AiDerivationService._render``'s exact semantics —
a per-placeholder ``str.replace`` loop, never ``str.format``/Jinja2 — so JSON
braces inside a customised prompt body survive untouched and an omitted
placeholder is left literally in place (REQ-046).

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.models import PROMPT_VARIABLE_KIND_CONFIG

from application.base import ValidationError
from application.prompt_slots import get_slot_data_variables, get_slot_default
from application.prompt_template_versioning import get_active_template
from application.prompt_variable_versioning import list_active_variables
from application.prompt_variables import (
    PROMPT_VARIABLE_DEFAULTS,
    VariableTypeError,
    deserialize_variable_value,
)

logger = logging.getLogger(__name__)

#: Matches ``{name}`` placeholders only — a JSON object like ``{"a": 1}`` has
#: a quote directly after the brace and therefore never matches.
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}")


class PromptSlotNotFoundError(ValidationError):
    """Raised when a slot has neither an active row nor a factory default."""


def _as_uuid(workspace_id: UUID | str | None) -> Optional[UUID]:
    """Coerce a workspace id to ``UUID``; ``None`` stays ``None``."""
    if workspace_id is None:
        return None
    if isinstance(workspace_id, UUID):
        return workspace_id
    return UUID(str(workspace_id))


def extract_placeholders(content: str) -> List[str]:
    """Return every ``{name}`` placeholder in *content*, in first-seen order."""
    seen: List[str] = []
    for match in PLACEHOLDER_PATTERN.finditer(content or ""):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def render_template(content: str, /, **values: Any) -> str:
    """Substitute ``{name}`` placeholders without touching other braces.

    *content* is positional-only: ``PromptVariable.name`` is deliberately
    unrestricted (an admin can register a ``config`` variable called
    ``content`` at runtime — that is the whole point of the catalog), so a
    keyword parameter named ``content`` here would collide with a same-named
    value in ``**values`` and raise ``TypeError: got multiple values for
    argument 'content'`` on every render call for that tenant.
    """
    rendered = content
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def try_resolve_template_content(
    slot_name: str, ctx: AuthContext, workspace_id: UUID | str | None = None
) -> Optional[str]:
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
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
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
    values: Dict[str, Any] = {
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


def resolve_and_render(
    slot_name: str,
    ctx: AuthContext,
    workspace_id: UUID | str | None = None,
    *,
    config_overrides: Optional[Dict[str, Any]] = None,
    **data_kwargs: Any,
) -> str:
    """Resolve *slot_name*'s body and render it with config + data values.

    ``data_kwargs`` win on a name collision with a ``config`` variable — the
    code-supplied artifact data is always the more specific answer.

    ``workspace_id`` is, like in :func:`resolve_template_content` and
    :func:`resolve_config_values`, never defaulted from ``ctx.workspace_id`` —
    it must be supplied by the caller for the entity actually being rendered.

    Raises:
        PromptSlotNotFoundError: See :func:`resolve_template_content`.
    """
    content = resolve_template_content(slot_name, ctx, workspace_id)
    config_values = resolve_config_values(ctx, workspace_id, overrides=config_overrides)
    return render_template(content, **{**config_values, **data_kwargs})


def unknown_placeholders(
    content: str,
    slot_name: str,
    ctx: AuthContext,
    workspace_id: UUID | str | None = None,
) -> List[str]:
    """Return placeholders in *content* that nothing can ever fill.

    A name counts as known when it is a declared ``data`` variable of
    *slot_name* or a resolvable ``config`` variable. Everything else is
    almost certainly a typo (spec §5) — reported, never blocking.
    """
    known = set(get_slot_data_variables(slot_name))
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
