"""Admin-only wiring for the brute-force lockout (issue #1135).

Three pieces live here and all of them are DELIBERATELY scoped to the Django
admin login path so that neither REST authentication nor its throttling state is
touched:

1. :class:`LockoutAdminAuthenticationForm` — a subclass of Django's
   ``AdminAuthenticationForm`` that checks :func:`admin_lockout.is_locked` at the
   **start** of ``clean()``, before ``super().clean()`` runs the password check
   (``confirm_login_allowed`` otherwise runs only *after* credentials succeed, so
   it is too late for a pre-auth gate). Wired via
   ``admin.site.login_form = LockoutAdminAuthenticationForm``.

2. :func:`_on_user_login_failed` / :func:`_on_user_logged_in` — receivers for
   ``django.contrib.auth.signals``. These signals fire for the REST login as
   well, so each receiver inspects ``request.path`` and returns immediately
   unless the request is an **admin login POST** (see :func:`_is_admin_login_request`).
   This guarantees a hard separation in both directions: REST failures never
   create/increment admin lockout rows, and an admin lockout never changes REST
   throttle behaviour.

3. :func:`install` — connects the receivers (once) and installs the custom
   login form. Called from ``AuthTenancyConfig.ready()``.
"""
from __future__ import annotations

import logging

from django.contrib import admin, messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.exceptions import ValidationError
from django.dispatch import receiver

from auth_tenancy import admin_lockout

logger = logging.getLogger(__name__)

__all__ = [
    "LockoutAdminAuthenticationForm",
    "install",
]

#: Message shown on the admin login page when a login is blocked. Plain and
#: generic on purpose: it must neither leak whether the username exists nor the
#: exact counter values.
LOCKOUT_MESSAGE = (
    "Too many failed login attempts. This account and IP address are "
    "temporarily locked. Please try again later."
)

#: Absolute admin login path prefix. The admin site is mounted at
#: ``/admin/`` (reqogniloom/urls.py). Used only to *scope* the shared auth
#: signals — never to authorize anything.
_ADMIN_PREFIX = "/admin/"


def _is_admin_login_request(request) -> bool:
    """True only for a POST to the Django admin login view.

    ``django.contrib.auth``'s ``user_login_failed`` / ``user_logged_in`` signals
    are emitted by whatever called ``authenticate()`` — the REST ``LoginView``
    and the admin both do. The lockout must react to the admin only, so this
    gate requires *all* of:

    * a request object with a path and a method,
    * ``POST`` (a GET merely renders the form),
    * a path under ``/admin/``,
    * and the resolved URL name ``admin:login`` — the last check makes a
      future ``/admin/...`` route that happens to authenticate something else
      fail closed rather than silently feed this lockout.

    Anything else (including ``/api/v1/auth/login/``) returns ``False``, which
    is what keeps REST behaviour untouched in both directions.
    """
    if request is None:
        return False
    path = getattr(request, "path", None)
    method = getattr(request, "method", None)
    if not path or method != "POST" or not path.startswith(_ADMIN_PREFIX):
        return False
    try:
        from django.urls import resolve

        match = resolve(path)
    except Exception:  # noqa: BLE001 - a resolver hiccup must never feed the lockout
        return False
    return match.view_name == "admin:login"


def _submitted_username(request) -> object:
    """Best-effort username from the admin request body (fallback for failures)."""
    post = getattr(request, "POST", None)
    if post is not None:
        try:
            return post.get("username")
        except Exception:  # noqa: BLE001 - defensive; never break the signal path
            return None
    return None


class LockoutAdminAuthenticationForm(AdminAuthenticationForm):
    """``AdminAuthenticationForm`` with a pre-authentication lockout gate.

    ``clean()`` checks the lock **before** delegating to the parent, so a locked
    pair is rejected without ever running the password check. On a blocked
    attempt the pair is *not* re-counted (recording is owned by the
    ``user_login_failed`` receiver, and ``super().clean()`` never runs, so no
    additional failure signal is emitted), a plaintext :class:`ValidationError`
    is raised for the form, a WARNING is logged, and a visible notice is added to
    the messages framework — none of which exposes the submitted username.
    """

    def clean(self):
        request = getattr(self, "request", None)
        if request is not None:
            client_ip = admin_lockout.resolve_client_ip(request)
            # The username field may fail its own (non-blocking) validation when
            # empty, so read it via cleaned_data with a raw-data fallback.
            raw_username = self.data.get("username") if self.data else None
            username = self.cleaned_data.get("username") or raw_username
            if admin_lockout.is_locked(client_ip, username):
                logger.warning(
                    "admin login blocked: lockout active for ip=%s digest=%s "
                    "— issue #1135",
                    client_ip,
                    admin_lockout.username_digest(username)[:8],
                )
                try:
                    messages.warning(request, LOCKOUT_MESSAGE)
                except Exception:  # noqa: BLE001 - message backend must not break the gate
                    logger.warning(
                        "admin login lockout: could not add messages notice",
                        exc_info=True,
                    )
                raise ValidationError(LOCKOUT_MESSAGE)
        return super().clean()


# The receivers are plain functions; ``install()`` connects them.
def _on_user_login_failed(sender, credentials, request=None, **kwargs) -> None:
    """Record an admin login failure on the (IP, username) lockout counter.

    Scoped to the admin login POST via :func:`_is_admin_login_request`; a REST
    ``/auth/login/`` failure returns immediately, so REST failures never touch
    the admin lockout table.
    """
    if not _is_admin_login_request(request):
        return
    client_ip = admin_lockout.resolve_client_ip(request)
    username = None
    if isinstance(credentials, dict):
        username = credentials.get("username")
    if not username:
        username = _submitted_username(request)
    admin_lockout.register_failure(client_ip, username)


def _on_user_logged_in(sender, request=None, user=None, **kwargs) -> None:
    """Reset the lockout counter after a successful admin login.

    Scoped to the admin login POST; a successful REST login never clears an
    admin lockout row (and vice versa is impossible — REST never writes one).
    """
    if not _is_admin_login_request(request):
        return
    client_ip = admin_lockout.resolve_client_ip(request)
    username = getattr(user, "get_username", lambda: None)() if user is not None else None
    admin_lockout.reset(client_ip, username)


_INSTALLED = False


def install() -> None:
    """Connect the signal receivers and install the custom admin login form.

    Idempotent and side-effect-safe before the app registry is ready: signal
    receivers are connected once (``weak=False`` so they survive without a
    module-level reference), and the form is only assigned when the admin site is
    instantiated. Called from ``AuthTenancyConfig.ready()``.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    if admin.site.login_form is None:
        admin.site.login_form = LockoutAdminAuthenticationForm
    elif admin.site.login_form is not LockoutAdminAuthenticationForm:
        # A foreign login_form is already installed (another AppConfig.ready or a
        # custom AdminSite). Do NOT silently clobber it — that would discard
        # whatever hardening it carries. Warn loudly so the operator knows the
        # brute-force gate is NOT active for this admin site.
        logger.warning(
            "admin login lockout: admin.site.login_form is already set to %r; "
            "the brute-force gate was NOT installed — merge "
            "LockoutAdminAuthenticationForm into that form (issue #1135)",
            admin.site.login_form,
        )

    user_login_failed.connect(
        _on_user_login_failed,
        dispatch_uid="auth_tenancy.admin_lockout.user_login_failed",
        weak=False,
    )
    user_logged_in.connect(
        _on_user_logged_in,
        dispatch_uid="auth_tenancy.admin_lockout.user_logged_in",
        weak=False,
    )
    _INSTALLED = True
