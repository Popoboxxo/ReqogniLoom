"""Production-hardening system checks (plan P1.1 / P1.3 / P2.9, 2026-11-25 review).

Pins three things that were previously only *documented* in ``.env.example``:

* the codes and their severities (E001/E002 are errors, W010-W014 are warnings,
  E010-E014 the strict-mode escalation),
* that the checks are inert outside a production context (dev/test must not get
  harder to start, and CI runs ``manage.py check`` against ``settings_test``),
* that no diagnostic ever echoes the configured value.

Because the suite runs under ``settings_test``, the production context is
injected per test by monkeypatching ``reqogniloom.checks.is_production_context``;
the delegation of that helper to the established settings rule is covered
separately with explicit arguments.
"""

from __future__ import annotations

import pytest
from django.core.checks import Error, Warning
from django.core.checks.registry import registry
from django.test import override_settings

from reqogniloom import checks

#: A value that satisfies the shared weak-secret rule (>= 32 chars, no marker).
STRONG_PEPPER = "9bOyYICG9xRhCczy8KyQ5pdacKtiV0trdzveCAYmZonCtdMcBAoX_69GjGUAYNtNx"


@pytest.fixture
def production(monkeypatch):
    """Force the production context for one test."""
    monkeypatch.setattr(checks, "is_production_context", lambda *a, **kw: True)


@pytest.fixture
def development(monkeypatch):
    """Force the non-production context for one test."""
    monkeypatch.setattr(checks, "is_production_context", lambda *a, **kw: False)


def _ids(diagnostics) -> list[str]:
    return [diagnostic.id for diagnostic in diagnostics]


# ---------------------------------------------------------------------------
# Context detection — delegated to the single established rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("django_env", "settings_module", "expected"),
    [
        ("production", "reqogniloom.settings", True),
        ("production", "", True),
        # CI runs `manage.py check` against the test module: must stay exempt.
        ("production", "reqogniloom.settings_test", False),
        ("production", "settings_test", False),
        ("development", "reqogniloom.settings", False),
        ("dev", "reqogniloom.settings", False),
        ("local", "reqogniloom.settings", False),
        ("test", "reqogniloom.settings", False),
    ],
)
def test_is_production_context_follows_the_settings_rule(
    django_env: str, settings_module: str, expected: bool
) -> None:
    assert checks.is_production_context(django_env, settings_module) is expected


def test_is_production_context_reads_the_live_settings(monkeypatch) -> None:
    """No-argument form: DJANGO_ENV from settings, module from the environment."""
    from django.conf import settings as django_settings

    monkeypatch.setattr(django_settings, "DJANGO_ENV", "development")
    assert checks.is_production_context() is False

    monkeypatch.setattr(django_settings, "DJANGO_ENV", "production")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "reqogniloom.settings_test")
    assert checks.is_production_context() is False

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "reqogniloom.settings")
    assert checks.is_production_context() is True


# ---------------------------------------------------------------------------
# E001 / E002 — API_KEY_PEPPER (P1.3, finding M-5)
# ---------------------------------------------------------------------------


def test_missing_pepper_is_an_error_in_production(production) -> None:
    with override_settings(API_KEY_PEPPER=""):
        diagnostics = checks.check_api_key_pepper()

    assert _ids(diagnostics) == ["reqogniloom.E001"]
    assert isinstance(diagnostics[0], Error)
    message = f"{diagnostics[0].msg} {diagnostics[0].hint}"
    assert "API_KEY_PEPPER" in message
    # Actionable remediation, no value.
    assert "scripts/setup.sh" in message
    assert "token_urlsafe(64)" in message


def test_blank_pepper_counts_as_missing(production) -> None:
    with override_settings(API_KEY_PEPPER="   "):
        assert _ids(checks.check_api_key_pepper()) == ["reqogniloom.E001"]


def test_weak_pepper_is_an_error_in_production(production) -> None:
    weak = "CHANGE-ME-pepper-please-generate-one-for-this-deployment"
    with override_settings(API_KEY_PEPPER=weak):
        diagnostics = checks.check_api_key_pepper()

    assert _ids(diagnostics) == ["reqogniloom.E002"]
    assert isinstance(diagnostics[0], Error)
    joined = f"{diagnostics[0].msg} {diagnostics[0].hint}"
    assert "API_KEY_PEPPER" in joined
    # The configured value is never echoed into a startup log/CI output.
    assert weak not in joined


