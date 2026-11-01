"""``manage.py honcho_register_webhooks`` — manage Honcho's callback registration.

Plan A T-A4-7. Honcho has **no SDK surface for webhooks** (the capability spike in
``deploy/README.md`` records ``grep -i webhook`` over ``honcho-ai==2.5.1`` finding
nothing), so registration is raw HTTP against the same REST base URL this backend
already talks to::

    POST   /v3/workspaces/{workspace}/webhooks          {"url": ...}
    GET    /v3/workspaces/{workspace}/webhooks
    DELETE /v3/workspaces/{workspace}/webhooks/{id}

The receiver those deliveries reach is
``POST /api/v1/memory/webhooks/honcho/`` (see :mod:`memory.webhooks`).

Read-only by default
--------------------
With no action flag the command **lists** the registered webhooks and writes
nothing — the same "safe default" contract ``honcho_migrate_scopes`` follows.
Registration itself is idempotent anyway: Honcho answers ``200`` for a URL it
already knows and ``201`` for a newly created one, so repeating ``--url`` never
duplicates an endpoint.

``--url`` is validated locally first
------------------------------------
Honcho answers ``422`` for a URL it will not POST to, but that answer arrives
*after* the round trip and only tells the operator "no". :func:`_validate_callback_url`
therefore rejects the same shapes up front, with a message naming the reason:
scheme other than ``http``/``https``, userinfo in the netloc, a port other than
80/443, or a host that resolves to a private/loopback/link-local/reserved/
multicast/unspecified address. This is a **local** check and it rejects rather
than warns — the command is an operator tool, and registering a callback into
the cluster network is never the intent (Honcho would refuse it anyway, so
warning would only defer the same failure). It is not an SSRF defence for this
process: nothing here fetches the URL, it only never registers one that could
only ever be reachable from inside.

Documented failure modes (all reported, none retried)
-----------------------------------------------------
* ``409`` — the per-workspace webhook limit is reached. Remove an endpoint with
  ``--delete`` before registering another.
* ``422`` — the URL is not absolute, or it names a private/loopback/link-local
  IP literal. Honcho refuses to POST into your network, so ``--url`` must be a
  publicly resolvable address (a reverse proxy in front of this backend). The
  local pre-check above catches this shape before the request is sent.
* ``401``/``403`` — the Honcho key is peer- or session-scoped. Registration (like
  every workspace route) needs a **workspace-scoped or admin** ``HONCHO_API_KEY``.
* Timeouts — every request here uses a **30 s** budget and is **never retried**
  (the same budget Honcho's own delivery uses). A timeout is reported as a
  failure and the command exits non-zero; re-running is safe.

Delivery needs three things that registration does NOT check
------------------------------------------------------------
Registration succeeds even when nothing will ever be delivered. For a delivery
to arrive and verify, the Honcho server needs:

1. its own ``WEBHOOK_SECRET`` set (Honcho's variable — **not**
   ``HONCHO_WEBHOOK_SECRET``, which is this side's HMAC key; both must hold the
   same value),
2. a running deriver (the events are deriver-driven), and
3. a publicly reachable URL for this receiver.

Delivery is best-effort with a **30 s timeout and no retries**, so a missed or
throttled delivery only delays cache freshness — bounded by
``memory.health.HEALTH_CACHE_TTL_SECONDS`` — and never correctness. With
``HONCHO_WEBHOOK_SECRET`` unset the receiver answers ``503`` ("webhooks
disabled") instead of accepting unsigned deliveries.

Output is JSON Lines, one object per tenant::

    {"tenant": "...", "action": "list", "workspace": "reqogniloom_...",
     "status": 200, "ok": true, "endpoints": [{"id": "...", "url": "..."}],
     "detail": null, "notes": ["...", "..."]}
"""
from __future__ import annotations

import ipaddress
import json
import socket
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from memory.honcho_backend import HonchoMemoryBackend
from memory.webhooks import SECRET_ENV_VAR
from persistence.models import Tenant

#: Request budget for one Honcho call. Matches the 30 s best-effort timeout the
#: spike documents for Honcho's own delivery; there are no retries either side.
HTTP_TIMEOUT_SECONDS = 30

#: Emitted on every line so an operator sees the operational preconditions of a
#: *delivery* without reading this docstring. Registration never checks them.
_NOTES = (
    (
        "delivery needs the Honcho server's own WEBHOOK_SECRET set AND a running "
        "deriver; registration succeeds even when nothing will ever be delivered"
    ),
    (
        "delivery is best-effort: 30 s timeout, no retries - a missed event only "
        "delays cache freshness (bounded by the health-cache TTL)"
    ),
    (
        f"the receiver answers 503 'webhooks disabled' while {SECRET_ENV_VAR} is "
        "unset on this deployment"
    ),
)

#: Ports a callback URL may name. Honcho signs and POSTs over HTTPS in every
#: documented deployment; ``80`` is accepted only because a reverse proxy may
#: terminate TLS and forward plain HTTP, and the URL registered here is the
#: *public* one in front of it either way.
_ALLOWED_PORTS = frozenset({80, 443})


