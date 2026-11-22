"""Single source of truth for the ReqogniLoom MCP endpoint suffix.

Every shipped client config appends the same Streamable HTTP path to a base
URL. Keeping that append in one place prevents the four builders from drifting
apart (see ``dist/test_mcp_convention_parity.py``) and makes the base-URL
contract explicit: the value a user supplies is a *base URL without a path*.

Both interpolation forms the packages use (``${user_config.mcp_url}`` and
``{env:REQOGNILOOM_MCP_URL}``) end in ``}``, so normalization is a no-op for
them; the helper still accepts literal URLs so callers and tests share one
definition of the convention (issues #1961, #2049).
"""


def mcp_endpoint_url(base: str) -> str:
    """Return the canonical ``/mcp/`` endpoint for a ReqogniLoom base URL.

    A trailing slash and a trailing ``/mcp`` segment are stripped before the
    suffix is appended, so ``https://host``, ``https://host/``,
    ``https://host/mcp`` and ``https://host/mcp/`` all produce exactly
    ``https://host/mcp/`` instead of a doubled path.

    Args:
        base: Base URL without a path (a literal URL or an interpolation
            placeholder such as ``{env:REQOGNILOOM_MCP_URL}``).

    Returns:
        The base URL followed by exactly one ``/mcp/``.
    """
    normalized = base.rstrip("/")
    if normalized.endswith("/mcp"):
        normalized = normalized[: -len("/mcp")]
    return f"{normalized}/mcp/"