def test_short_pepper_is_rejected(production) -> None:
    with override_settings(API_KEY_PEPPER="too-short-to-be-a-pepper"):
        assert _ids(checks.check_api_key_pepper()) == ["reqogniloom.E002"]


def test_strong_pepper_passes(production) -> None:
    with override_settings(API_KEY_PEPPER=STRONG_PEPPER):
        assert checks.check_api_key_pepper() == []


def test_pepper_is_not_required_outside_production(development) -> None:
    with override_settings(API_KEY_PEPPER=""):
        assert checks.check_api_key_pepper() == []


# ---------------------------------------------------------------------------
# W010 — cookie flags (P1.1, finding M-2)
# ---------------------------------------------------------------------------


@override_settings(
    AUTH_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SESSION_COOKIE_SECURE=False,
)
def test_non_secure_cookies_warn_per_setting(production) -> None:
    diagnostics = checks.check_secure_cookies()

    assert _ids(diagnostics) == ["reqogniloom.W010"] * 3
    assert all(isinstance(diagnostic, Warning) for diagnostic in diagnostics)
    named = " ".join(diagnostic.msg for diagnostic in diagnostics)
    for setting in (
        "AUTH_COOKIE_SECURE",
        "CSRF_COOKIE_SECURE",
        "SESSION_COOKIE_SECURE",
    ):
        assert setting in named


@override_settings(
    AUTH_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SESSION_COOKIE_SECURE=True,
)
def test_secure_cookies_pass(production) -> None:
    assert checks.check_secure_cookies() == []


@override_settings(
    AUTH_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SESSION_COOKIE_SECURE=False,
)
def test_cookie_check_is_inert_outside_production(development) -> None:
    """The bundled Compose stack runs production mode over plain HTTP."""
    assert checks.check_secure_cookies() == []


# ---------------------------------------------------------------------------
# W011 — loopback origins (P1.1, finding M-3)
# ---------------------------------------------------------------------------


@override_settings(
    CORS_ALLOWED_ORIGINS=["http://localhost:3000", "https://app.example.com"],
    CSRF_TRUSTED_ORIGINS=["http://127.0.0.1:5173"],
)
def test_loopback_origins_warn_per_allowlist(production) -> None:
    diagnostics = checks.check_loopback_origins()

    assert _ids(diagnostics) == ["reqogniloom.W011", "reqogniloom.W011"]
    messages = " ".join(diagnostic.msg for diagnostic in diagnostics)
    assert "CORS_ALLOWED_ORIGINS" in messages
    assert "CSRF_TRUSTED_ORIGINS" in messages
    assert "localhost" in messages
    assert "127.0.0.1" in messages


@override_settings(
    CORS_ALLOWED_ORIGINS=["https://app.example.com"],
    CSRF_TRUSTED_ORIGINS=["https://app.example.com"],
)
def test_public_origins_pass(production) -> None:
    assert checks.check_loopback_origins() == []


@override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:5173"])
def test_origin_check_is_inert_outside_production(development) -> None:
    assert checks.check_loopback_origins() == []


@override_settings(
    CORS_ALLOWED_ORIGINS=[
        "http://[::1]:5173",  # IPv6 loopback — missed by a substring match
        "https://mylocalhost.example",  # NOT loopback — flagged by a substring match
        "https://app.127.0.0.1.example",  # NOT loopback for the same reason
    ],
    CSRF_TRUSTED_ORIGINS=["https://app.example.com"],
)
def test_loopback_matcher_compares_the_exact_hostname(production) -> None:
    diagnostics = checks.check_loopback_origins()

    assert _ids(diagnostics) == ["reqogniloom.W011"]
    message = diagnostics[0].msg
    assert "::1" in message
    assert "mylocalhost.example" not in message
    assert "app.127.0.0.1.example" not in message


@override_settings(
    CORS_ALLOWED_ORIGINS=["https://app.example.com"],
    CSRF_TRUSTED_ORIGINS=["localhost:5173", "https://app.example.com"],
)
def test_bare_host_port_entry_still_matches(production) -> None:
    """A scheme-less allowlist entry is a host:port pair, not ``scheme:path``."""
    diagnostics = checks.check_loopback_origins()

    assert _ids(diagnostics) == ["reqogniloom.W011"]
    assert "localhost" in diagnostics[0].msg


