"""ReqogniLoom dashboard plugin backend.

Mounted at ``/api/plugins/reqogniloom/`` by the Hermes dashboard.

Three groups of routes:

* **read** — the original dashboard surface (counts, workspaces, interviews,
  version) plus the live tool catalogue;
* **servers** — CRUD, activation and health probes for the multi-server
  registry (``reqogniloom_registry``), shared with ``/reqogniloom server …``;
* **write** — a two-phase gate in front of *every* tool the MCP server
  publishes: ``/write/preview`` classifies the call and issues a token bound to
  server+tool+arguments, ``/write`` executes it.

Every handler is sync (the shared client uses blocking ``urllib``; FastAPI runs
sync handlers in its threadpool) and every *domain* failure — backend
unreachable, key rejected, confirmation mismatch, gate closed — stays ``200``
with ``{"error": …}`` so the tab can render it instead of a 500.

Authentication
--------------
The plugin runs no server of its own: it returns an ``APIRouter`` that an
external Hermes dashboard mounts, and neither plugin.yaml nor
dashboard/manifest.json carries a port, bind address, ``secrets`` or ``env``
field, so the host hands the plugin no credential. The host dashboard's own auth
is therefore the only gate on this surface — the plugin adds no inbound second
factor. What it does add is an outbound one: per server an agent key (writes are
born as ``proposed`` artifacts) and an optional human key, needed by the
approval-class tools, which the server refuses for an agent principal.

The ``/write`` token is **not** part of that boundary — same host, same cookie.
It is an anti-fat-finger guard that lives in the backend (not the browser) so the
UI cannot skip the preview step by accident: the token is bound to the exact
arguments, so anything that changed between preview and execution is refused.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter
except Exception:  # Allows local unit tests without dashboard dependencies.

    class APIRouter:  # type: ignore
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

        def post(self, *_args, **_kwargs):
            return lambda fn: fn

        def patch(self, *_args, **_kwargs):
            return lambda fn: fn

        def delete(self, *_args, **_kwargs):
            return lambda fn: fn


# The plugin modules live one directory up (the plugin root), alongside
# plugin.yaml and __init__.py — dashboard/ is not itself a Python package
# (matches plugins/hermes-achievements/dashboard/'s flat layout), so a relative
# import isn't available; put the plugin root on sys.path instead.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

import reqogniloom_registry as registry  # noqa: E402
import reqogniloom_tools as tools  # noqa: E402
from reqogniloom_client import ReqogniLoomClient, ReqogniLoomError, resolve_workspace_id  # noqa: E402

router = APIRouter()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _client_for(server_id: Optional[str] = None) -> ReqogniLoomClient:
    """A client for one registry server, or for the active one.

    An explicit ``server_id`` yields a client bound to exactly that entry
    (explicit target + explicit credentials), so a request naming server B can
    never borrow server A's key from the environment.

    The entry's URL is re-checked here, not only when it was written: the key of
    this entry is about to be sent to that host, and ``servers.json`` is an
    editable file. A URL pointing at a metadata service or a link-local address is
    refused at the moment of use.
    """
    if not server_id:
        return ReqogniLoomClient()
    entry = registry.get_server(server_id)
    base_url = str(entry.get("base_url") or "")
    reason = registry.forbidden_host_reason(base_url)
    if reason:
        raise registry.RegistryError(
            f"server {server_id!r} points at {base_url!r}: {reason} — refusing to send its key"
        )
    api_key, user_api_key = registry.resolve_credentials(entry)
    return ReqogniLoomClient(
        base_url=base_url,
        api_key=api_key,
        user_api_key=user_api_key,
        server_id=str(entry.get("id") or ""),
    )


def _server_key(client: ReqogniLoomClient, server_id: Optional[str] = None) -> str:
    """The catalogue cache key for one target — always the normalised id.

    ``GET /tools?server_id=QS`` and ``?server_id=qs`` are the same server, so they
    have to hit the same cache entry; the registry lower-cases on the way in, and
    the cache key has to agree with it.
    """
    if server_id:
        try:
            return registry.validate_server_id(server_id)
        except registry.RegistryError:
            return server_id
    return str(getattr(client, "server_id", "") or getattr(client, "base_url", "") or "default")


def _error(exc: Exception) -> Dict[str, Any]:
    """One failure shape for the whole surface: message + optional code/retryable.

    ``status`` is the HTTP status the *ReqogniLoom backend* answered with, when
    the failure came from a request at all (403 for a key that lacks scope, 5xx
    for a degraded backend, ``None`` for a registry/validation refusal here).
    It is additive — ``error``/``code``/``retryable`` keep their meaning, so an
    existing consumer is unaffected — and it is what lets the tab say "permission
    denied (HTTP 403)" instead of only echoing a message that used to be dropped
    as an empty list (issue #1443).
    """
    payload: Dict[str, Any] = {"error": str(exc)}
    code = getattr(exc, "code", None)
    if code is not None:
        payload["code"] = code
    if getattr(exc, "retryable", False):
        payload["retryable"] = True
    status = getattr(exc, "status", None)
    if isinstance(status, int) and not isinstance(status, bool):
        payload["status"] = status
    return payload


def _payload_dict(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _catalogue_of(client: ReqogniLoomClient, server_id: Optional[str], refresh: bool) -> Dict[str, Any]:
    """The catalogue of the client's server (cached, see reqogniloom_tools)."""
    return tools.fetch_catalogue(client, server_key=_server_key(client, server_id), refresh=refresh)


def _tool_entry(client: ReqogniLoomClient, server_id: Optional[str], tool_name: str) -> Dict[str, Any]:
    catalogue = _catalogue_of(client, server_id, refresh=False)
    entry = tools.find_tool(catalogue, tool_name)
    if entry is None:
        raise ReqogniLoomError(f"unknown tool {tool_name!r} on this server")
    return entry


def _probe_and_record(server_id: str) -> Dict[str, Any]:
    """Probe one entry and store the outcome on it (best effort).

    The probe asks the server for its tool list, so it is also the moment the
    catalogue may have changed (server upgrade): the cache is dropped afterwards,
    otherwise "Test" and the Tools view disagree for up to the cache TTL.
    """
    try:
        entry = registry.get_server(server_id)
        verify = registry.probe_server(_client_for(server_id), entry)
        registry.record_verify(server_id, verify)
        tools.invalidate()
        return verify
    except (registry.RegistryError, ReqogniLoomError) as exc:
        return {"reachable": False, "auth_ok": False, "error": str(exc)}


# --------------------------------------------------------------------------
# read: the original dashboard surface
# --------------------------------------------------------------------------


@router.get("/stats")
def stats(workspace_id: str = "", server_id: str = "") -> Dict[str, Any]:
    """Counts for the resolved workspace; backend failures stay 200+error.

    Read-only: the remembered workspace is written by ``/workspace-selected`` and
    by ``/write``, never by a GET. A GET that mutates shared state is not
    cacheable, not idempotent and reachable by any prefetch.
    """
    try:
        client = _client_for(server_id or None)
        ws_id = resolve_workspace_id(client, workspace_id or None)
        return client.stats(ws_id)
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return _error(exc)


@router.get("/workspaces")
def workspaces(server_id: str = "") -> Dict[str, Any]:
    """Workspaces visible to the configured API key."""
    try:
        client = _client_for(server_id or None)
        return {"workspaces": client.list_workspaces()}
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return _error(exc)


@router.get("/version")
def version(server_id: str = "") -> Dict[str, Any]:
    """ReqogniLoom build version; backend failures stay 200+error."""
    try:
        client = _client_for(server_id or None)
        return client.version()
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return _error(exc)


@router.get("/interviews")
def interviews(workspace_id: str = "", status: str = "in_progress", server_id: str = "") -> Dict[str, Any]:
    """Interviews of one workspace, defaulting to the open ones.

    A count answers "how many" but not "which", so a session left hanging was
    invisible until it aged out; the tab renders these as detail rows.
    Read-only and best-effort, like the other handlers: a backend failure stays
    200+error.
    """
    try:
        client = _client_for(server_id or None)
        ws_id = resolve_workspace_id(client, workspace_id or None)
        return {"workspace_id": ws_id, "interviews": client.list_interviews(ws_id, status or None)}
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return _error(exc)


# --------------------------------------------------------------------------
# read: tool catalogue
# --------------------------------------------------------------------------


@router.get("/tools")
def tool_catalogue(refresh: int = 0, server_id: str = "") -> Dict[str, Any]:
    """Every tool of the selected server, classified (see reqogniloom_tools).

    ``refresh=1`` bypasses the 300 s cache — the button behind a server upgrade.
    """
    try:
        client = _client_for(server_id or None)
        return _catalogue_of(client, server_id or None, bool(refresh))
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return _error(exc)


@router.get("/tool/{tool_name:path}")
def tool_detail(tool_name: str, server_id: str = "") -> Dict[str, Any]:
    """One tool with its input schema — the form the UI renders."""
    try:
        client = _client_for(server_id or None)
        return {"tool": _tool_entry(client, server_id or None, tool_name)}
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return _error(exc)


# --------------------------------------------------------------------------
# servers
# --------------------------------------------------------------------------


@router.get("/servers")
def list_servers() -> Dict[str, Any]:
    """The registry: entries, active id and the write gate. Never key values."""
    try:
        registry.ensure_migrated()
        return registry.public_registry()
    except registry.RegistryError as exc:
        return _error(exc)


@router.post("/servers")
def add_server(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Add a server and probe it once, so the UI shows health immediately."""
    data = _payload_dict(payload)
    server_id = str(data.get("id") or "")
    try:
        updated = registry.add_server(
            server_id,
            str(data.get("base_url") or ""),
            name=data.get("name"),
            api_key=data.get("api_key"),
            api_key_env=data.get("api_key_env"),
            user_api_key=data.get("user_api_key"),
            user_api_key_env=data.get("user_api_key_env"),
            default_workspace_id=data.get("default_workspace_id"),
            activate=bool(data.get("activate", False)),
        )
    except registry.RegistryError as exc:
        return _error(exc)
    verify = _probe_and_record(server_id)
    view = registry.public_registry(updated)
    # Look the entry up through the registry, not by comparing the *request* id:
    # validate_server_id normalises to lower case, so a request for "QS" would
    # otherwise come back with server: null even though it was created.
    try:
        created = registry.public_server(registry.get_server(server_id, updated), updated)
    except registry.RegistryError:
        created = None
    return {"server": created, "verify": verify, "registry": view}


@router.patch("/servers/{server_id}")
def update_server(server_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Patch one entry. Empty-string values clear a field; absent ones stay."""
    data = _payload_dict(payload)
    fields = {
        key: data[key]
        for key in (
            "name",
            "base_url",
            "api_key",
            "api_key_env",
            "user_api_key",
            "user_api_key_env",
            "default_workspace_id",
        )
        if key in data
    }
    try:
        updated = registry.update_server(server_id, **fields)
    except registry.RegistryError as exc:
        return _error(exc)
    response: Dict[str, Any] = {"registry": registry.public_registry(updated)}
    if "base_url" in fields:
        # The catalogue belongs to the URL, so a changed URL invalidates it; and
        # the registry dropped the entry's keys on purpose (see update_server).
        tools.invalidate()
        response["note"] = (
            "base_url changed — the tool catalogue was reloaded and the stored keys "
            "were cleared. Enter the key for the new host."
        )
    return response


@router.post("/workspace-selected")
def workspace_selected(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Remember the workspace the operator picked, per server.

    Its own POST instead of a GET side effect: the tab selects a workspace for
    convenience, and that memory (``last_workspace_id``) is shared state on disk.
    """
    data = _payload_dict(payload)
    server_id = str(data.get("server_id") or "") or None
    workspace_id = str(data.get("workspace_id") or "")
    if not workspace_id:
        return {"error": "missing 'workspace_id'"}
    try:
        client = _client_for(server_id)
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return _error(exc)
    registry.remember_workspace(_server_key(client, server_id), workspace_id)
    return {"server": _server_key(client, server_id), "workspace_id": workspace_id}


@router.delete("/servers/{server_id}")
def delete_server(server_id: str) -> Dict[str, Any]:
    """Remove one entry; the catalogue cache is dropped with it."""
    try:
        updated = registry.remove_server(server_id)
    except registry.RegistryError as exc:
        return _error(exc)
    tools.invalidate()
    return {"registry": registry.public_registry(updated)}


@router.post("/servers/{server_id}/test")
def test_server(server_id: str) -> Dict[str, Any]:
    """Probe reachability (public version call) and the key (``tools/list``)."""
    try:
        registry.get_server(server_id)
    except registry.RegistryError as exc:
        return _error(exc)
    return {"server_id": server_id, "verify": _probe_and_record(server_id)}


@router.post("/active")
def set_active_server(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Switch the active server.

    The tool catalogue belongs to a server, so it is dropped here: a stale cache
    would keep showing the previous server's tools and tool count.
    """
    data = _payload_dict(payload)
    try:
        updated = registry.set_active(str(data.get("server_id") or ""))
    except registry.RegistryError as exc:
        return _error(exc)
    tools.invalidate()
    return {"registry": registry.public_registry(updated)}


@router.get("/write-gate")
def read_write_gate() -> Dict[str, Any]:
    return {"write_gate": registry.write_gate_enabled()}


@router.post("/write-gate")
def set_write_gate(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Open or close the global write switch (reads are never gated).

    The value must be a real boolean. A missing or malformed ``enabled`` used to
    be coerced with ``bool(...)`` — which turned a truncated body, or the string
    ``"false"``, into *open*: the one switch that guards every mutating tool must
    fail closed, not optimistically.
    """
    data = _payload_dict(payload)
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        return {"error": "'enabled' must be true or false"}
    try:
        updated = registry.set_write_gate(enabled)
    except registry.RegistryError as exc:
        # An unwritable registry must read as a domain failure, not as a 500:
        # the tab renders this message, and on a read-only $HERMES_HOME the
        # operator otherwise sees a traceback for a toggle.
        return _error(exc)
    return {"write_gate": bool(updated.get("write_gate", True))}


# --------------------------------------------------------------------------
# write gate
# --------------------------------------------------------------------------


@router.post("/write/preview")
def write_preview(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Classify a call and issue the token that authorises it.

    Nothing is executed here. The response carries what the confirmation dialog
    needs: the risk class (``normal`` needs a yes, ``destructive`` needs the tool
    name typed), whether the call needs the human key, a compact rendering of the
    arguments, validation problems, and the token.
    """
    data = _payload_dict(payload)
    tool_name = str(data.get("tool") or "")
    raw_arguments = data.get("arguments")
    if raw_arguments is not None and not isinstance(raw_arguments, dict):
        # Silently coercing to {} would execute the *wrong* call (an empty
        # argument set) and report success, which is worse than a refusal.
        return {"error": "'arguments' must be a JSON object"}
    arguments: Dict[str, Any] = raw_arguments or {}
    server_id = str(data.get("server_id") or "") or None
    if not tool_name:
        return {"error": "missing 'tool'"}
    try:
        client = _client_for(server_id)
        resolved_server = _server_key(client, server_id)
        entry = _tool_entry(client, server_id, tool_name)
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return _error(exc)
    risk = entry["risk"]
    human = bool(entry["requires_human"])
    return {
        "tool": tool_name,
        "server": resolved_server,
        "risk": risk,
        "class": entry["class"],
        "destructive": bool(entry["destructive"]),
        "requires_human": human,
        "human_key_available": client.has_user_api_key() if human else True,
        "summary": tools.summarise_arguments(arguments),
        "arguments": arguments,
        "problems": tools.validate_arguments(entry.get("input_schema"), arguments),
        "write_gate": registry.write_gate_enabled(),
        "blocked": bool(entry["class"] == tools.CLASS_MUTATE and not registry.write_gate_enabled()),
        # Issued here, consumed by /write: a token has to come from a preview and
        # can be used once, so a retried or double-submitted mutating call cannot
        # execute twice.
        "confirm_token": tools.issue_confirm_token(resolved_server, tool_name, arguments),
        "typed_confirmation": tool_name if risk == tools.RISK_DESTRUCTIVE else None,
    }


@router.post("/write")
def write(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute one tool call, once the gate has been satisfied.

    Order of refusals, most specific first: missing fields, closed write gate
    (mutating tools only), confirmation mismatch, destructive typed check,
    validation problems, missing human key. Only then does the call reach the
    server.
    """
    data = _payload_dict(payload)
    tool_name = str(data.get("tool") or "")
    raw_arguments = data.get("arguments")
    if raw_arguments is not None and not isinstance(raw_arguments, dict):
        return {"error": "'arguments' must be a JSON object"}
    arguments: Dict[str, Any] = raw_arguments or {}
    server_id = str(data.get("server_id") or "") or None
    token = str(data.get("confirm_token") or "")
    typed = data.get("typed")
    if not tool_name:
        return {"error": "missing 'tool'"}
    try:
        client = _client_for(server_id)
        resolved_server = _server_key(client, server_id)
        entry = _tool_entry(client, server_id, tool_name)
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return _error(exc)

    tool_class = entry["class"]
    risk = entry["risk"]
    if tool_class == tools.CLASS_MUTATE and not registry.write_gate_enabled():
        return {"error": "the write gate is closed for this install — open it in the server panel"}
    if risk == tools.RISK_DESTRUCTIVE and str(typed or "") != tool_name:
        return {"error": f"destructive call: type '{tool_name}' to confirm"}
    problems = tools.validate_arguments(entry.get("input_schema"), arguments)
    if problems:
        return {"error": "; ".join(problems), "problems": problems}
    human = bool(entry["requires_human"])
    principal = "user" if human else "agent"
    if human and not client.has_user_api_key():
        return {
            "error": (
                f"{tool_name} needs the human API key (user_api_key) of server "
                f"{resolved_server}: an agent may not decide its own proposal"
            ),
            "requires_human": True,
            "human_key_available": False,
        }
    # Consumed last, so a failed keystroke (wrong typed name, a validation
    # problem, a missing human key) does not burn the confirmation — but the
    # moment the call is about to go out, the token is gone and a replay of the
    # same body cannot execute twice.
    ok, reason = tools.consume_confirm_token(resolved_server, tool_name, arguments, token)
    if not ok:
        return {"error": reason}
    try:
        result = client.call_tool(tool_name, arguments, principal=principal)
    except (ReqogniLoomError, registry.RegistryError) as exc:
        return {"error": str(exc), "tool": tool_name, "server": resolved_server}
    if isinstance(arguments.get("workspace_id"), str):
        registry.remember_workspace(resolved_server, arguments["workspace_id"])
    return {
        "ok": True,
        "tool": tool_name,
        "server": resolved_server,
        "principal": principal,
        "mutating": tool_class == tools.CLASS_MUTATE,
        "result": result,
    }