def _validate_callback_url(url: str) -> str:
    """Return *url* when Honcho could POST to it, else raise ``CommandError``.

    Local pre-flight of the same shape Honcho rejects with ``422``, so the
    operator gets a reason instead of a status number (see the module docstring;
    this **rejects**, it does not warn). The address check is the security-
    relevant part: a callback URL pointing at ``127.0.0.1``/``10.0.0.0/8``/
    ``169.254.0.0/16``/``::1``/an unspecified or multicast address either fails
    at Honcho anyway or, worse, silently registers a target inside the
    deployment network. The host is resolved once, and **every** resolved address
    must be public — a name with one public and one private record is rejected.
    """
    value = str(url).strip()
    try:
        parts = urlsplit(value)
    except ValueError as exc:  # e.g. an unbalanced '[' in the netloc
        raise CommandError(f"--url is not a valid URL: {exc}") from exc
    if parts.scheme not in ("http", "https"):
        raise CommandError("--url must use http:// or https://")
    if parts.username or parts.password or "@" in parts.netloc:
        raise CommandError("--url must not carry userinfo (user:pass@)")
    try:
        host, port = parts.hostname, parts.port
    except ValueError as exc:  # out-of-range port, malformed IPv6 literal
        raise CommandError(f"--url has an invalid host or port: {exc}") from exc
    if not host:
        raise CommandError("--url must name a host")
    if port is not None and port not in _ALLOWED_PORTS:
        raise CommandError(
            f"--url must use port 80 or 443 (Honcho only POSTs to the public "
            f"callback), got {port}"
        )
    try:
        infos = socket.getaddrinfo(
            host,
            port or (443 if parts.scheme == "https" else 80),
            proto=socket.IPPROTO_TCP,
        )
    except OSError as exc:
        raise CommandError(f"--url host {host!r} does not resolve: {exc}") from exc
    for info in infos:
        literal = str(info[4][0]).split("%", 1)[0]
        try:
            addr = ipaddress.ip_address(literal)
        except ValueError as exc:  # pragma: no cover - getaddrinfo returns IPs
            raise CommandError(f"--url host {host!r} resolved to {literal!r}") from exc
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise CommandError(
                f"--url host {host!r} resolves to the non-public address "
                f"{literal} - Honcho refuses to POST into a private network"
            )
    return value


#: Documented Honcho answers, so a failure message names the cause instead of
#: just echoing a number.
_STATUS_HINTS = {
    401: "the Honcho API key is peer- or session-scoped; this route needs a "
    "workspace-scoped or admin key",
    403: "the Honcho API key is not allowed on this workspace route",
    409: "the per-workspace webhook limit is reached; delete an endpoint first",
    422: "the URL is not absolute, or it resolves to a private/loopback/"
    "link-local address - Honcho refuses to POST into your network",
}


