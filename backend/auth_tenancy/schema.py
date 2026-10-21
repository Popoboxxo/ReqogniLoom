"""drf-spectacular extension for the project's DRF authenticator (#1388).

Every generated operation emitted
``could not resolve authenticator <AuthTenancyAuthentication> … Ignoring for
now`` because drf-spectacular had no :class:`OpenApiAuthenticationExtension`
for it. The operations still inherited the global ``SECURITY`` setting, but the
document never *proved* the auth contract at the operation level, and the
warning noise hid real schema gaps.

This extension resolves the authenticator to the existing ``BearerAuth``
scheme. The scheme name matches ``SPECTACULAR_SETTINGS["APPEND_COMPONENTS"]``
(and the global ``SECURITY`` requirement), so the published component keeps its
single authoritative description there; this class exists to stop the warning
and to make the per-operation security requirement explicit.

The credential contract is deliberately **not** restated as a second scheme:
``X-API-Key`` is a header on the same authenticated surface, not a separate
OpenAPI security scheme (it shares the precedence rule documented on
``BearerAuth`` in ``reqogniloom.settings``). Adding a second scheme here would
advertise two independent auth mechanisms where the server actually applies
one fail-closed precedence chain.
"""
from __future__ import annotations

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension

__all__ = ["AuthTenancyAuthenticationScheme"]


class AuthTenancyAuthenticationScheme(OpenApiAuthenticationExtension):
    """Map :class:`auth_tenancy.rest.AuthTenancyAuthentication` to ``BearerAuth``."""

    target_class = "auth_tenancy.rest.AuthTenancyAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        """Return the HTTP bearer scheme (must match ``APPEND_COMPONENTS``).

        ``register_on_missing`` keeps the richer description configured in
        ``SPECTACULAR_SETTINGS``; this definition is the self-contained fallback
        so the component is still correct if the settings entry is removed.
        """
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Bearer token authentication. Use 'Authorization: Bearer "
                "<token>' (JWT) or send an API key as 'X-API-Key: reqlo_…'. "
                "Precedence: X-API-Key, then Authorization: Bearer, then the "
                "httpOnly access cookie. A present-but-invalid credential is "
                "rejected (401) and is never skipped in favour of the next one."
            ),
        }