# ---------------------------------------------------------------------------
# W012 — SYSTEM_ADMIN_PASSWORD (P1.1, finding M-1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "admin",
        "Password",
        "changeme",
        "qwerty",
        "short7!",  # 7 characters
        "CHANGE-ME-admin-password",
        "placeholder-admin-pw",
    ],
)
def test_trivial_admin_password_warns(production, monkeypatch, value: str) -> None:
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", value)

    diagnostics = checks.check_system_admin_password()

    assert _ids(diagnostics) == ["reqogniloom.W012"]
    joined = f"{diagnostics[0].msg} {diagnostics[0].hint}"
    assert "SYSTEM_ADMIN_PASSWORD" in joined
    # The hint must name removal as the legitimate alternative to a strong value
    # (empty = no admin provisioned, the state after bootstrap).
    assert "REMOVE the variable" in joined


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_empty_admin_password_is_not_a_finding(production, monkeypatch, value: str):
    """Empty is the DESIRED end state — no admin provisioned, not a defect.

    The template ships the variable empty and `scripts/setup.sh` fills it, so a
    finding here would warn on the documented `cp .env.example .env` path and
    (under strict mode) abort `migrate` for a deployment that deliberately
    removed the variable after bootstrap.
    """
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", value)

    assert checks.check_system_admin_password() == []


def test_unset_admin_password_is_not_a_finding(production, monkeypatch) -> None:
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)

    assert checks.check_system_admin_password() == []


def test_admin_password_warning_does_not_echo_the_value(production, monkeypatch):
    """Value-independence instead of a substring assert: the message names the
    marker category ("change-me/changeme/placeholder"), which would collide with
    a substring check for exactly those values."""
    messages = []
    for value in ("admin", "qwerty"):
        monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", value)
        messages.append(checks.check_system_admin_password()[0].msg)

    assert messages[0] == messages[1]
    assert "SYSTEM_ADMIN_PASSWORD" in messages[0]


@pytest.mark.parametrize(
    "value", ["initial-pw", "s3cure-bootstrap-pw", "s3lf-init-pw-2026"]
)
def test_operator_passwords_without_a_marker_are_accepted(
    production, monkeypatch, value: str
) -> None:
    """The floor is length + denylist, not the 32-character secret rule: these
    are the values the existing bootstrap tests use, and a human-chosen
    10-character password must not warn on every start."""
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", value)
    assert checks.check_system_admin_password() == []


def test_admin_password_check_is_inert_outside_production(
    development, monkeypatch
) -> None:
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "admin")
    assert checks.check_system_admin_password() == []


# ---------------------------------------------------------------------------
# W013 — HTTPS redirect / HSTS
# ---------------------------------------------------------------------------


@override_settings(SECURE_SSL_REDIRECT=False, SECURE_HSTS_SECONDS=0)
def test_missing_tls_hardening_warns(production) -> None:
    diagnostics = checks.check_tls_hardening()

    assert _ids(diagnostics) == ["reqogniloom.W013", "reqogniloom.W013"]
    messages = " ".join(diagnostic.msg for diagnostic in diagnostics)
    assert "SECURE_SSL_REDIRECT" in messages
    assert "SECURE_HSTS_SECONDS" in messages


@override_settings(SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=31536000)
def test_configured_tls_hardening_passes(production) -> None:
    assert checks.check_tls_hardening() == []


@override_settings(SECURE_SSL_REDIRECT=False, SECURE_HSTS_SECONDS=0)
def test_tls_check_is_inert_outside_production(development) -> None:
    assert checks.check_tls_hardening() == []


# ---------------------------------------------------------------------------
# W014 — CSP_POLICY (P2.9, finding m-14)
# ---------------------------------------------------------------------------

#: The shipped default from ``settings.py`` — the state of an untouched deployment.
SHIPPED_CSP = "default-src 'self'; frame-ancestors 'none'; base-uri 'self'"


@override_settings(CSP_POLICY=SHIPPED_CSP)
def test_shipped_csp_default_is_not_a_finding(production) -> None:
    """An untouched deployment inherits the default and must stay quiet."""
    assert checks.check_content_security_policy() == []


@pytest.mark.parametrize("policy", ["", "   ", "\t\n"])
def test_blank_csp_warns(production, policy: str) -> None:
    with override_settings(CSP_POLICY=policy):
        diagnostics = checks.check_content_security_policy()

    assert _ids(diagnostics) == ["reqogniloom.W014"]
    assert isinstance(diagnostics[0], Warning)
    joined = f"{diagnostics[0].msg} {diagnostics[0].hint}"
    # Names the variable, the middleware that consumes it and the shipped default.
    assert "CSP_POLICY" in joined
    assert "ContentSecurityPolicyMiddleware" in joined
    assert SHIPPED_CSP in joined
    # The hint points at the binding checklist.
    assert "docs/runbooks/production-hardening.md" in joined