def _request(
    method: str, url: str, *, api_key: str, payload: dict[str, Any] | None = None
) -> tuple[int, Any]:
    """Perform one JSON call against Honcho; ``(status, parsed_body_or_text)``.

    ``status`` is ``0`` when the request never produced an HTTP status (timeout,
    DNS, connection refused). Module-level so a test can substitute it and drive
    every documented branch without a live Honcho.
    """
    import requests  # lazy, matches this repo's HTTP convention

    try:
        response = requests.request(
            method,
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - any transport failure is reported, never retried
        return 0, f"{type(exc).__name__}: {exc}"
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, response.text


def _endpoints(body: Any) -> list[dict[str, Any]]:
    """Normalise a response into ``[{id, url}]``.

    Three shapes are accepted: the documented bare array (``--list``), a wrapping
    ``{"items": [...]}`` (a server-version difference must not turn a successful
    read into a traceback), and a **single** endpoint object as returned by the
    registration POST — without that last case ``--url`` printed ``endpoints:
    []`` even though it had just created one. Any other shape yields ``[]``: the
    response body is never echoed, so an unexpected payload is reported as an
    empty list rather than dumped into an operator's terminal.
    """
    if isinstance(body, dict):
        if isinstance(body.get("items"), list):
            rows = body["items"]
        elif "id" in body or "url" in body:
            rows = [body]
        else:
            rows = []
    else:
        rows = body
    if not isinstance(rows, list):
        return []
    return [
        {"id": row.get("id"), "url": row.get("url")}
        for row in rows
        if isinstance(row, dict)
    ]


class Command(BaseCommand):
    """List (default), register or delete the Honcho webhook callback URL."""

    help = (
        "Manage Honcho's webhook registration for the memory cache-invalidation "
        "receiver (Plan A T-A4-7). Default action is the read-only --list."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant",
            default=None,
            help="Limit the run to one tenant UUID (default: every tenant).",
        )
        action = parser.add_mutually_exclusive_group()
        action.add_argument(
            "--list",
            action="store_true",
            default=False,
            dest="list",
            help=(
                "List the registered webhooks and write nothing. This is also "
                "what happens when neither --url nor --delete is given."
            ),
        )
        action.add_argument(
            "--url",
            default=None,
            help=(
                "Register this callback URL. Must be absolute and publicly "
                "reachable: a non-http(s) scheme, userinfo, a port other than "
                "80/443 or a private/loopback/link-local address is rejected "
                "locally before the request is sent."
            ),
        )
        action.add_argument(
            "--delete",
            default=None,
            metavar="ENDPOINT_ID",
            dest="delete",
            help="Delete the endpoint with this id (see --list).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        url = options.get("url")
        endpoint_id = options.get("delete")
        if url is not None and not str(url).strip():
            raise CommandError("--url must not be empty")
        if endpoint_id is not None and not str(endpoint_id).strip():
            raise CommandError("--delete needs an endpoint id (see --list)")
        if url is not None:
            # Validate BEFORE the Honcho config lookup: a malformed URL is not
            # worth a round trip, and the error must name the URL, not the key.
            url = _validate_callback_url(url)

        # ``--list`` is an explicit selector, not a no-op default: argparse
        # forbids combining it with --url/--delete, and "no action flag at all"
        # means the same read-only list.
        if options.get("list"):
            action = "list"
        elif endpoint_id:
            action = "delete"
        elif url:
            action = "register"
        else:
            action = "list"
        base_url, api_key = HonchoMemoryBackend._resolve_config()
        if not base_url or not api_key:
            raise CommandError(
                "HONCHO_BASE_URL and HONCHO_API_KEY must be set (or configured "
                "through SystemMemorySettings) to talk to Honcho"
            )

        tenants = self._tenants(options.get("tenant"))
        failed = 0
        for tenant in tenants:
            workspace = HonchoMemoryBackend._honcho_workspace_id(tenant.id)
            status, body, detail = self._run(
                action,
                base_url=base_url.rstrip("/"),
                api_key=api_key,
                workspace=workspace,
                url=url,
                endpoint_id=endpoint_id,
            )
            ok = 200 <= status < 300
            if not ok:
                failed += 1
            line: dict[str, Any] = {
                "tenant": str(tenant.id),
                "action": action,
                "workspace": workspace,
                "status": status,
                "ok": ok,
                "endpoints": body,
                "detail": detail,
                "notes": list(_NOTES),
            }
            if not ok and status in _STATUS_HINTS:
                line["hint"] = _STATUS_HINTS[status]
            self.stdout.write(json.dumps(line))
        if failed:
            raise CommandError(
                f"{failed} of {len(tenants)} tenant(s) failed; see the emitted "
                "lines (nothing was retried)"
            )

    def _run(
        self,
        action: str,
        *,
        base_url: str,
        api_key: str,
        workspace: str,
        url: str | None,
        endpoint_id: str | None,
    ) -> tuple[int, list[dict[str, Any]] | None, str | None]:
        """Dispatch one action; returns ``(status, endpoints, detail)``."""
        collection = f"{base_url}/v3/workspaces/{quote(workspace, safe='')}/webhooks"
        if action == "list":
            status, body = _request("GET", collection, api_key=api_key)
            detail = None if 200 <= status < 300 else _detail(body)
            return status, _endpoints(body), detail
        if action == "register":
            status, body = _request(
                "POST", collection, api_key=api_key, payload={"url": url}
            )
            # 200 = already registered, 201 = newly created; both are success.
            return status, _endpoints(body), None if 200 <= status < 300 else _detail(body)
        status, body = _request(
            "DELETE",
            f"{collection}/{quote(str(endpoint_id), safe='')}",
            api_key=api_key,
        )
        return status, None, None if 200 <= status < 300 else _detail(body)

    @staticmethod
    def _tenants(tenant_id: str | None) -> list[Tenant]:
        """The tenants to act for — one explicit id, or every tenant.

        ``Tenant`` is the isolation boundary itself and carries no ``tenant`` FK,
        so its plain manager is the correct accessor (same as
        ``honcho_migrate_scopes``); nothing here reads tenant-scoped rows.
        """
        if tenant_id:
            try:
                parsed = UUID(str(tenant_id))
            except (TypeError, ValueError) as exc:
                raise CommandError(
                    f"--tenant must be a valid UUID, got {tenant_id!r}"
                ) from exc
            tenant = Tenant.objects.filter(id=parsed).first()
            if tenant is None:
                raise CommandError(f"unknown tenant: {tenant_id}")
            return [tenant]
        return list(Tenant.objects.order_by("id"))


def _detail(body: Any) -> str | None:
    """Short, non-leaking description of an unsuccessful response.

    Honcho's error bodies are short JSON; they are stringified and truncated so a
    chatty reverse proxy cannot flood the operator's terminal. The URL and the
    API key never appear here — neither is part of a Honcho error payload, and
    this function only ever receives the response body.
    """
    if body is None:
        return None
    text = body if isinstance(body, str) else json.dumps(body)
    return text[:500]


__all__ = ["HTTP_TIMEOUT_SECONDS", "Command"]
