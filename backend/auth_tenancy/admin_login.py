"""Admin-only wiring for the brute-force lockout (issue #1135) and the second
factor (issue #1308, Plan E / WP E3.5).

Three pieces live here and all of them are DELIBERATELY scoped to the Django
admin login path so that neither REST authentication nor its throttling state is
touched:

1. :class:`LockoutAdminAuthenticationForm` — a subclass of Django's
   ``AdminAuthenticationForm`` that checks :func:`admin_lockout.is_locked` at the
   **start** of ``clean()``, before ``super().clean()`` runs the password check
   (``confirm_login_allowed`` otherwise runs only *after* credentials succeed, so
   it is too late for a pre-auth gate). Wired via
   ``admin.site.login_form = MfaAdminAuthenticationForm``.

   :class:`MfaAdminAuthenticationForm` extends it with the TOTP/recovery-code
   check (WP E3.5). It is the form that is actually installed, so the lockout
   gate and the second factor cannot drift apart into two installed forms.

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
from django.forms import CharField, TextInput

from auth_tenancy import admin_lockout
from auth_tenancy.services.mfa import MfaError, MfaService

logger = logging.getLogger(__name__)

__all__ = [
    "LockoutAdminAuthenticationForm",
    "MfaAdminAuthenticationForm",
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

#: Shown when the password was correct but the second factor could not be
#: verified. Deliberately ONE generic message for every cause — wrong code,
#: replayed code, locked device, account deactivated mid-flow *and* "this
#: account has no device at all". Security review F4: the previous pair of
#: messages told a password holder whether a device exists, which is a
#: targeting oracle ("this account is not protected — enroll your own device"
#: is not reachable here, but "no device" still confirms the account is
#: half-configured). The caller already proved the password, so nothing about
#: the stored factor should leak either.
MFA_INVALID_MESSAGE = "The second factor for this account could not be verified."


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


class MfaAdminAuthenticationForm(LockoutAdminAuthenticationForm):
    """Admin login form with a TOTP/recovery second factor (#1308, WP E3.5).

    Extends :class:`LockoutAdminAuthenticationForm` (issue #1135) instead of
    Django's form directly, so the pre-authentication lockout gate and the
    second factor apply to the *same* login: the lockout runs first, the
    password check second, the code check last.

    Why a form and not a middleware: Django's admin ``login()`` view signs the
    user in as soon as the form is valid, so the only place that can refuse the
    session *after* the password succeeded but *before* the session exists is
    ``clean()``.

    Failure handling mirrors Django's own ``authenticate()`` contract: a wrong
    code sends ``user_login_failed`` (with the username only — never the code),
    which is what feeds the ADR-021 lockout counter in
    :func:`_on_user_login_failed`. Without that signal five wrong codes per
    window would be free.

    The field is optional so a non-MFA login (``MFA_STAFF_ENFORCEMENT=off``, or
    ``optional`` without an enrolled device) keeps working unchanged; the code
    is only demanded when :meth:`MfaService.mfa_required` says so.
    """

    otp_code = CharField(
        required=False,
        label="Second factor code",
        widget=TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "autocapitalize": "characters",
                "spellcheck": "false",
            }
        ),
        help_text=(
            "Six-digit code from your authenticator app, or one of your recovery "
            "codes."
        ),
    )

    def clean(self):
        cleaned = super().clean()
        user = self.get_user()
        if user is None:
            # Wrong password / locked / inactive — the parent already answered.
            return cleaned

        service = MfaService()
        if not service.mfa_required(user):
            return cleaned

        if not service.is_enrolled(user):
            # ``required`` without a device: there is nothing to verify, and the
            # admin surface must not become a self-service enrollment path
            # (ENT-E7 = A / QR-S01). Answered with the SAME generic message as a
            # wrong code (security review F4) so a password holder cannot probe
            # whether the account has a device.
            self._reject(MFA_INVALID_MESSAGE, user)
            return cleaned

        code = (cleaned.get("otp_code") or "").strip()
        if not code:
            self._reject(MFA_INVALID_MESSAGE, user)
            return cleaned

        try:
            # One input for both factors (the page has room for one row): six
            # digits are a TOTP code, anything else is treated as a recovery
            # code — ``verify`` normalises and rejects it if it is neither.
            if code.isdigit() and len(code) == 6:
                service.verify(user, code=code)
            else:
                service.verify(user, recovery_code=code)
        except MfaError:
            self._reject(MFA_INVALID_MESSAGE, user)
        return cleaned

    def _reject(self, message: str, user) -> None:
        """Refuse the login, charge the failure counter, and raise.

        ``user_login_failed`` is emitted exactly as ``django.contrib.auth``'s
        ``authenticate()`` does on a bad password, so the existing
        (IP, username) lockout receiver counts a wrong *code* like a wrong
        password. The credentials dict is deliberately username-only: no code,
        no factor kind, nothing an operator log could leak.
        """
        user_login_failed.send(
            sender=self.__class__,
            credentials={"username": getattr(user, "get_username", lambda: "")()},
            request=getattr(self, "request", None),
        )
        # Defense in depth: ``get_user()`` must not hand a session-able user back
        # after the form was rejected.
        self.user_cache = None
        raise ValidationError(message)


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

    if admin.site.login_form in (None, LockoutAdminAuthenticationForm):
        # ``LockoutAdminAuthenticationForm`` is our own earlier wiring (#1135),
        # not a foreign form: upgrading it to the MFA-aware subclass is exactly
        # the intended supersession, not a clobber.
        admin.site.login_form = MfaAdminAuthenticationForm
    elif admin.site.login_form is not MfaAdminAuthenticationForm:
        # A foreign login_form is already installed (another AppConfig.ready or a
        # custom AdminSite). Do NOT silently clobber it — that would discard
        # whatever hardening it carries. Warn loudly so the operator knows the
        # brute-force gate and the second factor are NOT active for this admin
        # site.
        logger.warning(
            "admin login lockout/MFA: admin.site.login_form is already set to %r; "
            "the brute-force gate and the second factor were NOT installed — "
            "merge MfaAdminAuthenticationForm into that form (issue #1135, #1308)",
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
