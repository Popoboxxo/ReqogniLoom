"""Production-hardening startup checks (plans P1.1 / P1.3 / P2.9, 2026-11-25 REST/MCP review).

WHY THIS MODULE EXISTS
----------------------
Findings M-1 (real secrets / trivial admin password), M-2 (auth cookies without
``Secure``), M-3 (``localhost`` in the CORS/CSRF allowlist) and M-5 (no
API-key pepper) were previously *documented only* — a long comment block in
``.env.example``. Nothing verified any of it, so a production deployment could
run with ``SYSTEM_ADMIN_PASSWORD=admin``, non-``Secure`` cookies and a
``localhost`` allowlist while every health probe answered 200.

These checks are registered from ``RestApiConfig.ready`` and therefore run in
``manage.py check``, ``runserver`` and the one-shot ``migrate`` container: the
configuration gap is reported before the first request, in the same place the
existing ``rest_api.E001`` throttle check already fails fast.

SEVERITY POLICY — deliberate, not an oversight
----------------------------------------------
``reqogniloom.E001`` / ``E002`` (the API-key pepper) are **errors**. P1.3 exists
so a production deployment is not shippable without the pepper: both deployment
paths (``bash scripts/setup.sh`` and ``.env.example``) know how to provide one,
and a missing pepper has no legitimate production interpretation — it is not a
policy choice, it is an unnoticed omission. In dev/test the checks are inert
(``is_production_context`` is False), so nothing gets harder to start locally.

SCOPE OF THAT ENFORCEMENT — stated precisely
-------------------------------------------
An ``Error`` from a system check blocks every process that **runs** Django
system checks: ``manage.py check``, ``runserver`` and the one-shot ``migrate``
container all abort on one, which covers the documented deployment paths and
puts the failure before the first request. It does **not** make "production
without a pepper impossible": a bare ASGI/gunicorn start that never runs a check
step (e.g. ``gunicorn reqogniloom.asgi:application`` without a preceding
``manage.py check``) would come up unpeppered. That is a documented residual
risk (``docs/runbooks/secret-rotation.md`` §2), not a guarantee, and the honest
wording matters more than a stronger claim: an operator who believes the check
is airtight will not look for the check-less start.

Deliberately NOT enforced at runtime: ``hash_api_key`` must keep hashing without
a pepper. ``api_key_hash_candidates`` calls it to verify the LEGACY
``sha256:`` form, so a runtime refusal would break API-key authentication for
every existing deployment instead of failing its startup — a configuration
warning turned into a login outage. ``auth_tenancy.services.mfa`` hashes
recovery codes through the same helper. The startup check is the enforcement
point on purpose; do not "fix" this in the hashing helper.

``W010``–``W014`` are **warnings** because the bundled Compose stack
*deliberately* supports production mode without TLS termination — see the
``AUTH_COOKIE_SECURE`` / ``CSRF_COOKIE_SECURE`` / ``SECURE_SSL_REDIRECT``
comment blocks in ``.env.example``: browsers silently drop a ``Secure`` cookie
over plain ``http://``, so forcing those flags (or HSTS) would break the
documented HTTP-only quickstart and abort ``migrate`` on a configuration that
is intentionally supported. ``SECURITY_STRICT_PRODUCTION_CHECKS=True``
escalates the five warnings to ``reqogniloom.E010``–``E014`` for hardened
deployments and CI. It must never default to True: that would turn the
supported HTTP-only mode into a startup failure.

``W014`` (an empty ``CSP_POLICY``) is in that warning group for the same
reason, not because an empty policy is harmless: ``settings.CSP_POLICY`` ships
a non-empty restrictive default, so an empty value is always an explicit
operator decision — and a decision that silently drops the header's protection.
It is reported rather than fatal because a *new* error must never block the
first ``migrate`` of an existing HTTP-only deployment that never touched CSP.

``W012``/``E012`` (a trivial ``SYSTEM_ADMIN_PASSWORD``) is the exception inside
that group: an EMPTY value is *not* a finding, because empty is the desired end
state (no admin provisioned, and the state a deployment reaches after
bootstrap). Only a non-empty trivial/placeholder value is reported — that one
does abort ``migrate`` on a fresh database, which is why it may escalate.

SECRET HYGIENE
--------------
Every message names the *variable*, never its value. These strings land in
container logs, CI output and bug reports; a secret echoed by a startup warning
is a worse outcome than the misconfiguration being reported.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings as django_settings
from django.core.checks import Error, Warning, register

from auth_tenancy.services.bootstrap_password import (
    bootstrap_password_rejection_reason,
)

#: Code emitted when ``API_KEY_PEPPER`` is empty/blank in production.
E001_API_KEY_PEPPER_MISSING = "reqogniloom.E001"
#: Code emitted when ``API_KEY_PEPPER`` is set but too weak / a placeholder.
E002_API_KEY_PEPPER_WEAK = "reqogniloom.E002"

#: Cookie flags that must be ``Secure`` behind TLS.
COOKIE_SECURE_SETTINGS: tuple[str, ...] = (
    "AUTH_COOKIE_SECURE",
    "CSRF_COOKIE_SECURE",
    "SESSION_COOKIE_SECURE",
)

#: Origin allowlists that must not fall back to a loopback host in production.
ORIGIN_SETTINGS: tuple[str, ...] = ("CORS_ALLOWED_ORIGINS", "CSRF_TRUSTED_ORIGINS")

#: Hostnames that only make sense for a local development deployment. Matched
#: against the parsed, lowercased *hostname* of each origin — never as a
#: substring, which both missed ``http://[::1]:5173`` and flagged
#: ``https://mylocalhost.example``.
LOOPBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

_REGISTERED = False


def is_production_context(
    django_env: str | None = None, settings_module: str | None = None
) -> bool:
    """Decide whether the production-only checks apply to this process.

    Delegates to ``reqogniloom.settings._is_production_secret_context`` — the
    single established rule (``DJANGO_ENV`` not in
    ``{development, dev, local, test}`` **and** a settings module that is not
    ``settings_test``). Duplicating that rule here would let the two drift, and
    ``settings_test`` must stay exempt because CI runs ``manage.py check``
    against it.

    Args:
        django_env: Override for ``settings.DJANGO_ENV`` (tests).
        settings_module: Override for ``DJANGO_SETTINGS_MODULE`` (tests).

    Returns:
        True in a production context, False in dev/test.
    """
    # Imported lazily: this module is imported from ``RestApiConfig.ready``,
    # i.e. while the app registry is being populated. A module-level import of
    # the settings module would be a needless import cycle risk, and the lazy
    # form keeps the check callable from a plain unit test.
    from reqogniloom import settings as project_settings

    if django_env is None:
        django_env = str(getattr(django_settings, "DJANGO_ENV", "production") or "production")
    if settings_module is None:
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    return bool(
        project_settings._is_production_secret_context(django_env, settings_module)
    )


def _is_weak_secret(value: str) -> bool:
    """Reuse the shared weak-secret rule (``<32`` chars or a placeholder marker).

    Deliberately not a second marker list: ``reqogniloom.settings`` already owns
    the definition used for ``SECRET_KEY`` / ``AUTH_JWT_SECRET``.
    """
    from reqogniloom import settings as project_settings

    return bool(project_settings._is_weak_secret(value))


def _strict() -> bool:
    """True when ``SECURITY_STRICT_PRODUCTION_CHECKS`` escalates to errors."""
    return bool(getattr(django_settings, "SECURITY_STRICT_PRODUCTION_CHECKS", False))


def _finding(
    message: str, hint: str, *, warning_id: str, error_id: str
) -> Error | Warning:
    """Build the diagnostic for ``warning_id``, escalated to ``error_id`` if strict."""
    if _strict():
        return Error(message, hint=hint, id=error_id)
    return Warning(message, hint=hint, id=warning_id)


# ---------------------------------------------------------------------------
# P1.3 — API-key pepper (M-5): errors, always
# ---------------------------------------------------------------------------


def check_api_key_pepper(app_configs: Any = None, **kwargs: Any) -> list[Error]:
    """Require a non-empty, non-placeholder ``API_KEY_PEPPER`` in production.

    The pepper is a server-side HMAC key for the stored API-key hashes: without
    it a database dump is enough to test candidate keys offline. Legacy
    ``sha256:`` hashes keep working (the prefix distinguishes the variant), so
    an existing deployment does not have to re-issue every key on day one — but
    a *new* production deployment must not be able to opt out by accident.
    """
    if not is_production_context():
        return []

    pepper = str(getattr(django_settings, "API_KEY_PEPPER", "") or "").strip()
    if not pepper:
        return [
            Error(
                "API_KEY_PEPPER is not set in a production deployment "
                "(DJANGO_ENV=production).",
                hint=(
                    "Generate a value with `bash scripts/setup.sh` (it fills an "
                    "empty API_KEY_PEPPER) or with "
                    'python -c "import secrets; print(secrets.token_urlsafe(64))", '
                    "set API_KEY_PEPPER in the deployment environment and restart. "
                    "The pepper is the server-side key of the API-key hashes: "
                    "without it a stolen database dump alone is enough to test "
                    "candidate keys offline. Setting it peppers only NEWLY created "
                    "keys; existing keys keep working unpeppered until they are "
                    "rotated — and CHANGING it later invalidates every peppered key "
                    "(forced re-issue for all clients)."
                ),
                id=E001_API_KEY_PEPPER_MISSING,
            )
        ]

    if _is_weak_secret(pepper):
        return [
            Error(
                "API_KEY_PEPPER is set to a weak or placeholder value in a "
                "production deployment (minimum 32 characters, no "
                "change-me/placeholder/dev-secret markers).",
                hint=(
                    "Replace API_KEY_PEPPER with a value from "
                    "`bash scripts/setup.sh` or "
                    'python -c "import secrets; print(secrets.token_urlsafe(64))". '
                    "A guessable pepper restores exactly the offline-attack "
                    "window it is supposed to close. Rotating it invalidates every "
                    "peppered API key, so do it deliberately (see "
                    "docs/runbooks/secret-rotation.md)."
                ),
                id=E002_API_KEY_PEPPER_WEAK,
            )
        ]

    return []


# ---------------------------------------------------------------------------
# P1.1 — M-2: cookie flags / M-3: loopback origins / admin password / TLS
# ---------------------------------------------------------------------------


def check_secure_cookies(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """Warn (``W010``) about cookie flags that are not ``Secure`` in production."""
    if not is_production_context():
        return []

    findings: list[Error | Warning] = []
    for name in COOKIE_SECURE_SETTINGS:
        if bool(getattr(django_settings, name, False)):
            continue
        findings.append(
            _finding(
                f"{name} is False in a production deployment, so the cookie it "
                "controls is sent without the Secure flag and can leak over a "
                "plain-HTTP request.",
                hint=(
                    f"Set {name}=True once the app is reachable over HTTPS "
                    "(TLS-terminating reverse proxy in front). Keep it False only "
                    "for a plain-HTTP deployment: browsers silently drop a Secure "
                    "cookie over http://, so flipping it without TLS breaks login. "
                    "AUTH_COOKIE_SECURE, CSRF_COOKIE_SECURE and "
                    "SESSION_COOKIE_SECURE must MATCH each other — a mismatch makes "
                    "every UI write fail with a raw 403; GET /health/ reports it as "
                    "csrf_cookie_secure_matches_auth='mismatch'."
                ),
                warning_id="reqogniloom.W010",
                error_id="reqogniloom.E010",
            )
        )
    return findings


def _origin_hostname(origin: object) -> str:
    """Return the exact, lowercased hostname of one allowlist entry.

    ``CORS_ALLOWED_ORIGINS`` / ``CSRF_TRUSTED_ORIGINS`` entries are
    scheme + host [+ port] strings, but a scheme is not guaranteed (Django
    accepts a bare host), and ``urlsplit`` reads a bare ``host:port`` pair as
    ``scheme:path``. Prefixing ``//`` yields a netloc either way, so both
    ``http://[::1]:5173`` and ``localhost:5173`` resolve to their host.

    Returns ``""`` for an entry that carries no hostname; such an entry is
    never reported, because a value this check cannot parse is not evidence of
    a loopback origin.
    """
    text = str(origin).strip()
    if not text:
        return ""
    candidate = text if "://" in text else f"//{text}"
    try:
        return (urlsplit(candidate).hostname or "").lower()
    except ValueError:
        # A malformed IPv6 literal raises instead of parsing; treat it as "no
        # hostname" rather than failing the whole system check.
        return ""


def check_loopback_origins(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """Warn (``W011``) about ``localhost``/``127.0.0.1`` in a production allowlist."""
    if not is_production_context():
        return []

    findings: list[Error | Warning] = []
    for name in ORIGIN_SETTINGS:
        raw = getattr(django_settings, name, None) or []
        origins = raw.split(",") if isinstance(raw, str) else list(raw)
        hits = sorted(
            {
                host
                for origin in origins
                if (host := _origin_hostname(origin)) in LOOPBACK_HOSTS
            }
        )
        if not hits:
            continue
        findings.append(
            _finding(
                f"{name} still lists a loopback origin ({', '.join(hits)}) in a "
                "production deployment.",
                hint=(
                    f"Replace the loopback entries in {name} with the deployment's "
                    "real browser origin(s) — scheme + host + port, e.g. "
                    "https://app.example.com. The bundled values are development "
                    "defaults: an allowlist that accepts localhost also accepts "
                    "anything running on the server host or reachable through a "
                    "local tunnel."
                ),
                warning_id="reqogniloom.W011",
                error_id="reqogniloom.E011",
            )
        )
    return findings


def check_system_admin_password(
    app_configs: Any = None, **kwargs: Any
) -> list[Error | Warning]:
    """Warn (``W012``) about a trivial non-empty ``SYSTEM_ADMIN_PASSWORD``.

    Read from the environment rather than from ``django.conf.settings``: the
    variable is consumed by ``bootstrap_admin`` / ``application.self_init`` and
    is deliberately not re-exported as a setting (it must not be importable from
    anywhere that could log it).

    An EMPTY/unset variable produces **no finding at all**: empty means "no
    admin account is provisioned", and it is exactly the state a deployment
    reaches after bootstrap (the account exists, the variable is removed). The
    template ships it empty and ``bash scripts/setup.sh`` fills it on the
    recommended path, so treating empty as a problem would warn on the
    documented end state and — under ``SECURITY_STRICT_PRODUCTION_CHECKS`` —
    escalate it to ``E012`` and abort ``migrate`` for a deployment that is
    already correct.

    Only a NON-EMPTY value that is trivial/placeholder is reported. That is a
    real defect: the bootstrap paths refuse it fail-closed, so the next
    ``migrate`` on a fresh database aborts. Under strict mode the finding
    escalates to ``E012``.

    The floor is the same one the bootstrap paths enforce
    (``auth_tenancy.services.bootstrap_password``), not the 32-character
    secret rule: this is a human-chosen login password, and a legitimate
    12-character passphrase must not produce a warning on every start.
    """
    if not is_production_context():
        return []

    value = (os.environ.get("SYSTEM_ADMIN_PASSWORD") or "").strip()
    if not value:
        # Empty is the desired end state (and the template default) — not a
        # finding, and deliberately not escalatable by the strict flag.
        return []

    reason = bootstrap_password_rejection_reason(value)
    if reason is None:
        return []

    return [
        _finding(
            f"SYSTEM_ADMIN_PASSWORD {reason} in a production deployment.",
            hint=(
                "The bootstrap paths refuse this value, so creating the admin "
                "(`migrate` on a fresh database) or "
                "`python manage.py bootstrap_admin --reset-password` aborts. "
                "Either set a value of at least 8 characters that is not a "
                "well-known default (admin, password, changeme, letmein, qwerty, "
                "...) and carries no change-me/placeholder marker — "
                "`bash scripts/setup.sh` generates one — or REMOVE the variable "
                "entirely: empty means no admin is provisioned and is the "
                "intended state once the account exists."
            ),
            warning_id="reqogniloom.W012",
            error_id="reqogniloom.E012",
        )
    ]


def check_tls_hardening(app_configs: Any = None, **kwargs: Any) -> list[Error | Warning]:
    """Warn (``W013``) about missing HTTPS redirect / HSTS in production.

    Two independent findings share the code, one per setting:

    * ``SECURE_SSL_REDIRECT=False`` — the reachable case in the bundled stack,
      which serves plain HTTP on purpose.
    * ``SECURE_HSTS_SECONDS<=0`` — reachable only when an operator *explicitly*
      sets it to 0 (or a nonsense value, which the defensive ``int()`` reads as
      0). In a production context ``DEBUG`` is forced False, so the settings
      default is ``31536000`` and this branch does not fire on an untouched
      deployment. It is deliberately kept: "HSTS off in production" is a real
      regression state, and the branch is what reports it. No separate code was
      invented for a state the settings default already prevents.
    """
    if not is_production_context():
        return []

    findings: list[Error | Warning] = []

    if not bool(getattr(django_settings, "SECURE_SSL_REDIRECT", False)):
        findings.append(
            _finding(
                "SECURE_SSL_REDIRECT is False in a production deployment, so "
                "plain-HTTP requests are served instead of being redirected to "
                "HTTPS.",
                hint=(
                    "Set SECURE_SSL_REDIRECT=True ONLY when a TLS-terminating "
                    "reverse proxy (nginx, Traefik, HAProxy) is in front and "
                    "forwards X-Forwarded-Proto: https. Enabling it without such a "
                    "proxy redirects every request to https:// where nothing is "
                    "listening, which makes the deployment unreachable — that is "
                    "why the bundled Compose stack leaves it False."
                ),
                warning_id="reqogniloom.W013",
                error_id="reqogniloom.E013",
            )
        )

    try:
        hsts_seconds = int(getattr(django_settings, "SECURE_HSTS_SECONDS", 0) or 0)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        hsts_seconds = 0
    if hsts_seconds <= 0:
        findings.append(
            _finding(
                "SECURE_HSTS_SECONDS is 0 in a production deployment, so browsers "
                "are not told to keep using HTTPS for this host.",
                hint=(
                    "Set SECURE_HSTS_SECONDS to e.g. 31536000 once HTTPS is the "
                    "only scheme the deployment serves. HSTS is cached by the "
                    "browser for the configured duration, so switching it on for a "
                    "deployment that is also reachable over plain HTTP will lock "
                    "those clients out — enable it together with "
                    "SECURE_SSL_REDIRECT."
                ),
                warning_id="reqogniloom.W013",
                error_id="reqogniloom.E013",
            )
        )

    return findings


def check_content_security_policy(
    app_configs: Any = None, **kwargs: Any
) -> list[Error | Warning]:
    """Warn (``W014``) about an empty/blank ``CSP_POLICY`` in production.

    ``reqogniloom.security_middleware.ContentSecurityPolicyMiddleware`` writes
    ``settings.CSP_POLICY`` verbatim into the ``Content-Security-Policy``
    response header, so an empty value reaches the browser as an empty policy —
    no ``default-src``, no ``frame-ancestors``, no restriction at all. Clickjacking
    and script-injection protection rely on that header (SEC-008 / #75).

    Empty is never the shipped state: ``settings.py`` applies the restrictive
    default ``default-src 'self'; frame-ancestors 'none'; base-uri 'self'`` when
    the variable is unset, so a blank value means somebody set the variable to an
    empty string. The finding is a warning (``E014`` under
    ``SECURITY_STRICT_PRODUCTION_CHECKS``) rather than an error so the documented
    HTTP-only stack keeps starting; it names no other setting and no value.
    """
    if not is_production_context():
        return []

    policy = str(getattr(django_settings, "CSP_POLICY", "") or "")
    if policy.strip():
        return []

    return [
        _finding(
            "CSP_POLICY is empty or blank in a production deployment, so the "
            "Content-Security-Policy response header carries no policy and "
            "restricts nothing.",
            hint=(
                "Remove the CSP_POLICY variable to inherit the shipped "
                "restrictive default (default-src 'self'; frame-ancestors 'none'; "
                "base-uri 'self'), or set CSP_POLICY to a policy of your own. The "
                "header is written by "
                "reqogniloom.security_middleware.ContentSecurityPolicyMiddleware "
                "from exactly this setting — an empty value is the only way to "
                "silently switch the protection off. The SPA's own CSP is served "
                "by the frontend container (frontend/nginx-security-headers.conf), "
                "not by this backend value; see "
                "docs/runbooks/production-hardening.md."
            ),
            warning_id="reqogniloom.W014",
            error_id="reqogniloom.E014",
        )
    ]


def register_production_security_checks() -> None:
    """Register the checks; called from ``RestApiConfig.ready``.

    Idempotent: ``ready`` can run more than once in a long-lived test process
    (app-registry reloads), and re-registering would duplicate every diagnostic.
    """
    global _REGISTERED
    if _REGISTERED:
        return
    for check in (
        check_api_key_pepper,
        check_secure_cookies,
        check_loopback_origins,
        check_system_admin_password,
        check_tls_hardening,
        check_content_security_policy,
    ):
        register(check)
    _REGISTERED = True


__all__ = [
    "check_api_key_pepper",
    "check_content_security_policy",
    "check_loopback_origins",
    "check_secure_cookies",
    "check_system_admin_password",
    "check_tls_hardening",
    "is_production_context",
    "register_production_security_checks",
]
