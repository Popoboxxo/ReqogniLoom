"""REST transparency field ``memory_injected`` (Plan A T-A1-5, ADR-024 AC-6).

Opens a :mod:`memory.injection_ledger` per request and, once the view has
produced its response, copies the ledger's contract into it. Registration in
``settings.MIDDLEWARE`` sits right after ``AuthenticationMiddleware`` so the
caller identity exists by the time anything downstream reads memory.

Why ``process_template_response`` and not ``__call__``: DRF's ``Response``
serialises ``.data`` only in ``Response.render()``, which Django calls *inside*
the middleware chain after the template-response hooks have run. Mutating
``.data`` in ``__call__`` (i.e. after ``get_response`` returned) would be too
late — the JSON is already written. The hook therefore runs while ``render()``
has not happened yet, and the injected key reaches the wire.

Additive by construction: only a ``dict`` body on a 2xx response, and only when
the ledger recorded at least one entry. A list payload, an error response or a
request that never touched memory stays byte-identical (Plan A riser
"memory_injected per Middleware verändert Response-Bodies"). Non-DRF responses
have no ``.data`` and are untouched too.
"""
from __future__ import annotations

from typing import Any, Callable

from memory.injection_ledger import current_ledger, open_ledger

#: Response key carrying the contract; documented in Plan A T-A1-5.
CONTRACT_KEY = "memory_injected"


class MemoryInjectionLedgerMiddleware:
    """Attach the request's memory-injection ledger to 2xx dict responses."""

    def __init__(self, get_response: Callable[[Any], Any]) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        # The ledger stays open for the whole view call, so entries recorded
        # several layers down (resolve_and_render -> build_memory_context) are
        # collected here. process_template_response runs inside get_response
        # and therefore still sees it.
        with open_ledger():
            return self.get_response(request)

    def process_template_response(self, request: Any, response: Any) -> Any:
        """Inject ``memory_injected`` into a 2xx DRF ``dict`` response."""
        ledger = current_ledger()
        if ledger is None:
            return response
        contract = ledger.as_contract()
        if contract is None:
            return response

        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int) or not 200 <= status_code < 300:
            return response

        data = getattr(response, "data", None)
        if not isinstance(data, dict):
            return response
        # Never overwrite a payload that already carries the key (a service may
        # report its own, more precise contract).
        if CONTRACT_KEY in data:
            return response
        data[CONTRACT_KEY] = contract
        return response


__all__ = ["CONTRACT_KEY", "MemoryInjectionLedgerMiddleware"]
