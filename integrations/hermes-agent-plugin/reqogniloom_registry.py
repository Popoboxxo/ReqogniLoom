"""Multi-server registry for the reqogniloom plugin.

``$HERMES_HOME/reqogniloom/servers.json`` — one small JSON file listing the
ReqogniLoom instances this install can talk to, which one is active, and the
credentials that belong to each. Written under a best-effort exclusive lock and
mode ``0600``, in the same spirit as ``reqogniloom_state.py``'s ``state.json``:
the writers are separate short-lived processes (every ``/reqogniloom``
invocation, the dashboard's request handlers, the detached capture worker).

Why a file and not environment variables: a server has to be addable from the
dashboard UI while the process keeps running. Environment variables of the
already-running host process cannot be extended after start, so a var-only
scheme would force a gateway restart per server. Environment variables keep two
roles:

* they *seed* the registry on first use (an install that only ever set
  ``REQOGNILOOM_BASE_URL``/``REQOGNILOOM_API_KEY`` migrates itself, see
  :func:`ensure_migrated`);
* an entry may *reference* one instead of storing a key, via
  ``api_key_source: "env"`` + ``api_key_env: "NAME"`` — then the environment
  wins for that entry and the file holds no secret for it.

Layout::

    {
      "registry_version": 1,
      "write_gate": true,
      "active": "qs",
      "servers": [
        {
          "id": "qs",
          "name": "QS 172.20.5.120",
          "base_url": "http://172.20.5.120:8001",
          "api_key": "reqlo_…",              # agent principal (writes → "proposed")
          "api_key_source": "file",          # "file" | "env"
          "api_key_env": null,               # name of the env var when source=="env"
          "user_api_key": "reqlo_…",         # human principal (approve-class tools)
          "user_api_key_source": "file",
          "user_api_key_env": null,
          "default_workspace_id": null,
          "last_workspace_id": null,
          "verify": {"reachable": true, "app_version": "1.8.0-beta.21",
                     "tool_count": 248, "checked_at": "2026-10-18T10:00:00Z"}
        }
      ]
    }

Credentials never leave this module's :func:`resolve_credentials` — the
dashboard API serialises entries with :func:`public_server`, which reports only
*whether* a key exists and *where it comes from*, never its value.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

REGISTRY_VERSION = 1
REGISTRY_FILENAME = "servers.json"

#: Credentials in this file must not be world/group readable.
FILE_MODE = 0o600

#: Seconds to wait for the registry lock before proceeding unlocked. Every
#: writer is a short local read-modify-write; a lost update would drop a server
#: entry, so the caller is told when the lock was not taken.
LOCK_TIMEOUT_SECONDS = 5.0

#: Server ids are used in file contents, dashboard URLs and slash commands, so
#: they stay in a narrow, URL- and shell-safe alphabet.
SERVER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

#: Env variables that seed the registry on migration.
ENV_BASE_URL = "REQOGNILOOM_BASE_URL"
ENV_API_KEY = "REQOGNILOOM_API_KEY"

#: Id of the entry created from the environment on migration.
DEFAULT_SERVER_ID = "default"
DEFAULT_SERVER_NAME = "default (from environment)"

#: The ReqogniLoom default the client falls back to when nothing is configured.
FALLBACK_BASE_URL = "http://localhost:8001"


class RegistryError(RuntimeError):
    """A registry operation that cannot be carried out as asked.

    Raised for an unknown server id, an invalid id/base URL, or a request that
    would leave the registry without an active server it needs. The slash
    command and the dashboard API both render it as a readable message rather
    than letting it escape.
    """


# --------------------------------------------------------------------------
# paths / locking
# --------------------------------------------------------------------------


def hermes_home() -> Path:
    """``$HERMES_HOME`` when set, else ``~/.hermes`` (resolved at call time)."""
    val = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(val) if val else Path.home() / ".hermes"


def registry_path() -> Path:
    return hermes_home() / "reqogniloom" / REGISTRY_FILENAME


def _empty_registry() -> Dict[str, Any]:
    return {"registry_version": REGISTRY_VERSION, "write_gate": True, "active": None, "servers": []}


def load_registry() -> Dict[str, Any]:
    """Current registry, or an empty one for a missing/corrupt file.

    A corrupt file reads as "no servers" on purpose: the alternative is the
    plugin refusing to start until an operator deletes a file they cannot see
    from inside Hermes. The unreadable copy is kept next to it as
    ``servers.json.bad`` so nothing is lost silently.
    """
    path = registry_path()
    if not path.exists():
        return _empty_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("reqogniloom registry unreadable (%s); starting from empty", exc)
        try:
            path.replace(path.with_suffix(".json.bad"))
        except OSError:
            pass
        return _empty_registry()
    if not isinstance(data, dict):
        return _empty_registry()
    servers = data.get("servers")
    registry = _empty_registry()
    registry.update(data)
    registry["servers"] = [s for s in servers if isinstance(s, dict)] if isinstance(servers, list) else []
    registry["registry_version"] = REGISTRY_VERSION
    registry.setdefault("write_gate", True)
    return registry


def save_registry(registry: Dict[str, Any]) -> None:
    """Replace the registry atomically, mode ``0600``, directory ``0700``."""
    path = registry_path()
    _ensure_registry_dir()
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        # Create the temp file already restrictive: this file holds every
        # server's keys, and a world-readable window between write and chmod is
        # exactly the exposure the mode is there to prevent.
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(registry, indent=2, sort_keys=True))
        os.replace(tmp, path)
        os.chmod(path, FILE_MODE)
    except OSError as exc:
        # An unwritable home is a configuration problem, not a crash: the
        # dashboard renders RegistryError as a readable message instead of a 500.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise RegistryError(f"cannot write {path}: {exc}") from exc


def _ensure_registry_dir(path: Optional[Path] = None) -> Path:
    """The registry directory, created (and kept) mode ``0700``.

    Every writer goes through here: the file that holds the credentials must not
    sit in a world-traversable directory, and `mkdir(exist_ok=True, mode=...)`
    alone does not fix a directory some other writer created first.
    """
    directory = (path or registry_path()).parent
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


@contextmanager
def registry_lock(timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[bool]:
    """Best-effort exclusive lock next to the registry file.

    Yields ``True`` when the lock was taken and ``False`` on timeout; a caller
    that cannot lock proceeds, because blocking a slash command on a stale lock
    is worse than a last-writer-wins race on a file that holds a handful of
    entries.
    """
    lock_path = registry_path().with_suffix(".json.lock")
    _ensure_registry_dir(lock_path)
    deadline = time.monotonic() + timeout
    fd: Optional[int] = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                logger.warning("reqogniloom registry lock timed out; proceeding unlocked")
                yield False
                return
            time.sleep(0.05)
        except OSError:
            yield False
            return
    try:
        yield True
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            lock_path.unlink()
        except OSError:
            pass


def update_registry(mutate: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """Locked read-modify-write; ``mutate`` returns the new registry or ``None``."""
    with registry_lock():
        registry = load_registry()
        result = mutate(registry)
        new_registry = registry if result is None else result
        save_registry(new_registry)
        return new_registry


# --------------------------------------------------------------------------
# validation helpers
# --------------------------------------------------------------------------


def validate_server_id(server_id: str) -> str:
    """Return the normalised id, or raise :class:`RegistryError`."""
    candidate = (server_id or "").strip().lower()
    if not SERVER_ID_RE.match(candidate):
        raise RegistryError(
            f"invalid server id {server_id!r}: use 1-32 characters from [a-z0-9-_], "
            f"starting with a letter or digit (e.g. 'qs')"
        )
    return candidate


def validate_base_url(value: str) -> str:
    """Return the normalised base URL (no trailing slash), or raise."""
    candidate = (value or "").strip()
    if not candidate.startswith(("http://", "https://")):
        raise RegistryError(
            f"invalid base URL {value!r}: expected an http:// or https:// URL, "
            f"e.g. http://localhost:8001"
        )
    return candidate.rstrip("/")


def _trim(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


#: Credentials are only ever read from variables the plugin owns. An arbitrary
#: name would turn the server panel into an environment-variable exfiltration
#: channel: a new entry could name ``AWS_SECRET_ACCESS_KEY``, and the very next
#: health probe would send that value as ``X-API-Key`` to whatever ``base_url``
#: the same request supplied.
ALLOWED_KEY_ENV_PREFIXES = ("REQOGNILOOM_API_KEY", "REQOGNILOOM_USER_API_KEY")


def validate_key_env(value: Optional[str]) -> Optional[str]:
    """Return a permitted environment variable name, or ``None``."""
    name = _trim(value)
    if name is None:
        return None
    if not re.match(r"^[A-Z][A-Z0-9_]*$", name) or not name.startswith(ALLOWED_KEY_ENV_PREFIXES):
        raise RegistryError(
            f"refusing environment variable {value!r}: only names starting with "
            f"{' or '.join(ALLOWED_KEY_ENV_PREFIXES)} may hold a server credential"
        )
    return name


# --------------------------------------------------------------------------
# entry construction / lookup
# --------------------------------------------------------------------------


def _new_entry(
    server_id: str,
    name: Optional[str] = None,
    *,
    base_url: str,
    api_key: Optional[str] = None,
    api_key_env: Optional[str] = None,
    user_api_key: Optional[str] = None,
    user_api_key_env: Optional[str] = None,
    default_workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """One normalised registry entry (internal; keys may be present)."""
    entry: Dict[str, Any] = {
        "id": server_id,
        "name": _trim(name) or server_id,
        "base_url": base_url,
        "api_key": None,
        "api_key_source": "none",
        "api_key_env": None,
        "user_api_key": None,
        "user_api_key_source": "none",
        "user_api_key_env": None,
        "default_workspace_id": _trim(default_workspace_id),
        "last_workspace_id": None,
        "verify": None,
    }
    if api_key_env:
        entry["api_key_source"] = "env"
        entry["api_key_env"] = validate_key_env(api_key_env)
    elif api_key:
        entry["api_key_source"] = "file"
        entry["api_key"] = api_key
    if user_api_key_env:
        entry["user_api_key_source"] = "env"
        entry["user_api_key_env"] = validate_key_env(user_api_key_env)
    elif user_api_key:
        entry["user_api_key_source"] = "file"
        entry["user_api_key"] = user_api_key
    return entry


def find_server(registry: Dict[str, Any], server_id: str) -> Optional[Dict[str, Any]]:
    wanted = (server_id or "").strip().lower()
    for entry in registry.get("servers", []):
        if isinstance(entry, dict) and str(entry.get("id", "")).lower() == wanted:
            return entry
    return None


def get_server(server_id: str, registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One entry by id (keys included), or raise :class:`RegistryError`."""
    reg = registry if registry is not None else load_registry()
    entry = find_server(reg, server_id)
    if entry is None:
        known = ", ".join(sorted(str(s.get("id")) for s in reg.get("servers", []))) or "none"
        raise RegistryError(f"unknown server {server_id!r}; configured: {known}")
    return entry


