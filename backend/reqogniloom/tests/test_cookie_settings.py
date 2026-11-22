"""R2 (systemaudit 2026-09-02): CSRF_COOKIE_SECURE must follow
AUTH_COOKIE_SECURE, not `not DEBUG` — a DEBUG=False deployment reachable
only over plain HTTP must not have the browser silently drop the CSRF
cookie (every UI write then 403s with "CSRF cookie not set").

Final review: SESSION_COOKIE_SECURE had the identical bug — on the same
plain-HTTP deployment the browser drops the session cookie too, which
breaks Django admin login."""
import importlib
import os

import pytest


# settings.py derives CSRF_COOKIE_SECURE / SESSION_COOKIE_SECURE from
# AUTH_COOKIE_SECURE only when those env vars are UNSET. Ambient values (e.g.
# the test stack's `env_file: .env` injecting `CSRF_COOKIE_SECURE=False`) shadow
# that default, so clear them before reloading unless a test sets them itself.
_COOKIE_SECURE_ENV_VARS = (
    "AUTH_COOKIE_SECURE",
    "SESSION_COOKIE_SECURE",
    "CSRF_COOKIE_SECURE",
)


def _reload_settings_with_env(monkeypatch, **env):
    # Drop every cookie-secure env var the caller did not explicitly set so the
    # AUTH-derived defaults take effect. monkeypatch records and restores each
    # change at teardown, so subsequent tests still see the original values.
    for key in _COOKIE_SECURE_ENV_VARS:
        if key not in env:
            monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import reqogniloom.settings as settings_module
    importlib.reload(settings_module)
    return settings_module


@pytest.mark.parametrize("auth_secure", ["True", "False"])
def test_csrf_cookie_secure_follows_auth_cookie_secure(monkeypatch, auth_secure):
    settings_module = _reload_settings_with_env(
        monkeypatch,
        AUTH_COOKIE_SECURE=auth_secure,
        DJANGO_ENV="production",
        DEBUG="False",
    )
    try:
        assert settings_module.CSRF_COOKIE_SECURE == (auth_secure == "True")
    finally:
        monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
        importlib.reload(settings_module)


@pytest.mark.parametrize("auth_secure", ["True", "False"])
def test_session_cookie_secure_follows_auth_cookie_secure(monkeypatch, auth_secure):
    settings_module = _reload_settings_with_env(
        monkeypatch,
        AUTH_COOKIE_SECURE=auth_secure,
        DJANGO_ENV="production",
        DEBUG="False",
    )
    try:
        assert settings_module.SESSION_COOKIE_SECURE == (auth_secure == "True")
    finally:
        monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
        importlib.reload(settings_module)


def test_session_cookie_secure_env_override_still_wins(monkeypatch):
    """An explicit SESSION_COOKIE_SECURE must beat the AUTH-derived default."""
    settings_module = _reload_settings_with_env(
        monkeypatch,
        AUTH_COOKIE_SECURE="False",
        SESSION_COOKIE_SECURE="True",
        DJANGO_ENV="production",
        DEBUG="False",
    )
    try:
        assert settings_module.SESSION_COOKIE_SECURE is True
    finally:
        monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
        monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
        importlib.reload(settings_module)
