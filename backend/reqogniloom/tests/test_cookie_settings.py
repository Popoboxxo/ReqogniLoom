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


def _reload_settings_with_env(monkeypatch, **env):
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