def active_server(registry: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The active entry, or ``None`` when the registry has none.

    ``None`` is a legitimate state — an install that has never configured a
    server still runs on the environment/default path.
    """
    reg = registry if registry is not None else load_registry()
    active = _trim(reg.get("active"))
    if active:
        entry = find_server(reg, active)
        if entry is not None:
            return entry
    servers = [s for s in reg.get("servers", []) if isinstance(s, dict)]
    if len(servers) == 1:
        # A single configured server is unambiguous: never make the user pick.
        return servers[0]
    return None


# --------------------------------------------------------------------------
# credential resolution
# --------------------------------------------------------------------------


def resolve_credentials(entry: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """``(api_key, user_api_key)`` for one entry, environment included.

    An entry with ``*_source: "env"`` takes the value from the environment at
    call time (so a rotated key in ``.env`` applies without touching the file);
    a ``"file"`` entry uses the stored value. Missing values come back as
    ``None`` rather than raising — the caller decides whether a key is
    mandatory (a read against a keyless server fails later with the client's own
    actionable message).
    """
    if not entry:
        return None, None
    api_key: Optional[str] = None
    if entry.get("api_key_source") == "env":
        api_key = _trim(os.environ.get(_trim(entry.get("api_key_env")) or ""))
    else:
        api_key = _trim(entry.get("api_key"))
    user_key: Optional[str] = None
    if entry.get("user_api_key_source") == "env":
        user_key = _trim(os.environ.get(_trim(entry.get("user_api_key_env")) or ""))
    else:
        user_key = _trim(entry.get("user_api_key"))
    return api_key, user_key


# --------------------------------------------------------------------------
# public projection (never contains a key)
# --------------------------------------------------------------------------


def public_server(entry: Dict[str, Any], registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Serialisable view of one entry for API/UI use — **no key values**.

    Reports only *whether* each credential resolves and *where it comes from*,
    which is what the dashboard needs to render "key: env REQOGNILOOM_API_KEY_x"
    or "no key configured" without ever handing a secret to the browser.

    ``active`` comes from the resolver (:func:`active_server`), not from a
    literal comparison with the stored pointer: a registry with exactly one
    server and no explicit ``active`` is used by every call, so the UI has to
    mark that server — otherwise the tab shows "no server selected" while all
    traffic goes to it.
    """
    reg = registry if registry is not None else load_registry()
    current = active_server(dict(reg, active=reg.get("active")))
    api_key, user_key = resolve_credentials(entry)
    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "base_url": entry.get("base_url"),
        "active": current is not None and str(current.get("id")) == str(entry.get("id")),
        "has_api_key": bool(api_key),
        "api_key_source": entry.get("api_key_source") or "none",
        "api_key_env": entry.get("api_key_env"),
        "has_user_api_key": bool(user_key),
        "user_api_key_source": entry.get("user_api_key_source") or "none",
        "user_api_key_env": entry.get("user_api_key_env"),
        "default_workspace_id": entry.get("default_workspace_id"),
        "last_workspace_id": entry.get("last_workspace_id"),
        "verify": entry.get("verify"),
    }


