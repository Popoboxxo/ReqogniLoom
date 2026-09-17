"""Rate limiting for the REST API (GitHub #269, findings 1 + 2).

Two problems are solved here.

**Finding 1 — authenticated endpoints were not throttled at all.** Only
``/auth/login/`` and ``/auth/refresh/`` carried a ``throttle_classes``; every
other endpoint accepted an unbounded request rate from a caller holding a
valid token, so scraping or a DoS via an ordinary account was free.
DRF's stock ``UserRateThrottle``/``AnonRateThrottle`` cannot be used as-is:
``AuthTenancyAuthentication`` returns ``auth_context.user_id`` (a ``UUID``) as
DRF's ``request.user`` surrogate, and the stock classes call
``request.user.is_authenticated`` — an ``AttributeError`` (HTTP 500) on a
``UUID``. The classes below read ``request.auth_context`` instead, which is the
project's actual identity carrier.

**Finding 2 — the login throttle was per-IP and counted successes.** Twelve
failed logins for bogus users exhausted the bucket for the *whole IP*, so the
next login with correct credentials — even for a different user — got a 429.
Behind a NAT or a reverse proxy that is a trivial auth-DoS against every user
of the API.

The chosen balance, and why:

* The primary counter is keyed on the **(client IP, username) pair**, not on
  either alone. Per-IP alone is the reported bug. Per-username alone is worse:
  an attacker could lock a known admin account out from a botnet, i.e. turn the
  brute-force defence into the DoS. The pair makes an attacker pay a fresh IP
  *per targeted account*, while an innocent user behind the same NAT keeps a
  private bucket.
* Only **failed** attempts are counted, and a successful login **clears the
  pair's counter**. Correct credentials can therefore never be refused because
  of someone else's — or one's own earlier — typos.
* A deliberately looser **per-IP** counter (``login_ip``) still caps credential
  *spraying*, where one host tries one password against many usernames and
  would otherwise never fill a per-pair bucket. It also only counts failures,
  and it is NOT cleared by a successful login — otherwise one valid account
  would be enough to reset the spray budget.

**Finding 3 (GitHub #944) — the ceilings are runtime-configurable.** Every rate
below is resolved through :func:`admin_ops.rate_limits.resolve_rate`, so an
admin can change a limit without a redeploy:

    tenant override  >  global override  >  settings/env  >  disabled

``DynamicRateThrottle`` re-reads the rate on every request (not at class
definition time), which is what makes that possible.

**Failure policy — fail-open on a cache outage.** The counters live in the
default cache (Redis in production). If that cache is unreachable the throttle
cannot count, and this module deliberately lets the request through rather than
raising or denying:

* the throttle is a DoS *mitigation*, not an authorization boundary —
  authentication, RBAC and API-key scoping are enforced independently and are
  unaffected by a cache outage;
* the cache is also what backs sessions and the rest of the framework, so a
  Redis outage is already an availability incident. Turning it into a hard
  API-wide 503 (fail-closed) would make the outage strictly worse, and would
  brick local development and the test suite whenever Redis hiccups.

The window is logged at WARNING on every refused-cache access, and the residual
risk is explicit: for as long as the cache is down, rate limits are not
enforced. The same policy governs ``mcp_server.throttling``, which delegates to
the classes here.

All rates are configurable via environment variables (see
``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']``); an empty value disables
the corresponding throttle.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured
from rest_framework.request import Request
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle

from auth_tenancy.context import AuthMethod

logger = logging.getLogger(__name__)

__all__ = [
    "AuthContextAnonRateThrottle",
    "AuthContextUserRateThrottle",
    # Public because mcp_server.throttling builds on it: the MCP transport
    # endpoints are plain Django views and need the same settings-driven,
    # test-overridable rate resolution rather than a second mechanism.
    "DynamicRateThrottle",
    "LoginIpRateThrottle",
    "LoginRateThrottle",
    "RefreshRateThrottle",
    "record_login_failure",
    "reset_login_throttle",
]


class DynamicRateThrottle(SimpleRateThrottle):
    """``SimpleRateThrottle`` that resolves its rate on every instantiation.

    DRF freezes ``SimpleRateThrottle.THROTTLE_RATES`` at *class definition*
    time, so a rate configured after the module was first imported is ignored.
    That silently breaks two things this project needs:

    * ``override_settings(REST_FRAMEWORK=...)`` in tests — the first test to
      import the module would pin the rate for the whole session, which is
      exactly the false-green trap a rate-limit regression test must avoid;
    * any future runtime reconfiguration of the operator-tunable
      ``API_RATE_LIMIT_*`` values.

    Reading ``api_settings`` inside ``get_rate`` costs one dict lookup per
    request and removes the import-order dependency entirely.

    Since #944 ``get_rate`` only describes the *settings* layer. The effective
    rate is applied per request by :meth:`_refresh_rate`, which layers the
    runtime overrides on top; ``allow_request`` calls it before delegating, so
    a limit changed through the admin API takes effect on the very next
    request.
    """

    def get_rate(self) -> str | None:
        """Current *settings* rate for ``self.scope``, honouring live overrides.

        This is precedence layer 3 only — the runtime layers are applied in
        :meth:`_refresh_rate`, which is what callers should rely on.
        """
        scope = getattr(self, "scope", None)
        if not scope:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must declare a `scope`."
            )
        try:
            return api_settings.DEFAULT_THROTTLE_RATES[scope]
        except KeyError as exc:
            raise ImproperlyConfigured(
                f"No throttle rate set for '{scope}' in DEFAULT_THROTTLE_RATES."
            ) from exc

    def _refresh_rate(self, request: Any) -> None:
        """Apply the *effective* rate (runtime override > settings) for this request.

        ``SimpleRateThrottle.__init__`` resolves the rate before the request is
        available, so ``self.rate`` there is always the settings layer. This
        method is the request-aware second pass; ``num_requests``/``duration``
        are re-parsed together with it so the three never disagree.

        Never raises: :func:`admin_ops.rate_limits.resolve_rate` already
        degrades to the settings value on any lookup failure, and a throttle
        must not be the thing that turns a cache blip into a 500.
        """
        scope = getattr(self, "scope", None)
        if not scope:
            return
        from admin_ops.rate_limits import resolve_rate

        rate = resolve_rate(scope, tenant_id=_tenant_id(request), default=self.rate)
        if rate != self.rate:
            self.rate = rate
            self.num_requests, self.duration = self.parse_rate(rate)

    def allow_request(self, request: Any, view: Any) -> bool:
        """Resolve the effective rate, then count — fail-open if the cache is down."""
        self._refresh_rate(request)
        try:
            return super().allow_request(request, view)
        except Exception:  # noqa: BLE001 - documented fail-open policy, see module docstring
            logger.warning(
                "rate limiting cache unavailable for scope %r; allowing request "
                "(fail-open) — limits are NOT enforced until the cache recovers",
                getattr(self, "scope", None),
                exc_info=True,
            )
            return True


def _tenant_id(request: Any) -> Optional[UUID]:
    """Tenant of the request, or ``None`` when it has no auth context.

    Anonymous REST requests (schema, health, login, refresh) and every MCP
    request reach the throttle without a tenant; they simply start at the
    global-override layer instead of the tenant one.
    """
    ctx = getattr(request, "auth_context", None)
    tenant_id = getattr(ctx, "tenant_id", None)
    return tenant_id if isinstance(tenant_id, UUID) else None


def _auth_identity(request: Any) -> str | None:
    """Rate-limit bucket identity of the caller, or ``None`` when anonymous.

    Identification order, per #944: **API key > authenticated user > IP** (the
    IP fallback lives in :class:`AuthContextAnonRateThrottle`).

    API keys come first on purpose. A key is the credential the caller actually
    presented, and one user may hand out several of them (a CI key and an agent
    key); keying those on the owning user would silently merge their budgets, so
    one noisy script could exhaust the interactive client's allowance — the same
    defect class #269 finding 2 describes for the login endpoint. It also makes
    per-key ceilings observable, which is what the MCP side already does.

    Sourced from ``request.auth_context`` (set by ``AuthTenancyAuthentication``)
    rather than from ``request.user``, which is a bare ``UUID`` here.
    """
    ctx = getattr(request, "auth_context", None)
    if ctx is None:
        return None

    if getattr(ctx, "auth_method", None) == AuthMethod.API_KEY:
        api_key_id = getattr(ctx, "api_key_id", None)
        if api_key_id is not None:
            return f"key:{api_key_id}"

    user_id = getattr(ctx, "user_id", None)
    return f"user:{user_id}" if user_id is not None else None


class AuthContextUserRateThrottle(DynamicRateThrottle):
    """Per-caller cap for every authenticated endpoint (#269 finding 1).

    Returns ``None`` (= not applicable) for anonymous requests so
    :class:`AuthContextAnonRateThrottle` handles those; the two are listed
    together in ``DEFAULT_THROTTLE_CLASSES`` and are mutually exclusive per
    request.
    """

    scope = "user"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        ident = _auth_identity(request)
        if ident is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AuthContextAnonRateThrottle(DynamicRateThrottle):
    """Per-IP cap for unauthenticated requests (schema, health, login page).

    .. note:: DRF runs authentication and permission checks *before*
       throttling, so a request rejected with 401/403 never reaches this class.
       It therefore protects the genuinely public endpoints; brute-force
       against credentials is covered by :class:`LoginRateThrottle`, which is
       attached to the login view itself.
    """

    scope = "anon"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        if _auth_identity(request) is not None:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class _FailureCountingThrottle(DynamicRateThrottle):
    """A throttle whose bucket is filled explicitly, not by every request.

    ``SimpleRateThrottle.allow_request`` records the request it is checking.
    That is wrong for credential endpoints: it makes *successful* logins
    consume the brute-force budget, which is half of #269 finding 2. Here
    ``allow_request`` only *reads* the history; the view calls
    :meth:`record_failure` after it knows the credentials were bad, and
    :meth:`reset` after a success.
    """

    def allow_request(self, request: Request, view: Any) -> bool:
        """Deny when the bucket for this request's key is already full."""
        self._refresh_rate(request)
        if self.rate is None:
            return True

        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True

        history = self._recent_history(self.key)
        if history is None:
            # Cache unavailable - fail open (see the module docstring).
            return True
        self.history = history
        self.now = self.timer()
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        # NOTE: deliberately no throttle_success() — see the class docstring.
        return True

    def _recent_history(self, key: str) -> list[float] | None:
        """Cached timestamps for *key*, minus the ones outside the window.

        Returns ``None`` when the cache could not be read at all, which every
        caller treats as "fail open" — see the module docstring for why letting
        the request through is the safer default for this project. It is worth
        distinguishing from ``[]``: an empty history means "no failures
        recorded", which with a ``0/min`` rate is already a refusal, whereas an
        unreadable history must never be.
        """
        try:
            history = list(self.cache.get(key, []))
        except Exception:  # noqa: BLE001 - documented fail-open policy
            logger.warning(
                "rate limiting cache unavailable for scope %r; cannot read "
                "failure bucket (fail-open)",
                getattr(self, "scope", None),
                exc_info=True,
            )
            return None
        now = self.timer()
        while history and history[-1] <= now - self.duration:
            history.pop()
        return history

    def _cache_set(self, key: str, history: list[float]) -> None:
        """Best-effort counter write — a cache outage must not 500 a login."""
        try:
            self.cache.set(key, history, self.duration)
        except Exception:  # noqa: BLE001 - documented fail-open policy
            logger.warning(
                "rate limiting cache unavailable for scope %r; failed attempt "
                "not counted (fail-open)",
                getattr(self, "scope", None),
                exc_info=True,
            )

    def record_failure(self, request: Request, view: Any = None) -> None:
        """Charge one failed attempt against this request's bucket."""
        self._refresh_rate(request)
        if self.rate is None:
            return
        key = self.get_cache_key(request, view)
        if key is None:
            return
        history = self._recent_history(key)
        if history is None:
            return
        history.insert(0, self.timer())
        self._cache_set(key, history)

    def reset(self, request: Request, view: Any = None) -> None:
        """Clear this request's bucket (called after a successful login)."""
        self._refresh_rate(request)
        if self.rate is None:
            return
        key = self.get_cache_key(request, view)
        if key is not None:
            try:
                self.cache.delete(key)
            except Exception:  # noqa: BLE001 - documented fail-open policy
                logger.warning(
                    "rate limiting cache unavailable; could not clear bucket "
                    "for scope %r",
                    getattr(self, "scope", None),
                    exc_info=True,
                )

    def wait(self) -> float | None:
        """Seconds until the oldest recorded failure leaves the window."""
        if self.rate is None or not getattr(self, "history", None):
            return None
        remaining = self.duration - (self.timer() - self.history[-1])
        return max(remaining, 1.0)


def _username_digest(request: Any) -> str:
    """Stable, cache-key-safe digest of the submitted username.

    Hashed rather than embedded verbatim so the key stays within the character
    and length limits of every cache backend, and so a cache dump does not read
    like a user directory. Lower-cased because usernames are matched
    case-insensitively at login.
    """
    data = getattr(request, "data", None)
    username = data.get("username") if isinstance(data, dict) else None
    if not isinstance(username, str):
        username = ""
    return hashlib.sha256(username.strip().lower().encode("utf-8")).hexdigest()[:32]


class LoginRateThrottle(_FailureCountingThrottle):
    """Per-(IP, username) cap on *failed* logins (#72, reworked for #269).

    See the module docstring for why the key is the pair and not either half.
    """

    scope = "login"

    def get_cache_key(self, request: Request, view: Any = None) -> str | None:
        ident = f"{self.get_ident(request)}:{_username_digest(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginIpRateThrottle(_FailureCountingThrottle):
    """Looser per-IP cap on *failed* logins — anti credential-spraying (#269).

    Not cleared by a successful login: an attacker holding one valid account
    must not be able to refill the spray budget at will.
    """

    scope = "login_ip"

    def get_cache_key(self, request: Request, view: Any = None) -> str | None:
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class RefreshRateThrottle(DynamicRateThrottle):
    """#135: rate-limit the public refresh endpoint.

    Unlike login this stays a plain per-IP counter over *all* requests: the
    endpoint carries no username, its identity comes from an httpOnly cookie,
    and a legitimate client refreshes at most a few times per hour — so there
    is no false-lockout scenario of the kind #269 finding 2 describes.
    """

    scope = "refresh"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


#: Throttles charged when a login attempt fails.
_LOGIN_FAILURE_THROTTLES = (LoginRateThrottle, LoginIpRateThrottle)


def record_login_failure(request: Request) -> None:
    """Charge a failed login against the per-pair and per-IP buckets."""
    for throttle_cls in _LOGIN_FAILURE_THROTTLES:
        throttle_cls().record_failure(request)


def reset_login_throttle(request: Request) -> None:
    """Clear the per-(IP, username) bucket after a successful login.

    The per-IP spray counter is intentionally left untouched.
    """
    LoginRateThrottle().reset(request)