@override_settings(CSP_POLICY="default-src 'none'")
def test_widened_csp_policy_passes(production) -> None:
    """Any non-blank policy satisfies the check — it is not a policy validator."""
    assert checks.check_content_security_policy() == []


@pytest.mark.parametrize("policy", ["", "   "])
def test_csp_check_is_inert_outside_production(development, policy: str) -> None:
    """The bundled Compose stack runs production mode over plain HTTP."""
    with override_settings(CSP_POLICY=policy):
        assert checks.check_content_security_policy() == []


# ---------------------------------------------------------------------------
# Strict mode — W010-W014 escalate to E010-E014
# ---------------------------------------------------------------------------


@override_settings(
    SECURITY_STRICT_PRODUCTION_CHECKS=True,
    AUTH_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SESSION_COOKIE_SECURE=False,
)
def test_strict_mode_escalates_cookies(production) -> None:
    diagnostics = checks.check_secure_cookies()

    assert _ids(diagnostics) == ["reqogniloom.E010"] * 3
    assert all(isinstance(diagnostic, Error) for diagnostic in diagnostics)


@override_settings(
    SECURITY_STRICT_PRODUCTION_CHECKS=True,
    CORS_ALLOWED_ORIGINS=["http://localhost:3000"],
    CSRF_TRUSTED_ORIGINS=[],
)
def test_strict_mode_escalates_origins(production) -> None:
    assert _ids(checks.check_loopback_origins()) == ["reqogniloom.E011"]


@override_settings(SECURITY_STRICT_PRODUCTION_CHECKS=True)
def test_strict_mode_escalates_admin_password(production, monkeypatch) -> None:
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "admin")
    assert _ids(checks.check_system_admin_password()) == ["reqogniloom.E012"]


@override_settings(SECURITY_STRICT_PRODUCTION_CHECKS=True)
def test_strict_mode_does_not_escalate_an_empty_admin_password(
    production, monkeypatch
) -> None:
    """Removing the variable after bootstrap stays the documented safe state.

    Strict mode turns the W012 warning into an error; empty is not a warning, so
    it must not become an error either — otherwise the hardening flag would lock
    a correctly bootstrapped deployment out of `migrate`.
    """
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "")

    assert checks.check_system_admin_password() == []


@override_settings(
    SECURITY_STRICT_PRODUCTION_CHECKS=True,
    SECURE_SSL_REDIRECT=False,
    SECURE_HSTS_SECONDS=0,
)
def test_strict_mode_escalates_tls(production) -> None:
    assert _ids(checks.check_tls_hardening()) == ["reqogniloom.E013"] * 2


@override_settings(SECURITY_STRICT_PRODUCTION_CHECKS=True)
def test_strict_mode_escalates_csp(production) -> None:
    with override_settings(CSP_POLICY=""):
        diagnostics = checks.check_content_security_policy()

    assert _ids(diagnostics) == ["reqogniloom.E014"]
    assert isinstance(diagnostics[0], Error)


@override_settings(SECURITY_STRICT_PRODUCTION_CHECKS=True, CSP_POLICY=SHIPPED_CSP)
def test_strict_mode_keeps_the_shipped_csp_quiet(production) -> None:
    """The flag escalates findings; it must not invent one for a correct setup."""
    assert checks.check_content_security_policy() == []


@override_settings(SECURITY_STRICT_PRODUCTION_CHECKS=False)
def test_pepper_errors_are_not_affected_by_the_strict_flag(production) -> None:
    """E001/E002 are unconditional: the flag only escalates warnings."""
    with override_settings(API_KEY_PEPPER=""):
        assert _ids(checks.check_api_key_pepper()) == ["reqogniloom.E001"]


# ---------------------------------------------------------------------------
# Wiring — the checks are actually registered by the app config
# ---------------------------------------------------------------------------


def test_checks_are_registered_by_the_app_config() -> None:
    registered = set(registry.registered_checks)
    for check in (
        checks.check_api_key_pepper,
        checks.check_secure_cookies,
        checks.check_loopback_origins,
        checks.check_system_admin_password,
        checks.check_tls_hardening,
        checks.check_content_security_policy,
    ):
        assert check in registered, f"{check.__name__} is not registered"


def test_registration_is_idempotent() -> None:
    # ``registered_checks`` is a set of callables (Django's check registry).
    before = set(registry.registered_checks)
    checks.register_production_security_checks()
    assert set(registry.registered_checks) == before