def public_registry(registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Whole registry for API/UI use: entries + ``active`` + ``write_gate``."""
    reg = registry if registry is not None else load_registry()
    return {
        "registry_version": REGISTRY_VERSION,
        "active": reg.get("active"),
        "write_gate": bool(reg.get("write_gate", True)),
        "path": str(registry_path()),
        "servers": [public_server(entry, reg) for entry in reg.get("servers", []) if isinstance(entry, dict)],
    }


# --------------------------------------------------------------------------
# mutation API
# --------------------------------------------------------------------------


def ensure_migrated() -> Dict[str, Any]:
    """Create the registry file if it does not exist yet.

    Called by the surfaces that intend to *manage* servers (the slash command's
    ``server`` group and the dashboard API) — never implicitly from client
    construction, which must stay side-effect free.

    Migration rules:

    * ``REQOGNILOOM_BASE_URL`` and ``REQOGNILOOM_API_KEY`` set → one entry
      ``default`` referencing both environment variables (no secret is copied
      into the file), active.
    * only ``REQOGNILOOM_BASE_URL`` set → one entry ``default`` without a key.
    * nothing set → an empty registry; the UI shows its configuration state.

    An existing file is returned untouched: once it exists it is authoritative.
    """
    path = registry_path()
    if path.exists():
        return load_registry()

    env_base = _trim(os.environ.get(ENV_BASE_URL))
    env_key = _trim(os.environ.get(ENV_API_KEY))
    entry: Optional[Dict[str, Any]] = None
    if env_base:
        try:
            base_url = validate_base_url(env_base)
        except RegistryError as exc:
            logger.warning("ignoring %s during migration: %s", ENV_BASE_URL, exc)
            base_url = ""
        if base_url:
            entry = _new_entry(
                DEFAULT_SERVER_ID,
                DEFAULT_SERVER_NAME,
                base_url=base_url,
                api_key_env=ENV_API_KEY if env_key else None,
            )

    def mutate(reg: Dict[str, Any]) -> Dict[str, Any]:
        # Re-checked inside the lock: two first-run requests (an env-only install
        # opening the tab while a slash command migrates) must not both create the
        # entry, and a fixed temp name would let them interleave on one file.
        if reg.get("servers"):
            return reg
        if entry is None:
            return reg
        return {**reg, "servers": [entry], "active": DEFAULT_SERVER_ID}

    try:
        return update_registry(mutate)
    except RegistryError as exc:  # e.g. an unwritable home
        logger.warning("could not create the registry: %s", exc)
        return load_registry()


def set_write_gate(enabled: bool) -> Dict[str, Any]:
    """Global write switch for the dashboard (default on)."""
    return update_registry(lambda reg: {**reg, "write_gate": bool(enabled)})


def write_gate_enabled(registry: Optional[Dict[str, Any]] = None) -> bool:
    reg = registry if registry is not None else load_registry()
    return bool(reg.get("write_gate", True))


def add_server(
    server_id: str,
    base_url: str,
    *,
    name: Optional[str] = None,
    api_key: Optional[str] = None,
    api_key_env: Optional[str] = None,
    user_api_key: Optional[str] = None,
    user_api_key_env: Optional[str] = None,
    default_workspace_id: Optional[str] = None,
    activate: bool = False,
) -> Dict[str, Any]:
    """Add one server. Raises :class:`RegistryError` for an invalid/duplicate id."""
    sid = validate_server_id(server_id)
    url = validate_base_url(base_url)
    entry = _new_entry(
        sid,
        name,
        base_url=url,
        api_key=api_key,
        api_key_env=api_key_env,
        user_api_key=user_api_key,
        user_api_key_env=user_api_key_env,
        default_workspace_id=default_workspace_id,
    )

    def mutate(reg: Dict[str, Any]) -> Dict[str, Any]:
        if find_server(reg, sid) is not None:
            raise RegistryError(f"server {sid!r} already exists")
        servers = list(reg.get("servers", [])) + [entry]
        active = reg.get("active")
        if activate or not active:
            active = sid
        return {**reg, "servers": servers, "active": active}

    return update_registry(mutate)


def update_server(server_id: str, **fields: Any) -> Dict[str, Any]:
    """Patch one entry. ``None`` values are ignored; ``""`` clears a field.

    Recognised fields: ``name``, ``base_url``, ``api_key``, ``api_key_env``,
    ``user_api_key``, ``user_api_key_env``, ``default_workspace_id``. Setting a
    key clears the other key source (a value or a variable, never both).
    """
    sid = validate_server_id(server_id)

    def mutate(reg: Dict[str, Any]) -> Dict[str, Any]:
        entry = find_server(reg, sid)
        if entry is None:
            raise RegistryError(f"unknown server {sid!r}")
        updated = dict(entry)
        if fields.get("name") is not None:
            updated["name"] = _trim(fields["name"]) or sid
        if fields.get("base_url") is not None:
            updated["base_url"] = validate_base_url(str(fields["base_url"]))
        if fields.get("default_workspace_id") is not None:
            updated["default_workspace_id"] = _trim(fields["default_workspace_id"])
        if fields.get("api_key_env") is not None:
            env_name = validate_key_env(fields["api_key_env"])
            updated["api_key_source"] = "env" if env_name else "none"
            updated["api_key_env"] = env_name
            updated["api_key"] = None
        if fields.get("api_key") is not None:
            value = _trim(fields["api_key"])
            updated["api_key_source"] = "file" if value else "none"
            updated["api_key"] = value
            updated["api_key_env"] = None
        if fields.get("user_api_key_env") is not None:
            env_name = validate_key_env(fields["user_api_key_env"])
            updated["user_api_key_source"] = "env" if env_name else "none"
            updated["user_api_key_env"] = env_name
            updated["user_api_key"] = None
        if fields.get("user_api_key") is not None:
            value = _trim(fields["user_api_key"])
            updated["user_api_key_source"] = "file" if value else "none"
            updated["user_api_key"] = value
            updated["user_api_key_env"] = None
        servers = [
            updated if str(s.get("id")) == sid else s for s in reg.get("servers", []) if isinstance(s, dict)
        ]
        return {**reg, "servers": servers}

    return update_registry(mutate)


def remove_server(server_id: str) -> Dict[str, Any]:
    """Drop one entry; the active pointer moves to the first survivor."""
    sid = validate_server_id(server_id)

    def mutate(reg: Dict[str, Any]) -> Dict[str, Any]:
        servers = [s for s in reg.get("servers", []) if isinstance(s, dict)]
        remaining = [s for s in servers if str(s.get("id")) != sid]
        if len(remaining) == len(servers):
            raise RegistryError(f"unknown server {sid!r}")
        active = reg.get("active")
        if str(active or "") == sid:
            active = str(remaining[0].get("id")) if remaining else None
        return {**reg, "servers": remaining, "active": active}

    return update_registry(mutate)


def set_active(server_id: str) -> Dict[str, Any]:
    """Make one server the active one."""
    sid = validate_server_id(server_id)

    def mutate(reg: Dict[str, Any]) -> Dict[str, Any]:
        if find_server(reg, sid) is None:
            raise RegistryError(f"unknown server {sid!r}")
        return {**reg, "active": sid}

    return update_registry(mutate)


def record_verify(server_id: str, verify: Dict[str, Any]) -> Dict[str, Any]:
    """Store the outcome of one health probe on the entry."""
    sid = validate_server_id(server_id)

    def mutate(reg: Dict[str, Any]) -> Dict[str, Any]:
        entry = find_server(reg, sid)
        if entry is None:
            raise RegistryError(f"unknown server {sid!r}")
        updated = dict(entry)
        updated["verify"] = verify
        servers = [
            updated if str(s.get("id")) == sid else s for s in reg.get("servers", []) if isinstance(s, dict)
        ]
        return {**reg, "servers": servers}

    return update_registry(mutate)


def remember_workspace(server_id: str, workspace_id: str) -> None:
    """Best-effort: remember the workspace the user last worked in *per server*.

    Never raises and never blocks a caller: a lost memory here costs one
    re-selection in the UI, nothing else.
    """
    try:
        sid = validate_server_id(server_id)
    except RegistryError:
        return
    if not workspace_id:
        return

    def mutate(reg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        entry = find_server(reg, sid)
        if entry is None:
            return None
        updated = dict(entry)
        updated["last_workspace_id"] = workspace_id
        servers = [
            updated if str(s.get("id")) == sid else s for s in reg.get("servers", []) if isinstance(s, dict)
        ]
        return {**reg, "servers": servers}

    try:
        update_registry(mutate)
    except (RegistryError, OSError):
        # OSError too: this runs after a successful mutation on the write path,
        # and a full disk must not turn a landed write into a reported failure.
        return


def env_seed_note() -> str:
    """One-line hint for an empty registry, naming the variables that seed it."""
    return (
        f"No server configured yet. Add one with `/reqogniloom server add <id> <base-url>` "
        f"or set {ENV_BASE_URL} (and {ENV_API_KEY}) and run any /reqogniloom command once."
    )


def format_servers(registry: Optional[Dict[str, Any]] = None) -> str:
    """Human-readable server list for the slash command."""
    reg = registry if registry is not None else load_registry()
    entries = [s for s in reg.get("servers", []) if isinstance(s, dict)]
    if not entries:
        return env_seed_note()
    active = str(reg.get("active") or "")
    lines = [f"ReqogniLoom servers ({len(entries)}), active: {active or '—'}:"]
    for index, entry in enumerate(entries, start=1):
        view = public_server(entry, reg)
        marker = "*" if view["active"] else " "
        key_part = (
            f"agent-key: {view['api_key_source']}"
            + (f" ({view['api_key_env']})" if view["api_key_env"] else "")
            if view["has_api_key"]
            else "agent-key: missing"
        )
        human_part = "human-key: yes" if view["has_user_api_key"] else "human-key: no"
        reach = view.get("verify") or {}
        if reach:
            state = "reachable" if reach.get("reachable") else "unreachable"
            reach_part = f"{state}, {reach.get('app_version') or '?'}, {reach.get('tool_count', '?')} tools"
        else:
            reach_part = "not checked"
        lines.append(
            f"{marker} {view['id']:<12} {view['base_url']:<32} {key_part}, {human_part}, {reach_part}"
        )
    lines.append(
        "Switch with `/reqogniloom server use <id>`, check with `/reqogniloom server test [id]`."
    )
    return "\n".join(lines)


def probe_server(client: Any, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Health-probe one server through a client and store the outcome.

    Two independent channels, deliberately: ``GET /api/v1/version/`` is public
    (proves reachability without needing the key to be valid) and ``tools/list``
    with the entry's key (proves the key works AND gives the tool count the UI
    shows). A failing key must not read as "server down".
    """
    started = time.monotonic()
    api_key, _ = resolve_credentials(entry)
    result: Dict[str, Any] = {
        "reachable": False,
        "auth_ok": False,
        "app_version": None,
        "tool_count": None,
        "latency_ms": None,
        "error": None,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        payload = client.version()
        if isinstance(payload, dict):
            result["app_version"] = payload.get("version") or payload.get("app_version")
        result["reachable"] = True
    except Exception as exc:  # ReqogniLoomError or transport — both are "unreachable"
        result["error"] = str(exc)
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        return result
    if not api_key:
        # No credential *for this entry* — say so instead of forwarding the
        # client's global message ("export REQOGNILOOM_API_KEY"), which names the
        # wrong variable on a multi-server install.
        result["error"] = (
            f"no credential configured for server {entry.get('id')!r} "
            f"— set its api_key or api_key_env in the server panel"
        )
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        return result
    try:
        tools = client.tools_list(api_key=api_key)
        result["auth_ok"] = True
        result["tool_count"] = len(tools)
    except Exception as exc:
        result["error"] = str(exc)
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result
